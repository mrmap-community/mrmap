import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import F, Func, Value
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
