"""Declaring and taking back metadata relations, and their ISO round trip (#985).

The relation endpoint answers the curator's declaration of a coupling on the
established kinds of D5 of docs/metadata-identity.md, and the write carries the
provenance of the curator's own row (`is_internal` plus `origin=EDITOR`), which
D7.1 protects from every later harvest. What is pinned here:

* the pair of a service metadata record with a dataset metadata record is the
  new storable combination: stored once per pair and kind, idempotent, from
  either declaring side (the AC "link from either side, stored once");
* the matrix: a dataset beside a layer or feature type only, no element beside
  a pair, no row without a record, and the payload can not name the
  server-owned provenance;
* the write permission is the CHANGE permission over one coupled record, not a
  permission over the join row (D11); DELETE only answers for the curator's
  own kind;
* the ISO round trip through the ONE reverse mapper: the pair serializes as a
  `srv:operatesOn` row of the SERVICE record's document - `uuidref` the dataset
  record's document identity, `href` its location - added idempotently on every
  publish, removed exactly when the relation goes away, and never for a
  coupling which is not the standards-serializable CURATED_PUBLICATION kind;
  harvested operatesOn evidence beside it keeps its bytes.
"""

import json

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from guardian.shortcuts import assign_perm
from mptt2.models import Tree
from registry.enums.metadata import MetadataOriginEnum
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.publish import publish_document
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataRelation,
                                      ServiceMetadataRecord)
from registry.models.service import Layer, WebMapService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"


def api(client, method, path, body=None):
    """One json:api request, return (status, body)."""
    response = getattr(client, method)(
        path, body, format="vnd.api+json", HTTP_ACCEPT=JSONAPI)
    return response.status_code, (
        json.loads(response.content) if response.content else {})


class CouplingFixtures:
    """One dataset record, one service record and one layer to couple them."""

    def make_parts(self, origin_url="https://catalogue.example/doc.xml"):
        contact = MetadataContact.objects.create(name="Relation contact")
        self.contact = contact
        self.dataset = DatasetMetadataRecord.objects.create(
            metadata_contact=contact, dataset_contact=contact,
            title="Coupled dataset", code_space="de.mrmap.",
            code="coupled-dataset",
            file_identifier="de.mrmap.coupled-dataset",
            origin_url=origin_url)
        self.service_record = ServiceMetadataRecord.objects.create(
            metadata_contact=contact,
            title="Coupling service", code="coupling-service",
            file_identifier="de.mrmap.coupling-service")
        self.wms = WebMapService.objects.create(
            title="Coupling wms", version=130, origin=1,
            service_url="https://example.com/wms/coupling",
            metadata_contact=contact, service_contact=contact)
        self.layer = Layer.objects.create(
            service=self.wms, title="Coupling layer",
            identifier="coupling-layer",
            mptt_tree=Tree.objects.create(), mptt_lft=1, mptt_rgt=2,
            mptt_depth=0)


class RecordPairModelTests(CouplingFixtures, TestCase):
    """The pair row: one per pair and kind, asserted from either side."""

    def test_a_pair_is_stored_once_from_either_declaring_side(self):
        self.make_parts()
        from_service = self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        from_dataset = self.dataset.add_record_relation(
            self.service_record, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        self.assertEqual(from_service.pk, from_dataset.pk)
        self.assertEqual(MetadataRelation.objects.count(), 1)
        row = from_service
        self.assertEqual(row.service_metadata_id, self.service_record.pk)
        self.assertEqual(row.dataset_metadata_id, self.dataset.pk)
        self.assertTrue(row.is_internal)
        self.assertEqual(row.origin, MetadataOriginEnum.EDITOR.value)
        self.assertTrue(row.is_publishable)

    def test_two_records_of_one_kind_have_no_combination(self):
        self.make_parts()
        other = DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact, dataset_contact=self.contact,
            title="Second dataset", file_identifier="de.mrmap.second")
        with self.assertRaises(ValueError):
            self.dataset.add_record_relation(
                other, origin=MetadataOriginEnum.EDITOR.value,
                is_internal=True)
        with self.assertRaises(ValueError):
            self.service_record.add_record_relation(
                self.layer, origin=MetadataOriginEnum.EDITOR.value,
                is_internal=True)

    def test_removal_takes_back_the_cited_kind_only(self):
        self.make_parts()
        self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        # the harvested kind of the same pair (written by no api, but the
        # key of the table knows it): must not answer the curator's removal
        MetadataRelation.objects.create(
            service_metadata=self.service_record,
            dataset_metadata=self.dataset, is_internal=False,
            origin=MetadataOriginEnum.CATALOGUE.value)
        self.dataset.remove_record_relation(
            self.service_record, internal=True,
            origin=MetadataOriginEnum.EDITOR.value)
        remaining = MetadataRelation.objects.all()
        self.assertEqual(remaining.count(), 1)
        self.assertFalse(remaining.first().is_internal)


class RelationApiWriteTests(CouplingFixtures, TestCase):
    """POST and DELETE of /api/registry/metadata-relations."""

    fixtures = ["test_users.json"]
    PATH = "/api/registry/metadata-relations"

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.curator = get_user_model().objects.create_user(
            "relation-curator", password="test")

    def setUp(self):
        self.make_parts()

    def grant(self, action, obj):
        assign_perm(
            f"registry.{action}_{obj._meta.model_name}", self.curator, obj)

    def api_client(self):
        client = APIClient()
        client.force_authenticate(user=self.curator)
        return client

    def relation_body(self, relationships):
        return {"data": {"type": "MetadataRelation",
                         "attributes": {},
                         "relationships": relationships}}

    def relation(self, name, obj):
        return {name: {"data": {
            "type": obj._meta.object_name, "id": str(obj.pk)}}}

    def test_a_pair_post_stores_the_curators_row(self):
        self.grant("change", self.service_record)
        self.grant("view", self.service_record)
        self.grant("view", self.dataset)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body({
                **self.relation("serviceMetadata", self.service_record),
                **self.relation("datasetMetadata", self.dataset)}))
        self.assertEqual(status, 201, answer)
        row = MetadataRelation.objects.get(pk=answer["data"]["id"])
        self.assertTrue(row.is_internal)
        self.assertEqual(row.origin, MetadataOriginEnum.EDITOR.value)
        # the posture the screen's take-back button reads (see the read test)
        self.assertIs(answer["data"]["attributes"]["isPublishable"], True)

    def test_relinking_the_same_pair_asserts_the_standing_row(self):
        self.grant("change", self.dataset)
        self.grant("view", self.dataset)
        self.grant("view", self.service_record)
        body = self.relation_body({
            **self.relation("serviceMetadata", self.service_record),
            **self.relation("datasetMetadata", self.dataset)})
        first = api(self.api_client(), "post", self.PATH, body)
        second = api(self.api_client(), "post", self.PATH, body)
        self.assertEqual(first[0], 201, first[1])
        self.assertEqual(second[0], 201, second[1])
        self.assertEqual(first[1]["data"]["id"], second[1]["data"]["id"])
        self.assertEqual(
            MetadataRelation.objects.filter(
                service_metadata=self.service_record,
                dataset_metadata=self.dataset).count(), 1)

    def test_an_element_coupling_of_the_dataset_is_declarable(self):
        self.grant("change", self.dataset)
        self.grant("view", self.dataset)
        self.grant("view", self.layer)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body({
                **self.relation("layer", self.layer),
                **self.relation("datasetMetadata", self.dataset)}))
        self.assertEqual(status, 201, answer)
        row = MetadataRelation.objects.get(pk=answer["data"]["id"])
        self.assertEqual(row.layer_id, self.layer.pk)
        self.assertTrue(row.is_publishable)

    def test_a_whole_service_is_never_coupled_to_a_dataset(self):
        """The combination the check constraint refuses answers a 400."""
        self.grant("change", self.dataset)
        self.grant("view", self.wms)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body({
                **self.relation("wms", self.wms),
                **self.relation("datasetMetadata", self.dataset)}))
        self.assertEqual(status, 400, answer)
        self.assertFalse(MetadataRelation.objects.exists())

    def test_a_row_naming_no_record_declares_nothing(self):
        self.grant("change", self.wms)
        self.grant("view", self.wms)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body(self.relation("wms", self.wms)))
        self.assertEqual(status, 400, answer)

    def test_a_record_alone_names_no_partner(self):
        """The legacy "record without relation" row is no api declaration."""
        self.grant("change", self.dataset)
        self.grant("view", self.dataset)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body(
                self.relation("datasetMetadata", self.dataset)))
        self.assertEqual(status, 400, answer)
        self.assertFalse(MetadataRelation.objects.exists())

    def test_the_provenance_of_the_row_is_not_writable(self):
        self.grant("change", self.service_record)
        self.grant("view", self.service_record)
        self.grant("view", self.dataset)
        body = self.relation_body({
            **self.relation("serviceMetadata", self.service_record),
            **self.relation("datasetMetadata", self.dataset)})
        body["data"]["attributes"] = {"isInternal": False, "origin": 1}
        status, answer = api(self.api_client(), "post", self.PATH, body)
        self.assertEqual(status, 400, answer)
        pointers = {error["source"]["pointer"] for error in answer["errors"]}
        self.assertTrue(any("isInternal" in pointer for pointer in pointers))
        self.assertTrue(any("origin" in pointer for pointer in pointers))

    def test_writing_without_the_change_permission_over_either_record_is_denied(self):
        self.grant("view", self.service_record)
        self.grant("view", self.dataset)
        status, answer = api(
            self.api_client(), "post", self.PATH,
            self.relation_body({
                **self.relation("serviceMetadata", self.service_record),
                **self.relation("datasetMetadata", self.dataset)}))
        self.assertEqual(status, 403, answer)
        self.assertFalse(MetadataRelation.objects.exists())

    def test_the_write_gate_of_the_deployment_refuses_the_post(self):
        self.grant("change", self.service_record)
        self.grant("view", self.dataset)
        with self.settings(MRMAP_METADATA_EDITOR_WRITES_ENABLED=False):
            status, _ = api(
                self.api_client(), "post", self.PATH,
                self.relation_body({
                    **self.relation("serviceMetadata", self.service_record),
                    **self.relation("datasetMetadata", self.dataset)}))
        self.assertEqual(status, 403)
        self.assertFalse(MetadataRelation.objects.exists())

    def test_delete_takes_back_the_curators_row(self):
        self.grant("change", self.dataset)
        self.grant("view", self.dataset)
        self.grant("view", self.service_record)
        row = self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        status, answer = api(
            self.api_client(), "delete", f"{self.PATH}/{row.pk}")
        self.assertEqual(status, 204, answer)
        self.assertFalse(MetadataRelation.objects.filter(pk=row.pk).exists())

    def test_delete_never_takes_back_a_harvested_coupling(self):
        self.grant("change", self.dataset)
        self.grant("view", self.service_record)
        row = MetadataRelation.objects.create(
            service_metadata=self.service_record,
            dataset_metadata=self.dataset, is_internal=False,
            origin=MetadataOriginEnum.CATALOGUE.value)
        status, _ = api(self.api_client(), "delete", f"{self.PATH}/{row.pk}")
        self.assertEqual(status, 403)
        self.assertTrue(MetadataRelation.objects.filter(pk=row.pk).exists())

    def test_the_read_side_states_which_row_may_be_taken_back(self):
        """`isPublishable` is the model's answer, so the screen asks it
        instead of mirroring the origin enum of the backend (#985). Read
        through the list, because that is the query a relations screen runs."""
        self.grant("view", self.dataset)
        self.grant("view", self.service_record)
        editor = self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        harvested = MetadataRelation.objects.create(
            service_metadata=self.service_record,
            dataset_metadata=self.dataset, is_internal=False,
            origin=MetadataOriginEnum.CATALOGUE.value)
        status, answer = api(
            self.api_client(), "get",
            f"{self.PATH}?filter[dataset_metadata]={self.dataset.pk}")
        self.assertEqual(status, 200, answer)
        rows = {row["id"]: row for row in answer["data"]}
        self.assertIs(
            rows[str(editor.pk)]["attributes"]["isPublishable"], True)
        self.assertIs(
            rows[str(harvested.pk)]["attributes"]["isPublishable"], False)

    def test_the_pair_group_is_askable_from_either_screen(self):
        """The two filter terms the pair group of a record screen needs are
        declared terms of this endpoint - #1080's rule that a screen sends
        nothing the endpoint does not answer - and they find the one row from
        either side of the coupling."""
        row = self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        self.grant("view", self.dataset)
        self.grant("view", self.service_record)
        for own, partner, obj in (
                ("dataset_metadata", "service_metadata", self.dataset),
                ("service_metadata", "dataset_metadata", self.service_record)):
            status, answer = api(
                self.api_client(), "get",
                f"{self.PATH}?filter[{own}]={obj.pk}"
                f"&filter[{partner}__isnull]=false")
            self.assertEqual(status, 200, answer)
            self.assertEqual(
                [record["id"] for record in answer["data"]], [str(row.pk)],
                f"the pair group of {own} answers something else")

    def test_the_partner_of_a_pair_is_includable(self):
        """The graph of the relations screen asks the ends of a row by
        `include` and asks the title it shows through a sparse fieldset, so the
        pair ends have to answer like the five element columns do (#985)."""
        row = self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)
        self.grant("view", self.dataset)
        self.grant("view", self.service_record)
        status, answer = api(
            self.api_client(), "get",
            f"{self.PATH}/{row.pk}?include=datasetMetadata"
            "&fields[DatasetMetadataRecord]=title")
        self.assertEqual(status, 200, answer)
        included = {
            entry["type"]: entry for entry in answer.get("included", [])}
        self.assertIn("DatasetMetadataRecord", included, answer)
        self.assertEqual(
            included["DatasetMetadataRecord"]["id"], str(self.dataset.pk))
        self.assertEqual(
            included["DatasetMetadataRecord"]["attributes"],
            {"title": "Coupled dataset"},
            "the sparse fieldset of the include did not travel")


class RelationPublishRoundTripTests(CouplingFixtures, TestCase):
    """The pair through the ONE reverse mapper (#985)."""

    def setUp(self):
        self.make_parts()

    def _declare(self):
        return self.service_record.add_record_relation(
            self.dataset, origin=MetadataOriginEnum.EDITOR.value,
            is_internal=True)

    def _operates_on(self):
        """The operatesOn rows of the service record's stored document.

        Asked of a FRESH instance: the publish writes through the row, so the
        document read here is the committed one, never an earlier in-memory
        copy of the test's record object.
        """
        record = ServiceMetadataRecord.objects.get(pk=self.service_record.pk)
        publish_document(record)
        records = MDMetadataXmlMapper.extract_mapped_values(
            record.xml_backup_file.read())
        for mapper_record in records:
            if mapper_record["model"].endswith("ServiceMetadataRecord"):
                return mapper_record["values"].get("operates_on") or []
        self.fail("the service record is not in its own document")

    def test_a_declared_pair_serializes_as_operates_on(self):
        self._declare()
        rows = self._operates_on()
        self.assertEqual(rows, [{
            "uuidref": str(self.dataset.file_identifier),
            "href": self.dataset.origin_url}])

    def test_republishing_adds_nothing_a_second_time(self):
        self._declare()
        self._operates_on()  # publishes once
        self.assertEqual(len(self._operates_on()), 1)
        self.assertEqual(len(self._operates_on()), 1)

    def test_the_heal_of_a_replaced_document_carries_the_declaration_back(self):
        """A re-harvest replaced the stored document: the next publish heals."""
        self._declare()
        self._operates_on()
        # the harvest posture of D7.4: the document is the catalogues and may
        # be replaced wholesale - UPDATE, not save(), because the point is a
        # stored document which lost the declaration without any editor write
        ServiceMetadataRecord.objects.filter(
            pk=self.service_record.pk).update(xml_backup_file="")
        rows = self._operates_on()
        self.assertEqual(len(rows), 1)

    def test_take_back_removes_exactly_the_declared_row(self):
        row = self._declare()
        other = DatasetMetadataRecord.objects.create(
            metadata_contact=self.contact, dataset_contact=self.contact,
            title="Other dataset", code_space="de.mrmap.",
            code="other-dataset", file_identifier="de.mrmap.other",
            origin_url="https://catalogue.example/other.xml")
        self.service_record.add_record_relation(
            other, origin=MetadataOriginEnum.EDITOR.value, is_internal=True)
        self.assertEqual(len(self._operates_on()), 2)
        row.take_back()
        rows = self._operates_on()
        self.assertEqual(rows, [{
            "uuidref": str(other.file_identifier), "href": other.origin_url}])

    def test_only_the_standards_serializable_kind_is_written(self):
        # the curator's own kind, but not an EDITOR declaration: LOCAL_ONLY
        MetadataRelation.objects.create(
            service_metadata=self.service_record,
            dataset_metadata=self.dataset, is_internal=True,
            origin=MetadataOriginEnum.CATALOGUE.value)
        # and a CURATED pair whose dataset has no printable location
        self.dataset.origin_url = ""
        self.dataset.save(mark_customized=False)
        self._declare()
        self.assertEqual(self._operates_on(), [])

    def test_operatesOn_evidence_the_harvest_brought_in_stays(self):
        """A harvested row beside the declaration is not the record's row."""
        harvest_doc = b"""<?xml version="1.0" encoding="UTF-8"?>
<MD_Metadata xmlns="http://www.isotc211.org/2005/gmd"
             xmlns:gco="http://www.isotc211.org/2005/gco"
             xmlns:srv="http://www.isotc211.org/2005/srv"
             xmlns:xlink="http://www.w3.org/1999/xlink">
  <fileIdentifier><gco:CharacterString>%s</gco:CharacterString></fileIdentifier>
  <dateStamp><gco:DateTime>2026-01-01T00:00:00</gco:DateTime></dateStamp>
  <hierarchyLevel><MD_ScopeCode
      codeList="http://wis.wmo.int/2011/schemata/iso19139_2007/schema/resources/Codelist/ML_gmxCodelists.xml#MD_ScopeCode"
      codeListValue="service"/></hierarchyLevel>
  <identificationInfo><srv:SV_ServiceIdentification>
    <srv:operatesOn uuidref="urn:uuid:harvested" xlink:href="https://other.example/doc"/>
  </srv:SV_ServiceIdentification></identificationInfo>
</MD_Metadata>""" % self.service_record.file_identifier.encode()
        self.service_record.xml_backup_file = ContentFile(
            harvest_doc, name="xml_backup.xml")
        self.service_record.save(mark_customized=False)
        self._declare()
        rows = self._operates_on()
        self.assertIn({"uuidref": "urn:uuid:harvested",
                       "href": "https://other.example/doc"}, rows)
        self.assertIn({"uuidref": str(self.dataset.file_identifier),
                       "href": self.dataset.origin_url}, rows)
        # and taking the declaration back leaves the harvested strand alone
        MetadataRelation.objects.filter(
            service_metadata=self.service_record,
            dataset_metadata=self.dataset).first().take_back()
        rows = self._operates_on()
        self.assertEqual(rows, [{"uuidref": "urn:uuid:harvested",
                                 "href": "https://other.example/doc"}])

    def test_an_ambiguous_identifier_still_serializes_the_coupled_record(self):
        """The AC's ambiguity case: the coupling is by PK, so the identifier
        collision never selects the wrong end. A SERVICE record sharing the
        dataset's fileIdentifier (the collision the per-kind uniqueness of the
        record tables still allows) leaves the declaration unambiguous: the
        row names the coupled dataset's identifier AND its location."""
        twin = ServiceMetadataRecord.objects.create(
            metadata_contact=self.contact,
            title="Twin service record", code="twin-service",
            file_identifier=self.dataset.file_identifier)
        self.assertEqual(twin.file_identifier, self.dataset.file_identifier)
        self._declare()
        rows = self._operates_on()
        self.assertEqual(rows, [{
            "uuidref": str(self.dataset.file_identifier),
            "href": self.dataset.origin_url}])
