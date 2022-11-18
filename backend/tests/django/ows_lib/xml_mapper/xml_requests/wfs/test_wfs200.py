import os

from django.contrib.gis.geos import Polygon
from django.test import SimpleTestCase
from eulxml.xmlmap import load_xmlobject_from_file
from lxml import etree
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
        # print(self.parsed_xml_request.queries[0].filter.condition)

        self.parsed_xml_request.secure_spatial(
            value_reference="THE_GEOM", polygon=Polygon(((-180, -90),
                                                         (-180, 90),
                                                         (180, 90),
                                                         (180, -90),
                                                         (-180, -90)), srid=4326))

        first = self.parsed_xml_request.serializeDocument()
        second = load_xmlobject_from_file(
            filename=self.secured_xml, xmlclass=GetFeatureRequest)
        second = second.serializeDocument()

        # We need to format both xml files the same way... otherwise the self.assertXMLEqual function, which is based on str compare will fail
        parser = etree.XMLParser(
            remove_blank_text=True, remove_comments=True, ns_clean=True, encoding="UTF-8", remove_pis=True)

        first_xml = etree.fromstring(text=first, parser=parser)
        second_xml = etree.fromstring(text=second, parser=parser)

        self.assertXMLEqual(etree.tostring(first_xml).decode("UTF-8"),
                            etree.tostring(second_xml).decode("UTF-8"))
