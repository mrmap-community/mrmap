from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
from requests import Request, Session


class WebFeatureServiceClientTest(SimpleTestCase):
    def setUp(self):
        self.session = Mock(spec=Session)

    def tearDown(self):
        self.session.send.assert_not_called()

    def make_client(self, feature_types, version="2.0.0", formats=("application/json",), method="Get"):
        formats_xml = "".join(f"<ows:Value>{value}</ows:Value>" for value in formats)
        capabilities = f"""
            <WFS_Capabilities version="{version}" xmlns="http://www.opengis.net/wfs/2.0"
                xmlns:ows="http://www.opengis.net/ows/1.1" xmlns:xlink="http://www.w3.org/1999/xlink">
                <ows:OperationsMetadata><ows:Operation name="GetFeature">
                    <ows:DCP><ows:HTTP><ows:{method} xlink:href="https://example.test/wfs?token=preview"/>
                    </ows:HTTP></ows:DCP>
                    <ows:Parameter name="outputFormat"><ows:AllowedValues>{formats_xml}
                    </ows:AllowedValues></ows:Parameter>
                </ows:Operation></ows:OperationsMetadata>
                <FeatureTypeList>{feature_types}</FeatureTypeList>
            </WFS_Capabilities>
        """.encode()
        return WebFeatureServiceClient(capabilities, session=self.session)

    def feature_type(self, name="example:roads", crs="urn:ogc:def:crs:EPSG::4326", formats=None,
                     lower="5 40", upper="25 50", with_bbox=True, crs_tag="DefaultCRS"):
        formats_xml = "" if formats is None else "<OutputFormats>" + "".join(
            f"<Format>{value}</Format>" for value in formats) + "</OutputFormats>"
        bbox = f"""<ows:WGS84BoundingBox><ows:LowerCorner>{lower}</ows:LowerCorner>
            <ows:UpperCorner>{upper}</ows:UpperCorner></ows:WGS84BoundingBox>""" if with_bbox else ""
        return f"""<FeatureType><Name>{name}</Name><{crs_tag}>{crs}</{crs_tag}>
            {formats_xml}{bbox}</FeatureType>"""

    def params(self, request):
        self.assertIsInstance(request, Request)
        self.assertEqual(request.method, "GET")
        return {key: values[0] for key, values in parse_qs(urlparse(request.url).query).items()}

    def test_preview_uses_a_bounded_geojson_request_and_wfs_axis_order(self):
        params = self.params(self.make_client(self.feature_type()).get_preview_request())

        self.assertEqual(params["SERVICE"], "WFS")
        self.assertEqual(params["VERSION"], "2.0.0")
        self.assertEqual(params["REQUEST"], "GetFeature")
        self.assertEqual(params["TYPENAMES"], "example:roads")
        self.assertEqual(params["COUNT"], "500")
        self.assertEqual(params["SRSNAME"], "EPSG:4326")
        self.assertEqual(params["OUTPUTFORMAT"], "application/json")
        self.assertEqual(params["BBOX"], "40.0,5.0,50.0,25.0,EPSG:4326")
        self.assertEqual(params["token"], "preview")

    def test_preview_uses_version_specific_feature_type_and_count_parameters(self):
        for version, type_key, count_key, crs_tag in (
                ("1.1.0", "TYPENAME", "MAXFEATURES", "DefaultSRS"),
                ("2.0.0", "TYPENAMES", "COUNT", "DefaultCRS"),
                ("2.0.2", "TYPENAMES", "COUNT", "DefaultCRS")):
            with self.subTest(version=version):
                client = self.make_client(self.feature_type(crs_tag=crs_tag), version=version)

                params = self.params(client.get_preview_request(max_features=20))

                self.assertEqual(params["VERSION"], version)
                self.assertEqual(params[type_key], "example:roads")
                self.assertEqual(params[count_key], "20")
                self.assertNotIn("TYPENAMES" if type_key == "TYPENAME" else "TYPENAME", params)
                self.assertNotIn("COUNT" if count_key == "MAXFEATURES" else "MAXFEATURES", params)

    def test_preview_selects_first_suitable_feature_type_in_capabilities_order(self):
        client = self.make_client("".join((
            self.feature_type(name=""),
            self.feature_type(name="projected", crs="EPSG:3857"),
            self.feature_type(name="gml", formats=("application/gml+xml",)),
            self.feature_type(name="missing_extent", with_bbox=False),
            self.feature_type(name="invalid_extent", lower="nan 40"),
            self.feature_type(), self.feature_type(name="example:water"))))

        self.assertEqual(self.params(client.get_preview_request())["TYPENAMES"], "example:roads")

    def test_preview_restricts_selection_to_eligible_feature_types(self):
        client = self.make_client(self.feature_type() + self.feature_type(name="example:water"))

        self.assertEqual(self.params(client.get_preview_request(type_names=["example:water"]))["TYPENAMES"], "example:water")
        self.assertEqual(self.params(client.get_preview_request(
            type_names=["example:water", "example:roads"]))["TYPENAMES"], "example:roads")
        for type_names in ([], ["unknown"]):
            with self.subTest(type_names=type_names), self.assertRaises(ValueError):
                client.get_preview_request(type_names=type_names)

    def test_preview_uses_feature_type_formats_before_operation_formats(self):
        client = self.make_client(self.feature_type(formats=("application/geo+json",)))

        self.assertEqual(self.params(client.get_preview_request())["OUTPUTFORMAT"], "application/geo+json")

        with self.assertRaises(ValueError):
            self.make_client(self.feature_type(formats=("application/gml+xml",))).get_preview_request()

    def test_preview_accepts_advertised_geojson_aliases(self):
        for output_format in ("application/json", "application/geo+json", "json", "GeoJSON"):
            with self.subTest(output_format=output_format):
                client = self.make_client(self.feature_type(), formats=("application/gml+xml", output_format))

                self.assertEqual(self.params(client.get_preview_request())["OUTPUTFORMAT"], output_format)

    def test_preview_accepts_advertised_epsg4326_aliases(self):
        for crs in ("EPSG:4326", "urn:ogc:def:crs:EPSG::4326", "urn:x-ogc:def:crs:EPSG:4326",
                    "http://www.opengis.net/def/crs/EPSG/0/4326"):
            with self.subTest(crs=crs):
                client = self.make_client(self.feature_type(crs=crs))

                self.assertEqual(self.params(client.get_preview_request())["SRSNAME"], "EPSG:4326")

    def test_preview_can_use_other_crs(self):
        feature = self.feature_type(crs="EPSG:3857").replace("</DefaultCRS>", "</DefaultCRS><OtherCRS>EPSG:4326</OtherCRS>")

        self.assertEqual(self.params(self.make_client(feature).get_preview_request())["SRSNAME"], "EPSG:4326")

    def test_preview_rejects_missing_geojson_or_epsg4326_configuration(self):
        for feature, formats in ((self.feature_type(), ("application/gml+xml",)),
                                 (self.feature_type(crs="CRS:84"), ("application/json",)),
                                 (self.feature_type(crs="EPSG:3857"), ("application/json",)),
                                 ("", ("application/json",))):
            with self.subTest(feature=feature, formats=formats), self.assertRaises(ValueError):
                self.make_client(feature, formats=formats).get_preview_request()

    def test_preview_rejects_invalid_wgs84_extents(self):
        for lower, upper in (("", "25 50"), ("5", "25 50"), ("5 40 0", "25 50 1"),
                             ("nan 40", "25 50"), ("5 40", "inf 50"), ("a 40", "25 50"),
                             ("25 40", "5 50"), ("5 50", "25 40"), ("5 40", "5 50"),
                             ("-181 40", "25 50"), ("5 -91", "25 50"), ("5 40", "181 50"),
                             ("5 40", "25 91")):
            with self.subTest(lower=lower, upper=upper), self.assertRaises(ValueError):
                self.make_client(self.feature_type(lower=lower, upper=upper)).get_preview_request()

    def test_preview_requires_getfeature_get_support(self):
        with self.assertRaises(ValueError):
            self.make_client(self.feature_type(), method="Post").get_preview_request()

    def test_preview_rejects_unsupported_versions(self):
        with self.assertRaises(ValueError):
            self.make_client(self.feature_type(), version="1.0.0").get_preview_request()

    def test_preview_requires_a_bounded_positive_integer_feature_count(self):
        client = self.make_client(self.feature_type())

        for max_features in (0, -1, 501, 1.5, "5", None, True):
            with self.subTest(max_features=max_features), self.assertRaises(ValueError):
                client.get_preview_request(max_features=max_features)
