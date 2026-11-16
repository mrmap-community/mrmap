"""The create/update API for metadata records (#1241).

The record resources follow the default json:api CRUD contract - POST/PUT/
PATCH on the record endpoints, no bespoke action endpoints (the cross-cutting
decision of the #1238 review). What a record write answers is pinned here:

* POST of a minimal payload (profile optional, title, the record's contacts)
  creates a stored record with the server-assigned uuid, `origin` EDITOR -
  the value of a curator creation, the reading of the AC's "origin=
  customized" on the existing enum, the issue carries the word for review -
  `is_customized` True, because a record which came into existence at the
  curator's desk is curated content and no catalogue's copy (#1248), and the
  generic profile the creation paths fall back to (#1240);
* a creation may name the record's file identifier and the answer to a
  collision is a 400 pointing at that field, before the row is written; left
  blank, the model generates the uuid. The identifier stays read-only from the
  second request on (#1248);
* PATCH touches only the sent fields and marks the record through the normal
  model save: `is_customized=True` and `date_stamp` bumped, the side effects
  the harvest overwrite gate of #1244 relies on;
* a write which names a read-only field is a 400 naming the field via
  `errors[].source.pointer`, never the silent drop a `read_only` DRF field
  performs today (#1240 pinned those fields as readOnly);
* the profile's structural rules are asked as part of the same request
  (#1243), fail-closed for rule shapes this version can not assess;
* a successful save IS the publish (#1244): the record's ISO document is
  regenerated from the saved row inside the same transaction - the round trip
  itself is pinned by `tests_metadata_record_publish`;
* the permission behaviour is today's guardian `canEdit`/`canDelete` with no
  new role concept.

And the activation gate: since #1244 integrates the round trip (a successful
save regenerates the served ISO document in the same transaction), the shipped
default answers the write paths openly; the gate itself stays a deployment
posture - while ``MRMAP_METADATA_EDITOR_WRITES_ENABLED`` is off, public
POST/PUT/PATCH answer 403 with the reason. The closed-gate class pins that
posture; the write classes above run without an override and pin the
default-open posture.
"""

import json
from datetime import timedelta
from uuid import UUID

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from guardian.shortcuts import assign_perm
from lxml import etree
from rest_framework.test import APIClient
from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataProfile, ServiceMetadataRecord)
from registry.serializers.metadata import (ApplicationMetadataRecordSerializer,
                                           DatasetMetadataRecordSerializer,
                                           ServiceMetadataRecordSerializer)
from tests.django.registry.tests_metadata_profile import ensure_generic_profile

JSONAPI = "application/vnd.api+json"


def api(client, method, path, body=None):
    """One json:api request, return (status, body)."""
    response = getattr(client, method)(
        path, body, format="vnd.api+json", HTTP_ACCEPT=JSONAPI)
    return response.status_code, (
        json.loads(response.content) if response.content else {})


class RecordWriteModelSemanticsTests(TestCase):
    """What the model save must do before any endpoint is allowed to write.

    The harvest overwrite gate compares date stamps
    (`get_or_create_metadatarecord`); the bump of the editor save and the
    untouched stamp of the harvesting save are the two halves of curated
    content surviving a re-harvest (#1241, gate unchanged per #1244).
    """

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name="Save semantics")

    def _record(self):
        return DatasetMetadataRecord.objects.create(
            title="Stamped by its creator", dataset_contact=self.contact,
            metadata_contact=self.contact)

    def test_an_editor_style_update_bumps_the_stamp_and_flags_the_record(self):
        record = self._record()
        stamp = record.date_stamp
        record.abstract = "edited at the desk"
        record.save()
        self.assertTrue(record.is_customized)
        self.assertGreater(record.date_stamp, stamp)

    def test_a_harvesting_write_keeps_the_parsed_stamp_and_the_flag(self):
        """mark_customized=False means "the catalogue wrote this" (#858)."""
        record = self._record()
        old = record.date_stamp - timedelta(days=400)
        record.date_stamp = old
        record.save(mark_customized=False)
        reloaded = DatasetMetadataRecord.objects.get(pk=record.pk)
        self.assertFalse(reloaded.is_customized)
        self.assertEqual(reloaded.date_stamp, old)

    def test_creation_keeps_both_side_effects_off(self):
        record = self._record()
        self.assertFalse(record.is_customized)
        self.assertIsNotNone(record.date_stamp)


class RecordWriteSerializerCreationTests(TestCase):
    """The serializer-level creation path of all three record resources (#1241).

    Asked one level below the endpoint, in the shape validation hands it -
    the request-level behaviour of the same rules is pinned by the endpoint
    tests below.
    """

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name="Serializer contact")
        cls.profile = ensure_generic_profile()

    def _create(self, serializer_class, **attrs):
        serializer = serializer_class(context={"request": None})
        return serializer.create({
            "title": "Created over the api layer",
            "metadata_contact": self.contact,
            **attrs,
        })

    def test_a_created_service_record_answers_the_editor_origin(self):
        record = self._create(ServiceMetadataRecordSerializer)
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)
        self.assertEqual(record.profile_id, self.profile.pk)

    def test_a_created_dataset_record_answers_the_editor_origin(self):
        record = self._create(
            DatasetMetadataRecordSerializer, dataset_contact=self.contact)
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)

    def test_a_created_application_record_answers_the_editor_origin(self):
        record = self._create(
            ApplicationMetadataRecordSerializer,
            application_contact=self.contact)
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)

    def test_a_created_record_is_curated_content_of_every_kind(self):
        """#1248: a record authored here is customized from its first row on."""
        for serializer, attrs in (
                (ServiceMetadataRecordSerializer, {}),
                (DatasetMetadataRecordSerializer,
                 {"dataset_contact": self.contact}),
                (ApplicationMetadataRecordSerializer,
                 {"application_contact": self.contact})):
            with self.subTest(serializer=serializer.__name__):
                self.assertTrue(self._create(serializer, **attrs).is_customized)


class RecordWriteApiTests(TestCase):
    """The write endpoints at the shipped default, gate open since #1244."""

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Write contact")
        cls.profile = ensure_generic_profile()
        cls.curator = get_user_model().objects.create_user(
            "record-curator", password="test")
        cls.record = DatasetMetadataRecord.objects.create(
            title="Harvested dataset record",
            abstract="the abstract before the edit",
            dataset_contact=cls.contact,
            metadata_contact=cls.contact,
            profile=cls.profile)

    def grant(self, action, model, obj=None):
        permission = f"registry.{action}_{model._meta.model_name}"
        assign_perm(permission, self.curator, obj)

    def dataset_body(self, attributes=None, relationships=None, pk=None):
        data = {"type": "DatasetMetadataRecord",
                "attributes": attributes or {},
                "relationships": relationships or {}}
        if pk:
            data["id"] = str(pk)
        return {"data": data}

    def contact_relation(self, name, contact):
        return {name: {"data": {
            "type": "MetadataContact", "id": str(contact.pk)}}}

    def test_a_minimal_post_stores_the_record_the_editor_can_edit(self):
        """profile + title + contact, per json:api (acceptance criteria)."""
        self.grant("add", DatasetMetadataRecord)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        body = self.dataset_body(
            attributes={"title": "Created at the desk"},
            relationships={
                **self.contact_relation("metadataContact", self.contact),
                **self.contact_relation("datasetContact", self.contact)})
        status, answer = api(client, "post", "/api/registry/dataset-metadata", body)
        self.assertEqual(status, 201, answer)
        record = DatasetMetadataRecord.objects.get(pk=answer["data"]["id"])
        # server-assigned uuid - the payload named no id
        self.assertEqual(UUID(answer["data"]["id"]), record.pk)
        self.assertEqual(record.title, "Created at the desk")
        # "origin='customized'": the enum value of the curator creation; the
        # word of the AC named on the existing MetadataOriginEnum.EDITOR
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)
        # the #1240 creation path: no profile named means the generic one
        self.assertEqual(record.profile_id, self.profile.pk)
        # the creation is itself the curation: the record is authored here and
        # is no catalogue's copy, which is what the flag answers (#1248)
        self.assertTrue(record.is_customized)
        # the update side effects stay with an update: the creation carries its
        # own stamp and no editor has changed a field of it yet
        self.assertIsNotNone(record.date_stamp)

    def test_a_post_without_the_model_grant_is_denied(self):
        """Permission behaviour is today's canEdit/canDelete, no new concept."""
        client = APIClient()
        client.force_authenticate(user=self.curator)
        body = self.dataset_body(
            attributes={"title": "Nobody granted this"},
            relationships={
                **self.contact_relation("metadataContact", self.contact),
                **self.contact_relation("datasetContact", self.contact)})
        status, answer = api(client, "post", "/api/registry/dataset-metadata", body)
        self.assertEqual(status, 403, answer)
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)

    def test_a_partial_update_touches_only_the_sent_field(self):
        self.grant("change", DatasetMetadataRecord)
        self.grant("change", DatasetMetadataRecord, self.record)
        old_stamp = self.record.date_stamp
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            self.dataset_body(attributes={"title": "Curated title"},
                              pk=self.record.pk))
        self.assertEqual(status, 200, answer)
        record = DatasetMetadataRecord.objects.get(pk=self.record.pk)
        self.assertEqual(record.title, "Curated title")
        # the untouched field answers what it held
        self.assertEqual(record.abstract, "the abstract before the edit")
        # the side effects of the normal model save (#1241 AC 2)
        self.assertTrue(record.is_customized)
        self.assertGreater(record.date_stamp, old_stamp)

    def test_an_update_without_the_object_grant_is_denied(self):
        """The model grant alone stays what canEdit answers today."""
        self.grant("change", DatasetMetadataRecord)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            self.dataset_body(attributes={"title": "Model grant is not enough"},
                              pk=self.record.pk))
        self.assertEqual(status, 403, answer)
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "Harvested dataset record")

    def test_a_write_to_a_read_only_field_names_the_field_via_a_pointer(self):
        """file_identifier/date_stamp/origin/is_broken: the read-only pin of #1240."""
        self.grant("change", DatasetMetadataRecord)
        self.grant("change", DatasetMetadataRecord, self.record)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            self.dataset_body(
                attributes={"title": "A good title", "dateStamp":
                            "2020-01-01T00:00:00Z"},
                pk=self.record.pk))
        self.assertEqual(status, 400, answer)
        errors = answer["errors"]
        pointers = [error["source"]["pointer"] for error in errors]
        self.assertIn("/data/attributes/dateStamp", pointers)
        # the refused write changed nothing
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "Harvested dataset record")

    def test_a_post_naming_several_read_only_fields_refuses_them_all(self):
        """Every member the server owns, on every verb.

        `file_identifier` is the one member a creation may name (#1248), so it
        is not among the offenders here — its own tests below pin what a
        creation does with it and that an update still may not name it.
        """
        self.grant("add", DatasetMetadataRecord)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "post", "/api/registry/dataset-metadata",
            self.dataset_body(
                attributes={
                    "title": "Stamped by the client",
                    "dateStamp": "2020-01-01T00:00:00Z",
                    "origin": MetadataOriginEnum.CATALOGUE.value,
                    "isBroken": True},
                # the required contacts must be in the payload: without them,
                # the field-level required errors pre-empt the validate()
                # pass which answers the read-only refusal
                relationships={
                    **self.contact_relation("metadataContact", self.contact),
                    **self.contact_relation("datasetContact", self.contact)}))
        self.assertEqual(status, 400, answer)
        pointers = {error["source"]["pointer"] for error in answer["errors"]}
        self.assertEqual(pointers, {
            "/data/attributes/dateStamp",
            "/data/attributes/origin",
            "/data/attributes/isBroken"})

    def test_a_profile_which_names_rules_refuses_the_write_fail_closed(self):
        """A rule object of a shape the evaluator can not assess (the shape
        #1243 predates) must never let a payload pass as validated."""
        governed = MetadataProfile.objects.create(
            name="iso19139-gdi-de", label="GDI-DE",
            rules=[{"type": "gdi-de-mandatory"}])
        self.record.profile = governed
        self.record.save(mark_customized=False)
        self.grant("change", DatasetMetadataRecord)
        self.grant("change", DatasetMetadataRecord, self.record)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            self.dataset_body(attributes={"title": "Anything"},
                              pk=self.record.pk))
        self.assertEqual(status, 400, answer)
        self.assertIn("rules", answer["errors"][0]["detail"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "Harvested dataset record")

    def test_a_service_record_post_stamps_the_editor_origin(self):
        self.grant("add", ServiceMetadataRecord)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        body = {"data": {
            "type": "ServiceMetadataRecord",
            "attributes": {"title": "Service record created at the desk"},
            "relationships": self.contact_relation(
                "metadataContact", self.contact)}}
        status, answer = api(client, "post", "/api/registry/service-metadata", body)
        self.assertEqual(status, 201, answer)
        record = ServiceMetadataRecord.objects.get(pk=answer["data"]["id"])
        self.assertEqual(record.origin, MetadataOriginEnum.EDITOR.value)


class RecordCreationFileIdentifierTests(TestCase):
    """The file identifier a creation names (#1248).

    The create screen asks the curator for the ISO ``fileIdentifier`` of the
    record they author. Three answers are pinned here, none of which leaves a
    half-written record behind: a free identifier becomes the row's value and
    the value of the document served for it; a taken one is refused with the
    pointer of the member the curator typed; a blank one lets the model
    generate the uuid. Afterwards the value is immutable — it is the identifier
    by which a catalogue's document finds the row
    (``get_or_create_metadatarecord()``), so renaming it would move the record
    to another identity instead of editing it.
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Identifier contact")
        cls.profile = ensure_generic_profile()
        cls.curator = get_user_model().objects.create_user(
            "identifier-curator", password="test")

    def grant(self, action, model, obj=None):
        assign_perm(f"registry.{action}_{model._meta.model_name}",
                    self.curator, obj)

    def curator_client(self):
        # not named `client`: TestCase._pre_setup assigns an instance
        # attribute of that name, which would shadow the method
        client = APIClient()
        client.force_authenticate(user=self.curator)
        return client

    def body(self, attributes=None, pk=None):
        contact = {"data": {
            "type": "MetadataContact", "id": str(self.contact.pk)}}
        data = {"type": "DatasetMetadataRecord",
                "attributes": {"title": "Created at the desk",
                               **(attributes or {})},
                "relationships": {"metadataContact": contact,
                                  "datasetContact": contact}}
        if pk:
            data["id"] = str(pk)
        return {"data": data}

    def test_a_named_identifier_becomes_the_row_and_the_document(self):
        self.grant("add", DatasetMetadataRecord)
        status, answer = api(
            self.curator_client(), "post", "/api/registry/dataset-metadata",
            self.body(attributes={"fileIdentifier": "de-bbk-nrw-2026-0001"}))
        self.assertEqual(status, 201, answer)
        record = DatasetMetadataRecord.objects.get(pk=answer["data"]["id"])
        self.assertEqual(record.file_identifier, "de-bbk-nrw-2026-0001")
        # row and served document agree from the first save: the publish writes
        # the row's identifier into the document's gmd:fileIdentifier (#1244)
        root = etree.fromstring(record.xml_backup)
        identifiers = root.xpath(
            "//*[local-name()='fileIdentifier']"
            "//*[local-name()='CharacterString']/text()")
        self.assertEqual(identifiers, ["de-bbk-nrw-2026-0001"])

    def test_a_collision_is_answered_on_the_field_before_the_record(self):
        DatasetMetadataRecord.objects.create(
            title="Already in the catalogue",
            dataset_contact=self.contact, metadata_contact=self.contact,
            file_identifier="de-bbk-nrw-2026-0001")
        self.grant("add", DatasetMetadataRecord)
        status, answer = api(
            self.curator_client(), "post", "/api/registry/dataset-metadata",
            self.body(attributes={"fileIdentifier": "de-bbk-nrw-2026-0001"}))
        self.assertEqual(status, 400, answer)
        self.assertEqual(
            [error["source"]["pointer"] for error in answer["errors"]],
            ["/data/attributes/fileIdentifier"])
        self.assertIn("already exists", answer["errors"][0]["detail"])
        # the refused creation wrote no row: the one which was there before is
        # still the only one carrying that identifier
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)

    def test_a_blank_identifier_is_generated_by_the_server(self):
        self.grant("add", DatasetMetadataRecord)
        status, answer = api(
            self.curator_client(), "post", "/api/registry/dataset-metadata",
            self.body(attributes={"fileIdentifier": "   "}))
        self.assertEqual(status, 201, answer)
        record = DatasetMetadataRecord.objects.get(pk=answer["data"]["id"])
        # the model's uuid4 default: a curator who does not name the record
        # gets an identifier the server generated
        self.assertEqual(UUID(record.file_identifier).hex,
                         record.file_identifier.replace("-", ""))

    def test_an_over_long_identifier_names_the_field_it_refuses(self):
        self.grant("add", DatasetMetadataRecord)
        status, answer = api(
            self.curator_client(), "post", "/api/registry/dataset-metadata",
            self.body(attributes={"fileIdentifier": "x" * 1001}))
        self.assertEqual(status, 400, answer)
        self.assertEqual(
            [error["source"]["pointer"] for error in answer["errors"]],
            ["/data/attributes/fileIdentifier"])
        self.assertEqual(DatasetMetadataRecord.objects.count(), 0)

    def test_the_identifier_is_read_only_once_the_record_exists(self):
        """The creation exception does not reach an update (#1241 stays)."""
        record = DatasetMetadataRecord.objects.create(
            title="Created, then renamed?",
            dataset_contact=self.contact, metadata_contact=self.contact,
            file_identifier="de-bbk-nrw-2026-0001")
        self.grant("change", DatasetMetadataRecord)
        self.grant("change", DatasetMetadataRecord, record)
        status, answer = api(
            self.curator_client(), "patch",
            f"/api/registry/dataset-metadata/{record.pk}",
            self.body(attributes={"fileIdentifier": "something-else"},
                      pk=record.pk))
        self.assertEqual(status, 400, answer)
        self.assertEqual(
            [error["source"]["pointer"] for error in answer["errors"]],
            ["/data/attributes/fileIdentifier"])
        record.refresh_from_db()
        self.assertEqual(record.file_identifier, "de-bbk-nrw-2026-0001")


class RecordWriteActivationGateTests(TestCase):
    """The activation gate as deployment posture: open default, closed option.

    With the round trip integrated (#1244) the shipped default answers the
    record writes openly - a curator's PATCH succeeds without any override.
    A deployment that sets ``MRMAP_METADATA_EDITOR_WRITES_ENABLED=False``
    deliberately keeps its editor read-only: POST/PUT/PATCH answer 403 with
    the reason. The gate is a deployment posture, not a grant - no permission
    bypasses it. Reads answer as always and DELETE stays at today's behaviour
    in both postures: a deletion removes the record together with the document
    served for it, so it leaves no stale document behind.
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Gate contact")
        cls.record = DatasetMetadataRecord.objects.create(
            title="Record at the gate",
            dataset_contact=cls.contact,
            metadata_contact=cls.contact)
        cls.curator = get_user_model().objects.create_user(
            "gate-curator", password="test")
        for action in ("add", "change"):
            assign_perm(
                f"registry.{action}_datasetmetadatarecord", cls.curator)
        assign_perm("registry.change_datasetmetadatarecord", cls.curator,
                    cls.record)

    def test_the_shipped_default_answers_the_write_paths_open(self):
        """No override: the record write is the ordinary CRUD answer (#1244)."""
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            {"data": {"type": "DatasetMetadataRecord",
                      "id": str(self.record.pk),
                      "attributes": {"title": "The default opens writes"}}})
        self.assertEqual(status, 200, answer)
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "The default opens writes")

    @override_settings(MRMAP_METADATA_EDITOR_WRITES_ENABLED=False)
    def test_post_and_patch_and_put_answer_403_while_the_gate_is_closed(self):
        client = APIClient()
        client.force_authenticate(user=self.curator)
        body = {"data": {"type": "DatasetMetadataRecord",
                         "attributes": {"title": "Writes are gated"},
                         "relationships": {
                             "metadataContact": {"data": {
                                 "type": "MetadataContact",
                                 "id": str(self.contact.pk)}},
                             "datasetContact": {"data": {
                                 "type": "MetadataContact",
                                 "id": str(self.contact.pk)}}}}}
        status, answer = api(client, "post", "/api/registry/dataset-metadata", body)
        self.assertEqual(status, 403, answer)
        self.assertIn("disabled", answer["errors"][0]["detail"])

        body["data"]["id"] = str(self.record.pk)
        for method in ("patch", "put"):
            status, answer = api(
                client, method,
                f"/api/registry/dataset-metadata/{self.record.pk}", body)
            self.assertEqual(status, 403, (method, answer))
        self.record.refresh_from_db()
        self.assertEqual(self.record.title, "Record at the gate")

    @override_settings(MRMAP_METADATA_EDITOR_WRITES_ENABLED=False)
    def test_a_superuser_is_refused_like_any_client(self):
        """The gate is a deployment posture, not a grant - no permission
        bypasses it."""
        admin = get_user_model().objects.create_superuser(
            "gate-admin", password="test")
        client = APIClient()
        client.force_authenticate(user=admin)
        status, answer = api(
            client, "patch",
            f"/api/registry/dataset-metadata/{self.record.pk}",
            {"data": {"type": "DatasetMetadataRecord",
                      "id": str(self.record.pk),
                      "attributes": {"title": "Even the admin"}}})
        self.assertEqual(status, 403, answer)

    @override_settings(MRMAP_METADATA_EDITOR_WRITES_ENABLED=False)
    def test_reads_answer_as_always_while_the_gate_is_closed(self):
        client = APIClient()
        status, answer = api(client, "get", "/api/registry/dataset-metadata")
        self.assertEqual(status, 200, answer)
        status, answer = api(
            client, "get", f"/api/registry/dataset-metadata/{self.record.pk}")
        self.assertEqual(status, 200, answer)

    def test_delete_stays_at_todays_behaviour(self):
        """A deletion removes the record together with its served document;
        it leaves no stale document behind, so the gate leaves it alone."""
        admin = get_user_model().objects.create_superuser(
            "gate-deleter", password="test")
        client = APIClient()
        client.force_authenticate(user=admin)
        status, _ = api(
            client, "delete",
            f"/api/registry/dataset-metadata/{self.record.pk}")
        self.assertEqual(status, 204)
        self.assertFalse(
            DatasetMetadataRecord.objects.filter(pk=self.record.pk).exists())
