from eulxml import xmlmap

from resourceNew.parsers.consts import NS_WC
from resourceNew.parsers.mixins import DBModelConverterMixin


class FeatureTypeElement(DBModelConverterMixin, xmlmap.XmlObject):
    model = 'resourceNew.FeatureTypeElement'
    name = xmlmap.StringField(xpath=f"//{NS_WC}sequence']/{NS_WC}element']/@name")
    data_type = xmlmap.StringField(xpath=f"//{NS_WC}sequence']/{NS_WC}element']/@type")
    required = xmlmap.SimpleBooleanField(xpath=f"//{NS_WC}sequence']/{NS_WC}element']/@nillable", true="true", false="false")
