
import datetime
from collections.abc import Iterable
from typing import Callable, List
from urllib import parse

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.utils import timezone
from eulxml.xmlmap import (FloatField, IntegerField, NodeField, NodeListField,
                           SimpleBooleanField, StringField, StringListField,
                           XmlObject)
from isodate.duration import Duration
from isodate.isodates import parse_date
from isodate.isodatetime import datetime_isoformat, parse_datetime
from isodate.isoduration import duration_isoformat, parse_duration
from isodate.isoerror import ISO8601Error
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


class TimeExtent:
    """Helper class to abstract single time extent objects"""

    def __init__(
            self,
            start: datetime.datetime,
            stop: datetime.datetime = None,
            resolution: int = None,
            callback: Callable = None,
            *args,
            **kwargs):
        super().__init__(*args, **kwargs)
        self.__start = start
        self.__stop = stop
        self.__resolution = resolution
        self._callback = callback

    @property
    def start(self) -> datetime.datetime:
        return self.__start

    @start.setter
    def start(self, value: datetime.datetime) -> None:
        self.__start = value
        if self._callback:
            self._callback(self)

    @property
    def stop(self) -> datetime.datetime:
        return self.__stop

    @stop.setter
    def stop(self, value: datetime.datetime) -> None:
        self.__stop = value
        if self._callback:
            self._callback(self)

    @property
    def resolution(self) -> int:
        return self.__resolution

    @resolution.setter
    def resolution(self, value: int) -> None:
        self.__resolution = value
        if self._callback:
            self._callback(self)

    @property
    def is_value(self):
        return self.start and not self.stop and not self.resolution

    @property
    def is_interval(self):
        return self.start and self.stop and self.resolution

    @property
    def is_valid(self):
        return self.is_value or self.is_interval

    def to_xml_value(self) -> str:
        if self.is_value:
            return datetime_isoformat(self.start)
        elif self.is_interval:
            if self.resolution == 0:
                return f"{datetime_isoformat(self.start)}/{datetime_isoformat(self.stop)}/0"
            else:
                return f"{datetime_isoformat(self.start)}/{datetime_isoformat(self.stop)}/{duration_isoformat(self.resolution)}"

    def __str__(self) -> str:
        return f"{self.start} | {self.stop} | {self.resolution}"


class TimeDimension(WebMapServiceDefaultSettings):
    """ Time Dimension in ISO8601 format"""

    ROOT_NAME = "wms:Dimension[@name='time']"

    name = StringField(xpath="./@name", choices="time")
    units = StringField(xpath="./@units", choices="ISO8601")

    __extent = StringField(xpath="./text()")

    _extent = []  # cache variable to store the parsed extent value

    @property
    def time_extents(self):
        if not self._extent:
            self.__parse_extent()
        return self._extent

    @time_extents.setter
    def time_extents(self, time_extents: list[TimeExtent]) -> None:
        """Custom setter function to serialize a list of TimeExtent objects and update it to the xml node"""
        values = []
        intervals = []
        not_valid = []

        for time_extent in time_extents:
            if not time_extent._callback:
                time_extent._callback = self.__parse_extent
            if not time_extent.is_valid:
                raise ValueError(
                    f"time extent objects is not valid: {time_extent}")
            if time_extent.is_value:
                values.append(time_extent)
            elif time_extent.is_interval:
                intervals.append(time_extent)

        if values and intervals:
            raise ValueError("mixing values and intervals is not supported.")

        if not_valid:
            raise ValueError("some passed time extent objects are not valid")

        self.__extent = ",".join([value for value in time_extents])
        self._extent = []

    def __parse_extent_value(self, start, stop, resolution) -> tuple:
        _start = parse_datetime(start)  # iso date time
        _stop = parse_datetime(stop)  # iso date time
        try:
            _resolution = int(resolution)
        except ValueError:
            _resolution = parse_duration(resolution)
            if isinstance(_resolution, Duration):
                _resolution = _resolution.totimedelta(start=timezone.now())
        return _start, _stop, _resolution

    def __parse_datetime_or_date(self, value):
        _value = None
        try:
            _value = parse_datetime(value)
        except ISO8601Error:
            try:
                _value = parse_date(value)
            except ISO8601Error:
                settings.ROOT_LOGGER.debug(
                    msg=f"can't parse time dimension from value: {value}")

        return _value

    def __parse_list_of_multiple_intervals(self) -> list[TimeExtent]:
        __extents = []
        intervals = self.__extent.split(",")
        for interval in intervals:
            __extents.append(self.__parse_single_interval(interval=interval))
        return __extents

    def __parse_single_interval(self, interval) -> TimeExtent:
        split = interval.split("/")
        start, stop, resolution = self.__parse_extent_value(
            start=split[0], stop=split[1], resolution=split[2])
        return TimeExtent(start=start, stop=stop, resolution=resolution)

    def __parse_list_of_values(self) -> list[TimeExtent]:
        split = self.__extent.split(",")
        for value in split:
            _value = self.__parse_datetime_or_date(value)
            if _value:
                self.extents.append(TimeExtent(start=_value, stop=_value))

    def __parse_extent(self, *args, **kwargs):
        """
            OGC WMS 1.3.0 Spech page 53:

            Table C.2 — Syntax for listing one or more extent values

            value 								A single value.
            value1,value2,value3,... 			a A list of multiple values.
            min/max/resolution 					An interval defined by its lower and upper bounds and its resolution.
            min1/max1/res1,min2/max2/res2,... 	a A list of multiple intervals.

            A resolution value of zero (as in min/max/0) means that the data are effectively at infinitely-fine resolution for the
            purposes of making requests on the server. For instance, an instrument which continuously monitors randomly-
            occurring data may have no explicitly defined temporal resolution.
        """

        # ogc wms dimension supports more thant time in iso 8601 format.
        # But for now we only implement this, cause other ones are not common usage
        if self.name == "time" and self.units == "ISO8601":
            if "," in self.__extent and "/" in self.__extent:
                # case 4 of table C.2: A list of multiple interval
                self._extent.extend(self.__parse_list_of_multiple_intervals())
            elif "/" in self.__extent:
                # case 3 of table C.2: An interval defined by its lower and upper bounds and its resolution
                self._extent.append(self.__parse_single_interval(
                    interval=self.__extent))
            elif "," in self.__extent:
                # case 2 of table C.2: a A list of multiple values
                self.__parse_list_of_values()
            else:
                # case 1 of table C.2: one single value was detected
                _value = self.__parse_datetime_or_date(self.__extent)
                if _value:
                    self._extent.append(TimeExtent(start=_value, stop=_value))


class ReferenceSystem(WebMapServiceDefaultSettings):

    __ref_system = StringField(xpath=".")
    __code = None
    __prefix = None

    def __extract_ref_system(self) -> None:
        if "::" in self.__ref_system:
            # example: ref_system = urn:ogc:def:crs:EPSG::4326
            code = self.__ref_system.rsplit(":")[-1]
            prefix = self.__ref_system.rsplit(":")[-3]
        elif ":" in self.__ref_system:
            # example: ref_system = EPSG:4326
            code = self.__ref_system.rsplit(":")[-1]
            prefix = self.__ref_system.rsplit(":")[-2]
        else:
            raise SemanticError("reference system unknown")

        self.__code = code
        self.__prefix = prefix

    @property
    def code(self) -> str:
        if not self.__code:
            self.__extract_ref_system()
        return self.__code

    @code.setter
    def code(self, new_code) -> None:
        self.__ref_system = f"{self.__prefix}:{new_code}"

    @property
    def prefix(self) -> str:
        if not self.__prefix:
            self.__extract_ref_system()
        return self.__prefix

    @prefix.setter
    def prefix(self, new_prefix) -> None:
        self.__ref_system = f"{new_prefix}:{self.__code}"


class LegendUrl(WebMapServiceDefaultSettings):
    ROOT_NAME = "wms:LegendUrl"

    legend_url = StringField(
        xpath="./wms:OnlineResource[@xlink:type='simple']/@xlink:href")
    height = IntegerField(xpath="./@height")
    width = IntegerField(xpath="./@width")
    mime_type = StringField(xpath="./wms:Format")


class Style(WebMapServiceDefaultSettings):
    ROOT_NAME = "wms:Style"

    name = StringField(xpath="./wms:Name")
    title = StringField(xpath="./wms:Title")
    legend_url = NodeField(xpath="./wms:LegendURL", node_class=LegendUrl)


class LayerMetadata(WebMapServiceDefaultSettings):
    title = StringField(xpath="./wms:Title")
    abstract = StringField(xpath="./wms:Abstract")
    keywords = StringListField(xpath="./wms:KeywordList/wms:Keyword")


class Layer(WebMapServiceDefaultSettings):

    ROOT_NAME = "wms:Layer"

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

    metadata = NodeField(xpath=".", node_class=LayerMetadata)
    remote_metadata = StringListField(
        xpath="./wms:MetadataURL/wms:OnlineResource[@xlink:type='simple']/@xlink:href")

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
            operation_url.url = replaced.geturl()
