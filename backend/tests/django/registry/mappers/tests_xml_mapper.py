from pathlib import Path

from django.test import TestCase
from registry.mappers.configs.wms import XPATH_MAP
from registry.mappers.xml_mapper import XmlMapper


class XmlMapperTest(TestCase):

    def test_success(self):
        """Test that create manager function works correctly."""

        xml = Path(Path.joinpath(
            Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/1.1.1.xml')).resolve().__str__()

        mapper = XmlMapper(xml=xml, mapping=XPATH_MAP[("WMS", "1.1.1")])

        data = mapper.xml_to_django()
        i = 0
