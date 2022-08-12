from pathlib import Path

from django.test import TestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.xml_mapper.capabilities.wms.capabilities import WebMapService


class WebMapServiceTestCase(TestCase):

    def test_xml_loading(self):
        path = Path(Path.joinpath(
            Path(__file__).parent.resolve(), "./wms_1.3.0.xml"))

        parsed_capabilities: WebMapService = load_xmlobject_from_file(
            path.resolve().__str__(), xmlclass=WebMapService)

        print(parsed_capabilities.version)
        print(parsed_capabilities.service_url)
