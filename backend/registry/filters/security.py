from django.utils.translation import gettext_lazy as _
from django_filters import BaseInFilter, FilterSet, NumberFilter
from registry.models.security import (AllowedWebMapServiceOperation,
                                      WebMapServiceOperation)
from rest_framework_gis.filters import GeometryFilter
from rest_framework_gis.filterset import GeoFilterSet


class NumberInFilter(BaseInFilter, NumberFilter):
    pass


class WebMapServiceOperationFilterSet(FilterSet):
    id__in = NumberInFilter(
        label=_("primary key in"),
        field_name="pk",
        lookup_expr="in"
    )
    id__exact = NumberInFilter(
        label=_("primary key exact"),
        field_name="pk",
        lookup_expr="exact"
    )
    id__icontains = NumberInFilter(
        label=_("primary key icontains"),
        field_name="pk",
        lookup_expr="icontains"
    )
    id__contains = NumberInFilter(
        label=_("primary key contains"),
        field_name="pk",
        lookup_expr="contains"
    )

    class Meta:
        model = WebMapServiceOperation
        fields = {
            'value': ['exact', 'icontains', 'contains', 'in'],
        }


class AllowedWebMapServiceOperationFilterSet(GeoFilterSet):
    allowed_area__contains = GeometryFilter(
        label=_('allowed area contains'),
        help_text=_(
            'returns rules with allowed area that are contained by the passed geometry'),
        field_name='allowed_area',
        lookup_expr='contains')
    allowed_area__covers = GeometryFilter(
        label=_('allowed area covers'),
        help_text=_(
            'returns rules with allowed area that are covers the passed geometry'),
        field_name='allowed_area',
        lookup_expr='covers')
    allowed_area__equals = GeometryFilter(
        label=_('allowed area equals'),
        help_text=_(
            'returns rules with allowed area that are equal to the passed geometry'),
        field_name='allowed_area',
        lookup_expr='equals')
    allowed_area__intersects = GeometryFilter(
        label=_('allowed area intersects'),
        help_text=_(
            'returns rules with allowed area that intersects the passed geometry'),
        field_name='allowed_area',
        lookup_expr='intersects')

    class Meta:
        model = AllowedWebMapServiceOperation
        fields = {
            "description": ["exact", "icontains", "contains"],
            "secured_service__id": ["exact", "icontains", "contains"],
            "secured_layers__id": ["exact", "icontains", "contains"],
            "operations__value": ["exact", "icontains", "contains"],
        }
