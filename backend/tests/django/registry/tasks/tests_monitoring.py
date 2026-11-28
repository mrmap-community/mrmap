from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ObjectDoesNotExist
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TransactionTestCase
from django.test.utils import override_settings
from django_celery_beat.models import IntervalSchedule
from MrMap.celery import app
from MrMap.settings import BASE_DIR
from notify.enums import ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.models.monitoring import (
    CatalogueServiceMonitoringRun, CatalogueServiceMonitoringSetting,
    GetCapabilitiesProbe,
    GetCapabilitiesProbeResult,
    GetMapProbe, GetMapProbeResult,
    WebFeatureServiceMonitoringRun, WebFeatureServiceMonitoringSetting,
    WebMapServiceMonitoringRun,
    WebMapServiceMonitoringSetting)
from registry.models.service import (CatalogueService, WebFeatureService,
                                     WebMapService)
from registry.ows_lib.client.core import OgcClient
from registry.ows_lib.csw.csw import CatalogueServiceClient
from registry.ows_lib.wfs.wfs import WebFeatureServiceClient
from registry.tasks.monitoring import (create_csw_monitoring_run,
                                       create_wfs_monitoring_run,
                                       create_wms_monitoring_run)
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, timeout):
    if "ServiceException" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/wms_service_exception.xml')))

    elif "GetCapabilities" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/dwd_wms_1.3.0.xml')))
    elif "GetMap" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/karte_rp.fcgi.png')))
    elif "GetFeatureInfo" in request.url:
        return MockResponse(
            url=request.url,
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),

                                       '../../test_data/wms/feature_info.xml')))
    else:
        print(request.url)


def setup_capabilitites_file(service_exception_url=False):
    wms: WebMapService = WebMapService.objects.get(
        pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")

    if service_exception_url:
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.1.1_exception.xml", mode="rb")
    else:
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/1.1.1.xml", mode="rb")

    wms.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read(), content_type="application/xml")

    wms.save()


class WmsGetCapabilitiesMonitoringTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    def setUp(self):
        self.wms: WebMapService = WebMapService.objects.get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
        )
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.monitoring_setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.wms,
            interval=self.interval
        )

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_run_with_only_get_capabilities_probe(self, mocked_send_request):
        setup_capabilitites_file()
        GetCapabilitiesProbe.objects.create(setting=self.monitoring_setting)

        run = WebMapServiceMonitoringRun.objects.create(
            setting=self.monitoring_setting,
        )

        self.assertEqual(GetCapabilitiesProbeResult.objects.filter(run=run).count(), 1)
        self.assertFalse(GetMapProbeResult.objects.filter(run=run).exists())
        mocked_send_request.assert_called_once()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True)
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_run_with_only_get_map_probe(self, mocked_send_request):
        setup_capabilitites_file()
        probe = GetMapProbe.objects.create(setting=self.monitoring_setting)
        probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun.objects.create(
            setting=self.monitoring_setting,
        )

        self.assertEqual(GetMapProbeResult.objects.filter(run=run).count(), 1)
        self.assertFalse(GetCapabilitiesProbeResult.objects.filter(run=run).exists())
        mocked_send_request.assert_called_once()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_run_wms_monitoring(self, mocked_send_request,  mocked_on_commit):
        setup_capabilitites_file()
        cap_probe = GetCapabilitiesProbe.objects.create(
            setting=self.monitoring_setting,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            setting=self.monitoring_setting,
        )
        map_probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun(setting=self.monitoring_setting)
        run.save()

        self.assertEqual(1, GetCapabilitiesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())
        try:
            get_cap_result = GetCapabilitiesProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_cap_result.check_response_is_valid_xml_success)
            self.assertEqual(
                get_cap_result.check_response_is_valid_xml_message,
                "OK",
            )
            self.assertTrue(
                get_cap_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_not_contain_message,
                "OK"
            )
            self.assertTrue(
                get_cap_result.check_response_does_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_contain_message,
                "OK",
            )

            get_map_result = GetMapProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_map_result.check_response_image_success)
            self.assertEqual(
                get_map_result.check_response_image_message,
                "OK",
            )
            self.assertTrue(
                get_map_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_map_result.check_response_does_not_contain_message,
                "OK",
            )

        except ObjectDoesNotExist:
            self.fail("result was not found.")

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_run_wms_monitoring_with_service_exceptions(self, mocked_send_request,  mocked_on_commit):
        setup_capabilitites_file(service_exception_url=True)
        cap_probe = GetCapabilitiesProbe.objects.create(
            setting=self.monitoring_setting,
            check_response_is_valid_xml=True,
        )
        map_probe = GetMapProbe.objects.create(
            setting=self.monitoring_setting,
        )
        map_probe.layers.set(self.wms.layers.all())

        run = WebMapServiceMonitoringRun(setting=self.monitoring_setting)
        run.save()

        self.assertEqual(1, GetCapabilitiesProbeResult.objects.count())
        self.assertEqual(1, GetMapProbeResult.objects.count())

        try:
            get_cap_result = GetCapabilitiesProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertTrue(
                get_cap_result.check_response_is_valid_xml_success)
            self.assertEqual(
                get_cap_result.check_response_is_valid_xml_message,
                "OK",
            )

            self.assertFalse(
                get_cap_result.check_response_does_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_contain_message,
                "Title> is not part of the response. Abstract> is not part of the response. "
            )

            self.assertFalse(
                get_cap_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_cap_result.check_response_does_not_contain_message,
                "ExceptionReport> is part of the response. ServiceException> is part of the response. ",
            )

            get_map_result = GetMapProbeResult.objects.get(
                run__pk=run.pk,
            )
            self.assertFalse(
                get_map_result.check_response_image_success)
            self.assertEqual(
                get_map_result.check_response_image_message,
                "Could not create image from response.",
            )
            self.assertFalse(
                get_map_result.check_response_does_not_contain_success)
            self.assertEqual(
                get_map_result.check_response_does_not_contain_message,
                "ExceptionReport> is part of the response. ServiceException> is part of the response. "
            )

        except ObjectDoesNotExist:
            self.fail("result was not found.")


class MonitoringRunWithoutProbesTest(TransactionTestCase):
    """Tests the runs of a monitoring setting which has no probes (#1806).

    A setting is born without probes: they are a separate resource and nothing
    creates one together with the setting. The empty probe list used to short
    circuit the chain which executes the checks — celery applied the task which
    finishes the run without any argument at all — so every scheduled run of
    such a setting raised before its first check and its background process
    stayed "Running 0 checks" forever. A run which had nothing to check is a
    completed run: these tests hold that against all three kinds of setting.
    """

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wms.json', 'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period='hours')
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

    def assert_run_completed_without_checks(self, run):
        """The terminal state of a run which had nothing to check.

        The run itself is done and the process which reports it decided about
        itself: not the "running indeterminate" of a process which never
        learned its steps.
        """
        self.assertIsNotNone(run.date_done)
        # `failing_probe_checks()` names the result models of this kind of run
        for result_model, _query in type(run).failing_probe_checks().values():
            self.assertFalse(
                result_model.objects.filter(run=run).exists())

        process = BackgroundProcess.objects.process_info().get(
            pk=run.background_process_id)
        self.assertEqual(ProcessStatusEnum.COMPLETED, process.status)
        # the phase is the only answer why the run has no results at all
        self.assertEqual(
            "Completed without checks: the setting has no probes",
            process.phase)
        self.assertEqual(0, process.total_steps)
        self.assertEqual(0, process.done_steps)
        self.assertIsNotNone(process.done_at)
        self.assertEqual('completed', process.state)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_wms_run_of_a_setting_without_probes_completes(self):
        create_wms_monitoring_run.apply(args=(self.wms_setting.name,))

        self.assert_run_completed_without_checks(
            WebMapServiceMonitoringRun.objects.get(setting=self.wms_setting))

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_wfs_run_of_a_setting_without_probes_completes(self):
        create_wfs_monitoring_run.apply(args=(self.wfs_setting.name,))

        self.assert_run_completed_without_checks(
            WebFeatureServiceMonitoringRun.objects.get(
                setting=self.wfs_setting))

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_csw_run_of_a_setting_without_probes_completes(self):
        create_csw_monitoring_run.apply(args=(self.csw_setting.name,))

        self.assert_run_completed_without_checks(
            CatalogueServiceMonitoringRun.objects.get(
                setting=self.csw_setting))

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch('registry.tasks.monitoring.chain')
    def test_a_run_without_probes_dispatches_no_chain(self, mocked_chain):
        """Nothing to check means no fan-out to plan at all

        The chain of an empty group is the crash of #1806; a run which has
        nothing to check may never be handed to it.
        """
        create_wms_monitoring_run.apply(args=(self.wms_setting.name,))

        self.assertFalse(
            mocked_chain.called,
            msg='the run of a setting without probes was dispatched as a '
                'chain of an empty group')
        self.assert_run_completed_without_checks(
            WebMapServiceMonitoringRun.objects.get(setting=self.wms_setting))

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch('registry.tasks.monitoring.chain')
    def test_a_run_with_probes_still_dispatches_its_chain(self, mocked_chain):
        """The guard only answers the empty case, the fan-out stays as it was"""
        GetCapabilitiesProbe.objects.create(setting=self.wms_setting)

        create_wms_monitoring_run.apply(args=(self.wms_setting.name,))

        self.assertTrue(
            mocked_chain.called,
            msg='the run of a setting with probes was not dispatched as a '
                'chain of its checks')
        process = BackgroundProcess.objects.process_info().get(
            pk=WebMapServiceMonitoringRun.objects.get(
                setting=self.wms_setting).background_process_id)
        # the chain is mocked, so no check ran: the process plans its one
        # step and waits for it, as it did before the guard existed
        self.assertEqual(ProcessStatusEnum.RUNNING, process.status)
        self.assertEqual(1, process.total_steps)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_a_probe_added_after_the_run_is_not_reported_as_empty(
            self, mocked_send_request):
        """The guard only changes the answer of a run which really has none"""
        setup_capabilitites_file()
        GetCapabilitiesProbe.objects.create(setting=self.wms_setting)

        create_wms_monitoring_run.apply(args=(self.wms_setting.name,))

        run = WebMapServiceMonitoringRun.objects.get(setting=self.wms_setting)
        self.assertEqual(1, GetCapabilitiesProbeResult.objects.filter(
            run=run).count())
        process = BackgroundProcess.objects.process_info().get(
            pk=run.background_process_id)
        self.assertEqual("Running 1 checks", process.phase)
        self.assertEqual(1, process.total_steps)
        self.assertEqual(1, process.done_steps)


class MonitoringTaskRoutingTest(SimpleTestCase):
    def test_monitoring_tasks_route_to_a_consumed_queue(self):
        task_names = (
            "run_wms_monitoring",
            "run_wfs_monitoring",
            "run_csw_monitoring",
            "create_wms_monitoring_run",
            "create_wfs_monitoring_run",
            "create_csw_monitoring_run",
            "run_probe_check",
            "finish_run",
        )
        for task_name in task_names:
            with self.subTest(task=task_name):
                route = app.amqp.router.route(
                    {}, f"registry.tasks.monitoring.{task_name}",
                )
                self.assertEqual(route["queue"].name, "default")
                self.assertEqual(route["queue"].exchange.name, "default")
                self.assertEqual(route["queue"].routing_key, "default")


class WmsCapabilitiesRequestTest(SimpleTestCase):
    def test_get_capabilities_request_for_supported_wms_versions(self):
        for version in ("1.1.1", "1.3.0"):
            with self.subTest(version=version):
                xml = Path(
                    BASE_DIR, "tests/django/test_data/capabilities/wms",
                    f"{version}.xml",
                ).read_bytes()
                client = OgcClient(capabilities=xml)
                request = client.get_capabilities_request()
                self.assertEqual(request.method, "GET")
                self.assertIn("REQUEST=GetCapabilities", request.url)
                self.assertIn(f"VERSION={version}", request.url)
                self.assertTrue(request.url.startswith("http"))


class MonitoringRunCreationTest(TransactionTestCase):
    """Tests the tasks which are scheduled by a monitoring setting."""

    fixtures = ['test_users.json', 'test_keywords.json', 'test_crs.json',
                'test_wfs.json', 'test_csw.json']

    def setUp(self):
        self.interval = IntervalSchedule.objects.create(every=1, period='days')
        self.wfs_setting = WebFeatureServiceMonitoringSetting.objects.create(
            service=WebFeatureService.objects.get(
                pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41"),
            interval=self.interval)
        self.csw_setting = CatalogueServiceMonitoringSetting.objects.create(
            service=CatalogueService.objects.get(
                pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41"),
            interval=self.interval)

    @patch.object(
        target=WebFeatureServiceMonitoringRun, attribute="dispatch_run")
    def test_create_wfs_monitoring_run_creates_run_for_setting(
            self, mocked_dispatch_run):
        create_wfs_monitoring_run.apply(args=(self.wfs_setting.name,))

        self.assertEqual(
            1, WebFeatureServiceMonitoringRun.objects.filter(
                setting=self.wfs_setting).count())
        self.assertEqual(
            0, CatalogueServiceMonitoringRun.objects.count())

    @patch.object(
        target=CatalogueServiceMonitoringRun, attribute="dispatch_run")
    def test_create_csw_monitoring_run_creates_run_for_setting(
            self, mocked_dispatch_run):
        create_csw_monitoring_run.apply(args=(self.csw_setting.name,))

        self.assertEqual(
            1, CatalogueServiceMonitoringRun.objects.filter(
                setting=self.csw_setting).count())
        self.assertEqual(
            0, WebFeatureServiceMonitoringRun.objects.count())


class WfsGetFeatureRequestTest(SimpleTestCase):
    def test_get_feature_kvp_request_uses_version_specific_parameters(self):
        xml = Path(
            BASE_DIR, "tests/django/test_data/capabilities/wfs",
            "fixture_2.0.0.xml",
        ).read_bytes()
        client = WebFeatureServiceClient(capabilities=xml)
        request = client.get_feature_kvp_request(
            type_names=["dwd:dwd_is_sgv-geolinkamellen"],
            max_features=1,
            srs_name="CRS:84")

        self.assertEqual(request.method, "GET")
        self.assertIn("REQUEST=GetFeature", request.url)
        self.assertIn("VERSION=2.0.0", request.url)
        self.assertIn("TYPENAMES=dwd%3Adwd_is_sgv-geolinkamellen", request.url)
        self.assertIn("COUNT=1", request.url)
        self.assertIn("SRSNAME=CRS%3A84", request.url)


class CswGetRecordsRequestTest(SimpleTestCase):
    def test_get_records_request_uses_the_configured_probe_values(self):
        xml = Path(
            BASE_DIR, "tests/django/test_data/capabilities/csw",
            "2.0.2.xml",
        ).read_bytes()
        client = CatalogueServiceClient(capabilities=xml)
        request = client.get_records_request(
            type_names="gmd:MD_Metadata",
            result_type="results",
            element_set_name="summary",
            max_records=1)

        self.assertEqual(request.method, "GET")
        self.assertIn("REQUEST=GetRecords", request.url)
        self.assertIn("VERSION=2.0.2", request.url)
        self.assertIn("resultType=results", request.url)
        self.assertIn("elementSetName=summary", request.url)
        self.assertIn("maxRecords=1", request.url)
