from django.utils.translation import gettext_lazy as _
from django_filters import BooleanFilter
from django_filters.filterset import FilterSet
from registry.models.service import (CatalogueService, FeatureType, Layer,
                                     WebFeatureService, WebMapService)
from rest_framework_gis.filters import GeometryFilter
from rest_framework_gis.filterset import GeoFilterSet


class ServiceSpatialFilterSet(FilterSet):
    bbox_lat_lon__contains = GeometryFilter(method='filter_coverage')
    bbox_lat_lon__covers = GeometryFilter(method='filter_coverage')
    bbox_lat_lon__equals = GeometryFilter(method='filter_coverage')
    bbox_lat_lon__intersects = GeometryFilter(method='filter_coverage')

    def filter_coverage(self, queryset, name, value):
        from django.db.models import Q
        from registry.querys.explorer import service_elements
        from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord
        lookup = name.rsplit('__', 1)[-1]
        if queryset.model is CatalogueService:
            ids = [model.objects.filter(**{f'bounding_geometry__{lookup}': value})
                   .values('harvested_through') for model in (DatasetMetadataRecord, ServiceMetadataRecord)]
            return queryset.filter(Q(pk__in=ids[0]) | Q(pk__in=ids[1]))
        elements, field = service_elements(queryset.model)
        return queryset.filter(pk__in=elements.filter(**{f'{field}__{lookup}': value}).values('service'))


class WebMapServiceFilterSet(ServiceSpatialFilterSet):
    is_update_candidate = BooleanFilter(
        field_name="update_candidate_of", lookup_expr="isnull", exclude=True,
    )

    # The alerts of a service are answered by annotations which the viewset only
    # adds to a query which asks for them, see registry/querys/alerts.py. Only
    # the schedules a service did not keep are not filterable here, because they
    # are answered by python.
    has_alert = BooleanFilter(field_name="has_alert")
    monitoring_failed = BooleanFilter(field_name="monitoring_failed")
    update_review_required = BooleanFilter(
        field_name="update_review_required")
    update_failed = BooleanFilter(field_name="update_failed")

    class Meta:
        model = WebMapService
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class LayerFilterSet(GeoFilterSet):
    is_update_candidate = BooleanFilter(
        field_name="service__update_candidate_of", lookup_expr="isnull", exclude=True,
    )

    bbox_lat_lon__contains = GeometryFilter(
        label=_('bbox contains'),
        help_text=_(
            'returns layers with bbox that are contained by the passed geometry'),
        field_name='bbox_lat_lon_inherited',
        lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        label=_('bbox covers'),
        help_text=_(
            'returns layers with bbox that are covers the passed geometry'),
        field_name='bbox_lat_lon_inherited',
        lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        label=_('bbox equals'),
        help_text=_(
            'returns layers with bbox that are equal to the passed geometry'),
        field_name='bbox_lat_lon_inherited',
        lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        label=_('bbox intersects'),
        help_text=_(
            'returns layers with bbox that intersects the passed geometry'),
        field_name='bbox_lat_lon_inherited',
        lookup_expr='intersects')

    has_mapping = BooleanFilter(
        label=_('has mapping'),
        help_text=_('returns layers that are not mapped to any layer mapping'),
        field_name='mapping',
        lookup_expr='isnull',
        exclude=True
    )
    has_reverse_mapping = BooleanFilter(
        label=_('has reverse mapping'),
        help_text=_('returns layers that are mapped to a layer mapping'),
        field_name='reverse_mapping',
        lookup_expr='isnull',
        exclude=True
    )

    class Meta:
        model = Layer
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
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
            'service': ['exact'],
            # 'no_mapping': ['exact']
            # TODO: mapping is a reverse field on Layer. How can we filter for layers without mapping?
        }


class WebFeatureServiceFilterSet(ServiceSpatialFilterSet):
    is_update_candidate = BooleanFilter(
        field_name="update_candidate_of", lookup_expr="isnull", exclude=True,
    )

    # the alerts of a service, see WebMapServiceFilterSet
    has_alert = BooleanFilter(field_name="has_alert")
    monitoring_failed = BooleanFilter(field_name="monitoring_failed")
    update_review_required = BooleanFilter(
        field_name="update_review_required")
    update_failed = BooleanFilter(field_name="update_failed")

    class Meta:
        model = WebFeatureService
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class FeatureTypeFilterSet(GeoFilterSet):
    is_update_candidate = BooleanFilter(
        field_name="service__update_candidate_of", lookup_expr="isnull", exclude=True,
    )

    bbox_lat_lon__contains = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='contains')
    bbox_lat_lon__covers = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='covers')
    bbox_lat_lon__equals = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='equals')
    bbox_lat_lon__intersects = GeometryFilter(
        field_name='bbox_lat_lon', lookup_expr='intersects')

    has_mapping = BooleanFilter(
        label=_("has mapping"),
        help_text=_(
            "returns featuretypes that are not mapped to any featuretype mapping"),
        field_name="mapping",
        lookup_expr="isnull",
        exclude=True,
    )
    has_reverse_mapping = BooleanFilter(
        label=_("has reverse mapping"),
        help_text=_(
            "returns featuretypes that are mapped to a featuretype mapping"),
        field_name="reverse_mapping",
        lookup_expr="isnull",
        exclude=True,
    )

    class Meta:
        model = FeatureType
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }


class CatalogueServiceFilterSet(ServiceSpatialFilterSet):
    # the alerts of a service, see WebMapServiceFilterSet. A catalogue is the
    # only kind of service whose records are pulled by a harvesting job, so it
    # answers the state of that job in addition.
    has_alert = BooleanFilter(field_name="has_alert")
    monitoring_failed = BooleanFilter(field_name="monitoring_failed")
    update_review_required = BooleanFilter(
        field_name="update_review_required")
    update_failed = BooleanFilter(field_name="update_failed")
    harvest_aborted = BooleanFilter(field_name="harvest_aborted")
    harvest_incomplete = BooleanFilter(field_name="harvest_incomplete")
    is_update_candidate = BooleanFilter(
        field_name="update_candidate_of", lookup_expr="isnull", exclude=True,
    )

    class Meta:
        model = CatalogueService
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            'title': ['exact', 'icontains', 'contains'],
            'abstract': ['exact', 'icontains', 'contains']
        }
