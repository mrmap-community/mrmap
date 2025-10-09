from urllib import parse

from celery import chord, shared_task, states
from django.conf import settings
from notify.tasks import BackgroundProcessBased, finish_background_process
from ows_lib.xml_mapper.utils import get_parsed_service
from registry.exceptions.metadata import UnknownMetadataKind
from registry.mappers.persistence import PersistenceHandler
from registry.mappers.xml_mapper import OGCServiceXmlMapper
from registry.models import CatalogueService, WebFeatureService, WebMapService
from registry.models.metadata import (DatasetMetadataRecord,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.security import (WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from requests import Request, Session
from rest_framework.reverse import reverse
from urllib3.exceptions import MaxRetryError


@shared_task(
    bind=True,
    queue="default",
    base=BackgroundProcessBased
)
def build_ogc_service(
        self,
        get_capabilities_url: str,
        collect_metadata_records: bool,
        service_auth_pk: None,
        http_request,
        background_process_pk,
        **kwargs):
    try:
        self.update_state(state=states.STARTED, meta={
            'done': 0, 'total': 3, 'phase': 'download capabilities document...'})
        self.update_background_process(
            phase=f"download capabilities document from {get_capabilities_url}"
        )

        auth = None
        if service_auth_pk:
            match parse.parse_qs(parse.urlsplit(get_capabilities_url).query)['SERVICE'][0].lower():
                case 'wms':
                    auth = WebMapServiceAuthentication.objects.get(
                        id=service_auth_pk)
                case 'wfs':
                    auth = WebFeatureServiceAuthentication.objects.get(
                        id=service_auth_pk)
                case _:
                    auth = None

        session = Session()
        session.proxies = settings.PROXIES
        request = Request(method="GET",
                          url=get_capabilities_url,
                          auth=auth.get_auth_for_request() if auth else None)
        response = session.send(
            request=request.prepare(),
            timeout=15,
        )

        self.update_state(
            state=states.STARTED,
            meta={'done': 1, 'total': 3,
                  'phase': 'parse capabilities document...'}
        )
        self.update_background_process(
            phase='parse capabilities document...'
        )

        self.update_state(
            state=states.STARTED,
            meta={'done': 2, 'total': 3, 'phase': 'persisting service...'}
        )
        self.update_background_process(
            phase='persisting service...'
        )

        mapper = OGCServiceXmlMapper.from_xml(response.content)
        data = mapper.xml_to_django()
        db_service = data[0]
        handler = PersistenceHandler(mapper)
        handler.persist_all()
        db_service.refresh_from_db()

        # create all needed database objects and rollback if any error occours to avoid from database inconsistence
        if isinstance(db_service, WebMapService):
            self_url = reverse(
                viewname='registry:wms-detail', args=[db_service.pk])
        elif isinstance(db_service, WebFeatureService):
            self_url = reverse(
                viewname='registry:wfs-detail', args=[db_service.pk])
        elif isinstance(db_service, CatalogueService):
            self_url = reverse(
                viewname='registry:csw-detail', args=[db_service.pk])

        if auth:
            auth.service = db_service
            auth.save()

        self.update_state(
            state=states.SUCCESS,
            meta={'done': 3, 'total': 3}
        )

        # TODO: use correct Serializer and render the json:api as result
        return_dict = {
            "data": {
                "type": db_service.__class__.__name__,
                "id": str(db_service.pk),
                "links": {
                    "self": self_url
                }
            }
        }
    except (ConnectionError, TimeoutError) as e:
        raise e
    except Exception as e:
        self.update_state(state=states.FAILURE)
        self.update_background_process(phase=str(e))
        settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        raise e

    if collect_metadata_records:
        remote_metadata_list = None
        if isinstance(db_service, WebMapService):
            remote_metadata_list = WebMapServiceRemoteMetadata.objects.filter(
                service__pk=db_service.pk)
        elif isinstance(db_service, WebFeatureService):
            remote_metadata_list = WebFeatureServiceRemoteMetadata.objects.filter(
                service__pk=db_service.pk)
        if remote_metadata_list:
            task_kwargs = {
                "http_request": http_request,
                "background_process_pk": background_process_pk
            }

            tasks = [
                fetch_remote_metadata_xml.s(
                    remote_metadata.pk,
                    db_service.__class__.__name__,
                    **task_kwargs
                )
                for remote_metadata in remote_metadata_list]
            chord(tasks)(finish_background_process.s(
                **task_kwargs), max_retries=300, interval=1)

            self.update_background_process(
                phase='collecting metadata records...',
                service=db_service,
                total_steps=tasks.__len__()
            )
        else:
            self.update_background_process(
                completed=True,
                service=db_service,
            )

    else:
        self.update_background_process(
            completed=True,
            service=db_service,
        )

    return return_dict


@shared_task(bind=True,
             queue="download",
             base=BackgroundProcessBased,
             )
def fetch_remote_metadata_xml(
    self,
    remote_metadata_id,
    class_name,
    **kwargs
):
    self.update_state(state=states.STARTED, meta={
                      'done': 0, 'total': 1, 'phase': 'fetching remote document...'})

    remote_metadata = None
    if class_name == 'WebMapService':
        remote_metadata = WebMapServiceRemoteMetadata.objects.get(
            pk=remote_metadata_id)
    elif class_name == 'WebFeatureService':
        remote_metadata = WebFeatureServiceRemoteMetadata.objects.get(
            pk=remote_metadata_id)
    if not remote_metadata:
        return None
    try:
        remote_metadata.fetch_remote_content()
        self.update_state(state=states.STARTED, meta={'done': 1, 'total': 2})

        metadata_record = remote_metadata.create_metadata_instance()
        self.update_state(state=states.STARTED, meta={'done': 2, 'total': 2})
        return {
            "data": {
                "type": "DatasetMetadataRecord" if isinstance(metadata_record, DatasetMetadataRecord) else "ServiceMetadata",
                "id": f"{metadata_record.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:datasetmetadata-detail', args=[metadata_record.pk])}"
                }
            }
        }
    except MaxRetryError:
        # fetch_remote_content went wrong
        pass
    except UnknownMetadataKind:
        try:
            kind = remote_metadata.parsed_metadata._hierarchy_level
        except Exception:
            kind = 'unknown'
        settings.ROOT_LOGGER.warning(
            f"Can't handle RemoteMetadata with id: {remote_metadata.pk}, cause the kind '{kind}' is not supported.")

    except Exception as e:
        settings.ROOT_LOGGER.exception(
            f"RemoteMetadata id: {remote_metadata.pk}", e, stack_info=True, exc_info=True)

    self.update_background_process(
        step_done=True
    )
