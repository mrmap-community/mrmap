from logging import Logger

from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult
from simple_history.models import HistoricalRecords

from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from notify.utils import build_action_payload, send_msg

logger: Logger = settings.ROOT_LOGGER


def log_exception(exception):
    # errors while building messages and sending messages shall be ignored
    logger.warning("can't send websocket message")
    if settings.DEBUG:
        logger.exception(exception, stack_info=True, exc_info=True)


@receiver(post_delete, sender=BackgroundProcess, dispatch_uid='update_BackgroundProcess_listeners_on_post_delete')
def update_background_process_listeners_on_background_process_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        reducer_action = build_action_payload(
            request=request,
            instance=BackgroundProcess.objects.process_info().get(
                pk=kwargs['instance'].pk),
            resource_type="BackgroundProcess",
            reducer_name="backgroundProcesses",
            serializer_cls=BackgroundProcessSerializer,
            action="delete"
        )
        send_msg(msg=reducer_action)
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
        background_process = BackgroundProcess.objects.process_info().get(
            pk=kwargs['instance'].pk)
        reducer_action = build_action_payload(
            request=request,
            instance=background_process,
            resource_type="BackgroundProcess",
            reducer_name="backgroundProcesses",
            serializer_cls=BackgroundProcessSerializer,
            action="created" if kwargs.get("created", False) else "updated"
        )
        send_msg(msg=reducer_action)
    except Exception as e:
        log_exception(e)


@receiver(post_delete, sender=TaskResult, dispatch_uid='update_BackgroundProcess_listeners_on_post_delete_TaskResult')
@receiver(post_save, sender=TaskResult, dispatch_uid='update_BackgroundProcess_listeners_on_post_save_TaskResult')
def update_background_process_listeners_on_task_result_save_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        task_result: TaskResult = kwargs['instance']
        if not task_result.processes.exists():
            return
        reducer_action = build_action_payload(
            request=request,
            instance=task_result.processes.process_info()[0],
            resource_type="BackgroundProcess",
            reducer_name="backgroundProcesses",
            serializer_cls=BackgroundProcessSerializer,
            action="updated"
        )
        send_msg(msg=reducer_action)
    except Exception as e:
        log_exception(e)
