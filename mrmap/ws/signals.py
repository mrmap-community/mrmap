from asgiref.sync import async_to_sync
from celery import states
from celery.signals import after_task_publish
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.html import format_html
from django_celery_results.models import TaskResult
from django.utils.translation import gettext_lazy as _

from service.helper.enums import OGCServiceEnum
from service.models import Metadata
from ws.messages import Toast


def update_count(channel_layer, instance):
    # todo: for now we send all pending tasks serialized as json
    #  further changes:
    #   * filter by the created_by object show only pending tasks for that the user
    #     has permissions
    tasks_count = TaskResult.objects.filter(status__in=[states.STARTED, states.PENDING]).count()
    response = {'pendingTaskCount': tasks_count}

    async_to_sync(channel_layer.group_send)(
        "app_view_model_observers",
        {
            "type": "send.msg",
            "msg": response,
        },
    )


def send_task_toast(channel_layer, started, instance):
    title = _('New task scheduled') if started else _('Task done')
    body = format_html('<a href={}>{}</a>', f'{reverse("resource:pending-tasks")}?task_id={instance.task_id}', _('details'))
    response = Toast(title=title, body=body).get_response()

    async_to_sync(channel_layer.group_send)(
        "toast_observers",
        {
            "type": "send.msg",
            "msg": response,
        },
    )


@receiver(post_save, sender=TaskResult, dispatch_uid='update_pending_task_listeners_on_post_save')
@receiver(post_delete, sender=TaskResult, dispatch_uid='update_pending_task_listeners_on_post_delete')
def update_pending_task_listeners(**kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    channel_layer = get_channel_layer()

    if 'created' in kwargs:
        if kwargs['created']:
            # post_save signal --> new TaskResult object
            update_count(channel_layer, kwargs['instance'])
            send_task_toast(channel_layer, True, kwargs['instance'])
        else:
            if kwargs['instance'].status in [states.SUCCESS, states.FAILURE]:
                send_task_toast(channel_layer, False, kwargs['instance'])
    else:
        # post_delete signal
        update_count(channel_layer, kwargs['instance'])

    async_to_sync(channel_layer.group_send)(
        "pending_task_table_observers",
        {
            "type": "send.table.as.html",
        },
    )

@after_task_publish.connect
def task_send_handler(sender=None, headers=None, body=None, **kwargs):
    """
    Dispatched when a task has been sent to the broker. Note that this is executed in the process that sent the task.

    Sender is the name of the task being sent.

    Cause if we create celery Task which are sended to the broker with countdown, no TaskResult object in our result
    backend is created. So the user can't see the task till the TaskResult is created.

    One other use case is, if a task lifetime is >>> 1 second the celery Task doesn't life that long as the a redirect
    took. For a better user experience we can now start celery Task's with countdown and show pending tasks on the
    PendingTaskTable view.
    """
    info = headers if 'task' in headers else body
    TaskResult.objects.create(task_id=info['id'],
                              task_name=sender,
                              meta={
                                  "phase": "Pending..."
                              })
