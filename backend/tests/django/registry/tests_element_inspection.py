from datetime import datetime, timezone

from django.test import TestCase
from registry.models.metadata import TimeExtent
from registry.models.service import FeatureType, Layer
from tests.django.registry.tests_query_performance import (SERVICES,
                                                           QueryMeasurementMixin)


class ElementInspectionIncludeTests(QueryMeasurementMixin, TestCase):
    """The read oriented inspector reads Layer and FeatureType details with the
    relationships it renders already included."""

    fixtures = SERVICES

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
