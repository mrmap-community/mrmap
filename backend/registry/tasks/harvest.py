
from celery import shared_task
from django.utils.timezone import now
from eulxml import xmlmap
from registry.models import DatasetMetadata
from registry.models.harvest import HarvestingJob
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
    for md_metadata in xml.records:
        dataset_metadata, update, exists = DatasetMetadata.iso_metadata.update_or_create_from_parsed_metadata(
            parsed_metadata=md_metadata,
            related_object=harvesting_job.service,
            origin_url=harvesting_job.service.get_record_by_id_url(id=md_metadata.file_identifier))

        if exists and update:
            harvesting_job.updated_records.add(dataset_metadata)
        elif exists and not update:
            harvesting_job.existing_records.add(dataset_metadata)
        elif not exists:
            harvesting_job.new_records.add(dataset_metadata)

    return None


@shared_task(queue="harvest")
def set_done_at(list, harvesting_job_id):
    harvesting_job: HarvestingJob = HarvestingJob.objects.get(
        pk=harvesting_job_id)
    harvesting_job.done_at = now()
    harvesting_job.save()
