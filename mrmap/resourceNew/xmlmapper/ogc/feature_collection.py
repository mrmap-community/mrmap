from eulxml import xmlmap
from resourceNew.xmlmapper.consts import NS_WC
from resourceNew.xmlmapper.gml.gml import Gml


class Member(xmlmap.XmlObject):
    bounded_by = xmlmap.NodeField(xpath=f"//{NS_WC}boundedBy']/gml:*", node_class=Gml)
    geom = xmlmap.NodeField(xpath=f"//{NS_WC}THE_GEOM']/gml:*", node_class=Gml)


class FeatureCollection(xmlmap.XmlObject):
    number_matched = xmlmap.IntegerField(xpath=f"@numberMatched")
    number_returned = xmlmap.IntegerField(xpath=f"@numberReturned")
    bounded_by = xmlmap.NodeField(xpath=f"{NS_WC}boundedBy']/gml:*", node_class=Gml)
    members = xmlmap.NodeListField(xpath=f"{NS_WC}member']", node_class=Member)

