import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django_celery_beat.models import IntervalSchedule
from registry.models.monitoring import (
    CatalogueServiceGetCapabilitiesProbeResult,
    CatalogueServiceGetRecordsProbeResult, CatalogueServiceMonitoringRun,
    CatalogueServiceMonitoringSetting,
    WebFeatureServiceGetCapabilitiesProbeResult,
    WebFeatureServiceGetFeatureProbeResult, WebFeatureServiceMonitoringRun,
    WebFeatureServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebFeatureService
from rest_framework.test import APIClient

JSONAPI = 'application/vnd.api+json'
MONITORED_URI = "https://www.example.de/wfs"
SERVICE_URI = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

# all services which are monitored and answered through the api
MONITORED_SERVICES = (
    {
        "service_model": WebFeatureService,
        "setting_model": WebFeatureServiceMonitoringSetting,
        "run_model": WebFeatureServiceMonitoringRun,
        "result_models": (
            (WebFeatureServiceGetCapabilitiesProbeResult,
             "registry:webfeatureservicemonitoring"
             "-getcapabilities-probe-result"),
            (WebFeatureServiceGetFeatureProbeResult,
             "registry:webfeatureservicemonitoring-getfeature-probe-result")),
        "nested_settings_path": "wfs",
        "run_url_name": "registry:webfeatureservicemonitoringrun",
    },
    {
        "service_model": CatalogueService,
        "setting_model": CatalogueServiceMonitoringSetting,
        "run_model": CatalogueServiceMonitoringRun,
        "result_models": (
            (CatalogueServiceGetCapabilitiesProbeResult,
             "registry:catalogueservicemonitoring"
             "-getcapabilities-probe-result"),
            (CatalogueServiceGetRecordsProbeResult,
             "registry:catalogueservicemonitoring-getrecords-probe-result")),
        "nested_settings_path": "csw",
        "run_url_name": "registry:catalogueservicemonitoringrun",
    },
)


class MonitoringApiTest(TestCase):
    """Tests the api endpoints which answer the monitoring of a service.

    The monitoring of a service is answered by the settings of the service, the
    runs of this settings and the results of the probes of a run. All of this
    endpoints are registered for every monitored kind of service.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="monitoring-api", password="test")
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        # without an explicit accept the browsable api renderer is used
        self.client.credentials(HTTP_ACCEPT=JSONAPI)
        self.interval = IntervalSchedule.objects.create(every=1, period='days')

    def create_run(self, kind):
        """Create a setting, a run and one result of every probe"""
        service = kind["service_model"].objects.get(pk=SERVICE_URI)
        setting = kind["setting_model"].objects.create(
            service=service, interval=self.interval)
        run = kind["run_model"].objects.create(setting=setting)
        results = [
            (url_name, result_model.objects.create(
                run=run,
                monitored_uri=MONITORED_URI,
                check_response_is_valid_xml_success=True,
                check_response_does_contain_success=True,
                check_response_does_not_contain_success=True))
            for result_model, url_name in kind["result_models"]
        ]
        return service, setting, run, results

    def test_settings_are_answered_as_related_resource_of_the_service(self):
        for kind in MONITORED_SERVICES:
            with self.subTest(service=kind["service_model"].__name__):
                service, setting, _, _ = self.create_run(kind)

                response = self.client.get(
                    f"/api/registry/{kind['nested_settings_path']}"
                    f"/{service.pk}/monitoring-settings")

                self.assertEqual(response.status_code, 200)
                body = json.loads(response.content)
                self.assertEqual(body["meta"]["pagination"]["count"], 1)
                self.assertEqual(
                    body["data"][0]["id"], str(setting.pk))

    def test_run_is_answered_with_the_success_of_its_probes(self):
        for kind in MONITORED_SERVICES:
            with self.subTest(service=kind["service_model"].__name__):
                _, _, run, _ = self.create_run(kind)

                response = self.client.get(reverse(
                    f"{kind['run_url_name']}-list"))

                self.assertEqual(response.status_code, 200)
                body = json.loads(response.content)
                self.assertEqual(body["meta"]["pagination"]["count"], 1)
                self.assertTrue(
                    body["data"][0]["attributes"]["success"])

                detail = self.client.get(reverse(
                    f"{kind['run_url_name']}-detail", kwargs={"pk": run.pk}))

                self.assertEqual(detail.status_code, 200)
                self.assertEqual(
                    json.loads(detail.content)["data"]["id"], str(run.pk))

    def test_probe_results_are_answered_for_their_own(self):
        for kind in MONITORED_SERVICES:
            with self.subTest(service=kind["service_model"].__name__):
                _, _, _, results = self.create_run(kind)

                for url_name, result in results:
                    with self.subTest(result=result.__class__.__name__):
                        response = self.client.get(
                            reverse(f"{url_name}-detail",
                                    kwargs={"pk": result.pk}))

                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            json.loads(response.content)["data"]["id"],
                            str(result.pk))

    def test_monitoring_runs_need_a_setting_to_be_created(self):
        for kind in MONITORED_SERVICES:
            with self.subTest(service=kind["service_model"].__name__):
                self.create_run(kind)

                response = self.client.post(
                    reverse(f"{kind['run_url_name']}-list"),
                    {"data": {"type": kind["run_model"].__name__,
                              "attributes": {}}},
                    format="vnd.api+json")

                self.assertEqual(response.status_code, 400)
