from datetime import datetime, timezone

from django.test import TestCase
from django.contrib.gis.geos import MultiPolygon, Polygon
from registry.models.metadata import TimeExtent
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
