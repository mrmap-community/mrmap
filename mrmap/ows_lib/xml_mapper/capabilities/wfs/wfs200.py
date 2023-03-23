from eulxml.xmlmap import (NodeField, NodeListField, StringField,
                           StringListField)
from ows_lib.xml_mapper.capabilities.mixins import (OGCServiceTypeMixin,
                                                    ReferenceSystemMixin)
from ows_lib.xml_mapper.capabilities.wfs.mixins import (FeatureTypeMixin,
                                                        WebFeatureServiceMixin)
from ows_lib.xml_mapper.mixins import CustomXmlObject
from ows_lib.xml_mapper.namespaces import (FES_2_0_NAMEPSACE,
                                           GML_3_2_2_NAMESPACE,
                                           OWS_1_1_NAMESPACE,
                                           WFS_2_0_0_NAMESPACE,
                                           XLINK_NAMESPACE)


class WebFeatureServiceDefaultSettings(CustomXmlObject):
    ROOT_NS = WFS_2_0_0_NAMESPACE
    ROOT_NAMESPACES = {
        "wms": WFS_2_0_0_NAMESPACE,
        "ows": OWS_1_1_NAMESPACE,
        "gml": GML_3_2_2_NAMESPACE,
        "fes": FES_2_0_NAMEPSACE,
        "xlink": XLINK_NAMESPACE
    }


class ServiceMetadataContact(WebFeatureServiceDefaultSettings):
    ROOT_NAME = "ows:ServiceProvider"

    name = StringField(xpath="./ows:ProviderName")
    person_name = StringField(xpath="./ows:ServiceContact/ows:IndividualName")

    phone = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Voice")
    facsimile = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Phone/ows:Facsimile")
    email = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:ElectronicMailAddress")
    country = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:Country")
    postal_code = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:PostalCode")
    city = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:City")
    state_or_province = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:AdministrativeArea")
    address = StringField(
        xpath="./ows:ServiceContact/ows:ContactInfo/ows:Address/ows:DeliveryPoint")


class ServiceType(WebFeatureServiceDefaultSettings, OGCServiceTypeMixin):
    ROOT_NAME = "WFS_Capabilities/@version='2.0.0'"

    version = StringField(xpath="./@version", choices='2.0.0')
    _name = StringField(xpath="./ows:ServiceIdentification/ows:ServiceType")


class ReferenceSystem(WebFeatureServiceDefaultSettings, ReferenceSystemMixin):
    _ref_system = StringField(xpath=".")


class DefaultReferenceSystem(ReferenceSystem):
    ROOT_NAME = "DefaultCRS"


class OtherReferenceSystem(ReferenceSystem):
    ROOT_NAME = "OtherCRS"


class OutputFormat(WebFeatureServiceDefaultSettings):
    ROOT_NAME = "Format"

    mime_type = StringField(xpath="./wfs:Format")


class RemoteMetadata(WebFeatureServiceDefaultSettings):
    ROOT_NAME = "MetadataURL"

    link = StringField(xpath="./@xlink:href")


class FeatureType(WebFeatureServiceDefaultSettings, FeatureTypeMixin):
    ROOT_NAME = "FeatureType"

    identifier = StringField(xpath="./wfs:Name")
    title = StringField(xpath="wfs:Title")
    abstract = StringField(xpath="wfs:Abstract")

    remote_metadata = NodeListField(
        xpath="./wfs:MetadataURL", node_class=RemoteMetadata)

    _bbox_lower_corner = StringField(
        xpath="./ows:WGS84BoundingBox/ows:LowerCorner")
    _bbox_upper_corner = StringField(
        xpath="./ows:WGS84BoundingBox/ows:UpperCorner")

    output_formats = NodeListField(
        xpath="./wfs:OutputFormats/wfs:Format", node_class=OutputFormat)

    _default_crs_class = DefaultReferenceSystem
    _other_crs_class = OtherReferenceSystem
    _default_reference_system = NodeField(
        xpath="./wfs:DefaultCRS", node_class=_default_crs_class)
    _other_reference_systems = NodeListField(
        xpath="./wfs:OtherCRS", node_class=_other_crs_class)

    keywords = StringListField(xpath="./ows:Keywords/ows:Keyword")


class WebFeatureService(WebFeatureServiceDefaultSettings, WebFeatureServiceMixin):
    ROOT_NAME = "WFS_Capabilities"
    XSD_SCHEMA = "http://www.opengis.net/wfs/2.0"

    title = StringField(xpath="./ows:ServiceIdentification/ows:Title")
    abstract = StringField(xpath="./ows:ServiceIdentification/ows:Abstract")
    fees = StringField(xpath="./ows:ServiceIdentification/ows:Fees")
    access_constraints = StringField(
        xpath="./ows:ServiceIdentification/ows:AccessConstraints")

    # ForeignKey
    service_contact = NodeField(xpath="./ows:ServiceProvider",
                                node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = StringListField(
        xpath="./ows:ServiceIdentification/ows:Keywords/ows:Keyword")

    service_type = NodeField(xpath=".", node_class=ServiceType)

    feature_types = NodeListField(xpath="./wfs:FeatureTypeList/wfs:FeatureType",
                                  node_class=FeatureType)

    # cause the information of operation urls are stored as entity name inside the xpath, we need to parse every operation url seperate.
    # To simplify the access of operation_urls we write a custom getter and setter property for it.
    # With that technique the usage of this mapper is easier and matches the db model
    _get_capabilities_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:Parameter[@name='AcceptFormats']/ows:AllowedValues/ows:Value")
    _get_capabilities_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_capabilities_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _describe_feature_type_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeFeatureType']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _describe_feature_type_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeFeatureType']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _describe_feature_type_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeFeatureType']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _get_feature_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetFeature']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _get_feature_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetFeature']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_feature_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetFeature']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _get_property_value_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetPropertyValue']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _get_property_value_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetPropertyValue']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_property_value_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetPropertyValue']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _list_stored_queries_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='ListStoredQueries']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _list_stored_queries_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='ListStoredQueries']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _list_stored_queries_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='ListStoredQueries']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _describe_stored_queries_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeStoredQueries']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _describe_stored_queries_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeStoredQueries']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _describe_stored_queries_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeStoredQueries']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _create_stored_query_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='CreateStoredQuery']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _create_stored_query_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='CreateStoredQuery']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _create_stored_query_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='CreateStoredQuery']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    _drop_stored_query_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DropStoredQuery']/ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value")
    _drop_stored_query_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DropStoredQuery']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _drop_stored_query_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DropStoredQuery']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    # TODO: more Operations possible: LockFeature, GetFeatureWithLock, Transaction
