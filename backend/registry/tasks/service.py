from celery import shared_task, chord
from django.db import transaction
from requests import Session, Request
from django.conf import settings
from registry.models.metadata import DatasetMetadata, RemoteMetadata
from registry.models import WebMapService, WebFeatureService, CatalougeService
from registry.xmlmapper.ogc.capabilities import get_parsed_service, WmsService as WmsXmlMapper, Wfs200Service as WfsXmlMapper, CswService as CswXmlMapper
from celery import states
from rest_framework.reverse import reverse


@shared_task(bind=True)
def build_ogc_service(self, data: dict, **kwargs):
    # TODO: set current user
    self.update_state(state=states.STARTED, meta={'done': 0, 'total': 3, 'phase': 'download capabilities document...'})

    auth = None
    if "auth" in data:
        auth_dict = data.get("auth")  # noqa
        # TODO: init ServiceAuthentication

    session = Session()
    session.proxies = settings.PROXIES
    request = Request(method="GET",
                      url=data.get("get_capabilities_url"),
                      auth=auth.get_auth_for_request() if auth else None)
    response = session.send(request.prepare())

    self.update_state(state=states.STARTED, meta={'done': 1, 'total': 3, 'phase': 'parse capabilities document...'})

    parsed_service = get_parsed_service(xml=response.content)

    self.update_state(state=states.STARTED, meta={'done': 2, 'total': 3, 'phase': 'persisting service...'})

    with transaction.atomic():
        # create all needed database objects and rollback if any error occours to avoid from database inconsistence
        if isinstance(parsed_service, WmsXmlMapper):
            db_service = WebMapService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
        elif isinstance(parsed_service, WfsXmlMapper):
            db_service = WebFeatureService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
        elif isinstance(parsed_service, CswXmlMapper):
            db_service = CatalougeService.capabilities.create_from_parsed_service(parsed_service=parsed_service)
        else:
            raise NotImplementedError("Unknown XML mapper detected. Only WMS, WFS and CSW services are allowed.")

        if auth:
            auth.service = db_service
            auth.save()

    self.update_state(state=states.SUCCESS, meta={'done': 3, 'total': 3})

    if data.get("collect_metadata_records", False):
        remote_metadata_list = RemoteMetadata.objects.filter(service__pk=db_service.pk)
        
        header = [fetch_remote_metadata_xml.s(remote_metadata.pk, **kwargs) for remote_metadata in remote_metadata_list]
        callback = parse_remote_metadata_xml_for_service.s(**kwargs)
        chord(header)(callback)

    return {
        "data": {
            "type": "OgcService",
            "id": f"{db_service.pk}",
            "links": {
                "self": f"{reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}"
            }
        }
    }


@shared_task(bind=True, queue="download_iso_metadata")
def fetch_remote_metadata_xml(self, remote_metadata_id, **kwargs):
    self.update_state(state=states.STARTED, meta={'done': 0, 'total': 1, 'phase': 'fetching remote document...'})
    remote_metadata = RemoteMetadata.objects.get(pk=remote_metadata_id)
    try:
        remote_metadata.fetch_remote_content()
        self.update_state(state=states.SUCCESS, meta={'done': 1, 'total': 1})
        return remote_metadata.id
    except Exception:
        # settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        # TODO: log exception in debug level
        return None


@shared_task(bind=True)
def parse_remote_metadata_xml_for_service(self, remote_metadata_ids: list, **kwargs):
    step = 0
    total = len(remote_metadata_ids)

    self.update_state(state=states.STARTED, meta={'done': 0, 'total': total, 'phase': 'persisting collected iso metadata...'})

    remote_metadata_list = RemoteMetadata.objects.filter(id__in=[x for x in remote_metadata_ids if x is not None])
    successfully_list = []
    dataset_list = []
    if remote_metadata_list:
        for remote_metadata in remote_metadata_list:
            try:
                db_metadata = remote_metadata.create_metadata_instance()
                successfully_list.append(db_metadata.pk)
                if isinstance(db_metadata, DatasetMetadata):
                    dataset_list.append(db_metadata.pk)
                self.update_state(state=states.STARTED, meta={'done': step, 'total': total, 'phase': 'persisting collected iso metadata...'})
                step += 1
            except Exception as e:
                settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)

    self.update_state(state=states.SUCCESS, meta={'done': step, 'total': total})

    # TODO: return json:api schema of list representation
    return successfully_list