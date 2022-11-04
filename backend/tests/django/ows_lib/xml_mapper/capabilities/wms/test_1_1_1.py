import os

from django.test import SimpleTestCase
from ows_lib.xml_mapper.capabilities.wms.wms111 import WebMapService
from ows_lib.xml_mapper.namespaces import XLINK_NAMESPACE
from tests.django.ows_lib.xml_mapper.capabilities.wms.mixins import \
    WebMapServiceTestCase
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class WebMapService111TestCase(WebMapServiceTestCase, SimpleTestCase):

    path = os.path.join(DJANGO_TEST_ROOT_DIR,
                        "./test_data/capabilities/wms/1.1.1.xml")

    xml_class = WebMapService

    version = "1.1.1"

    def _get_added_get_map_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Request/GetMap/DCPType/HTTP/Post/OnlineResource/@xlink:href",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_operation_xml_nodes(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Request",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })

    def _get_all_operation_urls(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities//Request//DCPType/HTTP//OnlineResource/@xlink:href",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })

    def _get_added_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Request/GetCapabilities/DCPType/HTTP/Get/OnlineResource/@xlink:href",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_root_layer_min_x(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Layer/LatLonBoundingBox/@minx",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_root_layer_max_x(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Layer/LatLonBoundingBox/@maxx",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_root_layer_min_y(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Layer/LatLonBoundingBox/@miny",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_root_layer_max_y(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability/Layer/LatLonBoundingBox/@maxy",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_new_time_extent(self):
        return self.parsed_capabilities.node.xpath(
            "//WMT_MS_Capabilities/Capability//Layer[Name='dwd:Autowarn_Analyse']/Extent[@name='time']",
            namespaces={
                "xlink": XLINK_NAMESPACE
            })[0].text
