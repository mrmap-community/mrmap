import os

from csw.exceptions import InvalidQuery, NotSupported
from django.contrib.gis.db.models.fields import MultiPolygonField
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.expressions import ArraySubquery
from django.core.exceptions import FieldError
from django.db.models.aggregates import Count
from django.db.models.expressions import Case, F, OuterRef, Value, When
from django.db.models.fields import CharField
from django.db.models.functions import Cast, Coalesce, Concat, datetime
from django.db.models.query_utils import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from eulxml.xmlmap import load_xmlobject_from_file
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.capabilities.csw.csw202 import (CatalogueService,
                                                        ServiceMetadataContact)
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.exceptions import OGCServiceException
from ows_lib.xml_mapper.xml_responses.csw.get_record_by_id import \
    GetRecordsResponse as GetRecordByIdResponse
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.models.metadata import Keyword, MetadataRelation
from registry.proxy.ogc_exceptions import (MissingRequestParameterException,
                                           MissingServiceParameterException,
                                           OperationNotSupportedException)


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

        elif self.ogc_request.ogc_query_params.get("outputSchema", "http://www.isotc211.org/2005/gmd") != "http://www.isotc211.org/2005/gmd":
            return NotSupported(
                ogc_request=self.ogc_request,
                locator="outputSchema",
                message="Only 'http://www.isotc211.org/2005/gmd' as outputschema is supported.")
        elif self.ogc_request.ogc_query_params.get("typeNames", "gmd:MD_Metadata") != "gmd:MD_Metadata":
            return NotSupported(
                ogc_request=self.ogc_request,
                locator="typeNames",
                message="Only 'http://www.isotc211.org/2005/gmd' as outputschema is supported.")

    def get_field_map(self):
        # this dict mapps the ogc specificated filterable attributes to our database schema(s)
        field_mapping = {
            "title": "title",
            "Title": "title",
            "dc:title": "title",
            "abstract": "abstract",
            "Abstract": "abstract",
            "dc:abstract": "abstract",
            "description": "abstract",
            # "subject": "keywords",  # TODO: keywords right?
            # "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record
            "coverage": "bounding_geometry",
            "ows:BoundingBox": "bounding_geometry",
            "date": "date_stamp",
            "dc:modified": "date_stamp",
            "modified": "date_stamp",
            "Modified": "date_stamp",
            "type": "hierarchy_level",
            "dc:type": "hierarchy_level",
            "Type": "hierachy_level",
            "ResourceIdentifier": "resource_identifier",
            "identifier": "file_identifier",
            "Identifier": "file_identifier",
            "AnyText": "search"
        }
        return field_mapping

    def get_basic_queryset(self):
        # TODO: only prefetch related if result_type is not hits

        # # "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record

        # "type": "type",
        # "dc:type": "type",

        return MetadataRelation.objects.annotate(
            title=Coalesce(
                "dataset_metadata__title",
                "service_metadata__title",
                "layer__title",
                "feature_type__title",
                "wms__title",
                "wfs__title",
                "csw__title"
            ),
            abstract=Coalesce(
                "dataset_metadata__abstract",
                "service_metadata__abstract",
                "layer__abstract",
                "feature_type__abstract",
                "wms__abstract",
                "wfs__abstract",
                "csw__abstract"
            ),
            bounding_geometry=Coalesce(
                "dataset_metadata__bounding_geometry",
                # TODO: "service_metadata__bounding_geometry",
                "layer__bbox_lat_lon",
                "feature_type__bbox_lat_lon",
                # TODO: get from child layers "wms__bbox_lat_lon",
                # TODO: get from child featuretypes "wfs__bbox_lat_lon",
                # TODO: "csw__bbox_lat_lon"
                output_field=MultiPolygonField()
            ),
            date_stamp=Coalesce(
                "dataset_metadata__date_stamp",
                "service_metadata__date_stamp",
                "layer__date_stamp",
                "feature_type__date_stamp",
                "wms__date_stamp",
                "wfs__date_stamp",
                "csw__date_stamp"
            ),
            resource_identifier=Concat(
                F("dataset_metadata__dataset_id_code_space"),
                F("dataset_metadata__dataset_id"),
                output_field=CharField()
            ),
            file_identifier=Coalesce(
                "dataset_metadata__file_identifier",
                "service_metadata__file_identifier",
                Cast("layer__id", CharField()),
                Cast("feature_type__id", CharField()),
                Cast("wms__id", CharField()),
                Cast("wfs__id", CharField()),
                Cast("csw__id", CharField()),
                output_field=CharField()
            ),
            hierarchy_level=Case(
                When(dataset_metadata__isnull=False, then=Value("dataset")),
                When(service_metadata__isnull=False, then=Value("service")),
                default=Value("dataset")
            ),
            all_related_keywords=ArraySubquery(
                Keyword.objects.filter(
                    Q(datasetmetadatarecord_metadata=OuterRef(
                        "dataset_metadata__pk"))
                    | Q(servicemetadatarecord_metadata=OuterRef(
                        "service_metadata__pk"))
                ).distinct("keyword").values_list("keyword", flat=True)
            ),
            search=Concat(
                "title",
                Value(" "),
                "abstract",
                output_field=CharField()
            ),
        ).prefetch_related(
            "dataset_metadata",
            "service_metadata"
        )

    def get_capabilities(self, request):
        """Return the camouflaged capabilities document of the founded service.
        .. note::
           See :meth:`registry.models.document.DocumentModelMixin.xml_secured` for details of xml_secured function.
        :return: the camouflaged capabilities document.
        :rtype: :class:`django.http.response.HttpResponse`
        """

        # select keywords by most freuqency linked by dataset or service; first 10 are used
        relation_ids = self.get_basic_queryset().all(
        ).aggregate(pks=ArrayAgg("pk", distinct=True))["pks"]

        keywords = Keyword.objects.filter(
            Q(datasetmetadatarecord_metadata__resource_relation__in=relation_ids) |
            Q(servicemetadatarecord_metadata__resource_relation__in=relation_ids)
        ).annotate(
            frequency=Count("pk"),
        ).order_by("-frequency").values_list("keyword", flat=True)[:10]

        cap_file = os.path.dirname(
            os.path.abspath(__file__)) + "/capabilitites.xml"

        capabilitites_doc: CatalogueService = load_xmlobject_from_file(
            cap_file, xmlclass=CatalogueService)
        capabilitites_doc.keywords = keywords

        capabilitites_doc.title = "Mr. Map CSW"
        capabilitites_doc.service_contact = ServiceMetadataContact(name="test")

        capabilitites_doc.operation_urls.extend(
            [
                OperationUrl(method="Get", operation="GetCapabilities",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"]),
                OperationUrl(method="Get", operation="GetRecords",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"]),
                OperationUrl(method="Post", operation="GetRecords",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"]),
                OperationUrl(method="Get", operation="GetRecordById",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"]),
                OperationUrl(method="Post", operation="GetRecordById",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"])
            ]
        )

        return HttpResponse(
            status=200,
            content=capabilitites_doc.serializeDocument(pretty=True),
            content_type="application/xml"
        )

    def get_records(self, request):

        field_mapping = self.get_field_map()

        q = self.ogc_request.filter_constraint(field_mapping=field_mapping)
        if isinstance(q, OGCServiceException):
            return q

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self
        result = self.get_basic_queryset()

        # TODO: implement a default order by created at
        # .order_by(
        #     # Default action is to
        #     # present the records
        #     # in the order in which
        #     # they are retrieved
        #     "-file_identifier"
        # )

        # TODO: catch FieldError for unsupported filter fields
        try:
            result = result.filter(q)
        except FieldError as e:
            requested_field = str(e).split(":")[0].split("'")[1]
            available_fields = field_mapping.keys()

            return InvalidQuery(
                ogc_request=self.ogc_request,
                locator="Constraint" if self.ogc_request.is_get else "csw:Query",
                message=f"The field '{requested_field}' is not provided as a queryable. Queryable fields are: {', '.join(available_fields)}"
            )

        total_records = result.count()

        start_position = int(
            self.ogc_request.ogc_query_params.get("startPosition", "1")) - 1
        max_records = int(
            self.ogc_request.ogc_query_params.get("maxRecords", "10"))

        heap_count = start_position + max_records
        next_record = heap_count + 1
        next_record = next_record if next_record < total_records else total_records

        result = result[start_position: heap_count]
        records_returned = len(result)

        result_type = self.ogc_request.ogc_query_params.get(
            "resultType", "hits")

        if result_type == "hits":
            xml = GetRecordsResponse(
                total_records=total_records,
                records_returned=records_returned,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0 if next_record == total_records else next_record
            )
        elif result_type == "validate":
            pass
            # TODO: return Acknowledgement
        else:
            xml = GetRecordsResponse(
                total_records=total_records,
                records_returned=records_returned,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0 if next_record == total_records else next_record
            )
            for record in result:
                if record.dataset_metadata:
                    print(record.dataset_metadata.xml_backup_string)
                    xml.gmd_records.append(
                        record.dataset_metadata.xml_backup)
                elif record.service_metadata:
                    xml.gmd_records.append(
                        record.service_metadata.xml_backup)
        return HttpResponse(status=200, content=xml.serialize(pretty=True), content_type="application/xml")

    def get_record_by_id(self, request):
        requested_entities = self.ogc_request.requested_entities
        if len(requested_entities) == 1:
            records = self.get_basic_queryset().filter(
                file_identifier=requested_entities[0])
        else:
            records = self.get_basic_queryset().filter(
                file_identifier__in=requested_entities)
        xml = GetRecordByIdResponse(
            version="2.0.2",
            time_stamp=self.start_time,
        )
        for record in records:
            if record.dataset_metadata:
                xml.gmd_records.append(
                    record.dataset_metadata.xml_backup)
            elif record.service_metadata:
                xml.gmd_records.append(
                    record.service_metadata.xml_backup)
        return HttpResponse(status=200, content=xml.serialize(pretty=True), content_type="application/xml")

    def get_and_post(self, request, *args, **kwargs):
        """Http get/post method

        :return:
        :rtype: dict or :class:`requests.models.Request`
        """
        if self.ogc_request.is_get_capabilities_request:
            return self.get_capabilities(request=request)
        elif self.ogc_request.is_get_records_request:
            return self.get_records(request=request)
        elif self.ogc_request.is_get_record_by_id_request:
            return self.get_record_by_id(request=request)
        # TODO: other csw operations
        else:
            return OperationNotSupportedException(ogc_request=self.ogc_request)
