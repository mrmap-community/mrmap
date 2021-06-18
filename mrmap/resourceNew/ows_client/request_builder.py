from abc import ABC
from requests import Request


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

    def get_get_capabilities_request(self) -> Request:
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_CAPABILITIES_QV})
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def get_operation_by_name(self, operation: str):
        return getattr(self, operation)


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

    def get_get_params(self, get_dict):
        """ Parses the GET parameters into all member variables, which can be found in a request.

        Returns:
            the for this version converted get_dict
        """
        _get_dict = {}
        for key, val in get_dict.items():
            key = key.upper()
            if key == "SERVICE":
                _get_dict.update({self.SERVICE_QP: val})
            if key == "REQUEST":
                _get_dict.update({self.REQUEST_QP: val})
            elif key == "LAYERS":
                _get_dict.update({self.LAYERS_QP: val})
            elif key == "BBOX":
                _get_dict.update({self.BBOX_QP: val})
            elif key == "VERSION":
                _get_dict.update({self.VERSION_QP: val})
            elif key == "FORMAT" or key == "OUTPUTFORMAT":
                _get_dict.update({self.FORMAT_QP: val})
            elif key == "SRS" or key == "CRS" or key == "SRSNAME":
                _get_dict.update({self.CRS_QP: val})
            elif key == "WIDTH":
                _get_dict.update({self.WIDTH_QP: val})
            elif key == "HEIGHT":
                _get_dict.update({self.HEIGHT_QP: val})
        return _get_dict

    def construct_request_with_get_dict(self, get_dict) -> Request:
        get_dict = self.get_get_params(get_dict=get_dict)
        if hasattr(self, get_dict.get(self.REQUEST_QP).lower()):
            return getattr(self, get_dict.get(self.REQUEST_QP))(**get_dict)

    def getmap(self, **kwargs):
        return self.get_get_map_request(**kwargs)

    def map(self, **kwargs):
        return self.get_get_map_request(**kwargs)

    def get_get_map_request(self,
                            layer_list,
                            crs: str,
                            bbox: str,
                            width: int,
                            height: int,
                            format: str,
                            style_list=None,
                            **kwargs) -> Request:

        if isinstance(layer_list, str):
            layer_list = [layer_list]
        if not style_list:
            style_list = [""]  # A client may request the default Style using a null value (as in “STYLES=”)
        if isinstance(style_list, str):
            style_list = [style_list]

        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_MAP_QV,
                             self.LAYERS_QP: ",".join(layer_list) if len(layer_list) > 1 else layer_list[0],
                             self.STYLES_QP: ",".join(style_list) if len(style_list) > 1 else style_list[0],
                             self.CRS_QP: crs,
                             self.BBOX_QP: bbox,
                             self.WIDTH_QP: width,
                             self.HEIGHT_QP: height,
                             self.FORMAT_QP: format})
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def feature_info(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def getfeatureinfo(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def get_get_feature_info_request(self, layer_list, x: int, y: int, info_format=None, feature_count=None, **kwargs):
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
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.DESCRIBE_FEATURE_TYPE_QV})
        if type_name_list:
            if isinstance(type_name_list, str):
                type_name_list = [type_name_list]
            query_params.update(
                {self.TYPE_NAME_QV: ",".join(type_name_list) if len(type_name_list) > 1 else type_name_list[0]})
        if output_format:
            query_params.update({self.OUTPUT_FORMAT_QV: output_format})
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def get_get_feature_request(self):
        # todo
        raise NotImplementedError
        req = PreparedRequest()
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.GET_FEATURE_QV})
        req.prepare_url(self.base_url, query_params)
        return req


def OgcService(base_url: str, service_type: str, version: str):
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
