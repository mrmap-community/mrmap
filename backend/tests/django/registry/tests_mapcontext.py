from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone
from registry.models.mapcontext import MapContext, MapContextLayer, WMS_OFFERING_CODE
from registry.models.metadata import Style
from registry.models.service import Layer
from registry.views_ows.mapcontext import OwsContextView


class OwsContextExportTests(TestCase):
    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_mapcontext.json']

    def export(self):
        response = self.client.get('/mrmap-proxy/ows/1')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_metadata_and_hierarchy(self):
        document = self.export()
        self.assertEqual(document['id'], 'http://testserver/mrmap-proxy/ows/1')
        self.assertEqual(document['properties']['lang'], 'en')
        self.assertEqual(document['properties']['subtitle'], 'MapContext1')
        user = get_user_model().objects.get(username='mrmap')
        self.assertEqual(document['properties']['authors'][0]['name'], user.get_full_name() or user.get_username())
        self.assertTrue(document['properties']['updated'])
        self.assertNotIn('language', document['properties'])
        self.assertEqual([feature['properties']['folder'] for feature in document['features']],
                         ['/0', '/0/0', '/0/0/0', '/0/0/1', '/0/1'])
        for feature in document['features']:
            self.assertTrue(feature['id'].startswith('http://testserver/'))
            self.assertTrue(feature['properties']['updated'])
            self.assertIsNone(feature['geometry'])
            self.assertNotIn('offerings', feature)
        layer = MapContextLayer.objects.get(pk=3)
        self.assertEqual(layer.folder_name, '/1/2/3')

    def test_style_scales_and_independent_operation_activation(self):
        layer = MapContextLayer.objects.get(pk=1)
        style = Style.objects.create(layer=layer.rendering_layer, name='configured', title='Configured style')
        selection_layer = Layer.objects.filter(is_queryable=True).exclude(pk=layer.rendering_layer_id).first()
        self.assertIsNotNone(selection_layer)
        # QuerySet update deliberately bypasses unrelated model scale validation.
        MapContextLayer.objects.filter(pk=1).update(
            layer_style=style, layer_scale_min=0, layer_scale_max=50000,
            selection_layer=selection_layer, rendering_active=False,
            selection_active=True)
        resource = self.export()['features'][0]
        properties = resource['properties']
        self.assertEqual(properties['minscaledenominator'], 0)
        self.assertEqual(properties['maxscaledenominator'], 50000)
        self.assertEqual(len(properties['offerings']), 1)
        offering = properties['offerings'][0]
        self.assertEqual(offering['code'], WMS_OFFERING_CODE)
        self.assertEqual(offering['styles'], [{'name': style.name, 'title': style.title, 'default': True}])
        rendering, selection = offering['operations']
        self.assertEqual(rendering['code'], 'GetMap')
        self.assertFalse(rendering['active'])
        self.assertEqual(parse_qs(urlparse(rendering['href']).query)['STYLES'], [style.name])
        self.assertEqual(selection['code'], 'GetFeatureInfo')
        self.assertTrue(selection['active'])
        self.assertEqual(parse_qs(urlparse(selection['href']).query)['QUERY_LAYERS'], [selection_layer.identifier])
        self.assertEqual(parse_qs(urlparse(selection['href']).query)['INFO_FORMAT'], [selection['type']])

    def test_latest_history_is_per_object_with_and_without_prefetch(self):
        context = MapContext.objects.get(pk=1)
        context.title = 'changed context'
        context._history_user = get_user_model().objects.get(username='mrmap')
        context.save()
        latest = context.change_log.first().history_date
        self.assertEqual(context.updated, latest)
        self.assertEqual(self.export()['properties']['updated'], latest.isoformat())
        layer = MapContextLayer.objects.get(pk=2)
        layer.title = 'changed child'
        layer.save()
        latest_layer = layer.change_log.first().history_date
        self.assertEqual(layer.updated, latest_layer)
        document = self.export()
        self.assertEqual(document['features'][1]['properties']['updated'], latest_layer.isoformat())
        self.assertTrue(document['features'][0]['properties']['updated'].startswith('2022-'))

    def test_missing_history_uses_export_time_without_inventing_author(self):
        MapContext.change_log.filter(id=1).delete()
        now = timezone.now()
        with patch('registry.models.mapcontext.timezone.now', return_value=now):
            properties = self.export()['properties']
        self.assertEqual(properties['updated'], now.isoformat())
        self.assertNotIn('authors', properties)

    def test_model_export_without_request_uses_absolute_urns(self):
        document = MapContext.objects.get(pk=1).as_ows_context()
        self.assertEqual(document['id'], 'urn:mrmap:mapcontext:1')
        self.assertEqual(document['features'][0]['id'], 'urn:mrmap:mapcontextlayer:1')

    def test_prefetched_export_does_not_query_ancestors_at_any_depth(self):
        parent = MapContextLayer.objects.get(pk=3)
        for depth in range(6):
            child = MapContextLayer(map_context_id=1, title=f'deep group {depth}')
            child.insert_at(parent)
            parent = child
        context = OwsContextView().get_queryset().get(pk=1)
        # Exporting the prefetched flat tree needs no recursive ancestor queries,
        # including groups beyond the endpoint's former four-level preload.
        with patch.object(MapContextLayer, 'rendering_offering', return_value=None), \
                patch.object(MapContextLayer, 'selection_offering', return_value=None):
            with self.assertNumQueries(0):
                document = context.as_ows_context(request=RequestFactory().get('/'))
        deepest = next(feature for feature in document['features'] if feature['properties']['title'] == 'deep group 5')
        self.assertEqual(deepest['properties']['folder'], '/0/0/0' + '/0' * 6)
