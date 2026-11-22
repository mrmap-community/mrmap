"""Celery tasks of the OGC service registration (#1263).

The collection of a registration's metadata references runs on a work queue
of its own: the root task seals a plan of one ``TemporaryMdMetadataFile``
work row per advertised reference, and one delivery per row fetches, stores,
imports and decides exactly that row. The row is the permit - a delivery
only works under the claim token it just took, a successful import deletes
the row, and the absence of the row is the proof which makes a redelivery a
no-op instead of a second import.

Documents which several references advertise identically are pulled once per
collection run, not once per reference: a shared acquisition row carries the
fetch permit and the stored bytes for one request identity, the delivery
which wins its claim fetches, and every other reference of that identity
imports a copy of the stored document under its own claim and keeps its own
outcome - a failing import still costs exactly one reference (#1410).
"""
from datetime import timedelta
from itertools import chain
from urllib import parse

from accounts.models.groups import Organization
from celery import chord, shared_task, states
from celery.signals import worker_ready
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import now
from extras.ssrf import GuardedSession
from extras.tasks import SingletonTask
from MrMap import celery_queues
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.tasks import BackgroundProcessBased
from registry.enums.metadata import (CollectionStepOutcome,
                                     DocumentAcquisitionStateEnum,
                                     ReferenceErrorKind,
                                     ReferenceWorkStateEnum)
from registry.exceptions.metadata import (MetadataFetchTimeout,
                                          MetadataFetchUnreachable,
                                          UnknownMetadataKind)
from registry.exceptions.service import (CapabilitiesPersistenceError,
                                         NoContent)
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models import (FeatureType, Layer,
                             WebFeatureService, WebMapService)
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      LayerRemoteMetadata,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata,
                                      fetch_metadata_document)
from registry.models.security import (WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from registry.settings import (REGISTRATION_ORPHAN_FILE_GRACE_SECONDS,
                               REGISTRATION_RECOVERY_BATCH_SIZE,
                               REGISTRATION_REFERENCE_LEASE_SECONDS,
                               REGISTRATION_REQUEST_TIMEOUT_SECONDS)
from requests import Request
from requests.exceptions import ConnectionError, Timeout
from rest_framework.reverse import reverse

#: The recovery of #1263 re-drives a PENDING row only after it has outlived
#: this age. A healthy fan-out drains the ``download`` queue long before an
#: hour has passed; an hour is what separates a queued row from one whose
#: driving message was lost, without letting the hourly pass stack a second
#: copy onto a backlog which is merely slow.
REFERENCE_PENDING_RECOVERY_AGE = timedelta(hours=1)

#: How long the chord body may wait for references which are still being
#: worked on by deliveries of a redriven or contested row - five seconds per
#: attempt, so 25 minutes; the hourly recovery is the backstop behind it.
FINISH_WAIT_MAX_RETRIES = 300
FINISH_WAIT_COUNTDOWN_SECONDS = 5


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
        owner_pk=None,
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

        auth = _capabilities_auth(service_auth_pk, get_capabilities_url)

        # the url is user input from registration or from an upstream document: its
        # connections pass the host policy of `extras.ssrf` (#1474, SEC-16)
        session = GuardedSession()
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
        # The ownership decided at POST time (#733) is written with the row
        # the mapper just built: the default is keyed by the name of the
        # concrete service class the document mapped to, so it lands on the
        # service and on nothing else. A message which carries no owner -
        # one queued before this field existed - stores an ownerless service,
        # the same shape the migration documents for the legacy rows.
        defaults = {}
        if owner_pk:
            defaults[db_service.__class__.__name__] = {
                "owner": Organization.objects.get(pk=owner_pk)}
        handler = PersistenceHandler(mapper, defaults=defaults)
        try:
            handler.persist_all()
        except IntegrityError as e:
            # a schema which refuses a row of the document is a defined
            # failure of the build, not a psycopg dump for the activity
            # popover and the TaskResult (#1201)
            raise CapabilitiesPersistenceError(e) from e
        db_service.refresh_from_db()

        # create all needed database objects and rollback if any error occours to avoid from database inconsistence
        self_url = _service_self_url(db_service)

        if auth:
            auth.service = db_service
            auth.save()

        self.update_state(
            state=states.SUCCESS,
            meta={'done': 3, 'total': 3}
        )

        # FUTURE: use correct Serializer and render the json:api as result
        return_dict = {
            "data": {
                "type": db_service.__class__.__name__,
                "id": str(db_service.pk),
                "links": {
                    "self": self_url
                }
            }
        }
    except (ConnectionError, Timeout) as e:
        # the requests exceptions, not the builtins of the same name:
        # requests raises requests.exceptions.*, which are not subclasses
        # of the builtins, and BackgroundProcessBased.autoretry_for covers
        # exactly these two (#1457). A host which refused or stayed silent
        # is a retry, not a failure of the build: running it through the
        # generic branch below reported every attempt as one.
        raise e
    except Exception as e:
        self.update_state(state=states.FAILURE)
        # the error text is a diagnostic, not a phase: it stays free text
        # and the browser answers it untranslated (#1267)
        self.update_background_process(phase=str(e))
        settings.ROOT_LOGGER.exception(e, stack_info=True, exc_info=True)
        raise e

    if collect_metadata_records:
        _collect_advertised_references(
            self, db_service, background_process_pk, http_request)
    else:
        self.update_background_process(
            completed=True,
            service=db_service,
        )

    return return_dict


def _capabilities_auth(service_auth_pk, get_capabilities_url):
    """The stored authentication of the service this url belongs to."""
    if not service_auth_pk:
        return None
    match parse.parse_qs(parse.urlsplit(get_capabilities_url).query)['SERVICE'][0].lower():
        case 'wms':
            return WebMapServiceAuthentication.objects.get(
                id=service_auth_pk)
        case 'wfs':
            return WebFeatureServiceAuthentication.objects.get(
                id=service_auth_pk)
        case _:
            return None


def _service_self_url(db_service):
    """The detail url of the service this task just built."""
    if isinstance(db_service, WebMapService):
        return reverse(
            viewname='registry:wms-detail', args=[db_service.pk])
    if isinstance(db_service, WebFeatureService):
        return reverse(
            viewname='registry:wfs-detail', args=[db_service.pk])
    return reverse(
        viewname='registry:csw-detail', args=[db_service.pk])


def _collect_advertised_references(self, db_service, background_process_pk,
                                   http_request):
    """Fan out the metadata reference collection of the built service."""
    if not isinstance(db_service, (WebMapService, WebFeatureService)):
        # a registration which collects no references (a CSW) stays the
        # plain run it was: no plan, no summary, completion as before.
        self.update_background_process(
            completed=True,
            service=db_service,
        )
        return

    remote_metadata_list = advertised_references(db_service)

    # the plan of the collection is sealed with its rows, its number
    # of steps and its reference total in one transaction, before the
    # first message can be answered: a client which reads the process
    # while the fan-out runs already knows how many references were
    # expected (#1259), and the row identity of #1263 is what makes a
    # second delivery of this root find the plan sealed instead of
    # writing the same references a second time. A service whose
    # document advertised no metadata reference at all seals a plan
    # of ZERO: a planned empty collection answers 0 where an
    # uncollected run answers NULL (#1263).
    sealed = plan_registration_references(
        self, background_process_pk, remote_metadata_list, db_service)
    if sealed is None:
        settings.ROOT_LOGGER.warning(
            f"BackgroundProcess {background_process_pk} holds no "
            f"open plan to publish for: this delivery found its "
            f"reference plan already sealed, or the process decided "
            f"or gone. It writes no second fan-out.",
            stack_info=True)
        return
    if not sealed:
        # planned empty: the seal said 0 and there is nothing to
        # wait for - the run completes with its zero-reference
        # summary right here (#1263).
        self.update_background_process(
            completed=True,
            service=db_service,
        )
        return

    task_kwargs = {
        "http_request": http_request,
        "background_process_pk": background_process_pk
    }
    tasks = [
        collect_reference.s(
            temporary_md_metadata_file_id=row_id,
            **task_kwargs
        )
        for row_id in sealed]
    # the chord body does not just close the process: it waits
    # while references are still being worked on by deliveries
    # whose message it never saw finish - the recovery's
    # redeliveries and the losers of a contested claim - so a
    # run never completes below an unfinished reference (#1263).
    chord(tasks)(finish_metadata_collection.s(
        **task_kwargs), max_retries=300, interval=1)
    # A publish the broker refuses leaves the sealed plan behind
    # with nothing queued: the worker-start recovery and the
    # hourly sweep read exactly that shape out of the database
    # and re-drive it (#1263, like the harvest recovery of #891).


def advertised_references(service):
    """The metadata references one service advertises, as ``RemoteMetadata`` rows.

    The capabilities mapping leaves every advertised ISO reference behind as a
    ``RemoteMetadata`` row - the configs name the subclass per element kind
    (``mappers/configs/wms130.py``, ``wfs200.py``) - and these rows are what a
    collection has to fetch. The reference of the service describes the service
    row itself, the reference of an element describes the element, so the two
    reads are one answer. A service which advertises no metadata at all - a CSW
    is the kind which never has any - answers the empty list.

    A collection which runs after an update (#1274) reads the same answer for
    the service as it is published by that update: the rows the candidate
    carried are gone with it through the ``describes`` cascade, so what is left
    to collect are exactly the references which describe what the update
    published.

    Args:
        service: the built or published service to read the references of

    Returns:
        list: the ``RemoteMetadata`` rows of the service and its elements
    """
    if isinstance(service, WebMapService):
        return list(chain(
            WebMapServiceRemoteMetadata.objects.filter(
                describes__pk=service.pk),
            LayerRemoteMetadata.objects.filter(
                describes__service__pk=service.pk)
        ))
    if isinstance(service, WebFeatureService):
        return list(chain(
            WebFeatureServiceRemoteMetadata.objects.filter(
                describes__pk=service.pk),
            FeatureTypeRemoteMetadata.objects.filter(
                describes__service__pk=service.pk)
        ))
    return []


# The concrete work-row field which names the described element of a
# planned reference: the same four targets, in the same order, as the
# isinstance chain of #1263's planning.
_DESCRIBED_FOREIGN_KEYS = (
    (WebMapService, "described_wms"),
    (WebFeatureService, "described_wfs"),
    (Layer, "described_layer"),
    (FeatureType, "described_featuretype"),
)


def _described_foreign_key_field(described):
    """The work-row field which names this described element, or None
    when the planning cannot name it with one of the four concrete
    foreign keys (#1263)."""
    for model, field in _DESCRIBED_FOREIGN_KEYS:
        if isinstance(described, model):
            return field
    return None


def _plan_shared_acquisitions(rows, background_process_pk):
    """One shared document acquisition per distinct advertised url of a
    sealed plan (#1410).

    References which advertise the same document point at one acquisition
    row, and that row is what pays the one HTTP request the references
    import their copies from. The rows are built unsaved and returned as
    the plan's second bulk write; every reference row already points at
    its acquisition in memory.
    """
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition)

    acquisitions = {}
    for row in rows:
        key = RegistrationDocumentAcquisition.build_acquisition_key(
            row.requested_url)
        acquisition = acquisitions.get(key)
        if acquisition is None:
            acquisition = RegistrationDocumentAcquisition(
                background_process_id=background_process_pk,
                acquisition_key=key,
                requested_url=row.requested_url,
                request_id=timezone.now(),
            )
            acquisitions[key] = acquisition
        row.acquisition = acquisition
    return acquisitions


def plan_registration_references(
        task, background_process_pk, remote_metadata_list, db_service):
    """Seal the per-reference work list of one registration, once.

    One row per logical reference - the described resource and the exact
    advertised url are its identity, deduplicated here so the same url
    advertised for the same resource twice still plans one row - written in
    one transaction under the lock of the background process, together with
    the process' plan numbers and the ``references_plan_sealed`` marker.
    A redelivery of the root which finds the marker set writes nothing: the
    plan of a registration is written by the first delivery that seals it
    and by no other (#1263). The plan belongs to the collecting process and
    not to the kind of run which reports through it: the update of a service
    seals its own plan through this very function (#1274).

    Args:
        task: the reporting task (its ``update_background_process`` names
            the plan on the process inside the sealing transaction)
        background_process_pk: the collecting process the plan belongs to
        remote_metadata_list: the advertised references the capabilities
            document left behind as ``RemoteMetadata`` rows
        db_service: the built service, for the process' related resource

    Returns:
        list|None: the primary keys of the planned rows in plan order, or
            None when the plan was already sealed (or the process is gone
            or decided, for which there is nothing left to plan either).
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition)

    rows = []
    seen = set()
    for remote_metadata in remote_metadata_list:
        described = remote_metadata.describes
        if described is None:
            continue
        url = remote_metadata.link
        key = TemporaryMdMetadataFile.build_reference_key(described, url)
        if key in seen:
            # the same reference advertised twice (capabilities do it):
            # one logical reference is one work row (#1263)
            continue
        seen.add(key)
        field = _described_foreign_key_field(described)
        if field is None:
            # a described element this planning cannot name with one of the
            # four concrete foreign keys is not plannable - it would violate
            # the row's completeness constraint; naming it beats dropping it
            # silently (#1263).
            settings.ROOT_LOGGER.warning(
                f"RemoteMetadata {remote_metadata.pk} describes a "
                f"{described.__class__.__name__} the reference planning "
                f"does not know; the reference is not collected.",
                stack_info=True)
            continue
        rows.append(TemporaryMdMetadataFile(
            background_process_id=background_process_pk,
            reference_key=key,
            requested_url=url,
            described_display=(getattr(described, "title", "") or "")[:512],
            # when the request for this document was planned: the age the
            # recovery measures a stuck PENDING row by
            request_id=timezone.now(),
            **{field: described},
        ))

    acquisitions = _plan_shared_acquisitions(rows, background_process_pk)

    with transaction.atomic():
        process = BackgroundProcess.objects.select_for_update().filter(
            pk=background_process_pk).first()
        if process is None or process.done_at is not None:
            # decided or deleted while this delivery worked: nothing to plan
            # for, and the rows' owner is gone with them through the cascade
            return None
        if process.references_plan_sealed:
            return None
        RegistrationDocumentAcquisition.objects.bulk_create(
            acquisitions.values())
        TemporaryMdMetadataFile.objects.bulk_create(rows)
        # the plan is named on the process inside the sealing transaction:
        # a reader of the process either sees no plan or the whole plan,
        # and the counters start at the plan's zeros before any worker can
        # report an outcome (#1259, guarded by the sealed marker of #1263)
        task.update_background_process(
            phase='collect_metadata_records',
            service=db_service,
            total_steps=len(rows),
            references_total=len(rows)
        )
        BackgroundProcess.objects.filter(
            pk=background_process_pk).update(references_plan_sealed=True)
    return [row.pk for row in rows]


@shared_task(bind=True,
             queue="download",
             base=BackgroundProcessBased,
             )
def collect_reference(
    self,
    background_process_pk,
    temporary_md_metadata_file_id,
    allow_failed=False,
    **kwargs
):
    """Fetch, import and decide one planned registration reference (#1263).

    The work row addressed by ``(background_process_pk,
    temporary_md_metadata_file_id)`` is the permit of this delivery: the
    task claims the row under a fresh single-use token, does its work, and
    reports the outcome only while that token still owns the row. What the
    row's state makes impossible for a redelivery is answered by the claim
    itself:

    * the row is gone - a successful import deleted it, its absence is the
      proof of success - or the process it belongs to is gone: no-op;
    * another delivery holds the row on an unexpired lease, or the row is
      already decided FAILED, or the process is decided: this delivery
      waits out a bounded retry and then withdraws without touching the
      counters - the holder reports exactly once;
    * everything this delivery decides (success, no content, unparsable
      kind, no identifiable record, failed import) happens in a
      transaction which re-locks process and row and checks the token: an
      outcome a recovery already wrote over is discarded, never applied a
      second time.

    A transport failure is not a decision: the lease is released and the
    exception raised back, which is what engages the base class's bounded
    retry; only the last permitted attempt decides the row as failed, with
    the machine-readable ``error_kind`` that names what a retry - of the
    automatic kind or the authorized one of #1265 - may later read.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    row = TemporaryMdMetadataFile.objects.filter(
        pk=temporary_md_metadata_file_id).first()
    if row is None:
        # the row was consumed by a successful delivery, or its process was
        # deleted and the cascade took it: a redelivery is a no-op, not a
        # reference to recreate (#1263)
        settings.ROOT_LOGGER.info(
            f"TemporaryMdMetadataFile {temporary_md_metadata_file_id} is "
            f"not there to collect: its reference was decided before this "
            f"delivery reached it.")
        return None

    claimed = row.claim_for_processing(
        background_process_pk, REGISTRATION_REFERENCE_LEASE_SECONDS,
        allow_failed=allow_failed)
    if claimed is None:
        # a live lease, a decided failure, a vanished or decided process:
        # in every shape some other answer already owns this row. Waiting
        # it out beats failing the chord member: the holder reports and the
        # chord body reads the decided row.
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=FINISH_WAIT_COUNTDOWN_SECONDS)
        return None
    token, retried = claimed

    if row.acquisition_id is not None:
        # a row planned with its shared document acquisition (#1410): the
        # fetch happens once for the acquisition's request identity and
        # this reference imports a copy - see the helper. A row without
        # one (planned before #1410, or a retried reference whose
        # acquisition drained with its last sibling) fetches its own
        # document exactly the way #1263 always did.
        return _collect_under_shared_acquisition(
            self, row, background_process_pk, temporary_md_metadata_file_id,
            token, retried)

    return _collect_reference_own_fetch(
        self, row, background_process_pk, temporary_md_metadata_file_id,
        token, retried)


def _collect_reference_own_fetch(
        task, row, background_process_pk, temporary_md_metadata_file_id,
        token, retried):
    """Fetch, store and decide one reference's OWN document (#1263).

    The per-reference path every row walks while no shared acquisition of
    #1410 backs it: this delivery pays the HTTP request, stores the bytes
    under its own claim token and imports them behind the same permit.
    """
    try:
        content = fetch_metadata_document(
            row.requested_url,
            reference=(f"registration reference of "
                       f"{row.described_display or row.requested_url}"))
    except (MetadataFetchTimeout, MetadataFetchUnreachable) as e:
        return _decide_unanswered_reference(
            task, row, e, background_process_pk,
            temporary_md_metadata_file_id, token, retried)
    except NoContent as e:
        # an answer which is no document is decided by reading it again:
        # recorded, not retried - the row keeps it for inspection (#1263)
        _decide_reference_failure(
            background_process_pk, temporary_md_metadata_file_id,
            token, ReferenceErrorKind.NO_CONTENT, e, retried=retried)
        settings.ROOT_LOGGER.warning(
            f"Registration reference {temporary_md_metadata_file_id} of "
            f"process {background_process_pk} was answered with no "
            f"content: {e}", stack_info=True)
        task.log_process(
            f"The reference of '{row.described_display or row.requested_url}'"
            f" was answered without a document: {e}", LogTypeEnum.WARNING)
        return {"data": None, "outcome": None,
                "error_kind": ReferenceErrorKind.NO_CONTENT.value}

    # the document is stored under the permit itself: the name carries the
    # claim token, so every attempt writes its own bytes and a late attempt
    # can never overwrite the document a decided row points at. A lost
    # attempt's file is what the bounded registration orphan sweep reads out
    # of this prefix and takes back (#1263).
    try:
        row.md_metadata_file.save(
            f"reference-{temporary_md_metadata_file_id}-{token}.xml",
            ContentFile(content.encode("utf-8")),
            save=False)
    except Exception as e:
        # the storage itself refused: not a decision about the document -
        # the lease goes back and the base retry or the recovery decides
        row.release_claim(token)
        settings.ROOT_LOGGER.exception(
            f"Could not store the document of registration reference "
            f"{temporary_md_metadata_file_id}: {e}",
            stack_info=True, exc_info=True)
        task.log_process(
            f"The document of reference "
            f"'{row.described_display or row.requested_url}' could not be "
            f"stored: {e}", LogTypeEnum.WARNING)
        raise
    storage_name = row.md_metadata_file.name

    # one decision about one reference: the record, its coupling, the row's
    # end state and the process' counters are written in the same
    # transaction, behind the row lock which re-checks the permit.
    return _decide_stored_reference(
        task, row, background_process_pk, temporary_md_metadata_file_id,
        token, retried, storage_name)


def _answer_refused_shared_fetch(
        task, doc, row, background_process_pk, error,
        temporary_md_metadata_file_id, token, retried, doc_token):
    """Answer a shared fetch the network refused (#1410).

    A missing answer decides nothing yet: the fetch permit goes back and
    the attempt budget of the acquisition keeps trying - the lease makes a
    doubled fetch by a concurrent sibling impossible, so waiting siblings
    wait instead of racing another request. The budget is the row's own
    claim count: ten fetches for the whole identity, the legacy transport
    budget spent once per document. #1263's other half keeps its force per
    delivery: the last attempt the retry policy permits to THIS reference
    decides it even while the identity could fetch on - and then it decides
    itself only, because every sibling's own policy is still running and
    its delivery still answers for it.
    """
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition)

    doc.release_claim(doc_token)
    attempts = RegistrationDocumentAcquisition.objects.filter(
        pk=doc.pk).values_list("attempt_count", flat=True).first() or 0
    identity_spent = attempts >= task.max_retries
    if not identity_spent and task.request.retries < task.max_retries:
        # nothing is decided: the reference permit goes back too and the
        # retried delivery claims both rows again (#1260, #1263)
        row.release_claim(token)
        raise task.retry(
            countdown=FINISH_WAIT_COUNTDOWN_SECONDS,
            max_retries=FINISH_WAIT_MAX_RETRIES)
    kind = (ReferenceErrorKind.FETCH_TIMEOUT
            if isinstance(error, MetadataFetchTimeout)
            else ReferenceErrorKind.FETCH_UNREACHABLE)
    return _decide_shared_fetch_failure(
        task, doc, background_process_pk, kind, error,
        temporary_md_metadata_file_id, token, retried,
        mirror=identity_spent)


def _collect_under_shared_acquisition(
        task, row, background_process_pk, temporary_md_metadata_file_id,
        token, retried):
    """Work a reference whose document is acquired once for its identity.

    The #1410 shape of ``collect_reference``: the reference row stays this
    delivery's permit and its outcome stays its own; only the fetch is
    shared. Three shapes answer from the acquisition row:

    * STORED - its bytes are copied into this reference's own file and
      imported behind the reference's own claim token, exactly the way the
      own-fetch path imports what it fetched;
    * claimable (PENDING, or a LEASE whose holder died) - this delivery
      fetches under the acquisition's own claim token, stores the shared
      copy and then walks the same import;
    * leased by another delivery - the reference claim goes back and the
      task waits in bounded rounds for the fetcher. The fetch lease is
      shorter than the wait budget, so a dead fetcher is always taken over
      by one of the waiting references.

    A fetch which fails keeps #1263's two budgets apart: while the
    acquisition's attempt budget and this delivery's own retry policy both
    allow another round, nothing is decided and the permits go back. The
    last attempt the policy permits to one reference decides that one
    reference; only when the identity itself is spent - its fetch budget
    gone or the answer was no document at all - does the decision mirror
    onto every reference still waiting, each keeping its own row, counter
    and retry identity (#1263 semantics, #1410 batching).
    """
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition)

    doc_pk = row.acquisition_id
    doc = RegistrationDocumentAcquisition.objects.filter(
        pk=doc_pk).first()
    if doc is None:
        # the acquisition drained while this message waited (its last
        # sibling decided in between): this reference re-fetches its own
        # document, the legacy shape of #1263
        return _collect_reference_own_fetch(
            task, row, background_process_pk,
            temporary_md_metadata_file_id, token, retried)

    if doc.state == DocumentAcquisitionStateEnum.STORED.value:
        return _import_shared_document(
            task, row, doc, background_process_pk,
            temporary_md_metadata_file_id, token, retried)

    claimed_doc = doc.claim_for_processing(
        background_process_pk, REGISTRATION_REFERENCE_LEASE_SECONDS)
    if claimed_doc is None:
        # refused without a decision of ours: re-read and dispatch once -
        # STORED means the race landed, PENDING means take another turn,
        # a live LEASE means wait for the fetcher
        doc = RegistrationDocumentAcquisition.objects.filter(
            pk=doc_pk).first()
        if doc is None:
            return _collect_reference_own_fetch(
                task, row, background_process_pk,
                temporary_md_metadata_file_id, token, retried)
        if doc.state != DocumentAcquisitionStateEnum.STORED.value:
            return _wait_for_shared_document(task, row, token)
        return _import_shared_document(
            task, row, doc, background_process_pk,
            temporary_md_metadata_file_id, token, retried)

    token_d, _doc_retried = claimed_doc
    try:
        content = fetch_metadata_document(
            doc.requested_url,
            reference=(f"shared registration document of "
                       f"{row.described_display or doc.requested_url}"))
    except (MetadataFetchTimeout, MetadataFetchUnreachable) as e:
        # the two budgets - the acquisition's fetch count and this
        # delivery's retry policy - answer apart, see the helper
        return _answer_refused_shared_fetch(
            task, doc, row, background_process_pk, e,
            temporary_md_metadata_file_id, token, retried, token_d)
    except NoContent as e:
        # an answer which is no document is decided by reading it again:
        # recorded at once for every waiting reference, not retried (#1263
        # posture, #1410 batching)
        doc.release_claim(token_d)
        return _decide_shared_fetch_failure(
            task, doc, background_process_pk,
            ReferenceErrorKind.NO_CONTENT, e,
            temporary_md_metadata_file_id, token, retried, mirror=True)

    # the document is stored under the fetch permit: the name carries the
    # fetch claim token, so a lost attempt's bytes are an orphan the
    # registration sweep reads out of the prefix, never a rewrite of what
    # a stored acquisition points at.
    try:
        doc.md_metadata_file.save(
            f"document-{doc_pk}-{token_d}.xml",
            ContentFile(content.encode("utf-8")),
            save=False)
    except Exception as e:
        # the storage itself refused: not a decision about the document -
        # both permits go back and the base retry or the recovery decides,
        # exactly like the own-fetch path treats its storage refusals
        doc.release_claim(token_d)
        row.release_claim(token)
        settings.ROOT_LOGGER.exception(
            f"Could not store the shared registration document "
            f"{doc_pk} of process {background_process_pk}: {e}",
            stack_info=True, exc_info=True)
        task.log_process(
            f"The document of reference "
            f"'{row.described_display or row.requested_url}' could not be "
            f"stored: {e}", LogTypeEnum.WARNING)
        raise
    if not doc.store_document(token_d, doc.md_metadata_file.name):
        # the fetch lease died while the document was in flight - a
        # takeover already owns this acquisition. These bytes are an
        # orphan by definition; this reference is one of the waiting ones
        # now.
        _delete_storage_file_after_commit(doc.md_metadata_file.name)
        return _wait_for_shared_document(task, row, token)

    return _import_shared_document(
        task, row, doc, background_process_pk,
        temporary_md_metadata_file_id, token, retried, content=content)


def _import_shared_document(
        task, row, doc, background_process_pk, temporary_md_metadata_file_id,
        token, retried, content=None):
    """Copy the acquisition's document into this reference's own file and
    decide the reference behind its own claim (#1410).

    The copy is what keeps the #1263 semantics whole for a shared fetch:
    every reference row owns its bytes, a failed import keeps a file for
    inspection, a successful import deletes the row and its copy, and the
    sweep's live-name set stays a per-row property. What the copy does not
    duplicate is the request - that is the whole point of #1410.
    """
    if content is None:
        try:
            with doc.md_metadata_file.open("rb") as document:
                content = document.read()
        except Exception as e:
            # the shared bytes could not be read: not a decision about the
            # document - the reference permit goes back and the base retry
            # or the recovery tries again
            row.release_claim(token)
            settings.ROOT_LOGGER.exception(
                f"Could not read the shared registration document "
                f"{doc.pk} for reference "
                f"{temporary_md_metadata_file_id}: {e}",
                stack_info=True, exc_info=True)
            raise
    try:
        row.md_metadata_file.save(
            f"reference-{temporary_md_metadata_file_id}-{token}.xml",
            ContentFile(content),
            save=False)
    except Exception as e:
        row.release_claim(token)
        settings.ROOT_LOGGER.exception(
            f"Could not store the document copy of registration reference "
            f"{temporary_md_metadata_file_id}: {e}",
            stack_info=True, exc_info=True)
        task.log_process(
            f"The document of reference "
            f"'{row.described_display or row.requested_url}' could not be "
            f"stored: {e}", LogTypeEnum.WARNING)
        raise
    storage_name = row.md_metadata_file.name

    result = _decide_stored_reference(
        task, row, background_process_pk, temporary_md_metadata_file_id,
        token, retried, storage_name)
    _drain_acquisition_if_last(doc.pk)
    return result


def _wait_for_shared_document(task, row, token):
    """Let this reference's turn wait for another delivery's fetch.

    The reference claim goes back first - a reference which is only waiting
    holds no permit - and the task retries in bounded rounds. The fetch
    lease is shorter than the total wait, so a fetcher which died is taken
    over by one of the waiting deliveries; a waiter which runs out of rounds
    leaves its row PENDING for the recovery, the same shape a lost claim
    already leaves (#1263).
    """
    row.release_claim(token)
    if task.request.retries < FINISH_WAIT_MAX_RETRIES:
        raise task.retry(
            countdown=FINISH_WAIT_COUNTDOWN_SECONDS,
            max_retries=FINISH_WAIT_MAX_RETRIES)
    settings.ROOT_LOGGER.warning(
        f"Registration reference {row.pk} gave up waiting for the shared "
        f"document of acquisition {row.acquisition_id}; the recovery "
        f"re-drives it.", stack_info=True)
    return None


def _decide_shared_fetch_failure(
        task, doc, background_process_pk, kind, error,
        temporary_md_metadata_file_id, token, retried, mirror=True):
    """Decide a shared fetch's failure for this reference - and, when the
    identity itself is spent, once for every reference still waiting on
    its document (#1410).

    The own reference is decided through its claim token like the own-fetch
    path decides a final transport failure; the caller hands it a row its
    delivery still holds. ``mirror`` names which failure this is: an
    identity whose fetch budget ran out, or an answer which is no document
    at all, can never answer again in this run - then every other
    reference of this acquisition which is still PENDING is decided with
    the same kind under its own conditional update, each telling the
    polling client about itself with a warning of its own, exactly the way
    a per-reference failure tells one (#1263's honesty, #1410's batching).
    A sibling which already claimed again in the meantime is deliberately
    not touched: its delivery owns its answer. While the identity still
    has budget and only this delivery's own policy ran out, no sibling is
    decided here at all - its attempts are still its own to make.
    The acquisition row goes back to PENDING: a reference which the retry
    API of #1265 hands back to work re-fetches through the very same
    identity, once, instead of minting a per-reference request.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    decided_own = _decide_reference_failure(
        background_process_pk, temporary_md_metadata_file_id,
        token, kind, error, retried=retried)
    if decided_own:
        settings.ROOT_LOGGER.warning(
            f"The shared registration document {doc.pk} of process "
            f"{background_process_pk} was not answered ({kind.value}): "
            f"{error}.", stack_info=True)
        task.log_process(
            f"Could not fetch the shared reference document of "
            f"'{doc.requested_url}': {error} The reference is kept and "
            f"can be fetched again.",
            LogTypeEnum.WARNING)
    if not mirror:
        return {"data": None, "outcome": None, "error_kind": kind.value}
    moment = now()
    with transaction.atomic():
        # the process first, the rows second - the lock order every other
        # decision path of the collection keeps, so the mirror of a shared
        # failure can never deadlock against a sibling's own decision
        process = BackgroundProcess.objects.select_for_update().filter(
            pk=background_process_pk).first()
        if process is None or process.done_at is not None:
            return {"data": None, "outcome": None,
                    "error_kind": kind.value}
        candidates = list(TemporaryMdMetadataFile.objects.filter(
            acquisition_id=doc.pk,
            state=ReferenceWorkStateEnum.PENDING.value,
        ).exclude(pk=temporary_md_metadata_file_id).values_list(
            "pk", flat=True))
        if not candidates:
            return {"data": None, "outcome": None,
                    "error_kind": kind.value}
        # one conditional UPDATE for all still-open references of the
        # identity - the shape #1395 asks of task code. A sibling which
        # claimed again in the meantime fails the state check and keeps
        # its own answer: its delivery owns it.
        TemporaryMdMetadataFile.objects.filter(
            pk__in=candidates,
            state=ReferenceWorkStateEnum.PENDING.value).update(
                state=ReferenceWorkStateEnum.FAILED.value,
                claim_token=None,
                lease_expires_at=None,
                error_kind=kind.value,
                error_at=moment,
                import_error=str(error))
        decided = list(TemporaryMdMetadataFile.objects.filter(
            pk__in=candidates,
            state=ReferenceWorkStateEnum.FAILED.value,
            error_kind=kind.value,
            error_at=moment).order_by("pk"))
        if decided:
            # the stamp above is this statement's alone: a sibling another
            # path decided in between kept its own error_at and is not
            # counted or told about twice
            BackgroundProcess.objects.record_reference_outcome(
                background_process_pk, failed_delta=len(decided),
                steps_delta=len(decided))
            for row in decided:
                # one warning per decided reference: the polling client
                # of #1264 learns of every failed step by itself, no
                # matter which path decided it
                task.log_process(
                    f"Could not fetch the document of reference "
                    f"'{row.requested_url or row.pk}': {error} Its shared "
                    f"document stayed unanswered; the reference is kept "
                    f"and can be fetched again.",
                    LogTypeEnum.WARNING)
    return {"data": None, "outcome": None, "error_kind": kind.value}


def _drain_acquisition_if_last(acquisition_pk):
    """Take a shared acquisition away when no reference points at it.

    The acquisition exists to serve reference rows; the last one to decide
    (its success deletes the row, and every failure shape either kept the
    reference for the retry API or never pointed here again) removes the
    row and with it the stored copy. A FAILED reference keeps pointing at
    the row on purpose - its authorized retry re-uses the identity and a
    still-valid stored copy instead of paying for a second document.
    """
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition, TemporaryMdMetadataFile)

    with transaction.atomic():
        doc = RegistrationDocumentAcquisition.objects \
            .select_for_update(of=("self",)).filter(
                pk=acquisition_pk).first()
        if doc is None:
            return False
        if TemporaryMdMetadataFile.objects.filter(
                acquisition_id=acquisition_pk).exists():
            return False
        doc.delete()
    return True


def _decide_unanswered_reference(task, row, error, background_process_pk,
                                 temporary_md_metadata_file_id, token,
                                 retried):
    """Handle the fetch of a reference which was not answered.

    A transport failure is not a decision: while retries are left the
    lease goes back and the exception travels to the base class's
    bounded retry. Only the last permitted attempt decides the row as
    failed, naming which of the two ways the document was lost; the row
    is kept for the retry of #1265.
    """
    if task.request.retries < task.max_retries:
        # nothing is decided by a missing answer: the lease goes back so
        # the retried delivery (or, if this worker dies with it, the
        # recovery) can claim the row again (#1260, #1207)
        row.release_claim(token)
        raise error
    kind = (ReferenceErrorKind.FETCH_TIMEOUT
            if isinstance(error, MetadataFetchTimeout)
            else ReferenceErrorKind.FETCH_UNREACHABLE)
    if _decide_reference_failure(
            background_process_pk, temporary_md_metadata_file_id,
            token, kind, error, retried=retried):
        settings.ROOT_LOGGER.warning(
            f"Registration reference {temporary_md_metadata_file_id} "
            f"of process {background_process_pk} was not answered "
            f"after {task.max_retries} retries: {error}", stack_info=True)
        task.log_process(
            f"Could not fetch the reference document of "
            f"'{row.described_display or row.requested_url}': {error} "
            f"Given up after {task.max_retries} retries; the reference "
            f"is kept and can be fetched again.",
            LogTypeEnum.WARNING)
    return None


def _decide_stored_reference(task, row, background_process_pk,
                             temporary_md_metadata_file_id, token, retried,
                             storage_name):
    """Import the fetched document behind its still-valid permit and
    decide the reference in the same transaction (#1263).

    Answers the task result of the outcome this delivery owns: the
    decided failure, the created record - or None when the permit died
    while the document was in flight and this delivery owns nothing to
    report.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    with transaction.atomic():
        process = BackgroundProcess.objects.select_for_update(of=("self",)).filter(
            pk=background_process_pk).first()
        fresh = TemporaryMdMetadataFile.objects.select_for_update(of=("self",)).filter(
            pk=temporary_md_metadata_file_id).first()
        if (fresh is None or fresh.state != ReferenceWorkStateEnum.LEASED.value
                or str(fresh.claim_token) != str(token)):
            # the permit died while the document was in flight - a recovery
            # re-drove the row, or the process' deletion took it. Nothing
            # this delivery could report is still its to report; what it
            # stored is an orphan by definition and the sweep is its answer.
            _delete_storage_file_after_commit(storage_name)
            settings.ROOT_LOGGER.warning(
                f"The claim of registration reference "
                f"{temporary_md_metadata_file_id} was lost while the "
                f"document was fetched; this delivery's outcome is "
                f"discarded.", stack_info=True)
            return None

        try:
            with transaction.atomic():
                fresh.md_metadata_file = storage_name
                record = fresh.import_registration_reference()
        except Exception as e:
            return _decide_import_failure(
                task, process, fresh, token, retried, e, storage_name,
                background_process_pk, temporary_md_metadata_file_id, row)

        if record is None:
            return _decide_no_identifiable_record(
                task, process, fresh, token, retried, storage_name, row)

        # the reference is stored: the row's job is done, and the row goes
        # away with it - the absence is what a redelivery reads as decided.
        # The stored document goes with it, after this commit; the record
        # and its coupling are the permanent answer and stay.
        fresh.delete()
        BackgroundProcess.objects.record_reference_outcome(
            process.pk, stored_delta=1,
            failed_delta=-1 if retried else 0,
            step_done=not retried)

    task.update_state(state=states.STARTED, meta={'done': 1, 'total': 1})
    is_dataset = isinstance(record, DatasetMetadataRecord)
    return {
        "data": {
            "type": "DatasetMetadataRecord" if is_dataset else "ServiceMetadata",
            "id": f"{record.pk}",
            "links": {
                "self": f"{reverse(viewname=f'registry:{"datasetmetadata" if is_dataset else "servicemetadata"}-detail', args=[record.pk])}"
            }
        },
        "outcome": CollectionStepOutcome.RECORD_CREATED.value,
    }


def _decide_import_failure(task, process, fresh, token, retried, error,
                           storage_name, background_process_pk,
                           temporary_md_metadata_file_id, row):
    """Record a reference whose import did not get through.

    The savepoint in the caller undid everything the mapping wrote; the
    row and its stored document carry the decision and its reason. An
    unmapped hierarchyLevel is the known kind; anything else the import
    could not get through is recorded as a failed import - visible, kept,
    and fetchable again (#1257, #1263).
    """
    kind = (ReferenceErrorKind.UNSUPPORTED_KIND
            if isinstance(error, UnknownMetadataKind)
            else ReferenceErrorKind.IMPORT_FAILED)
    _decide_reference_failure_locked(
        process, fresh, token, kind, error,
        storage_name=storage_name, retried=retried)
    settings.ROOT_LOGGER.warning(
        f"Registration reference {temporary_md_metadata_file_id} "
        f"of process {background_process_pk} could not be "
        f"imported ({kind.value}): {error}", stack_info=True)
    task.log_process(
        f"The reference document of "
        f"'{row.described_display or row.requested_url}' could not "
        f"be imported ({kind.value}): {error}", LogTypeEnum.WARNING)
    return {"data": None, "outcome": None,
            "error_kind": kind.value}


def _decide_no_identifiable_record(task, process, fresh, token, retried,
                                   storage_name, row):
    """Record a reference fetched and parsed with no record in it (#1261) -
    kept as the row's document for whoever reads the failed reference."""
    _decide_reference_failure_locked(
        process, fresh, token,
        ReferenceErrorKind.NO_IDENTIFIABLE_RECORD, None,
        storage_name=storage_name, retried=retried)
    task.log_process(
        f"The reference document of "
        f"'{row.described_display or row.requested_url}' was "
        f"fetched and parsed, but it carries no identifiable "
        f"record.", LogTypeEnum.WARNING)
    return {
        "data": None,
        "outcome": CollectionStepOutcome.NO_IDENTIFIABLE_RECORD.value,
    }


def _decide_reference_failure(
        background_process_pk, temporary_md_metadata_file_id,
        claim_token, kind, error, storage_name=None, retried=False):
    """Record a decided failure of a reference under its own fresh locks.

    The entry the paths outside the finalize transaction walk: it takes the
    process-then-row lock order and only decides while the claim token
    still owns the row - a permit lost meanwhile belongs to an answer that
    is or will be the other holder's to report.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    with transaction.atomic():
        process = BackgroundProcess.objects.select_for_update(of=("self",)).filter(
            pk=background_process_pk).first()
        row = TemporaryMdMetadataFile.objects.select_for_update(of=("self",)).filter(
            pk=temporary_md_metadata_file_id).first()
        if (row is None
                or row.state != ReferenceWorkStateEnum.LEASED.value
                or str(row.claim_token) != str(claim_token)):
            if storage_name:
                _delete_storage_file_after_commit(storage_name)
            return False
        return _decide_reference_failure_locked(
            process, row, claim_token, kind, error,
            storage_name=storage_name, retried=retried)


def _decide_reference_failure_locked(
        process, row, claim_token, kind, error, storage_name=None,
        retried=False):
    """Write the FAILED end state of one reference while its row is locked.

    The row is kept - a failed reference is the retryable finding of the
    run, not a vanished one (#1263) - with the machine-readable kind of
    what decided it, and the stored document when the failure left one.
    The counters move through ``record_reference_outcome`` so a process
    which decided itself in the meantime is not silently reopened.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    values = {
        "state": ReferenceWorkStateEnum.FAILED.value,
        "claim_token": None,
        "lease_expires_at": None,
        "error_kind": kind.value,
        "error_at": now(),
        "import_error": str(error) if error is not None else "",
    }
    if storage_name:
        values["md_metadata_file"] = storage_name
    updated = TemporaryMdMetadataFile.objects.filter(
        pk=row.pk,
        state=ReferenceWorkStateEnum.LEASED.value,
        claim_token=claim_token).update(**values)
    if updated and process is not None and not retried:
        BackgroundProcess.objects.record_reference_outcome(
            process.pk, failed_delta=1, step_done=True)
    # a re-failed retry moves no counter: its first decision already
    # counted this reference as failed and its step as done - the sealed
    # plan's counts belong to the plan, not to the attempts (#1263)
    return updated


def _delete_storage_file_after_commit(name):
    """Take one orphaned stored document away after the current commit.

    A file deletion is no rollback material, so it waits for the commit of
    whatever decided the database around it; a refusal does not lose the
    bytes - the bounded registration sweep re-reads the prefix and takes
    what no row references anymore.
    """
    if not name:
        return
    from registry.models.harvest import \
        TemporaryMdMetadataFile  # local import: cycle
    storage = TemporaryMdMetadataFile._meta.get_field(
        "md_metadata_file").storage

    def _remove():
        try:
            storage.delete(name)
        except Exception:
            settings.ROOT_LOGGER.warning(
                f"Could not delete the orphaned registration reference "
                f"document {name}; the bounded registration sweep will try "
                f"again.", stack_info=True)

    transaction.on_commit(_remove)


@shared_task(bind=True,
             queue=celery_queues.DB_ROUTINES,
             base=BackgroundProcessBased)
def finish_metadata_collection(self, *args, **kwargs):
    """Close a run whose reference fan-out has all reported in.

    The body of the collection's chord, and the closer the recovery publishes
    for a sealed plan whose rows all decided. It runs when every member
    answered, which is not the same as every reference being decided: a
    redelivery which lost its claim withdraws without deciding, and the
    delivery that holds the lease may still be working the row. So the body
    looks at the work rows instead of trusting the chord - while a delivery
    holds a LEASE it waits, and the run completes with the last decision it
    waited for, not under it (#1263). A row nobody ever claimed is nobody's
    work: with every delivery of the fan-out answered, no claim on it can come
    anymore, and the completion counts it skipped like #1259 always did.
    The check and the completion hold the process lock which every claim
    takes first, so no claim can slip between looking and completing; a
    claim which loses that race meets a completed run and withdraws. Like
    every completion of a planned collection the summary closes with the
    references which never answered an outcome at all (#1259).

    A registration is closed by completing its process. An update reports
    through a job as well, and the job is the one which decides about its run:
    for an update the body closes the job which reports this process, so the
    metadata step ends the update it is a step of (#1274) - including for a
    process an administrator decided about in the meantime, whose job must not
    stay unfinished forever.
    """
    if self.background_process_pk is None:
        self.update_background_process(
            completed=True
        )
        return

    if _wait_for_open_leases_or_close_run(self):
        raise self.retry(countdown=FINISH_WAIT_COUNTDOWN_SECONDS,
                         max_retries=FINISH_WAIT_MAX_RETRIES)


def _wait_for_open_leases_or_close_run(task):
    """Under the process lock: wait while a delivery holds a lease, or
    complete the run with the last decision it waited for (#1263).

    Answers True when this body has to run again.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    with transaction.atomic():
        process = BackgroundProcess.objects.select_for_update().filter(
            pk=task.background_process_pk).first()
        if process is None:
            # the run was deleted while its chord answered - there is
            # nothing to complete, and its deletion sweep owns the rows
            return False
        from registry.models.harvest import (  # local import: cycle
            RegistrationDocumentAcquisition)
        leased = TemporaryMdMetadataFile.objects.filter(
            background_process_id=task.background_process_pk,
            state=ReferenceWorkStateEnum.LEASED.value,
        ).exists() or RegistrationDocumentAcquisition.objects.filter(
            background_process_id=task.background_process_pk,
            state=DocumentAcquisitionStateEnum.LEASED.value,
        ).exists()
        if leased and task.request.retries < FINISH_WAIT_MAX_RETRIES:
            return True
        if leased:
            # the wait itself ran out - only reachable while
            # something keeps re-leasing rows faster than they
            # decide. The completion below counts what stayed
            # undecided as skipped, exactly like any interrupted
            # plan; from the done_at written here on, the claim gate
            # refuses every late report about these rows.
            settings.ROOT_LOGGER.warning(
                f"BackgroundProcess {task.background_process_pk} "
                f"completed while registration work rows or shared "
                f"document acquisitions were still leased - late "
                f"outcomes are refused from here.",
                stack_info=True)
        _close_finished_run(task)
    return False


def _close_finished_run(task):
    """Close the run this collection belongs to.

    A run which an update job reports is closed by that job, not here:
    the collection is a step of the update (#1274), so the update
    decides what its run did and the process of the job mirrors the
    status the job answers. A registration has nothing but its process
    and completes it right here.
    """
    from registry.models.update import \
        update_job_for_process  # local import: cycle
    job = update_job_for_process(task.background_process_pk)
    if job is not None:
        job.metadata_step_completed()
    else:
        task.update_background_process(
            completed=True
        )


@worker_ready.connect
def recover_registration_references_after_restart(sender, **kwargs):
    # a crash between committing a sealed plan and publishing its chord
    # leaves exactly the database shape this recovery reads; like the
    # harvest recovery, the worker start is what notices without a
    # schedule. Addressed by name, the call is a remote call: the queue is
    # part of it and the task's own declaration is not what routes it - so
    # the call names the queue of #1263's isolation the task declares
    # (#1455)
    sender.app.send_task(
        "registry.tasks.service.recover_registration_reference_work",
        queue=celery_queues.DB_ROUTINES)


def _drain_finished_acquisitions(processes):
    """Take away the crash residue of #1410's shared acquisitions.

    An acquisition whose references all decided while its own row (or its
    stored copy) stayed behind is a crash residue - no reference reads it
    anymore and the pass takes it, and with it its bytes, away. A FAILED
    reference keeps its row and keeps pointing at the acquisition, so a
    retryable failure never drains it.

    Read whole: one selection over every swept process, one bulk delete,
    then the bytes (#1395's shape for task code; the reference's FK is
    SET_NULL, so the delete can never take a work row - at most it orphans
    the acquisition a race just created a reference for, and the reference
    still answers from its own row). Returns the amount of drained rows.
    """
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition, TemporaryMdMetadataFile)

    residue = []
    acquisitions = list(
        RegistrationDocumentAcquisition.objects.filter(
            background_process__in=processes).only(
                "id", "md_metadata_file"))
    if acquisitions:
        referenced = set(
            TemporaryMdMetadataFile.objects.filter(
                acquisition__in=[a.pk for a in acquisitions]).values_list(
                    "acquisition_id", flat=True))
        residue = [a for a in acquisitions if a.pk not in referenced]
    if not residue:
        return 0
    names = [a.md_metadata_file.name for a in residue
             if a.md_metadata_file]
    storage = RegistrationDocumentAcquisition._meta.get_field(
        "md_metadata_file").storage
    try:
        RegistrationDocumentAcquisition.objects.filter(
            pk__in=[a.pk for a in residue]).delete()
    except Exception:
        # nothing is deleted, nothing is lost: the rows and their bytes
        # stay and the next pass reads them again
        settings.ROOT_LOGGER.warning(
            f"Could not drain {len(residue)} shared document "
            f"acquisition(s) of the swept registration processes - the "
            f"next sweep will.", stack_info=True)
        return 0
    for name in names:
        # the bulk delete walks past the row's own file sweep, so the
        # pass takes the bytes itself - the same helper the orphan
        # sweep uses, which keeps a failure for the next pass
        _delete_registration_orphan(storage, name)
    return len(residue)


@shared_task(queue=celery_queues.DB_ROUTINES, base=SingletonTask)
def recover_registration_reference_work(*args, **kwargs):
    """Re-drive the registration reference work no live chord will decide.

    The sealed plan answers what was planned, the work rows answer what is
    still open: a RUNNING or still-published process whose PENDING row has
    outlived the age a healthy queue drains in, or whose LEASE has expired,
    is a reference whose driving message was lost - a broker which
    swallowed the publish, a worker which died with the claim, a chord
    whose members failed without their body ever running. Each eligible row
    is handed back to ``collect_reference``, whose claim makes the doubled
    message harmless when the original turns out to have been alive after
    all (#1263).

    A sealed plan whose every row is decided - deleted or FAILED - but
    whose process never completed (the same crash shapes, one step later)
    is closed through the same ``finish_metadata_collection`` the chord
    body would have called. And the stored documents no work row references
    anymore - a lost attempt's bytes, a storage refusal of a completion
    sweep - are reaped from the process prefixes, within the same bounded
    reach as the harvesting cleanup keeps its own prefix (#1263).

    Returns:
        dict: what one pass redrove, completed and deleted; empty counts
            are the normal answer of an idle deployment.
    """
    from registry.models.harvest import TemporaryMdMetadataFile  # local

    summary = {"redriven": 0, "completed": [], "orphan_files": 0,
               "drained": 0}
    moment = timezone.now()

    processes = BackgroundProcess.objects.filter(
        references_plan_sealed=True,
        done_at__isnull=True,
        status__in=[ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING],
    ).order_by("pk")

    stale_pending_before = moment - REFERENCE_PENDING_RECOVERY_AGE
    for process in processes:
        eligible = TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk).filter(
                # a PENDING row which outlived any plausible queue time, or
                # a LEASE whose holder did not report within its lease; a
                # row planned without an age stamp (none is planned that
                # way, but an inserted one must not hide forever) counts as
                # old. The FAILED row of a decided failure is never re-
                # driven automatically: only the authorization of #1265
                # hands a decided reference back to work.
                (Q(state=ReferenceWorkStateEnum.PENDING.value)
                 & (Q(request_id__isnull=True)
                    | Q(request_id__lt=stale_pending_before)))
                | Q(state=ReferenceWorkStateEnum.LEASED.value,
                    lease_expires_at__lt=moment)
        ).order_by("pk")[:REGISTRATION_RECOVERY_BATCH_SIZE]
        for row in eligible:
            try:
                collect_reference.apply_async(kwargs={
                    "background_process_pk": process.pk,
                    "temporary_md_metadata_file_id": row.pk,
                })
                summary["redriven"] += 1
            except Exception:
                # a broker which refuses now answers again on the next
                # pass; one row's publish must not end the sweep
                settings.ROOT_LOGGER.warning(
                    f"Could not re-drive registration reference {row.pk} "
                    f"of process {process.pk} - the next sweep will.",
                    stack_info=True)

    # the drain pass of #1410: crash residue goes, retryable failures stay
    summary["drained"] += _drain_finished_acquisitions(processes)

    for process in processes:
        outstanding = TemporaryMdMetadataFile.objects.filter(
            background_process_id=process.pk,
            state__in=[ReferenceWorkStateEnum.PENDING.value,
                       ReferenceWorkStateEnum.LEASED.value],
        ).exists()
        if outstanding:
            continue
        try:
            finish_metadata_collection.apply_async(kwargs={
                "background_process_pk": process.pk,
            })
            summary["completed"].append(process.pk)
        except Exception:
            settings.ROOT_LOGGER.warning(
                f"Could not publish the completion of registration process "
                f"{process.pk} whose references all decided - the next "
                f"sweep will.", stack_info=True)

    try:
        summary["orphan_files"] = sweep_registration_orphan_files()
    except Exception:
        settings.ROOT_LOGGER.exception(
            "The registration orphan file sweep failed; the bytes stay "
            "until the next pass.", stack_info=True, exc_info=True)

    if summary["redriven"] or summary["completed"] or summary[
            "orphan_files"] or summary["drained"]:
        settings.ROOT_LOGGER.info(
            f"Registration reference recovery: {summary['redriven']} row(s) "
            f"re-driven, {len(summary['completed'])} process(es) closed "
            f"({summary['completed'][:20]}), "
            f"{summary['drained']} drained acquisition(s), "
            f"{summary['orphan_files']} orphan document(s) deleted.")
    return summary


def sweep_registration_orphan_files():
    """Delete the stored documents below the registration prefix that no
    work row references anymore (#1263).

    The prefix is the registration's own - the harvesting cleanup's numeric
    job-directory rule never reaches it and this sweep never walks it: this
    function lists ``temporary_md_metadata_file/registration/<process>/``
    and nothing else. A file is an orphan when no row of that process
    stores under its name and no row's current claim token names it as the
    document of a live attempt, and it is older than the grace which covers
    the window between writing a document and committing the row that names
    it. Failed references keep their document: only a row's deletion (or a
    process deletion, whose sweep runs on_commit) takes a decided row's
    bytes away - this function only adds the lost attempts and the failed
    removals.
    """
    from registry.tasks.harvest import _temp_files_storage  # local import
    from registry.models.harvest import (  # local import: cycle
        REGISTRATION_FILE_SUBDIR, TEMPORARY_MD_METADATA_FILE_SUBDIR)

    storage = _temp_files_storage()
    base = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{REGISTRATION_FILE_SUBDIR}"
    try:
        process_dirs, _ = storage.listdir(base)
    except FileNotFoundError:
        # no registration ever stored a document: nothing to reap
        return 0

    grace = timedelta(seconds=REGISTRATION_ORPHAN_FILE_GRACE_SECONDS)
    return sum(
        _sweep_registration_process_dir(storage, base, process_dir, grace)
        for process_dir in process_dirs)


def _sweep_registration_process_dir(storage, base, process_dir, grace):
    """Delete the orphaned documents below one process directory."""
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    if not process_dir.isdigit():
        # not a process prefix this code wrote - never delete what the
        # layout does not explain (same posture as the harvest sweep,
        # which ignores non-numeric directories)
        return 0
    from registry.models.harvest import (  # local import: cycle
        RegistrationDocumentAcquisition)
    process_pk = int(process_dir)
    rows = TemporaryMdMetadataFile.objects.filter(
        background_process_id=process_pk)
    live_names = {name for name in rows.values_list(
        "md_metadata_file", flat=True) if name}
    live_tokens = {str(token) for token in rows.values_list(
        "claim_token", flat=True) if token is not None}
    # the shared acquisitions of #1410 store below the very same prefix:
    # their live names and live fetch tokens join the live set, so the
    # sweep spares a stored copy and the bytes of a fetch in flight and
    # reaps what no acquisition row names anymore
    acq = RegistrationDocumentAcquisition.objects.filter(
        background_process_id=process_pk)
    live_names |= {name for name in acq.values_list(
        "md_metadata_file", flat=True) if name}
    live_tokens |= {str(token) for token in acq.values_list(
        "claim_token", flat=True) if token is not None}
    try:
        _, file_names = storage.listdir(f"{base}/{process_dir}")
    except FileNotFoundError:
        return 0
    deleted = 0
    for file_name in file_names:
        full_name = f"{base}/{process_dir}/{file_name}"
        if not _registration_file_is_orphan(
                storage, full_name, file_name, live_names, live_tokens,
                grace):
            continue
        if _delete_registration_orphan(storage, full_name):
            deleted += 1
    return deleted


def _registration_file_is_orphan(storage, full_name, file_name, live_names,
                                 live_tokens, grace):
    """Whether no live row names this document and its age is past grace."""
    if full_name in live_names:
        return False
    if any(token in file_name for token in live_tokens):
        # the document of an attempt whose lease still runs - not
        # an orphan yet, whatever its row's stored name says
        return False
    return _registration_orphan_is_old(storage, full_name, grace)


def _registration_orphan_is_old(storage, full_name, grace):
    """Whether the file is past the grace which covers the write window."""
    try:
        modified = storage.get_modified_time(full_name)
    except Exception:
        # an unreadable age is no licence to delete: the next pass
        # reads it, a byte too live stays a byte too live
        return False
    return modified <= timezone.now() - grace


def _delete_registration_orphan(storage, full_name):
    """True when the file is gone afterwards."""
    try:
        storage.delete(full_name)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        settings.ROOT_LOGGER.warning(
            f"Could not delete the orphaned registration reference "
            f"document {full_name}; the next sweep tries again.",
            stack_info=True)
        return False
