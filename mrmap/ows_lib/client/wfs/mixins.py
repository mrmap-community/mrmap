from typing import List

from ows_lib.client.mixins import OgcClient
from ows_lib.client.utils import update_queryparams
from ows_lib.xml_mapper.xml_requests.wfs.get_feature import GetFeatureRequest
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
            "VERSION": self.capabilitie.sservice_type.version,
            "REQUEST": "DescribeFeatureType",
            "SERVICE": self.capabilities.service_type.name,
            self.type_name_qp: ",".join(type_names),
            self.output_format_qp: ",".join(output_format)
        }
        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "DescribeFeatureType", "Get").url,
            params=params)
        return Request(method="GET", url=url)

    def prepare_get_feature_request(
            self,
            get_feature_request: GetFeatureRequest):
        params = {
            "VERSION": self.capabilities.service_type.version,
            "REQUEST": "GetFeature",
            "SERVICE": self.capabilities.service_type.name,
        }
        url = update_queryparams(
            url=self.capabilities.get_operation_url_by_name_and_method(
                "GetFeature", "Post").url,
            params=params)

        return Request(method="POST", url=url, data=get_feature_request.serializeDocument(), headers={"Content-Type": "application/xml"})
