"""The task read plans of the monitoring runs (#1397).

`MonitoringRunQuerySet.for_monitoring_task()` centralizes the fetch of the
``run_{wms,wfs,csw}_monitoring`` tasks. The tests pin what the convention
promises for it: the plan is the plan the tasks used inline (no invented
eager relation), one bounded statement per run regardless of the probe and
result data around it, lazy and chainable, and resolved per concrete run
model — the base model has no ``setting`` field to join.
"""
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from registry.managers.monitoring import (MonitoringRunManager,
                                          MonitoringRunQuerySet)
from registry.models.monitoring import (
    GetCapabilitiesProbe, GetMapProbe,
    WebFeatureServiceMonitoringRun, WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun, WebMapServiceMonitoringSetting)
from registry.models.service import WebFeatureService, WebMapService

from tests.django.utils import QueryPlanMixin


class ForMonitoringTaskTest(QueryPlanMixin, TestCase):
    """the plan of ``run_wms_monitoring`` and its siblings"""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json',
                'test_crs.json', 'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1,
                                                        period='days')
        self.wms_setting = WebMapServiceMonitoringSetting.objects.create(
            service=WebMapService.objects.get(
                pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"),
            interval=self.interval)
        self.wfs_setting = WebFeatureServiceMonitoringSetting.objects.create(
            service=WebFeatureService.objects.get(
                pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41"),
            interval=self.interval)

    def _wms_run(self):
        return WebMapServiceMonitoringRun.objects.create(
            setting=self.wms_setting)

    def test_plan_is_the_inline_plan_of_the_tasks(self):
        """before/after: the method answers the same SQL the tasks used to
        write inline — exactly ``select_related("setting")``, nothing more"""
        planned = str(
            WebMapServiceMonitoringRun.objects.for_monitoring_task().query)
        inline = str(WebMapServiceMonitoringRun.objects
                     .select_related("setting").query)
        self.assertEqual(planned, inline)

    def test_fetch_answers_the_run_with_its_setting_in_one_statement(self):
        run = self._wms_run()
        # probe configuration exists around the run, but the plan joins none
        # of it: the probes are read from the setting by the task itself
        GetCapabilitiesProbe.objects.create(setting=self.wms_setting)
        GetMapProbe.objects.create(setting=self.wms_setting)

        fetched, sqls = self.measure(
            lambda: WebMapServiceMonitoringRun.objects
            .for_monitoring_task().get(pk=run.pk))

        self.assertEqual(1, len(sqls))
        probe_tables = self.tables_read(
            str(GetCapabilitiesProbe.objects.get_queryset().query),
            str(GetMapProbe.objects.get_queryset().query))
        self.assertTrue(probe_tables)
        self.assertEqual(
            set(), self.tables_read(sqls[0]) & probe_tables)
        # the setting is cached: asking for it answers no further statement
        _, setting_reads = self.measure(lambda: fetched.setting)
        self.assertEqual([], setting_reads)
        self.assertEqual(self.wms_setting.pk, fetched.setting.pk)

    def test_method_is_lazy_and_stays_chainable(self):
        run = self._wms_run()

        def wire():
            # building and extending the plan must not hit the database
            return (WebMapServiceMonitoringRun.objects
                    .for_monitoring_task().using('default')
                    .filter(pk=run.pk))

        _, wiring_reads = self.measure(wire)
        self.assertEqual([], wiring_reads)

        # the chained operations answer the run
        _, reads = self.measure(
            lambda: WebMapServiceMonitoringRun.objects
            .for_monitoring_task().filter(pk=run.pk).first())
        self.assertEqual(1, len(reads))
        _, reads = self.measure(
            lambda: list(WebMapServiceMonitoringRun.objects
                         .for_monitoring_task().iterator()))
        self.assertEqual(1, len(reads))

    def test_composes_with_the_annotating_manager_methods(self):
        """the delegation keeps the existing queryset behavior intact"""
        run = self._wms_run()
        manager = WebMapServiceMonitoringRun._default_manager
        self.assertIsInstance(manager, MonitoringRunManager)
        self.assertIsInstance(
            manager.for_monitoring_task(), MonitoringRunQuerySet)
        self.assertIsInstance(
            manager.with_is_successful(), MonitoringRunQuerySet)
        runs, reads = self.measure(
            lambda: list(WebMapServiceMonitoringRun.objects
                         .with_is_successful().for_monitoring_task()))
        self.assertEqual([run.pk], [r.pk for r in runs])
        self.assertEqual(1, len(reads))

    def test_concrete_models_answer_their_own_setting(self):
        """typed subclasses: each run model joins its own setting relation —
        the base has none — and the other kind's pk answers nothing"""
        wms_run = self._wms_run()
        wfs_run = WebFeatureServiceMonitoringRun.objects.create(
            setting=self.wfs_setting)

        wms, wms_reads = self.measure(
            lambda: WebMapServiceMonitoringRun.objects
            .for_monitoring_task().get(pk=wms_run.pk))
        wfs, wfs_reads = self.measure(
            lambda: WebFeatureServiceMonitoringRun.objects
            .for_monitoring_task().get(pk=wfs_run.pk))

        self.assertEqual(1, len(wms_reads))
        self.assertEqual(1, len(wfs_reads))
        self.assertEqual(self.wms_setting.pk, wms.setting.pk)
        self.assertEqual(self.wfs_setting.pk, wfs.setting.pk)
        # the concrete tables differ — one plan name, per-model resolution
        self.assertNotEqual(self.tables_read(wms_reads[0]),
                            self.tables_read(wfs_reads[0]))
        with self.assertRaises(
                WebFeatureServiceMonitoringRun.DoesNotExist):
            WebFeatureServiceMonitoringRun.objects \
                .for_monitoring_task().get(pk=wms_run.pk)
