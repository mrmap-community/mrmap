import json
from datetime import datetime, timedelta
from logging import Logger

from celery import Task, shared_task, states
from celery.signals import (task_failure, task_postrun, task_prerun,
                            task_retry, task_revoked)
from celery.utils.time import get_exponential_backoff_interval
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import F
from django.db.models.functions import Coalesce, Now
from django.db.models.signals import post_save
from django.utils.timezone import now
from django_celery_results.models import TaskResult
from MrMap import celery_queues
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.exceptions.harvesting import InternalServerError
from requests.exceptions import ConnectionError, Timeout

logger: Logger = settings.ROOT_LOGGER

#: The stamp which asked the mirroring below to write a task's states into
#: its `TaskResult` row. The asynchronous api stamped the messages it
#: published until the registration contract moved to the `BackgroundProcess`
#: (#1177, D01/B of #1175); the receivers stay for the rows and in-flight
#: messages of that coexistence window, and their removal is #1180 - the
#: `threads` relation which cancellation used to read is retired by #1179
#: without touching this mirroring.
MIRROR_TASK_RESULT_STAMP = 'mirror_task_result'


def mirror_requested(request):
    """Whether the publication of a task asked for its states to be mirrored.

    Historically only a root task published by the asynchronous api had a
    `TaskResult` row to mirror into, and the api said so by stamping the
    message it publishes; celery carries stamped headers in the request of
    the task. Every other task - the harvesting and the monitoring fan out
    among them - is not asked here and does no `TaskResult` sql at all: an
    indexed `UPDATE` which matches no row still costs a database round trip
    per task and signal. Eligibility is therefore read from the message,
    never looked up in the table (#1176).

    `request` is celery's request of the task: the `Context` of a running one
    or the one a revocation hands over.
    """
    if request is None:
        return False
    return MIRROR_TASK_RESULT_STAMP in (request.get('stamped_headers') or [])


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    """To automaticly get the BackgroundProcess object on task runtime."""
    task.background_process_pk = kwargs["kwargs"].get(
        "background_process_pk", None)
    if isinstance(task, BackgroundProcessBased) and task.background_process_pk is not None:
        task.update_background_process()


def serialize_result(retval):
    """The return value of a task as the JSON the TaskResult resource answers from.

    A value this cannot express must not cost a client the state of its task, so
    it is left out and the resource answers an empty result, like it does for
    every row which never got one.
    """
    try:
        return json.dumps(retval)
    except (TypeError, ValueError):
        logger.warning(
            "can't mirror the result of a task of type %s",
            type(retval).__name__)
        return None


def mirror_task_result(task_id, **values):
    """Write what the worker knows about a task into the row the api published it with.

    `AsyncCreateMixin` (extras/viewsets.py) answers a POST which triggers a task
    with a `TaskResult` resource, and polling that resource is how a client learns
    the outcome of its registration (#1146). That code only inserts the row; the
    result backend of this deployment is Celery's native Redis backend
    (`CELERY_RESULT_BACKEND` in MrMap/settings.py), which writes nothing into
    this table, so the state has to be mirrored here or the row keeps reading
    PENDING after the worker answered long ago.

    Which tasks may reach this at all is decided by `mirror_requested` before
    any sql is made, and only a row which already exists is written: the api
    inserts the row of its task before it publishes, and a row for a task it
    never published would fill the resource, which no client asks for, with
    entries of its own.
    """
    if not task_id:
        return

    TaskResult.objects.filter(task_id=task_id).update(**values)


@task_prerun.connect
def mirror_task_result_start(sender, task_id, **kwargs):
    """Mirror that the worker began the task.

    Without this the row reads PENDING while the task is running, which is the
    state a client cannot tell a task which still waits in a queue apart from.
    """
    if not mirror_requested(sender.request):
        return

    mirror_task_result(task_id, status=states.STARTED, date_started=Now())


@task_failure.connect
def mirror_task_result_failure(sender, task_id, einfo, **kwargs):
    """Mirror the error of a task which is not retried any further.

    `einfo.traceback` is the text celery hands to its own result backends for a
    failure, and it is what a client which registered a service wants to read
    about a task that did not build it.
    """
    if not mirror_requested(sender.request):
        return

    mirror_task_result(
        task_id, status=states.FAILURE, traceback=einfo.traceback)


@task_postrun.connect
def mirror_task_result_end(sender, task_id, state, retval, **kwargs):
    """Mirror the state the run ended with, and the value of a successful one.

    `task_postrun` is the only signal handing over the task id together with the
    return value. A state the `TaskResult` model does not know of (`REJECTED`,
    `IGNORED`) is left out: the resource would answer a status its schema does not
    declare, and celery's own database backend does not store those either.
    """
    if not mirror_requested(sender.request):
        return

    if state not in states.ALL_STATES:
        return

    values = {"status": state}
    if state == states.SUCCESS:
        values.update({"result": serialize_result(retval)})
    if state in states.READY_STATES:
        # the column says when the task was completed, so only a state which
        # completed it stamps it - it cannot start out empty, because the third
        # party model declares it auto_now and not null
        values.update({"date_done": Now()})

    mirror_task_result(task_id, **values)


@task_revoked.connect
def mirror_task_result_revoked(sender, request, **kwargs):
    """Mirror a revocation: the task will not run to an end, so no postrun follows.

    The abort of a BackgroundProcess revokes the tasks it still waits for (see
    `BackgroundProcess.save` in notify/models.py), and the client which polls the
    row of one of them has to learn that from it.
    """
    if not mirror_requested(request):
        return

    mirror_task_result(
        (request or {}).get("id"),
        status=states.REVOKED,
        date_done=Now())


@task_retry.connect
def report_process_retry(sender, request, reason, **kwargs):
    """Mirror one retry of a task onto the process which reports its work.

    A retrying task neither failed nor progressed: the operation waits for
    its next attempt, and the process which reports it would otherwise keep
    answering plain running for the whole backoff window - the state the
    overview of the background activity is asked to tell apart (#1207).

    Which process a task reports to is read from the kwargs the broker
    transports - the same seam the ``get_background_process`` above uses for
    the start of a task.
    """
    pk = (getattr(request, "kwargs", None) or {}).get(
        "background_process_pk")
    if pk is None:
        # a task which was never given a process retries invisibly, like the
        # progress reports of a process-less task
        return
    try:
        # celery's Retry carries the textual answer of what the task failed
        # on in `excs` (its safe_repr of the exception) and a context message;
        # str of the exception itself would answer the constructor tuple
        reason_text = (
            getattr(reason, "excs", None)
            or getattr(reason, "message", None)
            or str(reason))
        BackgroundProcess.objects.report_retry(
            pk, reason=reason_text,
            until=retry_scheduled_at(sender, request, reason))
    except Exception as e:
        # the retry itself does not depend on this report; the window closes
        # on its own and the next report of the task answers the state again
        logger.warning(
            "can't report the retry of a task to the process %s: %s", pk, e)


def retry_scheduled_at(sender, request, reason):
    """When the retried attempt of a task is due.

    Whoever asked for the retry handed a delay to ``retry`` whenever it knew
    one: celery carries it on the ``Retry`` exception the signal answers with
    - the seconds of an exponential backoff the autoretry decorator computed
    before calling ``retry``, or an explicit countdown or eta. Only a retry
    which ran without any of them has to have its window answered from the
    task's own retry policy, and then with the very helper and formula celery
    uses for the backoff, not an invented one.

    A window which is estimated is a window which may be a little wrong: an
    attempt which fails again rewrites it, a terminal outcome decides about
    the process anyway, and the state of an operation whose window ran out
    without a report reads running again by itself.
    """
    when = getattr(reason, "when", None)
    if isinstance(when, datetime):
        return when
    if isinstance(when, (int, float)):
        return now() + timedelta(seconds=float(when))
    backoff = getattr(sender, "retry_backoff", False) or 1
    return now() + timedelta(seconds=get_exponential_backoff_interval(
        factor=int(max(1.0, float(backoff))),
        retries=getattr(request, "retries", 0) or 0,
        maximum=int(getattr(sender, "retry_backoff_max", 600) or 600),
        full_jitter=bool(getattr(sender, "retry_jitter", False))))


class BackgroundProcessBased(Task):
    autoretry_for = (Timeout, ConnectionError, InternalServerError)
    retry_backoff = 30
    retry_backoff_max = 5 * 60
    retry_jitter = False
    max_retries = 10

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self.log_process(f"An error occurred: {exc}"[:512])
        self.update_background_process(
            phase=f"An error occurred: {exc}"[:512],
            failed=True
        )

    def log_process(self, description, log_type=None):
        """A durable log entry on the process which this task reports to.

        The process is where a polling client looks, so what the worker
        learned about a step which failed or a run which did not belongs
        beside its state (#1177). A task which was never given a process
        logs nowhere, like the reports of the manager.
        """
        BackgroundProcess.objects.log(
            getattr(self, "background_process_pk", None),
            description, log_type)

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        pass
        # return super().update_state(task_id, state, meta, **kwargs)

    def update_background_process(
        self,
        phase: str = "",
        service=None,
        total_steps=None,
        step_done=False,
        completed=False,
        failed=False,
    ):
        # will be provided by get_background_process signal if the pk is provided by kwargs
        if getattr(self, "background_process_pk", None) is not None:
            try:
                query = BackgroundProcess.objects.filter(
                    pk=self.background_process_pk)
                kwargs = {"status": ProcessStatusEnum.RUNNING}

                if phase:
                    kwargs.update({
                        "phase": phase
                    })
                if service:
                    kwargs.update({
                        "related_resource_type": ContentType.objects.get_for_model(service),
                        "related_id": service.pk
                    })
                if total_steps is not None:
                    kwargs.update({
                        "total_steps": total_steps
                    })
                if step_done:
                    kwargs.update({
                        "done_steps": F("done_steps") + 1
                    })
                if failed:
                    kwargs.update({"status": ProcessStatusEnum.FAILED, "done_at": now()})
                elif completed:
                    kwargs.update({
                        "total_steps": Coalesce(F("total_steps"), 1),
                        "done_steps": Coalesce(F("total_steps"), 1),
                        "done_at": now(),
                        "phase": "completed",
                        "status": ProcessStatusEnum.COMPLETED
                    })

                if kwargs:
                    # A terminal outcome cannot be overwritten by sibling tasks.
                    active_query = query.filter(
                        done_at__isnull=True,
                        status__in=[ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING])
                    bare_running = kwargs == {"status": ProcessStatusEnum.RUNNING}
                    if kwargs.get("status") == ProcessStatusEnum.RUNNING:
                        # any report of a task which works ends the window of a
                        # reported retry: the operation works again (#1207)
                        kwargs["retry_scheduled_until"] = None
                    if bare_running:
                        # get_background_process fires on every task start; a
                        # process which is already running and has no retry
                        # window to close answers nothing to write and must not
                        # broadcast anything either.
                        active_query = active_query.exclude(
                            status=ProcessStatusEnum.RUNNING,
                            retry_scheduled_until__isnull=True)
                    # every write of this path is a state report, and the
                    # revision which orders the reports is counted in the same
                    # UPDATE (#1207)
                    kwargs["revision"] = F("revision") + 1
                    updated = active_query.update(**kwargs)

                    if updated:
                        try:
                            # process_info provides the progress annotation and
                            # the related resource type in one go, so the
                            # post_save receiver doesn't have to reload.
                            instance = BackgroundProcess.objects.process_info().get(
                                pk=self.background_process_pk)
                            post_save.send(
                                BackgroundProcess,
                                instance=instance,
                                created=False
                            )
                        except BackgroundProcess.DoesNotExist:
                            logger.warning(
                                f"Can't get BackgroundProcess by id {self.background_process_pk}")

            except Exception as e:
                logger.exception(e, stack_info=True, exc_info=True)
        else:
            logger.warning(
                f"No background process provided for BackgroundProcessBased task. {self.name}")


@shared_task(
    bind=True,
    queue=celery_queues.DB_ROUTINES,
    base=BackgroundProcessBased
)
def finish_background_process(
    self,
    *args,
    **kwargs
):
    self.update_background_process(
        completed=True
    )
