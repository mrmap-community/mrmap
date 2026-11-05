"""Bounded generation of WFS monitoring probes from the stored capabilities.

The web feature service sibling of
:mod:`registry.helper.monitoring_generation`: same transient, read-only
contract — it writes no settings, no probes and executes no request against
the registered service, it only proposes. Every proposal mirrors the fields of
the concrete probe models in :mod:`registry.models.monitoring` so that the
persistence of the epic can store it without further interpretation.

The presets follow the epic:

* ``basic`` — GetCapabilities plus one representative bounded GetFeature probe.
* ``standard`` — basic plus one bounded GetFeature probe per selected feature
  type.
* ``comprehensive`` — standard plus a DescribeFeatureType probe per feature
  type, but only where the service advertises that operation and the required
  parameters can be satisfied. Everything else is reported as an explicit skip.

Every protocol decision comes from the STORED capabilities document: the
advertised WFS version, the operation endpoints, the feature types with their
formats, CRSs and extents and the count bound the service advertises for
GetFeature. Only versions whose requests this registry can actually build and
execute are offered — see :data:`SUPPORTED_VERSIONS`; a service stored with
another version is answered with ``version`` instead of being proposed probes
the monitoring could never run.

The requests are always bounded: a probe names only stored feature types and
limits the response with the count parameter the protocol version knows
(``COUNT`` for 2.x, ``MAXFEATURES`` for 1.1.0 — see
:meth:`registry.ows_lib.wfs.wfs.WebFeatureServiceClient.get_feature_kvp_request`).
"""
from lxml import etree

from registry.enums.service import OGCServiceVersionEnum
from registry.helper.monitoring_generation import (
    DEFAULT_PROBE_LIMIT, DEFAULT_TIMEOUT, GENERATOR_VERSION,
    IMPLEMENTED_PRESETS, MAX_PROBES, MAX_RESPONSE_BYTES, MAX_SKIPPED_REPORTED,
    MAX_TIMEOUT, PRESET_BASIC, PRESET_COMPREHENSIVE, PRESET_STANDARD,
    SkipReason, _Lookup, candidate_identifier, request_summary, window)
from registry.helper.preview import PreviewError, integer, parse_xml
from registry.models.service import FeatureType
from registry.ows_lib.client.exceptions import InitialError
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient

#: the WFS versions this generator proposes probes for. It is exactly the set
#: of versions whose key-value requests AND operation endpoint lookup the
#: client implements: 2.0.0/2.0.2 use TYPENAMES/COUNT, 1.1.0 uses
#: TYPENAME/MAXFEATURES and both find their endpoints in the OWS Common
#: OperationsMetadata of the document. A WFS 1.0.0 document has no
#: OperationsMetadata, so no request of a probe could be built — offering it
#: would advertise a version this registry can not monitor.
SUPPORTED_VERSIONS = ("1.1.0", "2.0.0", "2.0.2")

#: upper bound of features a single bounded GetFeature probe requests
MAX_FEATURES = 100
DEFAULT_MAX_FEATURES = 10

#: response formats whose body the feature collection check can inspect as XML,
#: ordered by preference; the first advertised match is proposed
XML_FORMAT_PREFERENCE = (
    "application/gml+xml; version=3.2",
    "text/xml; subtype=gml/3.2",
    "gml32",
    "gml3",
    "GML3",
    "GML32",
    "text/xml; subtype=gml/3.1.1",
    "text/xml; subtype=gml/2.1.2",
    "GML2",
    "application/gml+xml",
    "text/xml",
    "application/xml",
    "xml",
)
#: response formats whose body the feature collection check can inspect as JSON
JSON_FORMAT_PREFERENCE = (
    "application/json",
    "application/geo+json",
    "json",
    "geojson",
)

#: the operations each preset of the WFS generator proposes
WFS_OPERATIONS = {
    PRESET_BASIC: ["GetCapabilities", "GetFeature"],
    PRESET_STANDARD: ["GetCapabilities", "GetFeature"],
    PRESET_COMPREHENSIVE: [
        "GetCapabilities", "GetFeature", "DescribeFeatureType"],
}

CRS_URN_PREFIX = "urn:ogc:def:crs:"


class WfsSkipReason:
    """The explicit reasons a feature type or operation gets no probe."""

    UNKNOWN_FEATURE_TYPE = "unknownFeatureType"
    NO_SUPPORTED_FORMAT = "noSupportedFormat"
    NOT_ADVERTISED = "operationNotAdvertised"


def _stored_client(service) -> WebFeatureServiceClient:
    """The WFS client on the capabilities stored for the service.

    Never sends anything and never falls back to the model's remote reload.
    """
    try:
        if not service.xml_backup_file:
            raise PreviewError("discovery")
        capabilities = service.xml_backup
    except (FileNotFoundError, ValueError):
        raise PreviewError("discovery")
    client = WebFeatureServiceClient(
        capabilities=etree.tostring(parse_xml(capabilities)))
    if client.service_version != OGCServiceVersionEnum(service.version).label:
        raise PreviewError("discovery")
    return client


def _operation_node(client, operation: str):
    """The OperationsMetadata node of an operation, if the document has one."""
    return client._capabilities_etree.xpath(
        "//*[local-name()='OperationsMetadata']"
        "/*[local-name()='Operation' and @name='%s']" % operation)[:1] or [None]


def _advertised(client, operation: str) -> bool:
    """Whether the document advertises a GET endpoint for an operation."""
    node = _operation_node(client, operation)[0]
    if node is None:
        return False
    return bool(node.xpath(
        ".//*[local-name()='DCP']/*[local-name()='HTTP']"
        "/*[local-name()='Get']"))


def _operation_formats(client, operation: str) -> list:
    """The response formats an operation advertises as its outputFormat values."""
    node = _operation_node(client, operation)[0]
    if node is None:
        return []
    values = node.xpath(
        "./*[local-name()='Parameter' or local-name()='Constraint']"
        "[translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
        "'abcdefghijklmnopqrstuvwxyz')='outputformat']"
        "//*[local-name()='Value']/text()")
    return list(dict.fromkeys(
        value.strip() for value in values if value.strip()))


def _count_bound(client):
    """The count the service advertises as its own upper bound, if any.

    WFS 2.x names the constraint ``CountDefault``, WFS 1.1.0 ``MaxFeatures``.
    A proposed request never exceeds it — a probe which asks for more features
    than the service answers with by one request would fail for a healthy
    service.
    """
    node = _operation_node(client, "GetFeature")[0]
    if node is None:
        return None
    for name in ("CountDefault", "MaxFeatures", "countDefault"):
        for value in node.xpath(
                "./*[local-name()='Constraint'][@name='%s']"
                "/*[local-name()='DefaultValue' or local-name()='Value']"
                "/text()" % name):
            try:
                return int(value.strip())
            except ValueError:
                continue
    return None


def _feature_type_nodes(client) -> dict:
    """Every capabilities FeatureType node by its advertised Name, first wins."""
    nodes = {}
    for node in client._capabilities_etree.xpath(
            "//*[local-name()='FeatureType']"):
        name = (node.findtext("{*}Name") or "").strip()
        if name and name not in nodes:
            nodes[name] = node
    return nodes


def _canonical_crs(value: str):
    """The stored shape of an advertised CRS reference.

    The registry stores a CRS as ``PREFIX:CODE`` (see
    ``registry.mappers.parsers.value.srs_to_prefix``), so a document carrying
    ``urn:ogc:def:crs:EPSG::4326`` and the stored reference system
    ``EPSG:4326`` describe the same system. Compared canonically, the proposal
    can name the stored system which the request builder sends.
    """
    value = (value or "").strip()
    if not value:
        return None
    if value.startswith(CRS_URN_PREFIX):
        parts = value.split(":")
        # urn : ogc : def : crs : <prefix> : <version> : <code>
        if len(parts) > 6 and parts[4]:
            return f"{parts[4]}:{parts[6]}"
        return None
    return value.upper() if value.upper().startswith(("EPSG:", "CRS:")) else value


def _advertised_crs(node) -> set:
    """The CRSs advertised for a feature type, in the stored shape."""
    values = set()
    for element in node.xpath(
            "./*[local-name()='DefaultCRS' or local-name()='OtherCRS'"
            " or local-name()='DefaultSRS' or local-name()='OtherSRS'"
            " or local-name()='SRS']"):
        canonical = _canonical_crs(element.text or "")
        if canonical:
            values.add(canonical)
    return values


def _advertised_formats(client, node) -> list:
    """The GetFeature response formats of a feature type.

    The WFS 2.0 spec falls back to the formats the GetFeature operation
    advertises when the feature type names none — the same rule the
    ``FeatureType.output_formats`` field documents.
    """
    values = [value.strip() for value in node.xpath(
        "./*[local-name()='OutputFormats']/*[local-name()='Format']/text()")
        if value.strip()]
    if values:
        return list(dict.fromkeys(values))
    return _operation_formats(client, "GetFeature")


def _select_format(formats: list):
    """The format to request and whether its response can be inspected.

    Prefers a GML/XML format: it is the protocol default and the response the
    XML checks of the probe understand. Falls back to an advertised JSON
    format, which the feature collection check reads as GeoJSON. Without an
    inspectable format no output format is requested at all — the service
    answers its default (GML) — and the content checks stay at the exception
    level instead of forcing an unknown body through a parser.

    Returns:
        tuple: (format or None, whether the response body is inspectable)
    """
    if not formats:
        # the WFS protocol default of a GetFeature response is GML and a
        # DescribeFeatureType response is an XML schema, so a document which
        # names no formats at all is inspected as XML
        return None, True
    lowered = {value.lower(): value for value in formats}
    for preferred in XML_FORMAT_PREFERENCE:
        if preferred.lower() in lowered:
            return lowered[preferred.lower()], True
    for preferred in JSON_FORMAT_PREFERENCE:
        if preferred.lower() in lowered:
            return lowered[preferred.lower()], True
    return None, False


def _select_schema_format(formats: list):
    """The format a DescribeFeatureType probe shall request.

    The response of the operation is an XML schema document, so only an
    advertised XML format is usable — asking for a JSON one would propose a
    probe whose schema check can never pass. A document naming no formats at
    all keeps the protocol default, which IS the XML schema.

    Returns:
        tuple: (format or None, whether the response body is inspectable)
    """
    if not formats:
        return None, True
    lowered = {value.lower(): value for value in formats}
    for preferred in XML_FORMAT_PREFERENCE:
        if preferred.lower() in lowered:
            return lowered[preferred.lower()], True
    return None, False


def _skip(reason: str, feature_type, detail: str) -> dict:
    return {"reason": reason, "featureType": feature_type, "detail": detail}


def _get_feature_probe(client, lookup, feature_type, node, max_features,
                       timeout, format_override):
    """Propose the bounded GetFeature probe of one feature type or its skip.

    Returns:
        tuple: (probe dict or None, skip dict or None)
    """
    identifier = (feature_type.identifier or "").strip()
    if not identifier:
        return None, _skip(
            SkipReason.GROUP_LAYER, None,
            "feature type without an advertised Name can not be requested")
    if not feature_type.is_active:
        return None, _skip(
            SkipReason.INACTIVE, identifier,
            "feature type is deactivated in the registry")
    if node is None:
        return None, _skip(
            SkipReason.STALE, identifier,
            "the stored capabilities do not advertise this feature type anymore")

    advertised_formats = _advertised_formats(client, node)
    if format_override and format_override not in advertised_formats:
        return None, _skip(
            WfsSkipReason.NO_SUPPORTED_FORMAT, identifier,
            f"the feature type does not advertise the requested response "
            f"format {format_override}")
    if format_override:
        output_format = format_override
        inspectable = _select_format([format_override])[1]
    else:
        output_format, inspectable = _select_format(advertised_formats)

    crs = (str(feature_type.default_reference_system)
           if feature_type.default_reference_system_id else None)
    advertised_crs = _advertised_crs(node)
    if crs and advertised_crs and crs not in advertised_crs:
        return None, _skip(
            SkipReason.UNSUPPORTED_CRS, identifier,
            f"the stored default reference system {crs} is not advertised for "
            f"the feature type ({', '.join(sorted(advertised_crs))})")

    # the service's own advertised bound limits what may be requested
    bound = _count_bound(client)
    features = min(max_features, bound) if bound else max_features

    try:
        request = client.get_feature_kvp_request(
            type_names=[identifier],
            max_features=features,
            srs_name=crs,
            output_format=output_format)
    except (InitialError, ValueError) as error:
        return None, _skip(
            SkipReason.OPERATION_UNSUPPORTED, identifier,
            f"the GetFeature request can not be built: {error}")

    probe = {
        "candidateId": candidate_identifier("GetFeature", [identifier]),
        "probeType": "GetFeature",
        "targetFeatureType": {
            "id": str(feature_type.pk), "identifier": identifier,
            "title": feature_type.title},
        "parameters": {
            "featureTypes": [identifier],
            "featureTypeIds": [str(feature_type.pk)],
            "crs": crs,
            "crsId": lookup.reference_system_id(crs) if crs else None,
            "outputFormat": output_format,
            "outputFormatId": (lookup.mime_type_id(output_format)
                               if output_format else None),
            "maxFeatures": features,
            "timeout": timeout,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
            "checkFeatureCollection": inspectable,
            "expectFeatures": False,
        },
        "supported": {
            "crs": sorted(advertised_crs),
            "formats": advertised_formats,
            "countBound": bound,
            "maxFeatures": MAX_FEATURES},
        "requestSummary": request_summary(request, "GetFeature"),
    }
    return probe, None


def _describe_probes(client, lookup, feature_type, node, timeout, formats):
    """Propose the DescribeFeatureType probe of one feature type or its skip.

    The comprehensive operation of a WFS: it validates that the service can
    still describe the stored feature types. Only an advertised XML format is
    proposed, since the probe validates an XML schema document.

    Returns:
        tuple: (probe dict or None, skip dict or None)
    """
    identifier = (feature_type.identifier or "").strip()
    if not identifier or not feature_type.is_active or node is None:
        # the GetFeature proposal of the same feature type already reported
        # why this feature type does not become a probe at all
        return None, None

    output_format, inspectable = _select_schema_format(formats)
    if not inspectable:
        return None, _skip(
            WfsSkipReason.NO_SUPPORTED_FORMAT, identifier,
            "the DescribeFeatureType operation advertises no XML response "
            "format the schema check could validate")

    try:
        request = client.describe_feature_type_request(
            type_names=[identifier],
            output_format=[output_format] if output_format else None)
    except (InitialError, ValueError) as error:
        return None, _skip(
            SkipReason.OPERATION_UNSUPPORTED, identifier,
            f"the DescribeFeatureType request can not be built: {error}")

    probe = {
        "candidateId": candidate_identifier("DescribeFeatureType", [identifier]),
        "probeType": "DescribeFeatureType",
        "targetFeatureType": {
            "id": str(feature_type.pk), "identifier": identifier,
            "title": feature_type.title},
        "parameters": {
            "featureTypes": [identifier],
            "featureTypeIds": [str(feature_type.pk)],
            "outputFormat": output_format,
            "outputFormatId": (lookup.mime_type_id(output_format)
                               if output_format else None),
            "timeout": timeout,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
        },
        "supported": {
            "formats": formats},
        "requestSummary": request_summary(request, "DescribeFeatureType"),
    }
    return probe, None


def _scan_feature_types(client, lookup, feature_types, nodes, max_features,
                        timeout, format_override, selection, comprehensive,
                        describe_formats, describes_advertised):
    """Deterministic scan over the stored feature types of the service.

    Returns one group of probes per proposed feature type (the bounded
    GetFeature probe and, for the comprehensive preset, its
    DescribeFeatureType probe) and the ordered skips. The group is the unit
    the preview pages over: a comprehensive probe is never answered without
    the standard probe of its own feature type.
    """
    groups = []
    skips = []
    selected = set(selection)
    matched = set()
    for feature_type in feature_types:
        identifier = (feature_type.identifier or "").strip()
        tokens = {value for value in (identifier, str(feature_type.pk)) if value}
        if selection and tokens & selected:
            matched |= tokens
        in_page = not selection or bool(tokens & matched)

        probe, skip = _get_feature_probe(
            client, lookup, feature_type, nodes.get(identifier),
            max_features, timeout, format_override)
        group = []
        if in_page and probe is not None:
            group.append(probe)
        elif in_page and skip is not None:
            skips.append(skip)

        if comprehensive and in_page and probe is not None:
            if not describes_advertised:
                skips.append(_skip(
                    WfsSkipReason.NOT_ADVERTISED, identifier,
                    "the capabilities advertise no Get endpoint for the "
                    "DescribeFeatureType operation"))
            else:
                described, skip = _describe_probes(
                    client, lookup, feature_type, nodes.get(identifier),
                    timeout, describe_formats)
                if described is not None:
                    group.append(described)
                elif skip is not None:
                    skips.append(skip)
        if group:
            groups.append(group)

    for token in selection:
        if token not in matched:
            skips.append(_skip(
                WfsSkipReason.UNKNOWN_FEATURE_TYPE, token,
                "the service registers no feature type with this identifier"))
    return groups, skips


def _feature_types(service):
    """The stored feature types of the service in deterministic order.

    An own query instead of the relation of the given instance: the endpoints
    of the registry prefetch the feature types narrowed to the columns their
    serializer answers, and such a deferred relation can not additionally be
    traversed for the reference system this proposal needs.
    """
    return list(FeatureType.objects
                .filter(service=service)
                .select_related("default_reference_system")
                .prefetch_related("output_formats")
                .order_by("identifier", "pk"))


def _request_bounds(query):
    """The validated request parameters shared by preview and apply."""
    timeout = integer(query.get("timeout"), DEFAULT_TIMEOUT, MAX_TIMEOUT)
    max_features = integer(
        query.get("maxFeatures"), DEFAULT_MAX_FEATURES, MAX_FEATURES)
    limit = integer(query.get("limit"), DEFAULT_PROBE_LIMIT, MAX_PROBES)
    try:
        offset = int(query.get("offset") or 0)
    except (TypeError, ValueError):
        raise PreviewError("offset", 400)
    if offset < 0:
        raise PreviewError("offset", 400)
    return {"timeout": timeout, "maxFeatures": max_features,
            "limit": limit, "offset": offset}


def _selection(query):
    """The explicitly selected feature types, by identifier or by id."""
    if hasattr(query, "getlist"):
        values = ([value.strip() for value in query.getlist("featureType")
                   if value.strip()]
                  + [value.strip() for value in query.getlist("layer")
                     if value.strip()])
    else:
        values = []
        for name in ("featureType", "layer"):
            value = query.get(name) or []
            values.extend([value.strip()] if isinstance(value, str) and value.strip()
                          else [item for item in value if item])
    return values


def _service_state(service, query):
    """Everything a preview and an apply need to read from the service.

    Raises the same PreviewErrors for both, so a preview which can not be
    generated now can not be applied either.
    """
    if getattr(service, "service_type", None) != "WFS":
        raise PreviewError("serviceType", 400)
    if not service.is_active:
        raise PreviewError("disabled", 423)

    client = _stored_client(service)
    if client.service_version not in SUPPORTED_VERSIONS:
        # honest about what this registry can execute — see SUPPORTED_VERSIONS
        raise PreviewError("version", 422)

    preset = (query.get("preset") or PRESET_STANDARD).strip().lower()
    if preset not in IMPLEMENTED_PRESETS:
        raise PreviewError("preset", 400)

    format_override = (query.get("outputFormat") or "").strip() or None
    get_feature_formats = _operation_formats(client, "GetFeature")
    if format_override and get_feature_formats \
            and format_override not in get_feature_formats:
        # the same rule as the WMS preview: an overridden format must be one
        # the service really advertises for the operation
        raise PreviewError("formatOverride", 400)
    service_skips = []
    capabilities_request = None
    try:
        capabilities_request = client.get_capabilities_request()
    except InitialError:
        service_skips.append(_skip(
            SkipReason.OPERATION_UNSUPPORTED, None,
            "the capabilities advertise no GetCapabilities endpoint"))
    get_feature_advertised = _advertised(client, "GetFeature")
    if not get_feature_advertised:
        service_skips.append(_skip(
            SkipReason.OPERATION_UNSUPPORTED, None,
            "the capabilities advertise no GetFeature endpoint"))
    describes_advertised = _advertised(client, "DescribeFeatureType")
    describe_formats = _operation_formats(client, "DescribeFeatureType") \
        if describes_advertised else []

    state = {
        "client": client,
        "preset": preset,
        "comprehensive": preset == PRESET_COMPREHENSIVE,
        "service_skips": service_skips,
        "capabilities_request": capabilities_request,
        "describes_advertised": describes_advertised,
        "describe_formats": describe_formats,
        "format_override": format_override,
        "count_bound": _count_bound(client),
        "advertised": {
            "GetCapabilities": capabilities_request is not None,
            "GetFeature": get_feature_advertised,
            "DescribeFeatureType": describes_advertised},
    }
    return state


def generate_wfs_probe_preview(service, query) -> dict:
    """Propose the monitoring probes of a registered WFS from its stored capabilities.

    Args:
        service (WebFeatureService): the registered service to inspect
        query (dict-like): the request parameters ``preset``, ``featureType``
            (repeatable selection by identifier or id), ``offset``, ``limit``,
            ``timeout`` and ``maxFeatures``

    Returns:
        dict: the preview contract (probes, skips, pagination and bounds)

    Raises:
        PreviewError: on an invalid parameter, a non-WFS service, an
            unsupported stored version or missing stored capabilities
    """
    state = _service_state(service, query)
    client = state["client"]
    bounds = _request_bounds(query)
    preset = state["preset"]

    lookup = _Lookup()
    groups, skips = _scan_feature_types(
        client, lookup, _feature_types(service), _feature_type_nodes(client),
        bounds["maxFeatures"], bounds["timeout"], state["format_override"],
        _selection(query), state["comprehensive"], state["describe_formats"],
        state["describes_advertised"])

    probes = []
    if state["capabilities_request"] is not None:
        probes.append({
            "candidateId": candidate_identifier("GetCapabilities", []),
            "probeType": "GetCapabilities",
            "targetFeatureType": None,
            "parameters": {
                "timeout": bounds["timeout"],
                "maxResponseBytes": MAX_RESPONSE_BYTES},
            "supported": {},
            "requestSummary": request_summary(
                state["capabilities_request"], "GetCapabilities"),
        })

    total = len(groups)
    if preset == PRESET_BASIC:
        # one representative bounded GetFeature of the first feature type
        page = list(groups[0][:1]) if groups else []
        consumed = min(1, total)
    else:
        page, consumed = window(groups, bounds["offset"], bounds["limit"])
    probes.extend(page)

    reported = state["service_skips"] + skips
    offset = bounds["offset"]
    limit = bounds["limit"]
    return {
        "serviceId": str(service.pk),
        "serviceTitle": service.title,
        "preset": preset,
        "generatorVersion": GENERATOR_VERSION,
        "wfsVersion": client.service_version,
        "bounds": {
            "maxTimeout": MAX_TIMEOUT,
            "maxFeatures": MAX_FEATURES,
            "defaultMaxFeatures": DEFAULT_MAX_FEATURES,
            "advertisedCountBound": state["count_bound"],
            "maxResponseBytes": MAX_RESPONSE_BYTES,
            "maxProbes": MAX_PROBES,
            "defaultLimit": DEFAULT_PROBE_LIMIT},
        "presets": {
            "implemented": list(IMPLEMENTED_PRESETS),
            "notImplemented": []},
        "operations": WFS_OPERATIONS,
        "advertisedOperations": state["advertised"],
        "supportedVersions": list(SUPPORTED_VERSIONS),
        "request": {
            "timeout": bounds["timeout"],
            "maxFeatures": bounds["maxFeatures"],
            "outputFormat": state["format_override"]},
        "pagination": {
            "offset": offset, "limit": limit,
            "totalFeatureCandidates": total,
            "truncated": bool(preset != PRESET_BASIC
                              and offset + consumed < total),
            "selectionRequired": total > MAX_PROBES and not _selection(query)},
        "probes": probes,
        "skipped": reported[:MAX_SKIPPED_REPORTED],
        "skippedTotal": len(reported),
        "skippedTruncated": len(reported) > MAX_SKIPPED_REPORTED,
    }


def wfs_candidate_map(service) -> dict:
    """The candidates the WFS generator currently proposes for the service.

    The revalidation source of the apply, without pagination and with the
    generator's default request parameters — see
    :func:`registry.helper.monitoring_generation.current_candidate_map`.
    """
    state = _service_state(service, {})
    client = state["client"]

    lookup = _Lookup()
    groups, _skips = _scan_feature_types(
        client, lookup, _feature_types(service), _feature_type_nodes(client),
        DEFAULT_MAX_FEATURES, DEFAULT_TIMEOUT, None,
        # preset agnostic on purpose: the map answers every candidate the
        # current capabilities can produce, so an apply of any preset
        # revalidates against the same map
        [], True, state["describe_formats"], state["describes_advertised"])

    candidates = {
        probe["candidateId"]: probe
        for group in groups for probe in group}
    if state["capabilities_request"] is not None:
        candidates[candidate_identifier("GetCapabilities", [])] = {
            "candidateId": candidate_identifier("GetCapabilities", []),
            "probeType": "GetCapabilities",
            "targetFeatureType": None,
            "parameters": {
                "timeout": DEFAULT_TIMEOUT,
                "maxResponseBytes": MAX_RESPONSE_BYTES},
            "supported": {},
        }
    return candidates
