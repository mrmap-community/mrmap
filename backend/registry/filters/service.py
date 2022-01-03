from django_filters.filterset import FilterSet
from registry.models.service import (FeatureType, Layer, WebFeatureService,
                                     WebMapService)
from rest_framework_gis.filters import GeometryFilter
from rest_framework_gis.filterset import GeoFilterSet


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
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
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
