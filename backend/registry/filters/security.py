from django.utils.translation import gettext_lazy as _
from registry.models.security import AllowedWebMapServiceOperation
from rest_framework_gis.filters import GeometryFilter
from rest_framework_gis.filterset import GeoFilterSet


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
            "operations__operation": ["exact", "icontains", "contains"],
        }
