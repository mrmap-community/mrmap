from pathlib import Path
from unittest import skip

from django.test import TestCase
from registry.enums.service import HttpMethodEnum
from registry.models.service import (CatalougeService,
                                     CswOperationUrlQueryable,
                                     WebFeatureService, WebMapService)
from registry.xmlmapper.ogc.capabilities import get_parsed_service


class WebMapServiceCapabilitiesManagerTest(TestCase):

    @skip("test which test runs endless")
    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/dwd_wms_1.3.0.xml')))

        WebMapService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service = WebMapService.objects.count()
        self.assertEqual(1, db_service)


class WebFeatureServiceCapabilitiesManagerTest(TestCase):

    @skip("test which test runs endless")
    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/dwd_wfs_2_0_0.xml')))

        WebFeatureService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service = WebFeatureService.objects.count()
        self.assertEqual(1, db_service)


class CatalougeServiceCapabilitiesManagerTest(TestCase):

    @skip("test which test runs endless")
    def test_success(self):
        """Test that create_from_parsed_service manager function works correctly."""

        parsed_service = get_parsed_service(xml=Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/csw_hessen_2_0_2.xml')))

        db_service = CatalougeService.capabilities.create_from_parsed_service(
            parsed_service=parsed_service)

        db_service_count = CatalougeService.objects.count()
        self.assertEqual(1, db_service_count)

        queryables = CswOperationUrlQueryable.objects.closest_matches(
            value="Type", operation="GetRecords", service_id=db_service.pk).filter(operation_url__method=HttpMethodEnum.GET.value)

        self.assertEqual(2, queryables.count())
