import urllib
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from epsg_cache.utils import get_epsg_srid
from lxml import etree
from registry.enums.metadata import (MetadataCharsetChoices,
                                     UpdateFrequencyChoices)
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)


def int_to_bool(mapper, value: int = 0) -> bool:
    """Wandelt 0 in False und 1 in True um. Andere Werte werfen einen ValueError."""
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"Ungültiger Wert {value}, nur 0 oder 1 erlaubt.")


def str_to_bool(mapper, value: str = "0") -> bool:
    """Wandelt den String '0' in False und '1' in True um. Andere Werte werfen einen ValueError."""
    if value == "0":
        return False
    if value == "1":
        return True
    raise ValueError(f"Ungültiger Wert {value!r}, nur '0' oder '1' erlaubt.")


def srs_to_prefix(mapper, value):
    if "::" in value:
        # example: ref_system = urn:ogc:def:crs:EPSG::4326
        return value.rsplit(":")[-3]
    elif ":" in value:
        # example: ref_system = EPSG:4326
        return value.rsplit(":")[-2]
    else:
        return ""


def srs_to_code(mapper, value):
    if "::" in value:
        # example: ref_system = urn:ogc:def:crs:EPSG::4326
        return value.rsplit(":")[-1]
    elif ":" in value:
        # example: ref_system = EPSG:4326
        return value.rsplit(":")[-1]
    else:
        return ""


def bbox_to_polygon(mapper, minx, maxx, miny, maxy):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    minx = float(minx)
    maxx = float(maxx)
    miny = float(miny)
    maxy = float(maxy)
    return Polygon.from_bbox((minx, miny, maxx, maxy))


def polygon_to_bbox(mapper, polygon):
    """
    Erwartet ein GEOS Polygon,
    gibt eine Liste von Strings zurück: [minx, maxx, miny, maxy]
    passend zu den XML-@Attribute Inputs.
    """
    if polygon is None:
        return [None, None, None, None]
    try:
        # extent: (xmin, ymin, xmax, ymax)
        xmin, ymin, xmax, ymax = polygon.extent
    except AttributeError as e:
        raise ValueError(
            f"polygon_to_bbox: expected polygon, got {polygon}: {e}")
    return [str(xmin), str(xmax), str(ymin), str(ymax)]


def version_to_int(mapper, version):
    return OGCServiceVersionEnum(version).value


def method_to_enum(mapper, url_element):
    tag = url_element.tag
    if "}" in tag:
        tag = tag.split("}")[1]
    if tag:
        return HttpMethodEnum(tag)


def operation_to_enum(mapper, operation_str):
    return OGCOperationEnum(operation_str)


def charset_to_enum(mapper, charset_str):
    return MetadataCharsetChoices(charset_str)


def language_to_enum(mapper, language_str):
    return MetadataCharsetChoices(language_str)


def update_frequency_code_to_enum(mapper, update_frequence_code_str):
    return UpdateFrequencyChoices(update_frequence_code_str)


def string_to_datetime(value: str):
    dt = parse_datetime(value)
    if dt:
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    d = parse_date(value)
    if d:
        dt = datetime.combine(d, datetime.min.time())
        return timezone.make_aware(dt)

    raise ValueError(f"Ungültiges Datumsformat: {value}")


def _split_code(mapper, code_string):
    _code = ""
    _code_space = ""
    if code_string:
        # new implementation:
        # http://inspire.ec.europa.eu/file/1705/download?token=iSTwpRWd&usg=AOvVaw18y1aTdkoMCBxpIz7tOOgu
        # from 2017-03-02 - the MD_Identifier - see C.2.5 Unique resource identifier - it is separated with a slash
        # - the codes pace should be everything after the last slash
        # now try to check if a single slash is available and if the md_identifier is a url
        parsed_url = urllib.parse.urlsplit(code_string)
        if parsed_url.scheme == "http" or parsed_url.scheme == "https" and "/" in parsed_url.path:
            tmp = code_string.split("/")
            _code = tmp[len(tmp) - 1]
            _code_space = code_string.replace(_code, "")
        elif parsed_url.scheme == "http" or parsed_url.scheme == "https" and "#" in code_string:
            tmp = code_string.split("#")
            _code = tmp[1]
            _code_space = tmp[0]
        else:
            _code = code_string
            _code_space = ""

    return _code.replace('\n', '').strip(), _code_space.replace('\n', '').strip()


def string_to_code(mapper, code):
    _split_code(mapper, code)[0]


def string_to_code_space(mapper, code):
    _split_code(mapper, code)[1]


def _parse_geographic_bbox(mapper, element):
    nsmap = mapper.mapping.get("_namespaces", None)
    min_x = element.find(
        "./gmd:westBoundLongitude/gco:Decimal",
        namespaces=nsmap
    )
    max_x = element.find(
        "./gmd:eastBoundLongitude/gco:Decimal",
        namespaces=nsmap
    )
    min_y = element.find(
        "./gmd:southBoundLatitude/gco:Decimal",
        namespaces=nsmap
    )
    max_y = element.find(
        "./gmd:northBoundLatitude/gco:Decimal",
        namespaces=nsmap
    )

    if min_x and max_x and min_y and max_y:
        return Polygon((
            (min_x, min_y),
            (min_x, max_y),
            (max_x, max_y),
            (max_x, min_y),
            (min_x, min_y)
        ))


def _parse_bounding_polygon(mapper, element):
    geometries = []
    for gmd_polygon in element.iterfind("./gmd:polygon"):
        srs_name = gmd_polygon.find("./@srsName")
        geometry = GEOSGeometry.from_gml(etree.tostring(gmd_polygon))

        if srs_name:
            _, srid = get_epsg_srid(srs_name)
        else:
            srid = 4326  # default srs
        geometries.append(GEOSGeometry(geo_input=geometry.wkt, srid=srid))
    return MultiPolygon(geometries)


def iso_bbox_to_multipolygon(mapper, elements):
    polygons = []

    for element in elements:

        if element.tag == "gmd:EX_GeographicBoundingBox":
            polygon = _parse_geographic_bbox(mapper, elements)
            if polygon:
                polygons.append(polygon)

        elif element.tag == "gmd:EX_BoundingPolygon":
            multipolygon = _parse_bounding_polygon(mapper, elements)
            if multipolygon:
                polygons.extend(multipolygon)

    if polygons:
        return MultiPolygon(polygons)
        return MultiPolygon(polygons)
