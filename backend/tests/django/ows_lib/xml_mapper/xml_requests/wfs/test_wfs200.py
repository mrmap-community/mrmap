import os

from django.contrib.gis.geos import Polygon
from django.test import SimpleTestCase
from eulxml.xmlmap import load_xmlobject_from_file
from lxml import etree, objectify
from ows_lib.xml_mapper.xml_requests.wfs.wfs200 import GetFeatureRequest
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class GetFeatureRequestTestCase(SimpleTestCase):

    insecure_xml = os.path.join(DJANGO_TEST_ROOT_DIR,
                                "./test_data/xml_requests/get_feature_2.0.0.xml")
    secured_xml = os.path.join(DJANGO_TEST_ROOT_DIR,
                               "./test_data/xml_requests/get_feature_secured_2.0.0.xml")

    def setUp(self) -> None:
        self.parsed_xml_request: GetFeatureRequest = load_xmlobject_from_file(
            self.insecure_xml, xmlclass=GetFeatureRequest)

    def test_secure_spatial(self):
        print(self.parsed_xml_request.query[0].filter.condition)

        self.parsed_xml_request.secure_spatial(
            value_reference="bla", polygon=Polygon(((-180, -90),
                                                    (-180, 90),
                                                    (180, 90),
                                                    (180, -90),
                                                    (-180, -90))))

        obj1 = objectify.fromstring(
            self.parsed_xml_request.serializeDocument())
        first = etree.tostring(obj1)
        obj2 = objectify.fromstring(open(self.secured_xml, "rb").read())
        second = etree.tostring(obj2)

        self.assertEqual(first, second)
