"""A HarvestingJob announces its own progress over the websocket.

The frontend subscribes to the topic of what it displays: the run detail through
RealtimeShowContextProvider, the lists of runs through RealtimeListBase, which
additionally listens on the resource wide topic carrying the creates. Both name
the resource "HarvestingJob", so every phase transition of a job has to be
published to "resource/HarvestingJob/<pk>" respectively "resource/HarvestingJob".

progress, totalSteps and doneSteps are no model fields but annotations. A
payload built from the instance post_save hands over would not carry them and
the frontend, which replaces its record with the record of the message, would
show the job at 0 %. The receiver therefore selects the job through
HarvestingJob.objects.with_process_info() after the save, which is what the
payload assertions of these tests are about.

Run with:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        django-tests python manage.py test \
        tests.django.notify.test_harvesting_signals -v 3 --noinput
"""

from collections import OrderedDict
from unittest.mock import patch

from channels.layers import BaseChannelLayer
from django.test import TestCase
from django.utils.timezone import now
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

from notify.utils import group_name
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from tests.django.notify.test_consumer_fanout import RecordingChannelLayer


class HarvestingJobSignalsTest(TestCase):

    def setUp(self):
        # the receiver builds its payload with a request and stays quiet without
        # one; inside a celery task extras/tasks.py provides it
        self.request = APIRequestFactory().get(
            "/api/registry/harvesting/harvesting-jobs/")
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

    def job(self, **kwargs):
        """Creates a job which is downloading its 10 records in 2 round trips."""
        fields = {"total_records": 10, "max_step_size": 5,
                  "phase": Phase.DOWNLOAD_RECORDS.value}
        fields.update(kwargs)
        return HarvestingJob.objects.get(
            pk=HarvestingJob.objects.create(**fields).pk)

    def unhandled(self, job, count=1, has_import_error=False):
        # outside of publish_during(), because every TemporaryMdMetadataFile
        # schedules a celery task on commit
        for _ in range(count):
            TemporaryMdMetadataFile.objects.create(
                job=job, has_import_error=has_import_error)

    def attributes_of(self, message):
        return message["json"]["event"]["payload"]["records"][0]["attributes"]

    def test_created_job_is_announced_on_the_resource_wide_topic(self):
        self.publish_during(lambda: HarvestingJob.objects.create(
            total_records=10, max_step_size=5,
            phase=Phase.DOWNLOAD_RECORDS.value))

        self.assertEqual(len(self.layer.sent), 1)
        group, message = self.layer.sent[0]
        self.assertEqual(message["json"]["topic"], "resource/HarvestingJob")
        self.assertEqual(message["json"]["event"]["type"], "created")
        self.assertEqual(group, group_name("resource/HarvestingJob"))
        self.assertTrue(
            message["immediate"],
            "a client which misses the create of a job never learns of it")

    def test_phase_change_reaches_the_group_of_the_job_it_belongs_to(self):
        job = self.job()
        self.unhandled(job)
        job = HarvestingJob.objects.get(pk=job.pk)
        job.phase = Phase.RECORDS_TO_DB.value

        published = self.publish_during(lambda: job.save())

        self.assertEqual(len(published), 1)
        topic = f"resource/HarvestingJob/{job.pk}"
        group, message = published[0]
        self.assertEqual(message["json"]["topic"], topic)
        self.assertEqual(
            group, group_name(topic),
            "publisher and subscriber meet in the translated topic, which is "
            "what the channel layer accepts as group name")
        self.assertTrue(BaseChannelLayer().require_valid_group_name(group))
        self.assertEqual(message["json"]["event"]["type"], "updated")
        self.assertFalse(
            message["immediate"],
            "intermediate states may be collapsed by the consumer's debounce")

    def test_the_announcement_carries_the_progress_of_the_saved_state(self):
        job = self.job()
        self.unhandled(job)
        job = HarvestingJob.objects.get(pk=job.pk)
        job.phase = Phase.RECORDS_TO_DB.value

        _, message = self.publish_during(lambda: job.save())[0]
        attributes = self.attributes_of(message)
        annotated = HarvestingJob.objects.with_process_info().get(pk=job.pk)

        # 10 total_records / 5 max_step_size -> 2 download tasks, +1 for
        # call_fetch_total_records, one record still waiting to be imported
        self.assertEqual(attributes["totalSteps"], 13)
        self.assertEqual(attributes["doneSteps"], 12)
        self.assertAlmostEqual(attributes["progress"], 92.31, places=2)
        self.assertEqual(attributes["phase"], Phase.RECORDS_TO_DB.value)
        self.assertEqual(attributes["unhandledRecordsCount"], 1)
        self.assertEqual(attributes["importErrorCount"], 0)
        for field, value in (("totalSteps", annotated.total_steps),
                             ("doneSteps", annotated.done_steps),
                             ("progress", annotated.progress)):
            self.assertEqual(
                attributes[field], value,
                "the message must not tell a different progress than the "
                "endpoint the frontend reads the record from")

    def test_the_terminal_state_is_announced_immediately(self):
        job = self.job()
        job = HarvestingJob.objects.get(pk=job.pk)
        job.phase = Phase.COMPLETED.value
        job.done_at = now()

        _, message = self.publish_during(lambda: job.save())[0]

        self.assertTrue(
            message["immediate"],
            "a client which keeps showing a progress bar after this message "
            "never gets another one to finish it with")
        self.assertEqual(self.attributes_of(message)["progress"], 100.0)

    def test_records_with_an_import_error_do_not_count_as_unhandled(self):
        job = self.job()
        self.unhandled(job, count=1)
        self.unhandled(job, count=2, has_import_error=True)
        job = HarvestingJob.objects.get(pk=job.pk)

        _, message = self.publish_during(lambda: job.save())[0]
        attributes = self.attributes_of(message)

        self.assertEqual(attributes["unhandledRecordsCount"], 1)
        self.assertEqual(attributes["importErrorCount"], 2)

    def test_nothing_is_sent_without_a_request(self):
        job = self.job()
        job = HarvestingJob.objects.get(pk=job.pk)
        del HistoricalRecords.context.request

        published = self.publish_during(lambda: job.save())

        self.assertEqual(
            published, [],
            "the payload is rendered relative to a request; without one there "
            "is nothing to send and the receiver must not break the save")
