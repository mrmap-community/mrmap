"""Tests of the persisted operational incident (#1319).

The incident is the deduplicated, permission-filterable record of a problem
which stands: its identity is a stable dedup key independent of any Celery
retry, its lifecycle has one transition, and its payload is bounded and
redacted. These tests answer those promises against the model and the
manager; the tests of the api answer who may read the rows.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils.timezone import now
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum)
from notify.models import (INCIDENT_DETAILS_MAX_BYTES,
                           INCIDENT_DETAILS_VALUE_MAX_LENGTH,
                           INCIDENT_SUMMARY_MAX_LENGTH,
                           OperationalIncident, incident_details_bytes,
                           purge_expired_operational_incidents,
                           sanitize_incident_details)
from registry.models.harvest import HarvestingJob
from registry.models.service import CatalogueService, WebMapService

#: the WMS of ``test_wms.json`` and its second row, and the first catalogue
#: of ``test_csw.json``
WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
OTHER_WMS_PK = "1b195589-dcfa-403f-9e66-e7e1c0a67024"
CSW_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class DeduplicationTests(TestCase):
    """The report of a standing problem is one incident, not one per retry."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.other = WebMapService.objects.get(pk=OTHER_WMS_PK)

    def report(self, summary="the service did not answer", **kwargs):
        kwargs.setdefault("resource", {"web_map_service": self.service})
        return OperationalIncident.objects.report(
            code="csw_did_not_answer",
            source=IncidentSourceEnum.MONITORING.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary=summary,
            **kwargs)

    def test_reports_a_new_incident(self):
        incident, created = self.report()
        self.assertTrue(created)
        self.assertEqual(incident.occurrence_count, 1)
        self.assertEqual(incident.status, IncidentStatusEnum.ACTIVE.value)
        self.assertIsNotNone(incident.id)
        self.assertEqual(incident.scope, "resource")

    def test_deduplicates_recurrences_into_the_standing_incident(self):
        """Ten retries of one incident are one incident (the epic's test)."""
        first, created = self.report(summary="first")
        for attempt in range(9):
            incident, created = self.report(
                summary=f"retry {attempt}",
                occurred_at=now() + timedelta(seconds=attempt))
            self.assertFalse(created)
            self.assertEqual(incident.pk, first.pk)
        incident = OperationalIncident.objects.get(pk=first.pk)
        self.assertEqual(incident.occurrence_count, 10)
        self.assertEqual(incident.first_occurred_at, first.first_occurred_at)
        self.assertGreater(incident.last_occurred_at, first.first_occurred_at)
        # the latest evidence replaces the older one
        self.assertEqual(incident.summary, "retry 8")
        self.assertEqual(OperationalIncident.objects.count(), 1)

    def test_keyed_by_code_and_resource_not_by_the_summary(self):
        """The dedup key names the problem, not the worded message."""
        incident, _ = self.report(summary="first worded differently")
        other, created = self.report(summary="worded completely otherwise")
        self.assertFalse(created)
        self.assertEqual(incident.pk, other.pk)

    def test_a_different_resource_is_a_different_incident(self):
        """The same code about another service deduplicates to its own row."""
        first, _ = self.report()
        second, created = self.report(
            summary="the other service did not answer too",
            resource={"web_map_service": self.other})
        self.assertTrue(created)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.dedup_key, second.dedup_key)
        self.assertEqual(
            OperationalIncident.objects.filter(
                code="csw_did_not_answer").count(), 2)

    def test_a_system_incident_is_keyed_by_the_code_alone(self):
        first, created = OperationalIncident.objects.report(
            code="queue_without_consumer",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the queue has no consumer")
        self.assertTrue(created)
        self.assertEqual(first.scope, "system")
        second, created = OperationalIncident.objects.report(
            code="queue_without_consumer",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the queue has no consumer")
        self.assertFalse(created)
        self.assertEqual(first.pk, second.pk)
        self.assertTrue(second.dedup_key.endswith("|system"))

    def test_retry_information_is_carried_and_raised(self):
        incident, _ = self.report(
            retry_count=1,
            retry_scheduled_until=now() + timedelta(minutes=5))
        self.assertEqual(incident.retry_count, 1)
        incident, _ = self.report(retry_count=2)
        self.assertEqual(incident.retry_count, 2)
        # a report which knows nothing about retries keeps what stands
        incident, _ = self.report()
        self.assertEqual(incident.retry_count, 2)

    def test_report_names_at_most_one_resource(self):
        with self.assertRaises(ValueError):
            OperationalIncident.objects.report(
                code="two_resources",
                source=IncidentSourceEnum.SYSTEM.value,
                severity=IncidentSeverityEnum.ERROR.value,
                summary="two are none",
                resource={"web_map_service": self.service.pk,
                          "catalogue_service_id": CSW_PK})

    def test_report_refuses_an_unknown_resource_field(self):
        with self.assertRaises(ValueError):
            OperationalIncident.objects.report(
                code="no_such_thing",
                source=IncidentSourceEnum.SYSTEM.value,
                severity=IncidentSeverityEnum.ERROR.value,
                summary="an incident never names a user",
                resource={"user": 1})


class LifecycleTests(TestCase):
    """The lifecycle has one transition and it is terminal."""

    fixtures = ["test_users.json", "test_keywords.json", "test_wms.json"]

    def setUp(self):
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.incident, _ = OperationalIncident.objects.report(
            code="update_did_not_finish",
            source=IncidentSourceEnum.UPDATE.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="the update stopped before its end",
            resource={"web_map_service": self.service})

    def test_resolve_moves_the_single_transition(self):
        resolved = OperationalIncident.objects.resolve(self.incident.dedup_key)
        self.assertEqual(resolved, 1)
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status,
                         IncidentStatusEnum.RESOLVED.value)
        self.assertIsNotNone(self.incident.resolved_at)

    def test_resolve_is_idempotent(self):
        OperationalIncident.objects.resolve(self.incident.dedup_key)
        self.assertEqual(
            OperationalIncident.objects.resolve(self.incident.dedup_key), 0)

    def test_recurrence_after_resolution_opens_a_new_incident(self):
        """A problem which returns is a new incident, not a reopened one."""
        key = self.incident.dedup_key
        OperationalIncident.objects.resolve(key)
        reopened, created = OperationalIncident.objects.report(
            code="update_did_not_finish",
            source=IncidentSourceEnum.UPDATE.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary="it stands again",
            resource={"web_map_service": self.service})
        self.assertTrue(created)
        self.assertNotEqual(reopened.pk, self.incident.pk)
        self.assertEqual(reopened.dedup_key, key)
        self.assertEqual(
            OperationalIncident.objects.filter(dedup_key=key).count(), 2)
        self.assertEqual(
            OperationalIncident.objects.filter(
                dedup_key=key,
                status=IncidentStatusEnum.ACTIVE.value).count(), 1)

    def test_a_resolved_incident_never_counts_a_recurrence(self):
        """A report never silently moves a resolved row back to active."""
        key = self.incident.dedup_key
        OperationalIncident.objects.resolve(key)
        OperationalIncident.objects.report(
            code="update_did_not_finish",
            source=IncidentSourceEnum.UPDATE.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary="recurrence creates its own row",
            resource={"web_map_service": self.service})
        self.incident.refresh_from_db()
        self.assertEqual(self.incident.status,
                         IncidentStatusEnum.RESOLVED.value)
        self.assertEqual(self.incident.occurrence_count, 1)


class DatabaseConstraintTests(TestCase):
    """The typed resource and lifecycle promises are guarded in the database."""

    fixtures = ["test_users.json", "test_keywords.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.catalogue = CatalogueService.objects.get(pk=CSW_PK)

    def new(self, **values):
        values.setdefault("dedup_key", "constraint|test")
        values.setdefault("code", "constraint")
        values.setdefault("source", IncidentSourceEnum.SYSTEM.value)
        values.setdefault("severity", IncidentSeverityEnum.ERROR.value)
        values.setdefault("summary", "a constraint test")
        values.setdefault("first_occurred_at", now())
        values.setdefault("last_occurred_at", now())
        return OperationalIncident(**values)

    def test_two_resources_are_refused_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.new(
                    web_map_service=self.service,
                    catalogue_service=self.catalogue).save(force_insert=True)

    def test_a_resolved_incident_without_its_moment_is_refused(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.new(status=IncidentStatusEnum.RESOLVED.value).save(
                    force_insert=True)

    def test_only_one_active_incident_per_dedup_key(self):
        self.new().save(force_insert=True)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.new(summary="two active at once are none").save(
                    force_insert=True)

    def test_a_resolved_key_gives_the_slot_to_the_next_incident(self):
        """The unique slot belongs to the active incident, not to history."""
        first = self.new()
        first.save(force_insert=True)
        OperationalIncident.objects.resolve(first.dedup_key)
        again = self.new(summary="the problem returned")
        again.save(force_insert=True)
        self.assertNotEqual(again.pk, first.pk)

    def test_the_dedup_key_carries_the_typed_resource_label(self):
        key = OperationalIncident.objects.build_dedup_key(
            "csw_did_not_answer", web_map_service=self.service)
        self.assertEqual(
            key, f"csw_did_not_answer|registry.webmapservice|{WMS_PK}")
        self.assertEqual(
            OperationalIncident.objects.build_dedup_key("storm"),
            "storm|system")


class SanitizationTests(TestCase):
    """What an incident stores is redacted and bounded, before it is stored."""

    def test_sensitive_keys_are_redacted(self):
        details = sanitize_incident_details({
            "endpoint": "http://csw.example/api",
            "Authorization": "Bearer abc.def",
            "api_key": "super-secret",
            "records": {"X-Secret": "nope", "count": 3},
        })
        self.assertNotIn("abc.def", str(details))
        self.assertNotIn("super-secret", str(details))
        self.assertNotIn("nope", str(details))
        self.assertEqual(details["Authorization"], "[redacted]")
        self.assertEqual(details["api_key"], "[redacted]")
        self.assertEqual(details["records"]["X-Secret"], "[redacted]")
        self.assertEqual(details["records"]["count"], 3)
        # a plain endpoint name is no credential and stays
        self.assertEqual(details["endpoint"], "http://csw.example/api")

    def test_values_are_bounded(self):
        details = sanitize_incident_details({
            "trace": "x" * 10_000,
            "codes": list(range(100)),
        })
        self.assertLessEqual(
            len(details["trace"]), INCIDENT_DETAILS_VALUE_MAX_LENGTH)
        self.assertLessEqual(incident_details_bytes(details),
                             INCIDENT_DETAILS_MAX_BYTES)

    def test_an_over_grown_payload_is_bounded_and_says_so(self):
        details = sanitize_incident_details(
            {f"key_{index:03}": "v" * 200 for index in range(60)})
        self.assertLessEqual(
            incident_details_bytes(details), INCIDENT_DETAILS_MAX_BYTES)
        self.assertTrue(details.get("truncated"))

    def test_bounded_details_survive_a_full_clean(self):
        incident = OperationalIncident(
            dedup_key="bounded|clean",
            code="bounded", source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="sanitized before stored",
            details=sanitize_incident_details({"key": "x" * 10_000}),
            first_occurred_at=now(), last_occurred_at=now())
        incident.full_clean()  # must not raise

    def test_an_unsanitized_over_grown_payload_is_refused(self):
        incident = OperationalIncident(
            dedup_key="overgrown|clean",
            code="overgrown", source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="too big to store",
            details={"trace": "x" * 10_000},
            first_occurred_at=now(), last_occurred_at=now())
        with self.assertRaises(ValidationError):
            incident.full_clean()

    def test_a_report_stores_only_the_bounded_summary(self):
        incident, _ = OperationalIncident.objects.report(
            code="long_summary",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary="s" * (INCIDENT_SUMMARY_MAX_LENGTH + 100))
        self.assertEqual(len(incident.summary), INCIDENT_SUMMARY_MAX_LENGTH)

    def test_details_must_be_a_mapping(self):
        with self.assertRaises(ValidationError):
            sanitize_incident_details("a raw response body is no mapping")


class ScopeTests(TestCase):
    """Scope is derived from the typed relations, never stored beside them."""

    fixtures = ["test_users.json", "test_keywords.json", "test_csw.json"]

    def test_a_resource_incident_reports_the_resource_scope(self):
        incident = OperationalIncident(
            dedup_key="scope|wms", code="scope",
            source=IncidentSourceEnum.MONITORING.value,
            severity=IncidentSeverityEnum.WARNING.value, summary="s",
            first_occurred_at=now(), last_occurred_at=now(),
            web_map_service_id=WMS_PK)
        self.assertEqual(incident.scope, "resource")

    def test_a_job_incident_is_answered_from_its_service(self):
        catalogue = CatalogueService.objects.get(pk=CSW_PK)
        job = HarvestingJob.objects.create(
            service=catalogue, phase="collect", date_created=now())
        incident = OperationalIncident.objects.create(
            dedup_key="scope|job", code="scope",
            source=IncidentSourceEnum.HARVESTING.value,
            severity=IncidentSeverityEnum.WARNING.value, summary="s",
            first_occurred_at=now(), last_occurred_at=now(),
            harvesting_job=job)
        self.assertEqual(incident.scope, "resource")
        # the visibility of the incident is decided by the catalogue behind
        # the job - the path of the RESOURCE_FIELDS table
        self.assertEqual(
            OperationalIncident.objects._service_of("harvesting_job"),
            CatalogueService)

    def test_a_system_incident_reports_the_system_scope(self):
        incident = OperationalIncident(
            dedup_key="scope|system", code="scope",
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.WARNING.value, summary="s",
            first_occurred_at=now(), last_occurred_at=now())
        self.assertEqual(incident.scope, "system")


class RetentionTests(TestCase):
    """Only resolved incidents past their retention are taken back."""

    def resolved(self, key, days_ago):
        return OperationalIncident.objects.create(
            dedup_key=key, code="old", source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.WARNING.value, summary="old",
            first_occurred_at=now() - timedelta(days=days_ago + 1),
            last_occurred_at=now() - timedelta(days=days_ago + 1),
            status=IncidentStatusEnum.RESOLVED.value,
            resolved_at=now() - timedelta(days=days_ago))

    def test_purges_only_resolved_incidents_past_the_retention(self):
        old = self.resolved("old|r1", 120)
        recent = self.resolved("recent|r2", 10)
        standing, _ = OperationalIncident.objects.report(
            code="stands", source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.ERROR.value,
            summary="an active incident is never purged")
        with self.settings(OPERATIONAL_INCIDENT_RETENTION_DAYS=90):
            summary = purge_expired_operational_incidents()
        self.assertEqual(summary["purged"], 1)
        self.assertFalse(OperationalIncident.objects.filter(pk=old.pk).exists())
        self.assertTrue(
            OperationalIncident.objects.filter(pk=recent.pk).exists())
        self.assertTrue(
            OperationalIncident.objects.filter(pk=standing.pk).exists())

    @override_settings(OPERATIONAL_INCIDENT_RETENTION_DAYS=0)
    def test_a_retention_of_zero_keeps_everything(self):
        self.resolved("old|zero", 400)
        summary = purge_expired_operational_incidents()
        self.assertEqual(summary["purged"], 0)
        self.assertEqual(OperationalIncident.objects.count(), 1)

    def test_the_task_reports_what_it_purged(self):
        from notify.tasks import delete_expired_operational_incidents

        self.resolved("old|task", 400)
        with self.settings(OPERATIONAL_INCIDENT_RETENTION_DAYS=90):
            summary = delete_expired_operational_incidents.run(
                delete_expired_operational_incidents)
        self.assertEqual(summary["purged"], 1)
