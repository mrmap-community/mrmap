"""The polling resource of a service registration is its BackgroundProcess.

D01/B of #1175: the POST which registers a WMS, WFS or CSW answers the
`BackgroundProcess` the viewset created and no longer a `TaskResult` - a
registration leaves no row of that legacy table behind. D02/A: the process
completes when the whole workflow ran to the end, including the metadata
collection which was requested; the service it built is named as soon as it
exists, and metadata steps which failed are readable in the process' logs
while the service and its link stay.

The state transitions are answered through celery's tracer, like in
`test_task_result_status.py`, because the reports into the process run in the
very same signal handlers a worker pays.
"""

import json
from pathlib import Path
from unittest.mock import patch
from urllib3.exceptions import MaxRetryError

from accounts.models import Organization
from celery.app.trace import build_tracer
from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from django_celery_results.models import TaskResult
from drf_spectacular.generators import SchemaGenerator
from guardian.shortcuts import assign_perm
from notify.enums import LogTypeEnum, ProcessStatusEnum
from notify.models import BackgroundProcess, BackgroundProcessLog
from notify.tasks import BackgroundProcessBased
from registry.models import CatalogueService, WebMapService
from registry.models.metadata import RemoteMetadata
from registry.tasks.service import build_ogc_service
from rest_framework import status
from rest_framework.test import APIClient
from tests.django.notify.test_task_result_status import WorkerRunMixin
from tests.django.utils import MockResponse

JSONAPI = "application/vnd.api+json"
CAPABILITIES = Path(
    __file__).parent.parent / "test_data/capabilities/wms/1.3.0.xml"
CAPABILITIES_URL = (
    "http://some-service.de/wms"
    "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities")
CSW_CAPABILITIES = Path(
    __file__).parent.parent / "test_data/capabilities/csw/2.0.2.xml"
CSW_CAPABILITIES_URL = (
    "http://some-catalogue.de/csw"
    "?service=CSW&version=2.0.2&request=GetCapabilities")


@override_settings(CHANNEL_LAYERS={
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class RegistrationPollingTests(WorkerRunMixin, TransactionTestCase):
    """A client which only knows HTTP follows its registration on the process.

    A `TransactionTestCase` with the channel layer of the tests: the answers
    of a task commit for real (see `test_task_result_status.py`) and the
    progress reports of the process broadcast over channels, which no
    deployment's redis is asked of here.
    """

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_superuser(
            username="registrar", password="test")
        self.organization = Organization.objects.create(name="Registering Amt")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    # -- the api side -------------------------------------------------------

    def register(self, endpoint="registry:wms-list", url=CAPABILITIES_URL,
                 collect="false", service_type="WebMapService"):
        return self.client.post(
            reverse(endpoint),
            data={
                "data": {
                    "type": service_type,
                    "attributes": {
                        "get_capabilities_url": url,
                        "collect_metadata_records": collect,
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

    def poll(self, pk, client=None):
        return (client or self.client).get(
            reverse("notify:backgroundprocess-detail", args=[pk]))

    def poll_attributes(self, pk, client=None):
        response = self.poll(pk, client=client)
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)["data"]

    def downloads(self, content):
        """Serves the document the task of the registration fetches."""
        return patch(
            "registry.tasks.service.Session.send",
            side_effect=lambda request, *args, **kwargs: MockResponse(
                status_code=status.HTTP_200_OK, content=content))

    def register_without_running_the_task(self):
        """Publishes a registration whose task no worker answers yet.

        Returns the answer of the POST and the kwargs the view handed to the
        publication, which carry the id of the process to answer for.
        """
        with patch.object(
                build_ogc_service, "apply_async",
                autospec=True) as apply_async:
            response = self.register()
        self.assertEqual(response.status_code, 202, response.content)
        task_kwargs = apply_async.call_args.kwargs["kwargs"]
        return response, task_kwargs

    def answer_shared(self, task, args=(), kwargs=None):
        """Answers one of the real project tasks the way a worker would.

        The task keeps its own definition - base, autoretry and all - but is
        asked of this process and writes its states to the local result
        backend of the test app, so no broker and no deployment cache are
        reached. A signature of a captured chord names its task, so a name is
        looked up in the app the registration belongs to.
        """
        if isinstance(task, str):
            task = build_ogc_service.app.tasks[task]
        old_backend = task.__dict__.get("_backend")
        task._backend = self.app.backend
        self.addCleanup(setattr, task, "_backend", old_backend)
        trace = build_tracer(task.name, task, app=self.app)
        return trace(self.task_id, args, kwargs or {},
                     {"id": self.task_id})

    # -- the contract of the answer ------------------------------------------

    def test_the_answer_is_the_process_before_any_worker_can_update_it(self):
        """The polling resource exists, typed and addressed, at answer time.

        The process is written together with the request which published the
        task, and the task is not out yet: what the client can read
        immediately is the queued state of exactly the resource the answer
        names - and no legacy `TaskResult` row was made on the way.
        """
        response, task_kwargs = self.register_without_running_the_task()
        body = json.loads(response.content)
        process_id = body["data"]["id"]

        self.assertEqual(
            str(task_kwargs["background_process_pk"]), process_id)
        self.assertEqual(body["data"]["type"], "BackgroundProcess")
        self.assertEqual(
            response["Content-Location"],
            f"http://testserver/api/notify/background-processes/{process_id}")

        resource = self.poll_attributes(process_id)
        self.assertEqual(resource["type"], "BackgroundProcess")
        self.assertEqual(resource["id"], process_id)
        self.assertEqual(
            resource["links"]["self"], response["Content-Location"])
        attributes = resource["attributes"]
        self.assertEqual(attributes["status"], "pending")
        self.assertIsNone(attributes["doneAt"])

        # D01/B: no legacy row was made for this registration
        self.assertEqual(TaskResult.objects.count(), 0)

    def test_the_published_root_is_owned_before_a_worker_can_pick_it_up(self):
        """The abort right after the POST revokes the task by its id (#1179).

        The id of the root task is decided and written with the process
        before the message goes out - the read below happens inside the
        publication itself, before celery can have handed the message to
        anyone. The abort then meets the honest case of a worker which has
        not seen the message: an inspection which answers nothing. It is the
        stored id, not worker sight and not a `TaskResult` row, which the
        revocation targets.
        """
        seen_at_publish = {}

        def publish(*args, **kwargs):
            # the state of the row at the very moment the message is handed
            # to celery: the id has to be durable already now
            stored = BackgroundProcess.objects.filter(
                pk=kwargs["kwargs"]["background_process_pk"]).values_list(
                    "celery_task_ids", flat=True).get()
            seen_at_publish["celery_task_ids"] = stored
            seen_at_publish["task_id"] = kwargs.get("task_id")

        with patch.object(
                build_ogc_service, "apply_async", autospec=True,
                side_effect=publish):
            response = self.register()
        self.assertEqual(response.status_code, 202, response.content)

        task_id = seen_at_publish["task_id"]
        self.assertIsNotNone(task_id, "the publication names its task id")
        self.assertEqual(
            [str(task_id)],
            [str(i) for i in seen_at_publish["celery_task_ids"]],
            "the id the message is published with must be stored with the "
            "process before the dispatch")

        process = BackgroundProcess.objects.get(
            pk=json.loads(response.content)["data"]["id"])

        with patch("notify.models.app.control.inspect") as inspect, \
                patch("notify.models.app.control.revoke") as revoke:
            for answer in ("active", "reserved", "scheduled"):
                getattr(inspect.return_value, answer).return_value = None

            self.assertEqual(
                process.get_related_task_ids(), [task_id],
                "the queued message is owned although no worker reports it")

            process.phase = "abort"
            process.save(update_fields=["phase"])

        self.assertEqual(set(revoke.call_args.args[0]), {task_id})
        self.assertTrue(revoke.call_args.kwargs["terminate"])

        attributes = self.poll_attributes(process.pk)["attributes"]
        self.assertEqual(attributes["status"], "aborted")
        self.assertIsNotNone(attributes["doneAt"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
    def test_a_registration_without_metadata_completes_and_names_the_service(self):
        """collect_metadata_records off: the workflow is over with the service.

        The root task ran to its end within the publication, so the process
        it reports for is completed and names the service it built.
        """
        with self.downloads(CAPABILITIES):
            response = self.register()
        self.assertEqual(response.status_code, 202, response.content)

        process_id = json.loads(response.content)["data"]["id"]
        service = WebMapService.objects.get()

        attributes = self.poll_attributes(process_id)["attributes"]
        self.assertEqual(attributes["status"], "completed")
        self.assertEqual(
            attributes["relatedResource"],
            {"type": "WebMapService", "id": str(service.pk)})
        self.assertIsNotNone(attributes["doneAt"])
        self.assertEqual(TaskResult.objects.count(), 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
    def test_a_catalogue_registration_names_the_service_it_built(self):
        """The same contract answers for a CSW, whose collection is always off."""
        with self.downloads(CSW_CAPABILITIES):
            response = self.register(
                endpoint="registry:csw-list", url=CSW_CAPABILITIES_URL,
                service_type="CatalogueService")
        self.assertEqual(response.status_code, 202, response.content)

        process_id = json.loads(response.content)["data"]["id"]

        attributes = self.poll_attributes(process_id)["attributes"]
        self.assertEqual(attributes["status"], "completed")

        # `registry.0002_data` seeds a CSW of its own into every database, so
        # the service built here is read back through the process naming it
        catalogue = CatalogueService.objects.get(
            pk=attributes["relatedResource"]["id"])
        self.assertEqual(
            attributes["relatedResource"],
            {"type": "CatalogueService", "id": str(catalogue.pk)})
        # and it is the service of the document which was served
        self.assertEqual(catalogue.title, "CSW Geoportal Hessen")
        self.assertEqual(TaskResult.objects.count(), 0)

    # -- the milestones of a registration with collection --------------------

    def _start_a_collecting_registration(self):
        """Answers the root of a collecting registration without its chord.

        The chord which collects the remote metadata is captured instead of
        published: what it would carry becomes readable, and its completion
        callback can be answered by hand afterwards.
        """
        captured = {}

        def capture_chord(header):
            def run(body, **options):
                captured["header"] = header
                captured["body"] = body
            return run

        with patch.object(
                build_ogc_service, "apply_async",
                autospec=True) as apply_async:
            response = self.register(collect="true")
        self.assertEqual(response.status_code, 202, response.content)
        task_kwargs = apply_async.call_args.kwargs["kwargs"]

        with self.downloads(CAPABILITIES), patch(
                "registry.tasks.service.chord", side_effect=capture_chord):
            self.answer_shared(build_ogc_service, kwargs=task_kwargs)
        return captured

    def test_the_service_is_named_while_metadata_continues_to_be_collected(self):
        """D02/A: the service link appears before the collection has ended.

        The root built and persisted the service; the requested collection
        did not end - it did not even start on a worker - so the process
        still runs: its completion means the whole workflow, not the service.
        """
        captured = self._start_a_collecting_registration()
        service = WebMapService.objects.get()
        process = BackgroundProcess.objects.get()

        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertIsNone(process.done_at)
        self.assertEqual(
            process.related_resource_type.model_class(), WebMapService)
        self.assertEqual(process.related_id, service.pk)

        # the collection the document asks for is what keeps the process open
        self.assertGreater(len(captured["header"]), 0)
        process.refresh_from_db()
        self.assertEqual(process.total_steps, len(captured["header"]))

        # and the client reading the http resource sees exactly that
        attributes = self.poll_attributes(process.pk)["attributes"]
        self.assertEqual(attributes["status"], "running")
        self.assertEqual(
            attributes["relatedResource"],
            {"type": "WebMapService", "id": str(service.pk)})

    def test_the_registration_completes_only_when_the_collection_ended(self):
        """A failed metadata step is logged, not mistaken for the end.

        The children which could not fetch their document leave a warning in
        the process' logs; the completion callback of the chord says the
        workflow ran to its end, and that is when - and only then - the
        process completes, with its service and its warnings readable.
        """
        captured = self._start_a_collecting_registration()
        process = BackgroundProcess.objects.get()

        with patch.object(
                RemoteMetadata, "fetch_remote_content",
                side_effect=MaxRetryError(None, "no route to the metadata")):
            for child in captured["header"]:
                self.answer_shared(
                    child.task, args=child.args, kwargs=child.kwargs)

        # every failed step told the polling client about itself
        warnings = BackgroundProcessLog.objects.filter(
            background_process=process, log_type=LogTypeEnum.WARNING)
        self.assertEqual(warnings.count(), len(captured["header"]))

        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertEqual(process.done_steps, process.total_steps)

        body = captured["body"]
        self.answer_shared(body.task, args=body.args, kwargs=body.kwargs)

        attributes = self.poll_attributes(process.pk)["attributes"]
        self.assertEqual(attributes["status"], "completed")
        self.assertEqual(
            attributes["relatedResource"],
            {"type": "WebMapService",
             "id": str(WebMapService.objects.get().pk)})
        self.assertEqual(TaskResult.objects.count(), 0)

    # -- outcomes which must not be mistaken ---------------------------------

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, BROKER_BACKEND='memory')
    def test_a_registration_which_could_not_be_built_fails_without_a_service(self):
        """The failure before any service exists is terminal and readable."""
        with self.downloads('<html>not a capabilities document</html>'):
            response = self.register()
        self.assertEqual(response.status_code, 202, response.content)

        process_id = json.loads(response.content)["data"]["id"]

        attributes = self.poll_attributes(process_id)["attributes"]
        self.assertEqual(attributes["status"], "failed")
        self.assertIsNone(attributes["relatedResource"])
        self.assertEqual(WebMapService.objects.count(), 0)
        # the client learns what went wrong from the resource it polls
        self.assertIn(
            "An error occurred",
            BackgroundProcessLog.objects.get(
                background_process_id=process_id,
                log_type=LogTypeEnum.ERROR).description)

    def test_a_registration_waiting_for_a_retry_is_not_reported_as_finished(self):
        """A retry keeps the process readable as running, never terminal."""
        process = BackgroundProcess.objects.create(
            phase="collecting", process_type="registering",
            description="a registration waiting for another attempt")

        def registering(background_process_pk=None):
            raise Retry("the remote is currently unreachable")

        self.answer(
            self.task(registering, base=BackgroundProcessBased),
            task_kwargs={"background_process_pk": str(process.pk)},
            opted_in=False)

        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.RUNNING)
        self.assertIsNone(process.done_at)

    def test_a_terminal_outcome_stays_terminal_for_the_work_still_in_flight(self):
        """The failure of the root is terminal even while a report arrives later.

        A task answered in this process must not end up beside a state its
        own failure decided, and a report which arrives after that decision
        cannot revive the process - the same protection a worker which dies
        after its failure leans on.
        """
        process = BackgroundProcess.objects.create(
            phase="download capabilities document...",
            process_type="registering",
            description="a registration which fails")

        def registering(background_process_pk=None):
            raise ValueError("the capabilities document is broken")

        self.answer(
            self.task(registering, base=BackgroundProcessBased),
            task_kwargs={"background_process_pk": str(process.pk)},
            opted_in=False)

        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.FAILED)
        self.assertIsNotNone(process.done_at)
        self.assertTrue(BackgroundProcessLog.objects.filter(
            background_process=process, log_type=LogTypeEnum.ERROR).exists())

        # and a late report about the same process cannot revive it
        BackgroundProcess.objects.report(
            process.pk, ProcessStatusEnum.RUNNING, phase="still working")
        process.refresh_from_db()
        self.assertEqual(process.status, ProcessStatusEnum.FAILED)

    # -- abort and visibility over the same resource --------------------------

    def test_an_abort_of_the_registration_process_ends_the_polling(self):
        """The abort the overview performs is what a polling client reads."""
        self.register_without_running_the_task()
        process = BackgroundProcess.objects.get()

        with patch.object(BackgroundProcess, "get_related_task_ids",
                          return_value=[]):
            aborted = self.client.patch(
                reverse("notify:backgroundprocess-detail", args=[process.pk]),
                {"data": {"type": "BackgroundProcess",
                          "id": str(process.pk),
                          "attributes": {"phase": "abort"}}},
                format="vnd.api+json")

        self.assertEqual(aborted.status_code, 200, aborted.content)

        attributes = self.poll_attributes(process.pk)["attributes"]
        self.assertEqual(attributes["status"], "aborted")
        self.assertIsNotNone(attributes["doneAt"])

    def test_the_schema_answers_the_process_for_a_registration(self):
        """The generated contract of a registration POST is the process.

        A client which reads the schema instead of the answer must learn the
        same thing: a 202 whose body is a `BackgroundProcess` and nothing of
        the legacy row (#1177).
        """
        schema = SchemaGenerator().get_schema(public=True)
        operation = schema["paths"]["/api/registry/wms"]["post"]

        self.assertIn("202", operation["responses"], json.dumps(operation))
        self.assertEqual(
            operation["responses"]["202"]["content"]["application/vnd.api+json"]
            ["schema"]["$ref"],
            "#/components/schemas/BackgroundProcessResponse")
        self.assertNotIn("TaskResult", json.dumps(operation))

    def test_the_process_shares_the_visibility_of_the_service_it_named(self):
        """Existing permissions and visibility are preserved for the polling.

        While the process belongs to no resource it is not narrowed by a
        resource permission; once it names a service, only a user who may
        view that service reads the process of its registration.
        """
        _, task_kwargs = self.register_without_running_the_task()
        with self.downloads(CAPABILITIES):
            self.answer_shared(build_ogc_service, kwargs=task_kwargs)

        service = WebMapService.objects.get()
        process = BackgroundProcess.objects.get()

        other = get_user_model().objects.create_user(
            username="viewer", password="test")
        other_client = APIClient()
        other_client.force_authenticate(other)
        other_client.credentials(HTTP_ACCEPT=JSONAPI)

        # without a permission on the service, its registration is not readable
        self.assertEqual(
            self.poll(process.pk, client=other_client).status_code, 404)

        assign_perm("registry.view_webmapservice", other, service)
        self.assertEqual(
            self.poll(process.pk, client=other_client).status_code, 200)
