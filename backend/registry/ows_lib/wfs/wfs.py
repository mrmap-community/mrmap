import math

from lxml.etree import _Element
from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.client.exceptions import InitialError
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
        return "OUTPUTFORMAT"

    @property
    def max_features_qp(self):
        return "COUNT" if self.service_version.startswith("2.") else "MAXFEATURES"

    def get_preview_request(self, max_features: int = 500, type_names: list[str] = None) -> Request:
        """Build, without sending, a bounded GeoJSON GetFeature request.

        Choose the first named feature type in capabilities order that has an
        advertised GeoJSON format, EPSG:4326 and a usable WGS84 bounding box.
        Optional type_names restricts selection to eligible feature types.
        The BBOX uses the WFS 1.1/2.0 axis order and an explicit EPSG:4326 CRS.
        Raises ValueError when no such configuration is advertised.
        """
        if self.service_type != "WFS" or self.service_version not in {"1.1.0", "2.0.0", "2.0.2"}:
            raise ValueError("Previews require WFS 1.1.0 or 2.0 capabilities")
        if type(max_features) is not int or not 1 <= max_features <= 500:
            raise ValueError("Preview feature count must be an integer between 1 and 500")

        eligible = set(type_names) if type_names is not None else None
        root = self._capabilities_etree
        operation_formats = root.xpath(
            "//*[local-name()='Operation' and @name='GetFeature']"
            "/*[local-name()='Parameter' and @name='outputFormat']//*[local-name()='Value']/text()")
        for node in root.findall("{*}FeatureTypeList/{*}FeatureType"):
            name = (node.findtext("{*}Name") or "").strip()
            if not name or (eligible is not None and name not in eligible):
                continue
            formats = node.xpath("./*[local-name()='OutputFormats']/*/text()") or operation_formats
            output_format = next((value.strip() for value in formats if value.strip().lower() in
                                  {"application/json", "application/geo+json", "json", "geojson"}), None)
            crs = node.xpath(
                "./*[local-name()='DefaultCRS' or local-name()='OtherCRS' or "
                "local-name()='DefaultSRS' or local-name()='OtherSRS' or local-name()='SRS']/text()")
            if not output_format or not any(value.strip().upper().endswith((":4326", "::4326", "/4326")) for value in crs):
                continue
            try:
                west, south, east, north = self._get_preview_bbox(node)
            except ValueError:
                continue
            try:
                request = self.get_feature_kvp_request(
                    type_names=[name], max_features=max_features,
                    srs_name="EPSG:4326", output_format=output_format)
            except InitialError as error:
                raise ValueError(str(error)) from error
            request.url = update_queryparams(
                url=request.url,
                params={"BBOX": ",".join(map(str, (south, west, north, east))) + ",EPSG:4326"})
            return request
        raise ValueError("Capabilities contain no feature type suitable for a GeoJSON preview")

    @staticmethod
    def _get_preview_bbox(node):
        bbox = node.find("{*}WGS84BoundingBox")
        if bbox is None:
            raise ValueError("Feature type has no WGS84 bounding box")
        try:
            lower = tuple(map(float, (bbox.findtext("{*}LowerCorner") or "").split()))
            upper = tuple(map(float, (bbox.findtext("{*}UpperCorner") or "").split()))
            if len(lower) != 2 or len(upper) != 2:
                raise ValueError("Preview bounding box must have two-dimensional corners")
            west, south = lower
            east, north = upper
            if (not all(math.isfinite(value) for value in (*lower, *upper))
                    or not -180 <= west < east <= 180 or not -90 <= south < north <= 90):
                raise ValueError("Preview bounding box must have finite, increasing WGS84 bounds")
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid preview bounding box") from error
        return west, south, east, north

    def describe_feature_type_request(
            self,
            type_names: list[str],
            output_format: list[str]) -> Request:

        params = {
            "VERSION": self.service_version,
            "REQUEST": "DescribeFeatureType",
            "SERVICE": self.service_type,
            self.type_name_qp: ",".join(type_names),
        }
        # With no advertised XML format, let the service use its protocol-defined default.
        if output_format:
            params[self.output_format_qp] = ",".join(output_format)
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
