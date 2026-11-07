
from django.contrib.gis.geos import GEOSGeometry
from django.db.utils import IntegrityError
from django.test import SimpleTestCase, TestCase
from registry.models.security import (
    AllowedWebMapServiceOperation, WebFeatureServiceHttpRequestLog,
    WebFeatureServiceHttpResponseLog, WebMapServiceHttpRequestLog,
    WebMapServiceHttpResponseLog)
from registry.models.service import WebFeatureService, WebMapService


class AllowedWebMapServiceOperationModelTest(TestCase):

    fixtures = ['test_users.json', 'test_keywords.json', "test_wms.json"]

    def test_save_without_geometry(self):
        allowed_wms_operation = AllowedWebMapServiceOperation.objects.create(
            secured_service=WebMapService.objects.get(pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'))
        self.assertIsInstance(obj=allowed_wms_operation,
                              cls=AllowedWebMapServiceOperation)

    def test_save_with_empty_geometry(self):
        self.assertRaises(
            IntegrityError,
            AllowedWebMapServiceOperation.objects.create,
            secured_service=WebMapService.objects.get(
                pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'),
            allowed_area=GEOSGeometry("MULTIPOLYGON EMPTY"))


class HttpLogModelPerServiceTypeTest(SimpleTestCase):
    """The exchange with a secured service is logged in its service's own models.

    The proxy reads the concrete log models out of the relations named here, and an
    abstract log model has no table of its own and cannot be instantiated (#1153).
    A renamed relation is caught by this test and not by a proxied request.
    """

    def test_every_secured_service_type_names_its_concrete_log_pair(self):
        for service_cls, request_log_cls, response_log_cls in (
            (WebMapService, WebMapServiceHttpRequestLog,
             WebMapServiceHttpResponseLog),
            (WebFeatureService, WebFeatureServiceHttpRequestLog,
             WebFeatureServiceHttpResponseLog),
        ):
            self.assertEqual(
                request_log_cls, service_cls().http_request_logs.model)
            self.assertEqual(
                response_log_cls,
                request_log_cls._meta.get_field("response").related_model)
            self.assertEqual(
                request_log_cls,
                response_log_cls._meta.get_field("request").related_model)
