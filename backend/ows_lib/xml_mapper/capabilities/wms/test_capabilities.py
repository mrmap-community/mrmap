from pathlib import Path

from django.test import SimpleTestCase
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.xml_mapper.capabilities.wms.capabilities import (Format,
                                                              OperationUrl,
                                                              WebMapService)
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE


class WebMapServiceTestCase(SimpleTestCase):

    def setUp(self) -> None:
        path = Path(Path.joinpath(
            Path(__file__).parent.resolve(), "./wms_1.3.0.xml"))

        self.parsed_capabilities: WebMapService = load_xmlobject_from_file(
            path.resolve().__str__(), xmlclass=WebMapService)

    def _test_root_mapper(self):
        self.assertEqual(self.parsed_capabilities.version, "1.3.0")
        self.assertEqual(self.parsed_capabilities.service_url,
                         "https://maps.dwd.de/geoserver/")

    def _test_service_metadata_mapper(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.title,
            "DWD GeoServer WMS")
        self.assertEqual(
            self.parsed_capabilities.service_metadata.abstract,
            "This is the Web Map Server of DWD.")
        self.assertEqual(
            self.parsed_capabilities.service_metadata.fees,
            "none"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.access_constraints,
            "http://www.dwd.de/DE/service/copyright/copyright_node.html"
        )

    def _test_service_contact_mapper(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.name,
            "Deutscher Wetterdienst"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.person_name,
            ""
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.phone,
            ""
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.facsimile,
            ""
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.email,
            "info@dwd.de"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.country,
            "Germany"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.postal_code,
            "63067"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.city,
            "Offenbach"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.state_or_province,
            "Hessen"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.service_contact.address,
            "Frankfurter Strasse 135"
        )

    def _test_service_keywords(self):
        self.assertEqual(
            self.parsed_capabilities.service_metadata.keywords[0].keyword,
            "meteorology"
        )
        self.assertEqual(
            self.parsed_capabilities.service_metadata.keywords[1].keyword,
            "climatology"
        )

    def _test_get_capabilities_operation_urls(self):
        self.assertEqual(
            self.parsed_capabilities.operation_urls[0].url,
            "https://maps.dwd.de/geoserver/ows?SERVICE=WMS&"
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
            self.parsed_capabilities.operation_urls[0].mime_types[0].mime_type,
            "text/xml"
        )

        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].url,
            "https://maps.dwd.de/geoserver/ows?SERVICE=WMS&"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].method,
            "Post"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].operation,
            "GetCapabilities"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[1].mime_types[0].mime_type,
            "text/xml"
        )

    def _test_get_map_operation_urls(self):
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].url,
            "https://maps.dwd.de/geoserver/ows?SERVICE=WMS&"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].method,
            "Get"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].operation,
            "GetMap"
        )
        self.assertEqual(
            len(self.parsed_capabilities.operation_urls[2].mime_types),
            24
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].mime_types[0].mime_type,
            "image/png"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].mime_types[1].mime_type,
            "application/atom+xml"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[2].mime_types[2].mime_type,
            "application/json;type=geojson"
        )

    def _test_get_feature_info_operation_urls(self):
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].url,
            "https://maps.dwd.de/geoserver/ows?SERVICE=WMS&"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].method,
            "Get"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].operation,
            "GetFeatureInfo"
        )
        self.assertEqual(
            len(self.parsed_capabilities.operation_urls[3].mime_types),
            8
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].mime_types[0].mime_type,
            "text/plain"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].mime_types[1].mime_type,
            "application/vnd.ogc.gml"
        )
        self.assertEqual(
            self.parsed_capabilities.operation_urls[3].mime_types[2].mime_type,
            "text/xml"
        )

    def test_wms_xml_mapper(self):
        self._test_root_mapper()
        self._test_service_metadata_mapper()
        self._test_service_contact_mapper()
        self._test_service_keywords()
        self._test_get_capabilities_operation_urls()
        self._test_get_map_operation_urls()
        self._test_get_feature_info_operation_urls()

    def test_wms_operation_urls_append(self):
        self.parsed_capabilities.operation_urls.append(
            OperationUrl(
                method="Post",
                operation="GetMap",
                mime_types=[Format(context={"mime_type": "image/png"})],
                url="http://example.com")
        )

        added_operation_url = self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource/@xlink:href",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0]

        self.assertEqual(
            added_operation_url,
            "http://example.com"
        )

    def test_wms_operation_urls_clear(self):
        self.parsed_capabilities.operation_urls.clear()

        operation_urls = self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Request",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })

        self.assertEqual(
            len(self.parsed_capabilities.operation_urls),
            0
        )

        self.assertEqual(
            len(operation_urls),
            0
        )
