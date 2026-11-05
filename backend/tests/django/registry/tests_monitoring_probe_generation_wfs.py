"""Tests of the bounded WFS monitoring probe generation from stored capabilities.

The web feature service sibling of
``tests_monitoring_probe_generation.py``: the generator must propose
deterministic, protocol correct GetCapabilities, GetFeature and — for the
comprehensive preset — DescribeFeatureType candidates from the STORED
capabilities, without ever writing settings or contacting the service.

The assertions follow the acceptance criteria of the story: only versions whose
requests this registry can really build are offered, every GetFeature request
is bounded by the advertised feature types and the count the protocol version
knows, the response format decides which content checks are meaningful, and a
comprehensive operation which the service does not advertise or whose required
parameters can not be satisfied is answered by an explicit skip reason.
"""
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from registry.enums.service import OGCServiceVersionEnum
from registry.helper.monitoring_generation import (
    DEFAULT_PROBE_LIMIT, DEFAULT_TIMEOUT, GENERATOR_VERSION, MAX_PROBES,
    SkipReason, candidate_identifier)
from registry.helper.monitoring_generation_wfs import (
    DEFAULT_MAX_FEATURES, MAX_FEATURES, SUPPORTED_VERSIONS, WfsSkipReason,
    generate_wfs_probe_preview)
from registry.helper.preview import PreviewError
from registry.models.monitoring import (
    WebFeatureServiceGetFeatureProbe, WebFeatureServiceMonitoringSetting)
from registry.models.service import WebFeatureService

WFS = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'

#: the feature types the WMS fixture registers for this service, in the
#: deterministic order of the generator (by identifier)
FEATURE_TYPES = ['node2', 'node3', 'node4', 'wfs1-node1']

#: the version codes the registry stores for the advertised version strings
VERSION_CODES = {label: value
                 for value, label in OGCServiceVersionEnum.choices}

GML = 'application/gml+xml; version=3.2'
JSON = 'application/json'

#: the WFS versions whose documents this generator reads, with the CRS element
#: and the namespaces the protocol version names them with
CRS_ELEMENTS = {"1.1.0": "DefaultSRS", "2.0.0": "DefaultCRS",
                "2.0.2": "DefaultCRS"}
NAMESPACES = {"1.1.0": ("http://www.opengis.net/wfs",
                        "http://www.opengis.net/ows"),
              "2.0.0": ("http://www.opengis.net/wfs/2.0",
                        "http://www.opengis.net/ows/1.1"),
              "2.0.2": ("http://www.opengis.net/wfs/2.0",
                        "http://www.opengis.net/ows/1.1")}


def capabilities(version="2.0.0", feature_types=None, get_capabilities=True,
                 get_feature=True, describe=True,
                 get_feature_formats=(GML, JSON),
                 describe_formats=(GML,), count_default=None,
                 crs="urn:ogc:def:crs:EPSG::4326", per_type_formats=True,
                 endpoint="https://registered.example/wfs?"):
    """A WFS capabilities document with an OWS Common OperationsMetadata.

    Args:
        version (str): the advertised version, decides the CRS element
        feature_types (list): ``(name, formats)`` per FeatureType node; the
            formats fall back to the ones the GetFeature operation advertises
        get_capabilities/get_feature/describe (bool): whether the operation
            advertises a GET endpoint at all
        get_feature_formats/describe_formats (tuple): the outputFormat values
            the operation advertises
        count_default (int): the CountDefault constraint of GetFeature
        per_type_formats (bool): whether the feature types name their own
            OutputFormats
    """
    names = ([name for name in feature_types] if feature_types is not None
             else FEATURE_TYPES)
    operations = ""
    if get_capabilities:
        operations += _operation("GetCapabilities", endpoint, ["text/xml"])
    if get_feature:
        operations += _operation(
            "GetFeature", endpoint, list(get_feature_formats),
            (f'<ows:Constraint name="CountDefault"><ows:DefaultValue>'
             f'{count_default}</ows:DefaultValue></ows:Constraint>'
             if count_default is not None else ""))
    if describe:
        operations += _operation("DescribeFeatureType", endpoint,
                                 list(describe_formats))

    crs_element = CRS_ELEMENTS[version]
    wfs_ns, ows_ns = NAMESPACES[version]
    types = ""
    for name in names:
        formats = (f'<wfs:OutputFormats><wfs:Format>{GML}</wfs:Format>'
                   f'</wfs:OutputFormats>' if per_type_formats else "")
        types += f"""
            <wfs:FeatureType><wfs:Name>{name}</wfs:Name>
                <wfs:Title>{name}</wfs:Title>
                <wfs:{crs_element}>{crs}</wfs:{crs_element}>
                <ows:WGS84BoundingBox>
                    <ows:LowerCorner>3 1</ows:LowerCorner>
                    <ows:UpperCorner>4 2</ows:UpperCorner>
                </ows:WGS84BoundingBox>
                {formats}
            </wfs:FeatureType>"""

    return f"""
        <wfs:WFS_Capabilities version="{version}" serviceType="WFS"
            xmlns:wfs="{wfs_ns}"
            xmlns:ows="{ows_ns}"
            xmlns:xlink="http://www.w3.org/1999/xlink">
            <ows:OperationsMetadata>{operations}</ows:OperationsMetadata>
            <wfs:FeatureTypeList>{types}</wfs:FeatureTypeList>
        </wfs:WFS_Capabilities>""".encode()


def _operation(name, endpoint, formats, extra=""):
    """One OWS Common Operation with a GET endpoint and its outputFormat."""
    values = "".join(f"<ows:Value>{value}</ows:Value>" for value in formats)
    parameter = (f'<ows:Parameter name="outputFormat"><ows:AllowedValues>'
                 f'{values}</ows:AllowedValues></ows:Parameter>'
                 if values else "")
    return (f'<ows:Operation name="{name}"><ows:DCP><ows:HTTP>'
            f'<ows:Get xlink:href="{endpoint}"/></ows:HTTP></ows:DCP>'
            f'{parameter}{extra}</ows:Operation>')


#: a WFS 1.0.0 document as the protocol versions it: the operations are named
#: by the protocol's own elements and no OWS Common OperationsMetadata exists,
#: so no request of a probe can be read out of it
WFS_1_0_0 = """
    <WFS_Capabilities version="1.0.0"
        xmlns="http://www.opengis.net/wfs"
        xmlns:ogc="http://www.opengis.net/ogc"
        xmlns:xlink="http://www.w3.org/1999/xlink">
        <Service><Name>WFS</Name><Title>legacy</Title></Service>
        <Capability>
            <GetCapabilities><DCPType><HTTP><Get>
                <OnlineResource xlink:href="https://registered.example/wfs?"/>
            </Get></HTTP></DCPType></GetCapabilities>
            <GetFeature><ResultFormat><GML3/></ResultFormat><DCPType><HTTP><Get>
                <OnlineResource xlink:href="https://registered.example/wfs?"/>
            </Get></HTTP></DCPType></GetFeature>
        </Capability>
        <FeatureTypeList><FeatureType>
            <Name>node2</Name><Title>node2</Title><SRS>EPSG:4326</SRS>
        </FeatureType></FeatureTypeList>
    </WFS_Capabilities>""".encode()


def params_of(url) -> dict:
    return {key: values[0] for key, values in parse_qs(
        urlsplit(url).query, keep_blank_values=True).items()}


class MonitoringWfsProbeGenerationTest(TestCase):
    """The generator proposes bounded, protocol correct probes from the state."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wfs.json']

    def setUp(self):
        self.wfs = WebFeatureService.objects.get(pk=WFS)
        # the fixture ships one deactivated feature type; activate all of them
        # to get a deterministic baseline
        self.wfs.featuretypes.update(is_active=True)
        self.store("2.0.0")

    def store(self, version, document=None, **kwargs):
        self.wfs.version = VERSION_CODES[version]
        self.wfs.xml_backup_file = SimpleUploadedFile(
            'probe-preview.xml', document or capabilities(version=version,
                                                          **kwargs))
        self.wfs.save()

    def generate(self, **params):
        return generate_wfs_probe_preview(self.wfs, params)

    def errors(self, **params):
        with self.assertRaises(PreviewError) as caught:
            self.generate(**params)
        return caught.exception

    def probes(self, result, probe_type):
        return [probe for probe in result["probes"]
                if probe["probeType"] == probe_type]

    def targets(self, probes):
        return [probe["targetFeatureType"]["identifier"] for probe in probes]

    def skip_reasons(self, result):
        return {skip["reason"] for skip in result["skipped"]}

    def skipped_types(self, result, reason):
        return [skip["featureType"] for skip in result["skipped"]
                if skip["reason"] == reason]

    # --- the honest version matrix -------------------------------------------

    def test_every_offered_version_is_generated_from(self):
        for version in SUPPORTED_VERSIONS:
            with self.subTest(version=version):
                self.store(version)

                result = self.generate(preset="standard")

                self.assertEqual(result["wfsVersion"], version)
                self.assertEqual(result["supportedVersions"],
                                 list(SUPPORTED_VERSIONS))
                # a version the generator offers must answer every operation
                self.assertEqual(result["advertisedOperations"], {
                    "GetCapabilities": True, "GetFeature": True,
                    "DescribeFeatureType": True})
                self.assertEqual(
                    self.targets(self.probes(result, "GetFeature")),
                    FEATURE_TYPES)

    def test_version_1_0_0_is_not_offered(self):
        # a WFS 1.0.0 document has no OWS Common OperationsMetadata, so no
        # request of a probe could be built: the generator must not advertise
        # a version it can not monitor
        self.store("1.0.0", document=WFS_1_0_0)

        error = self.errors()

        self.assertEqual(error.code, "version")
        self.assertEqual(error.status, 422)

    def test_a_version_the_generator_offers_must_be_the_stored_one(self):
        # the registry believes the service is 2.0.0, the document says 2.0.2
        self.wfs.version = VERSION_CODES["2.0.0"]
        self.wfs.xml_backup_file = SimpleUploadedFile(
            'probe-preview.xml', capabilities(version="2.0.2"))
        self.wfs.save()

        self.assertEqual(self.errors().code, "discovery")

    # --- bounded GetFeature requests ------------------------------------------

    def test_get_feature_request_is_bounded_by_feature_type_and_count(self):
        result = self.generate(preset="standard")

        probe = self.probes(result, "GetFeature")[0]
        params = params_of(probe["requestSummary"]["url"])
        self.assertEqual(params["REQUEST"], "GetFeature")
        self.assertEqual(params["SERVICE"], "WFS")
        self.assertEqual(params["VERSION"], "2.0.0")
        self.assertEqual(params["TYPENAMES"], "node2")
        self.assertEqual(params["COUNT"], str(DEFAULT_MAX_FEATURES))
        self.assertEqual(params["SRSNAME"], "EPSG:4326")
        self.assertEqual(params["OUTPUTFORMAT"], GML)
        # the probe names exactly one feature type and stays inside the bounds
        self.assertEqual(probe["parameters"]["featureTypes"], ["node2"])
        self.assertEqual(probe["parameters"]["maxFeatures"], DEFAULT_MAX_FEATURES)
        self.assertNotIn("BBOX", params)

    def test_wfs_1_1_0_is_bounded_by_the_parameter_it_knows(self):
        self.store("1.1.0")

        result = self.generate(preset="standard", maxFeatures=7)

        params = params_of(self.probes(result, "GetFeature")[0]["requestSummary"]["url"])
        self.assertEqual(params["TYPENAME"], "node2")
        self.assertEqual(params["MAXFEATURES"], "7")
        self.assertNotIn("TYPENAMES", params)
        self.assertNotIn("COUNT", params)

    def test_the_advertised_count_bounds_the_proposal(self):
        self.store("2.0.0", count_default=5)

        result = self.generate(preset="standard", maxFeatures=50)

        probe = self.probes(result, "GetFeature")[0]
        self.assertEqual(probe["parameters"]["maxFeatures"], 5)
        self.assertEqual(probe["supported"]["countBound"], 5)
        self.assertEqual(
            params_of(probe["requestSummary"]["url"])["COUNT"], "5")

    def test_max_features_stays_inside_the_documented_bound(self):
        self.assertEqual(self.generate()["bounds"]["maxFeatures"], MAX_FEATURES)
        self.assertEqual(self.errors(maxFeatures=MAX_FEATURES + 1).code, "limit")
        self.assertEqual(self.errors(offset=-1).code, "offset")
        self.assertEqual(self.errors(preset="kitchen-sink").code, "preset")

    # --- response formats and the checks they make possible -------------------

    def test_a_gml_format_is_preferred_and_its_response_is_inspectable(self):
        probe = self.probes(self.generate(preset="standard"), "GetFeature")[0]

        self.assertEqual(probe["parameters"]["outputFormat"], GML)
        self.assertTrue(probe["parameters"]["checkFeatureCollection"])

    def test_an_advertised_json_format_is_not_forced_through_xml_checks(self):
        self.store("2.0.0", get_feature_formats=(JSON,),
                   describe_formats=(JSON,), per_type_formats=False)

        probe = self.probes(self.generate(preset="standard"), "GetFeature")[0]

        self.assertEqual(probe["parameters"]["outputFormat"], JSON)
        self.assertTrue(probe["parameters"]["checkFeatureCollection"])

    def test_an_uninspectable_format_keeps_the_content_checks_at_the_service(self):
        # a document which advertises only a format nobody can parse must not
        # produce a probe whose feature collection check would always fail
        self.store("2.0.0", get_feature_formats=("application/vnd.ogc.wfs_xml",),
                   describe_formats=("application/vnd.ogc.wfs_xml",),
                   per_type_formats=False)

        probe = self.probes(self.generate(preset="standard"), "GetFeature")[0]

        self.assertIsNone(probe["parameters"]["outputFormat"])
        self.assertFalse(probe["parameters"]["checkFeatureCollection"])
        self.assertNotIn("OUTPUTFORMAT",
                         params_of(probe["requestSummary"]["url"]))

    def test_a_feature_type_without_the_overridden_format_is_skipped(self):
        result = self.generate(preset="standard", outputFormat=JSON)

        self.assertEqual(self.skip_reasons(result),
                         {WfsSkipReason.NO_SUPPORTED_FORMAT})
        self.assertEqual(self.skipped_types(result, WfsSkipReason.NO_SUPPORTED_FORMAT),
                         FEATURE_TYPES)

    def test_an_unadvertised_output_format_override_is_refused(self):
        self.assertEqual(self.errors(outputFormat="text/html").code,
                         "formatOverride")

    def test_the_feature_type_formats_win_over_the_operation_formats(self):
        self.store("2.0.0", get_feature_formats=(JSON,), per_type_formats=True)

        probe = self.probes(self.generate(preset="standard"), "GetFeature")[0]

        # the feature type names GML for itself, so GML is what is requested
        self.assertEqual(probe["parameters"]["outputFormat"], GML)

    # --- CRS handling ----------------------------------------------------------

    def test_a_stored_crs_advertised_as_a_urn_is_the_same_system(self):
        # the registry stores EPSG:4326, the document advertises the URN of it
        probe = self.probes(self.generate(preset="standard"), "GetFeature")[0]

        self.assertEqual(probe["parameters"]["crs"], "EPSG:4326")
        self.assertIn("EPSG:4326", probe["supported"]["crs"])

    def test_a_stored_crs_the_feature_type_does_not_advertise_is_skipped(self):
        self.store("2.0.0", crs="urn:ogc:def:crs:EPSG::25832")

        result = self.generate(preset="standard")

        self.assertEqual(self.skip_reasons(result), {SkipReason.UNSUPPORTED_CRS})
        self.assertEqual(self.skipped_types(result, SkipReason.UNSUPPORTED_CRS),
                         FEATURE_TYPES)

    # --- explicit skip reasons --------------------------------------------------

    def test_deactivated_feature_type_is_skipped(self):
        self.wfs.featuretypes.filter(identifier="node3").update(is_active=False)

        result = self.generate(preset="standard")

        self.assertEqual(self.skipped_types(result, SkipReason.INACTIVE), ["node3"])
        self.assertNotIn("node3", self.targets(self.probes(result, "GetFeature")))

    def test_feature_type_the_capabilities_do_not_advertise_anymore_is_stale(self):
        self.store("2.0.0", feature_types=FEATURE_TYPES[:-1])

        result = self.generate(preset="standard")

        self.assertEqual(self.skipped_types(result, SkipReason.STALE),
                         [FEATURE_TYPES[-1]])

    def test_an_unknown_selection_is_reported(self):
        result = self.generate(preset="standard", featureType=["node2", "nope"])

        self.assertEqual(self.targets(self.probes(result, "GetFeature")), ["node2"])
        self.assertEqual(self.skipped_types(result, WfsSkipReason.UNKNOWN_FEATURE_TYPE),
                         ["nope"])

    def test_a_selection_by_feature_type_id_is_accepted(self):
        pk = str(self.wfs.featuretypes.get(identifier="node3").pk)

        result = self.generate(preset="standard", featureType=[pk])

        self.assertEqual(self.targets(self.probes(result, "GetFeature")), ["node3"])
        self.assertEqual(result["skipped"], [])

    def test_a_service_without_an_advertised_getfeature_endpoint_proposes_nothing(self):
        self.store("2.0.0", get_feature=False)

        result = self.generate(preset="standard")

        self.assertEqual(self.probes(result, "GetFeature"), [])
        self.assertIn(SkipReason.OPERATION_UNSUPPORTED, self.skip_reasons(result))

    def test_a_service_without_getcapabilities_endpoint_proposes_no_capabilities(self):
        self.store("2.0.0", get_capabilities=False)

        result = self.generate(preset="standard")

        self.assertEqual(self.probes(result, "GetCapabilities"), [])
        self.assertEqual(result["advertisedOperations"]["GetCapabilities"], False)
        # the feature type probes are unaffected
        self.assertEqual(len(self.probes(result, "GetFeature")), len(FEATURE_TYPES))

    # --- the comprehensive preset ----------------------------------------------

    def test_comprehensive_adds_the_describe_feature_type_of_every_type(self):
        result = self.generate(preset="comprehensive")

        describes = self.probes(result, "DescribeFeatureType")
        self.assertEqual(self.targets(describes), FEATURE_TYPES)
        self.assertEqual(
            {probe["targetFeatureType"]["identifier"] for probe in describes},
            set(self.targets(self.probes(result, "GetFeature"))))

        probe = describes[0]
        params = params_of(probe["requestSummary"]["url"])
        self.assertEqual(probe["candidateId"],
                         candidate_identifier("DescribeFeatureType", ["node2"]))
        self.assertEqual(params["REQUEST"], "DescribeFeatureType")
        self.assertEqual(params["TYPENAMES"], "node2")
        self.assertEqual(params["OUTPUTFORMAT"], GML)
        self.assertEqual(probe["parameters"]["timeout"], DEFAULT_TIMEOUT)

    def test_comprehensive_reports_an_unadvertised_operation_per_feature_type(self):
        self.store("2.0.0", describe=False)

        result = self.generate(preset="comprehensive")

        self.assertEqual(self.probes(result, "DescribeFeatureType"), [])
        self.assertEqual(result["advertisedOperations"]["DescribeFeatureType"], False)
        self.assertEqual(
            self.skipped_types(result, WfsSkipReason.NOT_ADVERTISED), FEATURE_TYPES)
        # the standard part of the preset is unaffected
        self.assertEqual(len(self.probes(result, "GetFeature")), len(FEATURE_TYPES))

    def test_comprehensive_reports_only_uninspectable_describe_formats(self):
        self.store("2.0.0", describe_formats=("application/json",))

        result = self.generate(preset="comprehensive")

        self.assertEqual(self.probes(result, "DescribeFeatureType"), [])
        self.assertEqual(self.skipped_types(result, WfsSkipReason.NO_SUPPORTED_FORMAT),
                         FEATURE_TYPES)

    # --- presets, ordering, paging and stable identities -----------------------

    def test_basic_proposes_one_representative_bounded_request(self):
        result = self.generate(preset="basic")

        self.assertEqual([probe["probeType"] for probe in result["probes"]],
                         ["GetCapabilities", "GetFeature"])
        self.assertEqual(self.targets(self.probes(result, "GetFeature")),
                         [FEATURE_TYPES[0]])
        # the scan still saw every candidate
        self.assertEqual(result["pagination"]["totalFeatureCandidates"],
                         len(FEATURE_TYPES))

    def test_candidate_identity_is_independent_of_preset_and_parameters(self):
        basic = self.probes(self.generate(preset="basic"), "GetFeature")[0]
        standard = next(
            probe for probe in self.probes(
                self.generate(preset="standard", maxFeatures=4), "GetFeature")
            if probe["targetFeatureType"]["identifier"] == FEATURE_TYPES[0])

        self.assertEqual(basic["candidateId"], standard["candidateId"])
        self.assertEqual(basic["candidateId"],
                         candidate_identifier("GetFeature", [FEATURE_TYPES[0]]))

    def test_generation_is_deterministic(self):
        self.assertEqual(self.generate(preset="comprehensive"),
                         self.generate(preset="comprehensive"))

    def test_a_page_never_splits_a_feature_type_from_its_describe_probe(self):
        first = self.generate(preset="comprehensive", limit=1)
        second = self.generate(preset="comprehensive", limit=1, offset=1)

        self.assertEqual([probe["probeType"] for probe in first["probes"]][1:],
                         ["GetFeature", "DescribeFeatureType"])
        self.assertEqual([probe["probeType"] for probe in second["probes"]][1:],
                         ["GetFeature", "DescribeFeatureType"])
        self.assertEqual(second["probes"][1]["targetFeatureType"]["identifier"],
                         FEATURE_TYPES[1])
        self.assertTrue(first["pagination"]["truncated"])
        self.assertFalse(self.generate(preset="standard")["pagination"]["truncated"])

    def test_the_contract_reports_the_operations_bounds_and_versions(self):
        result = self.generate(preset="standard")

        self.assertEqual(result["preset"], "standard")
        self.assertEqual(result["generatorVersion"], GENERATOR_VERSION)
        self.assertEqual(result["presets"], {
            "implemented": ["basic", "standard", "comprehensive"],
            "notImplemented": []})
        self.assertEqual(result["operations"], {
            "basic": ["GetCapabilities", "GetFeature"],
            "standard": ["GetCapabilities", "GetFeature"],
            "comprehensive": ["GetCapabilities", "GetFeature",
                              "DescribeFeatureType"]})
        bounds = result["bounds"]
        self.assertEqual(bounds["maxFeatures"], MAX_FEATURES)
        self.assertEqual(bounds["defaultMaxFeatures"], DEFAULT_MAX_FEATURES)
        self.assertEqual(bounds["maxProbes"], MAX_PROBES)
        self.assertEqual(bounds["defaultLimit"], DEFAULT_PROBE_LIMIT)
        self.assertIsNone(bounds["advertisedCountBound"])
        self.assertEqual(result["request"], {
            "timeout": DEFAULT_TIMEOUT,
            "maxFeatures": DEFAULT_MAX_FEATURES,
            "outputFormat": None})

    # --- transience and the surrounding guards ------------------------------------

    def test_generation_writes_nothing_and_never_contacts_the_service(self):
        counts = {model: model.objects.count() for model in (
            WebFeatureServiceGetFeatureProbe,
            WebFeatureServiceMonitoringSetting)}
        historical = WebFeatureService.history.count()

        with patch("requests.sessions.Session.send",
                   side_effect=AssertionError("preview must not contact the service")
                   ) as send:
            for _ in range(2):
                self.generate(preset="comprehensive")

        send.assert_not_called()
        for model, count in counts.items():
            self.assertEqual(model.objects.count(), count, model)
        self.assertEqual(WebFeatureService.history.count(), historical)

    def test_missing_stored_capabilities_never_fall_back_to_the_service(self):
        # the second WFS fixture service registers no capabilities document
        service = WebFeatureService.objects.get(
            pk='72bda0a1-a808-48ba-ab1d-bf03081263df')

        with patch("requests.sessions.Session.send") as send:
            with self.assertRaises(PreviewError) as caught:
                generate_wfs_probe_preview(service, {})

        self.assertEqual(caught.exception.code, "discovery")
        send.assert_not_called()

    def test_malformed_stored_capabilities_are_reported(self):
        self.wfs.xml_backup_file = SimpleUploadedFile(
            'broken.xml', b"<FeatureType><broken>")
        self.wfs.save()

        self.assertEqual(self.errors().code, "malformed")

    def test_disabled_service_is_locked(self):
        WebFeatureService.objects.filter(pk=WFS).update(is_active=False)
        self.wfs.refresh_from_db()

        error = self.errors()

        self.assertEqual(error.code, "disabled")
        self.assertEqual(error.status, 423)

    def test_credentials_of_an_advertised_endpoint_never_reach_the_summary(self):
        self.store("2.0.0", document=capabilities(
            version="2.0.0",
            endpoint="https://registered-user:registered-pw@registered.example/wfs?"))

        result = self.generate(preset="comprehensive")

        for probe in result["probes"]:
            url = probe["requestSummary"]["url"]
            self.assertNotIn("registered-user", url)
            self.assertNotIn("registered-pw", url)
            self.assertIn("registered.example", url)
