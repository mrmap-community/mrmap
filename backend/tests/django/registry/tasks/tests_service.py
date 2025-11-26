from pathlib import Path
from unittest.mock import patch

from django.test import TransactionTestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from notify.models import BackgroundProcess
from registry.enums.service import AuthTypeEnum, OGCServiceVersionEnum
from registry.models.security import WebMapServiceAuthentication
from registry.models.service import WebMapService
from registry.tasks.service import build_ogc_service
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, *args, **kwargs):
    if request.url == 'https://maps.dwd.de/geoserver/wms?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities':
        return MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml')))
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
