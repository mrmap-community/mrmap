import operator
from functools import reduce

from celery import states
from django.db.models import Q
from django_filters import rest_framework as filters
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob

unready_condition = reduce(
    operator.or_, [Q(status__exact=s) for s in states.UNREADY_STATES])


class HarvestingJobFilterSet(filters.FilterSet):

    is_unready = filters.BooleanFilter(
        method="filter_is_unready"
    )

    def filter_is_unready(self, queryset, name, value):
        f = Q(done_at__isnull=True) & ~Q(
            phase__lt=HarvestingPhaseEnum.COMPLETED.value)

        if not value:
            f = ~Q(f)
        return queryset.filter(f)

    class Meta:
        model = HarvestingJob
        fields = {
            # 'is_unready': ['exact'],
            'service__id': ['exact', 'contains', 'icontains', 'in'],
            'id': ['exact', 'contains', 'icontains', 'in'],
            # the lookups of the moment a run was made, as the background processes of the same
            # work already answer them (notify/views.py): a run which never had a creation could
            # not be filtered by one, which is why this is here since #1079 fills the column
            'date_created': ['exact', 'gt', 'lt', 'range'],
        }
