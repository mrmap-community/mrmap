"""Ein DefaultConsumer fuehrt Buch nur ueber seine eigene Verbindung.

Channels instantiiert pro WebSocket-Verbindung genau EINE Consumer-Instanz
(AsyncConsumer.as_asgi -> cls(**initkwargs)) und kopiert Klassenattribute nicht
in die Instanz. Frueher war `messages` ein klassenweites Dict: alle Verbindungen
desselben worker-Prozesses teilten sich dadurch das Debounce-Fenster (ein Client
entwedert die anderen) und das Dict wuchs unbegrenzt, weil disconnect() nicht
aufgeraeumt hat. Beide Eigenschaften sind hier getestet, ebenso das
Subscribe-Protokoll, mit dem sich Verbindungen zu den Topics ihrer Anzeigen
zusammenschalten.

Diese Tests laufen ohne Datenbank und ohne echten Websocket-Stack. Ausfuehren:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test tests.django.notify.test_consumer_fanout \
        -v 3 --noinput
"""

from unittest.mock import MagicMock

from django.test import SimpleTestCase
from notify.consumers import DefaultConsumer


class RecordingChannelLayer:
    """Kanaldiele, die Gruppenbeitritte und -verlasse aufzeichnet."""

    def __init__(self):
        self.added = []
        self.discarded = []

    async def group_add(self, group, channel):
        self.added.append((group, channel))

    async def group_discard(self, group, channel):
        self.discarded.append((group, channel))


class DefaultConsumerTests(SimpleTestCase):

    CHANNEL_NAME = "this-connections-channel"

    def consumer(self, channel_layer=None):
        consumer = DefaultConsumer()
        consumer.channel_layer = channel_layer or RecordingChannelLayer()
        consumer.channel_name = self.CHANNEL_NAME
        # send_json ist die Stelle, an der die Nachricht zum Client geht
        consumer.send_json = MagicMock()
        return consumer

    def event(self, pk=1, action="updated", immediate=False, phase="running"):
        topic = ("resource/BackgroundProcess" if action == "created"
                 else f"resource/BackgroundProcess/{pk}")
        return {
            "json": {
                "topic": topic,
                "event": {
                    "type": action,
                    "payload": {"ids": [pk], "records": [{
                        "id": str(pk),
                        "attributes": {"phase": phase}}]},
                },
            },
            "immediate": immediate,
        }

    def sent_phases(self, consumer):
        return [call.kwargs["content"]["event"]["payload"]["records"][0]
                ["attributes"]["phase"]
                for call in consumer.send_json.call_args_list]

    def subscribe(self, consumer, topic, action="subscribe"):
        consumer.receive_json({"action": action, "topic": topic})

    def test_every_connection_delivers_its_own_updated_event(self):
        """Zwei Clients desselben Prozesses muessen beide Updates bekommen."""
        first, second = self.consumer(), self.consumer()
        first.send_msg(self.event())
        second.send_msg(self.event())

        self.assertEqual(first.send_json.call_count, 1)
        self.assertEqual(
            second.send_json.call_count, 1,
            "der Versand an first darf second nicht aussperren: das Sende-"
            "Tracking haengt an der Verbindung, nicht an der Klasse")

    def test_intermediate_updates_are_collapsed(self):
        """Ein Prozess meldet jeden Schritt, die Nachrichten werden gebuendelt."""
        consumer = self.consumer()
        for _ in range(10):
            consumer.send_msg(self.event())

        self.assertEqual(
            consumer.send_json.call_count, 1,
            "jedes Payload enthaelt den kompletten Datensatz, ein Zwischenstand "
            "pro debounce-Intervall reicht")

    def test_immediate_event_bypasses_the_debounce_window(self):
        """Der letzte Zustand eines Prozesses darf nicht im Fenster untergehen."""
        consumer = self.consumer()
        consumer.send_msg(self.event())
        consumer.send_msg(self.event(phase="step 2"))
        consumer.send_msg(self.event(immediate=True, phase="completed"))

        self.assertEqual(
            self.sent_phases(consumer), ["running", "completed"],
            "eine Meldung ueber completed/failed/abort muss den Client immer "
            "erreichen, sonst haengt die Anzeige unter 100%")

    def test_subscribed_topic_is_joined_once_and_left(self):
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)

        self.subscribe(consumer, "resource/BackgroundProcess/1")
        self.subscribe(consumer, "resource/BackgroundProcess/1")
        self.assertEqual(
            layer.added, [("resource/BackgroundProcess/1", self.CHANNEL_NAME)],
            "ein Topic mehrfach zu joinen ist uberfluessig")

        self.subscribe(consumer, "resource/BackgroundProcess/1",
                       action="unsubscribe")
        self.assertEqual(
            layer.discarded,
            [("resource/BackgroundProcess/1", self.CHANNEL_NAME)])

    def test_topics_of_other_applications_are_rejected(self):
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)

        self.subscribe(consumer, "admin/whatever")
        consumer.receive_json({"action": "subscribe"})
        self.assertEqual(
            layer.added, [],
            "Gruppennamen sind ein gemeinsamer Namespace aller Verbindungen, "
            "deshalb werden nur resource/-Topics akzeptiert")

    def test_disconnect_leaves_topics_and_forgets_state(self):
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)
        for pk in range(5):
            self.subscribe(consumer, f"resource/BackgroundProcess/{pk}")
        consumer.send_msg(self.event())

        consumer.disconnect(1000)

        self.assertEqual(len(layer.discarded), 5,
                         "channels kuemmert sich nur um die statischen groups")
        self.assertEqual(consumer.topics, set())
        self.assertEqual(
            consumer.sent_at, {},
            "ohne Aufraeumen waechst das Tracking mit jedem Prozess, den die "
            "Verbindung je gesehen hat")
