"""Tests the alerts which the resources of the services answer.

An alert is not stored anywhere but derived from the runs and jobs of a service,
so every test creates the state behind an alert and asks the queryset or the
endpoint of that service for the alerts it has to answer. Because the alerts are
attributes of a service, they are asked for like any other attribute: with the
fields of a request, a filter of it or its sort.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils.timezone import now
from django_celery_beat.models import CrontabSchedule
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.update import UpdateJobStatusEnum as JobState
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.monitoring import (GetCapabilitiesProbeResult,
                                        WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebMapService
from registry.models.update import WebMapServiceUpdateJob
from registry.querys.alerts import ALERT_ATTRIBUTES, alerts_requested
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
WMS_ONE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WMS_TWO = "1b195589-dcfa-403f-9e66-e7e1c0a67024"
CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"
MONITORED_URI = "https://www.example.de/wms"

#: the resources which answer the alerts of the services of a deployment
SERVICE_ROUTE = {
    WebMapService: "registry:wms-list",
    CatalogueService: "registry:csw-list",
}


class ServiceAlertsMixin:
    """The states which the alerts of a service are derived from.

    The runs and jobs of a service are the only data an alert is made of, so
    this creates them and reads the alerts of a service the way the api of its
    kind does.
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
        """A client which asks the api as the given user

        Args:
            user: the user the api answers

        Returns:
            APIClient: a client which asks as that user
        """
        client = APIClient()
        client.force_authenticate(user)
        # without an explicit accept the browsable api renderer is used
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    @staticmethod
    def alerts(service):
        """The row of a service with its alerts annotated

        Args:
            service: the service to read the alerts of

        Returns:
            the row of the service with the alerts annotated
        """
        return type(service).objects.with_alert_information().get(
            pk=service.pk)

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

    def harvesting_job(self, service=None, phase=Phase.COMPLETED,
                       import_errors=0, hours_ago=1):
        """Create the last harvesting run of a catalogue"""
        happened = now() - timedelta(hours=hours_ago)
        job = HarvestingJob.objects.create(
            service=service or self.csw,
            date_created=happened, done_at=happened,
            total_records=max(import_errors, 1), phase=Phase(phase))
        for number in range(import_errors):
            TemporaryMdMetadataFile.objects.create(
                job=job, has_import_error=True, import_error="no record",
                md_metadata_file=SimpleUploadedFile(
                    f"record_{number}.xml", b"<record/>"))
        return job


class ServiceAlertsQueryTest(ServiceAlertsMixin, TestCase):
    """Tests the annotations which answer the alerts of the services.

    These annotations are the only place which decides whether a service needs
    attention, so every state behind an alert is asked of the queryset of its
    kind of service here - the endpoints only answer what this annotates.
    """

    def test_a_service_without_a_run_and_a_job_needs_no_attention(self):
        alerts = self.alerts(self.wms_one)
        self.assertFalse(alerts.has_alert)
        self.assertFalse(alerts.monitoring_failed)
        self.assertIsNone(alerts.monitoring_failed_at)
        self.assertFalse(alerts.update_review_required)
        self.assertIsNone(alerts.update_review_required_at)
        self.assertFalse(alerts.update_failed)
        self.assertIsNone(alerts.update_failed_at)

    def test_a_failing_monitoring_run_needs_attention(self):
        run = self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        alerts = self.alerts(self.wms_one)
        self.assertTrue(alerts.monitoring_failed)
        self.assertTrue(alerts.has_alert)
        self.assertEqual(alerts.monitoring_failed_at, run.date_done)

    def test_only_the_newest_run_of_a_service_decides_its_monitoring(self):
        """A service is healthy again as soon as its newest run passes"""
        setting = self.monitoring_setting(self.wms_one)
        self.monitoring_run(setting, False, hours_ago=3)
        self.monitoring_run(setting, True, hours_ago=1)
        self.assertFalse(self.alerts(self.wms_one).has_alert)
        self.monitoring_run(setting, False, hours_ago=0)
        self.assertTrue(self.alerts(self.wms_one).monitoring_failed)

    def test_a_failing_update_needs_attention(self):
        self.update_job(self.wms_one, JobState.ERROR, done_at=now())
        alerts = self.alerts(self.wms_one)
        self.assertTrue(alerts.update_failed)
        self.assertTrue(alerts.has_alert)
        self.assertIsNotNone(alerts.update_failed_at)

    def test_only_the_newest_update_job_decides_the_update(self):
        """The service answers the state of its newest job and not of an old one"""
        failed = self.update_job(self.wms_one, JobState.ERROR, done_at=now())
        self.update_job(self.wms_one, JobState.WAITING_FOR_PROCESSING)
        # both jobs are created within the same microsecond, so the older one is
        # moved back in time to answer which of them is the newest
        WebMapServiceUpdateJob.objects.filter(pk=failed.pk).update(
            date_created=now() - timedelta(hours=1))
        alerts = self.alerts(self.wms_one)
        self.assertFalse(alerts.update_failed)
        self.assertIsNone(alerts.update_failed_at)
        self.assertFalse(alerts.has_alert)

    def test_an_update_which_waits_for_a_review_needs_attention(self):
        job = self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        alerts = self.alerts(self.wms_one)
        self.assertTrue(alerts.update_review_required)
        self.assertIsNotNone(alerts.update_review_required_at)
        self.assertTrue(alerts.has_alert)
        # a service which is decided about does not answer the alert again
        job.finish(JobState.UPDATED)
        alerts = self.alerts(self.wms_one)
        self.assertFalse(alerts.update_review_required)
        self.assertIsNone(alerts.update_review_required_at)

    def test_an_update_which_is_still_running_needs_no_attention(self):
        self.update_job(self.wms_one, JobState.WAITING_FOR_PROCESSING)
        self.assertFalse(self.alerts(self.wms_one).has_alert)

    def test_an_aborted_harvesting_needs_attention(self):
        self.harvesting_job(phase=Phase.ABORTED)
        alerts = self.alerts(self.csw)
        self.assertTrue(alerts.harvest_aborted)
        self.assertFalse(alerts.harvest_incomplete)
        self.assertTrue(alerts.has_alert)
        self.assertIsNotNone(alerts.harvest_failed_at)

    def test_the_records_a_harvesting_left_behind_need_attention(self):
        self.harvesting_job(import_errors=2)
        alerts = self.alerts(self.csw)
        self.assertTrue(alerts.harvest_incomplete)
        self.assertFalse(alerts.harvest_aborted)
        self.assertTrue(alerts.has_alert)

    def test_a_harvesting_which_left_nothing_behind_needs_no_attention(self):
        self.harvesting_job()
        self.assertFalse(self.alerts(self.csw).has_alert)

    def test_only_the_newest_harvesting_of_a_catalogue_decides(self):
        self.harvesting_job(phase=Phase.ABORTED, hours_ago=3)
        self.harvesting_job(hours_ago=1)
        self.assertFalse(self.alerts(self.csw).has_alert)

    def test_a_map_service_does_not_answer_the_state_of_a_harvesting(self):
        """Only the records of a catalogue are pulled by a harvesting job"""
        alerts = self.alerts(self.wms_one)
        self.assertFalse(hasattr(alerts, "harvest_aborted"))
        self.assertFalse(hasattr(alerts, "harvest_failed_at"))

    def test_a_service_does_not_answer_the_alerts_of_another_service(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        self.assertTrue(self.alerts(self.wms_one).has_alert)
        self.assertFalse(self.alerts(self.wms_two).has_alert)


class ServiceAlertsApiTest(ServiceAlertsMixin, TestCase):
    """Tests the alerts which the endpoints of the services answer.

    An alert is answered as an attribute of a service, which means that a client
    asks for it with the fields, the filters and the sort of a request - and that
    it is answered read only, like every attribute which the queries of a service
    answer instead of a column of a table.
    """

    def services(self, service_type, client=None, **query):
        """The services which the endpoint of their kind answers

        Args:
            service_type: the kind of service to ask for
            client: the client which asks, the admin asks per default
            **query: the query parameters of the request

        Returns:
            dict: the answered attributes of the services by their id
        """
        response = (client or self.client).get(
            reverse(SERVICE_ROUTE[service_type]), query)
        self.assertEqual(response.status_code, 200, response.content)
        return {
            resource["id"]: resource["attributes"]
            for resource in response.json()["data"]}

    def test_the_attributes_of_a_service_answer_its_alerts(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        answered = self.services(WebMapService)
        self.assertTrue(answered[WMS_ONE]["hasAlert"])
        self.assertTrue(answered[WMS_ONE]["monitoringFailed"])
        self.assertIsNotNone(answered[WMS_ONE]["monitoringFailedAt"])
        self.assertFalse(answered[WMS_ONE]["updateReviewRequired"])
        # the service which needs nothing to do answers nothing as an alert
        self.assertFalse(answered[WMS_TWO]["hasAlert"])

    def test_the_alerts_of_a_service_are_answered_with_its_other_attributes(
            self):
        """A client which asks for single fields gets the alerts it asks for

        The fields of a sparse request are named as the database names them,
        which is what the clients of this deployment do - the frontend asks for
        `string_representation` and `total_records` - and the request is answered
        with the names the api gives the attributes.
        """
        self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        answered = self.services(
            WebMapService,
            **{"fields[WebMapService]": "title,has_alert,update_review_required"})
        self.assertEqual(
            sorted(answered[WMS_ONE]),
            ["hasAlert", "title", "updateReviewRequired"])
        self.assertTrue(answered[WMS_ONE]["updateReviewRequired"])

    def test_the_services_which_need_attention_can_be_filtered(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        answered = self.services(
            WebMapService, **{"filter[hasAlert]": "true"})
        self.assertEqual(sorted(answered), [WMS_ONE])
        healthy = self.services(
            WebMapService, **{"filter[monitoringFailed]": "false"})
        self.assertEqual(sorted(healthy), [WMS_TWO])

    def test_the_services_which_need_attention_can_be_sorted(self):
        for wms, hours_ago in ((self.wms_one, 3), (self.wms_two, 1)):
            self.monitoring_run(
                self.monitoring_setting(wms), False, hours_ago)
        answered = self.services(WebMapService, **{"sort": "-monitoringFailedAt"})
        self.assertEqual(list(answered), [WMS_TWO, WMS_ONE])

    def test_a_catalogue_answers_the_state_of_its_harvesting(self):
        self.harvesting_job(import_errors=1)
        answered = self.services(CatalogueService)
        self.assertTrue(answered[CSW_ONE]["harvestIncomplete"])
        self.assertTrue(answered[CSW_ONE]["hasAlert"])

    def test_the_alerts_of_a_service_cannot_be_written(self):
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        # an alert always tells about the service it belongs to, so it is answered
        # read only to every client which may read that service - and no client
        # writes an alert, because the queries of the service answer it
        answered = self.services(WebMapService, client=self.user_client)
        self.assertEqual(sorted(answered), sorted([WMS_ONE, WMS_TWO]))
        self.assertTrue(answered[WMS_ONE]["hasAlert"])
        self.assertFalse(answered[WMS_TWO]["hasAlert"])

        response = self.client.patch(
            reverse("registry:wms-detail", kwargs={"pk": WMS_ONE}),
            json.dumps({
                "data": {"id": WMS_ONE, "type": "WebMapService",
                         "attributes": {"monitoringFailed": False}}}),
            content_type=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.alerts(self.wms_one).monitoring_failed)


class AlertsRequestedTest(SimpleTestCase):
    """Tests which requests of a service want its alerts annotated.

    The alerts of a service are answered by a subquery per attribute, so they are
    only added to a query which asks for them. A request which does not want them
    must not pay for them.
    """

    def requested(self, **query):
        """Whether the alerts of a map service have to be annotated

        Args:
            **query: the query parameters of the request

        Returns:
            bool: True if the request asks for the alerts
        """
        request = RequestFactory().get("/api/registry/wms/", query)
        return alerts_requested(request, "WebMapService", ALERT_ATTRIBUTES)

    def test_a_request_which_wants_everything_wants_the_alerts(self):
        self.assertTrue(self.requested())
        self.assertTrue(self.requested(**{"sort": "title"}))

    def test_a_sparse_fieldset_without_alerts_does_not_want_them(self):
        self.assertFalse(
            self.requested(**{"fields[WebMapService]": "title,hits"}))

    def test_a_sparse_fieldset_with_an_alert_wants_them(self):
        self.assertTrue(
            self.requested(**{"fields[WebMapService]": "title,hasAlert"}))
        # a client names the fields it wants as the api names them, but a request
        # may also name them as the database does
        self.assertTrue(
            self.requested(**{"fields[WebMapService]": "has_alert"}))

    def test_a_filter_or_a_sort_by_an_alert_wants_them(self):
        self.assertTrue(self.requested(
            **{"fields[WebMapService]": "title", "filter[hasAlert]": "true"}))
        self.assertTrue(self.requested(
            **{"fields[WebMapService]": "title",
               "sort": "-monitoringFailedAt"}))


class CrossServiceAlertsApiTest(ServiceAlertsMixin, TestCase):
    fixtures = ServiceAlertsMixin.fixtures + ["test_wfs.json"]

    def response(self, client=None, **query):
        response = (client or self.client).get(
            reverse('registry:service-alert-list'), query)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_cross_service_shape_filters_and_pagination(self):
        self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        self.harvesting_job(phase=Phase.ABORTED)
        response = self.response(**{'page[size]': 1})
        self.assertEqual(response['meta']['pagination']['count'], 2)
        self.assertEqual(len(response['data']), 1)
        alert = response['data'][0]
        self.assertEqual(alert['type'], 'ServiceAlert')
        self.assertEqual(alert['attributes']['severity'], 'error')
        self.assertEqual(alert['attributes']['serviceType'], 'CatalogueService')
        self.assertIn('/show/HarvestingJob', alert['attributes']['targetPath'])
        response = self.response(**{'filter[severity]': 'warning'})
        self.assertEqual(len(response['data']), 1)
        self.assertEqual(response['data'][0]['attributes']['category'], 'update_review_required')
        self.assertEqual(self.response(**{'filter[service]': WMS_TWO})['data'], [])
        self.assertEqual(self.response(**{'filter[serviceType]': 'WebFeatureService'})['data'], [])
        self.assertEqual(self.response(**{'filter[category]': 'update_failed'})['data'], [])

    def test_resolved_alert_disappears_and_identity_is_stable(self):
        job = self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        before = self.response()['data'][0]['id']
        self.assertEqual(self.response()['data'][0]['id'], before)
        job.finish(JobState.UPDATED)
        self.assertEqual(self.response()['data'], [])

    def test_permission_scoping_applies_before_count_and_filters(self):
        from guardian.shortcuts import assign_perm
        self.update_job(self.wms_one, JobState.ERROR)
        self.update_job(self.wms_two, JobState.ERROR)
        self.assertEqual(self.response(self.user_client)['data'], [])
        assign_perm('registry.view_webmapservice', self.user, self.wms_one)
        response = self.response(self.user_client, **{'page[size]': 1})
        self.assertEqual(response['meta']['pagination']['count'], 1)
        self.assertEqual(response['data'][0]['attributes']['service'], WMS_ONE)
        self.assertEqual(self.response(self.user_client, **{'filter[service]': WMS_TWO})['data'], [])

    def test_monitoring_recovery_and_newest_first(self):
        setting = self.monitoring_setting(self.wms_one)
        self.monitoring_run(setting, False, hours_ago=3)
        self.update_job(self.wms_two, JobState.ERROR, done_at=now())
        response = self.response(**{'filter[severity]': 'error', 'sort': '-occurred_at'})
        self.assertEqual([row['attributes']['service'] for row in response['data']], [WMS_TWO, WMS_ONE])
        self.monitoring_run(setting, True)
        self.assertEqual(len(self.response()['data']), 1)

    def test_overdue_enabled_setting_reuses_scheduling_rule(self):
        setting = self.monitoring_setting(self.wms_one)
        type(setting).objects.filter(pk=setting.pk).update(last_run_at=now() - timedelta(hours=1))
        response = self.response(**{'filter[category]': 'monitoring_overdue'})
        self.assertEqual(len(response['data']), 1)
        self.assertIn('/show/WebMapServiceMonitoringSetting', response['data'][0]['attributes']['targetPath'])
        type(setting).objects.filter(pk=setting.pk).update(enabled=False)
        self.assertEqual(self.response()['data'], [])

    def test_unknown_filter_and_sort_are_rejected(self):
        for query in ({'filter[unknown]': 'x'}, {'sort': 'unknown'}, {'filter[severity]': 'unknown'}):
            response = self.client.get(reverse('registry:service-alert-list'), query)
            self.assertEqual(response.status_code, 400, response.content)

    def test_endpoint_is_read_only_and_requires_authentication(self):
        response = APIClient().get(reverse('registry:service-alert-list'))
        self.assertIn(response.status_code, (401, 403))
        response = self.client.post(reverse('registry:service-alert-list'), {}, format='vnd.api+json')
        self.assertEqual(response.status_code, 405)


class ServiceAlertViewParityTest(ServiceAlertsMixin, TestCase):
    """Tests that the view of the alerts and the services cannot drift apart.

    The view is created by the union which `service_alert_rows()` builds from
    the very annotations which the services themselves answer - so its rows
    must be the rows which the annotations project, decided by the same rules.
    """
    fixtures = CrossServiceAlertsApiTest.fixtures

    def test_the_view_answers_the_projection_of_the_annotations(self):
        from registry.models.alerts import ServiceAlertView
        from registry.models.service import WebFeatureService
        from registry.querys.alerts import ALERT_CATEGORIES, service_alert
        self.monitoring_run(self.monitoring_setting(self.wms_one), False)
        self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        self.harvesting_job(phase=Phase.ABORTED)
        services = []
        for model in (WebMapService, WebFeatureService, CatalogueService):
            services += list(model.objects.filter(
                update_candidate_of__isnull=True))
        expected = {}
        for service in services:
            annotated = self.alerts(service)
            resource = type(service).__name__
            for category, (severity, at, target) in ALERT_CATEGORIES.items():
                if not getattr(annotated, category, False):
                    continue
                alert = service_alert(
                    service, category, severity, getattr(annotated, at),
                    target if target == 'HarvestingJob' else resource + target)
                if category == 'update_review_required' \
                        and getattr(annotated, 'alert_review_job_id', None) \
                        and resource != 'CatalogueService':
                    alert['resource_type'] = resource + 'UpdateJob'
                    alert['resource_id'] = str(annotated.alert_review_job_id)
                    alert['target_path'] = (
                        f"/{alert['resource_type']}/{alert['resource_id']}/show")
                expected[alert['id']] = alert
        answered = {row['id']: row for row in ServiceAlertView.objects.values()}
        self.assertEqual(answered, expected)


class CrossServiceAlertSourcesTest(ServiceAlertsMixin, TestCase):
    fixtures = CrossServiceAlertsApiTest.fixtures
    response = CrossServiceAlertsApiTest.response

    # Keep source-specific cases separate from the API contract assertions.
    def test_wfs_and_csw_updates_share_the_same_projection(self):
        from registry.models.service import WebFeatureService
        from registry.models.update import CatalogueServiceUpdateJob, WebFeatureServiceUpdateJob
        wfs = WebFeatureService.objects.first()
        WebFeatureServiceUpdateJob.objects.create(service=wfs, status=JobState.REVIEW_REQUIRED.value)
        CatalogueServiceUpdateJob.objects.create(service=self.csw, status=JobState.ERROR.value)
        response = self.response()
        self.assertEqual({row['attributes']['serviceType'] for row in response['data']},
                         {'WebFeatureService', 'CatalogueService'})
        review = next(row for row in response['data'] if row['attributes']['category'] == 'update_review_required')
        self.assertIn('/WebFeatureServiceUpdateJob/', review['attributes']['targetPath'])

    def test_update_candidate_and_job_are_one_problem(self):
        candidate = WebMapService.objects.create(
            title='Candidate', service_url=self.wms_one.service_url,
            version=self.wms_one.version, origin=self.wms_one.origin,
            update_candidate_of=self.wms_one,
            metadata_contact=self.wms_one.metadata_contact,
            service_contact=self.wms_one.service_contact)
        # A dangling candidate still asks for attention, even without a job.
        self.assertEqual(len(self.response()['data']), 1)
        job = self.update_job(self.wms_one, JobState.REVIEW_REQUIRED)
        response = self.response()
        self.assertEqual(len(response['data']), 1)
        self.assertEqual(response['data'][0]['attributes']['service'], WMS_ONE)
        self.assertEqual(response['data'][0]['attributes']['resourceId'], str(job.pk))
        candidate.delete()
        job.finish(JobState.UPDATED)
        self.assertEqual(self.response()['data'], [])

    def test_overdue_harvesting_uses_the_shared_schedule_helper(self):
        from registry.models.harvest import PeriodicHarvestingJob
        setting = PeriodicHarvestingJob.objects.create(service=self.csw, crontab=self.crontab)
        PeriodicHarvestingJob.objects.filter(pk=setting.pk).update(last_run_at=now() - timedelta(hours=1))
        response = self.response(**{'filter[category]': 'harvest_overdue'})
        self.assertEqual(len(response['data']), 1)
        self.assertIsNotNone(response['data'][0]['attributes']['occurredAt'])
        self.assertIn('/show/PeriodicHarvestingJob', response['data'][0]['attributes']['targetPath'])
        PeriodicHarvestingJob.objects.filter(pk=setting.pk).update(enabled=False)
        self.assertEqual(self.response()['data'], [])

    def test_overdue_updates_are_collected_for_every_protocol(self):
        from registry.models.service import WebFeatureService
        from registry.models.update import (
            CatalogueServiceUpdateSetting, WebFeatureServiceUpdateSetting, WebMapServiceUpdateSetting)
        for model, service in (
                (WebMapServiceUpdateSetting, self.wms_one),
                (WebFeatureServiceUpdateSetting, WebFeatureService.objects.first()),
                (CatalogueServiceUpdateSetting, self.csw)):
            setting = model.objects.create(service=service, crontab=self.crontab)
            model.objects.filter(pk=setting.pk).update(last_run_at=now() - timedelta(hours=1))
        response = self.response(**{'filter[category]': 'update_overdue'})
        self.assertEqual(len(response['data']), 3)
        self.assertEqual({row['attributes']['serviceType'] for row in response['data']},
                         {'WebMapService', 'WebFeatureService', 'CatalogueService'})
        self.assertTrue(all(row['attributes']['occurredAt'] for row in response['data']))

    def test_invalidation_waits_for_commit_and_contains_no_service_data(self):
        from unittest.mock import patch
        from registry.tasks.monitoring import finish_run
        with patch('notify.utils.send_msg') as send:
            with self.captureOnCommitCallbacks(execute=True):
                self.update_job(self.wms_one, JobState.ERROR)
                self.assertFalse(send.called)
            self.assertEqual(send.call_args.args[0] if send.call_args.args else send.call_args.kwargs['msg'], {
                'topic': 'resource/ServiceAlert',
                'event': {'type': 'created', 'payload': {'ids': []}},
            })
            send.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                self.harvesting_job(phase=Phase.ABORTED)
                self.assertFalse(send.called)
            self.assertTrue(any(call.args and call.args[0].get('topic') == 'resource/ServiceAlert'
                                for call in send.call_args_list))
            send.reset_mock()
            run = self.monitoring_run(self.monitoring_setting(self.wms_one), False)
            with self.captureOnCommitCallbacks(execute=True):
                finish_run(None, run.pk)
                self.assertFalse(send.called)
            self.assertTrue(any(call.args and call.args[0].get('topic') == 'resource/ServiceAlert'
                                for call in send.call_args_list))


class ServiceAlertOrderingTest(SimpleTestCase):
    def test_overdue_schedule_and_run_timestamps_compare_as_instants(self):
        from datetime import datetime
        from registry.views.alerts import ServiceAlertListView
        from rest_framework.request import Request
        view = ServiceAlertListView()
        view.request = Request(RequestFactory().get('/', {'sort': '-occurredAt'}))
        rows = [
            {'id': 'schedule', 'occurred_at': datetime.fromisoformat('2026-10-22T10:00:00+02:00')},
            {'id': 'run', 'occurred_at': datetime.fromisoformat('2026-10-22T09:00:00+00:00')},
            {'id': 'candidate', 'occurred_at': None},
        ]
        self.assertEqual([row['id'] for row in view.filter_queryset(rows)],
                         ['run', 'schedule', 'candidate'])
