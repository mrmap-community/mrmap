import django_filters
from django_filters.widgets import RangeWidget

from MrMap.widgets import BootstrapDatePickerRangeWidget
from service.models import Metadata, Layer, FeatureType, ProxyLog, MetadataType, ServiceType
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


class ProxyLogTableFilter(django_filters.FilterSet):
    time_search = django_filters.DateTimeFromToRangeFilter(label=_("Timestamp"),
                                                           field_name='timestamp',
                                                           widget=BootstrapDatePickerRangeWidget(),)
    service_title_search = django_filters.CharFilter(label=_("Service title"),
                                                     field_name='metadata__title',
                                                     lookup_expr='icontains',)
    group_search = django_filters.CharFilter(label=_("Group"),
                                             field_name='metadata__created_by',
                                             lookup_expr='name__icontains')
    user_search = django_filters.CharFilter(label=_("User"),
                                            field_name='user',
                                            lookup_expr='username__icontains',)
    service_type_search = django_filters.ModelMultipleChoiceFilter(label=_("Service type"),
                                                                   field_name='metadata__service__servicetype',
                                                                   queryset=ServiceType.objects.all())

    class Meta:
        model = ProxyLog
        fields = []
