import json
import uuid
from datetime import timedelta
from logging import Logger

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models import F, Func, Q, Value
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from MrMap.celery import app
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, LogTypeEnum, ProcessNameEnum,
                          ProcessStatusEnum)
from notify.managers import (BackgroundProcessManager,
                             OperationalIncidentManager)

logger: Logger = settings.ROOT_LOGGER


CREATED_DATETIME_VERBOSE_NAME = _('Created DateTime')


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
        verbose_name=CREATED_DATETIME_VERBOSE_NAME,
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

    # the stored summary of collecting the metadata references of a service
    # (#1259). A run which collected everything and a run in which every
    # reference failed both end COMPLETED - the epic's decision D9 keeps it
    # that way, because that is how harvesting shows a run with import errors
    # too - so these counters are what tells the two apart without reading the
    # free text of the process logs, which the retention of #1208 purges.
    # Like the reporting fields above they are written by the reporters only,
    # while the outcome of a reference is decided and when the run decides
    # about itself, never aggregated while a client reads it (#1037).
    #
    # Every counter is empty where the process never planned a collection: the
    # answers of a run which collected no references are none, not zeroes, and
    # a zero stays the honest answer of a planned collection which found
    # nothing.
    #
    # They sit on the process, not on the described service, because they
    # answer for one run: the same service can be registered again, #1274
    # collects during an update through this same path, and this is the only
    # row which outlives the run - the per-reference work rows of #1263 are
    # disposable and deleted on success. Like the retry fields above they
    # belong to the generic model, stay empty for the kinds which collect
    # nothing, and the job center answers them from the one process resource
    # without a per-kind join (#1207); #1263 prescribes this host and names.
    references_total = models.IntegerField(
        null=True,
        default=None,
        editable=False,
        verbose_name=_('references total'),
        help_text=_(
            'how many metadata references the collection of this process '
            'planned; empty where the process collected no references'))
    references_stored = models.IntegerField(
        null=True,
        default=None,
        editable=False,
        verbose_name=_('references stored'),
        help_text=_(
            'how many references of the collection produced a stored '
            'metadata record'))
    references_failed = models.IntegerField(
        null=True,
        default=None,
        editable=False,
        verbose_name=_('references failed'),
        help_text=_(
            'how many references of the collection could not be collected, '
            'including the documents which carry no identifiable record'))
    references_skipped = models.IntegerField(
        null=True,
        default=None,
        editable=False,
        verbose_name=_('references skipped'),
        help_text=_(
            'how many references the collection planned but never reported '
            'an outcome for'))
    # the one-time marker of a planned collection (#1263): the work rows of
    # the run exist and its expected count is stored. The plan is written and
    # sealed in a single transaction, and a sealed process is never
    # re-planned: a duplicate delivery of the registration root which finds
    # the marker set must not recreate work rows a successful worker already
    # deleted, nor reset the counters the workers moved. It also separates an
    # unplanned run (no marker, NULL counters) from a planned run which found
    # zero references (marker set, references_total = 0).
    references_plan_sealed = models.BooleanField(
        default=False,
        editable=False,
        verbose_name=_('references plan sealed'),
        help_text=_(
            'the collection of this process planned its references exactly '
            'once; a duplicate planning delivery never reopens it'))

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
        """The seconds from the creation of this process to its decision.

        This is the wall-clock span between the two timestamps the process
        stores itself: it answers how long the request waited for its
        decision, the waiting, retry and scheduling intervals of the related
        celery tasks included - tasks of one process are scheduled
        independently, not exactly one after another. It is NOT the time the
        work spent running: per-task running times are no longer persisted
        since the ``TaskResult`` mirror was retired (#1180), so no better
        answer is derivable from this model, and the api therefore labels it
        as the time until the process decided rather than a work duration.

        A process which did not decide about itself yet took no time to
        finish, and the answer of a process which names no creation moment
        would be a guess - both answer ``None``.
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
        for queues in filter(lambda q: q is not None, (i.active(), i.reserved(), i.scheduled())):
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

    def delete(self, *args, **kwargs):
        """Delete this process and take its registration work files with it.

        The temporary work rows of a registration (#1263) live and die with
        their collecting process: the database cascade takes the rows, but a
        cascade never touches the storage, and the failed downloads stored on
        them are exactly the bytes the issue refuses to leak. The file names
        are read before the rows are gone - after the delete nothing but the
        storage would know them - and physically removed once the delete
        committed: a file deletion is no rollback material, so it never runs
        while the database decision could still be undone. The permanent
        metadata records and their ``MetadataRelation`` couplings are not
        this process's to take and stay untouched.
        """
        from registry.models.harvest import (  # local import: app cycle
            registration_work_file_names)
        names = registration_work_file_names([self.pk])
        result = super().delete(*args, **kwargs)
        transaction.on_commit(lambda: _delete_registration_files(names))
        return result


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
        verbose_name=CREATED_DATETIME_VERBOSE_NAME,
        help_text=_('Datetime field when the task result was created in UTC')
    )
    extented_description = models.FileField(
        null=True,
        verbose_name=_("Extented Description"),
        help_text=_("this can be the response content for example"),
        upload_to=extented_description_file_path)


def _delete_registration_files(names):
    """Physically remove the stored documents of deleted registration work rows.

    Runs after the rows and the process are gone. Bounded and idempotent: a
    name the storage does not hold is already the state this removal wants,
    and a name the storage cannot give up yet is not lost - the bounded
    registration orphan sweep of #1263 re-reads the process prefix and takes
    what no row references anymore, which is how a failed removal gets
    retried. Bytes are never leaked silently: every failed removal is an
    ERROR the operator can act on.
    """
    if not names:
        return
    removed = 0
    failed = []
    storage = default_storage
    for name in names:
        try:
            storage.delete(name)
            removed += 1
        except FileNotFoundError:
            removed += 1  # already the state this sweep wants
        except OSError:
            failed.append(name)
    if failed:
        logger.error(
            "could not delete %s stored registration reference file(s) %s of "
            "a deleted background process; the registration orphan sweep "
            "retries them (#1263)", len(failed), failed[:20])
    else:
        logger.info(
            "deleted %s stored registration reference file(s) of a deleted "
            "background process (#1263)", removed)


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
    stored_files = list(
        BackgroundProcessLog.objects.filter(
            background_process_id__in=pks)
        .exclude(extented_description="")
        .exclude(extented_description=None)
        .values_list("extented_description", flat=True))
    # the retained registration work rows (#1263) cascade with the process
    # too; their stored documents are named here before the same cascade
    # takes their rows, so the loop below takes the bytes with them
    from registry.models.harvest import (  # local import: app cycle
        registration_work_file_names)
    stored_files += registration_work_file_names(pks)

    logs = BackgroundProcessLog.objects.filter(
        background_process_id__in=pks).delete()[1].get(
            "notify.BackgroundProcessLog", 0)
    purged = expired.delete()[1].get("notify.BackgroundProcess", 0)

    files = 0
    for name in stored_files:
        try:
            default_storage.delete(name)
            files += 1
        except OSError:
            pass  # the storage does not hold it - which is what this sweep wants

    return {"retention_days": days, "purged": purged, "logs": logs,
            "files": files}


#: the longest summary an incident row carries; the same bound the summary
#: of a background process keeps (#1208), so no incident answer grows with a
#: remote error document
INCIDENT_SUMMARY_MAX_LENGTH = 512

#: the serialized size of an incident's structured details - a bounded
#: payload, never a log tail or a response body (#1319)
INCIDENT_DETAILS_MAX_BYTES = 2048

#: how many keys the bounded payload keeps at most; the rest is reported as
#: truncated rather than silently dropped
INCIDENT_DETAILS_MAX_KEYS = 32

#: the longest string value inside the bounded payload
INCIDENT_DETAILS_VALUE_MAX_LENGTH = 256

#: the longest list inside the bounded payload and its item count
INCIDENT_DETAILS_MAX_LIST_ITEMS = 10

#: key names whose value never reaches an incident row: an incident summary
#: and its details are answered to every user who may view the affected
#: resource, so nothing which could carry a credential or an auth header is
#: ever stored (#1319)
SENSITIVE_DETAIL_KEY_PARTS = (
    "token", "password", "passwd", "secret", "authorization", "apikey",
    "api_key", "api-key", "bearer", "signature", "credential", "cookie",
)

#: what a redacted value answers instead of the credential it replaces
REDACTED_PLACEHOLDER = "[redacted]"


def incident_details_bytes(details):
    """The stored size of an incident's bounded payload.

    One answer for the writer which bounds the payload and the clean which
    refuses an over-grown one, so both read the same bytes.
    """
    return len(json.dumps(details, sort_keys=True, default=str).encode("utf-8"))


def _is_sensitive_detail_key(key):
    lowered = key.lower()
    return any(part in lowered for part in SENSITIVE_DETAIL_KEY_PARTS)


def _bounded_detail_value(value, depth=0):
    """The value an incident row may store: bounded, never the original."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:INCIDENT_DETAILS_VALUE_MAX_LENGTH]
    if isinstance(value, (list, tuple)):
        items = [_bounded_detail_value(item, depth + 1)
                 for item in value[:INCIDENT_DETAILS_MAX_LIST_ITEMS]]
        if len(value) > len(items):
            items.append(f"(+{len(value) - len(items)} more)")
        return items
    if isinstance(value, dict) and depth < 1:
        return {
            str(key)[:64]: (
                REDACTED_PLACEHOLDER if _is_sensitive_detail_key(str(key))
                else _bounded_detail_value(item, depth + 1))
            for key, item in value.items()
        }
    # a nested mapping below the depth, and everything exotic: its readable
    # shape, bounded - an incident names the kind of evidence, it is no
    # document store
    return str(value)[:INCIDENT_DETAILS_VALUE_MAX_LENGTH]


def sanitize_incident_details(details):
    """The redacted, bounded mapping which an incident row stores (#1319).

    The producers of incidents report what they saw while they saw it - the
    response of a remote catalogue, the error of a task. None of it may be
    stored as it came: a key which names a credential answers the
    redaction placeholder, strings and lists are bounded, and when the
    serialized payload still outgrows its budget the least keys of the
    sorted set are dropped and the payload says so itself. The structured
    evidence of the run itself stays where it is authoritative - the
    process log of #1208 and the probe artifacts of #682.
    """
    if details is None:
        return {}
    if not isinstance(details, dict):
        raise ValidationError(_(
            "The details of an incident must be a mapping of structured "
            "metadata."))
    bounded = {}
    for key, value in details.items():
        name = str(key)[:64]
        bounded[name] = (
            REDACTED_PLACEHOLDER if _is_sensitive_detail_key(name)
            else _bounded_detail_value(value))

    kept = {}
    dropped = 0
    considered = 0
    for name in sorted(bounded):
        if len(kept) >= INCIDENT_DETAILS_MAX_KEYS:
            dropped = len(bounded) - considered
            break
        # the budget is tested with the truncation marker already on, so the
        # stored payload never outgrows it - not even by the marker itself
        candidate = dict(kept)
        candidate[name] = bounded[name]
        candidate["truncated"] = True
        if incident_details_bytes(candidate) > INCIDENT_DETAILS_MAX_BYTES:
            dropped = len(bounded) - considered
            break
        del candidate["truncated"]
        kept = candidate
        considered += 1
    if dropped:
        kept["truncated"] = True
    return kept


def _at_most_one_resource_check(fields):
    """The Q which no two of the given fields may be filled at once.

    An incident names its affected resource with exactly one typed foreign
    key (#1319) - the epic refuses a generic content-type relation, so the
    database has to guard the combinations directly. Pairwise null clauses
    are what a CheckConstraint answers as a conditional expression.
    """
    fields = list(fields)
    check = Q()
    for index, first in enumerate(fields):
        for second in fields[index + 1:]:
            check &= (Q(**{f"{first}__isnull": True})
                      | Q(**{f"{second}__isnull": True}))
    return check


#: the typed resources an incident may name, each mapped to the path which
#: leads from it to the service whose view permission decides the visibility
#: of the incident ("" answers the resource which is a service itself). This
#: table is the single source for the dedup key, the database check, the
#: visibility rule and the service filter - a new kind of affected resource
#: enters here and everywhere follows.
INCIDENT_RESOURCE_FIELDS = {
    "web_map_service": "",
    "web_feature_service": "",
    "catalogue_service": "",
    "harvesting_job": "service",
    "web_map_service_update_job": "service",
    "web_feature_service_update_job": "service",
    "catalogue_service_update_job": "service",
    "web_map_service_monitoring_run": "setting__service",
    "web_feature_service_monitoring_run": "setting__service",
    "catalogue_service_monitoring_run": "setting__service",
}


class OperationalIncident(models.Model):
    """One operational incident, deduplicated across its recurrences (#1319).

    An incident is the persisted answer to "what is broken for whom, since
    when, how often" - the stable row which a notification center of #1321
    lists and which publishers of #1320 raise once and resolve once. It is
    never the status of a job: the ``BackgroundProcess``, the harvesting
    job, the update job, the monitoring run and the service alerts stay
    authoritative for what a run did; this row only keeps the incident
    state which those per-execution records cannot answer on their own: a
    stable identity across retries, the deduplicated lifecycle and the
    permission-filtered visibility. The per-execution history remains where
    it always was - the process rows and their logs (#1208), the probe
    artifacts (#682).

    Identity and lifecycle
        ``dedup_key`` is the stable key of the problem behind the row. While
        one row with the key is ACTIVE, a recurrence raises its
        ``occurrence_count`` and ``last_occurred_at`` instead of creating
        another row - ten retries of one incident are one incident, not ten
        notifications. ``resolve`` moves the single lifecycle transition
        ACTIVE -> RESOLVED; a resolution is terminal, and a problem which
        returns afterwards is a new incident sharing the key with its
        history. A partial unique index enforces at most one active row per
        key in the database, independent of any individual Celery retry.

    Affected resource
        Every resource the epic names as an affected kind - the services,
        the harvesting job, the concrete update jobs and the concrete
        monitoring runs - is one typed, nullable foreign key. At most one of
        them is ever filled, which a database check enforces. An incident
        with no resource is a system incident: it names the deployment
        itself and belongs to the administrators alone. ``GenericForeignKey``
        and ``ContentType`` are deliberately absent: an incident row can
        only ever name a real object, and deletion follows it.

    Deletion and retention
        The resource FKs cascade: a service, a job or a run which is gone
        takes the incidents which name it - an incident about a deleted
        resource asks for an action nobody can take anymore. The decided
        ones of the retention window are taken back by
        ``purge_expired_operational_incidents``; active incidents are never
        purged.

    Authorization
        There is exactly one rule, implemented once by
        ``OperationalIncidentManager.visible_for_user``: a superuser sees
        everything, an authenticated user sees the resource incidents whose
        affected service he may view, and nobody but a superuser ever sees
        a system incident. Anonymous clients read nothing at all. List,
        detail, every filter and every count run over the filtered
        queryset, so a total never tells about an incident which the caller
        may not see.
    """

    #: the typed resources an incident may name, each mapped to the path
    #: which leads from it to the service whose view permission decides the
    #: visibility of the incident; see INCIDENT_RESOURCE_FIELDS
    RESOURCE_FIELDS = INCIDENT_RESOURCE_FIELDS

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name=_('id'),
        help_text=_(
            'the stable identifier of the incident, referable by later '
            'integrations independently of its dedup key'))
    dedup_key = models.CharField(
        max_length=255,
        editable=False,
        verbose_name=_('dedup key'),
        help_text=_(
            'the stable key of the problem behind this incident; while an '
            'incident with the key is active, a recurrence of the same '
            'problem raises its count instead of creating another row'))
    code = models.CharField(
        max_length=64,
        verbose_name=_('code'),
        help_text=_(
            'the structured incident code, stable per meaning; publishers '
            'of the same problem report the same code and never a new one'))
    source = models.CharField(
        max_length=32,
        choices=IncidentSourceEnum.choices,
        verbose_name=_('source'),
        help_text=_(
            'which domain of the deployment raised the incident: '
            'harvesting, update, monitoring or the deployment itself'))
    severity = models.CharField(
        max_length=16,
        choices=IncidentSeverityEnum.choices,
        verbose_name=_('severity'),
        help_text=_(
            'how much attention the incident asks for; a retry is a '
            'warning, its exhaustion an error of the same code'))
    status = models.CharField(
        max_length=16,
        choices=IncidentStatusEnum.choices,
        default=IncidentStatusEnum.ACTIVE.value,
        editable=False,
        verbose_name=_('status'),
        help_text=_(
            'the lifecycle of the incident: active while the problem '
            'stands, resolved once recovery resolved it; a resolution is '
            'terminal'))
    first_occurred_at = models.DateTimeField(
        editable=False,
        verbose_name=_('first occurrence'),
        help_text=_(
            'the moment the incident was reported for the first time'))
    last_occurred_at = models.DateTimeField(
        editable=False,
        verbose_name=_('last occurrence'),
        help_text=_(
            'the moment the incident was reported for the last time; every '
            'recurrence moves it'))
    occurrence_count = models.PositiveIntegerField(
        default=1,
        editable=False,
        verbose_name=_('occurrence count'),
        help_text=_(
            'how often the problem behind the dedup key was reported while '
            'the incident was active'))
    summary = models.CharField(
        max_length=INCIDENT_SUMMARY_MAX_LENGTH,
        verbose_name=_('summary'),
        help_text=_(
            'the safe, human readable summary of the incident; it never '
            'carries a credential, a raw response or a stack trace'))
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_('details'),
        help_text=_(
            'redacted, bounded structured metadata of the incident; the '
            'full evidence stays in the log of the reported process'))
    retry_count = models.PositiveIntegerField(
        default=0,
        editable=False,
        verbose_name=_('retry count'),
        help_text=_(
            'how many retries the reporting operation told with its last '
            'report, or none where it knows none'))
    retry_scheduled_until = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_('retry scheduled until'),
        help_text=_(
            'until when the next attempt of the reported operation is due; '
            'while this window is open the incident reports a retry, not a '
            'failure'))
    resolved_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        verbose_name=_('resolved at'),
        help_text=_(
            'the moment recovery resolved the incident, empty while it is '
            'active'))
    date_created = models.DateTimeField(
        default=now,
        editable=False,
        verbose_name=CREATED_DATETIME_VERBOSE_NAME,
        help_text=_('Datetime field when the incident was created in UTC'))

    # the typed relations to the resources an incident may name - one table
    # per concrete kind, because the epic refuses a generic relation and
    # the update jobs and monitoring runs have no shared concrete parent.
    web_map_service = models.ForeignKey(
        to="registry.WebMapService",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    web_feature_service = models.ForeignKey(
        to="registry.WebFeatureService",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    catalogue_service = models.ForeignKey(
        to="registry.CatalogueService",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    harvesting_job = models.ForeignKey(
        to="registry.HarvestingJob",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    web_map_service_update_job = models.ForeignKey(
        to="registry.WebMapServiceUpdateJob",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    web_feature_service_update_job = models.ForeignKey(
        to="registry.WebFeatureServiceUpdateJob",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    catalogue_service_update_job = models.ForeignKey(
        to="registry.CatalogueServiceUpdateJob",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    web_map_service_monitoring_run = models.ForeignKey(
        to="registry.WebMapServiceMonitoringRun",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    web_feature_service_monitoring_run = models.ForeignKey(
        to="registry.WebFeatureServiceMonitoringRun",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')
    catalogue_service_monitoring_run = models.ForeignKey(
        to="registry.CatalogueServiceMonitoringRun",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='operational_incidents',
        related_query_name='operational_incident')

    objects = OperationalIncidentManager()

    class Meta:
        verbose_name = _('Operational Incident')
        verbose_name_plural = _('Operational Incidents')
        ordering = ["-last_occurred_at", "id"]
        indexes = [
            # the list of the notification center pages the active incidents
            # by their last report; the history asks the resolved ones by
            # their moment
            models.Index(
                fields=["status", "last_occurred_at"],
                name="opinc_status_last_idx"),
            models.Index(
                fields=["dedup_key"],
                name="opinc_dedup_idx"),
            # one active incident per problem, enforced by the database:
            # the history of a resolved key may keep its rows, but a
            # recurrence never finds an open slot twice. The partial unique
            # index is a UniqueConstraint over the active rows - ``Index``
            # carries no uniqueness
            models.UniqueConstraint(
                fields=["dedup_key"],
                condition=Q(status=IncidentStatusEnum.ACTIVE.value),
                name="opinc_active_dedup_uniq"),
            models.Index(
                fields=["resolved_at"],
                name="opinc_resolved_at_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=_at_most_one_resource_check(
                    INCIDENT_RESOURCE_FIELDS),
                name="%(app_label)s_%(class)s_at_most_one_resource"),
            models.CheckConstraint(
                condition=(
                    Q(status=IncidentStatusEnum.ACTIVE.value,
                      resolved_at__isnull=True)
                    | Q(status=IncidentStatusEnum.RESOLVED.value,
                        resolved_at__isnull=False)),
                name="%(app_label)s_%(class)s_resolved_moment_matches_status"),
        ]

    def __str__(self):
        return f"{self.code} {self.dedup_key}"

    @property
    def scope(self):
        """Whether the incident names a resource or the deployment itself.

        The answer is derived from the typed relations, so it can never
        disagree with them: an incident without an affected resource is a
        system incident.
        """
        for field in self.RESOURCE_FIELDS:
            if getattr(self, f"{field}_id") is not None:
                return "resource"
        return "system"

    def clean(self):
        super().clean()
        if self.details and (
                incident_details_bytes(self.details)
                > INCIDENT_DETAILS_MAX_BYTES):
            raise ValidationError(_(
                "The details of an incident exceed their bounded size and "
                "have to be sanitized before they are stored."))


def purge_expired_operational_incidents(retention_days=None) -> dict:
    """Takes back the resolved incidents whose retention has passed (#1319).

    An incident is the stable handle of a problem which stands; a resolved
    one has told what it had to tell, and the authoritative history of the
    reported operation stays in the job history of #1208. Only resolved
    incidents go, decided by ``resolved_at``; an active incident is never
    purged out from under its caller. A retention of 0 keeps every resolved
    incident until an operator removes it.

    Returns what was done, which is what the log line of the beat task says.
    """
    days = (settings.OPERATIONAL_INCIDENT_RETENTION_DAYS
            if retention_days is None else retention_days)
    if days <= 0:
        return {"retention_days": days, "purged": 0}

    cutoff = now() - timedelta(days=days)
    expired = OperationalIncident.objects.filter(
        status=IncidentStatusEnum.RESOLVED.value,
        resolved_at__lt=cutoff)
    purged = expired.delete()[1].get("notify.OperationalIncident", 0)
    return {"retention_days": days, "purged": purged}
