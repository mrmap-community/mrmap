from lxml import etree

from registry.models.metadata import TimeExtent
from dateutil.parser import isoparse
from dateutil import parser
from datetime import timedelta, UTC
from dateutil.parser import ParserError
from psycopg.types.range import Range
from django.utils import timezone


def parse_reference_systems(mapper, crs_str):
    """
    Parst alle DefaultCRS und OtherCRS des aktuellen FeatureType.

    """
    if isinstance(crs_str, etree._Element):
        raise ValueError("Expected string, got Element")
    
    code = ""
    prefix = ""
    if "http://www.opengis.net/def/crs/EPSG" in crs_str:
        code = crs_str.split("/")[-1]
        prefix = "EPSG"
    else:
        code = crs_str.split(":")[-1]
        prefix = "EPSG"
    return prefix, code

def parse_code(mapper, crs_str):
    """
    Parst den Code aus einem CRS String.
    """
    if not isinstance(crs_str, str):
        raise ValueError(f"Expected string, got {type(crs_str)}")
    _, code = parse_reference_systems(mapper, crs_str)
    return code

def parse_prefix(mapper, crs_str):
    """
    Parst den Code aus einem CRS String.
    """
    if not isinstance(crs_str, str):
        raise ValueError(f"Expected string, got {type(crs_str)}")
    prefix, _ = parse_reference_systems(mapper, crs_str)
    return prefix



def parse_timeextent(mapper, time_extent_element):
    """
    Parst die Zeitangaben aus den EX_TemporalExtent Elementen.

    Erwartet eine Liste von lxml Elementen.
    """
    nsmap = mapper.mapping.get("_namespaces", None)
    begin_position = time_extent_element.findtext("./gml:TimePeriod/gml:beginPosition", namespaces=nsmap)
    end_position = time_extent_element.findtext("./gml:TimePeriod/gml:endPosition", namespaces=nsmap)
    # ISO 8601 Duration
    duration_str = time_extent_element.findtext("./gml:TimePeriod/gml:duration", namespaces=nsmap)
    
    interval_value = time_extent_element.xpath("./gml:TimePeriod/gml:timeInterval/text()", namespaces=nsmap)
    interval_unit = time_extent_element.xpath("./gml:TimePeriod/gml:timeInterval/@unit", namespaces=nsmap)
    resolution = None
    if duration_str:
        try:
            # Use dateutil.parser to parse the duration string into a datetime object
            parsed = parser.parse(duration_str)
            # Convert the parsed datetime to a timedelta (if applicable)
            resolution = timedelta(days=parsed.day, seconds=parsed.second, microseconds=parsed.microsecond)
        except ParserError:
            raise ValueError(f"Invalid duration format: {duration_str}")

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
                timerange=Range(dt_start, dt_end, bounds="[]"),
                resolution=resolution
            )
    if begin_position and not end_position:
        dt = isoparse(begin_position)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone=UTC)
        if dt:
            return TimeExtent(
                timerange=Range(dt, dt, bounds="[]"),
                resolution=resolution
            )   
