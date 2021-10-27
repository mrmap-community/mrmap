import uuid

from django.db.models import Q

from extras.api.filters import MrMapApiSearchFilter, validate_uuid
from registry.models import MapContext


class MapContextApiFilter(MrMapApiSearchFilter):
    """
    This filter can be used to filter MapContexts by different values in API views or viewsets.
    See https://django-filter.readthedocs.io/en/stable/guide/rest_framework.html
    """

    class Meta:
        model = MapContext
        fields = {}

    @staticmethod
    def search_filter(queryset, name, value):
        if validate_uuid(value):
            return queryset.filter(Q(id__contains=uuid.UUID(value)))
        # __icontains -> case insensitive contains
        return queryset.filter(
            Q(title__icontains=value) |
            Q(abstract__icontains=value) |
            Q(mapcontextlayer__layer__service__service_type__name__icontains=value) |
            Q(owned_by_org__name__icontains=value)
        ).distinct()
