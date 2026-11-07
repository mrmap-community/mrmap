"""The answers of a harvesting schedule and the sort by its next run (#1082).

A schedule which is asked when it runs next answered the German word
``"unbekannt"`` inside the JSON of every language - a word no client can
translate and no screen can show as a date. The endpoint now answers the
instant the schedule is expected to fire next, the moment it fired last and
how often it fired in all; the screen of all schedules sorts by that instant,
which the database does not have as a column. These tests pin the three
answers, that no request is ever answered with the word again, and the
ordering over the python-decided annotation.
"""
from datetime import datetime, timezone
from json import dumps, loads
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve
from django_celery_beat.models import CrontabSchedule
from extras.scheduling import with_next_run_at
from registry.models.harvest import PeriodicHarvestingJob
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService
from registry.serializers.harvesting import PeriodicHarvestingJobSerializer
from rest_framework.test import APIRequestFactory

JSONAPI = "application/vnd.api+json"


def baseline(schedule, **values):
    """Pin the state of a saved schedule, which the save itself decides.

    Args:
        schedule: the schedule to answer for
        **values: the columns to write: `enabled`, `date_changed`,
            `last_run_at`
    """
    PeriodicHarvestingJob.objects.filter(pk=schedule.pk).update(**values)
    schedule.refresh_from_db()
    return schedule


class NextRunAnnotationTest(TestCase):
    """The CASE annotation which lets a database sort answer the next run.

    The schedules are built with unsaved instances on purpose: saving a
    schedule is Beat's own decision (`date_changed` follows the save and the
    last run of a disabled schedule is cleared), so the baselines are written
    as they are after a dispatch.
    """

    def schedule(self, pk, **values):
        """A schedule which answers `values` and is answered by the next run.

        Args:
            pk: the id to answer with - no save asks a database this way
            **values: the values of the schedule
        """
        return PeriodicHarvestingJob(
            pk=pk, service=self.service, crontab=self.crontab, **values)

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Schedule contact')
        cls.service = CatalogueService.objects.create(
            title='Schedule catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        cls.crontab = CrontabSchedule.objects.create(
            minute='30', hour='2', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone='UTC')

    def test_the_enabled_schedule_answers_the_moment_after_its_last_run(self):
        """the next tick of the crontab after the dispatch, not after today:
        Beat waits from the run it did, so a schedule at 02:30 which last ran
        at 02:00 is expected the same night, not a year from now"""
        made = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
        enabled = self.schedule(1, enabled=True, last_run_at=made)
        self.assertEqual(
            with_next_run_at([enabled])[0].next_run_at,
            datetime(2026, 11, 5, 2, 30, tzinfo=timezone.utc))

    def test_the_disabled_schedule_is_annotated_as_no_moment(self):
        made = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
        disabled = self.schedule(1, enabled=False, last_run_at=made)
        self.assertIsNone(with_next_run_at([disabled])[0].next_run_at)

    def test_a_schedule_which_never_ran_is_answered_by_its_change(self):
        """a dispatch which never happened leaves no last run - the date the
        schedule was changed is Beat's baseline for the next one"""
        never = self.schedule(
            1, enabled=True,
            date_changed=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(
            with_next_run_at([never])[0].next_run_at,
            datetime(2026, 11, 5, 2, 30, tzinfo=timezone.utc))

    def test_no_schedule_at_all_still_answers_the_annotation(self):
        """an empty list sorts on the constant, not on an empty CASE"""
        qs = with_next_run_at(PeriodicHarvestingJob.objects.none())
        self.assertEqual(list(qs), [])

    def test_the_database_sorts_the_no_moment_after_the_moments(self):
        """the null placement the screen of the schedules relies on (#1082):
        a row which answers no next run sorts after its siblings ascending
        and before them descending - the databases' own rule, pinned here
        so the screen and a future change both know which one was chosen"""
        # saved one by one: the schedule inherits a table from celery's own
        # PeriodicTask, which `bulk_create` refuses to write
        moment = PeriodicHarvestingJob.objects.create(
            service=self.service, crontab=self.crontab, enabled=True)
        no_moment = PeriodicHarvestingJob.objects.create(
            service=self.service, crontab=self.crontab, enabled=False)
        ordered = list(
            with_next_run_at(
                PeriodicHarvestingJob.objects.all()).order_by('next_run_at')
            .values_list('pk', flat=True))
        self.assertEqual(ordered, [moment.pk, no_moment.pk])
        ordered = list(
            with_next_run_at(
                PeriodicHarvestingJob.objects.all()).order_by('-next_run_at')
            .values_list('pk', flat=True))
        self.assertEqual(ordered, [no_moment.pk, moment.pk])


class PeriodicHarvestingJobEndpointTest(TestCase):
    """The answers of the schedules endpoint, through its full stack.

    The moments of the schedule are written as they are after a dispatch:
    saving it is Beat's own decision, `date_changed` following the save and
    the last run of a disabled schedule being cleared by it.
    """

    fixtures = ["test_users.json"]

    ENDPOINT = '/api/registry/harvesting/periodic-harvesting-jobs'

    @classmethod
    def setUpTestData(cls):
        get_user_model().objects.get_or_create(username="AnonymousUser")
        contact = MetadataContact.objects.create(name='Endpoint contact')
        cls.service = CatalogueService.objects.create(
            title='Endpoint catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        cls.crontab = CrontabSchedule.objects.create(
            minute='30', hour='2', day_of_week='*', day_of_month='*',
            month_of_year='*', timezone='UTC')
        made = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
        cls.schedule = baseline(
            PeriodicHarvestingJob.objects.create(
                service=cls.service, crontab=cls.crontab, enabled=True,
                total_run_count=3),
            date_changed=made, last_run_at=made)

    def get(self, **params):
        """the answer of the endpoint, as a client reads it (rendered JSON:API)"""
        request = APIRequestFactory().get(
            self.ENDPOINT, params, HTTP_ACCEPT=JSONAPI)
        callback, _, kwargs = resolve(self.ENDPOINT)
        response = callback(request, **kwargs)
        if not response.is_rendered:
            response.render()
        return response.status_code, loads(response.content)

    def attributes_of(self, body, schedule_id=None):
        """the attributes of the answered row, of one schedule when named"""
        rows = body['data']
        if schedule_id is not None:
            rows = [row for row in rows if row['id'] == schedule_id]
        self.assertEqual(len(rows), 1, msg=f'expected one row in {body}')
        return rows[0]['attributes']

    def test_the_schedule_answers_its_instants_and_count(self):
        status, body = self.get()
        self.assertEqual(status, 200, body)
        attributes = self.attributes_of(body)
        # the camelized spelling the renderer answers with; the instants are
        # compared as instants, because the deployment decides by which offset
        # an aware moment is printed (#1082)
        self.assertEqual(
            datetime.fromisoformat(attributes['nextRunAt']),
            datetime(2026, 11, 5, 2, 30, tzinfo=timezone.utc))
        self.assertEqual(
            datetime.fromisoformat(attributes['lastRunAt']),
            datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc))
        self.assertEqual(attributes['totalRunCount'], 3)

    def test_the_mixin_answers_no_word_for_a_setting_without_a_crontab(self):
        """the regression of #1082 in the answer itself: a schedule which has
        no crontab answers nothing, and never a German word.

        The instance is unsaved on purpose - celery's own model refuses a
        schedule without a crontab, so this is the only way the row exists.
        """
        without_crontab = PeriodicHarvestingJob(
            pk=1, service=self.service, enabled=True)
        self.assertIsNone(
            PeriodicHarvestingJobSerializer().get_time_until_next_run(
                without_crontab))

    def test_a_schedule_without_a_next_run_is_answered_as_nothing(self):
        """the regression of #1082: the empty answer is never the German word.

        A disabled schedule is the row which answers no next run: celery's own
        model refuses a schedule without a crontab, so nothing else answers
        none - while switching a schedule off is what an administrator does.
        """
        made = datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc)
        disabled = baseline(
            PeriodicHarvestingJob.objects.create(
                service=self.service, crontab=self.crontab, enabled=True),
            enabled=False, date_changed=made, last_run_at=made)
        status, body = self.get()
        self.assertEqual(status, 200, body)
        self.assertNotIn('unbekannt', dumps(body).lower())
        attributes = self.attributes_of(body, str(disabled.pk))
        self.assertIsNone(attributes['nextRunAt'])
        # what it did is still answered: switching a schedule off does not
        # un-happen the dispatch which ran before it
        self.assertEqual(
            datetime.fromisoformat(attributes['lastRunAt']),
            datetime(2026, 11, 5, 2, 0, tzinfo=timezone.utc))

    def test_the_request_which_sorts_by_the_next_run_is_answered(self):
        """the order the screen of all schedules asks for: the moment is no
        column of the database, so the annotation of `NextRunOrderingFilter`
        decides it - the schedule which answers a moment comes first, the one
        which answers none after it"""
        disabled = baseline(
            PeriodicHarvestingJob.objects.create(
                service=self.service, crontab=self.crontab, enabled=True),
            enabled=False)
        status, body = self.get(sort='nextRunAt')
        self.assertEqual(status, 200, body)
        self.assertEqual(
            [row['id'] for row in body['data']],
            [str(self.schedule.pk), str(disabled.pk)])

    def test_the_enabled_flag_facets_the_list(self):
        status, body = self.get(**{'filter[enabled]': 'true'})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body['data']), 1)
        status, body = self.get(**{'filter[enabled]': 'false'})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body['data']), 0)

    def test_a_request_without_the_next_run_pays_for_no_estimate(self):
        """the sparse fieldset keeps the python decision off the screen which
        shows no next run (#1082) - the cost is the remaining estimate of the
        crontab, so it is the one which must not be asked"""
        with patch('registry.serializers.harvesting.next_run_expected_at') \
                as estimated:
            estimated.return_value = None
            self.get(**{'fields[PeriodicHarvestingJob]': 'enabled'})
            estimated.assert_not_called()
        # the same request naming the next run asks the estimate
        with patch('registry.serializers.harvesting.next_run_expected_at') \
                as estimated:
            estimated.return_value = None
            self.get(**{'fields[PeriodicHarvestingJob]': 'nextRunAt'})
            estimated.assert_called()
