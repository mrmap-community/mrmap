

import json

from axis_order_cache.utils import adjust_axis_order
from django.contrib.gis.geos import GEOSGeometry
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
        if not self._service:
            self._service = super().service

            # The security manager of server model does provide security_info_per_feature_type attribute as json encoded object.
            # To use the information in common django/python way, we convert the given json object to dict/geos objects.
            _security_info_per_feature_type = []

            for security_info in self._service.security_info_per_feature_type:
                polygon_dict = security_info.get("allowed_area_union")
                geometry = GEOSGeometry(json.dumps(polygon_dict))
                # The given geometry object has always the x/y representation for there coordinates
                # from geoserver docs: https://docs.geoserver.org/stable/en/user/services/wfs/axis_order.html
                # WFS 1.0.0: Provides geographic coordinates in east/north and may not be trusted to respect the EPSG definition axis order.
                # So for WFS 1.0.0 we don't need anything to do. It is interpreted as x/y
                if self.ogc_request.service_version != "1.0.0":
                    # All other versions of wfs uses the epsg definition of axis ordering.
                    # WFS 1.1.0: Respects the axis order defined by the EPSG definition.
                    # WFS 2.0.0: Respects the axis order defined by the EPSG definition.
                    # So we need to request the epsg registry and adjust the axis order if needed.
                    geometry = adjust_axis_order(geometry)
                _security_info_per_feature_type.append(
                    {
                        "type_name": security_info.get("type_name"),
                        "geometry_property_name": security_info.get("geometry_property_name"),
                        "allowed_area_union": geometry
                    }
                )

            self._service.security_info_per_feature_type = _security_info_per_feature_type

        return self._service

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
        self.ogc_request.xml_request.secure_spatial(
            feature_types=self.service.security_info_per_feature_type)

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
