"""Task-side SQL guards for the alert refresh (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
the alert refresh"). ``refresh_service_alerts`` runs on every beat interval
AND on every invalidation, so its cost is paid most often of all the V1
families. The checklist items this module carries:

*   the annotation SELECT count stays constant in the number of services
    (per kind) - the database-side design #1030 asked for;
*   the storage probes of ``missing_capabilities_rows`` are bounded by the
    named prefixes, not by the services (#1394 replaced the per-service
    ``storage.exists()`` with a per-prefix listing; storage probes are not
    SQL, so they are counted where they are paid, not through the query
    capture - the red baseline #1395 pinned here is now its green guard);
*   an open alert keeps its identity across refreshes (#1030).
"""
import os
import tempfile
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
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

    def test_the_capabilities_backup_probes_are_bounded_by_prefixes(self):
        """One listing per named prefix, never one probe per service (#1394).

        This is the assertion #1395 landed as the red baseline of the linear
        shape: the refresh asks the storage for the prefix the names live
        below, so the ``exists()`` probes of a fire stay constant while the
        services below that prefix grow - and the green half still answers
        the right services: only a named file the storage does not hold
        leaves an alert row behind.
        """
        def count_probes():
            with patch('django.core.files.storage.default_storage.exists',
                       return_value=False) as exists:
                self.refresh_alerts()
                return exists.call_count

        base = count_probes()
        self._extra_services(3)
        # name a backup document on each new service below the prefix the
        # services of a deployment use; none of them is written to storage,
        # so every one of them is a candidate for an alert
        named = list(WebMapService.objects.filter(
            title__startswith='refresh growth'))
        self.assertEqual(len(named), 3)
        for service in named:
            WebMapService.objects.filter(pk=service.pk).update(
                xml_backup_file=f'xml_documents/{service.pk}/backup.xml')
        after = count_probes()
        self.assertEqual(
            after, base,
            msg=f'three services naming a document below an already listed '
                f'prefix must not add a single probe (before {base}, '
                f'after {after}): the refresh lists the prefix once')

    def test_only_a_named_document_the_storage_misses_is_alerted(self):
        """The listing answers the same rows the per-service probe answered.

        The fixtures themselves name a CSW backup document the fresh media
        root does not hold, so the exact row set is not the point here -
        the point is that the listing and the old probe answer the same
        question per name: the held document answers no row, the missing
        one does.
        """
        with override_settings(MEDIA_ROOT=tempfile.mkdtemp()):
            self._extra_services(2)
            held, missing = list(WebMapService.objects.filter(
                title__startswith='refresh growth'))[:2]
            for service in (held, missing):
                WebMapService.objects.filter(pk=service.pk).update(
                    xml_backup_file=f'xml_documents/{service.pk}/backup.xml')
            # the storage holds the document of exactly one of them
            directory = os.path.join(
                settings.MEDIA_ROOT, 'xml_documents', str(held.pk))
            os.makedirs(directory)
            with open(os.path.join(directory, 'backup.xml'), 'wb') as handle:
                handle.write(b'<wms:ServiceException/>')
            self.refresh_alerts()

        alerted = set(ServiceAlert.objects.filter(
            category='capabilities_backup_missing').values_list(
                'service', flat=True))
        self.assertIn(
            str(missing.pk), alerted,
            'the row exists for the service whose named document the '
            'storage does not hold')
        self.assertNotIn(
            str(held.pk), alerted,
            'the service whose named document the storage holds keeps no '
            'row - the prefix listing saw the file')

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
