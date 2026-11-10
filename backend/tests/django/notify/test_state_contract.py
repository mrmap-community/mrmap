"""The state contract of the Background Job Center (#1207).

The drawer renders one row per background process. The state, the retry flag
and the error summary of that row are no columns of their own: they are
derived from the stored status, the celery states of the threads of the
process and its error logs, and read through the annotated queryset of
`process_info()` - which both the list endpoint and the websocket payloads go
through.
"""
import json

from celery import states
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now, timedelta
from django_celery_results.models import TaskResult
from notify.enums import (JobStateEnum, LogTypeEnum, ProcessNameEnum,
                          ProcessStatusEnum)
from notify.models import BackgroundProcess
from notify.serializers import BackgroundProcessSerializer
from rest_framework.test import APIRequestFactory, APIClient

JSONAPI = "application/vnd.api+json"


class JobStateTests(TestCase):
    """Tests the state which the drawer renders for each stored status."""

    def setUp(self):
        self.process = BackgroundProcess.objects.create(
            phase="running",
            process_type=ProcessNameEnum.HARVESTING.value,
            description="a harvesting")
        # the url field of the serializer builds absolute links, so it needs a
        # request - like the payload builder in notify/utils.py hands one
        self.context = {"request": APIRequestFactory().get(
            "/api/notify/background-processes/")}

    def report(self, status):
        BackgroundProcess.objects.report(self.process.pk, status)
        return BackgroundProcess.objects.process_info().get(pk=self.process.pk)

    def serialized(self, instance):
        return BackgroundProcessSerializer(instance, context=self.context).data

    def test_maps_each_stored_status_to_its_logical_state(self):
        for status, state in (
                (ProcessStatusEnum.PENDING, JobStateEnum.QUEUED),
                (ProcessStatusEnum.RUNNING, JobStateEnum.RUNNING),
                (ProcessStatusEnum.COMPLETED, JobStateEnum.COMPLETED),
                (ProcessStatusEnum.FAILED, JobStateEnum.FAILED),
                (ProcessStatusEnum.ABORTED, JobStateEnum.ABORTED)):
            BackgroundProcess.objects.filter(
                pk=self.process.pk).update(status=status, done_at=None)
            instance = BackgroundProcess.objects.process_info().get(
                pk=self.process.pk)

            self.assertEqual(
                state.value, self.serialized(instance)["state"],
                f"{status.label} must answer {state}")

    def test_answers_a_running_process_as_retrying_while_a_thread_retries(self):
        task_result = TaskResult.objects.create(
            task_id="11111111-1111-1111-1111-111111111111",
            status=states.RETRY)
        self.report(ProcessStatusEnum.RUNNING)
        self.process.threads.add(task_result)

        instance = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)
        answer = self.serialized(instance)

        self.assertTrue(answer["is_retrying"])
        self.assertEqual(JobStateEnum.RETRYING.value, answer["state"])

    def test_answers_a_finished_thread_as_plain_running(self):
        task_result = TaskResult.objects.create(
            task_id="22222222-2222-2222-2222-222222222222",
            status=states.SUCCESS)
        self.report(ProcessStatusEnum.RUNNING)
        self.process.threads.add(task_result)

        instance = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)
        answer = self.serialized(instance)

        self.assertFalse(answer["is_retrying"])
        self.assertEqual(JobStateEnum.RUNNING.value, answer["state"])

    def test_answers_the_last_error_of_the_process_as_its_error_summary(self):
        BackgroundProcess.objects.log(
            self.process.pk, "the first failure")
        BackgroundProcess.objects.log(
            self.process.pk, "the remote service is still unreachable")
        BackgroundProcess.objects.log(
            self.process.pk, "a record could not be read",
            log_type=LogTypeEnum.WARNING)

        instance = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)

        self.assertEqual(
            "the remote service is still unreachable",
            self.serialized(instance)["error_summary"])

    def test_answers_no_error_summary_without_error_logs(self):
        instance = BackgroundProcess.objects.process_info().get(
            pk=self.process.pk)

        self.assertIsNone(self.serialized(instance)["error_summary"])
        self.assertFalse(self.serialized(instance)["is_retrying"])

    def test_answers_an_unannotated_instance_without_failing(self):
        # the signal paths re-read the process through process_info(), but a
        # serializer which is handed a plain row must still answer the contract
        self.report(ProcessStatusEnum.RUNNING)
        instance = BackgroundProcess.objects.get(pk=self.process.pk)
        answer = self.serialized(instance)

        self.assertEqual(JobStateEnum.RUNNING.value, answer["state"])
        self.assertFalse(answer["is_retrying"])
        self.assertIsNone(answer["error_summary"])


class JobCenterApiTests(TestCase):
    """Tests the state contract and the history window as the api answers them.

    The drawer and its history read these fields over the same endpoint the
    overview already uses: the state of every row and a window over the times
    a process was created and decided about.
    """

    def setUp(self):
        self.client = APIClient()
        self.client.credentials(HTTP_ACCEPT=JSONAPI)
        self.yesterday = BackgroundProcess.objects.create(
            phase="completed",
            process_type=ProcessNameEnum.MONITORING.value,
            description="yesterday's monitoring",
            status=ProcessStatusEnum.COMPLETED,
            date_created=now() - timedelta(days=2),
            done_at=now() - timedelta(days=2))
        self.today = BackgroundProcess.objects.create(
            phase="completed",
            process_type=ProcessNameEnum.HARVESTING.value,
            description="today's harvesting",
            status=ProcessStatusEnum.COMPLETED,
            date_created=now() - timedelta(hours=2),
            done_at=now() - timedelta(hours=2))

    def listed(self, **query_params):
        response = self.client.get(
            reverse("notify:backgroundprocess-list"), query_params)

        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)

    def attributes(self, **query_params):
        return {process["attributes"]["description"]: process["attributes"]
                for process in self.listed(**query_params)["data"]}

    def test_answers_the_state_and_the_retry_of_every_listed_process(self):
        attributes = self.attributes()

        self.assertEqual(
            JobStateEnum.COMPLETED.value,
            attributes["today's harvesting"]["state"])
        self.assertFalse(
            attributes["today's harvesting"]["isRetrying"])
        self.assertIsNone(
            attributes["today's harvesting"]["errorSummary"])

    def test_counts_only_the_processes_which_decided_after_a_time(self):
        # the tile "Completed (24 h)" of the drawer counts the completions of
        # the last day by the time the processes were decided about
        listed = self.listed(
            **{"filter[status]": "completed",
               "filter[doneAt.gt]": (now() - timedelta(days=1)).isoformat()})

        self.assertEqual(
            [str(self.today.pk)],
            [process["id"] for process in listed["data"]])

    def test_lists_only_the_processes_which_started_before_a_time(self):
        # the history tab pages the older processes up by their creation time
        listed = self.listed(
            **{"filter[dateCreated.lt]": (now() - timedelta(days=1)).isoformat()})

        self.assertEqual(
            [str(self.yesterday.pk)],
            [process["id"] for process in listed["data"]])

    def test_answers_the_state_contract_in_the_detail_view_too(self):
        # the websocket payload of a process is built by the same serializer
        # over an instance of process_info(); the detail view is its stand-in
        # here (the delivery of the payloads is pinned by test_signals.py)
        response = self.client.get(reverse(
            "notify:backgroundprocess-detail", kwargs={"pk": self.today.pk}))

        attributes = json.loads(response.content)["data"]["attributes"]

        self.assertEqual(JobStateEnum.COMPLETED.value, attributes["state"])
        self.assertIs(attributes["isRetrying"], False)
        self.assertIsNone(attributes["errorSummary"])
