
from celery import shared_task
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from requests.exceptions import Timeout


@shared_task(
    queue="default",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5}
)
def call_fetch_total_records(harvesting_job_id):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    return harvesting_job.fetch_total_records()


@shared_task(
    queue="download",
    autoretry_for=(Timeout,),
    retry_kwargs={'max_retries': 5}
)
def call_fetch_records(harvesting_job_id,
                       start_position,
                       **kwargs):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    return harvesting_job.fetch_records(start_position=start_position)


@shared_task(queue="db-calc")
def call_md_metadata_file_to_db(md_metadata_file_id: int):
    temporary_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
        pk=md_metadata_file_id)
    try:
        dataset_metadata = temporary_md_metadata_file.md_metadata_file_to_db()
    except Exception as exception:
        return {
            "id": exception.__class__.__name__,
            "title": f"can't created MetadataRecord from xml. TemporaryMdMetadataFile id: {md_metadata_file_id}",
            "detail": str(exception)
        }
    return dataset_metadata.pk
