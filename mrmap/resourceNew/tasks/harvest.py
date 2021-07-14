from celery import shared_task, chain, chord, group
from django.core.files.base import ContentFile
from django.utils import timezone
from eulxml import xmlmap

from job.models import Job
from job.tasks import NewJob, CurrentTask
from resourceNew.enums.service import OGCOperationEnum, HttpMethodEnum
from resourceNew.models import DatasetMetadata, Service, OperationUrl
from resourceNew.models.harvest import HarvestResult
from resourceNew.ows_client.request_builder import WebService
from resourceNew.parsers.ogc.csw_get_record_response import GetRecordsResponse
from structure.enums import PendingTaskEnum


@shared_task(name="async_harvest_service",
             bind=True,
             base=NewJob)
def register_service(self,
                     service_id,
                     **kwargs):
    workflow = schedule_get_records.s(service_id, **kwargs)
    workflow.apply_async()
    return self.job.pk


@shared_task(name="async_get_records_total_hits",
             bind=True,
             base=CurrentTask)
def schedule_get_records(self,
                         service_id,
                         step_size=100,
                         **kwargs):
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url").get(service__id=service_id,
                                                                  operation=OGCOperationEnum.GET_RECORDS.value,
                                                                  method=HttpMethodEnum.GET.value)
    remote_service = WebService.manufacture_service(url=get_records_url)
    request = remote_service.get_get_records_request(**{"type_name_list": "gmd:MD_Metadata",
                                                        "result_type": "hits"})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())

    get_records_xml = xmlmap.load_xmlobject_from_string(string=response.content,
                                                        xmlclass=GetRecordsResponse)

    max_records = get_records_xml.total_records
    round_trips = (max_records // step_size)
    if max_records % step_size > 0:
        round_trips += 1

    get_record_tasks = []
    for round_trip in range(round_trips):
        start_position = round_trip * step_size
        if round_trip != 0:
            start_position += 1
        get_record_tasks.append(get_records.s(service_id, max_records, start_position, **kwargs))
    header = get_record_tasks
    callback = analyze_results.s(**kwargs)
    chord(header)(callback)


@shared_task(name="async_get_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def get_records(self,
                service_id,
                max_records,
                start_position,
                **kwargs):
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url").get(service__id=service_id,
                                                                  operation=OGCOperationEnum.GET_RECORDS.value,
                                                                  method=HttpMethodEnum.GET.value)
    remote_service = WebService.manufacture_service(url=get_records_url)
    request = remote_service.get_get_records_request(**{"type_name_list": "gmd:MD_Metadata",
                                                        "max_records": max_records,
                                                        "start_position": start_position})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())

    content_type = response.headers.get("content-type")
    if "/" in content_type:
        content_type = content_type.split("/")[-1]
    result = HarvestResult.objects.create(service=Service.objects.get(id=service_id),
                                          job=Job.objects.get(id=self.job.pk))
    result.result_file.save(name=f'{max_records}_{start_position}.{content_type}',
                            content=ContentFile(response.text))
    return result.pk


@shared_task(name="async_analyze_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def analyze_results(self,
                    harvest_results,
                    **kwargs):
    results = HarvestResult.objects.filter(id__in=harvest_results)
    dataset_list = []
    for result in results:
        xml = result.parse()
        for md_metadata in xml.records:
            if md_metadata.hierarchy_level == "dataset":
                dataset_list.append(DatasetMetadata.iso_metadata.create_from_parsed_metadata(md_metadata))
    if self.task:
        self.task.status = PendingTaskEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{DatasetMetadata.get_table_url()}?id__in={",".join(str(pk) for pk in dataset_list)}">dataset metadata</a>'
        self.task.save()
    return dataset_list
