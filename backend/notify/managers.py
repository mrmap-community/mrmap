
from celery.states import FAILURE, PENDING, STARTED, SUCCESS
from django.db import models
from django.db.models import Case, Count, Q, Value, When
from django.db.models.fields import CharField
from django.db.models.query import Prefetch
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult


class BackgroundProcessManager(models.Manager):

    def process_info(self):
        qs = self.get_queryset()
        qs = qs.annotate(
            pending_threads_count=Count(
                'threads', filter=Q(threads__status=PENDING)),
            running_threads_count=Count(
                'threads', filter=Q(threads__status=STARTED)),
            successed_threads_count=Count(
                'threads', filter=Q(threads__status=SUCCESS)),
            failed_threads_count=Count(
                'threads', filter=Q(threads__status=FAILURE)),
            all_threads_count=Count('threads'),
        ).annotate(
            status=Case(
                When(Q(
                    pending_threads_count__gt=0,
                    running_threads_count__lte=0),
                    then=Value("pending")),
                When(Q(
                    pending_threads_count__lte=0,
                    running_threads_count__gt=0),
                    then=Value("running")),
                When(Q(
                    pending_threads_count__lte=0,
                    failed_threads_count__gt=0,
                    successed_threads_count__lte=0),
                    then=Value("failed")),
                When(Q(
                    pending_threads_count__lte=0,
                    running_threads_count__lte=0,
                    successed_threads_count__gt=0),
                    then=Value("successed")),
                default=Value("unknown"),
                output_field=CharField()
            )
        ).order_by('-date_created')
        qs = qs.prefetch_related(
            Prefetch(
                "threads",
                queryset=TaskResult.objects.filter(status=STARTED),
                to_attr='running_threads_list'
            )
        )
        return qs
