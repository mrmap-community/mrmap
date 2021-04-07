from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from structure.models import PendingTask


@receiver(post_save, sender=PendingTask, dispatch_uid='update_pending_task_listeners')
def update_pending_task_listeners(instance, **kwargs):
    """
    Send the information to the channel group when a PendingTask is created/modified

    Args:
        instance: the created/modified instance of PendingTask Model
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "pending_task_observers",
        {
            "type": "send.rendered.table",
            "instance_pk": instance.pk,
        },
    )
