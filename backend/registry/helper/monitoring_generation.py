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
the stored read of :mod:`registry.helper.preview`, which answers a
:class:`registry.ows_lib.wms.wms.WebMapServiceClient`; inherited layer values
come from the existing inherited-attribute queries of the
:class:`registry.models.service.Layer` queryset.
"""
import hashlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.helper.preview import PreviewError, integer, stored_client
from registry.models.metadata import MimeType, ReferenceSystem
from registry.ows_lib.client.exceptions import InitialError
from registry.ows_lib.wms.wms import LAYER_CHAIN, WebMapServiceClient

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

# the capabilities element which carries the name of a layer or a style; the
# element is named the same in every version, only its namespace differs
NAME_QP = "{*}Name"

# the CRSs whose request extent the stored geographic bbox can serialize
# without a native BoundingBox; ordered by preference
GEOGRAPHIC_PREFERENCE = ("CRS:84", "EPSG:4326", "EPSG:4258")
# the dimensions the GetMap request builder is able to express
REQUESTABLE_DIMENSIONS = {"time": "TIME", "elevation": "ELEVATION"}

VERSION_DEFAULT_EXCEPTIONS = {
    "1.3.0": "XML",
    "1.1.1": "application/vnd.ogc.se_xml",
}


@dataclass(frozen=True)
class _RequestOptions:
    """The request wide state which every probe of one answer shares.

    The scan threads these through its steps: they come from the request
    parameters and the version defaults which the generation reads from the
    service, and no single layer proposal changes them.
    """

    width: int
    height: int
    timeout: int
    exceptions: str
    format_override: Optional[str] = None
    crs_override: Optional[str] = None


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
    """The exception format a probe of this service shall ask for.

    An advertised XML format is preferred, because the probe reads the error
    message out of the response. What is advertised but not XML is
    deliberately NOT proposed: a service which draws its exceptions into the
    image (se_inimage) would answer a failing GetMap with a valid image and
    hide the failure. With nothing usable advertised the request carries the
    default of its own version (ogc wms 1.1.1 7.3.3.4 / 1.3.0 7.2.4.3), which
    a server that can not honor it reports loudly.
    """
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
        name = (node.findtext(NAME_QP) or "").strip()
        if name and name not in nodes:
            nodes[name] = node
    return nodes


def _ancestors(node) -> list:
    """The capabilities Layer chain from the root down to the node itself."""
    return list(node.xpath(LAYER_CHAIN))


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
            name = (style.findtext(NAME_QP) or "").strip()
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
            return (styles[0].findtext(NAME_QP) or "").strip()
    return ""


def _fixed_dimensions(node) -> tuple:
    """The image dimensions a layer only renders at, inherited down the chain.

    Raises:
        ValueError: when the document advertises a dimension which can not be
            read; a layer with an unreadable constraint is not proposable.
    """
    attributes = {}
    for ancestor in _ancestors(node):
        attributes.update(ancestor.attrib)
    dimensions = []
    for name in ("fixedWidth", "fixedHeight"):
        value = (attributes.get(name) or "0").strip()
        try:
            dimensions.append(int(value))
        except ValueError:
            raise ValueError(
                f"{SkipReason.FIXED_DIMENSIONS}|the layer advertises the "
                f"unreadable {name} '{value}'") from None
        if dimensions[-1] < 0:
            raise ValueError(
                f"{SkipReason.FIXED_DIMENSIONS}|the layer advertises the "
                f"negative {name} '{value}'")
    return tuple(dimensions)


def _declared_values(element) -> list:
    """The values a dimension declaration carries inside its own element.

    Only 1.3.0 writes them there; 1.1.1 keeps them in the ``Extent`` sibling,
    which is the same read on a different element.
    """
    return [value.strip() for value in (element.text or "").split(",")
            if value.strip()]


def _declare_dimension(declared: dict, element) -> None:
    """One ``Dimension`` or ``Extent`` declaration into the gathered ones.

    Both elements carry the names in the ``name`` attribute, the default in
    the ``default`` attribute and the advertised values in the element itself.
    A later declaration of the same name replaces what it states and keeps
    what it does not.
    """
    default = (element.get("default") or "").strip()
    values = _declared_values(element)
    for name in (element.get("name") or "").lower().split():
        declaration = declared.setdefault(name, {"default": None, "values": []})
        declaration["default"] = default or declaration["default"]
        declaration["values"] = values or declaration["values"]


def _declared_dimensions(node) -> dict:
    """The dimension declarations of the layer chain, in document order."""
    declared = {}
    for ancestor in _ancestors(node):
        elements = ancestor.findall("{*}Dimension") + ancestor.findall("{*}Extent")
        for element in elements:
            _declare_dimension(declared, element)
    return declared


def _resolve_dimension(declaration: dict):
    """What a probe shall do with one declared dimension.

    Returns:
        dict: ``default`` and ``value`` of the proposal, ``None`` when the
            dimension is required but advertises nothing to request it with
    """
    if declaration["default"]:
        # the server applies its default when the request omits the
        # dimension, so no value is sent
        return {"default": declaration["default"], "value": None}
    if declaration["values"]:
        # a required dimension is requested with its first advertised value
        return {"default": None, "value": declaration["values"][0]}
    # required and nothing to request it with: not proposable
    return None


def _dimensions(node) -> dict:
    """The effective dimensions of a layer, inherited down the chain.

    Returns a mapping of the lower-cased dimension name to its resolved
    proposal: ``None`` when the declared dimension is required but no value
    can be read from the document (which makes the layer not proposable), a
    mapping with ``default`` and/or ``value`` otherwise. Declarations of a
    deeper layer replace same-named inherited ones.
    """
    declared = _declared_dimensions(node)
    return {name: _resolve_dimension(declaration)
            for name, declaration in declared.items()}


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


def _not_renderable(layer, node, identifier: str):
    """Why this layer can not be rendered on its own, or None when it can."""
    if not identifier:
        return _skip(
            SkipReason.GROUP_LAYER, None,
            "layer without an advertised Name is not renderable on its own")
    if not layer.is_active:
        return _skip(
            SkipReason.INACTIVE, identifier,
            "layer is deactivated in the registry")
    if node is None:
        return _skip(
            SkipReason.STALE, identifier,
            "the stored capabilities do not advertise this layer anymore")
    return None


def _geographic_extent(layer):
    """The geographic bounding box the layer states or inherits, or None."""
    geographic = getattr(layer, "bbox_lat_lon_inherited", None)
    if geographic is None or geographic.empty:
        return None
    return geographic


def _probe_crs(client, node, identifier: str, crs_override) -> str:
    """The CRS a probe of this layer shall use.

    Raises:
        ValueError: as ``reason|detail`` when an override is not advertised
            for the layer or no CRS can be selected from the document.
    """
    if crs_override:
        if crs_override not in _advertised_crs(node, client):
            raise ValueError(
                f"{SkipReason.UNSUPPORTED_CRS}|'{crs_override}' is not "
                "advertised for the layer")
        return crs_override
    return _select_crs(client, node, identifier)


def _check_fixed_dimensions(node, width: int, height: int) -> None:
    """Refuse a layer which only renders other image dimensions than asked.

    Raises:
        ValueError: as ``reason|detail`` when the layer only renders image
            dimensions other than the ones the request asks for.
    """
    fixed_width, fixed_height = _fixed_dimensions(node)
    if (fixed_width and fixed_width != width) \
            or (fixed_height and fixed_height != height):
        raise ValueError(
            f"{SkipReason.FIXED_DIMENSIONS}|the layer only renders the fixed "
            f"image dimensions {fixed_width}x{fixed_height}")


def _dimensions_skip(dimensions: dict, identifier: str):
    """Why the declared dimensions make the layer not proposable, or None."""
    for name, proposal in sorted(dimensions.items()):
        if name not in REQUESTABLE_DIMENSIONS:
            return _skip(
                SkipReason.UNSUPPORTED_DIMENSION, identifier,
                f"dimension '{name}' can not be expressed by the GetMap "
                "probe abstraction")
        if proposal is None:
            return _skip(
                SkipReason.UNAVAILABLE_DIMENSION, identifier,
                f"dimension '{name}' is required but advertises no value "
                "the probe could request")
    return None


def _image_format(image_formats: list, format_override) -> str:
    """The format a GetMap probe of this service shall ask for.

    An explicit override wins, it was checked against the advertised ones.
    Otherwise PNG before JPEG: a monitoring probe reads the response bytes,
    and an exception drawn into a lossy image is harder to interpret.
    """
    if format_override:
        return format_override
    for value in ("image/png", "image/jpeg"):
        if value in image_formats:
            return value
    return image_formats[0] if image_formats else ""


def _dimension_values(dimensions: dict) -> tuple:
    """The GetMap keyword arguments the advertised dimension values need.

    Returns:
        tuple: the keyword arguments and the name of the dimension whose
            advertised value the request can not carry, when there is one.
    """
    request_kwargs = {}
    for name, proposal in sorted(dimensions.items()):
        value = proposal["value"] if proposal else None
        if not value:
            continue
        if name == "elevation":
            try:
                request_kwargs[name] = float(value)
            except ValueError:
                return request_kwargs, name
        elif name == "time":
            request_kwargs[name] = [value]
    return request_kwargs, None


def _dimension_parameters(dimensions: dict, identifier: str) -> tuple:
    """The dimension part of a probe and of the request which proves it.

    Returns:
        tuple: the defaults the server applies on its own, the keyword
            arguments the GetMap must carry and the skip which says when an
            advertised value can not be requested.
    """
    defaults = {name: proposal["default"]
                for name, proposal in sorted(dimensions.items())
                if proposal and proposal["default"]}
    request_kwargs, unusable = _dimension_values(dimensions)
    if unusable is None:
        return defaults, request_kwargs, None
    return {}, {}, _skip(
        SkipReason.UNAVAILABLE_DIMENSION, identifier,
        f"dimension '{unusable}' advertises the non-numeric value "
        f"'{dimensions[unusable]['value']}'")


def _getmap_probe(client, lookup, layer, node, identifier, geographic, crs,
                  dimensions, image_formats, options):
    """The GetMap proposal of a layer whose advertised state is proposable."""
    try:
        bbox, axis_order = client.get_map_bbox(
            crs=crs, layer_name=identifier, geographic=geographic)
    except ValueError as error:
        return None, _skip(SkipReason.UNSUPPORTED_CRS, identifier, str(error))

    defaults, request_kwargs, skip = _dimension_parameters(dimensions, identifier)
    if skip is not None:
        return None, skip

    style = _default_style_name(node)
    image_format = _image_format(image_formats, options.format_override)
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
        "width": options.width,
        "height": options.height,
        "timeout": options.timeout,
        "maxResponseBytes": MAX_RESPONSE_BYTES,
        "exceptions": options.exceptions,
        "dimensionDefaults": defaults,
    }
    parameters.update(request_kwargs)

    try:
        request = client.get_map_request(
            layers=[identifier], styles=[style], crs=crs, bbox=bbox,
            width=options.width, height=options.height, format=image_format,
            exceptions=options.exceptions, **request_kwargs)
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


def _layer_probe(client, lookup, layer, node, image_formats, options):
    """Propose the GetMap probe of one layer or report why it is not proposable.

    The checks run in the order in which a reviewer reads the state of the
    layer: is it renderable at all, does it state an extent, can it be asked
    for in a CRS and at the requested image dimensions, and can its
    dimensions be expressed. The first unmet condition is the reported skip.

    Returns:
        tuple: (probe dict or None, skip dict or None)
    """
    identifier = (layer.identifier or "").strip()
    skip = _not_renderable(layer, node, identifier)
    geographic = None
    crs = None
    dimensions = {}

    if skip is None:
        geographic = _geographic_extent(layer)
        if geographic is None:
            skip = _skip(
                SkipReason.NO_EXTENT, identifier,
                "no geographic bounding box stated or inherited by the layer")

    if skip is None:
        try:
            crs = _probe_crs(client, node, identifier, options.crs_override)
            _check_fixed_dimensions(node, options.width, options.height)
        except ValueError as error:
            reason, _, detail = str(error).partition("|")
            skip = _skip(reason, identifier, detail)

    if skip is None:
        dimensions = _dimensions(node)
        skip = _dimensions_skip(dimensions, identifier)

    if skip is not None:
        return None, skip
    return _getmap_probe(
        client, lookup, layer, node, identifier, geographic, crs, dimensions,
        image_formats, options)


def _layer_tokens(layer) -> set:
    """The values a caller can select this layer by: its name and its id."""
    identifier = (layer.identifier or "").strip()
    return {value for value in (identifier, str(layer.pk)) if value}


def _matched_tokens(layers, requested: set) -> set:
    """The tokens of the layers which an explicit selection does select."""
    matched = set()
    for layer in layers:
        tokens = _layer_tokens(layer)
        if tokens & requested:
            matched |= tokens
    return matched


def _unknown_selection(selection: list, matched: set) -> list:
    """The skips of the requested layers which the service does not register."""
    skips = []
    for identifier in selection:
        if identifier not in matched:
            skips.append(_skip(
                SkipReason.UNKNOWN_LAYER, identifier,
                "the service registers no layer with this identifier"))
    return skips


def _scan_layers(client, lookup, layers, nodes, image_formats, selection,
                 options):
    """Run the per-layer proposal in one deterministic scan over the service tree.

    ``selection`` is the set of layer identifiers or ids explicitly requested;
    when it is non-empty only the selected layers are proposed. Returns the
    ordered proposals and the ordered skips of the scanned layers.
    """
    proposals = []
    skips = []
    requested = set(selection)
    matched = _matched_tokens(layers, requested)
    for layer in layers:
        identifier = (layer.identifier or "").strip()
        selected = bool(_layer_tokens(layer) & matched)
        probe, skip = _layer_probe(
            client, lookup, layer, nodes.get(identifier), image_formats,
            options)
        if requested and not selected:
            # an explicitly requested probe must not appear for other layers
            continue
        if probe is not None:
            proposals.append(probe)
        elif skip is not None and (not requested or selected):
            skips.append(skip)
    skips.extend(_unknown_selection(selection, matched))
    return proposals, skips


def _preset(query) -> str:
    """The preset of the request, validated against what is implemented.

    Raises:
        PreviewError: ``presetNotImplemented`` for the preset of the epic
            which does not exist yet, ``preset`` for anything unknown.
    """
    preset = (query.get("preset") or PRESET_STANDARD).strip().lower()
    if preset == PRESET_COMPREHENSIVE:
        raise PreviewError("presetNotImplemented", 400)
    if preset not in IMPLEMENTED_PRESETS:
        raise PreviewError("preset", 400)
    return preset


def _offset(query) -> int:
    """The first proposal of the answer, validated.

    Raises:
        PreviewError: ``offset`` for a value which is not a position.
    """
    try:
        offset = int(query.get("offset") or 0)
    except (TypeError, ValueError):
        raise PreviewError("offset", 400)
    if offset < 0:
        raise PreviewError("offset", 400)
    return offset


def _crs_override(query):
    """The CRS the caller asks all probes to use, validated.

    Raises:
        PreviewError: ``crsOverride`` for a code which is not an EPSG or CRS
            authority code, because the BBOX serialization depends on it.
    """
    crs_override = (query.get("crs") or "").strip().upper() or None
    if crs_override and not crs_override.startswith(("EPSG:", "CRS:")):
        raise PreviewError("crsOverride", 400)
    return crs_override


def _endpoint_state(client) -> tuple:
    """The GetCapabilities request of the service and the endpoints it lacks.

    A probe without its advertised endpoint is reported, never proposed, so a
    missing operation is a service wide skip rather than a failed request.
    """
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
    return capabilities_request, service_skips


def _request_selection(query) -> list:
    """The layers the caller selected, by identifier or by layer id."""
    if hasattr(query, "getlist"):
        return [value.strip() for value in query.getlist("layer") if value.strip()]
    value = query.get("layer") or []
    if isinstance(value, str):
        return [value]
    return [item for item in value if item]


def _page(proposals: list, preset: str, offset: int, limit: int) -> list:
    """The proposals this answer carries.

    ``basic`` asks for the single representative probe of the service, so it
    takes the first one; ``standard`` answers a page of the selection.
    """
    if preset == PRESET_BASIC:
        return proposals[:1]
    return proposals[offset:offset + limit]


def _pagination(offset: int, limit: int, total: int, preset: str,
                selection: list) -> dict:
    """Where this answer sits in the candidates and what the caller must do."""
    return {
        "offset": offset, "limit": limit,
        "totalGetMapCandidates": total,
        "truncated": bool(preset != PRESET_BASIC and offset + limit < total),
        "selectionRequired": total > MAX_PROBES and not selection}


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

    preset = _preset(query)

    width = integer(query.get("width"), DEFAULT_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION)
    height = integer(query.get("height"), DEFAULT_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION)
    timeout = integer(query.get("timeout"), DEFAULT_TIMEOUT, MAX_TIMEOUT)
    limit = integer(query.get("limit"), DEFAULT_PROBE_LIMIT, MAX_PROBES)
    offset = _offset(query)

    # the stored read of the live preview, for the protocol client: the bounded
    # session it carries is never used here, generation only reads the document
    client = stored_client(service, client_class=WebMapServiceClient)
    if client.service_version not in {"1.1.1", "1.3.0"}:
        raise PreviewError("version", 422)

    format_override = (query.get("imageFormat") or "").strip() or None
    crs_override = _crs_override(query)

    exceptions = _exception_format(client)
    image_formats = _advertised_image_formats(client)
    if format_override and format_override not in image_formats:
        raise PreviewError("formatOverride", 400)

    capabilities_request, service_skips = _endpoint_state(client)
    if not image_formats and not format_override:
        # without a renderable format every GetMap candidate would be a
        # misleading probe, so this is the state of the whole service
        raise PreviewError("noImageFormat", 422)

    layers = list(service.layers.with_inherited_attributes_cte()
                  .order_by("mptt_tree_id", "mptt_lft"))
    nodes = _node_map(client)
    selection = _request_selection(query)

    lookup = _Lookup()
    options = _RequestOptions(
        width=width, height=height, timeout=timeout, exceptions=exceptions,
        format_override=format_override, crs_override=crs_override)
    proposals, skips = _scan_layers(
        client, lookup, layers, nodes, image_formats, selection, options)

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
    probes.extend(_page(proposals, preset, offset, limit))

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
        "pagination": _pagination(offset, limit, total, preset, selection),
        "probes": probes,
        "skipped": reported[:MAX_SKIPPED_REPORTED],
        "skippedTotal": len(reported),
        "skippedTruncated": len(reported) > MAX_SKIPPED_REPORTED,
    }
