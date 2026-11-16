from django.contrib.auth import get_user_model
from django.test import TestCase
from guardian.shortcuts import assign_perm

from registry.models.metadata import DatasetMetadataRecord
from tests.django.registry.tests_query_performance import QueryMeasurementMixin


class RecordListCanEditTests(QueryMeasurementMixin, TestCase):
    """``canEdit`` on the record list is paid for only by the screen asking.

    The batch edit (#1249) reads the selection's records over the list
    endpoint and sends only what the user may edit, so the list answers
    ``can_edit`` when the request names it in the sparse fieldset; every
    other list answer keeps the per-row permission checks off its cost.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_wms.json", "test_datasetmetadata.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.dataset = DatasetMetadataRecord.objects.first()
        cls.other = DatasetMetadataRecord.objects.create(
            title="Other record", code="other-record",
            metadata_contact=cls.dataset.metadata_contact,
            dataset_contact=cls.dataset.dataset_contact)

    def _editor(self, name):
        editor = get_user_model().objects.create_user(name, password="test")
        assign_perm("registry.change_datasetmetadatarecord", editor)
        return editor

    def test_the_plain_list_answer_holds_no_permission_fields(self):
        self.user = self._editor("list-plain")
        status, body, _ = self.request(
            "/api/registry/dataset-metadata", user="user")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["data"])
        for row in body["data"]:
            self.assertNotIn("canEdit", row["attributes"])
            self.assertNotIn("canDelete", row["attributes"])

    def test_a_named_sparse_fieldset_answers_can_edit_per_row(self):
        editor = self._editor("list-editor")
        assign_perm(
            "registry.change_datasetmetadatarecord", editor, self.dataset)
        self.user = editor
        status, body, _ = self.request(
            "/api/registry/dataset-metadata", user="user",
            **{"fields[DatasetMetadataRecord]": "id,title,can_edit"})
        self.assertEqual(status, 200, body)
        by_id = {row["id"]: row for row in body["data"]}
        # the permission is answered per record, not per request: the editor
        # may change the granted record and none of the others
        self.assertTrue(
            by_id[str(self.dataset.pk)]["attributes"]["canEdit"], body)
        self.assertFalse(
            by_id[str(self.other.pk)]["attributes"]["canEdit"], body)
        # can_delete stays stripped even when named - the list never answers it
        status, body, _ = self.request(
            "/api/registry/dataset-metadata", user="user",
            **{"fields[DatasetMetadataRecord]": "id,can_edit,can_delete"})
        self.assertEqual(status, 200, body)
        for row in body["data"]:
            self.assertIn("canEdit", row["attributes"])
            self.assertNotIn("canDelete", row["attributes"])

    def test_a_model_grant_alone_is_answered_false_on_every_row(self):
        self.user = self._editor("list-model-only")
        status, body, _ = self.request(
            "/api/registry/dataset-metadata", user="user",
            **{"fields[DatasetMetadataRecord]": "id,can_edit"})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["data"])
        for row in body["data"]:
            self.assertFalse(row["attributes"]["canEdit"])

    def test_the_detail_action_answers_can_edit_unasked(self):
        """The detail screen keeps its answer: only the list gates on the
        sparse fieldset, retrieve stays as it was (#1243's editor form)."""
        self.user = self._editor("list-detail")
        status, body, _ = self.request(
            f"/api/registry/dataset-metadata/{self.dataset.pk}", user="user")
        self.assertEqual(status, 200, body)
        self.assertIn("canEdit", body["data"]["attributes"])
