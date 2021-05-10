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
            f"appviewmodelconsumer_{instance.owned_by_org.pk}_observers",
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
            f"toastconsumer_{instance.owned_by_org.pk}_observers",
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
                # post_save signal --> updated instance
                if instance.status in [states.SUCCESS, states.FAILURE]:
                    update_count(channel_layer, instance)
                    send_task_toast(channel_layer, False, instance)
        else:
            # post_delete signal
            update_count(channel_layer, instance)

        async_to_sync(channel_layer.group_send)(
            f"pendingtasktableconsumer_{instance.owned_by_org.pk}_observers",
            {
                "type": "send.table.as.html",
            },
        )
