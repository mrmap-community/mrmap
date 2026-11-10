from celery import states
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from MrMap.celery import app
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.managers import BackgroundProcessManager


class BackgroundProcess(models.Model):
    status = models.PositiveSmallIntegerField(
        choices=ProcessStatusEnum.choices,
        default=ProcessStatusEnum.PENDING,
        editable=False)

    threads = models.ManyToManyField(
        to=TaskResult,
        related_name='processes',
        related_query_name='process',
        blank=True)
    celery_task_ids = ArrayField(models.UUIDField(), default=list, blank=True)
    date_created = models.DateTimeField(
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
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

    # the normalized operation reporting of #1207: what a client of the
    # background job center needs to follow one logical operation from the
    # moment it was made until it decided about itself. All of it is written
    # by the reporters through BackgroundProcessManager, never by a client,
    # so every field below is not editable.
    revision = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name=_('revision'),
        help_text=_(
            'counter of the state reports of this process; every message '
            'about the process carries the revision it reported, so a client '
            'which receives an older one out of order can drop it'))
    action_required = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_('action required'),
        help_text=_(
            'a reporter decided that this process stands until a human '
            'acts; it is set by the watchdog of a stalled import and by an '
            'update which waits for its review and cleared when the work '
            'goes on'))
    retry_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name=_('retry count'),
        help_text=_(
            'how many retries of its tasks the process has reported since '
            'it was created'))
    retry_reason = models.CharField(
        max_length=512,
        blank=True,
        default='',
        editable=False,
        verbose_name=_('retry reason'),
        help_text=_(
            'what the last reported retry of a task of this process '
            'failed on'))
    retry_scheduled_until = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_('retry scheduled until'),
        help_text=_(
            'until when the next attempt of the retried task is due; while '
            'this window is open the process reports itself as retrying'))

    class Meta:
        verbose_name = _('Background Process')
        verbose_name_plural = _('Background Processes')
        indexes = [
            # process_info() orders by -date_created and every list request of
            # the frontend (including its polling) runs that ordering; without
            # this the whole table is sorted on each request
            models.Index(
                fields=["date_created"],
                name="bgproc_date_created_idx"),
        ]

    objects = BackgroundProcessManager()

    def __str__(self):
        return f"{self.process_type} {self.related_id}"

    def get_related_task_ids(self):
        """All task ids which belong to this process and are not finished yet.

        The worker reports the kwargs it received from the broker, and the
        broker transports the uuid as a string, so self.pk has to be stringified
        for the comparison to ever match.
        """
        task_ids = []
        related_pk = str(self.pk)

        i = app.control.inspect()
        for queues in list(filter(lambda q: q is not None, (i.active(), i.reserved(), i.scheduled()))):
            for task_list in queues.values():
                for task in task_list:
                    if task.get("kwargs", {}).get("background_process_pk") == related_pk:
                        task_id = task.get("request", {}).get(
                            "id", None) or task.get("id", None)
                        task_ids.append(task_id)

        unready_tasks = self.threads.filter(
            status__in=states.UNREADY_STATES).values_list("task_id", flat=True)

        return list(set(list(unready_tasks) + task_ids + self.celery_task_ids))

    def save(self, *args, **kwargs):
        aborted = self.phase == "abort"
        if aborted:
            self.done_at = now()
            self.status = ProcessStatusEnum.ABORTED
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"status", "done_at"}

        # every write of an existing process is a new report of its state, and
        # the revision which orders the reports is counted by the database so
        # that concurrent writers cannot read each other's write away (#1207)
        bump = not self._state.adding
        if bump:
            self.revision = F("revision") + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"revision"}

        saved = super(BackgroundProcess, self).save(*args, **kwargs)

        if bump:
            # the database computed the expression; the listeners and the
            # response of an abort have to read the number, not the formula
            self.refresh_from_db(fields=["revision"])

        if aborted:
            # finding the tasks costs one blocking broadcast round trip per
            # inspector call; run it after the abort is stored, so a slow or
            # unreachable broker cannot keep the process looking alive
            related_tasks = self.get_related_task_ids()
            if related_tasks:
                app.control.revoke(related_tasks, terminate=True)

        return saved


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
        # Do not use this setting.
        # From django docs: Automatically set the field to now when the object is first created.
        # Useful for creation of timestamps. Note that the current date is always used;
        # it’s not just a default value that you can override.
        # So even if you set a value for this field when creating the object, it will be ignored.
        # If you want to be able to modify this field, set the following instead of auto_now_add=True:
        # auto_now_add=True,
        default=now,
        verbose_name=_('Created DateTime'),
        help_text=_('Datetime field when the task result was created in UTC')
    )
    extented_description = models.FileField(
        null=True,
        verbose_name=_("Extented Description"),
        help_text=_("this can be the response content for example"),
        upload_to=extented_description_file_path)
