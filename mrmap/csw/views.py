from django.contrib.gis.db.models.fields import MultiPolygonField
from django.contrib.postgres.aggregates import ArrayAgg
from django.contrib.postgres.expressions import ArraySubquery
from django.db.models.aggregates import Count
from django.db.models.expressions import Case, F, OuterRef, Value, When
from django.db.models.fields import CharField
from django.db.models.functions import Cast, Coalesce, Concat, datetime
from django.db.models.query_utils import Q
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.capabilities.csw.csw202 import (CatalogueService,
                                                        ServiceMetadataContact,
                                                        ServiceType)
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.exceptions import OGCServiceException
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

        csw_capabilities = CatalogueService(
            service_type=ServiceType(version="2.0.2", _name="CSW"),
            keywords=keywords
        )
        csw_capabilities.title = "Mr. Map CSW"
        csw_capabilities.service_contact = ServiceMetadataContact(name="test")

        csw_capabilities.operation_urls.extend(
            [
                OperationUrl(method="Get", operation="GetCapabilities",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"]),
                OperationUrl(method="Get", operation="GetRecords",
                             url=request.build_absolute_uri('csw'), mime_types=["application/xml"])
            ]
        )

        return HttpResponse(
            status=200,
            content=csw_capabilities.serializeDocument(),
            content_type="application/xml"
        )

    def get_records(self, request):

        # this dict mapps the ogc specificated filterable attributes to our database schema(s)
        field_mapping = {
            "title": "title",
            "dc:title": "title",
            "abstract": "abstract",
            "dc:abstract": "abstract",
            "description": "abstract",
            # "subject": "keywords",  # TODO: keywords right?
            # "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record
            "coverage": "bounding_geometry",
            "ows:BoundingBox": "bounding_geometry",
            "date": "date_stamp",
            "dc:modified": "date_stamp",
            "type": "hierarchy_level",
            "dc:type": "hierarchy_level",
            "ResourceIdentifier": "resource_identifier"
        }
        q = self.ogc_request.filter_constraint(field_mapping=field_mapping)
        if isinstance(q, OGCServiceException):
            return q

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self
        result = self.get_basic_queryset()

        # TODO: implement type filter

        # .order_by(
        #     # Default action is to
        #     # present the records
        #     # in the order in which
        #     # they are retrieved
        #     "-file_identifier"
        # )

        # TODO: catch FieldError for unsupported filter fields
        result = result.filter(q)
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
        # TODO: other csw operations
        else:

            return OperationNotSupportedException(ogc_request=self.ogc_request)
