from django_filters import FilterSet
from rest_framework_gis.filters import GeometryFilter
from registry.models.metadata import DatasetMetadataRecord, ServiceMetadataRecord


class DatasetMetadataRecordSpatialFilterSet(FilterSet):
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


class ServiceMetadataRecordSpatialFilterSet(FilterSet):
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
