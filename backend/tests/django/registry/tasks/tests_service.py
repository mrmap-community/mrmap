from pathlib import Path
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.service import AuthTypeEnum, OGCServiceVersionEnum
from registry.exceptions.service import CapabilitiesPersistenceError
from registry.models.metadata import (DatasetMetadataRecord, LegendUrl,
                                      ServiceMetadataRecord, Style)
from registry.models.security import WebMapServiceAuthentication
from registry.models.service import WebFeatureService, WebMapService
from registry.tasks.service import build_ogc_service
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, *args, **kwargs):
    if request.url == 'https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0.xml')))
    elif request.url == 'https://example.com/wms-legendurl-without-size?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0_legendurl_without_size.xml')))
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
    """The message the error class answers is what the activity popover and
    the TaskResult show of a database refusal (#1201).
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
