import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save
from django.dispatch import receiver
from structure.models import PendingTask


@receiver(post_save, sender=PendingTask, dispatch_uid='update_pending_task_listeners')
def update_pending_task_listeners(sender, instance, **kwargs):
    """
    Sends the PendingTaskTable to the client when a PendingTask is modified
    """
    print('signal called')
    message = {
        'instance_id': instance.pk,
    }

    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
        "pending_task_observers",
        {
            "type": "send.message",
            "text": json.dumps(message),
        },
    )
