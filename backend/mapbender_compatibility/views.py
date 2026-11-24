import datetime
import re
from typing import Any
from urllib import parse

from csw.queryables import (application_records, dataset_records,
                            service_records)
from django.db.models.query_utils import Q
from django.forms import ValidationError
from django.http import HttpResponse, JsonResponse
from django.http.request import HttpRequest as HttpRequest
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import View
from registry.expressions.search import client_search_query
from registry.helper.xml import parse_untrusted
from registry.mappers.factory import MDMetadataXmlMapper
from registry.models.service import CatalogueService as DBCatalogueService
from registry.ows_lib.xml.consts import NAMESPACE_LOOKUP

# One coordinate of a searchBbox: digits with at most one decimal point and an
# optional sign, with the whitespace a float() takes, and nothing else. A bbox
# is sent on by the remote CSW into a CQL BBOX() predicate, whose parser takes a
# bare number, so a value which is not one is dropped rather than forwarded.
BBOX_COORDINATE = re.compile(r"\s*[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s*")


def cql_literal(value: str) -> str:
    """The value of a CQL string literal, doubled inside its own quotes.

    The predicate is forwarded verbatim to the catalogue the client names with
    ``catalogueId``, and a single quote of the search word closed the literal it
    was interpolated into - everything behind it was parsed as CQL by the
    remote service, not as a word of the search (#1469).
    """
    return str(value).replace("'", "''")


def echoed_value(value: str) -> str:
    """A request parameter as the answer echoes it back to the client.

    The MapBender widget writes the search filter of the answer straight into
    its HTML, so an angle bracket of a parameter would open a tag there. Only
    the two characters which open markup are replaced: a real client sends them
    percent-encoded, so every request it makes is answered byte-identically,
    and the ``&`` of the echoed query string is the separator the widget itself
    parses.
    """
    return str(value).replace("<", "&lt;").replace(">", "&gt;")


def search_bbox_filter(search_bbox: str) -> str:
    """The BBOX predicate of a searchBbox, or "" when it names no bbox.

    Checked against the coordinates it names instead of interpolated, so
    whatever else the parameter carries never reaches the predicate. Accepted
    coordinates are rejoined as they were received (#1469).
    """
    coordinates = search_bbox.split(",")
    if len(coordinates) != 4 or any(
            not BBOX_COORDINATE.fullmatch(coord) for coord in coordinates):
        return ""
    return f"BBOX(the_geom, {search_bbox})"


# FUTURE: log the request on this view. HTTP_Referer, searchUrl, searchText, HTTP_USER_AGENT, catalogueId
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
        # FUTURE: implement , seperated search values
        search_text = self.request.GET.get("searchText", "*")
        if search_text == "*":
            search_text = ""
        return search_text.split(",")

    def build_cql_filter(self):
        any_text_filters = self.get_search_text_filter()

        search_resources = self.request.GET.get("searchResources", "dataset")

        cql_filter_expr = f"Type LIKE '{cql_literal(search_resources)}'"

        for any_text in any_text_filters:
            # the first_loop flag of the original implementation never
            # flipped, so every search text was ANDed - the FUTURE note
            # above owns the comma semantics
            cql_filter_expr += f" And AnyText LIKE '{cql_literal(any_text)}'"

        # example: &searchBbox=7.18159618172,50.2823608933,7.26750846535,50.3502633407
        search_bbox = self.request.GET.get("searchBbox")
        if search_bbox:
            # FUTURE: the_geom col name need to be checked by capabilitites of the remote csw to set the corret geometry col
            bbox_filter = search_bbox_filter(search_bbox)
            if bbox_filter == "":
                return cql_filter_expr
            if cql_filter_expr != "":
                cql_filter_expr += f"AND {bbox_filter}"
            else:
                cql_filter_expr += bbox_filter

        # FUTURE: implement inside or outside bbox as cql filter
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

            total_records, entries = self._remote_search_records(
                client, gmd_metadata_response)
            if total_records is not None:
                srv.extend(entries)
                content["md"]["nresults"] = total_records
        except DBCatalogueService.DoesNotExist:
            # FUTURE: response with error code
            pass
        except ValidationError:
            pass

        return content

    def _remote_search_records(self, client, response):
        """The number of matches and the mapbender rows of an answered
        GetRecords; None answers a catalogue which did not answer well."""
        if not (200 <= response.status_code < 400):
            return None, []

        xml = parse_untrusted(response.content)

        total_records = int(xml.xpath("/csw:GetRecordsResponse/csw:SearchResults/@numberOfRecordsMatched", namespaces={
            "csw": NAMESPACE_LOOKUP["csw_2_0_2"]
        })[0] or 0)

        entries = []
        mappers = MDMetadataXmlMapper.from_xml(
            response.content)
        for mapper in mappers:
            data = mapper.xml_to_django()
            for md_metadata in data:
                entries.append(self._remote_search_entry(
                    client, md_metadata))
        return total_records, entries

    @staticmethod
    def _remote_search_entry(client, md_metadata):
        get_record_by_id_url = client.get_record_by_id_request(
            id=md_metadata.file_identifier)

        return {
            "id": md_metadata.file_identifier,
            "date": md_metadata.date_stamp,
            "datasetId": md_metadata.file_identifier,
            "previewUrl": "TODO",
            "respOrg": md_metadata.metadata_contact.name if md_metadata.metadata_contact else None,
            "bbox": ",".join([str(coord) for coord in md_metadata.bounding_geometry.extent]) if md_metadata.bounding_geometry else None,
            "title": md_metadata.title,
            "abstract": md_metadata.abstract,
            "mdLink": get_record_by_id_url.url,
            "htmlLink": f'https://www.geoportal.rlp.de/mapbender/php/mod_exportIso19139.php?url={parse.quote_plus(get_record_by_id_url.url)}&resolveCoupledResources=true',
        }

    def local_search(self):
        search_pages = int(self.request.GET.get("searchPages", 1) or 1)
        max_records = int(self.request.GET.get("maxResults", 10) or 10)
        start_position = search_pages * max_records - max_records

        heap_count = start_position + max_records

        records = self._local_search_resources()

        result = []
        total_records = 0
        if records is not None:
            total_records, result = self._local_search_page(
                records, start_position, heap_count)

        srv = [self._local_search_entry(record) for record in result]
        return {
            "md": {
                "nresults": total_records,
                "p": search_pages,
                "rpp": max_records,
                "genTime": 0,
            },
            "srv": srv
        }

    def _local_search_resources(self):
        """The record source of the requested hierarchy level; None is the
        level this search cannot serve."""
        search_resources = self.request.GET.get("searchResources", "dataset")
        if search_resources == "dataset":
            return dataset_records()
        elif search_resources == "service":
            return service_records()
        elif search_resources == "application":
            return application_records()
        # FUTURE: implement other hierachylevels also
        # return empty result for all other hierachylevels
        return None

    def _local_search_page(self, records, start_position, heap_count):
        """The searched page of the local records and the size of the
        result set the client is told about."""
        # the search words of the client are words of the vector of a record, and a
        # record is found by a word of its title, its abstract or one of its
        # keywords. Without a search word the client browses, which is not a search
        # that matches nothing
        search_words = Q()
        for any_text in self.get_search_text_filter():
            if any_text.strip():
                search_words |= Q(
                    search_vector=client_search_query(any_text))
        if search_words:
            records = records.filter(search_words)

        total_records = records.count()
        result = records.select_related(
            "metadata_contact")[start_position: heap_count]
        return total_records, result

    @staticmethod
    def _local_search_entry(record):
        # FUTURE: #527
        return {
            "id": record.pk,
            "date": record.date_stamp,
            "datasetId": "TODO",
            "previewUrl": "TODO",
            "respOrg": record.metadata_contact.name if record.metadata_contact else None,
            "bbox": ",".join([str(coord) for coord in record.bounding_geometry.extent]) if record.bounding_geometry else None,  # nopep8
            "title": record.title,
            "abstract": record.abstract,
            "mdLink": "TODO",
            "htmlLink": "TODO",
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

        # every parameter of the request is echoed back into the search filter
        # below, and a MapBender client renders that filter as HTML - the echo
        # is markup-free, a client which percent-encodes its own parameters
        # cannot tell the difference (#1469)
        echoed_querystring = "&".join(
            [f"{key}={echoed_value(value)}" for key, value in request.GET.items()])

        resources["md"]["genTime"] = (
            datetime.datetime.now() - self.start_time).total_seconds()
        any_text_filters = self.get_search_text_filter()
        search_resources = self.request.GET.get("searchResources", "dataset")

        data = {
            echoed_value(search_resources): resources or [],
            "searchFilter": {
                "origUrl": echoed_querystring,
                "searchText": {
                    "title": "Suchbegriff(e):",
                    "delLink": "&".join([f"{key}=*" if key == "searchText" else f"{key}={echoed_value(value)}" for key, value in request.GET.items()]),  # nopep8
                    "item": [{
                        "title": echoed_value(f),
                        "delLink": "&".join([f"{key}={echoed_value(','.join([k for k in any_text_filters if f != k]) or '*')}" if key == "searchText" else f"{key}={echoed_value(value)}" for key, value in request.GET.items()]),  # nopep8
                    } for f in any_text_filters
                    ]
                },
                "searchResources": {
                    "title": "Art der Ressource:",
                    "delLink": echoed_querystring,
                    "item": [
                        {
                            "title": echoed_value(search_resources),
                            "delLink": echoed_querystring,
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
                                "title": "inside 7.18159618172,50.2823608933,7.26750846535,50.3502633407",
                                "delLink": "searchText=&catalogueId=6&searchResources=dataset&target=webclient&searchTypeBbox=inside"
                            }
                        ]
                    }
                }
            )

        return JsonResponse(data)
