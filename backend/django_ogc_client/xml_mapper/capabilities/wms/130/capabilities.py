
from django_ogc_client.xml_mapper.mixins import DBModelConverterMixin
from django_ogc_client.xml_mapper.namespaces import XLINK_NAMESPACE
from eulxml.xmlmap import NodeField, NodeListField, StringField, XmlObject


class WebMapService130(DBModelConverterMixin, XmlObject):
    ROOT_NAMESPACES = dict([("xlink", XLINK_NAMESPACE)])
    ROOT_NAME = "WMS_Capabilities/@version='1.3.0'"

    __root_node = "WMS_Capabilities"
    __service_path = f"{__root_node}/Service/"

    service_url = StringField(
        xpath=f"{__service_path}/OnlineResource[@xlink:type='simple']/@xlink:href")
    version = StringField(xpath=f"{__root_node}/@version")

    all_layers = None
    service_type = NodeField(xpath=".", node_class=ServiceType)
    service_metadata = NodeField(
        xpath=__service_path, node_class=ServiceMetadata)
    operation_urls = NodeListField(xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP']"
                                   f"//{NS_WC}OnlineResource']",
                                   node_class=WmsOperationUrl)
