import datetime
from typing import Callable, Dict

from django.conf import settings
from django.contrib.gis.geos import Polygon
from django.utils import timezone
from isodate import (Duration, ISO8601Error, parse_date, parse_datetime,
                     parse_duration)
from isodate.isodatetime import datetime_isoformat
from isodate.isoduration import duration_isoformat
from ows_lib.xml_mapper.capabilities.mixins import OGCServiceMixin
from ows_lib.xml_mapper.mixins import CallbackList


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

    def transform_to_model(self) -> Dict:
        attr = {}
        if self.start:
            attr.update({"start": self.start})
        if self.stop:
            attr.update({"stop": self.stop})
        if self.resolution:
            attr.update({"resolution": self.resolution})
        return attr


class TimeDimensionMixin:
    # cache variable to store the parsed extent value
    _time_extents: CallbackList = None

    @property
    def time_extents(self):
        if not self._time_extents:
            self.__parse_extent()
        return self._time_extents

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
        self._time_extents = CallbackList(
            time_extents, callback=self.__serialize_time_extents)
        self.__serialize_time_extents()

    def __serialize_time_extents(self, *args, **kwargs):
        self._extent = ",".join([time_extent.to_xml_value()
                                 for time_extent in self.time_extents])

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
        intervals = self._extent.split(",")
        for interval in intervals:
            __extents.append(self.__parse_single_interval(interval=interval))
        return __extents

    def __parse_single_interval(self, interval) -> TimeExtent:
        split = interval.split("/")
        start, stop, resolution = self.__parse_extent_value(
            start=split[0], stop=split[1], resolution=split[2])
        return TimeExtent(start=start, stop=stop, resolution=resolution)

    def __parse_list_of_values(self) -> list[TimeExtent]:
        split = self._extent.split(",")
        _extents = []
        for value in split:
            _value = self.__parse_datetime_or_date(value)
            if _value:
                _extents.append(
                    TimeExtent(start=_value, stop=_value))
        return _extents

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
        __extents = []
        if self.name == "time" and self.units == "ISO8601":
            if "," in self._extent and "/" in self._extent:
                # case 4 of table C.2: A list of multiple interval
                __extents.extend(self.__parse_list_of_multiple_intervals())
            elif "/" in self._extent:
                # case 3 of table C.2: An interval defined by its lower and upper bounds and its resolution
                __extents.append(self.__parse_single_interval(
                    interval=self._extent))
            elif "," in self._extent:
                # case 2 of table C.2: a A list of multiple values
                __extents.extend(self.__parse_list_of_values())
            else:
                # case 1 of table C.2: one single value was detected
                _value = self.__parse_datetime_or_date(self._extent)
                if _value:
                    __extents.append(TimeExtent(start=_value, stop=_value))
        self._time_extents = CallbackList(
            __extents, callback=self.__serialize_time_extents)


class LayerMixin:
    def __str__(self):
        return self.identifier

    @property
    def _bbox_min_x(self):
        raise NotImplementedError

    @property
    def _bbox_min_y(self):
        raise NotImplementedError

    @property
    def _bbox_max_x(self):
        raise NotImplementedError

    @property
    def _bbox_max_y(self):
        raise NotImplementedError

    @property
    def bbox_lat_lon(self) -> Polygon:
        # there is no default xmlmap field which parses to a geos polygon. So we convert it here.
        if self._bbox_min_x and self._bbox_max_x and self._bbox_min_y and self._bbox_max_y:
            return Polygon(
                (
                    (self._bbox_min_x, self._bbox_min_y),
                    (self._bbox_min_x, self._bbox_max_y),
                    (self._bbox_max_x, self._bbox_max_y),
                    (self._bbox_max_x, self._bbox_min_y),
                    (self._bbox_min_x, self._bbox_min_y)
                )
            )

    @bbox_lat_lon.setter
    def bbox_lat_lon(self, polygon: Polygon) -> None:
        # Custom setter function to mapp the geos Polygon object back to the xml attributes
        self._bbox_min_x = polygon.extent[0]
        self._bbox_min_y = polygon.extent[1]
        self._bbox_max_x = polygon.extent[2]
        self._bbox_max_y = polygon.extent[3]

    @property
    def descendants(self, include_self=True):
        descendants = [self] if include_self else []
        for child in self.children:
            descendants.extend(child.descendants)
        return descendants


class WebMapServiceMixin(OGCServiceMixin):
    """Abstract class for WebMapService xml mappers,
    which implements functionality for global usage."""

    _possible_operations = ["GetCapabilities", "GetMap",
                            "GetFeatureInfo", "DescribeLayer", "GetLegendGraphic", "GetStyles"]

    @property
    def layers(self):
        """Flat list of all layers of this web map service"""
        __layers = []
        __layers.extend(self.root_layer.descendants)
        return __layers

    def get_layer_by_identifier(self, identifier: str):
        return next((layer for layer in self.layers if layer.identifier == identifier), None)
