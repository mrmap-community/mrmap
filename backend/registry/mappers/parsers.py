
import isodate
from dateutil.parser import isoparse
from django.contrib.gis.geos import Polygon
from registry.models import LayerTimeExtent
from registry.models.metadata import MimeType
from registry.models.service import WebMapServiceOperationUrl


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
    Parser für <Extent name="time"> Elemente.
    - Unterstützt Intervalle im Format 'start/end/resolution'
    - Unterstützt mehrere Einzelwerte, komma-separiert
    """
    text = (el.text or "").strip()
    if not text:
        return None

    layer = mapper.get_instance_by_element(mapper.current_element)

    instances = []
    parts = [p.strip() for p in text.split(",") if p.strip()]

    for part in parts:
        # Intervall-Notation (start/end[/resolution])
        if "/" in part:
            segments = part.split("/")
            if len(segments) < 2:
                continue

            start = isoparse(segments[0])
            end = isoparse(segments[1])
            resolution = None
            if len(segments) == 3:
                # Auflösung: z.B. "P1D" -> relativedelta
                resolution = _parse_duration(segments[2])

            inst = LayerTimeExtent(
                timerange=(start, end),
                resolution=resolution,
                layer=layer,
            )
            instances.append(inst)

        # Einzelwert
        else:
            dt = isoparse(part)
            inst = LayerTimeExtent(
                timerange=(dt, dt),
                resolution=None,
                layer=layer,
            )
            instances.append(inst)

    return instances


def _parse_duration(duration_str):
    """
    ISO-8601 Duration Parser.
    Unterstützt Tage, Monate, Jahre, Stunden, Minuten, Sekunden.
    Gibt ein relativedelta oder timedelta zurück.
    """
    if not duration_str:
        return None

    try:
        # isodate.parse_duration gibt timedelta oder relativedelta zurück
        return isodate.parse_duration(duration_str)
    except Exception:
        return None


def parse_operation_urls(mapper, el):
    """
    Parst alle OperationUrls (GetCapabilities, GetMap, GetFeatureInfo, etc.)
    aus einem <Request>-Element eines WMS-Capabilities-Dokuments.

    Gibt eine Liste von WebMapServiceOperationUrl-Instanzen zurück.
    """
    instances = []
    nsmap = mapper.mapping.get("_namespaces", None)

    # Iteriere über alle Operationen im Request-Block
    for op_el in el.xpath("./*", namespaces=nsmap):
        operation_name = op_el.tag

        # Alle MimeTypes unter <Format>
        format_values = [
            f for f in op_el.xpath("./Format", namespaces=nsmap) if f.text
        ]

        # Finde alle HTTP-Methoden und URLs
        for method in ("Get", "Post"):
            urls = op_el.xpath(
                f"./DCPType/HTTP/{method}/OnlineResource",
                namespaces=nsmap,
            )
            for url in urls:
                href = url.xpath("./@xlink:href", namespaces=nsmap)
                if href and href[0]:
                    op_inst = WebMapServiceOperationUrl(
                        operation=operation_name,
                        method=method.upper(),
                        url=href[0].strip(),
                    )
                    path = url.getroottree().getpath(url)
                    mapper.store_to_cache(path, op_inst)
                    # TODO: store_to_cache
                    # MimeTypes als leere Liste initialisieren
                    op_inst._mime_types_parsed = []

                    # Falls MimeTypes gefunden → Dummy MimeType-Objekte erzeugen (noch nicht speichern)
                    for fmt in format_values:
                        # TODO: store_to_cache
                        mime_inst = MimeType(mime_type=fmt.text.strip())
                        format_path = fmt.getroottree().getpath(fmt)
                        mapper.store_to_cache(format_path, mime_inst)
                        op_inst._mime_types_parsed.append(mime_inst)

                    instances.append(op_inst)

    return instances
