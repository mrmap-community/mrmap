
from datetime import timedelta

from dateutil import parser as date_parser
from django.contrib.gis.geos import Polygon
from registry.models import LayerTimeExtent


def int_to_bool(value: int = 0) -> bool:
    """Wandelt 0 in False und 1 in True um. Andere Werte werfen einen ValueError."""
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"Ungültiger Wert {value}, nur 0 oder 1 erlaubt.")


def str_to_bool(value: str = "0") -> bool:
    """Wandelt den String '0' in False und '1' in True um. Andere Werte werfen einen ValueError."""
    if value == "0":
        return False
    if value == "1":
        return True
    raise ValueError(f"Ungültiger Wert {value!r}, nur '0' oder '1' erlaubt.")


def srs_to_prefix(value):
    if "::" in value:
        # example: ref_system = urn:ogc:def:crs:EPSG::4326
        return value.rsplit(":")[-3]
    elif ":" in value:
        # example: ref_system = EPSG:4326
        return value.rsplit(":")[-2]
    else:
        return ""


def srs_to_code(value):
    if "::" in value:
        # example: ref_system = urn:ogc:def:crs:EPSG::4326
        return value.rsplit(":")[-1]
    elif ":" in value:
        # example: ref_system = EPSG:4326
        return value.rsplit(":")[-1]
    else:
        return ""


def bbox_to_polygon(values):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    if len(values) != 4:
        raise ValueError(
            "bbox_to_polygon expects 4 inputs (minx, maxx, miny, maxy)")
    # Umwandlung in float
    try:
        minx, maxx, miny, maxy = map(float, values)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"bbox_to_polygon: unable to parse floats from {values}: {e}")
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    return Polygon.from_bbox((minx, miny, maxx, maxy))


def polygon_to_bbox(polygon):
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


def parse_timeextent(mapper, el):
    """
    Erwartet ein <Dimension name="time">- oder <Extent name="time">-Element.
    Baut daraus ein LayerTimeExtent-Objekt für ein DateTimeRangeField.
    """
    text = (el.text or "").strip()
    if not text:
        return None

    layer = mapper.get_instance_by_element(mapper.current_element)

    # Einzelwert
    if "/" not in text:
        ts = date_parser.isoparse(text)
        return LayerTimeExtent(
            timerange=(ts, ts),
            resolution=None,
            layer=layer
        )

    # Intervall (+ optional Auflösung)
    parts = text.split("/")
    start = date_parser.isoparse(parts[0]) if parts[0] else None
    end = date_parser.isoparse(parts[1]) if len(
        parts) > 1 and parts[1] else start

    resolution = None
    if len(parts) == 3 and parts[2]:
        token = parts[2].upper()
        if token.startswith("P") and token.endswith("D"):
            days = int(token[1:-1])
            resolution = timedelta(days=days)

    return LayerTimeExtent(
        timerange=(start, end),   # ✅ direkt Tuple, kein psycopg2-Objekt
        resolution=resolution,
        layer=layer
    )
