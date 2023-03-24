
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult

from notify.enums import ProcessNameEnum
from notify.managers import BackgroundProcessManager


class BackgroundProcess(models.Model):
    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process',
        blank=True)
    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the process was created in UTC'),
        null=True,
        blank=True)
    phase = models.CharField(
        max_length=512,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    process_type = models.CharField(
        max_length=32,
        choices=ProcessNameEnum.as_choices(drop_empty_choice=True),
        verbose_name=_('process type'),
        help_text=_('tells you what kind of process this is'))
    description = models.CharField(
        max_length=512,
        verbose_name=_('description'),
        help_text=_('Human readable description of what this process does')
    )
    related_resource_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True)
    related_id = models.UUIDField(
        null=True,
        blank=True
    )
    service = GenericForeignKey(
        ct_field='related_resource_type',
        fk_field='related_id')

    class Meta:
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')

    objects = BackgroundProcessManager()
