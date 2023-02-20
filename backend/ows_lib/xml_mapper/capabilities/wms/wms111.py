from eulxml.xmlmap import (FloatField, IntegerField, NodeField, NodeListField,
                           SimpleBooleanField, StringField, StringListField)
from ows_lib.xml_mapper.capabilities.mixins import (OGCServiceTypeMixin,
                                                    ReferenceSystemMixin)
from ows_lib.xml_mapper.capabilities.wms.mixins import (LayerMixin,
                                                        TimeDimensionMixin,
                                                        WebMapServiceMixin)
from ows_lib.xml_mapper.mixins import CustomXmlObject
from ows_lib.xml_mapper.namespaces import XLINK_NAMESPACE


class WebMapServiceDefaultSettings(CustomXmlObject):
    ROOT_NAMESPACES = {
        "xlink": XLINK_NAMESPACE
    }


class ServiceMetadataContact(WebMapServiceDefaultSettings):
    ROOT_NAME = "ContactInformation"

    name = StringField(
        xpath="ContactPersonPrimary/ContactOrganization")
    person_name = StringField(
        xpath="ContactPersonPrimary/ContactPerson")
    phone = StringField(xpath="ContactVoiceTelephone")
    facsimile = StringField(xpath="ContactFacsimileTelephone")
    email = StringField(xpath="ContactElectronicMailAddress")
    country = StringField(xpath="ContactAddress/Country")
    postal_code = StringField(xpath="ContactAddress/PostCode")
    city = StringField(xpath="ContactAddress/City")
    state_or_province = StringField(
        xpath="ContactAddress/StateOrProvince")
    address = StringField(xpath="ContactAddress/Address")


class ServiceType(WebMapServiceDefaultSettings, OGCServiceTypeMixin):
    ROOT_NAME = "WMS_Capabilities/@version='1.3.0'"

    version = StringField(xpath="./@version", choices='1.3.0')

    _name = StringField(xpath="./Service/Name")


class TimeDimension(WebMapServiceDefaultSettings, TimeDimensionMixin):
    """ Time Dimension in ISO8601 format"""

    ROOT_NAME = "Dimension[@name='time']"

    name = StringField(xpath="./@name", choices="time")
    units = StringField(xpath="./@units", choices="ISO8601")

    _extent = StringField(xpath="../Extent[@name='time']")


class ReferenceSystem(WebMapServiceDefaultSettings, ReferenceSystemMixin):
    ROOT_NAME = "SRS"

    _ref_system = StringField(xpath=".")


class MimeType(WebMapServiceDefaultSettings):
    ROOT_NAME = "Format"
    mime_type = StringField(xpath="./Format")


class LegendUrl(WebMapServiceDefaultSettings):
    ROOT_NAME = "LegendUrl"

    legend_url = StringField(
        xpath="./OnlineResource[@xlink:type='simple']/@xlink:href")
    height = IntegerField(xpath="./@height")
    width = IntegerField(xpath="./@width")
    mime_type = NodeField(xpath="./Format", node_class=MimeType)


class Style(WebMapServiceDefaultSettings):
    ROOT_NAME = "Style"

    name = StringField(xpath="./Name")
    title = StringField(xpath="./Title")
    legend_url = NodeField(xpath="./LegendURL", node_class=LegendUrl)


class RemoteMetadata(WebMapServiceDefaultSettings):
    ROOT_NAME = "OnlineResource[@xlink:type='simple']/@xlink:href"
    link = StringField(
        xpath="./@xlink:href")


class Layer(WebMapServiceDefaultSettings, LayerMixin):
    ROOT_NAME = "Layer"

    title = StringField(xpath="./Title")
    abstract = StringField(xpath="./Abstract")
    keywords = StringListField(xpath="./KeywordList/Keyword")

    scale_min = FloatField(xpath="./ScaleHint/@min")
    scale_max = FloatField(xpath="./ScaleHint/@max")

    _bbox_min_x = FloatField(
        xpath="./LatLonBoundingBox/@minx")
    _bbox_max_x = FloatField(
        xpath="./LatLonBoundingBox/@maxx")
    _bbox_min_y = FloatField(
        xpath="./LatLonBoundingBox/@miny")
    _bbox_max_y = FloatField(
        xpath="./LatLonBoundingBox/@maxy")

    reference_systems = NodeListField(
        xpath="./SRS", node_class=ReferenceSystem)
    identifier = StringField(xpath="./Name")
    styles = NodeListField(xpath="./Style", node_class=Style)
    is_queryable = SimpleBooleanField(
        xpath="./@queryable", true=1, false=0)
    is_opaque = SimpleBooleanField(xpath="./@opaque", true=1, false=0)
    is_cascaded = SimpleBooleanField(
        xpath="./@cascaded", true=1, false=0)

    dimensions = NodeListField(
        xpath="./Dimension[@name='time']", node_class=TimeDimension)

    parent = NodeField(xpath="../../Layer", node_class="self")
    children = NodeListField(xpath="./Layer", node_class="self")

    remote_metadata = NodeListField(
        xpath="./MetadataURL/OnlineResource[@xlink:type='simple']",
        node_class=RemoteMetadata)


class WebMapService(WebMapServiceDefaultSettings, WebMapServiceMixin):
    ROOT_NAME = "WMT_MS_Capabilities/@version='1.1.1'"
    XSD_SCHEMA = "http://schemas.opengis.net/wms/1.1.1/WMS_MS_Capabilities.dtd"

    title = StringField(xpath="./Service/Title")
    abstract = StringField(xpath="./Service/Abstract")
    fees = StringField(xpath="./Service/Fees")
    access_constraints = StringField(xpath="./Service/AccessConstraints")

    # ForeignKey
    service_contact = NodeField(xpath="./Service/ContactInformation",
                                node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = StringListField(xpath="./Service/KeywordList/Keyword")

    service_url = StringField(
        xpath="./Service/OnlineResource[@xlink:type='simple']/@xlink:href")

    service_type = NodeField(xpath=".", node_class=ServiceType)

    root_layer = NodeField(
        xpath="./Capability/Layer", node_class=Layer)

    _layers = NodeListField(
        xpath="./Capability//Layer", node_class=Layer)

    # cause the information of operation urls are stored as entity name inside the xpath, we need to parse every operation url seperate.
    # To simplify the access of operation_urls we write a custom getter and setter property for it.
    # With that technique the usage of this mapper is easier and matches the db model
    _get_capabilities_mime_types = StringListField(
        xpath="./Capability/Request/GetCapabilities/Format")
    _get_capabilities_get_url = StringField(
        xpath="./Capability/Request/GetCapabilities/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_capabilities_post_url = StringField(
        xpath="./Capability/Request/GetCapabilities/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_map_mime_types = StringListField(
        xpath="./Capability/Request/GetMap/Format")
    _get_map_get_url = StringField(
        xpath="./Capability/Request/GetMap/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_map_post_url = StringField(
        xpath="./Capability/Request/GetMap/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_feature_info_mime_types = StringListField(
        xpath="./Capability/Request/GetFeatureInfo/Format")
    _get_feature_info_get_url = StringField(
        xpath="./Capability/Request/GetFeatureInfo/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_feature_info_post_url = StringField(
        xpath="./Capability/Request/GetFeatureInfo/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")

    _describe_layer_mime_types = StringListField(
        xpath="./Capability/Request/DescribeLayer/Format")
    _describe_layer_get_url = StringField(
        xpath="./Capability/Request/DescribeLayer/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _describe_layer_post_url = StringField(
        xpath="./Capability/Request/DescribeLayer/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_legend_graphic_mime_types = StringListField(
        xpath="./Capability/Request/GetLegendGraphic/Format")
    _get_legend_graphic_get_url = StringField(
        xpath="./Capability/Request/GetLegendGraphic/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_legend_graphic_post_url = StringField(
        xpath="./Capability/Request/GetLegendGraphic/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")

    _get_styles_mime_types = StringListField(
        xpath="./Capability/Request/GetStyles/Format")
    _get_styles_get_url = StringField(
        xpath="./Capability/Request/GetStyles/DCPType/HTTP/Get/OnlineResource[@xlink:type='simple']/@xlink:href")
    _get_styles_post_url = StringField(
        xpath="./Capability/Request/GetStyles/DCPType/HTTP/Post/OnlineResource[@xlink:type='simple']/@xlink:href")
