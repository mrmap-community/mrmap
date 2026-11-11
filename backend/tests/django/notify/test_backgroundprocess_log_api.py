import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now, timedelta
from guardian.shortcuts import assign_perm
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.models.service import WebMapService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class BackgroundProcessLogApiTests(TestCase):
    """Tests the api of the error details a background process left behind.

    A log entry carries the error detail of work done on a resource, so it
    belongs to whoever may read the process it reports on: the api answers the
    logs of the processes the user may see and nothing else (#1208). The
    history asks which errors one process left behind, and the job drawer
    reads them newest report first.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json"]

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        self.service = WebMapService.objects.get(pk=WMS_PK)
        # a superuser sees every process, so the unrestricted reads are asked
        # of with him
        self.client = self.client_for(get_user_model().objects.create_superuser(
            username="logs", password="test"))
        self.user_client = self.client_for(self.user)
        # a process of a service the user may not see and one which names no
        # resource at all: exactly the pair the visibility decides differently
        self.hidden = BackgroundProcess.objects.create(
            phase="failed",
            process_type=ProcessNameEnum.REGISTERING.value,
            description="a registering process",
            status=ProcessStatusEnum.FAILED,
            related_resource_type=ContentType.objects.get_for_model(
                WebMapService),
            related_id=self.service.pk)
        self.visible = BackgroundProcess.objects.create(
            phase="failed",
            process_type=ProcessNameEnum.MONITORING.value,
            description="a process without a resource",
            status=ProcessStatusEnum.FAILED)
        self.hidden_log = self.log(self.hidden, "the hidden error", seconds_ago=2)
        self.visible_log = self.log(self.visible, "the visible error", seconds_ago=1)

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        # without an explicit accept the browsable api renderer is used
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    @staticmethod
    def log(process, description, seconds_ago=0):
        """A log entry whose date is the moment the history sorts by."""
        entry = BackgroundProcessLog.objects.create(
            background_process=process,
            log_type=LogTypeEnum.ERROR,
            description=description)
        entry.date = now() - timedelta(seconds=seconds_ago)
        entry.save()
        return entry

    def listed(self, client=None, **query_params):
        response = (client or self.client).get(
            reverse("notify:backgroundprocesslog-list"), query_params)

        self.assertEqual(response.status_code, 200)
        return [entry["id"] for entry in json.loads(
            response.content)["data"]]

    def test_answers_every_log_to_the_superuser(self):
        self.assertEqual(
            {str(self.hidden_log.pk), str(self.visible_log.pk)},
            set(self.listed()))

    def test_answers_only_the_logs_of_the_processes_the_user_may_see(self):
        # the user may not see the service, so he may not read the error the
        # registering on it reported
        self.assertEqual(
            [str(self.visible_log.pk)], self.listed(client=self.user_client))

    def test_answers_the_logs_of_a_hidden_resource_after_it_is_granted(self):
        assign_perm("registry.view_webmapservice", self.user, self.service)

        self.assertEqual(
            {str(self.hidden_log.pk), str(self.visible_log.pk)},
            set(self.listed(client=self.user_client)))

    def test_refuses_a_log_of_a_hidden_resource_as_it_is_gone(self):
        response = self.user_client.get(reverse(
            "notify:backgroundprocesslog-detail",
            kwargs={"pk": self.hidden_log.pk}))

        self.assertEqual(response.status_code, 404)

    def test_filters_the_logs_by_their_process(self):
        self.assertEqual(
            [str(self.visible_log.pk)],
            self.listed(**{"filter[backgroundProcess]": self.visible.pk}))

    def test_filters_the_logs_of_a_hidden_process_to_nobody_but_the_superuser(
            self):
        self.assertEqual(
            [], self.listed(client=self.user_client,
                            **{"filter[backgroundProcess]": self.hidden.pk}))

    def test_sorts_the_logs_by_the_moment_they_reported(self):
        self.assertEqual(
            [str(self.visible_log.pk), str(self.hidden_log.pk)],
            self.listed(sort="-date"))
        self.assertEqual(
            [str(self.hidden_log.pk), str(self.visible_log.pk)],
            self.listed(sort="date"))

    def nested_listed(self, process, client=None):
        response = (client or self.client).get(
            reverse("notify:backgroundprocess-logs-list",
                    kwargs={"parent_lookup_background_process": process.pk}))

        self.assertEqual(response.status_code, 200)
        return [entry["id"] for entry in json.loads(
            response.content)["data"]]

    def test_the_nested_route_answers_the_logs_of_its_process(self):
        self.assertEqual(
            [str(self.hidden_log.pk)],
            self.nested_listed(self.hidden))

    def test_the_nested_route_hides_the_logs_of_a_hidden_process(self):
        self.assertEqual(
            [], self.nested_listed(self.hidden, client=self.user_client))
        self.assertEqual(
            [str(self.visible_log.pk)],
            self.nested_listed(self.visible, client=self.user_client))
