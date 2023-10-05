from pathlib import Path

from django.test import TestCase
from ows_lib.xml_mapper.utils import get_parsed_service
from registry.models.metadata import ReferenceSystem
from registry.models.service import (CatalogueService, Layer,
                                     WebFeatureService, WebMapService)


class WebMapServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create manager function works correctly."""

        parsed_service = get_parsed_service(Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.3.0.xml')))

        WebMapService.capabilities.create(
            parsed_service=parsed_service)

        db_service = WebMapService.objects.count()
        self.assertEqual(1, db_service)

        db_layers = Layer.objects.all()
        self.assertEqual(137, len(db_layers))

        db_crs = ReferenceSystem.objects.all()
        crs_expected = [900913, 4839, 4326, 4258, 3857, 3413,
                        31468, 31467, 3045, 3044, 25833, 25832, 1000001]

        self.assertEqual(len(crs_expected), len(db_crs))
        for crs in crs_expected:
            _ = ReferenceSystem(code=str(crs), prefix="EPSG")
            self.assertIn(_, db_crs)

        self.assertEqual(13, db_layers[0].reference_systems.count())
        for crs in crs_expected:
            _ = ReferenceSystem(code=str(crs), prefix="EPSG")
            self.assertIn(_, db_layers[0].reference_systems.all())


class WebFeatureServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create manager function works correctly."""

        parsed_service = get_parsed_service(Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/capabilities/wfs/2.0.0.xml')))

        WebFeatureService.capabilities.create(
            parsed_service=parsed_service)

        db_service = WebFeatureService.objects.count()
        self.assertEqual(1, db_service)


class CatalogueServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create manager function works correctly."""

        parsed_service = get_parsed_service(Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/capabilities/csw/2.0.2.xml')))

        CatalogueService.capabilities.create(
            parsed_service=parsed_service)

        db_service_count = CatalogueService.objects.count()
        self.assertEqual(1, db_service_count)

        #  See TODO in CswOperationUrlQueryable model
        # queryables = CswOperationUrlQueryable.objects.closest_matches(
        #     value="Type", operation="GetRecords", service_id=db_service.pk).filter(operation_url__method=HttpMethodEnum.GET.value)

        # self.assertEqual(2, queryables.count())
