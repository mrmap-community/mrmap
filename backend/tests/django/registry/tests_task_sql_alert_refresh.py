"""Task-side SQL guards for the alert refresh (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
the alert refresh"). ``refresh_service_alerts`` runs on every beat interval
AND on every invalidation, so its cost is paid most often of all the V1
families. The checklist items this module carries:

*   the annotation SELECT count stays constant in the number of services
    (per kind) - the database-side design #1030 asked for;
*   the per-service ``storage.exists()`` probe of ``missing_capabilities_rows``
    is captured as the linear RED baseline #1394 replaces with per-prefix
    listings (storage probes are not SQL, so they are counted where they
    are paid, not through the query capture);
*   an open alert keeps its identity across refreshes (#1030).
"""
from unittest.mock import patch

from django.test import TestCase
from registry.models.alerts import ServiceAlert
from registry.models.metadata import MetadataContact
from registry.models.service import WebMapService
from tests.django.registry.tests_service_alerts import ServiceAlertsMixin
from tests.django.sql_guard import SqlGuardMixin


class AlertRefreshScalingTest(ServiceAlertsMixin, SqlGuardMixin, TestCase):
    """The refresh of the whole deployment, measured like a task."""

    def _extra_services(self, count):
        """More services of an existing kind - the annotation reads must not
        grow with them."""
        # MetadataContact is unique over its full field set, so every seed
        # batch needs its own contact row
        contact = MetadataContact.objects.create(
            name=f'refresh contact {MetadataContact.objects.count()}')
        for index in range(count):
            WebMapService.objects.create(
                title=f'refresh growth service {index}',
                version=130, origin=1,
                service_url=f'http://refresh-growth.example.org/{index}',
                metadata_contact=contact, service_contact=contact)

    def test_the_refresh_costs_the_same_whatever_the_services(self):
        """One SELECT per kind, never per service (the #1030 design).

        The fixture already answers several kinds; each seed adds plain
        WMS rows without schedules, alerts or stored documents - a
        deployment which simply grew.
        """
        def seed(size):
            self._extra_services(size)

        measured = self.assertQueryCountIndependent(
            sizes=(0, 1, 10),
            seed=seed,
            run=self.refresh_alerts,
            label='the alert refresh')
        self.assertEqual(len(set(measured.values())), 1)

    def test_the_capabilities_backup_probe_is_linear_red_baseline(self):
        """One ``storage.exists()`` per service naming a document, per fire.

        This is THE dominant cost of the refresh per the audit, and the one
        scoped storage-vs-SQL change #1394 should take: list the per-kind
        prefixes once instead of probing per service. Until then the guard
        pins the current shape: probes == services naming a document, and
        grows one per service added.
        """
        def count_probes():
            with patch('django.core.files.storage.default_storage.exists',
                       return_value=False) as exists:
                self.refresh_alerts()
                return exists.call_count

        base = count_probes()
        self._extra_services(3)
        # name a backup file on each new service without touching storage
        named = list(WebMapService.objects.filter(
            title__startswith='refresh growth'))
        self.assertEqual(len(named), 3)
        for service in named:
            service.xml_backup_file = 'missing_capabilities_backup.xml'
            WebMapService.objects.filter(pk=service.pk).update(
                xml_backup_file=service.xml_backup_file.name)
        after = count_probes()
        self.assertEqual(
            after - base, 3,
            msg='red baseline (#1394): the refresh probes the storage once '
                'per service naming a document; the prefix-listing fix '
                'flattens this - tighten the assertion then')

    def test_an_open_alert_keeps_its_identity_across_refreshes(self):
        """The full replace rewrites the rows but not the identities (#1030).

        A reader polling the attention list must not see an open problem
        appear as a new one on every fire: the row of the same open state
        answers the same id.
        """
        setting = self.monitoring_setting(self.wms_one)
        self.monitoring_run(setting, passed=False)

        first = self.refresh_alerts()
        ids_first = set(ServiceAlert.objects.values_list('pk', flat=True))
        self.assertTrue(ids_first, 'the failing run answers an alert')
        second = self.refresh_alerts()
        ids_second = set(ServiceAlert.objects.values_list('pk', flat=True))
        self.assertEqual(ids_first, ids_second,
                         'an open alert keeps its identifier')
        self.assertEqual(first, second)
