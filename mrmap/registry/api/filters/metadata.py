import uuid

from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db.models import Q

from MrMap.filters import MrMapApiSearchFilter, validate_uuid
from registry.models import DatasetMetadata


class DatasetMetadataApiFilter(MrMapApiSearchFilter):
    """
    This filter can be used to filter FeatureTypes by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        model = DatasetMetadata
        fields = {}

    @staticmethod
    def search_filter(queryset, name, value):
        if validate_uuid(value):
            return queryset.filter(Q(id__contains=uuid.UUID(value)))
        # __icontains -> case insensitive contains
        return queryset.filter(
            Q(title__icontains=value) |
            Q(abstract__icontains=value) |
            Q(keywords__keyword__icontains=value) |
            Q(self_pointing_layers__layer__service__service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        )

    @staticmethod
    def bbox_filter(queryset, name, bbox_coords):
        bbox_polygon = GEOSGeometry(Polygon.from_bbox(bbox_coords), srid=4326)  # [xmin, ymin, xmax, ymax]
        return queryset.filter(bounding_geometry__intersects=bbox_polygon)
