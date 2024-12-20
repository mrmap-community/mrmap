import operator
from functools import reduce

from celery import states
from django.db import models
from django.db.models import Case, Count, F, Q, Value, When
from django.db.models.fields import CharField, FloatField
from django.db.models.functions import Round
from django.db.models.query import Prefetch
from django_celery_results.models import TaskResult

ready_condition = reduce(
    operator.or_, [Q(threads__status__exact=s) for s in states.READY_STATES])
unready_condition = reduce(
    operator.or_, [Q(threads__status__exact=s) for s in states.UNREADY_STATES])


class BackgroundProcessManager(models.Manager):

    def process_info(self):
        qs = self.get_queryset()
        qs = qs.annotate(
            unready_threads_count=Count(
                'threads', filter=unready_condition),
            ready_threads_count=Count(
                'threads', filter=ready_condition),
            all_threads_count=Count('threads'),
        ).annotate(
            status=Case(
                When(
                    Q(done_at__isnull=False),
                    then=Value("completed")),
                When(Q(
                    unready_threads_count__gt=0),
                    then=Value("running")),
                default=Value("pending"),
                output_field=CharField()
            ),
            progress=Case(
                When(
                    Q(done_at__isnull=False),
                    then=Value(100.0)),
                When(
                    Q(total_steps__isnull=True),
                    then=Value(0.0)  # noqa
                ),
                # 1.0 factor is needed to force cast the F field to a decimal number...
                default=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precission=2),  # noqa
                output_field=FloatField()
            )
        ).order_by('-date_created')
        qs = qs.prefetch_related(
            Prefetch(
                "threads",
                queryset=TaskResult.objects.filter(
                    reduce(operator.or_, [Q(status__exact=s) for s in states.UNREADY_STATES])),
                to_attr='running_threads_list'
            )
        )
        return qs
