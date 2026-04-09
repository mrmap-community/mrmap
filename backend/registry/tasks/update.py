import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    queue="default",
)
def create_wms_update_job(*args, **kwargs):
    from registry.models.service import WebMapService
    from registry.models.update import WebMapServiceUpdateJob

    job = WebMapServiceUpdateJob.objects.create(
        service=WebMapService.objects.get(pk=kwargs.get("service_id")))
    return job.pk


@shared_task(
    queue="default",
)
def run_wms_update(*args, **kwargs):
    from registry.models.update import WebMapServiceUpdateJob
    update_job_id = kwargs.get("update_job_id", None)
    try:
        update_job: WebMapServiceUpdateJob = WebMapServiceUpdateJob.objects.get(
            pk=update_job_id)

        update_job.update()
    except WebMapServiceUpdateJob.DoesNotExist:
        logger.error(
            f"Update job with ID {update_job_id} does not exist. Task startet with args: {args} and kwargs: {kwargs}")
