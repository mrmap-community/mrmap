"""The moment a harvesting run was made (#1079).

A run is one row of `registry_harvestingjob` and until #1079 that row knew nothing about when the
run happened: `ProcessingData.date_created` carried the comment explaining why `auto_now_add` is
the wrong tool and never answered the default it asks for. Everything which orders runs or
measures them therefore answered nothing - the sort the endpoint offers, the card of the last
runs of a catalogue, the elapsed time of a run and the time range filters of #1080.

What is pinned here is the smallest promise which makes all of those work: the model answers the
moment of its own accord, a moment which is handed to it wins over that answer, a run whose
creation cannot be known stays empty, and the endpoint keeps the order and the filters which the
column makes possible. That a run *created before* this change answers its moment is the business
of the migration test next door.
"""
from datetime import timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, now
from registry.models.harvest import HarvestingJob
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService
from registry.tasks.harvest import create_harvesting_job
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
CATALOGUE = '33333333-3333-3333-3333-333333333333'
SCHEDULED = '44444444-4444-4444-4444-444444444444'

#: handed to `run()` to leave the creation of a run to the model
UNSET = object()


class HarvestingRunMomentTest(TestCase):
    """The start of a run, from the row which records it to the answer of the endpoint."""

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Moment contact')
        cls.catalogue = CatalogueService(
            id=CATALOGUE, title='Catalogue', version=202, origin=1,
            service_url='https://example.com/csw', metadata_contact=contact,
            service_contact=contact)
        cls.scheduled = CatalogueService(
            id=SCHEDULED, title='Scheduled catalogue', version=202, origin=1,
            service_url='https://example.com/csw', metadata_contact=contact,
            service_contact=contact)
        CatalogueService.objects.bulk_create([cls.catalogue, cls.scheduled])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username='moment', password='test'))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def start_run(self, service=None, made=UNSET, ended=None, **kwargs):
        """A harvesting run of a catalogue.

        Args:
            service: the catalogue the run belongs to
            made: the moment to hand to the run, left out when the run is created the way the
                harvesting creates one and the model has to answer the moment itself. None is a
                value of its own: it marks a run whose creation is unknown.
            ended: the moment the run ended, None while it did not
            **kwargs: everything else the row of a run carries

        Returns:
            HarvestingJob: the run
        """
        creation = {} if made is UNSET else {'date_created': made}
        return HarvestingJob.objects.create(
            service=service or self.catalogue, done_at=ended, **creation, **kwargs)

    def answered_ids(self, **params):
        """The ids of the runs the endpoint answers, in the order it answers them.

        Args:
            **params: the query parameters of the request

        Returns:
            list: the id of every answered run, first row first
        """
        response = self.client.get(
            reverse('registry:harvestingjob-list'),
            {'filter[service__id]': CATALOGUE, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return [row['id'] for row in response.json()['data']]

    def test_a_run_started_by_an_administrator_answers_its_moment(self):
        """the harvest which the "harvest now" of the ui starts knows when it began

        The screen sends nothing but the catalogue, so the moment of the run is answered by the
        model or by nobody - and the screen which shows the run reads it out of the same answer.
        """
        before = now()
        with patch('celery.canvas.Signature.apply_async'), \
                patch('registry.tasks.harvest.call_fetch_total_records'):
            response = self.client.post(
                reverse('registry:harvestingjob-list'),
                {"data": {
                    "type": "HarvestingJob",
                    "relationships": {"service": {"data": {
                        "id": CATALOGUE, "type": "CatalogueService"}}}}},
                format="vnd.api+json")
        self.assertEqual(response.status_code, 201, response.content)
        answered = parse_datetime(
            response.json()['data']['attributes']['dateCreated'])
        self.assertIsNotNone(answered, "the answer which started the run hides its start")
        self.assertLessEqual(before, answered)
        self.assertGreaterEqual(now(), answered)

    def test_a_run_of_a_scheduled_harvest_answers_its_moment(self):
        """the run which the schedule of a catalogue starts answers the same moment

        A periodic harvest is started by a worker without a request to attach a time to, so the
        moment is written where the row of the run is written.
        """
        delivery_id = str(uuid4())
        create_harvesting_job.push_request(id=delivery_id)
        self.addCleanup(create_harvesting_job.pop_request)
        with patch('celery.canvas.Signature.apply_async'), \
                patch('registry.tasks.harvest.call_fetch_total_records'):
            with self.captureOnCommitCallbacks(execute=True):
                job_id = create_harvesting_job.run(service_id=self.scheduled.pk)
        job = HarvestingJob.objects.get(pk=job_id)
        self.assertIsNotNone(job.date_created)
        self.assertLess(job.date_created - now(), timedelta(seconds=30))
        self.assertGreater(job.date_created - now(), timedelta(seconds=-30))

    def test_the_moment_of_a_run_is_an_instant_with_a_time_zone(self):
        """the moment is stored in a timestamp with a time zone, as the column of the model says

        A run which was made at one instant answers that instant in every zone, so the ordering of
        the runs of a catalogue does not depend on the zone the deployment runs in - which is what
        the "in UTC" of #1079 asks for, and what a plain naive timestamp could not keep.
        """
        made = now() - timedelta(hours=5)
        job = self.start_run(made=made)
        job.refresh_from_db()
        self.assertTrue(is_aware(job.date_created))
        self.assertEqual(job.date_created.astimezone(timezone.utc), made.astimezone(timezone.utc))

    def test_a_moment_handed_to_a_run_wins_over_the_answer_of_the_model(self):
        """`default` and not `auto_now_add`: the scenarios of #870 give a run a moment of their
        own and the migration of 0038 hands the runs of a deployment the moment their change log
        records - both would be ignored by auto_now_add"""
        made = now() - timedelta(days=3)
        job = self.start_run(made=made)
        job.refresh_from_db()
        self.assertEqual(job.date_created, made)

    def test_a_run_whose_start_is_unknown_stays_empty(self):
        """`null` stays: a row which cannot know its creation is marked as unknown and the screens
        of #1071 answer it "not recorded" instead of inventing a moment"""
        job = self.start_run(made=None)
        job.refresh_from_db()
        self.assertIsNone(job.date_created)

    def test_the_endpoint_orders_the_runs_by_their_start(self):
        """the sort the endpoint offers and did not keep: the newer run comes first

        The runs are created in the opposite order of their starts, so an answer which simply
        leaves the rows in the order the database gives them fails here instead of passing on the
        order the rows happen to be stored in.
        """
        older = self.start_run(made=now() - timedelta(days=2),
                               ended=now() - timedelta(days=2))
        newer = self.start_run(made=now() - timedelta(hours=3),
                               ended=now() - timedelta(hours=3))
        self.assertEqual(
            self.answered_ids(**{'sort': '-date_created',
                                 'fields[HarvestingJob]': 'id'}),
            [str(newer.pk), str(older.pk)])
        self.assertEqual(
            self.answered_ids(**{'sort': 'date_created',
                                 'fields[HarvestingJob]': 'id'}),
            [str(older.pk), str(newer.pk)])

    def test_the_default_answer_of_the_endpoint_is_the_newest_run_first(self):
        """the ordering of the model is `-date_created`, which is what the list of runs (#1087)
        and the card of a catalogue start from"""
        older = self.start_run(made=now() - timedelta(days=2),
                               ended=now() - timedelta(days=2))
        newer = self.start_run(made=now() - timedelta(hours=3),
                               ended=now() - timedelta(hours=3))
        self.assertEqual(
            self.answered_ids(**{'fields[HarvestingJob]': 'id'}),
            [str(newer.pk), str(older.pk)])

    def test_the_activity_card_of_a_catalogue_answers_the_newest_runs(self):
        """the three runs the card of a catalogue shows really are its three newest

        The card asks the related endpoint of its catalogue for three runs sorted by their start
        and names the moment of its newest one; a page of runs which is not the newest three is
        the bug which made #1079.
        """
        starts = [now() - timedelta(days=days) for days in (6, 4, 2, 1)]
        runs = [self.start_run(made=moment, ended=moment) for moment in starts]
        response = self.client.get(
            f'/api/registry/csw/{CATALOGUE}/harvesting-jobs',
            {'sort': '-date_created', 'page[size]': 3,
             'fields[HarvestingJob]': 'id,date_created'})
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['data']
        self.assertEqual(
            [row['id'] for row in rows],
            [str(runs[3].pk), str(runs[2].pk), str(runs[1].pk)])
        # The answer names the moment in the time zone of the deployment (TIME_ZONE of the
        # settings), so what is pinned is the instant behind the string - the instant the card of
        # the catalogue puts next to its last run.
        self.assertEqual(
            [parse_datetime(row['attributes']['dateCreated']) for row in rows],
            list(reversed(starts[1:])))

    def test_the_endpoint_answers_a_time_range_of_the_column(self):
        """the filters of #1080 can only be answered once the column holds a value"""
        older = self.start_run(made=now() - timedelta(days=2),
                               ended=now() - timedelta(days=2))
        newer = self.start_run(made=now() - timedelta(hours=3),
                               ended=now() - timedelta(hours=3))
        boundary = (now() - timedelta(days=1)).isoformat()
        self.assertEqual(
            self.answered_ids(**{'filter[date_created__gt]': boundary,
                                 'fields[HarvestingJob]': 'id'}),
            [str(newer.pk)])
        self.assertEqual(
            self.answered_ids(**{'filter[date_created__lt]': boundary,
                                 'fields[HarvestingJob]': 'id'}),
            [str(older.pk)])
        self.assertEqual(
            self.answered_ids(**{'fields[HarvestingJob]': 'id'}),
            [str(newer.pk), str(older.pk)])
