from celery import shared_task, chain, chord, group
from django.core.files.base import ContentFile
from django.utils import timezone
from eulxml import xmlmap
from job.tasks import NewJob, CurrentTask
from resourceNew.enums.service import OGCOperationEnum, HttpMethodEnum
from resourceNew.models import DatasetMetadata, Service, OperationUrl
from resourceNew.models.harvest import HarvestResult
from resourceNew.ows_client.request_builder import CatalogueServiceWeb
from resourceNew.parsers.ogc.csw_get_record_response import GetRecordsResponse
from structure.enums import PendingTaskEnum


@shared_task(name="async_harvest_service",
             bind=True,
             base=NewJob)
def harvest_service(self,
                    service,
                    **kwargs):
    workflow = schedule_get_records.s(service, **kwargs)
    workflow.apply_async()
    return self.job.pk


@shared_task(name="async_schedule_get_records",
             bind=True,
             base=CurrentTask)
def schedule_get_records(self,
                         service_id,
                         step_size=100,
                         **kwargs):
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url", flat=True).get(service__id=service_id,
                                                                             operation=OGCOperationEnum.GET_RECORDS.value,
                                                                             method=HttpMethodEnum.GET.value)
    remote_service = CatalogueServiceWeb(base_url=get_records_url,
                                         version=db_service.service_version)
    request = remote_service.get_get_records_request(**{remote_service.TYPE_NAME_QP: "gmd:MD_Metadata",
                                                        remote_service.OUTPUT_SCHEMA_QP: "http://www.isotc211.org/2005/gmd",
                                                        remote_service.RESULT_TYPE_QP: "hits"})
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
        get_record_tasks.append(get_records.s(service_id, max_records, step_size, start_position, **kwargs))
    header = get_record_tasks
    callback = analyze_results.s(service_id, **kwargs)
    chord(header)(callback)


@shared_task(name="async_get_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def get_records(self,
                service_id,
                max_records,
                step_size,
                start_position,
                **kwargs):
    db_service = Service.objects.get(pk=service_id)
    get_records_url = OperationUrl.objects.values_list("url", flat=True).get(service__id=service_id,
                                                                             operation=OGCOperationEnum.GET_RECORDS.value,
                                                                             method=HttpMethodEnum.GET.value)
    remote_service = CatalogueServiceWeb(base_url=get_records_url,
                                         version=db_service.service_version)
    request = remote_service.get_get_records_request(**{remote_service.TYPE_NAME_QP: "gmd:MD_Metadata",
                                                        remote_service.OUTPUT_SCHEMA_QP: "http://www.isotc211.org/2005/gmd",
                                                        remote_service.RESULT_TYPE_QP: "results",
                                                        remote_service.MAX_RECORDS_QP: step_size,
                                                        remote_service.START_POSITION_QP: start_position})
    session = db_service.get_session_for_request()
    response = session.send(request.prepare())

    content_type = response.headers.get("content-type")
    if "/" in content_type:
        content_type = content_type.split("/")[-1]
    result = HarvestResult.objects.create(service=Service.objects.get(id=service_id),
                                          job=self.task.job)
    result.result_file.save(name=f'{start_position}_to_{start_position + step_size - 1}_of_{max_records}.{content_type}',
                            content=ContentFile(response.text))
    return result.pk


@shared_task(name="async_analyze_records",
             bind=True,
             base=CurrentTask,
             queue="harvest")
def analyze_results(self,
                    harvest_results,
                    service_id,
                    **kwargs):
    service = Service.objects.get(pk=service_id)
    results = HarvestResult.objects.filter(id__in=harvest_results)
    dataset_list = []
    for result in results:
        xml = result.parse()
        for md_metadata in xml.records:
            try:
                if md_metadata.hierarchy_level == "dataset":
                    dataset = DatasetMetadata.iso_metadata.create_from_parsed_metadata(parsed_metadata=md_metadata,
                                                                                       related_object=service,
                                                                                       origin_url=None)
                    dataset_list.append(dataset.pk)
            except Exception as e:
                # todo: log the exception
                pass
    if self.task:
        self.task.status = PendingTaskEnum.SUCCESS.value
        self.task.done_at = timezone.now()
        self.task.phase = f'Done. <a href="{DatasetMetadata.get_table_url()}?id__in={",".join(str(pk) for pk in dataset_list)}">dataset metadata</a>'
        self.task.save()
    return dataset_list
