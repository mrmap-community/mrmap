
from tracemalloc import start

from celery import shared_task
from django.core.files.base import ContentFile
from django.utils.timezone import now
from eulxml import xmlmap
from registry.models import DatasetMetadata
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.xmlmapper.iso_metadata.iso_metadata import MdMetadata
from registry.xmlmapper.ogc.csw_get_record_response import \
    GetRecordsResponse as XmlGetRecordsResponse
from requests.models import Response


def get_hits_task(harvesting_job_id):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    get_records_hits_url: str = harvesting_job.service.get_records_hits_url()
    response: Response = harvesting_job.service.send_get_request(
        url=get_records_hits_url, timeout=60)
    xml: XmlGetRecordsResponse = xmlmap.load_xmlobject_from_string(string=response.text,
                                                                   xmlclass=XmlGetRecordsResponse)
    harvesting_job.started_at = now()
    harvesting_job.total_records = xml.total_records
    harvesting_job.save()
    return xml.total_records


@shared_task(queue="harvest")
def get_records_task(harvesting_job_id,
                     start_position,
                     **kwargs):
    harvesting_job: HarvestingJob = HarvestingJob.objects.select_related("service").get(
        pk=harvesting_job_id)
    step_size: int = harvesting_job.step_size

    get_records_url: str = harvesting_job.service.get_records_url(
        max_records=step_size, start_position=start_position)
    response: Response = harvesting_job.service.send_get_request(
        url=get_records_url, timeout=60)
    xml: XmlGetRecordsResponse = xmlmap.load_xmlobject_from_string(string=response.text,
                                                                   xmlclass=XmlGetRecordsResponse)

    md_metadata: MdMetadata
    db_md_metadata_file_list = []
    _counter = 0
    for md_metadata in xml.records:
        db_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile(
            job=harvesting_job)
        # save the file without saving the instance in db... this will be done with bulk_create
        db_md_metadata_file.md_metadata_file.save(
            name=f"record_nr_{_counter + start_position}",
            content=ContentFile(content=md_metadata.serializeDocument()),
            save=False)
        db_md_metadata_file_list.append(db_md_metadata_file)
        _counter += 1

    db_objs = TemporaryMdMetadataFile.objects.bulk_create(
        objs=db_md_metadata_file_list)

    return db_objs


@shared_task(queue="harvest")
def temporary_md_metadata_file_to_db(md_metadata_file_id):
    temporary_md_metadata_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
        pk=md_metadata_file_id)
    dataset_metadata = temporary_md_metadata_file.md_metadata_file_to_db()
    # TODO: delete temporary_md_metadata_file and check if there any existing temporary_md_metadata_file objects left.. if not set done_at
    return dataset_metadata.pk
