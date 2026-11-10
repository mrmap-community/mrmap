import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import F, Func, Q, Value
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from MrMap.celery import app
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.managers import BackgroundProcessManager


class AppendTaskIds(Func):
    """The ids a process already owns, extended by new ones, in one write.

    `array_cat` is postgres' concatenation of two arrays; the database-side
    expression keeps the append atomic, so a registration which stores its
    task id and a report of concurrently running work cannot overwrite each
    other. A bare `+` of the ORM is not one: postgres defines no `+` for
    arrays.
    """

    function = "ARRAY_CAT"
    output_field = ArrayField(models.UUIDField())


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

    # the ids registered here own the process's unfinished work which no
    # worker can report about yet (see `append_celery_task_ids`, #1179)
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

    def append_celery_task_ids(self, task_ids):
        """Register task ids as belonging to this process, durably.

        The caller hands over the id of a task it is about to publish, before
        the message goes out, so an abort of the process can revoke that task
        although no worker has read the message yet (#1179). A retried task
        keeps its id, which is why one registered root task stays findable
        through every retry of its publication.

        Only work which was published with this process as its own belongs
        here - the root tasks - never the fan out a task body publishes;
        that work carries the process in its kwargs and the worker
        inspection of `get_related_task_ids` answers it, so the array stays
        as small as the process has roots instead of growing with every
        child.

        The write is a database-side concatenation: a report of the work
        which runs concurrently cannot lose an id this publication just
        registered, and this registration cannot lose a reported step.

        Args:
            task_ids (list): ids of the tasks published for this process;
                strings and uuids alike, they are stored as uuids
        """
        ids = [uuid.UUID(str(task_id)) for task_id in task_ids]
        if not ids:
            return
        BackgroundProcess.objects.filter(pk=self.pk).update(
            celery_task_ids=AppendTaskIds(
                F("celery_task_ids"),
                Value(ids, output_field=ArrayField(models.UUIDField()))))
        self.celery_task_ids = list(self.celery_task_ids or []) + ids

    def get_related_task_ids(self):
        """All task ids which belong to this process and are not finished yet.

        Two maintained sources answer this: the ids registered before their
        publication (`append_celery_task_ids`), which cover a message no
        worker has picked up yet, and the worker inspection, which names the
        work a worker has already read - active, reserved and the scheduled
        retries - and is matched by the kwargs the task was published with.
        A revocation of an id whose task already ran to its end is a no-op
        in celery, so an id stays safe to revoke after its task completed.

        The `TaskResult` status lookup through the retired `threads` relation
        which this answered from before is gone: the source audit of #1179
        found no supported workflow populating that relation, and the
        cancellation must not depend on rows of a table which the deployment
        is about to leave behind.

        The worker reports the kwargs it received from the broker, and the
        broker transports the uuid as a string, so self.pk has to be stringified
        for the comparison to ever match.
        """
        task_ids = [str(task_id) for task_id in self.celery_task_ids or []]
        related_pk = str(self.pk)

        i = app.control.inspect()
        for queues in list(filter(lambda q: q is not None, (i.active(), i.reserved(), i.scheduled()))):
            for task_list in queues.values():
                for task in task_list:
                    if task.get("kwargs", {}).get("background_process_pk") == related_pk:
                        task_id = task.get("request", {}).get(
                            "id", None) or task.get("id", None)
                        task_ids.append(task_id)

        return list(set(task_ids))

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
    deletes rows and never touches the storage. The thread mirror of the
    process was retired with the async-process migration (#1180), so nothing
    but the process' own reports cascades here. A retention of 0
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
