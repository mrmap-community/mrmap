import json
import re
from collections import OrderedDict

from asgiref.sync import async_to_sync
from channels.layers import BaseChannelLayer, get_channel_layer
from django.conf import settings
from django.db import transaction
from rest_framework_json_api.renderers import JSONRenderer

logger = settings.ROOT_LOGGER

# A topic is the path the frontend subscribes with (see build_action_payload
# below and DefaultConsumer.receive_json). Groups of a channel layer are named
# after them, but a group name may only hold ASCII alphanumerics, hyphens,
# underscores and periods and may not reach MAX_NAME_LENGTH characters
# (channels/layers.py: group_name_regex) - a "/" is not one of the allowed
# characters. Topics are therefore translated before they are handed to the
# channel layer. The segments deliberately exclude the ".": it is the character
# the separator becomes, so two different topics can never end up in the same
# group.
TOPIC_PATTERN = re.compile(r"resource/[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)?")


def group_name(topic):
    """Returns the name of the channel layer group which carries a topic.

    Returns None for everything which is not a topic of this application or too
    long to become a group name. Both sides of the fan out - the publisher here
    and the subscriber in notify/consumers.py - go through this function, so
    they always meet in the same group, and neither ever hands a name the layer
    rejects with a TypeError over.
    """
    if not isinstance(topic, str) or not TOPIC_PATTERN.fullmatch(topic):
        return None
    # the translation replaces every "/" by exactly one character, so the topic
    # is already as long as the name it becomes
    if len(topic) >= BaseChannelLayer.MAX_NAME_LENGTH:
        return None
    return topic.replace("/", ".")


def send_msg(msg, group=None, immediate=False):
    """Publishes msg to the channel layer group named after its topic.

    Connections join the group of every topic they display (see
    DefaultConsumer.receive_json), so a message is only written to the
    websockets that listen for it. immediate marks the messages the consumer
    must not collapse into its debounce window.
    """
    topic = group or msg.get("topic")
    name = group_name(topic)
    if name is None:
        # a message which no connection can subscribe to: worth a log line,
        # while the TypeError about the group name is not worth a stack trace
        logger.warning("can't send websocket message, %r is no topic", topic)
        return
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        name,
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
