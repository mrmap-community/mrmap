import typing
from datetime import timedelta

import isodate
from dateutil.parser import isoparse
from lxml import etree
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models import TimeExtent
from registry.models.metadata import MimeType
from registry.models.service import WebMapServiceOperationUrl

if typing.TYPE_CHECKING:
    from django.db.models import Manager


def timeextent_to_value(mapper, instance):
    return instance.xml_value()


def parse_timeextent(mapper, el):
    """
    Parser für <Extent name="time"> Elemente.
    - Unterstützt Intervalle im Format 'start/end/resolution'
    - Unterstützt mehrere Einzelwerte, komma-separiert
    """
    text = (el.text or "").strip()
    if not text:
        return None

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
            resolution = timedelta(0)
            if len(segments) == 3:
                # Auflösung: z.B. "P1D" -> relativedelta
                resolution = _parse_duration(mapper, segments[2])

            inst = TimeExtent(
                begin=start,
                end=end,
                resolution=resolution,
            )
            instances.append(inst)

        # Einzelwert
        else:
            dt = isoparse(part)
            inst = TimeExtent(
                begin=dt,
                end=dt,
                resolution=timedelta(0),
            )
            instances.append(inst)

    return instances


def _parse_duration(mapper, duration_str):
    """
    ISO-8601 Duration Parser.
    Unterstützt Tage, Monate, Jahre, Stunden, Minuten, Sekunden.
    Gibt ein timedelta zurück (nicht isodate.Duration).
    """
    if not duration_str:
        return timedelta(0)

    try:
        dur = isodate.parse_duration(duration_str)

        # Convert isodate.Duration → timedelta (approximate months/years)
        if isinstance(dur, isodate.Duration):
            days = 0
            if dur.years:
                days += dur.years * 365
            if dur.months:
                days += dur.months * 30
            dur = timedelta(
                days=days + (dur.tdelta.days if dur.tdelta else 0),
                seconds=(dur.tdelta.seconds if dur.tdelta else 0),
                microseconds=(dur.tdelta.microseconds if dur.tdelta else 0),
            )
        return dur
    except Exception:
        return timedelta(0)


def parse_operation_urls(mapper, el):
    """
    Parst alle OperationUrls (GetCapabilities, GetMap, GetFeatureInfo, etc.)
    aus einem <Request>-Element eines WMS-Capabilities-Dokuments.

    Gibt eine Liste von WebMapServiceOperationUrl-Instanzen zurück.
    """
    nsmap = mapper.mapping.get("_namespaces", None)

    method_name = etree.QName(el).localname
    method_enum = HttpMethodEnum(method_name)

    operation_name = el.xpath("local-name(../../../.)")
    operation_enum = OGCOperationEnum(
        operation_name) if operation_name else None

    online_resource = el.find(
        f"./{"wms:"if "wms" in nsmap else ""}OnlineResource", namespaces=nsmap)
    url = online_resource.xpath(
        "./@xlink:href", namespaces=nsmap) if online_resource is not None else None

    format_values = [f
                     for f in el.xpath(f"../../.././{"wms:"if "wms" in nsmap else ""}Format", namespaces=nsmap)
                     if f.text]

    if method_name is None or operation_enum is None or url is None:
        return
    url = url[0]

    op_inst = WebMapServiceOperationUrl(
        operation=operation_enum,
        method=method_enum,
        url=url.strip(),
    )

    # MimeTypes vorbereiten (noch nicht speichern)
    op_inst._mime_types_parsed = []
    for fmt in format_values:
        mime_inst = MimeType(mime_type=fmt.text.strip())
        format_path = fmt.getroottree().getpath(fmt)
        mapper.store_to_cache(format_path, mime_inst)
        op_inst._mime_types_parsed.append(mime_inst)

    return op_inst


def reverse_parse_operation_urls(
        mapper,
        xml_element: etree._Element,
        instance: WebMapServiceOperationUrl
) -> etree.Element:
    """
    Update a WMS Operation URL XML element based on a database instance.

    - Ensures OnlineResource exists and sets xlink:href
    - Removes all <Format> elements
    - Appends <Format> elements from instance.mime_types.all()

    Args:
        mapper: XmlMapper instance (optional for utilities)
        xml_element (etree._Element): Element corresponding to
            ./wms:Capability/wms:Request/wms:{operation}/wms:DCPType/wms:HTTP/wms:{method}
        instance (WebMapServiceOperationUrl): Database instance containing
            URL and MIME types.

    Returns:
        etree.Element: The updated XML element.
    """
    nsmap = mapper.mapping.get("_namespaces", {
        "wms", "http://www.opengis.net/wms",
        "xlink", "http://www.w3.org/1999/xlink"
    })

    # 1️⃣ Ensure OnlineResource exists
    online_resource = xml_element.xpath(
        ".//wms:OnlineResource", namespaces=nsmap)
    if online_resource is None:
        # Typically OnlineResource is under wms:HTTP (Get/Post)
        online_resource = etree.SubElement(
            xml_element, f"{{{nsmap["wms"]}}}OnlineResource")
    else:
        online_resource = online_resource[0]
    # Set xlink:href
    online_resource.set(f"{{{nsmap["xlink"]}}}href", instance.url)

    # 2️⃣ Remove all existing <Format> elements
    # TODO: Format is placed under wms:HTTP
    # TODO: remove existing formats from xml
    for fmt_el in xml_element.findall(".//wms:Format", namespaces=nsmap):
        parent = fmt_el.getparent()
        if parent is not None:
            parent.remove(fmt_el)

    # 3️⃣ Append <Format> elements from instance.mime_types.all()
    for mime_type in instance.mime_types.all():
        fmt_el = etree.SubElement(xml_element, f"{{{nsmap["wms"]}}}Format")
        fmt_el.text = str(mime_type)

    return xml_element
