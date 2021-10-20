import uuid

from django.db.models import Q

from MrMap.filters import MrMapSearchFilter, validate_uuid
from registry.models import MapContext


class MapContextFilter(MrMapSearchFilter):
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
        return queryset
