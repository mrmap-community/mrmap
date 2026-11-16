from datetime import UTC, timedelta
from logging import Logger
from uuid import uuid4

import isodate
from dateutil.parser import isoparse
from django.conf import settings
from django.utils import timezone
from lxml import etree
from registry.enums.iso import CategoryChoices
from registry.models.metadata import IsoCategory, ReferenceSystem, TimeExtent

logger: Logger = settings.ROOT_LOGGER


def parse_reference_system(_mapper, el: etree._Element | etree._ElementUnicodeResult):

    # An element without character content is a missing value, not an import
    # error: lxml answers None for the text of an empty
    # <gco:CharacterString/>, which a publisher leaves inside
    # <gmd:referenceSystemInfo> the same way #989 found it inside
    # <gmd:topicCategory>. It is read as the empty text the character branch
    # already answers, and a reference system without a code is skipped - that
    # costs the reference system at most, never the record (#1074).
    crs_str = (el.text or "").strip() if isinstance(
        el, etree._Element) else el.strip()
    if not crs_str:
        return

    code = ""
    prefix = ""
    if "http://www.opengis.net/def/crs/EPSG" in crs_str:
        code = crs_str.split("/")[-1]
        prefix = "EPSG"
    else:
        code = crs_str.split(":")[-1]
        prefix = "EPSG"
    return ReferenceSystem(prefix=prefix, code=code)


def serialize_reference_system(_mapper, instance: ReferenceSystem):
    return f"http://www.opengis.net/def/crs/EPSG/0/{instance.code}"


def parse_topic_category(_mapper, el: etree._Element | etree._ElementUnicodeResult):
    # An element without character content is a missing value, not an import
    # error: lxml answers None for the text of an empty
    # <gmd:MD_TopicCategoryCode/>, which is the ordinary shape of an optional
    # element a publisher leaves in the record. It is read as the empty text
    # the character branch already answers - CategoryChoices('') is no
    # choice, so the parser answers None and the record imports without that
    # category (#989).
    category_str = (el.text or "").strip() if isinstance(
        el, etree._Element) else el.strip()
    value = CategoryChoices(category_str)
    if value:
        return IsoCategory(value=value)


def serialize_topic_category(_mapper, instance: IsoCategory):
    return CategoryChoices(instance.value).label


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
    resolution = _resolution_of(duration_str, interval_value, interval_unit)

    if begin_position and end_position:
        return _extent_between(
            mapper, begin_position, end_position, resolution)
    if begin_position and not end_position:
        dt = _utc_aware(isoparse(begin_position))
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

    if not any((begin_position, end_position, duration_str,
                interval_value, interval_unit)):
        # an EMPTY placeholder element carries nothing - that is the state
        # the write mapper of #1246 fills, not a value it failed to read
        return None

    logger.warning(
        f"Unable to parse TimeExtent from values: {begin_position} {end_position} {duration_str} {interval_value} {interval_unit}")


def _resolution_of(duration_str, interval_value, interval_unit):
    """The resolution the duration or the timeInterval spelling of the
    element carries, or zero."""
    if duration_str:
        duration = isodate.parse_duration(duration_str)

        # isodate may return datetime.timedelta or isodate.Duration
        if isinstance(duration, timedelta):
            return duration
        # Convert Duration (years/months not supported by timedelta)
        return duration.tdelta

    if interval_value and interval_unit:
        return _resolution_of_interval(interval_value, interval_unit)

    return timedelta(0)


def _resolution_of_interval(interval_value, interval_unit):
    """
    Parse a time interval expressed as a decimal number (e.g., '1.0') and a
    unit (e.g., 'hour') into a timedelta object that Django's DurationField
    can accept.
    """
    if interval_unit == "hour":
        return timedelta(hours=float(interval_value))
    if interval_unit == "minute":
        return timedelta(minutes=float(interval_value))
    if interval_unit == "second":
        return timedelta(seconds=float(interval_value))
    raise ValueError(f"Unsupported unit: {interval_value}")


def _utc_aware(dt):
    """The datetime aware in UTC, left alone when it already is aware."""
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone=UTC)
    return dt


def _extent_between(mapper, begin_position, end_position, resolution):
    """The extent between two positions; skipped when they are inverted."""
    dt_start = _utc_aware(isoparse(begin_position))
    dt_end = _utc_aware(isoparse(end_position))
    if dt_start > dt_end:
        mapper.warnings.append(
            f"Skipped temporal extent because begin {begin_position} is after end {end_position}."
        )
        return None
    return TimeExtent(
        begin=dt_start,
        end=dt_end,
        resolution=resolution
    )


def _time_position_text(value):
    """The gml position text for an aware or naive datetime.

    Naive UTC without an offset: :func:`parse_timeextent` localizes a naive
    position to UTC, so this text reads back as the very same instant on every
    deployment - unlike the localtime text of ``datetime_to_string``, whose
    reader assumes the deployment timezone. An offset here would round-trip
    too, but the repository's own documents carry none.
    """
    if timezone.is_aware(value):
        value = value.astimezone(UTC)
    return value.strftime("%Y-%m-%dT%H:%M:%S")


def serialize_timeextent_fragment(mapper, instance):
    """The gml:TimePeriod fragment for one TimeExtent row (#1246).

    The inverse of :func:`parse_timeextent`: both positions as naive UTC text,
    the resolution as an ISO 8601 duration when the row carries one. A row
    with neither position is a rolling window or a relative extent - shapes
    the editor of #1246 does not offer to write - and answers None, which
    makes the write mapper leave whatever the document carries for that row
    untouched rather than guess a GML shape for it.
    """
    begin = getattr(instance, "begin", None)
    end = getattr(instance, "end", None)
    if begin is None and end is None:
        return None

    nsmap = mapper.mapping.get("_namespaces", {})
    gml = nsmap.get("gml")
    if not gml:  # pragma: no cover - config carries all
        return None

    period = etree.Element(f"{{{gml}}}TimePeriod")
    # gml:id is an NCName and unique per document; the row's pk is neither
    # guaranteed present nor document-unique, so a fresh id per fragment -
    # two fragments of one document never share one
    period.set(f"{{{gml}}}id", f"mrmap-{uuid4().hex}")
    if begin is not None:
        position = etree.SubElement(period, f"{{{gml}}}beginPosition")
        position.text = _time_position_text(begin)
    if end is not None:
        position = etree.SubElement(period, f"{{{gml}}}endPosition")
        position.text = _time_position_text(end)
    resolution = getattr(instance, "resolution", None)
    if resolution and isinstance(resolution, timedelta) and resolution > timedelta(0):
        duration = etree.SubElement(period, f"{{{gml}}}duration")
        duration.text = isodate.duration_isoformat(resolution)
    return period
