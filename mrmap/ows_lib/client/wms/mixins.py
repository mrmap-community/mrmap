from typing import List

from ows_lib.client.mixins import OgcClient
from ows_lib.client.utils import update_queryparams
from requests import Request


class WebMapServiceMixin(OgcClient):

    @property
    def crs_qp(self):
        raise NotImplementedError

    @property
    def get_map_operation_name(self):
        raise NotImplementedError

    @property
    def get_feature_info_operation_name(self):
        raise NotImplementedError

    def prepare_get_map_request(
            self,
            layers: List[str],
            styles: List[str],
            crs: str,
            bbox: tuple[float, float, float, float],
            width: int,
            height: int,
            format: str,
            transparent: bool = None,
            bgcolor: int = 0xFFFFFF,
            exceptions: str = "xml",
            time: List[str] = None,
            elevation: float = None) -> Request:

        if isinstance(transparent, str):
            if transparent == "TRUE":
                transparent = True
            else:
                transparent = False

        params = {
            "VERSION": self.capabilities.service_type.version,
            "REQUEST": "GetMap",
            "SERVICE": self.capabilities.service_type.name,
            "LAYERS": ",".join(layers),
            "STYLES": ",".join(styles),
            self.crs_qp: crs,
            "BBOX": ",".join(bbox),
            "WIDTH": width,
            "HEIGHT": height,
            "FORMAT": format,
            "TRANSPARENT": transparent,
            "BGCOLOR": hex(bgcolor),
            "EXCEPTIONS": exceptions,
        }
        if time:
            params.update({"TIME": ",".join(time)})
        if elevation:
            params.update({"ELEVATION": elevation})

        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                self.get_map_operation_name, "Get").url,
            params=params)

        return Request(method="GET", url=url)

    def prepare_get_feature_info_request(
            self,
            get_map_request: Request,
            query_layers: List[str],
            info_format: str,
            i: int,
            j: int,
            feature_count: int = 0,
            exceptions: str = "xml") -> Request:

        params = get_map_request.params

        get_feature_info_params = {
            "VERSION": self.capabilities.service_type.version,
            "REQUEST": "GetFeatureInfo",
            "SERVICE": self.capabilities.service_type.name,
            "QUERY_LAYERS": ",".join(query_layers),
            "INFO_FORMAT": info_format,
            "FEATURE_COUNT": feature_count,
            "I": i,
            "J": j,
            "EXCEPTIONS": exceptions,
        }

        params.update(get_feature_info_params)

        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                self.get_feature_info_operation_name, "Get").url,
            params=params)

        return Request(method="GET", url=url)
