"""Celery tasks of the OGC service registration (#1263).

The collection of a registration's metadata references runs on a work queue
of its own: the root task seals a plan of one ``TemporaryMdMetadataFile``
work row per advertised reference, and one delivery per row fetches, stores,
imports and decides exactly that row. The row is the permit - a delivery
only works under the claim token it just took, a successful import deletes
the row, and the absence of the row is the proof which makes a redelivery a
no-op instead of a second import.
"""
from datetime import timedelta
from itertools import chain
from urllib import parse

from celery import chord, shared_task, states
from celery.signals import worker_ready
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.timezone import now
from extras.tasks import SingletonTask
from MrMap import celery_queues
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.tasks import BackgroundProcessBased
from registry.enums.metadata import (CollectionStepOutcome,
                                     ReferenceErrorKind,
                                     ReferenceWorkStateEnum)
from registry.exceptions.metadata import (MetadataFetchTimeout,
                                          MetadataFetchUnreachable,
                                          UnknownMetadataKind)
from registry.exceptions.service import (CapabilitiesPersistenceError,
                                         NoContent)
from registry.mappers.factory import OGCServiceXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.models import (CatalogueService, FeatureType, Layer,
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
from requests import Request, Session
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
        if isinstance(db_service, (WebMapService, WebFeatureService)):
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
            elif sealed:
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
            else:
                # planned empty: the seal said 0 and there is nothing to
                # wait for - the run completes with its zero-reference
                # summary right here (#1263).
                self.update_background_process(
                    completed=True,
                    service=db_service,
                )
        else:
            # a registration which collects no references (a CSW) stays the
            # plain run it was: no plan, no summary, completion as before.
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
        row = TemporaryMdMetadataFile(
            background_process_id=background_process_pk,
            reference_key=key,
            requested_url=url,
            described_display=(getattr(described, "title", "") or "")[:512],
            # when the request for this document was planned: the age the
            # recovery measures a stuck PENDING row by
            request_id=timezone.now(),
        )
        if isinstance(described, WebMapService):
            row.described_wms = described
        elif isinstance(described, WebFeatureService):
            row.described_wfs = described
        elif isinstance(described, Layer):
            row.described_layer = described
        elif isinstance(described, FeatureType):
            row.described_featuretype = described
        else:
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
        rows.append(row)

    with transaction.atomic():
        process = BackgroundProcess.objects.select_for_update().filter(
            pk=background_process_pk).first()
        if process is None or process.done_at is not None:
            # decided or deleted while this delivery worked: nothing to plan
            # for, and the rows' owner is gone with them through the cascade
            return None
        if process.references_plan_sealed:
            return None
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

    try:
        content = fetch_metadata_document(
            row.requested_url,
            reference=(f"registration reference of "
                       f"{row.described_display or row.requested_url}"))
    except (MetadataFetchTimeout, MetadataFetchUnreachable) as e:
        if self.request.retries < self.max_retries:
            # nothing is decided by a missing answer: the lease goes back so
            # the retried delivery (or, if this worker dies with it, the
            # recovery) can claim the row again (#1260, #1207)
            row.release_claim(token)
            raise
        # the last attempt the retry policy permits got no answer either:
        # this is the decision, and it names which of the two ways the
        # document was lost. The row is kept for the retry of #1265.
        kind = (ReferenceErrorKind.FETCH_TIMEOUT
                if isinstance(e, MetadataFetchTimeout)
                else ReferenceErrorKind.FETCH_UNREACHABLE)
        if _decide_reference_failure(
                background_process_pk, temporary_md_metadata_file_id,
                token, kind, e, retried=retried):
            settings.ROOT_LOGGER.warning(
                f"Registration reference {temporary_md_metadata_file_id} "
                f"of process {background_process_pk} was not answered "
                f"after {self.max_retries} retries: {e}", stack_info=True)
            self.log_process(
                f"Could not fetch the reference document of "
                f"'{row.described_display or row.requested_url}': {e} "
                f"Given up after {self.max_retries} retries; the reference "
                f"is kept and can be fetched again.",
                LogTypeEnum.WARNING)
        return None
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
        self.log_process(
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
        self.log_process(
            f"The document of reference "
            f"'{row.described_display or row.requested_url}' could not be "
            f"stored: {e}", LogTypeEnum.WARNING)
        raise
    storage_name = row.md_metadata_file.name

    # one decision about one reference: the record, its coupling, the row's
    # end state and the process' counters are written in the same
    # transaction, behind the row lock which re-checks the permit.
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
            # the savepoint above undid everything the mapping wrote; the
            # row and its stored document carry the decision and its reason.
            # An unmapped hierarchyLevel is the known kind; anything else
            # the import could not get through is recorded as a failed
            # import - visible, kept, and fetchable again (#1257, #1263).
            kind = (ReferenceErrorKind.UNSUPPORTED_KIND
                    if isinstance(e, UnknownMetadataKind)
                    else ReferenceErrorKind.IMPORT_FAILED)
            _decide_reference_failure_locked(
                process, fresh, token, kind, e,
                storage_name=storage_name, retried=retried)
            settings.ROOT_LOGGER.warning(
                f"Registration reference {temporary_md_metadata_file_id} "
                f"of process {background_process_pk} could not be "
                f"imported ({kind.value}): {e}", stack_info=True)
            self.log_process(
                f"The reference document of "
                f"'{row.described_display or row.requested_url}' could not "
                f"be imported ({kind.value}): {e}", LogTypeEnum.WARNING)
            return {"data": None, "outcome": None,
                    "error_kind": kind.value}

        if record is None:
            # fetched and parsed, but no record identifies itself in it:
            # the decided failure which names no record (#1261) - kept as
            # the row's document for whoever reads the failed reference.
            _decide_reference_failure_locked(
                process, fresh, token,
                ReferenceErrorKind.NO_IDENTIFIABLE_RECORD, None,
                storage_name=storage_name, retried=retried)
            self.log_process(
                f"The reference document of "
                f"'{row.described_display or row.requested_url}' was "
                f"fetched and parsed, but it carries no identifiable "
                f"record.", LogTypeEnum.WARNING)
            return {
                "data": None,
                "outcome": CollectionStepOutcome.NO_IDENTIFIABLE_RECORD.value,
            }

        # the reference is stored: the row's job is done, and the row goes
        # away with it - the absence is what a redelivery reads as decided.
        # The stored document goes with it, after this commit; the record
        # and its coupling are the permanent answer and stay.
        fresh.delete()
        BackgroundProcess.objects.record_reference_outcome(
            process.pk, stored_delta=1,
            failed_delta=-1 if retried else 0,
            step_done=not retried)

    self.update_state(state=states.STARTED, meta={'done': 1, 'total': 1})
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
    from registry.models.harvest import TemporaryMdMetadataFile  # local import: cycle

    if self.background_process_pk is not None:
        wait = False
        with transaction.atomic():
            process = BackgroundProcess.objects.select_for_update().filter(
                pk=self.background_process_pk).first()
            if process is None:
                # the run was deleted while its chord answered - there is
                # nothing to complete, and its deletion sweep owns the rows
                return
            leased = TemporaryMdMetadataFile.objects.filter(
                background_process_id=self.background_process_pk,
                state=ReferenceWorkStateEnum.LEASED.value,
            ).exists()
            if leased and self.request.retries < FINISH_WAIT_MAX_RETRIES:
                wait = True
            else:
                if leased:
                    # the wait itself ran out - only reachable while
                    # something keeps re-leasing rows faster than they
                    # decide. The completion below counts what stayed
                    # undecided as skipped, exactly like any interrupted
                    # plan; from the done_at written here on, the claim gate
                    # refuses every late report about these rows.
                    settings.ROOT_LOGGER.warning(
                        f"BackgroundProcess {self.background_process_pk} "
                        f"completed while registration work rows were still "
                        f"leased - late outcomes are refused from here.",
                        stack_info=True)
                # A run which an update job reports is closed by that job, not
                # here: the collection is a step of the update (#1274), so the
                # update decides what its run did and the process of the job
                # mirrors the status the job answers. A registration has
                # nothing but its process and completes it right here.
                from registry.models.update import \
                    update_job_for_process  # local import: cycle
                job = update_job_for_process(self.background_process_pk)
                if job is not None:
                    job.metadata_step_completed()
                else:
                    self.update_background_process(
                        completed=True
                    )
        if wait:
            raise self.retry(countdown=FINISH_WAIT_COUNTDOWN_SECONDS,
                             max_retries=FINISH_WAIT_MAX_RETRIES)
    else:
        self.update_background_process(
            completed=True
        )


@worker_ready.connect
def recover_registration_references_after_restart(sender, **kwargs):
    # a crash between committing a sealed plan and publishing its chord
    # leaves exactly the database shape this recovery reads; like the
    # harvest recovery, the worker start is what notices without a schedule
    sender.app.send_task(
        "registry.tasks.service.recover_registration_reference_work")


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
    from registry.models.harvest import (  # local import: cycle
        TemporaryMdMetadataFile)

    summary = {"redriven": 0, "completed": [], "orphan_files": 0}
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

    if summary["redriven"] or summary["completed"] or summary["orphan_files"]:
        settings.ROOT_LOGGER.info(
            f"Registration reference recovery: {summary['redriven']} row(s) "
            f"re-driven, {len(summary['completed'])} process(es) closed "
            f"({summary['completed'][:20]}), "
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
        REGISTRATION_FILE_SUBDIR, TEMPORARY_MD_METADATA_FILE_SUBDIR,
        TemporaryMdMetadataFile)

    storage = _temp_files_storage()
    base = f"{TEMPORARY_MD_METADATA_FILE_SUBDIR}/{REGISTRATION_FILE_SUBDIR}"
    try:
        process_dirs, _ = storage.listdir(base)
    except FileNotFoundError:
        # no registration ever stored a document: nothing to reap
        return 0

    deleted = 0
    grace = timedelta(seconds=REGISTRATION_ORPHAN_FILE_GRACE_SECONDS)
    for process_dir in process_dirs:
        if not process_dir.isdigit():
            # not a process prefix this code wrote - never delete what the
            # layout does not explain (same posture as the harvest sweep,
            # which ignores non-numeric directories)
            continue
        process_pk = int(process_dir)
        rows = TemporaryMdMetadataFile.objects.filter(
            background_process_id=process_pk).only(
                "md_metadata_file", "claim_token")
        live_names = {row.md_metadata_file.name for row in rows
                      if row.md_metadata_file.name}
        live_tokens = {str(row.claim_token) for row in rows
                       if row.claim_token is not None}
        try:
            _, file_names = storage.listdir(f"{base}/{process_dir}")
        except FileNotFoundError:
            continue
        for file_name in file_names:
            full_name = f"{base}/{process_dir}/{file_name}"
            if full_name in live_names:
                continue
            if any(token in file_name for token in live_tokens):
                # the document of an attempt whose lease still runs - not
                # an orphan yet, whatever its row's stored name says
                continue
            try:
                modified = storage.get_modified_time(full_name)
                if modified > timezone.now() - grace:
                    continue
            except Exception:
                # an unreadable age is no licence to delete: the next pass
                # reads it, a byte too live stays a byte too live
                continue
            try:
                storage.delete(full_name)
                deleted += 1
            except FileNotFoundError:
                continue
            except Exception:
                settings.ROOT_LOGGER.warning(
                    f"Could not delete the orphaned registration reference "
                    f"document {full_name}; the next sweep tries again.",
                    stack_info=True)
    return deleted
