import django_filters
from service.models import AllowedOperation


class AllowedOperationFilter(django_filters.FilterSet):
    class Meta:
        model = AllowedOperation
        fields = {'operations', 'allowed_groups', 'secured_metadata'}

    def __init__(self, *args, **kwargs):
        super(AllowedOperationFilter, self).__init__(prefix='allowed-operations-filter', *args, **kwargs)
