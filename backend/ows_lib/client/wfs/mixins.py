from typing import List

from ows_lib.client.mixins import OgcClient
from ows_lib.client.utils import update_queryparams
from requests import Request


class WebFeatureServiceMixin(OgcClient):

    @property
    def type_name_qp(self):
        raise NotImplementedError

    @property
    def output_format_qp(self):
        raise NotImplementedError

    def prepare_describe_feature_type_request(
            self,
            type_names: List[str],
            output_format: List[str]) -> Request:
        params = {
            "VERSION": self.capabilities.version,
            "REQUEST": "DescribeFeatureType",
            self.type_name_qp: ",".join(type_names),
            self.output_format_qp: ",".join(output_format)
        }
        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "DescribeFeatureType", "Get").url,
            params=params)
        return Request(method="GET", url=url)
