import datetime
from itertools import chain

from csw.describe_record import (CSWDescribeRecordBuilder,
                                 SUPPORTED_RECORD_TYPE_NAMES)
from csw.elementsets import (DEFAULT_ELEMENT_SET, ELEMENT_SETS,
                             apply_sort, loaded_fields, merge_sorted,
                             project_gmd_record, requested_element_set,
                             requested_sort_by, sortable_field,
                             sortable_properties)
from csw.exceptions import DocumentUnavailable, InvalidQuery, NotSupported
from csw.queryables import (FIELD_MAP, dataset_records, search_filter,
                            service_records)
from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models.aggregates import Count
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from lxml import etree
from registry.enums.service import OGCOperationEnum
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWBuilder, CSWCapabilities
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.response.exceptions import (
    InvalidParameterValueException, MissingRequestParameterException,
    MissingVersionParameterException,
    OGCServiceException, OperationNotSupportedException,
    VersionNegotiationFailedException,
    MissingServiceParameterException, ParsingErrorException)
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.settings import MRMAP_CSW_PK

# Table 65 note a of OGC 07-006r1: the KVP binding compares the value of the
# REQUEST parameter case-insensitively. Dispatch -- and the request analysis in
# OGCRequest -- compare that value against the label which names the operation,
# so the value of a GET request is answered as that label before anything reads
# it; a value which names no operation this endpoint serves keeps its own
# spelling, which is what an OperationNotSupported report echoes back.
KVP_OPERATIONS = {
    label.lower(): label
    for label in (
        OGCOperationEnum.GET_CAPABILITIES.label,
        OGCOperationEnum.DESCRIBE_RECORD.label,
        OGCOperationEnum.GET_RECORDS.label,
        OGCOperationEnum.GET_RECORD_BY_ID.label,
    )
}

# The CSW versions this endpoint answers. One version profiles this catalogue,
# and the registry of the schemas its responses are built from registers it
# alone: the ("csw", "discovery", <version>) key of XSD_LOOKUP in
# registry/ows_lib/xml/consts.py answers a ValueError for every other value,
# which is the raw HTTP 500 #910 reports for a wrong `version` -- the report of
# the refused version has to be built before that lookup is asked.
SUPPORTED_CSW_VERSIONS = ("2.0.2",)

# The metadata sections a GetCapabilities document is made of (the top level
# children of the document CSWCapabilities.to_xml builds). Table 64 lets a
# client ask for a subset of these names by the `sections` parameter and reserves
# "All" for the whole document.
CAPABILITIES_SECTIONS = (
    "ServiceIdentification",
    "ServiceProvider",
    "OperationsMetadata",
    "Filter_Capabilities",
)

# The media types the capabilities document can be answered in. The handler
# answers the document as application/xml and builds no other encoding of it, so
# an AcceptFormats list without this type names a document this endpoint does
# not have.
CAPABILITIES_FORMATS = ("application/xml",)


def parse_kvp_list(value):
    """The values of a KVP parameter which carries a comma separated list.

    Table 64 hands `sections`, `acceptVersions` and `acceptFormats` that way; an
    empty value carries no value at all, so a request which names the parameter
    without a value is answered as a request which does not name it.
    """
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def first_mutually_supported(requested, supported):
    """The first value a client prefers which this service also speaks.

    `requested` is ordered by the preference of the client -- Table 64 hands
    `acceptVersions` and `acceptFormats` most preferred first, Table 65's
    mandatory `version` is the same list with one value -- so the value both
    sides agree on is the first requested one this service speaks. For the one
    version this catalogue speaks that is also the highest version common to both
    that OGC 05-008, 7.3.2 answers. `None` says nothing is common to both; the
    caller refuses with the exception its parameter names, because the reason of
    a refusal differs per parameter: `VersionNegotiationFailed` for a version
    which can not be negotiated, `InvalidParameterValue` for a value which is no
    value of that parameter at all.
    """
    return next(
        (value for value in requested if value in supported), None)


@method_decorator(csrf_exempt, name="dispatch")
class CswServiceView(View):
    """
    MrMap CSW implementation

    """

    def dispatch(self, request, *args, **kwargs):
        self.start_time = datetime.datetime.now()
        self.ogc_request = OGCRequest.from_django_request(request)
        self.canonicalize_kvp_operation()

        exception = self.check_request()
        if exception:
            return exception

        exception = self.check_kvp_version()
        if exception:
            return exception
        # self.analyze_request()

        return self.get_and_post(request=request, *args, **kwargs)

    def canonicalize_kvp_operation(self):
        """Answers the REQUEST value of a GET request as the label of the
        operation it spells, whatever case the client chose (Table 65 note a)."""
        if not self.ogc_request.is_get:
            return
        canonical = KVP_OPERATIONS.get((self.ogc_request.operation or "").lower())
        if canonical:
            self.ogc_request.operation = canonical

    def check_kvp_version(self):
        """Refuses the `version` of a KVP request this endpoint can not answer.

        Table 65 makes `version` a mandatory (One) parameter of GetRecords with
        the fixed value of the version this catalogue profiles, so a GetRecords
        without it, or with a value outside :data:`SUPPORTED_CSW_VERSIONS`, is a
        refused request -- not a broken one (#910 answered both with a raw HTTP
        500: the handler of a KVP GetRecords asks ``OGCRequest.xml_request``,
        which builds the request XML with a ``CSWBuilder`` of the requested
        version, and the schema lookup of that builder raises a ValueError for
        every version but 2.0.2).

        The refusal belongs beside :meth:`canonicalize_kvp_operation`, the other
        KVP parameter dispatch settles before a handler reads the request. The
        XML binding carries its version as the `version` attribute of the request
        element and is read by the binding path of #912; that path can ask the
        same question of the attribute it parses through
        :func:`first_mutually_supported`, and
        :meth:`refuse_unsupported_version` answers the report of a single
        requested version.
        """
        if not (self.ogc_request.is_get
                and self.ogc_request.is_get_records_request):
            return

        requested = (
            self.ogc_request.ogc_query_params.get("VERSION") or "").strip()
        if not requested:
            return MissingVersionParameterException(
                ogc_request=self.ogc_request,
                message=(
                    "The version parameter is mandatory for GetRecords and must "
                    f"name one of {', '.join(SUPPORTED_CSW_VERSIONS)}."))
        return self.refuse_unsupported_version(requested, locator="version")

    def refuse_unsupported_version(self, requested, locator="version"):
        """The report of one requested version this endpoint does not speak, or None.

        `InvalidParameterValue` names a value which is no version this catalogue
        answers; `VersionNegotiationFailed` belongs to the version negotiation of
        a GetCapabilities, where a client hands a list to choose from (see
        :meth:`check_capabilities_versions`).
        """
        if first_mutually_supported([requested], SUPPORTED_CSW_VERSIONS) is not None:
            return
        return InvalidParameterValueException(
            ogc_request=self.ogc_request,
            locator=locator,
            message=(
                f"Unsupported version: {requested}. This catalogue speaks "
                f"{', '.join(SUPPORTED_CSW_VERSIONS)}."))

    def check_request(self):
        """proof if all mandatory query parameters are part of the reuqest"""
        if self.ogc_request.xml_parse_error is not None:
            # a posted request document which is not well-formed XML: the
            # parsing-error report answers it -- not the XMLSyntaxError which
            # used to raise out of the request analysis and answer a raw HTTP
            # 500 for every broken POST (#912)
            return ParsingErrorException(
                ogc_request=self.ogc_request,
                message=(
                    "The request document could not be parsed: "
                    f"{self.ogc_request.xml_parse_error}"))
        elif not self.ogc_request.operation:
            return MissingRequestParameterException(ogc_request=self.ogc_request)

        elif not self.ogc_request.service_type:
            return MissingServiceParameterException(ogc_request=self.ogc_request)
        # The ElementSetName of a request is read and answered where the response
        # is built (see get_records), which is also where a posted request is
        # covered: these KVP checks can not cover it (FIXME: if post method, this
        # will not cover the check)

        elif self.ogc_request.ogc_query_params.get("outputSchema", "http://www.isotc211.org/2005/gmd") != "http://www.isotc211.org/2005/gmd":  # NOSONAR normative ISO 19139 gmd outputSchema identifier, compared as an OGC schema key - not a network endpoint
            return NotSupported(
                # ogc_request=self.ogc_request,
                service_type=self.ogc_request.service_type,
                service_version=self.ogc_request.service_version,
                locator="outputSchema",
                message="Only 'http://www.isotc211.org/2005/gmd' as outputschema is supported.")
        elif self.ogc_request.ogc_query_params.get("typeNames", "gmd:MD_Metadata") != "gmd:MD_Metadata":
            return NotSupported(
                # ogc_request=self.ogc_request,
                service_type=self.ogc_request.service_type,
                service_version=self.ogc_request.service_version,
                locator="typeNames",
                message="Only 'gmd:MD_Metadata' as typeNames is supported.")

    def get_field_map(self):
        # the queryables of this endpoint and the field of a metadata record each of
        # them is answered from; see csw/queryables.py for the three of them which a
        # record does not answer as a column
        return FIELD_MAP

    def read_stored_documents(self, records):
        """The stored documents of the given records, parsed.

        A record answers its stored ``xml_backup`` document, and that document
        is a file of the media storage: a file which is gone from the storage,
        an empty or corrupt one, used to raise its FileNotFoundError out of the
        list comprehension which materialized a matched page and kill the whole
        response of an otherwise valid query with a raw HTTP 500 (#912). Such a
        record is refused with the report which names it instead; which record
        cannot be served is what a client -- and the operator who has to restore
        it -- needs to know.

        :return: the parsed documents, or the refusal naming the record of the
            one which cannot be served
        :rtype: list | :class:`~registry.ows_lib.response.exceptions.OGCServiceException`
        """
        documents = []
        for record in records:
            try:
                documents.append(etree.fromstring(record.xml_backup))
            except (OSError, ValueError, SyntaxError) as e:
                return DocumentUnavailable(
                    ogc_request=self.ogc_request,
                    message=(
                        "The stored document of the record "
                        f"'{record.file_identifier}' cannot be served: {e}"))
        return documents

    def get_filter_constraint(self):
        field_mapping = self.get_field_map()
        return self.ogc_request.filter_constraint(field_mapping=field_mapping)

    def check_capabilities_versions(self):
        """Refuses an `acceptVersions` list with no version this endpoint speaks.

        OGC 07-006r1, 10.8.3 obliges a CSW to implement the `AcceptVersions`
        parameter of GetCapabilities: :func:`first_mutually_supported` picks the
        first requested version this catalogue also speaks, and a
        list with nothing in common with :data:`SUPPORTED_CSW_VERSIONS` is refused
        with `VersionNegotiationFailed` naming the versions this server speaks
        (OGC 05-008, Table 4). An absent parameter negotiates the default of the
        endpoint, as OGC 05-008, 7.3.1 answers it.
        """
        requested = parse_kvp_list(
            self.ogc_request.ogc_query_params.get("ACCEPTVERSIONS"))
        if not requested:
            return

        negotiated = first_mutually_supported(
            requested, SUPPORTED_CSW_VERSIONS)
        if negotiated is not None:
            # the document this handler builds is the document of that version,
            # which is all the answer the negotiation of a one version server
            # changes; a server which spoke more than one version would build the
            # document of `negotiated` here
            return

        return VersionNegotiationFailedException(
            ogc_request=self.ogc_request,
            message=(
                "None of the requested versions is supported: "
                f"{', '.join(requested)}. This catalogue speaks "
                f"{', '.join(SUPPORTED_CSW_VERSIONS)}."))

    def check_capabilities_formats(self):
        """Refuses an `acceptFormats` list without the type this document has.

        The second parameter 10.8.3 obliges a CSW to implement: the list is
        negotiated like the versions, so a client which prefers another encoding
        but will accept application/xml is answered -- and a list without it asks
        for a document this endpoint does not have, which
        `InvalidParameterValue` names. An absent parameter is the default format
        of the endpoint.
        """
        requested = parse_kvp_list(
            self.ogc_request.ogc_query_params.get("ACCEPTFORMATS"))
        if not requested:
            return

        negotiated = first_mutually_supported(
            requested, CAPABILITIES_FORMATS)
        if negotiated is not None:
            # this endpoint encodes the document in the one type it speaks, so the
            # negotiated type is the type the response already carries
            return

        return InvalidParameterValueException(
            ogc_request=self.ogc_request,
            locator="acceptFormats",
            message=(
                f"None of the requested formats is supported: "
                f"{', '.join(requested)}. This catalogue answers "
                f"{', '.join(CAPABILITIES_FORMATS)}."))

    def requested_capabilities_sections(self):
        """The sections of the document a request asks for, or their refusal.

        The third parameter 10.8.3 obliges a CSW to implement. Table 64 hands
        `sections` as a comma separated list of section names and OGC 05-008,
        7.3.1 answers an absent parameter, as the reserved value "All", with the
        whole document -- the empty list this returns says exactly that. A name
        this endpoint builds no section for is refused with
        `InvalidParameterValue` naming the parameter.
        """
        params = self.ogc_request.ogc_query_params
        requested = parse_kvp_list(
            params.get("SECTIONS") or params.get("SECTION"))
        if not requested or any(name.lower() == "all" for name in requested):
            return []

        unknown = [
            name for name in requested
            if name not in CAPABILITIES_SECTIONS
        ]
        if unknown:
            return InvalidParameterValueException(
                ogc_request=self.ogc_request,
                locator="sections",
                message=(
                    f"Unsupported sections: {', '.join(unknown)}. This "
                    f"catalogue answers {', '.join(CAPABILITIES_SECTIONS)} "
                    "and All."))
        return requested

    def only_requested_sections(self, capabilities, sections):
        """Drops the top level sections of a document which were not requested.

        The document keeps the order and the shape it has without the parameter:
        the sections which were asked for simply keep their places.
        """
        if not sections:
            return

        for element in list(capabilities):
            if etree.QName(element).localname not in sections:
                capabilities.remove(element)

    def get_capabilities(self, request):
        """Return the camouflaged capabilities document of the founded service.
        .. note::
           See :meth:`registry.models.document.DocumentModelMixin.xml_secured` for details of xml_secured function.

        The three request parameters OGC 07-006r1, 10.8.3 obliges a CSW to
        implement are honoured before the document is read: `AcceptVersions`
        negotiates the version the answer speaks, `AcceptFormats` refuses a media
        type the answer can not be encoded in and `Sections` narrows the answer to
        the metadata sections the client asked for. Without them the full document
        of the profiled version answers, byte for byte as before.
        :return: the camouflaged capabilities document.
        :rtype: :class:`django.http.response.HttpResponse`
        """

        exception = (self.check_capabilities_versions()
                     or self.check_capabilities_formats())
        if exception:
            return exception

        sections = self.requested_capabilities_sections()
        if isinstance(sections, OGCServiceException):
            return sections

        # the 10 most used keywords of the catalogue for the capabilities
        # KeywordList. One grouped aggregation per keyword link table (#912):
        # the previous per-row Subquery(Count()) pair was evaluated for every
        # keyword row -- and each count twice, because the usage filter
        # re-read the same annotations -- so the database could never apply
        # the top-10 limit before all keywords had been counted, which is
        # what pushed a cold GetCapabilities over the nginx timeout on the
        # demo box. A keyword is only a candidate when it carries links, and
        # equal usages keep the keyword id order the old sequential sort
        # produced, so the answered document is unchanged.
        usage_counts = {}
        for keyword_links in (DatasetMetadataRecord.keywords.through.objects,
                              ServiceMetadataRecord.keywords.through.objects):
            for row in keyword_links.values('keyword').annotate(
                    count=Count('keyword')):
                usage_counts[row['keyword']] = usage_counts.get(
                    row['keyword'], 0) + row['count']
        most_used = sorted(usage_counts,
                           key=lambda pk: (-usage_counts[pk], pk))[:10]
        keywords = []
        if most_used:
            names = dict(Keyword.objects.filter(
                pk__in=most_used).values_list('pk', 'keyword'))
            keywords = [names[pk] for pk in most_used]

        csw = CatalogueService.objects.get(pk=MRMAP_CSW_PK)

        builder = CSWCapabilities(
            csw,
            extra_keywords=keywords,
            base_url=request.build_absolute_uri("/csw"),
            operation_parameters={
                "GetRecords": {
                    "CONSTRAINTLANGUAGE": ["FILTER", "CQL_TEXT"],
                    "outputSchema": ["http://www.isotc211.org/2005/gmd"],  # NOSONAR normative ISO 19139 gmd outputSchema identifier advertised in the capabilities - not a network endpoint
                    "outputFormat": ["application/xml"],
                    "ElementSetName": ["full"],
                    "resultType": ["results", "hits", "validate"],
                    "typeNames": ["gmd:MD_Metadata"],
                },
                "GetRecordById": {
                    "outputSchema": ["http://www.isotc211.org/2005/gmd"],  # NOSONAR normative ISO 19139 gmd outputSchema identifier advertised in the capabilities - not a network endpoint
                    "outputFormat": ["application/xml"],
                    "ElementSetName": ["full"],
                    "typeNames": ["gmd:MD_Metadata"],
                },
            },
            filter_capabilities={
                "Spatial_Capabilities": {
                    "GeometryOperands": [
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Point"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:LineString"
                        },
                        {
                            "name": "GeometryOperand",
                            "text": "gml:Polygon"
                        }
                    ],
                    "SpatialOperators": [
                        {
                            "name": "SpatialOperator",
                            "_name": "BBOX"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Contains"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Crosses"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Disjoint"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Equals"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Intersects"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Overlaps"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Touches"
                        },
                        {
                            "name": "SpatialOperator",
                            "_name": "Within"
                        }
                    ],
                },
                "Scalar_Capabilities": {
                    "LogicalOperators": [
                        {
                            "name": "LogicalOperator",
                            "text": "AND"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "OR"
                        },
                        {
                            "name": "LogicalOperator",
                            "text": "NOT"
                        }
                    ],

                    "ComparisonOperators": [
                        {
                            "name": "ComparisonOperator",
                            "text": "EqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "NotEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThan"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "LessThanEqualTo"
                        },
                        {
                            "name": "ComparisonOperator",
                            "text": "GreaterThanEqualTo"
                        }
                    ]
                }
            }
        )

        # the sections a client asked for are read out of the built document, so
        # that the document which answers without the parameter is the one this
        # builder has always answered
        capabilities = builder.to_xml()
        self.only_requested_sections(capabilities, sections)
        capabilitites_doc = etree.tostring(
            capabilities,
            pretty_print=True,
            xml_declaration=True,
            encoding="UTF-8"
        ).decode("utf-8")

        # if (settings.DEBUG):
        # return TemplateResponse(request, "csw/debug.html", {"content": capabilitites_doc})
        return HttpResponse(
            status=200,
            content=capabilitites_doc,
            content_type="application/xml"
        )

    def get_records(self, request):
        field_mapping = self.get_field_map()

        q = self.get_filter_constraint()
        if isinstance(q, OGCServiceException):
            return q

        # The element set the response is answered in is read from the request
        # element -- both bindings carry their parameters in it (see
        # csw/elementsets.py) -- and a value outside ElementSetType is refused
        # before anything of the result set is read; 10.8.4.9, Table 65.
        requested_set = requested_element_set(self.ogc_request.xml_request)
        element_set = (requested_set or DEFAULT_ELEMENT_SET).lower()
        if element_set not in ELEMENT_SETS:
            return InvalidParameterValueException(
                ogc_request=self.ogc_request,
                locator="ElementSetName",
                message=(
                    f"ElementSetName must be one of "
                    f"{', '.join(repr(name) for name in ELEMENT_SETS)}; "
                    f"'{requested_set}' is none of them."))

        # SortBy is read the same way and mapped onto the ordering of both record
        # sources; a property this catalogue does not sort on is refused with the
        # InvalidParameterValue 10.8.4.9 leaves for it.
        sort_specs = []
        for property_name, descending in requested_sort_by(self.ogc_request.xml_request):
            field = sortable_field(property_name)
            if field is None:
                return InvalidParameterValueException(
                    ogc_request=self.ogc_request,
                    locator="SortBy" if self.ogc_request.is_get else "csw:SortBy",
                    message=(
                        f"The property '{property_name}' is not sortable. "
                        f"Sortable properties are: "
                        f"{', '.join(sortable_properties())}."))
            sort_specs.append((field, descending))

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self
        constraint = search_filter(q)

        try:
            # a GetRecords answers the stored document of a record and nothing else
            # of it, so nothing else of it is read -- save for the fields it is
            # sorted by, which the merge of the two sources compares
            dataset_metadata_records_result = apply_sort(
                dataset_records().filter(
                    constraint).only(*loaded_fields(sort_specs)),
                sort_specs)
            service_metadata_records_result = apply_sort(
                service_records().filter(
                    constraint).only(*loaded_fields(sort_specs)),
                sort_specs)
        except FieldError as e:
            requested_field = str(e).split(":")[0].split("'")[1]
            available_fields = field_mapping.keys()

            return InvalidQuery(
                ogc_request=self.ogc_request,
                locator="Constraint" if self.ogc_request.is_get else "csw:Query",
                message=f"The field '{requested_field}' is not provided as a queryable. Queryable fields are: {', '.join(available_fields)}"  # nopep8
            )
        total_records = dataset_metadata_records_result.count(
        ) + service_metadata_records_result.count()

        start_position = int(
            (self.ogc_request.xml_request.xpath(
                "/csw:GetRecords/@startPosition",
                namespaces={"csw": NAMESPACE_LOOKUP["csw_2_0_2"]}
            ) or ["1"])[0]
        ) - 1
        max_records = int(
            (self.ogc_request.xml_request.xpath(
                "/csw:GetRecords/@maxRecords",
                namespaces={"csw": NAMESPACE_LOOKUP["csw_2_0_2"]}
            ) or ["10"])[0]
        )

        max_records = max_records if max_records <= 1000 else 1000

        heap_count = start_position + max_records

        result_type = (self.ogc_request.xml_request.xpath(
            "/csw:GetRecords/@resultType",
            namespaces={"csw": NAMESPACE_LOOKUP["csw_2_0_2"]}
        ) or ["hits"])[0]

        builder = CSWBuilder()

        if result_type == "hits":
            # Table 66: a hits response answers the size of the result set and no
            # record of it -- numberOfRecordsReturned is 0 and nextRecord is 0,
            # which means "all records have been returned" and stops a client from
            # paging on a phantom position. No page is read for this answer.
            xml = builder.build_get_records_response(
                total_records=total_records,
                records_returned=0,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0,
                element_set=element_set,
            )
        elif result_type == "validate":
            # no errors while here. So the request was acknowledget as successfully
            xml = builder.build_acknowledgement(
                timestamp=self.start_time,
                echoed_request=self.ogc_request.xml_request)
        else:
            # Both sources are ordered by the same total order -- the requested
            # sorting over the primary key -- which means that a record which is
            # among the first `heap_count` records of the merged result is among
            # the first `heap_count` records of *its own* source too: every record
            # standing in front of it in the merged order stands in front of it in
            # its own source as well. So taking that many records from both and
            # merging them by that order answers the requested page, for the price
            # of two limited queries.
            merged_records = merge_sorted(
                chain(dataset_metadata_records_result[:heap_count],
                      service_metadata_records_result[:heap_count]),
                sort_specs
            )

            result = merged_records[start_position: heap_count]

            next_record = heap_count + 1
            next_record = next_record if next_record < total_records else total_records

            records_returned = len(result)

            # Table 66: the response names the element set it answers with, and
            # the non-full sets are the stored documents pruned to their view
            gmd_records = self.read_stored_documents(result)
            if isinstance(gmd_records, OGCServiceException):
                return gmd_records
            gmd_records = [project_gmd_record(document, element_set)
                           for document in gmd_records]
            xml = builder.build_get_records_response(
                total_records=total_records,
                records_returned=records_returned,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0 if next_record == total_records else next_record,
                element_set=element_set,
                gmd_records=gmd_records
            )

        content = etree.tostring(
            xml,
            pretty_print=True,
            encoding="utf-8",
            xml_declaration=True
        )
        # if (settings.DEBUG):
        #    return TemplateResponse(request, "csw/debug.html", {"content": content})
        return HttpResponse(status=200, content=content, content_type="application/xml")

    def get_record_by_id(self, request):
        requested_entities = self.ogc_request.requested_entities
        if len(requested_entities) == 1:
            dataset_metadata_records = DatasetMetadataRecord.objects.filter(
                file_identifier=requested_entities[0])

            service_metadata_records = ServiceMetadataRecord.objects.filter(
                file_identifier=requested_entities[0])
        else:
            dataset_metadata_records = DatasetMetadataRecord.objects.filter(
                file_identifier__in=requested_entities)

            service_metadata_records = ServiceMetadataRecord.objects.filter(
                file_identifier__in=requested_entities)
        records = chain(dataset_metadata_records, service_metadata_records)

        gmd_records = self.read_stored_documents(records)
        if isinstance(gmd_records, OGCServiceException):
            return gmd_records

        builder = CSWBuilder()
        xml = builder.build_get_records_by_id_response(gmd_records=gmd_records)

        return HttpResponse(
            status=200, content=etree.tostring(xml, pretty_print=True, encoding="utf-8", xml_declaration=True),
            content_type="application/xml")

    def requested_type_names(self):
        """The typeNames the DescribeRecord request asks for.

        A DescribeRecord which names no typeName asks for the whole information
        model of the catalogue (10.2.4.1), which is the set of typeNames this
        endpoint serves -- so an absent parameter is answered as that set rather
        than as nothing. The KVP binding separates a list by comma, the XML
        binding carries one ``csw:TypeName`` element per name.
        """
        if self.ogc_request.is_get:
            requested = (
                self.ogc_request.ogc_query_params.get("TYPENAME")
                or self.ogc_request.ogc_query_params.get("TypeName")
                or self.ogc_request.ogc_query_params.get("typeNames")
                or ""
            )
            names = requested.replace(",", " ").split()
        else:
            names = [
                element.text.strip()
                for element in self.ogc_request.xml_request.xpath(
                    "/csw:DescribeRecord/csw:TypeName",
                    namespaces={"csw": NAMESPACE_LOOKUP["csw_2_0_2"]}
                )
                if element.text
            ]
        return list(dict.fromkeys(names)) or list(SUPPORTED_RECORD_TYPE_NAMES)

    def describe_record(self, request):
        """Answer the schema description of the requested record types.

        See :mod:`csw.describe_record` for what a SchemaComponent of this
        endpoint carries and why.
        """
        requested_type_names = self.requested_type_names()
        if [
            name for name in requested_type_names
            if name not in SUPPORTED_RECORD_TYPE_NAMES
        ]:
            return NotSupported(
                service_type=self.ogc_request.service_type,
                service_version=self.ogc_request.service_version,
                locator="typeName",
                message=(
                    "Only "
                    f"{', '.join(repr(name) for name in SUPPORTED_RECORD_TYPE_NAMES)}"
                    " as typeName is supported."))

        builder = CSWDescribeRecordBuilder()
        xml = builder.build_describe_record_response(requested_type_names)

        return HttpResponse(
            status=200,
            content=etree.tostring(xml, pretty_print=True, encoding="utf-8", xml_declaration=True),
            content_type="application/xml")

    def get_and_post(self, request, *args, **kwargs):
        """Http get/post method

        :return:
        :rtype: dict or :class:`requests.models.Request`
        """
        if self.ogc_request.is_get_capabilities_request:
            return self.get_capabilities(request=request)
        elif self.ogc_request.is_get_records_request:
            with transaction.atomic():
                return self.get_records(request=request)
        elif self.ogc_request.is_get_record_by_id_request:
            return self.get_record_by_id(request=request)
        elif self.ogc_request.is_describe_record_request:
            return self.describe_record(request=request)
        # The operations of the minimal CSW profile (Table 60) are answered
        # above; everything else -- GetDomain and the transactional operations
        # which mrmap does not serve -- is refused below.
        else:
            # the fallback of an operation this endpoint does not implement: the
            # OWS Common report which names it (see #907 -- this call answering
            # a TypeError -> raw 500 until the exception machinery of #908 made
            # the identity of the report optional from the request itself)
            return OperationNotSupportedException(ogc_request=self.ogc_request)
