
from collections.abc import Iterable
from typing import Callable, List
from urllib import parse

from eulxml.xmlmap import NodeField, StringField, StringListField, XmlObject
from ows_lib.xml_mapper.mixins import DBModelConverterMixin
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE


class WebMapServiceDefaultSettings(DBModelConverterMixin, XmlObject):
    ROOT_NS = "wms"
    ROOT_NAMESPACES = {
        "wms": WMS_1_3_0_NAMESPACE,
        "xlink": XLINK_NAMESPACE
    }


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
    keywords = StringListField(xpath="wms:KeywordList/wms:Keyword")


class OperationUrl:
    """Helper class to flatten operationurl information which are stored in the xml path."""

    def __init__(self, method: str, operation: str, mime_types: list[str], url: str, callback: Callable = None) -> None:
        self.__method = method
        self.__operation = operation
        self.__mime_types = mime_types
        self.__url = url
        self._callback = callback

    def __str__(self) -> str:
        return f"op: {self.operation} | http method: {self.method} | url: {self.url}"

    @property
    def method(self) -> str:
        return self.__method

    @method.setter
    def method(self, value: str) -> None:
        """Custom setter to trigger callback function to update xml nodes"""
        self.__method = value
        if self._callback:
            self._callback(self)

    @property
    def operation(self) -> str:
        return self.__operation

    @operation.setter
    def operation(self, value: str) -> None:
        self.__operation = value
        if self._callback:
            self._callback(self)

    @property
    def url(self) -> str:
        return self.__url

    @url.setter
    def url(self, value: str) -> None:
        self.__url = value
        if self._callback:
            self._callback(self)

    @property
    def mime_types(self) -> list[str]:
        return self.__mime_types

    @mime_types.setter
    def mime_types(self, value: list[str]):
        self.__mime_types = value
        if self._callback:
            self._callback(self)


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
        operation_url_to_pop = self[__index]
        super().pop(__index)
        self.callback(list_operation="pop", items=operation_url_to_pop)

    def clear(self) -> None:
        super().clear()
        self.callback(list_operation="clear")

    def insert(self, __index, __object) -> None:
        super().insert(__index, __object)
        self.callback(list_operation="insert", items=__object)

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
    __get_capabilitites_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:Format")
    __get_capabilitites_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_capabilitites_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetCapabilities/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    __get_map_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:Format")
    __get_map_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_map_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetMap/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    __get_feature_info_mime_types = StringListField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:Format")
    __get_feature_info_get_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Get/wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    __get_feature_info_post_url = StringField(
        xpath="./wms:Capability/wms:Request/wms:GetFeatureInfo/wms:DCPType/wms:HTTP/wms:Post/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    def __update_or_create_operation_url_xml_node(self, operation_url: OperationUrl):
        match operation_url.operation:
            case "GetCapabilities":
                new_mime_types = filter(
                    lambda mime_type: mime_type not in self.__get_capabilitites_mime_types, operation_url.mime_types)
                self.__get_capabilitites_mime_types.extend(new_mime_types)
                if operation_url.method == "Get":
                    self.__get_capabilitites_get_url = operation_url.url
                elif operation_url.method == "Post":
                    self.__get_capabilitites_post_url = operation_url.url
            case "GetMap":
                new_mime_types = filter(
                    lambda mime_type: mime_type not in self.__get_map_mime_types, operation_url.mime_types)
                self.__get_map_mime_types.extend(new_mime_types)
                if operation_url.method == "Get":
                    self.__get_map_get_url = operation_url.url
                elif operation_url.method == "Post":
                    self.__get_map_post_url = operation_url.url
            case "GetFeatureInfo":
                new_mime_types = filter(
                    lambda mime_type: mime_type not in self.__get_feature_info_mime_types, operation_url.mime_types)
                self.__get_feature_info_mime_types.extend(new_mime_types)
                if operation_url.method == "Get":
                    self.__get_feature_info_get_url = operation_url.url
                elif operation_url.method == "Post":
                    self.__get_feature_info_post_url = operation_url.url
            case _:
                raise ValueError(
                    f"unsuported operation: {operation_url.operation}")

    def __operation_has_get_and_post(self, operation_url: OperationUrl) -> bool:
        return self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Get") and self.get_operation_url_by_name_and_method(name=operation_url.operation, method="Post")

    def __remove_operation_url_xml_node(self, operation_url: OperationUrl):

        match operation_url.operation:
            case "GetCapabilities":
                if operation_url.method == "Get":
                    self.__get_capabilitites_get_url = None
                elif operation_url.method == "Post":
                    self.__get_capabilitites_post_url = None
                if not self.__operation_has_get_and_post(operation_url):
                    self.__get_capabilitites_mime_types = []
            case "GetMap":
                if operation_url.method == "Get":
                    self.__get_map_get_url = None
                elif operation_url.method == "Post":
                    self.__get_map_post_url = None
                if not self.__operation_has_get_and_post(operation_url):
                    self.__get_map_mime_types = []
            case "GetFeatureInfo":
                if operation_url.method == "Get":
                    self.__get_feature_info_get_url = None
                elif operation_url.method == "Post":
                    self.__get_feature_info_post_url = None
                if not self.__operation_has_get_and_post(operation_url):
                    self.__get_feature_info_mime_types = []
            case _:
                raise ValueError(
                    f"unsuported operation: {operation_url.operation}")

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

    def __handle_list_operation(self, list_operation, items: OperationUrl = None):
        """Custom setter to set/append new operation urls. The XML will be build implicitly by using this setter."""

        if isinstance(items, Iterable):
            for item in items:
                if not item._update:
                    item._update = self.__update_or_create_operation_url_xml_node
        else:
            if items and not items._callback:
                items._callback = self.__update_or_create_operation_url_xml_node

        match list_operation:
            case "append" | "insert":
                self.__update_or_create_operation_url_xml_node(items)
            case "extend":
                [self.__update_or_create_operation_url_xml_node(
                    item) for item in items]
            case "pop" | "remove":
                self.__remove_operation_url_xml_node(items)
            case "clear":
                self.__clear_all_operation_urls()

    @property
    def __get_capabilities_operation_urls(self) -> List[OperationUrl]:
        _operation_urls: List[OperationUrl] = []
        if self.__get_capabilitites_get_url:
            _operation_urls.append(
                OperationUrl(
                    method="Get",
                    operation="GetCapabilities",
                    mime_types=self.__get_capabilitites_mime_types,
                    url=self.__get_capabilitites_get_url,
                    callback=self.__update_or_create_operation_url_xml_node)
            )
        if self.__get_capabilitites_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetCapabilities",
                    mime_types=self.__get_capabilitites_mime_types,
                    url=self.__get_capabilitites_post_url,
                    callback=self.__update_or_create_operation_url_xml_node)
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
                    url=self.__get_map_get_url,
                    callback=self.__update_or_create_operation_url_xml_node)
            )
        if self.__get_map_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetMap",
                    mime_types=self.__get_map_mime_types,
                    url=self.__get_map_post_url,
                    callback=self.__update_or_create_operation_url_xml_node)
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
                    url=self.__get_feature_info_get_url,
                    callback=self.__update_or_create_operation_url_xml_node)
            )
        if self.__get_map_post_url:
            _operation_urls.append(
                OperationUrl(
                    method="Post",
                    operation="GetFeatureInfo",
                    mime_types=self.__get_feature_info_mime_types,
                    url=self.__get_feature_info_post_url,
                    callback=self.__update_or_create_operation_url_xml_node)
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
                _operation_urls, callback=self.__handle_list_operation)

        return self.__operation_urls

    def get_operation_url_by_name_and_method(self, name, method) -> OperationUrl:
        return next((operation_url for operation_url in self.operation_urls if operation_url.operation == name and operation_url.method == method), None)

    def camouflage_urls(self, new_domain: str, scheme: str = None) -> None:
        for operation_url in self.operation_urls:
            parsed = parse.urlparse(operation_url.url)
            if scheme:
                replaced: parse.ParseResult = parsed._replace(
                    netloc=new_domain, scheme=scheme)
            else:
                replaced: parse.ParseResult = parsed._replace(
                    netloc=new_domain)
            operation_url = replaced.geturl()

    # TODO: all_layers = None
