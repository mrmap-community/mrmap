from ws.signals import update_count
from asgiref.sync import async_to_sync
from celery import states
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.html import format_html
from django.utils.translation import gettext as _
from jobs.models import Job, Task
from django.contrib.contenttypes.models import ContentType


def send_task_toast(channel_layer, started, instance):
    if instance.owned_by_org:
        title = _('New task scheduled') if started else _('Task done')
        body = format_html('<a href={}>{}</a>', f'{instance.get_absolute_url()}', _('details'))

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


@receiver(post_save, sender=Job, dispatch_uid='update_job_table_listeners_on_job_post_save')
@receiver(post_delete, sender=Job, dispatch_uid='update_job_table_listeners_on_job_post_delete')
@receiver(post_save, sender=Task, dispatch_uid='update_job_table_listeners_on_task_post_save')
@receiver(post_delete, sender=Task, dispatch_uid='update_job_table_listeners_on_task_post_delete')
def update_job_table_listeners(instance, **kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    channel_layer = get_channel_layer()
    if isinstance(instance, Task):
        instance = instance.job

    if instance.owned_by_org:
        if 'created' in kwargs:
            if kwargs['created']:
                # post_save signal --> new Task object
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
            f"jobtableconsumer_{instance.owned_by_org.pk}_observers",
            {
                "type": "send.table.as.html",
            },
        )


@receiver(post_save, sender=Task, dispatch_uid='update_task_table_listeners_on_task_post_save')
@receiver(post_delete, sender=Task, dispatch_uid='update_task_table_listeners_on_task_post_delete')
def update_task_table_listeners(instance, **kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    channel_layer = get_channel_layer()
    if instance.owned_by_org:
        async_to_sync(channel_layer.group_send)(
            f"tasktableconsumer_{instance.owned_by_org.pk}_observers",
            {
                "type": "send.table.as.html",
            },
        )
