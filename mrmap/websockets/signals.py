from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from structure.models import PendingTask


@receiver(post_save, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_save')
@receiver(post_delete, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_delete')
def update_pending_task_listeners(signal, instance, **kwargs):
    """
    Send the information to the channel group when a PendingTask is created/modified

    Args:
        instance: the created/modified/deleted instance of PendingTask Model
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "pending_task_observers",
        {
            #"type": "send.table.as.json",
            "type": "send.table.as.html",
            "instance_pk": instance.pk,
        },
    )
