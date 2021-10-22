import uuid

from django.contrib.gis.geos import GEOSGeometry, Polygon
from django.db.models import Q
from extras.api.filters import MrMapApiSearchFilter, validate_uuid
from registry.api.serializers.service import LayerSerializer, FeatureTypeSerializer
from registry.models import Service, FeatureType, Layer


class ServiceApiFilter(MrMapApiSearchFilter):
    """
    This filter can be used to filter Services by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        model = Service
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
            Q(service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        )

    @staticmethod
    def bbox_filter(queryset, name, bbox_coords):
        bbox_polygon = GEOSGeometry(Polygon.from_bbox(bbox_coords), srid=4326)  # [xmin, ymin, xmax, ymax]
        unique_services = list()
        layer_within_bbox = Layer\
            .objects\
            .filter(bbox_lat_lon__intersects=bbox_polygon)
        layers = LayerSerializer(layer_within_bbox, many=True).data
        for layer in layers:
            if layer['service'] not in unique_services:
                unique_services.append(layer['service'])
        feature_type_within_bbox = FeatureType\
            .objects\
            .filter(bbox_lat_lon__intersects=bbox_polygon)
        feature_types = FeatureTypeSerializer(feature_type_within_bbox, many=True).data
        for feature_type in feature_types:
            if feature_type['service'] not in unique_services:
                unique_services.append(feature_type['service'])
        return queryset.filter(id__in=unique_services)


class LayerApiFilter(MrMapApiSearchFilter):
    """
    This filter can be used to filter Layers by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        model = Layer
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
            Q(service__service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        )


class FeatureTypeApiFilter(MrMapApiSearchFilter):
    """
    This filter can be used to filter FeatureTypes by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        model = FeatureType
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
            Q(service__service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        )
