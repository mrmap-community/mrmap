import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now, timedelta
from guardian.shortcuts import assign_perm
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.models.service import WebMapService
from rest_framework.test import APIClient

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
