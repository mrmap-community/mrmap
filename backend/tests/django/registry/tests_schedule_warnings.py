"""Tests the schedule warnings which the settings endpoints answer (#1332).

A saved monitoring, update or harvesting schedule carries a recurrence risk
which only its history can judge: an interval shorter than the runs it
schedules measurably take, a run which missed its time, an expired validity or
an evidence base too small to judge at all. The warnings are derived at the
read from the persisted state (`registry.querys.schedule_warnings`), so every
test creates the state behind a warning and asks the endpoint of the setting
for the rows it has to answer - exactly the way the alerts of the services are
tested.

The rules answer against the wall clock, so these tests hold it to one
`MOMENT` while they ask - the guidance of #1186: a setting which was never
dispatched must not turn overdue at a minute boundary in the middle of a test.

The unit tests hold the decision itself (`warnings_for_setting`) without a
database; the endpoint tests pin the JSON:API shape - the camelized attribute
and the camelCase value keys - the per-row keying of the page batch, the
sparse-field gate of the schedules endpoint and the page-bounded query cost.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django_celery_beat.models import CrontabSchedule
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.enums.update import UpdateJobStatusEnum as JobState
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.monitoring import (WebMapServiceMonitoringRun,
                                        WebMapServiceMonitoringSetting)
from registry.models.service import CatalogueService, WebMapService
from registry.models.update import (WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.querys.schedule_warnings import (MIN_RELIABLE_SAMPLES,
                                               warnings_for_setting)
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
WMS_ONE = "cd16cc1f-3abb-4625-bb96-fbe80dbe23e3"
WMS_TWO = "1b195589-dcfa-403f-9e66-e7e1c0a67024"

UTC = timezone.utc

#: a moment in the quiet middle of a UTC day: the crontabs of these tests are
#: hourly or per minute and the held clock keeps every expectation of them
#: true however long the test runs
MOMENT = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)


def instant(answered):
    """Parse an answered moment back into an instant.

    The endpoints answer their moments as ISO strings, the decision answers
    them as the datetimes it computed - both are read through this.
    """
    if isinstance(answered, datetime):
        return answered
    return datetime.fromisoformat(answered.replace('Z', '+00:00'))


# ---------------------------------------------------------------------------
# the decision, without a database
# ---------------------------------------------------------------------------

class ScheduleWarningsDecisionTest(SimpleTestCase):
    """The rules which decide the warning rows of one setting.

    The settings are unsaved instances with an unsaved crontab carrying a pk:
    `next_run_expected_at` only asks for the cached crontab and its python
    schedule, so no row and no query is needed to decide a rule.
    """

    def setUp(self):
        self.crontab = CrontabSchedule(
            id=1, minute='0', hour='*', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone='UTC')

    def setting(self, **values):
        """A monitoring setting which answers `values`, saved nowhere"""
        values.setdefault('id', 1)
        values.setdefault('enabled', True)
        values.setdefault('one_off', False)
        values.setdefault('total_run_count', 0)
        return WebMapServiceMonitoringSetting(crontab=self.crontab, **values)

    def decide(self, setting, estimate=None):
        """The rows of the setting, decided at the held `MOMENT`"""
        with patch('django.utils.timezone.now', return_value=MOMENT):
            return warnings_for_setting(setting, estimate, MOMENT)

    def test_a_deactivated_setting_answers_nothing(self):
        """The screen already shows the flag; nothing speaks against it"""
        setting = self.setting(enabled=False,
                               last_run_at=MOMENT - timedelta(hours=5))
        self.assertEqual(self.decide(setting), [])

    def test_a_missed_run_is_warned_with_the_moment_it_was_expected_at(self):
        """The overdue warning leads; the missing evidence is still named"""
        setting = self.setting(last_run_at=MOMENT - timedelta(hours=2))
        rows = self.decide(setting)
        self.assertEqual(
            [row['code'] for row in rows],
            ['schedule_overdue', 'insufficient_evidence'])
        overdue = rows[0]
        self.assertEqual(overdue['severity'], 'warning')
        self.assertEqual(overdue['interval'], '1:00:00')
        # the hourly crontab after a run two hours ago was expected an hour ago
        self.assertEqual(instant(overdue['expectedAt']),
                         MOMENT - timedelta(hours=1))
        self.assertEqual(instant(overdue['computedAt']), MOMENT)

    def test_an_expired_validity_is_an_informations_row_alone(self):
        """stale, not broken - and no recurrence left to judge"""
        setting = self.setting(
            last_run_at=MOMENT - timedelta(hours=2),
            expires=MOMENT - timedelta(minutes=1))
        rows = self.decide(setting)
        self.assertEqual([row['code'] for row in rows], ['schedule_expired'])
        self.assertEqual(rows[0]['severity'], 'info')
        self.assertEqual(instant(rows[0]['expiredAt']),
                         MOMENT - timedelta(minutes=1))

    def test_a_setting_without_a_next_run_answers_no_recurrence(self):
        """a one-off which ran neither missed its time nor waits for another"""
        setting = self.setting(
            last_run_at=MOMENT - timedelta(hours=2),
            one_off=True, total_run_count=1)
        self.assertEqual(self.decide(setting), [])

    def test_no_finished_run_is_an_information_not_a_warning(self):
        setting = self.setting(last_run_at=MOMENT)
        rows = self.decide(setting)
        self.assertEqual([row['code'] for row in rows],
                         ['insufficient_evidence'])
        self.assertEqual(rows[0]['severity'], 'info')
        self.assertEqual(rows[0]['unknownReason'], 'no_completed_runs')
        self.assertEqual(rows[0]['sampleCount'], 0)
        self.assertEqual(rows[0]['interval'], '1:00:00')

    def test_fewer_than_the_reliable_amount_of_runs_stays_informational(self):
        setting = self.setting(last_run_at=MOMENT)
        estimate = {
            'average': timedelta(minutes=90),
            'last_done': MOMENT - timedelta(hours=1),
            'samples': MIN_RELIABLE_SAMPLES - 1}
        rows = self.decide(setting, estimate)
        self.assertEqual([row['code'] for row in rows],
                         ['insufficient_evidence'])
        self.assertEqual(rows[0]['unknownReason'], 'too_few_samples')
        self.assertEqual(rows[0]['sampleCount'], MIN_RELIABLE_SAMPLES - 1)

    def test_a_measured_run_longer_than_the_wait_is_warned_with_both(self):
        setting = self.setting(last_run_at=MOMENT)
        estimate = {
            'average': timedelta(minutes=90),
            'last_done': MOMENT - timedelta(hours=1),
            'samples': MIN_RELIABLE_SAMPLES}
        rows = self.decide(setting, estimate)
        self.assertEqual([row['code'] for row in rows],
                         ['schedule_too_tight'])
        self.assertEqual(rows[0]['severity'], 'warning')
        self.assertEqual(rows[0]['interval'], '1:00:00')
        self.assertEqual(rows[0]['observedDuration'], '1:30:00')
        self.assertEqual(rows[0]['sampleCount'], MIN_RELIABLE_SAMPLES)
        self.assertEqual(instant(rows[0]['lastDoneAt']),
                         MOMENT - timedelta(hours=1))

    def test_a_measured_run_the_wait_meets_answers_nothing(self):
        setting = self.setting(last_run_at=MOMENT)
        estimate = {
            'average': timedelta(minutes=30),
            'last_done': MOMENT - timedelta(hours=1),
            'samples': MIN_RELIABLE_SAMPLES}
        self.assertEqual(self.decide(setting, estimate), [])

    def test_the_overdue_schedule_answers_its_warnings_before_the_evidence(self):
        setting = self.setting(last_run_at=MOMENT - timedelta(hours=2))
        estimate = {
            'average': timedelta(minutes=90),
            'last_done': MOMENT - timedelta(hours=1),
            'samples': MIN_RELIABLE_SAMPLES}
        rows = self.decide(setting, estimate)
        self.assertEqual(
            [row['code'] for row in rows],
            ['schedule_overdue', 'schedule_too_tight'])
        self.assertTrue(
            all(row['severity'] == 'warning' for row in rows))


# ---------------------------------------------------------------------------
# the endpoints
# ---------------------------------------------------------------------------

class ScheduleWarningsEndpointMixin:
    """States and requests behind the warnings of the settings endpoints."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(
            username='schedules', password='test')
        cls.wms_one = WebMapService.objects.get(pk=WMS_ONE)
        cls.wms_two = WebMapService.objects.get(pk=WMS_TWO)
        cls.csw = CatalogueService.objects.first()
        cls.every_minute = CrontabSchedule.objects.create(
            minute='*', hour='*', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone='UTC')
        cls.hourly = CrontabSchedule.objects.create(
            minute='0', hour='*', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone='UTC')

    def api(self):
        """An authenticated API client (not `self.client`: Django's TestCase
        overwrites that attribute with its plain test client)."""
        client = APIClient()
        client.force_authenticate(self.admin)
        client.credentials(HTTP_ACCEPT=JSONAPI)
        return client

    def ask(self, route, **query):
        """The answered attributes of the rows of one settings endpoint.

        The request is decided against `MOMENT`: the schedules answer against
        the wall clock and holding it holds the answer (#1186).
        """
        with patch('django.utils.timezone.now', return_value=MOMENT):
            response = self.api().get(reverse(route), query)
        self.assertEqual(response.status_code, 200, response.content)
        return {
            row['id']: row['attributes'] for row in response.json()['data']}

    def monitoring_setting(self, service, crontab=None):
        return WebMapServiceMonitoringSetting.objects.create(
            service=service, crontab=crontab or self.every_minute)

    def monitoring_runs(self, setting, count, minutes=40):
        """Finished runs of a monitoring setting, each taking `minutes`"""
        for index in range(count):
            done = MOMENT - timedelta(hours=index + 1)
            WebMapServiceMonitoringRun.objects.create(
                setting=setting,
                date_created=done - timedelta(minutes=minutes),
                date_done=done)

    def update_setting(self, service, crontab=None):
        return WebMapServiceUpdateSetting.objects.create(
            service=service, crontab=crontab or self.every_minute)

    def update_jobs(self, service, count, minutes=40):
        """Finished update jobs of a service, each taking `minutes`"""
        for index in range(count):
            done = MOMENT - timedelta(hours=index + 1)
            job = WebMapServiceUpdateJob.objects.create(
                service=service, status=JobState.UPDATED.value, done_at=done)
            # `date_created` is auto_now_add - the moment it started is written
            # after the save, which is what decides the duration
            WebMapServiceUpdateJob.objects.filter(pk=job.pk).update(
                date_created=done - timedelta(minutes=minutes))

    def harvesting_runs(self, service, count, minutes=40):
        """Completed harvests of a catalogue, each taking `minutes`.

        The fixture of the catalogues carries harvesting jobs of its own; the
        evidence of these tests is only what they made themselves.
        """
        HarvestingJob.objects.filter(service=service).delete()
        for index in range(count):
            done = MOMENT - timedelta(hours=index + 1)
            HarvestingJob.objects.create(
                service=service, phase=Phase.COMPLETED.value,
                total_records=1,
                date_created=done - timedelta(minutes=minutes),
                done_at=done)

    def periodic_job(self, service, crontab=None):
        return PeriodicHarvestingJob.objects.create(
            service=service, crontab=crontab or self.every_minute)

    def codes(self, attributes):
        """the codes of the answered warning rows of one setting"""
        return [row['code'] for row in attributes['scheduleWarnings']]


class MonitoringSettingsWarningsTest(ScheduleWarningsEndpointMixin, TestCase):
    """The warnings which the monitoring settings endpoint answers."""

    ROUTE = 'registry:webmapservicemonitoringsetting-list'
    RESOURCE = 'WebMapServiceMonitoringSetting'

    def attributes_of(self, setting, **query):
        answered = self.ask(self.ROUTE, **query)
        self.assertIn(str(setting.pk), answered)
        return answered[str(setting.pk)]

    def test_a_missed_run_is_answered_as_the_overdue_warning(self):
        setting = self.monitoring_setting(self.wms_one)
        type(setting).objects.filter(pk=setting.pk).update(
            last_run_at=MOMENT - timedelta(hours=2))
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes),
                         ['schedule_overdue', 'insufficient_evidence'])
        first = attributes['scheduleWarnings'][0]
        self.assertEqual(first['severity'], 'warning')
        self.assertEqual(first['interval'], '0:01:00')
        self.assertLess(instant(first['expectedAt']),
                        instant(first['computedAt']))
        self.assertEqual(instant(first['computedAt']), MOMENT)

    def test_a_measured_run_longer_than_the_wait_is_answered_as_too_tight(self):
        setting = self.monitoring_setting(self.wms_one, self.hourly)
        self.monitoring_runs(setting, MIN_RELIABLE_SAMPLES, minutes=90)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['schedule_too_tight'])
        first = attributes['scheduleWarnings'][0]
        self.assertEqual(first['observedDuration'], '1:30:00')
        self.assertEqual(first['sampleCount'], MIN_RELIABLE_SAMPLES)

    def test_a_run_the_wait_meets_answers_an_empty_list(self):
        setting = self.monitoring_setting(self.wms_one, self.hourly)
        self.monitoring_runs(setting, MIN_RELIABLE_SAMPLES, minutes=5)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(attributes['scheduleWarnings'], [])

    def test_history_too_small_for_a_judgement_is_an_information(self):
        setting = self.monitoring_setting(self.wms_one, self.hourly)
        self.monitoring_runs(setting, 1, minutes=90)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['insufficient_evidence'])
        first = attributes['scheduleWarnings'][0]
        self.assertEqual(first['severity'], 'info')
        self.assertEqual(first['unknownReason'], 'too_few_samples')
        self.assertEqual(first['sampleCount'], 1)

    def test_the_warnings_of_two_settings_are_answered_per_row(self):
        """The batch of the page may never mix the evidence of its rows"""
        overdue = self.monitoring_setting(self.wms_one)
        type(overdue).objects.filter(pk=overdue.pk).update(
            last_run_at=MOMENT - timedelta(hours=2))
        healthy = self.monitoring_setting(self.wms_two, self.hourly)
        self.monitoring_runs(healthy, MIN_RELIABLE_SAMPLES, minutes=5)
        answered = self.ask(
            self.ROUTE,
            **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        overdue_rows = answered[str(overdue.pk)]['scheduleWarnings']
        self.assertEqual(overdue_rows[0]['code'], 'schedule_overdue')
        self.assertEqual(
            answered[str(healthy.pk)]['scheduleWarnings'], [])

    def test_a_deactivated_setting_answers_no_warning(self):
        setting = self.monitoring_setting(self.wms_one)
        type(setting).objects.filter(pk=setting.pk).update(
            enabled=False, last_run_at=MOMENT - timedelta(hours=2))
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(attributes['scheduleWarnings'], [])

    def test_a_setting_past_its_validity_answers_the_expired_information(self):
        setting = self.monitoring_setting(self.wms_one)
        type(setting).objects.filter(pk=setting.pk).update(
            expires=MOMENT - timedelta(minutes=1))
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['schedule_expired'])
        self.assertEqual(
            attributes['scheduleWarnings'][0]['severity'], 'info')

    def test_the_detail_answers_the_warnings_without_being_asked(self):
        """A single read answers its own row through the serializer alone"""
        setting = self.monitoring_setting(self.wms_one)
        type(setting).objects.filter(pk=setting.pk).update(
            last_run_at=MOMENT - timedelta(hours=2))
        with patch('django.utils.timezone.now', return_value=MOMENT):
            response = self.api().get(
                reverse('registry:webmapservicemonitoringsetting-detail',
                        kwargs={'pk': setting.pk}),
                HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        attributes = response.json()['data']['attributes']
        self.assertEqual(
            [row['code'] for row in attributes['scheduleWarnings']],
            ['schedule_overdue', 'insufficient_evidence'])

    def test_a_list_which_names_no_warnings_does_not_answer_them(self):
        setting = self.monitoring_setting(self.wms_one)
        answered = self.ask(
            self.ROUTE, **{'fields[%s]' % self.RESOURCE: 'enabled'})
        self.assertNotIn('scheduleWarnings', answered[str(setting.pk)])


class UpdateSettingsWarningsTest(ScheduleWarningsEndpointMixin, TestCase):
    """The warnings which the update settings endpoint answers.

    The evidence of an update schedule hangs on the service and not on the
    setting - the update jobs belong to the service - which the batch of the
    page reads across and hands back keyed by the setting.
    """

    ROUTE = 'registry:webmapserviceupdatesetting-list'
    RESOURCE = 'WebMapServiceUpdateSetting'

    def attributes_of(self, setting, **query):
        answered = self.ask(self.ROUTE, **query)
        self.assertIn(str(setting.pk), answered)
        return answered[str(setting.pk)]

    def test_jobs_longer_than_the_wait_are_answered_as_too_tight(self):
        setting = self.update_setting(self.wms_one, self.hourly)
        self.update_jobs(self.wms_one, MIN_RELIABLE_SAMPLES, minutes=90)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['schedule_too_tight'])
        first = attributes['scheduleWarnings'][0]
        self.assertEqual(first['observedDuration'], '1:30:00')
        self.assertEqual(first['sampleCount'], MIN_RELIABLE_SAMPLES)

    def test_the_jobs_of_another_service_answer_no_evidence(self):
        setting = self.update_setting(self.wms_two, self.hourly)
        self.update_jobs(self.wms_one, MIN_RELIABLE_SAMPLES, minutes=90)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['insufficient_evidence'])
        self.assertEqual(
            attributes['scheduleWarnings'][0]['unknownReason'],
            'no_completed_runs')

    def test_a_still_running_job_is_no_finished_run(self):
        setting = self.update_setting(self.wms_one, self.hourly)
        # two finished runs are too little to judge; only if the still
        # running job were counted as a finished one does the third
        # 90 minute sample turn the answer into a judgement
        self.update_jobs(self.wms_one, MIN_RELIABLE_SAMPLES - 1, minutes=90)
        WebMapServiceUpdateJob.objects.create(
            service=self.wms_one, status=JobState.UPDATING.value)
        attributes = self.attributes_of(
            setting, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['insufficient_evidence'])


class PeriodicHarvestingJobWarningsTest(ScheduleWarningsEndpointMixin,
                                        TestCase):
    """The warnings which the harvesting schedules endpoint answers."""

    ROUTE = 'registry:periodicharvestingjob-list'
    RESOURCE = 'PeriodicHarvestingJob'

    def attributes_of(self, job, **query):
        answered = self.ask(self.ROUTE, **query)
        self.assertIn(str(job.pk), answered)
        return answered[str(job.pk)]

    def test_harvests_longer_than_the_wait_are_answered_as_too_tight(self):
        job = self.periodic_job(self.csw, self.hourly)
        self.harvesting_runs(self.csw, MIN_RELIABLE_SAMPLES, minutes=90)
        attributes = self.attributes_of(
            job, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['schedule_too_tight'])
        first = attributes['scheduleWarnings'][0]
        self.assertEqual(first['observedDuration'], '1:30:00')
        self.assertEqual(first['sampleCount'], MIN_RELIABLE_SAMPLES)
        self.assertIsNotNone(first['lastDoneAt'])

    def test_a_harvest_which_never_finished_answers_no_estimate(self):
        """an invented duration must not be mistaken for a measured one"""
        job = self.periodic_job(self.csw, self.hourly)
        self.harvesting_runs(self.csw, MIN_RELIABLE_SAMPLES, minutes=90)
        HarvestingJob.objects.filter(service=self.csw).update(
            phase=Phase.ABORTED.value)
        attributes = self.attributes_of(
            job, **{'fields[%s]' % self.RESOURCE: 'schedule_warnings'})
        self.assertEqual(self.codes(attributes), ['insufficient_evidence'])

    def test_the_screen_which_shows_no_warnings_pays_for_no_evidence(self):
        """the sparse-field gate of the schedules endpoint (#1082 pattern)"""
        self.harvesting_runs(self.csw, MIN_RELIABLE_SAMPLES, minutes=90)
        with patch('registry.views.scheduling.schedule_warnings_by_id') \
                as batch, \
                patch('registry.serializers.scheduling.'
                      'schedule_warnings_by_id') as single:
            self.ask(self.ROUTE, **{'fields[%s]' % self.RESOURCE: 'enabled'})
            batch.assert_not_called()
            single.assert_not_called()
        # the same endpoint naming the warnings asks for them again
        self.ask(self.ROUTE, **{'fields[%s]' % self.RESOURCE:
                                'schedule_warnings'})

    def test_a_harvesting_schedule_stays_saveable_while_it_is_too_tight(self):
        """a tight schedule is a warning and never a rejected save (#693)"""
        job = self.periodic_job(self.csw, self.hourly)
        self.harvesting_runs(self.csw, MIN_RELIABLE_SAMPLES, minutes=90)
        with patch('django.utils.timezone.now', return_value=MOMENT):
            response = self.api().patch(
                reverse('registry:periodicharvestingjob-detail',
                        kwargs={'pk': job.pk}),
                data={'data': {'id': str(job.pk),
                               'type': 'PeriodicHarvestingJob',
                               'attributes': {'enabled': True}}},
                format='vnd.api+json')
        self.assertEqual(response.status_code, 200, response.content)


class ScheduleWarningsQueryCostTest(ScheduleWarningsEndpointMixin, TestCase):
    """The list pays one evidence aggregate per page, not one per row (#1332).

    The tables of the runs are searched in the captured statements: the
    evidence aggregate is the only reader they have on these endpoints, so it
    may appear once for a page of two rows exactly as often as for a page of
    one.
    """

    # the schedules of a harvest live in `registry_periodicharvestingjob`,
    # whose name contains the run table's name - only the quoted table name
    # tells the schedule of a harvest from its runs apart
    RUN_TABLES = ('monitoringrun', 'updatejob', '"registry_harvestingjob"')

    def count_evidence_reads(self, path, **params):
        """queries of one request which read the runs or jobs of the settings"""
        with CaptureQueriesContext(connections['default']) as context:
            self.api().get(path, params, HTTP_ACCEPT=JSONAPI)
        return [query for query in context
                if any(table in query['sql'].lower()
                       for table in self.RUN_TABLES)]

    def test_the_evidence_aggregate_does_not_grow_with_the_rows(self):
        first = self.monitoring_setting(self.wms_one, self.hourly)
        second = self.monitoring_setting(self.wms_two, self.hourly)
        self.monitoring_runs(first, MIN_RELIABLE_SAMPLES)
        self.monitoring_runs(second, MIN_RELIABLE_SAMPLES)
        path = reverse('registry:webmapservicemonitoringsetting-list')
        fields = {'fields[WebMapServiceMonitoringSetting]':
                  'schedule_warnings'}
        with patch('django.utils.timezone.now', return_value=MOMENT):
            both = self.count_evidence_reads(path, **fields)
            single = self.count_evidence_reads(
                path, **dict(fields, **{'filter[id]': str(first.pk)}))
        self.assertEqual(
            len(both), len(single),
            msg=f'{len(both)} evidence queries for two rows against '
                f'{len(single)} for one - the aggregate is read per row')

    def test_a_request_without_warnings_asks_no_evidence_at_all(self):
        """the schedules endpoint keeps its promise (#1082 pattern)"""
        self.periodic_job(self.csw, self.hourly)
        self.harvesting_runs(self.csw, MIN_RELIABLE_SAMPLES)
        path = reverse('registry:periodicharvestingjob-list')
        with patch('django.utils.timezone.now', return_value=MOMENT):
            quiet = self.count_evidence_reads(
                path, **{'fields[PeriodicHarvestingJob]': 'enabled'})
            loud = self.count_evidence_reads(
                path, **{'fields[PeriodicHarvestingJob]':
                         'schedule_warnings'})
        self.assertEqual(quiet, [])
        self.assertGreater(len(loud), 0)


class ScheduleWarningsSchemaTest(SimpleTestCase):
    """The OpenAPI schema describes the answered warnings with their codes.

    The codes are the stable half of the contract shared with the draft
    preview of #1327 - a client which branches on them must find the enum in
    the schema and not only in the source.
    """

    def property_of(self, node, name):
        """The first definition of `name` anywhere in the schema node"""
        if isinstance(node, dict):
            if name in node and isinstance(node[name], dict) \
                    and 'items' in node[name]:
                return node[name]
            for value in node.values():
                found = self.property_of(value, name)
                if found is not None:
                    return found
        elif isinstance(node, list):
            for value in node:
                found = self.property_of(value, name)
                if found is not None:
                    return found
        return None

    def test_the_settings_schema_names_the_warning_codes(self):
        from django.urls import include, path
        from drf_spectacular.generators import SchemaGenerator
        from registry.urls import urlpatterns

        patterns = [
            pattern for pattern in urlpatterns if getattr(pattern, 'name', None)
            in {'webmapservicemonitoringsetting-list',
                'webmapserviceupdatesetting-list',
                'periodicharvestingjob-list'}]
        schema = SchemaGenerator(
            patterns=[path('api/registry/', include(patterns))]
        ).get_schema(public=True)
        attribute = self.property_of(schema['components'], 'scheduleWarnings')
        self.assertIsNotNone(
            attribute, msg='scheduleWarnings is not described by the schema')
        items = attribute['items']
        self.assertEqual(items['required'], ['code', 'severity', 'computedAt'])
        self.assertEqual(
            items['properties']['code']['enum'],
            ['schedule_overdue', 'schedule_too_tight',
             'insufficient_evidence', 'schedule_expired'])
        # the value keys are camelCase as the answer spells them
        self.assertIn('observedDuration', items['properties'])
        self.assertIn('sampleCount', items['properties'])
