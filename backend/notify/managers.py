from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, models, transaction
from django.db.models import (Case, F, OuterRef, Q, Subquery, TextField,
                              Value, When)
from django.db.models.fields import FloatField, IntegerField
from django.db.models.functions import (Coalesce, Greatest, Least, Now, Round)
from django.db.models.signals import post_save
from django.utils.timezone import now
from guardian.shortcuts import get_objects_for_user
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, LogTypeEnum,
                          OperationStateEnum, ProcessStatusEnum)


def capped_done_steps(steps):
    """Expression which adds ``steps`` to the done steps of a process, capped.

    GREATEST keeps a report which would count past the total from pulling a
    further reported progress back, and Coalesce answers the NULL which Least
    leaves behind when there is no total to cap at - a process which does not
    know its total cannot exceed it. Shared by this manager's ``report`` and
    the task-side update path of ``notify/tasks.py``, so no step reporter can
    push a process beyond 100 % (#1261, #1258). A ceiling is not exactly-once
    accounting: duplicate reports of one logical step are still counted, they
    merely stop at the total; the per-reference identity which makes
    accounting exact belongs to the reference-level outcomes of #1263.
    """
    return Coalesce(
        Greatest(
            F("done_steps"),
            Least(F("done_steps") + steps, F("total_steps"))),
        F("done_steps") + steps)


class BackgroundProcessManager(models.Manager):

    #: statuses a process can still be moved away from
    ACTIVE_STATUS = [ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING]
    #: statuses a process decides about itself with
    TERMINAL_STATUS = [
        ProcessStatusEnum.COMPLETED,
        ProcessStatusEnum.FAILED,
        ProcessStatusEnum.ABORTED,
    ]

    def process_info(self):
        # imported here, because the log lives next to the process which is
        # annotated by this queryset and the models module imports this manager
        from notify.models import BackgroundProcessLog
        # the summary of what went wrong is the last error the operation told,
        # answered by one subquery instead of one query per rendered process
        error_summary = Subquery(
            BackgroundProcessLog.objects.filter(
                background_process_id=OuterRef("pk"),
                log_type=LogTypeEnum.ERROR,
            ).order_by("-date", "-id").values("description")[:1],
            output_field=TextField(),
        )
        # the normalized state of the operation (#1207): derived from the
        # stored fields, so every report which moves them moves the state with
        # it and no reporter maintains a second truth. The order of the cases
        # is the meaning: an operation which decided about itself is never
        # rendered as waiting, and only a running one can need attention, wait
        # for a retry or not know its steps. The python mirror is
        # OperationStateEnum.derive.
        state = Case(
            When(
                status=ProcessStatusEnum.COMPLETED,
                then=Value(OperationStateEnum.COMPLETED.value)),
            When(
                status=ProcessStatusEnum.FAILED,
                then=Value(OperationStateEnum.FAILED.value)),
            When(
                status=ProcessStatusEnum.ABORTED,
                then=Value(OperationStateEnum.ABORTED.value)),
            When(
                status=ProcessStatusEnum.PENDING,
                then=Value(OperationStateEnum.QUEUED.value)),
            When(
                action_required=True,
                then=Value(OperationStateEnum.ACTION_REQUIRED.value)),
            When(
                Q(retry_scheduled_until__gt=Now()),
                then=Value(OperationStateEnum.RETRYING.value)),
            When(
                Q(total_steps__isnull=True) | Q(total_steps__lte=0),
                then=Value(OperationStateEnum.RUNNING_INDETERMINATE.value)),
            default=Value(OperationStateEnum.RUNNING.value),
            output_field=TextField(),
        )
        # related_resource_type is rendered as a JSON:API relationship, so it is
        # always needed; without this the list endpoint and every websocket
        # payload triggers one ContentType query per BackgroundProcess.
        qs = self.get_queryset().select_related("related_resource_type")
        qs = qs.annotate(
            progress=Case(
                When(
                    Q(status=ProcessStatusEnum.COMPLETED),
                    then=Value(100.0)),
                When(
                    Q(total_steps__isnull=True),
                    then=Value(0.0)  # noqa
                ),
                # 1.0 factor is needed to force cast the F field to a decimal number...
                default=Case(
                    When(
                        total_steps__gt=0,
                        then=Round(F("done_steps") * 1.0 / F("total_steps") * 100.0, precision=2),  # noqa

                    ),
                    default=0.0
                ),
                output_field=FloatField()
            ),
            error_summary=error_summary,
            state=state,
        ).order_by('-date_created')
        return qs

    def report(self, pk, status, phase=None, total_steps=None, step_done=False,
               steps_done=0):
        """Mirror the state of a job in the background process which reports it.

        A background process is only a report about work which happens
        elsewhere, so the process of a job which is not finished yet is written
        by the model of that job. A process which decided about itself is not
        touched: the abort of an administrator must not be overwritten by the
        work which is still in flight.

        Args:
            pk: primary key of the process or None when it has none
            status (ProcessStatusEnum): the status to report
            phase (str): current phase of the process, optional
            total_steps (int): amount of steps the process is made of, optional
            step_done (bool): whether a step of the process was done, optional
            steps_done (int): amount of steps which were done since the last
                report, for the reporter which coalesces its work into one
                bulk increment instead of writing one row update per step (#958)

        The done steps are moved with the shared capped increment
        `capped_done_steps`, so a reporter which counts too eagerly inflates
        a process towards its end and never past its total.

        A process which reports itself COMPLETED is written as done: the
        completion of the work is the proof that its steps are over, and the
        overview of the background activity renders exactly these numbers.
        A COMPLETED report also closes the stored summary of a metadata
        collection with the references which never answered an outcome
        (#1259), whoever completes the process - the run's own task or the job
        of an update which collects as its last step (#1274).

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0

        values = {"status": status}
        if status == ProcessStatusEnum.RUNNING:
            # a report of a task which works ends the window of a reported
            # retry: the operation works again, whatever one of its tasks
            # was retrying (#1207)
            values["retry_scheduled_until"] = None
        if phase is not None:
            values["phase"] = str(phase)[:512]
        if total_steps is not None:
            values["total_steps"] = total_steps
        steps = (1 if step_done else 0) + max(int(steps_done or 0), 0)
        if steps:
            values["done_steps"] = capped_done_steps(steps)
        if status == ProcessStatusEnum.COMPLETED:
            values["done_steps"] = Coalesce(
                F("total_steps"), F("done_steps"))
            # a run which planned a metadata collection closes its summary with
            # the references it never heard an answer from (#1259). The task
            # side of a registration writes the same answer; this is the answer
            # for whoever completes the process through a report - the job of an
            # update whose run collected its metadata as its last step (#1274).
            # A process which planned no collection answers NULL, as it did
            # before this write existed.
            values["references_skipped"] = Case(
                When(
                    references_total__isnull=True,
                    then=Value(None, output_field=IntegerField())),
                default=Greatest(
                    F("references_total")
                    - Coalesce(F("references_stored"), 0)
                    - Coalesce(F("references_failed"), 0),
                    0),
                output_field=IntegerField(),
            )
        if status in self.TERMINAL_STATUS:
            values["done_at"] = now()

        return self._apply(pk, values)

    def raise_steps(self, pk, done_steps):
        """Move the reported steps of a process up to the durable state of its
        work, never down.

        This is the reconciliation of a reporter whose own increments were lost
        - by a worker which died with counts it had not reported yet, or by a
        backlog which is published anew after a restart (#958). The caller
        derives `done_steps` from durable bookkeeping; this method only lets
        that answer raise the progress, so a reconciliation racing with a
        worker's own report cannot lower what both of them have seen.

        Args:
            pk: primary key of the process or None when it has none
            done_steps (int): the steps which provably are done by now

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0
        return self._apply(pk, {"done_steps": Greatest(
            Coalesce(F("done_steps"), 0), max(int(done_steps), 0))})

    def record_reference_outcome(self, pk, stored_delta=0, failed_delta=0,
                                 step_done=False):
        """Transition the per-reference outcome counters of a collection exactly once.

        The outcome of one registration reference (#1263) moves the stored
        summary of its process: a first decision counts the reference once,
        and an authorized retry which turns a failed reference into a stored
        one shifts the last-outcome counters - ``done_steps`` and
        ``references_total`` stay where the sealed plan put them.

        The write is one conditional UPDATE with database-side expressions,
        so it is safe under concurrent reporters and never a Python
        read-modify-write. Two process shapes accept it, and the caller must
        hold the process lock while choosing between them:

        * an ACTIVE process takes the counters and, for a first decision,
          the capped ``done_steps`` mirror of the decided count;
        * an existing terminal COMPLETED process takes the narrow retry
          transition of #1265: the counters and the revision move, while the
          status, ``done_at`` and every other completed field stay exactly
          as they were - a retry does not reopen its parent run (D3), and
          ``update_background_process(step_done=True)`` is not used for it.

        A FAILED or ABORTED process is never silently reopened and nothing
        is written for it. The listeners learn the new state over the
        revision-bumped payload like every other report.

        Args:
            pk: primary key of the process
            stored_delta (int): +/-1 on the stored counter
            failed_delta (int): +/-1 on the failed counter
            step_done (bool): whether this outcome decides a reference for
                the first time and mirrors into ``done_steps``

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0
        values = {}
        if stored_delta:
            values["references_stored"] = Greatest(
                Coalesce(F("references_stored"), 0) + stored_delta, 0)
        if failed_delta:
            values["references_failed"] = Greatest(
                Coalesce(F("references_failed"), 0) + failed_delta, 0)
        if step_done:
            values["done_steps"] = capped_done_steps(1)
        if not values:
            return 0

        updated = self.get_queryset().filter(
            pk=pk,
            done_at__isnull=True,
            status__in=self.ACTIVE_STATUS,
        ).update(revision=F("revision") + 1, **values)
        if not updated:
            # the narrow path of D3: a COMPLETED run whose retried reference
            # decided differently - counters and revision only, never the
            # decision fields of the run itself
            completed_values = {
                key: value for key, value in values.items()
                if key != "done_steps"}
            if not completed_values:
                # a first-decision report of a reference that a COMPLETED run
                # never had is not this method's contract; the completion of
                # a run waits for all its rows decided, so nothing legit
                # reaches here and nothing is guessed
                return 0
            updated = self.get_queryset().filter(
                pk=pk,
                status=ProcessStatusEnum.COMPLETED,
            ).update(revision=F("revision") + 1, **completed_values)

        if updated:
            try:
                post_save.send(
                    self.model,
                    instance=self.process_info().get(pk=pk),
                    created=False)
            except self.model.DoesNotExist:
                pass
        return updated

    def report_retry(self, pk, reason, until=None):
        """Mirror one reported retry of a task onto its process (#1207).

        A retry is not a failure: the operation keeps its status and its
        steps, and the report only answers what the retry adds to the story
        - that a task gave up once more on something, and until when its next
        attempt is due. While that window is open the process reports itself
        as retrying; the window closing is not a write, it is simply a state
        which no longer holds when the next look reads it. A process which
        decided about itself is not moved, like every other report.

        Args:
            pk: primary key of the process or None when it has none
            reason: what the retried task failed on, stored truncated
            until: the moment the next attempt is due, or None when the
                reporter could not answer one

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0
        return self._apply(pk, {
            "retry_count": F("retry_count") + 1,
            "retry_reason": str(reason)[:512],
            "retry_scheduled_until": until,
        })

    def set_action_required(self, pk, flag=True, phase=None):
        """Tell a process that its work stands until a human acts (#1207).

        The epic of the background job center distinguishes an operation
        which works from one which waits for somebody to decide: a harvest
        whose import backlog the watchdog found untouched on the broker
        (#1038) and an update whose mapping must be reviewed. Their verdicts
        live on the reporting job, and the flag here is what makes the state
        of the process answer it too.

        Only a flip is written: setting the flag on a process which already
        carries it would broadcast a message which says nothing new, and a
        reporter which re-reports its stall per beat would flood the listeners
        with it. A process which decided about itself is not moved.

        Args:
            pk: primary key of the process or None when it has none
            flag (bool): whether the operation stands for a human
            phase (str): phase to report with the flip, optional

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0
        values = {"action_required": bool(flag)}
        if phase is not None:
            values["phase"] = str(phase)[:512]
        return self._apply(
            pk, values,
            only_if=Q(action_required=not flag))

    def _apply(self, pk, values, only_if=None):
        """Write the reported values to an active process and let its
        listeners learn about the new state.

        The revision of the state report is counted in the same UPDATE which
        writes the values, so every message a listener receives names the
        revision of the state it carries and a client which reads them out of
        order can drop the older one (#1207).

        Args:
            pk: primary key of the process
            values (dict): the values to write, expressions included
            only_if: an additional Q the row has to answer for the write to
                happen, for a report which shall not repeat itself
        """
        query = self.get_queryset().filter(
            pk=pk,
            done_at__isnull=True,
            status__in=self.ACTIVE_STATUS,
        )
        if only_if is not None:
            query = query.filter(only_if)
        updated = query.update(revision=F("revision") + 1, **values)

        if updated:
            try:
                # QuerySet.update() doesn't fire signals, but the listeners of a
                # process have to learn about its new state: they are how an
                # open overview of the frontend updates without reloading.
                post_save.send(
                    self.model,
                    instance=self.process_info().get(pk=pk),
                    created=False)
            except self.model.DoesNotExist:
                pass
        return updated

    def log(self, pk, description, log_type=None):
        """Add a log entry to the process which the frontend can link to.

        Args:
            pk: primary key of the process or None when it has none
            description (str): what happened
            log_type (LogTypeEnum): type of the log entry, errors by default

        Returns:
            BackgroundProcessLog: the created log entry or None
        """
        if pk is None:
            return None
        # imported here, because the log lives next to the process which is
        # rendered by this manager
        from notify.enums import LogTypeEnum
        from notify.models import BackgroundProcessLog

        return BackgroundProcessLog.objects.create(
            background_process_id=pk,
            log_type=LogTypeEnum.ERROR if log_type is None else log_type,
            description=str(description)[:4096])

    def visible_for_user(self, user, queryset=None):
        """Narrow down to the processes which belong to resources the user may view.

        A process names its resource with a generic relation, so what the user
        is permitted to see has to be looked up per type of the related
        resource. Processes which do not belong to a resource cannot be decided
        by a resource permission and stay visible - a registration for example
        only learns the service it belongs to while it runs.

        Every type which can be named here is a kind of service, and every kind
        of service is answered from a guardian table of its own
        (``registry/models/guardian.py``). That is what keeps this loop away
        from the shared table, whose text column a lookup of a uuid primary key
        casts for the rows of every model in it (#863). A new kind of resource
        which is looked up here needs such a table - see
        ``tests/django/registry/tests_guardian_object_permission_tables.py``.

        Args:
            user: the user which looks at the processes
            queryset: the processes to narrow down, this manager's by default

        Returns:
            QuerySet: the processes the user is permitted to see
        """
        if queryset is None:
            queryset = self.get_queryset()

        related_types = queryset.exclude(
            related_resource_type__isnull=True).values_list(
                "related_resource_type", flat=True).distinct()

        visible = Q(related_resource_type__isnull=True) | Q(related_id__isnull=True)
        for content_type in ContentType.objects.filter(pk__in=related_types):
            model = content_type.model_class()
            if model is None or not isinstance(model._meta.pk, models.UUIDField):
                # the resource of a process is addressed by its uuid, so a
                # resource of another kind can never be named by a process
                continue
            permitted = get_objects_for_user(
                user,
                f"{model._meta.app_label}.view_{model._meta.model_name}",
                klass=model,
                accept_global_perms=True)
            visible |= Q(
                related_resource_type=content_type,
                related_id__in=permitted.values("pk"))

        return queryset.filter(visible)


class OperationalIncidentManager(models.Manager):
    """The reporting, lifecycle and visibility of persisted incidents (#1319).

    The manager is the one writer which producers of incidents (#1320) use:
    ``report`` upserts the active incident of a dedup key idempotently - a
    recurrence raises the occurrence count of the standing row instead of
    creating a notification of its own - and ``resolve`` performs the single
    lifecycle transition. ``visible_for_user`` implements the one
    authorization rule which every read of the api runs over, so list,
    detail, filter and count can never disagree about what a caller may see.
    """

    #: the longest dedup key an incident stores; the key is built from a
    #: code, a model label and a primary key and therefore always fits
    DEDUP_KEY_MAX_LENGTH = 255
    #: how often ``report`` re-enters its decision when it loses a race with
    #: a concurrent report or resolve of the same key
    REPORT_RACES = 3

    def build_dedup_key(self, code, **resource):
        """The stable dedup key of one problem, independently of any retry.

        The key names the problem, never an execution: a code plus the typed
        resource it stands for, or the code plus ``system`` where the
        problem is the deployment itself. A Celery retry of a task, a
        second delivery of the same watchdog verdict and a UI which polls
        twice all answer the same key, which is what lets ``report``
        deduplicate them into one incident (#1319).
        """
        resource = self._single_resource(resource)
        if not resource:
            key = f"{code}|system"
        else:
            field, value = resource.popitem()
            model = self.model._meta.get_field(
                field).related_model
            key = f"{code}|{model._meta.label}|{getattr(value, 'pk', value)}"
        if len(key) > self.DEDUP_KEY_MAX_LENGTH:
            raise ValueError("The dedup key of an incident is too long.")
        return key

    def _single_resource(self, resource):
        """The resource keyword arguments, kept to the one an incident names.

        A reporter names its affected resource by one of the typed fields of
        the model (or their ``_id`` form). Nothing more than one is accepted
        - the database check refuses two anyway, and the dedup key of a
        resource which could be two is not a stable key.
        """
        fields = self.model.RESOURCE_FIELDS
        normalized = {}
        for name, value in resource.items():
            field = name[:-3] if name.endswith("_id") else name
            if field not in fields:
                raise ValueError(
                    f"'{name}' is no typed resource of an incident.")
            normalized[field] = value
        filled = {f: v for f, v in normalized.items() if v is not None}
        if len(filled) > 1:
            raise ValueError(
                "An incident names at most one affected resource.")
        return filled

    def report(self, code, source, severity, summary, resource=None,
               details=None, occurred_at=None, retry_count=None,
               retry_scheduled_until=None, dedup_key=None):
        """Upsert the active incident of one dedup key, idempotently.

        A recurrence of a problem which already stands as an active incident
        is not a second incident: the occurrence count of the standing row
        moves up, its last occurrence and its latest evidence replace the
        older ones and nothing else happens - ten retries of one incident
        are one incident (#1319), and the authoritative report of each
        single execution stays where it always was, in the process log of
        #1208. A problem which was resolved and returns is a new incident
        with the same key: the resolved history row is never reopened, the
        transition to ``resolved`` is terminal.

        The deduplication races are decided by the database: the partial
        unique index of ``dedup_key`` over the active rows refuses two
        concurrent creators of the same problem, and the loser of that race
        reads the winner's row and moves its counters instead. ``update``
        never writes an incident which was resolved between the read and the
        write - the write is conditional on the row still being active, and
        a resolution which came in between turns this report into the
        creator of the new incident it really is.

        Args:
            code (str): the structured incident code, stable per problem
            source (IncidentSourceEnum): which domain reports the incident
            severity (IncidentSeverityEnum): warning or error
            summary (str): the safe human readable summary; stored truncated
            resource (dict): at most one typed resource, e.g.
                ``{"catalogue_service": job.service_id}``
            details (dict): redacted structured metadata, stored bounded and
                redacted by ``sanitize_incident_details``
            occurred_at: the moment of this occurrence, now by default
            retry_count: the retry the reported operation is at, if known
            retry_scheduled_until: until when the operation's next attempt
                is due, if known
            dedup_key (str): the key to deduplicate by; built from the code
                and the resource when not given

        Returns:
            tuple: the incident and whether it was created
        """
        from notify.models import (INCIDENT_SUMMARY_MAX_LENGTH,
                                   sanitize_incident_details)

        severity = IncidentSeverityEnum(severity).value
        source = IncidentSourceEnum(source).value
        summary = str(summary)[:INCIDENT_SUMMARY_MAX_LENGTH]
        details = sanitize_incident_details(details)
        resource = self._single_resource(resource or {})
        key = dedup_key or self.build_dedup_key(code, **resource)
        at = occurred_at or now()

        for _ in range(self.REPORT_RACES):
            active = self.get_queryset().filter(
                dedup_key=key,
                status=IncidentStatusEnum.ACTIVE.value).first()
            if active is not None:
                values = {
                    "severity": severity,
                    "summary": summary,
                    "details": details,
                    "last_occurred_at": at,
                    "occurrence_count": F("occurrence_count") + 1,
                }
                if retry_count is not None:
                    values["retry_count"] = max(int(retry_count), 0)
                if retry_scheduled_until is not None:
                    values["retry_scheduled_until"] = retry_scheduled_until
                moved = self.get_queryset().filter(
                    pk=active.pk,
                    status=IncidentStatusEnum.ACTIVE.value).update(**values)
                if moved:
                    return self.get_queryset().get(pk=active.pk), False
                # resolved by a concurrent resolver between read and write:
                # this report is the recurrence of a resolved problem and
                # has to create its new incident, which the next round does
                continue
            try:
                with transaction.atomic():
                    incident = self.model(
                        code=code, source=source, severity=severity,
                        summary=summary, details=details, dedup_key=key,
                        first_occurred_at=at, last_occurred_at=at,
                        retry_count=max(int(retry_count or 0), 0),
                        retry_scheduled_until=retry_scheduled_until,
                        **resource)
                    incident.save()
                return incident, True
            except IntegrityError:
                # a concurrent report created the active incident of this
                # key; the next round deduplicates onto its row
                continue
        raise RuntimeError(
            f"The report of the incident '{code}' lost every race.")

    def resolve(self, dedup_key, at=None):
        """Resolve the active incidents of one dedup key (#1319).

        Recovery of the reported problem resolves the incident standing
        under the key of that problem. This is the lifecycle's single
        transition, active -> resolved; it is answered by one conditional
        update and idempotent: resolving an already resolved problem moves
        nothing and answers zero.

        Returns:
            int: how many incidents this call resolved
        """
        return self.get_queryset().filter(
            dedup_key=dedup_key,
            status=IncidentStatusEnum.ACTIVE.value).update(
                status=IncidentStatusEnum.RESOLVED.value,
                resolved_at=at or now())

    def _service_of(self, field):
        """The service model behind one typed resource field.

        Walks the path which ``RESOURCE_FIELDS`` names from the resource to
        the service whose view permission decides the visibility of an
        incident about that resource - the path is empty for the services
        themselves.
        """
        model = self.model._meta.get_field(field).related_model
        for step in filter(None, self.model.RESOURCE_FIELDS[field].split("__")):
            model = model._meta.get_field(step).related_model
        return model

    def _visible_service_ids(self, user):
        """The visible service ids per service model of a deployment.

        The same answer ``collect_service_alerts`` gives: for every kind of
        service the services the caller may view, decided by guardian and
        scoped to the published services - an update candidate is no service
        of its own to which an incident could add visibility. The superuser
        needs none of these queries; guardian answers everything to him, and
        the view short-circuits him before this is ever called.
        """
        visible = {}
        seen_models = set()
        for field in self.model.RESOURCE_FIELDS:
            service_model = self._service_of(field)
            if service_model in seen_models:
                continue
            seen_models.add(service_model)
            visible[service_model] = get_objects_for_user(
                user, f'{service_model._meta.app_label}.view_'
                      f'{service_model._meta.model_name}',
                klass=service_model.objects.filter(
                    update_candidate_of__isnull=True),
                accept_global_perms=True)
        return visible

    def _visibility_q(self, visible):
        """The Q which an incident has to answer to be visible.

        An incident is visible exactly when the service behind its typed
        resource is visible - services answer themselves, jobs and runs are
        answered through their service. A system incident names no resource
        and therefore answers none of these clauses: it is visible to the
        superuser alone, who is short-circuited before this Q is built.
        """
        scope = Q()
        for field, path in self.model.RESOURCE_FIELDS.items():
            service_model = self._service_of(field)
            lookup = f"{field}__{path}" if path else field
            scope |= Q(**{f"{lookup}__in": visible[service_model]})
        return scope

    def service_scoped(self, queryset, service_pk):
        """Narrow a queryset to the incidents which stand for one service.

        The read of the contextual screen of #1322: all incidents whose
        affected resource is the service itself or a job or run belonging
        to it.
        """
        return queryset.filter(self._service_q(service_pk))

    def _service_q(self, service_pk):
        """The Q naming the incidents which belong to one service."""
        scope = Q()
        for field, path in self.model.RESOURCE_FIELDS.items():
            lookup = f"{field}__{path}" if path else field
            # the primary key of a service is a uuid; the lookup answers the
            # matching column whatever kind of service the value names
            scope |= Q(**{f"{lookup}": service_pk})
        return scope

    def visible_for_user(self, user, queryset=None):
        """The incidents which the caller may view - the one rule (#1319).

        A superuser sees every incident. An authenticated user sees the
        incidents whose affected service he may view, decided by the same
        guardian permissions which hide the services themselves; jobs and
        runs which belong to a visible service are visible incidents of
        that service. System incidents - the ones naming no resource, the
        deployment's own watchdog findings - answer no service and are
        therefore never part of this answer: they belong to a superuser
        alone. An anonymous caller never reaches a queryset at all, the api
        refuses him the endpoint.

        Every read of the api - the list, the detail, every filter and with
        them every count and page total - runs over exactly this narrowing,
        which is why a total of a count or the existence behind a detail
        url can never name an incident the caller may not see.
        """
        if queryset is None:
            queryset = self.get_queryset()
        if user is None or not user.is_authenticated:
            return queryset.none()
        if user.is_superuser:
            return queryset
        return queryset.filter(self._visibility_q(
            self._visible_service_ids(user)))
