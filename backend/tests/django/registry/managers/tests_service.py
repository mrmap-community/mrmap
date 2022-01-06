from pathlib import Path

from django.test import TestCase
from registry.models.service import WebMapService
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
