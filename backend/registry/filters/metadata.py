from django_filters import BooleanFilter, FilterSet
from rest_framework_gis.filters import GeometryFilter
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord


class MetadataQualityFilterSetMixin(FilterSet):
    """Additive filters behind the indicators the discovery shows for metadata records.

    The distinction between an unknown value and an explicit false one belongs to the UI; these
    filters answer the binary question of a facet. Facet counts are answered by the api over the
    complete authorized result set and never over a page, so the same filters serve for rows and
    counts alike.
    """
    is_broken = BooleanFilter(field_name='is_broken')
    has_insufficient_quality = BooleanFilter(method='filter_has_insufficient_quality')
    has_coverage = BooleanFilter(method='filter_has_coverage')
    has_licence = BooleanFilter(method='filter_has_licence')

    def filter_has_insufficient_quality(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.exclude(insufficient_quality='') if value else queryset.filter(insufficient_quality='')

    def filter_has_coverage(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(bounding_geometry__isnull=not value)

    def filter_has_licence(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.exclude(licence__isnull=True) if value else queryset.filter(licence__isnull=True)


class DatasetMetadataRecordSpatialFilterSet(MetadataQualityFilterSetMixin, FilterSet):
    bounding_geometry__intersects = GeometryFilter(field_name='bounding_geometry', lookup_expr='intersects')
    bounding_geometry__within = GeometryFilter(field_name='bounding_geometry', lookup_expr='within')
    bounding_geometry__contains = GeometryFilter(field_name='bounding_geometry', lookup_expr='contains')

    class Meta:
        model = DatasetMetadataRecord
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            "title": ["exact", "icontains", "contains"],
            "abstract": ["exact", "icontains", "contains"],
            "keywords__keyword": ["exact", "icontains", "contains"],
            "harvested_dataset_metadata_relation__harvesting_job": ["exact"],
            "harvested_dataset_metadata_relation__collecting_state": ["exact"],
            # "harvested_by": ['exact', 'icontains', 'contains', 'in'],
            # "harvested_by__background_process__started_at": ['gte', 'lte', 'exact', 'gt', 'lt', 'range'],
            # "ignored_by": ['exact', 'icontains', 'contains', 'in'],
            # "updated_by": ['exact', 'icontains', 'contains', 'in'],
            # "updated_by__background_process__started_at": ['gte', 'lte', 'exact', 'gt', 'lt', 'range'],
        }


class ServiceMetadataRecordSpatialFilterSet(MetadataQualityFilterSetMixin, FilterSet):
    bounding_geometry__intersects = GeometryFilter(field_name='bounding_geometry', lookup_expr='intersects')
    bounding_geometry__within = GeometryFilter(field_name='bounding_geometry', lookup_expr='within')
    bounding_geometry__contains = GeometryFilter(field_name='bounding_geometry', lookup_expr='contains')

    class Meta:
        model = ServiceMetadataRecord
        fields = {
            'id': ['exact', 'icontains', 'contains', 'in'],
            "title": ["exact", "icontains", "contains"],
            "abstract": ["exact", "icontains", "contains"],
            "keywords__keyword": ["exact", "icontains", "contains"],
            "harvested_service_metadata_relation__harvesting_job": ["exact"],
            "harvested_service_metadata_relation__collecting_state": ["exact"],
        }
