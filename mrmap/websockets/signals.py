from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from structure.models import PendingTask


@receiver(post_save, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_save')
@receiver(post_delete, sender=PendingTask, dispatch_uid='update_pending_task_listeners_on_post_delete')
def update_pending_task_listeners(instance, **kwargs):
    """
    Send the information to the channel group when a PendingTask is created/modified

    Args:
        instance: the created/modified/deleted instance of PendingTask Model
    """
    notify_observers = False
    if 'created' in kwargs:
        signal_type = 'post_save'
        if kwargs['created']:
            # always notify observers if a new pending task was created
            notify_observers = True
        else:
            # only notify observers if something significant was changed on this pending task object
            for significant_field in instance.significant_fields:
                old_value = getattr(instance, f'_{significant_field}')
                new_value = getattr(instance, significant_field)
                if old_value != new_value:
                    notify_observers = True
                    break
    else:
        signal_type = 'post_delete'
        # always notify observers if a pending task was deleted
        notify_observers = True

    if notify_observers:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "pending_task_observers",
            {
                "type": "send.table.as.html",
                "signal_type": signal_type,
                "instance_pk": instance.pk,
            },
        )
