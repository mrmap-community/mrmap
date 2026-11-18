"""The scheduler and system-info endpoints are admin only (#1445).

``CrontabScheduleViewSet``, ``PeriodicTaskViewSet`` and ``SystemView``
carried no ``permission_classes``, so the global
``IsAuthenticatedOrReadOnly`` applied: every anonymous caller could READ
the release, platform and database answers of ``/api/system/info``, and
every authenticated user - any registered account of any organization -
could create or retarget a ``PeriodicTask``, which schedules ANY
registered Celery task with ANY arguments: in-deployment job execution,
queue flooding, SSRF amplification. The module's own standard, set by
``SystemStatusView`` and the capacity view of #1326, is ``IsAdminUser``;
the frontend has gated these resources through ``ADMINISTRATION_RESOURCES``
all along. These tests pin that standard on the three repaired endpoints,
including the write path that made the read refusal not enough.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from django_celery_beat.models import PeriodicTask

JSONAPI = "application/vnd.api+json"

CRONTAB_URL = "/api/system/crontabs"
PERIODIC_TASK_URL = "/api/system/periodic-tasks"
INFO_URL = "/api/system/info"


def document(resource_type, attributes):
    return {"data": {"type": resource_type, "attributes": attributes}}


CRONTAB_DOCUMENT = document("CrontabSchedule", {
    "minute": "0", "hour": "*/2", "day_of_month": "*",
    "month_of_year": "*", "day_of_week": "*"})
TASK_DOCUMENT = document("PeriodicTask", {
    "name": "anything-anywhere",
    "task": "registry.tasks.service.recover_registration_reference_work",
    # the serializer's CrontabStringField takes the five-field string and
    # get_or_creates the schedule behind it
    "scheduling": "0 */2 * * *",
    "kwargs": "{}"})


class SystemEndpointsAdminOnlyTests(TestCase):
    """anonymous and plain accounts stay out; a staff account gets in"""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(
            username="system-admin", password="x", is_staff=True)
        self.plain = get_user_model().objects.create_user(
            username="plain-user", password="x")

    def client_for(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def assert_refused(self, url, user=None, method="get", body=None):
        client = self.client_for(user)
        send = getattr(client, method)
        response = (send(url, body, format="vnd.api+json",
                         HTTP_ACCEPT=JSONAPI)
                    if body is not None
                    else send(url, HTTP_ACCEPT=JSONAPI))
        self.assertIn(response.status_code, (401, 403),
                      f"{method} {url} as "
                      f"{'anonymous' if user is None else user.username}"
                      f" answered {response.status_code}")

    def test_the_reads_are_admin_only(self):
        for url in (CRONTAB_URL, PERIODIC_TASK_URL, INFO_URL):
            self.assert_refused(url)
            self.assert_refused(url, user=self.plain)

    def test_the_writes_are_admin_only(self):
        for url, body in ((CRONTAB_URL, CRONTAB_DOCUMENT),
                          (PERIODIC_TASK_URL, TASK_DOCUMENT)):
            self.assert_refused(url, method="post", body=body)
            self.assert_refused(url, user=self.plain, method="post",
                                body=body)

    def test_a_plain_user_cannot_schedule_work(self):
        """the refusal is the whole story: the attempt leaves no row behind

        The assertion names the attempt, not a table count: a migrated
        database already carries the beat rows that ``registry/apps.py``
        creates on post_migrate.
        """
        self.assert_refused(PERIODIC_TASK_URL, user=self.plain,
                            method="post", body=TASK_DOCUMENT)
        self.assertFalse(PeriodicTask.objects.filter(
            name="anything-anywhere").exists())

    def test_an_admin_reads_the_scheduler_and_the_system(self):
        for url in (CRONTAB_URL, PERIODIC_TASK_URL, INFO_URL):
            response = self.client_for(self.admin).get(
                url, HTTP_ACCEPT=JSONAPI)
            self.assertEqual(response.status_code, 200, response.content)

    def test_an_admin_still_schedules_through_the_same_endpoints(self):
        response = self.client_for(self.admin).post(
            PERIODIC_TASK_URL, TASK_DOCUMENT, format="vnd.api+json",
            HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(PeriodicTask.objects.filter(
            name="anything-anywhere").exists())
