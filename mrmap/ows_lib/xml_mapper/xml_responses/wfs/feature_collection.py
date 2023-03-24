
from eulxml.xmlmap import IntegerField, NodeField, NodeListField, XmlObject
from ows_lib.xml_mapper.gml.gml import Gml
from ows_lib.xml_mapper.namespaces import (GML_3_2_2_NAMESPACE,
                                           WFS_2_0_0_NAMESPACE)


class Member(XmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAME = "member"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE
    }


class FeatureCollection(XmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAME = "FeatureCollection"
    ROOT_NAMESPACES = {
        "wfs": WFS_2_0_0_NAMESPACE,
        "gml": GML_3_2_2_NAMESPACE
    }

    number_matched: int = IntegerField(xpath="./@numberMatched")
    number_returned: int = IntegerField(xpath="./@numberReturned")

    members: Member = NodeListField(xpath="./wfs:member", node_class=Member)

    bounded_by: Gml = NodeField(xpath="./wfs:boundedBy/gml:*", node_class=Gml)
