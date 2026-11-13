from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import (Case, F, OuterRef, Q, Subquery, TextField,
                              Value, When)
from django.db.models.fields import FloatField
from django.db.models.functions import (Coalesce, Greatest, Least, Now, Round)
from django.db.models.signals import post_save
from django.utils.timezone import now
from guardian.shortcuts import get_objects_for_user
from notify.enums import (LogTypeEnum, OperationStateEnum,
                          ProcessStatusEnum)


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
