from asgiref.sync import async_to_sync
from django.utils import timezone
from notify.auth import NonAnonymousJsonWebsocketConsumer


class DefaultConsumer(NonAnonymousJsonWebsocketConsumer):
    """Fan-out consumer of the /ws/default/ endpoint.

    A client declares which messages it wants with a subscribe frame and undoes
    it with an unsubscribe frame:

        {"action": "subscribe", "topic": "resource/BackgroundProcess/<uuid>"}

    notify.utils.send_msg publishes a message to the group named after its
    topic, so it only reaches the connections that subscribed to it.

    Channels creates ONE consumer instance per connection and never copies class
    attributes into it (channels.consumer.AsyncConsumer has no __init__, and
    WebsocketConsumer.__init__ only replaces groups when it is None). Anything
    mutable that is declared on the class is therefore shared by every
    connection of the worker process, which is why all per connection state is
    created in __init__.
    """

    groups = ['default']

    # minimum distance in ms between two messages of the same topic
    debounce = 1000

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # topic -> when the last message was sent over THIS connection
        self.sent_at = {}
        # topics the client asked for. self.groups must not be appended to: for
        # groups=['default'] it still is the class level list (websocket.py:27)
        self.topics = set()

    def send_msg(self, event):
        """Sends event, collapsing repeated progress messages of one topic.

        A background process reports on every single step and every message
        carries the complete record, so intermediate states can be dropped
        without losing information. Messages flagged as immediate are never
        dropped: that is the create event and the terminal state of a process,
        and a client which misses one keeps showing a progress bar that will
        never finish.
        """
        topic = event["json"]["topic"]
        now = timezone.now()
        sent_at = self.sent_at.get(topic)
        if (
            not event.get("immediate")
            and sent_at is not None
            and (now - sent_at).total_seconds() * 1000 < self.debounce
        ):
            return
        self.sent_at[topic] = now
        return super().send_msg(event)

    def receive_json(self, content, **kwargs):
        """Subscribes or unsubscribes the connection to the asked for topic."""
        topic = content.get("topic") if isinstance(content, dict) else None
        # group names are one flat namespace shared by every connection of the
        # deployment, so only topics of this application are accepted
        if not isinstance(topic, str) or not topic.startswith("resource/"):
            return
        action = content.get("action")
        if action == "subscribe":
            self._join_topic(topic)
        elif action == "unsubscribe":
            self._leave_topic(topic)

    def disconnect(self, code):
        # channels only removes the static groups, the requested topics and the
        # timestamp bookkeeping belong to this connection
        for topic in self.topics:
            async_to_sync(self.channel_layer.group_discard)(
                topic, self.channel_name)
        self.topics.clear()
        self.sent_at.clear()
        super().disconnect(code)

    def _join_topic(self, topic):
        if topic in self.topics:
            return
        async_to_sync(self.channel_layer.group_add)(topic, self.channel_name)
        self.topics.add(topic)

    def _leave_topic(self, topic):
        if topic not in self.topics:
            return
        async_to_sync(self.channel_layer.group_discard)(topic, self.channel_name)
        self.topics.discard(topic)
        self.sent_at.pop(topic, None)
