import logging

from celery import chord, shared_task
from django.db import OperationalError, transaction
from notify.tasks import BackgroundProcessBased
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


@shared_task(queue="default")
def run_wfs_update(*args, **kwargs):
    from registry.models.update import WebFeatureServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = WebFeatureServiceUpdateJob.objects.get(
            pk=update_job_id)
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


@shared_task(queue="default")
def run_csw_update(*args, **kwargs):
    from registry.models.update import CatalogueServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = CatalogueServiceUpdateJob.objects.get(
            pk=update_job_id)
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
