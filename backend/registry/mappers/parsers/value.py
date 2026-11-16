import math
import urllib
from datetime import datetime

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Polygon
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from epsg_cache.utils import get_epsg_srid
from lxml import etree
from registry.enums.iso import (LanguageChoices,
                                MetadataCharsetChoices, UpdateFrequencyChoices)
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)
from registry.mappers.parsers.utils import get_tag


def boolean_to_int(_mapper, value: bool = False) -> int:
    """Wandelt False in 0 und True in 1 um."""
    return int(value)


def str_to_bool(_mapper, value: str = "0") -> bool:
    """Wandelt den String '0' in False und '1' in True um. Andere Werte werfen einen ValueError."""
    if value == "0" or value == "false":
        return False
    if value == "1" or value == "true":
        return True
    raise ValueError(f"Ungültiger Wert {value!r}, nur '0' oder '1' erlaubt.")


def str_to_int(_mapper, value: str = "0") -> int:
    """Wandelt den String '0' in 0 und '1' in 1 um. Andere Werte werfen einen ValueError."""
    return int(value)


def srs_to_prefix(_mapper, value: str):
    match value.split(":"):
        case [prefix, _]:
            # example: EPSG:4326
            return prefix
        case ["urn", "ogc", "def", "crs", prefix, *_]:
            # examples:
            # urn:ogc:def:crs:EPSG::4326
            # urn:ogc:def:crs:EPSG:6.3:26986
            # urn:ogc:def:crs:OGC:1.3:AUTO42003:1:-100:45
            return prefix
        case _:
            return ""


def srs_to_code(_mapper, value: str):
    match value.split(":"):
        case [_, code]:
            # example: EPSG:4326
            return code
        case ["urn", "ogc", "def", "crs", _, _, code, *_]:
            # examples:
            # urn:ogc:def:crs:EPSG::4326
            # urn:ogc:def:crs:EPSG:6.3:26986
            # urn:ogc:def:crs:OGC:1.3:AUTO42003:1:-100:45
            return code
        case _:
            return ""


def bbox_to_polygon(_mapper, minx, maxx, miny, maxy):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    if minx and maxx and miny and maxy:
        minx = float(minx)
        maxx = float(maxx)
        miny = float(miny)
        maxy = float(maxy)
        return Polygon.from_bbox((minx, miny, maxx, maxy))


def polygon_to_bbox(_mapper, polygon):
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


def version_to_int(_mapper, version):
    return OGCServiceVersionEnum(version).value


def int_to_version(_mapper, version: int):
    return OGCServiceVersionEnum(version).label


def method_to_enum(_mapper, url_element):
    tag = get_tag(url_element)
    if tag:
        return HttpMethodEnum(tag)


def serialize_method(_mapper, value):
    return HttpMethodEnum(value).label


def operation_to_enum(_mapper, operation_str):
    return OGCOperationEnum(operation_str)


def serialize_operation(_mapper, value):
    return OGCOperationEnum(value).label


def charset_to_enum(_mapper, charset_str):
    return MetadataCharsetChoices(charset_str)


def language_to_enum(_mapper, language_str):
    return LanguageChoices(language_str)


def int_to_language(_mapper, value):
    return LanguageChoices(value).label


def update_frequency_code_to_enum(_mapper, update_frequence_code_str):
    return UpdateFrequencyChoices(update_frequence_code_str)


def string_to_datetime(_mapper, value: str):
    dt = parse_datetime(value)
    if dt:
        return timezone.make_aware(dt) if timezone.is_naive(dt) else dt

    d = parse_date(value)
    if d:
        dt = datetime.combine(d, datetime.min.time())
        return timezone.make_aware(dt)

    raise ValueError(f"Ungültiges Datumsformat: {value}")


def _split_code(_mapper, code_string):
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
        elif parsed_url.scheme == "https" and "#" in code_string:
            # an http url always took the branch above
            tmp = code_string.split("#")
            _code = tmp[1]
            _code_space = tmp[0]
        else:
            _code = code_string
            _code_space = ""

    return _code.replace('\n', '').strip(), _code_space.replace('\n', '').strip()


def string_to_code(mapper, code):
    return _split_code(mapper, code)[0]


def string_to_code_space(mapper, code):
    return _split_code(mapper, code)[1]


def _parse_geographic_bbox(mapper, element):
    nsmap = mapper.mapping.get("_namespaces", None)
    min_x = float(element.findtext(
        "./gmd:westBoundLongitude/gco:Decimal",
        namespaces=nsmap
    ))
    max_x = float(element.findtext(
        "./gmd:eastBoundLongitude/gco:Decimal",
        namespaces=nsmap
    ))
    min_y = float(element.findtext(
        "./gmd:southBoundLatitude/gco:Decimal",
        namespaces=nsmap
    ))
    max_y = float(element.findtext(
        "./gmd:northBoundLatitude/gco:Decimal",
        namespaces=nsmap
    ))

    if (all(math.isfinite(value) for value in (min_x, max_x, min_y, max_y))
            and -180 <= min_x < max_x <= 180 and -90 <= min_y < max_y <= 90):
        return Polygon((
            (min_x, min_y),
            (min_x, max_y),
            (max_x, max_y),
            (max_x, min_y),
            (min_x, min_y)
        ))


def _parse_bounding_polygon(mapper, element):
    geometries = []
    # the prefix map the rest of the parser uses: without it the `gmd:`
    # prefix of the path is unknown to lxml and the whole branch raises
    # (surfaced when #1246 first wrote a polygon the reader had to read back)
    nsmap = mapper.mapping.get("_namespaces")
    for gmd_polygon in element.iterfind("./gmd:polygon", namespaces=nsmap):
        srs_name = gmd_polygon.get("srsName")
        # from_gml reads a GML geometry, not the gmd:polygon wrapper around
        # it: the reader is the FIRST gml child, which is a Polygon as the
        # write mapper of #1246 serializes it and a MultiSurface as the
        # fixtures of the wild carry it - OGR answers both as a polygon
        geometry_el = next(
            (c for c in gmd_polygon if isinstance(c.tag, str)), None)
        if geometry_el is None:
            continue
        geometry = GEOSGeometry.from_gml(etree.tostring(geometry_el))

        if srs_name:
            _, srid = get_epsg_srid(srs_name)
        else:
            srid = 4326  # default srs
        geometries.append(GEOSGeometry(geo_input=geometry.wkt, srid=srid))
    return MultiPolygon(geometries)


def iso_bbox_to_multipolygon(mapper, elements=[]):
    polygons = []
    if elements is None:
        elements = []
    if isinstance(elements, etree.Element):
        elements = [elements]

    for element in elements:

        if element.tag == "{http://www.isotc211.org/2005/gmd}EX_GeographicBoundingBox":
            polygon = _parse_geographic_bbox(mapper, element)
            if polygon:
                polygons.append(polygon)

        elif element.tag == "{http://www.isotc211.org/2005/gmd}EX_BoundingPolygon":
            multipolygon = _parse_bounding_polygon(mapper, element)
            if multipolygon:
                polygons.extend(multipolygon)

    if polygons:
        return MultiPolygon(polygons)


# reverse parsers (#1242): the write mapper turns a mapped value back into the
# external representation the _parser of the same spec reads


def _coordinate_text(coord):
    """The xsd:decimal/GML-posList text for one coordinate.

    ``repr`` of a float is the shortest text that reads back as the very same
    binary value, which is what keeps the write mapper's skip-if-equal compare
    stable: serialize, parse, compare answers equal for an unchanged geometry,
    so a fresh read-write-read round trip leaves the document byte-identical.
    The rare exponent form is not an xsd:decimal, so it falls back to a fixed
    representation that still round-trips.
    """
    value = float(coord)
    text = repr(value)
    if "e" in text or "E" in text:
        text = format(value, ".17f")
    return text


def _is_bbox_rectangle(polygon):
    """Whether one polygon is exactly an axis-aligned rectangle without holes.

    The four vertices of the exterior ring must alternate between sharing x
    and sharing y - the shape :func:`_parse_geographic_bbox` reads back as the
    very same rectangle. Interior rings disqualify: an EX_GeographicBoundingBox
    can not carry a hole.
    """
    if polygon is None or polygon.num_interior_rings > 0:
        return False
    coords = list(polygon.exterior_ring or [])
    if len(coords) != 5 or coords[0] != coords[-1]:
        return False
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        if x1 != x2 and y1 != y2:
            return False
    return True


def serialize_bounding_geometry(mapper, value):
    """The gmd:EX_GeographicBoundingBox / gmd:EX_BoundingPolygon fragment.

    The inverse of :func:`iso_bbox_to_multipolygon` (#1246): a rectangle
    without holes is written as the bounding box - the shape catalogues and
    the INSPIRE view expect - everything else as one gmd:polygon/gml:Polygon
    per polygon, lon-lat ordered like the reader assumes (the parser defaults
    an unqualified GML geometry to EPSG:4326). The answer is an element
    fragment, which the write mapper (#1242) places in the document; it
    carries no namespace prefix of its own, lxml binds the document's when it
    serializes. Interior rings are not written: the mapped value of this
    field is the bounding geometry, not a doughnut.
    """
    if value is None:
        return None
    multipolygon = (
        MultiPolygon([value]) if isinstance(value, Polygon) else value)
    polygons = list(multipolygon or [])
    if not polygons:
        return None

    nsmap = mapper.mapping.get("_namespaces", {})
    gmd = nsmap.get("gmd")
    gco = nsmap.get("gco")
    gml = nsmap.get("gml")
    if not (gmd and gco and gml):  # pragma: no cover - config carries all
        return None

    if len(polygons) == 1 and _is_bbox_rectangle(polygons[0]):
        min_x, min_y, max_x, max_y = polygons[0].extent
        element = etree.Element(f"{{{gmd}}}EX_GeographicBoundingBox")
        for name, coord in (
                ("westBoundLongitude", min_x),
                ("eastBoundLongitude", max_x),
                ("southBoundLatitude", min_y),
                ("northBoundLatitude", max_y)):
            bound = etree.SubElement(element, f"{{{gmd}}}{name}")
            decimal = etree.SubElement(bound, f"{{{gco}}}Decimal")
            decimal.text = _coordinate_text(coord)
        return element

    element = etree.Element(f"{{{gmd}}}EX_BoundingPolygon")
    for polygon in polygons:
        wrapper = etree.SubElement(element, f"{{{gmd}}}polygon")
        geometry = etree.SubElement(wrapper, f"{{{gml}}}Polygon")
        geometry.set("srsDimension", "2")
        exterior = etree.SubElement(geometry, f"{{{gml}}}exterior")
        ring = etree.SubElement(exterior, f"{{{gml}}}LinearRing")
        coords = list(polygon.exterior_ring or [])
        if coords and coords[0] != coords[-1]:
            coords.append(coords[0])
        positions = " ".join(
            f"{_coordinate_text(x)} {_coordinate_text(y)}"
            for x, y in coords)
        pos_list = etree.SubElement(ring, f"{{{gml}}}posList")
        pos_list.text = positions
    return element


def int_to_charset(mapper, value):
    return MetadataCharsetChoices(value).label


def int_to_update_frequency(mapper, value):
    return UpdateFrequencyChoices(value).label


def datetime_to_string(mapper, value):
    """The gco:DateTime text for an aware datetime.

    Rendered in the deployment's current timezone without an offset, the
    shape string_to_datetime() reads back as the same instant - which is what
    lets the write mapper notice an unchanged date_stamp and leave the node
    alone instead of rewriting the representation on every save.
    """
    if value is None:
        return None
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%Y-%m-%dT%H:%M:%S")
