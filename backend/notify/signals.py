from typing import OrderedDict

from asgiref.sync import async_to_sync
from celery import states
from channels.layers import get_channel_layer
from crum import get_current_request
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult
from rest_framework_json_api import utils
from rest_framework_json_api.renderers import JSONRenderer

from notify.serializers import TaskResultSerializer


@receiver(post_save, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_save')
@receiver(post_delete, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_delete')
def update_task_result_listeners(**kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    print('huhu')
    channel_layer = get_channel_layer()
    # TODO: serialize the TaskResult as JSON:API
    request = get_current_request()
    request.query_params = OrderedDict()
    task_serializer = TaskResultSerializer(
        kwargs['instance'], **{"context": {"request": request}})
    json = {
        'jsonapi': {
            'data': JSONRenderer.build_json_resource_obj(
                fields=utils.get_serializer_fields(serializer=task_serializer),
                resource=task_serializer.data,
                resource_instance=kwargs['instance'],
                resource_name=utils.get_resource_type_from_instance(
                    kwargs['instance']),
                serializer=task_serializer)
        }
    }

    if 'created' in kwargs:
        if kwargs['created']:
            # post_save signal --> new TaskResult object
            json.update({"event": "create"})
        else:
            if kwargs['instance'].status in [states.SUCCESS, states.FAILURE]:
                json.update({"event": "update"})
    else:
        # post_delete signal
        json.update({"event": "delete"})

    async_to_sync(channel_layer.group_send)(
        "default",
        {
            "type": "send.msg",
                    "json": json,
        },
    )
