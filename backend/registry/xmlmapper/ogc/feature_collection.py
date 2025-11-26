from eulxml import xmlmap
from ows_lib.xml_mapper.gml.gml import Gml
from registry.xmlmapper.consts import NS_WC


# TODO: #527
class Member(xmlmap.XmlObject):
    bounded_by = xmlmap.NodeField(
        xpath=f"//{NS_WC}boundedBy']/gml:*", node_class=Gml)
    geom = xmlmap.NodeField(xpath=f"//{NS_WC}THE_GEOM']/gml:*", node_class=Gml)

# TODO: #527


class FeatureCollection(xmlmap.XmlObject):
    number_matched = xmlmap.IntegerField(xpath="@numberMatched")
    number_returned = xmlmap.IntegerField(xpath="@numberReturned")
    bounded_by = xmlmap.NodeField(
        xpath=f"{NS_WC}boundedBy']/gml:*", node_class=Gml)
    members = xmlmap.NodeListField(xpath=f"{NS_WC}member']", node_class=Member)
    members = xmlmap.NodeListField(xpath=f"{NS_WC}member']", node_class=Member)
