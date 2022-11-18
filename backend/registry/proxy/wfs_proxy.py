
from django.contrib.gis.geos import GEOSGeometry
from django.http.response import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from eulxml import xmlmap
from ows_lib.client.exceptions import MissingBboxParam, MissingServiceParam
from ows_lib.client.utils import construct_polygon_from_bbox_query_param
from ows_lib.client.wfs.mixins import \
    WebFeatureServiceMixin as WebFeatureServiceClient
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

    def get_bbox_from_request(self):
        # TODO: get the requested area of interest by given request
        #  GetFeature:
        #  Transaction
        raise NotImplementedError()
        try:
            self.request.bbox = construct_polygon_from_bbox_query_param(
                get_dict=self.request.query_parameters
            )
        except (MissingBboxParam, MissingServiceParam):
            # only to avoid error while handling sql in get_service()
            self.request.bbox = GEOSGeometry("POLYGON EMPTY")

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
        raise NotImplementedError()

    def handle_secured_transaction(self):
        raise NotImplementedError()
