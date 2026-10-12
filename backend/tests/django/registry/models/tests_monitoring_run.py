from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from registry.models.monitoring import (
    CatalogueServiceGetRecordsProbeResult,
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetMapProbeResult, WebFeatureServiceGetFeatureProbeResult,
    WebFeatureServiceMonitoringRun, WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun, WebMapServiceMonitoringSetting)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)

MONITORED_URI = "https://www.example.de/wfs"


class MonitoringRunSuccessTest(TestCase):
    """Tests the annotated success state of the monitoring runs.

    A monitoring run is only successful if none of the probe checks of the run
    failed. So every failing check of every result of the run decides about the
    success, no matter which kind of probe created the result.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.wms_setting = WebMapServiceMonitoringSetting.objects.create(
            service=WebMapService.objects.get(
                pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"),
            interval=self.interval)
        self.wfs_setting = WebFeatureServiceMonitoringSetting.objects.create(
            service=WebFeatureService.objects.get(
                pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41"),
            interval=self.interval)
        self.csw_setting = CatalogueServiceMonitoringSetting.objects.create(
            service=CatalogueService.objects.get(
                pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41"),
            interval=self.interval)

    def test_run_without_results_is_successful(self):
        for setting, run_model in (
            (self.wms_setting, WebMapServiceMonitoringRun),
            (self.wfs_setting, WebFeatureServiceMonitoringRun),
            (self.csw_setting, CatalogueServiceMonitoringRun),
        ):
            with self.subTest(run_model=run_model.__name__):
                run = run_model.objects.create(setting=setting)
                self.assertTrue(
                    run_model.objects.with_is_successful()
                    .get(pk=run.pk).success)

    def test_wfs_run_with_failing_get_feature_check_is_not_successful(self):
        run = WebFeatureServiceMonitoringRun.objects.create(
            setting=self.wfs_setting)
        WebFeatureServiceGetFeatureProbeResult.objects.create(
            run=run,
            monitored_uri=MONITORED_URI,
            check_response_is_valid_xml_success=True,
            check_response_does_contain_success=False,
            check_response_does_not_contain_success=True)

        annotated = WebFeatureServiceMonitoringRun.objects \
            .with_is_successful().get(pk=run.pk)
        self.assertFalse(annotated.success)
        self.assertFalse(annotated.is_get_feature_failed is False)

    def test_wfs_run_with_passed_checks_is_successful(self):
        run = WebFeatureServiceMonitoringRun.objects.create(
            setting=self.wfs_setting)
        WebFeatureServiceGetFeatureProbeResult.objects.create(
            run=run,
            monitored_uri=MONITORED_URI,
            check_response_is_valid_xml_success=True,
            check_response_does_contain_success=True,
            check_response_does_not_contain_success=True)

        annotated = WebFeatureServiceMonitoringRun.objects \
            .with_is_successful().get(pk=run.pk)
        self.assertTrue(annotated.success)
        self.assertFalse(annotated.is_get_feature_failed)

    def test_csw_run_with_failing_get_records_check_is_not_successful(self):
        run = CatalogueServiceMonitoringRun.objects.create(
            setting=self.csw_setting)
        CatalogueServiceGetRecordsProbeResult.objects.create(
            run=run,
            monitored_uri=MONITORED_URI,
            check_response_is_valid_xml_success=True,
            check_response_does_contain_success=False,
            check_response_does_not_contain_success=True)

        self.assertFalse(
            CatalogueServiceMonitoringRun.objects
            .with_is_successful().get(pk=run.pk).success)

    def test_wms_run_with_failing_get_map_check_is_not_successful(self):
        run = WebMapServiceMonitoringRun.objects.create(
            setting=self.wms_setting)
        GetMapProbeResult.objects.create(
            run=run,
            monitored_uri=MONITORED_URI,
            check_response_image_success=False,
            check_response_does_not_contain_success=True)

        self.assertFalse(
            WebMapServiceMonitoringRun.objects
            .with_is_successful().get(pk=run.pk).success)
