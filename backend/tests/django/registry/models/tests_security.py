from unittest import skip

from django.contrib.gis.geos import GEOSGeometry
from django.db.utils import IntegrityError
from django.test import TestCase
from registry.models.security import AllowedWebMapServiceOperation
from registry.models.service import WebMapService


class AllowedWebMapServiceOperationModelTest(TestCase):

    fixtures = ['test_keywords.json', "test_wms.json"]

    @skip("test which test runs endless")
    def test_save_without_geometry(self):
        allowed_wms_operation = AllowedWebMapServiceOperation.objects.create(
            secured_service=WebMapService.objects.get(pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'))
        self.assertIsInstance(obj=allowed_wms_operation,
                              cls=AllowedWebMapServiceOperation)

    @skip("test which test runs endless")
    def test_save_with_empty_geometry(self):
        self.assertRaises(
            IntegrityError,
            AllowedWebMapServiceOperation.objects.create,
            secured_service=WebMapService.objects.get(
                pk='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'),
            allowed_area=GEOSGeometry("MULTIPOLYGON EMPTY"))
