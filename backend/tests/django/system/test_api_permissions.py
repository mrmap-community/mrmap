"""The system API answers administrators only (#1445).

``/api/system/crontabs``, ``/api/system/periodic-tasks`` and
``/api/system/info`` used to answer ``AllowAny``: an anonymous caller could
create or retarget a ``PeriodicTask`` - scheduling any registered Celery task
with any JSON arguments - and read the Django, Python and PostgreSQL versions
beside the database's name and size. The module's own standard beside them is
``IsAdminUser`` (``SystemStatusView``, ``CapacitySnapshotView``); the three now
answer it too. The scenarios mirror ``test_endpoint_requires_staff`` of
``test_status.py``.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework.test import APIClient

JSONAPI_ACCEPT = "application/vnd.api+json"

#: The endpoints #1445 closed to everybody but staff.
ADMIN_ONLY_ENDPOINTS = (
    "/api/system/crontabs",
    "/api/system/periodic-tasks",
    "/api/system/info",
)

#: The write endpoints among them; a refused POST must never reach the
#: serializer, so the bodies below are never validated against a row.
WRITABLE_ENDPOINTS = ADMIN_ONLY_ENDPOINTS[:2]


class SystemApiPermissionTests(TestCase):
    """Anonymous and plain readers are refused; staff is answered."""

    def setUp(self):
        self.client = APIClient()
        # migrations may seed scheduler rows; the denial assertions compare
        # against the count the test starts from, not against zero
        self.crontabs_before = CrontabSchedule.objects.count()
        self.tasks_before = PeriodicTask.objects.count()

    def test_anonymous_is_refused_at_every_endpoint(self):
        for path in ADMIN_ONLY_ENDPOINTS:
            with self.subTest(path=path):
                # the Basic/Token challenge makes the unauthenticated answer
                # a 401; a session-only deployment answers 403. Either way
                # the endpoint refuses before anything of the row is seen.
                self.assertIn(
                    self.client.get(path, HTTP_ACCEPT=JSONAPI_ACCEPT).status_code,
                    (401, 403))

    def test_anonymous_can_not_write_a_schedule(self):
        for path in WRITABLE_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.post(
                    path, {}, format="vnd.api+json",
                    HTTP_ACCEPT=JSONAPI_ACCEPT)
                self.assertIn(response.status_code, (401, 403))
        self.assertEqual(CrontabSchedule.objects.count(), self.crontabs_before)
        self.assertEqual(PeriodicTask.objects.count(), self.tasks_before)

    def test_logged_in_non_staff_is_refused(self):
        self.client.force_authenticate(User(username='reader', is_staff=False))
        for path in ADMIN_ONLY_ENDPOINTS:
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path, HTTP_ACCEPT=JSONAPI_ACCEPT).status_code,
                    403)

    def test_logged_in_non_staff_can_not_write_a_schedule(self):
        self.client.force_authenticate(User(username='writer', is_staff=False))
        for path in WRITABLE_ENDPOINTS:
            with self.subTest(path=path):
                response = self.client.post(
                    path, {}, format="vnd.api+json",
                    HTTP_ACCEPT=JSONAPI_ACCEPT)
                self.assertEqual(response.status_code, 403)
        self.assertEqual(CrontabSchedule.objects.count(), self.crontabs_before)
        self.assertEqual(PeriodicTask.objects.count(), self.tasks_before)

    def test_staff_is_answered(self):
        self.client.force_authenticate(User(username='admin', is_staff=True))
        for path in ADMIN_ONLY_ENDPOINTS:
            with self.subTest(path=path):
                self.assertEqual(
                    self.client.get(path, HTTP_ACCEPT=JSONAPI_ACCEPT).status_code,
                    200)
