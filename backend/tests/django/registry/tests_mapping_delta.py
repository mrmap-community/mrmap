from django.test import SimpleTestCase
from registry.models import Layer, LayerMapping
from registry.serializers.update import (
    LayerMappingSerializer, WebMapServiceUpdateJobSerializer,
)
from rest_framework_json_api.utils import get_included_resources


class LayerMappingDeltaTest(SimpleTestCase):
    def delta(self, old, new):
        mapping = LayerMapping(old_layer=old, new_layer=new)
        serializer = LayerMappingSerializer()
        return serializer.fields["delta"].to_representation(mapping)

    def test_changed_fields_have_old_and_new_values(self):
        self.assertEqual(
            self.delta(
                Layer(title="Old title", abstract="Old abstract"),
                Layer(title="New title", abstract="New abstract"),
            ),
            [
                {"field": "title", "old": "Old title", "new": "New title"},
                {"field": "abstract", "old": "Old abstract", "new": "New abstract"},
            ],
        )

    def test_equal_values_including_null_have_empty_delta(self):
        self.assertEqual(self.delta(Layer(), Layer()), [])

    def test_null_transitions_and_false_values(self):
        self.assertEqual(
            self.delta(
                Layer(is_queryable=True, scale_min=None, scale_max=0),
                Layer(is_queryable=False, scale_min=0, scale_max=None),
            ),
            [
                {"field": "is_queryable", "old": True, "new": False},
                {"field": "scale_min", "old": None, "new": 0},
                {"field": "scale_max", "old": 0, "new": None},
            ],
        )

    def test_unmatched_layer_has_no_comparison(self):
        self.assertIsNone(self.delta(None, Layer()))

    def test_jobs_include_mappings_by_default(self):
        self.assertIn(
            "mappings",
            get_included_resources(None, WebMapServiceUpdateJobSerializer),
        )
