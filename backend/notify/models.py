
from celery.states import FAILURE, PENDING, STARTED, SUCCESS
from django.db import models
from django.db.models import (BooleanField, Case, Count, DateTimeField,
                              ExpressionWrapper, F, Min, OuterRef, Q, Subquery,
                              Value, When)
from django.db.models.functions import Coalesce
from django.db.models.lookups import GreaterThan, LessThanOrEqual
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from MrMap.enums import EnumChoice


class ProcessNameEnum(EnumChoice):
    HARVESTING = 'harvesting'
    MONITORING = 'monitoring'
    REGISTERING = 'registering'


class BackgroundProcessManager(models.Manager):

    def process_info(self):
        qs = self.get_queryset()
        qs = qs.annotate(
            pending_threads=Count(
                'threads', filter=Q(threads__status=PENDING)),
            running_threads=Count(
                'threads', filter=Q(threads__status=STARTED)),
            successed_threads=Count(
                'threads', filter=Q(threads__status=SUCCESS)),
            failed_threads=Count('threads', filter=Q(threads__status=FAILURE)),
            date_created=Min('threads__date_created')
        ).order_by('-date_created')
        return qs


class BackgroundProcess(models.Model):
    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process')
    progress = models.FloatField(
        default=0.0,
        verbose_name=_('progress'),
        help_text=_('the current progress of the process as per'))
    phase = models.CharField(
        max_length=256,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    name = models.CharField(
        max_length=32,
        choices=ProcessNameEnum.as_choices(drop_empty_choice=True),
        verbose_name=_('name'),
        help_text=_('Human readable short name of this process'))
    description = models.CharField(
        max_length=128,
        verbose_name=_('description'),
        help_text=_('Human readable description of what this process does')
    )

    class Meta:
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')

    objects = BackgroundProcessManager()
