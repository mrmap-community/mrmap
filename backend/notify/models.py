from datetime import timedelta

from celery import states
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django_celery_results.models import TaskResult
from MrMap.celery import app
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.managers import BackgroundProcessManager


class BackgroundProcess(models.Model):
    """The durable report of one background operation (#1208).

    A process outlives the moment it was created: it is how the job history
    of the frontend answers what the deployment did, what failed and how long
    it took, after the snackbar which announced it is gone. Rows of decided
    processes are taken back by ``purge_expired_background_processes`` after
    the retention of the deployment; processes which did not end yet are
    never of that kind.
    """

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

    @property
    def duration(self):
        """The seconds this process took from its creation to its decision.

        Answered from the two timestamps the process stores itself, so it also
        answers for an instance which was not read through ``process_info()`` -
        a websocket payload or the answer of a registration. A process which
        did not decide about itself yet took no time to finish, and the answer
        of a process which names no creation moment would be a guess.
        """
        if self.done_at is None or self.date_created is None:
            return None
        return (self.done_at - self.date_created).total_seconds()

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

        saved = super(BackgroundProcess, self).save(*args, **kwargs)

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


def purge_expired_background_processes(retention_days=None) -> dict:
    """Takes back the background processes whose retention has passed (#1208).

    The rows a decided process leaves are the job history itself: services,
    catalogues and monitoring settings delete their own records, but nothing
    but this sweep takes the reports of the work done on them back, so the
    history would grow with every operation of the deployment. Only processes
    which decided about themselves go: ``done_at`` is the moment of that
    decision, and a terminal process which names none falls back onto the
    moment it was created. A process which did not end yet is never of that
    kind - the history is bounded, a running job is not deleted out of it.

    The log entries of a process go with it by cascade. The files their
    ``extented_description`` names are taken back here, because the cascade
    deletes rows and never touches the storage. The ``TaskResult`` rows the
    process was published with stay: they belong to the api which published
    them (#1176), not to the history which reports them. A retention of 0
    keeps every process until an operator removes it.

    Returns what was done, which is what the log line and the beat result say.
    """
    days = (settings.BACKGROUND_PROCESS_RETENTION_DAYS
            if retention_days is None else retention_days)
    if days <= 0:
        return {"retention_days": days, "purged": 0, "logs": 0, "files": 0}

    cutoff = now() - timedelta(days=days)
    expired = BackgroundProcess.objects.filter(
        Q(done_at__lt=cutoff)
        | Q(done_at__isnull=True,
            status__in=BackgroundProcessManager.TERMINAL_STATUS,
            date_created__lt=cutoff))
    pks = list(expired.values_list("pk", flat=True))
    if not pks:
        return {"retention_days": days, "purged": 0, "logs": 0, "files": 0}

    # the names before the rows: after the cascade there is nothing left
    # pointing at the stored files anymore
    stored_files = [
        name for name in BackgroundProcessLog.objects.filter(
            background_process_id__in=pks)
        .exclude(extented_description="")
        .exclude(extented_description=None)
        .values_list("extented_description", flat=True)]

    logs = BackgroundProcessLog.objects.filter(
        background_process_id__in=pks).delete()[1].get(
            "notify.BackgroundProcessLog", 0)
    purged = expired.delete()[1].get("notify.BackgroundProcess", 0)

    files = 0
    for name in stored_files:
        try:
            default_storage.delete(name)
            files += 1
        except (FileNotFoundError, OSError):
            pass  # the storage does not hold it - which is what this sweep wants

    return {"retention_days": days, "purged": purged, "logs": logs,
            "files": files}
