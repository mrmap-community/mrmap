from celery import shared_task, states
from celery.canvas import group
from django.conf import settings
from django.db import transaction
from extras.tasks import CurrentUserTaskMixin
from registry.models import CatalougeService, WebFeatureService, WebMapService
from registry.models.metadata import DatasetMetadata, RemoteMetadata
from registry.models.security import ServiceAuthentication
from registry.xmlmapper.ogc.capabilities import CswService as CswXmlMapper
from registry.xmlmapper.ogc.capabilities import Wfs200Service as WfsXmlMapper
from registry.xmlmapper.ogc.capabilities import WmsService as WmsXmlMapper
from registry.xmlmapper.ogc.capabilities import get_parsed_service
from requests import Request, Session
from rest_framework.reverse import reverse


@shared_task(bind=True,
             base=CurrentUserTaskMixin)
def build_ogc_service(self, get_capabilities_url: str, collect_metadata_records: bool, service_auth_pk: None, **kwargs):
    self.update_state(state=states.STARTED, meta={
                      'done': 0, 'total': 3, 'phase': 'download capabilities document...'})

    auth = None
    if service_auth_pk:
        auth = ServiceAuthentication.objects.get(id=service_auth_pk)

    session = Session()
    session.proxies = settings.PROXIES
    request = Request(method="GET",
                      url=get_capabilities_url,
                      auth=auth.get_auth_for_request() if auth else None)
    response = session.send(request.prepare())

    self.update_state(state=states.STARTED, meta={
                      'done': 1, 'total': 3, 'phase': 'parse capabilities document...'})

    parsed_service = get_parsed_service(xml=response.content)

    self.update_state(state=states.STARTED, meta={
                      'done': 2, 'total': 3, 'phase': 'persisting service...'})

    with transaction.atomic():
        # create all needed database objects and rollback if any error occours to avoid from database inconsistence
        # FIXME: pass the current user
        if isinstance(parsed_service, WmsXmlMapper):
            db_service = WebMapService.capabilities.create_from_parsed_service(
                parsed_service=parsed_service)
        elif isinstance(parsed_service, WfsXmlMapper):
            db_service = WebFeatureService.capabilities.create_from_parsed_service(
                parsed_service=parsed_service)
        elif isinstance(parsed_service, CswXmlMapper):
            db_service = CatalougeService.capabilities.create_from_parsed_service(
                parsed_service=parsed_service)
        else:
            raise NotImplementedError(
                "Unknown XML mapper detected. Only WMS, WFS and CSW services are allowed.")

        if auth:
            auth.service = db_service
            auth.save()

    self.update_state(state=states.SUCCESS, meta={'done': 3, 'total': 3})

    return_dict = {
        "data": {
            "type": "OgcService",
            "id": f"{db_service.pk}",
            "links": {
                "self": f"{reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}"
            }
        }
    }

    if collect_metadata_records:
        remote_metadata_list = RemoteMetadata.objects.filter(
            service__pk=db_service.pk)
        if remote_metadata_list:
            job = group([fetch_remote_metadata_xml.s(remote_metadata.pk, **kwargs)
                        for remote_metadata in remote_metadata_list])
            group_result = job.apply_async()
            group_result.save()

            data = return_dict["data"]
            data.update({
                "meta": {
                    "collect_metadata_records_job_id": group_result.id
                }
            })

    return return_dict


@shared_task(bind=True,
             base=CurrentUserTaskMixin,
             queue="download_iso_metadata")
def fetch_remote_metadata_xml(self, remote_metadata_id, **kwargs):
    self.update_state(state=states.STARTED, meta={
                      'done': 0, 'total': 1, 'phase': 'fetching remote document...'})
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
        self.update_state(state=states.STARTED, meta={'done': 1, 'total': 2})
        metadata_record = remote_metadata.create_metadata_instance()
        self.update_state(state=states.STARTED, meta={'done': 2, 'total': 2})
        return {
            "data": {
                "type": "DatasetMetadata" if isinstance(metadata_record, DatasetMetadata) else "ServiceMetadata",
                "id": f"{metadata_record.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:datasetmetadata-detail', args=[metadata_record.pk])}"
                }
            }
        }
    except Exception as e:
        settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        return None
