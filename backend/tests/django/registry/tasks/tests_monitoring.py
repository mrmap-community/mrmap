from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings
from django_celery_beat.models import IntervalSchedule
from MrMap.celery import app
from MrMap.settings import BASE_DIR
from registry.models.monitoring import (GetCapabilitiesProbe,
                                        GetCapabilitiesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import WebMapService
from registry.ows_lib.client.core import OgcClient
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, timeout):
    if "ServiceException" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/wms_service_exception.xml')))

    elif "GetCapabilities" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/dwd_wms_1.3.0.xml')))
    elif "GetMap" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/karte_rp.fcgi.png')))
    elif "GetFeatureInfo" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),

                                       '../../test_data/wms/feature_info.xml')))
    else:
        print(request.url)


def setup_capabilitites_file(service_exception_url=False):
    wms: WebMapService = WebMapService.objects.get(
        pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

    if service_exception_url:
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.1.1_exception.xml", mode="rb")
    else:
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.1.1.xml", mode="rb")

    wms.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read(), content_type="application/xml")

    wms.save()


class WmsGetCapabilitiesMonitoringTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        )
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.monitoring_setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms,
            interval=self.interval
        )

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_run_with_only_get_capabilities_probe(self, mocked_send_request):
        setup_capabilitites_file()
        GetCapabilitiesProbe.objects.create(setting=self.monitoring_setting)

        run = WebMapServiceMonitoringRun.objects.create(
            setting=self.monitoring_setting,
        )

        self.assertEqual(GetCapabilitiesProbeResult.objects.filter(run=run).count(), 1)
        self.assertFalse(GetMapProbeResult.objects.filter(run=run).exists())
        mocked_send_request.assert_called_once()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_run_with_only_get_map_probe(self, mocked_send_request):
        setup_capabilitites_file()
        probe = GetMapProbe.objects.create(setting=self.monitoring_setting)
        probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun.objects.create(
            setting=self.monitoring_setting,
        )

        self.assertEqual(GetMapProbeResult.objects.filter(run=run).count(), 1)
        self.assertFalse(GetCapabilitiesProbeResult.objects.filter(run=run).exists())
        mocked_send_request.assert_called_once()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_run_wms_monitoring(self, mocked_send_request,  mocked_on_commit):
        setup_capabilitites_file()
        cap_probe = GetCapabilitiesProbe.objects.create(
            setting=self.monitoring_setting,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            setting=self.monitoring_setting,
        )
        map_probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun(setting=self.monitoring_setting)
        run.save()

        self.assertEqual(1, GetCapabilitiesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())
        try:
            get_cap_result = GetCapabilitiesProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_cap_result.check_response_is_valid_xml_success)
            self.assertEqual(
                get_cap_result.check_response_is_valid_xml_message,
                "OK",
            )
            self.assertTrue(
                get_cap_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_not_contain_message,
                "OK"
            )
            self.assertTrue(
                get_cap_result.check_response_does_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_contain_message,
                "OK",
            )

            get_map_result = GetMapProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_map_result.check_response_image_success)
            self.assertEqual(
                get_map_result.check_response_image_message,
                "OK",
            )
            self.assertTrue(
                get_map_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_map_result.check_response_does_not_contain_message,
                "OK",
            )

        except ObjectDoesNotExist:
            self.fail("result was not found.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_run_wms_monitoring_with_service_exceptions(self, mocked_send_request,  mocked_on_commit):
        setup_capabilitites_file(service_exception_url=True)
        cap_probe = GetCapabilitiesProbe.objects.create(
            setting=self.monitoring_setting,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            setting=self.monitoring_setting,
        )
        map_probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun(setting=self.monitoring_setting)
        run.save()

        self.assertEqual(1, GetCapabilitiesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())

        try:
            get_cap_result = GetCapabilitiesProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_cap_result.check_response_is_valid_xml_success)
            self.assertEqual(
                get_cap_result.check_response_is_valid_xml_message,
                "OK",
            )

            self.assertFalse(
                get_cap_result.check_response_does_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_contain_message,
                "Title> is not part of the response. Abstract> is not part of the response. "
            )

            self.assertFalse(
                get_cap_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_not_contain_message,
                "ExceptionReport> is part of the response. ServiceException> is part of the response. ",
            )

            get_map_result = GetMapProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertFalse(
                get_map_result.check_response_image_success)
            self.assertEqual(
                get_map_result.check_response_image_message,
                "Could not create image from response.",
            )
            self.assertFalse(
                get_map_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_map_result.check_response_does_not_contain_message,
                "ExceptionReport> is part of the response. ServiceException> is part of the response. "
            )

        except ObjectDoesNotExist:
            self.fail("result was not found.")


class MonitoringTaskRoutingTest(SimpleTestCase):
    def test_monitoring_tasks_route_to_a_consumed_queue(self):
        task_names = (
            "run_wms_monitoring",
            "run_get_capabilitites_probe_check",
            "run_get_map_probe_check",
            "finish_run",
        )
        for task_name in task_names:
            with self.subTest(task=task_name):
                route = app.amqp.router.route(
                    {}, f"registry.tasks.monitoring.{task_name}",
                )
                self.assertEqual(route["queue"].name, "default")
                self.assertEqual(route["queue"].exchange.name, "default")
                self.assertEqual(route["queue"].routing_key, "default")


class WmsCapabilitiesRequestTest(SimpleTestCase):
    def test_get_capabilities_request_for_supported_wms_versions(self):
        for version in ("1.1.1", "1.3.0"):
            with self.subTest(version=version):
                xml = Path(
                    BASE_DIR, "tests/django/test_data/capabilities/wms",
                    f"{version}.xml",
                ).read_bytes()
                client = OgcClient(capabilities=xml)
                request = client.get_capabilities_request()
                self.assertEqual(request.method, "GET")
                self.assertIn("REQUEST=GetCapabilities", request.url)
                self.assertIn(f"VERSION={version}", request.url)
                self.assertTrue(request.url.startswith("http"))
