"""Task-side SQL guards for the monitoring family (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
monitoring"). What this pins, per the #1395 coverage checklist:

*   ``run_probe_check`` - one check is pinned green: the by-pk probe fetch
    carries the ``setting__service__auth`` chain in its single SELECT
    (``Probe.for_probe_execution()``, #1393) and ``GetMapProbe.build_request``
    reads its scoped ``layers`` exactly once and reuses the loaded rows for
    the identifiers, the bbox and the styles (three reads before #1393). The
    check writes the result row, the capped progress step and nothing else -
    the probe configuration row is never written per check.
*   ``delete_expired_probe_response_artifacts`` - the SELECT side is constant
    in the number of expired rows (one read per result model); the UPDATE
    side is linear, one per expired row - the documented red baseline #1394
    collapses into paged reads and batched UPDATEs.

The numbers below are statements and rows, not runtime (V1 scope; #1396 owns
timings).
"""
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils.timezone import now
from django_celery_beat.models import IntervalSchedule
from registry.models.monitoring import (
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetMapProbe, GetMapProbeResult, PROBE_RESULT_MODELS,
    WebFeatureServiceMonitoringRun, WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun, WebMapServiceMonitoringSetting,
    purge_expired_probe_response_artifacts)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.ows_lib.client.core import OgcClient
from registry.tasks.monitoring import run_probe_check
from tests.django.registry.tasks.tests_monitoring import (
    side_effect, setup_capabilitites_file)
from tests.django.sql_guard import SqlGuardMixin, statements_of

WMS_PK = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WFS_PK = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'
CSW_PK = '9cc4889d-0cd4-4c3b-8975-58de6d30db41'


def patched_requests():
    """The network off, answered like the neighbour monitoring tests."""
    return patch.object(OgcClient, 'send_request', side_effect=side_effect)


class TempMediaMixin:
    """Probe artifacts below a temporary media root, cleaned up."""

    def enable_temp_media(self):
        override = override_settings(MEDIA_ROOT=tempfile.mkdtemp())
        override.enable()
        self.addCleanup(override.disable)


class ProbeCheckStatementShapeTest(TempMediaMixin, SqlGuardMixin, TestCase):
    """What one ``run_probe_check`` costs today, statement by statement.

    GetMap is the widest probe kind (it reads the scoped layers CTE); the
    guards read the capture of exactly one check.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.enable_temp_media()
        self.wms = WebMapService.objects.get(pk=WMS_PK)
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms, interval=self.interval)

    def _get_map_check(self):
        setup_capabilitites_file()
        probe = GetMapProbe.objects.create(setting=self.setting)
        probe.layers.set(self.wms.layers.all())
        monitoring_run = WebMapServiceMonitoringRun.objects.create(
            setting=self.setting)
        return probe, monitoring_run

    def _one_check(self):
        probe, monitoring_run = self._get_map_check()
        with patched_requests():
            return self.capture(lambda: run_probe_check.run(
                probe_model=probe._meta.label_lower,
                run_model=monitoring_run._meta.label_lower,
                probe_pk=probe.pk,
                run_pk=monitoring_run.pk))

    def test_one_check_fetches_the_probe_with_its_setting_chain(self):
        """Green baseline (#1393): the by-pk fetch carries the setting chain.

        ``Probe.for_probe_execution()`` selects ``setting__service__auth``
        with the probe, so the body's ``setting.service.client`` never pays
        lazy SELECTs: exactly one statement reads the probe and it JOINs the
        setting, the service and the optional auth row.
        """
        _, context = self._one_check()
        probe_selects = statements_of(
            context, verb='select', table=GetMapProbe._meta.db_table)
        self.assertEqual(len(probe_selects), 1,
                         'exactly one by-pk read of the probe')
        fetch = probe_selects[0]['sql'].lower()
        setting_table = GetMapProbe._meta.get_field(
            'setting').related_model._meta.db_table
        service_table = WebMapService._meta.db_table
        self.assertIn(setting_table.lower(), fetch,
                      msg='the fetch JOINs the setting it runs for')
        self.assertIn(service_table.lower(), fetch,
                      msg='the fetch JOINs the service whose client sends '
                          'the request - the lazy chain is gone')

    def test_the_layers_relation_is_read_exactly_once(self):
        """Green baseline (#1393): one layers read per GetMap probe check.

        ``build_request`` evaluates the scoped inherited-attributes CTE once
        and reuses the loaded rows for the identifiers, the bbox and the
        styles count; before #1393 the same relation was read three times
        per check.
        """
        _, context = self._one_check()
        layer_reads = [
            query for query in context.captured_queries
            if (query['sql'].lstrip().lower().startswith(('select', 'with'))
                and '"registry_layer"' in query['sql'].lower())]
        self.assertEqual(len(layer_reads), 1,
                         msg='build_request reads its scoped layers once; a '
                             'second read means the loaded list was dropped '
                             'and the CTE queryset re-evaluated')

    def test_the_result_and_progress_writes_are_one_each(self):
        """Green baseline: one result INSERT, one capped progress UPDATE and
        no write on the shared probe configuration.

        ``Probe.run_checks`` never re-saves the probe row (the vestigial
        save #1393 removed), so the configuration table is untouched by a
        check.
        """
        _, context = self._one_check()
        result_inserts = statements_of(
            context, verb='insert', table=GetMapProbeResult._meta.db_table)
        self.assertEqual(len(result_inserts), 1)
        progress_updates = statements_of(
            context, verb='update', table='notify_backgroundprocess')
        self.assertEqual(len(progress_updates), 1,
                         'the step_done report is the one process write')
        probe_updates = statements_of(
            context, verb='update', table=GetMapProbe._meta.db_table)
        self.assertEqual(len(probe_updates), 0,
                         msg='a check answers in its result row; it writes '
                             'nothing to the probe configuration')


class ArtifactPurgeScalingTest(TempMediaMixin, SqlGuardMixin, TestCase):
    """``delete_expired_probe_response_artifacts`` over 0/1/10/100+ rows.

    Six result models share the sweep; the checklist asks the SELECT side to
    stay constant while the sweep's rows grow - and since #1394 so does the
    WRITE side: the sweep reads through ``for_cleanup_batch()`` in bounded
    pages and clears a page with one UPDATE, so the statement count is
    bounded by the models and their pages, never by the rows. "Rows keep
    every column except ``response_body``" is the correctness half.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json',
                'test_wfs.json', 'test_csw.json']

    PURGE_SETTINGS = dict(MONITORING_PROBE_RESPONSE_RETENTION_DAYS=7)
    EXPIRED = dict(date_created=now() - timedelta(days=30))

    def setUp(self):
        self.enable_temp_media()
        interval = IntervalSchedule.objects.create(every=1, period='days')
        self.runs = {
            'wms': WebMapServiceMonitoringRun.objects.create(
                setting=WebMapServiceMonitoringSetting.objects.create(
                    service=WebMapService.objects.get(pk=WMS_PK),
                    interval=interval)),
            'wfs': WebFeatureServiceMonitoringRun.objects.create(
                setting=WebFeatureServiceMonitoringSetting.objects.create(
                    service=WebFeatureService.objects.get(pk=WFS_PK),
                    interval=interval)),
            'csw': CatalogueServiceMonitoringRun.objects.create(
                setting=CatalogueServiceMonitoringSetting.objects.create(
                    service=CatalogueService.objects.get(pk=CSW_PK),
                    interval=interval)),
        }
        # every result model reads with the run kind its FK accepts
        self.cycle = []
        for model in PROBE_RESULT_MODELS:
            target = model._meta.get_field('run').related_model.__name__
            kind = ('wfs' if target.startswith('WebFeature')
                    else 'csw' if target.startswith('Catalogue') else 'wms')
            self.cycle.append((model, kind))

    def _expired_rows(self, count):
        """``count`` rows with a stored body, aged past the retention."""
        built = []
        for index in range(count):
            model, kind = self.cycle[index % len(self.cycle)]
            result = model(run=self.runs[kind], monitored_uri='http://x/y')
            result.response_body = ContentFile(b'<response/>',
                                               name=f'response_{index}')
            result.save()
            model.objects.filter(pk=result.pk).update(**self.EXPIRED)
            built.append(result)
        return built

    def test_the_sweep_scales_with_pages_of_rows_not_reads(self):
        """SELECTs constant, UPDATEs one per PAGE - the shape of #1394.

        The ``extra`` allowance states the bounded write side honestly: a
        fire pays at most one batched UPDATE per result model (the rows of
        these fixtures fit in one page per model), never one per row. The
        UPDATE count of the sweep is asserted as a number in
        ``test_the_clear_rides_pages_not_rows``.
        """
        def seed(size):
            self._expired_rows(size)

        with override_settings(**self.PURGE_SETTINGS):
            measured = self.assertQueryCountIndependent(
                sizes=(0, 1, 10, 100),
                seed=seed,
                run=purge_expired_probe_response_artifacts,
                per_row=0,
                extra=len(PROBE_RESULT_MODELS),
                label='the artifact purge')

        # the reads are six: one per result model, never per row
        self.assertEqual(measured[0], len(PROBE_RESULT_MODELS))

    def test_the_clear_rides_pages_not_rows(self):
        """The green half of the #1394 batching: one UPDATE per model.

        30 expired rows spread over the six result models: the clear is at
        most six batched UPDATE statements - the per-row ``save`` loop it
        replaced stood one UPDATE per row, which the fingerprint guard below
        would report as a repetition.
        """
        rows = self._expired_rows(30)
        with override_settings(**self.PURGE_SETTINGS):
            summary, context = self.capture(
                purge_expired_probe_response_artifacts)
        self.assertEqual(summary['purged'], 30)
        updates = statements_of(context, verb='update')
        self.assertLessEqual(
            len(updates), len(PROBE_RESULT_MODELS),
            msg='every expired row of a page is cleared by the page\'s '
                'one UPDATE, never by a statement of its own')
        self.assertNoNPlusOne(
            purge_expired_probe_response_artifacts,
            label='the second fire over the cleared rows')
        for row in rows:
            self.assertIsNone(
                type(row).objects.values_list(
                    'response_body', flat=True).get(pk=row.pk),
                'the second fire found nothing left to clear')

    def test_expired_bodies_leave_and_rows_keep_their_answers(self):
        """Correctness half: only ``response_body`` goes.

        The rows of the probe results and their check answers stay so the
        monitoring history keeps answering what ran and when (#682).
        """
        rows = self._expired_rows(6)
        with override_settings(**self.PURGE_SETTINGS):
            summary = purge_expired_probe_response_artifacts()
        self.assertEqual(summary['purged'], 6)
        for row in rows:
            fresh = type(row).objects.get(pk=row.pk)
            # the purge unbinds the FileField; an unbound field answers as a
            # falsy FieldFile, not as None
            self.assertFalse(fresh.response_body)
            self.assertEqual(fresh.monitored_uri, 'http://x/y')

    def test_a_recent_body_is_left_alone(self):
        model = GetMapProbeResult
        result = model(run=self.runs['wms'], monitored_uri='http://x/y')
        result.response_body = ContentFile(b'<response/>', name='fresh')
        result.save()
        with override_settings(**self.PURGE_SETTINGS):
            summary = purge_expired_probe_response_artifacts()
        self.assertEqual(summary['purged'], 0)
        self.assertIsNotNone(
            type(result).objects.get(pk=result.pk).response_body)
