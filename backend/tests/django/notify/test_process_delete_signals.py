"""A deleted BackgroundProcess announces itself over the websocket.

Clients display a process in the overview lists (RealtimeListBase subscribes
to the resource wide topic and to the topic of every visible row) and on an
open process screen (RealtimeShowContextProvider). A deletion which is never
announced leaves the row of a gone process in every open list and keeps a
screen rendering work whose row does not exist anymore.

Until #1456 that announcement never fired: the receiver built its payload
from a reload through process_info() of the row which post_delete reports as
just deleted - always ObjectDoesNotExist, always swallowed by the exception
handler, so no message ever went out. The payload is built from the instance
the signal hands over now; the deletion collector passes the fetched row, so
every stored field is on it, and a bulk delete - the retention sweep of
#1208 - delivers the same signal per collected instance. The annotations of
process_info() are the exception: state derives from the stored fields and
progress stays out of the payload, because a client which learns of a
deletion refetches its list instead of replacing a record.

Run with:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test \
        tests.django.notify.test_process_delete_signals -v 3 --noinput
"""

from collections import OrderedDict
from unittest.mock import patch

from django.test import TestCase
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from notify.utils import group_name
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

from tests.django.notify.test_consumer_fanout import RecordingChannelLayer


class BackgroundProcessDeleteSignalsTest(TestCase):

    def setUp(self):
        # the receiver builds its payload with a request and stays quiet
        # without one; in production the web request or, inside a celery
        # task, extras/tasks.py provides it
        self.request = APIRequestFactory().get(
            "/api/notify/background-processes/")
        self.request.query_params = OrderedDict()
        HistoricalRecords.context.request = self.request
        self.layer = RecordingChannelLayer()

    def tearDown(self):
        if hasattr(HistoricalRecords.context, "request"):
            del HistoricalRecords.context.request

    def publish_during(self, action):
        """Runs action and returns the (group, message) pairs it published."""
        before = len(self.layer.sent)
        with patch("notify.utils.get_channel_layer", return_value=self.layer):
            with self.captureOnCommitCallbacks(execute=True):
                action()
        return self.layer.sent[before:]

    def process(self, **kwargs):
        fields = {"phase": "a phase",
                  "process_type": ProcessNameEnum.MONITORING.value,
                  "description": "a process"}
        fields.update(kwargs)
        # outside of publish_during(): the create announcement is not what
        # these tests assert, and its pending message stays out of the
        # capture which only executes the callbacks of its own block
        return BackgroundProcess.objects.create(**fields)

    def attributes_of(self, message):
        return message["json"]["event"]["payload"]["records"][0]["attributes"]

    def test_a_deleted_process_is_announced_on_the_topic_of_its_row(self):
        """The deletion of one process reaches the groups of its topic.

        This is the red test of #1456: while the receiver reloaded the
        already deleted row, the exception was swallowed and this group
        never saw a single message.
        """
        process = self.process()
        # Model.delete() hands the pk over: the collector nulls it on the
        # instance afterwards, so the expectation has to be read before
        pk = process.pk

        published = self.publish_during(lambda: process.delete())

        topic = f"resource/BackgroundProcess/{pk}"
        self.assertEqual(1, len(published),
                         "the deletion was announced once - or, before the "
                         "fix, not at all")
        group, message = published[0]
        self.assertEqual(
            group_name(topic), group,
            "publisher and subscriber meet in the translated topic, which "
            "is what the channel layer accepts as group name")
        self.assertEqual(topic, message["json"]["topic"])
        self.assertEqual("delete", message["json"]["event"]["type"])
        self.assertEqual([pk], message["json"]["event"]["payload"]["ids"])
        self.assertTrue(
            message["immediate"],
            "a deleted record which is collapsed away by the debounce stays "
            "visible in every open list until the next unrelated refresh")
        self.assertFalse(BackgroundProcess.objects.filter(pk=pk).exists())

    def test_the_announcement_answers_the_stored_fields_of_the_gone_row(self):
        """The payload is built from the instance, not from a reload.

        Every stored field the deletion collector handed over renders into
        the record, the state derives from them like the endpoint derives
        it, and the annotation of process_info() which cannot be answered
        from a gone row stays out of the payload instead of breaking the
        whole message.
        """
        process = self.process(
            status=ProcessStatusEnum.FAILED,
            description="the run which failed",
            total_steps=5, done_steps=3)
        # read before the delete: the collector nulls the pk on the instance
        pk, revision = process.pk, process.revision

        _, message = self.publish_during(lambda: process.delete())[0]
        record = message["json"]["event"]["payload"]["records"][0]
        attributes = self.attributes_of(message)

        self.assertEqual(str(pk), record["id"])
        self.assertEqual("the run which failed", attributes["description"])
        self.assertEqual("failed", attributes["status"])
        self.assertEqual(
            "failed", attributes["state"],
            "state has no stored field of its own; the serializer derives "
            "it from the fields the handed over instance still answers")
        self.assertEqual(revision, attributes["revision"])
        self.assertIsNone(
            attributes["errorSummary"],
            "the log entries cascaded with the process, so the fallback "
            "which reads them finds nothing - which is the honest answer")
        self.assertNotIn(
            "progress", attributes,
            "the annotation of process_info() cannot be answered from a "
            "deleted row; a client which learns of a deletion refetches "
            "instead of replacing a record")

    def test_a_bulk_delete_announces_every_collected_process(self):
        """The retention sweep of #1208 deletes through a queryset.

        QuerySet.delete() sends post_delete per collected instance - the
        collector cannot fast-delete a model with a connected listener -
        and each of those instances carries its stored fields, so every
        process the sweep takes back disappears from the open lists of the
        clients which show it.
        """
        gone = [self.process(description=f"gone {i}") for i in range(3)]
        kept = self.process(description="kept")

        published = self.publish_during(
            lambda: BackgroundProcess.objects.filter(
                pk__in=[process.pk for process in gone]).delete())

        self.assertEqual(
            {str(process.pk) for process in gone},
            {message["json"]["event"]["payload"]["records"][0]["id"]
             for _, message in published},
            "each deleted process announced itself once on its own topic")
        for _, message in published:
            self.assertEqual("delete", message["json"]["event"]["type"])
        self.assertNotIn(
            str(kept.pk),
            {message["json"]["event"]["payload"]["records"][0]["id"]
             for _, message in published},
            "a process the sweep kept must not vanish from a client's list")
        self.assertTrue(BackgroundProcess.objects.filter(
            pk=kept.pk).exists())

    def test_nothing_is_sent_without_a_request(self):
        process = self.process()
        del HistoricalRecords.context.request

        published = self.publish_during(lambda: process.delete())

        self.assertEqual(
            published, [],
            "the payload is rendered relative to a request; without one "
            "there is nothing to send and the receiver must not break the "
            "deletion")
        self.assertFalse(BackgroundProcess.objects.filter(pk=process.pk).exists())
