import logging
import traceback
from datetime import timedelta

from celery import chord, shared_task
from django.conf import settings
from django.db import OperationalError, transaction
from django.utils.timezone import now
from extras.tasks import SingletonTask
from MrMap import celery_queues
from notify.tasks import BackgroundProcessBased
from registry.enums.update import UpdateJobStatusEnum
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


@shared_task(queue="default")
def create_wms_update_job(*args, **kwargs):
    from registry.models.update import (WebMapServiceUpdateJob,
                                        WebMapServiceUpdateSetting)

    with transaction.atomic():
        job, created = WebMapServiceUpdateJob.objects.get_or_create(
            service=WebMapServiceUpdateSetting.objects.get(
                name=kwargs.get("name")).service,
            done_at__isnull=True,
        )
        if not created:
            # Recover lost deliveries, including failures after the job was
            # committed but before its initial message reached the broker.
            # The runner locks the job and checks completion/review status.
            transaction.on_commit(lambda: run_wms_update.apply_async(
                kwargs={"update_job_id": job.pk}))
    return job.pk


@shared_task(
    queue="default",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(RequestException, OperationalError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def run_wms_update(*args, **kwargs):
    from registry.enums.update import UpdateJobStatusEnum
    from registry.models.update import WebMapServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        with transaction.atomic():
            update_job = WebMapServiceUpdateJob.objects.select_for_update().get(
                pk=update_job_id)
            if update_job.status == UpdateJobStatusEnum.REVIEW_REQUIRED.value:
                if not update_job.are_all_layers_updateable():
                    return
            elif update_job.done_at is not None:
                return
            update_job.update()
    except WebMapServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )


@shared_task(queue="default")
def create_wfs_update_job(*args, **kwargs):
    from registry.models.update import (WebFeatureServiceUpdateJob,
                                        WebFeatureServiceUpdateSetting)

    job, _ = WebFeatureServiceUpdateJob.objects.get_or_create(
        service=WebFeatureServiceUpdateSetting.objects.get(
            name=kwargs.get("name")).service,
        done_at__isnull=True,
    )
    return job.pk


@shared_task(
    queue="default",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(RequestException, OperationalError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def run_wfs_update(*args, **kwargs):
    """Run the update a schedule, a manual request or a review handed over.

    The guards of ``run_wms_update``, ported to the WFS runner (#1453). Without
    them a message acknowledged before its worker died is gone for good: the job
    stays unfinished, the one-unfinished-job-per-service constraint makes the
    next period re-use it without enqueueing anything, and the service is never
    updated again. With them the broker answers the lost delivery once more -
    and the read of the job under its row lock is what keeps that redelivery
    from running the same update twice: a job which decided about itself, and a
    mapping which still waits for its review, answer without touching the
    update. A transient failure of the remote or of the database retries
    instead of ending the run.
    """
    from registry.enums.update import UpdateJobStatusEnum
    from registry.models.update import WebFeatureServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        with transaction.atomic():
            update_job = WebFeatureServiceUpdateJob.objects.select_for_update().get(
                pk=update_job_id)
            if update_job.status == UpdateJobStatusEnum.REVIEW_REQUIRED.value:
                if not update_job.are_all_featuretypes_updateable():
                    return
            elif update_job.done_at is not None:
                return
            update_job.update()
    except WebFeatureServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )


@shared_task(queue="default")
def create_csw_update_job(*args, **kwargs):
    from registry.models.update import (CatalogueServiceUpdateJob,
                                        CatalogueServiceUpdateSetting)

    job, _ = CatalogueServiceUpdateJob.objects.get_or_create(
        service=CatalogueServiceUpdateSetting.objects.get(
            name=kwargs.get("name")).service,
        done_at__isnull=True,
    )
    return job.pk


@shared_task(
    queue="default",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(RequestException, OperationalError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 5},
)
def run_csw_update(*args, **kwargs):
    """Run the update a schedule or a manual request handed over.

    The same guards as for ``run_wfs_update`` (#1453): the redelivery of a
    delivery whose worker died must not run the update of a service a second
    time, so the job is read under its row lock and a job which is over answers
    without fetching anything. A CSW has no elements to map, so its run never
    stands at a review: the WMS' branch for an unanswered mapping has nothing to
    answer here, and the guard is the job's own end.
    """
    from registry.models.update import CatalogueServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        with transaction.atomic():
            update_job = CatalogueServiceUpdateJob.objects.select_for_update().get(
                pk=update_job_id)
            if update_job.done_at is not None:
                return
            update_job.update()
    except CatalogueServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )


@shared_task(
    bind=True,
    queue="default",
    base=BackgroundProcessBased,
)
def collect_update_metadata(self, background_process_pk=None, **kwargs):
    """Collect the metadata an updated service advertises (#1274).

    The step an update was missing. The job which adopted its candidate
    publishes this for the process which reports it, and the step runs the
    collection machinery a registration already uses: it seals one plan of one
    work row per advertised reference (#1263), publishes one
    ``collect_reference`` delivery per row and lets the chord body wait until
    every reference answered. Nothing here fetches, imports or reports a
    document of its own, and no second harvesting mechanism is involved.

    What it collects are the references which describe the service as this
    update published it - the rows a rejected candidate carried died with it,
    so an element which was never adopted creates nothing. That is also how a
    service which was registered before this step exists gains its records with
    its next scheduled or manual update: the backfill of the epic's D5, without
    a data migration.

    The step names how many references it expects on the process before the
    fan-out is published (#1259) and reports into the process of the update it
    belongs to, which is what makes it visible in the job center row of that
    update. It does not close the run: the completion of the fan-out closes the
    job (#1274), so an update never reports done while its records are missing.
    """
    from registry.models.update import \
        update_job_for_process  # local import: cycle
    from registry.tasks.service import (advertised_references,
                                        collect_reference,
                                        finish_metadata_collection,
                                        plan_registration_references)

    job = update_job_for_process(background_process_pk)
    if job is None:
        # no update job reports to this process anymore - its run is over, it
        # was deleted, or the process belongs to a registration: there is
        # nothing to collect and nobody whose step this is
        logger.warning(
            f"No update job reports to background process "
            f"{background_process_pk}; its metadata step collects nothing.")
        return None

    # the plan is sealed exactly once (#1263): a redelivery of this step finds
    # it sealed and writes no second fan-out, while the chord of the delivery
    # which sealed it still closes the run
    sealed = plan_registration_references(
        self, background_process_pk,
        advertised_references(job.service), job.service)
    if sealed is None:
        logger.warning(
            f"BackgroundProcess {background_process_pk} holds no open plan to "
            f"publish for: this delivery of an update's metadata step found "
            f"its reference plan already sealed, or the process decided or "
            f"gone. It writes no second fan-out.")
        # Only an active process means somebody still drives the fan-out
        # whose seal this found closed. A decided or vanished process
        # collects nothing ever again, and the run may not stay unfinished
        # for a step nobody drives: it closes as it stands (#1274).
        from notify.models import BackgroundProcess  # local import: cycle
        process = BackgroundProcess.objects.filter(
            pk=background_process_pk).first()
        if process is None or process.done_at is not None:
            job.metadata_step_completed()
        return None
    if not sealed:
        # planned empty: the service advertises no metadata reference, so there
        # is nothing to wait for and the step answers where it stands - the run
        # closes with its zero-reference summary (#1263)
        job.metadata_step_completed()
        return len(sealed)

    chord(
        [
            collect_reference.s(
                temporary_md_metadata_file_id=row_id,
                background_process_pk=background_process_pk)
            for row_id in sealed
        ])(
            finish_metadata_collection.s(
                background_process_pk=background_process_pk),
            max_retries=300, interval=1)
    # a publish the broker refuses leaves the sealed plan behind with nothing
    # queued: the recovery of #1263 reads exactly that shape out of the database
    # and re-drives it, and the completion it publishes closes this job too
    return len(sealed)


# ---------------------------------------------------------------------------
# The sweep of stale unfinished service-update jobs (#1460)
#
# The guards of #1453 answer the lost delivery: a redelivery finds the job under
# its row lock and either runs it or answers what it already decided. What no
# guard answers is the delivery which is gone for good - a broker recreated with
# the database kept, a purge, a discard - and the run whose retries died without
# the job ever deciding: the job stands unfinished, and the constraint of one
# unfinished job per service (``only_one_unfinished_update_per_service``) makes
# every later fire of its schedule re-use it without enqueueing anything. The
# service is then never updated again, silently, forever.
#
# This sweep is the belt-and-braces of the issue: it fails unfinished jobs which
# stand beyond a configurable horizon (``UPDATE_JOB_STALE_HORIZON_HOURS``, see
# MrMap/settings.py) and tells the incident channel of #1319 about every service
# it decided about. The horizon is what distinguishes a job which still works
# from one nobody drives - no legitimate update run takes this long - and a job
# a worker takes at this very moment is protected by the same row lock the
# runners of #1453 hold: whoever reads the row under the lock first decides, and
# the runner which wakes on a decided job answers without fetching anything.
# ---------------------------------------------------------------------------

#: the statuses the sweep may decide about: the job which waits for its worker,
#: the job whose run was started, and the job handed back for a resumed run -
#: the unfinished states which name work nobody decided yet
STALE_SWEEP_STATUSES = [
    UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value,
    UpdateJobStatusEnum.UPDATING.value,
    UpdateJobStatusEnum.RESUME.value,
]

#: the suffix of the verdict code the sweep reports; together with the watchdog
#: prefix of #1320's reporting module it names "an update job stood stale", one
#: standing incident per service, resolved by the terminal resolver of that
#: module when the service's next update completes
STALE_UPDATE_JOB_CODE_SUFFIX = "stale_update_job"


def update_job_stale_horizon():
    """The time an unfinished update job may stand before the sweep decides.

    The deployment answers with ``UPDATE_JOB_STALE_HORIZON_HOURS``; the floor of
    one hour keeps a misconfigured 0 from failing jobs which only waited a
    moment for a busy queue - the queue's own watchdog is #1320's verdict, not
    this sweep.
    """
    return timedelta(hours=max(1, int(getattr(
        settings, "UPDATE_JOB_STALE_HORIZON_HOURS", 24))))


def update_job_models():
    """The concrete kinds of service-update job, every one the sweep reads."""
    from registry.models.update import (CatalogueServiceUpdateJob,
                                        WebFeatureServiceUpdateJob,
                                        WebMapServiceUpdateJob)

    return (WebMapServiceUpdateJob, WebFeatureServiceUpdateJob,
            CatalogueServiceUpdateJob)


def sweep_stale_update_job(job_model, update_job_id, horizon=None):
    """Fail one stale unfinished job and tell the incident channel about it.

    The decision and its report are separate commits: a job which was decided
    must not be undone by an incident which cannot be written - the posture of
    #1320 turned to the sweep's side, an unwritable report is told and the
    service stops being blocked either way.

    Args:
        job_model: the concrete job kind of the job
        update_job_id: the job to decide about
        horizon: the configured horizon to name on the report; read again here
            when not given

    Returns:
        bool: whether this call decided the job (``False`` when the job is over
            or was redriven while the sweep waited for its row lock)
    """
    from notify.models import BackgroundProcess  # local import: cycle

    horizon = horizon or update_job_stale_horizon()
    with transaction.atomic():
        # the same locked read as the runners of #1453: a job which is over, at
        # a review, or meanwhile decided answers without a second decision
        job = job_model.objects.select_for_update().filter(
            pk=update_job_id,
            done_at__isnull=True,
            status__in=STALE_SWEEP_STATUSES).first()
        if job is None:
            return False
        stale_label = str(UpdateJobStatusEnum(job.status).label)
        if job.background_process_id is not None:
            # the process log is the per-execution evidence of #1208 and it
            # outlives the decided report, so the story of the sweep is on the
            # process itself and not only in the incident
            BackgroundProcess.objects.log(
                job.background_process_id,
                f"stale update job sweep: the job stood unfinished as "
                f"'{stale_label}' since {job.date_created.isoformat()} and "
                f"was failed beyond the horizon of {horizon} (#1460)")
        # finish writes the process as FAILED and frees the constraint of the
        # service: from here its schedule creates a fresh job again
        job.finish(UpdateJobStatusEnum.ERROR)
    _report_stale_update_job(job, stale_label, horizon)
    return True


def _report_stale_update_job(job, stale_label, horizon):
    """Publish the watchdog verdict about one job the sweep decided (#1460).

    The verdict goes through the one reporting seam of #1320 over the process
    which reports the job, so it names the service as its typed resource and
    the terminal resolver of that module resolves it with the service's next
    completed update.
    """
    from notify.enums import IncidentSeverityEnum
    from notify.incident_reporting import (WATCHDOG_CODE_PREFIX,
                                           publish_watchdog_verdict)

    process = job.background_process
    if process is None:
        # the verdict is told over the process which reports the operation; a
        # job whose process is gone keeps its decision in its own row and in
        # the service alert of #1030, which reads the errored job directly
        logger.warning(
            f"the stale update job sweep failed job {job.pk} of service "
            f"{job.service_id} without an incident: its background process "
            f"is gone")
        return
    summary = (
        f"The service update job {job.pk} stood unfinished as "
        f"'{stale_label}' since {job.date_created.isoformat()} and was "
        f"failed by the stale update job sweep beyond the horizon of "
        f"{horizon}.")
    try:
        incident, created = publish_watchdog_verdict(
            f"{WATCHDOG_CODE_PREFIX}{STALE_UPDATE_JOB_CODE_SUFFIX}",
            process,
            IncidentSeverityEnum.ERROR.value,
            summary,
            {
                "update_job": str(job.pk),
                "job_status": stale_label,
                "date_created": job.date_created.isoformat(),
                "horizon": str(horizon),
            })
    except Exception as e:
        # the job is decided and its service is free - an incident which
        # cannot be written never rolls that back
        logger.warning(
            f"can't publish the stale update job incident of job {job.pk}: "
            f"{e}")
        return
    if incident is not None:
        logger.info(
            f"the stale update job sweep reported incident "
            f"{incident.dedup_key} ({'new' if created else 'standing'}) for "
            f"the failed job {job.pk} (#1460)")


@shared_task(queue=celery_queues.DB_ROUTINES, base=SingletonTask)
def sweep_stale_update_jobs(*args, at=None, **kwargs):
    """Fail the service-update jobs which stand stale beyond the horizon.

    The housekeeping of the issue: every fire reads the unfinished jobs of
    every kind which stood in a not-yet-decided state since before the horizon
    - jobs which wait for a worker that will never come, whose worker died for
    good, or whose retries ended with the broker no longer holding a trace -
    and decides each one about itself as an error, so its schedule is free
    again. A mapping which waits for a human review is not swept: it belongs
    to the human who was asked to answer it, and it says so in the job center
    as action-required (#1207). A job which decided its outcome while its
    metadata step is open is not swept either: the recovery of #1274/#1263
    redrives that step, and the step itself closes such a run when nobody
    drives it anymore.

    The message goes to db-routines like the other beat housekeeping, and the
    ``SingletonTask`` skips a fire which meets an earlier one still reading.
    """
    at = at or now()
    horizon = update_job_stale_horizon()
    cutoff = at - horizon
    swept = []
    for job_model in update_job_models():
        # materialised per kind: the sweep commits decisions while it walks,
        # and it must judge every job by the snapshot the scan took
        stale_ids = list(job_model.objects.filter(
            done_at__isnull=True,
            status__in=STALE_SWEEP_STATUSES,
            date_created__lt=cutoff,
        ).order_by("pk").values_list("pk", flat=True))
        for job_id in stale_ids:
            try:
                if sweep_stale_update_job(job_model, job_id, horizon=horizon):
                    swept.append(job_id)
            except Exception:
                # one job which cannot be read must not keep the others
                # standing; its next fire is the answer
                logger.error(
                    f"could not sweep the stale {job_model.__name__} "
                    f"{job_id}: {traceback.format_exc()}")
    if swept:
        logger.info(
            f"the stale update job sweep failed {len(swept)} unfinished "
            f"service-update jobs beyond the horizon of {horizon} (#1460)")
    return swept
