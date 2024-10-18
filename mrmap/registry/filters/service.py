from django.utils.translation import gettext_lazy as _
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
            'id': ['exact', 'icontains', 'contains', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class LayerFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(
        label=_('bbox contains'),
        help_text=_(
            'returns layers with bbox that are contained by the passed geometry'),
        field_name='bbox_inherited',
        lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        label=_('bbox covers'),
        help_text=_(
            'returns layers with bbox that are covers the passed geometry'),
        field_name='bbox_inherited',
        lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        label=_('bbox equals'),
        help_text=_(
            'returns layers with bbox that are equal to the passed geometry'),
        field_name='bbox_inherited',
        lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        label=_('bbox intersects'),
        help_text=_(
            'returns layers with bbox that intersects the passed geometry'),
        field_name='bbox_inherited',
        lookup_expr='intersects')

    class Meta:
        model = Layer
        fields = {
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains'],
            'identifier': ['exact', 'icontains', 'contains'],
            'is_queryable': ['exact'],
            'is_broken': ['exact'],
            'is_customized': ['exact'],
            'is_searchable': ['exact'],
            'is_active': ['exact'],
            'is_opaque': ['exact'],
            'is_cascaded': ['exact'],
            'mptt_lft': ['exact', 'gt', 'gte', 'lt', 'lte'],
            'mptt_rgt': ['exact', 'gt', 'gte', 'lt', 'lte'],
            'mptt_tree': ['exact'],
            'mptt_depth': ['exact', 'gt', 'gte', 'lt', 'lte'],
            'service': ['exact']
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
