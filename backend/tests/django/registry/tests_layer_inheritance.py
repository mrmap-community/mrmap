"""The effective values of the inherited attributes of a layer (#1315).

The layers of a WMS are answered with the *effective* value of every attribute
which the OGC specifications inherit from a parent layer: ``is_queryable``,
``is_cascaded``, ``is_opaque``, ``scale_min``, ``scale_max``,
``bbox_lat_lon``, the aggregated ``reference_systems``, ``time_extents`` and
``styles`` and the security information of the layer. All of them are answered
by the three common table expressions of
:meth:`registry.querys.service.LayerQuerySet.with_inherited_attributes_cte`.

Those CTEs used to answer one row for **every layer of the registry** and were
joined to a request which shows the layers of one service: the layers tab of a
service with 4 layers materialised 265,653 layers with six correlated ancestor
probes each and threw all but four of them away on the join again - 48.5 s of
the 49.3 s of that request on an idle database (#1315). They are now computed
for the layers the queryset selects, while the ancestry itself is still looked
up in every layer, so no layer can answer another value than before.

The tests keep the two properties apart which the AC of #1315 name:

* the *values* - the scoped CTEs answer exactly what the unscoped shape
  answered, for trees with depth, branches, parents without an own value and
  overrides, for two trees of one service, for the layers of another service
  and for a deep hierarchy. The unscoped shape is still reachable
  (``Layer.objects.with_inherited_attributes_cte()`` without a filter) and is
  the oracle of the comparison.
* the *shape* - the work of one request may not grow with the layers the
  deployment holds besides the service it answers. Seconds belong to the
  hardware, the read shape and the number of statements do not, so those are
  what CI guards; the measured numbers of the reported scale are the opt-in
  benchmark at the end of this module.
"""
import math
import os
import re
from datetime import timedelta
from statistics import median
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.gis.geos import MultiPolygon, Polygon
from django.db import connections
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import now
from mptt2.models import Tree
from rest_framework.test import APIClient

from registry.enums.service import HttpMethodEnum, OGCOperationEnum
from registry.filters.service import LayerFilterSet
from registry.models.metadata import (MimeType, ReferenceSystem, Style,
                                      TimeExtent)
from registry.models.security import AllowedWebMapServiceOperation
from registry.models.service import (Layer, WebMapService,
                                     WebMapServiceOperationUrl)
from tests.django.registry.tests_query_performance import QueryMeasurementMixin

JSONAPI = 'application/vnd.api+json'

WORLD = Polygon(((1, 1), (1, 2), (2, 2), (2, 1), (1, 1)), srid=4326)
SMALL = Polygon(((3, 3), (3, 4), (4, 4), (4, 3), (3, 3)), srid=4326)
OTHER = Polygon(((5, 5), (5, 6), (6, 6), (6, 5), (5, 5)), srid=4326)
DEEP = Polygon(((7, 7), (7, 8), (8, 8), (8, 7), (7, 7)), srid=4326)

#: the attributes of the answer which the three CTEs of the layer queryset
#: compute, in contrast to the columns a layer row carries itself
CTE_ATTRIBUTES = [
    'is_queryable_inherited', 'is_cascaded_inherited', 'is_opaque_inherited',
    'scale_min_inherited', 'scale_max_inherited', 'bbox_lat_lon_inherited',
    'reference_systems_inherited', 'time_extents_inherited',
    'styles_inherited', 'is_secured', 'is_spatial_secured',
]

LAYER_FIELDS = {field.name for field in Layer._meta.get_fields()
                if field.concrete}


def build_tree(service, spec):
    """Stores the layer tree ``spec`` for ``service`` and returns its layers.

    A spec names the own values of a layer and its children below ``children``::

        {'identifier': 'root', 'bbox_lat_lon': WORLD,
         'children': [{'identifier': 'root.a', 'scale_min': 10}]}

    The MPTT columns are numbered in preorder - left boundary on entering a
    node, right boundary on leaving it - which is how the tree of a harvested
    capabilities document is stored. Every call gets a tree of its own, because
    a tree is the namespace an ancestry is looked up in.
    """

    def size(node):
        return 1 + sum(size(child) for child in node.get('children', ()))

    tree = Tree.objects.create()
    layers = []

    def walk(node, parent, depth, left):
        right = left + 2 * size(node) - 1
        attributes = {key: value for key, value in node.items()
                      if key in LAYER_FIELDS
                      and key not in ('identifier', 'title')}
        row = Layer(
            service=service,
            identifier=node['identifier'],
            title=node['identifier'],
            mptt_tree=tree,
            mptt_parent=parent,
            mptt_depth=depth,
            mptt_lft=left,
            mptt_rgt=right,
            **attributes)
        row.save()
        layers.append(row)
        next_left = left + 1
        for child in node.get('children', ()):
            next_left = walk(child, row, depth + 1, next_left)
        # the next free number behind this subtree, which is what the sibling
        # of the node continues with
        return right + 1

    walk(spec, None, 0, 1)
    return layers


class LayerTreeMixin:
    """The trees the AC of #1315 name: depth, branches, an override in the
    middle of a branch, a parent without an own value, two trees of one
    service, a second service whose tree is numbered exactly like the measured
    one and a deep hierarchy."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json']

    # the layers of another service, to ask whether a request grows with the
    # size of the deployment
    FILLER_LAYERS = 2000
    DEPTH = 40

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.seed()

    @classmethod
    def seed(cls):
        """Stores the trees and rules of this fixture.

        A ``TestCase`` gets this through ``setUpTestData``; the opt-in
        benchmark at the end is a ``TransactionTestCase`` which truncates the
        tables and calls it from ``setUp``.
        """
        template = WebMapService.objects.order_by('pk').first()
        cls.measured = cls.service(template, 'measured')
        cls.other = cls.service(template, 'other')
        cls.multi = cls.service(template, 'multi')
        WebMapServiceOperationUrl.objects.create(
            service=cls.measured, operation=OGCOperationEnum.GET_MAP.value,
            method=HttpMethodEnum.GET.value,
            url='https://www.example.de/wms/measured?') .mime_types.add(
            MimeType.objects.get(mime_type='image/png'))

        # the measured tree: overrides in a branch and layers which state
        # nothing of their own
        build_tree(cls.measured, {
            'identifier': 'root', 'bbox_lat_lon': WORLD,
            'children': [
                {'identifier': 'a', 'scale_min': 10, 'is_queryable': True,
                 'is_opaque': True, 'children': [
                     {'identifier': 'a1'},
                     {'identifier': 'a2', 'scale_min': 20,
                      'is_cascaded': True,
                      'children': [{'identifier': 'a21'}]}]},
                {'identifier': 'b', 'is_queryable': True, 'children': [
                    {'identifier': 'b1', 'scale_max': 500000,
                     'bbox_lat_lon': SMALL}]}]})

        # the very same shape for the other service, with values which any
        # ancestry that is not restricted to its own tree would answer: both
        # trees number their layers from 1, like every MPTT tree does
        build_tree(cls.other, {
            'identifier': 'other-root', 'scale_min': 999999,
            'scale_max': 999998, 'bbox_lat_lon': OTHER,
            'is_queryable': True, 'is_cascaded': True, 'is_opaque': True,
            'children': [{'identifier': 'other-a'}]})

        # two trees within one service: the ancestry of a layer ends at the
        # root of its own tree, not at the service
        build_tree(cls.multi, {
            'identifier': 'multi-tree-1', 'scale_min': 1,
            'children': [{'identifier': 'multi-1-a'}]})
        build_tree(cls.multi, {
            'identifier': 'multi-tree-2', 'scale_min': 777,
            'children': [{'identifier': 'multi-2-a'}]})

        # a deep chain: every level is the only child of the level before it;
        # the root is numbered like the persistence of a capabilities document
        # numbers it (registry/mappers/extensions.py)
        parent = Layer.objects.create(
            service=cls.measured, identifier='deep-root', title='deep-root',
            bbox_lat_lon=DEEP, mptt_tree=Tree.objects.create(),
            mptt_lft=1, mptt_rgt=2, mptt_depth=0)
        cls.deep_layers = [parent]
        for level in range(1, cls.DEPTH + 1):
            child = Layer(
                service=cls.measured, identifier=f'deep-{level}',
                title=f'deep-{level}',
                scale_min=level if level == 3 else None)
            child.insert_at(parent)
            cls.deep_layers.append(child)
            parent = child

        # the aggregated attributes and the security of single layers
        leaf = Layer.objects.get(identifier='a1')
        cls.reference_system = ReferenceSystem.objects.first()
        leaf.reference_systems.add(cls.reference_system)
        cls.time_extent = TimeExtent.objects.create(
            begin=now(), end=now(), resolution=timedelta(0))
        leaf.time_extents.add(cls.time_extent)
        cls.style = Style.objects.create(layer=leaf, name='style',
                                         title='Style')
        spatial = AllowedWebMapServiceOperation.objects.create(
            secured_service=cls.measured,
            description='measured spatial rule',
            allowed_area=MultiPolygon(Polygon(
                ((0, 0), (0, 1), (1, 1), (1, 0), (0, 0)), srid=4326)))
        spatial.secured_layers.add(Layer.objects.get(identifier='b'))
        plain = AllowedWebMapServiceOperation.objects.create(
            secured_service=cls.other, description='rule of another service')
        plain.secured_layers.add(Layer.objects.get(identifier='other-a'))

    @classmethod
    def service(cls, template, name):
        return WebMapService.objects.create(
            title=f'WMS {name}',
            service_url=f'https://www.example.de/wms/{name}',
            version=template.version, origin=template.origin,
            metadata_contact=template.metadata_contact,
            service_contact=template.service_contact)

    @classmethod
    def grow(cls, service, count):
        """Adds ``count`` leaf layers below the first root of ``service``.

        The layers of a big deployment are not saved one by one: what is
        measured is the read of a request, not the write of a harvest, and the
        numbering of a flat row of leaves under a root is trivial.
        """
        root = service.layers.order_by('mptt_tree', 'mptt_lft').first()
        Layer.objects.filter(pk=root.pk).update(mptt_rgt=2 + 2 * count)
        Layer.objects.bulk_create([
            Layer(service=service, identifier=f'filler-{service.pk}-{number}',
                  title=f'filler-{service.pk}-{number}',
                  mptt_tree=root.mptt_tree, mptt_parent=root, mptt_depth=1,
                  mptt_lft=2 + 2 * number, mptt_rgt=3 + 2 * number)
            for number in range(count)])

    @classmethod
    def grow_with_sql(cls, service, count):
        """Adds ``count`` leaf layers of ``service`` with one set-based insert.

        The seeder of the benchmark: hundreds of thousands of rows cannot be
        saved one by one, so the row shape of one existing leaf is copied by
        the database itself, like ``tests_service_alerts`` seeds its services.
        History and triggers of the ORM path are no part of a seed.
        """
        root = service.layers.order_by('mptt_tree', 'mptt_lft').first()
        Layer.objects.filter(pk=root.pk).update(mptt_rgt=2 + 2 * count)
        with connections['default'].cursor() as cursor:
            cursor.execute("""
                INSERT INTO registry_layer
                SELECT (sub.rec).*
                FROM (SELECT
                          jsonb_populate_record(
                              NULL::registry_layer,
                              (to_jsonb(l) - 'id' - 'identifier' - 'title'
                               - 'file_identifier'
                               - 'service_id' - 'mptt_tree_id'
                               - 'mptt_parent_id' - 'mptt_depth'
                               - 'mptt_lft' - 'mptt_rgt'
                               || jsonb_build_object(
                                      'id', gen_random_uuid(),
                                      'file_identifier', gen_random_uuid(),
                                      'identifier', 'bench-' || g,
                                      'title', 'bench-' || g,
                                      'service_id', %s,
                                      'mptt_tree_id', %s,
                                      'mptt_parent_id', %s,
                                      'mptt_depth', 1,
                                      'mptt_lft', 2 + 2 * g,
                                      'mptt_rgt', 3 + 2 * g)
                          )) AS rec
                      FROM registry_layer l, generate_series(1, %s) g
                      WHERE l.id = %s) sub
            """, [service.pk, root.mptt_tree_id, root.pk, count, root.pk])

    def effective_values(self, queryset):
        """The answers of the CTEs of a queryset, per layer identifier."""
        return {
            layer.identifier: {
                attribute: getattr(layer, attribute)
                for attribute in CTE_ATTRIBUTES}
            for layer in queryset}


class InheritedLayerValuesTest(LayerTreeMixin, TestCase):
    """The values the CTEs answer, with the scoping of #1315 and without it."""

    def measured_values(self):
        return self.effective_values(
            Layer.objects.filter(service=self.measured)
            .with_inherited_attributes_cte())

    def test_scoping_the_ctes_answers_the_same_values(self):
        """The old and the new shape answer the same value for every layer.

        ``Layer.objects.with_inherited_attributes_cte()`` without a filter is
        the shape before #1315: it computes the effective values of every layer
        of the registry. The scoped shape is the queryset of the layers
        endpoint, narrowed to one service - which holds the trees of this
        fixture, including the two trees of one service and the deep chain.
        """
        before = self.effective_values(Layer.objects
                                       .with_inherited_attributes_cte())
        for service in (self.measured, self.other, self.multi):
            with self.subTest(service=service.title):
                after = self.effective_values(
                    Layer.objects.filter(service=service)
                    .with_inherited_attributes_cte())
                self.assertTrue(after)
                self.assertEqual(
                    after, {key: before[key] for key in after},
                    'a layer answers another effective value as soon as the '
                    'CTEs are computed for fewer layers than the registry')

    def test_the_layers_of_a_service_answer_their_own_values(self):
        """The effective values of the measured tree, layer by layer.

        The rule the annotations follow is the rule of their SQL: an attribute
        which the layer states itself is answered by the layer, and an attribute
        it does not state is answered by the first layer of its path - ordered
        by the MPTT left boundary, which is the root of the tree - whether that
        one states the value or not. A boolean is answered by the layer alone,
        because its column is never null and the coalesce of the annotation
        therefore never asks the ancestry. #1315 narrows *how many* layers are
        computed and keeps this rule; another reading of the inheritance is not
        part of it and would be an own change with own acceptance criteria.
        """
        expected = {
            'root': {'bbox_lat_lon_inherited': WORLD,
                     'scale_min_inherited': None},
            'a': {'scale_min_inherited': 10, 'is_queryable_inherited': True,
                  'is_opaque_inherited': True, 'is_cascaded_inherited': False,
                  'bbox_lat_lon_inherited': WORLD},
            # the value which the parent of a1 states is not answered for a1,
            # because the path is probed from the root of the tree
            'a1': {'scale_min_inherited': None,
                   'is_queryable_inherited': False,
                   'bbox_lat_lon_inherited': WORLD},
            'a2': {'scale_min_inherited': 20, 'is_cascaded_inherited': True,
                   'bbox_lat_lon_inherited': WORLD},
            'a21': {'scale_min_inherited': None,
                    'is_cascaded_inherited': False,
                    'bbox_lat_lon_inherited': WORLD},
            'b': {'is_queryable_inherited': True,
                  'bbox_lat_lon_inherited': WORLD},
            # an own value wins, the missing ones come from the path
            'b1': {'scale_max_inherited': 500000,
                   'scale_min_inherited': None,
                   'bbox_lat_lon_inherited': SMALL},
        }
        values = self.measured_values()
        for identifier, attributes in expected.items():
            for attribute, value in attributes.items():
                with self.subTest(layer=identifier, attribute=attribute):
                    self.assertEqual(values[identifier][attribute], value)

    def test_a_deep_tree_answers_the_values_of_its_path(self):
        """A hierarchy of ``DEPTH`` levels is answered like a shallow one."""
        values = self.effective_values(
            Layer.objects.filter(service=self.measured)
            .with_inherited_attributes_cte())
        self.assertEqual(len(values), 7 + self.DEPTH + 1)
        for level in range(0, self.DEPTH + 1):
            identifier = 'deep-root' if level == 0 else f'deep-{level}'
            with self.subTest(level=level):
                # the bbox of the root of the chain, the scale of the level
                # which states it, and nothing else
                self.assertEqual(
                    values[identifier]['bbox_lat_lon_inherited'], DEEP)
                self.assertEqual(
                    values[identifier]['scale_min_inherited'],
                    3 if level == 3 else None)

    def test_layers_of_another_service_are_never_part_of_the_answer(self):
        """Two trees number their layers the same, so the service separates them.

        The root of the other service has the same left boundary as the root of
        the measured one, like every MPTT tree starts at 1: a read which
        answered an ancestry without its tree would mix them, and the values of
        the fixture are chosen so that any mix shows up.
        """
        values = self.measured_values()
        for identifier, answered in values.items():
            with self.subTest(layer=identifier):
                self.assertNotEqual(
                    answered['scale_min_inherited'], 999999,
                    "the scale of the other service's root was inherited")
                self.assertNotEqual(
                    answered['bbox_lat_lon_inherited'], OTHER,
                    "the bbox of the other service's root was inherited")
        self.assertEqual(
            sorted(identifier for identifier, answered in values.items()
                   if answered['is_queryable_inherited']),
            ['a', 'b'], 'the queryable flags of another service leaked')
        self.assertEqual(
            sorted(identifier for identifier, answered in values.items()
                   if answered['is_secured']), ['b'],
            'the spatial rule of the measured service answers its own layer '
            'while a rule of another service reached the answer')
        # the rule of the other service is answered for its own layer only:
        # secured by its rule, not spatially secured by the rule of this one
        other_values = self.effective_values(
            Layer.objects.filter(service=self.other)
            .with_inherited_attributes_cte())
        self.assertTrue(other_values['other-a']['is_secured'])
        self.assertFalse(other_values['other-a']['is_spatial_secured'])

    def test_two_trees_of_one_service_keep_their_own_ancestry(self):
        """A service may hold more than one tree; a path ends at its own root."""
        values = self.effective_values(
            Layer.objects.filter(service=self.multi)
            .with_inherited_attributes_cte())
        self.assertEqual(len(set(Layer.objects.filter(service=self.multi)
                                 .values_list('mptt_tree_id', flat=True))), 2,
                         'the fixture holds two trees for one service')
        # the first row of every path is the root of its own tree - which is
        # where a value the layer does not state itself is looked up, and the
        # roots state different values so a mix of the trees cannot pass
        self.assertEqual(values['multi-tree-1']['scale_min_inherited'], 1)
        self.assertEqual(values['multi-1-a']['scale_min_inherited'], 1)
        self.assertEqual(values['multi-tree-2']['scale_min_inherited'], 777)
        self.assertEqual(values['multi-2-a']['scale_min_inherited'], 777)

    def test_aggregated_attributes_and_security_are_answered_per_layer(self):
        """The two other CTEs answer the layer they include and no other."""
        values = self.measured_values()
        self.assertEqual(
            [system['code'] for system
             in values['a1']['reference_systems_inherited']],
            [self.reference_system.code])
        self.assertEqual(
            [extent['pk'] for extent in values['a1']['time_extents_inherited']],
            [self.time_extent.pk])
        self.assertEqual(
            [style['name'] for style in values['a1']['styles_inherited']],
            [self.style.name])
        # a layer without rows of its own answers the aggregation of nothing
        self.assertEqual(values['root']['styles_inherited'], [])
        self.assertEqual(values['root']['reference_systems_inherited'], [])
        self.assertFalse(values['root']['is_secured'])
        self.assertFalse(values['a1']['is_secured'])
        # the one rule of the service is answered for its own layer only
        self.assertTrue(values['b']['is_secured'])
        self.assertTrue(values['b']['is_spatial_secured'])

    def test_the_get_map_url_still_uses_the_inherited_bbox(self):
        """A consumer of an inherited value outside the API keeps its value.

        A layer without an own bbox builds its GetMap url out of the bbox of
        its ancestry - the read the monitoring and the viewer of a layer rely
        on. It asks the queryset of the whole registry and must keep working
        with a scoped as well as with an unscoped computation.
        """
        layer = Layer.objects.get(identifier='b')
        url = layer.get_map_url(format='image/png', width=100, height=100)
        self.assertIn('BBOX=' + '%2C'.join(map(str, WORLD.extent)), url)

    def test_the_layers_of_a_service_keep_their_mptt_order(self):
        """The order of the answer is the preorder of every tree of the service.

        The trees themselves are ordered by their id - a uuid, so which tree of
        a service answers first is none of the tests business; the preorder
        within a tree is.
        """
        ordered = list(
            Layer.objects.filter(service=self.measured)
            .with_inherited_attributes_cte()
            .order_by('mptt_tree', 'mptt_lft')
            .values_list('identifier', flat=True))
        self.assertEqual(
            [row for row in ordered if not row.startswith('deep')],
            ['root', 'a', 'a1', 'a2', 'a21', 'b', 'b1'])
        self.assertEqual(
            [row for row in ordered if row.startswith('deep')][:3],
            ['deep-root', 'deep-1', 'deep-2'])

    def test_the_bbox_filter_of_the_layer_filterset_uses_the_annotation(self):
        """``LayerFilterSet`` filters on ``bbox_lat_lon_inherited``.

        The inherited bbox must stay a part of the query: the filter of the API
        names the annotation of the CTE, so it answers the layers whose
        effective bbox covers the given geometry - which are the layers of the
        tree with the bbox of their root, not the layer with an own one.
        """
        bounds = Polygon(((1.2, 1.2), (1.2, 1.8), (1.8, 1.8), (1.8, 1.2),
                          (1.2, 1.2)), srid=4326)
        for service, expected in (
                (self.measured, {'root', 'a', 'a1', 'a2', 'a21', 'b'}),
                (self.other, set())):
            with self.subTest(service=service.title):
                queryset = Layer.objects.filter(service=service) \
                    .with_inherited_attributes_cte()
                filtered = LayerFilterSet(
                    {'bbox_lat_lon__covers': bounds.wkt},
                    queryset=queryset).qs
                self.assertEqual(
                    set(filtered.values_list('identifier', flat=True)),
                    expected)


class LayersEndpointTest(LayerTreeMixin, QueryMeasurementMixin, TestCase):
    """The layers endpoint of one service: the answer and the work it costs."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.path = f'/api/registry/wms/{cls.measured.pk}/layers'

    #: the semi-join with which each CTE of the layer queryset restricts itself
    #: to the layers the statement answers; the subselect's alias is chosen by
    #: the compiler and differs between a plain queryset and the statement of a
    #: request, so the pattern does not name it
    SCOPE_MARKER = re.compile(
        r'IN \(SELECT \w+\."id" AS "pk" FROM "registry_layer" \w+'
        r' WHERE \w+\."service_id"')

    def test_the_statement_computes_the_inheritance_for_its_own_layers(self):
        """The regression of #1315 is pinned as text: the CTEs are scoped.

        The number of statements of a request does not say *what* it computes
        for its rows - only the time says that, and the time belongs to the
        hardware. So the read shape is pinned directly: every base of the three
        recursive CTEs carries the restriction to the layers of the statement,
        and the statement of the endpoint request shows the same. The ancestry
        lookups inside the CTEs stay unrestricted on purpose - a parent is
        looked up in the whole registry, which is what makes the scoping
        value-safe (see the equivalence test) - so this marker is the property
        the 48.5 s of the issue were missing.
        """
        sql = str(Layer.objects.filter(service=self.measured)
                  .with_inherited_attributes_cte().query)
        for cte in ('"ancestors" AS (', '"aggregated_ancestors" AS (',
                    '"layer_security_information" AS ('):
            self.assertIn(cte, sql)
        self.assertEqual(
            len(self.SCOPE_MARKER.findall(sql)), 3,
            msg='the layers of a service answered: ' + sql[:400])
        # the marker does exist only where the layers of a service are asked:
        # the whole-registry queryset restricts its CTEs to itself, which is no
        # service restriction at all
        registry_sql = str(Layer.objects.all()
                           .with_inherited_attributes_cte().query)
        self.assertEqual(len(self.SCOPE_MARKER.findall(registry_sql)), 0,
                         'the marker matched a statement without a service '
                         'restriction - it would not catch a regression')
        _status, _body, queries = self.request(
            self.path, user='user', **{'page[size]': 100})
        statements = [query['sql'] for query in queries
                      if '"ancestors" AS (' in query['sql']]
        self.assertTrue(statements,
                        'the layers endpoint answered without the CTEs at all')
        for statement in statements:
            self.assertEqual(
                len(self.SCOPE_MARKER.findall(statement)), 3,
                msg='a statement of the layers endpoint computed the '
                    'inheritance without restricting it to the layers of '
                    'the service: ' + statement[:400])

    def layers_of_answer(self, body):
        """The answered rows, keyed by their title."""
        return {row['attributes']['title']: row for row in body['data']}

    def test_the_layers_answer_the_effective_values_in_json_api(self):
        """The JSON:API answer of the layers endpoint keeps its shape."""
        status, body, _queries = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.assertEqual(status, 200, body)
        answered = self.layers_of_answer(body)
        self.assertEqual(
            {row['type'] for row in body['data']}, {'Layer'})
        self.assertEqual(answered['a']['attributes']['isQueryable'], True)
        self.assertEqual(answered['a']['attributes']['scaleMin'], 10)
        self.assertEqual(answered['a1']['attributes']['scaleMin'], None)
        self.assertEqual(answered['a1']['attributes']['isQueryable'], False)
        self.assertEqual(answered['b']['attributes']['isSecured'], True)
        self.assertEqual(answered['b']['attributes']['isSpatialSecured'], True)
        self.assertEqual(answered['a1']['attributes']['isSecured'], False)
        # the inherited bbox is answered as "bboxLatLon", the own one as "bbox"
        for title, expected in (('a1', WORLD), ('b1', SMALL)):
            self.assertEqual(
                answered[title]['attributes']['bboxLatLon'],
                {'type': 'Polygon',
                 'bbox': list(expected.extent),
                 'coordinates': [[list(point)
                                  for point in expected[0]]]})
            self.assertEqual(
                answered[title]['attributes']['bbox'],
                None if title == 'a1' else
                {'type': 'Polygon',
                 'coordinates': [[list(point)
                                  for point in expected[0]]]})
        # the relations of a layer are answered as related resources
        self.assertEqual(
            answered['root']['relationships']['service']['data']['id'],
            str(self.measured.pk))
        # the order of the tree is the order of the answer (the deep chain is
        # the service's second tree, its rank between the trees is the tree
        # id's sort order and none of this assertion's business)
        self.assertEqual(
            [row['attributes']['title'] for row in body['data']
             if not row['attributes']['title'].startswith('deep')],
            ['root', 'a', 'a1', 'a2', 'a21', 'b', 'b1'])

    def test_only_the_layers_of_the_service_of_the_url_are_answered(self):
        """Service scoping is part of the contract of the nested endpoint."""
        status, body, _queries = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.assertEqual(status, 200, body)
        self.assertEqual(
            set(self.layers_of_answer(body)),
            set(self.measured.layers.values_list('title', flat=True)))
        self.assertNotIn('other-root', self.layers_of_answer(body))

    def test_the_answer_needs_the_same_work_for_a_bigger_tree(self):
        """The number of statements may not grow with the tree of the service."""
        _status, _body, before = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.grow(self.measured, 40)
        status, _body, after = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.assertEqual(status, 200)
        self.assertEqual(
            len(after.captured_queries), len(before.captured_queries),
            msg=f'the layers of a service asked {len(before.captured_queries)} '
                f'statements before and {len(after.captured_queries)} after its '
                f'tree grew by 40 layers: '
                f'{[q["sql"][:80] for q in after.captured_queries]}')

    def test_the_answer_needs_the_same_work_for_more_layers_in_the_registry(self):
        """Layers of other services may not make this answer work more.

        This is the property the 48.5 s of #1315 broke: the request answered
        the layers of one service but computed the inheritance of every layer
        of the deployment, so it became slower the bigger the registry was -
        and not the smaller the service.
        """
        _status, _body, before = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.grow(self.other, self.FILLER_LAYERS)
        status, _body, after = self.request(
            self.path, user='user', **{'page[size]': 100})
        self.assertEqual(status, 200)
        self.assertEqual(
            len(after.captured_queries), len(before.captured_queries),
            msg=f'the layers of a service asked {len(before.captured_queries)} '
                f'statements before and {len(after.captured_queries)} after '
                f'{self.FILLER_LAYERS} layers of another service existed: '
                f'{[q["sql"][:80] for q in after.captured_queries]}')


class LayerInheritanceBenchmark(LayerTreeMixin, QueryMeasurementMixin,
                                TransactionTestCase):
    """The measured benchmark of the layers of a service (#1315).

    NOT A CI TEST - skipped unless the environment names it, because it
    measures seconds and not shapes; the shapes it relies on are guarded by
    ``LayersEndpointTest`` and ``InheritedLayerValuesTest`` in every run.

    The fixture is the scale the issue reports: a service with 4 layers in a
    registry of ``REGISTRY_LAYERS`` layers of other services, seeded with
    set-based SQL over the row shape the ORM creates, then ANALYZE. The
    measurement is the layers endpoint of that service, requested warm; the
    reported numbers are median and p95 of the runs, the number of statements
    of one warm request and the rows the materialised CTE answers.

    The live rig measured 48.5 s for 4 layers with 265,653 layers of the
    registry; that hardware is not this rig, so the AC ask for a warm request
    under 2 s in a comparable environment. Run it at the head of the fix and at
    the commit before it to read both on one machine
    (``MRMAP_LAYER_CTE_BENCHMARK_RUNS`` lowers the repetition count):

        MRMAP_LAYER_CTE_BENCHMARK=1 docker compose ... run --rm django-tests \
            python manage.py test \
            tests.django.registry.tests_layer_inheritance.LayerInheritanceBenchmark \
            --noinput --keepdb
    """

    REGISTRY_LAYERS = 265653
    SERVICE_LAYERS = 4
    ITERATIONS = int(os.environ.get('MRMAP_LAYER_CTE_BENCHMARK_RUNS', '25'))
    # the target of the AC of #1315 for a comparable environment
    WARM_MEDIAN_SECONDS = 2.0

    def setUp(self):
        # a TransactionTestCase truncates the tables and gets no setUpTestData,
        # so the fixture of the mixin and the user of the request are set up
        # per test (see backend/tests/AGENTS.md)
        super().setUp()
        self.user = get_user_model().objects.get(username='User1')
        get_user_model().objects.get_or_create(username='AnonymousUser')
        self.seed()

    @skipUnless(
        os.environ.get('MRMAP_LAYER_CTE_BENCHMARK') == '1',
        'opt-in benchmark of #1315; the shapes it measures run in every CI run')
    def test_warm_median_and_statement_count_of_the_layers_of_a_service(self):
        from time import perf_counter

        # the reported request: a service with 4 layers in a registry of
        # hundreds of thousands of layers
        Layer.objects.filter(service=self.measured).delete()
        build_tree(self.measured, {
            'identifier': 'bench-root', 'bbox_lat_lon': WORLD,
            'children': [{'identifier': f'bench-{number}'}
                         for number in range(self.SERVICE_LAYERS - 1)]})
        self.grow_with_sql(self.other, self.REGISTRY_LAYERS
                           - self.SERVICE_LAYERS - self.other.layers.count())
        self.assertEqual(
            self.measured.layers.count(), self.SERVICE_LAYERS,
            'the measured service must hold the 4 layers of the report')
        with connections['default'].cursor() as cursor:
            cursor.execute('ANALYZE registry_layer')
            cursor.execute('SELECT count(*) FROM registry_layer')
            layers = cursor.fetchone()[0]

        client = APIClient()
        client.force_login(self.user)
        path = f'/api/registry/wms/{self.measured.pk}/layers'
        for _ in range(3):  # warm-up: plan cache and relation caches
            self.assertEqual(
                client.get(path, HTTP_ACCEPT=JSONAPI).status_code, 200)

        durations = []
        for _ in range(self.ITERATIONS):
            started = perf_counter()
            response = client.get(path, HTTP_ACCEPT=JSONAPI)
            durations.append(perf_counter() - started)
            self.assertEqual(response.status_code, 200)
        durations.sort()
        with CaptureQueriesContext(connections['default']) as queries:
            self.assertEqual(
                client.get(path, HTTP_ACCEPT=JSONAPI).status_code, 200)
        p95 = durations[max(0, math.ceil(0.95 * len(durations)) - 1)]
        statement = [query['sql'] for query in queries.captured_queries
                     if '"ancestors" AS (' in query['sql']]
        print(
            'LAYER-CTE-BENCHMARK '
            f'layers={layers} service_layers={self.SERVICE_LAYERS} '
            f'iterations={self.ITERATIONS} '
            f'median_s={median(durations):.3f} p95_s={p95:.3f} '
            f'statements={len(queries.captured_queries)} '
            f'cte_statement_chars={len(statement[0]) if statement else 0}',
            flush=True)
        self.assertLess(
            median(durations), self.WARM_MEDIAN_SECONDS,
            f'the layers of a service with {self.SERVICE_LAYERS} layers in a '
            f'registry of {layers} layers took {median(durations):.3f} s warm; '
            f'the AC of #1315 ask for less than {self.WARM_MEDIAN_SECONDS} s')
