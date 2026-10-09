"""Ein DefaultConsumer fuehrt Buch nur ueber seine eigene Verbindung.

Channels instantiiert pro WebSocket-Verbindung genau EINE Consumer-Instanz
(AsyncConsumer.as_asgi -> cls(**initkwargs)) und kopiert Klassenattribute nicht
in die Instanz. Frueher war `messages` ein klassenweites Dict: alle Verbindungen
desselben worker-Prozesses teilten sich dadurch das Debounce-Fenster (ein Client
entwedert die anderen) und das Dict wuchs unbegrenzt, weil disconnect() nicht
aufgeraeumt hat. Beide Eigenschaften sind hier getestet, ebenso das
Subscribe-Protokoll, mit dem sich Verbindungen zu den Topics ihrer Anzeigen
zusammenschalten, und dass aus einem Topic ein Gruppennamen wird, den die
Kanaldiele akzeptiert (Topics enthalten ein "/", Gruppennamen nicht).

Diese Tests laufen ohne Datenbank und ohne echten Websocket-Stack. Ausfuehren:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test tests.django.notify.test_consumer_fanout \
        -v 3 --noinput
"""

from unittest.mock import MagicMock, patch

from channels.layers import BaseChannelLayer
from django.test import SimpleTestCase
from notify.consumers import DefaultConsumer
from notify.utils import group_name, send_msg


class RecordingChannelLayer:
    """Kanaldiele, die Gruppenbeitritte, -verlasse und Sends aufzeichnet."""

    def __init__(self):
        self.added = []
        self.discarded = []
        self.sent = []

    async def group_add(self, group, channel):
        self.added.append((group, channel))

    async def group_discard(self, group, channel):
        self.discarded.append((group, channel))

    async def group_send(self, group, message):
        self.sent.append((group, message))


class DefaultConsumerTests(SimpleTestCase):

    CHANNEL_NAME = "this-connections-channel"
    PROCESS_PK = "0f5b0dc8-3d3f-4c0a-9b1e-0d4d0f9d0a11"

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
        topic = f"resource/BackgroundProcess/{self.PROCESS_PK}"

        self.subscribe(consumer, topic)
        self.subscribe(consumer, topic)
        self.assertEqual(
            layer.added, [(group_name(topic), self.CHANNEL_NAME)],
            "ein Topic mehrfach zu joinen ist uberfluessig")

        self.subscribe(consumer, topic, action="unsubscribe")
        self.assertEqual(
            layer.discarded, [(group_name(topic), self.CHANNEL_NAME)])

    def test_a_topic_is_joined_as_a_group_name_the_layer_accepts(self):
        """Gruppennamen einer Kanaldiele duerfen kein Slash enthalten."""
        layer = BaseChannelLayer()

        for topic in ("resource/BackgroundProcess",
                      f"resource/BackgroundProcess/{self.PROCESS_PK}"):
            with self.subTest(topic=topic):
                self.assertTrue(
                    layer.require_valid_group_name(group_name(topic)),
                    "der Topic wurde unveraendelt als Gruppenname benutzt, was "
                    "channels/layers.py mit TypeError ablehnt und der Verbindung "
                    "den WebSocket schliesst")

    def test_the_publisher_sends_to_the_group_the_subscriber_joined(self):
        """send_msg und der Abonnent treffen sich im selben Gruppennamen."""
        topic = f"resource/BackgroundProcess/{self.PROCESS_PK}"
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)
        self.subscribe(consumer, topic)

        with patch("notify.utils.get_channel_layer", return_value=layer):
            send_msg(self.event(pk=self.PROCESS_PK)["json"])

        self.assertEqual(
            [(group, message["json"]["topic"])
             for group, message in layer.sent],
            [(group_name(topic), topic)],
            "die Nachricht muss in der Gruppe landen, die der Client joined hat, "
            "und muss dem Client ihren Topic unveraendelt nennen, weil er seine "
            "Abonnements an genau diesem String erkennt")
        self.assertEqual(consumer.topics, {topic})

    def test_topics_of_other_applications_are_rejected(self):
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)

        self.subscribe(consumer, "admin/whatever")
        consumer.receive_json({"action": "subscribe"})
        self.assertEqual(
            layer.added, [],
            "Gruppennamen sind ein gemeinsamer Namespace aller Verbindungen, "
            "deshalb werden nur resource/-Topics akzeptiert")

    def test_topics_which_cannot_become_a_group_name_are_rejected(self):
        """Nur Topics, die Gruppenname werden koennen, werden gejoint."""
        layer = RecordingChannelLayer()
        consumer = self.consumer(layer)

        for topic in ("resource/BackgroundProcess/1?all=1",
                      "resource/BackgroundProcess/1 2",
                      "resource/BackgroundProcess/1/2",
                      "resource/" + "x" * 100):
            with self.subTest(topic=topic):
                self.assertIsNone(group_name(topic))
                self.subscribe(consumer, topic)

        self.assertEqual(
            layer.added, [],
            "die Kanaldiele wirft solche Namen mit TypeError aus und beendet "
            "damit die Verbindung, also lieber gar nicht erst joinen")

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
