
from eulxml.xmlmap import NodeField, StringField, XmlObject
from ows_lib.xml_mapper.mixins import DBModelConverterMixin
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE


class WebMapServiceDefaultSettings(DBModelConverterMixin, XmlObject):
    ROOT_NS = "wms"
    ROOT_NAMESPACES = {
        "wms": WMS_1_3_0_NAMESPACE,
        "xlink": XLINK_NAMESPACE
    }


# class ServiceMetadataContact(DBModelConverterMixin, xmlmap.XmlObject):
#     ROOT_NAME = "ContactInformation"

#     name = StringField(xpath="ContactPersonPrimary/ContactOrganization")
#     person_name = StringField(xpath="ContactPersonPrimary/ContactPerson")
#     phone = StringField(xpath="ContactVoiceTelephone")
#     facsimile = StringField(xpath="ContactFacsimileTelephone")
#     email = StringField(xpath="ContactElectronicMailAddress")
#     country = StringField(xpath="ContactAddress/Country")
#     postal_code = StringField(xpath="ContactAddress/PostCode")
#     city = StringField(xpath="ContactAddress/City")
#     state_or_province = StringField(xpath="ContactAddress/StateOrProvince")
#     address = StringField(xpath="ContactAddress/Address")


class ServiceMetadata(WebMapServiceDefaultSettings):
    ROOT_NAME = "Service"

    title = StringField(xpath="wms:Title")
    abstract = StringField(xpath="wms:Abstract")
    fees = StringField(xpath="wms:Fees")
    access_constraints = StringField(xpath="wms:AccessConstraints")

    # ForeignKey
    # service_contact = NodeField(xpath="wms:ContactInformation",
    #                             node_class=ServiceMetadataContact)

    # # ManyToManyField
    # keywords = NodeListField(xpath="KeywordList/Keyword",
    #                          node_class=Keyword)


class WebMapService(WebMapServiceDefaultSettings):
    ROOT_NAME = f"/wms:WMS_Capabilities/@version='1.3.0'"
    XSD_SCHEMA = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    __root_node = "/wms:WMS_Capabilities"
    __service_path = f"/{__root_node}/wms:Service"

    service_url = StringField(
        xpath=f"{__service_path}/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    version = StringField(xpath=f"{__root_node}/@version", choices='1.3.0')

    # service_type = NodeField(xpath=".", node_class=ServiceType)
    service_metadata = NodeField(
        xpath=__service_path, node_class=ServiceMetadata)
    # operation_urls = NodeListField(xpath=f"{NS_WC}Capability']/{NS_WC}Request']//{NS_WC}DCPType']/{NS_WC}HTTP']"
    #                                f"//{NS_WC}OnlineResource']",
    #                                node_class=WmsOperationUrl)

    # all_layers = None
