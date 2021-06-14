import django_filters
from django.utils import timezone
from django_filters.widgets import RangeWidget
from resourceNew.models.service import Layer, FeatureType, FeatureTypeElement
from django.utils.translation import gettext_lazy as _


class LayerFilterSet(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='metadata__title',
                                      lookup_expr='icontains')
    time_dimension = django_filters.DateTimeFromToRangeFilter(label=_("Time dimension"),
                                                              help_text=_("Search for layers with time dimension in given datetime range."),
                                                              method="filter_time_dimension",
                                                              widget=RangeWidget(attrs={'placeholder': 'YYYY-MM-DD hh:mm:ss'}))

    class Meta:
        model = Layer
        fields = {
            "id": ["in", ],
            "parent": ["exact", ],
            "service__id": ["in", ]
        }

    def filter_time_dimension(self, queryset, name, value):
        if value.start and not value.stop:
            return queryset.filter(layer_dimension__time_extent__start__lte=value.start,
                                   layer_dimension__time_extent__stop__lte=timezone.now())
        elif not value.start and value.stop:
            return queryset.filter(layer_dimension__time_extent__stop__lte=value.stop)
        elif value.start and value.stop:
            return queryset.filter(layer_dimension__time_extent__start__gte=value.start,
                                   layer_dimension__time_extent__stop__lte=value.stop)
        else:
            return queryset


class FeatureTypeFilterSet(django_filters.FilterSet):
    title = django_filters.CharFilter(field_name='metadata__title',
                                      lookup_expr='icontains')
    time_dimension = django_filters.DateTimeFromToRangeFilter(label=_("Time dimension"),
                                                              help_text=_("Search for feature types with time dimension in given datetime range."),
                                                              method="filter_time_dimension",
                                                              widget=RangeWidget(
                                                                  attrs={'placeholder': 'YYYY-MM-DD hh:mm:ss'}))

    class Meta:
        model = FeatureType
        fields = {
            "id": ["in", ],
            "service__id": ["in", ]
        }

    def filter_time_dimension(self, queryset, name, value):
        if value.start and not value.stop:
            return queryset.filter(feature_type_dimension__time_extent__start__lte=value.start,
                                   feature_type_dimension__time_extent__stop__lte=timezone.now())
        elif not value.start and value.stop:
            return queryset.filter(feature_type_dimension__time_extent__stop__lte=value.stop)
        elif value.start and value.stop:
            return queryset.filter(feature_type_dimension__time_extent__start__gte=value.start,
                                   feature_type_dimension__time_extent__stop__lte=value.stop)
        else:
            return queryset


class FeatureTypeElementFilterSet(django_filters.FilterSet):
    class Meta:
        model = FeatureTypeElement
        fields = {
            "id": ["in", ],
            "name": ["icontains", ],
            "data_type": ["icontains"],
            "feature_type__id": ["in", ]
        }

