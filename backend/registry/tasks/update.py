import logging

from celery import shared_task
from django.db import OperationalError, transaction
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

    job = WebFeatureServiceUpdateJob.objects.create(
        service=WebFeatureServiceUpdateSetting.objects.get(
            name=kwargs.get("name")).service
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

    job = CatalogueServiceUpdateJob.objects.create(
        service=CatalogueServiceUpdateSetting.objects.get(
            name=kwargs.get("name")).service
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
