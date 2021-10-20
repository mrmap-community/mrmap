import uuid
from django.db.models import Q
from MrMap.filters import MrMapSearchFilter, validate_uuid
from registry.models import Service, FeatureType, Layer


class ServiceFilter(MrMapSearchFilter):
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
            Q(id__contains=uuid.UUID(value) if validate_uuid(value) else value) |
            Q(title__icontains=value) |
            Q(abstract__icontains=value) |
            Q(keywords__keyword__icontains=value) |
            Q(service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        )


class LayerFilter(MrMapSearchFilter):
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
        return queryset


class FeatureTypeFilter(MrMapSearchFilter):
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
        return queryset
