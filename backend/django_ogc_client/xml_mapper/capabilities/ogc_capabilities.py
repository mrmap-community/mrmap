from eulxml.xmlmap import XmlObject
from django_ogc_client.xml_mapper.namespaces import XLINK_NAMESPACE

from django_ogc_client.xml_mapper.mixins import DBModelConverterMixin


class Service(DBModelConverterMixin, XmlObject):
    ROOT_NAMESPACES = dict([("xlink", XLINK_NAMESPACE)])

    service_url = xmlmap.StringField(
        xpath=f"{NS_WC}Service']/OnlineResource[@xlink:type='simple']/@xlink:href")
    version = StringField(xpath=f"@{NS_WC}version']")
