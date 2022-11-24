from django.contrib.gis.geos import GEOSGeometry
from django.http import HttpRequest
from eulxml.xmlmap import load_xmlobject_from_string
from ows_lib.client.exceptions import MissingBboxParam, MissingServiceParam
from ows_lib.client.utils import construct_polygon_from_bbox_query_param
from ows_lib.xml_mapper.xml_requests.utils import PostRequest
from registry.enums.service import OGCOperationEnum


class OGCRequest(object):

    _GET_LOWER = None
    request: HttpRequest = None
    operation: str = ""
    service_version: str = ""
    service_type: str = ""
    bbox = None

    def __init__(self, request: HttpRequest) -> None:
        self.request = request

        if request.method == "GET":
            # TODO: analyze GET params
            pass
        elif request.method == "POST":
            post_request: PostRequest = load_xmlobject_from_string(
                string=request.body, xml_class=PostRequest)

            self.operation = post_request.operation
            self.service_version = post_request.version
            self.service_type = post_request.service_type

    def is_post(self):
        return self.request.method == "POST"

    def is_get(self):
        return self.request.method == "GET"

    def is_get_capabilities_request(self):
        return self.operation == OGCOperationEnum.GET_CAPABILITIES.value.lower()

    def bbox(self):

        try:
            construct_polygon_from_bbox_query_param(
                get_dict=self.GET_LOWER)
        except (MissingBboxParam, MissingServiceParam):
            # only to avoid error while handling sql in service property
            self.request.bbox = GEOSGeometry("POLYGON EMPTY")

    @property
    def GET_LOWER(self):
        return {k.lower(): v for k, v in self.request.GET.items()} if not self._GET_LOWER else self._GET_LOWER
