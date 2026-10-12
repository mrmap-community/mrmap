from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from guardian.shortcuts import assign_perm
from notify.enums import LogTypeEnum, ProcessNameEnum, ProcessStatusEnum
from notify.filters import BackgroundProcessFilterSet
from notify.models import BackgroundProcess, BackgroundProcessLog
from registry.models.service import WebFeatureService, WebMapService

WMS_PK = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"


class BackgroundProcessReportingTests(TestCase):
    """Tests the report which a job writes in its background process.

    A background process is only the report of work which happens elsewhere, so
    the state of a running process is written by the job which owns it, while a
    process which decided about itself - usually by an abort - must not be
    overwritten by the work which is still in flight.
    """

    def setUp(self):
        self.process = BackgroundProcess.objects.create(
            phase="queued",
            process_type=ProcessNameEnum.UPDATE.value,
            description="update of a service")

    def info(self):
        return BackgroundProcess.objects.process_info().get(pk=self.process.pk)

    def test_report_updates_an_active_process(self):
        updated = BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING,
            phase="reading capabilities")

        self.assertEqual(1, updated)
        self.assertEqual(ProcessStatusEnum.RUNNING, self.info().status)
        self.assertEqual("reading capabilities", self.info().phase)
        self.assertIsNone(self.info().done_at)

    def test_report_does_not_overwrite_a_process_which_decided_about_itself(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.ABORTED)
        aborted = self.info()

        updated = BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.COMPLETED, phase="updated")

        self.assertEqual(0, updated)
        self.assertEqual(ProcessStatusEnum.ABORTED, self.info().status)
        self.assertEqual("queued", self.info().phase)
        self.assertEqual(aborted.done_at, self.info().done_at)

    def test_report_counts_a_step_towards_the_total(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, total_steps=4)
        for _ in range(2):
            BackgroundProcess.objects.report(
                self.process.pk, ProcessStatusEnum.RUNNING, step_done=True)

        process = self.info()
        self.assertEqual(2, process.done_steps)
        self.assertEqual(4, process.total_steps)
        self.assertEqual(50.0, process.progress)

    def test_report_marks_a_terminal_process_as_done(self):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, total_steps=3)
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.FAILED)

        process = self.info()
        self.assertEqual(ProcessStatusEnum.FAILED, process.status)
        self.assertIsNotNone(process.done_at)

    def test_report_without_a_process_does_nothing(self):
        self.assertEqual(
            0,
            BackgroundProcess.objects.report(None, ProcessStatusEnum.RUNNING))

    @patch("notify.managers.post_save")
    def test_report_informs_the_listeners_of_the_process(self, post_save):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING, total_steps=2,
            step_done=True)

        post_save.send.assert_called_once()
        instance = post_save.send.call_args.kwargs["instance"]
        self.assertEqual(self.process.pk, instance.pk)
        self.assertFalse(post_save.send.call_args.kwargs["created"])
        # the listeners render the payload of the process, so the instance which
        # is handed over has to carry the state which was just written
        self.assertEqual(1, instance.done_steps)
        self.assertEqual(50.0, instance.progress)

    @patch("notify.managers.post_save")
    def test_report_of_a_process_which_was_not_updated_informs_nobody(
            self, post_save):
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.COMPLETED)
        BackgroundProcess.objects.report(
            self.process.pk, ProcessStatusEnum.RUNNING)

        # only the report which really moved the process informed the listeners
        post_save.send.assert_called_once()

    def test_log_adds_an_entry_which_belongs_to_the_process(self):
        entry = BackgroundProcess.objects.log(
            self.process.pk, "the remote service did not answer")

        self.assertEqual(LogTypeEnum.ERROR, entry.log_type)
        self.assertEqual(
            1, BackgroundProcessLog.objects.filter(
                background_process=self.process).count())

    def test_log_without_a_process_stays_without_an_entry(self):
        self.assertIsNone(BackgroundProcess.objects.log(None, "nothing to log"))
        self.assertEqual(0, BackgroundProcessLog.objects.count())


class BackgroundProcessVisibilityTests(TestCase):
    """Tests which processes a user may see.

    A process names its resource with a generic relation, so the permission to
    see a process is the permission to see the resource it reports. A process
    without a resource cannot be decided that way and stays visible, because a
    registration for example only learns its service while it runs.
    """

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_wfs.json"]

    WFS_PK = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"

    def setUp(self):
        self.user = get_user_model().objects.get(username="User2")
        self.service = WebMapService.objects.get(pk=WMS_PK)
        self.of_service = BackgroundProcess.objects.create(
            phase="running",
            process_type=ProcessNameEnum.MONITORING.value,
            description="monitoring of the service",
            related_resource_type=ContentType.objects.get_for_model(
                WebMapService),
            related_id=self.service.pk)
        self.resourceless = BackgroundProcess.objects.create(
            phase="running",
            process_type=ProcessNameEnum.REGISTERING.value,
            description="registering a new service")

    def visible_ids(self):
        return set(BackgroundProcess.objects.visible_for_user(
            self.user).values_list("pk", flat=True))

    def test_a_process_of_a_resource_without_permission_is_not_visible(self):
        self.assertEqual({self.resourceless.pk}, self.visible_ids())

    def test_a_process_of_a_resource_the_user_may_view_is_visible(self):
        assign_perm("registry.view_webmapservice", self.user, self.service)

        self.assertEqual(
            {self.of_service.pk, self.resourceless.pk}, self.visible_ids())

    def test_a_process_of_another_resource_is_not_visible(self):
        assign_perm(
            "registry.view_webfeatureservice", self.user,
            WebFeatureService.objects.get(pk=self.WFS_PK))

        self.assertEqual({self.resourceless.pk}, self.visible_ids())

    def test_a_process_without_a_resource_is_always_visible(self):
        self.assertIn(self.resourceless.pk, self.visible_ids())

    def test_a_superuser_sees_every_process(self):
        superuser = get_user_model().objects.create_superuser(
            username="super", password="super", email="super@example.com")

        self.assertEqual(
            2, BackgroundProcess.objects.visible_for_user(superuser).count())


class BackgroundProcessFilterTests(TestCase):
    """Tests the filter of the overview of the background activity.

    The api answers the status of a process by the name of its choice, so the
    overview filters by these names and not by the numbers the database stores.
    """

    def setUp(self):
        self.processes = {
            status: BackgroundProcess.objects.create(
                phase=status.label,
                process_type=ProcessNameEnum.UPDATE.value,
                description=f"a {status.label} process",
                status=status)
            for status in ProcessStatusEnum}

    def filtered(self, **data):
        return BackgroundProcessFilterSet(
            data, queryset=BackgroundProcess.objects.all())

    def test_filters_one_status_by_its_name(self):
        self.assertEqual(
            [self.processes[ProcessStatusEnum.RUNNING]],
            list(self.filtered(status="running").qs))

    def test_filters_multiple_statuses_by_their_names(self):
        expected = {
            self.processes[ProcessStatusEnum.PENDING],
            self.processes[ProcessStatusEnum.RUNNING]}

        self.assertEqual(
            expected, set(self.filtered(status="pending,running").qs))

    def test_filters_a_status_by_the_number_the_database_stores(self):
        self.assertEqual(
            [self.processes[ProcessStatusEnum.FAILED]],
            list(self.filtered(status="3").qs))

    def test_keeps_every_process_without_a_status(self):
        self.assertEqual(5, self.filtered().qs.count())

    def test_refuses_a_status_which_does_not_exist(self):
        filterset = self.filtered(status="scheduled")

        self.assertFalse(filterset.is_valid())
        self.assertIn("invalid_choice", filterset.errors["status"].as_data()[0].code)

    def test_still_filters_the_fields_of_the_previous_filter(self):
        self.assertEqual(
            [self.processes[ProcessStatusEnum.ABORTED]],
            list(self.filtered(phase__icontains="aborted").qs))
