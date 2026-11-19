"""The extent editing API of issue #1246: time rows, contacts, record write.

The metadata editor edits the record's extents through the ordinary json:api
resources - no bespoke action endpoints (the cross-cutting decision of the
#1238 review):

* the time-extents resource answers LIST/RETRIEVE/CREATE only - a time row
  is a lookup shared by records, so PATCH/DELETE on an existing row answer
  405 rather than drift every document which references it; creating a row
  with an end before its begin answers the 400 the model's CHECK constraint
  would otherwise answer as a raw DataError;
* the contact resource answers how many rows already carry each contact
  (`usage_count`), which is the reuse hint of the contact chooser;
* a record PATCH may name the extent members: the bounding geometry as the
  GeoJSON the serializer field parses, the time extents as the M2M
  relationship of already created rows (#1246). Since both configs answer a
  `_reverse_parser`, the round trip admission of #1244 lets the members
  through and the published document carries the new values.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from guardian.shortcuts import assign_perm
from lxml import etree
from rest_framework.test import APIClient
from registry.mappers.publish import publish_document
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact,
                                      MetadataProfile, TimeExtent)

JSONAPI = "application/vnd.api+json"
ISO_DATA = Path(__file__).parent / '../test_data/iso_metadata'


def api(client, method, path, body=None):
    """One json:api request, return (status, body)."""
    response = getattr(client, method)(
        path, body, format="vnd.api+json", HTTP_ACCEPT=JSONAPI)
    return response.status_code, (
        json.loads(response.content) if response.content else {})


class TimeExtentResourceTests(TestCase):
    """LIST/RETRIEVE/CREATE - and nothing more - on the time row resource."""

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.editor = get_user_model().objects.create_user(
            "extent-editor", password="test")
        cls.row = TimeExtent.objects.create(
            begin=datetime(2020, 1, 1, tzinfo=UTC),
            end=datetime(2020, 12, 31, tzinfo=UTC))

    def api_client(self):
        # not `client`: SimpleTestCase.setUp assigns self.client with its own
        # django.test.Client, which would shadow the method.
        client = APIClient()
        client.force_authenticate(user=self.editor)
        return client

    def period_body(self, begin, end):
        return {"data": {
            "type": "TimeExtent",
            "attributes": {"begin": begin, "end": end}}}

    def test_a_created_period_row_answers_and_stores(self):
        status, answer = api(self.api_client(), "post",
                             "/api/registry/time-extents",
                             self.period_body("2021-03-01T00:00:00Z",
                                              "2021-09-30T00:00:00Z"))
        self.assertEqual(status, 201, answer)
        row = TimeExtent.objects.get(pk=answer["data"]["id"])
        self.assertEqual(row.begin, datetime(2021, 3, 1, tzinfo=UTC))
        self.assertEqual(row.end, datetime(2021, 9, 30, tzinfo=UTC))

    def test_a_period_running_backwards_is_refused_by_the_serializer(self):
        """The CHECK constraint would answer a DataError; the 400 names the
        member - the inline validation the editor's period rows state."""
        status, answer = api(self.api_client(), "post",
                             "/api/registry/time-extents",
                             self.period_body("2021-09-30T00:00:00Z",
                                              "2021-03-01T00:00:00Z"))
        self.assertEqual(status, 400, answer)
        pointers = [e.get("source", {}).get("pointer", "")
                    for e in answer.get("errors", [])]
        self.assertTrue(any("end" in p for p in pointers), answer)
        self.assertEqual(TimeExtent.objects.count(), 1)

    def test_an_existing_row_can_not_be_changed_or_removed(self):
        """The rows are lookups shared by records; editing one in place would
        drift every document which references it (#1246)."""
        client = self.api_client()
        detail = f"/api/registry/time-extents/{self.row.pk}"
        patch = {"data": {"type": "TimeExtent", "id": str(self.row.pk),
                          "attributes": {"end": "2024-01-01T00:00:00Z"}}}
        self.assertEqual(api(client, "patch", detail, patch)[0], 405)
        self.assertEqual(api(client, "delete", detail)[0], 405)
        self.assertEqual(self.row.__class__.objects.get(
            pk=self.row.pk).end, datetime(2020, 12, 31, tzinfo=UTC))


class ContactUsageCountTests(TestCase):
    """The reuse hint the contact chooser of #1246 ranks its list by."""

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.admin = get_user_model().objects.create_superuser(
            "contact-admin", email="a@b.c", password="test")
        cls.used = MetadataContact.objects.create(name="Shared office")
        cls.fresh = MetadataContact.objects.create(name="Nobody's contact")
        cls.other = MetadataContact.objects.create(name="Other office")
        cls.record_a = DatasetMetadataRecord.objects.create(
            title="A record with the contact",
            metadata_contact=cls.used, dataset_contact=cls.used)
        cls.record_b = DatasetMetadataRecord.objects.create(
            title="Another one",
            metadata_contact=cls.used, dataset_contact=cls.other)

    def admin_client(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        return client

    def test_the_list_answers_the_references_per_contact(self):
        status, answer = api(self.admin_client(), "get",
                             "/api/registry/metadata-contacts")
        self.assertEqual(status, 200, answer)
        by_name = {r["attributes"]["name"]: r["attributes"]["usageCount"]
                   for r in answer["data"]}
        # used answers as the metadata contact of both records and as the
        # dataset contact of one - three references
        self.assertEqual(by_name["Shared office"], 3)
        self.assertEqual(by_name["Nobody's contact"], 0)

    def test_a_created_contact_answers_zero_and_the_detail_the_count(self):
        client = self.admin_client()
        body = {"data": {"type": "MetadataContact",
                         "attributes": {"name": "New office"}}}
        status, answer = api(client, "post",
                             "/api/registry/metadata-contacts", body)
        self.assertEqual(status, 201, answer)
        self.assertEqual(answer["data"]["attributes"]["usageCount"], 0)
        status, answer = api(
            client, "get",
            f"/api/registry/metadata-contacts/{answer['data']['id']}")
        self.assertEqual(status, 200, answer)
        self.assertEqual(answer["data"]["attributes"]["usageCount"], 0)


class RecordExtentWriteTests(TestCase):
    """The record PATCH naming the extent members, and the served document."""

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.get_or_create(username="AnonymousUser")
        cls.contact = MetadataContact.objects.create(name="Extent contact")
        cls.profile = MetadataProfile.objects.create(name="generic-extent")
        cls.editor = get_user_model().objects.create_user(
            "extent-writer", password="test")
        cls.record = DatasetMetadataRecord.objects.create(
            title="Record with extents",
            metadata_contact=cls.contact,
            dataset_contact=cls.contact,
            profile=cls.profile)
        for action in ("add", "change"):
            assign_perm(f"registry.{action}_datasetmetadatarecord",
                        cls.editor)
        assign_perm("registry.change_datasetmetadatarecord",
                    cls.editor, cls.record)

    def api_client(self):
        client = APIClient()
        client.force_authenticate(user=self.editor)
        return client

    def patch(self, attributes=None, relationships=None):
        body = {"data": {"type": "DatasetMetadataRecord",
                         "id": str(self.record.pk),
                         "attributes": attributes or {},
                         "relationships": relationships or {}}}
        return api(self.api_client(), "patch",
                   f"/api/registry/dataset-metadata/{self.record.pk}", body)

    def document(self) -> bytes:
        self.record.refresh_from_db()
        self.record.xml_backup_file.open("rb")
        return self.record.xml_backup_file.read()

    def test_the_extent_members_are_admitted_writes_now(self):
        """#1244 refused these members while no reverse parser existed; the
        reverse parsers of #1246 admit them automatically."""
        status, answer = self.patch(attributes={
            "boundingGeometry": {
                "type": "Polygon",
                "coordinates": [[[2, 48], [3, 48], [3, 49], [2, 49], [2, 48]]]}})
        self.assertEqual(status, 200, answer)
        self.record.refresh_from_db()
        self.assertIsNotNone(self.record.bounding_geometry)
        root = etree.fromstring(self.document())
        boxes = root.xpath("//*[local-name()='EX_GeographicBoundingBox']")
        self.assertEqual(len(boxes), 1)
        texts = boxes[0].xpath(
            "./*[local-name()='westBoundLongitude' or "
            "local-name()='eastBoundLongitude' or "
            "local-name()='southBoundLatitude' or "
            "local-name()='northBoundLatitude']"
            "//*[local-name()='Decimal']/text()")
        self.assertEqual(sorted(float(t) for t in texts),
                         sorted([2.0, 3.0, 48.0, 49.0]))

    def test_a_patched_time_relationship_lands_in_the_document(self):
        row = TimeExtent.objects.create(
            begin=datetime(2019, 5, 1, tzinfo=UTC),
            end=datetime(2019, 6, 1, tzinfo=UTC),
            resolution=timedelta(0))
        status, answer = self.patch(relationships={
            "timeExtents": {"data": [
                {"type": "TimeExtent", "id": str(row.pk)}]}})
        self.assertEqual(status, 200, answer)
        self.record.refresh_from_db()
        self.assertEqual(list(self.record.time_extents.all()), [row])
        doc = self.document()
        self.assertIn(b"2019-05-01T00:00:00", doc)
        self.assertIn(b"2019-06-01T00:00:00", doc)
        # and a second publish of the unchanged record writes nothing more
        publish_document(self.record)
        self.assertEqual(self.document(), doc)

    def test_the_citation_identifier_stays_refused(self):
        """The one #1242 TODO without a reverse parser: the refusal set is
        derived from the configs, so `code` stays unwritable while the
        extent members are not."""
        status, answer = self.patch(attributes={"code": "x"})
        self.assertEqual(status, 400, answer)
