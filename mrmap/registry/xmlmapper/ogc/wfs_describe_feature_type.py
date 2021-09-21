from eulxml import xmlmap

from registry.xmlmapper.consts import NS_WC
from registry.xmlmapper.mixins import DBModelConverterMixin


class FeatureTypeElement(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'registry.FeatureTypeElement'
    max_occurs = xmlmap.IntegerField(xpath=f"@maxOccurs")
    min_occurs = xmlmap.IntegerField(xpath=f"@minOccurs")
    name = xmlmap.StringField(xpath=f"@name")
    data_type = xmlmap.StringField(xpath=f"@type")
    required = xmlmap.SimpleBooleanField(xpath=f"@nillable", true="true", false="false")
    # todo:
    targetNamespace = None


class DescribedFeatureType(xmlmap.XmlObject):
    elements = xmlmap.NodeListField(xpath=f"//{NS_WC}sequence']/{NS_WC}element']", node_class=FeatureTypeElement)
