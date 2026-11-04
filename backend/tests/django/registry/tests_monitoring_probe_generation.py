"""Tests of the bounded WMS monitoring probe generation from stored capabilities.

The generator is the transient heart of the monitoring preview endpoint: it
must propose deterministic, protocol correct GetMap candidates from the
STORED capabilities without ever writing settings or contacting the service.
These tests exercise it directly; the HTTP contract around it is covered in
tests_monitoring_probe_preview_api.py.
"""
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from registry.helper.monitoring_generation import (
    COMPREHENSIVE_OPERATIONS, DEFAULT_PROBE_LIMIT, GENERATOR_VERSION,
    MAX_PROBES, SkipReason, candidate_identifier, generate_probe_preview)
from registry.helper.preview import PreviewError
from registry.models.monitoring import (GetMapProbe,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import Layer, WebFeatureService, WebMapService

WMS = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS_WITHOUT_CAPABILITIES = '1b195589-dcfa-403f-9e66-e7e1c0a67024'
WFS = '73cf78c9-6605-47fd-ac4f-1be59265df65'

LAYER_ORDER = ['node1', 'node1.1', 'node1.1.1', 'node1.1.2',
               'node1.1.3', 'node1.2', 'node1.3', 'node1.3.1']


def capabilities(version, layers, get_map_formats="image/png image/jpeg",
                 get_map=True, get_capabilities=True, exceptions=True,
                 get_map_verb="Get"):
    """A minimal capabilities document wrapping the given Layer tree."""
    formats = "".join(f"<Format>{value}</Format>" for value in get_map_formats.split())
    get_capabilities_block = """
        <GetCapabilities><Format>text/xml</Format><DCPType><HTTP><Get>
            <OnlineResource xlink:href="https://registered.example/capabilities?"/>
        </Get></HTTP></DCPType></GetCapabilities>""" if get_capabilities else ""
    get_map_block = f"""
        <GetMap>{formats}<DCPType><HTTP><{get_map_verb}>
            <OnlineResource xlink:href="https://registered.example/wms?"/>
        </{get_map_verb}></HTTP></DCPType></GetMap>""" if get_map else ""
    exception_block = "<Exception><Format>XML</Format></Exception>" if exceptions else ""
    return f"""
        <WMS_Capabilities version="{version}" xmlns:xlink="http://www.w3.org/1999/xlink">
            <Capability><Request>{get_capabilities_block}{get_map_block}</Request>
                {exception_block}
                {layers}
            </Capability>
        </WMS_Capabilities>""".encode()


def layer_tree(crs_qp, style=True, crs="CRS:84 EPSG:4326 EPSG:4258 EPSG:3857",
               extra="", identifiers=LAYER_ORDER, native_bbox=True):
    """The capabilities tree matching the layer names of the WMS fixtures.

    Every other layer is nested under the node named after the first
    identifier, so the CRS, styles, native bounding boxes and dimensions of
    that node are inherited exactly like the registry models inherit their
    own values.
    """
    children = "".join(f"<Layer><Name>{name}</Name></Layer>"
                       for name in identifiers[1:])
    styles = ("<Style><Name>style node 1</Name><Title>s1</Title></Style>"
              "<Style><Name>other style</Name><Title>s2</Title></Style>") if style else ""
    bbox = (f'<BoundingBox {crs_qp}="EPSG:3857" minx="100000.0" miny="5000000.0" '
            'maxx="200000.0" maxy="6000000.0"/>') if native_bbox else ""
    return f"""
        <Layer><Name>{identifiers[0]}</Name>
            {styles}
            <{crs_qp}>{crs}</{crs_qp}>
            {bbox}
            {extra}
            {children}
        </Layer>"""


def params_of(url) -> dict:
    return {key: values[0] for key, values in parse_qs(
        urlsplit(url).query, keep_blank_values=True).items()}


class MonitoringProbeGenerationTest(TestCase):
    """The generator proposes protocol correct probes from the stored state."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs_proxy.json']

    def setUp(self):
        self.wms = WebMapService.objects.get(pk=WMS)
        # the fixtures ship one deactivated layer; the generator honours that,
        # so activate the whole tree to get a deterministic baseline
        self.wms.layers.update(is_active=True)
        self.store("1.3.0", layer_tree("CRS"))

    def store(self, version, layers, document=None, **kwargs):
        self.wms.version = int(version.replace(".", ""))
        self.wms.xml_backup_file = SimpleUploadedFile(
            'probe-preview.xml', document or capabilities(version, layers, **kwargs))
        self.wms.save()

    def generate(self, **params):
        return generate_probe_preview(self.wms, params)

    def errors(self, **params):
        with self.assertRaises(PreviewError) as caught:
            self.generate(**params)
        return caught.exception

    def get_map_probes(self, result):
        return [probe for probe in result["probes"] if probe["probeType"] == "GetMap"]

    def skip_reasons(self, result):
        return {skip["reason"] for skip in result["skipped"]}

    def skipped_layers(self, result, reason):
        return [skip["layer"] for skip in result["skipped"] if skip["reason"] == reason]

    # --- presets, ordering and stable identities ---------------------------

    def test_standard_preset_proposes_one_probe_per_layer_in_tree_order(self):
        result = self.generate(preset="standard")

        self.assertEqual(result["preset"], "standard")
        self.assertEqual(result["generatorVersion"], GENERATOR_VERSION)
        self.assertEqual(result["wmsVersion"], "1.3.0")
        self.assertEqual([probe["probeType"] for probe in result["probes"]][0],
                         "GetCapabilities")
        self.assertEqual([probe["targetLayer"]["identifier"]
                          for probe in self.get_map_probes(result)], LAYER_ORDER)
        self.assertEqual(result["pagination"]["totalGetMapCandidates"], len(LAYER_ORDER))
        self.assertFalse(result["pagination"]["truncated"])

    def test_basic_preset_stays_at_the_representative_layer(self):
        result = self.generate(preset="basic")

        get_map = self.get_map_probes(result)
        self.assertEqual(len(get_map), 1)
        self.assertEqual(get_map[0]["targetLayer"]["identifier"], "node1")
        # the scan still saw every candidate, the preset just proposes less
        self.assertEqual(result["pagination"]["totalGetMapCandidates"], len(LAYER_ORDER))

    def test_default_preset_is_standard(self):
        self.assertEqual(self.generate()["preset"], "standard")

    def test_candidate_identity_is_independent_of_preset_and_parameters(self):
        basic = self.generate(preset="basic")
        standard = self.generate(preset="standard")

        basic_probe = self.get_map_probes(basic)[0]
        same_in_standard = next(
            probe for probe in self.get_map_probes(standard)
            if probe["targetLayer"]["identifier"]
            == basic_probe["targetLayer"]["identifier"])
        self.assertEqual(basic_probe["candidateId"], same_in_standard["candidateId"])
        self.assertEqual(basic_probe["candidateId"],
                         candidate_identifier("GetMap", ["node1"]))
        # the GetCapabilities candidate is one identity across the service
        self.assertNotEqual(
            basic["probes"][0]["candidateId"], basic_probe["candidateId"])

    def test_generation_is_deterministic(self):
        self.assertEqual(self.generate(preset="standard"),
                         self.generate(preset="standard"))

    # --- version and CRS dependent BBOX serialization ----------------------

    def test_probe_serializes_bbox_like_the_executing_probe_would(self):
        result = self.generate(preset="basic")

        probe = self.get_map_probes(result)[0]
        params = params_of(probe["requestSummary"]["url"])
        self.assertEqual(probe["parameters"]["crs"], "CRS:84")
        self.assertEqual(probe["parameters"]["axisOrder"], "xy")
        self.assertEqual(probe["parameters"]["bbox"], [-180.0, -90.0, 180.0, 90.0])
        self.assertEqual(params["BBOX"], "-180.0,-90.0,180.0,90.0")
        self.assertEqual(params["CRS"], "CRS:84")
        self.assertEqual(params["LAYERS"], "node1")
        self.assertEqual(params["STYLES"], "style node 1")
        self.assertEqual(params["VERSION"], "1.3.0")
        self.assertEqual(params["EXCEPTIONS"], "XML")
        self.assertEqual(probe["requestSummary"]["method"], "GET")
        self.assertEqual(urlsplit(probe["requestSummary"]["url"]).path, "/wms")

    def test_geographic_crs_is_axis_swapped_for_130_only(self):
        for version, expected_bbox, crs_key, exceptions in [
                ("1.3.0", "-90.0,-180.0,90.0,180.0", "CRS", "XML"),
                ("1.1.1", "-180.0,-90.0,180.0,90.0", "SRS",
                 "application/vnd.ogc.se_xml")]:
            with self.subTest(version=version):
                self.store(version, layer_tree(
                    "SRS" if version == "1.1.1" else "CRS", crs="EPSG:4326"),
                    exceptions=False)

                probe = self.get_map_probes(self.generate(preset="basic"))[0]

                params = params_of(probe["requestSummary"]["url"])
                self.assertEqual(params[crs_key], "EPSG:4326")
                self.assertEqual(params["BBOX"], expected_bbox)
                self.assertEqual(probe["parameters"]["axisOrder"],
                                 "yx" if version == "1.3.0" else "xy")
                self.assertEqual(params["EXCEPTIONS"], exceptions)

    def test_native_bounding_box_is_taken_verbatim(self):
        # the capabilities BoundingBox already carries the protocol axis order
        probe = self.get_map_probes(self.generate(
            preset="basic", crs="EPSG:3857"))[0]

        params = params_of(probe["requestSummary"]["url"])
        self.assertEqual(probe["parameters"]["requestBbox"],
                         [100000.0, 5000000.0, 200000.0, 6000000.0])
        self.assertEqual(params["BBOX"], "100000.0,5000000.0,200000.0,6000000.0")
        # the geographic extent stays reported next to the request values
        self.assertEqual(probe["parameters"]["bbox"], [-180.0, -90.0, 180.0, 90.0])

    def test_crs_override_is_applied_and_validated_against_the_advertisement(self):
        probe = self.get_map_probes(self.generate(preset="basic", crs="epsg:4258"))[0]
        self.assertEqual(probe["parameters"]["crs"], "EPSG:4258")

        self.store("1.3.0", layer_tree("CRS", crs="CRS:84"))
        result = self.generate(preset="basic", crs="EPSG:4326")
        self.assertEqual(self.skip_reasons(result), {SkipReason.UNSUPPORTED_CRS})
        self.assertEqual(self.get_map_probes(result), [])

    def test_layers_without_advertised_crs_are_skipped(self):
        self.store("1.3.0", layer_tree("CRS", crs=""))

        result = self.generate(preset="standard")

        self.assertEqual(self.skip_reasons(result), {SkipReason.UNSUPPORTED_CRS})
        self.assertEqual(self.get_map_probes(result), [])

    def test_projected_crs_without_native_bbox_never_becomes_a_probe(self):
        self.store("1.3.0", layer_tree("CRS", crs="EPSG:4326 EPSG:3857",
                                       native_bbox=False))

        result = self.generate(preset="standard")

        # only the geographic CRS is serializable, so it is chosen for all
        self.assertEqual(result["skipped"], [])
        self.assertTrue(all(probe["parameters"]["crs"] == "EPSG:4326"
                            for probe in self.get_map_probes(result)))

    # --- inherited and per-layer values --------------------------------------

    def test_styles_and_dimensions_of_ancestors_are_inherited(self):
        probe = self.get_map_probes(self.generate(
            preset="standard", layer="node1.3.1"))[0]

        self.assertEqual(probe["parameters"]["styles"], ["style node 1"])
        self.assertEqual(probe["supported"]["styles"], ["style node 1", "other style"])
        self.assertEqual(probe["supported"]["formats"], ["image/png", "image/jpeg"])
        self.assertIn("CRS:84", probe["supported"]["crs"])

    def test_format_override_selects_an_advertised_image_format(self):
        probe = self.get_map_probes(self.generate(
            preset="basic", imageFormat="image/jpeg"))[0]

        self.assertEqual(probe["parameters"]["format"], "image/jpeg")
        self.assertEqual(params_of(probe["requestSummary"]["url"])["FORMAT"],
                         "image/jpeg")

    def test_svg_is_never_proposed_as_an_image_format(self):
        self.store("1.3.0", layer_tree("CRS"),
                   get_map_formats="image/svg+xml image/png")

        result = self.generate(preset="basic")

        self.assertEqual(self.get_map_probes(result)[0]["parameters"]["format"],
                         "image/png")

    # --- dimensions ----------------------------------------------------------

    def test_advertised_dimension_default_omits_the_request_value(self):
        self.store("1.3.0", layer_tree("CRS", extra=(
            '<Dimension name="time" units="ISO8601" default="2020-01-01">'
            '2020-01-01/2020-12-01/P1M</Dimension>')))

        probe = self.get_map_probes(self.generate(preset="basic"))[0]

        self.assertEqual(probe["parameters"]["dimensionDefaults"],
                         {"time": "2020-01-01"})
        self.assertNotIn("time", probe["parameters"])
        self.assertNotIn("TIME", params_of(probe["requestSummary"]["url"]))

    def test_required_dimension_is_requested_with_its_first_advertised_value(self):
        self.store("1.3.0", layer_tree("CRS", extra=(
            '<Dimension name="time" units="ISO8601">'
            '2020-06-01,2020-01-01</Dimension>')))

        probe = self.get_map_probes(self.generate(preset="basic"))[0]

        self.assertEqual(probe["parameters"]["time"], ["2020-06-01"])
        self.assertEqual(params_of(probe["requestSummary"]["url"])["TIME"], "2020-06-01")

    def test_111_extent_values_are_used_for_a_required_dimension(self):
        self.store("1.1.1", layer_tree(
            "SRS", crs="CRS:84 EPSG:4326", extra=(
                '<Dimension name="elevation" units="DEGREES"/>'
                '<Extent name="elevation">5.0, 10.0</Extent>')))

        probe = self.get_map_probes(self.generate(preset="basic"))[0]

        self.assertEqual(probe["parameters"]["elevation"], 5.0)
        self.assertEqual(params_of(probe["requestSummary"]["url"])["ELEVATION"], "5.0")

    def test_dimension_the_request_abstraction_cannot_express_is_skipped(self):
        self.store("1.3.0", layer_tree("CRS", extra=(
            '<Dimension name="reference_time" default="2020-01-01"/>')))

        result = self.generate(preset="standard")

        self.assertEqual(self.skip_reasons(result), {SkipReason.UNSUPPORTED_DIMENSION})
        self.assertEqual(self.skipped_layers(
            result, SkipReason.UNSUPPORTED_DIMENSION), LAYER_ORDER)

    def test_required_dimension_without_any_value_is_skipped(self):
        self.store("1.3.0", layer_tree("CRS", extra='<Dimension name="time"/>'))

        result = self.generate(preset="standard")

        self.assertEqual(self.skip_reasons(result), {SkipReason.UNAVAILABLE_DIMENSION})

    # --- explicit skip reasons -----------------------------------------------

    def test_layer_without_identifier_is_a_group_layer(self):
        self.wms.layers.filter(identifier="node1.1.2").update(identifier="")

        result = self.generate(preset="standard")

        self.assertIn(SkipReason.GROUP_LAYER, self.skip_reasons(result))
        self.assertNotIn("node1.1.2", [
            probe["targetLayer"]["identifier"] for probe in self.get_map_probes(result)])

    def test_deactivated_layer_is_skipped(self):
        self.wms.layers.filter(identifier="node1.2").update(is_active=False)

        result = self.generate(preset="standard")

        self.assertEqual(self.skipped_layers(result, SkipReason.INACTIVE), ["node1.2"])
        self.assertEqual(result["pagination"]["totalGetMapCandidates"], len(LAYER_ORDER) - 1)

    def test_layer_the_stored_capabilities_do_not_advertise_anymore_is_stale(self):
        self.store("1.3.0", layer_tree("CRS", identifiers=LAYER_ORDER[:-2]))

        result = self.generate(preset="standard")

        self.assertEqual(
            self.skipped_layers(result, SkipReason.STALE),
            [LAYER_ORDER[-2], LAYER_ORDER[-1]])

    def test_layer_without_stated_or_inherited_extent_is_skipped(self):
        Layer.objects.filter(service=self.wms).update(bbox_lat_lon=None)

        result = self.generate(preset="standard")

        self.assertEqual(self.skip_reasons(result), {SkipReason.NO_EXTENT})
        self.assertEqual(result["pagination"]["totalGetMapCandidates"], 0)

    def test_layer_with_fixed_image_dimensions_needs_exactly_them(self):
        self.store("1.3.0", layer_tree("CRS").replace(
            "<Layer>", '<Layer fixedWidth="512" fixedHeight="512">', 1))

        result = self.generate(preset="standard")
        self.assertEqual(
            self.skipped_layers(result, SkipReason.FIXED_DIMENSIONS), LAYER_ORDER)

        result = self.generate(preset="standard", width=512, height=512)
        self.assertNotIn(SkipReason.FIXED_DIMENSIONS, self.skip_reasons(result))

    def test_service_without_gettable_getmap_endpoint_proposes_no_map_probe(self):
        # the GetMap formats are advertised but only via POST: the probe
        # abstraction reads a plain GET url and must report the missing verb
        self.store("1.3.0", layer_tree("CRS"), get_map_verb="Post")

        result = self.generate(preset="standard")

        self.assertEqual(self.get_map_probes(result), [])
        self.assertIn(SkipReason.OPERATION_UNSUPPORTED, self.skip_reasons(result))

    def test_service_without_advertised_getcapabilities_endpoint_reports_the_skip(self):
        self.store("1.3.0", layer_tree("CRS"), get_capabilities=False)

        result = self.generate(preset="basic")

        self.assertEqual([probe["probeType"] for probe in result["probes"]], ["GetMap"])
        self.assertIn(SkipReason.OPERATION_UNSUPPORTED, self.skip_reasons(result))

    def test_skips_are_reported_with_an_explicit_detail(self):
        self.wms.layers.filter(identifier="node1.2").update(is_active=False)

        skip = next(skip for skip in self.generate(preset="standard")["skipped"]
                    if skip["layer"] == "node1.2")
        self.assertEqual(skip["reason"], SkipReason.INACTIVE)
        self.assertTrue(skip["detail"])

    # --- selection and pagination ---------------------------------------------

    def test_explicit_layer_selection_accepts_identifier_and_primary_key(self):
        layer = self.wms.layers.get(identifier="node1.2")

        for selection in ("node1.2", str(layer.pk)):
            with self.subTest(selection=selection):
                result = self.generate(preset="standard", layer=selection)

                self.assertEqual(
                    [probe["targetLayer"]["identifier"]
                     for probe in self.get_map_probes(result)], ["node1.2"])

    def test_selection_of_an_unknown_layer_is_reported_without_losing_the_known_one(self):
        result = self.generate(preset="standard", layer=["node1.2", "does-not-exist"])

        self.assertEqual(
            [probe["targetLayer"]["identifier"] for probe in self.get_map_probes(result)],
            ["node1.2"])
        self.assertEqual(self.skipped_layers(result, SkipReason.UNKNOWN_LAYER),
                         ["does-not-exist"])

    def test_pagination_pages_over_the_deterministic_candidates(self):
        first = self.generate(preset="standard", offset=0, limit=3)
        second = self.generate(preset="standard", offset=3, limit=3)

        self.assertEqual([probe["targetLayer"]["identifier"]
                          for probe in self.get_map_probes(first)], LAYER_ORDER[:3])
        self.assertEqual([probe["targetLayer"]["identifier"]
                          for probe in self.get_map_probes(second)], LAYER_ORDER[3:6])
        self.assertTrue(first["pagination"]["truncated"])
        self.assertEqual(first["pagination"]["limit"], 3)

    def test_pagination_reports_when_a_large_service_requires_selection(self):
        with patch("registry.helper.monitoring_generation.MAX_PROBES", 2):
            without_selection = self.generate(preset="standard", limit=2)
            with_selection = self.generate(preset="standard", layer="node1", limit=2)

        self.assertTrue(without_selection["pagination"]["selectionRequired"])
        self.assertFalse(with_selection["pagination"]["selectionRequired"])

    # --- bounds and invalid input ----------------------------------------------

    def test_documented_bounds_are_answered(self):
        bounds = self.generate()["bounds"]

        self.assertEqual(bounds["defaultLimit"], DEFAULT_PROBE_LIMIT)
        self.assertEqual(bounds["maxProbes"], MAX_PROBES)
        self.assertEqual(bounds["maxImageDimension"], 2048)
        self.assertEqual(bounds["maxTimeout"], 120)
        self.assertEqual(bounds["maxResponseBytes"], 8 * 1024 * 1024)

    def test_request_parameters_are_echoed(self):
        result = self.generate(width=128, height=64, timeout=45, preset="standard")

        self.assertEqual(result["request"], {
            "width": 128, "height": 64, "timeout": 45,
            "format": None, "crs": None})
        probe = self.get_map_probes(result)[0]
        self.assertEqual(probe["parameters"]["width"], 128)
        self.assertEqual(probe["parameters"]["timeout"], 45)

    def test_oversized_image_and_timeout_are_rejected(self):
        for params, code in [({"width": 4000}, "limit"), ({"timeout": 121}, "limit"),
                             ({"height": "abc"}, "malformed"), ({"limit": 0}, "limit")]:
            with self.subTest(**params):
                error = self.errors(**params)
                self.assertEqual(error.code, code)
                self.assertEqual(error.status, 400)

    def test_offset_must_be_a_non_negative_number(self):
        for offset in ("-1", "many"):
            with self.subTest(offset=offset):
                self.assertEqual(self.errors(offset=offset).code, "offset")

    def test_crs_override_must_name_a_coded_crs(self):
        self.assertEqual(self.errors(crs="urn:ogc:def:crs:EPSG::4326").code,
                         "crsOverride")

    def test_format_override_must_be_an_advertised_image_format(self):
        self.assertEqual(self.errors(imageFormat="image/tiff").code, "formatOverride")

    def test_service_without_any_advertised_image_format_is_reported(self):
        self.store("1.3.0", layer_tree("CRS"), get_map_formats="text/html")

        error = self.errors()
        self.assertEqual(error.code, "noImageFormat")
        self.assertEqual(error.status, 422)

    def test_comprehensive_preset_is_reported_as_not_implemented(self):
        error = self.errors(preset="comprehensive")

        self.assertEqual(error.code, "presetNotImplemented")
        self.assertEqual(error.status, 400)

    def test_the_contract_reports_which_presets_are_implemented(self):
        result = self.generate()

        self.assertEqual(result["presets"], {
            "implemented": ["basic", "standard"], "notImplemented": ["comprehensive"]})
        self.assertEqual(result["notImplemented"]["preset"], "comprehensive")
        self.assertEqual(result["notImplemented"]["operations"],
                         list(COMPREHENSIVE_OPERATIONS))

    def test_unknown_preset_is_rejected(self):
        self.assertEqual(self.errors(preset="kitchen-sink").code, "preset")

    def test_missing_stored_capabilities_never_fall_back_to_the_service(self):
        service = WebMapService.objects.get(pk=WMS_WITHOUT_CAPABILITIES)

        with patch("requests.sessions.Session.send") as send:
            with self.assertRaises(PreviewError) as caught:
                generate_probe_preview(service, {})

        self.assertEqual(caught.exception.code, "discovery")
        send.assert_not_called()

    def test_version_drift_between_registry_and_capabilities_is_discovery(self):
        # the fixtures store the service as 1.3.0, the document says 1.1.1
        self.wms.version = 130
        self.wms.xml_backup_file = SimpleUploadedFile(
            'probe-preview.xml', capabilities("1.1.1", layer_tree("SRS")))
        self.wms.save()

        self.assertEqual(self.errors().code, "discovery")

    def test_malformed_stored_capabilities_are_reported(self):
        self.wms.xml_backup_file = SimpleUploadedFile('broken.xml', b"<Layer><broken>")
        self.wms.save()

        self.assertEqual(self.errors().code, "malformed")

    def test_non_wms_services_are_not_generated_from(self):
        wfs = WebFeatureService.objects.get(pk=WFS)

        with self.assertRaises(PreviewError) as caught:
            generate_probe_preview(wfs, {})
        self.assertEqual(caught.exception.code, "serviceType")

    def test_disabled_service_is_locked(self):
        WebMapService.objects.filter(pk=WMS).update(is_active=False)
        self.wms.refresh_from_db()

        error = self.errors()
        self.assertEqual(error.code, "disabled")
        self.assertEqual(error.status, 423)

    # --- transience -----------------------------------------------------------

    def test_generation_writes_nothing_and_never_contacts_the_service(self):
        counts = {model: model.objects.count() for model in (
            GetMapProbe, WebMapServiceMonitoringSetting, Layer, WebMapService)}
        historical = WebMapService.history.count()

        with patch("requests.sessions.Session.send",
                   side_effect=AssertionError("preview must not contact the service")
                   ) as send:
            for _ in range(2):
                self.generate(preset="standard")

        send.assert_not_called()
        for model, count in counts.items():
            self.assertEqual(model.objects.count(), count, model)
        self.assertEqual(WebMapService.history.count(), historical)

    def test_credentials_of_an_advertised_endpoint_never_reach_the_summary(self):
        document = capabilities("1.3.0", layer_tree("CRS")).replace(
            b"https://registered.example/wms?",
            b"https://registered-user:registered-pw@registered.example/wms?")
        self.store("1.3.0", None, document=document)

        result = self.generate(preset="standard")

        for probe in self.get_map_probes(result):
            url = probe["requestSummary"]["url"]
            self.assertNotIn("registered-user", url)
            self.assertNotIn("registered-pw", url)
            self.assertIn("registered.example", url)
