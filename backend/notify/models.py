from celery import states
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from MrMap.celery import app
from notify.enums import LogTypeEnum, ProcessNameEnum
from notify.managers import BackgroundProcessManager


class BackgroundProcess(models.Model):
    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process',
        blank=True)
    celery_task_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    date_created = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the process was created in UTC'),
        null=True,
        blank=True)
    done_at = models.DateTimeField(
        verbose_name=_('Completed DateTime'),
        help_text=_('Datetime field when the process was completed in UTC'),
        null=True,
        blank=True)
    phase = models.CharField(
        max_length=512,
        verbose_name=_('phase'),
        help_text=_('Current phase of the process'))
    total_steps = models.IntegerField(
        verbose_name=_('total'),
        help_text=_('total steps of processing'),
        null=True,
        default=None)
    done_steps = models.IntegerField(
        verbose_name=_('done'),
        help_text=_('done steps of processing'),
        default=0)
    process_type = models.CharField(
        max_length=32,
        choices=ProcessNameEnum.choices,
        verbose_name=_('process type'),
        help_text=_('tells you what kind of process this is'))
    description = models.CharField(
        max_length=512,
        verbose_name=_('description'),
        help_text=_('Human readable description of what this process does'))
    related_resource_type = models.ForeignKey(
        to=ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True)
    related_id = models.UUIDField(
        null=True,
        blank=True)
    service = GenericForeignKey(
        ct_field='related_resource_type',
        fk_field='related_id')

    class Meta:
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')

    objects = BackgroundProcessManager()

    def __str__(self):
        return f"{self.process_type} {self.related_id}"

    def get_related_task_ids(self):
        task_ids = []

        i = app.control.inspect()
        for queues in list(filter(lambda q: q is not None, (i.active(), i.reserved(), i.scheduled()))):
            for task_list in queues.values():
                for task in task_list:
                    if ("background_process_pk", self.pk) in task.get("kwargs", {}).items():
                        task_id = task.get("request", {}).get(
                            "id", None) or task.get("id", None)
                        task_ids.append(task_id)

        unready_tasks = self.threads.filter(
            status__in=states.UNREADY_STATES).values_list("task_id", flat=True)

        return list(set(list(unready_tasks) + task_ids + self.celery_task_ids))

    def save(self, *args, **kwargs):
        if self.phase == "abort":
            self.done_at = now()

            related_tasks = self.get_related_task_ids()
            if related_tasks:
                app.control.revoke(related_tasks, terminate=True)

                return super(BackgroundProcess, self).save(*args, **kwargs)

        return super(BackgroundProcess, self).save(*args, **kwargs)


def extented_description_file_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/xml_documents/<job_id>/<filename>
    return f'BackgroundProcessLog/{instance.background_process_id}/{filename}'


class BackgroundProcessLog(models.Model):
    background_process = models.ForeignKey(
        to=BackgroundProcess,
        on_delete=models.CASCADE,
        related_name='logs',
        related_query_name='log'
    )
    log_type = models.CharField(
        choices=LogTypeEnum.choices,
        max_length=10
    )
    description = models.TextField(
        blank=True,
        default="",
        verbose_name=_('Description'),
    )
    date = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the task result was created in UTC')
    )
    extented_description = models.FileField(
        null=True,
        verbose_name=_("Extented Description"),
        help_text=_("this can be the response content for example"),
        upload_to=extented_description_file_path)
