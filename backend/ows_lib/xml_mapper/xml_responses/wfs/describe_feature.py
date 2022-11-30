
from eulxml.xmlmap import (IntegerField, NodeListField, SimpleBooleanField,
                           StringField, XmlObject)


class FeatureTypeProperty(XmlObject):
    ROOT_NAME = "element"

    max_occurs = IntegerField(xpath="./@maxOccurs")
    min_occurs = IntegerField(xpath="./@minOccurs")
    name = StringField(xpath="./@name")
    data_type = StringField(xpath="./@type")
    required = SimpleBooleanField(
        xpath="./@nillable", true="true", false="false")


class DescribeFeatureResponse(XmlObject):
    ROOT_NAME = "schema"
    XSD_SCHEMA = "https://www.w3.org/2001/XMLSchema.xsd"

    properties = NodeListField(
        xpath="./complexType/complexContent/extension/sequence/element", node_class=FeatureTypeProperty)
