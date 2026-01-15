from typing import List

from lxml.etree import _Element
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.request.utils import update_queryparams
from registry.ows_lib.xml.builder import XSDSkeletonBuilder
from requests import Request


class WebFeatureServiceClient(OgcClient):

    @property
    def exception_builder(self):
        return XSDSkeletonBuilder(("wfs", "Exception", self.service_version))

    @property
    def request_builder(self) -> XSDSkeletonBuilder:
        return XSDSkeletonBuilder(("wfs", "GetCapabilities", self.service_version))

    @property
    def type_name_qp(self):
        return "TYPENAMES" if self.service_version == "2.0.0" else "TYPENAME"

    @property
    def output_format_qp(self):
        return "OUTPUTFORMAT" if self.service_version == "2.0.0" else "OUTPUTFORMAT"

    def describe_feature_type_request(
            self,
            type_names: List[str],
            output_format: List[str]) -> Request:

        params = {
            "VERSION": self.service_version,
            "REQUEST": "DescribeFeatureType",
            "SERVICE": self.service_type,
            self.type_name_qp: ",".join(type_names),
            self.output_format_qp: ",".join(output_format)
        }
        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.DESCRIBE_FEATURE_TYPE,
                HttpMethodEnum.GET
            ),
            params=params)
        return Request(method="GET", url=url)

    def build_get_feature_request(self,) -> _Element:
        xml = self.request_builder.build_element(
            "GetFeature",
            nsmap={
                "wfs": "http://www.opengis.net/wfs/2.0",
                "fes": "http://www.opengis.net/fes/2.0"
            }
        )
        return xml

    def get_feature_request(
            self,
            get_feature_request: bytes) -> Request:

        params = {
            "VERSION": self.service_version,
            "REQUEST": "GetFeature",
            "SERVICE": self.service_type,
        }
        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.GET_FEATURE,
                HttpMethodEnum.POST
            ),
            params=params)

        return Request(method="POST", url=url, data=get_feature_request, headers={"Content-Type": "application/xml"})
