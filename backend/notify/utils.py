import json
from collections import OrderedDict

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from rest_framework_json_api.renderers import JSONRenderer


def send_msg(msg, group=None, immediate=False):
    """Publishes msg to the channel layer group named after its topic.

    Connections join the group of every topic they display (see
    DefaultConsumer.receive_json), so a message is only written to the
    websockets that listen for it. immediate marks the messages the consumer
    must not collapse into its debounce window.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        group or msg["topic"],
        {
            "type": "send.msg",
                    "json": msg,
                    "immediate": immediate,
        },
    )


def send_msg_on_commit(msg, group=None, immediate=False):
    """Sends msg once the data it describes is visible to other connections.

    Clients refetch as soon as the message arrives, so a message that is sent
    while a transaction is still open makes them read the state from before the
    update. Outside of a transaction Django runs the callback immediately, so
    this only defers sends that happen inside atomic blocks.
    """
    transaction.on_commit(
        lambda: send_msg(msg=msg, group=group, immediate=immediate))


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

    class DummyView:
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
