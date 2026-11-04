"""Bounded generation of WMS monitoring probes from the stored capabilities.

Transient by design: the generation proposes probe parameters and request
summaries for the monitoring preview endpoint. It writes no settings, no
probes and executes no request against the registered service. Every probe it
proposes can be persisted through the concrete probe models of
``registry.models.monitoring`` (the persistence child of the epic) without
further interpretation: the parameters mirror the fields of those models.

The presets follow the epic:

* ``basic`` — GetCapabilities plus one representative GetMap probe.
* ``standard`` — basic plus one GetMap probe per selected named layer.
* ``comprehensive`` — not implemented yet; reported explicitly.

Protocol decisions (advertised operations, formats, styles, dimensions and
the BBOX axis order) are read from the stored capabilities document through
the existing :class:`registry.ows_lib.wms.wms.WebMapServiceClient`; inherited
layer values come from the existing inherited-attribute queries of the
:class:`registry.models.service.Layer` queryset.
"""
import hashlib
from urllib.parse import urlsplit, urlunsplit

from lxml import etree
from registry.enums.service import HttpMethodEnum, OGCOperationEnum, OGCServiceVersionEnum
from registry.helper.preview import PreviewError, integer, parse_xml
from registry.models.metadata import MimeType, ReferenceSystem
from registry.ows_lib.client.exceptions import InitialError
from registry.ows_lib.wms.wms import WebMapServiceClient

#: version of the generation logic; part of every preview response so that a
#: consumer can tell which rules produced a proposal
GENERATOR_VERSION = "1.0.0"

PRESET_BASIC = "basic"
PRESET_STANDARD = "standard"
PRESET_COMPREHENSIVE = "comprehensive"
IMPLEMENTED_PRESETS = (PRESET_BASIC, PRESET_STANDARD)
#: the operations the comprehensive preset of the epic shall add once it exists
COMPREHENSIVE_OPERATIONS = ("GetFeatureInfo", "DescribeFeatureType")

# explicit bounds: a preview never grows over them and a large service is
# proposed through selection and pagination instead of unbounded
MAX_IMAGE_DIMENSION = 2048
MAX_TIMEOUT = 120
DEFAULT_TIMEOUT = 30
DEFAULT_IMAGE_DIMENSION = 256
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PROBES = 100
DEFAULT_PROBE_LIMIT = 25
MAX_SKIPPED_REPORTED = 200

# the CRSs whose request extent the stored geographic bbox can serialize
# without a native BoundingBox; ordered by preference
GEOGRAPHIC_PREFERENCE = ("CRS:84", "EPSG:4326", "EPSG:4258")
# the dimensions the GetMap request builder is able to express
REQUESTABLE_DIMENSIONS = {"time": "TIME", "elevation": "ELEVATION"}

VERSION_DEFAULT_EXCEPTIONS = {
    "1.3.0": "XML",
    "1.1.1": "application/vnd.ogc.se_xml",
}


class SkipReason:
    """The explicit reasons a layer or operation does not become a probe."""

    GROUP_LAYER = "groupLayer"
    INACTIVE = "inactive"
    STALE = "stale"
    NO_EXTENT = "noExtent"
    UNSUPPORTED_CRS = "unsupportedCrs"
    UNSUPPORTED_DIMENSION = "unsupportedDimension"
    UNAVAILABLE_DIMENSION = "unavailableDimension"
    FIXED_DIMENSIONS = "fixedDimensions"
    OPERATION_UNSUPPORTED = "operationUnsupported"
    UNKNOWN_LAYER = "unknownLayer"


def candidate_identifier(probe_type: str, identifiers: list) -> str:
    """The stable identity of a proposed probe.

    It is derived from the target of the probe (its type and the layer
    identifiers) and neither from the preset nor from the currently proposed
    parameters: the same target proposed under another preset or after a
    capabilities update is the same candidate, which lets the persistence of
    the epic's child issue recognize and deduplicate it.
    """
    digest = hashlib.sha256("|".join([
        "mrmap-monitoring-probe", probe_type,
        ",".join(identifiers)]).encode())
    return digest.hexdigest()[:20]


def generated_identity(service_pk, probe_type: str, identifiers: list) -> str:
    """The stable identity of a PERSISTED generated probe.

    The service-scoped variant of :func:`candidate_identifier`: layer
    identifiers are only unique inside one service, so the identity which the
    database pins with its unique constraint additionally names the service.
    Like the candidate identity it is derived from the target only — never
    from the preset or the current parameters — which is what makes repeated,
    retried and concurrent applies of the same candidate recognize the
    existing row instead of duplicating it.
    """
    digest = hashlib.sha256("|".join([
        "mrmap-monitoring-probe-identity", str(service_pk), probe_type,
        ",".join(identifiers)]).encode())
    return digest.hexdigest()[:20]


def request_summary(request, operation: str) -> dict:
    """The request a probe would send, prepared without a session.

    The registered credentials live in the session of the client, never in
    the summary; a userinfo part which an advertised operation url carries is
    stripped before the summary leaves the generator.
    """
    url = request.prepare().url
    parts = urlsplit(url)
    if parts.username or parts.password:
        netloc = parts.hostname or ""
        if parts.port:
            netloc = f"{netloc}:{parts.port}"
        url = urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return {"method": request.method, "operation": operation, "url": url}


def _stored_client(service) -> WebMapServiceClient:
    """The WMS client on the capabilities stored for the service.

    A missing or corrupted backup never triggers the model's remote fallback
    and the client is never used to send anything: generation reads the
    advertised state only.
    """
    try:
        if not service.xml_backup_file:
            # no document was ever stored for this service
            raise PreviewError("discovery")
        capabilities = service.xml_backup
    except (FileNotFoundError, ValueError):
        raise PreviewError("discovery")
    client = WebMapServiceClient(capabilities=etree.tostring(parse_xml(capabilities)))
    if client.service_version != OGCServiceVersionEnum(service.version).label:
        raise PreviewError("discovery")
    return client


class _Lookup:
    """Small caches which keep the per-layer generation free of re-queries."""

    def __init__(self):
        self._mime_types = {}
        self._reference_systems = {}

    def mime_type_id(self, mime_type: str):
        if mime_type not in self._mime_types:
            self._mime_types[mime_type] = MimeType.objects.filter(
                mime_type=mime_type).values_list("pk", flat=True).first()
        return self._mime_types[mime_type]

    def reference_system_id(self, crs: str):
        if crs not in self._reference_systems:
            prefix, _, code = crs.partition(":")
            self._reference_systems[crs] = ReferenceSystem.objects.filter(
                prefix=prefix, code=code).values_list("pk", flat=True).first()
        return self._reference_systems[crs]


def _advertised_image_formats(client) -> list:
    """The GetMap response formats which an image probe can validate."""
    formats = client._capabilities_etree.findall(
        "{*}Capability/{*}Request/{*}GetMap/{*}Format")
    return [value for value in
            ((value.text or "").strip() for value in formats)
            if value.startswith("image/") and "svg" not in value.lower()]


def _exception_format(client) -> str:
    formats = client._capabilities_etree.findall(
        "{*}Capability/{*}Exception/{*}Format")
    advertised = [(value.text or "").strip() for value in formats]
    preferred = next((value for value in advertised if value.lower() in {
        "xml", "application/xml", "text/xml",
        "application/vnd.ogc.se_xml"}), None)
    return preferred or VERSION_DEFAULT_EXCEPTIONS.get(
        client.service_version, "XML")


def _node_map(client) -> dict:
    """Every capabilities Layer node by its advertised Name, first wins."""
    nodes = {}
    for node in client._capabilities_etree.xpath("//*[local-name()='Layer']"):
        name = (node.findtext("{*}Name") or "").strip()
        if name and name not in nodes:
            nodes[name] = node
    return nodes


def _ancestors(node) -> list:
    """The capabilities Layer chain from the root down to the node itself."""
    return list(node.xpath("ancestor-or-self::*[local-name()='Layer']"))


def _advertised_crs(node, client) -> set:
    values = set()
    for ancestor in _ancestors(node):
        for element in ancestor.findall(f"{{*}}{client.crs_qp}"):
            values.update(
                part.upper() for part in (element.text or "").split() if part)
    return values


def _inherited_styles(node) -> list:
    """All styles advertised for the node or an ancestor, in document order."""
    styles = []
    for ancestor in _ancestors(node):
        for style in ancestor.findall("{*}Style"):
            name = (style.findtext("{*}Name") or "").strip()
            if name and name not in styles:
                styles.append(name)
    return styles


def _default_style_name(node) -> str:
    """The style a GetMap shall request to render the layer as advertised.

    The first Style of the deepest layer in the chain which advertises one;
    an advertised style without a Name keeps the server default (ogc wms
    1.1.1 7.1.4.5.8 / 1.3.0 7.2.4.6.9). This mirrors
    :meth:`registry.models.service.Layer.get_default_style` which the
    executing GetMapProbe uses on the stored rows.
    """
    for ancestor in reversed(_ancestors(node)):
        styles = ancestor.findall("{*}Style")
        if styles:
            return (styles[0].findtext("{*}Name") or "").strip()
    return ""


def _fixed_dimensions(node) -> tuple:
    attributes = {}
    for ancestor in _ancestors(node):
        attributes.update(ancestor.attrib)
    return (int(attributes.get("fixedWidth", "0") or 0),
            int(attributes.get("fixedHeight", "0") or 0))


def _dimensions(node) -> dict:
    """The effective dimensions of a layer, inherited down the chain.

    Returns a mapping of the lower-cased dimension name to its resolved
    proposal: ``None`` when the declared dimension is required but no value
    can be read from the document (which makes the layer not proposable), a
    mapping with ``default`` and/or ``value`` otherwise. Declarations of a
    deeper layer replace same-named inherited ones.
    """
    declared = {}
    for ancestor in _ancestors(node):
        for dimension in ancestor.findall("{*}Dimension"):
            for name in (dimension.get("name") or "").lower().split():
                declared.setdefault(name, {"default": None, "values": []})
                default = (dimension.get("default") or "").strip()
                if default:
                    declared[name]["default"] = default
                # 1.3.0 carries the advertised values inside the Dimension
                # element itself
                values = [value.strip() for value in (dimension.text or "").split(",")
                          if value.strip()]
                if values:
                    declared[name]["values"] = values
        for extent in ancestor.findall("{*}Extent"):
            for name in (extent.get("name") or "").lower().split():
                declaration = declared.setdefault(name, {"default": None, "values": []})
                default = (extent.get("default") or "").strip()
                if default:
                    declaration["default"] = default
                values = [value.strip() for value in (extent.text or "").split(",")
                          if value.strip()]
                if values:
                    declaration["values"] = values
    effective = {}
    for name, declaration in declared.items():
        default = declaration["default"]
        values = declaration["values"]
        if default:
            # the server applies its default when the request omits the
            # dimension, so no value is sent
            effective[name] = {"default": default, "value": None}
        elif values:
            # a required dimension is requested with its first advertised value
            effective[name] = {"default": None, "value": values[0]}
        else:
            # required and nothing to request it with: not proposable
            effective[name] = None
    return effective


def _select_crs(client, node, identifier: str) -> str:
    """The CRS the probe for this layer shall use, deterministic per state.

    Only a CRS which is advertised for the layer and whose BBOX can be
    serialized is chosen: a geographic CRS first, then an EPSG coded CRS
    which advertises a native BoundingBox.
    """
    advertised = _advertised_crs(node, client)
    if not advertised:
        raise ValueError(f"{SkipReason.UNSUPPORTED_CRS}|the layer advertises no CRS")
    for crs in GEOGRAPHIC_PREFERENCE:
        if crs in advertised:
            return crs
    native = client._native_layer_bboxes(identifier)
    projected = sorted(
        crs for crs in advertised
        if crs.startswith("EPSG:") and crs in native)
    if projected:
        return projected[0]
    raise ValueError(
        f"{SkipReason.UNSUPPORTED_CRS}|none of the advertised CRSs "
        f"({', '.join(sorted(advertised))}) is geographic or advertises a "
        "native bounding box in an EPSG coded CRS")


def _skip(reason: str, layer, detail: str) -> dict:
    return {"reason": reason, "layer": layer, "detail": detail}


def _layer_probe(client, lookup, layer, node, width, height, timeout,
                 exceptions, format_override, crs_override):
    """Propose the GetMap probe of one layer or report why it is not proposable.

    Returns:
        tuple: (probe dict or None, skip dict or None)
    """
    identifier = (layer.identifier or "").strip()
    if not identifier:
        return None, _skip(
            SkipReason.GROUP_LAYER, None,
            "layer without an advertised Name is not renderable on its own")
    if not layer.is_active:
        return None, _skip(
            SkipReason.INACTIVE, identifier,
            "layer is deactivated in the registry")
    if node is None:
        return None, _skip(
            SkipReason.STALE, identifier,
            "the stored capabilities do not advertise this layer anymore")

    geographic = getattr(layer, "bbox_lat_lon_inherited", None)
    if geographic is None or geographic.empty:
        return None, _skip(
            SkipReason.NO_EXTENT, identifier,
            "no geographic bounding box stated or inherited by the layer")

    image_formats = _advertised_image_formats(client)
    try:
        if crs_override:
            if crs_override not in _advertised_crs(node, client):
                raise ValueError(
                    f"{SkipReason.UNSUPPORTED_CRS}|'{crs_override}' is not "
                    "advertised for the layer")
            crs = crs_override
        else:
            crs = _select_crs(client, node, identifier)
    except ValueError as error:
        reason, _, detail = str(error).partition("|")
        return None, _skip(reason, identifier, detail)

    fixed_width, fixed_height = _fixed_dimensions(node)
    if (fixed_width and fixed_width != width) \
            or (fixed_height and fixed_height != height):
        return None, _skip(
            SkipReason.FIXED_DIMENSIONS, identifier,
            "the layer only renders the fixed image dimensions "
            f"{fixed_width}x{fixed_height}")

    dimensions = _dimensions(node)
    for name, proposal in sorted(dimensions.items()):
        if name not in REQUESTABLE_DIMENSIONS:
            return None, _skip(
                SkipReason.UNSUPPORTED_DIMENSION, identifier,
                f"dimension '{name}' can not be expressed by the GetMap "
                "probe abstraction")
        if proposal is None:
            return None, _skip(
                SkipReason.UNAVAILABLE_DIMENSION, identifier,
                f"dimension '{name}' is required but advertises no value "
                "the probe could request")

    try:
        bbox, axis_order = client.get_map_bbox(
            crs=crs, layer_name=identifier, geographic=geographic)
    except ValueError as error:
        return None, _skip(SkipReason.UNSUPPORTED_CRS, identifier, str(error))

    style = _default_style_name(node)
    image_format = format_override or next(
        (value for value in ("image/png", "image/jpeg") if value in image_formats),
        image_formats[0] if image_formats else "")

    parameters = {
        "layers": [identifier],
        "layerIds": [str(layer.pk)],
        "styles": [style],
        "crs": crs,
        "crsId": lookup.reference_system_id(crs),
        "format": image_format,
        "formatId": lookup.mime_type_id(image_format),
        "bbox": [float(value) for value in geographic.extent],
        "requestBbox": [float(value) for value in bbox],
        "axisOrder": axis_order,
        "width": width,
        "height": height,
        "timeout": timeout,
        "maxResponseBytes": MAX_RESPONSE_BYTES,
        "exceptions": exceptions,
        "dimensionDefaults": {
            name: proposal["default"] for name, proposal in sorted(dimensions.items())
            if proposal and proposal["default"]},
    }
    request_kwargs = {}
    for name, proposal in dimensions.items():
        if proposal and proposal["value"]:
            if name == "time":
                parameters["time"] = [proposal["value"]]
                request_kwargs["time"] = [proposal["value"]]
            elif name == "elevation":
                try:
                    elevation = float(proposal["value"])
                except ValueError:
                    return None, _skip(
                        SkipReason.UNAVAILABLE_DIMENSION, identifier,
                        f"dimension '{name}' advertises the non-numeric "
                        f"value '{proposal['value']}'")
                parameters["elevation"] = elevation
                request_kwargs["elevation"] = elevation

    try:
        request = client.get_map_request(
            layers=[identifier], styles=[style], crs=crs, bbox=bbox,
            width=width, height=height, format=image_format,
            exceptions=exceptions, **request_kwargs)
    except (InitialError, ValueError) as error:
        return None, _skip(
            SkipReason.OPERATION_UNSUPPORTED, identifier,
            f"the GetMap request can not be built: {error}")

    probe = {
        "candidateId": candidate_identifier("GetMap", [identifier]),
        "probeType": "GetMap",
        "targetLayer": {
            "id": str(layer.pk), "identifier": identifier, "title": layer.title},
        "parameters": parameters,
        "supported": {
            "crs": sorted(_advertised_crs(node, client)),
            "formats": image_formats,
            "styles": _inherited_styles(node),
            "dimensions": sorted(dimensions)},
        "requestSummary": request_summary(request, "GetMap"),
    }
    return probe, None


def _scan_layers(client, lookup, layers, nodes, width, height, timeout,
                 exceptions, format_override, crs_override, selection):
    """Run the per-layer proposal in one deterministic scan over the service tree.

    ``selection`` is the set of layer identifiers or ids explicitly requested;
    when it is non-empty only the selected layers are proposed. Returns the
    ordered proposals and the ordered skips of the scanned layers.
    """
    proposals = []
    skips = []
    selected = set(selection)
    matched = set()
    for layer in layers:
        identifier = (layer.identifier or "").strip()
        tokens = {value for value in (identifier, str(layer.pk)) if value}
        if selection and tokens & selected:
            matched |= tokens
        probe, skip = _layer_probe(
            client, lookup, layer, nodes.get(identifier),
            width, height, timeout, exceptions, format_override, crs_override)
        if selection and not tokens & matched:
            # an explicitly requested probe must not appear for other layers
            continue
        if probe is not None:
            proposals.append(probe)
        elif skip is not None and (not selection or tokens & matched):
            skips.append(skip)
    for identifier in selection:
        if identifier not in matched:
            skips.append(_skip(
                SkipReason.UNKNOWN_LAYER, identifier,
                "the service registers no layer with this identifier"))
    return proposals, skips


def generate_probe_preview(service, query) -> dict:
    """Propose the monitoring probes of a registered WMS from its stored capabilities.

    Args:
        service (WebMapService): the registered service to inspect
        query (dict-like): the request parameters ``preset``, ``layer``
            (repeatable selection by identifier or layer id), ``offset``,
            ``limit``, ``width``, ``height``, ``timeout``, ``imageFormat`` and
            ``crs``

    Returns:
        dict: the preview contract (probes, skips, pagination and bounds)

    Raises:
        PreviewError: on an invalid parameter, a non-WMS service or missing
            stored capabilities
    """
    if getattr(service, "service_type", None) != "WMS":
        raise PreviewError("serviceType", 400)
    if not service.is_active:
        raise PreviewError("disabled", 423)

    preset = (query.get("preset") or PRESET_STANDARD).strip().lower()
    if preset == PRESET_COMPREHENSIVE:
        raise PreviewError("presetNotImplemented", 400)
    if preset not in IMPLEMENTED_PRESETS:
        raise PreviewError("preset", 400)

    width = integer(query.get("width"), DEFAULT_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION)
    height = integer(query.get("height"), DEFAULT_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION)
    timeout = integer(query.get("timeout"), DEFAULT_TIMEOUT, MAX_TIMEOUT)
    limit = integer(query.get("limit"), DEFAULT_PROBE_LIMIT, MAX_PROBES)
    try:
        offset = int(query.get("offset") or 0)
    except (TypeError, ValueError):
        raise PreviewError("offset", 400)
    if offset < 0:
        raise PreviewError("offset", 400)

    client = _stored_client(service)
    if client.service_version not in {"1.1.1", "1.3.0"}:
        raise PreviewError("version", 422)

    format_override = (query.get("imageFormat") or "").strip() or None
    crs_override = (query.get("crs") or "").strip().upper() or None
    if crs_override and not crs_override.startswith(("EPSG:", "CRS:")):
        raise PreviewError("crsOverride", 400)

    exceptions = _exception_format(client)
    image_formats = _advertised_image_formats(client)
    if format_override and format_override not in image_formats:
        raise PreviewError("formatOverride", 400)

    # the operation endpoints the service advertises; a probe without its
    # advertised endpoint is reported, never proposed
    service_skips = []
    capabilities_request = None
    try:
        capabilities_request = client.get_capabilities_request()
    except InitialError:
        service_skips.append(_skip(
            SkipReason.OPERATION_UNSUPPORTED, None,
            "the capabilities advertise no GetCapabilities endpoint"))
    try:
        client.get_operation_url_by_name_and_method(
            OGCOperationEnum.GET_MAP, HttpMethodEnum.GET)
    except InitialError:
        service_skips.append(_skip(
            SkipReason.OPERATION_UNSUPPORTED, None,
            "the capabilities advertise no GetMap endpoint"))
    if not image_formats and not format_override:
        # without a renderable format every GetMap candidate would be a
        # misleading probe, so this is the state of the whole service
        raise PreviewError("noImageFormat", 422)

    layers = list(service.layers.with_inherited_attributes_cte()
                  .order_by("mptt_tree_id", "mptt_lft")
                  .prefetch_related("styles", "mptt_parent__styles"))
    nodes = _node_map(client)
    if hasattr(query, "getlist"):
        selection = [value.strip() for value in query.getlist("layer") if value.strip()]
    else:
        value = query.get("layer") or []
        selection = [value] if isinstance(value, str) else [
            item for item in value if item]

    lookup = _Lookup()
    proposals, skips = _scan_layers(
        client, lookup, layers, nodes, width, height, timeout,
        exceptions, format_override, crs_override, selection)

    probes = []
    if capabilities_request is not None:
        probes.append({
            "candidateId": candidate_identifier("GetCapabilities", []),
            "probeType": "GetCapabilities",
            "targetLayer": None,
            "parameters": {
                "timeout": timeout,
                "maxResponseBytes": MAX_RESPONSE_BYTES},
            "supported": {},
            "requestSummary": request_summary(capabilities_request, "GetCapabilities"),
        })

    total = len(proposals)
    page = proposals[:1] if preset == PRESET_BASIC else proposals[offset:offset + limit]
    probes.extend(page)

    reported = service_skips + skips
    return {
        "serviceId": str(service.pk),
        "serviceTitle": service.title,
        "preset": preset,
        "generatorVersion": GENERATOR_VERSION,
        "wmsVersion": client.service_version,
        "bounds": {
            "maxImageDimension": MAX_IMAGE_DIMENSION,
            "maxTimeout": MAX_TIMEOUT,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
            "maxProbes": MAX_PROBES,
            "defaultLimit": DEFAULT_PROBE_LIMIT},
        "presets": {
            "implemented": list(IMPLEMENTED_PRESETS),
            "notImplemented": [PRESET_COMPREHENSIVE]},
        "notImplemented": {
            "preset": PRESET_COMPREHENSIVE,
            "operations": list(COMPREHENSIVE_OPERATIONS),
            "note": "the comprehensive preset, which would add the additional "
                    "advertised operations, is not implemented yet"},
        "request": {
            "width": width, "height": height, "timeout": timeout,
            "format": format_override, "crs": crs_override},
        "pagination": {
            "offset": offset, "limit": limit,
            "totalGetMapCandidates": total,
            "truncated": bool(preset != PRESET_BASIC and offset + limit < total),
            "selectionRequired": total > MAX_PROBES and not selection},
        "probes": probes,
        "skipped": reported[:MAX_SKIPPED_REPORTED],
        "skippedTotal": len(reported),
        "skippedTruncated": len(reported) > MAX_SKIPPED_REPORTED,
    }


def current_candidate_map(service) -> dict:
    """The candidates the generator currently proposes for the service.

    The revalidation source of the apply action of the epic's persistence
    child: it answers every candidate which the CURRENT stored capabilities
    can produce — a full deterministic scan without pagination and with the
    generator's default request parameters — keyed by its ``candidateId``.
    A candidate of an outdated preview which is not in this map is stale: the
    capabilities changed and a new preview is required before persisting.

    The proposal parameters are the regeneration's current parameters: the
    customization rule of the persistence compares the stored parameters of a
    generated probe against exactly these.

    Raises:
        PreviewError: the same codes as :func:`generate_probe_preview` — a
            preview which can not be generated now can not be applied either.
    """
    if getattr(service, "service_type", None) != "WMS":
        raise PreviewError("serviceType", 400)
    if not service.is_active:
        raise PreviewError("disabled", 423)

    client = _stored_client(service)
    if client.service_version not in {"1.1.1", "1.3.0"}:
        raise PreviewError("version", 422)

    exceptions = _exception_format(client)
    image_formats = _advertised_image_formats(client)
    if not image_formats:
        raise PreviewError("noImageFormat", 422)

    capabilities_request = None
    try:
        capabilities_request = client.get_capabilities_request()
    except InitialError:
        pass

    layers = list(service.layers.with_inherited_attributes_cte()
                  .order_by("mptt_tree_id", "mptt_lft")
                  .prefetch_related("styles", "mptt_parent__styles"))
    proposals, _skips = _scan_layers(
        client, _Lookup(), layers, _node_map(client),
        DEFAULT_IMAGE_DIMENSION, DEFAULT_IMAGE_DIMENSION, DEFAULT_TIMEOUT,
        exceptions, None, None, [])

    candidates = {
        proposal["candidateId"]: proposal for proposal in proposals}
    if capabilities_request is not None:
        candidates[candidate_identifier("GetCapabilities", [])] = {
            "candidateId": candidate_identifier("GetCapabilities", []),
            "probeType": "GetCapabilities",
            "targetLayer": None,
            "parameters": {
                "timeout": DEFAULT_TIMEOUT,
                "maxResponseBytes": MAX_RESPONSE_BYTES},
            "supported": {},
        }
    return candidates
