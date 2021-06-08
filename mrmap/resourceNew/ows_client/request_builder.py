from abc import ABC
from requests.models import PreparedRequest


class WebService(ABC):
    REQUEST_QP = "REQUEST"
    SERVICE_QP = "SERVICE"
    VERSION_QP = "VERSION"
    GET_CAPABILITIES_QV = "GetCapabilities"

    def __init__(self, base_url: str, service_type: str, version: str, *args, **kwargs):
        self.base_url = base_url.split("?", 1)[0]
        self.service_type = service_type
        self.version = version
        version_split = version.split(".")
        if len(version_split) != 3:
            raise ValueError("the given version is not in sem version format like x.y.z")
        self.major_version = int(version_split[0])
        self.minor_version = int(version_split[1])
        self.path_version = int(version_split[2])

        super().__init__(*args, **kwargs)

    def get_default_query_params(self):
        return {self.VERSION_QP: self.version,
                self.SERVICE_QP: self.service_type}

    def get_get_capabilities_request(self):
        req = PreparedRequest()
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_CAPABILITIES_QV})
        req.prepare_url(self.base_url, query_params)
        return req


class WmsService(WebService):
    LAYERS_QP = "LAYERS"
    STYLES_QP = "STYLES"
    CRS_QP = "CRS"
    BBOX_QP = "CRS"
    WIDTH_QP = "WIDTH"
    HEIGHT_QP = "HEIGHT"
    FORMAT_QP = "FORMAT"
    TRANSPARENT_QP = "TRANSPARENT"
    GET_MAP_QV = "GetMap"
    GET_FEATURE_INFO_QV = "GetFeatureInfo"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.major_version == 1 and self.minor_version < 3:
            self.CRS_QP = "SRS"
        if self.major_version == 1 and self.minor_version < 1:
            # version 1.0.0 has other values
            self.VERSION_QP = "WMTVER"
            self.GET_CAPABILITIES_QV = "capabilities"
            self.GET_MAP_QV = "map"
            self.GET_FEATURE_INFO_QV = "feature_info"

    def get_get_map_request(self,
                            layer_list,
                            crs: str,
                            bbox: str,
                            width: int,
                            height: int,
                            format: str,
                            style_list=None,
                            ):

        if isinstance(layer_list, str):
            layer_list = [layer_list]
        if not style_list:
            style_list = [""]  # A client may request the default Style using a null value (as in “STYLES=”)
        if isinstance(style_list, str):
            style_list = [style_list]

        req = PreparedRequest()
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_MAP_QV,
                             self.LAYERS_QP: ",".join(layer_list) if len(layer_list) > 1 else layer_list[0],
                             self.STYLES_QP: ",".join(style_list) if len(style_list) > 1 else style_list[0],
                             self.CRS_QP: crs,
                             self.BBOX_QP: bbox,
                             self.WIDTH_QP: width,
                             self.HEIGHT_QP: height,
                             self.FORMAT_QP: format})
        req.prepare_url(self.base_url, query_params)
        return req

    def get_get_feature_info_url(self, layer_list, x: int, y: int, info_format=None, feature_count=None):
        raise NotImplementedError


class WfsService(WebService):
    DESCRIBE_FEATURE_TYPE_QV = "DescribeFeatureType"
    GET_FEATURE_QV = "GetFeature"
    TYPE_NAME_QV = "typeName"
    OUTPUT_FORMAT_QV = "outputFormat"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.major_version == 2 and self.minor_version == 0 and self.path_version < 2:
            self.TYPE_NAME_QV = "TYPENAME"
            self.OUTPUT_FORMAT_QV = "OUTPUTFORMAT"

    def get_describe_feature_type_request(self, type_name_list=None, output_format=None):
        req = PreparedRequest()
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.DESCRIBE_FEATURE_TYPE_QV})
        if type_name_list:
            if isinstance(type_name_list, str):
                type_name_list = [type_name_list]
            query_params.update(
                {self.TYPE_NAME_QV: ",".join(type_name_list) if len(type_name_list) > 1 else type_name_list[0]})
        if output_format:
            query_params.update({self.OUTPUT_FORMAT_QV: output_format})
        req.prepare_url(self.base_url, query_params)
        return req

    def get_get_feature_request(self):
        # todo
        raise NotImplementedError
        req = PreparedRequest()
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_FEATURE_QV})
        req.prepare_url(self.base_url, query_params)
        return req


def OgcService(base_url: str, service_type:str, version: str):
    """ ogc service factory function, returns a service type specific WebService object

        Args:
            base_url (str): the base url of the service
            service_type (ServiceTypeEnum): the type of the ogc service
            version: (str): the version of the service in sem version format x.y.z

        Returns:
            the specific WebService object based on the given service_type
    """
    if service_type == "wms":
        return WmsService(base_url=base_url, service_type=service_type, version=version)
    elif service_type == "wfs":
        return WfsService(base_url=base_url, service_type=service_type, version=version)
