"""The draft-preview endpoint of #1327: inform before saving, write nothing.

The tests answer the acceptance criteria of the issue directly: a permitted
user previews a draft of a monitoring, update or harvesting schedule and
gets the coming occurrences, the wait between them and the honest elapsed
history; the answer never writes - no row, no queue submission, no
`CrontabSchedule` - and no answer rejects a save. Permissions mirror the
CRUD path: the service must be visible, an edit needs `change` on its
setting, a draft needs the `add` permission; a foreign setting or another
organisation's service is answered as an error and never as data.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.timezone import now
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from extras.scheduling import next_run_occurrences
from guardian.shortcuts import assign_perm
from notify.enums import ProcessNameEnum, ProcessStatusEnum
from notify.models import BackgroundProcess
from registry.enums.capacity import EstimateGapEnum
from registry.models.harvest import HarvestingJob
from registry.models.monitoring import (
    WebMapServiceMonitoringRun, WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebMapService
from registry.querys.capacity import DraftSchedule
from registry.views.scheduling import SchedulingPreviewView
from rest_framework.test import APIRequestFactory, force_authenticate

JSONAPI = "application/vnd.api+json"

WMS_ONE = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'
WMS_TWO = '1b195589-dcfa-403f-9e66-e7e1c0a67024'
CSW_ONE = "9cc4889d-0cd4-4c3b-8975-58de6d30db41"


class _RanSetting:
    """A setting row stand-in carrying only the baseline of a schedule.

    Used to step a crontab across a known DST boundary through the very
    same `DraftSchedule` the estimator and the preview endpoint share.
    """

    def __init__(self, last_run_at):
        self.last_run_at = last_run_at
        self.date_changed = last_run_at
        self.enabled = True
        self.one_off = False
        self.total_run_count = 0
        self.start_time = None
        self.expires = None


class SchedulePreviewTestCase(TestCase):
    """Shared fixtures: services, a permitted caller and the ask helper."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def setUp(self):
        self.factory = APIRequestFactory()
        self.wms = WebMapService.objects.get(pk=WMS_ONE)
        self.other_wms = WebMapService.objects.get(pk=WMS_TWO)
        self.csw = CatalogueService.objects.get(pk=CSW_ONE)
        self.manager = get_user_model().objects.create_user(
            username='preview-manager')
        assign_perm('registry.view_webmapservice', self.manager, self.wms)
        assign_perm('registry.add_webmapservicemonitoringsetting',
                    self.manager)
        self.admin = get_user_model().objects.create_superuser(
            username='preview-admin', email='preview@example.com',
            password='x')

    def post_preview(self, document, user=None):
        """One POST of the preview endpoint, answered as the renderer wrote it."""
        request = self.factory.post(
            reverse('registry:scheduling-preview'),
            data=json.dumps(document), content_type=JSONAPI,
            HTTP_ACCEPT=JSONAPI)
        if user is not None:
            force_authenticate(request, user=user)
        response = SchedulingPreviewView.as_view()(request)
        response.render()
        return response

    def ask(self, attributes, user):
        """One draft question as a schedule screen would send it."""
        response = self.post_preview(
            {'data': {'type': 'SchedulingPreview',
                      'attributes': attributes}}, user)
        if response.status_code >= 400:
            return response, None
        return response, json.loads(response.content)['data']['attributes']

    def draft(self, **overrides):
        """A monitoring draft of the first WMS as the form would send it."""
        attributes = {
            'operation': 'monitoring',
            'service_kind': 'WebMapService',
            'service_id': str(self.wms.pk),
            'scheduling': '0 8 * * *',
            'timezone': 'UTC',
            'enabled': True,
        }
        attributes.update(overrides)
        return attributes

    def crontab(self, scheduling='*/5 * * * *', tz='UTC'):
        """A crontab row as the schedule screen would have made it."""
        minute, hour, day_of_month, month_of_year, day_of_week = \
            scheduling.split()
        return CrontabSchedule.objects.create(
            minute=minute, hour=hour, day_of_month=day_of_month,
            month_of_year=month_of_year, day_of_week=day_of_week,
            timezone=ZoneInfo(tz))

    def monitoring_setting(self, service=None, scheduling='*/5 * * * *',
                           enabled=False, **kwargs):
        """A saved monitoring schedule; disabled by default on purpose."""
        return WebMapServiceMonitoringSetting.objects.create(
            service=service or self.wms,
            crontab=self.crontab(scheduling),
            name=str(id(self)), enabled=enabled, **kwargs)

    def monitoring_run(self, setting, duration, ended=None):
        """A completed successful monitoring run which took `duration`."""
        process = BackgroundProcess.objects.create(
            phase="Preview test", process_type=ProcessNameEnum.MONITORING.value,
            description="preview test", status=ProcessStatusEnum.COMPLETED)
        # a run without failing probe results is successful by the very
        # annotation `with_is_successful` answers - there is no field
        run = WebMapServiceMonitoringRun.objects.create(
            setting=setting, background_process=process)
        ended = ended or now()
        WebMapServiceMonitoringRun.objects.filter(pk=run.pk).update(
            date_created=ended - duration, date_done=ended)
        return run


class DraftPreviewTest(SchedulePreviewTestCase):
    """What the answer says - and that answering it changes nothing."""

    def test_draft_answers_occurrences_interval_and_provenance(self):
        response, attributes = self.ask(self.draft(), self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(attributes['operation'], 'monitoring')
        self.assertEqual(attributes['scheduling'], '0 8 * * * UTC')
        self.assertTrue(attributes['enabled'])
        occurrences = attributes['nextOccurrences']
        self.assertEqual(len(occurrences), 3)
        self.assertEqual(occurrences, sorted(occurrences))
        self.assertGreater(attributes['intervalSeconds'], 0)
        # honest provenance: nothing completed yet says so as a gap
        self.assertEqual(attributes['elapsed']['sampleCount'], 0)
        self.assertIsNone(attributes['elapsed']['p95Seconds'])
        self.assertIn(EstimateGapEnum.NO_COMPLETED_RUNS.value,
                      attributes['warningCodes'])
        # no reliable capacity telemetry exists, and the answer says why
        self.assertIsNone(attributes['capacity'])
        self.assertTrue(attributes['capacityReason'])
        self.assertIn('expiresAt', attributes)
        self.assertIn('asOf', attributes)
        self.assertLess(attributes['asOf'], attributes['expiresAt'])
        self.assertIsNone(attributes['settingRevision'])

    def test_preview_writes_nothing_and_queues_nothing(self):
        before = {
            'tasks': PeriodicTask.objects.count(),
            'crontabs': CrontabSchedule.objects.count(),
            'runs': WebMapServiceMonitoringRun.objects.count(),
            'harvests': HarvestingJob.objects.count(),
            'processes': BackgroundProcess.objects.count(),
        }
        with CaptureQueriesContext(connection) as queries:
            with mock.patch('celery.app.base.Celery.send_task') as sender:
                response, attributes = self.ask(self.draft(), self.admin)
        self.assertEqual(response.status_code, 200, response.content)
        sender.assert_not_called()
        self.assertEqual({
            'tasks': PeriodicTask.objects.count(),
            'crontabs': CrontabSchedule.objects.count(),
            'runs': WebMapServiceMonitoringRun.objects.count(),
            'harvests': HarvestingJob.objects.count(),
            'processes': BackgroundProcess.objects.count(),
        }, before)
        # the request is answered by SELECTs alone - no statement of the
        # save path, no INSERT on the CrontabSchedule the proposal reuses
        writing = [q['sql'] for q in queries.captured_queries
                   if q['sql'].lstrip().upper().startswith(
                       ('INSERT', 'UPDATE', 'DELETE'))]
        self.assertEqual(writing, [])

    def test_a_measured_history_answers_p50_and_the_tight_interval_warning(self):
        """the #693 rule as an explained risk, not as a rejected save"""
        setting = self.monitoring_setting(
            scheduling='*/5 * * * *', enabled=True)
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, setting)
        self.monitoring_run(setting, timedelta(minutes=10))

        response, attributes = self.ask(
            self.draft(scheduling='*/5 * * * *', setting_id=setting.pk),
            self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(attributes['elapsed']['sampleCount'], 1)
        self.assertEqual(attributes['elapsed']['p50Seconds'], 600)
        # one observation answers no p95 - the gap is said, not guessed
        self.assertIsNone(attributes['elapsed']['p95Seconds'])
        self.assertIn(EstimateGapEnum.INSUFFICIENT_SAMPLES.value,
                      attributes['warningCodes'])
        # 5 minutes of wait against 10 minutes of elapsed - a flagged risk
        self.assertIs(attributes['potentialOverlap'], True)
        self.assertIn('schedule_tighter_than_elapsed',
                      attributes['warningCodes'])
        self.assertEqual(attributes['overlapBasis'], 'median')

    def test_disabled_and_one_off_drafts_are_answered_as_themselves(self):
        setting = self.monitoring_setting(scheduling='0 8 * * *',
                                          enabled=False)
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, setting)

        response, attributes = self.ask(
            {'operation': 'monitoring', 'service_kind': 'WebMapService',
             'service_id': str(self.wms.pk), 'setting_id': setting.pk},
            self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        # an edit without explicit fields previews the saved row as it is
        self.assertIs(attributes['enabled'], False)
        self.assertEqual(attributes['scheduling'], '0 8 * * * UTC')
        self.assertIn(EstimateGapEnum.SCHEDULE_DISABLED.value,
                      attributes['warningCodes'])
        self.assertIsNone(attributes['intervalSeconds'])
        self.assertEqual(attributes['nextOccurrences'], [])
        self.assertIsNotNone(attributes['settingRevision'])

    def test_enabling_a_disabled_setting_previews_the_proposed_contribution(self):
        """disabled -> enabled counts the proposal, not the saved row"""
        setting = self.monitoring_setting(scheduling='*/5 * * * *',
                                          enabled=False)
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, setting)

        response, attributes = self.ask(
            self.draft(scheduling='*/5 * * * *', setting_id=setting.pk,
                       enabled=True),
            self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(attributes['enabled'], True)
        self.assertNotIn(EstimateGapEnum.SCHEDULE_DISABLED.value,
                         attributes['warningCodes'])

    def test_start_time_of_the_draft_moves_the_first_occurrence_only_in_memory(self):
        start = now() + timedelta(days=7)
        before = (PeriodicTask.objects.count(),
                  CrontabSchedule.objects.count())
        response, attributes = self.ask(
            self.draft(startTime=start.isoformat()), self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertGreaterEqual(
            datetime.fromisoformat(attributes['nextOccurrences'][0]), start)
        # the answered row was never a row: no schedule was written -
        # while the fixtures may already carry schedules of their own
        self.assertEqual((
            PeriodicTask.objects.count(),
            CrontabSchedule.objects.count()), before)

    def test_all_three_families_are_previewable(self):
        self.assertEqual(
            self.ask(self.draft(), self.manager)[0].status_code, 200)
        self.assertEqual(self.ask(
            self.draft(operation='update'), self.admin)[0].status_code, 200)
        self.assertEqual(self.ask({
            'operation': 'harvest', 'service_kind': 'CatalogueService',
            'service_id': str(self.csw.pk), 'scheduling': '0 12 * * 1-5 UTC+2',
            'enabled': True}, self.admin)[0].status_code, 200)

    def test_harvesting_timezone_suffix_is_resolved_and_echoed(self):
        response, attributes = self.ask({
            'operation': 'harvest', 'service_kind': 'CatalogueService',
            'service_id': str(self.csw.pk),
            'scheduling': '0 12 * * 1-5 UTC+2', 'enabled': True}, self.admin)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(attributes['scheduling'], '0 12 * * 1-5 Etc/GMT-2')
        self.assertEqual(len(attributes['nextOccurrences']), 3)


class PreviewValidationTest(SchedulePreviewTestCase):
    """Honest errors where a draft answers no schedule at all."""

    def test_unparsable_crontab_answers_a_field_error(self):
        response, _ = self.ask(self.draft(scheduling='every five minutes'),
                               self.manager)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(b'scheduling', response.content)

    def test_a_timezone_suffix_is_an_error_for_the_monitoring_family(self):
        """its save path takes five fields - the preview answers the same"""
        response, _ = self.ask(
            self.draft(scheduling='0 12 * * 1-5 UTC+2'), self.manager)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(b'expected 5 fields', response.content)

    def test_celery_rejects_fields_that_parse_as_words_but_are_no_cron(self):
        response, _ = self.ask(self.draft(scheduling='* * * * 99'),
                               self.manager)
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_new_schedule_without_a_crontab_is_answered_as_incomplete(self):
        response, _ = self.ask(self.draft(scheduling=''), self.manager)
        self.assertEqual(response.status_code, 400, response.content)

    def test_an_unsupported_family_pair_is_a_field_error(self):
        response, _ = self.ask(self.draft(operation='harvest'), self.manager)
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn(b'operation', response.content)

    def test_an_unknown_service_is_not_found_not_empty(self):
        response, _ = self.ask(
            self.draft(service_id='1b195589-dcfa-403f-9e66-e7e1c0a60000'),
            self.admin)
        self.assertEqual(response.status_code, 404, response.content)

    def test_a_document_without_data_is_rejected(self):
        response = self.post_preview({'attributes': {}}, self.admin)
        self.assertEqual(response.status_code, 400, response.content)


class PreviewPermissionTest(SchedulePreviewTestCase):
    """Who may ask, and the boundary a foreign setting must not cross."""

    def test_anonymous_callers_are_refused(self):
        response = self.post_preview({'data': {'attributes': self.draft()}})
        self.assertEqual(response.status_code, 403, response.content)

    def test_a_user_without_any_permission_is_refused(self):
        nobody = get_user_model().objects.create_user(username='preview-none')
        response, _ = self.ask(self.draft(), nobody)
        self.assertEqual(response.status_code, 403, response.content)

    def test_view_on_the_service_alone_does_not_preview_a_new_schedule(self):
        viewer = get_user_model().objects.create_user(username='preview-view')
        assign_perm('registry.view_webmapservice', viewer, self.wms)
        response, _ = self.ask(self.draft(), viewer)
        self.assertEqual(response.status_code, 403, response.content)

    def test_add_permission_without_view_on_the_service_is_refused(self):
        adder = get_user_model().objects.create_user(username='preview-add')
        assign_perm('registry.add_webmapservicemonitoringsetting', adder)
        response, _ = self.ask(self.draft(), adder)
        self.assertEqual(response.status_code, 403, response.content)

    def test_editing_requires_the_change_permission_on_the_setting(self):
        setting = self.monitoring_setting()
        response, _ = self.ask(
            {'operation': 'monitoring', 'service_kind': 'WebMapService',
             'service_id': str(self.wms.pk), 'setting_id': setting.pk},
            self.manager)
        self.assertEqual(response.status_code, 403, response.content)

    def test_a_foreign_setting_never_probes_the_asked_service(self):
        """the setting must be the setting of the service it is answered on"""
        other_setting = self.monitoring_setting(service=self.other_wms)
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, other_setting)
        response, _ = self.ask(
            {'operation': 'monitoring', 'service_kind': 'WebMapService',
             'service_id': str(self.wms.pk),
             'setting_id': other_setting.pk},
            self.manager)
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_service_of_another_scope_never_answers_through_its_setting(self):
        setting = self.monitoring_setting(service=self.other_wms)
        # the caller may everything on the setting but sees no service
        assign_perm('registry.change_webmapservicemonitoringsetting',
                    self.manager, setting)
        response, _ = self.ask(
            {'operation': 'monitoring', 'service_kind': 'WebMapService',
             'service_id': str(self.other_wms.pk),
             'setting_id': setting.pk},
            self.manager)
        self.assertEqual(response.status_code, 403, response.content)


class NextOccurrencesDSTTest(TestCase):
    """The stepping of `next_run_occurrences` across a DST boundary."""

    def test_occurrences_span_the_spring_change_with_23_hours(self):
        berlin = ZoneInfo('Europe/Berlin')
        crontab = CrontabSchedule(
            minute='0', hour='3', day_of_month='*', month_of_year='*',
            day_of_week='*', timezone=berlin)
        baseline = datetime(2026, 3, 27, 3, 0, tzinfo=berlin)
        effective = DraftSchedule(
            _RanSetting(baseline), crontab, True, baseline)

        occurrences = next_run_occurrences(effective, count=3)

        self.assertEqual(len(occurrences), 3)
        self.assertEqual(occurrences, sorted(occurrences))
        # the moments keep the zone of the crontab; the distance is asked of
        # the instants, because CPython subtracts two moments sharing one
        # tzinfo object by their wall time and would hide the shifted hour
        instants = [moment.astimezone(timezone.utc) for moment in occurrences]
        self.assertEqual(
            instants, [moment.astimezone(timezone.utc)
                       for moment in sorted(instants)])
        first_gap = instants[1] - instants[0]
        second_gap = instants[2] - instants[1]
        # Berlin springs forward on 29 March 2026: the run of that night
        # waits 23 hours, the next one the full 24 again
        self.assertEqual(first_gap, timedelta(hours=23))
        self.assertEqual(second_gap, timedelta(hours=24))
        # the schedule answers the wall clock of its zone: 03:00 stays 03:00
        # before and after the change, only the offset moves
        self.assertEqual(
            [moment.strftime('%Y-%m-%d %H:%M %Z') for moment in occurrences],
            ['2026-03-28 03:00 CET', '2026-03-29 03:00 CEST',
             '2026-03-30 03:00 CEST'])
