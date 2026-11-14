from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from django.utils import timezone
from lxml import etree
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.enums.metadata import ReferenceWorkStateEnum
from registry.enums.service import AuthTypeEnum, OGCServiceVersionEnum
from registry.exceptions.service import (CapabilitiesPersistenceError,
                                         DuplicateLayerIdentifiers)
from registry.mappers.extensions import \
    validate_unique_layer_identifiers
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata, LegendUrl,
                                      LayerRemoteMetadata, MetadataContact,
                                      MetadataRelation, ServiceMetadataRecord,
                                      Style, WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.harvest import TemporaryMdMetadataFile
from registry.models.security import WebMapServiceAuthentication
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.settings import REGISTRATION_REQUEST_TIMEOUT_SECONDS
from registry.tasks.service import build_ogc_service, collect_reference
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse, WorkerRunMixin


def side_effect(request, *args, **kwargs):
    if request.url == 'https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0.xml')))
    elif request.url == 'https://example.com/wms-legendurl-without-size?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0_legendurl_without_size.xml')))
    elif request.url == 'https://example.com/wms-duplicate-layer-names?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0_duplicate_layer_names.xml')))
    elif request.url == 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_FF':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RBSN_FF.xml')))
    elif request.url == 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_RH':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RBSN_RH.xml')))
    elif request.url == 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_RR':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RBSN_RR.xml')))
    elif request.url == 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_T2m':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RBSN_T2m.xml')))
    elif request.url == 'https://registry.gdi-de.org/id/de.bund.dwd/de.dwd.geoserver.fach.RBSN_VPGB':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RBSN_VPGB.xml')))
    elif request.url == 'https://gdk.gdi-de.org/gdi-de/srv/eng/csw?Service=CSW&Request=GetRecordById&Version=2.0.2&outputSchema=http://www.isotc211.org/2005/gmd&elementSetName=full&id=de.dwd.geoserver.fach.RADOLAN-W4':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/RADOLAN-W4.xml')))
    elif request.url == 'https://example.com/wms-metadata':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/wms-service-metadata.xml')))
    elif request.url == 'https://geodienste.hamburg.de/HH_WFS_Bezirksradrouten_Hamburg_Nord?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wfs/hamburg_1.1.0.xml')))
    elif request.url == 'https://maps.dwd.de/geoserver/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wfs/2.0.0.xml')))
    elif request.url == 'https://example.com/wfs-metadata':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/wms-service-metadata.xml')))


class BuildOgcServiceTaskTest(TransactionTestCase):

    def setUp(self):
        self.http_request = {
            "path": "http://example.de",
            "method": "GET",
            "content_type": "application/vnd.api+json",
            "data": {},
            "user_pk": "af7aaeff-ce21-4e35-af4a-dd2caec92f0f",
        }

        self.background_process = BackgroundProcess.objects.create(
            phase="", process_type="registering", description="")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.tasks.service.Session.send", side_effect=side_effect)
    def test_success_without_service_auth(self, mock_send):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""
        task = build_ogc_service.delay(get_capabilities_url='https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                       collect_metadata_records=False,
                                       service_auth_pk=None,
                                       http_request=self.http_request,
                                       background_process_pk=self.background_process.pk,
                                       **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        db_service = WebMapService.objects.all()[:1][0]

        expected_result = {
            "data": {
                "type": "WebMapService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:wms-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=task.result, d2=expected_result,
                             msg="Task result does not match expection.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_success_with_service_auth(self, mock_send):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""
        auth = WebMapServiceAuthentication.objects.create(
            username="user", password="password", auth_type=AuthTypeEnum.BASIC.value)

        result = build_ogc_service.delay(get_capabilities_url='https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                         collect_metadata_records=False,
                                         service_auth_pk=auth.pk,
                                         http_request=self.http_request,
                                         background_process_pk=self.background_process.pk,
                                         **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        db_service = WebMapService.objects.all()[:1][0]

        expected_result = {
            "data": {
                "type": "WebMapService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:wms-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")

        self.assertEqual(
            db_service.version,
            OGCServiceVersionEnum.V_1_3_0.value
        )

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_success_with_collect_metadata_true(self, mock_send):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""

        result = build_ogc_service.delay(get_capabilities_url='https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                         collect_metadata_records=True,
                                         service_auth_pk=None,
                                         http_request=self.http_request,
                                         background_process_pk=self.background_process.pk,
                                         **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        db_service = WebMapService.objects.all()[:1][0]
        service_count = ServiceMetadataRecord.objects.count()
        self.assertEqual(1, service_count)
        dataset_count = DatasetMetadataRecord.objects.count()
        self.assertEqual(6, dataset_count)
        self.background_process.refresh_from_db()
        self.assertEqual(self.background_process.status, ProcessStatusEnum.COMPLETED)
        self.assertEqual(self.background_process.related_id, db_service.pk)
        self.assertGreater(self.background_process.total_steps, 0)
        # group_result = GroupResult.objects.latest('date_created')

        expected_result = {
            "data": {
                "type": "WebMapService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:wms-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_success_with_legendurl_without_size(self, mock_send):
        """A WMS whose ``LegendURL`` elements omit the optional ``width`` and
        ``height`` attributes registers instead of dying on the NOT NULL
        columns of registry_legendurl (#1201).
        """
        result = build_ogc_service.delay(get_capabilities_url='https://example.com/wms-legendurl-without-size?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                         collect_metadata_records=False,
                                         service_auth_pk=None,
                                         http_request=self.http_request,
                                         background_process_pk=self.background_process.pk,
                                         **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        db_service = WebMapService.objects.all()[:1][0]

        legend_urls = LegendUrl.objects.filter(
            style__layer__service=db_service)
        self.assertTrue(
            legend_urls.exists(),
            msg="The styles of the document lost their legend url.")
        self.assertFalse(
            legend_urls.filter(height__isnull=False).exists(),
            msg="A legend url without width/height stored an invented height.")
        self.assertFalse(
            legend_urls.filter(width__isnull=False).exists(),
            msg="A legend url without width/height stored an invented width.")

        self.background_process.refresh_from_db()
        self.assertEqual(self.background_process.status,
                         ProcessStatusEnum.COMPLETED)

        expected_result = {
            "data": {
                "type": "WebMapService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:wms-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.tasks.service.PersistenceHandler.persist_all", side_effect=IntegrityError(
        'null value in column "height" of relation "registry_legendurl" violates not-null constraint\n'
        'DETAIL: Failing row contains (639, , null, null, 5, 639).'))
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_integrity_error_on_persist_surfaces_as_clean_task_error(self, mock_send, mock_persist):
        """A database which refuses a row of the document is reported as the
        defined failure of the build, without the psycopg constraint dump in
        the phase of the background process (#1201).
        """
        with self.assertRaises(CapabilitiesPersistenceError) as ctx:
            build_ogc_service.delay(get_capabilities_url='https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                    collect_metadata_records=False,
                                    service_auth_pk=None,
                                    http_request=self.http_request,
                                    background_process_pk=self.background_process.pk,
                                    **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        self.assertEqual(
            str(ctx.exception),
            'The capabilities document could not be persisted: null value in '
            'column "height" of relation "registry_legendurl" violates '
            'not-null constraint')
        self.assertIsInstance(ctx.exception.__cause__, IntegrityError)

        self.background_process.refresh_from_db()
        self.assertNotIn('DETAIL', self.background_process.phase)

        # celery's eager path re-raises without running the failure
        # handlers of the worker (celery/app/trace.py raises before
        # handle_failure), so on_failure runs here the way the worker
        # runs it - it composes the final text of the activity popover
        build_ogc_service.on_failure(ctx.exception, 'task-id', (), {}, None)

        self.background_process.refresh_from_db()
        self.assertEqual(
            self.background_process.status, ProcessStatusEnum.FAILED)
        self.assertEqual(
            self.background_process.phase,
            'An error occurred: The capabilities document could not be '
            'persisted: null value in column "height" of relation '
            '"registry_legendurl" violates not-null constraint')

        self.assertFalse(
            WebMapService.objects.exists(),
            msg="The failed build left the service row behind.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_duplicate_layer_names_fail_with_a_clean_error(self, mock_send):
        """A capabilities document which re-lists layer names fails the
        build naming the duplicated identifiers, not the constraint dump of
        ``unique_identifer_per_wms`` (#1200).

        The document re-lists node1.1.1 under three parents and node1.3.1
        under two, like the swisstopo BGDI and IGN geopf WMS, and carries
        two unnamed group layers whose NULL identifiers may not be read as
        duplicates of each other.
        """
        with self.assertRaises(DuplicateLayerIdentifiers) as ctx:
            build_ogc_service.delay(get_capabilities_url='https://example.com/wms-duplicate-layer-names?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                                    collect_metadata_records=False,
                                    service_auth_pk=None,
                                    http_request=self.http_request,
                                    background_process_pk=self.background_process.pk,
                                    **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        self.assertEqual(
            list(ctx.exception.duplicated), ['node1.1.1', 'node1.3.1'],
            msg="only the re-listed identifiers are named.")

        message = str(ctx.exception)
        self.assertIn("'node1.1.1'", message)
        self.assertIn("'node1.3.1'", message)
        self.assertNotIn(
            "'node1.2'", message,
            msg="a name the document lists once appears in the error.")
        self.assertNotIn('unique_identifer_per_wms', message)
        self.assertNotIn('duplicate key', message)

        self.background_process.refresh_from_db()
        self.assertIn('duplicate layer names', self.background_process.phase)

        # celery's eager path re-raises without running the failure
        # handlers of the worker, so on_failure runs here the way the
        # worker runs it - it composes the final text of the activity
        # popover
        build_ogc_service.on_failure(ctx.exception, 'task-id', (), {}, None)

        self.background_process.refresh_from_db()
        self.assertEqual(
            self.background_process.status, ProcessStatusEnum.FAILED)
        self.assertEqual(
            self.background_process.phase,
            f'An error occurred: {message}')

        self.assertFalse(
            WebMapService.objects.exists(),
            msg="The failed build left the service row behind.")
        self.assertFalse(
            Layer.objects.exists(),
            msg="The failed build left layers behind.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_unmapped_capabilities_version_reports_clear_error(self, mock_send):
        """A document no mapping config handles names its version (#1210).

        The WFS 1.1.0 document of the reproduction carries a namespace the
        WFS 2.0.0 config finds nothing in, so the mapping produced no service
        and ``data[0]`` died as an IndexError. The failure the polling client
        reads must say what was refused.
        """
        with self.assertRaises(ValueError) as ctx:
            build_ogc_service.delay(
                get_capabilities_url='https://geodienste.hamburg.de/HH_WFS_Bezirksradrouten_Hamburg_Nord?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities',
                collect_metadata_records=False,
                service_auth_pk=None,
                http_request=self.http_request,
                background_process_pk=self.background_process.pk,
                **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        self.assertNotIsInstance(
            ctx.exception, IndexError,
            msg="the task still lets the empty mapping crash on data[0]")
        self.assertIn("could not be mapped", str(ctx.exception))
        self.assertIn("1.1.0", str(ctx.exception))

        self.background_process.refresh_from_db()
        self.assertIn("1.1.0", self.background_process.phase)
        self.assertEqual(
            WebFeatureService.objects.count(), 0,
            msg="no service may be written for an unmapped document")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', return_value=MockResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content='no xml'))
    def test_the_capabilities_request_waits_for_the_shared_timeout(self, mock_send):
        """The document of the registration is asked with the shared bound.

        The same value bounds the fetch of every metadata reference behind this
        document (#1260): one host answers both requests within one
        registration, so a host which cannot answer a plain GET within this
        window is a host the registration must not occupy a worker for.
        """
        with self.assertRaises(etree.XMLSyntaxError):
            build_ogc_service.delay(
                get_capabilities_url='https://maps.dwd.de/geoserver/wms'
                '?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities',
                collect_metadata_records=False,
                service_auth_pk=None,
                http_request=self.http_request,
                background_process_pk=self.background_process.pk,
                **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        self.assertEqual(
            mock_send.call_args.kwargs['timeout'],
            REGISTRATION_REQUEST_TIMEOUT_SECONDS)


class CapabilitiesPersistenceErrorTest(TestCase):
    """The message the error class answers is what the activity popover of a
    database refusal answers (#1201; the `TaskResult` show which also answered
    it is retired with the resource, #1180)
    """

    def test_names_the_refused_column_of_a_real_violation(self):
        """Out of a violation the database really raised, the message names
        the column and the relation it refused and leaves the DETAIL dump
        with the driver error.
        """
        with self.assertRaises(IntegrityError) as ctx:
            with transaction.atomic():
                # a Style without its layer violates the NOT NULL column
                # layer_id of registry_style
                Style(name="default", title="default").save()

        message = str(CapabilitiesPersistenceError(ctx.exception))

        self.assertIn('registry_style', message)
        self.assertIn('layer_id', message)
        self.assertNotIn('DETAIL', message)

    def test_falls_back_to_the_first_line_of_the_error(self):
        """Without a driver diagnostic behind the error, the message keeps
        the primary line of its text and drops the appended DETAIL blob.
        """
        error = IntegrityError(
            'null value in column "height" of relation "registry_legendurl" '
            'violates not-null constraint\n'
            'DETAIL: Failing row contains (639, , null, null, 5, 639).')

        self.assertEqual(
            str(CapabilitiesPersistenceError(error)),
            'The capabilities document could not be persisted: null value in '
            'column "height" of relation "registry_legendurl" violates '
            'not-null constraint')


class DuplicateLayerIdentifiersTest(TestCase):
    """The message the error class answers is what the activity popover and
    the TaskResult show of a document with duplicated layer names (#1200).
    """

    def test_names_at_most_five_duplicates_and_counts_the_rest(self):
        # swisstopo BGDI re-lists 169 names; the message stays readable
        duplicated = [f"alpha.{i}" for i in range(7)]

        message = str(DuplicateLayerIdentifiers(duplicated))

        for name in duplicated[:DuplicateLayerIdentifiers.MAX_NAMED_IDENTIFIERS]:
            self.assertIn(f"'{name}'", message)
        for name in duplicated[DuplicateLayerIdentifiers.MAX_NAMED_IDENTIFIERS:]:
            self.assertNotIn(f"'{name}'", message)
        self.assertIn('and 2 more', message)

    def test_stays_inside_the_phase_of_the_background_process(self):
        # on_failure composes "An error occurred: {message}" into the phase,
        # a column of BackgroundProcess.phase.max_length; the sentence must
        # arrive complete, not cut off mid-identifier
        budget = (BackgroundProcess._meta.get_field('phase').max_length
                  - len('An error occurred: '))

        duplicated = [f"{i}.{'x' * 500}" for i in range(100)]

        message = str(DuplicateLayerIdentifiers(duplicated))

        self.assertLessEqual(len(f'An error occurred: {message}'), budget)
        self.assertIn('…', message, msg="long identifiers are not dumped whole.")
        self.assertIn('and 95 more', message)


class StubCacheMapper:
    """Just the call the pre-save hook reads: the parsed instances."""

    def __init__(self, instances):
        self.instances = instances

    def read_all_from_cache(self):
        return {f"/stub/Element[{i}]": inst
                for i, inst in enumerate(self.instances)}


class ValidateUniqueLayerIdentifiersTest(TestCase):
    """The hook refuses the document before a single row is written (#1200).
    """

    def test_repeated_identifier_is_refused(self):
        mapper = StubCacheMapper([
            Layer(identifier='a'),
            Layer(identifier='b'),
            Layer(identifier='a'),
        ])

        with self.assertRaises(DuplicateLayerIdentifiers) as ctx:
            validate_unique_layer_identifiers(mapper)

        self.assertEqual(list(ctx.exception.duplicated), ['a'])

    def test_layers_without_a_name_are_not_duplicates_of_each_other(self):
        # a grouping node without <Name> carries a NULL identifier, which
        # the unique constraint of registry_layer tolerates repeatedly
        mapper = StubCacheMapper([
            Layer(identifier=None),
            Layer(identifier=None),
            Layer(identifier='a'),
        ])

        self.assertIsNone(validate_unique_layer_identifiers(mapper))


class CollectionStepAccountingTest(WorkerRunMixin, TransactionTestCase):
    """Each metadata reference of a collection reports exactly one step (#1258).

    The step report of the collecting task used to sit only behind the
    ``except`` branches, which the success path left by returning: a healthy
    run sat at 0 % until the chord completed and jumped to done. The process
    here is the one the registration work queue of #1263 leaves behind: a
    sealed plan of four references, and these tests answer ``collect_reference``
    over it once per row - with all references succeeding, all failing and
    half failing - and assert the accounting closes.

    The deliveries go through celery's tracer because the reports into the
    process run in the same signal handlers a worker pays; the delivery
    which exhausted its retry policy is the one which carries
    ``max_retries`` - an attempt below that number releases its row and
    decides nothing (the transport contract of #1260, moved onto the row).

    A TransactionTestCase because the tasks are the ones of the deployment:
    its celery signal handlers close the database connection around a task,
    which is only survivable outside the atomic block of a TestCase.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json"]

    # the references are advertised AT THE SERVICE, so their documents are
    # service records - the relation table only permits a service record to
    # couple a WMS (dataset records couple layers and feature types)
    SERVICE = (Path(__file__).parent.parent.parent
               / 'test_data/iso_metadata/service.xml')

    def setUp(self):
        super().setUp()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

        contact = MetadataContact.objects.create(name='collection contact')
        service = WebMapService.objects.create(
            title='Collection progress service', version=130, origin=1,
            service_url='https://collection.example.org/wms',
            metadata_contact=contact, service_contact=contact)
        self.process = BackgroundProcess.objects.create(
            process_type='registering',
            description='',
            phase='collect_metadata_records',
            total_steps=4,
            references_total=4, references_stored=0, references_failed=0,
            references_skipped=0,
            references_plan_sealed=True)
        # the four work rows the sealed plan left behind, one per advertised
        # link; the rows are the references - no RemoteMetadata row is read
        # while they are worked (#1263)
        self.rows = TemporaryMdMetadataFile.objects.bulk_create([
            TemporaryMdMetadataFile(
                background_process_id=self.process.pk,
                reference_key=TemporaryMdMetadataFile.build_reference_key(
                    service, f'https://collection.example.org/md/{i}'),
                requested_url=f'https://collection.example.org/md/{i}',
                described_wms=service,
                described_display=service.title,
                request_id=timezone.now())
            for i in range(4)])

    def _collect(self, failing=()):
        """Answer the task of the queue once per row, as a worker would.

        The boundary is the remote endpoint: the HTTP call inside
        ``fetch_metadata_document`` answers the dataset document on success
        and the ``ConnectionError`` of a refused connection otherwise - the
        failing rows are delivered carrying ``max_retries``, which is how a
        worker hands over the last attempt its retry policy permits.
        """
        failing_urls = {self.rows[i].requested_url for i in failing}

        def send(request, *args, **kwargs):
            if request.url in failing_urls:
                raise RequestsConnectionError('connection refused')
            return MockResponse(status_code=200, content=self.SERVICE)

        from celery.app.trace import build_tracer
        collect_reference._backend = self.app.backend
        self.addCleanup(
            lambda: collect_reference.__dict__.pop('_backend', None))
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)

        with patch.object(Session, 'send', side_effect=send):
            for index, row in enumerate(self.rows):
                retries = (collect_reference.max_retries
                           if index in failing else 0)
                # the fan-out addresses work through kwargs - the process
                # report handlers read the process exactly from there
                trace(collect_reference.name, (), {
                    'background_process_pk': self.process.pk,
                    'temporary_md_metadata_file_id': row.pk,
                }, {'id': f"accounting-{index}", 'retries': retries})

        return BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)

    @override_settings(BROKER_BACKEND='memory')
    def test_all_successes_count_their_steps(self):
        """The defect: the success path returned past the only step report,
        so a healthy collection never moved ``done_steps`` at all."""
        process = self._collect()

        self.assertEqual(process.done_steps, len(self.rows))
        self.assertEqual(process.total_steps, len(self.rows))
        self.assertEqual(
            process.progress, 100,
            msg="the progress of a completed collection shows without "
                "the chord body having marked the process COMPLETED")
        # the stored outcome of each reference moved the summary once (#1259,
        # now exactly once per reference because the row is the permit #1263)
        self.assertEqual(process.references_stored, len(self.rows))
        self.assertEqual(process.references_failed, 0)

    @override_settings(BROKER_BACKEND='memory')
    def test_all_failures_count_their_steps(self):
        process = self._collect(failing=range(len(self.rows)))

        self.assertEqual(process.done_steps, len(self.rows))
        self.assertEqual(process.progress, 100)
        self.assertEqual(process.references_failed, len(self.rows))
        self.assertEqual(process.references_stored, 0)
        # the refused fetches are visible on the process, not only counted
        self.assertEqual(
            BackgroundProcessLog.objects.filter(
                background_process_id=self.process.pk).count(),
            len(self.rows))
        # and each failure kept its row, retryable, with its kind (#1263)
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(
                background_process_id=self.process.pk,
                state=ReferenceWorkStateEnum.FAILED.value).count(),
            len(self.rows))

    @override_settings(BROKER_BACKEND='memory')
    def test_half_failures_count_their_steps(self):
        process = self._collect(failing=(1, 3))

        self.assertEqual(process.done_steps, len(self.rows))
        self.assertEqual(process.progress, 100)
        self.assertEqual(process.references_stored, 2)
        self.assertEqual(process.references_failed, 2)

    @override_settings(BROKER_BACKEND='memory')
    def test_an_attempt_below_the_last_one_decides_nothing(self):
        """A transient failure is an attempt, not an outcome (#1260, #1263).

        The delivery which is not the last the policy permits releases its
        row back to PENDING and decides nothing: no warning is written, the
        summary does not move and the row stays claimable by the retried
        delivery - which is what separates an attempt from a decision.
        """
        row = self.rows[0]

        def send(request, *args, **kwargs):
            raise RequestsConnectionError('connection refused')

        from celery.app.trace import build_tracer
        collect_reference._backend = self.app.backend
        trace = build_tracer(
            collect_reference.name, collect_reference, app=self.app)
        with patch.object(Session, 'send', side_effect=send):
            trace(collect_reference.name, (), {
                'background_process_pk': self.process.pk,
                'temporary_md_metadata_file_id': row.pk,
            }, {'id': 'accounting-retry', 'retries': 0})

        row.refresh_from_db()
        self.assertEqual(
            row.state, ReferenceWorkStateEnum.PENDING.value,
            msg="the released row must be claimable again")
        self.assertEqual(row.attempt_count, 1)
        self.assertEqual(
            BackgroundProcessLog.objects.filter(
                background_process_id=self.process.pk).count(), 0)
        process = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)
        self.assertEqual(process.done_steps, 0)
        self.assertEqual(process.references_failed, 0)


class WfsFeatureTypeMetadataFanOutTest(TransactionTestCase):
    """The fan-out of ``build_ogc_service`` must collect one record per
    reference it counted as a step — including the feature type references
    of a WFS, which a duplicated ``case`` pattern in the old class-name
    matching of the fetch task dropped silently: the run ended completed
    with counted steps, no record and no log line (#1257).

    Since #1263 the fan-out is the sealed work plan: one row per advertised
    reference with the described element in a concrete column, so no kind
    can be missed by a lookup the task performs at delivery time.

    The capabilities fixture is a WFS carrying one service level INSPIRE
    reference and a distinct ``MetadataURL`` on each of its five feature
    types: before the fix only the service level reference was collected
    while the five feature type steps were skipped without a trace.
    """

    def setUp(self):
        self.http_request = {
            "path": "http://example.de",
            "method": "GET",
            "content_type": "application/vnd.api+json",
            "data": {},
            "user_pk": "af7aaeff-ce21-4e35-af4a-dd2caec92f0f",
        }

        self.background_process = BackgroundProcess.objects.create(
            phase="", process_type="registering", description="")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_feature_type_references_are_collected_by_the_fan_out(self, mock_send):
        build_ogc_service.delay(
            get_capabilities_url='https://maps.dwd.de/geoserver/wfs?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities',
            collect_metadata_records=True,
            service_auth_pk=None,
            http_request=self.http_request,
            background_process_pk=self.background_process.pk,
            **{'user_pk': 'af7aaeff-ce21-4e35-af4a-dd2caec92f0f'})

        service = WebFeatureService.objects.get()

        # the persisted document leaves one reference row per metadata link:
        # one service level and five feature type ones
        self.assertEqual(
            WebFeatureServiceRemoteMetadata.objects.filter(
                describes=service).count(), 1)
        self.assertEqual(
            FeatureTypeRemoteMetadata.objects.filter(
                describes__service=service).count(),
            5,
            msg="the capabilities references did not survive persistence.")

        # one record created per reference...
        self.assertEqual(
            ServiceMetadataRecord.objects.count(), 1,
            msg="the service level reference was not collected.")
        self.assertEqual(
            DatasetMetadataRecord.objects.count(),
            5,
            msg="the feature type references were dropped instead of "
                "collected into records (#1257).")
        # ... and one relation row per described element
        self.assertEqual(
            MetadataRelation.objects.filter(
                wfs=service).count(), 1)
        self.assertEqual(
            MetadataRelation.objects.filter(
                feature_type__service=service).count(),
            5,
            msg="the collected records are not related to every described "
                "feature type.")

        # the step count of the run only counts what was dispatched, and
        # every dispatched step arrived: a skipped reference could make the
        # process report total_steps > 0 with nothing collected
        self.background_process.refresh_from_db()
        self.assertEqual(self.background_process.total_steps, 6)
        self.assertEqual(self.background_process.done_steps,
                         self.background_process.total_steps)
        self.assertEqual(self.background_process.status,
                         ProcessStatusEnum.COMPLETED)
        # and the sealed plan of #1263 answers the same six references it
        # planned, all stored, with every work row consumed by its success
        self.assertTrue(self.background_process.references_plan_sealed)
        self.assertEqual(self.background_process.references_total, 6)
        self.assertEqual(self.background_process.references_stored, 6)
        self.assertEqual(self.background_process.references_failed, 0)
        self.assertEqual(self.background_process.references_skipped, 0)
        self.assertFalse(
            TemporaryMdMetadataFile.objects.filter(
                background_process=self.background_process).exists(),
            msg="a successfully collected reference keeps its work row.")


class CollectReferenceKindTest(TransactionTestCase):
    """``collect_reference`` resolves each described kind of the work row to
    its concrete element: the four reference kinds the registration planning
    produces each fetch, store and import their document and couple the
    record to the element the row names with its one concrete foreign key
    (#1263).

    The class-name matching which silently dropped FeatureType references in
    #1257 does not exist anymore: the work row IS the described element's
    reference, and a row whose element vanished still names it through its
    display snapshot.

    The service and element rows come from the plain fixtures; the work rows
    are built per test next to the ``RemoteMetadata`` row the planning would
    have read, because the reference kinds belong to different described
    elements than the fixtures relate.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    # the document side_effect answers for the registry links: a dataset
    RBSN_T2M = ('https://registry.gdi-de.org/id/de.bund.dwd/'
                'de.dwd.geoserver.fach.RBSN_T2m')

    def setUp(self):
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        settings = override_settings(MEDIA_ROOT=media.name)
        settings.enable()
        self.addCleanup(settings.disable)

        self.http_request = {
            "path": "http://example.de",
            "method": "GET",
            "content_type": "application/vnd.api+json",
            "data": {},
            "user_pk": "af7aaeff-ce21-4e35-af4a-dd2caec92f0f",
        }
        self.wms = WebMapService.objects.first()
        self.layer = Layer.objects.filter(service=self.wms).first()
        self.wfs = WebFeatureService.objects.first()
        self.feature_type = FeatureType.objects.filter(service=self.wfs).first()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def _collect(self, remote_metadata):
        """Run the queue's consumer for one reference the way its fan-out
        runs it: one sealed row of a planned process, addressed by pk."""
        process = BackgroundProcess.objects.create(
            phase="", process_type="registering", description="",
            total_steps=1, references_total=1, references_stored=0,
            references_failed=0, references_skipped=0,
            references_plan_sealed=True)
        described = remote_metadata.describes
        row = TemporaryMdMetadataFile(
            background_process_id=process.pk,
            reference_key=TemporaryMdMetadataFile.build_reference_key(
                described, remote_metadata.link),
            requested_url=remote_metadata.link,
            described_display=(getattr(described, "title", "") or ""),
            request_id=timezone.now())
        if isinstance(described, WebMapService):
            row.described_wms = described
        elif isinstance(described, WebFeatureService):
            row.described_wfs = described
        elif isinstance(described, Layer):
            row.described_layer = described
        elif isinstance(described, FeatureType):
            row.described_featuretype = described
        else:
            self.fail(f"no work-row column for {described.__class__}")
        # bulk_create, not save: a saved registration row schedules its own
        # consumer on_commit, which the test would race against
        TemporaryMdMetadataFile.objects.bulk_create([row])

        task_result = collect_reference.delay(
            background_process_pk=process.pk,
            temporary_md_metadata_file_id=row.pk,
            http_request=self.http_request)
        process.refresh_from_db()
        return process, task_result.result, row.pk

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_web_map_service_reference_couples_its_service(self, mock_send):
        row = WebMapServiceRemoteMetadata.objects.create(
            link='https://example.com/wms-metadata', describes=self.wms)

        service_before = ServiceMetadataRecord.objects.count()
        process, result, _ = self._collect(row)

        self.assertEqual(
            ServiceMetadataRecord.objects.count(), service_before + 1,
            msg="the service reference did not become its record.")
        record = ServiceMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.wms, self.wms)
        self.assertIsNone(relation.layer)
        # the decided reference is consumed: row gone, stored once (#1263)
        self.assertFalse(TemporaryMdMetadataFile.objects.exists())
        self.assertEqual(process.references_stored, 1)
        self.assertEqual(process.done_steps, 1)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_layer_reference_couples_its_layer(self, mock_send):
        row = LayerRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.layer)

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result, _ = self._collect(row)

        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before + 1,
            msg="the layer reference did not become its record.")
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.layer, self.layer)
        self.assertIsNone(relation.feature_type)
        self.assertFalse(TemporaryMdMetadataFile.objects.exists())

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_web_feature_service_reference_couples_its_service(self, mock_send):
        row = WebFeatureServiceRemoteMetadata.objects.create(
            link='https://example.com/wfs-metadata', describes=self.wfs)

        service_before = ServiceMetadataRecord.objects.count()
        process, result, _ = self._collect(row)

        self.assertEqual(
            ServiceMetadataRecord.objects.count(), service_before + 1,
            msg="the service reference did not become its record: "
                f"{result}")
        record = ServiceMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.wfs, self.wfs)
        self.assertIsNone(relation.feature_type)
        self.assertFalse(TemporaryMdMetadataFile.objects.exists())

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_feature_type_reference_couples_its_feature_type(self, mock_send):
        # the regression of #1257, now structurally answered: the work row
        # names the feature type with a concrete column, so no kind can be
        # dropped by a match which forgot it
        row = FeatureTypeRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.feature_type)

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result, _ = self._collect(row)

        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before + 1,
            msg="the feature type reference was dropped silently (#1257).")
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.feature_type, self.feature_type)
        self.assertIsNone(relation.layer)
        self.assertFalse(TemporaryMdMetadataFile.objects.exists())

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_a_replayed_delivery_of_a_collected_reference_is_a_no_op(
            self, mock_send):
        """The proof of success is the absent row (#1263).

        The second delivery of the same task message - celery's
        at-least-once delivery, a redriven queue - finds no row and does
        nothing: no second record, no counter movement. This is the whole
        idempotency contract of the queue, answered without any success
        marker to consult.
        """
        row = WebMapServiceRemoteMetadata.objects.create(
            link='https://example.com/wms-metadata', describes=self.wms)

        _, first, work_pk = self._collect(row)
        record = ServiceMetadataRecord.objects.get()
        process = BackgroundProcess.objects.get(
            references_plan_sealed=True)

        replay = collect_reference.delay(
            background_process_pk=process.pk,
            temporary_md_metadata_file_id=work_pk)
        self.assertIsNone(
            replay.result,
            msg="the replay of a consumed reference answers no outcome")

        self.assertEqual(ServiceMetadataRecord.objects.count(), 1,
                         msg="the replay imported a second record.")
        self.assertEqual(MetadataRelation.objects.count(), 1,
                         msg="the replay coupled a second relation.")
        process.refresh_from_db()
        self.assertEqual(process.references_stored, 1,
                         msg="the replay moved the counters of the run.")
        self.assertEqual(process.done_steps, 1)
        self.assertEqual(first["data"]["id"], str(record.pk))
