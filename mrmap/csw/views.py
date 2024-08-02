import os
from itertools import chain

from csw.exceptions import InvalidQuery, NotSupported
from django.contrib.postgres.aggregates import ArrayAgg
from django.core.exceptions import FieldError
from django.db import transaction
from django.db.models.aggregates import Count
from django.db.models.functions import datetime
from django.db.models.query_utils import Q
from django.http import HttpResponse, JsonResponse
from django.http.request import HttpRequest as HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from eulxml.xmlmap import load_xmlobject_from_file
from lxml.etree import XMLSyntaxError
from ows_lib.models.ogc_request import OGCRequest
from ows_lib.xml_mapper.capabilities.csw.csw202 import (CatalogueService,
                                                        ServiceMetadataContact)
from ows_lib.xml_mapper.capabilities.mixins import OperationUrl
from ows_lib.xml_mapper.exceptions import OGCServiceException
from ows_lib.xml_mapper.xml_responses.csw.achnowledgment import Acknowledgement
from ows_lib.xml_mapper.xml_responses.csw.get_record_by_id import \
    GetRecordsResponse as GetRecordByIdResponse
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.models.materialized_views import (
    SearchableDatasetMetadataRecord, SearchableServiceMetadataRecord)
from registry.models.metadata import (DatasetMetadataRecord, Keyword,
                                      ServiceMetadataRecord)
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
            "subject": "keywords_list",  # TODO: keywords right?
            # "creator": "",  # TODO: find out what the creator field is exactly represented inside the iso metadata record
            "coverage": "bounding_geometry",
            "ows:BoundingBox": "bounding_geometry",
            "date": "date_stamp",
            "dc:modified": "date_stamp",
            "modified": "date_stamp",
            "Modified": "date_stamp",
            "type": "hierarchy_level",
            "dc:type": "hierarchy_level",
            "Type": "hierarchy_level",
            "ResourceIdentifier": "resource_identifier",
            "identifier": "file_identifier",
            "Identifier": "file_identifier",
            "AnyText": "search_vector"
        }
        return field_mapping

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

        dataset_record_ids = DatasetMetadataRecord.objects.all().aggregate(
            pks=ArrayAgg("pk", distinct=True))["pks"]
        service_record_ids = DatasetMetadataRecord.objects.all().aggregate(
            pks=ArrayAgg("pk", distinct=True))["pks"]
        keywords = Keyword.objects.filter(
            Q(datasetmetadatarecord_metadata__in=dataset_record_ids) |
            Q(servicemetadatarecord_metadata__in=service_record_ids)
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

        q = self.get_filter_constraint()
        if isinstance(q, OGCServiceException):
            return q

        # Cause our MetadataRelation cross table model relates to the concrete models and does not provide the field names by it self
        # we need to construct the concrete filter by our self
        dataset_metadata_records = SearchableDatasetMetadataRecord.objects.all()

        service_metadata_records = SearchableServiceMetadataRecord.objects.all()
        # TODO:This are the prepared queries for autogenerated
        # layer_records = Layer.objects.annotate(
        #     hierachy_level=Value("dataset"),
        #     resource_identifier=Concat(
        #          # TODO: should be the hostname of the instance
        #         Value("http://mrmap/"),
        #         F("pk"),
        #         output_field=CharField()
        #     ),
        # )
        # feature_type_records = FeatureType.objects.annotate(
        #     hierachy_level=Value("dataset"),
        #     resource_identifier=Concat(
        #          # TODO: should be the hostname of the instance
        #         Value("http://mrmap/"),
        #         F("pk"),
        #         output_field=CharField()
        #     ),
        # )

        try:
            # FIXME: replace wildcards from anytext lookups
            # Filter by AnyText with like operator and wildcards does not use a correct ts_vector query.

            dataset_metadata_records_result = dataset_metadata_records.filter(
                q).only("xml_backup_file", "pk", "date_stamp", "bounding_geometry", "title", "abstract",)
            service_metadata_records_result = service_metadata_records.filter(
                q).only("xml_backup_file", "pk", "date_stamp", "bounding_geometry", "title", "abstract",)
        except FieldError as e:
            requested_field = str(e).split(":")[0].split("'")[1]
            available_fields = field_mapping.keys()

            return InvalidQuery(
                ogc_request=self.ogc_request,
                locator="Constraint" if self.ogc_request.is_get else "csw:Query",
                message=f"The field '{requested_field}' is not provided as a queryable. Queryable fields are: {
                    ', '.join(available_fields)}"
            )

        # contact_stats = MetadataContact.objects.filter(
        #     datasetmetadatarecord_metadata_contact__in=dataset_metadata_records_result
        # ).annotate(
        #     frequency=Count("pk")
        # ).order_by("-frequency").values_list("name", "frequency")

        # print(contact_stats)

        total_records = dataset_metadata_records_result.count(
        ) + service_metadata_records_result.count()

        start_position = int(
            self.ogc_request.xml_request.start_position or 1) - 1
        max_records = int(
            self.ogc_request.xml_request.max_records or 10)
        max_records = max_records if max_records <= 1000 else 1000

        heap_count = start_position + max_records

        result_list = sorted(
            chain(dataset_metadata_records_result[start_position: heap_count],
                  service_metadata_records_result[start_position: heap_count]),
            # TODO: order by correct querparameter
            key=lambda instance: instance.pk
        )

        result = result_list[start_position: heap_count]

        next_record = heap_count + 1
        next_record = next_record if next_record < total_records else total_records

        records_returned = len(result)

        result_type = self.ogc_request.xml_request.result_type or "hits"

        if result_type == "hits":
            xml = GetRecordsResponse(
                total_records=total_records,
                records_returned=records_returned,
                version="2.0.2",
                time_stamp=self.start_time,
                next_record=0 if next_record == total_records else next_record
            )
        elif result_type == "validate":
            # no errors while here. So the request was acknowledget as successfully
            xml = Acknowledgement(
                time_stamp=self.start_time,
                echoed_get_records_request=self.ogc_request.xml_request
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
                try:
                    xml.gmd_records.append(
                        record.xml_backup)
                except XMLSyntaxError:
                    continue

        return HttpResponse(status=200, content=xml.serialize(pretty=True), content_type="application/xhtml+xml")

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
        xml = GetRecordByIdResponse(
            version="2.0.2",
            time_stamp=self.start_time,
        )
        for record in records:
            xml.gmd_records.append(record.xml_backup)
        return HttpResponse(status=200, content=xml.serialize(pretty=True), content_type="application/xml")

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


# TODO: log the request on this view. HTTP_Referer, searchUrl, searchText, HTTP_USER_AGENT, catalogueId

@method_decorator(csrf_exempt, name="dispatch")
class MapBenderSearchApi(View):

    def dispatch(self, request: HttpRequest, *args: os.Any, **kwargs: os.Any) -> HttpResponse:
        self.start_time = datetime.datetime.now()
        response = super().dispatch(request, *args, **kwargs)
        return response

    def build_ogc_filter(self):
        pass

    def get(self, request: HttpRequest, *args: os.Any, **kwargs: os.Any) -> HttpResponse:
        search_text = request.GET.get("searchText")
        catalogue_id = request.GET.get("catalogueId")
        # validate tot wms,wfs,wmc,georss
        search_resources = request.GET.get("searchResources")
        target = request.GET.get("target")
        # example: &searchBbox=7.18159618172,50.2823608933,7.26750846535,50.3502633407
        search_bbox = request.GET.get("searchBbox")
        search_type_bbox = request.GET.get(
            "searchTypeBbox")  # inside / outside
        language_code = request.GET.get("languageCode")
        output_format = request.GET.get("outputFormat")
        search_pages = request.GET.get("searchPages")

        self.stop_time = datetime.datetime.now()

        del_link_search_text = [f"{key}=*" if key == "searchText" else f"{
            key}={value}" for key, value in request.GET.items()].join("&")
        del_link_search_resources = [f"{key}={value}" if key != "searchResources" else f"{
            key}={value}" for key, value in request.GET.items()].join("&")

        data = {
            "dataset": {
                "md": {
                    "nresults": 0,  # TODO
                    "p": 1,  # TODO
                    "rpp": 10,
                    "genTime": self.stop_time - self.start_time,
                },
                "srv": [

                ]
            },
            "searchFilter": {
                "origUrl": [f"{key}={value}" for key, value in request.GET.items()].join("&"),
                "searchText": {
                    "title": "Suchbegriff(e):",
                    "delLink": del_link_search_text,
                    "item": [
                        {
                            "title": "wald",  # TODO
                            "delLink": del_link_search_text,
                        }
                    ]
                },
                "searchResources": {
                    "title": "Art der Ressource:",
                    "delLink": del_link_search_resources,
                    "item": [
                        {
                            "title": "Datensätze",  # TODO
                            "delLink": del_link_search_resources,
                        }
                    ]
                }
            }
        }

        JsonResponse(data)

        response = super().get(request, *args, **kwargs)

        return response
