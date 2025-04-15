import operator
from functools import reduce

from celery import states
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
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
        }
