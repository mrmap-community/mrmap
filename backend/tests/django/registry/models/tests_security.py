from django.contrib.gis.geos import GEOSGeometry
from django.db import IntegrityError
from django.test import TestCase
from registry.models.security import AllowedWebMapServiceOperation


class AllowedWebMapServiceOperationModelTest(TestCase):

    fixtures = ["test_wms.json"]

    def test_save_without_geometry(self):
        self.assertRaises(None, AllowedWebMapServiceOperation.objects.create(
            secured_service='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'))

    def test_save_with_empty_geometry(self):
        self.assertRaises(IntegrityError, AllowedWebMapServiceOperation.objects.create(
            secured_service='cd16cc1f-3abb-4625-bb96-fbe80dbe23e3', allowed_area=GEOSGeometry("POLYGON EMPTY")))
