
from celery.states import FAILURE, PENDING, STARTED, SUCCESS
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count, Min, Q
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
            all_threads=Count('threads'),
            date_created=Min('threads__date_created'),
        ).order_by('-date_created')
        return qs


class BackgroundProcess(models.Model):
    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process')
    phase = models.CharField(
        max_length=256,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    process_type = models.CharField(
        max_length=32,
        choices=ProcessNameEnum.as_choices(drop_empty_choice=True),
        verbose_name=_('process type'),
        help_text=_('tells you what kind of process this is'))
    description = models.CharField(
        max_length=128,
        verbose_name=_('description'),
        help_text=_('Human readable description of what this process does')
    )
    related_resource_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.CASCADE,
        null=True)
    related_id = models.UUIDField(
        null=True
    )
    service = GenericForeignKey(
        ct_field='related_resource_type',
        fk_field='related_id')

    class Meta:
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')

    objects = BackgroundProcessManager()
