from django.contrib.gis.geos import Polygon
from registry.enums.service import (HttpMethodEnum, OGCOperationEnum,
                                    OGCServiceVersionEnum)


def int_to_bool(mapper, value: int = 0) -> bool:
    """Wandelt 0 in False und 1 in True um. Andere Werte werfen einen ValueError."""
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"Ungültiger Wert {value}, nur 0 oder 1 erlaubt.")

def boolean_to_int(mapper, value: bool = False) -> int:
    """Wandelt False in 0 und True in 1 um."""
    return int(value)


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

def int_to_version(mapper, version: int):
    return OGCServiceVersionEnum(version).label


def method_to_enum(mapper, url_element):
    tag = url_element.tag
    if "}" in tag:
        tag = tag.split("}")[1]
    if tag:
        return HttpMethodEnum(tag)


def operation_to_enum(mapper, operation_str):
    return OGCOperationEnum(operation_str)
