from celery import shared_task, chain, chord, group
from django.core.files.base import ContentFile
from eulxml import xmlmap

from job.models import Job
from job.tasks import NewJob, CurrentTask
from resourceNew.enums.service import OGCOperationEnum, HttpMethodEnum
from resourceNew.models import DatasetMetadata, Service, OperationUrl
from resourceNew.models.harvest import HarvestResult
from resourceNew.ows_client.request_builder import WebService
from resourceNew.parsers.ogc.csw_get_record_response import GetRecordsResponse


@shared_task(name="async_harvest_service",
             bind=True,
             base=NewJob)
def register_service(self,
                     service_id,
                     **kwargs):
    """workflow = chain(create_service_from_parsed_service.s(form, quantity, **kwargs) |
                        group(schedule_collect_feature_type_elements.s(**kwargs) |
                              schedule_collect_linked_metadata.s(**kwargs))
                     )
    workflow.apply_async()"""
    return self.job.pk


@shared_task(name="async_get_records_total_hits",
             bind=True,
             base=CurrentTask)
def get_records_total_hits(self,
                           service_id,
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
    get_records_xml.total_records


@shared_task(name="async_get_records",
             bind=True,
             base=CurrentTask)
def get_records(self,
                service_id,
                max_records,
                start_position,
                **kwargs):

    result_xml = None
    content_type = "xml"
    result = HarvestResult.objects.create(service=Service.objects.get(id=service_id),
                                          job=Job.objects.get(id=self.job.pk))
    result.result_file.save(name=f'{max_records}_{start_position}.{content_type}',
                            content=ContentFile(result_xml))

    return result.pk


@shared_task(name="async_get_records",
             bind=True,
             base=CurrentTask)
def analyze_results(self,
                    harvest_results,
                    **kwargs):
    results = HarvestResult.objects.filter(id__in=harvest_results)
    xml = results.parse()

    if xml.hierarchy_level == "dataset":
        DatasetMetadata.iso_metadata.create_from_parsed_metadata(xml)

    return None