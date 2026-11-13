from itertools import chain
from urllib import parse

from celery import chord, shared_task, states
from django.conf import settings
from django.db import IntegrityError
from notify.enums import LogTypeEnum
from notify.tasks import BackgroundProcessBased, finish_background_process
from registry.enums.metadata import CollectionStepOutcome
from registry.exceptions.metadata import (MetadataFetchTimeout,
                                          MetadataFetchUnreachable,
                                          UnknownMetadataKind)
from registry.exceptions.service import CapabilitiesPersistenceError
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models import CatalogueService, WebFeatureService, WebMapService
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.security import (WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from registry.settings import REGISTRATION_REQUEST_TIMEOUT_SECONDS
from requests import Request, Session
from rest_framework.reverse import reverse


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
        # the phase is a key, not a sentence: it is stored untranslated and
        # the browser translates it where it shows it (#1267). The url is no
        # part of it - the process description already names the url.
        self.update_background_process(
            phase='download_capabilities'
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
            timeout=REGISTRATION_REQUEST_TIMEOUT_SECONDS,
        )

        self.update_state(
            state=states.STARTED,
            meta={'done': 1, 'total': 3,
                  'phase': 'parse capabilities document...'}
        )
        self.update_background_process(
            phase='parse_capabilities'
        )

        self.update_state(
            state=states.STARTED,
            meta={'done': 2, 'total': 3, 'phase': 'persisting service...'}
        )
        self.update_background_process(
            phase='persist_service'
        )

        mapper = OGCServiceXmlMapper.from_xml(response.content)
        data = mapper.xml_to_django()
        if not data:
            # No mapping config found an element in the document: it serves a
            # protocol version no mapper handles, e.g. WFS 1.1.0 (#1210). Say
            # that instead of letting data[0] raise a bare IndexError.
            raise ValueError(
                "The capabilities document could not be mapped to a service. "
                "The served version "
                f"'{mapper.xml_root.attrib.get('version')}' is not supported "
                "from Mr. Map.")
        db_service = data[0]
        handler = PersistenceHandler(mapper)
        try:
            handler.persist_all()
        except IntegrityError as e:
            # a schema which refuses a row of the document is a defined
            # failure of the build, not a psycopg dump for the activity
            # popover and the TaskResult (#1201)
            raise CapabilitiesPersistenceError(e) from e
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
        # the error text is a diagnostic, not a phase: it stays free text
        # and the browser answers it untranslated (#1267)
        self.update_background_process(phase=str(e))
        settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        raise e

    if collect_metadata_records:
        remote_metadata_list = None
        if isinstance(db_service, WebMapService):
            remote_metadata_list = list(chain(
                WebMapServiceRemoteMetadata.objects.filter(
                    describes__pk=db_service.pk),
                LayerRemoteMetadata.objects.filter(
                    describes__service__pk=db_service.pk)
            ))

        elif isinstance(db_service, WebFeatureService):
            remote_metadata_list = list(chain(
                WebFeatureServiceRemoteMetadata.objects.filter(
                    describes__pk=db_service.pk),
                FeatureTypeRemoteMetadata.objects.filter(
                    describes__service__pk=db_service.pk
                )
            ))

        if remote_metadata_list:
            task_kwargs = {
                "http_request": http_request,
                "background_process_pk": background_process_pk
            }

            tasks = [
                fetch_remote_metadata_xml.s(
                    remote_metadata.pk,
                    remote_metadata.__class__.__name__,
                    **task_kwargs
                )
                for remote_metadata in remote_metadata_list]
            self.update_background_process(
                phase='collect_metadata_records',
                service=db_service,
                total_steps=tasks.__len__()
            )
            chord(tasks)(finish_background_process.s(
                **task_kwargs), max_retries=300, interval=1)
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
    # the handled failures below reach the shared report at the end without
    # a result of their own; such a reference reports None, like before
    result = None
    try:
        # the pattern is the class name of the row the fan-out handed in;
        # every kind it can produce must name its own model, and a name it
        # does not know is a failure to report, not a step to skip (#1257)
        match(class_name):
            case "WebMapServiceRemoteMetadata":
                remote_metadata = WebMapServiceRemoteMetadata.objects.get(
                    pk=remote_metadata_id)
            case "LayerRemoteMetadata":
                remote_metadata = LayerRemoteMetadata.objects.get(
                    pk=remote_metadata_id)
            case "WebFeatureServiceRemoteMetadata":
                remote_metadata = WebFeatureServiceRemoteMetadata.objects.get(
                    pk=remote_metadata_id)
            case "FeatureTypeRemoteMetadata":
                remote_metadata = FeatureTypeRemoteMetadata.objects.get(
                    pk=remote_metadata_id)
            case _:
                raise UnknownMetadataKind(class_name)

        remote_metadata.fetch_remote_content()
        self.update_state(state=states.STARTED, meta={'done': 1, 'total': 2})

        metadata_record = remote_metadata.create_metadata_instance()
        self.update_state(state=states.STARTED, meta={'done': 2, 'total': 2})

        if metadata_record is None:
            # the document was fetched and mapped, but its file identifier
            # resolved to no record: the answer must not name one - it used
            # to read "id": "None", which a client cannot tell apart from a
            # created record (#1261). Like any other final outcome the
            # reference logs here and falls through to the shared report.
            self.log_process(
                f"RemoteMetadata {remote_metadata.pk} was fetched and "
                f"parsed, but its document carries no identifiable record.",
                LogTypeEnum.WARNING)
            result = {
                "data": None,
                "outcome": CollectionStepOutcome.NO_IDENTIFIABLE_RECORD.value,
            }
        else:
            is_dataset = isinstance(metadata_record, DatasetMetadataRecord)
            result = {
                "data": {
                    "type": "DatasetMetadataRecord" if is_dataset else "ServiceMetadata",
                    "id": f"{metadata_record.pk}",
                    "links": {
                        "self": f"{reverse(viewname=f'registry:{"datasetmetadata" if is_dataset else "servicemetadata"}-detail', args=[metadata_record.pk])}"
                    }
                },
                "outcome": CollectionStepOutcome.RECORD_CREATED.value,
            }
    except (MetadataFetchTimeout, MetadataFetchUnreachable) as e:
        # Nothing was answered, so this document is not decided yet - and this
        # attempt is not the one which decides it. Raised back, that is what
        # makes celery's bounded retry apply: `autoretry_for` of
        # `BackgroundProcessBased` covers both classes, and every attempt it
        # schedules is mirrored onto the process the registration polls
        # (#1207). A swallowed warning never retries, which is how a document
        # unreachable for ten seconds used to be given up for the whole
        # registration (#1260).
        if self.request.retries < self.max_retries:
            raise
        # The last attempt the policy allows got no answer either. The
        # reference is then recorded as failed, with the reason and with the
        # fact that another fetch could get it (#1263 gives such a failure its
        # own work row) - and one silent document does not decide the whole
        # registration it hangs below.
        settings.ROOT_LOGGER.warning(
            f"RemoteMetadata id: {remote_metadata.pk} was not answered after "
            f"{self.max_retries} retries: {e}")
        self.log_process(
            f"Could not fetch the remote document of RemoteMetadata "
            f"{remote_metadata.pk}: {e} Given up after {self.max_retries} "
            f"retries; the reference is kept and can be fetched again.",
            LogTypeEnum.WARNING)
    except UnknownMetadataKind as e:
        # Raised from two places now: the match above for a class name this
        # task never got, and the mapping selection of the read document for a
        # hierarchyLevel Mr. Map does not map (#1260). The first can happen
        # before any row was resolved - so the id named is the one the
        # reference was handed with, which is true for both - and the kind
        # which was not mapped is in the error. Another attempt reads the
        # same kind, so this is recorded rather than retried (#1257, #1260).
        settings.ROOT_LOGGER.warning(
            f"Can't handle RemoteMetadata with id: {remote_metadata_id}, "
            f"cause the kind '{e}' is not supported.")
        self.log_process(
            f"Can't handle RemoteMetadata with id: {remote_metadata_id}, "
            f"cause the kind '{e}' is not supported.",
            LogTypeEnum.WARNING)

    except Exception as e:
        # the id of the reference, not of a resolved row: the resolution
        # itself may be what failed (#1257)
        settings.ROOT_LOGGER.exception(
            f"RemoteMetadata id: {remote_metadata_id}", e, stack_info=True, exc_info=True)
        self.log_process(
            f"RemoteMetadata id: {remote_metadata_id} could not be "
            f"collected: {e}",
            LogTypeEnum.WARNING)

    # One step per reference which reached an outcome, success included: the
    # report used to sit only behind the except branches, which the success
    # path left by returning, so a healthy collection never moved done_steps
    # (#1258). Every path through the body passes here exactly once; an
    # attempt which dies before this line (a retry, a failed lookup) reports
    # nothing, so a retried reference is not counted twice.
    self.update_background_process(
        step_done=True
    )
    return result
