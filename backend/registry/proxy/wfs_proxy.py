
from typing import List

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from eulxml.xmlmap import load_xmlobject_from_string
from ows_lib.client.utils import get_requested_feature_types
from ows_lib.client.wfs.mixins import \
    WebFeatureServiceMixin as WebFeatureServiceClient
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import (GetFeatureRequest,
                                                             Query)
from registry.enums.service import OGCOperationEnum
from registry.models.service import WebFeatureService
from registry.proxy.mixins import OgcServiceProxyView


@method_decorator(csrf_exempt, name="dispatch")
class WebFeatureServiceProxy(OgcServiceProxyView):
    """Security proxy facade to secure registered services spatial by there operations and for sets of users.
    :attr service:  :class:`registry.models.service.Service` the requested service which was found by the pk.
    :attr remote_service: :class:`registry.ows_client.request_builder.WebService` the request builder to get
                          prepared :class:`requests.models.Request` objects with the correct uri and query params.
    :attr query_parameters: all query parameters in lower case.
    :attr access_denied_img: if sub elements are not accessible for the user, this PIL.Image object represents an
                             overlay with information about the resources, which can not be accessed
    :attr bbox: :class:`django.contrib.gis.geos.polygon.Polygon` the parsed bbox from query params.
    """
    service_cls = WebFeatureService

    @property
    def service(self) -> WebFeatureService:
        return super().service

    @property
    def remote_service(self) -> WebFeatureServiceClient:
        return super().remote_service

    @property
    def is_get_feature_request(self) -> bool:
        return self.request.query_parameters.get("request").lower() == OGCOperationEnum.GET_FEATURE.value.lower()

    def analyze_request(self):
        super().analyze_request()
        if self.is_get_feature_request:
            if self.request.method == "POST":
                get_feature_request: GetFeatureRequest = load_xmlobject_from_string(
                    string=self.request.body, xmlclass=GetFeatureRequest)
            elif self.request.method == "GET":
                # we construct a xml get feature request to post it with a filter
                queries: List[Query] = []
                for feature_type in get_requested_feature_types(
                        self.request.query_parameters):
                    query: Query = Query()
                    query.type_names = feature_type
                    queries.append(query)
                get_feature_request: GetFeatureRequest = GetFeatureRequest()
                get_feature_request.queries = queries

            self.request.get_feature_request = get_feature_request
            self.request.requested_entities = get_requested_feature_types(
                params=self.request.query_parameters)
            self.request.requested_entities.extend(
                get_feature_request.requested_feature_types)

            print(self.request.requested_entities)

    def secure_request(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        if (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.GET_FEATURE.value.lower()
        ):
            return self.handle_secured_get_feature()
        elif (
            self.request.query_parameters.get("request").lower()
            == OGCOperationEnum.TRANSACTION.value.lower()
        ):
            return self.handle_secured_transaction()

    def handle_secured_get_feature(self):
        self.request.get_feature_request.secure_spatial(
            value_reference=self.service.geometry_property_name,
            polygon=self.service.allowed_area_union
        )
        response = self.remote_service.send_request(
            self.remote_service.prepare_get_feature_request(get_feature_request=self.request.get_feature_request))

        return self.return_http_response(response=response)

    def handle_secured_transaction(self):
        #  Transaction: Transaction operations does not contains area of interest.
        #   F. E. the transaction request
        #   could contain an update for a not spatial value of some column. Then the request has no spatial limitation. Insert operation --> same problem
        # TODO: cause it is very complex to differ all the cases (UPDATE, INSERT, DELETE) in a transaction, we will do this in future.
        #       We could secure the transaction on table column level.
        #       * secure on feature level per permission (update, delete)
        #       * secure on table level for insert permission
        raise NotImplementedError()
