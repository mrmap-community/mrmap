import urllib.parse as urlparse
from abc import ABC
from urllib.parse import parse_qs

from axis_order_cache.registry import Registry
from axis_order_cache.utils import adjust_axis_order, get_epsg_srid
from django.contrib.gis.gdal import SpatialReference
from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.template.loader import render_to_string
from eulxml import xmlmap
from registry.xmlmapper.ogc.wfs_get_feature import GetFeature
from registry.xmlmapper.ogc.wfs_transaction import Transaction
from requests import Request

from .exceptions import (MissingBboxParam, MissingCrsParam,
                         MissingServiceParam, MissingVersionParam)


class WebService(ABC):
    REQUEST_QP = "REQUEST"
    SERVICE_QP = "SERVICE"
    VERSION_QP = "VERSION"
    GET_CAPABILITIES_QV = "GetCapabilities"

    version = (0, 0, 0)

    def __init__(self, base_url: str, service_type: str, version: str, *args, **kwargs):
        self.base_url = base_url.split("?", 1)[0]
        self.service_type = service_type
        self.version = version
        version_split = version.split(".")
        if len(version_split) != 3:
            raise ValueError(
                "the given version is not in sem version format like x.y.z")
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
        """Method to get the concrete method for an operation. """
        if hasattr(self, operation):
            return getattr(self, operation)

    def construct_request(self, query_params, data=None) -> Request:
        get_dict = self.get_get_params(query_params=query_params)
        if self.get_operation_by_name(get_dict.get(self.REQUEST_QP).lower()):
            if data:
                if isinstance(data, bytes):
                    # don't know why, but if we don't decode and encode again with UTF-8 the encoding is always wrong..
                    data = data.decode("UTF-8").encode("UTF-8")
                return self.get_operation_by_name(get_dict.get(self.REQUEST_QP).lower())(data=data, **get_dict)
            else:
                return self.get_operation_by_name(get_dict.get(self.REQUEST_QP).lower())(**get_dict)
        else:
            return Request(method="GET", url=self.base_url, params=query_params)

    @classmethod
    def manufacture_service(cls, url):
        parsed = urlparse.urlparse(url)
        service_type = parse_qs(parsed.query).get("SERVICE", None)
        version = parse_qs(parsed.query).get("VERSION", None)
        if not service_type:
            service_type = parse_qs(parsed.query).get("service", None)
            if not service_type:
                raise MissingServiceParam
        if not version:
            version = parse_qs(parsed.query).get("version", None)
            if not version:
                raise MissingVersionParam
        if service_type[0] in ["wms", "WMS"]:
            return WmsService(base_url=url, version=version[0])
        elif service_type[0] in ["wfs", "WFS"]:
            return WfsService(base_url=url, version=version[0])
        elif service_type[0] in ["csw", "CSW"]:
            return CatalogueServiceWeb(base_url=url, version=version[0])

    def set_version(self, new_version: tuple[int, int, int]):
        self.version = new_version


class WebMapAndFeatureService(WebService):
    BBOX_QP = "BBOX"
    CRS_QP = None

    @classmethod
    def _construct_polygon_from_bbox_query_param_for_wfs(cls, get_dict):
        """Construct a polygon from the parsed bbox query parameter, based on the given service type and version.

        **WFS 1.0.0 (see wfs specs - 6.2.8.2.3 BBOX)**:
        * Provides geographic coordinates in longitude/latitude | east/north and may not be trusted to
          respect the EPSG definition axis order. ==> mathematical x,y order is used.
        * The coordinate reference system of the bbox always matches the crs of the SRS query param.


        **WFS >1.0.0 (see wfs specs - 14.3.3 Bounding box)**:
        * Respects the axis order defined by the EPSG definition. ==> dynamic x,y order based on the result
          of the epsg registry is used.
        * The bbox values support n axis crs systems ==> BBOX=lcc1,lcc2,...,lccN,ucc1,ucc2,...uccN[,crsuri]
        * The coordinate reference system of the bbox by default is WGS84 (EPSG:4326). IF the bbox param provides a
        crsuri value this coordinate reference system shall be used instead.

        :return: the bbox parsed from the get_dict or an empty polygon if something went wrong.
        :rtype: :class:`django.contrib.gis.geos.polygon.Polygon`
        """
        try:
            major_version, minor_version, fix_version = get_dict["version"].split(
                ".")
            major_version = int(major_version)
            minor_version = int(minor_version)
            bbox = get_dict["bbox"]
            srid = get_dict.get("srs", None)
            if not srid:
                srid = get_dict.get("srsname", None)
                if not srid:
                    raise MissingCrsParam

            xy_order = True

            if major_version == 1 and minor_version < 1:
                min_x, min_y, max_x, max_y = bbox.split(",")
                min_x = float(min_x)
                min_y = float(min_y)
                max_x = float(max_x)
                max_y = float(max_y)
            else:
                bbox_values = bbox.split(",")
                registry = Registry()
                if len(bbox_values) == 4:
                    epsg_sr = registry.get(srid=4326)
                elif len(bbox_values) == 5:
                    authority, srid = get_epsg_srid(bbox_values[4])
                    epsg_sr = registry.get(srid=srid)
                else:
                    raise NotImplementedError(
                        "multiple dimension crs is not implemented.")
                min_x = float(bbox_values[0])
                min_y = float(bbox_values[1])
                max_x = float(bbox_values[2])
                max_y = float(bbox_values[3])
                xy_order = epsg_sr.is_xy_order

            if xy_order:
                return Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)),
                               srid=srid)
            else:
                return Polygon(((min_y, min_x), (max_y, min_x), (max_y, max_x), (min_y, max_x), (min_y, min_x)),
                               srid=srid)
        except Exception:
            pass
        return GEOSGeometry('POLYGON EMPTY')

    @classmethod
    def _construct_polygon_from_bbox_query_param_for_wms(cls, get_dict):
        """Construct a polygon from the parsed bbox query parameter, based on the given service type and version.

        * In WMS version < 1.3.0 requests with a Geographic Coordinate Reference System, the bbox is interpreted with
          X-axis ≙ Longitude and Y-axis ≙ Latitude value.
        * In WMS version >= 1.3.0 requests the bbox axis order is interpreted like the axis order of the requested
          reference system.

        .. note:: excerpt from ogc specs

            * **OGC WMS 1.1.0**: When the SRS parameter specifies a Geographic Coordinate Reference System, e.g.,
              "EPSG:4326", the returned image is implicitly projected using a pseudo-Plate Carrée projection that plots
              Longitude along the X-axis and Latitude along the Y-axis. The BBOX request parameter (Section 7.2.3.6)
              values for such a coordinate reference system shall be specified in the order minimum longitude, minimum
              latitude, maximum longitude, maximum latitude. The BBOX parameter values shall use the coordinate
              reference system units.
              Some Projected Coordinate Reference Systems, e.g., "EPSG:30800" ("RT38 2.5 gon W", used in Sweden), have
              axes order other than X=East, Y=North. The BBOX request parameter values for such a coordinate system
              shall be specified in the order minimum Easting, minimum Northing, maximum Easting, maximum Northing.
              The BBOX parameters shall use the coordinate reference system units. (see 6.5.5.1)
            * **OGC WMS 1.3.0**: EXAMPLE EPSG:4326 refers to WGS 84 geographic latitude, then longitude. That is, in
              this CRS the x axis corresponds to latitude, and the y axis to longitude. (see 6.7.3.3)

        :return: the bbox parsed from the get_dict or an empty polygon if something went wrong.
        :rtype: :class:`django.contrib.gis.geos.polygon.Polygon`
        """
        try:
            major_version, minor_version, fix_version = get_dict["version"].split(
                ".")
            minor_version = int(minor_version)
            srid = get_dict.get("srs", None)
            if not srid:
                srid = get_dict.get("crs", None)
                if not srid:
                    raise MissingCrsParam

            bbox = get_dict["bbox"]
            min_x, min_y, max_x, max_y = bbox.split(",")
            min_x = float(min_x)
            min_y = float(min_y)
            max_x = float(max_x)
            max_y = float(max_y)

            xy_order = True
            if minor_version >= 3:
                sr = SpatialReference(srs_input=srid)
                registry = Registry()
                epsg_sr = registry.get(srid=sr.srid)
                srid = epsg_sr.srid
                xy_order = epsg_sr.is_xy_order
            else:
                if ":" in srid:
                    srid = srid.split(":")[-1]
                srid = int(srid)

            if xy_order:
                return Polygon(((min_x, min_y), (min_x, max_y), (max_x, max_y), (max_x, min_y), (min_x, min_y)),
                               srid=srid)
            else:
                return Polygon(((min_y, min_x), (max_y, min_x), (max_y, max_x), (min_y, max_x), (min_y, min_x)),
                               srid=srid)
        except Exception:
            pass
        return GEOSGeometry('POLYGON EMPTY')

    @classmethod
    def construct_polygon_from_bbox_query_param(cls, get_dict) -> GEOSGeometry:
        """Construct a polygon from the parsed bbox query parameter, based on the given service type and version.

        :return: the bbox parsed from the get_dict or an empty polygon if something went wrong.
        :rtype: :class:`django.contrib.gis.geos.geometry.GEOSGeometry`
        """
        service_type = get_dict.get("service", None)
        if not get_dict.get("service", None):
            raise MissingServiceParam
        if not get_dict.get("bbox", None):
            raise MissingBboxParam
        if service_type.lower() == "wms":
            return cls._construct_polygon_from_bbox_query_param_for_wms(get_dict=get_dict)
        elif service_type.lower() == "wfs":
            return cls._construct_polygon_from_bbox_query_param_for_wfs(get_dict=get_dict)


class CatalogueServiceWeb(WebService):
    GET_RECORDS_QV = "GetRecords"
    TYPE_NAME_QP = "typeNames"
    OUTPUT_SCHEMA_QP = "outputSchema"
    CONSTRAINT_LANGUAGE_QP = "CONSTRAINTLANGUAGE"
    ELEMENT_SET_NAME_QP = "ElementSetName"
    RESULT_TYPE_QP = "resultType"
    START_POSITION_QP = "startPosition"
    MAX_RECORDS_QP = "maxRecords"
    OUTPUT_FORMAT_QP = "outputFormat"
    REQUEST_ID_QP = "requestId"

    def __init__(self, *args, **kwargs):
        super().__init__(service_type="CSW", *args, **kwargs)

    def get_get_records_kwargs(self,
                               type_name_list,
                               request_id: str = None,
                               result_type: str = "hits",
                               start_position: int = 1,
                               max_records: int = 10,
                               output_format: str = "application/xml",
                               output_schema: str = "http://www.opengis.net/cat/csw/2.0.2",
                               constraint_language: str = "FILTER",
                               element_set_name: str = "full",
                               **kwargs):
        if isinstance(type_name_list, str):
            type_name_list = [type_name_list]
        query_params = {self.TYPE_NAME_QP: ",".join(type_name_list) if len(type_name_list) > 1 else type_name_list[0],
                        self.RESULT_TYPE_QP: result_type,
                        self.START_POSITION_QP: start_position,
                        self.MAX_RECORDS_QP: max_records,
                        self.OUTPUT_FORMAT_QP: output_format,
                        self.OUTPUT_SCHEMA_QP: output_schema,
                        self.CONSTRAINT_LANGUAGE_QP: constraint_language,
                        self.ELEMENT_SET_NAME_QP: element_set_name}
        if request_id:
            query_params.update({self.REQUEST_ID_QP: request_id})
        return query_params

    def convert_kwargs_for_get_records(self, **kwargs):
        return {
            "type_name_list": kwargs[self.TYPE_NAME_QP].split(","),
            "result_type": kwargs.get(self.RESULT_TYPE_QP, None),
            "request_id": kwargs.get(self.REQUEST_ID_QP, None),
            "output_format": kwargs.get(self.OUTPUT_FORMAT_QP, None),
            "output_schema": kwargs.get(self.OUTPUT_SCHEMA_QP, None),
            "constraint_language": kwargs.get(self.CONSTRAINT_LANGUAGE_QP, None),
            "element_set_name": kwargs.get(self.ELEMENT_SET_NAME_QP, None),
            "start_position": kwargs.get(self.START_POSITION_QP, None),
            "max_records": kwargs.get(self.MAX_RECORDS_QP, None),
        }

    def getrecords(self, **kwargs):
        return self.get_get_records_request(**kwargs)

    def get_get_records_request(self, **kwargs):
        query_params = self.get_get_records_kwargs(
            **self.convert_kwargs_for_get_records(**kwargs))
        query_params.update({self.REQUEST_QP: self.GET_RECORDS_QV})
        query_params.update(self.get_default_query_params())
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req


class WmsService(WebMapAndFeatureService):
    LAYERS_QP = "LAYERS"
    STYLES_QP = "STYLES"
    CRS_QP = "CRS"
    WIDTH_QP = "WIDTH"
    HEIGHT_QP = "HEIGHT"
    FORMAT_QP = "FORMAT"
    TRANSPARENT_QP = "TRANSPARENT"
    BG_COLOR_QP = "BGCOLOR"
    EXCEPTIONS_QP = "EXCEPTIONS"
    TIME_QP = "TIME"
    ELEVATION_QP = "ELEVATION"
    QUERY_LAYERS_QP = "QUERY_LAYERS"
    INFO_FORMAT_QP = "INFO_FORMAT"
    FEATURE_COUNT_QP = "FEATURE_COUNT"
    I_QP = "I"
    J_QP = "J"
    GET_MAP_QV = "GetMap"
    GET_FEATURE_INFO_QV = "GetFeatureInfo"
    get_params = {}

    def __init__(self, *args, **kwargs):
        super().__init__(service_type="wms", *args, **kwargs)
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
            _key = key.upper()
            match _key:
                case "SERVICE":
                    _query_params.update({self.SERVICE_QP: val})
                case "REQUEST":
                    _query_params.update({self.REQUEST_QP: val})
                case "LAYERS":
                    _query_params.update({self.LAYERS_QP: val})
                case "BBOX":
                    _query_params.update({self.BBOX_QP: val})
                case "VERSION":
                    _query_params.update({self.VERSION_QP: val})
                case ("FORMAT" | "OUTPUTFORMAT"):
                    _query_params.update({self.FORMAT_QP: val})
                case ("SRS" | "CRS" | "SRSNAME"):
                    _query_params.update({self.CRS_QP: val})
                case ("WIDTH"):
                    _query_params.update({self.WIDTH_QP: val})
                case "HEIGHT":
                    _query_params.update({self.HEIGHT_QP: val})
                case "TRANSPARENT":
                    _query_params.update({self.TRANSPARENT_QP: val})
                case "EXCEPTIONS":
                    _query_params.update({self.EXCEPTIONS_QP: val})
                case "BGCOLOR":
                    _query_params.update({self.BG_COLOR_QP: val})
                case "TIME":
                    _query_params.update({self.TIME_QP: val})
                case "ELEVATION":
                    _query_params.update({self.ELEVATION_QP: val})
                case "QUERY_LAYERS":
                    _query_params.update({self.QUERY_LAYERS_QP: val})
                case "INFO_FORMAT":
                    _query_params.update({self.INFO_FORMAT_QP: val})
                case "FEATURE_COUNT":
                    _query_params.update({self.FEATURE_COUNT_QP: val})
                case "I":
                    _query_params.update({self.I_QP: val})
                case "J":
                    _query_params.update({self.J_QP: val})
        return _query_params

    def get_requested_layers(self, query_params: dict):
        return self.get_get_params(query_params=query_params).get(self.LAYERS_QP).split(",")

    def convert_kwargs_for_get_map(self, **kwargs):
        transparent = kwargs.get(self.TRANSPARENT_QP.lower(), False),
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

    def get_get_map_kwargs(self,
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
                           **kwargs):
        if isinstance(layer_list, str):
            layer_list = [layer_list]
        if not style_list:
            # A client may request the default Style using a null value (as in “STYLES=”)
            style_list = [""]
        if isinstance(style_list, str):
            style_list = [style_list]

        query_params = {self.LAYERS_QP: ",".join(layer_list) if len(layer_list) > 1 else layer_list[0],
                        self.STYLES_QP: ",".join(style_list) if len(style_list) > 1 else style_list[0],
                        self.CRS_QP: crs,
                        self.BBOX_QP: bbox,
                        self.WIDTH_QP: width,
                        self.HEIGHT_QP: height,
                        self.FORMAT_QP: format,
                        self.TRANSPARENT_QP: "TRUE" if transparent else "FALSE",
                        self.BG_COLOR_QP: bg_color,
                        self.EXCEPTIONS_QP: exceptions}
        if time:
            query_params.update({self.TIME_QP: time})
        if elevation:
            query_params.update({self.ELEVATION_QP: elevation})
        return query_params

    def get_get_map_request(self, **kwargs) -> Request:
        query_params = self.get_get_map_kwargs(**kwargs)
        query_params.update({self.REQUEST_QP: self.GET_MAP_QV})
        query_params.update(self.get_default_query_params())
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def convert_kwargs_for_get_feature_info(self, **kwargs):
        return {
            "query_layers": kwargs[self.QUERY_LAYERS_QP.lower()].split(","),
            "info_format": kwargs[self.INFO_FORMAT_QP.lower()],
            "feature_count": kwargs.get(self.FEATURE_COUNT_QP.lower(), 1),
            "i": kwargs[self.I_QP.lower()],
            "j": kwargs[self.J_QP.lower()],
            "exceptions": kwargs.get(self.EXCEPTIONS_QP.lower(), "XML"),
        }

    def get_get_feature_info_kwargs(self,
                                    query_layers,
                                    info_format: str,
                                    i: int,
                                    j: int,
                                    feature_count: int = 1,
                                    exceptions: str = "XML",
                                    **kwargs):
        if isinstance(query_layers, str):
            query_layers = [query_layers]
        query_params = {self.QUERY_LAYERS_QP: ",".join(query_layers) if len(query_layers) > 1 else query_layers[0],
                        self.INFO_FORMAT_QP: info_format,
                        self.FEATURE_COUNT_QP: feature_count,
                        self.I_QP: i,
                        self.J_QP: j,
                        self.EXCEPTIONS_QP: exceptions}
        return query_params

    def feature_info(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def getfeatureinfo(self, **kwargs):
        return self.get_get_feature_info_request(**kwargs)

    def get_get_feature_info_request(self, **kwargs):
        query_params = self.get_get_map_kwargs(
            **self.convert_kwargs_for_get_map(**kwargs))
        query_params.update(self.get_get_feature_info_kwargs(
            **self.convert_kwargs_for_get_feature_info(**kwargs)))
        query_params.update({self.REQUEST_QP: self.GET_FEATURE_INFO_QV})
        query_params.update(self.get_default_query_params())
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req


class WfsService(WebMapAndFeatureService):
    DESCRIBE_FEATURE_TYPE_QV = "DescribeFeatureType"
    GET_FEATURE_QV = "GetFeature"
    TRANSACTION_QV = "Transaction"
    TYPE_NAME_QP = "typeName"
    TYPE_NAME_DFT_QP = "TYPENAME"
    OUTPUT_FORMAT_QP = "outputFormat"
    CRS_QP = "srsName"
    FEATURE_ID_QP = "featureID"
    COUNT_QP = "count"
    MAX_FEATURES_QP = "maxFeatures"
    SORT_BY_QP = "sortBy"
    PROPERTY_NAME_QP = "propertyName"

    def __init__(self, *args, **kwargs):
        super().__init__(service_type="wfs", *args, **kwargs)
        if self.major_version == 2 and self.minor_version == 0:
            self.TYPE_NAME_QP = "TYPENAMES"
            self.OUTPUT_FORMAT_QP = "OUTPUTFORMAT"

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
            elif key == "BBOX":
                _query_params.update({self.BBOX_QP: val})
            elif key == "VERSION":
                _query_params.update({self.VERSION_QP: val})
            elif key == "OUTPUTFORMAT":
                _query_params.update({self.OUTPUT_FORMAT_QP: val})
            elif key == "SRSNAME":
                _query_params.update({self.CRS_QP: val})
            elif key == "TYPENAMES" or key == "TYPENAME":
                _query_params.update({self.TYPE_NAME_QP: val})
            elif key == "FEATUREID":
                _query_params.update({self.FEATURE_ID_QP: val})
            elif key == "COUNT":
                _query_params.update({self.COUNT_QP: val})
            elif key == "MAXFEATURES":
                _query_params.update({self.MAX_FEATURES_QP: val})
            elif key == "SORTBY":
                _query_params.update({self.SORT_BY_QP: val})
            elif key == "PROPERTYNAME":
                _query_params.update({self.PROPERTY_NAME_QP: val})
        return _query_params

    def convert_kwargs_for_get_feature(self, **kwargs):
        return {
            "type_names": kwargs[self.TYPE_NAME_QP],
            "bbox": kwargs.get(self.BBOX_QP, None),
            "srs_name": kwargs.get(self.CRS_QP, None),
            "feature_id": kwargs.get(self.FEATURE_ID_QP, None),
            "count": kwargs.get(self.COUNT_QP, None),
            "property_name": kwargs.get(self.PROPERTY_NAME_QP, None),
            "sort_by": kwargs.get(self.SORT_BY_QP, None),
            "max_features": kwargs.get(self.MAX_FEATURES_QP, None),
            "filter_xml": kwargs.get("filter_xml", None),
        }

    def get_get_feature_kwargs(self,
                               type_names,
                               bbox: str = None,
                               srs_name: str = None,
                               feature_id: str = None,
                               count: int = None,
                               property_name=None,
                               sort_by: str = None,
                               max_features: int = None,
                               **kwargs):
        if isinstance(type_names, str):
            type_names = [type_names]
        if property_name and isinstance(property_name, str):
            property_name = [property_name]

        query_params = {self.TYPE_NAME_QP: ",".join(
            type_names) if len(type_names) > 1 else type_names[0]}
        if property_name:
            query_params.update(
                {self.PROPERTY_NAME_QP: ",".join(property_name) if len(property_name) > 1 else property_name[0]})
        if bbox:
            query_params.update({self.BBOX_QP: bbox})
        if srs_name:
            query_params.update({self.CRS_QP: srs_name})
        if feature_id:
            query_params.update({self.FEATURE_ID_QP: feature_id})
        if count:
            query_params.update({self.COUNT_QP: count})
        if sort_by:
            query_params.update({self.SORT_BY_QP: sort_by})
        if max_features:
            query_params.update({self.MAX_FEATURES_QP: max_features})
        return query_params

    def convert_kwargs_for_transaction(self, **kwargs):
        return {}

    def get_transaction_kwargs(self, **kwargs):
        return {}

    def get_requested_feature_types(self, query_params: dict, post_body: str):
        if post_body:
            if "transaction" == query_params.get("request").lower():
                transaction_xml = xmlmap.load_xmlobject_from_string(string=post_body,
                                                                    xmlclass=Transaction)
                return transaction_xml.operation.get_type_names().split(",")
            elif "getfeature" == query_params.get("request").lower():
                get_feature_xml = xmlmap.load_xmlobject_from_string(string=post_body,
                                                                    xmlclass=GetFeature)
                return get_feature_xml.get_type_names().split(",")
        else:
            return self.get_get_params(query_params=query_params).get(self.TYPE_NAME_QP).split(",")

    def get_describe_feature_type_request(self, type_name_list=None, output_format=None):
        query_params = self.get_default_query_params()
        query_params.update({self.REQUEST_QP: self.DESCRIBE_FEATURE_TYPE_QV})
        if type_name_list:
            if isinstance(type_name_list, str):
                type_name_list = [type_name_list]
            query_params.update(
                {self.TYPE_NAME_DFT_QP: ",".join(type_name_list) if len(type_name_list) > 1 else type_name_list[0]})
        if output_format:
            query_params.update({self.OUTPUT_FORMAT_QP: output_format})
        req = Request(method="GET", url=self.base_url, params=query_params)
        return req

    def getfeature(self, **kwargs):
        return self.get_get_feature_request(**kwargs)

    def get_get_feature_request(self, data: str = None, **kwargs):
        query_params = self.get_get_feature_kwargs(
            **self.convert_kwargs_for_get_feature(**kwargs))
        query_params.update({self.REQUEST_QP: self.GET_FEATURE_QV})
        query_params.update(self.get_default_query_params())
        if data:
            if self.BBOX_QP.lower() in kwargs:
                # bbox and xml filter together is not supported.
                del query_params[self.BBOX_QP]
            if self.TYPE_NAME_QP.lower() in kwargs:
                # typename and xml filter together is not supported.
                del query_params[self.TYPE_NAME_QP]
            req = Request(method="POST",
                          url=self.base_url,
                          params=query_params,
                          data=data,
                          headers={"content-type": "application/xml"})
        else:
            req = Request(method="GET",
                          url=self.base_url,
                          params=query_params)
        return req

    def transaction(self, **kwargs):
        return self.get_transaction_request(**kwargs)

    def get_transaction_request(self, data: str, **kwargs):
        query_params = self.get_transaction_kwargs(
            **self.convert_kwargs_for_transaction(**kwargs))
        query_params.update({self.REQUEST_QP: self.TRANSACTION_QV})
        query_params.update(self.get_default_query_params())

        if self.TYPE_NAME_QP.lower() in kwargs:
            # typename and xml filter together is not supported.
            del query_params[self.TYPE_NAME_QP]
        return Request(method="POST",
                       url=self.base_url,
                       params=query_params,
                       data=data,
                       headers={"content-type": "application/xml"})

    def construct_filter_xml(self, type_names, value_reference, polygon: Polygon):
        if self.major_version >= 2:
            polygon = adjust_axis_order(polygon)

            template_name = "registry/xml/wfs/get_feature_v2.xml"
        else:
            template_name = "registry/xml/wfs/get_feature_v1.xml"
        return render_to_string(template_name=template_name, context={"type_names": type_names,
                                                                      "value_reference": value_reference,
                                                                      "polygon": polygon})


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
        return WmsService(base_url=base_url, version=version)
    elif service_type == "wfs":
        return WfsService(base_url=base_url, version=version)
