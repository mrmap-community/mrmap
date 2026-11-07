"""The resource the async api points a client at must answer how its task went (#1146).

A POST which triggers a task is answered with a `TaskResult` resource and the
client polls that resource to learn the outcome; it has nothing else to look at,
because the result backend of this deployment is the redis cache
(`extras.celery:RetryingCacheBackend`), which writes nothing into the table the
resource reads. The state of a task is therefore mirrored into the row of that
task by the celery signals connected in notify/tasks.py.
"""

import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from celery import Celery, states
from celery.app.task import Context
from celery.app.trace import build_tracer
from celery.exceptions import Reject, Retry
from celery.signals import task_revoked
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.test.utils import override_settings
from django.urls import reverse
from django_celery_results.models import TaskResult
from accounts.models import Organization
from notify.tasks import serialize_result
from registry.models.service import WebMapService
from rest_framework import status
from rest_framework.test import APIClient
from tests.django.utils import MockResponse

JSONAPI = "application/vnd.api+json"
CAPABILITIES = Path(
    __file__).parent.parent / "test_data/capabilities/wms/1.3.0.xml"
CAPABILITIES_URL = (
    "http://some-service.de/wms"
    "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities")


class WorkerRunMixin:
    """Answers tasks the way a worker does, so their signals are really sent.

    The mirroring listens to the signals celery's tracer sends while a task is
    answered, so the tests go through the tracer instead of calling the mirroring
    with hand made arguments. The app is of its own and its result backend is a
    local cache: a broker is not needed to answer a task and must not be reached
    by accident.
    """

    def setUp(self):
        super().setUp()
        self.app = Celery('task-result-test', set_as_current=False)
        self.addCleanup(self.app.close)
        self.app.conf.update(
            result_backend=settings.CELERY_RESULT_BACKEND,
            cache_backend='local-memory',
        )
        self.task_id = str(uuid4())

    def task(self, function, **options):
        task = self.app.task(shared=False, **options)(function)
        task._backend = self.app.backend
        return task

    def answer(self, task, task_id=None):
        trace = build_tracer(task.name, task, app=self.app)
        return trace(task_id or self.task_id, (), {},
                     {'id': task_id or self.task_id})

    def publish(self):
        """The row the api leaves behind for the task it has just published."""
        return TaskResult.objects.create(task_id=self.task_id)


class TaskResultMirrorTests(WorkerRunMixin, TransactionTestCase):
    """Every state a task reaches is written into the row published for it.

    A `TransactionTestCase`: answering a task commits for real, because the
    worker's own `task_prerun` handler of this project (`close_connections_before_task`
    in MrMap/celery.py) closes the connection a `TestCase` runs its atomic block on.
    """

    def test_the_row_reads_started_while_the_task_is_running(self):
        @self.task
        def registering():
            # what a client polling the resource reads at this very moment
            return {"while_running": TaskResult.objects.get(
                task_id=self.task_id).status}

        row = self.publish()
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.SUCCESS)
        self.assertEqual(
            json.loads(row.result)["while_running"], states.STARTED)
        self.assertIsNotNone(row.date_started)

    def test_a_task_which_answered_writes_its_result(self):
        outcome = {"data": {"type": "WebMapService", "id": str(uuid4())}}

        @self.task
        def registering():
            return outcome

        row = self.publish()
        created = row.date_done
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.SUCCESS)
        self.assertDictEqual(json.loads(row.result), outcome)
        self.assertGreater(row.date_done, created)

    def test_a_failing_task_answers_its_error(self):
        @self.task
        def registering():
            raise ValueError('the capabilities document is broken')

        row = self.publish()
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.FAILURE)
        self.assertIn('the capabilities document is broken', row.traceback)
        self.assertIsNotNone(row.date_done)

    def test_a_task_waiting_for_a_retry_is_not_reported_as_finished(self):
        @self.task
        def registering():
            raise Retry('the service is currently unreachable')

        row = self.publish()
        created = row.date_done
        self.answer(registering)

        row.refresh_from_db()
        self.assertEqual(row.status, states.RETRY)
        # the column says when the task was completed, so a task which still
        # waits for another attempt leaves it as it was
        self.assertEqual(row.date_done, created)

    def test_a_revoked_task_is_reported(self):
        @self.task
        def registering():
            return None

        row = self.publish()
        # a revoked task is never answered to an end, so no `task_postrun`
        # follows it, and the abort of a background process revokes the tasks it
        # waits for (see BackgroundProcess.save)
        task_revoked.send(
            sender=registering,
            request=Context({"id": self.task_id}),
            terminated=True,
            signum=9,
            expired=False)

        row.refresh_from_db()
        self.assertEqual(row.status, states.REVOKED)
        self.assertIsNotNone(row.date_done)

    def test_no_row_is_made_for_a_task_which_was_never_published(self):
        """The mirroring only writes a row which the api published before.

        The tasks of the harvesting and of the monitoring fan out pass through
        the very same signals; a row for each of them would fill the resource,
        which no client asks for, with thousands of entries of its own.
        """
        @self.task
        def import_record():
            return 'imported'

        self.answer(import_record)

        self.assertEqual(TaskResult.objects.count(), 0)

    def test_a_state_the_model_does_not_know_is_left_alone(self):
        @self.task
        def registering():
            raise Reject('nothing to do here', requeue=False)

        row = self.publish()
        self.answer(registering)

        # the resource would answer a status its schema does not declare, and
        # celery's own database backend does not store this state either
        row.refresh_from_db()
        self.assertEqual(row.status, states.STARTED)

    def test_a_result_which_cannot_be_expressed_is_left_out(self):
        # losing the value must not cost the client the state of its task
        with self.assertLogs('MrMap.root', level='WARNING'):
            self.assertIsNone(serialize_result(object()))


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class AsyncRegistrationTests(TransactionTestCase):
    """The reproduction of #1146: register a service and poll what the 202 pointed at.

    The task is answered in this process (`CELERY_TASK_ALWAYS_EAGER`), which is
    the hardest case for its row: the row has to be written before the message is
    handed to the broker, or the task is answered while its row does not exist
    yet and the outcome of the registration is lost. The channel layer is the
    in memory one, because the task reports its progress there and no
    deployment's redis is asked of here.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="registrar", password="test")
        self.organization = Organization.objects.create(name="Registering Amt")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def register(self):
        return self.client.post(
            reverse("registry:wms-list"),
            data={
                "data": {
                    "type": "WebMapService",
                    "attributes": {
                        "get_capabilities_url": CAPABILITIES_URL,
                        "collect_metadata_records": "false",
                    },
                    "relationships": {
                        "owner": {
                            "data": {
                                "type": "Organization",
                                "id": str(self.organization.pk),
                            }
                        }
                    },
                }
            },
            format="vnd.api+json",
        )

    def poll(self, pk):
        response = self.client.get(
            reverse("notify:taskresult-detail", args=[pk]))
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)["data"]["attributes"]

    def downloads(self, content):
        """Serves the document the task of the registration fetches.

        `content` is a path or a string, both of which `MockResponse` answers.
        """
        return patch(
            "registry.tasks.service.Session.send",
            side_effect=lambda request, *args, **kwargs: MockResponse(
                status_code=status.HTTP_200_OK, content=content))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
    def test_the_polling_answers_the_service_the_task_built(self):
        with self.downloads(CAPABILITIES):
            response = self.register()

        self.assertEqual(response.status_code, 202, response.content)

        service = WebMapService.objects.get()
        attributes = self.poll(json.loads(response.content)["data"]["id"])
        self.assertEqual(attributes["status"], states.SUCCESS)
        self.assertDictEqual(
            attributes["result"],
            {
                "data": {
                    "type": "WebMapService",
                    "id": str(service.pk),
                    "links": {
                        "self": reverse(
                            "registry:wms-detail", args=[service.pk]),
                    },
                }
            })
        self.assertIsNotNone(attributes["dateStarted"])
        self.assertIsNotNone(attributes["dateDone"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
    def test_the_polling_answers_a_registration_which_could_not_be_built(self):
        with self.downloads('<html>not a capabilities document</html>'):
            response = self.register()

        self.assertEqual(response.status_code, 202, response.content)

        attributes = self.poll(json.loads(response.content)["data"]["id"])
        self.assertEqual(attributes["status"], states.FAILURE)
        self.assertEqual(WebMapService.objects.count(), 0)
        # the client learns what went wrong instead of watching a task which
        # never ends
        self.assertTrue(attributes["traceback"])
