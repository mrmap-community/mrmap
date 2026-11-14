"""The create-dialog option "collect metadata records" says what it does (#1264).

The registration dialog renders this option straight from the OpenAPI schema,
so the promise lives in the serializer strings. Issue #1264 demands three
things of that promise and one of the field's presence:

* the WMS and the WFS create explain the option with the SAME label and help
  text - one word per concept (#1267, D6);
* the help text names what a decision needs: the documents the capabilities
  reference, that an unreachable document is reported as a failed reference
  which can be retried (true since #1263/#1265), and the background jobs as
  the place to look;
* the default stays True - switching it off would change registration
  behaviour for every existing client;
* a CSW does not carry the field at all - it has no remote metadata records
  to collect (the view never asked the client), so schema and form agree.
"""
import json

from django.test import SimpleTestCase
from django.urls import include, path
from drf_spectacular.generators import SchemaGenerator
from registry.serializers.service import (
    CatalogueServiceCreateSerializer,
    WebFeatureServiceCreateSerializer,
    WebMapServiceCreateSerializer,
)
from registry.urls import urlpatterns

#: the camelized attribute name the dialog's form is built from
ATTRIBUTE = "collectMetadataRecords"

CREATE_SERIALIZERS = {
    "wms": WebMapServiceCreateSerializer,
    "wfs": WebFeatureServiceCreateSerializer,
}


def _create_body_attributes(schema, path_):
    """The inline-resolved `data.attributes.properties` of a POST operation."""
    operation = schema["paths"][path_]["post"]
    content = operation["requestBody"]["content"]
    media = next(iter(content.values()))

    def resolve(node, seen):
        # inline every $ref against this schema's components; the seen set
        # breaks a component which (transitively) references itself
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                if name in seen:
                    return {}
                return resolve(schema["components"]["schemas"][name], seen | {name})
            return {key: resolve(value, seen) for key, value in node.items()}
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        return node

    body = resolve(media["schema"], set())
    attributes = body.get("properties", {}).get("data", {})
    attributes = attributes.get("properties", {}).get("attributes", {})
    return attributes.get("properties", {})


class CollectMetadataOptionSerializerTests(SimpleTestCase):
    """The option's strings as the serializers answer them."""

    def test_wms_and_wfs_explain_the_option_identically(self):
        fields = {}
        for service, serializer in CREATE_SERIALIZERS.items():
            with self.subTest(service=service):
                field = serializer().fields["collect_metadata_records"]
                self.assertTrue(field.label)
                self.assertTrue(field.help_text)
                # losing the default would change registration for every client
                self.assertIs(field.default, True)
                fields[service] = (field.label, field.help_text)
        self.assertEqual(fields["wms"], fields["wfs"])

    def test_help_text_names_what_is_collected_a_failure_and_the_place_to_look(self):
        help_text = WebMapServiceCreateSerializer().fields[
            "collect_metadata_records"].help_text.lower()
        # what is collected: the documents the capabilities document references
        self.assertIn("capabilities", help_text)
        self.assertIn("referenced", help_text)
        # what happens on failure: reported, and it can be retried
        self.assertIn("failed", help_text)
        self.assertIn("retried", help_text)
        # where to look afterwards: the background jobs
        self.assertIn("background jobs", help_text)
        # the claim of the old text - that ALL related documents are collected
        # - is what #1264 removed; only capabilities-referenced ones are
        self.assertNotIn("all related", help_text)

    def test_csw_create_serializer_does_not_have_the_field(self):
        # a CSW has no remote metadata records; the view hardcoded False,
        # the client is not asked (#1264: schema and form must agree)
        self.assertNotIn(
            "collect_metadata_records",
            CatalogueServiceCreateSerializer().fields)


class CollectMetadataOptionSchemaTests(SimpleTestCase):
    """The same answers in the schema the dialog builds its form from."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        names = {"wms-list", "wfs-list", "csw-list"}
        patterns = [p for p in urlpatterns if getattr(p, "name", None) in names]
        cls.schema = SchemaGenerator(
            patterns=[path("api/registry/", include(patterns))]).get_schema(public=True)

    def test_wms_and_wfs_create_bodies_offer_the_attribute_with_one_text(self):
        texts = {}
        for service in CREATE_SERIALIZERS:
            with self.subTest(service=service):
                properties = _create_body_attributes(
                    self.schema, f"/api/registry/{service}")
                self.assertIn(ATTRIBUTE, properties)
                texts[service] = json.dumps(properties[ATTRIBUTE], sort_keys=True)
        self.assertEqual(texts["wms"], texts["wfs"])

    def test_csw_create_body_does_not_offer_the_attribute(self):
        properties = _create_body_attributes(self.schema, "/api/registry/csw")
        self.assertNotIn(ATTRIBUTE, properties)
