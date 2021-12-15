from asgiref.sync import async_to_sync
from celery import states
from channels.layers import get_channel_layer
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult


@receiver(post_save, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_save')
@receiver(post_delete, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_delete')
def update_task_result_listeners(**kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    channel_layer = get_channel_layer()
    # TODO: serialize the TaskResult as JSON:API
    json = {
        "data": {
            "type": "TaskResult",
                    "id": "1",
                    "attributes": {
                        "title": "JSON:API paints my bikeshed!"
                    },
            "relationships": {
                        "author": {
                            "links": {
                                "related": "http://example.com/articles/1/author"
                            }
                        }
                    }
        }
    }
    if 'created' in kwargs:
        if kwargs['created']:
            # post_save signal --> new TaskResult object
            json.update({"meta": {"ws-event": "create"}})
        else:
            if kwargs['instance'].status in [states.SUCCESS, states.FAILURE]:
                json.update({"meta": {"ws-event": "update"}})
    else:
        # post_delete signal
        json.update({"meta": {"ws-event": "delete"}})

    async_to_sync(channel_layer.group_send)(
        "default",
        {
            "type": "send.msg",
                    "json": json,
        },
    )
