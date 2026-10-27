"""The capabilities documents which advertise exactly one registered resource.

The document of a single layer or feature type is generated for every request out
of the registry (registry/proxy/resource_capabilities.py), so the tests below
narrow documents of the versions the mappers answer with and ask the endpoints of
registered services.
"""
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from lxml import etree
from MrMap.settings import BASE_DIR
from registry.helper.resource_capabilities import (
    AMBIGUOUS_ELEMENT, MALFORMED, NO_SUCH_ELEMENT, NOT_SUPPORTED,
    CapabilitiesError, feature_type_capabilities_url,
    layer_capabilities_url, single_resource)
from registry.models.service import FeatureType, Layer
from rest_framework.test import APIClient
from tests.django.registry.tests_query_performance import SERVICES

JSONAPI = "application/vnd.api+json"

# A WMS document with a layer nested in a named layer and a layer beside it. The
# named layer and the unnamed container above it carry the attributes which the
# nested layer inherits, so narrowing must write them into the nested layer and
# answer the document without the parents.
WMS_130 = """<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Service><Name>WMS</Name><Title>A service</Title></Service>
  <Capability>
    <Request>
      <GetCapabilities>
        <DCPType><HTTP><Get><OnlineResource
          xmlns:xlink="http://www.w3.org/1999/xlink"
          xlink:href="https://wms.test/ows"/></Get></HTTP></DCPType>
      </GetCapabilities>
    </Request>
    <Layer queryable="0">
      <EX_GeographicBoundingBox>
        <westBoundLongitude>-90</westBoundLongitude>
        <eastBoundLongitude>90</eastBoundLongitude>
        <southBoundLatitude>-180</southBoundLatitude>
        <northBoundLatitude>180</northBoundLatitude>
      </EX_GeographicBoundingBox>
      <KeywordList><Keyword>inherited</Keyword></KeywordList>
      <CRS>EPSG:4326</CRS>
      <CRS>EPSG:3857</CRS>
      <MinScaleDenominator>100</MinScaleDenominator>
      <Layer queryable="1">
        <Name>root</Name>
        <Title>The ancestor</Title>
        <CRS>EPSG:4326</CRS>
        <Layer>
          <Name>nested</Name>
          <Title>The requested layer</Title>
          <CRS>EPSG:25832</CRS>
          <KeywordList><Keyword>own</Keyword></KeywordList>
        </Layer>
      </Layer>
      <Layer><Name>sibling</Name><Title>Another layer</Title></Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>"""

WMS_111 = WMS_130.replace('version="1.3.0"', 'version="1.1.1"')

# A WFS document of the version which lists the type names of a service as the
# allowed values of a parameter of its operations.
WFS_100 = """<?xml version="1.0" encoding="UTF-8"?>
<WFS_Capabilities version="1.0.0" xmlns="http://www.opengis.net/wfs">
  <Service><Name>WFS</Name><Title>A service</Title></Service>
  <FeatureTypeList>
    <FeatureType><Name>first</Name><Title>First</Title></FeatureType>
    <FeatureType><Name>second</Name><Title>Second</Title></FeatureType>
  </FeatureTypeList>
</WFS_Capabilities>"""

WFS_100_WITH_TYPE_NAMES = """<?xml version="1.0" encoding="UTF-8"?>
<WFS_Capabilities version="1.0.0" xmlns="http://www.opengis.net/wfs">
  <Service><Name>WFS</Name><Title>A service</Title></Service>
  <FeatureTypeList>
    <FeatureType><Name>first</Name><Title>First</Title></FeatureType>
    <FeatureType><Name>second</Name><Title>Second</Title></FeatureType>
  </FeatureTypeList>
  <OperationsMetadata>
    <Operation name="GetFeature">
      <Parameter name="typeName">
        <AllowedValues><Value>first</Value><Value>second</Value></AllowedValues>
      </Parameter>
      <Parameter name="maxFeatures">
        <AllowedValues><Value>100</Value></AllowedValues>
      </Parameter>
    </Operation>
    <Operation name="GetFeatureWithMetadata">
      <Parameter name="typeName">
        <AllowedValues><Value>NoValues</Value></AllowedValues>
      </Parameter>
    </Operation>
  </OperationsMetadata>
</WFS_Capabilities>"""


def localname(element) -> str:
    """The tag of an element without the namespace it is written in.

    Comment and processing instruction nodes answer a function instead of a string as their tag, so
    they are answered as the empty name, which no element of a capabilities document is named by.
    """
    return element.tag.rsplit("}", 1)[-1] if isinstance(element.tag, str) else ""


def named(document, parent_name):
    """The text of the name of every resource of the given kind in a document."""
    root = etree.fromstring(document)
    return [
        element.text
        for element in root.iter()
        if localname(element) == "Name"
        and localname(element.getparent()) == parent_name
    ]


def count(document, name) -> int:
    """How often an element with the given name appears in a document."""
    root = etree.fromstring(document)
    return len([
        element for element in root.iter() if localname(element) == name
    ])


def child_texts(parent, name) -> list:
    """The text of every direct child element of the parent with the given name."""
    return [
        (child.text or "").strip() for child in parent if localname(child) == name
    ]


class SingleWmsResourceTest(SimpleTestCase):
    """The narrowing of a WMS capabilities document to one advertised layer."""

    def narrow(self, document, identifier):
        narrowed = single_resource(document, "WMS", identifier)
        return narrowed, etree.fromstring(narrowed)

    def test_advertises_only_the_requested_layer(self):
        for version, document in (("1.3.0", WMS_130), ("1.1.1", WMS_111)):
            with self.subTest(version=version):
                narrowed, root = self.narrow(document, "nested")
                self.assertEqual(root.get("version"), version)
                self.assertEqual(named(narrowed, "Layer"), ["nested"])
                self.assertNotIn("sibling", narrowed.decode("utf-8"))

    def test_answers_a_nested_layer_alone_with_what_it_inherits(self):
        narrowed, root = self.narrow(WMS_130, "nested")
        layers = [
            element for element in root.iter() if localname(element) == "Layer"
        ]
        # the parents are containers of inherited values only: with the inherited
        # values written into the requested layer, the document does not need
        # them anymore and answers the requested layer alone
        self.assertEqual(count(narrowed, "Layer"), 1)
        self.assertEqual(len(layers), 1)
        layer = layers[0]
        self.assertEqual(localname(layer.getparent()), "Capability")
        self.assertEqual(named(narrowed, "Layer"), ["nested"])
        # what the parents answered, the layer answers of its own now, while it
        # keeps what it answered itself
        self.assertEqual(
            sorted(child_texts(layer, "CRS")),
            ["EPSG:25832", "EPSG:3857", "EPSG:4326"])
        self.assertEqual(
            child_texts(layer, "Title"), ["The requested layer"])
        self.assertEqual(
            child_texts(layer, "MinScaleDenominator"), ["100"])
        self.assertEqual(
            [localname(child) for child in layer
             if localname(child) == "EX_GeographicBoundingBox"],
            ["EX_GeographicBoundingBox"])
        self.assertEqual(
            [keyword.text for keyword in layer.iter()
             if localname(keyword) == "Keyword"],
            ["own", "inherited"])
        # the nearest parent which names the attribute answers it
        self.assertEqual(layer.get("queryable"), "1")

    def test_keeps_the_service_and_the_operations_of_the_service(self):
        narrowed, root = self.narrow(WMS_130, "nested")
        self.assertEqual(
            root.xpath("//*[local-name()='Service']"
                       "/*[local-name()='Title']/text()"),
            ["A service"])
        self.assertEqual(
            root.xpath("//*[local-name()='GetCapabilities']"
                       "//*[local-name()='OnlineResource']"
                       "/@*[local-name()='href']"),
            ["https://wms.test/ows"])

    def test_refuses_a_document_of_an_unsupported_version(self):
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow(WMS_130.replace('version="1.3.0"', 'version="1.3.1"'),
                        "nested")
        self.assertEqual(error.exception.code, NOT_SUPPORTED)
        self.assertEqual(error.exception.status, 501)

    def test_refuses_a_layer_the_service_does_not_advertise(self):
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow(WMS_130, "absent")
        self.assertEqual(error.exception.code, NO_SUCH_ELEMENT)
        self.assertEqual(error.exception.status, 404)

    def test_refuses_a_resource_without_an_identifier(self):
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow(WMS_130, None)
        self.assertEqual(error.exception.code, NO_SUCH_ELEMENT)
        self.assertEqual(error.exception.status, 404)

    def test_refuses_an_ambiguous_identifier(self):
        ambiguous = WMS_130.replace("<Name>sibling</Name>",
                                    "<Name>nested</Name>")
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow(ambiguous, "nested")
        self.assertEqual(error.exception.code, AMBIGUOUS_ELEMENT)

    def test_refuses_a_document_which_can_not_be_read(self):
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow("this is no xml", "nested")
        self.assertEqual(error.exception.code, MALFORMED)
        self.assertEqual(error.exception.status, 502)


class SingleWfsResourceTest(SimpleTestCase):
    """The narrowing of a WFS capabilities document to one feature type."""

    def narrow(self, document, identifier):
        narrowed = single_resource(document, "WFS", identifier)
        return narrowed, etree.fromstring(narrowed)

    def test_advertises_only_the_requested_feature_type(self):
        for version in ("1.0.0", "1.1.0", "2.0.0", "2.0.2"):
            document = WFS_100.replace('version="1.0.0"', f'version="{version}"')
            with self.subTest(version=version):
                narrowed, _ = self.narrow(document, "second")
                self.assertEqual(named(narrowed, "FeatureType"), ["second"])

    def test_restricts_the_advertised_type_names_to_one_value(self):
        narrowed, root = self.narrow(WFS_100_WITH_TYPE_NAMES, "second")
        self.assertEqual(
            root.xpath("//*[local-name()='Parameter'][@name='typeName']"
                       "//*[local-name()='Value']/text()"),
            ["second", "NoValues"])

    def test_keeps_a_parameter_which_does_not_name_type_names(self):
        narrowed, root = self.narrow(WFS_100_WITH_TYPE_NAMES, "second")
        self.assertEqual(
            root.xpath("//*[local-name()='Parameter'][@name='maxFeatures']"
                       "//*[local-name()='Value']/text()"),
            ["100"])

    def test_refuses_a_document_of_an_unsupported_version(self):
        with self.assertRaises(CapabilitiesError) as error:
            self.narrow(WFS_100.replace('version="1.0.0"', 'version="3.0.0"'),
                        "second")
        self.assertEqual(error.exception.code, NOT_SUPPORTED)
        self.assertEqual(error.exception.status, 501)


class CapabilitiesUrlTest(SimpleTestCase):
    """The adresses of the documents name the resource in their path."""

    def test_the_url_names_the_resource_without_parameters(self):
        url = layer_capabilities_url("22222222-2222-2222-2222-222222222222")
        self.assertEqual(
            url, "/mrmap-proxy/wms/layer/22222222-2222-2222-2222-222222222222")
        url = feature_type_capabilities_url("22222222-2222-2222-2222-222222222222")
        self.assertEqual(
            url, "/mrmap-proxy/wfs/featuretype/22222222-2222-2222-2222-222222222222")


class ResourceCapabilitiesEndpointTest(TestCase):
    """The endpoints which answer the capabilities document of one resource.

    A capabilities request is answered out of the registry and never
    forwarded, so these tests need registered services but no remote service.
    """

    fixtures = SERVICES

    @staticmethod
    def element(model):
        """An element of a service which is advertised with a name."""
        return model.objects.exclude(identifier__isnull=True).exclude(identifier="").first()

    @staticmethod
    def with_backup(service, name):
        """The service with the stored document its mappers answer the capabilities of.

        The document of a registered service is generated out of the registry on the
        basis of the document which was stored when the service was registered
        (registry/models/document.py). The fixtures of the registry describe the
        registry but no remote service and therefore carry no such document.
        """
        with open(f"{BASE_DIR}/tests/django/test_data/{name}", mode="rb") as cap_file:
            service.xml_backup_file = SimpleUploadedFile(
                "capabilitites.xml", cap_file.read())
        service.save()
        return service

    def setUp(self):
        self.client = APIClient()
        self.client.login(username="User1", password="User1")
        self.layer = self.element(Layer)
        self.with_backup(self.layer.service, "capabilities/wms/1.3.0.xml")
        self.feature_type = self.element(FeatureType)
        self.with_backup(
            self.feature_type.service, "capabilities/wfs/local_mapserver.2.0.0.xml")
        self.assertIsNotNone(self.layer)
        self.assertIsNotNone(self.feature_type)

    def test_answers_the_document_of_one_layer(self):
        response = self.client.get(f"/mrmap-proxy/wms/layer/{self.layer.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(
            named(response.content, "Layer"), [self.layer.identifier])
        # the parents of a nested layer are not part of the document
        self.assertEqual(count(response.content, "Layer"), 1)

    def test_answers_the_document_of_one_feature_type(self):
        response = self.client.get(
            f"/mrmap-proxy/wfs/featuretype/{self.feature_type.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            named(response.content, "FeatureType"),
            [self.feature_type.identifier])
        self.assertEqual(count(response.content, "FeatureType"), 1)

    def test_answers_a_client_which_appends_the_parameters_itself(self):
        response = self.client.get(
            f"/mrmap-proxy/wms/layer/{self.layer.pk}"
            "?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.3.0")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            named(response.content, "Layer"), [self.layer.identifier])

    def test_answers_an_unknown_resource_with_an_exception_report(self):
        response = self.client.get(f"/mrmap-proxy/wms/layer/{uuid4()}")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"ServiceExceptionReport", response.content)

    def attributes_of(self, endpoint, pk):
        response = self.client.get(f"/api/registry/{endpoint}/{pk}",
                                   HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200)
        return response.json()["data"]["attributes"]

    def test_layer_answers_the_url_of_its_own_document(self):
        attributes = self.attributes_of("layers", self.layer.pk)
        self.assertTrue(
            attributes["capabilitiesUrl"].endswith(
                f"/mrmap-proxy/wms/layer/{self.layer.pk}"),
            msg=attributes["capabilitiesUrl"])

    def test_feature_type_answers_the_url_of_its_own_document(self):
        attributes = self.attributes_of("featuretypes", self.feature_type.pk)
        self.assertTrue(
            attributes["capabilitiesUrl"].endswith(
                f"/mrmap-proxy/wfs/featuretype/{self.feature_type.pk}"),
            msg=attributes["capabilitiesUrl"])
