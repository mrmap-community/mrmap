import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from django.urls import resolve
from guardian.shortcuts import assign_perm
from rest_framework.test import APIRequestFactory, force_authenticate
from django.utils.timezone import now
from registry.models.metadata import (DatasetMetadataRecord, IsoCategory,
                                      Language, Licence, MetadataRelation,
                                      ServiceMetadataRecord, TimeExtent)
from registry.models.service import Layer, WebMapService
from tests.django.registry.tests_query_performance import QueryMeasurementMixin


class RecordDetailsTests(QueryMeasurementMixin, TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_csw.json", "test_wms.json", "test_datasetmetadata.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.dataset = DatasetMetadataRecord.objects.first()
        cls.service = ServiceMetadataRecord.objects.create(
            title="Service record", code="service-record",
            metadata_contact=cls.dataset.metadata_contact)
        cls.licence = Licence.objects.create(name="Open licence", identifier="test")
        cls.extent = TimeExtent.objects.create(begin=now(), end=now(), resolution=timedelta(0))
        for record in (cls.dataset, cls.service):
            record.licence = cls.licence
            record.save()
            record.time_extents.add(cls.extent)
            record.languages.add(Language.objects.first())
        cls.dataset.categories.add(IsoCategory.objects.first())
        MetadataRelation.objects.create(
            dataset_metadata=cls.dataset, layer=Layer.objects.first(), origin=5)
        cls.link = MetadataRelation.objects.create(
            service_metadata=cls.service, wms=WebMapService.objects.first(),
            origin=5, is_internal=True)

    def test_record_detail_includes_and_permissions(self):
        for resource, record in (("dataset", self.dataset), ("service", self.service)):
            include = "metadataContact,licence,keywords,referenceSystems,timeExtents,languages,createdBy,lastModifiedBy,harvestedThrough"
            if resource == "dataset":
                include += ",datasetContact,categories"
            path = f"/api/registry/{resource}-metadata/{record.pk}"
            status, body, queries = self.request(path, include=include, **{"fields[CatalogueService]": "title,string_representation"})
            self.assertEqual(status, 200, body)
            self.assertFalse(body["data"]["attributes"]["canEdit"])
            self.assertFalse(body["data"]["attributes"]["canDelete"])
            types = {row["type"] for row in body["included"]}
            self.assertTrue({"MetadataContact", "Licence", "TimeExtent", "Language"} <= types)
            self.assertLessEqual(len(queries), 25)
            licence = next(row for row in body["included"] if row["type"] == "Licence")
            self.assertEqual(licence["attributes"]["name"], "Open licence")
            extent = next(row for row in body["included"] if row["type"] == "TimeExtent")
            self.assertIn("begin", extent["attributes"])

    def test_metadata_relations_expose_provenance_and_filter(self):
        status, body, _ = self.request("/api/registry/metadata-relations", **{
            "filter[service_metadata]": str(self.service.pk), "filter[wms__isnull]": "false"})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["attributes"]["origin"], 5)
        self.assertTrue(body["data"][0]["attributes"]["isInternal"])
        self.assertEqual(body["data"][0]["relationships"]["wms"]["data"]["id"], str(self.link.wms_id))

    def test_change_log_contains_field_diffs_and_is_read_only(self):
        for resource, record in (("dataset", self.dataset), ("service", self.service)):
            record.title = "Corrected title"
            record.save()
            path = f"/api/registry/historical-{resource}-metadata"
            status, body, _ = self.request(path, include="historyUser", **{
                "filter[history_relation]": str(record.pk)})
            self.assertEqual(status, 200, body)
            changes = [change for row in body["data"] for change in row["attributes"].get("delta") or []]
            self.assertTrue(any(change["field"] == "title" and change["new"] == "Corrected title" for change in changes))

    def test_superuser_actions_match_backend_permissions(self):
        self.user = get_user_model().objects.create_superuser("record-admin", password="test")
        status, body, _ = self.request(f"/api/registry/service-metadata/{self.service.pk}", user="user")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["data"]["attributes"]["canEdit"])
        self.assertTrue(body["data"]["attributes"]["canDelete"])

    def test_nested_record_lists_resolve(self):
        for resource, record, relations in (
                ("dataset", self.dataset, ("keywords", "licence", "metadata-contact", "dataset-contact", "referencesystems", "csws", "layers", "featuretypes")),
                ("service", self.service, ("keywords", "licence", "metadata-contact", "referencesystems", "csws", "wms", "wfs"))):
            for relation in relations:
                with self.subTest(resource=resource, relation=relation):
                    status, body, _ = self.request(f"/api/registry/{resource}-metadata/{record.pk}/{relation}")
                    self.assertEqual(status, 200, body)

    def test_relation_graph_include_has_named_targets(self):
        status, body, queries = self.request("/api/registry/metadata-relations", **{
            "filter[service_metadata]": str(self.service.pk), "include": "wms,wfs,csw",
            "fields[WebMapService]": "title,stringRepresentation"})
        self.assertEqual(status, 200, body)
        self.assertTrue(body["included"][0]["attributes"]["title"])
        self.assertLessEqual(len(queries), 10)

    def test_the_groups_of_the_relations_screen_are_its_filled_columns(self):
        """The relations tab reads its groups from which column a row fills (#1268).

        The tab asks one bounded query per column of MetadataRelation which a row
        can fill, beside the column which holds the record, so a service record is
        asked for the elements it describes as well and not for its services alone.
        The graph of the same tab draws itself from one request which includes every
        column, and a column no row fills must not disturb that answer.
        """
        path = "/api/registry/metadata-relations"
        described = MetadataRelation.objects.create(
            service_metadata=self.service, layer=Layer.objects.first(), origin=1)
        for column, expected in (("layer", [described]), ("wms", [self.link]),
                                 ("feature_type", []), ("wfs", []), ("csw", [])):
            with self.subTest(column=column):
                status, body, _ = self.request(path, user="user", **{
                    "filter[service_metadata]": str(self.service.pk),
                    f"filter[{column}__isnull]": "false"})
                self.assertEqual(status, 200, body)
                # the count of the group is the answer of its own query: the tab
                # shows it beside the name of the group and pages its rows with it
                self.assertEqual(
                    len(body["data"]), body["meta"]["pagination"]["count"], body)
                self.assertEqual(
                    self.ids_of(body), [str(row.pk) for row in expected])
        status, body, queries = self.request(path, user="user", **{
            "filter[service_metadata]": str(self.service.pk),
            "include": "layer,featureType,wms,wfs,csw",
            **{f"fields[{resource}]": "title,string_representation" for resource in (
                "Layer", "FeatureType", "WebMapService", "WebFeatureService",
                "CatalogueService")}})
        self.assertEqual(status, 200, body)
        # both couplings of the record are answered, the layer as well as the
        # service, each with the name the graph and the tables of the tab show
        self.assertEqual(
            {row["type"] for row in body["included"]}, {"Layer", "WebMapService"})
        self.assertTrue(
            all(row["attributes"].get("title") for row in body["included"]), body)
        self.assertLessEqual(len(queries), 10)

    def test_dataset_graph_include_uses_inherited_layer_titles(self):
        status, body, queries = self.request("/api/registry/metadata-relations", **{
            "filter[dataset_metadata]": str(self.dataset.pk), "include": "layer,featureType,csw",
            "fields[Layer]": "title,stringRepresentation"})
        self.assertEqual(status, 200, body)
        layer = next(row for row in body["included"] if row["type"] == "Layer")
        self.assertTrue(layer["attributes"]["title"])
        self.assertLessEqual(len(queries), 10)

    def test_edit_permission_requires_model_and_object_grants(self):
        reader = get_user_model().objects.create_user("record-reader", password="test")
        assign_perm("registry.change_datasetmetadatarecord", reader)
        self.user = reader
        path = f"/api/registry/dataset-metadata/{self.dataset.pk}"
        status, body, _ = self.request(path, user="user")
        self.assertEqual(status, 200, body)
        self.assertFalse(body["data"]["attributes"]["canEdit"])
        assign_perm("registry.change_datasetmetadatarecord", reader, self.dataset)
        status, body, _ = self.request(path, user="user")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["data"]["attributes"]["canEdit"])
        self.assertFalse(body["data"]["attributes"]["canDelete"])

    def test_history_endpoints_reject_writes(self):
        admin = get_user_model().objects.create_superuser("history-admin", password="test")
        for resource in ("dataset", "service"):
            path = f"/api/registry/historical-{resource}-metadata"
            request = APIRequestFactory().post(path, {}, format="vnd.api+json")
            force_authenticate(request, user=admin)
            callback, _, kwargs = resolve(path)
            self.assertEqual(callback(request, **kwargs).status_code, 405)

    def test_change_log_serializes_geometry_additions_changes_and_removals(self):
        first = MultiPolygon(Polygon.from_bbox((5, 47, 15, 55)), srid=4326)
        second = MultiPolygon(Polygon.from_bbox((6, 48, 14, 54)), srid=4326)
        for resource, record in (("dataset", self.dataset), ("service", self.service)):
            record.bounding_geometry = None
            record.save()
            for old, new in ((None, first), (first, second), (second, None)):
                with self.subTest(resource=resource, old=old, new=new):
                    record.bounding_geometry = new
                    record.save()
                    status, body, _ = self.request(
                        f"/api/registry/historical-{resource}-metadata",
                        include="historyUser", sort="-historyDate", **{
                            "filter[history_relation]": str(record.pk),
                            "fields[User]": "username,string_representation",
                            "page[size]": 100,
                        })
                    self.assertEqual(status, 200, body)
                    change = next(
                        change for row in body["data"]
                        for change in row["attributes"].get("delta") or []
                        if change["field"] == "bounding_geometry")
                    self.assertEqual(change["old"], json.loads(old.geojson) if old else None)
                    self.assertEqual(change["new"], json.loads(new.geojson) if new else None)
