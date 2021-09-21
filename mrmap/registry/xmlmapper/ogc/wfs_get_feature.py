from eulxml import xmlmap
from registry.xmlmapper.ogc.wfs_filter import Filter


class GetFeature(xmlmap.XmlObject):
    filter = xmlmap.NodeField(xpath="wfs:Query/fes:Filter/*",
                              node_class=Filter)
    type_name = xmlmap.StringField(xpath="@typeName")
    type_names = xmlmap.StringField(xpath="@typeNames")

    def get_type_names(self):
        if self.type_name:
            return self.type_name
        else:
            return self.type_names
