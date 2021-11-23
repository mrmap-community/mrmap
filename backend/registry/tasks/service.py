from celery import shared_task
from django.db import transaction
from requests import Session, Request
from django.conf import settings
from registry.models import WebMapService, WebFeatureService, CatalougeService
from registry.xmlmapper.ogc.capabilities import get_parsed_service, WmsService as WmsXmlMapper, Wfs200Service as WfsXmlMapper, CswService as CswXmlMapper
from celery import states
from rest_framework.reverse import reverse


@shared_task(bind=True)
def build_ogc_service(self, data: dict, **kwargs):
    self.update_state(state=states.STARTED, meta={'done': 0, 'total': 3, 'phase': 'download capabilities document...'})

    auth = None
    if "auth" in data:
        auth_dict = data.get("auth")
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

    return {"api_enpoint": reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}
