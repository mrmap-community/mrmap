"""Tests of the incident api (#1319).

The api is the read side of the persisted incidents: one permission rule
decides list, detail, every filter and every count together, the payload is
read-only for regular clients, and the answer shape is the JSON:API contract
the notification center of #1321 will consume. The permission matrix -
resource owner, unrelated user, administrator, anonymous - is the heart of
the issue and is answered as a matrix here.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from guardian.shortcuts import assign_perm
from notify.enums import IncidentSeverityEnum, IncidentSourceEnum
from notify.models import OperationalIncident
from registry.models.harvest import HarvestingJob
from registry.models.service import CatalogueService, WebMapService
from registry.models.update import WebMapServiceUpdateJob
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

#: the WMS of ``test_wms.json`` and the first catalogue of ``test_csw.json``
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
CSW_PK = "639cb553-8c30-4e72-a38d-10351ce81cf1"


class OperationalIncidentApiTests(TestCase):
    """Who may read which incident, through which question."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.owner = get_user_model().objects.get(username="User1")
        self.unrelated = get_user_model().objects.get(username="User2")
        self.admin = get_user_model().objects.create_superuser(
            username="admin", password="test")
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)
        assign_perm("registry.view_webmapservice", self.owner, self.service)
        assign_perm("registry.view_catalogueservice", self.owner,
                    self.catalogue)

        # one incident about the service itself, one about a harvesting job
        # of the catalogue and one system incident of the deployment
        self.on_service, _ = OperationalIncident.objects.report(
            code="monitoring_did_not_answer",
            source=IncidentSourceEnum.MONITORING.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary="the last probe of the service did not answer",
            resource={"web_map_service": self.service},
            details={"attempt": 4},
            retry_count=3,
            retry_scheduled_until=now() + timedelta(minutes=5))
        self.job = HarvestingJob.objects.create(
            service=self.catalogue, phase="collect", date_created=now())
        self.on_job, _ = OperationalIncident.objects.report(
            code="harvest_stalled",
            source=IncidentSourceEnum.HARVESTING.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the records of the harvest stopped flowing",
            resource={"harvesting_job": self.job})
        self.system, _ = OperationalIncident.objects.report(
            code="queue_without_consumer",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the import queue has no consumer")
        # a second catalogue with its own incident, hidden from the owner:
        # the leak question of the issue
        contact = self.hidden_contact()
        self.hidden_catalogue = CatalogueService.objects.create(
            title="hidden", version=202, origin=1,
            service_url="http://hidden.example/csw",
            metadata_contact=contact, service_contact=contact)
        self.hidden, _ = OperationalIncident.objects.report(
            code="harvest_stalled",
            source=IncidentSourceEnum.HARVESTING.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="a harvest nobody may see",
            resource={"catalogue_service": self.hidden_catalogue})

    @staticmethod
    def hidden_contact():
        from registry.models.metadata import MetadataContact
        return MetadataContact.objects.create(
            name="hidden", email="hidden@example.com")

    @staticmethod
    def client_for(user):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    def listed(self, client, **query_params):
        response = client.get(
            reverse("notify:operationalincident-list"), query_params)
        self.assertEqual(response.status_code, 200, response.content)
        body = json.loads(response.content)
        return body

    def ids(self, body):
        return {row["id"] for row in body["data"]}

    # ------------------------------------------------------------------
    # the permission matrix
    # ------------------------------------------------------------------

    def test_anonymous_reads_nothing(self):
        response = self.client_for(None).get(
            reverse("notify:operationalincident-list"))
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_read_a_detail_url_either(self):
        response = self.client_for(None).get(reverse(
            "notify:operationalincident-detail",
            kwargs={"pk": self.system.pk}))
        self.assertEqual(response.status_code, 403)

    def test_the_owner_reads_the_incidents_of_his_resources(self):
        body = self.listed(self.client_for(self.owner))
        self.assertEqual(
            self.ids(body), {str(self.on_service.pk), str(self.on_job.pk)})

    def test_an_unrelated_user_reads_none_of_them(self):
        body = self.listed(self.client_for(self.unrelated))
        self.assertEqual(self.ids(body), set())
        self.assertEqual(body["meta"]["pagination"]["count"], 0)

    def test_an_unrelated_user_cannot_ask_the_hidden_incident_by_filter(self):
        """A filtered count never names an incident the caller may not see."""
        body = self.listed(
            self.client_for(self.unrelated),
            **{"filter[service]": str(self.hidden_catalogue.pk)})
        self.assertEqual(body["meta"]["pagination"]["count"], 0)
        body = self.listed(
            self.client_for(self.unrelated),
            **{"filter[code]": "harvest_stalled"})
        self.assertEqual(body["meta"]["pagination"]["count"], 0)

    def test_an_unrelated_user_finds_no_detail_behind_the_url(self):
        response = self.client_for(self.unrelated).get(reverse(
            "notify:operationalincident-detail",
            kwargs={"pk": self.hidden.pk}))
        self.assertEqual(response.status_code, 404)

    def test_system_incidents_belong_to_the_admin_alone(self):
        body = self.listed(self.client_for(self.admin))
        self.assertIn(str(self.system.pk), self.ids(body))
        # the owner of two resources is still not the administrator
        body = self.listed(self.client_for(self.owner))
        self.assertNotIn(str(self.system.pk), self.ids(body))

    def test_the_admin_reads_every_incident(self):
        body = self.listed(self.client_for(self.admin))
        self.assertEqual(
            self.ids(body),
            {str(self.on_service.pk), str(self.on_job.pk),
             str(self.system.pk), str(self.hidden.pk)})

    def test_the_owner_sees_the_job_incident_through_its_catalogue(self):
        """The visibility of a job incident is the catalogue behind it."""
        body = self.listed(
            self.client_for(self.owner),
            **{"filter[service]": str(self.catalogue.pk)})
        self.assertEqual(self.ids(body), {str(self.on_job.pk)})

    # ------------------------------------------------------------------
    # reading contract
    # ------------------------------------------------------------------

    def test_answers_the_contract_of_an_incident(self):
        response = self.client_for(self.admin).get(reverse(
            "notify:operationalincident-detail",
            kwargs={"pk": self.on_service.pk}))
        self.assertEqual(response.status_code, 200)
        row = json.loads(response.content)["data"]
        self.assertEqual(row["id"], str(self.on_service.pk))
        attributes = row["attributes"]
        self.assertEqual(attributes["code"], "monitoring_did_not_answer")
        self.assertEqual(attributes["source"], "monitoring")
        self.assertEqual(attributes["severity"], "warning")
        self.assertEqual(attributes["status"], "active")
        self.assertEqual(attributes["scope"], "resource")
        self.assertEqual(attributes["occurrenceCount"], 1)
        self.assertEqual(attributes["retryCount"], 3)
        self.assertIsNotNone(attributes["retryScheduledUntil"])
        self.assertIsNone(attributes["resolvedAt"])
        self.assertEqual(
            attributes["affectedResource"],
            {"type": "WebMapService", "id": WMS_PK})
        self.assertEqual(attributes["details"], {"attempt": 4})
        # the internal dedup key stays out of the api
        self.assertNotIn("dedupKey", attributes)

    def test_a_system_incident_answers_no_affected_resource(self):
        response = self.client_for(self.admin).get(reverse(
            "notify:operationalincident-detail",
            kwargs={"pk": self.system.pk}))
        attributes = json.loads(response.content)["data"]["attributes"]
        self.assertEqual(attributes["scope"], "system")
        self.assertIsNone(attributes["affectedResource"])

    def test_the_api_is_read_only_for_regular_clients(self):
        client = self.client_for(self.admin)
        url = reverse("notify:operationalincident-list")
        for method in ("post", "put", "patch", "delete"):
            response = getattr(client, method)(
                url, json.dumps({}), content_type=JSONAPI)
            self.assertEqual(response.status_code, 405, method)
        response = client.delete(reverse(
            "notify:operationalincident-detail",
            kwargs={"pk": self.system.pk}))
        self.assertEqual(response.status_code, 405)

    # ------------------------------------------------------------------
    # filter, sort, pagination
    # ------------------------------------------------------------------

    def test_filters_the_lifecycle_of_the_incidents(self):
        OperationalIncident.objects.resolve(self.on_service.dedup_key)
        body = self.listed(
            self.client_for(self.admin), **{"filter[status]": "active"})
        self.assertNotIn(str(self.on_service.pk), self.ids(body))
        body = self.listed(
            self.client_for(self.admin), **{"filter[status]": "resolved"})
        self.assertEqual(self.ids(body), {str(self.on_service.pk)})

    def test_filters_by_severity_code_and_source(self):
        body = self.listed(
            self.client_for(self.admin), **{"filter[severity]": "error"})
        self.assertEqual(
            self.ids(body),
            {str(self.on_job.pk), str(self.system.pk), str(self.hidden.pk)})
        body = self.listed(
            self.client_for(self.admin), **{"filter[code.in]": "harvest_stalled,queue_without_consumer"})
        self.assertEqual(
            self.ids(body),
            {str(self.on_job.pk), str(self.system.pk), str(self.hidden.pk)})
        body = self.listed(
            self.client_for(self.admin), **{"filter[source]": "monitoring"})
        self.assertEqual(self.ids(body), {str(self.on_service.pk)})

    def test_refuses_a_choice_which_the_api_does_not_know(self):
        response = self.client_for(self.admin).get(
            reverse("notify:operationalincident-list"),
            {"filter[status]": "acknowledged"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.content)["errors"][0]["code"],
            "invalid_choice")

    def test_refuses_an_unknown_filter(self):
        response = self.client_for(self.admin).get(
            reverse("notify:operationalincident-list"),
            {"filter[not_a_field]": "x"})
        self.assertEqual(response.status_code, 400)

    def test_pages_and_counts_the_visible_incidents(self):
        body = self.listed(
            self.client_for(self.admin), **{"page[size]": "2"})
        self.assertEqual(body["meta"]["pagination"]["count"], 4)
        self.assertEqual(len(body["data"]), 2)
        # the same page of the owner only counts what the owner may see
        body = self.listed(
            self.client_for(self.owner), **{"page[size]": "2"})
        self.assertEqual(body["meta"]["pagination"]["count"], 2)

    def test_sorts_by_the_moments_and_the_counts(self):
        self.on_service.last_occurred_at = now() + timedelta(hours=1)
        self.on_service.save(update_fields=["last_occurred_at"])
        body = self.listed(self.client_for(self.admin), sort="-lastOccurredAt")
        self.assertEqual(
            body["data"][0]["id"], str(self.on_service.pk))
        body = self.listed(self.client_for(self.admin), sort="lastOccurredAt")
        self.assertNotEqual(
            body["data"][0]["id"], str(self.on_service.pk))
        response = self.client_for(self.admin).get(
            reverse("notify:operationalincident-list"),
            {"sort": "not_a_field"})
        self.assertEqual(response.status_code, 400)

    def test_windows_the_history_by_its_moments(self):
        body = self.listed(
            self.client_for(self.admin),
            **{"filter[lastOccurredAt.gt]":
               (now() + timedelta(hours=1)).isoformat()})
        self.assertEqual(self.ids(body), set())
        body = self.listed(
            self.client_for(self.admin),
            **{"filter[lastOccurredAt.gt]":
               (now() - timedelta(hours=1)).isoformat()})
        self.assertEqual(
            self.ids(body),
            {str(self.on_service.pk), str(self.on_job.pk),
             str(self.system.pk), str(self.hidden.pk)})

    def test_filters_by_the_typed_relations(self):
        body = self.listed(
            self.client_for(self.admin),
            **{"filter[harvestingJob]": str(self.job.pk)})
        self.assertEqual(self.ids(body), {str(self.on_job.pk)})
        body = self.listed(
            self.client_for(self.admin),
            **{"filter[webMapService]": str(self.service.pk)})
        self.assertEqual(self.ids(body), {str(self.on_service.pk)})

    def test_an_incident_about_an_update_job_is_answered_through_its_service(
            self):
        """The third path of the typed relations: update jobs."""
        job = WebMapServiceUpdateJob.objects.create(service=self.service)
        incident, _ = OperationalIncident.objects.report(
            code="update_did_not_finish",
            source=IncidentSourceEnum.UPDATE.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the update of the service stopped",
            resource={"web_map_service_update_job": job})
        body = self.listed(
            self.client_for(self.owner),
            **{"filter[service]": str(self.service.pk)})
        self.assertIn(str(incident.pk), self.ids(body))
        self.assertNotIn(str(self.system.pk), self.ids(body))

    # ------------------------------------------------------------------
    # query cost regression
    # ------------------------------------------------------------------

    def test_the_list_of_a_page_costs_one_page_and_its_count(self):
        """The page of the notification center is one bounded read.

        The affected resource is answered from the foreign key ids the rows
        already carry, so no relation is followed per row; the permission
        narrowing is one query with guardian subqueries. The count is the
        second query pagination needs. Pinned so an include or a per-row
        lookup which grows the page linearly shows up red here.
        """
        client = self.client_for(self.admin)
        url = reverse("notify:operationalincident-list")
        client.get(url)  # warm up: superuser path without guardian reads
        with self.assertNumQueries(2):
            client.get(url)

    def test_a_detail_is_one_read(self):
        client = self.client_for(self.admin)
        url = reverse("notify:operationalincident-detail",
                      kwargs={"pk": self.on_service.pk})
        client.get(url)
        with self.assertNumQueries(1):
            client.get(url)

    def test_the_owner_page_answers_its_rows_without_per_row_reads(self):
        """The guardian subqueries are part of the one page read."""
        client = self.client_for(self.owner)
        url = reverse("notify:operationalincident-list")
        client.get(url)  # the guardian lookups settle their own caches
        # page + count: the three service permissions ride along as
        # subqueries, not as separate list fetches
        with self.assertNumQueries(2):
            client.get(url)
