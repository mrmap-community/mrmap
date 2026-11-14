"""The metadata profile resource, its link from the records and the ISO
element paths of the writable fields (#1240).

Three things are pinned here:

* the profile answers as an ordinary json:api resource and the editor can
  fetch it with the record it edits (`include=profile`, sparse
  `fields[MetadataProfile]`), because the record's `profile` link points at
  the profile document;
* the OpenAPI schema carries the ISO 19139 element path of every WRITABLE
  mapped field as `x-iso-path`, and the served paths are the mapper configs'
  own — this module walks `registry/mappers/configs` on its own and is not
  allowed to see an answer the schema did not get from them (#981/#982: one
  ISO interpretation layer);
* the `editable=False` fields of the model are `readOnly` in the schema of
  every metadata serializer, so no schema-driven form offers them.
"""

from django.test import SimpleTestCase, TestCase
from django.urls import include as url_include
from django.urls import path
from rest_framework_json_api.utils import format_field_name

from registry.mappers.configs import application, dataset, service
from registry.models.metadata import (GENERIC_ISO19139_PROFILE_PK,
                                      DatasetMetadataRecord, MetadataContact)
from registry.urls import urlpatterns
from tests.django.registry.tests_query_performance import QueryMeasurementMixin

#: the detail routes whose generation answers the record components with
#: their read and request variants — the list routes belong in the subset
#: because it is POST on the list which makes spectacular emit the plain
#: request component — plus the profile resource itself
SCHEMA_PATTERN_NAMES = {
    "datasetmetadata-list",
    "datasetmetadata-detail",
    "servicemetadata-list",
    "servicemetadata-detail",
    "applicationmetadata-list",
    "applicationmetadata-detail",
    "metadataprofile-detail",
    "metadataprofile-list",
}

_SCHEMA = None


def subset_schema():
    """The record components of the api, generated once per test process.

    Same recipe as `tests_nested_service_schema.py`: generating a schema
    from the handful of routes at stake costs seconds instead of the
    document's minute.
    """
    global _SCHEMA
    if _SCHEMA is None:
        from drf_spectacular.generators import SchemaGenerator
        patterns = [pattern for pattern in urlpatterns
                    if getattr(pattern, "name", None) in SCHEMA_PATTERN_NAMES]
        _SCHEMA = SchemaGenerator(
            patterns=[path("api/registry/", url_include(patterns))]
        ).get_schema(public=True)
    return _SCHEMA


def schemas():
    return subset_schema()["components"]["schemas"]


def component_properties(component):
    """The attribute and relationship properties of a record component.

    The plain resource component nests them under
    ``properties.attributes`` / ``properties.relationships``; the request
    variants nest the whole resource under ``data``.
    """
    properties = component.get("properties", {})
    data = properties.get("data")
    if isinstance(data, dict) and "properties" in data:
        properties = data["properties"]
    return {
        **((properties.get("attributes") or {}).get("properties") or {}),
        **((properties.get("relationships") or {}).get("properties") or {}),
    }


def expected_paths_from_config(config_module):
    """Walk the mapper config by hand — the drift guard's own reading.

    Deliberately a second, tiny reading of the configs and not a call into
    `registry.mappers.paths`: what this test asserts is that the schema
    serves what the CONFIGS say, not what the same walker that filled it
    says. The known values in `IsoPathSchemaTests` catch what both readings
    could share.
    """
    config = next(iter(config_module.XPATH_MAP.values()))
    resource = next(cfg for cfg in config.values()
                    if isinstance(cfg, dict) and cfg.get("_model"))
    base = resource["_base_xpath"]

    def join(relative):
        return f"{base}/{relative[2:] if relative.startswith('./') else relative}"

    paths = {}
    for name, field in resource["fields"].items():
        if isinstance(field, str):
            paths[format_field_name(name)] = join(field)
        elif isinstance(field, dict) and "_values" not in field:
            if "_inputs" in field:
                paths[format_field_name(name)] = join(field["_inputs"][0])
            elif "_model" in field and "_base_xpath" in field:
                paths[format_field_name(name)] = join(field["_base_xpath"])
    return paths


#: the model fields which the OpenAPI schema must never offer for writing
#: (acceptance criteria of #1240; the list is what the model calls
#: editable=False, which is how the schema derives it in the first place)
NON_WRITABLE_FIELDS = ("file_identifier", "date_stamp", "origin", "is_broken")


class MetadataProfileResourceTests(QueryMeasurementMixin, TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_wms.json", "test_datasetmetadata.json"]

    def test_profile_answers_sections_and_rules_as_attributes(self):
        status, body, _ = self.request("/api/registry/metadata-profiles")
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body["data"]), 1)
        profile = body["data"][0]
        self.assertEqual(profile["type"], "MetadataProfile")
        self.assertEqual(profile["id"], str(GENERIC_ISO19139_PROFILE_PK))
        attributes = profile["attributes"]
        self.assertEqual(attributes["name"], "iso19139-generic")
        self.assertEqual(attributes["label"], "Generic")
        # the section rail of #1245 renders exactly this grouping
        self.assertEqual(attributes["sections"][0]["id"], "identification")
        title = next(field
                     for section in attributes["sections"]
                     for field in section["fields"]
                     if field["field"] == "title")
        self.assertEqual(title["requirement"], "mandatory")
        # the structural rules are filled by #1243; the attribute exists now
        self.assertEqual(attributes["rules"], [])

    def test_every_record_defaults_to_the_seeded_generic_profile(self):
        contact = MetadataContact.objects.first()
        record = DatasetMetadataRecord.objects.create(
            title="Created without a profile",
            dataset_contact=contact,
            metadata_contact=contact)
        self.assertEqual(record.profile_id, GENERIC_ISO19139_PROFILE_PK)

    def test_record_answers_profile_relationship_with_a_link_to_the_profile(self):
        record = DatasetMetadataRecord.objects.first()
        status, body, _ = self.request(f"/api/registry/dataset-metadata/{record.pk}")
        self.assertEqual(status, 200, body)
        relation = body["data"]["relationships"]["profile"]
        self.assertEqual(relation["data"], {
            "type": "MetadataProfile", "id": str(GENERIC_ISO19139_PROFILE_PK)})
        self.assertTrue(
            relation["links"]["related"].endswith(
                f"/api/registry/metadata-profiles/{GENERIC_ISO19139_PROFILE_PK}"),
            relation["links"])

    def test_profile_arrives_with_the_record_and_can_be_sparsed(self):
        record = DatasetMetadataRecord.objects.first()
        status, body, _ = self.request(
            f"/api/registry/dataset-metadata/{record.pk}", include="profile")
        self.assertEqual(status, 200, body)
        included = next(row for row in body["included"] if row["type"] == "MetadataProfile")
        self.assertEqual(included["id"], str(GENERIC_ISO19139_PROFILE_PK))
        self.assertIn("sections", included["attributes"])

        status, body, _ = self.request(
            f"/api/registry/dataset-metadata/{record.pk}", include="profile",
            **{"fields[MetadataProfile]": "rules"})
        self.assertEqual(status, 200, body)
        included = next(row for row in body["included"] if row["type"] == "MetadataProfile")
        self.assertEqual(set(included["attributes"]), {"rules"})


class IsoPathSchemaTests(SimpleTestCase):
    """`x-iso-path` of the writable fields, kept honest against the configs."""

    RECORDS = {
        "DatasetMetadataRecord": (dataset, ("DatasetMetadataRecord",
                                            "DatasetMetadataRecordRequest",
                                            "PatchedDatasetMetadataRecordRequest")),
        "ServiceMetadataRecord": (service, ("ServiceMetadataRecord",
                                            "ServiceMetadataRecordRequest",
                                            "PatchedServiceMetadataRecordRequest")),
        "ApplicationMetadataRecord": (application, ("ApplicationMetadataRecord",
                                                    "ApplicationMetadataRecordRequest",
                                                    "PatchedApplicationMetadataRecordRequest")),
    }

    def test_known_fields_answer_the_known_element(self):
        components = schemas()
        attributes = component_properties(components["DatasetMetadataRecord"])
        self.assertEqual(
            attributes["title"]["x-iso-path"],
            "/gmd:MD_Metadata/gmd:identificationInfo/gmd:MD_DataIdentification"
            "/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString")
        self.assertEqual(
            attributes["metadataContact"]["x-iso-path"],
            "/gmd:MD_Metadata/gmd:contact/gmd:CI_ResponsibleParty")
        self.assertEqual(
            component_properties(components["ServiceMetadataRecord"])["title"]["x-iso-path"],
            "/gmd:MD_Metadata/gmd:identificationInfo/srv:SV_ServiceIdentification"
            "/gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString")

    def test_served_paths_are_the_mapper_configs_paths(self):
        """AC #1240: the paths served to the editor match the mapper configs.

        Every property the config maps and the component answers without
        readOnly must carry exactly the config's path — no more, no less.
        """
        components = schemas()
        for record, (config_module, component_names) in self.RECORDS.items():
            expected = expected_paths_from_config(config_module)
            for component_name in component_names:
                component = components.get(component_name)
                if component is None:
                    self.fail(f"{component_name} is not in the schema")
                properties = component_properties(component)
                for name, property_schema in properties.items():
                    with self.subTest(record=record, component=component_name, field=name):
                        if not isinstance(property_schema, dict):
                            continue
                        if name not in expected or property_schema.get("readOnly"):
                            self.assertNotIn(
                                "x-iso-path", property_schema,
                                f"{name} is not a writable mapped field and must not answer a path")
                            continue
                        self.assertIn("x-iso-path", property_schema)
                        self.assertEqual(property_schema["x-iso-path"], expected[name])
                # a mapped writable field of the component is never left without its path
                for name, path_value in expected.items():
                    property_schema = properties.get(name)
                    if isinstance(property_schema, dict) and not property_schema.get("readOnly"):
                        self.assertEqual(property_schema.get("x-iso-path"), path_value,
                                         f"{component_name}.{name} lost its config path")

    def test_the_profile_resource_itself_answers_no_iso_path(self):
        """One ISO interpretation layer: only mapped fields carry a path."""
        for component_name in ("MetadataProfile", "PaginatedMetadataProfileList",
                               "MetadataProfileResponse"):
            component = schemas().get(component_name)
            if component is None:
                continue
            with self.subTest(component=component_name):
                self.assertNotIn("x-iso-path", str(component))

    def test_record_profile_relationship_carries_no_iso_path(self):
        """The profile is a mrmap concept, no ISO 19139 element maps to it."""
        for record, (_, component_names) in self.RECORDS.items():
            with self.subTest(record=record):
                properties = component_properties(schemas()[component_names[0]])
                self.assertNotIn("x-iso-path", properties["profile"])


class MetadataReadOnlySchemaTests(SimpleTestCase):
    """The editable=False fields never answer as writable (#1240).

    The OpenAPI marker is what keeps a schema-driven form from offering
    them; the EditGuesser of the current dialog ignored the schema, which
    is how these fields looked writable today.
    """

    def test_read_only_in_every_record_component(self):
        components = schemas()
        for record, (_, component_names) in IsoPathSchemaTests.RECORDS.items():
            for component_name in component_names:
                properties = component_properties(components[component_name])
                for field in NON_WRITABLE_FIELDS:
                    name = format_field_name(field)
                    with self.subTest(component=component_name, field=name):
                        property_schema = properties.get(name)
                        if property_schema is None:
                            continue  # absent from a request body is the same refusal
                        self.assertTrue(property_schema.get("readOnly"),
                                        f"{component_name}.{name} is offered for writing")

    def test_the_derivation_covers_every_non_editable_model_field(self):
        """The pin above holds for ALL of them, not only for the named four."""
        components = schemas()
        properties = component_properties(components["DatasetMetadataRecord"])
        for model_field in DatasetMetadataRecord._meta.get_fields():
            if not getattr(model_field, "concrete", False) or getattr(model_field, "editable", True):
                continue
            if not hasattr(model_field, "primary_key") or model_field.primary_key:
                continue  # the resource id is the envelope's own field
            name = format_field_name(model_field.name)
            with self.subTest(field=name):
                if name in properties:
                    self.assertTrue(properties[name].get("readOnly"))
