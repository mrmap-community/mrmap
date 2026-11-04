""" Extract the advertised access links and coupling hints of a harvested ISO record.

    The mapping configs of ``registry.mappers.configs`` persist the descriptive
    fields of an ISO 19139 record. The record's original ``MD_Metadata`` document
    survives in the record's ``xml_backup_file`` (see
    :class:`registry.models.document.DocumentModelMixin`), so the advertised
    access information can be read from any already stored record without a
    reharvest and without a database migration.

    The extractor answers an internal typed structure; it does not create
    service instances, does not touch ``MetadataRelation`` rows and does not
    perform network requests. Validating a candidate against the real endpoint
    (fetching the capabilities document) is the responsibility of the consumer
    of this extraction, not of the extraction itself.

    The XML paths which are read are the ones the ISO 19139 schemas define for
    advertised access information:

    * dataset / service distribution links:
      ``/gmd:MD_Metadata/gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions``
      and the distributor specific ``gmd:distributor/gmd:MD_Distributor/gmd:distributorTransferOptions``,
      both holding ``gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource``.
    * service operation endpoints:
      ``/gmd:MD_Metadata/gmd:identificationInfo/srv:SV_ServiceIdentification/srv:containsOperations/srv:SV_OperationMetadata``
      with ``srv:operationName``, ``srv:DCP`` and ``srv:connectPoint``,
      plus ``srv:serviceType`` / ``srv:serviceTypeVersion``. Note that a
      ``serviceType`` such as ``view`` is a category and by itself no proof of
      a WMS.
    * dataset / service coupling hints: ``srv:operatesOn/@uuidref``,
      ``srv:operatesOn/@xlink:href`` and
      ``srv:coupledResource/srv:SV_CoupledResource`` with ``srv:identifier``,
      ``srv:operationName`` and ``srv:scopedName``.

    Links which belong to a contact (``gmd:CI_Contact/gmd:onlineResource``) are
    deliberately not part of the extraction: a contact homepage is not a
    service access point. The XPath expressions therefore walk the explicit
    branches above instead of searching the document for any
    ``CI_OnlineResource``, and they match the namespace URIs, not the prefix
    spellings of a concrete document.

    A missing, unreadable or malformed stored document is answered as a
    structured :class:`AccessLinkExtraction` status instead of an exception.
    The XML is parsed without resolving external entities and without
    retrieving remote schema documents or DTDs.
"""

import os
from dataclasses import dataclass
from enum import StrEnum
from typing import IO, Optional, Union
from urllib.parse import parse_qsl, urlsplit

from lxml import etree

from registry.mappers.utils import load_file
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

NSMAP = {
    "gmd": NAMESPACE_LOOKUP["gmd"],
    "gco": NAMESPACE_LOOKUP["gco"],
    "gmx": NAMESPACE_LOOKUP["gmx"],
    "srv": NAMESPACE_LOOKUP["srv"],
    "xlink": NAMESPACE_LOOKUP["xlink"],
}

_MD_METADATA = "{%s}MD_Metadata" % NAMESPACE_LOOKUP["gmd"]
_XLINK_HREF = "{%s}href" % NAMESPACE_LOOKUP["xlink"]
_PREFIX_BY_URI = {uri: prefix for prefix, uri in NSMAP.items()}

# Branches below a MD_Metadata element which advertise an access link.
ONLINE_RESOURCE_XPATHS = (
    "./gmd:distributionInfo/gmd:MD_Distribution"
    "/gmd:transferOptions/gmd:MD_DigitalTransferOptions"
    "/gmd:onLine/gmd:CI_OnlineResource",
    "./gmd:distributionInfo/gmd:MD_Distribution/gmd:distributor"
    "/gmd:MD_Distributor/gmd:distributorTransferOptions"
    "/gmd:MD_DigitalTransferOptions"
    "/gmd:onLine/gmd:CI_OnlineResource",
)

_SERVICE_IDENTIFICATION_XPATH = (
    "./gmd:identificationInfo/srv:SV_ServiceIdentification")
_IDENTIFICATION_XPATHS = (
    "./gmd:identificationInfo/gmd:MD_DataIdentification",
    _SERVICE_IDENTIFICATION_XPATH,
)
_CITATION_IDENTIFIER_XPATH = (
    "gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier"
    "/gmd:code/gco:CharacterString")

# Lower cased request values of OGC operations which may be advertised inside
# a URL. A GetCapabilities request is handled separately, everything else in
# this set marks the URL as the endpoint of a single operation.
OGC_OPERATIONS = frozenset({
    "getcapabilities", "getmap", "getfeatureinfo", "getfeature",
    "getpropertyvalue", "getpropertyvaluevalues", "describefeaturetype",
    "getgmlobject", "liststoredqueries", "describestoredqueries",
    "getcoverage", "getcoveragebis", "describecoverage", "getdomain",
    "getrecords", "getrecordbyid", "getrepositoryitem", "gettile",
    "getlegendgraphic", "getstyles", "getschema",
})

# Lower cased service tokens which mark a URL as an OGC operation endpoint.
OGC_SERVICE_TOKENS = frozenset({"wms", "wfs", "wcs", "csw", "wmts"})


class ExtractionStatus(StrEnum):
    """ Explicit state of a whole extraction over a stored document. """

    OK = "ok"
    #: The record carries no stored xml at all.
    MISSING = "missing"
    #: The stored xml exists but could not be read.
    UNREADABLE = "unreadable"
    #: The stored xml could not be parsed.
    MALFORMED = "malformed"
    #: The document parsed but holds no MD_Metadata element.
    NO_RECORDS = "no_records"


class LinkType(StrEnum):
    """ Explicit kind of an advertised link, judged from the hints of the
        record alone.

        A capability of the referenced resource (e.g. its supported CRS) can
        only be answered by resolving the link, never by the extraction.
    """

    #: A URL which advertises an OGC GetCapabilities request.
    CAPABILITIES = "capabilities"
    #: A URL which advertises another concrete OGC operation.
    OGC_OPERATION = "ogc_operation"
    #: A URL which advertises a download of data.
    DOWNLOAD = "download"
    #: A URL which points at further information or another metadata document.
    METADATA_REFERENCE = "metadata_reference"
    #: Nothing in the record identifies what the URL provides.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OnlineResourceLink:
    """ A normalized ``gmd:CI_OnlineResource`` with its XML location.

        The values keep the original strings of the document; empty elements
        and ``gco:nilReason`` placeholders become ``None``.
    """
    url: str
    link_type: LinkType
    protocol: Optional[str] = None
    application_profile: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    function: Optional[str] = None
    #: OGC ``request`` taken from the URL query, e.g. ``GetFeature``.
    request: Optional[str] = None
    #: OGC ``service`` taken from the URL query or protocol, e.g. ``WFS``.
    service: Optional[str] = None
    #: ``typeNames`` / ``typeName`` hints taken from the URL query.
    type_names: tuple = ()
    #: Location of the CI_OnlineResource inside the stored document.
    source: str = ""


@dataclass(frozen=True)
class ServiceOperation:
    """ A ``srv:SV_OperationMetadata`` entry of a service identification. """
    name: Optional[str] = None
    #: The ``srv:DCPList`` code, e.g. ``WebServices``.
    dcp: Optional[str] = None
    #: The operation's ``srv:connectPoint`` if it carries a usable URL.
    connect_point: Optional[OnlineResourceLink] = None
    #: Location of the SV_OperationMetadata inside the stored document.
    source: str = ""


@dataclass(frozen=True)
class CouplingHint:
    """ A hint that a service record operates on a dataset record.

        ``uuidref`` and ``href`` come from a ``srv:operatesOn`` element, the
        remaining values from a ``srv:SV_CoupledResource``. Both name the
        *resource* identity; the *metadata* identity of the record itself is
        answered separately by :attr:`MetadataAccessInfo.file_identifier`.
    """
    uuidref: Optional[str] = None
    href: Optional[str] = None
    identifier: Optional[str] = None
    operation_name: Optional[str] = None
    scoped_name: Optional[str] = None
    #: Location of the source element inside the stored document.
    source: str = ""


@dataclass(frozen=True)
class MetadataAccessInfo:
    """ All advertised access information of a single ``MD_Metadata``. """
    #: The lower cased ``gmd:MD_ScopeCode`` of the hierarchyLevel.
    record_type: Optional[str] = None
    #: Metadata identity of this record (``gmd:fileIdentifier``).
    file_identifier: Optional[str] = None
    #: Resource identities from the citation, kept apart from the metadata
    #: identity: they identify the described resource, not this document.
    resource_identifiers: tuple = ()
    #: The raw ``srv:serviceType``; a value such as ``view`` is a category.
    service_type: Optional[str] = None
    service_type_version: Optional[str] = None
    links: tuple = ()
    operations: tuple = ()
    #: The ``srv:SV_CouplingType`` code, e.g. ``tight``.
    coupling_type: Optional[str] = None
    coupling_hints: tuple = ()
    #: The source URL of the record, kept alongside the normalized hints.
    origin_url: Optional[str] = None
    #: Human readable notes about skipped or incomplete entries.
    warnings: tuple = ()


@dataclass(frozen=True)
class AccessLinkExtraction:
    """ Result of an extraction over one stored document.

        ``status`` is :attr:`ExtractionStatus.OK` exactly when ``records``
        holds one :class:`MetadataAccessInfo` per parsed ``MD_Metadata``.
    """
    status: ExtractionStatus
    #: Structured detail of a non OK status.
    detail: str = ""
    records: tuple = ()


def _strict_parser() -> etree.XMLParser:
    """ Parser which never resolves external entities nor fetches remote
        DTDs or schema locations. """
    return etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        dtd_validation=False,
        recover=False,
    )


def _clean_text(element: etree._Element, xpath: str) -> Optional[str]:
    """ Text of the first element matched below element, or None.

        Empty and whitespace only text (including ``gco:nilReason``
        placeholders) becomes None.
    """
    found = element.xpath(xpath, namespaces=NSMAP)
    if not found:
        return None
    text = found[0].text
    if text is None:
        return None
    text = text.strip()
    return text or None


def _clean_attribute(element: Optional[etree._Element],
                     name: str) -> Optional[str]:
    """ Non empty attribute value of an element which may be None. """
    if element is None:
        return None
    value = element.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _qname(element: etree._Element) -> str:
    """ Prefixed tag name of the element, using this module's prefixes. """
    tag = element.tag
    if not isinstance(tag, str):
        return str(tag)
    qname = etree.QName(tag)
    prefix = _PREFIX_BY_URI.get(qname.namespace)
    return f"{prefix}:{qname.localname}" if prefix else qname.localname


def _xml_location(element: etree._Element) -> str:
    """ Position of the element inside the stored document, as a readable
        path with 1 based indexes wherever a sibling repeats the tag. """
    parts = []
    node = element
    while node is not None:
        name = _qname(node)
        parent = node.getparent()
        if parent is not None:
            same_tag = [
                child for child in parent.iterchildren()
                if isinstance(child, etree._Element) and child.tag == node.tag]
            if len(same_tag) > 1:
                name = f"{name}[{same_tag.index(node) + 1}]"
        parts.append(name)
        node = parent
    return "/".join(reversed(parts))


def _query_parameters(url: str) -> dict:
    """ Lower cased query parameters of the URL; the URL itself stays
        untouched. Only the query string is split, no request is performed. """
    query = urlsplit(url).query
    parameters = {}
    for key, value in parse_qsl(query, keep_blank_values=True):
        parameters.setdefault(key.lower(), value)
    return parameters


def _service_from_protocol(protocol: Optional[str]) -> Optional[str]:
    """ Service token of an ``OGC:<SERVICE>-...`` protocol string. """
    if not protocol or not protocol.upper().startswith("OGC:"):
        return None
    token = protocol[4:].split("-", 1)[0].strip().lower()
    return token if token in OGC_SERVICE_TOKENS else None


def _split_type_names(value: str) -> tuple:
    return tuple(
        name.strip() for name in value.split(",") if name.strip())


def classify_url(url: str, protocol: Optional[str] = None,
                 function: Optional[str] = None) -> LinkType:
    """ Classify an advertised URL into an explicit :class:`LinkType`.

        The classification reads only the URL query and the record's own
        protocol / function hints. It never promotes a link to a map service
        it cannot name: an unrecognized hint stays
        :attr:`LinkType.UNKNOWN`.
    """
    parameters = _query_parameters(url)
    request = parameters.get("request", "").lower()
    if request == "getcapabilities":
        return LinkType.CAPABILITIES
    if request in OGC_OPERATIONS:
        return LinkType.OGC_OPERATION
    if parameters.get("service", "").lower() in OGC_SERVICE_TOKENS:
        return LinkType.OGC_OPERATION
    if _service_from_protocol(protocol):
        return LinkType.OGC_OPERATION
    function = (function or "").lower()
    if function == "download":
        return LinkType.DOWNLOAD
    if function == "information":
        return LinkType.METADATA_REFERENCE
    return LinkType.UNKNOWN


def _parse_online_resource(element: etree._Element,
                           warnings: list) -> Optional[OnlineResourceLink]:
    """ Normalize one ``gmd:CI_OnlineResource``.

        Returns None when the resource carries no linkage URL; the caller
        notes the warning so that a record with one broken link stays usable.
    """
    url = _clean_text(element, "./gmd:linkage/gmd:URL")
    if url is None:
        warnings.append(
            f"ignored online resource without URL at {_xml_location(element)}")
        return None
    protocol = _clean_text(element, "./gmd:protocol/gco:CharacterString")
    function = _clean_attribute(
        element.find("./gmd:function/gmd:CI_OnLineFunctionCode",
                     namespaces=NSMAP),
        "codeListValue") or _clean_text(
            element, "./gmd:function/gmd:CI_OnLineFunctionCode")
    parameters = _query_parameters(url)
    type_names = ()
    for parameter in ("typenames", "typename"):
        if parameter in parameters:
            type_names = _split_type_names(parameters[parameter])
            break
    return OnlineResourceLink(
        url=url,
        link_type=classify_url(url, protocol=protocol, function=function),
        protocol=protocol,
        application_profile=_clean_text(
            element, "./gmd:applicationProfile/gco:CharacterString"),
        name=_clean_text(element, "./gmd:name/gco:CharacterString"),
        description=_clean_text(
            element, "./gmd:description/gco:CharacterString"),
        function=function,
        request=parameters.get("request") or None,
        service=parameters.get("service")
        or _service_from_protocol(protocol) or None,
        type_names=type_names,
        source=_xml_location(element),
    )


def _parse_operation(element: etree._Element,
                     warnings: list) -> ServiceOperation:
    """ Normalize one ``srv:SV_OperationMetadata``. """
    connect_point = element.find(
        "./srv:connectPoint/gmd:CI_OnlineResource", namespaces=NSMAP)
    return ServiceOperation(
        name=_clean_text(
            element, "./srv:operationName/gco:CharacterString"),
        dcp=_clean_attribute(
            element.find("./srv:DCP/srv:DCPList", namespaces=NSMAP),
            "codeListValue"),
        connect_point=_parse_online_resource(connect_point, warnings)
        if connect_point is not None else None,
        source=_xml_location(element),
    )


def _parse_scoped_name(coupled: etree._Element) -> Optional[str]:
    """ Scoped name of a ``srv:SV_CoupledResource``.

        ISO 19139 renders ``srv:scopedName`` either as a ``gmx:Anchor``
        carrying the name in its xlink:href or as plain character text.
    """
    scoped = coupled.find("./srv:scopedName", namespaces=NSMAP)
    if scoped is None:
        return None
    return (_clean_attribute(
        scoped, _XLINK_HREF)
        or _clean_attribute(
            scoped.find("./gmx:Anchor", namespaces=NSMAP), _XLINK_HREF)
        or _clean_text(scoped, "./gmx:Anchor")
        or _clean_text(scoped, "."))


def _parse_coupling_hints(identification: etree._Element) -> tuple:
    """ Collect ``srv:operatesOn`` and ``srv:SV_CoupledResource`` hints. """
    hints = []
    for operates_on in identification.xpath(
            "./srv:operatesOn", namespaces=NSMAP):
        hints.append(CouplingHint(
            uuidref=_clean_attribute(operates_on, "uuidref"),
            href=_clean_attribute(operates_on, _XLINK_HREF),
            source=_xml_location(operates_on),
        ))
    for coupled in identification.xpath(
            "./srv:coupledResource/srv:SV_CoupledResource",
            namespaces=NSMAP):
        hints.append(CouplingHint(
            identifier=_clean_text(
                coupled, "./srv:identifier/gco:CharacterString"),
            operation_name=_clean_text(
                coupled, "./srv:operationName/gco:CharacterString"),
            scoped_name=_parse_scoped_name(coupled),
            source=_xml_location(coupled),
        ))
    return tuple(hints)


def _detect_record_type(record: etree._Element) -> Optional[str]:
    """ Lower cased ``hierarchyLevel`` scope code of the record. """
    scope = record.find("./gmd:hierarchyLevel/gmd:MD_ScopeCode",
                        namespaces=NSMAP)
    if scope is None:
        return None
    level = (_clean_attribute(scope, "codeListValue")
             or _clean_text(scope, "."))
    return level.lower() if level else None


def _extract_record(record: etree._Element,
                    origin_url: Optional[str]) -> MetadataAccessInfo:
    """ Build the access information of a single MD_Metadata element. """
    warnings: list = []

    links = []
    for xpath in ONLINE_RESOURCE_XPATHS:
        for resource in record.xpath(xpath, namespaces=NSMAP):
            link = _parse_online_resource(resource, warnings)
            if link is not None:
                links.append(link)

    identifiers = []
    for identification_xpath in _IDENTIFICATION_XPATHS:
        for identification in record.xpath(
                identification_xpath, namespaces=NSMAP):
            for identifier in identification.xpath(
                    _CITATION_IDENTIFIER_XPATH, namespaces=NSMAP):
                text = (identifier.text or "").strip()
                if text:
                    identifiers.append(text)

    operations = []
    coupling_hints = []
    service_type = None
    service_type_version = None
    coupling_type = None
    service_identification = record.find(
        _SERVICE_IDENTIFICATION_XPATH, namespaces=NSMAP)
    if service_identification is not None:
        service_type = _clean_text(
            service_identification, "./srv:serviceType/gco:LocalName")
        service_type_version = _clean_text(
            service_identification,
            "./srv:serviceTypeVersion/gco:CharacterString")
        coupling_type = _clean_attribute(
            service_identification.find(
                "./srv:couplingType/srv:SV_CouplingType", namespaces=NSMAP),
            "codeListValue")
        for operation in service_identification.xpath(
                "./srv:containsOperations/srv:SV_OperationMetadata",
                namespaces=NSMAP):
            operations.append(_parse_operation(operation, warnings))
        coupling_hints = _parse_coupling_hints(service_identification)

    return MetadataAccessInfo(
        record_type=_detect_record_type(record),
        file_identifier=_clean_text(
            record, "./gmd:fileIdentifier/gco:CharacterString"),
        resource_identifiers=tuple(identifiers),
        service_type=service_type,
        service_type_version=service_type_version,
        links=tuple(links),
        operations=tuple(operations),
        coupling_type=coupling_type,
        coupling_hints=tuple(coupling_hints),
        origin_url=origin_url,
        warnings=tuple(warnings),
    )


def extract_access_links(
        xml: Union[str, bytes, os.PathLike, IO, etree._Element,
                   etree._ElementTree],
        origin_url: Optional[str] = None) -> AccessLinkExtraction:
    """ Extract advertised links and coupling hints from a stored record.

        :param xml: the stored xml of a metadata record; the same input kinds
            as :func:`registry.mappers.utils.load_file` accepts, e.g. the
            ``xml_backup`` bytes of a ``MetadataRecord``
        :param origin_url: the source URL of the record, kept alongside the
            extracted hints for provenance
        :return: the extraction result; a missing, unreadable or malformed
            document is answered by an explicit status, never by an exception
    """
    try:
        content = load_file(xml)
    except (OSError, TypeError) as error:
        return AccessLinkExtraction(
            status=ExtractionStatus.UNREADABLE, detail=str(error))

    if not content or not content.strip():
        return AccessLinkExtraction(
            status=ExtractionStatus.MISSING,
            detail="the record carries no stored xml content")

    try:
        root = etree.fromstring(content, parser=_strict_parser())
    except (etree.XMLSyntaxError, etree.ParserError,
            UnicodeDecodeError, ValueError) as error:
        return AccessLinkExtraction(
            status=ExtractionStatus.MALFORMED, detail=str(error))

    if root.tag == _MD_METADATA:
        records_root = [root]
    else:
        records_root = root.iter(_MD_METADATA)

    records = tuple(
        _extract_record(md, origin_url) for md in records_root)

    if not records:
        return AccessLinkExtraction(
            status=ExtractionStatus.NO_RECORDS,
            detail="the stored xml holds no MD_Metadata element")

    return AccessLinkExtraction(
        status=ExtractionStatus.OK, records=records)
