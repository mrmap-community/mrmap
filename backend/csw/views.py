import datetime
from itertools import chain

from csw.exceptions import InvalidQuery, NotSupported
from csw.queryables import (FIELD_MAP, dataset_records, search_filter,
                            service_records)
from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models import BigIntegerField, F, OuterRef, Subquery, Value
from django.db.models.aggregates import Count
from django.db.models.functions import Coalesce
from django.db.models.query_utils import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from lxml import etree
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from registry.ows_lib.csw.builder import CSWBuilder, CSWCapabilities
from registry.ows_lib.request.ogc_request import OGCRequest
from registry.ows_lib.response.exceptions import (
    MissingRequestParameterException, MissingServiceParameterException,
    OGCServiceException, OperationNotSupportedException)
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP
from registry.settings import MRMAP_CSW_PK


@method_decorator(csrf_exempt, name="dispatch")
class CswServiceView(View):
    """
    MrMap CSW implementation

    """

    def dispatch(self, request, *args, **kwargs):
        self.start_time = datetime.datetime.now()
        self.ogc_request = OGCRequest.from_django_request(request)

        exception = self.check_request()
        if exception:
            return exception
        # self.analyze_request()

        return self.get_and_post(request=request, *args, **kwargs)

    def check_request(self):
        """proof if all mandatory query parameters are part of the reuqest"""
        if not self.ogc_request.operation:
            return MissingRequestParameterException(ogc_request=self.ogc_request)
        elif not self.ogc_request.service_type:
            return MissingServiceParameterException(ogc_request=self.ogc_request)
        # TODO: HAndle ELEMENTSETNAME parameter, handle resultType parameter
        # FIXME: if post method, this will not cover the check

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

    def get_filter_constraint(self):
        field_mapping = self.get_field_map()
        return self.ogc_request.filter_constraint(field_mapping=field_mapping)

    def get_capabilities(self, request):
        """Return the camouflaged capabilities document of the founded service.
        .. note::
           See :meth:`registry.models.document.DocumentModelMixin.xml_secured` for details of xml_secured function.
        :return: the camouflaged capabilities document.
        :rtype: :class:`django.http.response.HttpResponse`
        """

        dataset_count_subquery = DatasetMetadataRecord.keywords.through.objects.filter(
            keyword=OuterRef('pk')
        ).values('keyword').annotate(
            count=Count('keyword')
        ).values('count')

        service_count_subquery = ServiceMetadataRecord.keywords.through.objects.filter(
            keyword=OuterRef('pk')
        ).values('keyword').annotate(
            count=Count('keyword')
        ).values('count')

        keywords = Keyword.objects.annotate(
            dataset_count=Coalesce(Subquery(
                dataset_count_subquery, output_field=BigIntegerField()), Value(0)),
            service_count=Coalesce(Subquery(
                service_count_subquery, output_field=BigIntegerField()), Value(0)),
            usage_count=F('dataset_count') + F('service_count')
        ).filter(
            Q(dataset_count__gt=0) | Q(service_count__gt=0)
        ).order_by(
            '-usage_count'
        ).values_list(
            "keyword",
            flat=True
        )[:10]

        csw = CatalogueService.objects.get(pk=MRMAP_CSW_PK)

        builder = CSWCapabilities(
            csw,
            extra_keywords=list(keywords),
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

        capabilitites_doc = builder.to_xml_string()

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

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self
        constraint = search_filter(q)

        try:
            # a GetRecords answers the stored document of a record and nothing else of
            # it, so nothing else of it is read
            dataset_metadata_records_result = dataset_records().filter(
                constraint).only("pk", "xml_backup_file")
            service_metadata_records_result = service_records().filter(
                constraint).only("pk", "xml_backup_file")
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
            )
        elif result_type == "validate":
            # no errors while here. So the request was acknowledget as successfully
            xml = builder.build_acknowledgement(
                timestamp=self.start_time,
                echoed_request=self.ogc_request.xml_request)
        else:
            # Both sources are ordered by their primary key, which means that a record which
            # is among the first `heap_count` records of the merged result is among the
            # first `heap_count` records of *its own* source too: every record standing in
            # front of it in the merged order stands in front of it in its own source as
            # well. So taking that many records from both and merging them by pk answers the
            # requested page, for the price of two limited queries.
            # TODO: order by correct querparameter
            merged_records = sorted(
                chain(dataset_metadata_records_result[:heap_count],
                      service_metadata_records_result[:heap_count]),
                key=lambda instance: instance.pk
            )

            result = merged_records[start_position: heap_count]

            next_record = heap_count + 1
            next_record = next_record if next_record < total_records else total_records

            records_returned = len(result)

            gmd_records = [
                etree.fromstring(record.xml_backup)
                for record in result
            ]
            xml = builder.build_get_records_response(
                total_records=total_records,
                records_returned=records_returned,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0 if next_record == total_records else next_record,
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

        gmd_records = [
            etree.fromstring(record.xml_backup)
            for record in records
        ]

        builder = CSWBuilder()
        xml = builder.build_get_records_by_id_response(gmd_records=gmd_records)

        return HttpResponse(
            status=200, content=etree.tostring(xml, pretty_print=True, encoding="utf-8", xml_declaration=True),
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
        # TODO: other csw operations
        else:
            return OperationNotSupportedException(ogc_request=self.ogc_request)
