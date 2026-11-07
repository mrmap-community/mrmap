from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from django.contrib.gis.geos import Polygon
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from registry.models.metadata import ReferenceSystem
from registry.models.monitoring import (GetMapProbe,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebMapService
from registry.ows_lib.wms.wms import WebMapServiceClient


def capabilities(version: str, layers: str, get_map_formats="image/png"):
    """A minimal capabilities document with the given Layer tree."""
    namespace = 'xmlns="http://www.opengis.net/wms"' if version == "1.3.0" else ""
    root = "WMS_Capabilities" if version == "1.3.0" else "WMT_MS_Capabilities"
    formats = "".join(f"<Format>{value}</Format>" for value in get_map_formats.split(","))
    return f"""
        <{root} version="{version}" {namespace} xmlns:xlink="http://www.w3.org/1999/xlink">
            <Service><Name>WMS</Name><Title>t</Title><Abstract>a</Abstract></Service>
            <Capability><Request>
                <GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>
                    <OnlineResource xlink:href="https://registered.example/capabilities?"/>
                </Get></HTTP></DCPType></GetCapabilities>
                <GetMap>{formats}<DCPType><HTTP><Get>
                    <OnlineResource xlink:href="https://registered.example/wms?"/>
                </Get></HTTP></DCPType></GetMap>
            </Request>{layers}</Capability>
        </{root}>
    """.encode()


def params_of(request) -> dict:
    return {key: values[0] for key, values in parse_qs(
        urlparse(request.url).query, keep_blank_values=True).items()}


class GetMapProbeParameterSurvivalTest(TestCase):
    """The configured parameters of a GetMapProbe reach the request.

    The probe is built by the same abstraction the generator proposes its
    parameters for: what the preview promises, the executing probe must send.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        self.wms = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        self.interval = IntervalSchedule.objects.create(every=1, period="days")
        self.setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms, interval=self.interval)
        self.epsg_4326 = ReferenceSystem.objects.get(prefix="EPSG", code="4326")
        self.epsg_3857 = ReferenceSystem.objects.create(prefix="EPSG", code="3857")
        self.crs_84 = ReferenceSystem.objects.create(prefix="CRS", code="84")

    def layer(self, identifier) -> Layer:
        return self.wms.layers.get(identifier=identifier)

    def configured_bbox(self) -> Polygon:
        bbox = Polygon.from_bbox((3.0, 1.0, 4.0, 2.0))
        bbox.srid = 4326
        return bbox

    def probe(self, identifiers, **kwargs) -> GetMapProbe:
        probe = GetMapProbe.objects.create(setting=self.setting, **kwargs)
        probe.layers.set([self.layer(name) for name in identifiers])
        return probe

    def wms_client(self, version, layers) -> WebMapServiceClient:
        return WebMapServiceClient(
            capabilities=capabilities(version, layers), session=Mock())

    def build_params(self, probe, client) -> dict:
        return params_of(probe.build_request(client))

    def test_configured_bbox_survives_in_all_versions_and_crs(self):
        cases = [
            ("1.3.0", self.crs_84, "3.0,1.0,4.0,2.0"),
            ("1.3.0", self.epsg_4326, "1.0,3.0,2.0,4.0"),
            ("1.1.1", self.epsg_4326, "3.0,1.0,4.0,2.0"),
        ]
        for version, reference_system, expected in cases:
            with self.subTest(version=version, crs=str(reference_system)):
                probe = self.probe(
                    ["node1"], bbox_lat_lon=self.configured_bbox(),
                    reference_system=reference_system)
                params = self.build_params(probe, self.wms_client(
                    version, "<Layer><Name>node1</Name></Layer>"))

                self.assertEqual(params["BBOX"], expected)
                self.assertEqual(
                    params["CRS" if version == "1.3.0" else "SRS"],
                    str(reference_system))

    def test_configured_bbox_is_transformed_for_a_projected_crs(self):
        probe = self.probe(
            ["node1"], bbox_lat_lon=self.configured_bbox(),
            reference_system=self.epsg_3857)

        params = self.build_params(probe, self.wms_client(
            "1.3.0", "<Layer><Name>node1</Name></Layer>"))

        self.assertEqual(params["CRS"], "EPSG:3857")
        values = [float(value) for value in params["BBOX"].split(",")]
        self.assertAlmostEqual(values[0], 333958.47, delta=1)
        self.assertAlmostEqual(values[2], 445277.96, delta=1)

    def test_missing_configured_bbox_falls_back_to_the_inherited_extent(self):
        # node1.1 has no own extent; the stored extent of node1 is inherited
        version = "1.3.0"
        probe = self.probe(
            ["node1.1"], reference_system=self.epsg_4326)
        client = self.wms_client(
            version, """
            <Layer><Name>node1</Name><CRS>EPSG:4326</CRS>
                <EX_GeographicBoundingBox>
                    <westBoundLongitude>5</westBoundLongitude>
                    <eastBoundLongitude>16</eastBoundLongitude>
                    <southBoundLatitude>47</southBoundLatitude>
                    <northBoundLatitude>55</northBoundLatitude>
                </EX_GeographicBoundingBox>
                <Layer><Name>node1.1</Name></Layer>
            </Layer>""")

        params = self.build_params(probe, client)

        # the DB bbox of node1 is what the CTE inherits into node1.1
        inherited = Layer.objects.with_inherited_attributes_cte().get(
            pk=self.layer("node1.1").pk).bbox_lat_lon_inherited
        self.assertEqual(
            params["BBOX"],
            f"{inherited.extent[1]},{inherited.extent[0]},"
            f"{inherited.extent[3]},{inherited.extent[2]}")

    def test_advertised_native_bbox_wins_over_the_geographic_extent(self):
        probe = self.probe(["node1"], reference_system=self.epsg_3857)
        client = self.wms_client("1.3.0", """
            <Layer><Name>node1</Name><CRS>EPSG:3857</CRS>
                <BoundingBox CRS="EPSG:3857" minx="1" miny="2" maxx="3" maxy="4"/>
            </Layer>""")

        params = self.build_params(probe, client)

        self.assertEqual(params["BBOX"], "1.0,2.0,3.0,4.0")

    def test_styles_follow_the_configured_layers_in_order(self):
        # node1 advertises "style node 1" in the registry fixtures, node1.1
        # inherits it and node1.2 is styled by its own document style
        probe = self.probe(["node1", "node1.1"])

        params = self.build_params(probe, self.wms_client(
            "1.3.0", """
            <Layer><Name>node1</Name><CRS>CRS:84</CRS>
                <Style><Name>style node 1</Name><Title>s1</Title></Style>
                <Layer><Name>node1.1</Name></Layer>
            </Layer>"""))

        # the tree orders node1 before node1.1 and the styles stay aligned
        self.assertEqual(params["LAYERS"], "node1,node1.1")
        self.assertEqual(params["STYLES"], "style node 1,style node 1")

    def test_layer_without_any_advertised_style_keeps_the_server_default(self):
        from registry.models.metadata import Style
        Style.objects.filter(layer=self.layer("node1")).delete()

        probe = self.probe(["node1.1"])

        params = self.build_params(probe, self.wms_client(
            "1.3.0", "<Layer><Name>node1</Name><CRS>CRS:84</CRS>"
                     "<Layer><Name>node1.1</Name></Layer></Layer>"))

        self.assertEqual(params["STYLES"], "")

    def test_configured_timeout_and_format_reach_the_request(self):
        from registry.models.metadata import MimeType
        probe = self.probe(
            ["node1"], timeout=17, width=640, height=480,
            format=MimeType.objects.get(mime_type="image/png"))

        params = self.build_params(probe, self.wms_client(
            "1.1.1", "<Layer><Name>node1</Name></Layer>"))

        self.assertEqual(probe.timeout, 17)
        self.assertEqual(params["FORMAT"], "image/png")
        self.assertEqual(params["WIDTH"], "640")
        self.assertEqual(params["HEIGHT"], "480")
