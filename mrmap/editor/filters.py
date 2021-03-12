import django_filters
from django import forms
from django.utils.translation import gettext_lazy as _

from service.models import AllowedOperation
from structure.models import MrMapGroup
from users.helper import user_helper


class AllowedOperationFilter(django_filters.FilterSet):
    class Meta:
        model = AllowedOperation
        fields = {'operations', 'allowed_groups', 'secured_metadata'}

    def __init__(self, *args, **kwargs):
        super(AllowedOperationFilter, self).__init__(prefix='allowed-operations-filter', *args, **kwargs)
