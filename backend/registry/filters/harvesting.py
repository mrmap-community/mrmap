import operator
from functools import reduce

from celery import states
from django.db.models import Count, Q
from django.utils.translation import gettext_lazy as _
from django_filters import BaseInFilter, BooleanFilter, FilterSet, NumberFilter
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob, HarvestingLog

unready_condition = reduce(
    operator.or_, [Q(status__exact=s) for s in states.UNREADY_STATES])


class NumberInFilter(BaseInFilter, NumberFilter):
    pass


class HarvestingJobFilterSet(FilterSet):
    """The facets the harvesting job list answers.

    Every lookup a screen needs must be declared here: an undeclared
    ``filter[...]`` is answered with a 400 (code ``invalid``), never with the
    whole table, so a facet that is missing here is a screen that can not ask
    its question at all. Which filters exist is the set below; each lookup is
    pinned by a scenario in
    ``tests/behave/features/json:api/registry/harvesting/filter_harvestingjobs.feature``
    (#1080).
    """

    is_unready = BooleanFilter(
        method="filter_is_unready",
        help_text=_('Whether the job waits for its celery tasks, as the '
                    'worker queue answers it.'))

    is_running = BooleanFilter(
        method="filter_is_running",
        help_text=_('Whether the job was made and has not ended; the runs '
                    'that are pending, working or waiting for a decision.'))

    phase = NumberFilter(
        field_name='phase',
        help_text=_('Exact phase of the run: 0 pending, 1 total records '
                    'count, 2 downloading records, 3 records to database, '
                    '4 completed, 5 aborted.'))
    phase__in = NumberInFilter(
        field_name='phase', lookup_expr='in',
        help_text=_('Comma separated phases, for example the working runs '
                    'as phase=0,1,2,3.'))
    phase__lt = NumberFilter(
        field_name='phase', lookup_expr='lt',
        help_text=_('Runs in a phase before the given one.'))
    phase__gt = NumberFilter(
        field_name='phase', lookup_expr='gt',
        help_text=_('Runs in a phase after the given one.'))

    has_import_error = BooleanFilter(
        method="filter_has_import_error",
        help_text=_('Whether at least one temporary metadata file of the '
                    'run could not be imported.'))
    unhandled_records = BooleanFilter(
        method="filter_unhandled_records",
        help_text=_('Whether at least one temporary metadata file of the '
                    'run still awaits its decision.'))

    def filter_is_unready(self, queryset, name, value):
        f = Q(done_at__isnull=True) & ~Q(
            phase__lt=HarvestingPhaseEnum.COMPLETED.value)

        if not value:
            f = ~Q(f)
        return queryset.filter(f)

    def filter_is_running(self, queryset, name, value):
        if value is None:
            return queryset
        # a run was made and has not ended: the same question the progress
        # cards ask, phrased as a filter (#1080)
        f = Q(done_at__isnull=True)
        return queryset.filter(f if value else ~Q(f))

    def filter_has_import_error(self, queryset, name, value):
        if value is None:
            return queryset
        # the count is answered by the correlated subquery of the manager,
        # which uses the index over the job and its error flag instead of
        # reading every file of every job (#870, #886)
        qs = HarvestingJob.objects.with_temporary_file_counts(
            queryset,
            files_with_import_error=Count('id', filter=Q(has_import_error=True)))
        return qs.filter(files_with_import_error__gt=0) if value \
            else qs.filter(files_with_import_error=0)

    def filter_unhandled_records(self, queryset, name, value):
        if value is None:
            return queryset
        qs = HarvestingJob.objects.with_temporary_file_counts(
            queryset,
            files_with_unhandled_records=Count(
                'id', filter=Q(has_import_error=False)))
        return qs.filter(files_with_unhandled_records__gt=0) if value \
            else qs.filter(files_with_unhandled_records=0)

    class Meta:
        model = HarvestingJob
        fields = {
            # 'is_unready': ['exact'],
            'service__id': ['exact', 'contains', 'icontains', 'in'],
            'id': ['exact', 'contains', 'icontains', 'in'],
            'service__title': ['exact', 'icontains', 'contains'],
            'date_created': ['exact', 'gt', 'lt', 'range'],
            'done_at': ['exact', 'gt', 'lt', 'range'],
        }


class HarvestingLogFilterSet(FilterSet):
    """The facets the harvesting log list answers (see the rule above).

    The level lookups read the severity against its enum: FATAL is 0 and
    DEBUG is 4, so the warnings *and* errors an administrator wants are the
    lines below the info of an ordinary run, ``level__lte=2`` (#1080).
    """

    harvesting_job = NumberFilter(
        field_name='harvesting_job',
        help_text=_('Id of the harvesting run the line was written for.'))
    harvesting_job__in = NumberInFilter(
        field_name='harvesting_job', lookup_expr='in',
        help_text=_('Comma separated ids of harvesting runs.'))
    level = NumberFilter(
        field_name='level',
        help_text=_('Exact log level: 0 fatal, 1 error, 2 warning, 3 info, '
                    '4 debug.'))
    level__lte = NumberFilter(
        field_name='level', lookup_expr='lte',
        help_text=_('Lines of this level and worse; the levels count from '
                    'fatal, so 2 answers warnings and errors.'))
    level__gte = NumberFilter(
        field_name='level', lookup_expr='gte',
        help_text=_('Lines of this level and better.'))
    kind = NumberFilter(
        field_name='kind',
        help_text=_('Exact log kind: 0 remote error, 1 record count '
                    'mismatch.'))
    kind__in = NumberInFilter(
        field_name='kind', lookup_expr='in',
        help_text=_('Comma separated log kinds.'))

    class Meta:
        model = HarvestingLog
        fields = {
            'id': ['exact', 'in'],
            'timestamp': ['exact', 'gt', 'lt', 'range'],
        }
