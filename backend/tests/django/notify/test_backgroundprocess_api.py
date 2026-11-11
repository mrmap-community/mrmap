import json
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now, timedelta
from guardian.shortcuts import assign_perm
from notify.enums import (LogTypeEnum, ProcessNameEnum, ProcessStatusEnum)
from notify.models import BackgroundProcess, BackgroundProcessLog
from notify.serializers import BackgroundProcessSerializer
from registry.models.service import WebMapService
from rest_framework.test import APIClient, APIRequestFactory

JSONAPI = "application/vnd.api+json"
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class BackgroundProcessApiTests(TestCase):
    """Tests the api of the overview of the background activity.

    The overview answers what the deployment is doing, so it is filtered by the
    statuses the overview offers and sorted by the time a process was created. A
    user only sees the processes of the resources he may see, and the resource of
    a process decides who may abort it.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        self.service = WebMapService.objects.get(pk=WMS_PK)
        # a superuser sees and decides every process, so the queries of the
        # overview itself are answered with him
        self.client = self.client_for(get_user_model().objects.create_superuser(
            username="overview", password="test"))
        self.user_client = self.client_for(self.user)
        self.pending = self.create(
            "pending", ProcessStatusEnum.PENDING, seconds_ago=3)
        self.running = self.create(
            "running", ProcessStatusEnum.RUNNING, related=self.service,
            seconds_ago=2)
        self.completed = self.create(
            "completed", ProcessStatusEnum.COMPLETED, seconds_ago=1)

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        # without an explicit accept the browsable api renderer is used
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    @staticmethod
    def create(phase, status, related=None, seconds_ago=0):
        return BackgroundProcess.objects.create(
            phase=phase,
            process_type=ProcessNameEnum.MONITORING.value,
            description=f"a {phase} process",
            status=status,
            date_created=now() - timedelta(seconds=seconds_ago),
            related_resource_type=ContentType.objects.get_for_model(
                WebMapService) if related is not None else None,
            related_id=related.pk if related is not None else None)

    def listed(self, client=None, **query_params):
        response = (client or self.client).get(
            reverse("notify:backgroundprocess-list"), query_params)

        self.assertEqual(response.status_code, 200)
        return [process["id"] for process in json.loads(
            response.content)["data"]]

    def test_filters_the_processes_by_the_status_of_the_overview(self):
        self.assertEqual(
            {str(self.pending.pk), str(self.running.pk)},
            set(self.listed(**{"filter[status]": "pending,running"})))

    # the history screen of the frontend searches the past by its moments, so
    # both of the moments a process names are filterable facets (#1208). The
    # api addresses the fields by their camelCase json:api names, as the
    # frontend sends them
    def test_filters_the_history_by_the_moment_it_was_created(self):
        self.assertEqual(
            [str(self.pending.pk)],
            self.listed(**{
                "filter[dateCreated.lt]": self.running.date_created.isoformat()}))
        self.assertEqual(
            [str(self.completed.pk), str(self.running.pk)],
            self.listed(**{
                "filter[dateCreated.gt]": self.pending.date_created.isoformat()}))
        # the range includes both of its ends, so the moment of the pending
        # process as its start still answers that process itself
        self.assertEqual(
            [str(self.completed.pk), str(self.running.pk)],
            self.listed(**{
                "filter[dateCreated.range]": ",".join([
                    self.running.date_created.isoformat(),
                    self.completed.date_created.isoformat()])}))

    def test_filters_the_history_by_the_moment_a_process_decided(self):
        self.completed.done_at = self.completed.date_created + timedelta(minutes=2)
        self.completed.save()

        self.assertEqual(
            [str(self.completed.pk)],
            self.listed(**{
                "filter[doneAt.gte]": (now() - timedelta(hours=1)).isoformat()}))

    # the history answers how long a decided process took, which the show
    # screen of the frontend renders beside its timestamps (#1208)
    def test_answers_the_duration_of_a_decided_process(self):
        self.completed.done_at = self.completed.date_created + timedelta(minutes=2)
        self.completed.save()

        response = self.client.get(reverse(
            "notify:backgroundprocess-detail", kwargs={"pk": self.completed.pk}))

        self.assertEqual(
            120.0,
            json.loads(response.content)["data"]["attributes"]["duration"])

    def test_answers_no_duration_while_the_process_runs(self):
        response = self.client.get(reverse(
            "notify:backgroundprocess-detail", kwargs={"pk": self.running.pk}))

        self.assertIsNone(json.loads(
            response.content)["data"]["attributes"]["duration"])

    def test_sorts_the_processes_by_the_time_they_were_created(self):
        expected = [str(self.completed.pk), str(self.running.pk),
                    str(self.pending.pk)]

        self.assertEqual(expected, self.listed())
        self.assertEqual(
            [str(self.running.pk), str(self.pending.pk)],
            self.listed(**{"filter[status]": "pending,running"}))
        self.assertEqual(expected[::-1], self.listed(sort="dateCreated"))

    def test_answers_the_resource_of_a_process_by_type_and_id(self):
        response = self.client.get(reverse(
            "notify:backgroundprocess-detail", kwargs={"pk": self.running.pk}))

        self.assertEqual(response.status_code, 200)
        attributes = json.loads(response.content)["data"]["attributes"]
        self.assertEqual(
            {"type": "WebMapService", "id": str(self.service.pk)},
            attributes["relatedResource"])
        self.assertEqual("running", attributes["status"])

    def test_answers_no_resource_for_a_process_without_one(self):
        response = self.client.get(reverse(
            "notify:backgroundprocess-detail",
            kwargs={"pk": self.pending.pk}))

        self.assertIsNone(json.loads(
            response.content)["data"]["attributes"]["relatedResource"])

    def test_answers_only_the_processes_of_the_resources_the_user_may_view(self):
        self.assertEqual(
            {str(self.completed.pk), str(self.pending.pk)},
            set(self.listed(client=self.user_client)))

        assign_perm("registry.view_webmapservice", self.user, self.service)

        self.assertEqual(
            {str(self.completed.pk), str(self.running.pk), str(self.pending.pk)},
            set(self.listed(client=self.user_client)))

    def abort(self, process, client=None):
        with patch.object(
                BackgroundProcess, "get_related_task_ids", return_value=[]):
            return (client or self.client).patch(
                reverse("notify:backgroundprocess-detail",
                        kwargs={"pk": process.pk}),
                {"data": {"type": "BackgroundProcess", "id": str(process.pk),
                          "attributes": {"phase": "abort"}}},
                format="vnd.api+json")

    def test_aborts_a_process_of_a_resource_the_user_may_change(self):
        assign_perm("registry.view_webmapservice", self.user, self.service)
        assign_perm("registry.change_webmapservice", self.user, self.service)

        response = self.abort(self.running, client=self.user_client)

        self.assertEqual(response.status_code, 200)
        self.running.refresh_from_db()
        self.assertEqual(ProcessStatusEnum.ABORTED, self.running.status)
        self.assertEqual(
            "aborted",
            json.loads(response.content)["data"]["attributes"]["status"])

    def test_aborts_a_process_without_a_resource_for_a_superuser(self):
        response = self.abort(self.pending)

        self.assertEqual(response.status_code, 200)
        self.pending.refresh_from_db()
        self.assertEqual(ProcessStatusEnum.ABORTED, self.pending.status)

    def test_refuses_an_abort_without_the_permission_of_the_resource(self):
        # the user sees the process of the service but may not change it
        assign_perm("registry.view_webmapservice", self.user, self.service)

        self.assertEqual(
            self.abort(self.running, client=self.user_client).status_code, 403)

    def test_refuses_an_abort_of_an_anonymous_client(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_ACCEPT=JSONAPI)

        self.assertEqual(
            self.abort(self.pending, client=anonymous).status_code, 403)


class BackgroundProcessProgressSortTests(TestCase):
    """The overview sorts by the progress it renders.

    ``progress`` is no model field but an annotation of ``process_info()`` -
    completed processes at 100, processes which do not know their steps at 0
    and the rest at the share of their done steps. The failed-jobs view of the
    frontend asks for exactly this sort, which the viewset answered with a 400
    until the annotation entered its whitelist (issue #1035).
    """

    @classmethod
    def setUpTestData(cls):
        cls.none = cls.create("none", ProcessStatusEnum.RUNNING, seconds_ago=3)
        cls.half = cls.create("half", ProcessStatusEnum.RUNNING,
                              total_steps=8, done_steps=2, seconds_ago=2)
        cls.done = cls.create("done", ProcessStatusEnum.COMPLETED,
                              total_steps=8, done_steps=8, seconds_ago=1)

    def setUp(self):
        # a superuser sees every process, so the overview is asked with him
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="progress", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    @staticmethod
    def create(name, status, total_steps=None, done_steps=0, seconds_ago=0):
        return BackgroundProcess.objects.create(
            phase=f"process {name}",
            process_type=ProcessNameEnum.MONITORING.value,
            description=f"a process {name}",
            status=status,
            total_steps=total_steps,
            done_steps=done_steps,
            date_created=now() - timedelta(seconds=seconds_ago))

    def listed(self, **query_params):
        response = self.client.get(
            reverse("notify:backgroundprocess-list"), query_params)
        self.assertEqual(response.status_code, 200)
        return [process["id"] for process in
                response.json()["data"]]

    def test_sorts_the_processes_by_their_progress(self):
        self.assertEqual(
            [str(self.none.pk), str(self.half.pk), str(self.done.pk)],
            self.listed(sort="progress"))

    def test_sorts_the_processes_by_their_progress_descending(self):
        self.assertEqual(
            [str(self.done.pk), str(self.half.pk), str(self.none.pk)],
            self.listed(sort="-progress"))

    def test_a_sort_the_process_does_not_have_is_still_rejected(self):
        response = self.client.get(
            reverse("notify:backgroundprocess-list"),
            {"sort": "not_a_field"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "invalid")


class BackgroundProcessOperationContractTests(TestCase):
    """The additive operation contract of the background job center (#1207).

    The drawer of the frontend renders one operation by asking a handful of
    questions: in which state is it, how far did it get, what went wrong, what
    does it wait for, which resource does it belong to and which of its
    reports is the newest. All of them are answered by the list and the detail
    of a background process - derived from what its reporters store, so a
    screen never assembles a state out of columns itself.

    Everything this class asserts is additive to the answers of #1035: the
    status, the progress and the date sort of an overview stay as they are.
    """

    @classmethod
    def setUpTestData(cls):
        # one resource with several operations on it is the grouping of the
        # drawer: the processes of a service belong to one another
        cls.resource = uuid4()
        cls.wms = ContentType.objects.get_for_model(WebMapService)
        cls.queued = cls.make("queued", ProcessStatusEnum.PENDING)
        cls.running = cls.make("running", ProcessStatusEnum.RUNNING,
                               total=4, done=1, related=cls.resource)
        cls.indeterminate = cls.make(
            "indeterminate", ProcessStatusEnum.RUNNING, done=1)
        cls.retrying = cls.make(
            "retrying", ProcessStatusEnum.RUNNING, total=4,
            related=cls.resource,
            retry_scheduled_until=now() + timedelta(hours=1),
            retry_count=2, retry_reason="the remote did not answer")
        cls.attention = cls.make(
            "attention", ProcessStatusEnum.RUNNING, total=4,
            action_required=True)
        cls.failed = cls.make("failed", ProcessStatusEnum.FAILED, total=4)
        BackgroundProcessLog.objects.create(
            background_process=cls.failed, log_type=LogTypeEnum.ERROR,
            description="the capabilities did not answer")

    @classmethod
    def make(cls, name, status, total=None, done=0, related=None, **extra):
        return BackgroundProcess.objects.create(
            phase=f"phase of {name}",
            process_type=ProcessNameEnum.MONITORING.value,
            description=f"the {name} operation",
            status=status, total_steps=total, done_steps=done,
            related_resource_type=cls.wms if related else None,
            related_id=related, **extra)

    def setUp(self):
        # a superuser sees every process, so the contract is asked undisturbed
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username="contract", password="test"))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def attributes(self, process):
        response = self.client.get(
            reverse("notify:backgroundprocess-detail",
                    kwargs={"pk": process.pk}))
        self.assertEqual(response.status_code, 200)
        return json.loads(response.content)["data"]["attributes"]

    def listed(self, **query_params):
        response = self.client.get(
            reverse("notify:backgroundprocess-list"), query_params)
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)["data"]

    def test_answers_the_state_of_every_process(self):
        """one question per rendered operation, answered by one attribute"""
        answered = {row["id"]: row["attributes"]["state"]
                    for row in self.listed()}
        self.assertEqual(
            {str(self.queued.pk): "queued",
             str(self.running.pk): "running",
             str(self.indeterminate.pk): "running_indeterminate",
             str(self.retrying.pk): "retrying",
             str(self.attention.pk): "action_required",
             str(self.failed.pk): "failed"},
            answered)

    def test_answers_what_the_operation_failed_on(self):
        self.assertEqual(
            "the capabilities did not answer",
            self.attributes(self.failed)["errorSummary"])
        self.assertIsNone(self.attributes(self.running)["errorSummary"])

    def test_answers_the_progress_with_its_numerator_and_denominator(self):
        attributes = self.attributes(self.running)
        self.assertEqual(4, attributes["totalSteps"])
        self.assertEqual(1, attributes["doneSteps"])
        self.assertEqual(25.0, attributes["progress"])
        # an operation which does not know its steps answers no denominator -
        # and the drawer renders it with an indeterminate bar
        attributes = self.attributes(self.indeterminate)
        self.assertIsNone(attributes["totalSteps"])
        self.assertEqual("running_indeterminate", attributes["state"])

    def test_answers_the_retry_state_of_an_operation(self):
        attributes = self.attributes(self.retrying)
        self.assertEqual(2, attributes["retryCount"])
        self.assertEqual("the remote did not answer",
                         attributes["retryReason"])
        self.assertIsNotNone(attributes["retryScheduledUntil"])

    def test_answers_no_retry_state_where_nothing_was_retried(self):
        attributes = self.attributes(self.running)
        self.assertEqual(0, attributes["retryCount"])
        self.assertEqual("", attributes["retryReason"])
        self.assertIsNone(attributes["retryScheduledUntil"])

    def test_answers_the_revision_which_orders_the_reports(self):
        self.assertEqual(0, self.attributes(self.running)["revision"])

        BackgroundProcess.objects.report(
            self.running.pk, ProcessStatusEnum.RUNNING, step_done=True)

        self.assertEqual(1, self.attributes(self.running)["revision"])

    def test_answers_the_flag_of_a_standing_operation_only_as_its_state(self):
        """one question, one answer: the flag behind the state is no second
        truth a client has to weigh against it (#1207)"""
        attributes = self.attributes(self.attention)
        self.assertEqual("action_required", attributes["state"])
        self.assertNotIn("actionRequired", attributes)
        self.assertNotIn("action_required", attributes)

    def test_groups_the_operations_of_one_resource_by_their_related_id(self):
        listed = self.listed(**{"filter[relatedId.in]": str(self.resource)})
        self.assertEqual(
            {str(self.running.pk), str(self.retrying.pk)},
            {row["id"] for row in listed})
        self.assertEqual(
            {str(self.running.pk), str(self.retrying.pk)},
            {row["id"] for row in self.listed(
                **{"filter[relatedId]": str(self.resource)})})

    def test_filters_the_processes_by_the_state_the_drawer_renders(self):
        self.assertEqual(
            [str(self.running.pk)],
            [row["id"] for row in self.listed(**{"filter[state]": "running"})])
        self.assertEqual(
            {str(self.queued.pk), str(self.failed.pk)},
            {row["id"] for row in self.listed(
                **{"filter[state.in]": "queued,failed"})})
        self.assertEqual(
            [], self.listed(**{"filter[state]": "aborted"}))

    def test_refuses_a_state_the_api_does_not_answer(self):
        response = self.client.get(
            reverse("notify:backgroundprocess-list"),
            {"filter[state]": "strolling"}, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(
            response.json()["errors"][0]["code"], "invalid_choice")

    def test_sorts_the_processes_by_their_state(self):
        """the drawer sorts its tabs by the state it renders; the state is no
        column but the annotation of the overview, so the sort had to enter the
        whitelist with it. The names order alphabetically - and every name of
        the contract begins with a different letter but one pair."""
        self.assertEqual(
            ["action_required", "failed", "queued", "retrying",
             "running", "running_indeterminate"],
            [row["attributes"]["state"] for row in self.listed(sort="state")])

    def test_sorts_the_processes_by_their_revision(self):
        BackgroundProcess.objects.report(
            self.queued.pk, ProcessStatusEnum.RUNNING)

        revisions = [int(row["attributes"]["revision"])
                     for row in self.listed(sort="-revision")]
        self.assertEqual(sorted(revisions, reverse=True), revisions)
        self.assertEqual(1, revisions[0])

    def test_derives_the_state_of_a_process_without_the_annotation(self):
        """the answer of the asynchronous api renders the instance it just
        created, which carries no annotation of the overview yet"""
        process = BackgroundProcess.objects.create(
            phase="just created",
            process_type=ProcessNameEnum.HARVESTING.value,
            description="a process which was just made",
            status=ProcessStatusEnum.RUNNING, total_steps=5, done_steps=2,
            retry_scheduled_until=now() + timedelta(hours=1))
        request = APIRequestFactory().get("/")
        context = {"request": request}

        def answered():
            return BackgroundProcessSerializer(
                process, context=context).data

        # the serializer answers its declared fields flat; the nesting into
        # "attributes" and the camel case are the renderer's
        self.assertEqual("retrying", answered()["state"])
        self.assertIsNone(answered()["error_summary"])
        process.retry_scheduled_until = None
        self.assertEqual("running", answered()["state"])
        # an instance which was not read through process_info() answers the
        # summary of its errors for itself
        BackgroundProcessLog.objects.create(
            background_process=process, log_type=LogTypeEnum.ERROR,
            description="the catalogue did not answer")
        self.assertEqual(
            "the catalogue did not answer", answered()["error_summary"])
