import django_filters
from django import forms

from MrMap.filtersets import MrMapFilterSet
from MrMap.widgets import BootstrapDatePickerRangeWidget
from service.models import Metadata, Layer, FeatureType, ProxyLog, ServiceType
from django.utils.translation import gettext_lazy as _


class ChildLayerFilter(django_filters.FilterSet):
    child_layer_title = django_filters.CharFilter(field_name='metadata',
                                                  lookup_expr='title__icontains',
                                                  label=_('Layer title contains'))

    class Meta:
        model = Layer
        fields = []


class FeatureTypeFilter(django_filters.FilterSet):
    child_layer_title = django_filters.CharFilter(field_name='metadata',
                                                  lookup_expr='title__icontains',
                                                  label=_('Featuretype tile contains'))

    class Meta:
        model = FeatureType
        fields = []


class MetadataWmsFilter(django_filters.FilterSet):
    wms_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    class Meta:
        model = Metadata
        fields = []


class MetadataWfsFilter(django_filters.FilterSet):
    wfs_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label='Search')

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    class Meta:
        model = Metadata
        fields = []


class ProxyLogTableFilter(MrMapFilterSet):
    dr = django_filters.DateTimeFromToRangeFilter(
        label=_("Timestamp"),
        field_name='timestamp',
        method='filter_date_range',
        widget=BootstrapDatePickerRangeWidget(),
    )
    s = django_filters.CharFilter(
        label=_("Service title"),
        field_name='metadata__title',
        lookup_expr='icontains',
    )
    g = django_filters.CharFilter(
        label=_("Group"),
        field_name='metadata__created_by',
        lookup_expr='name__icontains'
    )
    u = django_filters.CharFilter(
        label=_("User"),
        field_name='user',
        lookup_expr='username__icontains',
    )
    t = django_filters.ModelMultipleChoiceFilter(
        label=_("Service type"),
        field_name='metadata__service__servicetype',
        queryset=ServiceType.objects.all(),
        widget=forms.CheckboxSelectMultiple
    )

    def filter_date_range(self, queryset, name, value):
        """ Replaces start and stop range DateTime with 00:00:00 and 23:59:59 to cover full days

        Args:
            queryset:
            name:
            value:
        Returns:

        """
        start = value.start.replace(hour=0, minute=0, second=0)
        stop = value.stop.replace(hour=23, minute=59, second=59)
        queryset = queryset.filter(
            timestamp__gte=start,
            timestamp__lte=stop
        )
        return queryset

    class Meta:
        model = ProxyLog
        fields = []
