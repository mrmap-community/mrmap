import json
from typing import OrderedDict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework_json_api.renderers import JSONRenderer


def send_msg(msg, group="default"):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group,
        {
            "type": "send.msg",
                    "json": msg,
        },
    )


def build_action_payload(request, instance, resource_type, serializer_cls, action):
    """ Returns the json payload for redux reducer actions """

    msg = json.loads('{}')

    if request and (not hasattr(request, "query_params") or not request.query_params):
        request.query_params = OrderedDict()

    task_serializer = serializer_cls(
        instance=instance,
        **{"context": {"request": request}}
    )

    renderer = JSONRenderer()

    class DummyView(object):
        resource_name = resource_type

    rendered_data = renderer.render(
        data=task_serializer.data,
        renderer_context={"view": DummyView(), "request": request}
    )
    # see https://marmelab.com/react-admin/RealtimeDataProvider.html#crud-events for recomendet datastructure
    msg.update(
        {
            "topic": f"resource/{resource_type}" if action == "created" else f"resource/{resource_type}/{instance.pk}",
            "event": {
                "type": action,
                "payload": {
                    "ids": [instance.id],
                    "records": [json.loads(rendered_data.decode("utf-8"))["data"]]
                },
            }
        }
    )
    return msg
