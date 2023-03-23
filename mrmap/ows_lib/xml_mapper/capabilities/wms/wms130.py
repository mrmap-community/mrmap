from eulxml.xmlmap import (FloatField, IntegerField, NodeField, NodeListField,
                           SimpleBooleanField, StringField, StringListField)
from ows_lib.xml_mapper.capabilities.mixins import (OGCServiceTypeMixin,
                                                    ReferenceSystemMixin)
from ows_lib.xml_mapper.capabilities.wms.mixins import (LayerMixin,
                                                        TimeDimensionMixin,
                                                        WebMapServiceMixin)
from ows_lib.xml_mapper.mixins import CustomXmlObject
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE


class WebMapServiceDefaultSettings(CustomXmlObject):
    ROOT_NS = WMS_1_3_0_NAMESPACE
    ROOT_NAMESPACES = {
        "wms": WMS_1_3_0_NAMESPACE,
        "xlink": XLINK_NAMESPACE
    }


class ServiceMetadataContact(WebMapServiceDefaultSettings):
    ROOT_NAME = "ContactInformation"

    name = StringField(
        xpath="./wms:ContactPersonPrimary/wms:ContactOrganization")
    person_name = StringField(
        xpath="./wms:ContactPersonPrimary/wms:ContactPerson")
    phone = StringField(xpath="./wms:ContactVoiceTelephone")
    facsimile = StringField(xpath="./wms:ContactFacsimileTelephone")
    email = StringField(xpath="./wms:ContactElectronicMailAddress")
    country = StringField(xpath="./wms:ContactAddress/wms:Country")
    postal_code = StringField(xpath="./wms:ContactAddress/wms:PostCode")
    city = StringField(xpath="./wms:ContactAddress/wms:City")
    state_or_province = StringField(
        xpath="./wms:ContactAddress/wms:StateOrProvince")
    address = StringField(xpath="./wms:ContactAddress/wms:Address")


class ServiceType(WebMapServiceDefaultSettings, OGCServiceTypeMixin):
    ROOT_NAME = "WMS_Capabilities/@version='1.3.0'"

    version = StringField(xpath="./@version", choices='1.3.0')
    _name = StringField(xpath="./wms:Service/wms:Name")


class TimeDimension(WebMapServiceDefaultSettings, TimeDimensionMixin):
    """ Time Dimension in ISO8601 format"""

    ROOT_NAME = "Dimension[@name='time']"

    name = StringField(xpath="./@name", choices="time")
    units = StringField(xpath="./@units", choices="ISO8601")

    _extent = StringField(xpath="./text()")


class ReferenceSystem(WebMapServiceDefaultSettings, ReferenceSystemMixin):
    ROOT_NAME = "CRS"

    _ref_system = StringField(xpath=".")


class MimeType(WebMapServiceDefaultSettings):
    ROOT_NAME = "Format"
    mime_type = StringField(xpath="./wms:Format")


class LegendUrl(WebMapServiceDefaultSettings):
    ROOT_NAME = "LegendUrl"

    legend_url = StringField(
        xpath="./wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    height = IntegerField(xpath="./@height")
    width = IntegerField(xpath="./@width")
    mime_type = NodeField(xpath="./wms:Format", node_class=MimeType)


class Style(WebMapServiceDefaultSettings):
    ROOT_NAME = "Style"

    name = StringField(xpath="./wms:Name")
    title = StringField(xpath="./wms:Title")
    legend_url = NodeField(xpath="./wms:LegendURL", node_class=LegendUrl)


class RemoteMetadata(WebMapServiceDefaultSettings):
    ROOT_NAME = "OnlineResource[@xlink:type='simple']/@xlink:href"
    link = StringField(
        xpath="./@xlink:href")


class Layer(WebMapServiceDefaultSettings, LayerMixin):
    ROOT_NAME = "Layer"

    title = StringField(xpath="./wms:Title")
    abstract = StringField(xpath="./wms:Abstract")
    keywords = StringListField(xpath="./wms:KeywordList/wms:Keyword")

    scale_min = FloatField(xpath="./wms:MinScaleDenominator")
    scale_max = FloatField(xpath="./wms:MaxScaleDenominator")

    _bbox_min_x = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:westBoundLongitude")
    _bbox_max_x = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:eastBoundLongitude")
    _bbox_min_y = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:southBoundLatitude")
    _bbox_max_y = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:northBoundLatitude")

    reference_systems = NodeListField(
        xpath="./wms:CRS", node_class=ReferenceSystem)
    identifier = StringField(xpath="./wms:Name")
    styles = NodeListField(xpath="./wms:Style", node_class=Style)
    is_queryable = SimpleBooleanField(
        xpath="./@queryable", true=1, false=0)
    is_opaque = SimpleBooleanField(xpath="./@opaque", true=1, false=0)
    is_cascaded = SimpleBooleanField(
        xpath="./@cascaded", true=1, false=0)
    dimensions = NodeListField(
        xpath="./wms:Dimension[@name='time']", node_class=TimeDimension)
    parent = NodeField(xpath="../../wms:Layer", node_class="self")
    children = NodeListField(xpath="./wms:Layer", node_class="self")

    remote_metadata = NodeListField(
        xpath="./wms:MetadataURL/wms:OnlineResource[@xlink:type='simple']",
        node_class=RemoteMetadata)


class WebMapService(WebMapServiceDefaultSettings, WebMapServiceMixin):
    ROOT_NAME = "WMS_Capabilities/@version='1.3.0'"
    XSD_SCHEMA = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    title = StringField(xpath="./wms:Service/wms:Title")
    abstract = StringField(xpath="./wms:Service/wms:Abstract")
    fees = StringField(xpath="./wms:Service/wms:Fees")
    access_constraints = StringField(
        xpath="./wms:Service/wms:AccessConstraints")
    service_url = StringField(
        xpath="./wms:Service/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    # ForeignKey
    service_contact = NodeField(xpath="./wms:Service/wms:ContactInformation",
                                node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = StringListField(
        xpath="./wms:Service/wms:KeywordList/wms:Keyword")

    service_type = NodeField(xpath=".", node_class=ServiceType)

    root_layer = NodeField(
        xpath="./wms:Capability/wms:Layer", node_class=Layer)

    _layers = NodeListField(
        xpath="./wms:Capability//wms:Layer", node_class=Layer)

    # cause the information of operation urls are stored as entity name inside the xpath, we need to parse every operation url seperate.
    # To simplify the access of operation_urls we write a custom getter and setter property for it.
    # With that technique the usage of this mapper is easier and matches the db model
    _get_capabilities_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:Format")
    _get_capabilities_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_capabilities_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_map_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:Format")
    _get_map_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_map_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_feature_info_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:Format")
    _get_feature_info_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_feature_info_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    _describe_layer_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:DescribeLayer/wms:Format")
    _describe_layer_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:DescribeLayer/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _describe_layer_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:DescribeLayer/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_legend_graphic_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetLegendGraphic/wms:Format")
    _get_legend_graphic_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetLegendGraphic/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_legend_graphic_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetLegendGraphic/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_styles_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetStyles/wms:Format")
    _get_styles_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetStyles/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_styles_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetStyles/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
