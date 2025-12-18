import typing
from collections import defaultdict
from datetime import timedelta

import isodate
from dateutil.parser import isoparse
from lxml import etree
from lxml.builder import ElementMaker

from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.models import TimeExtent
from registry.models.metadata import MimeType
from registry.models.service import WebMapServiceOperationUrl
from psycopg.types.range import Range

if typing.TYPE_CHECKING:
    from django.db.models import Manager


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
            resolution = None
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
                resolution=None,
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
        return None

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
        # Namespace-freier Name, z. B. "GetMap"
        operation_name = etree.QName(op_el).localname
        operation_enum = OGCOperationEnum(operation_name)

        if operation_enum is None:
            continue

        # Alle MimeTypes unter <Format>
        format_values = [
            f
            for f in op_el.xpath(
                "./wms:Format" if "wms" in nsmap else "./Format",
                namespaces=nsmap,
            )
            if f.text
        ]

        # Finde alle HTTP-Methoden und URLs
        for method in ("Get", "Post"):
            urls = op_el.xpath(
                (
                    f"./wms:DCPType/wms:HTTP/wms:{method}/wms:OnlineResource"
                    if "wms" in nsmap
                    else f"./DCPType/HTTP/{method}/OnlineResource"
                ),
                namespaces=nsmap,
            )

            method_enum = HttpMethodEnum(method)
            if method_enum is None:
                continue

            for url in urls:
                href = url.xpath("./@xlink:href", namespaces=nsmap)
                if not href or not href[0]:
                    continue

                op_inst = WebMapServiceOperationUrl(
                    operation=operation_enum,
                    method=method_enum,
                    url=href[0].strip(),
                )

                # optionales Cache-Handling
                path = url.getroottree().getpath(url)
                mapper.store_to_cache(path, op_inst)

                # MimeTypes vorbereiten (noch nicht speichern)
                op_inst._mime_types_parsed = []
                for fmt in format_values:
                    mime_inst = MimeType(mime_type=fmt.text.strip())
                    format_path = fmt.getroottree().getpath(fmt)
                    mapper.store_to_cache(format_path, mime_inst)
                    op_inst._mime_types_parsed.append(mime_inst)

                instances.append(op_inst)

    return instances


def reverse_parse_operation_urls(mapper, qs: "Manager[WebMapServiceOperationUrl]") -> etree.Element:
    namespaces = mapper.mapping.get("_namespaces", {})
    E = ElementMaker(namespace=namespaces.get("wms"), nsmap=namespaces)

    operations: dict[str, dict[str, typing.Any]] = defaultdict(dict)
    # example structure:
    # operations = {
    #     "GetCapabilities": {
    #         "urls": {"Get": "http://example.com/map", "Post": "http://example.com/map"},
    #         "mime_types": {"text/xml"},
    #     },
    #     "GetMap": {
    #         "urls": {"Get": "http://example.com/map"},
    #         "mime_types": {"image/png", "image/tiff"}
    #         },
    # }

    # collect data from django objects
    for operation_url in qs.all():
        operations[operation_url.get_operation_display()].setdefault("urls", dict())[operation_url.get_method_display()] = operation_url.url
        for mime_type in operation_url.mime_types.all():
            operations[operation_url.get_operation_display()].setdefault("mime_types", set()).add(mime_type.mime_type)

    # build XML element
    request = E("Request")
    for operation_name, operation in operations.items():
        op = E(operation_name)
        for mime_type in sorted(operation.get("mime_types", [])):
            op.append(E("Format", mime_type))

        http = E("HTTP")
        op.append(E("DCPType", http))

        for method, url in operation.get("urls", {}).items():
            http.append(
                E(
                    method,
                    E(
                        "OnlineResource",
                        **{f"{{{namespaces['xlink']}}}type": "simple", f"{{{namespaces['xlink']}}}href": url},
                    ),
                )
            )
        request.append(op)

    return request
