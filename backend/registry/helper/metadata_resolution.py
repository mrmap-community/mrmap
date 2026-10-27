""" Resolve which services can deliver a discovered metadata record.

    The resolver consumes the extraction of
    :mod:`registry.mappers.parsers.access_links` and answers, for one
    ``DatasetMetadataRecord`` or ``ServiceMetadataRecord``, the candidates
    which advertise access to the described resource:

    * the record's own advertised links (distribution links and service
      operation connect points),
    * the ``MetadataCouplingReference`` index rows of harvested service
      records which explicitly name the dataset, and
    * the registered resources already verified by a ``MetadataRelation``
      (``self_pointing_*``), kept apart from the remote candidates because
      their evidence is a stored relation, not an advertised URL.

    Discovery is cheap and performs no network request: it reads the stored
    xml of the record itself and the derived index. The endpoint answer is an
    explicit state per candidate:

    ``unvalidated``
        discovered from stored hints; the endpoint was not asked yet.
    ``resolved`` / ``ambiguous`` / ``unsupported`` / ``unavailable``
        answered by :func:`validate_capabilities_candidate`, which a user
        triggers explicitly. Only that step asks the remote endpoint, with a
        bounded time and response size, in an anonymous session which never
        forwards MrMap credentials, and only against a URL the record itself
        advertised.

    The resolver never writes: discovering a URL is not registering a service
    and never infers a ``MetadataRelation``.
"""

import time
from dataclasses import dataclass, replace
from enum import StrEnum
from urllib.parse import parse_qsl, urlsplit

from lxml import etree
from requests import Request, Session
from requests.exceptions import RequestException

from registry.mappers.parsers.access_links import (ExtractionStatus, LinkType,
                                                   extract_access_links)

# Budgets of one discovery: how many coupled service records are looked at
# and how many metadata references are resolved by origin url equality.
MAX_COUPLED_SERVICE_RECORDS = 10
MAX_METADATA_REFERENCE_RECORDS = 5

# Budgets of one capabilities validation, in the spirit of
# registry.helper.preview: a bounded time and a bounded response body.
CAPABILITIES_TIMEOUT = (3, 3)
CAPABILITIES_TIME_LIMIT = 15
CAPABILITIES_RESPONSE_LIMIT = 8 * 1024 * 1024
#: How many advertised names a validation answers at most.
ADVERTISED_NAMES_LIMIT = 100

#: Versions the MrMap viewer and registration flow can work with.
SUPPORTED_VERSIONS = {
    "WMS": {"1.1.1", "1.3.0"},
    "WFS": {"2.0.0"},
}

# Query parameters which describe a single operation call. A derived
# GetCapabilities candidate drops them; the hints of a resource stay on the
# candidate instead of the url. Everything else - the service token, the
# version and all vendor parameters - keeps its segment untouched.
OPERATION_QUERY_PARAMETERS = frozenset({
    "request", "outputformat", "count", "sortby", "maxfeatures",
    "typename", "typenames", "layers", "queryable", "transparent",
    "format", "styles", "srs", "crs", "bbox", "width", "height", "x", "y",
    "featureid", "fid", "exceptions",
})

# Operations whose URL is evidence enough to derive a GetCapabilities
# candidate, provided the service token is named by the url or the protocol.
DERIVABLE_OPERATIONS = frozenset({
    "getmap", "getfeatureinfo", "getfeature", "getpropertyvalue",
    "describefeaturetype", "getcoverage",
})


class CandidateState(StrEnum):
    """ Explicit state of a service candidate. """
    #: Discovered from stored hints; the endpoint was not asked.
    UNVALIDATED = "unvalidated"
    #: The endpoint answered capabilities which fit the candidate.
    RESOLVED = "resolved"
    #: The candidate needs a user selection (unmatched hints or several
    #: equally plausible targets).
    AMBIGUOUS = "ambiguous"
    #: What the endpoint or the hints describe is not a supported map or
    #: feature service.
    UNSUPPORTED = "unsupported"
    #: The endpoint could not be asked or did not answer usefully.
    UNAVAILABLE = "unavailable"


class CandidateSource(StrEnum):
    """ Where the evidence of a candidate comes from. """
    #: A link of the record's own distributionInfo.
    OWN_DISTRIBUTION = "own-distribution"
    #: A srv:connectPoint of the record's own containsOperations.
    OWN_OPERATION = "own-operation"
    #: The capabilities link of a harvested service record whose stored xml
    #: explicitly names the dataset.
    COUPLED_SERVICE_RECORD = "coupled-service-record"
    #: The origin url of a harvested record reached through an explicit
    #: metadata reference of the record.
    METADATA_REFERENCE_RECORD = "metadata-reference-record"


@dataclass(frozen=True)
class RegisteredTarget:
    """ A registered resource which a stored MetadataRelation verified. """
    resource_type: str
    id: int
    name: str
    service_id: int | None = None


@dataclass(frozen=True)
class ServiceCandidate:
    """ One advertised possibility to access the described resource. """
    #: The capabilities candidate url to ask; may equal the original url.
    url: str
    #: The url exactly as the record advertised it.
    original_url: str
    #: What the advertised url itself is, see LinkType.
    kind: LinkType
    #: How the candidate was found.
    source: CandidateSource
    #: The state; discovery only ever answers UNVALIDATED.
    state: CandidateState = CandidateState.UNVALIDATED
    #: The machine readable reason of a non unvalidated state.
    detail: str = ""
    #: The protocol string as advertised, e.g. OGC:WMS-1.3.0-...
    protocol: str | None = None
    #: The OGC service token, e.g. WMS or WFS.
    service: str | None = None
    #: A version named by the url or the protocol.
    advertised_version: str | None = None
    #: The operation name behind a connectPoint.
    operation: str | None = None
    #: WFS type name hints, kept apart from the url.
    type_names: tuple = ()
    #: WMS LAYERS hints, kept apart from the url.
    layers: tuple = ()
    #: The single best candidate of the resolution.
    preferred: bool = False
    #: Human readable proofs of why this candidate belongs to the record.
    evidence: tuple = ()
    #: Whether the capabilities url was derived from an operation url.
    derived: bool = False


@dataclass(frozen=True)
class RecordResolution:
    """ The discovery answer for one metadata record. """
    #: ExtractionStatus.OK plus the extraction detail for a broken backup.
    status: ExtractionStatus
    detail: str = ""
    file_identifier: str | None = None
    service_type: str | None = None
    service_type_version: str | None = None
    candidates: tuple = ()
    registered_targets: tuple = ()
    #: Links which advertise something but no service access, answered
    #: honestly instead of silently dropped.
    non_service_links: tuple = ()
    #: True when a budget cut the lookup; the answer may hold more.
    truncated: bool = False
    warnings: tuple = ()


@dataclass(frozen=True)
class ValidationResult:
    """ The answer of a user triggered capabilities validation. """
    state: CandidateState
    #: Machine readable reason: ok, not-advertised, not-fetchable, timeout,
    #: limit, redirected, denied, upstream, not-xml, parse, no-version,
    #: unsupported-service, exception-report:<code>, ...
    detail: str = ""
    service_type: str | None = None
    service_version: str | None = None
    #: The validation always asks the advertised capabilities by HTTP GET.
    method: str = "GET"
    #: Names the capabilities advertise, capped by ADVERTISED_NAMES_LIMIT.
    advertised_names: tuple = ()
    #: Hints the capabilities confirmed.
    matched_names: tuple = ()
    #: Hints the capabilities could not confirm.
    unresolved_hints: tuple = ()
    #: True when the capabilities hold more names than answered.
    names_truncated: bool = False


def stored_xml(record) -> bytes:
    """ The stored document of a record, empty when there is nothing to read.

        ``xml_backup`` opens the stored file, so a record whose file is gone
        raises instead of answering nothing - the same trap which
        :func:`registry.helper.preview.stored_client` guards. A resolution
        must not fail on that, and the extraction answers MISSING for the
        empty content, which is the honest state of such a record.

        :param record: a :class:`registry.models.document.DocumentModelMixin`
        :return: the stored bytes or an empty bytes value
    """
    try:
        return record.xml_backup or b""
    except (OSError, ValueError):
        return b""


def _version_from_protocol(protocol: str | None) -> str | None:
    """ Version token of an ``OGC:<SERVICE>-<VERSION>-...`` protocol. """
    if not protocol or not protocol.upper().startswith("OGC:"):
        return None
    parts = protocol[4:].split("-")
    return parts[1].strip() or None if len(parts) > 1 else None


def derive_capabilities_url(link) -> str | None:
    """ Derive the GetCapabilities url of an operation link.

        The query string is edited as raw segments: parameter name casing,
        value escaping (including escaped ampersands) and every vendor
        parameter survive untouched. Only the operation describing segments
        are dropped and the request segment is replaced in place, keeping its
        original spelling. Without a named service token the derivation
        refuses - the hints of the record must be sufficient.

        :param link: an :class:`registry.mappers.parsers.access_links.OnlineResourceLink`
        :return: the derived url or None when the hints are not sufficient
    """
    operation = (link.request or "").lower()
    if operation not in DERIVABLE_OPERATIONS:
        return None
    service = (link.service or "").upper() or None
    if service is None and link.protocol:
        token = link.protocol[4:].split("-", 1)[0].strip().upper() \
            if link.protocol.upper().startswith("OGC:") else ""
        service = token or None
    if service not in {"WMS", "WFS", "WCS", "CSW", "WMTS"}:
        return None

    parts = urlsplit(link.url)
    segments = parts.query.split("&") if parts.query else []
    kept = []
    request_segment = None
    service_segment = None
    for segment in segments:
        name = segment.split("=", 1)[0]
        lowered = name.lower()
        if lowered == "request":
            request_segment = segment
            continue
        if lowered == "service":
            service_segment = segment
        if lowered in OPERATION_QUERY_PARAMETERS:
            continue
        kept.append(segment)

    if request_segment is not None:
        name = request_segment.split("=", 1)[0]
        kept.append(f"{name}=GetCapabilities")
    else:
        kept.append("REQUEST=GetCapabilities")
    if service_segment is None:
        kept.append(f"SERVICE={service}")

    query = "&".join(kept)
    base = parts._replace(query="").geturl()
    return f"{base}?{query}" if query else base


def _query_values(parts, name: str, separator: str = "") -> tuple:
    """ Values one query parameter holds, the name casing ignored.

        Read with ``parse_qsl``, so a percent escaped value arrives unescaped
        and ``LAYERS`` is found like ``layers``. A separator splits the multi
        value parameters which OGC services write comma separated.
    """
    values = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() != name.lower() or not value:
            continue
        if separator:
            values.extend(part for part in value.split(separator) if part)
        else:
            values.append(value)
    return tuple(values)


def _dedup_key(url: str):
    """ Key which merges only endpoint equivalents.

        Scheme and host are case insensitive and a trailing slash is no
        difference; query parameters are compared name-insensitively but
        value-exactly, so different vendor parameters, different protocols or
        different type names never merge into one candidate.
    """
    parts = urlsplit(url)
    parameters = tuple(sorted(
        (name.lower(), value)
        for name, _, value in (
            segment.partition("=") for segment in parts.query.split("&")
            if segment)))
    return (
        parts.scheme.lower(),
        (parts.hostname or "").lower(),
        parts.port,
        parts.path.rstrip("/"),
        parameters,
    )


def _candidate_from_link(link, source: CandidateSource,
                         evidence: tuple) -> ServiceCandidate:
    """ Build the candidate of one extracted capability capable link. """
    derived_url = None
    derived = False
    if link.link_type == LinkType.CAPABILITIES:
        url = link.url
    else:
        derived_url = derive_capabilities_url(link)
        url = derived_url or link.url
        derived = derived_url is not None
    parts = urlsplit(link.url)
    advertised_version = _version_from_protocol(link.protocol)
    version_values = _query_values(parts, "version")
    if version_values:
        advertised_version = advertised_version or version_values[0]
    return ServiceCandidate(
        url=url,
        original_url=link.url,
        kind=link.link_type,
        source=source,
        protocol=link.protocol,
        service=(link.service or "").upper() or None,
        advertised_version=advertised_version,
        operation=link.request,
        type_names=link.type_names,
        layers=_query_values(parts, "layers", ","),
        evidence=evidence,
        derived=derived,
    )


def _merge_candidates(candidates: list) -> tuple:
    """ Deduplicate endpoint equivalents conservatively.

        Only endpoints which :func:`_dedup_key` calls equivalent merge - never
        a different vendor parameter, version or resource hint. Their evidence
        and hints union and the explicit capabilities endpoint wins over a
        derived twin of the same endpoint.
    """
    by_key = {}
    order = []
    for candidate in candidates:
        key = _dedup_key(candidate.url)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = candidate
            order.append(key)
            continue
        winner = candidate
        if (existing.kind == LinkType.CAPABILITIES
                and candidate.kind != LinkType.CAPABILITIES):
            # an explicit capabilities endpoint wins over a derived twin
            winner = existing
        by_key[key] = replace(
            winner,
            type_names=tuple(dict.fromkeys(
                existing.type_names + candidate.type_names)),
            layers=tuple(dict.fromkeys(
                existing.layers + candidate.layers)),
            evidence=tuple(dict.fromkeys(
                existing.evidence + candidate.evidence)))
    return tuple(by_key[key] for key in order)


def _mark_preferred(candidates: tuple) -> tuple:
    """ Mark the explicit capabilities candidate as the preferred one. """
    if not candidates:
        return candidates
    preferred = next((
        candidate for candidate in candidates
        if candidate.kind == LinkType.CAPABILITIES
        and not candidate.derived), None)
    if preferred is None:
        preferred = next((
            candidate for candidate in candidates
            if candidate.kind == LinkType.CAPABILITIES), None)
    if preferred is None:
        preferred = candidates[0]
    return tuple(
        replace(candidate, preferred=candidate is preferred)
        for candidate in candidates)


def _visible(user, queryset, model):
    """ Filter a queryset to the objects the user may view.

        ``user=None`` is the internal caller which is not restricted, e.g. a
        management command; a request always carries its user, so the API can
        not reach that branch.
    """
    from guardian.shortcuts import get_objects_for_user
    if user is None or user.is_superuser:
        return queryset
    return get_objects_for_user(
        user, f"registry.view_{model._meta.model_name}", klass=queryset)


def _registered_targets(record, user) -> tuple:
    """ The registered resources a stored MetadataRelation verified. """
    from registry.models.metadata import DatasetMetadataRecord
    from registry.models.service import (CatalogueService, FeatureType, Layer,
                                         WebFeatureService, WebMapService)
    targets = []
    if isinstance(record, DatasetMetadataRecord):
        pairs = (
            (record.self_pointing_layers.all(), Layer, "layer"),
            (record.self_pointing_feature_types.all(), FeatureType,
             "feature_type"),
        )
    else:
        pairs = (
            (record.self_pointing_wms.all(), WebMapService, "wms"),
            (record.self_pointing_wfs.all(), WebFeatureService, "wfs"),
            (record.self_pointing_csw.all(), CatalogueService, "csw"),
        )
    for queryset, model, kind in pairs:
        for resource in _visible(user, queryset, model).order_by("id"):
            targets.append(RegisteredTarget(
                resource_type=kind,
                id=resource.pk,
                name=str(resource),
                service_id=getattr(resource, "service_id", None)))
    return tuple(targets)


def _record_candidates(record, extraction) -> tuple:
    """ Candidates which the record's own extraction advertises. """
    candidates = []
    non_service = []
    for extracted in extraction.records:
        for link in extracted.links:
            evidence = (f"distribution link at {link.source}",)
            if link.link_type in (LinkType.CAPABILITIES,
                                  LinkType.OGC_OPERATION):
                candidates.append(_candidate_from_link(
                    link, CandidateSource.OWN_DISTRIBUTION, evidence))
            else:
                non_service.append({
                    "url": link.url,
                    "kind": str(link.link_type),
                    "name": link.name,
                    "evidence": evidence})
        for operation in extracted.operations:
            link = operation.connect_point
            if link is None:
                continue
            evidence = (f"operation {operation.name} at {operation.source}",)
            if link.link_type in (LinkType.CAPABILITIES,
                                  LinkType.OGC_OPERATION):
                candidates.append(_candidate_from_link(
                    link, CandidateSource.OWN_OPERATION, evidence))
            else:
                non_service.append({
                    "url": link.url, "kind": str(link.link_type),
                    "name": operation.name, "evidence": evidence})
    return candidates, non_service


def _coupled_service_candidates(dataset, user, warnings: list):
    """ Candidates from harvested service records naming the dataset.

        The reverse lookup is the derived ``MetadataCouplingReference`` index;
        only records the user may view are read and the number of parsed
        documents is bounded.

        :return: the candidates and whether a budget cut the lookup
        :rtype: tuple
    """
    from registry.enums.metadata import MetadataCouplingKindEnum
    from registry.models.metadata import (MetadataCouplingReference,
                                          ServiceMetadataRecord)
    references = list(
        MetadataCouplingReference.objects
        .for_dataset(dataset)
        .order_by("service_metadata_id", "id")
        .values("service_metadata_id", "reference_kind", "value"))
    if not references:
        return [], False
    service_ids = list(dict.fromkeys(
        reference["service_metadata_id"] for reference in references))
    visible = list(_visible(
        user,
        ServiceMetadataRecord.objects.filter(pk__in=service_ids),
        ServiceMetadataRecord).order_by("id")[:MAX_COUPLED_SERVICE_RECORDS])
    truncated = (
        len(service_ids) > MAX_COUPLED_SERVICE_RECORDS
        or len(visible) < len(service_ids))

    candidates = []
    for service_record in visible:
        evidence = tuple(
            "coupling reference "
            f"{MetadataCouplingKindEnum(reference['reference_kind']).label.lower()}"
            f" of service record {service_record.file_identifier}"
            f" names {reference['value']}"
            for reference in references
            if reference["service_metadata_id"] == service_record.pk)[:5]
        extraction = extract_access_links(
            stored_xml(service_record),
            origin_url=service_record.origin_url)
        if extraction.status != ExtractionStatus.OK:
            warnings.append(
                f"coupled service record {service_record.pk} has no readable"
                " stored xml")
            continue
        own_candidates, _ = _record_candidates(service_record, extraction)
        capabilities = [
            candidate for candidate in own_candidates
            if candidate.kind == LinkType.CAPABILITIES]
        for candidate in capabilities or own_candidates[:1]:
            candidates.append(replace(
                candidate,
                source=CandidateSource.COUPLED_SERVICE_RECORD,
                evidence=evidence))
    return candidates, truncated


def _metadata_reference_candidates(record, user, visited: set,
                                   warnings: list) -> tuple:
    """ Follow explicit metadata reference links to records in this MrMap.

        A reference is followed only when its url equals the ``origin_url``
        under which a visible metadata record was imported - evidence by
        exact equality, not by similarity. Bounded by a budget, a depth of
        one and the visited set of file identifiers, this is neither a
        catalogue crawl nor a recursive fetch; the second answer says whether
        that budget cut the references of the record.
    """
    from registry.models.metadata import ServiceMetadataRecord
    extraction = extract_access_links(
        stored_xml(record), origin_url=record.origin_url)
    if extraction.status != ExtractionStatus.OK:
        return [], False
    reference_urls = []
    for extracted in extraction.records:
        for link in extracted.links:
            if link.link_type == LinkType.METADATA_REFERENCE \
                    and link.url not in reference_urls:
                reference_urls.append(link.url)

    candidates = []
    for reference_url in reference_urls[:MAX_METADATA_REFERENCE_RECORDS]:
        referenced = _visible(
            user,
            ServiceMetadataRecord.objects.filter(
                origin_url=reference_url).order_by("id"),
            ServiceMetadataRecord).first()
        if referenced is None or referenced.file_identifier in visited:
            continue
        visited.add(referenced.file_identifier)
        referenced_extraction = extract_access_links(
            stored_xml(referenced), origin_url=referenced.origin_url)
        if referenced_extraction.status != ExtractionStatus.OK:
            warnings.append(
                f"referenced record {referenced.pk} has no readable stored"
                " xml")
            continue
        referenced_candidates, _ = _record_candidates(
            referenced, referenced_extraction)
        for candidate in referenced_candidates:
            if candidate.kind != LinkType.CAPABILITIES:
                continue
            candidates.append(replace(
                candidate,
                source=CandidateSource.METADATA_REFERENCE_RECORD,
                evidence=(f"metadata reference {reference_url} is the origin"
                          f" url of record {referenced.file_identifier}",)))
    return candidates, len(reference_urls) > MAX_METADATA_REFERENCE_RECORDS


def resolve_record(record, user=None) -> RecordResolution:
    """ Answer the service candidates of one metadata record, no network. """
    origin_url = getattr(record, "origin_url", None)
    extraction = extract_access_links(stored_xml(record),
                                      origin_url=origin_url)
    if extraction.status != ExtractionStatus.OK:
        return RecordResolution(
            status=extraction.status,
            detail=extraction.detail,
            file_identifier=getattr(record, "file_identifier", None))

    extracted = extraction.records[0]
    warnings = list(extracted.warnings)
    candidates, non_service = _record_candidates(record, extraction)

    from registry.models.metadata import DatasetMetadataRecord
    coupled = []
    truncated = False
    if isinstance(record, DatasetMetadataRecord):
        # The inverse lookup is the point of the coupling index: a harvested
        # service record may name this dataset even when the dataset itself
        # advertises its own endpoints. It costs one indexed query whenever
        # no service record names the dataset, which is the common case.
        coupled, truncated = _coupled_service_candidates(
            record, user, warnings)

    if not candidates and not coupled:
        visited = {extracted.file_identifier}
        referenced, references_cut = _metadata_reference_candidates(
            record, user, visited, warnings)
        coupled = referenced
        truncated = truncated or references_cut

    candidates = _mark_preferred(_merge_candidates(
        list(coupled) + candidates))

    return RecordResolution(
        status=ExtractionStatus.OK,
        file_identifier=extracted.file_identifier,
        service_type=extracted.service_type,
        service_type_version=extracted.service_type_version,
        candidates=candidates,
        registered_targets=_registered_targets(record, user),
        non_service_links=tuple(non_service),
        truncated=truncated,
        warnings=tuple(warnings),
    )


class _BoundedCapabilitiesSession(Session):
    """ Session which caps time and response size of one capabilities read.

        A fresh anonymous session: no MrMap credential, cookie or incoming
        header is forwarded to the remote host, and redirects are refused
        instead of silently following a host change.
    """

    class Limit(Exception):
        pass

    def send(self, request, **kwargs):
        self.started_at = time.monotonic()
        kwargs.update(timeout=CAPABILITIES_TIMEOUT, stream=True,
                      allow_redirects=False)
        with super().send(request, **kwargs) as response:
            if 300 <= response.status_code < 400:
                raise _Redirected()
            if response.status_code in (401, 403):
                raise _Denied()
            if response.status_code >= 400:
                raise _Upstream(response.status_code)
            chunks = []
            size = 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if (size > CAPABILITIES_RESPONSE_LIMIT
                        or time.monotonic() - self.started_at
                        > CAPABILITIES_TIME_LIMIT):
                    raise _BoundedCapabilitiesSession.Limit()
                chunks.append(chunk)
            return b"".join(chunks)


class _Redirected(Exception):
    pass


class _Denied(Exception):
    pass


class _Upstream(Exception):
    def __init__(self, status_code):
        super().__init__(str(status_code))
        self.status_code = status_code


def _advertised_names(root: etree._Element, service_type: str) -> tuple:
    """ The layer / feature type names a capabilities document advertises. """
    if service_type == "WMS":
        xpath = ".//*[local-name()='Layer']/*[local-name()='Name']"
    elif service_type == "WFS":
        xpath = ".//*[local-name()='FeatureType']/*[local-name()='Name']"
    else:
        return ()
    names = []
    for element in root.xpath(xpath):
        name = (element.text or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _confirm_hints(names: list, hints: tuple) -> tuple:
    """ Split the hints into confirmed and unresolved.

        A hint matches a name exactly or behind a namespace prefix on either
        side; a hint which several different names match stays unresolved -
        descriptive text is never used to pick a layer silently.
    """
    matched = []
    unresolved = []
    for hint in hints:
        found = [
            name for name in names
            if name == hint
            or name.endswith(f":{hint}")
            or hint.endswith(f":{name}")]
        if len(found) == 1:
            matched.append(found[0])
        else:
            unresolved.append(hint)
    return matched, unresolved


def validate_capabilities_candidate(candidate: ServiceCandidate,
                                    url: str) -> ValidationResult:
    """ Ask one advertised capabilities endpoint, once, with bounded cost.

        :param candidate: the candidate being validated; its hints are
            confirmed against the answer
        :param url: the url the caller asks; it must equal the candidate's
            discovery url, everything else is refused without a request
    """
    if url != candidate.url and url != candidate.original_url:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="not-advertised")

    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return ValidationResult(
            state=CandidateState.UNSUPPORTED, detail="not-fetchable")

    session = _BoundedCapabilitiesSession()
    try:
        # Like the preview and the OgcClient: an own anonymous session, the
        # request prepared by it, so no incoming header, cookie or credential
        # of the MrMap request is attached to the upstream call.
        content = session.send(request=session.prepare_request(
            Request(method="GET", url=url)))
    except _Redirected:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="redirected")
    except _Denied:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="denied")
    except _Upstream:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="upstream")
    except _BoundedCapabilitiesSession.Limit:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="limit")
    except (RequestException, ValueError):
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="timeout")

    parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                             no_network=True, dtd_validation=False,
                             recover=False)
    try:
        root = etree.fromstring(content, parser=parser)
    except (etree.XMLSyntaxError, etree.ParserError, UnicodeDecodeError,
            ValueError):
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="parse")

    root_name = etree.QName(root).localname
    if root_name in ("ExceptionReport", "ServiceExceptionReport"):
        # the code is an attribute of the reported exception, in both the
        # 1.1.x ServiceExceptionReport and the 2.0 ExceptionReport shape
        codes = root.xpath(".//*[@exceptionCode]/@exceptionCode")
        return ValidationResult(
            state=CandidateState.UNAVAILABLE,
            detail=f"exception-report:{codes[0] if codes else ''}")

    service_type = None
    tag = root_name.lower()
    if any(token in tag for token in ("wms", "wmt")):
        service_type = "WMS"
    elif "wfs" in tag:
        service_type = "WFS"
    elif "capabilities" in tag and "csw" in root.nsmap.values():
        service_type = "CSW"
    if service_type is None:
        return ValidationResult(
            state=CandidateState.UNSUPPORTED, detail="unsupported-service")

    version = root.attrib.get("version")
    if not version:
        return ValidationResult(
            state=CandidateState.UNAVAILABLE, detail="no-version",
            service_type=service_type)
    if version not in SUPPORTED_VERSIONS.get(service_type, set()):
        return ValidationResult(
            state=CandidateState.UNSUPPORTED, detail="unsupported-version",
            service_type=service_type, service_version=version)

    names = _advertised_names(root, service_type)
    names_truncated = len(names) > ADVERTISED_NAMES_LIMIT
    answered = names[:ADVERTISED_NAMES_LIMIT]

    hints = tuple(dict.fromkeys(candidate.type_names + candidate.layers))
    if hints:
        matched, unresolved = _confirm_hints(list(names), hints)
        state = (CandidateState.RESOLVED if not unresolved
                 else CandidateState.AMBIGUOUS)
        return ValidationResult(
            state=state,
            detail="ok" if not unresolved else "unresolved-hints",
            service_type=service_type, service_version=version,
            advertised_names=tuple(answered),
            matched_names=tuple(matched),
            unresolved_hints=tuple(unresolved),
            names_truncated=names_truncated)

    return ValidationResult(
        state=CandidateState.RESOLVED, detail="ok",
        service_type=service_type, service_version=version,
        advertised_names=tuple(answered),
        names_truncated=names_truncated)
