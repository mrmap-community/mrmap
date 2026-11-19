"""The deletion semantics which the monitoring history answers today (#1484).

#1484 is a DECISION ticket: whether the FK of a run or a probe to its setting
stays CASCADE or becomes a retention rule is asked of a human and not answered
yet (the decision requests on the issue are open). What this module fixes is
the semantics as they are while that question is open - the baseline which the
issue demands "either way" and against which the eventual on_delete migration
is measured: keeping CASCADE keeps these assertions green, changing the
semantics moves exactly these of them that the migration decides about.

What the assertions ask is what the deployment reads:

* every run, probe and probe result hangs under its setting - the alert
  derivation reaches a run through `setting__service_id`
  (`registry/querys/alerts.py`) and the nested endpoints hang runs, probes and
  results below the setting (`registry/urls.py`);
* the only retention which this family stores today is the SET_NULL of a run
  onto its background process (`registry/models/monitoring.py`) - the audit
  line of #1484 names exactly this asymmetry;
* a setting is bound to its service with CASCADE, so monitoring history never
  survives the service either.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils.timezone import now
from django_celery_beat.models import IntervalSchedule
from notify.models import BackgroundProcess
from registry.models.monitoring import (
    CatalogueServiceGetCapabilitiesProbe,
    CatalogueServiceGetCapabilitiesProbeResult,
    CatalogueServiceGetRecordsProbe, CatalogueServiceGetRecordsProbeResult,
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetCapabilitiesProbe, GetCapabilitiesProbeResult, GetMapProbe,
    GetMapProbeResult, WebFeatureServiceGetCapabilitiesProbe,
    WebFeatureServiceGetCapabilitiesProbeResult,
    WebFeatureServiceGetFeatureProbe,
    WebFeatureServiceGetFeatureProbeResult, WebFeatureServiceMonitoringRun,
    WebFeatureServiceMonitoringSetting, WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebFeatureService, \
    WebMapService

#: the service of WMS_ONE answers its alerts in `test_alert...` below
WMS_ONE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"

#: the second service of the wms fixture, torn down as a whole below
WMS_TWO = "1b195589-dcfa-403f-9e66-e7e1c0a67024"

#: the wfs and csw fixtures answer their one service under this same pk
MONITORED_OTHER = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

MONITORED_URI = "https://www.example.de/service"

#: the kinds whose monitoring is stored per setting, run and probe result.
#: The deletion rules below are the same for every kind, so every assertion
#: runs through all three of them instead of trusting one to speak for all.
MONITORED_KINDS = (
    {
        "service_model": WebMapService,
        "service_pk": WMS_ONE,
        "setting_model": WebMapServiceMonitoringSetting,
        "run_model": WebMapServiceMonitoringRun,
        "probe_models": (GetCapabilitiesProbe, GetMapProbe),
        "result_models": (GetCapabilitiesProbeResult, GetMapProbeResult),
    },
    {
        "service_model": WebFeatureService,
        "service_pk": MONITORED_OTHER,
        "setting_model": WebFeatureServiceMonitoringSetting,
        "run_model": WebFeatureServiceMonitoringRun,
        "probe_models": (WebFeatureServiceGetCapabilitiesProbe,
                         WebFeatureServiceGetFeatureProbe),
        "result_models": (WebFeatureServiceGetCapabilitiesProbeResult,
                          WebFeatureServiceGetFeatureProbeResult),
    },
    {
        "service_model": CatalogueService,
        "service_pk": MONITORED_OTHER,
        "setting_model": CatalogueServiceMonitoringSetting,
        "run_model": CatalogueServiceMonitoringRun,
        "probe_models": (CatalogueServiceGetCapabilitiesProbe,
                         CatalogueServiceGetRecordsProbe),
        "result_models": (CatalogueServiceGetCapabilitiesProbeResult,
                          CatalogueServiceGetRecordsProbeResult),
    },
)


class MonitoringHistoryDeletionBaselineTest(TestCase):
    """What dies with a monitoring setting and what survives it, as of today.

    A monitoring run is created by the periodic task of a setting and knows
    only its setting and its background process - there is no second path to
    a run. These tests build the smallest real history of a service (setting,
    run, one result of every probe kind, one probe configuration of every
    probe kind) and delete exactly one object of the family, so that every
    assertion names the deletion rule of one FK of `monitoring.py` and nothing
    else.
    """

    # the service fixtures carry simple-history rows naming "User1", so the
    # user fixture is part of the load like in the neighbor monitoring tests
    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period='days')

    def build_history(self, kind):
        """The smallest real monitoring history of one kind of service.

        Creating a run registers the dispatch of its probes with the commit -
        a plain TestCase never commits, so no task is sent and no probe is
        executed; the rows below are the state a finished run leaves behind.

        Returns:
            tuple: service, setting and run of the history
        """
        service = kind["service_model"].objects.get(pk=kind["service_pk"])
        setting = kind["setting_model"].objects.create(
            service=service, interval=self.interval)
        run = kind["run_model"].objects.create(setting=setting)
        for result_model in kind["result_models"]:
            # which probe checks a result answers is decided by the probe
            # kind, so every success the concrete result really stores is
            # stated as passed - GetMapProbeResult has no xml checks and the
            # getfeature results have no image check
            stored = {field.name for field in result_model._meta.get_fields()}
            result_model.objects.create(
                **{"run": run, "monitored_uri": MONITORED_URI},
                **{name: True for name in (
                    "check_response_is_valid_xml_success",
                    "check_response_does_contain_success",
                    "check_response_does_not_contain_success",
                    "check_response_image_success") if name in stored})
        for probe_model in kind["probe_models"]:
            probe_model.objects.create(setting=setting)
        return service, setting, run

    def assert_history_exists(self, kind):
        """The rows which build the history of a kind are all stored"""
        self.assertEqual(
            sum(model.objects.count() for model in kind["result_models"]),
            len(kind["result_models"]))
        self.assertEqual(
            sum(model.objects.count() for model in kind["probe_models"]),
            len(kind["probe_models"]))

    def assert_history_is_gone(self, kind):
        """No run, probe or result of a kind is stored any more"""
        self.assertEqual(kind["run_model"].objects.count(), 0)
        for result_model in kind["result_models"]:
            self.assertEqual(
                result_model.objects.count(), 0,
                f"{result_model.__name__} survived its setting")
        for probe_model in kind["probe_models"]:
            self.assertEqual(
                probe_model.objects.count(), 0,
                f"{probe_model.__name__} survived its setting")

    def test_setting_deletion_wipes_runs_probes_and_results(self):
        """Today: run.setting, probe.setting and result.run are all CASCADE.

        Deleting a monitoring setting deletes every run of the setting, every
        result of these runs and every probe configuration of the setting -
        the whole monitoring history which the alerts of the service derive
        their state from. The service itself is not touched, it only stops
        having a history.

        This is the cascade whose retention #1484 asks about: a human decision
        which changes one of these three FKs has to move this baseline, and
        the migration which keeps CASCADE leaves it standing.
        """
        for kind in MONITORED_KINDS:
            with self.subTest(service=kind["service_model"].__name__):
                service, setting, _ = self.build_history(kind)
                self.assert_history_exists(kind)

                setting.delete()

                self.assert_history_is_gone(kind)
                self.assertTrue(
                    kind["service_model"].objects.filter(pk=service.pk).exists(),
                    "deleting the setting deleted the service")

    def test_wiped_runs_leave_their_background_processes(self):
        """Today: a deleted run takes its process row no further than itself.

        The process which reported a wiped run in the background activity is
        not a row of the monitoring family - the FK points from the run to it
        and is SET_NULL. Deleting the run deletes the run row, not the process
        row, so the background activity keeps what it reported while the
        monitoring history is gone. The asymmetry which #1484 names - the run
        is kept past its process but not past its setting - is stated here
        from both sides.
        """
        _, setting, run = self.build_history(MONITORED_KINDS[0])
        process_id = run.background_process_id
        self.assertIsNotNone(
            process_id, "a created run does not report itself")

        setting.delete()

        self.assertEqual(
            WebMapServiceMonitoringRun.objects.count(), 0)
        self.assertTrue(
            BackgroundProcess.objects.filter(pk=process_id).exists(),
            "wiping the runs wiped the reported background processes")

    def test_run_survives_the_deletion_of_its_background_process(self):
        """Today: run.background_process is SET_NULL - the other rule.

        Deleting the process which reports a run leaves the run and its probe
        results standing with the FK nulled. This is the retention rule which
        #1484 weighs for the FK to the setting, documented beside the
        CASCADE baseline it is weighed against.
        """
        _, _, run = self.build_history(MONITORED_KINDS[0])
        run.refresh_from_db()
        process = run.background_process
        self.assertIsNotNone(process)

        process.delete()

        stored = WebMapServiceMonitoringRun.objects.filter(pk=run.pk).first()
        self.assertIsNotNone(
            stored, "the run died with its reporting background process")
        self.assertIsNone(
            stored.background_process_id,
            "the FK of the run to its process did not answer SET_NULL")
        self.assertEqual(
            GetCapabilitiesProbeResult.objects.filter(run=stored).count(), 1,
            "the results of the surviving run did not survive it")

    def test_alert_state_of_a_service_with_wiped_history_is_silent(self):
        """Today: after the wipe the alerts re-derive from nothing, silently.

        The attention of a service is decided by its newest run and its newest
        failing run being the same row (`registry/querys/alerts.py`). A service
        whose failing run dies with its setting therefore answers no monitoring
        alert any more - not an alert about the lost history. Whatever #1484
        decides, the derivation itself reads runs through the setting and this
        behavior of the derivation does not move; what the decision changes is
        whether the history is gone at this point at all.
        """
        kind = MONITORED_KINDS[0]
        service = kind["service_model"].objects.get(pk=WMS_ONE)
        setting = kind["setting_model"].objects.create(
            service=service, interval=self.interval)
        run = kind["run_model"].objects.create(
            setting=setting, date_created=now() - timedelta(hours=1))
        GetCapabilitiesProbeResult.objects.create(
            run=run, monitored_uri=MONITORED_URI,
            check_response_is_valid_xml_success=False,
            check_response_is_valid_xml_message="no xml",
            check_response_does_contain_success=True,
            check_response_does_not_contain_success=True)

        failing = WebMapService.objects.with_alert_information().get(
            pk=service.pk)
        self.assertTrue(
            failing.monitoring_failed,
            "a failing newest run does not answer the monitoring alert")

        setting.delete()

        wiped = WebMapService.objects.with_alert_information().get(
            pk=service.pk)
        self.assertFalse(
            wiped.monitoring_failed,
            "a service without history answers an alert it cannot derive")

    def test_service_deletion_tears_down_setting_and_history_together(self):
        """Today: setting.service is CASCADE - history never outlives a service.

        Whatever retention #1484 decides for the FK to the setting, deleting
        the service deletes its setting and with it every run, probe and
        result. A run which should outlive its configuration cannot be reached
        through the service it was made for any more - which is why SET_NULL
        below the setting stores history no service question answers.
        """
        kind = MONITORED_KINDS[0]
        # the second service of the wms fixture, so the first one keeps the
        # state which the other tests of this module rely on untouched
        service = WebMapService.objects.get(pk=WMS_TWO)
        setting = kind["setting_model"].objects.create(
            service=service, interval=self.interval)
        run = kind["run_model"].objects.create(setting=setting)
        GetCapabilitiesProbeResult.objects.create(
            run=run, monitored_uri=MONITORED_URI)

        service.delete()

        self.assertEqual(
            WebMapServiceMonitoringSetting.objects.count(), 0,
            "a setting survived the deletion of its service")
        self.assert_history_is_gone(kind)
