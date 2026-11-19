from logging import Logger

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from notify.utils import (build_action_payload, invalidate_service_alerts,
                          send_msg_on_commit)
from registry.models.harvest import HarvestingJob
# the phase the harvest alert of a catalogue reads off the newest run, and the
# constant it is named by: the invalidation below and the annotation of the
# alert read the same phase from the same constant
from registry.querys.alerts import ABORTED_PHASE
from registry.serializers.harvesting import HarvestingJobSerializer
from simple_history.models import HistoricalRecords

logger: Logger = settings.ROOT_LOGGER


def log_exception(exception):
    # errors while building messages and sending messages shall be ignored
    logger.warning("can't send websocket message")
    if settings.DEBUG:
        logger.exception(exception, stack_info=True, exc_info=True)


@receiver(post_delete, sender=BackgroundProcess, dispatch_uid='update_BackgroundProcess_listeners_on_post_delete')
def update_background_process_listeners_on_background_process_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is deleted

    post_delete fires after the row is gone: a reload through process_info()
    answered ObjectDoesNotExist for every deletion, the exception was
    swallowed and the "deleted" message never reached the listeners (#1456).
    The payload is built from the instance the signal hands over instead -
    the deletion collector passes the fetched row, so every stored field is
    on it, and a bulk delete (the retention sweep of #1208) delivers the
    same signal per collected instance. The annotations of process_info()
    are the exception and the serializer answers them from the stored
    fields (state) or leaves them out (progress): a client which learns of
    a deletion refetches its list, it never replaces a record of a row
    which does not exist anymore.
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        reducer_action = build_action_payload(
            request=request,
            instance=kwargs['instance'],
            resource_type="BackgroundProcess",
            serializer_cls=BackgroundProcessSerializer,
            action="delete"
        )
        # a record which is gone has to disappear from every open list
        send_msg_on_commit(msg=reducer_action, immediate=True)
    except Exception as e:
        log_exception(e)


@receiver(post_save, sender=BackgroundProcess, dispatch_uid='update_BackgroundProcess_listeners_on_post_save')
def update_background_process_listeners_on_background_process_save_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        background_process = kwargs['instance']
        if getattr(background_process, "progress", None) is None:
            # senders that wrote through QuerySet.update() hand over an instance
            # without annotation; process_info adds progress and the resource type
            background_process = BackgroundProcess.objects.process_info().get(
                pk=background_process.pk)
        reducer_action = build_action_payload(
            request=request,
            instance=background_process,
            resource_type="BackgroundProcess",
            serializer_cls=BackgroundProcessSerializer,
            action="created" if kwargs.get("created", False) else "updated"
        )
        # done_at is set by every terminal status (completed, failed, aborted):
        # the message which announces it must never be collapsed away
        send_msg_on_commit(
            msg=reducer_action,
            immediate=kwargs.get("created", False)
            or background_process.done_at is not None
        )
    except Exception as e:
        log_exception(e)


@receiver(post_save, sender=HarvestingJob, dispatch_uid='update_HarvestingJob_listeners_on_post_save')
def update_harvesting_job_listeners_on_harvesting_job_save(**kwargs):
    """
    Send the information to the channel group when a HarvestingJob is created/modified

    A job writes itself on every step of its workflow (see HarvestingJob.save,
    registry/tasks/harvest.py and registry/querys/harvest_history.py), which are
    exactly what the harvesting views of the frontend are waiting for: the push
    stays one per save, no matter which field the step wrote.

    The service alerts of the catalogue only hear the real status transitions
    of the run (#1485). What the harvest alert reads off the job are three
    facts - which run is the newest of the catalogue, whether that run was
    aborted and whether it is done (`annotate_harvest_alerts` in
    registry/querys/alerts.py); what a run left its records behind in travels
    with the record rows and the log lines and never with a save of the job. A
    save which moves none of the three - the plan and progress saves of the
    tasks, which write `total_records`, the step size or the bookkeeping of the
    watchdog - invalidated the stored alerts per save before: one
    invalidation message and one enqueued refresh of the whole alert table for
    a save which no alert can answer differently with.

    Which save is a transition, the model itself answers. The ordinary save of
    an open run is not one: `HarvestingJob.save` puts
    `skip_history_when_saving=True` on the instance for exactly those (and
    deletes it again once the save signal has run), so they skip the audit row
    of the run. Its decisions write the audit row: the creation, the abort, the
    zero-record completion taken inside `save()` itself, and every workflow
    save which names `skip_history_when_saving=False`. A run which carries
    `done_at` or the aborted phase stands decided anyway, and the creation of a
    run decides which run is the newest of its catalogue - these are
    transitions by their state alone, whichever save handed them over.
    """
    instance = kwargs['instance']
    if instance.service_id is not None and (
            kwargs.get('created', False)
            or instance.done_at is not None
            or instance.phase == ABORTED_PHASE
            or not getattr(instance, 'skip_history_when_saving', False)):
        invalidate_service_alerts()
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        # total_steps, done_steps and progress are no fields but annotations: a
        # payload built from the instance the signal hands over would not carry
        # them. They have to be read after the save, because an instance which
        # was selected before it (the API's get_object does so) still holds the
        # progress of the state before the update, and a client which received
        # the terminal message of a job would keep showing that frozen value.
        harvesting_job = HarvestingJob.objects.with_process_info().get(
            pk=kwargs['instance'].pk)
        reducer_action = build_action_payload(
            request=request,
            instance=harvesting_job,
            resource_type="HarvestingJob",
            serializer_cls=HarvestingJobSerializer,
            action="created" if kwargs.get("created", False) else "updated"
        )
        # done_at is set by every terminal phase (completed, aborted):
        # the message which announces it must never be collapsed away
        send_msg_on_commit(
            msg=reducer_action,
            immediate=kwargs.get("created", False)
            or harvesting_job.done_at is not None
        )
    except Exception as e:
        log_exception(e)


# the receivers which broadcast a `TaskResult` save into the listeners of the
# process it was threaded to are retired with the `threads` relation itself,
# together with that relation (#1179)
