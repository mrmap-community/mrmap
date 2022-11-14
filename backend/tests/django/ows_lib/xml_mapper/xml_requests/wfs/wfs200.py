import os

from django.test import SimpleTestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.xml_mapper.xml_requests.wfs.wfs200 import GetFeatureRequest
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class GetFeatureRequestTestCase(SimpleTestCase):

    path = os.path.join(DJANGO_TEST_ROOT_DIR,
                        "./test_data/xml_requests/get_feature_2.0.0.xml")

    def setUp(self) -> None:
        self.parsed_xml_request: GetFeatureRequest = load_xmlobject_from_file(
            self.path, xmlclass=GetFeatureRequest)
