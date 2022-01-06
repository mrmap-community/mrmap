import json
from typing import OrderedDict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult
from rest_framework_json_api.renderers import JSONRenderer
from simple_history.models import HistoricalRecords

from notify.serializers import TaskResultSerializer


@receiver(post_save, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_save')
@receiver(post_delete, sender=TaskResult, dispatch_uid='update_task_result_listeners_on_post_delete')
def update_task_result_listeners(**kwargs):
    """
    Send the information to the channel group when a TaskResult is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        # TODO: check task_name and filter by it

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
                action.update({'type': "taskResults/update"})
        else:
            # post_delete signal
            action.update({'type': "taskResults/remove"})

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "default",
            {
                "type": "send.msg",
                        "json": action,
            },
        )
    except Exception:
        # errors while building messages and sending messages shall be ignored
        pass
