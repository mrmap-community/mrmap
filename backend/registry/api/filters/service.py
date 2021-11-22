from registry.models.service import OgcService, WebFeatureService, WebMapService, FeatureType, Layer
from rest_framework_gis.filterset import GeoFilterSet
from rest_framework_gis.filters import GeometryFilter


class OgcServiceFilterSet(GeoFilterSet):
    layer__bbox_lat_lon__contains = GeometryFilter(field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='contains')
    layer__bbox_lat_lon__covers = GeometryFilter(field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='covers')
    layer__bbox_lat_lon__equals = GeometryFilter(field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='equals')
    layer__bbox_lat_lon__intersects = GeometryFilter(field_name='webmapservice__layer__bbox_lat_lon', lookup_expr='intersects')

    featuretype__bbox_lat_lon__contains = GeometryFilter(field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='contains')
    featuretype__bbox_lat_lon__covers = GeometryFilter(field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='covers')
    featuretype__bbox_lat_lon__equals = GeometryFilter(field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='equals')
    featuretype__bbox_lat_lon__intersects = GeometryFilter(field_name='webfeatureservice__featuretype__bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = OgcService
        fields = {
            'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class WebMapServiceFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(field_name='layer__bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(field_name='layer__bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(field_name='layer__bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(field_name='layer__bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = WebMapService
        fields = {
            'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class LayerFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = Layer
        fields = {
            'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class WebFeatureServiceFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(field_name='featuretype__bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(field_name='featuretype__bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(field_name='featuretype__bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(field_name='featuretype__bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = WebFeatureService
        fields = {
            'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class FeatureTypeFilterSet(GeoFilterSet):
    bbox_lat_lon__contains = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(field_name='bbox_lat_lon', lookup_expr='intersects')

    class Meta:
        model = FeatureType
        fields = {
            'id': ['exact', 'lt', 'gt', 'gte', 'lte', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }
