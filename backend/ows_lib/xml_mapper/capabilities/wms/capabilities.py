
from typing import Callable, List

from eulxml.xmlmap import NodeField, NodeListField, StringField, XmlObject
from ows_lib.xml_mapper.mixins import DBModelConverterMixin
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE


class WebMapServiceDefaultSettings(DBModelConverterMixin, XmlObject):
    ROOT_NS = "wms"
    ROOT_NAMESPACES = {
        "wms": WMS_1_3_0_NAMESPACE,
        "xlink": XLINK_NAMESPACE
    }


class Keyword(WebMapServiceDefaultSettings):
    ROOT_NAME = "Keyword"

    keyword = StringField(xpath=".")


class Format(WebMapServiceDefaultSettings):
    ROOT_NAME = "Format"

    mime_type = StringField(xpath=".")


class ServiceMetadataContact(WebMapServiceDefaultSettings):
    ROOT_NAME = "ContactInformation"

    name = StringField(
        xpath="wms:ContactPersonPrimary/wms:ContactOrganization")
    person_name = StringField(
        xpath="wms:ContactPersonPrimary/wms:ContactPerson")
    phone = StringField(xpath="wms:ContactVoiceTelephone")
    facsimile = StringField(xpath="wms:ContactFacsimileTelephone")
    email = StringField(xpath="wms:ContactElectronicMailAddress")
    country = StringField(xpath="wms:ContactAddress/wms:Country")
    postal_code = StringField(xpath="wms:ContactAddress/wms:PostCode")
    city = StringField(xpath="wms:ContactAddress/wms:City")
    state_or_province = StringField(
        xpath="wms:ContactAddress/wms:StateOrProvince")
    address = StringField(xpath="wms:ContactAddress/wms:Address")


class ServiceMetadata(WebMapServiceDefaultSettings):
    ROOT_NAME = "Service"

    title = StringField(xpath="wms:Title")
    abstract = StringField(xpath="wms:Abstract")
    fees = StringField(xpath="wms:Fees")
    access_constraints = StringField(xpath="wms:AccessConstraints")

    # ForeignKey
    service_contact = NodeField(xpath="wms:ContactInformation",
                                node_class=ServiceMetadataContact)

    # ManyToManyField
    keywords = NodeListField(xpath="wms:KeywordList/wms:Keyword",
                             node_class=Keyword)


class OperationUrl:
    """Helper class to flatten operationurl information which are stored in the xml path."""

    def __init__(self, method: str, operation: str, mime_types: list, url: str) -> None:
        self.method = method
        self.operation = operation
        self.mime_types = mime_types
        self.url = url


class CallbackList(list):

    def __init__(self, iterable, callback: Callable, *args, **kwargs) -> None:
        super().__init__(iterable, *args, **kwargs)
        self.callback = callback

    def append(self, item) -> None:
        super().append(item)
        self.callback(list_operation="append", items=item)

    def extend(self, items) -> None:
        super().extend(items)
        self.callback(list_operation="extend", items=items)

    def pop(self, __index):
        super().pop(__index)
        self.callback(list_operation="pop", index=__index)

    def clear(self) -> None:
        super().clear()
        self.callback(list_operation="clear")

    def insert(self, __index, __object) -> None:
        super().insert(__index, __object)
        self.callback(list_operation="insert", index=__index, items=__object)

    def remove(self, __value) -> None:
        super().remove(__value)
        self.callback(list_operation="remove", items=__value)


class WebMapService(WebMapServiceDefaultSettings):
    ROOT_NAME = f"wms:WMS_Capabilities/@version='1.3.0'"
    XSD_SCHEMA = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    service_url = StringField(
        xpath="./wms:Service/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    version = StringField(xpath="./@version", choices='1.3.0')

    # TODO: service_type = NodeField(xpath=".", node_class=ServiceType)
    service_metadata: ServiceMetadata = NodeField(
        xpath="./wms:Service", node_class=ServiceMetadata)

    # cause the information of operation urls are stored as entity name inside the xpath, we need to parse every operation url seperate.
    # To simplify the access of operation_urls we write a custom getter and setter property for it.
    # With that technique the usage of this mapper is easier and matches the db model
    __get_capabilitites_mime_types = NodeListField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:Format", node_class=Format)
    __get_capabilitites_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_capabilitites_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    __get_map_mime_types = NodeListField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:Format", node_class=Format)
    __get_map_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_map_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    __get_feature_info_mime_types = NodeListField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:Format", node_class=Format)
    __get_feature_info_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_feature_info_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    __operation_urls: CallbackList = None

    def __clear_all_operation_urls(self):
        self.__get_capabilitites_mime_types = []
        self.__get_capabilitites_get_url = None
        self.__get_capabilitites_post_url = None
        self.__get_map_mime_types = []
        self.__get_map_get_url = None
        self.__get_map_post_url = None
        self.__get_feature_info_mime_types = []
        self.__get_feature_info_get_url = None
        self.__get_feature_info_post_url = None

    def __manipulate_operation_urls(self, list_operation, index=None, items=None):
        """Custom setter to set/append new operation urls. The XML will be build implicitly by using this setter."""

        match list_operation:
            case "append":
                self.__handle_new_operation_url(items)
            case "extend":
                [self.__handle_new_operation_url(item) for item in items]
            case "pop":
                # TODO: implement pop
                pass
            case "clear":
                self.__clear_all_operation_urls()
            case "insert":
                # TODO: implement insert
                pass
            case "remove":
                # TODO: implement remove
                pass

    @property
    def __get_capabilities_operation_urls(self) -> List[OperationUrl]:
        _operation_urls: List[OperationUrl] = []
        if self.__get_capabilitites_get_url:
            _operation_urls.append(
                OperationUrl(
                    method="Get",
                    operation="GetCapabilities",
                    mime_types=self.__get_capabilitites_mime_types,
                    url=self.__get_capabilitites_get_url)
            )
        if self.__get_capabilitites_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetCapabilities",
                    mime_types=self.__get_capabilitites_mime_types,
                    url=self.__get_capabilitites_post_url)
            )
        return _operation_urls

    @property
    def __get_map_operation_urls(self) -> List[OperationUrl]:
        _operation_urls: List[OperationUrl] = []
        if self.__get_map_get_url:
            _operation_urls.append(
                OperationUrl(
                    method="Get",
                    operation="GetMap",
                    mime_types=self.__get_map_mime_types,
                    url=self.__get_map_get_url)
            )
        if self.__get_map_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetMap",
                    mime_types=self.__get_map_mime_types,
                    url=self.__get_map_post_url)
            )
        return _operation_urls

    @property
    def __get_feature_info_operation_urls(self) -> List[OperationUrl]:
        _operation_urls: List[OperationUrl] = []
        if self.__get_feature_info_get_url:
            _operation_urls.append(
                OperationUrl(
                    method="Get",
                    operation="GetFeatureInfo",
                    mime_types=self.__get_feature_info_mime_types,
                    url=self.__get_feature_info_get_url)
            )
        if self.__get_map_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetFeatureInfo",
                    mime_types=self.__get_feature_info_mime_types,
                    url=self.__get_feature_info_post_url)
            )
        return _operation_urls

    @property
    def operation_urls(self) -> List[OperationUrl]:
        """Custom getter to merge all operation urls as plane OperationUrl object."""
        if not self.__operation_urls:

            _operation_urls = []
            _operation_urls.extend(self.__get_capabilities_operation_urls)
            _operation_urls.extend(self.__get_map_operation_urls)
            _operation_urls.extend(self.__get_feature_info_operation_urls)

            self.__operation_urls = CallbackList(
                _operation_urls, callback=self.__manipulate_operation_urls)

        return self.__operation_urls

    def __handle_new_operation_url(self, new_operation_url):

        match new_operation_url.operation:
            case "GetCapabilities":
                # TODO: check if new_operation_url.mime_type exists in self.__get_capabilitites_mime_types and append it if not
                if new_operation_url.method == "Get":
                    self.__get_capabilitites_get_url = new_operation_url.url
                elif new_operation_url.method == "Post":
                    self.__get_capabilitites_post_url = new_operation_url.url
            case "GetMap":
                # TODO: check if new_operation_url.mime_type exists in self.__get_capabilitites_mime_types and append it if not
                if new_operation_url.method == "Get":
                    self.__get_map_get_url = new_operation_url.url
                elif new_operation_url.method == "Post":
                    self.__get_map_post_url = new_operation_url.url
            case "GetFeatureInfo":
                # TODO: check if new_operation_url.mime_type exists in self.__get_capabilitites_mime_types and append it if not
                if new_operation_url.method == "Get":
                    self.__get_feature_info_get_url = new_operation_url.url
                elif new_operation_url.method == "Post":
                    self.__get_feature_info_post_url = new_operation_url.url
            case _:
                raise ValueError("unsuported operation")

    # TODO: all_layers = None
