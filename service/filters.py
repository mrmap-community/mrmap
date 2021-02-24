import django_filters
from django import forms
from django.db.models import Q

from MrMap.filtersets import MrMapFilterSet
from MrMap.widgets import BootstrapDatePickerRangeWidget
from service.helper.enums import OGCServiceEnum
from service.models import Metadata, Layer, FeatureType, ProxyLog
from django.utils.translation import gettext_lazy as _
from structure.models import MrMapGroup, MrMapUser


class OgcWmsFilter(django_filters.FilterSet):
    service__is_root = django_filters.BooleanFilter(
        widget=forms.CheckboxInput(),
        label=_("Show layers"),
        initial=False,
        exclude=True,
    )

    class Meta:
        model = Metadata
        fields = {
            'title': ['icontains'],
            'service__is_root': ['exact'], }

    def __init__(self, *args, **kwargs):
        super(OgcWmsFilter, self).__init__(prefix='wms-filter', *args, **kwargs)


class OgcWfsFilter(django_filters.FilterSet):
    class Meta:
        model = Metadata
        fields = {'title': ['icontains'], }

    def __init__(self, *args, **kwargs):
        super(OgcWfsFilter, self).__init__(prefix='wfs-filter', *args, **kwargs)


class OgcCswFilter(django_filters.FilterSet):
    class Meta:
        model = Metadata
        fields = {'title': ['icontains'], }

    def __init__(self, *args, **kwargs):
        super(OgcCswFilter, self).__init__(prefix='csw-filter', *args, **kwargs)


class DatasetFilter(django_filters.FilterSet):
    class Meta:
        model = Metadata
        fields = {'title': ['icontains'], }

    def __init__(self, *args, **kwargs):
        super(DatasetFilter, self).__init__(prefix='dataset-filter', *args, **kwargs)


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
    show_layers = django_filters.BooleanFilter(
        widget=forms.CheckboxInput(),
        label=_("Show layers"),
        method='filter_layers',
        required=False,
        initial=False,
    )

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(contact__organization_name__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value) | \
               queryset.filter(service__published_for__organization_name__icontains=value) | \
               queryset.filter(created__icontains=value)

    @staticmethod
    def filter_layers(queryset, name, value):
        queryset = queryset.filter(
            service__is_root=not value
        )
        return queryset

    class Meta:
        model = Metadata
        fields = []


class MetadataWfsFilter(django_filters.FilterSet):
    wfs_search = django_filters.CharFilter(method='filter_search_over_all',
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


class MetadataCswFilter(django_filters.FilterSet):
    wfs_search = django_filters.CharFilter(method='filter_search_over_all',
                                           label=_('Search'))

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value) | \
               queryset.filter(service__created_by__name__icontains=value)

    class Meta:
        model = Metadata
        fields = []


class ProxyLogTableFilter(MrMapFilterSet):
    timestamp = django_filters.DateTimeFromToRangeFilter(
        label=_("Timestamp"),
        widget=BootstrapDatePickerRangeWidget(),
        help_text=_("Search in a date range."),
    )

    user__username = django_filters.ModelMultipleChoiceFilter(
        queryset=MrMapUser.objects.all(),
        widget=forms.CheckboxSelectMultiple,
    )

    user__groups__name = django_filters.ModelMultipleChoiceFilter(
        queryset=MrMapGroup.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        method="filter_by_group",
    )

    metadata__service__service_type__name = django_filters.MultipleChoiceFilter(
        choices=OGCServiceEnum.as_choices(drop_empty_choice=True),
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ProxyLog
        fields = {
                  'metadata__title': ['icontains'],
                  'metadata__id': ['icontains'],
                  }

    def __init__(self, *args, **kwargs):
        super(ProxyLogTableFilter, self).__init__(prefix='proxy-log-filter', *args, **kwargs)

    def filter_by_group(self, queryset, name, value):
        public_group = MrMapGroup.objects.get(name="Public")
        if public_group in value:
            value.remove(MrMapGroup.objects.get(name="Public"))
            logs_from_public_group = queryset.filter(Q(user=None))
            queryset = queryset.filter(user__groups__in=value) | logs_from_public_group
        elif value:
            queryset = queryset.filter(user__groups__in=value)
        return queryset


class MetadataDatasetFilter(django_filters.FilterSet):
    ds = django_filters.CharFilter(
        method='filter_search_over_all',
        label=_('Search')
    )

    @staticmethod
    def filter_search_over_all(queryset, name, value):  # parameter name is needed cause 3 values are expected

        return queryset.filter(title__icontains=value)

    class Meta:
        model = Metadata
        fields = []
