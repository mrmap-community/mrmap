import math

from django.contrib.gis.gdal import GDALException
from epsg_cache.models import SpatialReference
from epsg_cache.utils import get_epsg_srid
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.request.utils import update_queryparams
from requests import Request


class WebMapServiceClient(OgcClient):
    """WebMapService class which implements some basic functionality for all wms client applications"""

    @property
    def crs_qp(self):
        return "CRS" if self.service_version == "1.3.0" else "SRS"

    @property
    def get_map_operation_name(self):
        return "GetMap" if self.service_version in ["1.1.1", "1.3.0"] else "Map"

    @property
    def get_feature_info_operation_name(self):
        return "GetFeatureInfo" if self.service_version in ["1.1.1", "1.3.0"] else "FeatureInfo"

    def get_preview_request(self, width: int = 512, height: int = 256) -> Request:
        """Build, without sending, a GetMap preview of the whole service.

        Request named leaf layers in capabilities order, once per name. Select
        an advertised common CRS and image format, and use each layer's default
        style and dimension values.
        Width and height are pixel limits; the image preserves the extent's
        aspect ratio unless the service advertises fixed dimensions.

        Supports WMS 1.1.1 and 1.3.0. Raises ValueError when the capabilities
        cannot describe a single whole-service preview within those limits.
        """
        if self.service_type != "WMS" or self.service_version not in {"1.1.1", "1.3.0"}:
            raise ValueError("Previews require WMS 1.1.1 or 1.3.0 capabilities")
        if any(type(value) is not int or value < 1 for value in (width, height)):
            raise ValueError("Preview width and height must be positive integers")

        layers = self._get_preview_layers()
        crs, bbox = self._get_preview_extent(layers)
        fixed_width, fixed_height = self._get_preview_constraints(layers, crs, bbox)
        width, height = self._get_preview_size(crs, bbox, width, height, fixed_width, fixed_height)
        image_format = self._get_preview_format()
        return self.get_map_request(
            layers=[layer.findtext("{*}Name").strip() for layer in layers],
            styles=[""] * len(layers),
            crs=crs,
            bbox=bbox,
            width=width,
            height=height,
            format=image_format,
            transparent=image_format == "image/png",
            exceptions=self._get_preview_exception_format(),
        )

    def _get_preview_layers(self):
        def select(layer):
            children = layer.findall("{*}Layer")
            if children:
                # Some services advertise names for organizational groups that
                # they reject in GetMap. Prefer their concrete leaf layers.
                return [selected for child in children for selected in select(child)]
            if (layer.findtext("{*}Name") or "").strip():
                return [layer]
            return []

        layers_by_name = {}
        for root in self._capabilities_etree.findall("{*}Capability/{*}Layer"):
            for layer in select(root):
                layers_by_name.setdefault(layer.findtext("{*}Name").strip(), layer)
        layers = list(layers_by_name.values())
        if not layers:
            raise ValueError("Capabilities contain no named layers to preview")
        limit = self._capabilities_etree.findtext("{*}Service/{*}LayerLimit")
        if limit is not None and len(layers) > int(limit):
            raise ValueError("Whole-service preview exceeds the advertised layer limit")
        return layers

    @staticmethod
    def _checked_preview_bbox(values):
        try:
            bbox = tuple(float(value) for value in values)
        except (TypeError, ValueError):
            raise ValueError("Invalid preview bounding box") from None
        if (len(bbox) != 4 or not all(math.isfinite(value) for value in bbox)
                or bbox[0] >= bbox[2] or bbox[1] >= bbox[3]):
            raise ValueError("Preview bounding box must have finite, increasing bounds")
        return bbox

    def _get_preview_layer_extents(self, layer):
        supported = set()
        extents = {}
        geographic = None
        for ancestor in layer.xpath("ancestor-or-self::*[local-name()='Layer']"):
            for value in ancestor.findall(f"{{*}}{self.crs_qp}"):
                supported.update((value.text or "").split())
            for value in ancestor.findall("{*}BoundingBox"):
                crs = value.get(self.crs_qp)
                if crs:
                    # Capabilities BoundingBox already uses the protocol's axis order.
                    extents[crs] = self._checked_preview_bbox(
                        value.get(name) for name in ("minx", "miny", "maxx", "maxy"))
            if self.service_version == "1.3.0":
                value = ancestor.find("{*}EX_GeographicBoundingBox")
                if value is not None:
                    geographic = self._checked_preview_bbox(value.findtext(f"{{*}}{name}") for name in (
                        "westBoundLongitude", "southBoundLatitude", "eastBoundLongitude", "northBoundLatitude"))
            else:
                value = ancestor.find("{*}LatLonBoundingBox")
                if value is not None:
                    geographic = self._checked_preview_bbox(
                        value.get(name) for name in ("minx", "miny", "maxx", "maxy"))

        if geographic is not None:
            if "CRS:84" in supported:
                extents.setdefault("CRS:84", geographic)
            if "EPSG:4326" in supported:
                west, south, east, north = geographic
                extents.setdefault("EPSG:4326", (south, west, north, east)
                                   if self.service_version == "1.3.0" else geographic)
        return supported, extents

    def _get_preview_extent(self, layers):
        configurations = [self._get_preview_layer_extents(layer) for layer in layers]
        common = set.intersection(*(supported for supported, _ in configurations))
        if not common:
            raise ValueError("Preview layers have no common advertised CRS")
        available = common.intersection(*(set(extents) for _, extents in configurations))
        if not available:
            raise ValueError("Preview layers have no bounding boxes in a common advertised CRS")
        preferred = [value for value in ("CRS:84", "EPSG:4326", "EPSG:3857") if value in available]
        crs = preferred[0] if preferred else min(available)
        bounds = [extents[crs] for _, extents in configurations]
        return crs, (min(value[0] for value in bounds), min(value[1] for value in bounds),
                     max(value[2] for value in bounds), max(value[3] for value in bounds))

    def _get_preview_constraints(self, layers, crs, bbox):
        fixed = {"fixedWidth": set(), "fixedHeight": set()}
        for selected in layers:
            for layer in selected.iter("{*}Layer"):
                if not (layer.findtext("{*}Name") or "").strip():
                    continue
                attributes = {}
                dimensions = {}
                for ancestor in layer.xpath("ancestor-or-self::*[local-name()='Layer']"):
                    attributes.update(ancestor.attrib)
                    for dimension in ancestor.xpath("./*[local-name()='Dimension' or local-name()='Extent']"):
                        name = (dimension.get("name") or "").lower()
                        if self.service_version == "1.1.1" and dimension.tag.endswith("Dimension"):
                            # 1.1.1 keeps dimension metadata and its values/default separate.
                            dimensions.setdefault(name, None)
                        else:
                            dimensions[name] = dimension.get("default")
                for name, default in dimensions.items():
                    if not default:
                        raise ValueError(f"Cannot preview dimension '{name}' without a default value")
                for name, values in fixed.items():
                    value = int(attributes.get(name, "0"))
                    if value < 0:
                        raise ValueError(f"Invalid {name} in capabilities")
                    if value:
                        values.add(value)
                if attributes.get("noSubsets", "0").lower() in {"1", "true"}:
                    _, extents = self._get_preview_layer_extents(layer)
                    if extents.get(crs) != bbox:
                        raise ValueError("Preview extent conflicts with a layer that disallows subsets")
        if any(len(values) > 1 for values in fixed.values()):
            raise ValueError("Preview layers require incompatible fixed image dimensions")
        return tuple(next(iter(values), 0) for values in fixed.values())

    def _get_preview_size(self, crs, bbox, width, height, fixed_width, fixed_height):
        for name, limit in (("MaxWidth", width), ("MaxHeight", height)):
            value = self._capabilities_etree.findtext(f"{{*}}Service/{{*}}{name}")
            if value is not None:
                limit = min(limit, int(value))
            if limit < 1:
                raise ValueError(f"Invalid advertised {name}")
            if name == "MaxWidth":
                width = limit
            else:
                height = limit
        dx, dy = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if self.service_version == "1.3.0" and crs not in {"CRS:27", "CRS:83", "CRS:84"}:
            try:
                authority, code = get_epsg_srid(crs)
                if not authority or not authority.isalnum() or type(code) is not int:
                    raise ValueError(f"Cannot determine preview axis order for '{crs}'")
                # Pass an authority/code to local GDAL, never a potentially remote URL.
                if SpatialReference(srs_input=f"{authority}:{code}").is_yx_order:
                    dx, dy = dy, dx
            except GDALException:
                raise ValueError(f"Cannot determine preview axis order for '{crs}'") from None
        if not all(math.isfinite(value) for value in (dx, dy)):
            raise ValueError("Preview extent is too large")
        scale = min(width / dx, height / dy)
        result_width, result_height = max(1, round(dx * scale)), max(1, round(dy * scale))
        if fixed_width and fixed_height:
            result_width, result_height = fixed_width, fixed_height
        elif fixed_width:
            result_width, result_height = fixed_width, max(1, round(fixed_width * dy / dx))
        elif fixed_height:
            result_width, result_height = max(1, round(fixed_height * dx / dy)), fixed_height
        if result_width > width or result_height > height:
            raise ValueError("Fixed image dimensions exceed preview size limits")
        return result_width, result_height

    def _get_preview_format(self):
        formats = self._capabilities_etree.findall("{*}Capability/{*}Request/{*}GetMap/{*}Format")
        advertised = {(value.text or "").strip() for value in formats}
        for value in ("image/png", "image/jpeg"):
            if value in advertised:
                return value
        raise ValueError("Service advertises neither PNG nor JPEG GetMap output")

    def _get_preview_exception_format(self):
        formats = self._capabilities_etree.findall("{*}Capability/{*}Exception/{*}Format")
        for value in formats:
            name = (value.text or "").strip()
            if name.lower() in {"xml", "application/vnd.ogc.se_xml", "application/xml", "text/xml"}:
                return name
        raise ValueError("Service advertises no XML exception format")

    def get_map_request(
            self,
            layers: list[str],
            styles: list[str],
            crs: str,
            bbox: tuple[float, float, float, float],
            width: int,
            height: int,
            format: str,
            transparent: bool = None,
            bgcolor: int = 0xFFFFFF,
            exceptions: str = "xml",
            time: list[str] = None,
            elevation: float = None) -> Request:
        """Constructs a GetMap request to use for requesting

        :param layers: The name of layers which shall be requested
        :type layers: list[str]
        :param styles: The styles of the layers which shall be requested
        :type styles: list[str]
        :param crs: the reference system which shall be used
        :type crs: str
        :param bbox: the bounding box
        :type bbox: tuple[float, float, float, float]
        :param width: the pixel width
        :type width: int
        :param height: the pixel height
        :type height: int
        :param format: the response format
        :type format: str
        :param transparent: shall the response be a transparent image?, defaults to None
        :type transparent: bool, optional
        :param bgcolor: the background color of the response, defaults to 0xFFFFFF
        :type bgcolor: int, optional
        :param exceptions: the exception format which shall be used by the server, defaults to "xml"
        :type exceptions: str, optional
        :param time: the time value or range for map data, defaults to None
        :type time: list[str], optional
        :param elevation: _description_, defaults to None
        :type elevation: float, optional
        :return: the constructed get map request object
        :rtype: Request
        """

        if isinstance(transparent, str):
            if transparent == "TRUE":
                transparent = True
            else:
                transparent = False

        params = {
            "VERSION": self.service_version,
            "REQUEST": "GetMap",
            "SERVICE": self.service_type,
            "LAYERS": ",".join(layers),
            "STYLES": ",".join(styles),
            self.crs_qp: crs,
            "BBOX": ",".join(map(str, bbox)),
            "WIDTH": width,
            "HEIGHT": height,
            "FORMAT": format,
            "BGCOLOR": hex(bgcolor),
            "EXCEPTIONS": exceptions,
        }
        if transparent is not None:
            params["TRANSPARENT"] = "TRUE" if transparent else "FALSE"
        if time:
            params.update({"TIME": ",".join(time)})
        if elevation:
            params.update({"ELEVATION": elevation})

        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.GET_MAP,
                HttpMethodEnum.GET
            ),
            params=params)

        return Request(method="GET", url=url)

    def get_feature_info_request(
            self,
            get_map_request: Request,
            query_layers: list[str],
            info_format: str,
            i: int,
            j: int,
            feature_count: int = 0,
            exceptions: str = "xml") -> Request:
        """Constructs a GetFeatureInfo request to use for requesting

        :param get_map_request: The GetMap request where this request shall based on
        :type get_map_request: requests.Request
        :param query_layers: The list of layers for that the feature info shall be requested
        :type query_layers: list[str]
        :param info_format: The concrete format of the response
        :type info_format: str
        :param i: the x value of the x/y point tuple
        :type i: int
        :param j: the y value of the x/y point tuple
        :type j: int
        :param feature_count: The number of features that shall be returned, defaults to 0
        :type feature_count: int, optional
        :param exceptions: the exception format of the server to response with, defaults to "xml"
        :type exceptions: str, optional
        :return: the constructed get feature info request object
        :rtype: requests.Request
        """

        params: dict = get_map_request.params

        get_feature_info_params = {
            "VERSION": self.service_version,
            "REQUEST": "GetFeatureInfo",
            "SERVICE": self.service_type,
            "QUERY_LAYERS": ",".join(query_layers),
            "INFO_FORMAT": info_format,
            "FEATURE_COUNT": feature_count,
            "I": i,
            "J": j,
            "EXCEPTIONS": exceptions,
        }

        params.update(get_feature_info_params)

        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.GET_FEATURE_INFO,
                HttpMethodEnum.GET
            ),
            params=params)

        return Request(method="GET", url=url)
