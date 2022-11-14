from ows_lib.client.wms.mixins import WebMapServiceMixin


class WebMapService(WebMapServiceMixin):

    crs_qp = "CRS"
    get_map_operation_name = "GetMap"
    get_feature_info_operation_name = "GetFeatureInfo"
