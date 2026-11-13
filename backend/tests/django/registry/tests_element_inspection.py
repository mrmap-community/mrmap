from datetime import datetime, timezone

from django.test import TestCase
from django.contrib.gis.geos import MultiPolygon, Polygon
from registry.enums.metadata import MetadataOriginEnum
from registry.models.metadata import (DatasetMetadataRecord,
                                      FeatureTypeRemoteMetadata,
                                      MetadataRelation, TimeExtent)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation)
from registry.models.service import FeatureType, Layer
from tests.django.registry.tests_query_performance import (SERVICES,
                                                           QueryMeasurementMixin)


class ElementInspectionIncludeTests(QueryMeasurementMixin, TestCase):
    """The read oriented inspector reads Layer and FeatureType details with the
    relationships it renders already included."""

    fixtures = SERVICES

    def test_access_flags_describe_rules_for_the_selected_element(self):
        for model, rule_model, relation, endpoint, service_endpoint in (
                (Layer, AllowedWebMapServiceOperation, 'secured_layers', 'layers', 'wms'),
                (FeatureType, AllowedWebFeatureServiceOperation,
                 'secured_feature_types', 'featuretypes', 'wfs')):
            element = model.objects.filter(service__title=f'{service_endpoint.upper()}1').order_by('pk').first()
            other = model.objects.filter(service=element.service).exclude(pk=element.pk).first()
            self.assertIsNotNone(other)
            rule_model.objects.filter(secured_service=element.service).delete()

            def assert_flags(secured, spatial):
                for path, params in (
                        (f'/api/registry/{endpoint}/{element.pk}', {}),
                        (f'/api/registry/{endpoint}', {'filter[id]': str(element.pk)}),
                        (f'/api/registry/{service_endpoint}/{element.service_id}/{endpoint}',
                         {'filter[id]': str(element.pk)}),
                        (f'/api/registry/{endpoint}/{element.pk}',
                         {f'fields[{model.__name__}]': 'isSecured,isSpatialSecured'})):
                    with self.subTest(model=model.__name__, path=path, params=params,
                                      secured=secured, spatial=spatial):
                        status, body, _ = self.request(path, **params)
                        self.assertEqual(status, 200)
                        data = body['data']
                        attributes = (data[0] if isinstance(data, list) else data)['attributes']
                        self.assertIs(attributes['isSecured'], secured)
                        self.assertIs(attributes['isSpatialSecured'], spatial)

            assert_flags(False, False)
            rule = rule_model.objects.create(secured_service=element.service)
            getattr(rule, relation).add(other)
            assert_flags(False, False)
            getattr(rule, relation).add(element)
            assert_flags(True, False)
            rule.allowed_area = MultiPolygon(Polygon.from_bbox((6, 49, 7, 50)), srid=4326)
            rule.save()
            assert_flags(True, True)
            rule.delete()
            assert_flags(False, False)

    def test_layer_details_answer_the_inspection_includes(self):
        layer = Layer.objects.filter(
            reference_systems__isnull=False).first()
        self.assertIsNotNone(layer)
        extent = TimeExtent.objects.create(
            begin=datetime(2020, 1, 1, tzinfo=timezone.utc),
            end=datetime(2020, 12, 31, tzinfo=timezone.utc))
        layer.time_extents.add(extent)
        status, body, _ = self.request(
            f"/api/registry/layers/{layer.pk}", user="user",
            include="styles,referenceSystems,timeExtents")
        self.assertEqual(status, 200)
        types = {item["type"] for item in body.get("included", [])}
        self.assertIn("ReferenceSystem", types)
        self.assertIn("TimeExtent", types)

    def test_featuretype_details_answer_the_inspection_includes(self):
        feature_type = FeatureType.objects.filter(
            default_reference_system__isnull=False).first()
        self.assertIsNotNone(feature_type)
        status, body, _ = self.request(
            f"/api/registry/featuretypes/{feature_type.pk}", user="user",
            include="referenceSystems,outputFormats,defaultReferenceSystem")
        self.assertEqual(status, 200)
        types = {item["type"] for item in body.get("included", [])}
        self.assertIn("ReferenceSystem", types)


class ElementInspectionMetadataRelationTests(QueryMeasurementMixin, TestCase):
    """The metadata section of the inspection reads the records which a
    MetadataRelation already links, for a feature type like for a layer; the
    flag it answers with tells an empty result from the uncollected state of
    a registration which predates the collection of feature type references
    (#1262)."""

    fixtures = SERVICES + ["test_csw.json", "test_datasetmetadata.json"]

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.feature_type = FeatureType.objects.order_by("pk").first()
        cls.record = DatasetMetadataRecord.objects.first()

    def link_record(self):
        return MetadataRelation.objects.create(
            dataset_metadata=self.record,
            feature_type=self.feature_type,
            origin=MetadataOriginEnum.CAPABILITIES.value)

    def test_featuretype_relationship_lists_the_linked_record_without_include(self):
        self.link_record()
        status, body, _ = self.request(
            f"/api/registry/featuretypes/{self.feature_type.pk}", user="user")
        self.assertEqual(status, 200, body)
        relation = body["data"]["relationships"]["datasetMetadata"]["data"]
        self.assertEqual(
            [row["id"] for row in relation], [str(self.record.pk)])

    def test_featuretype_include_serializes_the_linked_record(self):
        self.link_record()
        status, body, _ = self.request(
            f"/api/registry/featuretypes/{self.feature_type.pk}", user="user",
            include="datasetMetadata")
        self.assertEqual(status, 200, body)
        types = {item["type"] for item in body.get("included", [])}
        self.assertIn("DatasetMetadataRecord", types)
        record = next(row for row in body["included"]
                      if row["type"] == "DatasetMetadataRecord")
        self.assertEqual(record["id"], str(self.record.pk))
        # the record travels through the same permission evaluation as the
        # record endpoints: without any object grant of its own it is not
        # editable by the requesting user
        self.assertFalse(record["attributes"]["canEdit"])

    def test_featuretype_metadata_relation_list_resolves(self):
        self.link_record()
        status, body, _ = self.request(
            f"/api/registry/featuretypes/{self.feature_type.pk}/dataset-metadata",
            user="user")
        self.assertEqual(status, 200, body)
        self.assertEqual(
            [row["id"] for row in body["data"]], [str(self.record.pk)])

    def test_metadata_relation_list_shares_the_record_endpoints_permission_answer(self):
        # the nested list is served by the same viewset which serves the
        # records standalone, so an anonymous request is answered the way the
        # record detail is - the relation adds no permission of its own
        self.link_record()
        detail_status, _, _ = self.request(
            f"/api/registry/dataset-metadata/{self.record.pk}")
        nested_status, body, _ = self.request(
            f"/api/registry/featuretypes/{self.feature_type.pk}/dataset-metadata")
        self.assertEqual(nested_status, detail_status, body)
        if detail_status == 200:
            self.assertEqual(
                [row["id"] for row in body["data"]], [str(self.record.pk)])

    def test_featuretype_answers_uncollected_metadata_references(self):
        path = f"/api/registry/featuretypes/{self.feature_type.pk}"

        def answer():
            status, body, _ = self.request(path, user="user")
            self.assertEqual(status, 200, body)
            return body["data"]["attributes"]["metadataReferencesUncollected"]

        # references the capabilities advertise stand beside no record: that
        # is the state #1257 leaves a pre-fix registration in
        self.assertIs(answer(), False)
        FeatureTypeRemoteMetadata.objects.create(
            link="https://example.org/metadata/record.xml",
            describes=self.feature_type)
        self.assertIs(answer(), True)
        # one collected record tells the collection apart from "no metadata":
        # the flag answers false again
        self.link_record()
        self.assertIs(answer(), False)
