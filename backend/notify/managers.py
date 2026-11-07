from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Case, F, Q, Value, When
from django.db.models.fields import FloatField
from django.db.models.functions import Coalesce, Greatest, Least, Round
from django.db.models.signals import post_save
from django.utils.timezone import now
from guardian.shortcuts import get_objects_for_user
from notify.enums import ProcessStatusEnum


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
            )
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

        The done steps are only ever moved up and are capped at the total: a
        reporter which counts too eagerly inflates a process towards its end,
        it never pulls a reported progress back. A total of None caps nothing
        - a process which does not know its total cannot exceed it.

        A process which reports itself COMPLETED is written as done: the
        completion of the work is the proof that its steps are over, and the
        overview of the background activity renders exactly these numbers.

        Returns:
            int: amount of processes which were updated
        """
        if pk is None:
            return 0

        values = {"status": status}
        if phase is not None:
            values["phase"] = str(phase)[:512]
        if total_steps is not None:
            values["total_steps"] = total_steps
        steps = (1 if step_done else 0) + max(int(steps_done or 0), 0)
        if steps:
            # GREATEST keeps a report which would count past the total from
            # pulling a further done process back, and Coalesce answers the
            # NULL which Least leaves behind when there is no total to cap at.
            values["done_steps"] = Coalesce(
                Greatest(
                    F("done_steps"),
                    Least(F("done_steps") + steps, F("total_steps"))),
                F("done_steps") + steps)
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

    def _apply(self, pk, values):
        """Write the reported values to an active process and let its
        listeners learn about the new state."""
        updated = self.get_queryset().filter(
            pk=pk,
            done_at__isnull=True,
            status__in=self.ACTIVE_STATUS,
        ).update(**values)

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
