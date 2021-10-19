from django.db.models import Q
from django_filters import rest_framework as api_filters
from django_filters.widgets import RangeWidget
from rest_framework_gis.filters import GeometryFilter, GeoFilterSet

from registry.api.serializers.service import LayerSerializer, FeatureTypeSerializer
from registry.models import Service, Layer, FeatureType

LANGUAGE_CHOICES = (
    (0, 'en'),
    (1, 'de')
)


class ServiceFilter(GeoFilterSet):
    """
    This filter can be used to filter Services by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """
    uuid = api_filters.CharFilter(method='uuid_filter', label='UUID')
    text = api_filters.CharFilter(method='text_filter', label='Text')
    registration_date = api_filters.DateFromToRangeFilter(
        widget=RangeWidget(
            attrs={'type': 'date'}
        ),
        method='registration_date_range_filter',
        label='Registration Date'
    )
    datestamp = api_filters.DateFromToRangeFilter(
        widget=RangeWidget(
            attrs={'type': 'date'}
        ),
        method='datestamp_range_filter',
        label='Date Stamp'
    )
    bbox = GeometryFilter(method='bbox_filter', label='Bounding Box')

    class Meta:
        model = Service
        fields = [
            'service_type__name',  # type_filter
            'owned_by_org__name',  # Owner_filter

        ]

    @staticmethod
    def uuid_filter(queryset, name, value):
        return queryset.filter(id__contains=value)

    @staticmethod
    def text_filter(queryset, name, value):
        # __icontains -> case insensitive contains
        return queryset.filter(Q(title__icontains=value) | Q(abstract__icontains=value) | Q(keywords__keyword__icontains=value))

    def language_filter(self):
        pass

    @staticmethod
    def registration_date_range_filter(queryset, name, _range):
        start_date = _range.start
        end_date = _range.stop
        return queryset.filter(created_at__gte=start_date, created_at__lte=end_date)

    @staticmethod
    def datestamp_range_filter(queryset, name, _range):
        start_date = _range.start
        end_date = _range.stop
        return queryset.filter(date_stamp__gte=start_date, date_stamp__lte=end_date)

    @staticmethod
    def bbox_filter(queryset, name, geometry):
        unique_services = list()
        layer_within_bbox = Layer.objects.filter(bbox_lat_lon__contains=geometry)
        layers = LayerSerializer(layer_within_bbox, many=True).data
        for layer in layers:
            if layer['service'] not in unique_services:
                unique_services.append(layer['service'])
        feature_type_within_bbox = FeatureType.objects.filter(bbox_lat_lon__intersects=geometry)
        feature_types = FeatureTypeSerializer(feature_type_within_bbox, many=True).data
        for feature_type in feature_types:
            if feature_type['service'] not in unique_services:
                unique_services.append(feature_type['service'])
        return queryset.filter(id__in=unique_services)
