from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from django.urls.base import reverse
from django_celery_results.models import GroupResult
from registry.enums.service import AuthTypeEnum
from registry.models.security import ServiceAuthentication
from registry.models.service import OgcService
from registry.tasks.service import build_ogc_service
from requests.sessions import Session
from rest_framework import status


class MockResponse:

    def __init__(self, status_code, content):
        self.status_code = status_code

        if isinstance(content, Path):
            in_file = open(content, "rb")
            self.content = in_file.read()
            in_file.close()

        if isinstance(content, str):
            self.content = content


class BuildOgcServiceTaskTest(TestCase):

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', return_value=MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml'))))
    def test_success_without_service_auth(self, mock_response):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""

        result = build_ogc_service.delay(get_capabilities_url='http://someurl',
                                         collect_metadata_records=False,
                                         service_auth_pk=None,
                                         **{'user_pk': 'somepk'})

        db_service = OgcService.objects.latest()

        expected_result = {
            "data": {
                "type": "OgcService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', return_value=MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml'))))
    def test_success_with_service_auth(self, mock_response):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""

        auth = ServiceAuthentication.objects.create(
            username="user", password="password", auth_type=AuthTypeEnum.BASIC.value)

        result = build_ogc_service.delay(get_capabilities_url='http://someurl',
                                         collect_metadata_records=False,
                                         service_auth_pk=auth.pk,
                                         **{'user_pk': 'somepk'})

        db_service = OgcService.objects.latest()

        expected_result = {
            "data": {
                "type": "OgcService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}"
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(Session, 'send', return_value=MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml'))))
    def test_success_with_collect_metadata_true(self, mock_response):
        """Test that the ``build_ogc_service`` task runs with no errors,
        and returns the correct result."""

        result = build_ogc_service.delay(get_capabilities_url='http://someurl',
                                         collect_metadata_records=True,
                                         service_auth_pk=None,
                                         **{'user_pk': 'somepk'})

        db_service = OgcService.objects.latest()
        group_result = GroupResult.objects.latest('date_created')

        expected_result = {
            "data": {
                "type": "OgcService",
                "id": f"{db_service.pk}",
                "links": {
                    "self": f"{reverse(viewname='registry:ogcservice-detail', args=[db_service.pk])}"
                },
                "meta": {
                    "collect_metadata_records_job_id": group_result.group_id
                }
            }
        }
        self.assertDictEqual(d1=result.result, d2=expected_result,
                             msg="Task result does not match expection.")
