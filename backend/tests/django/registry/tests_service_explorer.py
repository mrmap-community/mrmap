from django.contrib.gis.geos import MultiPolygon, Polygon
from django.test import TestCase
from registry.filters.service import WebMapServiceFilterSet, WebFeatureServiceFilterSet, CatalogueServiceFilterSet
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord, MetadataContact
from registry.models.service import WebMapService, WebFeatureService, CatalogueService, Layer
from registry.querys.explorer import service_coverage
from tests.django.registry.tests_query_performance import QueryMeasurementMixin, SERVICES


class ServiceExplorerTests(QueryMeasurementMixin, TestCase):
    fixtures = SERVICES

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        MetadataContact.objects.get_or_create(pk='1234', defaults={'name': 'Explorer contact'})

    def test_extent_is_opt_in_and_query_budget_is_fixed(self):
        for model, path in [(WebMapService, '/api/registry/wms'), (WebFeatureService, '/api/registry/wfs')]:
            fields = {'fields[' + model.__name__ + ']': 'id,title,extent,element_count,can_edit'}
            status, body, queries = self.request(path, user='user', **fields)
            self.assertEqual(status, 200)
            self.assertIn('extent', body['data'][0]['attributes'])
            self.assertIn('elementCount', body['data'][0]['attributes'])
            self.assertQueriesIndependentOfRows(path, **fields)
            _, plain, plain_queries = self.request(path, user='user')
            self.assertNotIn('extent', plain['data'][0]['attributes'])
            self.assertFalse(any('ST_Union' in query['sql'] for query in plain_queries))
            self.assertLessEqual(len(queries), len(plain_queries))

    def test_wms_inherits_parent_and_includes_child_extents(self):
        layer = Layer.objects.filter(mptt_parent__isnull=False).first()
        parent = layer.mptt_parent
        bounds = Polygon.from_bbox((6, 49, 7, 50))
        bounds.srid = 4326
        Layer.objects.filter(service=layer.service).update(bbox_lat_lon=None)
        Layer.objects.filter(pk=parent.pk).update(bbox_lat_lon=bounds)
        extent = service_coverage(WebMapService.objects.filter(pk=layer.service_id)).get().extent
        self.assertTrue(extent.equals(bounds))
        for lookup in ('contains', 'covers', 'equals', 'intersects'):
            filtered = WebMapServiceFilterSet({f'bbox_lat_lon__{lookup}': bounds.wkt}, queryset=WebMapService.objects.all()).qs
            self.assertIn(layer.service_id, filtered.values_list('pk', flat=True))
        Layer.objects.filter(pk=parent.pk).update(bbox_lat_lon=None)
        Layer.objects.filter(pk=layer.pk).update(bbox_lat_lon=bounds)
        self.assertTrue(service_coverage(WebMapService.objects.filter(pk=layer.service_id)).get().extent.equals(bounds))

    def test_spatial_filters_do_not_duplicate_services(self):
        for model, filterset in [(WebMapService, WebMapServiceFilterSet), (WebFeatureService, WebFeatureServiceFilterSet)]:
            geometry = Polygon.from_bbox((-180, -90, 180, 90))
            qs = filterset({'bbox_lat_lon__intersects': geometry.wkt}, queryset=model.objects.all()).qs
            ids = list(qs.values_list('pk', flat=True))
            self.assertTrue(ids)
            self.assertEqual(len(ids), len(set(ids)))

    def test_catalogue_coverage_is_from_harvested_records(self):
        from guardian.shortcuts import assign_perm
        catalogue = CatalogueService.objects.create(title='Catalogue', version=202, metadata_contact_id='1234', service_contact_id='1234')
        bounds = Polygon.from_bbox((6, 49, 7, 50))
        bounds.srid = 4326
        other = Polygon.from_bbox((10, 49, 11, 50))
        other.srid = 4326
        records = []
        for model, geometry in [(DatasetMetadataRecord, bounds), (ServiceMetadataRecord, other)]:
            record = model.objects.create(title='Harvested record', bounding_geometry=MultiPolygon(geometry), metadata_contact_id='1234', **({'dataset_contact_id': '1234'} if model is DatasetMetadataRecord else {}))
            record.harvested_through.add(catalogue)
            records.append(record)
        extent = service_coverage(CatalogueService.objects.filter(pk=catalogue.pk)).get().extent
        self.assertTrue(extent.equals(bounds.union(other)))
        for geometry in (bounds, other):
            qs = CatalogueServiceFilterSet({'bbox_lat_lon__intersects': geometry.wkt}, queryset=CatalogueService.objects.all()).qs
            self.assertEqual(list(qs.values_list('pk', flat=True)), [catalogue.pk])
        empty = CatalogueService.objects.create(title='Empty', version=202, metadata_contact_id='1234', service_contact_id='1234')
        self.assertIsNone(service_coverage(CatalogueService.objects.filter(pk=empty.pk)).get().extent)
        fields = {'fields[CatalogueService]': 'id,title,extent,element_count,can_edit'}
        assign_perm('registry.change_catalogueservice', self.user)
        assign_perm('change_catalogueservice', self.user, catalogue)
        for cache in ('_perm_cache', '_user_perm_cache', '_group_perm_cache'):
            self.user.__dict__.pop(cache, None)
        status, body, _ = self.request('/api/registry/csw', user='user', **fields)
        self.assertEqual(status, 200)
        attributes = next(row['attributes'] for row in body['data'] if row['id'] == str(catalogue.pk))
        self.assertEqual(attributes['elementCount'], 2)
        self.assertTrue(attributes['canEdit'])
        self.assertQueriesIndependentOfRows('/api/registry/csw', **fields)
        _, plain, queries = self.request('/api/registry/csw', user='user')
        self.assertNotIn('extent', plain['data'][0]['attributes'])
        self.assertNotIn('isAccessible', plain['data'][0]['attributes'])
        self.assertFalse(any('ST_Union' in query['sql'] for query in queries))
        records[0].harvested_through.clear()
        self.assertTrue(service_coverage(CatalogueService.objects.filter(pk=catalogue.pk)).get().extent.equals(other))

    def test_metadata_geometry_filters(self):
        from registry.filters.metadata import DatasetMetadataRecordSpatialFilterSet, ServiceMetadataRecordSpatialFilterSet
        bounds = Polygon.from_bbox((6, 49, 7, 50))
        bounds.srid = 4326
        outside = Polygon.from_bbox((20, 20, 21, 21))
        outside.srid = 4326
        for model, filterset in [(DatasetMetadataRecord, DatasetMetadataRecordSpatialFilterSet),
                                 (ServiceMetadataRecord, ServiceMetadataRecordSpatialFilterSet)]:
            inside = model.objects.create(title='Inside', bounding_geometry=MultiPolygon(bounds), metadata_contact_id='1234', **({'dataset_contact_id': '1234'} if model is DatasetMetadataRecord else {}))
            model.objects.create(title='Outside', bounding_geometry=MultiPolygon(outside), metadata_contact_id='1234', **({'dataset_contact_id': '1234'} if model is DatasetMetadataRecord else {}))
            for lookup in ('intersects', 'contains', 'within'):
                qs = filterset({f'bounding_geometry__{lookup}': bounds.wkt}, queryset=model.objects.all()).qs
                self.assertEqual(list(qs.values_list('pk', flat=True)), [inside.pk])

    def test_permissions_are_opt_in(self):
        status, body, _ = self.request('/api/registry/wms', **{'fields[WebMapService]': 'id,can_edit'})
        self.assertEqual(status, 200)
        self.assertTrue(body['data'])
        self.assertTrue(all(row['attributes']['canEdit'] is False for row in body['data']))

    def test_openapi_exposes_opt_in_fields_and_geometry_filters(self):
        from django.urls import path
        from drf_spectacular.generators import SchemaGenerator
        from registry.views.service import WebMapServiceViewSet, WebFeatureServiceViewSet, CatalogueServiceViewSet
        from registry.views.metadata import DatasetMetadataViewSet, ServiceMetadataViewSet
        views = [WebMapServiceViewSet, WebFeatureServiceViewSet, CatalogueServiceViewSet,
                 DatasetMetadataViewSet, ServiceMetadataViewSet]
        schema = SchemaGenerator(patterns=[path(f'{index}', view.as_view({'get': 'list'})) for index, view in enumerate(views)]).get_schema(public=True)
        for index in range(5):
            parameters = schema['paths'][f'/{index}']['get']['parameters']
            spatial = [p for p in parameters if 'intersects' in p['name']]
            self.assertEqual(len(spatial), 1)
            self.assertEqual(spatial[0]['schema']['format'], 'geojson')
        for name in ('WebMapServiceList', 'WebFeatureService', 'CatalogueService'):
            self.assertIn('extent', str(schema['components']['schemas'][name]))
