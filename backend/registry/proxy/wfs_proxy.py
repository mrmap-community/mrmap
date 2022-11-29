

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from ows_lib.client.wfs.mixins import \
    WebFeatureServiceMixin as WebFeatureServiceClient
from registry.models.service import WebFeatureService
from registry.proxy.mixins import OgcServiceProxyView


@method_decorator(csrf_exempt, name="dispatch")
class WebFeatureServiceProxy(OgcServiceProxyView):
    """Security proxy facade to secure registered services spatial by there operations and for sets of users.
    :attr service:  :class:`registry.models.service.Service` the requested service which was found by the pk.
    :attr remote_service: :class:`registry.ows_client.request_builder.WebService` the request builder to get
                          prepared :class:`requests.models.Request` objects with the correct uri and query params.
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

    def secure_request(self):
        """Handler to decide which subroutine for the given request param shall run.
        :return: the correct handler function for the given request param.
        :rtype: function
        """
        if self.ogc_request.is_get_feature_request:
            return self.handle_secured_get_feature()
        elif self.ogc_request.is_transaction_request:
            return self.handle_secured_transaction()

    def handle_secured_get_feature(self):

        print("props: ", self.service.geometry_property_names)
        print("area: ", self.service.allowed_area_union)
        self.ogc_request.xml_request.secure_spatial(
            value_reference=self.service.geometry_property_names,
            polygon=self.service.allowed_area_union
        )

        print("secured xml: ", self.ogc_request.xml_request.serializeDocument())

        response = self.remote_service.send_request(
            self.remote_service.prepare_get_feature_request(get_feature_request=self.ogc_request.xml_request))

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
