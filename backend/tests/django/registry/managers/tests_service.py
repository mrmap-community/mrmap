from pathlib import Path

from django.test import TestCase
from registry.models.service import (CatalougeService, WebFeatureService,
                                     WebMapService)
from registry.xmlmapper.ogc.capabilities import get_parsed_service


class WebMapServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml')))

        WebMapService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service = WebMapService.objects.count()
        self.assertEqual(1, db_service)


class WebFeatureServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/dwd_wfs_2_0_0.xml')))

        WebFeatureService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service = WebFeatureService.objects.count()
        self.assertEqual(1, db_service)


class CatalougeServiceCapabilitiesManagerTest(TestCase):

    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/csw_hessen_2_0_2.xml')))

        CatalougeService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service = CatalougeService.objects.count()
        self.assertEqual(1, db_service)
