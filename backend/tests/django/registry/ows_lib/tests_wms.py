from pathlib import Path
from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from django.test import SimpleTestCase
from lxml import etree
from registry.ows_lib.wms.wms import WebMapServiceClient
from requests import Request, Session


class WebMapServiceClientTest(SimpleTestCase):
    def setUp(self):
        self.session = Mock(spec=Session)

    def tearDown(self):
        self.session.send.assert_not_called()

    def make_client(self, layers, version="1.3.0", formats=("image/png", "image/jpeg"), extra="", exception_formats=None):
        namespace = 'xmlns="http://www.opengis.net/wms"' if version == "1.3.0" else ""
        root = "WMS_Capabilities" if version == "1.3.0" else "WMT_MS_Capabilities"
        if exception_formats is None:
            exception_formats = ("XML",) if version == "1.3.0" else ("application/vnd.ogc.se_xml",)
        formats_xml = "".join(f"<Format>{format}</Format>" for format in formats)
        exceptions_xml = "".join(f"<Format>{format}</Format>" for format in exception_formats)
        capabilities = f"""
            <{root} version="{version}" {namespace} xmlns:xlink="http://www.w3.org/1999/xlink">
                <Service><Name>WMS</Name>{extra}</Service>
                <Capability>
                    <Request><GetMap>{formats_xml}<DCPType><HTTP><Get>
                        <OnlineResource xlink:href="https://example.test/wms?token=preview"/>
                    </Get></HTTP></DCPType></GetMap></Request>
                    <Exception>{exceptions_xml}</Exception>
                    {layers}
                </Capability>
            </{root}>
        """.encode()
        return WebMapServiceClient(capabilities, session=self.session)

    def params(self, request):
        self.assertIsInstance(request, Request)
        self.assertEqual(request.method, "GET")
        return {key: values[0] for key, values in parse_qs(
            urlparse(request.url).query, keep_blank_values=True).items()}

    def bbox(self, params):
        return tuple(map(float, params["BBOX"].split(",")))

    def test_named_root_selects_named_leaf_descendants(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer><Name>roads</Name></Layer>
                <Layer><Name>water</Name></Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "roads,water")
        self.assertEqual(params["STYLES"], ",")
        self.assertEqual(params["CRS"], "CRS:84")
        self.assertEqual(params["WIDTH"], "512")
        self.assertEqual(params["HEIGHT"], "256")
        self.assertEqual(params["FORMAT"], "image/png")
        self.assertEqual(params["TRANSPARENT"], "TRUE")
        self.assertEqual(params["EXCEPTIONS"], "XML")
        self.assertEqual(params["token"], "preview")

    def test_named_and_unnamed_groups_select_named_leaf_layers(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer><Name>transport</Name><Layer><Name>roads</Name></Layer></Layer>
                <Layer><Layer><Name>water</Name></Layer></Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "roads,water")
        self.assertEqual(params["STYLES"], ",")

    def test_wms111_nested_named_groups_select_leaf_layers_in_order(self):
        client = self.make_client("""
            <Layer><Name>all</Name><SRS>EPSG:4326</SRS>
                <LatLonBoundingBox minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer><Name>transport</Name>
                    <Layer><Name>roads</Name></Layer>
                    <Layer><Name>railways</Name></Layer>
                </Layer>
                <Layer><Name>water</Name></Layer>
            </Layer>
        """, version="1.1.1")

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "roads,railways,water")
        self.assertEqual(params["STYLES"], ",,")

    def test_duplicate_leaf_names_use_first_occurrence(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <Layer><Name>transport</Name>
                    <Layer><Name>roads</Name>
                        <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="10" maxy="10"/>
                    </Layer>
                </Layer>
                <Layer><Name>basemap</Name>
                    <Layer><Name>roads</Name>
                        <BoundingBox CRS="CRS:84" minx="100" miny="0" maxx="120" maxy="10"/>
                    </Layer>
                    <Layer><Name>water</Name>
                        <BoundingBox CRS="CRS:84" minx="10" miny="0" maxx="20" maxy="10"/>
                    </Layer>
                </Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "roads,water")
        self.assertEqual(params["STYLES"], ",")
        self.assertEqual(self.bbox(params), (0, 0, 20, 10))

    def test_dwd_preview_requests_all_leaf_layers_without_group_names(self):
        capabilities = (Path(__file__).resolve().parents[2] / "test_data" / "dwd_wms_1.3.0.xml").read_bytes()
        root = etree.fromstring(capabilities)
        leaf_names = root.xpath(
            ".//*[local-name()='Layer' and not(*[local-name()='Layer'])]/*[local-name()='Name']/text()")
        group_names = set(root.xpath(
            ".//*[local-name()='Layer' and *[local-name()='Layer']]/*[local-name()='Name']/text()"))
        client = WebMapServiceClient(capabilities, session=self.session)

        params = self.params(client.get_preview_request())
        requested_names = params["LAYERS"].split(",")

        self.assertEqual(len(leaf_names), 121)
        self.assertEqual(requested_names, leaf_names)
        self.assertTrue({"Fachlayer", "Basislayer"}.issubset(group_names))
        self.assertTrue(group_names.isdisjoint(requested_names))
        self.assertEqual(params["STYLES"].split(","), [""] * 121)

    def test_crs_is_inherited_cumulatively_and_child_bbox_overrides_parent(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="-100" miny="-50" maxx="100" maxy="50"/>
                <Layer><CRS>EPSG:4326</CRS>
                    <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="10" maxy="10"/>
                    <Layer><Name>west</Name></Layer>
                </Layer>
                <Layer><Name>east</Name><CRS>EPSG:3857</CRS>
                    <BoundingBox CRS="CRS:84" minx="10" miny="5" maxx="20" maxy="10"/>
                </Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["CRS"], "CRS:84")
        self.assertEqual(self.bbox(params), (0, 0, 20, 10))

    def test_crs84_is_preferred_over_other_shared_crs(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>EPSG:3857</CRS><CRS>EPSG:4326</CRS><CRS>CRS:84</CRS>
                <BoundingBox CRS="EPSG:3857" minx="0" miny="0" maxx="2000" maxy="1000"/>
                <BoundingBox CRS="EPSG:4326" minx="0" miny="0" maxx="10" maxy="20"/>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
            </Layer>
        """)

        self.assertEqual(self.params(client.get_preview_request())["CRS"], "CRS:84")

    def test_wms111_uses_geographic_bbox_and_space_separated_srs(self):
        client = self.make_client("""
            <Layer><Name>all</Name><SRS>EPSG:3857 EPSG:4326</SRS>
                <LatLonBoundingBox minx="5" miny="40" maxx="25" maxy="50"/>
            </Layer>
        """, version="1.1.1")

        params = self.params(client.get_preview_request(width=400, height=300))

        self.assertEqual(params["SRS"], "EPSG:4326")
        self.assertNotIn("CRS", params)
        self.assertEqual(self.bbox(params), (5, 40, 25, 50))
        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("400", "200"))
        self.assertEqual(params["EXCEPTIONS"], "application/vnd.ogc.se_xml")

    def test_wms130_geographic_bbox_is_serialized_in_epsg4326_axis_order(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>EPSG:4326</CRS>
                <EX_GeographicBoundingBox>
                    <westBoundLongitude>5</westBoundLongitude><eastBoundLongitude>25</eastBoundLongitude>
                    <southBoundLatitude>40</southBoundLatitude><northBoundLatitude>50</northBoundLatitude>
                </EX_GeographicBoundingBox>
            </Layer>
        """)

        params = self.params(client.get_preview_request(width=400, height=300))

        self.assertEqual(self.bbox(params), (40, 5, 50, 25))
        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("400", "200"))

    def test_native_wms130_bbox_is_not_swapped_again(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>EPSG:4326</CRS>
                <BoundingBox CRS="EPSG:4326" minx="40" miny="5" maxx="50" maxy="25"/>
            </Layer>
        """)

        params = self.params(client.get_preview_request(width=400, height=300))

        self.assertEqual(self.bbox(params), (40, 5, 50, 25))
        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("400", "200"))

    def test_shared_projected_crs_uses_native_bbox_and_fits_portrait_extent(self):
        for crs in ("EPSG:3857", "EPSG:25832"):
            with self.subTest(crs=crs):
                client = self.make_client(f"""
                    <Layer><Name>all</Name><CRS>{crs}</CRS>
                        <BoundingBox CRS="{crs}" minx="0" miny="0" maxx="100" maxy="200"/>
                    </Layer>
                """)

                params = self.params(client.get_preview_request(width=400, height=300))

                self.assertEqual(params["CRS"], crs)
                self.assertEqual(self.bbox(params), (0, 0, 100, 200))
                self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("150", "300"))

    def test_northing_first_projected_bbox_preserves_easting_width(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>EPSG:3044</CRS>
                <BoundingBox CRS="EPSG:3044" minx="5000000" miny="300000" maxx="5000100" maxy="300200"/>
            </Layer>
        """)

        params = self.params(client.get_preview_request(width=400, height=300))

        self.assertEqual(params["CRS"], "EPSG:3044")
        self.assertEqual(self.bbox(params), (5000000, 300000, 5000100, 300200))
        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("400", "200"))

    def test_child_geographic_bounds_override_inherited_bounds(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <EX_GeographicBoundingBox>
                    <westBoundLongitude>-100</westBoundLongitude><eastBoundLongitude>100</eastBoundLongitude>
                    <southBoundLatitude>-50</southBoundLatitude><northBoundLatitude>50</northBoundLatitude>
                </EX_GeographicBoundingBox>
                <Layer><Name>all</Name>
                    <EX_GeographicBoundingBox>
                        <westBoundLongitude>5</westBoundLongitude><eastBoundLongitude>25</eastBoundLongitude>
                        <southBoundLatitude>40</southBoundLatitude><northBoundLatitude>50</northBoundLatitude>
                    </EX_GeographicBoundingBox>
                </Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(self.bbox(params), (5, 40, 25, 50))

    def test_jpeg_is_used_when_png_is_not_advertised(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
            </Layer>
        """, formats=("image/gif", "image/jpeg"))

        params = self.params(client.get_preview_request())

        self.assertEqual(params["FORMAT"], "image/jpeg")
        self.assertEqual(params["TRANSPARENT"], "FALSE")

    def test_advertised_maximum_image_size_is_respected(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
            </Layer>
        """, extra="<MaxWidth>120</MaxWidth><MaxHeight>100</MaxHeight>")

        params = self.params(client.get_preview_request())

        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("120", "60"))

    def test_inherited_fixed_image_size_is_respected(self):
        client = self.make_client("""
            <Layer fixedWidth="120" fixedHeight="60"><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer><Name>all</Name></Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual((params["WIDTH"], params["HEIGHT"]), ("120", "60"))

    def test_incompatible_fixed_sizes_across_layers_are_rejected(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer fixedWidth="120" fixedHeight="60"><Name>roads</Name></Layer>
                <Layer fixedWidth="100" fixedHeight="50"><Name>water</Name></Layer>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_fixed_image_size_exceeding_preview_limits_is_rejected(self):
        client = self.make_client("""
            <Layer fixedWidth="600" fixedHeight="300"><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request(width=512, height=256)

    def test_layer_limit_rejects_too_many_selected_layers(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Layer><Name>roads</Name></Layer>
                <Layer><Name>water</Name></Layer>
            </Layer>
        """, extra="<LayerLimit>1</LayerLimit>")

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_no_subsets_rejects_union_different_from_layer_bounds(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <Layer noSubsets="1"><Name>west</Name>
                    <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="10" maxy="10"/>
                </Layer>
                <Layer><Name>east</Name>
                    <BoundingBox CRS="CRS:84" minx="10" miny="0" maxx="20" maxy="10"/>
                </Layer>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_inherited_dimension_default_is_left_to_the_server(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Dimension name="time" units="ISO8601" default="2026-10-01">2026-10-01</Dimension>
                <Layer><Name>all</Name></Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "all")
        self.assertNotIn("TIME", params)

    def test_wms111_extent_provides_default_for_dimension_metadata(self):
        client = self.make_client("""
            <Layer><Name>all</Name><SRS>EPSG:4326</SRS>
                <LatLonBoundingBox minx="5" miny="40" maxx="25" maxy="50"/>
                <Dimension name="time" units="ISO8601"/>
                <Extent name="time" default="2026-10-01">2026-10-01</Extent>
            </Layer>
        """, version="1.1.1")

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "all")
        self.assertNotIn("TIME", params)

    def test_wms111_child_dimension_metadata_preserves_inherited_extent_default(self):
        client = self.make_client("""
            <Layer><SRS>EPSG:4326</SRS>
                <LatLonBoundingBox minx="5" miny="40" maxx="25" maxy="50"/>
                <Dimension name="time" units="ISO8601"/>
                <Extent name="time" default="2026-10-01">2026-10-01</Extent>
                <Layer><Name>all</Name><Dimension name="time" units="ISO8601"/></Layer>
            </Layer>
        """, version="1.1.1")

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "all")
        self.assertNotIn("TIME", params)

    def test_wms111_dimension_and_extent_names_match_case_insensitively(self):
        client = self.make_client("""
            <Layer><Name>all</Name><SRS>EPSG:4326</SRS>
                <LatLonBoundingBox minx="5" miny="40" maxx="25" maxy="50"/>
                <Dimension name="TiMe" units="ISO8601"/>
                <Extent name="time" default="2026-10-01">2026-10-01</Extent>
            </Layer>
        """, version="1.1.1")

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "all")
        self.assertNotIn("TIME", params)

    def test_named_child_supplies_default_for_inherited_dimension(self):
        client = self.make_client("""
            <Layer><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Dimension name="time" units="ISO8601">2026-10-01</Dimension>
                <Layer><Name>all</Name>
                    <Dimension name="time" units="ISO8601" default="2026-10-01">2026-10-01</Dimension>
                </Layer>
            </Layer>
        """)

        params = self.params(client.get_preview_request())

        self.assertEqual(params["LAYERS"], "all")
        self.assertNotIn("TIME", params)

    def test_dimension_without_default_is_rejected(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                <Dimension name="time" units="ISO8601">2026-10-01</Dimension>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_xml_exception_format_must_be_advertised(self):
        for exception_formats in ((), ("INIMAGE",)):
            with self.subTest(exception_formats=exception_formats):
                client = self.make_client("""
                    <Layer><Name>all</Name><CRS>CRS:84</CRS>
                        <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                    </Layer>
                """, exception_formats=exception_formats)

                with self.assertRaises(ValueError):
                    client.get_preview_request()

    def test_preview_requires_a_named_layer(self):
        with self.assertRaises(ValueError):
            self.make_client("<Layer><Title>Unnamed root</Title></Layer>").get_preview_request()

    def test_preview_requires_a_crs_shared_by_all_selected_layers(self):
        client = self.make_client("""
            <Layer>
                <Layer><Name>west</Name><CRS>CRS:84</CRS>
                    <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                </Layer>
                <Layer><Name>east</Name><CRS>EPSG:3857</CRS>
                    <BoundingBox CRS="EPSG:3857" minx="0" miny="0" maxx="2000" maxy="1000"/>
                </Layer>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_geographic_bounds_do_not_imply_support_for_a_geographic_crs(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>EPSG:3857</CRS>
                <EX_GeographicBoundingBox>
                    <westBoundLongitude>5</westBoundLongitude><eastBoundLongitude>25</eastBoundLongitude>
                    <southBoundLatitude>40</southBoundLatitude><northBoundLatitude>50</northBoundLatitude>
                </EX_GeographicBoundingBox>
            </Layer>
        """)

        with self.assertRaises(ValueError):
            client.get_preview_request()

    def test_preview_requires_extent_and_supported_image_format(self):
        for layers, formats in (
            ("<Layer><Name>all</Name><CRS>CRS:84</CRS></Layer>", ("image/png",)),
            ("""<Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
                </Layer>""", ("application/pdf",)),
        ):
            with self.subTest(layers=layers, formats=formats), self.assertRaises(ValueError):
                self.make_client(layers, formats=formats).get_preview_request()

    def test_invalid_or_incomplete_bbox_is_rejected(self):
        for attributes in (
            'minx="NaN" miny="0" maxx="20" maxy="10"',
            'minx="0" miny="0" maxx="20"',
        ):
            with self.subTest(attributes=attributes):
                client = self.make_client(f"""
                    <Layer><Name>all</Name><CRS>CRS:84</CRS>
                        <BoundingBox CRS="CRS:84" {attributes}/>
                    </Layer>
                """)

                with self.assertRaises(ValueError):
                    client.get_preview_request()

    def test_preview_requires_positive_dimensions(self):
        client = self.make_client("""
            <Layer><Name>all</Name><CRS>CRS:84</CRS>
                <BoundingBox CRS="CRS:84" minx="0" miny="0" maxx="20" maxy="10"/>
            </Layer>
        """)

        for width, height in ((0, 256), (512, 0), (-1, 256), (512, -1)):
            with self.subTest(width=width, height=height), self.assertRaises(ValueError):
                client.get_preview_request(width=width, height=height)

    def test_get_map_serializes_numeric_bbox_and_transparency(self):
        client = self.make_client("<Layer><Name>all</Name></Layer>")

        for transparent, expected in ((True, "TRUE"), (False, "FALSE"), (None, None)):
            with self.subTest(transparent=transparent):
                params = self.params(client.get_map_request(
                    layers=["all"], styles=[""], crs="CRS:84", bbox=(1.5, 2.5, 3.5, 4.5),
                    width=512, height=256, format="image/png", transparent=transparent))

                self.assertEqual(self.bbox(params), (1.5, 2.5, 3.5, 4.5))
                if expected is None:
                    self.assertNotIn("TRANSPARENT", params)
                else:
                    self.assertEqual(params["TRANSPARENT"], expected)
