from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from registry.models.monitoring import (LayerGetMapResult,
                                        WMSGetCapabilitiesResult)
from registry.tasks.monitoring import (check_get_map_operation,
                                       check_wms_get_capabilities_operation)
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(url, timeout):
    if "GetCapabilities" in url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/dwd_wms_1.3.0.xml')))
    elif "GetMap" in url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/karte_rp.fcgi.png')))


class WmsGetCapabilitiesMonitoringTaskTest(TestCase):

    fixtures = ['test_wms.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.models.service.WebMapService.send_get_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        task = check_wms_get_capabilities_operation.delay(
            service_pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3')

        wms_get_cap_result: WMSGetCapabilitiesResult = WMSGetCapabilitiesResult.objects.all()[
            :1][0]

        expected_result = {
            "data": {
                "type": "WMSGetCapabilitiesResult",
                "id": f"{wms_get_cap_result.pk}",
                "links": {
                        "self": f"{reverse(viewname='registry:wmsgetcapabilitiesresult-detail', args=[wms_get_cap_result.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=task.result, d2=expected_result,
                             msg="Task result does not match expection.")


class LayerGetMapMonitoringTaskTest(TestCase):

    fixtures = ['test_wms.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.models.service.WebMapService.send_get_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        task = check_get_map_operation.delay(
            layer_pk='16b93d90-6e2e-497a-b26d-cadbe60ab76e')

        layer_get_map_result: LayerGetMapResult = LayerGetMapResult.objects.all()[
            :1][0]

        expected_result = {
            "data": {
                "type": "LayerGetMapResult",
                "id": f"{layer_get_map_result.pk}",
                "links": {
                        "self": f"{reverse(viewname='registry:layergetmapresult-detail', args=[layer_get_map_result.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=task.result, d2=expected_result,
                             msg="Task result does not match expection.")
