import json
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

    request = get_current_request()
    if request and (not hasattr(request, 'query_params') or not request.query_params):
        request.query_params = OrderedDict()
    task_serializer = TaskResultSerializer(
        instance=kwargs['instance'], **{"context": {"request": request}})
    renderer = JSONRenderer()
    action = json.loads('{}')

    class DummyView(object):
        resource_name = 'TaskResult'

    action.update({'payload': json.loads(renderer.render(
        task_serializer.data, renderer_context={"view": DummyView(), "request": request}).decode("utf-8"))['data']})

    if 'created' in kwargs:
        if kwargs['created']:
            # post_save signal --> new TaskResult object
            action.update({'type': "taskResults/add"})
        else:
            if kwargs['instance'].status in [states.SUCCESS, states.FAILURE]:
                action.update({'type': "taskResults/update"})
    else:
        # post_delete signal
        action.update({'type': "taskResults/remove"})

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "default",
        {
            "type": "send.msg",
                    "json": str(action),
        },
    )
