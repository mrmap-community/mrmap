from datetime import UTC, timedelta
from logging import Logger

import isodate
from dateutil.parser import isoparse
from django.conf import settings
from django.utils import timezone
from lxml import etree
from registry.models.metadata import ReferenceSystem, TimeExtent

logger: Logger = settings.ROOT_LOGGER


def parse_reference_system(mapper, el: etree._Element):
    crs_str = el.text.strip()

    code = ""
    prefix = ""
    if "http://www.opengis.net/def/crs/EPSG" in crs_str:
        code = crs_str.split("/")[-1]
        prefix = "EPSG"
    else:
        code = crs_str.split(":")[-1]
        prefix = "EPSG"
    return ReferenceSystem(prefix=prefix, code=code)


def serialize_reference_system(mapper, instance: ReferenceSystem):
    return f"http://www.opengis.net/def/crs/EPSG/0/{instance.code}"


def parse_timeextent(mapper, time_extent_element):
    """
    Parst die Zeitangaben aus den EX_TemporalExtent Elementen.

    Erwartet eine Liste von lxml Elementen.
    """
    nsmap = mapper.mapping.get("_namespaces", None)
    begin_position = time_extent_element.findtext(
        "./gml:TimePeriod/gml:beginPosition", namespaces=nsmap)
    end_position = time_extent_element.findtext(
        "./gml:TimePeriod/gml:endPosition", namespaces=nsmap)
    # ISO 8601 Duration
    duration_str = time_extent_element.findtext(
        "./gml:TimePeriod/gml:duration", namespaces=nsmap)

    interval_value = time_extent_element.xpath(
        "./gml:TimePeriod/gml:timeInterval/text()", namespaces=nsmap)
    interval_unit = time_extent_element.xpath(
        "./gml:TimePeriod/gml:timeInterval/@unit", namespaces=nsmap)
    resolution = None
    if duration_str:
        duration = isodate.parse_duration(duration_str)

        # isodate may return datetime.timedelta or isodate.Duration
        if isinstance(duration, timedelta):
            resolution = duration
        else:
            # Convert Duration (years/months not supported by timedelta)
            resolution = duration.tdelta

    elif interval_value and interval_unit:
        """
        Parse a time interval expressed as a decimal number (e.g., '1.0') and a unit (e.g., 'hour') 
        into a timedelta object that Django's DurationField can accept.
        """
        if interval_unit == "hour":
            resolution = timedelta(hours=float(interval_value))
        elif interval_unit == "minute":
            resolution = timedelta(minutes=float(interval_value))
        elif interval_unit == "second":
            resolution = timedelta(seconds=float(interval_value))
        else:
            raise ValueError(f"Unsupported unit: {interval_value}")

    if begin_position and end_position:
        dt_start = isoparse(begin_position)
        dt_end = isoparse(end_position)
        if timezone.is_naive(dt_start):
            dt_start = timezone.make_aware(dt_start, timezone=UTC)
        if timezone.is_naive(dt_end):
            dt_end = timezone.make_aware(dt_end, timezone=UTC)
        if dt_start and dt_end:
            return TimeExtent(
                begin=dt_start,
                end=dt_end,
                resolution=resolution
            )
    if begin_position and not end_position:
        dt = isoparse(begin_position)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=UTC)
        if dt:
            return TimeExtent(
                begin=dt,
                end=dt,
                resolution=resolution
            )
    if not begin_position and not end_position and resolution:
        # rolling window
        return TimeExtent(
            begin=None,
            end=None,
            resolution=resolution,
            is_relative=True
        )

    logger.warning(
        f"Unable to parse TimeExtent from values: {begin_position} {end_position} {duration_str} {interval_value} {interval_unit}")
