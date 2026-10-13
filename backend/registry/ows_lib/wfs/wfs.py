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
        return "TYPENAMES" if self.service_version.startswith("2.") else "TYPENAME"

    @property
    def output_format_qp(self):
        return "OUTPUTFORMAT" if self.service_version == "2.0.0" else "OUTPUTFORMAT"

    @property
    def max_features_qp(self):
        return "COUNT" if self.service_version.startswith("2.") else "MAXFEATURES"

    def describe_feature_type_request(
            self,
            type_names: list[str],
            output_format: list[str]) -> Request:

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

    def get_feature_kvp_request(
            self,
            type_names: list[str],
            max_features: int = None,
            srs_name: str = None,
            output_format: str = None) -> Request:
        """Build a GetFeature request in the key value pairing style.

        Args:
            type_names (list[str]):
                the identifiers of the feature types which shall be requested
            max_features (int, optional):
                the maximum number of features the response shall contain.
                Defaults to None.
            srs_name (str, optional):
                the spatial reference system of the response. Defaults to None.
            output_format (str, optional):
                the output format of the response. Defaults to None, which lets
                the service decide about the output format.

        Returns:
            Request: the prepared GetFeature request
        """

        params = {
            "VERSION": self.service_version,
            "REQUEST": "GetFeature",
            "SERVICE": self.service_type,
            self.type_name_qp: ",".join(type_names),
        }
        if max_features:
            params.update({self.max_features_qp: max_features})
        if srs_name:
            params.update({"SRSNAME": srs_name})
        if output_format:
            params.update({self.output_format_qp: output_format})

        url = update_queryparams(
            url=self.get_operation_url_by_name_and_method(
                OGCOperationEnum.GET_FEATURE,
                HttpMethodEnum.GET
            ),
            params=params)

        return Request(method="GET", url=url)
