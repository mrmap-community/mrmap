import logging

from celery import shared_task

from registry import models

logger = logging.getLogger(__name__)


@shared_task(queue="default")
def create_wms_update_job(*args, **kwargs):
    job = models.WebMapServiceUpdateJob.objects.create(
        service=models.WebMapService.objects.get(pk=kwargs.get("service_id"))
    )
    return job.pk


@shared_task(queue="default")
def run_wms_update(*args, **kwargs):
    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = models.WebMapServiceUpdateJob.objects.get(pk=update_job_id)
        update_job.update()
    except models.WebMapServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )


@shared_task(queue="default")
def run_wfs_update(*args, **kwargs):
    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = models.WebFeatureServiceUpdateJob.objects.get(pk=update_job_id)
        update_job.update()
    except models.WebFeatureServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )

@shared_task(queue="default")
def run_csw_update(*args, **kwargs):
    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = models.CatalogueServiceUpdateJob.objects.get(pk=update_job_id)
        update_job.update()
    except models.CatalogueServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )
