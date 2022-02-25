import json
from typing import OrderedDict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django_celery_results.models import TaskResult
from rest_framework_json_api.renderers import JSONRenderer
from simple_history.models import HistoricalRecords

from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer


def build_action_payload(request, instance):
    background_process = BackgroundProcess.objects.process_info().get(pk=instance.pk)

    action = json.loads('{}')

    if request and (not hasattr(request, "query_params") or not request.query_params):
        request.query_params = OrderedDict()
    task_serializer = BackgroundProcessSerializer(
        instance=background_process, **{"context": {"request": request}})
    renderer = JSONRenderer()

    class DummyView(object):
        resource_name = "BackgroundProcess"

    rendered_data = renderer.render(
        data=task_serializer.data,
        renderer_context={"view": DummyView(), "request": request}
    )

    action.update(
        {"payload": json.loads(rendered_data.decode("utf-8"))["data"]}
    )

    return action


@receiver(post_delete, sender=BackgroundProcess, dispatch_uid='update_BackgroundProcess_listeners_on_post_delete')
@receiver(post_save, sender=BackgroundProcess, dispatch_uid='update_BackgroundProcess_listeners_on_post_save')
def update_background_process_listeners_on_background_process_save_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        reducer_action = build_action_payload(
            request=request,
            instance=kwargs['instance']
        )

        if 'created' in kwargs:
            if kwargs['created']:
                # post_save signal --> new BackgroundProcess object
                reducer_action.update({"type": "backgroundProcesses/add"})
            else:
                reducer_action.update({"type": "backgroundProcesses/update"})
        else:
            # post_delete signal
            reducer_action.update({"type": "backgroundProcesses/remove"})

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "default",
            {
                "type": "send.msg",
                        "json": reducer_action,
            },
        )
    except Exception:
        # errors while building messages and sending messages shall be ignored
        pass


@receiver(post_delete, sender=TaskResult, dispatch_uid='update_BackgroundProcess_listeners_on_post_delete_TaskResult')
@receiver(post_save, sender=TaskResult, dispatch_uid='update_BackgroundProcess_listeners_on_post_save_TaskResult')
def update_background_process_listeners_on_task_result_save_delete(**kwargs):
    """
    Send the information to the channel group when a BackgroundProcess is created/modified
    """
    if hasattr(HistoricalRecords.context, "request"):
        request = HistoricalRecords.context.request
    else:
        return
    try:
        task_result = kwargs['instance']
        if not task_result.processes.exists():
            return
        background_process = task_result.processes.all()[0]
        reducer_action = build_action_payload(
            request=request,
            instance=background_process
        )
        reducer_action.update({"type": "backgroundProcesses/update"})

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "default",
            {
                "type": "send.msg",
                        "json": reducer_action,
            },
        )
    except Exception:
        # errors while building messages and sending messages shall be ignored
        pass
