from eulxml import xmlmap

from resourceNew.parsers.consts import NS_WC
from resourceNew.parsers.gml.gml import Gml
from resourceNew.parsers.iso.iso_metadata import Polygon
from resourceNew.parsers.ogc.wfs_filter import Filter


class FeatureTypeElement(xmlmap.XmlObject):
    geom = xmlmap.NodeField(xpath=f"//gml:*",
                            node_class=Gml)


class FeatureType(xmlmap.XmlObject):
    element = xmlmap.NodeField(xpath="*",
                               node_class=FeatureTypeElement)


class Operation(xmlmap.XmlObject):
    action = xmlmap.StringField(xpath="name()")
    type_name = xmlmap.StringField(xpath="@typeName")
    type_names = xmlmap.StringField(xpath="@typeNames")
    feature_types = xmlmap.NodeListField(xpath="*",
                                         node_class=FeatureType)
    filter = xmlmap.NodeField(xpath=f"//{NS_WC}Filter']/*",
                              node_class=Filter)

    def get_type_names(self):
        if self.type_name:
            return self.type_name
        else:
            return self.type_names

    def secure_spatial(self, value_reference, polygon: Polygon, axis_order_correction: bool = True):
        if self.filter:
            self.filter.secure_spatial(value_reference, polygon, axis_order_correction)
        else:
            self.node.append(Filter.init_secured_filter_node(value_reference, polygon, axis_order_correction))


class Transaction(xmlmap.XmlObject):
    operation = xmlmap.NodeField(xpath=f"//wfs:Transaction/{NS_WC}Insert']|{NS_WC}Update']|{NS_WC}Delete']|{NS_WC}Replace']",
                                 node_class=Operation)
    version = xmlmap.StringField(xpath="@version")
    service_type = xmlmap.StringField(xpath="@service")

    def get_service_version(self):
        if self.version:
            return self.version.split(".")

    def get_major_service_version(self):
        return int(self.get_service_version()[0])
