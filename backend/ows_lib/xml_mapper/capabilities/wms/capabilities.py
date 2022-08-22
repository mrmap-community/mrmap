
from collections.abc import Iterable
from typing import Callable, List
from urllib import parse

from django.contrib.gis.geos import Polygon
from eulxml.xmlmap import (FloatField, NodeField, NodeListField,
                           SimpleBooleanField, StringField, StringListField,
                           XmlObject)
from ows_lib.xml_mapper.mixins import DBModelConverterMixin
from ows_lib.xml_mapper.namespaces import WMS_1_3_0_NAMESPACE, XLINK_NAMESPACE
from registry.xmlmapper.exceptions import SemanticError


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


class ServiceType(WebMapServiceDefaultSettings):
    ROOT_NAME = "wms:WMS_Capabilities/@version='1.3.0'"

    __name = StringField(xpath="./wms:Service/wms:Name")
    version = StringField(xpath="./@version", choices='1.3.0')

    @property
    def name(self) -> str:
        """ Custom property, cause the parsed name of the root element doesn't contains the right
            value for database. We need to parse again cause the root attribute contains different service type names
            as we store in our database.

            Returns:
                field_dict (dict): the dict which contains all needed information

            Raises:
                SemanticError if service name or version can not be found
        """
        if ":" in self.__name:
            name = self.__name.split(":", 1)[-1]
        elif " " in self.__name:
            name = self.__name.split(" ", 1)[-1]
        else:
            name = self.__name

        name = name.lower()

        if name not in ["wms", "wfs", "csw"]:
            raise SemanticError(f"could not determine the service type for the parsed capabilities document. "
                                f"Parsed name was {name}")

        return name

    @name.setter
    def name(self, value: str) -> None:
        self.__name = value


class Layer(WebMapServiceDefaultSettings):

    ROOT_NAME = "wms:Layer"

    is_leaf_node = False
    level = 0
    left = 0
    right = 0

    scale_min = FloatField(xpath="./wms:MinScaleDenominator")
    scale_max = FloatField(xpath="./wms:MaxScaleDenominator")

    __bbox_min_x = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:westBoundLongitude")
    __bbox_max_x = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:eastBoundLongitude")
    __bbox_min_y = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:southBoundLatitude")
    __bbox_max_y = FloatField(
        xpath="./wms:EX_GeographicBoundingBox/wms:northBoundLatitude")

    # TODO: reference_systems = NodeListField(xpath="wms:CRS", node_class=ReferenceSystem)
    identifier = StringField(xpath="./wms:Name")
    # TODO: styles = NodeListField(xpath="wms:Style", node_class=Style)
    is_queryable = SimpleBooleanField(
        xpath="./@queryable", true=1, false=0)
    is_opaque = SimpleBooleanField(xpath="./@opaque", true=1, false=0)
    is_cascaded = SimpleBooleanField(
        xpath="./@cascaded", true=1, false=0)
    # TODO: dimensions = NodeListField(xpath="wms:Dimension", node_class=Dimension130)
    parent = NodeField(xpath="../../wms:Layer", node_class="self")
    children = NodeListField(xpath="./wms:Layer", node_class="self")

    # TODO: metadata = NodeField(xpath=".", node_class=LayerMetadata)
    # TODO: remote_metadata = NodeListField(xpath="wms:MetadataURL", node_class=WebMapServiceRemoteMetadata)

    @property
    def bbox_lat_lon(self) -> Polygon:
        # there is no default xmlmap field which parses to a geos polygon. So we convert it here.
        if self.__bbox_min_x and self.__bbox_max_x and self.__bbox_min_y and self.__bbox_max_y:
            return Polygon(
                (
                    (self.__bbox_min_x, self.__bbox_min_y),
                    (self.__bbox_min_x, self.__bbox_max_y),
                    (self.__bbox_max_x, self.__bbox_max_y),
                    (self.__bbox_max_x, self.__bbox_min_y),
                    (self.__bbox_min_x, self.__bbox_min_y)
                )
            )

    @bbox_lat_lon.setter
    def bbox_lat_lon(self, polygon: Polygon) -> None:
        # Custom setter function to mapp the geos Polygon object back to the xml attributes
        self.__bbox_min_x = polygon.extent[0]
        self.__bbox_min_y = polygon.extent[1]
        self.__bbox_max_x = polygon.extent[2]
        self.__bbox_max_y = polygon.extent[3]

    def get_field_dict(self):
        dic = super().get_field_dict()
        dic.update({"bbox_lat_lon": self.bbox_lat_lon})
        return dic


class WebMapService(WebMapServiceDefaultSettings):
    ROOT_NAME = "wms:WMS_Capabilities/@version='1.3.0'"
    XSD_SCHEMA = "https://schemas.opengis.net/wms/1.3.0/capabilities_1_3_0.xsd"

    service_url = StringField(
        xpath="./wms:Service/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

    service_type = NodeField(xpath=".", node_class=ServiceType)
    service_metadata: ServiceMetadata = NodeField(
        xpath="./wms:Service", node_class=ServiceMetadata)

    root_layer = NodeField(
        xpath="wms:Capability/wms:Layer", node_class=Layer)

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
