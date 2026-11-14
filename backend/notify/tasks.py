from datetime import datetime, timedelta
from logging import Logger

from celery import Task, shared_task
from celery.signals import task_prerun, task_retry
from celery.utils.time import get_exponential_backoff_interval
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import (Case, F, IntegerField, Value, When)
from django.db.models.functions import Coalesce, Greatest
from django.db.models.signals import post_save
from django.utils.timezone import now
from extras.tasks import SingletonTask
from MrMap import celery_queues
from notify.enums import ProcessStatusEnum
from notify.managers import capped_done_steps
from notify.models import BackgroundProcess
from registry.exceptions.harvesting import InternalServerError
from requests.exceptions import ConnectionError, Timeout

logger: Logger = settings.ROOT_LOGGER


@task_prerun.connect
def get_background_process(task, *args, **kwargs):
    """To automaticly get the BackgroundProcess object on task runtime."""
    task.background_process_pk = kwargs["kwargs"].get(
        "background_process_pk", None)
    if isinstance(task, BackgroundProcessBased) and task.background_process_pk is not None:
        task.update_background_process()


@task_retry.connect
def report_process_retry(sender, request, reason, **kwargs):
    """Mirror one retry of a task onto the process which reports its work.

    A retrying task neither failed nor progressed: the operation waits for
    its next attempt, and the process which reports it would otherwise keep
    answering plain running for the whole backoff window - the state the
    overview of the background activity is asked to tell apart (#1207).

    Which process a task reports to is read from the kwargs the broker
    transports - the same seam the ``get_background_process`` above uses for
    the start of a task.
    """
    pk = (getattr(request, "kwargs", None) or {}).get(
        "background_process_pk")
    if pk is None:
        # a task which was never given a process retries invisibly, like the
        # progress reports of a process-less task
        return
    try:
        # celery's Retry carries the textual answer of what the task failed
        # on in `excs` (its safe_repr of the exception) and a context message;
        # str of the exception itself would answer the constructor tuple
        reason_text = (
            getattr(reason, "excs", None)
            or getattr(reason, "message", None)
            or str(reason))
        BackgroundProcess.objects.report_retry(
            pk, reason=reason_text,
            until=retry_scheduled_at(sender, request, reason))
    except Exception as e:
        # the retry itself does not depend on this report; the window closes
        # on its own and the next report of the task answers the state again
        logger.warning(
            "can't report the retry of a task to the process %s: %s", pk, e)


def retry_scheduled_at(sender, request, reason):
    """When the retried attempt of a task is due.

    Whoever asked for the retry handed a delay to ``retry`` whenever it knew
    one: celery carries it on the ``Retry`` exception the signal answers with
    - the seconds of an exponential backoff the autoretry decorator computed
    before calling ``retry``, or an explicit countdown or eta. Only a retry
    which ran without any of them has to have its window answered from the
    task's own retry policy, and then with the very helper and formula celery
    uses for the backoff, not an invented one.

    A window which is estimated is a window which may be a little wrong: an
    attempt which fails again rewrites it, a terminal outcome decides about
    the process anyway, and the state of an operation whose window ran out
    without a report reads running again by itself.
    """
    when = getattr(reason, "when", None)
    if isinstance(when, datetime):
        return when
    if isinstance(when, (int, float)):
        return now() + timedelta(seconds=float(when))
    backoff = getattr(sender, "retry_backoff", False) or 1
    return now() + timedelta(seconds=get_exponential_backoff_interval(
        factor=int(max(1.0, float(backoff))),
        retries=getattr(request, "retries", 0) or 0,
        maximum=int(getattr(sender, "retry_backoff_max", 600) or 600),
        full_jitter=bool(getattr(sender, "retry_jitter", False))))


class BackgroundProcessBased(Task):
    autoretry_for = (Timeout, ConnectionError, InternalServerError)
    retry_backoff = 30
    retry_backoff_max = 5 * 60
    retry_jitter = False
    max_retries = 10

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self.log_process(f"An error occurred: {exc}"[:512])
        self.update_background_process(
            phase=f"An error occurred: {exc}"[:512],
            failed=True
        )

    def log_process(self, description, log_type=None):
        """A durable log entry on the process which this task reports to.

        The process is where a polling client looks, so what the worker
        learned about a step which failed or a run which did not belongs
        beside its state (#1177). A task which was never given a process
        logs nowhere, like the reports of the manager.
        """
        BackgroundProcess.objects.log(
            getattr(self, "background_process_pk", None),
            description, log_type)

    def update_state(self, task_id=None, state=None, meta=None, **kwargs):
        pass
        # return super().update_state(task_id, state, meta, **kwargs)

    def update_background_process(
        self,
        phase: str = "",
        service=None,
        total_steps=None,
        step_done=False,
        completed=False,
        failed=False,
        references_total=None,
        reference_stored=False,
        reference_failed=False,
    ):
        """Report what this task knows about the process it runs for.

        Every argument is optional and only what the caller names is written:
        a task which starts reports nothing but that the process works again,
        a task which published a fan-out names its steps, a task which decided
        about one of them counts it.

        The ``references_*`` arguments are the summary of a collection of
        metadata references (#1259): ``references_total`` is the plan a caller
        names when it publishes its fan-out, the two booleans tell which
        outcome one reference reached, and the completion of the process closes
        the plan with the references which never reported an outcome - see
        ``finish_background_process``. A plan is named by the task which
        publishes the references, before a worker can answer one, and the
        outcome reports are the references' own.
        """
        # will be provided by get_background_process signal if the pk is provided by kwargs
        if getattr(self, "background_process_pk", None) is not None:
            try:
                query = BackgroundProcess.objects.filter(
                    pk=self.background_process_pk)
                kwargs = {"status": ProcessStatusEnum.RUNNING}

                if phase:
                    kwargs.update({
                        "phase": phase
                    })
                if service:
                    kwargs.update({
                        "related_resource_type": ContentType.objects.get_for_model(service),
                        "related_id": service.pk
                    })
                if total_steps is not None:
                    kwargs.update({
                        "total_steps": total_steps
                    })
                if reference_stored or reference_failed:
                    # one reference decided by this task; the Coalesce answers
                    # the NULL of a counter which never moved before - a
                    # collection counts from nothing, not from nothing plus
                    # nothing. Like the step increment below (see
                    # capped_done_steps) this is a report, not exactly-once
                    # accounting: a reference which is delivered twice is
                    # counted twice, and the identity which makes it exact
                    # belongs to #1263.
                    counter = (
                        "references_stored" if reference_stored
                        else "references_failed")
                    kwargs.update({
                        counter: Coalesce(F(counter), 0) + 1
                    })
                if step_done:
                    kwargs.update({
                        # the capped increment shared with the manager's
                        # report, so a duplicated step report cannot push
                        # this path beyond 100 % either (#1258, #1261)
                        "done_steps": capped_done_steps(1)
                    })
                if failed:
                    kwargs.update({"status": ProcessStatusEnum.FAILED, "done_at": now()})
                elif completed:
                    kwargs.update({
                        "total_steps": Coalesce(F("total_steps"), 1),
                        "done_steps": Coalesce(F("total_steps"), 1),
                        "done_at": now(),
                        "phase": "completed",
                        "status": ProcessStatusEnum.COMPLETED,
                        # a run which planned a collection closes its summary
                        # with the references it never heard an answer from
                        # (#1259): a plan which reported everything answers 0
                        # here, a plan whose fan-out was interrupted answers
                        # what is missing. A process which planned no
                        # collection answers NULL - which is what the column of
                        # an unplanned process holds anyway - so the completion
                        # of a harvest or of a registration without collection
                        # cannot answer a summary it never planned.
                        "references_skipped": Case(
                            When(
                                references_total__isnull=True,
                                then=Value(None, output_field=IntegerField())),
                            default=Greatest(
                                F("references_total")
                                - Coalesce(F("references_stored"), 0)
                                - Coalesce(F("references_failed"), 0),
                                0),
                            output_field=IntegerField(),
                        ),
                    })
                if references_total is not None:
                    # the plan of a collection, named by the task which
                    # publishes its fan-out: the expected number and the three
                    # outcome counters of a run which decided nothing yet. The
                    # Coalesces keep what a report already counted - a redelivery
                    # of the root which publishes the plan a second time must
                    # not erase the outcomes workers reported (#1259, and the
                    # guard of #1263). The plan is named last on purpose: an
                    # explicit plan is the answer of this write, whatever the
                    # completion above derived from the counters before it.
                    kwargs.update({
                        "references_total": references_total,
                        "references_stored": Coalesce(F("references_stored"), 0),
                        "references_failed": Coalesce(F("references_failed"), 0),
                        "references_skipped": Coalesce(F("references_skipped"), 0),
                    })

                if kwargs:
                    # A terminal outcome cannot be overwritten by sibling tasks.
                    active_query = query.filter(
                        done_at__isnull=True,
                        status__in=[ProcessStatusEnum.PENDING, ProcessStatusEnum.RUNNING])
                    bare_running = kwargs == {"status": ProcessStatusEnum.RUNNING}
                    if kwargs.get("status") == ProcessStatusEnum.RUNNING:
                        # any report of a task which works ends the window of a
                        # reported retry: the operation works again (#1207)
                        kwargs["retry_scheduled_until"] = None
                    if bare_running:
                        # get_background_process fires on every task start; a
                        # process which is already running and has no retry
                        # window to close answers nothing to write and must not
                        # broadcast anything either.
                        active_query = active_query.exclude(
                            status=ProcessStatusEnum.RUNNING,
                            retry_scheduled_until__isnull=True)
                    # every write of this path is a state report, and the
                    # revision which orders the reports is counted in the same
                    # UPDATE (#1207)
                    kwargs["revision"] = F("revision") + 1
                    updated = active_query.update(**kwargs)

                    if updated:
                        try:
                            # process_info provides the progress annotation and
                            # the related resource type in one go, so the
                            # post_save receiver doesn't have to reload.
                            instance = BackgroundProcess.objects.process_info().get(
                                pk=self.background_process_pk)
                            post_save.send(
                                BackgroundProcess,
                                instance=instance,
                                created=False
                            )
                        except BackgroundProcess.DoesNotExist:
                            logger.warning(
                                f"Can't get BackgroundProcess by id {self.background_process_pk}")

            except Exception as e:
                logger.exception(e, stack_info=True, exc_info=True)
        else:
            logger.warning(
                f"No background process provided for BackgroundProcessBased task. {self.name}")


@shared_task(
    bind=True,
    queue=celery_queues.DB_ROUTINES,
    base=BackgroundProcessBased
)
def finish_background_process(
    self,
    *args,
    **kwargs
):
    """Close the process a finished fan-out reports for.

    The body of a chord runs when every member answered - which is not the
    same as every member succeeding. The process is stored COMPLETED anyway
    (the epic's decision D9, which is how harvesting shows a run whose import
    had errors), and the counters of a planned metadata collection close with
    it: what the references answered is already on the row, and what is
    missing from the plan is stored as skipped. A client of the job center
    therefore reads "completed, but N references failed" from the process
    itself instead of mining its log lines (#1259).
    """
    self.update_background_process(
        completed=True
    )


@shared_task(queue=celery_queues.DB_ROUTINES, bind=True, base=SingletonTask)
def delete_expired_background_processes(self, *args, **kwargs):
    """Takes back the background processes whose retention has passed (#1208).

    Runs as a singleton on the ``db-routines`` queue like the other
    housekeeping: two sweeps over the same history have nothing to add to
    each other. The job history of the deployment grows with every reported
    operation; this sweep bounds it to the retention window, so the failures
    of the window stay discoverable while a deployment which ran for years
    does not answer its whole past. A process which ended after the moment
    of the retention is simply listed until this sweep reached it.
    """
    from notify.models import purge_expired_background_processes

    summary = purge_expired_background_processes()
    logger.info(
        "Background processes: %s decided processes deleted with %s of their "
        "log entries and %s stored files "
        "(retention %s days).", summary["purged"], summary["logs"],
        summary["files"], summary["retention_days"])
    return summary
