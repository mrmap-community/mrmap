from asgiref.sync import async_to_sync
from celery import states
from celery.signals import after_task_publish
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.urls import reverse
from django.utils.html import format_html
from django_celery_results.models import TaskResult
from django.utils.translation import gettext as _
from structure.models import PendingTask
from django.contrib.contenttypes.models import ContentType
from crum import get_current_user


def update_count(channel_layer, instance):
    if instance.owned_by_org:
        async_to_sync(channel_layer.group_send)(
            f"appviewmodelconsumer_{instance.owned_by_org.name}_observers",
            {
                "type": "update.app.view.model",
            },
        )


def send_task_toast(channel_layer, started, instance):
    if instance.owned_by_org:
        title = _('New task scheduled') if started else _('Task done')
        body = format_html('<a href={}>{}</a>', f'{reverse("resource:pending-tasks")}?task_id={instance.task_id}', _('details'))

        content_type = ContentType.objects.get_for_model(instance)

        async_to_sync(channel_layer.group_send)(
            f"toastconsumer_{instance.owned_by_org.name}_observers",
            {
                "type": "send.toast",
                "content_type": content_type.pk,
                "object_id": instance.pk,
                "title": title,
                "body": body
            },
        )


@receiver(post_save, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_save')
@receiver(post_delete, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_delete')
@receiver(post_save, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_save')
@receiver(post_delete, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_delete')
def update_pending_task_listeners(instance, **kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    channel_layer = get_channel_layer()

    if isinstance(instance, TaskResult):
        try:
            instance = instance.pendingtask
        except Exception:
            return

    if instance.owned_by_org:
        if 'created' in kwargs:
            if kwargs['created']:
                # post_save signal --> new PendingTask/TaskResult object
                update_count(channel_layer, instance)
                send_task_toast(channel_layer, True, instance)
            else:
                if instance.status in [states.SUCCESS, states.FAILURE]:
                    update_count(channel_layer, instance)
                    send_task_toast(channel_layer, False, instance)
        else:
            # post_delete signal
            update_count(channel_layer, kwargs['instance'])

        async_to_sync(channel_layer.group_send)(
            f"pendingtasktableconsumer_{instance.owned_by_org.name}_observers",
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

    owned_by_org_pk = body[0][0]
    try:
        PendingTask.objects.create(task_id=info['id'],
                                   task_name=sender,
                                   created_by_user=get_current_user(),
                                   owned_by_org_id=owned_by_org_pk,
                                   meta={
                                       "phase": "Pending..."
                                   })
    except Exception as e:
        import traceback
        traceback.print_exc()

