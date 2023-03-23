import os

from django.test import SimpleTestCase
from ows_lib.xml_mapper.capabilities.wms.wms130 import WebMapService
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE
from tests.django.ows_lib.xml_mapper.capabilities.wms.mixins import \
    WebMapServiceTestCase
from tests.django.settings import DJANGO_TEST_ROOT_DIR


class WebMapService130TestCase(WebMapServiceTestCase, SimpleTestCase):

    path = os.path.join(DJANGO_TEST_ROOT_DIR,
                        "./test_data/capabilities/wms/1.3.0.xml")

    xml_class = WebMapService

    version = "1.3.0"

    def _get_added_get_map_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource/@xlink:href",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_operation_xml_nodes(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Request",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })

    def _get_all_operation_urls(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities//wms:Request//wms:DCPType/wms:HTTP//wms:OnlineResource/@xlink:href",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })

    def _get_added_operation_url(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource/@xlink:href",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0]

    def _get_root_layer_min_x(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Layer/wms:EX_GeographicBoundingBox/wms:westBoundLongitude",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0].text

    def _get_root_layer_max_x(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Layer/wms:EX_GeographicBoundingBox/wms:eastBoundLongitude",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0].text

    def _get_root_layer_min_y(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Layer/wms:EX_GeographicBoundingBox/wms:southBoundLatitude",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0].text

    def _get_root_layer_max_y(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability/wms:Layer/wms:EX_GeographicBoundingBox/wms:northBoundLatitude",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0].text

    def _get_new_time_extent(self):
        return self.parsed_capabilities.node.xpath(
            "//wms:WMS_Capabilities/wms:Capability//wms:Layer[wms:Name='dwd:Autowarn_Analyse']/wms:Dimension",
            namespaces={
                "wms": WMS_1_3_0_NAMESPACE,
                "xlink": XLINK_NAMESPACE
            })[0].text
