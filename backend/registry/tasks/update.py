import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(queue="default")
def create_wms_update_job(*args, **kwargs):
    from registry.models.update import (WebMapServiceUpdateJob,
                                        WebMapServiceUpdateSetting)

    job = WebMapServiceUpdateJob.objects.create(
        service=WebMapServiceUpdateSetting.objects.get(
            name=kwargs.get("name")).service
    )
    return job.pk


@shared_task(queue="default")
def run_wms_update(*args, **kwargs):
    from registry.models.update import WebMapServiceUpdateJob

    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job = WebMapServiceUpdateJob.objects.get(
            pk=update_job_id)
        update_job.update()
    except WebMapServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}"
        )


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
