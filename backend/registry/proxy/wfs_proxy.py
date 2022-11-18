
from django.http.response import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from eulxml import xmlmap
from eulxml.xmlmap import load_xmlobject_from_string
from ows_lib.client.wfs.mixins import \
    WebFeatureServiceMixin as WebFeatureServiceClient
from ows_lib.xml_mapper.xml_requests.wfs.wfs200 import GetFeatureRequest
from registry.enums.service import OGCOperationEnum
from registry.models.service import WebFeatureService
from registry.proxy.mixins import OgcServiceProxyView
from registry.proxy.ogc_exceptions import ForbiddenException
from registry.xmlmapper.ogc.feature_collection import FeatureCollection


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

    service: WebFeatureService = None
    remote_service: WebFeatureServiceClient = None

    def get_service(self):
        try:
            # FIXME: the is currently no security manager...
            self.service = WebFeatureService.security.get_with_security_info(
                pk=self.kwargs.get("pk"), request=self.request
            )
        except WebFeatureService.DoesNotExist:
            raise Http404

        """Return the GetFeatureInfo response if the bbox is covered by any allowed area or the response features are
        contained in any allowed area.
        IF not we response with a owsExceptionReport in xml format.
        .. note:: excerpt from ogc specs
            **ogc wms 1.3.0**: The server shall return a response according to the requested INFO_FORMAT if the
            request is valid, or issue a service  exception  otherwise. The nature of the response is at the
            discretion of the service provider, but it shall pertain to the feature(s) nearest to (I,J).
            (see section 7.4.4)
        :return: the GetFeatureInfo response
        :rtype: :class:`request.models.Response` or dict if the request is not allowed.
        """
        if self.service.is_spatial_secured_and_covers:
            return self.return_http_response(response=self.get_remote_response())
        else:
            try:
                request = self.remote_service.construct_request(
                    query_params=self.request.GET
                )
                if request.params[self.remote_service.INFO_FORMAT_QP] != "text/xml":
                    (
                        xml_response,
                        requested_response,
                    ) = self.handle_get_feature_info_with_multithreading()
                else:
                    xml_response = self.get_remote_response(request=request)
                    requested_response = xml_response
                feature_collection = xmlmap.load_xmlobject_from_string(
                    xml_response.content, xmlclass=FeatureCollection
                )
                # FIXME: depends on xml wms version not on the registered service version
                axis_order_correction = (
                    True if self.service.major_service_version >= 2 else False
                )
                polygon = feature_collection.bounded_by.get_geometry(
                    axis_order_correction
                )
                if self.service.allowed_area_union.contains(polygon.convex_hull):
                    return self.return_http_response(response=requested_response)
            except Exception:
                pass
        return ForbiddenException()

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
        if self.request.method == "POST":
            get_feature_request: GetFeatureRequest = load_xmlobject_from_string(
                string=self.request.body, xmlclass=GetFeatureRequest)
            value_reference = self.get_geometry_based_value_reference()

            get_feature_request.secure_spatial(
                value_reference=value_reference,
                polygon=self.service.allowed_area_union
            )

            response = self.remote_service.send_request(
                self.remote_service.prepare_feature_type_request(get_feature_request=get_feature_request))

            self.return_http_response(response=response)
        else:
            raise NotImplementedError()

    def get_geometry_based_value_reference(self):
        # TODO: could be done by the security manager, which has an annotation with the first founded geometry prop name
        raise NotImplementedError()

    def handle_secured_transaction(self):
        #  Transaction: Transaction operations does not contains area of interest.
        #   F. E. the transaction request
        #   could contain an update for a not spatial value of some column. Then the request has no spatial limitation. Insert operation --> same problem
        # TODO: cause it is very complex to differ all the cases (UPDATE, INSERT, DELETE) in a transaction, we will do this in future.
        #       We could secure the transaction on table column level.
        #       * secure on feature level per permission (update, delete)
        #       * secure on table level for insert permission
        raise NotImplementedError()
