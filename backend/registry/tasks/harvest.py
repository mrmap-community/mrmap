import base64
import json
import os
import threading
import time
import traceback
from datetime import timedelta
from os import walk
from uuid import UUID, uuid4

from celery import Task, chord, shared_task, states
from celery.signals import worker_ready
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import OperationalError, transaction
from django.utils import timezone
from extras.tasks import SingletonTask
from kombu.exceptions import OperationalError as BrokerOperationalError
from lxml import etree
from lxml.etree import Error
from MrMap import celery_queues
from MrMap.celery import app
from MrMap.settings import FILE_IMPORT_DIR
from notify.enums import ProcessStatusEnum
from registry.enums.harvesting import (HarvestingPhaseEnum, LogLevelEnum,
                                       LogKindEnum)
from registry.exceptions.harvesting import InternalServerError
from registry.exceptions.service import CapabilitiesBackupMissing
from registry.ows_lib.client.exceptions import (InitialError,
                                                RedirectChainError)
from requests.exceptions import RequestException

logger = get_task_logger(__name__)


class HarvestingTask(Task):
    acks_late = True
    reject_on_worker_lost = True
    autoretry_for = (RequestException, OperationalError, BrokerOperationalError, InternalServerError)
    retry_backoff = True
    retry_backoff_max = 300
    retry_kwargs = {"max_retries": 10}

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """End a harvest whose tasks gave up instead of leaving it unfinished (#690).

        A page which keeps failing never completes the chord it belongs to, so the callback of that
        chord never runs and the job keeps waiting with `done_at = null` until some worker restart
        re-publishes the whole harvest. Ending the job through the existing abort path is what the
        alert of the catalogue, the harvest history and the notification of the background process
        already answer, so nothing of that needs a second implementation here.
        """
        harvesting_job_id = (kwargs or {}).get("harvesting_job_id")
        if harvesting_job_id is None:
            # a task which is not about one job can not end one
            return

        from registry.models.harvest import HarvestingJob  # avoid circular import errors

        try:
            with transaction.atomic():
                job = HarvestingJob.objects.select_for_update().filter(
                    pk=harvesting_job_id).first()
                if job is None or job.done_at is not None:
                    # the callback which completed or aborted the job already decided about it; a
                    # late failure of a task of it must not rewrite that
                    return
                start_position = (kwargs or {}).get("start_position")
                job.log(
                    description="task gave up" + (
                        f" on page start_position={start_position}"
                        if start_position is not None else ""),
                    extented_description=(
                        f"{self.name} failed after "
                        f"{getattr(self.request, 'retries', 0)} retries\n"
                        f"{type(exc).__name__}: {exc}"),
                    level=LogLevelEnum.ERROR.value,
                    # the loss of a stored document is an integrity error of
                    # the deployment, not an error of the remote (#1044); the
                    # uncategorized kind keeps it out of the remote-error
                    # reading of the harvest history
                    kind=(
                        None if isinstance(exc, CapabilitiesBackupMissing)
                        else LogKindEnum.REMOTE_ERROR.value),
                )
                job.phase = HarvestingPhaseEnum.ABORT.value
                job.fail_process(f"{type(exc).__name__}: {exc}")
                job.save(skip_history_when_saving=False)
        except Exception:
            # a failing harvest must not be answered with a broken worker
            logger.error(
                f"could not abort harvesting job {harvesting_job_id}: {traceback.format_exc()}")

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        """Remove the registered id of a task which reported in (#892).

        A task id is registered for the revocation of an abort, which only
        needs the work which could still be stopped: a task which ran to its
        end or gave up leaves no id behind, so the ids of a job stay bounded
        by its in-flight work instead of accumulating its whole backlog. A
        retry keeps the id - the task runs again under the same one - and a
        task which is not about one job never registered an id to begin with,
        the creation task of a job among them: its delivery id is the identity
        of the harvest for a redelivery of that message and stays registered.
        """
        if status not in (states.SUCCESS, states.FAILURE, states.REJECTED):
            return
        harvesting_job_id = (kwargs or {}).get("harvesting_job_id")
        if harvesting_job_id is None:
            return

        from registry.models.harvest import HarvestingJobTaskId  # avoid circular import errors

        try:
            HarvestingJobTaskId.objects.filter(
                job_id=harvesting_job_id, task_id=task_id).delete()
        except Exception:
            # bookkeeping must never be the reason a worker fails
            logger.error(
                f"could not remove the id {task_id} of harvesting job "
                f"{harvesting_job_id}: {traceback.format_exc()}")


class MetadataFileImportTask(HarvestingTask):
    """Base of the tasks which write stored metadata files to the database (#895).

    Building the client of the catalogue reads the stored capabilities
    document only (#1044), so a running import asks the remote nothing at
    all; the ``InitialError`` which a broken stored document can still raise
    when an advertised operation is missing stays retried here the way #895
    decided, so a file is redelivered with the backoff of the harvest
    instead of being lost to the marking below. A service whose stored
    document is gone from the storage is no catalogue hiccup: the
    ``CapabilitiesBackupMissing`` of its reads ends the run visibly instead
    of being paid per record.
    """

    autoretry_for = HarvestingTask.autoretry_for + (InitialError,)


# The queues a harvest publishes to (see the queue= of its tasks). The message
# a registered task id names can only sit in one of them, and the redis
# transport keys a queue by its plain name (#972). Since #970 the import
# backlog itself lives on HARVEST_IMPORT; the probe reads it like every other
# queue a harvest message of a registered id could wait on.
HARVEST_BROKER_QUEUES = (
    celery_queues.DEFAULT,
    celery_queues.DOWNLOAD,
    celery_queues.DB_ROUTINES,
    celery_queues.HARVEST_IMPORT,
)
# The keys the redis transport parks a message under once a worker has taken
# it out of the queue but not acked it yet (the driver_unacked_key /
# driver_index_key of kombu.transport.redis). Every harvest task acks late, so
# a message a worker is working stays here until the task reports in, and one
# whose worker died returns to its queue when the visibility timeout expires -
# which is why the queues plus these two keys are the whole broker-side life
# of a registered id (#972).
HARVEST_UNACKED_LIST_KEY = "unacked"
HARVEST_UNACKED_INDEX_KEY = "unacked_index"
# The message #970 must not publish a second time for one job while it still
# waits: the publish of the import chord, which recovery and the operator
# command use to resume a job. It is looked up by name because the publishing
# code does not know its task id in advance.
CHORD_PUBLISH_TASK_NAME = "registry.tasks.harvest.call_chord_md_metadata_file_to_db"
# How the queue keys are read: page by page, so a queue which is draining a
# real catalogue never has to be held in memory whole (#972).
HARVEST_BROKER_SCAN_PAGE = 500
# How long to wait for a worker to answer what it holds. The answer only
# reinforces the unacked keys above, so a worker which does not answer - the
# starting one at worker_ready never answers itself - must not make an answer
# of "no message" fail (#972).
HARVEST_WORKER_INSPECT_TIMEOUT = 0.5

# The files one worker has committed to the database but has not reported to
# the background process yet, per process: [steps, monotonic time of the last
# report of that process]. A harvest writes hundreds of thousands of files and
# the progress of all of them lives in the one row of the process; one UPDATE
# per file would serialize every import transaction behind the lock of that
# row (#958). So each worker counts its committed files itself and answers
# them in bulk - after HARVEST_IMPORT_PROGRESS_STEPS of them or after
# HARVEST_IMPORT_PROGRESS_SECONDS have passed, whichever comes first. The
# counts of a worker die with it; what it committed does not, and the chord
# rebuild of the recovery reads those from the durable backlog again
# (``reconcile_import_progress``).
_import_progress_pending = {}
_import_progress_lock = threading.Lock()
# The clock the coalescing waits by; the tests of #958 wind this one forward
# instead of letting the worker age for real.
_import_progress_clock = time.monotonic


def _report_imported_steps(background_process_pk, steps):
    """Write one coalesced bulk increment of imported files to the process.

    The bookkeeping of a harvest must never be the reason a worker fails: the
    progress of a process which is gone, aborted or unreachable is simply not
    reported, the import of the files it names is the work that matters.
    """
    from notify.models import BackgroundProcess  # avoid circular import errors

    try:
        BackgroundProcess.objects.report(
            background_process_pk, ProcessStatusEnum.RUNNING,
            steps_done=steps)
    except Exception:
        logger.error(
            f"could not report {steps} imported files of background process "
            f"{background_process_pk}: {traceback.format_exc()}")


def credit_import_progress(background_process_pk, steps=1):
    """Count committed files of a harvest towards the progress of its process.

    The credit is worker-local; the increment of the process row happens here
    only once the coalesced batch is due: the configured amount of steps has
    piled up or the configured age of the oldest unreported step passed. A
    retry of a task never credits a file it did not commit - the callers credit
    per committed file, so a redelivery of a chunk which finds the rows of its
    ids gone counts nothing (#958).
    """
    if not background_process_pk or steps <= 0:
        return
    threshold = max(1, int(getattr(
        settings, "HARVEST_IMPORT_PROGRESS_STEPS", 200)))
    interval = max(0, int(getattr(
        settings, "HARVEST_IMPORT_PROGRESS_SECONDS", 30)))
    key = str(background_process_pk)
    with _import_progress_lock:
        entry = _import_progress_pending.setdefault(key, [0, _import_progress_clock()])
        entry[0] += steps
        # an interval of 0 disables the time trigger alone - the step
        # threshold still coalesces; a negative one is the same 0
        due = entry[0] >= threshold or (
            interval > 0
            and _import_progress_clock() - entry[1] >= interval)
        if due:
            batch = entry[0]
            entry[0] = 0
            entry[1] = _import_progress_clock()
    if due:
        _report_imported_steps(background_process_pk, batch)


def flush_import_progress(background_process_pk):
    """Report everything this worker has committed for a process unreported.

    The trailing partial batch of a task which ends - in work or in a retryable
    outage - must not sit in the memory of this worker until some later file
    happens to come along: the caller which knows its run is over calls this
    (#958).
    """
    if not background_process_pk:
        return
    with _import_progress_lock:
        entry = _import_progress_pending.pop(str(background_process_pk), None)
    if entry and entry[0] > 0:
        _report_imported_steps(background_process_pk, entry[0])


def import_progress_pk(kwargs):
    """The background process whose progress the work of an import task feeds.

    The fan-outs name it in the kwargs of the chunk tasks; a message which
    predates that (#958) - one still queued when a deployment upgraded - falls
    back to the process of the job it names, so no committed file ever goes
    unreported because a kwarg is missing.
    """
    pk = kwargs.get("background_process_pk")
    if pk:
        return pk
    harvesting_job_id = kwargs.get("harvesting_job_id")
    if not harvesting_job_id:
        return None
    from registry.models.harvest import HarvestingJob  # avoid circular import

    try:
        return HarvestingJob.objects.filter(
            pk=harvesting_job_id).values_list(
                "background_process_id", flat=True).first()
    except Exception:
        logger.error(
            f"could not resolve the background process of harvesting job "
            f"{harvesting_job_id}: {traceback.format_exc()}")
        return None


def _iter_task_ids(node):
    """The task ids nested in one worker's inspect answer.

    ``inspect().active()`` and ``.scheduled()`` answer task-info dicts while
    ``.reserved()`` answers nested lists, so the walk collects every string
    which parses as a uuid and lets the caller intersect them with the
    registered ids (#972).
    """
    if isinstance(node, str):
        try:
            yield str(UUID(node))
        except ValueError:
            return
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_task_ids(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _iter_task_ids(value)


def _task_id_of_message(raw):
    """The task id a serialized celery message names, or None when the
    message does not answer that question.

    The protocol-2 envelope carries the task id as ``properties.correlation_id``;
    the base64 body must not be decoded for this. None is deliberately not a
    claim that no id is named: an unreadable message must keep the answer away
    from "no message" (#972).
    """
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    task_id = (message.get("properties") or {}).get("correlation_id") \
        or (message.get("headers") or {}).get("id")
    if not task_id:
        return None
    try:
        return str(UUID(str(task_id)))
    except ValueError:
        return None


def _chord_publish_of_message(raw, job_id):
    """Whether one serialized message is a publish of the import chord of this job.

    Answers True for the control message of this very job, False for any other
    message it could read - another task or the same task of another job - and
    None when the message cannot be read at all. The reading is one deeper
    than ``_task_id_of_message``: a recovery that publishes the chord through
    ``.delay`` does not know a task id in advance, so the pending publish is
    attributed by what the message names itself - the task name of the
    protocol-2 headers and the job id of its decoded body (#970). None is
    again no claim: an unreadable message must keep the answer away from
    "no pending publish" (#972's stance, carried over).
    """
    try:
        message = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(message, dict):
        return None
    name = (message.get("headers") or {}).get("task") \
        or (message.get("properties") or {}).get("task")
    if not name:
        return None
    if name != CHORD_PUBLISH_TASK_NAME:
        return False
    try:
        body = json.loads(base64.b64decode(message.get("body")))
    except (TypeError, ValueError):
        return None
    kwargs = body[1] if isinstance(body, list) and len(body) > 1 else None
    published_job = kwargs.get("harvesting_job_id") if isinstance(kwargs, dict) else None
    if published_job is None:
        return None
    return str(published_job) == str(job_id)


def _iter_broker_messages(client):
    """Every serialized message the harvest queues and the unacked keys hold,
    page by page so the whole backlog never has to be held in memory (#972).
    """

    def _paged(key, read):
        start = 0
        while True:
            page = read(key, start, start + HARVEST_BROKER_SCAN_PAGE - 1)
            if not page:
                return
            yield from page
            if len(page) < HARVEST_BROKER_SCAN_PAGE:
                return
            start += HARVEST_BROKER_SCAN_PAGE

    for queue in HARVEST_BROKER_QUEUES:
        yield from _paged(queue, client.lrange)
    yield from _paged(HARVEST_UNACKED_LIST_KEY, client.lrange)
    yield from _paged(HARVEST_UNACKED_INDEX_KEY, client.zrange)


def _queued_task_ids(client, registered):
    """The task ids the broker's queue and unacked keys currently hold, out of
    the registered ones.

    Answers None when a key could not be read or a message on it could not be
    attributed: a message which exists but does not name itself must not
    count as "no message" (#972). A live id exits the scan at its first match;
    a stale answer pays the scan of the queues, which a worker restart pays
    once per job - and since #859 a draining queue is a few thousand chunk
    messages, not one message per record.
    """
    try:
        for raw in _iter_broker_messages(client):
            task_id = _task_id_of_message(raw)
            if task_id is None:
                return None
            if task_id in registered:
                return {task_id}
    except Exception:
        logger.warning(
            f"could not read the harvest queues of the broker: {traceback.format_exc()}")
        return None
    return set()


def _chord_publish_queued(client, job_id):
    """Whether the broker's queue and unacked keys currently hold a publish of
    the import chord of this job.

    The same paged read as ``_queued_task_ids``, only asking a different
    question of every message: not "does this id name it" but "is this the
    chord control of this job" (#970). The answer leaves the scan at the first
    pending publish and answers None on the first message it cannot read at
    all - a pending chord publish must not be declined or re-published on a
    guess, so an unattributable message keeps the whole answer unknown,
    exactly as in the staleness probe (#972's stance, carried over).
    """
    try:
        for raw in _iter_broker_messages(client):
            match = _chord_publish_of_message(raw, job_id)
            if match is None:
                return None
            if match:
                return True
    except Exception:
        logger.warning(
            f"could not read the harvest queues of the broker: {traceback.format_exc()}")
        return None
    return False


def _worker_reported_task_ids():
    """The task ids the running workers report as active, reserved or scheduled.

    A worker which does not answer adds nothing: everything its tasks could
    still need is on the unacked keys until it acks late, and those the queue
    scan has already read (#972).
    """
    reported = set()
    try:
        inspector = app.control.inspect(timeout=HARVEST_WORKER_INSPECT_TIMEOUT)
        replies = (inspector.active(), inspector.reserved(), inspector.scheduled())
    except Exception:
        logger.warning(
            f"could not ask the workers what they hold: {traceback.format_exc()}")
        return reported
    for reply in replies:
        if reply is None:
            continue
        for held in reply.values():
            reported.update(_iter_task_ids(held))
    return reported


def import_run_message_state(registered_ids):
    """Whether the broker still holds a message of a registered import run.

    Answers True while one of the registered ids names a message which could
    still be consumed, False when the broker was readable and none of them
    names one - the shadow is stale - and None when the broker cannot be asked
    at all. This is what lets the database shadow of
    ``HarvestingJob.has_live_import_run`` go STALE: an id whose message the
    broker dropped (a broker recreated or flushed with the database kept, a
    purge, a message discarded by the transport) stays registered for the rest
    of the job's life, and one such id plus waiting files was enough to let
    recovery decline the backlog forever (#972). Time bounding the ids was the
    other remedy on the issue; the broker answers the actual question, and a
    wall-clock bound is a guess a real catalogue breaks in both directions -
    a 341k backlog legitimately runs for hours, and an id of a flushed broker
    wants to be stale at once (#970 measured both).
    """
    registered = {str(UUID(str(_id))) for _id in registered_ids}
    if not registered:
        return False
    try:
        with app.connection_for_read() as connection:
            client = getattr(connection.default_channel, "client", None)
            if client is None:
                logger.warning(
                    "the broker does not answer queue introspection; a registered "
                    "task id can not be told stale from live")
                return None
            queued = _queued_task_ids(client, registered)
    except Exception:
        logger.warning(
            f"could not ask the broker about the messages of a harvest: {traceback.format_exc()}")
        return None
    if queued is None:
        return None
    if queued & registered:
        return True
    if _worker_reported_task_ids() & registered:
        return True
    return False


def chord_publish_message_state(job_id):
    """Whether the broker still holds a pending publish of this job's import chord.

    True while a ``call_chord_md_metadata_file_to_db`` message of the job sits
    in one of the harvest queues or in the unacked keys, False when the broker
    was readable and none of them is one, None when the broker cannot be
    asked. This is #970's guard against the duplicate publishes: at the size
    of a real catalogue every worker restart appended another copy of the
    control message to the queue behind the very backlog it was meant to
    build, and none of the copies could run until the queue had drained. All
    harvest tasks ack late, so a control message a worker is working is on the
    unacked keys and the queue scan covers the whole life of a pending
    publish; unlike ``import_run_message_state`` it needs no inspect round to
    know that.
    """
    try:
        with app.connection_for_read() as connection:
            client = getattr(connection.default_channel, "client", None)
            if client is None:
                logger.warning(
                    "the broker does not answer queue introspection; a chord "
                    "publish can not be told pending from absent")
                return None
            return _chord_publish_queued(client, job_id)
    except Exception:
        logger.warning(
            f"could not ask the broker about a pending chord publish: "
            f"{traceback.format_exc()}")
        return None


def publish_import_chord(job, origin):
    """Publish the import chord of a job unless one of its publishes still waits.

    Recovery and the operator command resume a job's backlog through this one
    door, and the door is shut while the broker still holds a publish of it:
    that message will rebuild the chord once it is consumed, and a second one
    is exactly the pile-up which grew the queue per restart (#970). The
    decision is written to the harvesting log like every other one about the
    backlog (#972's logging pattern); when the broker cannot be asked, a
    duplicate publish is the risk #891 forbids, so publishing is declined and
    the operator path is named on the job. Answers whether it published.
    """
    state = chord_publish_message_state(job.pk)
    if state is True:
        logger.info(
            f"harvesting job {job.pk} keeps its waiting import chord publish: the "
            "broker still holds a message which will rebuild the backlog when "
            "it is consumed")
        job.log(description=(
            f"{origin}: a publish of the import chord is still pending on the "
            "broker; the waiting records will be published as a chord when it "
            "is consumed, so this publish was declined to keep the backlog single"))
        return False
    if state is None:
        logger.warning(
            f"harvesting job {job.pk} keeps its import backlog unpublished: the "
            "broker could not answer whether a publish of the import chord is "
            "already pending")
        job.log(
            level=LogLevelEnum.WARNING.value,
            description=(
                f"{origin}: the broker could not answer whether a publish of the "
                "import chord is still pending, so nothing was published to keep "
                "the backlog from being duplicated. Once the broker answers "
                f"again, resume with: manage.py resume_harvesting_job {job.pk}"))
        return False
    call_chord_md_metadata_file_to_db.delay(harvesting_job_id=job.pk)
    return True


def resume_stale_import_run(job, registered_ids, origin):
    """End a shadow of an import run which the broker does not hold anymore.

    Both the worker-restart recovery and ``manage.py resume_harvesting_job``
    come here once the broker was asked and answered that no registered id
    names a message which could still be consumed. The rows of those ids name
    nothing: they go - revoking them would be meaningless - and the decision
    with the ids is written to the harvesting log, so the harvesting card
    tells what happened to the backlog instead of only going on counting the
    waiting files (#972). Only the ids the broker was asked about are dropped:
    one a concurrent publishing registered in the meantime is fresh and stays.
    """
    from registry.models.harvest import HarvestingJobTaskId  # avoid circular import errors

    dead = HarvestingJobTaskId.objects.filter(
        job_id=job.pk, creation=False, task_id__in=list(registered_ids))
    dead_ids = [str(_id) for _id in dead.values_list("task_id", flat=True)]
    dead.delete()
    shown = dead_ids[:50]
    details = (
        "The rows of these task ids outlived their messages: the broker holds "
        "no queued, no unacked and no worker-held message for any of them.\n"
        f"{json.dumps(shown, indent=1)}\n")
    if len(dead_ids) > len(shown):
        details += f"{len(dead_ids) - len(shown)} more not shown.\n"
    details += ("The ids are gone with the messages they named; the backlog goes "
                "out again as one chord.")
    job.log(
        level=LogLevelEnum.WARNING.value,
        description=(
            f"{origin}: {len(dead_ids)} registered task ids name no message on the "
            "broker; the waiting records are published as a new import chord"),
        extented_description=details,
    )
    # the door of #970: if an earlier recovery already left a chord publish
    # waiting on the broker, that one will build the chord and this resume
    # declines visibly instead of adding a second copy
    return publish_import_chord(job, origin)


@worker_ready.connect
def recover_harvests_after_restart(sender, **kwargs):
    # Database state also covers a crash between commit and publishing a chord.
    sender.app.send_task("registry.tasks.harvest.recover_harvesting_jobs")


@shared_task(queue="default", base=HarvestingTask)
def recover_harvesting_jobs():
    """Resume the harvests which did not end while no worker was running.

    A worker restart leaves the messages of a running import chord in the
    broker - queued ones are untouched by it, unacked ones return through the
    visibility timeout - so a job whose tasks have not reported in has its
    backlog in the queue already. Re-chording such a job publishes the whole
    backlog a second time on top of the queued one and grows the queue per
    restart (#891); what recovery has to re-chord is a job whose run reported
    in - or which died between the commit of its phase and the publishing of
    its chord, whose own unacked message brings it back to run again.

    The registered ids answer that only as long as every one of them still
    names a message. A task id which outlives its message - a broker recreated
    or flushed with the database kept, a purge, a discarded message - is a row
    naming nothing, and it alone would let the guard decline the backlog for
    the life of the job (#972). So the shadow is not trusted with the verdict:
    the broker is asked, and whichever answer the asking takes is written to
    the harvesting log, which is what the harvesting card answers.
    """
    from registry.models.harvest import HarvestingJob

    for job in HarvestingJob.objects.filter(done_at__isnull=True).iterator():
        if job.phase <= HarvestingPhaseEnum.DOWNLOAD_RECORDS and job.service_id:
            call_fetch_total_records.delay(harvesting_job_id=job.pk)
        elif job.phase == HarvestingPhaseEnum.RECORDS_TO_DB:
            if not job.has_live_import_run():
                # no (or no waiting) shadow: publishing is what completes a run
                # whose chord was consumed while its callback was lost, and
                # what restarts one which died before its chord went out
                # (#891); publish_import_chord keeps a restart from stacking a
                # second control message behind a first one still pending (#970)
                publish_import_chord(job, origin="worker restart recovery")
            else:
                recover_records_to_db_job(job)

    try:
        # the harvests which ended are not what this recovery came for, but
        # the same start which re-publishes their running colleagues' chords
        # is the moment the cleanup of a lost publish or of a cleanup which
        # died with its worker gets its second chance (#1237)
        dispatch_cleanup_of_ended_harvest_backlogs()
    except Exception:
        # a housekeeping which cannot be dispatched here waits for the hourly
        # sweep instead of ending the recovery of the open harvests
        logger.error(
            f"could not dispatch the temporary file cleanup of ended "
            f"harvests: {traceback.format_exc()}")


def recover_records_to_db_job(job):
    """Decide about a job whose database shadow says an import run is live.

    Asks the broker (``import_run_message_state``) and writes its decision to
    the job: while one of the registered ids names a message which could still
    run, the backlog is being consumed and recovery must not stack a second
    one onto it (#891); when the broker holds none of them, the shadow is
    stale and the backlog goes out as a fresh chord (#972); when the broker
    cannot be asked at all, recovery stays on the safe side of #891 and names
    the operator path which can resume the job once the broker answers again.
    """
    registered = {
        str(_id) for _id in
        job.celery_task_ids.filter(creation=False).values_list("task_id", flat=True)}
    state = import_run_message_state(registered)
    if state is True:
        logger.info(
            f"harvesting job {job.pk} keeps its queued import backlog: the broker "
            f"still holds a message of the {len(registered)} ids it registered")
        job.log(
            description=(
                f"recovery left the import backlog alone: the broker still holds a "
                f"message of the run this job registered ({len(registered)} task ids)"))
        return
    if state is None:
        logger.warning(
            f"harvesting job {job.pk} keeps its queued import backlog although its "
            f"{len(registered)} registered ids could not be checked against the broker")
        job.log(
            level=LogLevelEnum.WARNING.value,
            description=(
                "recovery left the import backlog alone: the broker could not answer "
                "whether the run this job registered is still live. Once it answers "
                f"again, resume with: manage.py resume_harvesting_job {job.pk}"),
        )
        return
    resume_stale_import_run(job, registered, origin="worker restart recovery")


# Who the harvesting log of a job is told decided about it: "worker restart
# recovery" and "manage.py resume_harvesting_job" name themselves the same way
# when they resume a backlog (#1038).
HARVEST_IMPORT_WATCH_ORIGIN = "import watchdog"


def import_watch_interval():
    """The time an import backlog may stand still before the watchdog acts.

    The beat row of ``watch_import_backlogs`` fires on this very interval (see
    ``registry/apps.py``), so a backlog which is answered with the same amount of
    waiting files on two looks is one which stood still for a whole watchdog
    interval. Standing still is a readable question, because a working import
    cannot hide: a chunk commits its records one by one and every committed record
    deletes its own row (see ``import_md_metadata_file``), so the count of the
    waiting files moves while the import works (#859, #1038).
    """
    return timedelta(minutes=max(1, int(getattr(
        settings, "HARVEST_IMPORT_WATCH_INTERVAL_MINUTES", 5))))


def watch_import_backlog(harvesting_job_id, at=None):
    """Bound the wait of one open job whose import backlog does not drain.

    The end of an import chord is not observable by the code which depends on it:
    the wait of the chord is bounded by the budget this project hands to celery
    (``max_retries=300, interval=1`` at the publishing in
    ``call_chord_md_metadata_file_to_db``) and when that budget runs out, celery
    raises inside its own builtin ``chord_unlock`` task. The callback of the chord
    is what sets ``done_at``, reports the final statistics and raises the alert of
    the catalogue, and it is simply never called - which leaves the job open, its
    records unimported, and the whole failure in one worker log line (#1038).

    So the wait is bounded here, in mrmap's own terms and out of the durable state
    a harvest keeps anyway: the count of the files which still wait for their
    import, the task ids the job registered and has not seen report in, and what
    the broker answers about them. The decision needs all three, because the same
    standing backlog has two causes and only the broker tells them apart:

    * nothing of the run is on the broker anymore - its messages are gone, be it a
      flushed broker, a purge, or an unlock which gave up after the last header
      reported in. The backlog is stranded and goes out again as one fresh chord,
      which is also what completes a run whose chord came in while its callback
      was lost: ``publish_import_chord`` builds no chord and completes the harvest
      when nothing waits anymore (#891).
    * the broker still holds a message of the run - the work is queued and nobody
      consumes it, which is what a queue without a worker on its end turns into
      (#970 measured ten hours of that). Publishing over it is the pile-up #891
      forbids, so nothing goes out here; the job says on itself that its import
      does not move, which is what the api could not answer at all while the run
      reported "records to db".

    A backlog which moved since the last look is left alone and becomes the
    baseline of the next one, so an import which works is never asked about the
    broker. What the watchdog decides is written to the harvesting log like every
    other decision about the backlog, and it is told once per stall: the reported
    state on the job is the memory of that, and it is gone as soon as the backlog
    drains again.

    Args:
        harvesting_job_id: the job to look at
        at: the moment of the look; the tests wind this one instead of letting the
            beat interval pass for real
    """
    from registry.models.harvest import (HarvestingJob,  # avoid circular import
                                         TemporaryMdMetadataFile)

    at = at or timezone.now()
    with transaction.atomic():
        job = HarvestingJob.objects.select_for_update().filter(
            pk=harvesting_job_id, done_at__isnull=True,
            phase=HarvestingPhaseEnum.RECORDS_TO_DB.value).first()
        if job is None:
            # the run ended, was aborted, or never reached its import while this
            # watchdog was reading; there is no wait to bound
            return
        waiting = TemporaryMdMetadataFile.objects.filter(
            job_id=job.pk, has_import_error=False).count()
        untouched_since = (
            job.import_backlog_seen_at
            if job.import_backlog_seen == waiting
            and job.import_backlog_seen_at is not None
            and at - job.import_backlog_seen_at >= import_watch_interval()
            else None)
        if untouched_since is None:
            # the backlog moved since the last look, or this is the first look at
            # it: nothing is overdue, and a stall the watchdog had reported is
            # over with the drain. The count is the baseline of the next look.
            if job.import_stalled_at is not None:
                job.log(
                    level=LogLevelEnum.WARNING.value,
                    description=(
                        f"{HARVEST_IMPORT_WATCH_ORIGIN}: the import backlog of this "
                        f"job drains again; {waiting} records are left to import"))
                # the process which reported the stall reports the drain with
                # it, so the operation leaves action-required on its own (#1207)
                job.report_process_attention(False)
            HarvestingJob.objects.filter(pk=job.pk).update(
                import_backlog_seen=waiting,
                import_backlog_seen_at=at,
                import_stalled_at=None)
            return

        registered = {
            str(_id) for _id in
            job.celery_task_ids.filter(creation=False).values_list(
                "task_id", flat=True)}
        state = import_run_message_state(registered)
        publish_state = chord_publish_message_state(job.pk)
        waited = int((at - untouched_since).total_seconds() // 60)
        not_reported_yet = job.import_stalled_at is None
        if not_reported_yet:
            # the job itself answers what the watchdog sees: this run is no longer
            # waiting on work which somebody is doing (#1038)
            HarvestingJob.objects.filter(pk=job.pk).update(
                import_stalled_at=untouched_since)
            # and the process which reports the run says the same to the
            # background job center: this one stands until a human acts (#1207)
            job.report_process_attention(
                True,
                phase=f"{HARVEST_IMPORT_WATCH_ORIGIN}: import backlog stalled")
        # what the waiting costs decides the broker and never a guess: a second
        # publish of a backlog which is still queued is #891
        if state is None or publish_state is None:
            if not_reported_yet:
                job.log(
                    level=LogLevelEnum.WARNING.value,
                    description=(
                        f"{HARVEST_IMPORT_WATCH_ORIGIN}: {waiting} records have been "
                        f"waiting for their import for {waited} minutes and the "
                        "broker could not answer whether a message of this run is "
                        "still live, so nothing was published. Once the broker "
                        f"answers again, resume with: manage.py "
                        f"resume_harvesting_job {job.pk}"))
            return
        if state is False and publish_state is False:
            if not_reported_yet:
                job.log(
                    level=LogLevelEnum.WARNING.value,
                    description=(
                        f"{HARVEST_IMPORT_WATCH_ORIGIN}: {waiting} records have been "
                        f"waiting for their import for {waited} minutes while the "
                        f"broker holds no message of the run ({len(registered)} "
                        "registered task ids) and no publish of its import chord; "
                        "the backlog goes out again as one chord"))
            # the fresh chord is measured from now on, so the next look asks about
            # the new run instead of finding the old stall a second time
            HarvestingJob.objects.filter(pk=job.pk).update(
                import_backlog_seen=None,
                import_backlog_seen_at=None,
                import_stalled_at=None)
            # the work went out again: whatever the human was awaited for,
            # this run does not stand for it anymore (#1207)
            job.report_process_attention(False)
            resume_stale_import_run(
                job, registered, origin=HARVEST_IMPORT_WATCH_ORIGIN)
            return
        if not_reported_yet:
            job.log(
                level=LogLevelEnum.WARNING.value,
                description=(
                    f"{HARVEST_IMPORT_WATCH_ORIGIN}: {waiting} records have been "
                    f"waiting for their import for {waited} minutes although the "
                    "broker still holds a message of this run: the work is queued "
                    "and nothing imports it. Check that the workers consume the "
                    f"'{celery_queues.HARVEST_IMPORT}' queue the import backlog is "
                    "routed to; nothing was published over it (#891)"))


@shared_task(queue=celery_queues.DB_ROUTINES, base=SingletonTask)
def watch_import_backlogs(*args, **kwargs):
    """Watch the harvests whose import backlog does not drain (beat).

    The recovery of #891 and #972 asks its question when a worker starts, so a
    deployment which does not restart its containers never looks again at the
    harvests which are not making progress - and the chord of a stranded job does
    not report itself dead, because its retry budget ends inside celery's builtin
    unlock (#1038). This asks the same question on a beat interval instead of on a
    start: which open job waits for an import which nothing is doing, and may it
    be resumed without publishing a backlog a second time.
    ``watch_import_backlog`` answers that per job, through the recovery paths
    which already exist for it.

    The message stays on db-routines like every other beat task of a harvest
    (#970), and a fire which finds an earlier one still reading the broker is
    skipped instead of stacked onto it.
    """
    from registry.models.harvest import HarvestingJob  # avoid circular import

    for job_id in HarvestingJob.objects.filter(
        done_at__isnull=True,
        phase=HarvestingPhaseEnum.RECORDS_TO_DB.value,
    ).values_list("pk", flat=True).iterator():
        try:
            watch_import_backlog(job_id)
        except Exception:
            # one job which cannot be read must not keep the others unwatched,
            # and its next fire is the answer to a broker which was briefly dark
            logger.error(
                f"could not watch the import backlog of harvesting job "
                f"{job_id}: {traceback.format_exc()}")


# ---------------------------------------------------------------------------
# The stored records of a harvest which has ended (#1237)
#
# A run stores every record it downloads as a ``TemporaryMdMetadataFile`` row
# and a file below ``MEDIA_ROOT/temporary_md_metadata_file/<job_id>/``. The
# import deletes what it consumed, so whatever a job in a terminal phase still
# holds is definitively not consumed anymore: recovery and the watchdog only
# ever look at open jobs, and every late message of an ended run is guarded
# against the job's phase. Nothing deleted these leftovers - on the rig of
# #1237 the rows of 45 ended jobs filled 14 GB of the media volume. The
# cleanup below takes them back; it runs
#
# * scheduled by the transition itself (``complete_harvest`` and
#   ``HarvestingJob.abort`` publish it on the commit of the terminal state),
# * as the backstop of a lost publish on every worker start (end of
#   ``recover_harvesting_jobs``) and on the beat schedule of
#   ``sweep_ended_harvest_temp_files``,
# * and as the supported operator path through
#   ``manage.py cleanup_temporary_harvest_files``.
#
# Any of these may run beside each other: the cleanup deletes each batch of
# rows in a transaction of its own and afterwards the files the batch named,
# so a second run over the same job simply finds them gone - which is what it
# wants. The order is the one of ``purge_expired_background_processes``
# (#1208): rows first, files after their commit. A database rollback cannot
# undo a deleted file, while a file whose storage deletion failed is exactly
# the leftover a repeated cleanup signs off: once the rows are gone, the
# sweep of the job's own storage directory takes back what no row references
# anymore - the failure mode which would otherwise turn a crashed cleanup into
# a permanent, now invisible leak.
#
# How long a run which ended keeps its records at all is the retention window of
# #1295 (``MRMAP_HARVEST_TEMP_FILE_RETENTION_DAYS``, 0 by default): inside it a
# cleanup answers "deferred" and the terminal transition of #1237 is simply not
# reached; the hourly sweep is what meets the run when the window passes. With
# the default of 0 every path below deletes as it always did.
# ---------------------------------------------------------------------------

#: The phases a harvesting job cannot leave anymore; its stored records are
#: out of consumption in exactly these (#1237)
TERMINAL_HARVESTING_PHASES = [
    HarvestingPhaseEnum.COMPLETED.value,
    HarvestingPhaseEnum.ABORTED.value,
]


def temp_file_retention_days():
    """How many days the records of an ended run stay before they are taken (#1295).

    The window an operator chooses with ``MRMAP_HARVEST_TEMP_FILE_RETENTION_DAYS``;
    a negative value is the 0 which means "take them at once", because a window
    cannot be shorter than the terminal transition itself.
    """
    return max(0, int(getattr(settings, "HARVEST_TEMP_FILE_RETENTION_DAYS", 0)))


def temp_file_retention_holds(job):
    """Whether the retention window still shields the records of a terminal run.

    #1237 takes the backlog of a run with its terminal transition, and #1295 asks
    for a configurable window before that happens: while it is open, the operator
    can reschedule the import of a stored record of the run - the action of the
    admin, which re-publishes the import task of exactly that row - and find the
    document there. Only a run which completed answers such a re-import: the
    import of an aborted run refuses its own documents, so a window over the pile
    of an aborted run is what the operator wants to look at by hand and nothing
    more. The hourly sweep names the run again once the window passed, so holding
    it is a delay of the same deletion and not a second answer about whether it
    is due.

    A run whose terminal moment its row does not carry is not shielded: an
    unknown end would keep its records for ever, which is the unbounded pile the
    issue reports, while every terminal transition writes ``done_at`` and a row
    without it is a row somebody edited by hand. A run which is not there
    anymore is not shielded either - nothing can retry an import of a run nobody
    can name, and what is left of it are its files alone.
    """
    if temp_file_retention_days() <= 0 or job is None or job.done_at is None:
        return False
    # the same comparison the sweep of #1237 and the operator command of #1237
    # make: a run which ended before the cutoff is due, one at it or after it is
    # not - the two must not answer the same moment differently
    return job.done_at >= timezone.now() - timedelta(
        days=temp_file_retention_days())


#: The prefix of the harvesting log entry which a cleanup of a completed run
#: with import errors leaves on it. The error rows go with the cleanup, but
#: their exclusion of the run from a complete snapshot
#: (``registry.querys.harvest_history.complete_snapshots`` reads the ERROR
#: logs of a run) must outlive them (#1237).
TEMP_FILE_CLEANUP_LOG_PREFIX = "Temporary files cleaned up:"

#: How often one cleanup may hand itself over for the next bounded run; at
#: the default of 25,000 rows per run this carries a backlog of over a
#: million records and the demo rig's 163k of a single aborted job. What outlives
#: the chain is answered by the worker-start recovery and the hourly sweep (#1237).
TEMP_FILE_CLEANUP_MAX_CONTINUATIONS = 60


def _temp_files_storage():
    """The storage backend which holds the stored records of a harvest (#1237).

    Asked from the field, so a deployment which moves the media to another
    backend is cleaned by the backend which actually holds the files.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # avoid circular import
    return TemporaryMdMetadataFile._meta.get_field("md_metadata_file").storage


def _delete_temp_files(storage, names):
    """Delete the named storage files, tolerant of what is already gone.

    A file which is not there is the state this cleanup wants, not a failure;
    a file whose deletion refuses is counted - its bytes stay in the job's own
    directory until the sweep or a later run takes them. Nothing here logs per
    file except the exceptions which are no storage refusal: a real catalogue
    leaves hundreds of thousands of names to delete and the log of this is the
    summary, not the file list (#1237).

    Returns:
        tuple: how many files were deleted, found already gone, refused
    """
    deleted = missing = failed = 0
    for name in names:
        try:
            storage.delete(name)
            deleted += 1
        except FileNotFoundError:
            missing += 1
        except OSError:
            failed += 1
        except Exception:
            failed += 1
            logger.warning(
                f"the storage answered a cleanup delete with an unexpected "
                f"{type(Exception).__name__}: {traceback.format_exc()}")
    return deleted, missing, failed


def _sweep_harvest_temp_dir(storage, harvesting_job_id):
    """Take back what still lies in the storage directory of one ended job.

    While rows exist the directory is not swept - every file in it is still
    referenced by a row and goes batch by batch with its row. What this
    answers is the file without a row anymore: a deletion which failed after
    the row committed, a cleanup which died between the two, a job deleted
    around its leftovers - none of which the database can point at again
    (#1237). Only the job's own directory is read and emptied; a storage
    which cannot list is told instead of guessed at, and the directory itself
    is removed with ``rmdir`` alone, which never takes a non-empty tree.

    Returns:
        dict: files deleted, found gone, refused, and whether anything is left
    """
    from registry.models.harvest import (  # avoid circular import
        TEMPORARY_MD_METADATA_FILE_SUBDIR)
    summary = {"files": 0, "missing": 0, "failed": 0, "remaining": False}
    subdir = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{harvesting_job_id}"
    try:
        if not storage.exists(subdir):
            return summary
        entries, found = storage.listdir(subdir)
    except (NotImplementedError, FileNotFoundError):
        # no listdir (or the directory is gone with the race of a parallel
        # cleanup) - the rows are cleaned regardless, this only cannot see the
        # bytes which are not
        return summary
    except Exception:
        logger.warning(
            f"could not list the storage directory of harvesting job "
            f"{harvesting_job_id}: {traceback.format_exc()}")
        summary["remaining"] = True
        return summary
    deleted, missing, failed = _delete_temp_files(
        storage, [f"{subdir}/{name}" for name in found])
    summary.update(files=deleted, missing=missing, failed=failed)
    if entries or failed:
        # a subdirectory the flat sweep does not reach, or a refused file:
        # the directory stays and the next sweep looks again
        summary["remaining"] = True
        return summary
    location = getattr(storage, "location", None)
    if location is not None:
        try:
            # rmdir only ever removes the EMPTY directory; a parallel cleanup
            # which just filled it loses its race with an OSError, not with a
            # deleted file (#1237)
            os.rmdir(os.path.join(location, subdir))
        except OSError:
            pass  # not empty, already gone, or not a local directory
    return summary


def cleanup_harvesting_job_temp_files(harvesting_job_id, batch_size=None,
                                      max_rows=None, respect_retention=True):
    """Delete the stored records of a harvest which definitely ended (#1237).

    The job must have reached COMPLETED or ABORTED; a job which is not in a
    terminal phase keeps every row and file - a running import, a retry and
    the recovery of #891/#972 all read the backlog of an open job, and this
    function never touches it. The answer of the phase is read again under
    the lock of the first transaction, so a cleanup published beside a
    recovery cannot delete what a job consumes again.

    A terminal run answers ``deferred`` while the retention window of #1295 is
    open (``temp_file_retention_holds``); the window is 0 by default, so the
    default of this function is the immediate reclaim it shipped with (#1237).
    ``respect_retention=False`` answers it anyway: that is the operator who
    called ``manage.py cleanup_temporary_harvest_files`` and named what to take.

    The rows go in batches of ``batch_size``, each in a transaction of its
    own - a single 163k-row delete would hold its locks for minutes, and no
    transaction here is longer than the ids it names - and at most
    ``max_rows`` rows are handled per call, which keeps every task bounded;
    ``capped`` answers that a continuation is due. After a batch committed,
    its files are deleted (see ``_delete_temp_files``); a name outside the
    temporary storage tree of this job is refused and its row stays, so the
    cleanup can never reach a file of another job or of the permanent records.
    Once the rows are gone, the job's own storage directory is swept of
    whatever no row references anymore.

    A completed run which had import errors keeps those rows for the snapshot
    math of ``complete_snapshots``; the cleanup logs their count as an ERROR
    harvesting log entry first - once, guarded by its prefix - so the run
    stays excluded from the complete snapshots after its error rows are gone.
    An aborted run never enters that math (the phase filter answers it) and
    is logged not at all.

    Returns:
        dict: the aggregated answer - ``skipped`` and ``deferred`` (the run was
            not open for this cleanup at all, or not yet due), rows, files,
            missing, failed, rejected (names the cleanup refused to delete),
            the sweep numbers, ``remaining_rows``, ``capped`` and the wall
            seconds it took
    """
    from registry.models.harvest import (  # avoid circular import
        HarvestingJob, HarvestingLog, TEMPORARY_MD_METADATA_FILE_SUBDIR,
        TemporaryMdMetadataFile)

    started = time.monotonic()
    batch = max(1, int(batch_size or getattr(
        settings, "HARVEST_TEMP_FILE_CLEANUP_BATCH_SIZE", 500)))
    limit = max(0, int(getattr(
        settings, "HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN", 25000))
        if max_rows is None else max(0, int(max_rows)))

    summary = {
        "job": harvesting_job_id, "skipped": False, "deferred": False,
        "rows": 0, "files": 0, "missing": 0, "failed": 0, "rejected": 0,
        "swept_files": 0, "swept_missing": 0, "swept_failed": 0,
        "sweep_remaining": False, "remaining_rows": False, "capped": False,
    }

    job = HarvestingJob.objects.filter(pk=harvesting_job_id).first()
    if job is not None and job.phase not in TERMINAL_HARVESTING_PHASES:
        # a job which may still consume these files keeps them: the publish
        # of a terminal transition which raced with a recovery, or a hand
        # scheduled task of an old date, must never reach a running backlog
        # (#1237)
        summary["skipped"] = True
        return summary

    if respect_retention and temp_file_retention_holds(job):
        # the window of #1295: this run ended too recently for its records to
        # be out of reach of a retry, so nothing here is deleted and no log is
        # written - the ledger entry of a completed run belongs to the moment
        # its error rows actually go. The next fire of the hourly sweep names
        # the run again once the window passed, which is why this is an answer
        # of its own and not a continuation of this task
        summary["deferred"] = True
        return summary

    if job is not None and job.phase == HarvestingPhaseEnum.COMPLETED.value:
        # the ledger of the run outlives the rows which spelled it: an ERROR
        # harvesting log entry is what keeps a run with import errors out of
        # the complete snapshots once its error rows are gone (#1237). The
        # job row is locked while the decision is taken, so two cleanups which
        # meet here still write the entry once.
        with transaction.atomic():
            locked = HarvestingJob.objects.select_for_update().filter(
                pk=harvesting_job_id).first()
            if (locked is not None
                    and locked.phase == HarvestingPhaseEnum.COMPLETED.value):
                errors = TemporaryMdMetadataFile.objects.filter(
                    job_id=harvesting_job_id, has_import_error=True)
                if (errors.exists() and not HarvestingLog.objects.filter(
                        harvesting_job_id=harvesting_job_id,
                        description__startswith=(
                            TEMP_FILE_CLEANUP_LOG_PREFIX)).exists()):
                    locked.log(
                        description=(
                            f"{TEMP_FILE_CLEANUP_LOG_PREFIX} "
                            f"{errors.count()} stored records of this run had "
                            "import errors; their rows and files are taken "
                            "back now (#1237)"),
                        level=LogLevelEnum.ERROR.value)

    storage = _temp_files_storage()
    own_prefix = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{harvesting_job_id}/"
    # the layout which upload_to answered while the instance was unsaved: the
    # files of many runs share the literal "None" directory, and each row
    # names its own file inside it - the same deletion right as a file below
    # the job's own directory, and the only legacy layout which ever existed
    legacy_prefix = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/None/"

    cursor = 0
    processed = 0
    while processed < limit:
        batch_rows = list(
            TemporaryMdMetadataFile.objects
            .filter(job_id=harvesting_job_id, pk__gt=cursor)
            .order_by("pk")
            # the batch never runs past the bound of this run: an operator
            # who said --limit 1 gets one row back, not one batch
            .values_list("pk", "md_metadata_file")[:min(batch, limit - processed)])
        if not batch_rows:
            break
        cursor = batch_rows[-1][0]
        processed += len(batch_rows)
        deletable, names = [], []
        for pk, name in batch_rows:
            if name and not (name.startswith(own_prefix)
                             or name.startswith(legacy_prefix)):
                # a row whose file lives somewhere else than the temporary
                # tree of this run: deleting it could reach the media of a
                # permanent record or the backlog of a running job, so the
                # name is refused, the row stays, and the answer counts it for
                # whoever has to look at this row by hand (#1237)
                summary["rejected"] += 1
                continue
            deletable.append(pk)
            if name:
                names.append(name)
        if deletable:
            with transaction.atomic():
                TemporaryMdMetadataFile.objects.filter(
                    pk__in=deletable).delete()
            summary["rows"] += len(deletable)
            deleted, missing, failed = _delete_temp_files(storage, names)
            summary["files"] += deleted
            summary["missing"] += missing
            summary["failed"] += failed

    summary["remaining_rows"] = TemporaryMdMetadataFile.objects.filter(
        job_id=harvesting_job_id).exists()
    if not summary["remaining_rows"]:
        swept = _sweep_harvest_temp_dir(storage, harvesting_job_id)
        summary["swept_files"] = swept["files"]
        summary["swept_missing"] = swept["missing"]
        summary["swept_failed"] = swept["failed"]
        summary["sweep_remaining"] = swept["remaining"]
    elif processed >= limit:
        summary["capped"] = True

    summary["seconds"] = round(time.monotonic() - started, 1)
    return summary


def cleanup_needs_continuation(summary):
    """Whether the answer of a cleanup asks for another run.

    Rows which the bounded run did not reach (``capped``), rows which stayed
    behind (a late import of an aborted run flagged one after the cursor
    passed it, or a refused name), and files which the sweep could not take -
    all of them are work for the next run, and none of them may go unnoticed
    until a human asks: the task continues itself bounded, the worker start
    and the hourly sweep continue what the chain could not (#1237).
    """
    return bool(summary["remaining_rows"] or summary["failed"]
                or summary["swept_failed"] or summary["sweep_remaining"])


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True)
def cleanup_harvesting_job_temp_files_task(
        self, harvesting_job_id, batch_size=None, max_rows=None,
        continuation=0):
    """Clean the stored records of one ended harvest, bounded per fire (#1237).

    One run of this task takes at most ``HARVEST_TEMP_FILE_CLEANUP_ROWS_PER_RUN``
    rows, so the task which completes a harvest of half a million records is
    not itself the half-million-row monster the issue refuses; what is left
    hands the task over to itself until the job is clean. A continuation
    because the bound was hit goes out immediately, a stalled storage waits a
    minute before the next look. The chain is bounded
    (``TEMP_FILE_CLEANUP_MAX_CONTINUATIONS``); what outlives it is retried by
    the worker-start recovery and the hourly sweep, and is told on the log of
    the fire which ends the chain.
    """
    summary = cleanup_harvesting_job_temp_files(
        harvesting_job_id, batch_size=batch_size, max_rows=max_rows)
    if summary["skipped"]:
        return summary
    if summary["deferred"]:
        # the run ended inside the retention window of #1295, so its records are
        # still retry material and not leftovers. This is said out loud because
        # the pile of a deployment which sets a window is exactly what an
        # operator looking for a leak asks about first
        logger.info(
            "Temporary harvesting files of job %s stay: the retention window of "
            "%s day(s) is still open for this run. The hourly sweep takes them "
            "when it passes.",
            harvesting_job_id, temp_file_retention_days())
        return summary
    logger.info(
        "Temporary harvesting files of job %s: %s rows and %s files deleted, "
        "%s already gone, %s refused, %s rejected names, sweep took %s files "
        "(%s refused), %s rows left, %s s.",
        harvesting_job_id, summary["rows"], summary["files"],
        summary["missing"], summary["failed"], summary["rejected"],
        summary["swept_files"], summary["swept_failed"],
        summary["remaining_rows"], summary["seconds"])
    if cleanup_needs_continuation(summary):
        if continuation < TEMP_FILE_CLEANUP_MAX_CONTINUATIONS:
            cleanup_harvesting_job_temp_files_task.apply_async(
                kwargs={
                    "harvesting_job_id": harvesting_job_id,
                    "batch_size": batch_size,
                    "max_rows": max_rows,
                    "continuation": continuation + 1,
                },
                countdown=5 if summary["capped"] else 60)
        else:
            logger.warning(
                f"the cleanup of harvesting job {harvesting_job_id} still "
                f"holds {summary['remaining_rows']} rows after "
                f"{continuation + 1} runs; the worker start and the hourly "
                "sweep keep trying, and the operator path is: manage.py "
                f"cleanup_temporary_harvest_files --job-id {harvesting_job_id} "
                "--confirm")
    return summary


def dispatch_cleanup_of_ended_harvest_backlogs():
    """Schedule the cleanup of every ended harvest which still holds records.

    The rows answer which ended job keeps its backlog; the storage directory
    answers what the rows cannot: the files which no row references
    anymore - a cleanup which died between the row delete and the file
    deletes, a job deleted around its leftovers (#1237). A directory which
    names a job that is not terminal is the material of a running harvest and
    stays out, and a name which is no job id at all is nobody's to delete
    here: the "None" directory of the old unsaved-instance layout holds the
    files of open jobs side by side with the ones of ended runs, and only a
    row may point at its own file inside it. Of the runs which are due, that
    is: a run whose retention window of #1295 is still open is left for the
    fire which meets it after the window, so the sweep is also the periodic
    half of that retention.
    """
    from registry.models.harvest import (  # avoid circular import
        HarvestingJob, TEMPORARY_MD_METADATA_FILE_SUBDIR)

    pending = set(HarvestingJob.objects.filter(
        phase__in=TERMINAL_HARVESTING_PHASES,
        temporary_md_metadata_file__isnull=False,
    ).values_list("id", flat=True))

    storage = _temp_files_storage()
    try:
        entries, _files = storage.listdir(TEMPORARY_MD_METADATA_FILE_SUBDIR)
    except Exception:
        # the row-based half of the discovery does not wait for a storage
        # which cannot answer the question
        logger.warning(
            "could not list the temporary file storage root for the cleanup "
            f"of ended harvests: {traceback.format_exc()}")
        entries = []
    directories = {int(entry) for entry in entries
                   if str(entry).isdigit()}
    if directories:
        open_ids = set(HarvestingJob.objects.filter(
            pk__in=list(directories)).exclude(
                phase__in=TERMINAL_HARVESTING_PHASES).values_list(
                    "id", flat=True))
        # a directory whose job is gone (its rows cascaded with it) is orphaned
        # by definition; a directory of a terminal job without rows is the
        # file leftover the rows cannot name
        pending |= directories - open_ids

    days = temp_file_retention_days()
    if days and pending:
        # the window of #1295: a run which ended inside it is not due yet, and
        # naming it on every fire would publish a task whose only answer is
        # "deferred" - the sweep hands a run over once its window passed. A run
        # whose row carries no terminal moment stays pending, because
        # ``done_at__gte`` never matches a NULL; that is the same reading of an
        # unknown end which ``temp_file_retention_holds`` gives the cleanup.
        not_due = set(HarvestingJob.objects.filter(
            pk__in=list(pending),
            phase__in=TERMINAL_HARVESTING_PHASES,
            done_at__gte=timezone.now() - timedelta(days=days),
        ).values_list("id", flat=True))
        pending -= not_due

    dispatched = sorted(pending)
    for job_id in dispatched:
        try:
            cleanup_harvesting_job_temp_files_task.delay(
                harvesting_job_id=job_id)
        except Exception:
            logger.warning(
                f"could not schedule the temporary file cleanup of harvesting "
                f"job {job_id}: {traceback.format_exc()}")
    return dispatched


@shared_task(queue=celery_queues.DB_ROUTINES, base=SingletonTask)
def sweep_ended_harvest_temp_files(*args, **kwargs):
    """Take the stored records of ended harvests back on a schedule (#1237).

    The transitions schedule their own cleanup and the worker start recovers
    what a crash lost; this sweep is the answer of a deployment which does
    neither restart nor notice: every hour it looks for an ended job which
    still holds its backlog - a broker which swallowed the publish, a storage
    which was briefly dark, a cleanup whose worker died - and hands each one
    to ``cleanup_harvesting_job_temp_files_task``, which is idempotent and
    bounded per fire. ``SingletonTask`` keeps two sweeps from reading the
    same backlog twice at once.
    """
    dispatched = dispatch_cleanup_of_ended_harvest_backlogs()
    if dispatched:
        logger.info(
            f"the sweep of ended harvests scheduled the temporary file "
            f"cleanup of {len(dispatched)} job(s): {dispatched[:50]}")
    return dispatched


def schedule_cleanup_of_harvest_temp_files(harvesting_job_id):
    """Publish the cleanup of a harvest whose terminal state is about to commit.

    Registered with ``transaction.on_commit`` - outside an active transaction
    it fires at once - so no storage file of the run is touched before the
    database says the run ended. A publish the broker refuses must not fail
    the harvest whose commit it rides: the next worker start and the hourly
    sweep are the backstop of the lost message (#1237).
    """
    def _publish():
        try:
            cleanup_harvesting_job_temp_files_task.delay(
                harvesting_job_id=harvesting_job_id)
        except Exception:
            logger.warning(
                f"could not schedule the temporary file cleanup of harvesting "
                f"job {harvesting_job_id}; the worker start and the hourly "
                f"sweep will: {traceback.format_exc()}")

    transaction.on_commit(_publish)


@shared_task(queue="default", bind=True, base=HarvestingTask)
def create_harvesting_job(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob
    from registry.models.service import CatalogueService

    with transaction.atomic():
        service = CatalogueService.objects.select_for_update().get(pk=kwargs.get("service_id"))
        if not service.is_harvestable:
            return None
        # Keep the creation delivery's identity even after the harvest finishes.
        delivery_id = self.request.id or str(uuid4())
        job = HarvestingJob.objects.filter(
            celery_task_id__task_id=delivery_id).first()
        if job is None:
            # a harvest which names no step size starts from the size this catalogue is known to
            # answer - a schedule and the "harvest now" of the ui both come this way (#691)
            job, _ = HarvestingJob.objects.get_or_create(
                service=service, done_at__isnull=True,
                defaults={"max_step_size": service.max_step_size})
            job.append_celery_task_ids([delivery_id], creation=True)
        if job.done_at is None:
            transaction.on_commit(lambda: call_fetch_total_records.delay(harvesting_job_id=job.pk))
    return job.pk


@shared_task(bind=True, queue=celery_queues.DB_ROUTINES, base=HarvestingTask, max_retries=None)
def finish_harvesting_job(self, *args, **kwargs):
    """End a harvest whose import chord has come in.

    The chord callback stays on db-routines: the backlog it waits for now
    floods harvest-import, so this callback is reached while a catalogue is
    still being written to the database (#970).
    """
    from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
    from registry.querys.harvest_history import complete_harvest

    with transaction.atomic():
        job = HarvestingJob.objects.select_for_update().get(pk=kwargs.get("harvesting_job_id"))
        # whatever this worker still holds unreported of this job is committed
        # work: answer it before the run decides about itself (#958)
        flush_import_progress(job.background_process_id)
        if job.done_at is not None or job.phase != HarvestingPhaseEnum.RECORDS_TO_DB:
            return
        # Recovered chords may overlap. Documented import errors are terminal.
        if TemporaryMdMetadataFile.objects.filter(job=job, has_import_error=False).exists():
            raise self.retry(countdown=5)
        complete_harvest(job.pk)


@shared_task(queue="default", base=HarvestingTask)
def call_fetch_total_records(*args, **kwargs):
    from registry.models.harvest import HarvestingJob

    try:
        with transaction.atomic():
            harvesting_job = HarvestingJob.objects.select_for_update().get(pk=kwargs.get("harvesting_job_id"))
            if harvesting_job.done_at is not None or harvesting_job.phase > HarvestingPhaseEnum.DOWNLOAD_RECORDS:
                return harvesting_job.total_records
            # Reuse the original snapshot's count when recovering downloads.
            recovering = harvesting_job.phase == HarvestingPhaseEnum.DOWNLOAD_RECORDS
            if not recovering or harvesting_job.total_records is None:
                harvesting_job.fetch_total_records()
            harvesting_job.handle_total_records_defined(recovering=recovering)
            harvesting_job.save(skip_history_when_saving=False)
            return harvesting_job.total_records
    except (RequestException, OperationalError, BrokerOperationalError, InternalServerError,
            RedirectChainError):
        # the redirect chain of the endpoint is as explained as the remote errors above: its
        # own error names the URL asked and the target it stopped at, so the report below of
        # a something-which-went-wrong would read like a crash of MrMap instead of a
        # catalogue which does not answer (#1100, read together with #1088)
        raise
    except Exception:
        from registry.enums.harvesting import LogLevelEnum
        from registry.models.harvest import HarvestingLog

        log = HarvestingLog.objects.create(
            harvesting_job_id=kwargs.get("harvesting_job_id"),
            level=LogLevelEnum.ERROR,
            description='something went wrong during call_fetch_total_records()',
        )
        log.extented_description.save(
            name=f"harvesting_log_{log.pk}.txt",
            content=ContentFile(content=traceback.format_exc()),
        )
        raise


@shared_task(queue="download", bind=True, base=HarvestingTask)
def call_fetch_records(self, *args, **kwargs):
    from registry.models.harvest import HarvestingJob

    harvesting_job = HarvestingJob.objects.select_related("service", "service__auth").get(
        pk=kwargs.get("harvesting_job_id"))
    if harvesting_job.done_at is not None or harvesting_job.phase > HarvestingPhaseEnum.DOWNLOAD_RECORDS:
        return 0
    return harvesting_job.fetch_records(
        start_position=kwargs.get("start_position"),
        check_existing=bool(kwargs.get("recovering") or self.request.retries or
                            (self.request.delivery_info or {}).get("redelivered")),
    )


def iter_md_metadata_file_chunks(ids, batch_size=None):
    """Split the ids of stored metadata files into the batches one import task takes.

    The fan-out which writes harvested records to the database is bounded by this:
    one task per chunk instead of one task per record (#859).
    """
    size = batch_size or settings.HARVEST_IMPORT_BATCH_SIZE
    ids = list(ids)
    size = max(1, size)
    for start in range(0, len(ids), size):
        yield ids[start:start + size]


@shared_task(queue=celery_queues.DB_ROUTINES, base=HarvestingTask)
def call_chord_md_metadata_file_to_db(*args, **kwargs):
    """Build (or rebuild) the import chord of a harvesting job.

    The chord control stays on db-routines while its member tasks flood
    harvest-import (#970): this is the message recovery publishes to resume a
    job, and it must stay reachable while a backlog is being consumed - on a
    shared queue it waited behind the very backlog it was meant to build,
    unconsumed for the ~17 h a catalogue takes to drain (#970).
    """
    from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
    from registry.querys.harvest_history import complete_harvest

    harvesting_job_id = kwargs.get("harvesting_job_id")
    with transaction.atomic():
        harvesting_job = HarvestingJob.objects.select_for_update().get(pk=harvesting_job_id)
        if harvesting_job.done_at is not None:
            return
        # a job which is in the import phase already is rebuilt by recovery or
        # the resume command: its backlog was bounded by an earlier build, and
        # the progress already reported belongs to that bound (#958)
        resuming = harvesting_job.phase == HarvestingPhaseEnum.RECORDS_TO_DB
        http_request = kwargs.get("http_request") or harvesting_job._http_request()
        ids = list(TemporaryMdMetadataFile.objects.filter(
            job_id=harvesting_job_id, has_import_error=False).values_list("pk", flat=True))
        task_ids = []
        to_db_tasks = []
        for chunk in iter_md_metadata_file_chunks(ids):
            task_id = uuid4()
            task = call_md_metadata_files_to_db.s(
                md_metadata_file_ids=chunk,
                harvesting_job_id=harvesting_job_id,
                background_process_pk=harvesting_job.background_process_id,
                http_request=http_request)
            task.set(task_id=str(task_id))
            task_ids.append(task_id)
            to_db_tasks.append(task)

        harvesting_job.phase = HarvestingPhaseEnum.RECORDS_TO_DB.value
        if to_db_tasks:
            callback_id = uuid4()
            callback = finish_harvesting_job.s(
                harvesting_job_id=harvesting_job_id,
                http_request=http_request,
            ).set(task_id=str(callback_id))
            harvesting_job.append_celery_task_ids(task_ids + [callback_id])
            harvesting_job.save(skip_history_when_saving=False)
            if resuming:
                reconcile_import_progress(harvesting_job, len(ids))
            else:
                # the steps of the harvest stay granular by record, as the annotations of
                # TemporaryMdMetadataFileQuerySet.with_process_info derive them from the
                # files which are still waiting; bounding the tasks must not move the
                # progress the harvesting UI shows (#859)
                harvesting_job.report_process(
                    ProcessStatusEnum.RUNNING,
                    phase=str(HarvestingPhaseEnum.RECORDS_TO_DB.label),
                    total_steps=len(ids) + 1)
            transaction.on_commit(lambda: chord(to_db_tasks, callback).apply_async(max_retries=300, interval=1))
        else:
            complete_harvest(harvesting_job_id)


def reconcile_import_progress(job, waiting):
    """Bring the reported import steps of a job in line with its backlog.

    The row of the background process is the only account of progress which a
    draining import keeps, and a worker which died took the steps it had
    committed but not reported with it. This is the reconciliation from the
    durable state the issue of #958 asks for: while the backlog only drains,
    every file of the bound which was last set is waiting, flagged or imported,
    so the total minus what is still waiting is exactly the steps the run has
    handled - flagged files included, because the reporting workers credit a
    documented import error as handled work and completion has to be reachable
    with it. The answer is only ever raised onto the process, never lowered, so
    a reconciliation racing with the reports of live workers cannot undo what
    they have seen.

    The total is only ever grown: a rebuild must not shrink the denominator
    with the backlog it drained, that would pull the reported progress down in
    the one number the overview computes from the two. The answer of the
    formula is exact while the backlog only drains; files rescheduled into a
    running import grow the backlog without a durable trace, and across such
    growth the formula cannot tell the new files from imported ones - it then
    answers too little rather than too much. That is the safe direction: the
    steps already reported by live workers stay raised to whatever they have
    seen (``raise_steps``), and the completion of the run reports its steps as
    done anyway.

    A worker which survived its own stale run can flush a credit the rebuild
    already accounted for - bounded by one coalesced batch per such worker and
    capped at the total, while the loss it answers (a worker that died with
    unreported steps) is the case recovery must never under-report.

    Args:
        job: the harvesting job, locked by its caller
        waiting (int): the files of its backlog which are not flagged
    """
    from notify.models import BackgroundProcess  # avoid circular import errors
    from registry.models.harvest import TemporaryMdMetadataFile

    if job.background_process_id is None:
        return
    process = BackgroundProcess.objects.filter(
        pk=job.background_process_id).values("total_steps", "done_steps").first()
    if process is None:
        return
    flagged = TemporaryMdMetadataFile.objects.filter(
        job_id=job.pk, has_import_error=True).count()
    total = max(process["total_steps"] or 0, waiting + flagged + 1)
    done = process["done_steps"] or 0
    # every file of the bound is waiting, flagged or imported - and the live
    # reporters credit the flagged ones as handled work exactly like this
    # answer does: the +1 stays the finish step which no file is
    target = min(max(total - 1 - waiting, 0), total)
    if total != (process["total_steps"] or 0):
        BackgroundProcess.objects.report(
            job.background_process_id, ProcessStatusEnum.RUNNING,
            phase=str(HarvestingPhaseEnum.RECORDS_TO_DB.label),
            total_steps=total)
    if done < target:
        BackgroundProcess.objects.raise_steps(job.background_process_id, target)


def import_md_metadata_file(md_metadata_file_id, on_handled=None):
    """Write a single stored metadata file to the database and return what it created.

    Answers None when there is nothing to import: the row of a successful import is deleted, so
    its absence is the proof that it was imported. The chunk task relies on this to work through
    its ids again after a retry without importing a record twice.

    Only errors of the record itself are terminal and documented on the file. Everything the
    task base of the importing tasks retries is re-raised, so the file is redelivered with the
    backoff of the harvest instead of being lost to a remote or storage outage (#895). The
    integrity error of a service whose stored capabilities document is gone (#1044) is
    re-raised too: it is one broken service, not a broken record, and it must end the run
    once instead of marking every file of the backlog.

    `on_handled` is called once the file left the backlog for good - imported and committed, or
    documented as an import error and kept for inspection (#958). It names a transition which
    is committed by now, so a progress report built on it counts every file exactly once: a
    redelivery which finds the row deleted or already flagged imports nothing and credits
    nothing. Files which are merely skipped because their job is aborted are not handled work
    and credit nothing.
    """
    from registry.models.harvest import TemporaryMdMetadataFile

    try:
        with transaction.atomic():
            temporary_md_metadata_file = TemporaryMdMetadataFile.objects.select_for_update(of=("self",)).select_related(
                'job', 'job__service', 'job__service__auth',
            ).filter(pk=md_metadata_file_id).first()
            # Successful imports delete the row. Errors remain for inspection.
            if temporary_md_metadata_file is None or temporary_md_metadata_file.has_import_error:
                return
            if temporary_md_metadata_file.job.phase in [HarvestingPhaseEnum.ABORT, HarvestingPhaseEnum.ABORTED]:
                return
            results = temporary_md_metadata_file.md_metadata_file_to_db()
            handled = [(str(result[0].pk), result[1], result[2]) for result in results if result is not None]
        # out of the atomic block: the deletion of the row committed with it
        if on_handled is not None:
            on_handled()
        return handled
    except MetadataFileImportTask.autoretry_for:
        # Infrastructure outages and remote failures are retryable, not record import
        # errors: what the task base promises to retry must reach it, or its autoretry
        # is laundered into a terminal has_import_error by the marking below (#895).
        raise
    except CapabilitiesBackupMissing:
        # The catalogue's stored capabilities document is gone from the
        # storage: an integrity error of the service, not of this record.
        # Marking every file of such a run with the same traceback would
        # repeat the per-record multiplication of #1044 as error rows
        # instead of warnings - let the task give up, so the job ends with
        # one loud report naming the missing document and the recovery
        # status, and the backlog stays unflagged for the resumed run.
        raise
    except Exception as e:
        TemporaryMdMetadataFile.objects.filter(pk=md_metadata_file_id).update(
            has_import_error=True,
            import_error=traceback.format_exc()
        )
        logger.error(msg=e)
        # the documented error is terminal: the file is accounted for even though
        # it never became a record, and the total of the harvest counts it
        if on_handled is not None:
            on_handled()


@shared_task(queue=celery_queues.HARVEST_IMPORT, base=MetadataFileImportTask)
def call_md_metadata_file_to_db(*args, **kwargs):
    """Write one stored metadata file to the database.

    One message per stored file is the floodable import backlog of a harvest;
    a catalogue fills this queue for hours, which is why it is a queue of its
    own and nothing which has to answer quickly shares it (#970)."""
    progress_pk = import_progress_pk(kwargs)
    return import_md_metadata_file(
        kwargs.get("md_metadata_file_id"),
        on_handled=lambda: credit_import_progress(progress_pk))


@shared_task(queue=celery_queues.HARVEST_IMPORT, base=MetadataFileImportTask)
def call_md_metadata_files_to_db(*args, **kwargs):
    """Write a chunk of stored metadata files to the database (#859).

    One task per chunk instead of one per record bounds the broker messages, the task round-trips
    and the result writes of a harvest; the records themselves still commit one by one, so a
    record which fails is flagged and does not fail its chunk, and a retryable outage which
    raises for the whole chunk redelivers only what is not committed yet. The row of an aborted
    job is skipped per record, so an abort stops a chunk as early as it stopped a single record.

    The files this task commits are credited to the progress of the process of the job (#958);
    whatever the worker had credited unreported when a retryable outage ended it is flushed on
    the way out, because those files are committed and a redelivery will not count them again.
    """
    imported = []
    progress_pk = import_progress_pk(kwargs)
    try:
        for md_metadata_file_id in kwargs.get("md_metadata_file_ids") or ():
            results = import_md_metadata_file(
                md_metadata_file_id,
                on_handled=lambda: credit_import_progress(progress_pk))
            if results:
                imported.extend(results)
    finally:
        flush_import_progress(progress_pk)
    return imported


@shared_task(
    queue=celery_queues.DB_ROUTINES,
    bind=True,
    base=SingletonTask,
)
def check_for_files_to_import(self, *args, **kwargs):
    """Import the files handed into the drop directory (beat, every 5 minutes).

    The beat message itself stays on db-routines, which a harvest must not be
    able to fill: the backlog its import publishes floods harvest-import
    instead, so the drop directory keeps being watched while a catalogue
    drains (#970)."""
    from registry.models.harvest import TemporaryMdMetadataFile

    logger.info(f"watching for new files to import in '{FILE_IMPORT_DIR}'")
    dt = timezone.now()

    db_md_metadata_file_list = []
    idx = 0
    for dirpath, subdir, files in walk(FILE_IMPORT_DIR):
        files = filter(lambda file: "ignore" not in file, files)

        if files:
            with transaction.atomic():
                for file in files:
                    filename = os.path.join(dirpath, file)
                    try:
                        xml = etree.parse(filename)
                        md_metadatas = xml.xpath(
                            "//*[local-name()='MD_Metadata']")
                        for md_metadata in md_metadatas:
                            md_xml = etree.tostring(
                                md_metadata,
                                pretty_print=True,
                                xml_declaration=True,
                                encoding="utf-8")
                            db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile()
                            # save the file without saving the instance in db...
                            # this will be done with bulk_create
                            db_md_metadata_file.md_metadata_file.save(
                                name=f"file_import_{dt}_{idx}",
                                content=ContentFile(
                                    content=md_xml),
                                save=False)
                            db_md_metadata_file_list.append(
                                db_md_metadata_file)
                            idx += 1

                    except Error as e:
                        new_filename = f"ignore_{dt}_{file}"
                        os.rename(filename, os.path.join(
                            dirpath, new_filename))
                        logger.error(
                            f"can't handle file cause of the following exception: {e}\n the file is renamed as {new_filename} and will be ignored.")

                if db_md_metadata_file_list:
                    db_objs = TemporaryMdMetadataFile.objects.bulk_create_with_task_scheduling(
                        objs=db_md_metadata_file_list)

                    logger.info(
                        f"start file import handling for {len(db_objs)} files")

                    return [db_obj.pk for db_obj in db_objs]

    logger.info("No files to import")
