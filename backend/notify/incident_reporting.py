"""The publishers which turn Celery retries and failures into incidents (#1320).

The incident of #1319 is the persisted, deduplicated record of a standing
problem; this module is its producer. It reports from the seams which already
exist and are authoritative - the ``task_retry`` signal and the
``BackgroundProcess`` write paths of #1207/#1208 - and never from a second
status engine: a retry of a task, the moment a task gives up and the moment a
process completes are already recorded here truthfully; the incident only
gives those moments a stable identity across repetitions, so that ten retries
of one operation are one active incident whose count moves, not ten
notifications (#1320).

The identity rules of this producer:

*   The code of an operation incident is ``{process_type}_{task}``. The code
    names the problem - this kind of work failing - and never an execution:
    a retry raises the standing incident's severity-`warning` occurrence
    count, the exhaustion of the retry budget moves the same code to
    severity ``error`` and stays the same incident (#1319's lifecycle), and
    the authoritative per-execution evidence stays where it always was, in
    the process log of #1208.
*   Recovery is what resolves: the success of the reported operation is the
    authoritative proof that the problem is over, and so is the completion
    of the process which reports that operation. A failing process (FAILED)
    deliberately resolves nothing - a run which failed did not recover
    anything - and an aborted one (ABORTED) resolves nothing either: #690
    ends a harvest whose tasks gave up through the abort path, which is an
    ending, not a recovery. A stale incident of an abandoned run is resolved
    by the next successful run of the same operation on the same resource.
*   A process whose work names no typed resource of the incident model, or
    whose process type has no incident source (registering), reports no
    incident: the api of #1319 cannot place it anywhere truthful, and the
    process keeps reporting as it did before this module existed.

Nothing in this module may ever break the work it reports about: every
receiver swallows its own failure into a log line, exactly as the retry
reporting of #1207 does, because an incident which cannot be written is
never a reason to fail a harvest.
"""
import re
from logging import Logger

from celery.exceptions import MaxRetriesExceededError
from celery.signals import task_retry, task_success
from django.conf import settings
from django.db.models import Q
from django.db.models.signals import post_save
from django.utils.timezone import now

from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, ProcessNameEnum,
                          ProcessStatusEnum)
from notify.models import BackgroundProcess

logger: Logger = settings.ROOT_LOGGER

#: the process types whose domain answers an incident source of #1319; a
#: process type which is not here (registering) publishes no incident,
#: because the incident api has no truthful kind to place it under
INCIDENT_PROCESS_SOURCES = {
    ProcessNameEnum.HARVESTING.value: IncidentSourceEnum.HARVESTING.value,
    ProcessNameEnum.UPDATE.value: IncidentSourceEnum.UPDATE.value,
    ProcessNameEnum.MONITORING.value: IncidentSourceEnum.MONITORING.value,
}

#: the code prefix which the verdicts of the watchdog of #1320 share; the
#: terminal resolver of a completing process resolves the operation family
#: and the watchdog verdicts of its resource together, and no other code
#: family may start with these prefixes
OPERATION_CODE_SEPARATOR = "_"
WATCHDOG_CODE_PREFIX = "operational_"

#: the longest code the incident model stores; a code built from a long
#: dotted task name is bounded by keeping the tail of the name, which is
#: the segment which names the task proper
INCIDENT_CODE_MAX_LENGTH = 64

# The credential shapes a failure reason may carry: the userinfo of a URL,
# the query parameters of a signed request and an echoed auth header. The
# sanitization of #1319 redacts by KEY and bounds by value; a reason text
# is one free-form value, and these scrubbing patterns are what keeps a
# signed URL or an `Authorization` header out of an incident's details
# before that bound is even reached (#1320).
_URL_USERINFO_RE = re.compile(
    r"(?i)(?P<scheme>\w[\w+.-]*://)(?P<user>[^\s:/?@]+):(?P<secret>[^\s/?@]+)@")
_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&][\w.-]*(?:token|key|password|passwd|secret|signature|sig|auth)"
    r"[\w.-]*)=[^&\s]*")
_AUTH_HEADER_RE = re.compile(
    r"(?i)\b(authorization|proxy-authorization|x-api-key|api_key|apikey)\b"
    r"(\s*[:=]\s*)(?:\s*\w+\s+)?[^\s,;\"']+")


def scrub_secret_text(text):
    """The credential-bounded form of a free-form failure text (#1320).

    A retry reason is celery's safe_repr of an exception and often names
    the URL which did not answer - which for an OGC request is a signed
    query or a URL with userinfo. Only the secrets go; the shape of the
    failure stays readable, since the readable shape is why the reason is
    reported at all.
    """
    if text is None:
        return ""
    text = str(text)
    text = _URL_USERINFO_RE.sub(
        lambda m: f"{m.group('scheme')}{m.group('user')}:***@", text)
    text = _QUERY_SECRET_RE.sub(r"\1=***", text)
    text = _AUTH_HEADER_RE.sub(r"\1\2***", text)
    return text


def incident_resource_field_by_model():
    """The incident resource field which names a kind of related model.

    A ``BackgroundProcess`` names its affected resource with the content
    type relation of #1208; the incident of #1319 names it with one typed
    foreign key. This is the only bridge between the two: a process whose
    related model is one of the incident's typed resources reports about
    it, and a process which names anything else (or nothing) names no
    resource to an incident.
    """
    from notify.models import OperationalIncident

    mapping = {}
    for field in OperationalIncident.RESOURCE_FIELDS:
        related = OperationalIncident._meta.get_field(
            field).related_model._meta
        mapping[(related.app_label, related.model_name)] = field
    return mapping


def source_and_resource(process):
    """The incident source and typed resource a process reports under.

    Answers ``(None, None)`` for a process which publishes no incident: a
    process type without an incident source (registering) or, when the
    process names a related model which the incident model cannot type,
    the empty resource which is a system-scoped incident (#1319).
    """
    source = INCIDENT_PROCESS_SOURCES.get(process.process_type)
    if source is None:
        return None, None
    content_type = process.related_resource_type
    resource = {}
    if content_type is not None and process.related_id is not None:
        field = incident_resource_field_by_model().get(
            (content_type.app_label, content_type.model))
        if field is not None:
            resource = {field: process.related_id}
    return source, resource


def task_code_tail(task_name):
    """The stable, bounded task part of an incident code.

    Celery task names are dotted module paths ("registry.tasks.harvest."
    "fetch_md_metadata"); the last two segments name the task properly
    within its module, and the module prefix is the same for every task of
    one kind of work anyway. A name with fewer segments is kept whole.
    """
    segments = [s for s in str(task_name).split(".") if s]
    return "_".join(segments[-2:]) if segments else "unknown"


def operation_code(process_type, task_name):
    """The incident code of one failing operation.

    Derived from the process type and the task alone, so every retry,
    every redelivery and the exhaustion of one task compute the same code,
    which is what lets ``report`` of #1319 deduplicate them into the one
    standing incident (#1320).
    """
    return f"{process_type}{OPERATION_CODE_SEPARATOR}{task_code_tail(task_name)}" \
        [:INCIDENT_CODE_MAX_LENGTH]


def _read_process(pk):
    """The process an incident is reported about, typed relation included.

    Answers None for a process which is gone; a report about a deleted
    process is meaningless, since the incident cascades with the resource
    anyway.
    """
    if pk is None:
        return None
    return BackgroundProcess.objects.select_related(
        "related_resource_type").filter(pk=pk).first()


def _retry_attempt(request, retries=None):
    """The attempt number a retry signal announces.

    ``retries`` is the number of retries already asked for at the moment
    the signal is dispatched, so the attempt whose scheduling is reported
    here is the one after it. The request carries the same counter when
    the dispatch names no separate one.
    """
    if retries is None:
        retries = getattr(request, "retries", 0) or 0
    try:
        return int(retries) + 1
    except (TypeError, ValueError):
        return 1


@task_retry.connect
def publish_task_retry(sender, request, reason, **kwargs):
    """Raise or update the incident of an operation which schedules a retry.

    A retry is not a new incident: the report of #1319 raises the standing
    incident's count and latest evidence, or creates the one incident when
    this is the first retry of a problem which stands nobody has reported
    yet. The next attempt's deadline travels with it as the bounded retry
    metadata of the incident, computed by the same helper #1207 uses, so
    the api can answer "retry 4/10, next attempt 14:37" from the incident
    alone.
    """
    pk = (getattr(request, "kwargs", None) or {}).get(
        "background_process_pk")
    if pk is None:
        # a task without a process is invisible to the operation reporting
        # of #1207 already; it stays invisible to the incidents
        return
    try:
        from notify.models import OperationalIncident
        from notify.tasks import retry_scheduled_at

        process = _read_process(pk)
        if process is None:
            return
        source, resource = source_and_resource(process)
        if source is None:
            return
        attempt = _retry_attempt(request, kwargs.get("retries"))
        until = retry_scheduled_at(sender, request, reason)
        code = operation_code(process.process_type, getattr(
            sender, "name", "task"))
        window = f"; the next attempt is due by {until.isoformat()}" \
            if until is not None else ""
        summary = (
            f"The {process.process_type} task "
            f"'{task_code_tail(getattr(sender, 'name', 'task'))}' failed "
            f"and scheduled its attempt {attempt}{window}.")
        OperationalIncident.objects.report(
            code=code,
            source=source,
            severity=IncidentSeverityEnum.WARNING.value,
            summary=summary,
            resource=resource,
            details={
                "task": getattr(sender, "name", ""),
                "attempt": attempt,
                "reason": scrub_secret_text(
                    getattr(reason, "excs", None)
                    or getattr(reason, "message", None) or reason),
            },
            retry_count=attempt,
            retry_scheduled_until=until)
    except Exception as e:
        # as with the state report of #1207: the retry itself does not
        # depend on its publication
        logger.warning(
            "can't publish the retry incident of the process %s: %s",
            pk, e)


def task_retries(task):
    """The retries-counter of a task, readable outside a run as well.

    ``Task.request`` is a property over the worker's context stack, and the
    lookup itself raises ``AttributeError`` outside a running task - which
    is how the tests of #1177 call ``on_failure`` directly. The counter is
    evidence for the incident's summary, never a reason to break the
    failure handling it is reported from (#1320).
    """
    return getattr(getattr(task, "request", None), "retries", None)


def publish_terminal_failure(process_pk, task_name, exc, retries=None):
    """Publish the terminal failure of an operation which gave up.

    The callers are the ``on_failure`` seams of the tasks - the one moment
    a task answers that it will never try again, be it the exhausted retry
    budget of #690/#1207 or a failure which was never retryable. The
    incident published here carries the code of the operation (so the
    standing warning of its retries becomes the error it decided to be, in
    one row), the severity of a decision (``error``) and the truth of
    *why* it is terminal in its bounded details. It is written after the
    task wrote the failed state of its process, so the incident and the
    persisted source state agree by construction (#1320's AC).
    """
    if process_pk is None:
        return
    try:
        from notify.models import OperationalIncident

        process = _read_process(process_pk)
        if process is None:
            return
        source, resource = source_and_resource(process)
        if source is None:
            return
        exhausted = isinstance(exc, MaxRetriesExceededError)
        code = operation_code(process.process_type, task_name)
        tail = task_code_tail(task_name)
        attempts = f" after {int(retries)} retries" \
            if exhausted and retries is not None else ""
        gave_up = "gave up" + (
            f"{attempts} when its retry budget was exhausted"
            if exhausted else " without a further attempt")
        summary = (
            f"The {process.process_type} task '{tail}' {gave_up}.")
        OperationalIncident.objects.report(
            code=code,
            source=source,
            severity=IncidentSeverityEnum.ERROR.value,
            summary=summary,
            resource=resource,
            details={
                "task": str(task_name),
                "attempts": retries,
                "exhausted": exhausted,
                "reason": scrub_secret_text(exc),
            })
    except Exception as e:
        logger.warning(
            "can't publish the terminal failure incident of the process "
            "%s: %s", process_pk, e)


@task_success.connect
def resolve_on_task_success(sender, **kwargs):
    """Resolve the operation's incident when the operation answers again.

    The success of the very task which reported the retry is the
    authoritative proof that its problem recovered; it resolves the
    incident under the key of exactly that operation and resource. The
    resolve of #1319 is idempotent, so the successful majority of tasks -
    which never reported a retry and have no incident standing - costs one
    conditional update which moves nothing.
    """
    pk = (kwargs.get("kwargs") or {}).get("background_process_pk")
    if pk is None:
        return
    try:
        from notify.models import OperationalIncident

        process = _read_process(pk)
        if process is None:
            return
        source, resource = source_and_resource(process)
        if source is None:
            return
        code = operation_code(
            process.process_type, getattr(sender, "name", "task"))
        key = OperationalIncident.objects.build_dedup_key(code, **resource)
        if OperationalIncident.objects.resolve(key):
            logger.info("resolved incident %s on the success of %s",
                        key, code)
    except Exception as e:
        logger.warning(
            "can't resolve the retry incident of the process %s: %s",
            pk, e)


def resolve_incidents_of_completed_process(instance):
    """Close the incidents of an operation whose process completed.

    The completion of a process is the authoritative success of the work
    it reports - the proof that whatever its tasks retried has come to a
    good end - so every standing incident of that process's resource from
    the operation family and from the watchdog family resolves with it
    (#1320). The write is the same conditional update as ``resolve`` of
    #1319, only scoped by the resource and the code families instead of
    one key: a completing process does not know the task names which
    raised, and a bulk resolution which moves nothing costs one statement.

    A FAILED process reaches this function and resolves nothing on
    purpose: nothing recovered, and the incident must stay to say so. An
    ABORTED one resolves nothing either: #690 aborts a harvest whose tasks
    gave up, which is a failure ending rather than a recovery, and the
    next successful run of the same operation is what proves recovery
    (see ``resolve_on_task_success``).
    """
    from notify.models import OperationalIncident

    if instance.status != ProcessStatusEnum.COMPLETED:
        return
    process_type = instance.process_type
    if INCIDENT_PROCESS_SOURCES.get(process_type) is None:
        return

    content_type = getattr(instance, "related_resource_type", None)
    resource_field = None
    if content_type is not None and instance.related_id is not None:
        resource_field = incident_resource_field_by_model().get(
            (content_type.app_label, content_type.model))
    if resource_field is None:
        # a process which names no typed resource shares its system-scoped
        # operation incidents with every other process of its kind, so its
        # completion proves nothing about which of them recovered; the
        # exact key of the operation which actually succeeded is what
        # resolves those (see `resolve_on_task_success`)
        return

    clause = (
        Q(code__startswith=f"{process_type}{OPERATION_CODE_SEPARATOR}")
        | Q(code__startswith=WATCHDOG_CODE_PREFIX)) \
        & Q(**{resource_field: instance.related_id})

    resolved = OperationalIncident.objects.filter(
        clause,
        status=IncidentStatusEnum.ACTIVE.value).update(
            status=IncidentStatusEnum.RESOLVED.value,
            resolved_at=now())
    if resolved:
        # the caller ran inside the completion write; the resolution is
        # part of the same decision and must not be lost to a broken log
        logger.info(
            "resolved %s incidents of the completed process %s",
            resolved, instance.pk)


def _on_process_post_save(sender, instance, created, **kwargs):
    """The post_save entry of the terminal resolver.

    Every write path of a process - the manager report of #1207, the task
    side of #1179 and the abort of a save - sends this signal with a
    freshly read instance, which is why one receiver covers all of them.
    An open process answers nothing here at all: one attribute check, no
    query, so the receivers costs the reporting fan-out nothing.
    """
    if created or getattr(instance, "done_at", None) is None:
        return
    try:
        resolve_incidents_of_completed_process(instance)
    except Exception as e:
        logger.warning(
            "can't resolve the incidents of the completed process %s: %s",
            getattr(instance, "pk", "?"), e)


def register_incident_reporting():
    """Wire the process-state receivers of this module.

    The celery signal handlers of #1207 connect on the import of
    ``notify.tasks``; the two receivers here need the same lifecycle and
    are connected by the app's ``ready`` through this function, so the
    module is importable without a configured app and wires nothing on
    import alone.
    """
    post_save.connect(
        _on_process_post_save,
        sender=BackgroundProcess,
        dispatch_uid="notify.incident_reporting.terminal_process")


def publish_watchdog_verdict(code, process, severity, summary, details):
    """Publish one watchdog verdict about a running process (#1320).

    The watchdog of #1320 decides independently of the work it watches;
    this is the one seam through which it reports, so the code families
    and the resource typing stay in the hands of this module and the
    watchdog itself only reads the broker and the processes.

    Returns:
        tuple: the incident and whether it was created
    """
    from notify.models import OperationalIncident

    source, resource = source_and_resource(process)
    if source is None:
        return None, False
    return OperationalIncident.objects.report(
        code=code,
        source=source,
        severity=severity,
        summary=summary,
        resource=resource,
        details=details)


def system_verdict(code, severity, summary, details):
    """Publish a verdict about the deployment itself (no resource).

    A missing queue consumer names no user's resource but the deployment,
    and by the one rule of #1319 that makes it a system incident, visible
    to the administrators alone - which is exactly where the epic wants
    the queue-without-consumer evidence.
    """
    from notify.models import OperationalIncident

    return OperationalIncident.objects.report(
        code=code,
        source=IncidentSourceEnum.SYSTEM.value,
        severity=severity,
        summary=summary,
        resource=None,
        details=details)
