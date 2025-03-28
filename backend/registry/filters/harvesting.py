import operator
from functools import reduce

from celery import states
from django.db.models import Exists, OuterRef, Q
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from django_filters import rest_framework as filters
from registry.models.harvest import HarvestingJob

unready_condition = reduce(
    operator.or_, [Q(status__exact=s) for s in states.UNREADY_STATES])


class HarvestingJobFilterSet(filters.FilterSet):

    is_unready = filters.BooleanFilter(
        method="filter_is_unready"
    )

    def filter_is_unready(self, queryset, name, value):
        f = Q(background_process__done_at__isnull=True) & ~Q(
            background_process__phase="abort")

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
