from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from django_celery_beat.models import IntervalSchedule
from MrMap.settings import BASE_DIR
from registry.models.monitoring import (GetCapabilititesProbe,
                                        GetCapabilititesProbeResult,
                                        GetMapProbe, GetMapProbeResult,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
from registry.tasks.monitoring import run_wms_monitoring
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


class WmsGetCapabilitiesMonitoringTaskTest(TestCase):

    fixtures = ['test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        )
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.monitoring_settings = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms,
            interval=self.interval
        )

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("ows_lib.client.mixins.OgcClient.send_request", side_effect=side_effect)
    def test_run_wms_monitoring(self, mocked_run_checks):
        setup_capabilitites_file()
        cap_probe = GetCapabilititesProbe.objects.create(
            settings=self.monitoring_settings,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            settings=self.monitoring_settings,
        )
        map_probe.layers.set(self.wms.layers.all())

        eager_result = run_wms_monitoring.delay(
            setting_pk=self.monitoring_settings.pk)

        self.assertEqual(1, GetCapabilititesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())
        try:
            get_cap_result = GetCapabilititesProbeResult.objects.get(
                run__pk=eager_result.result,
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
                run__pk=eager_result.result,
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

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("ows_lib.client.mixins.OgcClient.send_request", side_effect=side_effect)
    def test_run_wms_monitoring_with_service_exceptions(self, mocked_run_checks):
        setup_capabilitites_file(service_exception_url=True)
        cap_probe = GetCapabilititesProbe.objects.create(
            settings=self.monitoring_settings,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            settings=self.monitoring_settings,
        )
        map_probe.layers.set(self.wms.layers.all())

        eager_result = run_wms_monitoring.delay(
            setting_pk=self.monitoring_settings.pk)

        self.assertEqual(1, GetCapabilititesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())

        try:
            get_cap_result = GetCapabilititesProbeResult.objects.get(
                run__pk=eager_result.result,
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
                run__pk=eager_result.result,
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
