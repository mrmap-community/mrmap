from service.models import Service
from service.helper.enums import OGCOperationEnum, OGCServiceVersionEnum, OGCServiceEnum
from monitoring.helper.urlHelper import UrlHelper
from django.core.exceptions import ObjectDoesNotExist


class WmsHelper:

    def __init__(self, service: Service):
        self.service = service
        self.get_capabilities_url = self.get_get_capabilities_url()
        self.get_styles_url = None
        self.get_legend_graphic_url = None
        self.describe_layer_url = None
        self.get_feature_info_url = None
        self.get_map_url = None

    def set_operation_urls(self):
        """ Sets the urls for all operations except GetCapabilities.

        Returns:
            nothing
        """
        self.get_styles_url = self.get_get_styles_url()
        self.get_legend_graphic_url = self.get_get_legend_graphic_url()
        self.describe_layer_url = self.get_describe_layer_url()
        self.get_feature_info_url = self.get_get_feature_info_url()
        self.get_map_url = self.get_get_map_url()

    def get_get_styles_url(self):
        """ Creates the url for the wms getStyles request.

        Returns:
            str: URL for getStyles request.
        """
        uri = self.service.get_styles_uri_GET
        if uri is None:
            return
        service_version = OGCServiceVersionEnum.V_1_1_1.value
        service_type = OGCServiceEnum.WMS.value
        try:
            layers = self.service.layer.identifier
        except ObjectDoesNotExist:
            layers = ''
        request_type = OGCOperationEnum.GET_STYLES.value

        queries = [
            ('SERVICE', service_type), ('REQUEST', request_type), ('VERSION', service_version), ('LAYERS', layers)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_legend_graphic_url(self):
        """ Creates the url for the wms getLegendGraphic request.

        Returns:
            str: URL for getLegendGraphic request.
        """
        uri = self.service.get_legend_graphic_uri_GET
        if uri is None:
            return
        request_type = OGCOperationEnum.GET_LEGEND_GRAPHIC.value
        try:
            layer = self.service.layer.identifier
        except ObjectDoesNotExist:
            layer = ''
        service_format = str(self.service.formats.all()[0])
        if 'image/png' in [str(f) for f in self.service.formats.all()]:
            service_format = 'image/png'

        queries = [
            ('REQUEST', request_type), ('LAYER', layer), ('FORMAT', service_format)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_describe_layer_url(self):
        """ Creates the url for the wms DescribeLayer request.

        Returns:
            str: URL for DescribeLayer request.
        """
        uri = self.service.describe_layer_uri_GET
        if uri is None:
            return
        request_type = OGCOperationEnum.DESCRIBE_LAYER.value
        # make sure that version is describeLayer specific version 1.1.1 and not wms version 1.3.0
        service_version = OGCServiceVersionEnum.V_1_1_1.value
        service_type = OGCServiceEnum.WMS.value
        try:
            layers = self.service.layer.identifier
        except ObjectDoesNotExist:
            layers = ''
        queries = [
            ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type), ('LAYERS', layers)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_feature_info_url(self):
        """ Creates the url for the wms getFeatureInfo request.

        Returns:
            str: URL for getFeatureInfo request.
        """
        uri = self.service.get_feature_info_uri_GET
        if uri is None:
            return
        request_type = OGCOperationEnum.GET_FEATURE_INFO.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WMS.value
        try:
            layers = self.service.layer.identifier
            crs = f'EPSG:{self.service.layer.bbox_lat_lon.crs.srid}'
            bbox = ','.join(map(str, self.service.layer.bbox_lat_lon.extent))
        except ObjectDoesNotExist:
            layers = ''
            crs = ''
            bbox = ''
        styles = ''
        width = 1
        height = 1
        query_layers = layers
        x = 0
        y = 0

        queries = [
            ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type), ('LAYERS', layers),
            ('CRS', crs), ('BBOX', bbox), ('STYLES', styles), ('WIDTH', width), ('HEIGHT', height),
            ('QUERY_LAYERS', query_layers)
        ]
        if service_version.lower() == OGCServiceVersionEnum.V_1_3_0.value.lower():
            queries = queries + [('I', x), ('J', y)]
        else:
            queries = queries + [('X', x), ('Y', y)]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_map_url(self):
        """ Creates the url for the wms getMap request.

        Returns:
            str: URL for getMap request.
        """
        uri = self.service.get_map_uri_GET
        if uri is None:
            return
        request_type = OGCOperationEnum.GET_MAP.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WMS.value
        try:
            layers = self.service.layer.identifier
            crs = f'EPSG:{self.service.layer.bbox_lat_lon.crs.srid}'
            bbox = ','.join(map(str, self.service.layer.bbox_lat_lon.extent))
        except ObjectDoesNotExist:
            layers = ''
            crs = ''
            bbox = ''
        styles = ''
        width = 1
        height = 1
        service_format = str(self.service.formats.all()[0])
        if 'image/png' in [str(f) for f in self.service.formats.all()]:
            service_format = 'image/png'

        queries = [
            ('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type), ('LAYERS', layers),
            ('CRS', crs), ('BBOX', bbox), ('STYLES', styles), ('WIDTH', width), ('HEIGHT', height),
            ('FORMAT', service_format)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_capabilities_url(self):
        """ Creates the url for the wms getCapabilities request.

        Returns:
            str: URL for getCapabilities request.
        """
        uri = self.service.get_capabilities_uri_GET
        if uri is None:
            # Return None if uri is not defined so that service check fails
            return
        request_type = OGCOperationEnum.GET_CAPABILITIES.value
        service_version = self.service.servicetype.version
        service_type = OGCServiceEnum.WMS.value

        queries = [('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type)]
        url = UrlHelper.build(uri, queries)
        return url
