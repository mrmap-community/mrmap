"""
Author: Jan Suleiman
Organization: terrestris GmbH & Co. KG, Bonn, Germany
Contact: suleiman@terrestris.de
Created on: 26.02.2020

"""
from monitoring.helper.urlHelper import UrlHelper
from resourceNew.enums.service import OGCServiceEnum, OGCOperationEnum, OGCServiceVersionEnum
from resourceNew.models import Service, Layer


class WmsHelper:

    def __init__(self, service: Service):
        self.service = service
        self.parent_service = service
        #self.parent_service = service.parent_service if service.metadata.is_layer_metadata else service

        # # Prefetch useful attributes for requests
        # self.layer = Layer.objects.get(
        #     metadata=service.metadata
        # ) if self.service.metadata.is_layer_metadata else Layer.objects.get(
        #     parent_service=self.service,
        #     parent=None
        # )
        self.layer = service.root_layer
        self.crs_srs_identifier = 'CRS' if self.service.service_type.version == OGCServiceVersionEnum.V_1_3_0.value else 'SRS'
        self.bbox = self.layer.bbox_lat_lon if self.layer.bbox_lat_lon.area > 0 else self.parent_service.metadata.find_max_bounding_box()

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
        # todo: filter url not empty
        uri = self.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_STYLES.value,
            method="Get"
        ).first()
        if uri is None or uri.url is None:
            return
        uri = uri.url
        service_version = OGCServiceVersionEnum.V_1_1_1.value
        service_type = OGCServiceEnum.WMS.value
        layers = self.layer.identifier
        request_type = OGCOperationEnum.GET_STYLES.value

        queries = [
            ('SERVICE', service_type),
            ('REQUEST', request_type),
            ('VERSION', service_version),
            ('LAYERS', layers)
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_legend_graphic_url(self):
        """ Creates the url for the wms getLegendGraphic request.

        Returns:
            str: URL for getLegendGraphic request.
        """
        operation_url = self.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_LEGEND_GRAPHIC.value,
            method="Get"
        ).first()
        if operation_url is None:
            return
        request_type = OGCOperationEnum.GET_LEGEND_GRAPHIC.value
        layer = self.layer.identifier

        service_format = operation_url.mime_types.filter(
            mime_type__istartswith='image/'
        ).exclude(
            mime_type__icontains='svg'
        ).first()

        if not service_format:
            # no formats are supported... return None
            return

        version = self.service.service_type.version
        service_type = self.service.service_type.name

        queries = [
            ('REQUEST', request_type),
            ('LAYER', layer),
            ('FORMAT', service_format),
            ('SERVICE', service_type),
            ('VERSION', version),
        ]
        url = UrlHelper.build(operation_url.url, queries)
        return url

    def get_describe_layer_url(self):
        """ Creates the url for the wms DescribeLayer request.

        Returns:
            str: URL for DescribeLayer request.
        """
        uri = self.service.operation_urls.filter(
            operation=OGCOperationEnum.DESCRIBE_LAYER.value,
            method="Get"
        ).first()
        if uri is None:
            return
        uri = uri.url
        request_type = OGCOperationEnum.DESCRIBE_LAYER.value
        # make sure that version is describeLayer specific version 1.1.1 and not wms version 1.3.0
        service_version = OGCServiceVersionEnum.V_1_1_1.value
        service_type = OGCServiceEnum.WMS.value

        layers = self.layer.identifier

        queries = [
            ('REQUEST', request_type),
            ('VERSION', service_version),
            ('SERVICE', service_type),
            ('LAYERS', layers),
            ('WIDTH', 1),
            ('HEIGHT', 1),
        ]
        url = UrlHelper.build(uri, queries)
        return url

    def get_get_feature_info_url(self):
        """ Creates the url for the wms getFeatureInfo request.

        Returns:
            str: URL for getFeatureInfo request.
        """
        uri = self.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_FEATURE_INFO.value,
            method="Get"
        ).first()
        if uri is None or not self.layer.is_queryable:
            return
        uri = uri.url
        request_type = OGCOperationEnum.GET_FEATURE_INFO.value
        service_version = self.service.service_type.version
        service_type = OGCServiceEnum.WMS.value

        layers = self.layer.identifier
        crs = f'EPSG:{self.bbox.crs.srid}'
        bbox = ','.join(map(str, self.bbox.extent))
        styles = ''
        width = 1
        height = 1
        query_layers = layers
        x = 0
        y = 0

        queries = [
            ('REQUEST', request_type),
            ('VERSION', service_version),
            ('SERVICE', service_type),
            ('LAYERS', layers),
            (self.crs_srs_identifier, crs),
            ('BBOX', bbox),
            ('STYLES', styles),
            ('WIDTH', width),
            ('HEIGHT', height),
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
        operation_url = self.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_MAP.value,
            method="Get"
        ).first()
        if operation_url is None:
            return
        # Fetch request parameters
        request_type = OGCOperationEnum.GET_MAP.value
        service_version = self.service.service_type.version
        service_type = OGCServiceEnum.WMS.value

        # Get bbox value for request
        layers = self.layer.identifier
        srs = f'EPSG:{self.bbox.crs.srid}'
        bbox = ','.join(map(str, self.bbox.extent))
        styles = ''
        width = 1
        height = 1

        service_format = operation_url.mime_types.filter(
            mime_type__istartswith='image/'
        ).exclude(
            mime_type__icontains='svg'
        ).first()

        queries = [
            ('REQUEST', request_type),
            ('VERSION', service_version),
            ('SERVICE', service_type),
            ('LAYERS', layers),
            (self.crs_srs_identifier, srs),
            ('BBOX', bbox),
            ('STYLES', styles),
            ('WIDTH', width),
            ('HEIGHT', height),
            ('FORMAT', service_format)
        ]
        url = UrlHelper.build(operation_url.url, queries)
        return url

    def get_get_capabilities_url(self):
        """ Creates the url for the wms getCapabilities request.

        Returns:
            str: URL for getCapabilities request.
        """
        uri = self.service.operation_urls.filter(
            operation=OGCOperationEnum.GET_CAPABILITIES.value,
            method="Get"
        )
        uri = uri.first()
        if uri is None:
            # Return None if uri is not defined so that service check fails
            return
        uri = uri.url
        request_type = OGCOperationEnum.GET_CAPABILITIES.value
        service_version = self.service.service_type.version
        service_type = OGCServiceEnum.WMS.value

        queries = [('REQUEST', request_type), ('VERSION', service_version), ('SERVICE', service_type)]
        url = UrlHelper.build(uri, queries)
        return url
