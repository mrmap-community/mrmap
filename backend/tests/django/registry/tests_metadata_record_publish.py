"""A committed save IS the publish of the record's ISO document (#1244).

Decision 1 of the design document's review (§7, PR #1238): the editor's
validated save regenerates ``xml_backup_file`` from the saved row inside the
same transaction - after the commit the CSW serves exactly the content the
editor saved, and a refused write changes neither the row nor the document.
There is no draft document, no editorial state column and no lock: last
committed save wins (decision 6 of §7), and the harvest overwrite gate of
#1241 (`is_customized` plus the bumped `date_stamp`) is what protects curated
content from a re-harvest - unchanged by this issue, pinned here against the
publish because both now write the same document.

Pinned top-down:

* a successful PATCH regenerates the stored document from the committed row:
    the patched values hold, values the payload did not name carry through
    from the row and the document, `fileIdentifier` names the record and
    `dateStamp` carries the stamp the save bumped - one node, rules included;
* a POST publishes the created record's FIRST document (a doc-less record
    would poison the CSW page it appears in), derived from the kind's seed,
    so it is servable right after the commit;
* a publish that fails rolls the whole write back: fields, document and the
    failed attempt to attach the new one are one commit or none (the written
    file of a failed attempt is unreferenced garbage of the media storage,
    never served);
* the curated round trip survives a re-harvest of the older catalogue
    document (the gate, end to end through the api);
* two writes: the last committed one serves, without any token or lock;
* members the document can not carry back (read out of it by the configs but
    not writable by the write mapper - #1242 named them) are refused, so no
    enabled write leaves row, document and CSW answer apart.
"""

from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from lxml import etree
from registry.exceptions.metadata import PublishRefused
from registry.mappers.factory import MDMetadataXmlMapper
from registry.mappers.persistence.handler import PersistenceHandler
from registry.mappers.rules import evaluate_rules
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      ReferenceSystem)
from rest_framework.test import APIClient
from tests.django.registry.tests_record_validation_on_save import (
    GENERIC_RULES, api, api_body, document_without, file_identifier_of)
from tests.django.registry.tests_metadata_profile import ensure_generic_profile

ISO_DATA = Path(__file__).resolve().parents[1] / "test_data" / "iso_metadata"


def served_values(record):
    """The mapped values of the record's stored document (its CSW answer)."""
    document = record.xml_backup
    return MDMetadataXmlMapper.extract_mapped_values(document)[0]["values"]


class PublishApiMixin:
    """Curator, generic-profile record carrying the full corpus document."""

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Publishing contact")
        cls.profile = ensure_generic_profile()
        cls.doc = document_without()
        cls.fid = file_identifier_of(cls.doc)
        cls.curator = get_user_model().objects.create_user(
            "publishing-curator", password="test")

    def record(self, title="Record before the publish"):
        record = DatasetMetadataRecord.objects.create(
            title=title, file_identifier=self.fid, profile=self.profile,
            metadata_contact=self.contact, dataset_contact=self.contact)
        record.xml_backup_file.save(
            "record.xml", ContentFile(self.doc), save=False)
        record.save(mark_customized=False)
        assign_perm("registry.change_datasetmetadatarecord", self.curator)
        assign_perm("registry.change_datasetmetadatarecord", self.curator,
                    record)
        return record

    def api_client(self):
        client = APIClient()
        client.force_authenticate(user=self.curator)
        return client

    def patch_record(self, record, attributes=None, relationships=None):
        return api(self.api_client(), "patch",
                   f"/api/registry/dataset-metadata/{record.pk}",
                   api_body(pk=record.pk, attributes=attributes,
                            relationships=relationships))

    def document_bytes(self, record):
        with open(record.xml_backup_file.path, "rb") as handle:
            return handle.read()


class PublishRegenerationTests(PublishApiMixin, TestCase):
    """After a committed write the stored document is the saved record."""

    def test_a_successful_patch_rewrites_the_served_document(self):
        record = self.record()
        before = self.document_bytes(record)

        status, answer = self.patch_record(
            record, {"title": "Nach der Kuratie",
                     "abstract": "Ein kuratierter Text"})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()

        values = served_values(record)
        # the saved content serves...
        self.assertEqual(values["title"], "Nach der Kuratie")
        self.assertEqual(values["abstract"], "Ein kuratierter Text")
        # ... the document names the record it belongs to, as exactly one
        # node, and it is not the drifted fixture it was
        self.assertEqual(str(values["file_identifier"]).strip(), self.fid)
        self.assertNotEqual(self.document_bytes(record), before)
        root = etree.fromstring(self.document_bytes(record))
        self.assertEqual(len(root.xpath(
            "//*[local-name()='MD_Metadata']")), 1)
        # the stamp the harvest gate compares IS the stamp the document tells
        expected_stamp = timezone.localtime(
            record.date_stamp).replace(microsecond=0)
        self.assertEqual(values["date_stamp"], expected_stamp)
        # healed towards the row: the stored document never carried this
        # record's own title; now it answers every seeded rule
        self.assertEqual(evaluate_rules(GENERIC_RULES, record.xml_backup), [])

    def test_the_last_of_two_wins_unchallenged(self):
        """Last-write-wins (§7 decision 6): no token gates the second write,
        the last committed save is the document that serves."""
        record = self.record()
        first_stamp = record.date_stamp

        status, answer = self.patch_record(record, {"title": "Erste Kuratie"})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()
        second_stamp = record.date_stamp
        status, answer = self.patch_record(record, {"title": "Zweite Kuratie"})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()

        self.assertEqual(record.title, "Zweite Kuratie")
        self.assertGreaterEqual(second_stamp, first_stamp)
        self.assertEqual(served_values(record)["title"], "Zweite Kuratie")


class PublishAtomicityTests(PublishApiMixin, TestCase):
    """Fields and document commit together or not at all."""

    def test_a_publish_crash_rolls_the_field_save_back_with_it(self):
        record = self.record()
        before = self.document_bytes(record)
        stamp = record.date_stamp
        with patch("registry.serializers.metadata.publish_document",
                   side_effect=RuntimeError("the storage died")):
            with self.assertRaises(RuntimeError):
                self.patch_record(record, {"title": "Nie gespeichert"})
        record.refresh_from_db()
        self.assertEqual(record.title, "Record before the publish")
        self.assertEqual(record.date_stamp, stamp)
        self.assertEqual(self.document_bytes(record), before)

    def test_a_refused_publish_answers_400_and_changes_nothing(self):
        record = self.record()
        before = self.document_bytes(record)
        with patch("registry.serializers.metadata.publish_document",
                   side_effect=PublishRefused("the mapper can not render")):
            status, answer = self.patch_record(
                record, {"title": "Nie gespeichert"})
        self.assertEqual(status, 400, answer)
        self.assertIn("document", answer["errors"][0]["detail"])
        record.refresh_from_db()
        self.assertEqual(record.title, "Record before the publish")
        self.assertEqual(self.document_bytes(record), before)


class CreatedRecordPublishTests(TestCase):
    """The POST publishes the created record's first document.

    A doc-less record poisons the CSW page it appears in (`read_stored_
    documents` refuses the page for one unreadable record), so the save that
    creates the row commits a servable document with it - derived from the
    kind's seed, not from an editor template (v2, §7 decision 5).
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Creating contact")
        cls.curator = get_user_model().objects.create_user(
            "creating-curator", password="test")
        assign_perm("registry.add_datasetmetadatarecord", cls.curator)

    def test_a_created_record_serves_a_single_record_document(self):
        client = APIClient()
        client.force_authenticate(user=self.curator)
        contact = {"data": {"type": "MetadataContact",
                            "id": str(self.contact.pk)}}
        status, answer = api(client, "post", "/api/registry/dataset-metadata",
                             api_body(
                                 attributes={"title": "Neu im Katalog"},
                                 relationships={"metadataContact": contact,
                                                "datasetContact": contact}))
        self.assertEqual(status, 201, answer)
        record = DatasetMetadataRecord.objects.get(pk=answer["data"]["id"])
        self.assertTrue(record.xml_backup_file)

        values = served_values(record)
        # exactly one servable record: the created row's own identity and
        # values, of the dataset kind
        records = MDMetadataXmlMapper.extract_mapped_values(record.xml_backup)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["model"], "registry.DatasetMetadataRecord")
        self.assertEqual(values["title"], "Neu im Katalog")
        self.assertEqual(str(values["file_identifier"]).strip(),
                         str(record.file_identifier))
        self.assertIsNotNone(values["date_stamp"])
        root = etree.fromstring(record.xml_backup)
        levels = root.xpath(
            "//*[local-name()='hierarchyLevel']"
            "//*[local-name()='MD_ScopeCode']/@codeListValue")
        self.assertEqual(levels, ["dataset"])


class PublishRespectsNonRoundtrippableMembersTests(PublishApiMixin, TestCase):
    """No enabled write leaves row, document and CSW answer apart.

    Fields the configs READ out of the document but the write mapper can not
    WRITE (bounding geometry, time extents, the citation identifier - the
    TODOs #1242 named) are refused as writes; the refusal is derived from
    the configs, so the test cites two of them by their json:api member
    names and checks nothing was stored.
    """

    def test_naming_a_member_the_document_can_not_carry_back_is_refused(self):
        record = self.record()
        before = self.document_bytes(record)
        status, answer = self.patch_record(
            record, attributes={"code": "ein-code",
                                "codeSpace": "http://example.org/space"})
        self.assertEqual(status, 400, answer)
        pointers = {error["source"]["pointer"] for error in answer["errors"]}
        self.assertEqual(pointers, {
            "/data/attributes/code", "/data/attributes/codeSpace"})
        # the refused write changed nothing
        record.refresh_from_db()
        self.assertEqual(record.title, "Record before the publish")
        self.assertEqual(self.document_bytes(record), before)


class PublishSurvivesReHarvestTests(TestCase):
    """The harvest overwrite gate still protects what the editor published.

    The publish bumps nothing of its own: the row save set `is_customized`
    and carried `date_stamp` past the catalogue document, and the gate of
    `get_or_create_metadatarecord` (#858 semantics, unchanged by #1244) is
    what keeps the re-harvest of the older document from overwriting either.
    """

    XML = ISO_DATA / "dataset.xml"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.curator = get_user_model().objects.create_user(
            "reharvest-curator", password="test")

    def _persist_dataset(self):
        mapper = MDMetadataXmlMapper.from_xml(self.XML)[0]
        mapper.xml_to_django()
        PersistenceHandler(mapper).persist_all()

    def test_a_curated_publish_survives_the_reharvest_of_the_older_document(self):
        self._persist_dataset()
        record = DatasetMetadataRecord.objects.get()
        catalog_stamp = record.date_stamp
        assign_perm("registry.change_datasetmetadatarecord", self.curator)
        assign_perm("registry.change_datasetmetadatarecord", self.curator,
                    record)
        client = APIClient()
        client.force_authenticate(user=self.curator)
        status, answer = api(client, "patch",
                             f"/api/registry/dataset-metadata/{record.pk}",
                             api_body(pk=record.pk,
                                      attributes={"title": "Kuratierter Titel"}))
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()
        self.assertTrue(record.is_customized)
        # the publish wrote the curated content into the served document and
        # the save carried the stamp past the catalogue document's one - the
        # precondition the gate of #858 compares
        self.assertEqual(served_values(record)["title"], "Kuratierter Titel")
        self.assertGreater(record.date_stamp, catalog_stamp)

        # the same catalogue answers again - its document carries the older
        # stamp, so the gate leaves the row AND the published document alone
        self._persist_dataset()

        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
        record.refresh_from_db()
        self.assertEqual(record.title, "Kuratierter Titel")
        self.assertEqual(served_values(record)["title"], "Kuratierter Titel")


class ReferenceSystemPublishTests(PublishApiMixin, TestCase):
    """A relation written through the api reaches the served document."""

    def test_a_reference_system_patch_lands_in_the_served_document(self):
        system = ReferenceSystem.objects.create(code="4326", prefix="EPSG")
        record = self.record()

        status, answer = self.patch_record(record, relationships={
            "referenceSystems": {"data": [
                {"type": "ReferenceSystem", "id": str(system.pk)}]}})
        self.assertEqual(status, 200, answer)
        record.refresh_from_db()

        rows = served_values(record)["reference_systems"]
        self.assertIn({"code": "4326", "prefix": "EPSG"},
                      [{k: row.get(k) for k in ("code", "prefix")}
                       for row in rows])
