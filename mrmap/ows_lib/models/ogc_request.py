from typing import List

from django.contrib.gis.geos import GEOSGeometry
from django.http import HttpRequest
from eulxml.xmlmap import XmlObject, load_xmlobject_from_string
from ows_lib.client.exceptions import MissingBboxParam, MissingServiceParam
from ows_lib.client.utils import (construct_polygon_from_bbox_query_param,
                                  get_requested_feature_types,
                                  get_requested_layers)
from ows_lib.xml_mapper.xml_requests.utils import PostRequest
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import (GetFeatureRequest,
                                                             Query)
from registry.enums.service import OGCOperationEnum


class OGCRequest:

    def __init__(self, request: HttpRequest) -> None:
        self.request: HttpRequest = request
        self._GET_LOWER: dict = {}
        self._ogc_query_params: dict = {}
        self._bbox: GEOSGeometry = None
        self._requested_entities: list[str] = []
        self._xml_request: XmlObject = None

        if request.method == "GET":
            self.operation: str = self.GET_LOWER.get("request", "")
            self.service_version: str = self.GET_LOWER.get("version", "")
            self.service_type: str = self.GET_LOWER.get("service", "")
        elif request.method == "POST":
            post_request: PostRequest = load_xmlobject_from_string(
                string=request.body, xmlclass=PostRequest)

            self.operation: str = post_request.operation
            self.service_version: str = post_request.version
            self.service_type: str = post_request.service_type

    @property
    def requested_entities(self) -> list[str]:
        if not self._requested_entities:
            if self.is_wms:
                self._requested_entities.extend(
                    get_requested_layers(params=self.GET_LOWER))
            else:
                if self.is_get_feature_request:
                    if self.is_get:
                        self._requested_entities.extend(
                            get_requested_feature_types(params=self.GET_LOWER))
                    elif self.is_post:
                        self._requested_entities.extend(
                            self.xml_request.requested_feature_types)
        return self._requested_entities

    @property
    def is_wms(self) -> bool:
        return self.service_type.lower() == 'wms'

    @property
    def is_wfs(self) -> bool:
        return self.service_type.lower() == 'wfs'

    @property
    def is_post(self) -> bool:
        return self.request.method == "POST"

    @property
    def is_get(self) -> bool:
        return self.request.method == "GET"

    @property
    def is_get_capabilities_request(self) -> bool:
        return self.operation.lower() == OGCOperationEnum.GET_CAPABILITIES.value.lower()

    @property
    def is_get_map_request(self) -> bool:
        return self.operation.lower() == OGCOperationEnum.GET_MAP.value.lower()

    @property
    def is_get_feature_info_request(self) -> bool:
        return self.operation.lower() == OGCOperationEnum.GET_FEATURE_INFO.value.lower()

    @property
    def is_get_feature_request(self) -> bool:
        return self.operation.lower() == OGCOperationEnum.GET_FEATURE.value.lower()

    @property
    def is_transaction_request(self) -> bool:
        return self.operation.lower() == OGCOperationEnum.TRANSACTION.value.lower()

    @property
    def bbox(self) -> GEOSGeometry:
        if not self._bbox:
            try:
                self._bbox = construct_polygon_from_bbox_query_param(
                    get_dict=self.GET_LOWER)
            except (MissingBboxParam, MissingServiceParam):
                # only to avoid error while handling sql in service property
                self._bbox = GEOSGeometry("POLYGON EMPTY")
        return self._bbox

    @property
    def GET_LOWER(self) -> dict:
        return {k.lower(): v for k, v in self.request.GET.items()} if not self._GET_LOWER else self._GET_LOWER

    @property
    def ogc_query_params(self) -> dict:
        """ Parses the GET parameters into all member variables, which can be found in a ogc request.
        Returns:
            the for this version converted get_dict
        """
        if not self._ogc_query_params:
            query_keys = ["SERVICE", "REQUEST", "LAYERS", "BBOX", "VERSION", "FORMAT",
                          "OUTPUTFORMAT", "SRS", "CRS", "SRSNAME", "WIDTH", "HEIGHT",
                          "TRANSPARENT", "EXCEPTIONS", "BGCOLOR", "TIME", "ELEVATION",
                          "QUERY_LAYERS", "INFO_FORMAT", "FEATURE_COUNT", "I", "J"]
            self._ogc_query_params = {key: self.GET_LOWER.get(
                key, self.GET_LOWER.get(key.lower())) for key in query_keys}

        return self._ogc_query_params

    @property
    def xml_request(self) -> XmlObject:
        if not self._xml_request:
            # FIXME: depending on version, different xml mapper are needed...
            if self.is_post:
                if self.is_get_feature_request:

                    self._xml_request: GetFeatureRequest = load_xmlobject_from_string(
                        string=self.request.body, xmlclass=GetFeatureRequest)
            elif self.is_get:
                # we construct a xml get feature request to post it with a filter
                queries: List[Query] = []
                for feature_type in self.requested_entities:
                    query: Query = Query()
                    query.type_names = feature_type
                    queries.append(query)
                self._xml_request: GetFeatureRequest = GetFeatureRequest()
                self._xml_request.queries = queries
        return self._xml_request
