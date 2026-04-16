from django.utils.translation import gettext_lazy as _
from django_filters.filterset import FilterSet
from registry.models.update import LayerMapping, WebMapServiceUpdateJob


class WebMapServiceUpdateJobFilterSet(FilterSet):

    class Meta:
        model = WebMapServiceUpdateJob
        fields = {
            "id": ['exact', 'icontains', 'contains', 'in'],
            "service": ['exact', ],
            "status": ['exact', 'icontains', 'contains', 'in'],
            "date_created": ['exact', 'icontains', 'contains', 'in'],
            "done_at": ['exact', 'icontains', 'contains', 'in'],

        }


class LayerMappingFilterSet(FilterSet):

    class Meta:
        model = LayerMapping
        fields = {
            "id": ['exact', 'icontains', 'contains', 'in'],
            "job": ['exact', ],
            "new_layer": ['exact',],
            "old_layer": ['exact', ],
            "created": ['exact', 'icontains', 'contains', 'in'],
            "is_confirmed": ['exact',],
        }
