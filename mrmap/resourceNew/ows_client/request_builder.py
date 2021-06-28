import distutils
from abc import ABC
from requests import Request
from django.contrib.gis.geos import Polygon


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
    BBOX_QP = "BBOX"
    WIDTH_QP = "WIDTH"
    HEIGHT_QP = "HEIGHT"
    FORMAT_QP = "FORMAT"
    TRANSPARENT_QP = "TRANSPARENT"
    BG_COLOR_QP = "BGCOLOR"
    EXCEPTIONS_QP = "EXCEPTIONS"
    TIME_QP = "TIME"
    ELEVATION_QP = "ELEVATION"
    GET_MAP_QV = "GetMap"
    GET_FEATURE_INFO_QV = "GetFeatureInfo"
    get_params = {}

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

    def get_get_params(self, query_params: dict):
        """ Parses the GET parameters into all member variables, which can be found in a request.

        Returns:
            the for this version converted get_dict
        """
        _query_params = {}
        for key, val in query_params.items():
            key = key.upper()
            if key == "SERVICE":
                _query_params.update({self.SERVICE_QP: val})
            if key == "REQUEST":
                _query_params.update({self.REQUEST_QP: val})
            elif key == "LAYERS":
                _query_params.update({self.LAYERS_QP: val})
            elif key == "BBOX":
                _query_params.update({self.BBOX_QP: val})
            elif key == "VERSION":
                _query_params.update({self.VERSION_QP: val})
            elif key == "FORMAT" or key == "OUTPUTFORMAT":
                _query_params.update({self.FORMAT_QP: val})
            elif key == "SRS" or key == "CRS" or key == "SRSNAME":
                _query_params.update({self.CRS_QP: val})
            elif key == "WIDTH":
                _query_params.update({self.WIDTH_QP: val})
            elif key == "HEIGHT":
                _query_params.update({self.HEIGHT_QP: val})
            elif key == "TRANSPARENT":
                _query_params.update({self.TRANSPARENT_QP: val})
            elif key == "EXCEPTIONS":
                _query_params.update({self.EXCEPTIONS_QP: val})
            elif key == "BGCOLOR":
                _query_params.update({self.BG_COLOR_QP: val})
            elif key == "TIME":
                _query_params.update({self.TIME_QP: val})
            elif key == "ELEVATION":
                _query_params.update({self.ELEVATION_QP: val})
        return _query_params

    def get_requested_layers(self, query_params: dict):
        return self.get_get_params(query_params=query_params).get(self.LAYERS_QP).split(",")

    def construct_polygon_from_bbox(self, get_dict):
        """
            wms 1.1.1, 1.3.0:
                * CRS=namespace:identifier | M | Coordinate reference system.
                * BBOX=minx,miny,maxx,maxy | M | Bounding box corners (lower left, upper right) in CRS units.

        """
        get_dict = self.get_get_params(get_dict)
        bbox = get_dict.get(self.BBOX_QP, None)
        srid = get_dict.get(self.CRS_QP, None)
        if bbox and srid:
            min_x, min_y, max_x, max_y = bbox.split(",")
            # todo: handle different namespaces
            srid = srid.split(":")[-1]
            return Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)), srid=srid)

    def construct_request_with_get_dict(self, query_params) -> Request:
        get_dict = self.get_get_params(query_params=query_params)
        if hasattr(self, get_dict.get(self.REQUEST_QP).lower()):
            return getattr(self, get_dict.get(self.REQUEST_QP).lower())(**get_dict)
        else:
            return Request(method="GET", url=self.base_url, params=query_params)

    def convert_kwargs_for_get_map(self, **kwargs):
        transparent = kwargs.get(self.TRANSPARENT_QP, False),
        if isinstance(transparent, str):
            if transparent == "TRUE":
                transparent = True
            else:
                transparent = False

        return {
            "layer_list": kwargs[self.LAYERS_QP].split(","),
            "crs": kwargs[self.CRS_QP],
            "bbox": kwargs[self.BBOX_QP],
            "width": kwargs[self.WIDTH_QP],
            "height": kwargs[self.HEIGHT_QP],
            "format": kwargs[self.FORMAT_QP],
            "style_list": kwargs.get(self.STYLES_QP, None),
            "transparent": transparent,
            "bg_color": kwargs.get(self.BG_COLOR_QP, "0xFFFFFF"),
            "exceptions": kwargs.get(self.EXCEPTIONS_QP, "XML"),
            "time": kwargs.get(self.TIME_QP, None),
            "elevation": kwargs.get(self.ELEVATION_QP, None)
        }

    def getmap(self, **kwargs):
        return self.get_get_map_request(**self.convert_kwargs_for_get_map(**kwargs))

    def map(self, **kwargs):
        return self.get_get_map_request(**self.convert_kwargs_for_get_map(**kwargs))

    def get_get_map_request(self,
                            layer_list,
                            crs: str,
                            bbox: str,
                            width: int,
                            height: int,
                            format: str,
                            time: str = None,
                            elevation: str = None,
                            style_list=None,
                            transparent: bool = False,
                            bg_color: str = "0xFFFFFF",
                            exceptions: str = "XML",
                            ) -> Request:

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
                             self.FORMAT_QP: format,
                             self.TRANSPARENT_QP: "TRUE" if transparent else "FALSE",
                             self.BG_COLOR_QP: bg_color,
                             self.EXCEPTIONS_QP: exceptions})
        if time:
            query_params.update({self.TIME_QP: time})
        if elevation:
            query_params.update({self.ELEVATION_QP: elevation})
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def feature_info(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def getfeatureinfo(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def get_get_feature_info_request(self, layer_list, x: int, y: int, info_format=None, feature_count=None):
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
