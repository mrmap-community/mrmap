from pathlib import Path
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.service import AuthTypeEnum, OGCServiceVersionEnum
from registry.exceptions.service import (CapabilitiesPersistenceError,
                                         DuplicateLayerIdentifiers)
from registry.mappers.extensions import \
    validate_unique_layer_identifiers
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata, LegendUrl,
                                      LayerRemoteMetadata, MetadataRelation,
                                      ServiceMetadataRecord, Style,
                                      WebFeatureServiceRemoteMetadata,
                                      WebMapServiceRemoteMetadata)
from registry.models.security import WebMapServiceAuthentication
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from registry.tasks.service import (build_ogc_service,
                                    fetch_remote_metadata_xml)
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse


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


class WfsFeatureTypeMetadataFanOutTest(TransactionTestCase):
    """The fan-out of ``build_ogc_service`` must collect one record per
    reference it counted as a step — including the feature type references
    of a WFS, which a duplicated ``case`` pattern in
    ``fetch_remote_metadata_xml`` dropped silently: the run ended completed
    with counted steps, no record and no log line (#1257).

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


class FetchRemoteMetadataXmlKindTest(TransactionTestCase):
    """``fetch_remote_metadata_xml`` resolves the class name it is handed to
    its own ``RemoteMetadata`` model: the four reference kinds the
    registration fan-out produces each fetch and persist their document and
    relate the record to the element they describe. A name the match does
    not know is a failure reported on the process, not a silently skipped
    step (#1257).

    The service and element rows come from the plain fixtures; the
    ``RemoteMetadata`` rows are created per test, because the reference
    kinds belong to different described elements than the fixtures relate.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    # the document side_effect answers for the registry links: a dataset
    RBSN_T2M = ('https://registry.gdi-de.org/id/de.bund.dwd/'
                'de.dwd.geoserver.fach.RBSN_T2m')

    def setUp(self):
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
    def _fetch(self, row, class_name=None):
        """Run the task for one reference row the way the fan-out runs it."""
        process = BackgroundProcess.objects.create(
            phase="", process_type="registering", description="")
        task_result = fetch_remote_metadata_xml.delay(
            row.pk,
            class_name or row.__class__.__name__,
            http_request=self.http_request,
            background_process_pk=process.pk)
        process.refresh_from_db()
        return process, task_result.result

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_web_map_service_reference_resolves_to_its_model(self, mock_send):
        row = WebMapServiceRemoteMetadata.objects.create(
            link='https://example.com/wms-metadata', describes=self.wms)

        service_before = ServiceMetadataRecord.objects.count()
        process, result = self._fetch(row)

        self.assertEqual(
            ServiceMetadataRecord.objects.count(), service_before + 1,
            msg="the service reference did not become its record.")
        record = ServiceMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.wms, self.wms)
        self.assertIsNone(relation.layer)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_layer_reference_resolves_to_its_model(self, mock_send):
        row = LayerRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.layer)

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result = self._fetch(row)

        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before + 1,
            msg="the layer reference did not become its record.")
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.layer, self.layer)
        self.assertIsNone(relation.feature_type)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_web_feature_service_reference_resolves_to_its_model(self, mock_send):
        row = WebFeatureServiceRemoteMetadata.objects.create(
            link='https://example.com/wfs-metadata', describes=self.wfs)

        service_before = ServiceMetadataRecord.objects.count()
        process, result = self._fetch(row)

        self.assertEqual(
            ServiceMetadataRecord.objects.count(), service_before + 1,
            msg="the service reference did not become its record: "
                f"{result}")
        record = ServiceMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.wfs, self.wfs)
        self.assertIsNone(relation.feature_type)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_feature_type_reference_resolves_to_its_model(self, mock_send):
        # the regression of #1257: every LayerRemoteMetadata name was caught
        # by the first branch, so this kind never reached its own model and
        # the task returned None without a log line
        row = FeatureTypeRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.feature_type)

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result = self._fetch(row)

        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before + 1,
            msg="the feature type reference was dropped silently (#1257).")
        record = DatasetMetadataRecord.objects.get()
        self.assertEqual(result["data"]["id"], str(record.pk))
        relation = MetadataRelation.objects.get()
        self.assertEqual(relation.feature_type, self.feature_type)
        self.assertIsNone(relation.layer)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_unknown_class_name_ends_in_a_logged_failure(self, mock_send):
        row = FeatureTypeRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.feature_type)

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result = self._fetch(
            row, class_name="CatalogueServiceRemoteMetadata")

        self.assertIsNone(
            result,
            msg="the failure of the unknown kind must not answer a record.")
        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before,
            msg="a name the match does not know must not collect anything.")
        self.assertEqual(MetadataRelation.objects.count(), 0)
        self.assertTrue(
            process.logs.filter(
                log_type=LogTypeEnum.WARNING,
                description__contains="CatalogueServiceRemoteMetadata").exists(),
            msg="the unknown kind left no warning on the process (#1257).")
        # the step is reported done like every other handled outcome of the
        # task, so the process its chord finishes on keeps its counts
        self.assertEqual(process.done_steps, 1)
        self.assertNotEqual(process.status, ProcessStatusEnum.FAILED)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', side_effect=side_effect)
    def test_id_of_another_kind_ends_in_a_logged_failure(self, mock_send):
        row = LayerRemoteMetadata.objects.create(
            link=self.RBSN_T2M, describes=self.layer)
        self.assertFalse(FeatureTypeRemoteMetadata.objects.exists())

        dataset_before = DatasetMetadataRecord.objects.count()
        process, result = self._fetch(
            row, class_name="FeatureTypeRemoteMetadata")

        self.assertIsNone(
            result,
            msg="the unresolvable reference must not answer a record.")
        self.assertEqual(
            DatasetMetadataRecord.objects.count(), dataset_before,
            msg="a name of the wrong kind must not resolve to a row.")
        self.assertTrue(
            process.logs.filter(log_type=LogTypeEnum.WARNING).exists(),
            msg="the unresolvable reference left no warning on the process.")
        self.assertEqual(process.done_steps, 1)
        self.assertNotEqual(process.status, ProcessStatusEnum.FAILED)
