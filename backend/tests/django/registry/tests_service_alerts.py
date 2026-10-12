from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import translation
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_celery_beat.models import CrontabSchedule
from guardian.shortcuts import assign_perm
from registry.enums.alerts import ServiceAlertCategory as Category
from registry.enums.alerts import ServiceAlertSeverity as Severity
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.update import UpdateJobStatusEnum as JobState
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.monitoring import (GetCapabilitiesProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebMapService
from registry.models.update import (WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
WMS_ONE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WMS_TWO = "1b195589-dcfa-403f-9e66-e7e1c0a67024"
CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
MONITORED_URI = "https://www.example.de/wms"

#: the route which answers the alerts of a kind of service
ALERTS_ROUTE = {
    WebMapService: "registry:wms-alerts-list",
    CatalogueService: "registry:csw-alerts-list",
}


class ServiceAlertsApiTest(TestCase):
    """Tests the endpoint which answers the attention a service needs.

    An alert is not stored but derived from the runs and jobs of a service, so
    every test creates the state behind an alert and asks the endpoint of that
    service for the alert it has to answer. As every alert tells about the
    service it belongs to, the tests also answer who may ask for them.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username="alerts", password="test")
        self.user = get_user_model().objects.get(username="User2")
        self.client = self.client_for(self.admin)
        self.user_client = self.client_for(self.user)
        self.wms_one = WebMapService.objects.get(pk=WMS_ONE)
        self.wms_two = WebMapService.objects.get(pk=WMS_TWO)
        self.csw = CatalogueService.objects.get(pk=CSW_ONE)
        self.crontab = CrontabSchedule.objects.create(
            minute="*", hour="*", day_of_week="*", day_of_month="*",
            month_of_year="*", timezone="UTC")

    @staticmethod
    def client_for(user):
        client = APIClient()
        client.force_authenticate(user)
        # without an explicit accept the browsable api renderer is used
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    def response(self, service, client=None, **query):
        """Ask the alerts endpoint of a service

        Args:
            service: the service the alerts belong to
            client: the client which asks, the admin asks per default
            **query: the query parameters of the request

        Returns:
            Response: the answer of the endpoint
        """
        return (client or self.client).get(
            reverse(ALERTS_ROUTE[type(service)],
                    kwargs={"parent_lookup_service": service.pk}), query)

    def alerts(self, service, client=None, **query):
        """The alerts which the endpoint of a service answers

        Args:
            service: the service the alerts belong to
            client: the client which asks, the admin asks per default
            **query: the query parameters of the request

        Returns:
            dict: the answered alerts by their id
        """
        response = self.response(service, client=client, **query)
        self.assertEqual(response.status_code, 200, response.content)
        return {alert["id"]: alert for alert in response.json()["data"]}

    def monitoring_setting(self, service):
        """Create the schedule which monitors a service"""
        return WebMapServiceMonitoringSetting.objects.create(
            service=service, crontab=self.crontab)

    def monitoring_run(self, setting, passed, hours_ago=1):
        """Create a run of a monitoring setting which did or did not pass"""
        run = WebMapServiceMonitoringRun.objects.create(
            setting=setting, date_created=now() - timedelta(hours=hours_ago))
        GetCapabilitiesProbeResult.objects.create(
            run=run, monitored_uri=MONITORED_URI,
            check_response_is_valid_xml_success=passed,
            check_response_is_valid_xml_message="xml" if passed else "no xml",
            check_response_does_contain_success=True,
            check_response_does_not_contain_success=True)
        return run

    def update_job(self, service, state, **kwargs):
        """Create an update job of a service which is in the given state"""
        return WebMapServiceUpdateJob.objects.create(
            service=service, status=JobState(state), **kwargs)

    def overdue_setting(self, model, service):
        """Create a schedule of a service whose last run lies in the past"""
        return model.objects.create(
            service=service, crontab=self.crontab, enabled=True,
            last_run_at=now() - timedelta(days=1))

    def update_candidate(self, service, job):
        """Mark a service as the copy which an update job works with"""
        WebMapService.objects.filter(pk=service.pk).update(
            update_candidate_of=job.service)
        return service

    def harvesting_job(self, service=None, phase=Phase.COMPLETED,
                       import_errors=0):
        """Create the last harvesting run of a catalogue"""
        job = HarvestingJob.objects.create(
            service=service or self.csw,
            total_records=max(import_errors, 1), phase=Phase(phase))
        for number in range(import_errors):
            TemporaryMdMetadataFile.objects.create(
                job=job, has_import_error=True, import_error="no record",
                md_metadata_file=SimpleUploadedFile(
                    f"record_{number}.xml", b"<record/>"))
        return job

    def test_a_service_which_needs_nothing_to_do_is_answered_with_nothing(self):
        """A service which is healthy has nothing to decide"""
        self.assertEqual(self.alerts(self.wms_one), {})

    def test_a_failing_monitoring_run_is_answered_as_an_error(self):
        run = self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        alerts = self.alerts(self.wms_one)
        alert_id = f"{Category.MONITORING_FAILED.value}:{run.pk}"
        self.assertEqual(sorted(alerts), [alert_id])
        attributes = alerts[alert_id]["attributes"]
        self.assertEqual(attributes["severity"], Severity.ERROR)
        self.assertEqual(attributes["category"], Category.MONITORING_FAILED)
        self.assertEqual(
            attributes["service"], {"type": "WebMapService", "id": WMS_ONE})
        self.assertEqual(attributes["resource"], {
            "type": "WebMapServiceMonitoringRun", "id": str(run.pk)})
        self.assertEqual(attributes["serviceTitle"], "WMS1")
        self.assertTrue(attributes["message"])

    def test_only_the_last_run_of_a_service_decides_its_monitoring(self):
        setting = self.monitoring_setting(self.wms_one)
        self.monitoring_run(setting, False, hours_ago=3)
        self.monitoring_run(setting, True, hours_ago=1)
        # the service is healthy again, until its newest run fails
        self.assertEqual(self.alerts(self.wms_one), {})
        run = self.monitoring_run(setting, False, hours_ago=0)
        self.assertEqual(sorted(self.alerts(self.wms_one)), [
            f"{Category.MONITORING_FAILED.value}:{run.pk}"])

    def test_an_update_which_waits_for_a_review_is_answered_as_warning(self):
        job = self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        alerts = self.alerts(self.wms_one)
        alert_id = f"{Category.UPDATE_REVIEW_REQUIRED.value}:{job.pk}"
        self.assertEqual(sorted(alerts), [alert_id])
        self.assertEqual(
            alerts[alert_id]["attributes"]["severity"], Severity.WARNING)
        self.assertEqual(alerts[alert_id]["attributes"]["resource"], {
            "type": "WebMapServiceUpdateJob", "id": str(job.pk)})

    def test_an_update_which_errored_is_answered_as_an_error(self):
        job = self.update_job(self.wms_one, JobState.ERROR, done_at=now())
        alerts = self.alerts(self.wms_one)
        alert_id = f"{Category.UPDATE_FAILED.value}:{job.pk}"
        self.assertEqual(sorted(alerts), [alert_id])
        self.assertEqual(
            alerts[alert_id]["attributes"]["severity"], Severity.ERROR)

    def test_an_update_which_is_still_running_needs_no_attention(self):
        self.update_job(self.wms_one, JobState.WAITING_FOR_PROCESSING)
        self.assertEqual(self.alerts(self.wms_one), {})

    def test_the_alerts_of_a_service_are_answered_errors_first(self):
        """A service answers at most one alert per category, worst first"""
        self.monitoring_run(self.monitoring_setting(self.wms_one), False,
                            hours_ago=3)
        self.overdue_setting(WebMapServiceMonitoringSetting, self.wms_one)
        self.update_job(self.wms_one, JobState.ERROR, done_at=now())
        alerts = self.alerts(self.wms_one)
        self.assertEqual(len(alerts), 3)
        categories = [alert["attributes"]["category"]
                      for alert in alerts.values()]
        # the errors are answered before the warnings and the newest error of
        # the same severity is answered first
        self.assertEqual(categories, [
            Category.UPDATE_FAILED, Category.MONITORING_FAILED,
            Category.MONITORING_OVERDUE])

    def test_a_service_does_not_answer_the_alerts_of_another_service(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        self.monitoring_run(self.monitoring_setting(self.wms_two), False)
        alerts = self.alerts(self.wms_two)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(
            list(alerts.values())[0]["attributes"]["service"]["id"], WMS_TWO)

    def test_the_candidate_of_an_update_is_not_answered_as_a_service(self):
        """The copy an update works with is not a service of its own"""
        job = self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        candidate = self.update_candidate(self.wms_two, job)
        self.monitoring_run(self.monitoring_setting(candidate), False)
        self.assertEqual(
            self.response(candidate).status_code, 404)

    def test_an_overdue_schedule_is_answered_for_the_service_it_watches(self):
        monitoring = self.overdue_setting(
            WebMapServiceMonitoringSetting, self.wms_one)
        self.overdue_setting(WebMapServiceUpdateSetting, self.wms_two)
        alerts = self.alerts(self.wms_one)
        self.assertEqual(sorted(alerts), [
            f"{Category.MONITORING_OVERDUE.value}:{monitoring.pk}"])
        attributes = alerts[
            f"{Category.MONITORING_OVERDUE.value}:{monitoring.pk}"]["attributes"]
        self.assertEqual(attributes["severity"], Severity.WARNING)
        # the alert names the expected time as the time it appeared
        self.assertIsNotNone(attributes["occurredAt"])

    def test_a_schedule_which_is_not_overdue_is_not_answered(self):
        setting = self.monitoring_setting(self.wms_one)
        setting.last_run_at = now()
        setting.save()
        self.assertEqual(self.alerts(self.wms_one), {})

    def test_an_aborted_harvesting_is_answered_for_its_catalogue(self):
        job = self.harvesting_job(phase=Phase.ABORTED)
        alerts = self.alerts(self.csw)
        alert_id = f"{Category.HARVESTING_INCOMPLETE.value}:{job.pk}"
        self.assertEqual(sorted(alerts), [alert_id])
        attributes = alerts[alert_id]["attributes"]
        self.assertEqual(
            attributes["service"], {"type": "CatalogueService", "id": CSW_ONE})
        self.assertEqual(attributes["serviceTitle"], "CSW1")

    def test_records_which_could_not_be_imported_are_answered(self):
        job = self.harvesting_job(import_errors=2)
        alerts = self.alerts(self.csw)
        alert_id = f"{Category.HARVESTING_INCOMPLETE.value}:{job.pk}"
        self.assertEqual(sorted(alerts), [alert_id])
        self.assertIn("2", alerts[alert_id]["attributes"]["message"])

    def test_a_harvesting_which_left_nothing_behind_needs_no_attention(self):
        self.harvesting_job()
        self.assertEqual(self.alerts(self.csw), {})

    def test_a_user_which_may_not_see_a_service_does_not_see_its_alerts(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        # every alert would tell about the service it belongs to, so the answer
        # stays the same as for a service which is not registered at all
        self.assertEqual(
            self.response(self.wms_one, self.user_client).status_code, 404)
        assign_perm("registry.view_webmapservice", self.user, self.wms_one)
        self.assertEqual(len(self.alerts(self.wms_one, self.user_client)), 1)

    def test_an_anonymous_client_sees_the_alerts_of_a_service(self):
        """The alerts are read like every other read of the registry api"""
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        anonymous = APIClient()
        anonymous.credentials(HTTP_ACCEPT=JSONAPI)
        self.assertEqual(len(self.alerts(self.wms_one, anonymous)), 1)

    def test_a_service_of_another_kind_is_not_answered_by_an_endpoint(self):
        """The map service of a request is not a catalogue of the deployment"""
        response = self.client.get(reverse(
            ALERTS_ROUTE[CatalogueService],
            kwargs={"parent_lookup_service": self.wms_one.pk}))
        self.assertEqual(response.status_code, 404)

    def test_an_id_which_no_service_of_a_kind_can_have_is_not_answered(self):
        response = self.client.get(reverse(
            ALERTS_ROUTE[WebMapService],
            kwargs={"parent_lookup_service": "not an id"}))
        self.assertEqual(response.status_code, 404)

    def test_the_alerts_of_a_service_are_counted_and_answered_at_once(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        self.overdue_setting(WebMapServiceMonitoringSetting, self.wms_one)
        self.overdue_setting(WebMapServiceUpdateSetting, self.wms_one)
        self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        payload = self.response(self.wms_one).json()
        # a service answers at most one alert per category, which is less than a
        # page of the api holds, so a client reads all of them at once
        self.assertEqual(payload["meta"]["pagination"]["count"], 4)
        self.assertEqual(len(payload["data"]), 4)

    def test_a_query_parameter_which_is_not_of_the_api_is_rejected(self):
        response = self.response(self.wms_one, bogus="x")
        self.assertEqual(response.status_code, 400)

    def test_the_schema_documents_the_alerts_of_every_service_kind(self):
        """The frontend builds a screen from the schema of the api, so the schema
        has to name the endpoint of every kind of service and describe the
        attributes of an alert with the values the frontend maps to labels.
        """
        # the schema view is cached for a long time, so the test must not read a
        # schema which was answered before
        caches["local-memory"].clear()
        # the schema is not answered as json:api, which the client of the api
        # tests asks for with every request
        self.client.credentials(HTTP_ACCEPT="application/vnd.oai.openapi+json")
        response = self.client.get(reverse("openapi-schema"))
        self.assertEqual(response.status_code, 200, response.content)
        schema = response.json()
        operations = {
            operation.get("operationId"): (path, operation)
            for path, item in schema.get("paths", {}).items()
            for _, operation in item.items()}
        for kind in ("WebMapService", "WebFeatureService", "CatalogueService"):
            path, operation = operations.get(
                f"list_related_ServiceAlert_of_{kind}", (None, None))
            self.assertIsNotNone(operation, kind)
            self.assertTrue(path.startswith("/api/registry/"))
            # the service is addressed in the path of the request, so nothing
            # else is filtered or sorted by a client
            parameters = [parameter["name"]
                          for parameter in operation["parameters"]]
            self.assertEqual(
                [parameter for parameter in parameters
                 if parameter.startswith(("filter", "sort"))], [])
        attributes = schema["components"]["schemas"]["ServiceAlert"][
            "properties"]["attributes"]["properties"]
        self.assertEqual(
            attributes["severity"]["enum"],
            [severity.value for severity in Severity])
        self.assertEqual(
            attributes["category"]["enum"],
            [category.value for category in Category])
        # the labels of an alert are translated, so that the administration of a
        # deployment in german does not answer english column headings
        with translation.override("de"):
            self.assertEqual(str(_("severity")), "Schweregrad")
            self.assertEqual(str(_("service title")), "Dienstetitel")
            self.assertEqual(
                str(_("the state of the service which needs attention")),
                "der Zustand des Dienstes, der Aufmerksamkeit benötigt")
