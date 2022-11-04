import os

from django.test import SimpleTestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.xml_mapper.capabilities.csw.csw202 import CatalogueService
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.namespaces import WFS_2_0_0_NAMESPACE, XLINK_NAMESPACE
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class CatalogueServiceTestCase(SimpleTestCase):

    path = os.path.join(DJANGO_TEST_ROOT_DIR,
                        "./test_data/capabilities/csw/2.0.2.xml")

    xml_class = CatalogueService

    version = "2.0.2"

    def setUp(self) -> None:
        self.parsed_capabilities: self.xml_class = load_xmlobject_from_file(
            self.path, xmlclass=self.xml_class)

    def _test_service_metadata_mapper(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.title,
            "CSW Geoportal Hessen")
        self.assertEqual(
            self.parsed_capabilities.service_metadata.abstract,
            "this is the official CSW of the Geoportal Hessen based on pycsw, an OGC CSW server implementation written in Python")
        self.assertEqual(
            self.parsed_capabilities.service_metadata.fees,
            "None"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.access_constraints,
            "None"
        )

    def _test_service_contact_mapper(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.name,
            "Zentrale Kompetenzstelle fuer Geoinformation"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.person_name,
            ""
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.phone,
            "+49-611-535-5513"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.facsimile,
            "+xx-xxx-xxx-xxxx"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.email,
            "you@example.org"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.country,
            "Deutschland"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.postal_code,
            "65195"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.city,
            "Wiesbaden"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.state_or_province,
            "Wiesbaden"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.address,
            "Schaperstrasse 16"
        )

    def _test_service_keywords(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.keywords[0],
            "catalogue"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.keywords[1],
            "discovery"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.keywords[2],
            "metadata"
        )

    def _test_get_capabilities_operation_urls(self):
        self.assertEqual(
            self.parsed_capabilities.operation_urls[0].url,
            "https://gdk.geoportal.hessen.de/pycsw/csw.py"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[0].method,
            "Get"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[0].operation,
            "GetCapabilities"
        )

        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].url,
            "https://gdk.geoportal.hessen.de/pycsw/csw.py"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].method,
            "Post"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].operation,
            "GetCapabilities"
        )

    def _test_service_type_mapper(self):
        self.assertEqual(
            self.parsed_capabilities.service_type.version, self.version)
        self.assertEqual(self.parsed_capabilities.service_type.name, "csw")

    def test_wms_xml_mapper(self):
        self._test_service_metadata_mapper()
        self._test_service_contact_mapper()
        self._test_service_keywords()
        self._test_get_capabilities_operation_urls()

        self._test_service_type_mapper()

    def _get_added_get_feature_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//wfs:WFS_Capabilities/ows:OperationsMetadata/ows:Operation[@name='GetFeature']/ows:DCP/ows:HTTP/ows:Get/@xlink:href",
            namespaces={
                "wfs": WFS_2_0_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_operation_xml_nodes(self):
        return self.parsed_capabilities.node.xpath(
            "//csw:Capabilities/ows:OperationsMetadata/",
            namespaces={
                "wfs": WFS_2_0_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })

    def _get_all_operation_urls(self):
        return self.parsed_capabilities.node.xpath(
            "//csw:Capabilities/ows:OperationsMetadata/ows:Operation//ows:DCP/ows:HTTP/ows:Get/@xlink:href",
            namespaces={
                "wfs": WFS_2_0_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })

    def _get_added_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//csw:Capabilities/ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:DCP/ows:HTTP/ows:Get/@xlink:href",
            namespaces={
                "wfs": WFS_2_0_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0]

    def test_operation_urls_append(self):
        o_url = OperationUrl(
            method="Post",
            operation="GetFeature",
            mime_types=["image/png"],
            url="http://example.com")

        self.parsed_capabilities.operation_urls.append(
            o_url
        )

        added_operation_url = self._get_added_get_feature_operation_url()

        self.assertEqual(
            added_operation_url,
            "http://example.com"
        )

    def test_operation_urls_insert(self):
        o_url = OperationUrl(
            method="Post",
            operation="GetMap",
            mime_types=["image/png"],
            url="http://example.com")

        self.parsed_capabilities.operation_urls.insert(
            0,
            o_url
        )

        added_operation_url = self._get_added_get_map_operation_url()

        self.assertEqual(
            added_operation_url,
            "http://example.com"
        )

    def test_operation_urls_clear(self):
        self.parsed_capabilities.operation_urls.clear()

        operation_urls = self._get_operation_xml_nodes()

        self.assertEqual(
            len(self.parsed_capabilities.operation_urls),
            0
        )

        self.assertEqual(
            len(operation_urls),
            0
        )

    def test_operation_urls_pop(self):
        self.parsed_capabilities.operation_urls.pop(1)

        operation_urls = self._get_all_operation_urls()

        self.assertEqual(
            len(self.parsed_capabilities.operation_urls),
            6
        )

        self.assertEqual(
            len(operation_urls),
            6
        )

    def test_operation_urls_remove(self):

        o_url = self.parsed_capabilities.operation_urls[2]

        self.parsed_capabilities.operation_urls.remove(o_url)

        operation_urls = self._get_all_operation_urls()

        self.assertEqual(
            len(self.parsed_capabilities.operation_urls),
            6
        )

        self.assertEqual(
            len(operation_urls),
            6
        )

    def test_operation_urls_update_single_object(self):

        o_url = self.parsed_capabilities.operation_urls[0]
        o_url.url = "http://example.com"

        new_o_url_url = self._get_added_operation_url()

        self.assertEqual(
            new_o_url_url,
            "http://example.com"
        )

    def test_camouflage_urls(self):

        self.parsed_capabilities.camouflage_urls(new_domain="example.com")

        new_o_url_url = self._get_added_operation_url()

        self.assertEqual(
            new_o_url_url,
            "https://example.com/geoserver/ows?SERVICE=WMS&"
        )
