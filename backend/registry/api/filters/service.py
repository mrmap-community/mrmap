from django.db.models.query_utils import Q
from django_filters.filters import Filter
from django_filters.filterset import FilterSet
from registry.models.service import (FeatureType, Layer, OgcService,
                                     WebFeatureService, WebMapService)
from rest_framework_gis.filters import GeometryFilter
from rest_framework_gis.filterset import GeoFilterSet


class OgcServiceFilterSet(FilterSet):
    layer__bbox_lat_lon__contains = Filter(
        field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='contains')
    layer__bbox_lat_lon__covers = Filter(
        field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='covers')
    layer__bbox_lat_lon__equals = Filter(
        field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='equals')
    layer__bbox_lat_lon__intersects = Filter(
        field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='intersects')

    featuretype__bbox_lat_lon__contains = Filter(
        field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='contains')
    featuretype__bbox_lat_lon__covers = Filter(
        field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='covers')
    featuretype__bbox_lat_lon__equals = Filter(
        field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='equals')
    featuretype__bbox_lat_lon__intersects = Filter(
        field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='intersects')

    bbox_lat_lon__contains = Filter(method='bbox_lat_lon_contains')
    bbox_lat_lon__covers = Filter(method='bbox_lat_lon_covers')
    bbox_lat_lon__equals = Filter(method='bbox_lat_lon_equals')
    bbox_lat_lon__intersects = Filter(method='bbox_lat_lon_intersects')

    class Meta:
        model = OgcService
        fields = {
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains'],
            'owned_by_org': ['exact'],
        }

    def bbox_lat_lon_contains(self, queryset, name, value):
        return queryset.filter(
            Q(webmapservice__layer__bbox_lat_lon__contains=value) |
            Q(webfeatureservice__featuretype__bbox_lat_lon__contains=value)
        )

    def bbox_lat_lon_covers(self, queryset, name, value):
        return queryset.filter(
            Q(webmapservice__layer__bbox_lat_lon__covers=value) |
            Q(webfeatureservice__featuretype__bbox_lat_lon__covers=value)
        )

    def bbox_lat_lon_equals(self, queryset, name, value):
        return queryset.filter(
            Q(webmapservice__layer__bbox_lat_lon__equals=value) |
            Q(webfeatureservice__featuretype__bbox_lat_lon__equals=value)
        )

    def bbox_lat_lon_intersects(self, queryset, name, value):
        return queryset.filter(
            Q(webmapservice__layer__bbox_lat_lon__intersects=value) |
            Q(webfeatureservice__featuretype__bbox_lat_lon__intersects=value)
        )


class WebMapServiceFilterSet(FilterSet):
    bbox_lat_lon__contains = GeometryFilter(
        field_name='layer__bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        field_name='layer__bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        field_name='layer__bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        field_name='layer__bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = WebMapService
        fields = {
            'id': ['exact', 'icontains'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains'],
            'created_at': ['lte', 'gte'],
        }


class LayerFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = Layer
        fields = {
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class WebFeatureServiceFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(
        field_name='featuretype__bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        field_name='featuretype__bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        field_name='featuretype__bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        field_name='featuretype__bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = WebFeatureService
        fields = {
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class FeatureTypeFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = FeatureType
        fields = {
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }
