from importlib import resources
from typing import List

from lxml.etree import _Element
from registry.client.core import OgcClient
from registry.client.utils import update_queryparams
from registry.client.xml.builder import XSDSkeletonBuilder
from requests import Request

WFS_XSD_BY_VERSION = {
    "2.0.0": "wfs200.xml",
    # "1.1.0": "wfs110.xml",
    # "1.0.0": "wfs100.xml",
}


class WebFeatureServiceMixin(OgcClient):

    @property
    def xml_builder(self) -> XSDSkeletonBuilder:
        try:
            xsd_filename = WFS_XSD_BY_VERSION[self.service_version]
        except KeyError:
            raise ValueError(
                f"Unsupported WFS version: {self.service_version}"
            )
        with resources.files("registry.client.xml.schemas") \
                .joinpath(xsd_filename) \
                .open("rb") as f:
            return XSDSkeletonBuilder(f)

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
                "DescribeFeatureType", "Get").url,
            params=params)
        return Request(method="GET", url=url)

    def build_get_feature_request(self,) -> _Element:
        xml = self.xml_builder.build_element(
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
                "GetFeature", "Post").url,
            params=params)

        return Request(method="POST", url=url, data=get_feature_request, headers={"Content-Type": "application/xml"})
