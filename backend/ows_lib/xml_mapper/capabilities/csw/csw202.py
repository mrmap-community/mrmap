from eulxml.xmlmap import NodeField, StringField, StringListField
from ows_lib.xml_mapper.capabilities.mixins import (OGCServiceMixin,
                                                    OGCServiceTypeMixin)
from ows_lib.xml_mapper.mixins import CustomXmlObject
from ows_lib.xml_mapper.namespaces import (CSW_2_0_2_NAMESPACE, OWS_NAMESPACE,
                                           XLINK_NAMESPACE)


class CatalogueServiceDefaultSettings(CustomXmlObject):
    ROOT_NS = CSW_2_0_2_NAMESPACE
    ROOT_NAMESPACES = {
        "csw": CSW_2_0_2_NAMESPACE,
        "ows": OWS_NAMESPACE,
        "xlink": XLINK_NAMESPACE
    }


class ServiceMetadataContact(CatalogueServiceDefaultSettings):
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


class ServiceType(CatalogueServiceDefaultSettings, OGCServiceTypeMixin):
    ROOT_NAME = "csw:Capabilities/@version='2.0.2'"

    version = StringField(xpath="./@version", choices='2.0.2')
    _name = StringField(xpath="./ows:ServiceIdentification/ows:ServiceType")


class CatalogueService(CatalogueServiceDefaultSettings, OGCServiceMixin):
    ROOT_NAME = "csw:Capabilities/@version='2.0.2'"
    XSD_SCHEMA = "http://schemas.opengis.net/csw/2.0.2/CSW-discovery.xsd"

    _possible_operations = ["GetCapabilities", "DescribeRecord",
                            "GetDomain", "GetRecords", "GetRecordById"]

    service_type = NodeField(xpath=".", node_class=ServiceType)
    title = StringField(xpath="./csw:ServiceIdentification/ows:Title")
    abstract = StringField(xpath="./csw:ServiceIdentification/ows:Abstract")
    fees = StringField(xpath="./csw:ServiceIdentification/ows:Fees")
    access_constraints = StringField(xpath="./csw:ServiceIdentification/ows:AccessConstraints")

    # ForeignKey
    service_contact = NodeField(xpath="./ows:ServiceProvider",
                                node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = StringListField(xpath="./csw:ServiceIdentification/ows:Keywords/ows:Keyword")

    # cause the information of operation urls are stored as entity name inside the xpath, we need to parse every operation url seperate.
    # To simplify the access of operation_urls we write a custom getter and setter property for it.
    # With that technique the usage of this mapper is easier and matches the db model
    _get_capabilities_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:Parameter[@name='AcceptFormats']/ows:AllowedValues/ows:Value")
    _get_capabilities_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_capabilities_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetCapabilities']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")
    _describe_record_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeRecord']/ows:Parameter[@name='outputFormat']/ows:Value")
    _describe_record_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeRecord']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _describe_record_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='DescribeRecord']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")
    _get_domain_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetDomain']/ows:Parameter[@name='ParameterName']/ows:Value")
    _get_domain_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetDomain']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_domain_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetDomain']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")
    _get_records_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecords']/ows:Parameter[@name='outputFormat']/ows:Value")
    _get_records_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecords']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_records_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecords']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")
    _get_record_by_id_mime_types = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecordById']/ows:Parameter[@name='outputFormat']/ows:Value")
    _get_record_by_id_get_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecordById']/ows:DCP/ows:HTTP/ows:Get/@xlink:href")
    _get_record_by_id_post_url = StringField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecordById']/ows:DCP/ows:HTTP/ows:Post/@xlink:href")

    get_records_constraints = StringListField(
        xpath="./ows:OperationsMetadata/ows:Operation[@name='GetRecords']/ows:Constraint/ows:Value")
