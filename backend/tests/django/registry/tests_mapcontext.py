import json
import threading
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction
from django.db.utils import OperationalError
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.utils import timezone
from registry.models.mapcontext import MapContext, MapContextLayer, WMS_OFFERING_CODE
from registry.models.metadata import Style
from registry.models.service import Layer
from registry.views_ows.mapcontext import OwsContextView
from rest_framework.test import APIClient

JSONAPI = 'application/vnd.api+json'

# a test thread which does not finish within this many seconds is a broken test
# and not a lock which is still held (the neighbour's rule)
TIMEOUT = 15

# the SQLSTATE of ``lock_not_available``: what a read asked for a row another
# transaction is still holding is refused with, once ``lock_timeout`` is over
LOCK_NOT_AVAILABLE = '55P03'


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


class MapContextLayerApiMixin:
    """An authorised API client and the payloads of the position endpoints.

    The fixtures put map context 2 and its layers 6 to 11 in tree 2. Layer 8,
    which the payloads below insert into, has the two children 9 and 10.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_mapcontext.json']

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='mapcontext-position', password='test')
        get_user_model().objects.get_or_create(username='AnonymousUser')
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        # without an explicit accept the browsable api renderer is used
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def add_layer(self, title, parent=8, position=None):
        """POST a new layer of map context 2 below the given parent."""
        attributes = {'title': title}
        if position is not None:
            attributes['position'] = position
        return self.client.post(
            '/api/registry/mapcontextlayers',
            {'data': {
                'type': 'MapContextLayer',
                'attributes': attributes,
                'relationships': {
                    'mptt_parent': {
                        'data': {'type': 'MapContextLayer', 'id': str(parent)}},
                    'mapContext': {
                        'data': {'type': 'MapContext', 'id': '2'}}}}},
            format='vnd.api+json')

    def move_layer(self, pk, parent, position, title=None):
        """PATCH an existing layer to a position below the given parent."""
        attributes = {'position': position}
        if title is not None:
            attributes['title'] = title
        return self.client.patch(
            f'/api/registry/mapcontextlayers/{pk}',
            {'data': {
                'type': 'MapContextLayer',
                'id': str(pk),
                'attributes': attributes,
                'relationships': {
                    'mptt_parent': {
                        'data': {'type': 'MapContextLayer', 'id': str(parent)}}}}},
            format='vnd.api+json')

    @staticmethod
    def children(parent):
        """the pks of the direct children of a layer, in tree order"""
        return list(MapContextLayer.objects.filter(mptt_parent_id=parent)
                    .order_by('mptt_lft').values_list('pk', flat=True))


class MapContextLayerPositionTests(MapContextLayerApiMixin, TestCase):
    """The ``position`` attribute of the map context layer endpoints (#1476).

    A POST which carried a position inserted the node and then answered nothing,
    because the position branch of ``MapContextLayerSerializer.create()`` had no
    return: ``serializer.instance`` stayed None and the request ended in a 500.
    The acceptance scenario of the same name covers the endpoint; what is
    measured here is the row the node ended up in, for every branch of the
    position the serializer distinguishes.
    """

    def test_create_at_the_first_position_prepends_the_new_layer(self):
        response = self.add_layer('mc2_position_first', position=0)

        self.assertEqual(response.status_code, 201)
        created = MapContextLayer.objects.get(title='mc2_position_first')
        self.assertEqual(self.children(8), [created.pk, 9, 10])

    def test_create_at_a_position_inserts_the_node_between_the_children(self):
        response = self.add_layer('mc2_position_middle', position=1)

        self.assertEqual(response.status_code, 201)
        created = MapContextLayer.objects.get(title='mc2_position_middle')
        self.assertEqual(self.children(8), [9, created.pk, 10])

        # the answer names the inserted node, which is exactly what the missing
        # return of the position branch took away
        body = json.loads(response.content)
        self.assertEqual(body['data']['id'], str(created.pk))
        self.assertEqual(body['data']['attributes']['mpttLft'], created.mptt_lft)
        self.assertEqual(body['data']['attributes']['mpttTreeId'], 2)

    def test_create_at_the_child_count_appends_the_new_layer(self):
        response = self.add_layer('mc2_position_last', position=2)

        self.assertEqual(response.status_code, 201)
        created = MapContextLayer.objects.get(title='mc2_position_last')
        self.assertEqual(self.children(8), [9, 10, created.pk])

    def test_create_without_position_appends_the_new_layer(self):
        response = self.add_layer('mc2_without_position')

        self.assertEqual(response.status_code, 201)
        created = MapContextLayer.objects.get(title='mc2_without_position')
        self.assertEqual(self.children(8), [9, 10, created.pk])


class MapContextLayerReorderTests(MapContextLayerApiMixin, TransactionTestCase):
    """A reorder of the map context layer tree is one unit of work (#1476).

    mptt2 commits its own tree update the moment ``insert_at``/``move_to``
    return, so the siblings the serializer counted for a position belonged to a
    transaction which was already over: a parallel reorder which counted them in
    that window claimed an index the first one had not committed yet, and a save
    refused after the tree update left the node moved while its attributes stayed
    unchanged. Both are answered by wrapping the reorder in a transaction.

    A reorder is only observable with real commits, hence a TransactionTestCase.
    """

    def claim_children(self, parent):
        """Read the children of a layer the way a reorder does: under a lock.

        Answers ``'blocked'`` instead of the pks when a running reorder still
        holds the rows. The lock timeout keeps this read from waiting forever,
        and only the 55P03 lock-not-available refusal counts: any other
        OperationalError is raised, so the test cannot mistake a broken read for
        a held lock.
        """
        try:
            with transaction.atomic():
                connection.cursor().execute("SET LOCAL lock_timeout = '200 ms'")
                return list(MapContextLayer.objects.select_for_update()
                            .filter(mptt_parent_id=parent)
                            .order_by('mptt_lft')
                            .values_list('pk', flat=True))
        except OperationalError as error:
            if getattr(error.__cause__, 'sqlstate', None) != LOCK_NOT_AVAILABLE:
                raise
            return 'blocked'

    def test_a_move_holds_its_rows_until_the_reorder_is_over(self):
        """A second reorder may not read the siblings a running one counted.

        The read of the parallel reorder is asked from inside the running one,
        right after mptt2 shifted the rows: while that reorder is still saving
        the rest of its PATCH, its rows must stay locked.
        """
        seen = []
        original_move_to = MapContextLayer.move_to

        def probe_from_another_session():
            try:
                seen.append(self.claim_children(1))
            finally:
                connections.close_all()

        def move_and_probe(instance, *args, **kwargs):
            moved = original_move_to(instance, *args, **kwargs)
            reader = threading.Thread(target=probe_from_another_session, daemon=True)
            reader.start()
            reader.join(TIMEOUT)
            return moved

        with patch.object(MapContextLayer, 'move_to', move_and_probe):
            response = self.move_layer(2, parent=1, position=2)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            seen, ['blocked'],
            'a parallel reorder could read and lock the tree of the reorder '
            'which was still saving its patch')

        # the very same read once the reorder is over does get the rows, so what
        # is asserted above is the window and not a permanently blocked reader
        self.assertEqual(self.claim_children(1), [5, 2])

    def test_a_refused_save_after_the_move_leaves_the_tree_untouched(self):
        """A PATCH whose own save is refused may not leave the node moved.

        A title longer than the model allows is refused by the model itself,
        which checks it in ``save()`` - after the tree update of the same
        request. Without the transaction of the reorder the node stayed in its
        new place while its attributes were never written.
        """
        self.assertEqual(self.children(1), [2, 5])

        with self.assertRaises(ValidationError):
            self.move_layer(2, parent=1, position=2, title='x' * 1001)

        self.assertEqual(self.children(1), [2, 5],
                         'the refused reorder left the node in the tree')
        layer = MapContextLayer.objects.get(pk=2)
        self.assertEqual(layer.mptt_lft, 2)
        self.assertEqual(layer.mptt_parent_id, 1)
