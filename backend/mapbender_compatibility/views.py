from typing import Any
from urllib import parse

from django.contrib.postgres.search import SearchQuery
from django.db.models.functions import datetime
from django.forms import ValidationError
from django.http import HttpResponse, JsonResponse
from django.http.request import HttpRequest as HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from eulxml.xmlmap import load_xmlobject_from_string
from ows_lib.xml_mapper.xml_responses.csw.get_records import GetRecordsResponse
from registry.models.materialized_views import (
    SearchableDatasetMetadataRecord, SearchableServiceMetadataRecord)
from registry.models.service import CatalogueService as DBCatalogueService


# TODO: log the request on this view. HTTP_Referer, searchUrl, searchText, HTTP_USER_AGENT, catalogueId
@method_decorator(csrf_exempt, name="dispatch")
class MapBenderSearchApi(View):
    """
    example requests:
    http://localhost:8001/mapbender/search?searchText=wald&catalogueId=4&searchResources=dataset&target=webclient
    http://localhost:8001/mapbender/search?searchText=wald&catalogueId=4&searchResources=dataset&target=webclient&searchBbox=7.18159618172,50.2823608933,7.26750846535,50.3502633407
    """

    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        self.start_time = datetime.datetime.now()
        response = super().dispatch(request, *args, **kwargs)
        return response

    def get_search_text_filter(self):
        # TODO: implement , seperated search values
        search_text = self.request.GET.get("searchText", "*")
        if search_text == "*":
            search_text = ""
        return search_text.split(",")

    def build_cql_filter(self):
        any_text_filters = self.get_search_text_filter()

        search_resources = self.request.GET.get("searchResources", "dataset")

        cql_filter_expr = f"Type LIKE '{search_resources}'"  # noqa

        # language_code = self.request.GET.get("languageCode", 'en')
        # cql_filter_expr += f" AND ResourceLanguage LIKE '{language_code}'" # noqa

        first_loop = True
        for any_text in any_text_filters:

            if first_loop:
                cql_filter_expr += f" And AnyText LIKE '{any_text}'"
            else:
                cql_filter_expr += f" Or AnyText LIKE '{any_text}'"

        # example: &searchBbox=7.18159618172,50.2823608933,7.26750846535,50.3502633407
        search_bbox = self.request.GET.get("searchBbox")
        if search_bbox:
            # TODO: the_geom col name need to be checked by capabilitites of the remote csw to set the corret geometry col
            if cql_filter_expr != "":
                cql_filter_expr += f"AND BBOX(the_geom, {search_bbox})"
            else:
                cql_filter_expr += f"BBOX(the_geom, {search_bbox})"

        # TODO: implement inside or outside bbox as cql filter
        # search_type_bbox = request.GET.get(
        #    "searchTypeBbox")  # inside / outside
        return cql_filter_expr

    def remote_search(self):
        srv = []
        content = {
            "md": {
                "nresults": 0,
                "p": self.request.GET.get("searchPages", 1),
                "rpp": self.request.GET.get("maxResults", 10),
            },
            "srv": srv
        }
        try:
            csw = DBCatalogueService.objects.get(pk=self.catalogue_id)

            search_pages = int(self.request.GET.get("searchPages", 1))
            max_results = int(self.request.GET.get("maxResults", 10))

            client = csw.client
            csw_request = client.get_records_request(
                cql_constraint=self.build_cql_filter(),
                max_records=max_results,
                start_position=(search_pages * max_results) - max_results + 1,
                result_type="results"
            )

            gmd_metadata_response = client.send_request(csw_request)

            if gmd_metadata_response.status_code >= 200 and gmd_metadata_response.status_code < 400:
                # TODO: #527: Edge Case. 'Client' component is needed here
                parsed_get_records: GetRecordsResponse = load_xmlobject_from_string(
                    gmd_metadata_response.content, GetRecordsResponse)

                for gmd_metadata in parsed_get_records.gmd_records:
                    get_record_by_id_url = client.get_record_by_id_request(
                        id=gmd_metadata.file_identifier)

                    srv.append({
                        "id": gmd_metadata.file_identifier,
                        "date": gmd_metadata.date_stamp,
                        "datasetId": f"{gmd_metadata.code_space}{gmd_metadata.code}",
                        "previewUrl": "TODO",
                        "respOrg": gmd_metadata.metadata_contact.name if gmd_metadata.metadata_contact else "",
                        "bbox": ",".join([str(coord) for coord in gmd_metadata.bounding_geometry.extent]) if gmd_metadata.bounding_geometry else None,
                        "title": gmd_metadata.title,
                        "abstract": gmd_metadata.abstract,
                        "mdLink": get_record_by_id_url.url,
                        "htmlLink": f'https://www.geoportal.rlp.de/mapbender/php/mod_exportIso19139.php?url={parse.quote_plus(get_record_by_id_url.url)}&resolveCoupledResources=true',
                    })
                content["md"]["nresults"] = parsed_get_records.total_records or 0
        except DBCatalogueService.DoesNotExist:
            # TODO: response with error code
            pass
        except ValidationError:
            pass

        return content

    def local_search(self):
        search_pages = int(self.request.GET.get("searchPages", 1) or 1)
        max_records = int(self.request.GET.get("maxResults", 10) or 10)
        start_position = search_pages * max_records - max_records

        heap_count = start_position + max_records

        dataset_metadata_records = SearchableDatasetMetadataRecord.objects.all()
        service_metadata_records = SearchableServiceMetadataRecord.objects.all()
        any_text_filters = self.get_search_text_filter()
        search_query = None
        if any_text_filters:
            for any_text in any_text_filters:
                if not search_query:
                    search_query = SearchQuery(any_text)
                else:
                    search_query |= SearchQuery(any_text)
        else:
            search_query = SearchQuery("")

        search_resources = self.request.GET.get("searchResources", "dataset")
        if search_resources == "dataset":
            dataset_metadata_records_result = dataset_metadata_records.filter(
                search_vector=search_query).only("xml_backup_file", "pk", "date_stamp", "bounding_geometry", "title", "abstract",)
            total_records = dataset_metadata_records_result.count()
            result = dataset_metadata_records_result[start_position: heap_count]
        elif search_resources == "service":
            service_metadata_records_result = service_metadata_records.filter(
                search_vector=search_query).only("xml_backup_file", "pk", "date_stamp", "bounding_geometry", "title", "abstract",)
            total_records = service_metadata_records_result.count()
            result = service_metadata_records_result[start_position: heap_count]
        else:
            # TODO: implement other hierachylevels also
            # return empty result for all other hierachylevels
            result = []
        srv = []
        for record in result:
            # TODO: #527
            gmd_metadata = record.xml_backup
            srv.append({
                "id": record.pk,
                "date": gmd_metadata.date_stamp,
                "datasetId": "TODO",
                "previewUrl": "TODO",
                "respOrg": gmd_metadata.child,
                "bbox": gmd_metadata.bounding_geometry.bbox,
                "title": gmd_metadata.title,
                "abstract": gmd_metadata.abstract,
                "mdLink": "TODO",
                "htmlLink": "TODO",
            })
        return {
            "md": {
                "nresults": total_records,
                "p": search_pages,
                "rpp": max_records,
                "genTime": 0,
            },
            "srv": srv
        }

    @property
    def is_remote_search(self):
        self.catalogue_id = self.request.GET.get("catalogueId")
        return True if self.catalogue_id else False

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:

        if self.is_remote_search:
            resources = self.remote_search()
        else:
            resources = self.local_search()

        del_link_search_resources = "&".join([f"{key}={value}" if key != "searchResources" else f"{key}={value}" for key, value in request.GET.items()])  # nopep8

        resources["md"]["genTime"] = (
            datetime.datetime.now() - self.start_time).total_seconds()
        any_text_filters = self.get_search_text_filter()
        search_resources = self.request.GET.get("searchResources", "dataset")

        data = {
            search_resources: resources or [],
            "searchFilter": {
                "origUrl": "&".join([f"{key}={value}" for key, value in request.GET.items()]),
                "searchText": {
                    "title": "Suchbegriff(e):",
                    "delLink": "&".join([f"{key}=*" if key == "searchText" else f"{key}={value}" for key, value in request.GET.items()]),  # nopep8
                    "item": [{
                        "title": f,
                        "delLink": "&".join([f"{key}={','.join([k for k in any_text_filters if f != k]) or '*'}" if key == "searchText" else f"{key}={value}" for key, value in request.GET.items()]),
                    } for f in any_text_filters
                    ]
                },
                "searchResources": {
                    "title": "Art der Ressource:",
                    "delLink": del_link_search_resources,
                    "item": [
                        {
                            "title": search_resources,  # TODO
                            "delLink": del_link_search_resources,
                        }
                    ]
                }
            }
        }

        if self.request.GET.get("searchBbox", None):
            data["searchFilter"].update(
                {
                    "searchBbox": {
                        "title": "Räumliche Einschränkung:",
                        "delLink": "searchText=&catalogueId=6&searchResources=dataset&target=webclient&searchTypeBbox=inside",
                        "item": [
                            {
                                # TODO
                                "title": "inside 7.18159618172,50.2823608933,7.26750846535,50.3502633407",
                                "delLink": "searchText=&catalogueId=6&searchResources=dataset&target=webclient&searchTypeBbox=inside"
                            }
                        ]
                    }
                }
            )

        return JsonResponse(data)
