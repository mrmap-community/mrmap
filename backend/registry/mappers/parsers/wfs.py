from django.contrib.gis.geos import Polygon
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.mappers.parsers.value import \
    bbox_to_polygon as bbox_value_to_polygon
from registry.mappers.parsers.value import srs_to_code, srs_to_prefix
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.service import WebFeatureServiceOperationUrl


def parse_reference_systems(mapper, el):
    """
    Parst alle DefaultCRS und OtherCRS des aktuellen FeatureType.

    """
    instances = []
    nsmap = mapper.mapping.get("_namespaces", None)

    # Iteriere über alle Operationen im Request-Block
    for crs_el in el.xpath("./wfs:OtherCRS", namespaces=nsmap):
        crs_el.text
        if crs_el.text:
            code = srs_to_code(mapper, crs_el.text)
            prefix = srs_to_prefix(mapper, crs_el.text)
            instances.append(
                ReferenceSystem(
                    code=code,
                    prefix=prefix
                )
            )
    default_crs_el = el.xpath("./wfs:DefaultCRS", namespaces=nsmap)
    if default_crs_el and len(default_crs_el) > 0 and default_crs_el[0].text:
        code = srs_to_code(mapper, default_crs_el[0].text)
        prefix = srs_to_prefix(mapper, default_crs_el[0].text)
        # TODO: the crosstable should have an tag to signal that this is the default one.
        instances.append(
            ReferenceSystem(
                code=code,
                prefix=prefix
            )
        )

    return instances


def bbox_to_polygon(mapper, lower_corner, upper_corner):
    """
    Erwartet values als Sequenz: (minx, maxx, miny, maxy)
    Gibt ein Polygon zurück.
    """
    # GEOS from_bbox expects (xmin, ymin, xmax, ymax)
    minx = lower_corner.split(" ")[0]
    miny = lower_corner.split(" ")[1]
    maxx = upper_corner.split(" ")[0]
    maxy = upper_corner.split(" ")[1]
    return bbox_value_to_polygon(mapper, minx, miny, maxx, maxy)


def parse_operation_urls(mapper, el):
    """
    Parst alle OperationUrls (GetCapabilities, GetFeature, DescribeFeatureType, etc.)
    aus einem <ows:OperationsMetadata>-Element eines WFS-Capabilities-Dokuments.

    Gibt eine Liste von WebMapServiceOperationUrl-Instanzen zurück.
    """
    instances = []
    nsmap = mapper.mapping.get("_namespaces", None)

    # Iteriere über alle <ows:Operation>-Elemente
    for op_el in el.xpath("./ows:Operation", namespaces=nsmap):
        operation_name = op_el.get("name")
        if not operation_name:
            continue

        # Enum-Objekt für die Operation (z. B. OGCOperationEnum.GetFeature)
        try:
            operation_enum = OGCOperationEnum(operation_name)
        except ValueError:
            continue

        # Suche nach relevanten Format-Parametern
        # (AcceptFormats)
        format_values = []
        for param_el in op_el.xpath(
            "./ows:Parameter[@name='outputFormat']/ows:AllowedValues/ows:Value",
            namespaces=nsmap,
        ):
            if param_el.text:
                format_values.append(param_el)

        # Iteriere über DCP/HTTP/GET|POST URLs
        for method in ("Get", "Post"):
            urls = op_el.xpath(
                f"./ows:DCP/ows:HTTP/ows:{method}",
                namespaces=nsmap,
            )

            try:
                method_enum = HttpMethodEnum(method)
            except ValueError:
                continue

            for url_el in urls:
                href = url_el.xpath("./@xlink:href", namespaces=nsmap)
                if not href or not href[0]:
                    continue

                op_inst = WebFeatureServiceOperationUrl(
                    operation=operation_enum,
                    method=method_enum,
                    url=href[0].strip(),
                )

                # Pfad speichern (Cache)
                path = url_el.getroottree().getpath(url_el)
                mapper.store_to_cache(path, op_inst)

                # MIME-Typen als MimeType-Objekte anhängen
                op_inst._mime_types_parsed = []
                for fmt in format_values:
                    mime_inst = MimeType(mime_type=fmt.text.strip())
                    fmt_path = fmt.getroottree().getpath(fmt)
                    mapper.store_to_cache(fmt_path, mime_inst)
                    op_inst._mime_types_parsed.append(mime_inst)

                instances.append(op_inst)

    return instances
