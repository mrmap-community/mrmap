"""What a harvesting run answers about its own work (#1071).

The diagnostics of a run are the screen its measurements belong to, and a run
which is working answered none of them: its throughput is measured by the runs
which finished (#692), its creation was never written, and nothing of the api
named what a run has left to do. An administrator watching a harvest therefore
had the database to query.

The numbers of this module answer on the existing endpoint of the harvesting
jobs, gated on the sparse fieldset like the neighbours they join:

* `elapsed_seconds` - the moment the run was made to its end or to now. The
  moment the run was made is read the way `harvest_durations` reads it, so a run
  of a deployment which has harvested for years answers a real elapsed time
  although the harvesting never set `date_created` (#693).
* `records_per_minute_running` - the records the run has stored so far against
  that time. Named apart from `records_per_minute`, which answers a completed
  run and compares the page sizes of a catalogue.
* `estimated_seconds_remaining` and `expected_done_at` - the elapsed time
  against the progress the steps already answer, scaled to the part which is
  left. A run whose records are not known yet, whose progress is nothing, or
  which is closed answers nothing: an invented estimate must not be mistaken for
  a measured one.

The cost belongs to these answers, because the screen which shows them asks them
again every few seconds while the import of the very same run is writing: nothing
here aggregates `registry_harvestedmetadatarelation`. The records a run has
stored come from the count of its own temporary files (#870, #886), the part
which is left from its steps. The last two tests pin that shape of the query, and
that the aggregation of the measured durations of one run reads the records of
that run instead of the whole table.

Run with:

    docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm \
        --no-deps django-tests python manage.py test \
        tests.django.registry.tests_harvesting_run_measurements --noinput
"""
from datetime import datetime, timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import (HarvestedMetadataRelation, HarvestingJob,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import (DatasetMetadataRecord, MetadataContact)
from registry.models.service import CatalogueService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
MEASUREMENTS = ('id,elapsed_seconds,records_per_minute_running,'
                'estimated_seconds_remaining,expected_done_at')

# the answers whose absence is asserted together: none of them is answered for a
# request which does not ask a measurement
MEASUREMENT_ANSWERS = ('elapsedSeconds', 'recordsPerMinuteRunning',
                       'estimatedSecondsRemaining', 'expectedDoneAt')


class HarvestingRunMeasurementsTest(TestCase):
    """The elapsed time, the throughput and the estimate of a run of a catalogue.

    A run is made the way the harvesting makes one: through its catalogue, which
    writes the first row of its change log and never sets `date_created`. Its
    records so far are the temporary files it has stored, because those are the
    numbers the steps of a run are derived from.
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        cls.contact = MetadataContact.objects.create(name='Measurement contact')
        cls.records = DatasetMetadataRecord.objects.bulk_create([
            DatasetMetadataRecord(
                metadata_contact=cls.contact, dataset_contact=cls.contact,
                title=f'Dataset {number}')
            for number in range(5)])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.get(
            username='User1'))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def working_run(self, phase=Phase.DOWNLOAD_RECORDS, total_records=100,
                    step_size=10, waiting=0, made=60, date_created=False,
                    done_at=None):
        """A harvesting run which worked for `made` seconds.

        Named apart from `TestCase.run`, which the runner itself owns.

        Args:
            phase: the phase the run is in
            total_records: the records the catalogue counted for it, None while
                they are still being determined
            step_size: the page size the run asks the catalogue with
            waiting: the temporary files the run has on its backlog; while it
                downloads these are the records it stored, while it imports they
                are the records which are NOT stored yet
            made: how many seconds ago the run was made
            date_created: write the creation on the row instead of leaving it to
                the change log, which is what the harvesting never does
            done_at: how many seconds ago the run ended, None while it works

        Returns:
            HarvestingJob: the run
        """
        service = CatalogueService(
            id=uuid4(), title='Catalogue under measurement', version=202,
            origin=1, service_url='https://example.com/csw',
            metadata_contact=self.contact, service_contact=self.contact)
        CatalogueService.objects.bulk_create([service])
        # the path of the api: creating a run with its catalogue writes the first
        # row of its change log and no `date_created`
        job = HarvestingJob.objects.create(
            service=service, total_records=total_records,
            max_step_size=step_size, phase=phase)
        row = {'date_created': now() - timedelta(seconds=made)} if date_created \
            else {}
        if done_at is not None:
            row['done_at'] = now() - timedelta(seconds=done_at)
        if row:
            HarvestingJob.objects.filter(pk=job.pk).update(**row)
            job.refresh_from_db()
        if not date_created:
            job.change_logs.all().update(
                history_date=now() - timedelta(seconds=made))
        TemporaryMdMetadataFile.objects.bulk_create(
            [TemporaryMdMetadataFile(job=job) for _ in range(waiting)])
        return job

    def answered(self, *jobs, fields=MEASUREMENTS, **params):
        """The attributes the endpoint answers for the given runs.

        Args:
            *jobs: the runs to ask
            fields: the sparse fieldset of the request
            **params: further query parameters of the request

        Returns:
            dict: the answered attributes of every run by its id
        """
        response = self.client.get(
            reverse('registry:harvestingjob-list'),
            {'fields[HarvestingJob]': fields, 'page[size]': 100, **params})
        self.assertEqual(response.status_code, 200, response.content)
        answered = {row['id']: row['attributes'] for row in response.json()['data']}
        return {str(job.pk): answered[str(job.pk)] for job in jobs}

    def queries_for(self, path, **params):
        """The queries a request against ``path`` answers with."""
        with CaptureQueriesContext(connections['default']) as context:
            response = self.client.get(path, params, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return [query['sql'] for query in context.captured_queries]

    def test_a_downloading_run_answers_its_time_its_throughput_its_estimate(self):
        """60 seconds of work which stored 50 of 100 records are 50 per minute

        10 round trips and 100 records make 111 steps, of which the 50 stored
        records and their 5 round trips are 6: the run estimates the remaining
        105 steps against the 6 which measured 60 seconds.
        """
        job = self.working_run(waiting=50, made=60)
        answered = self.answered(job)[str(job.pk)]

        self.assertIsNone(job.date_created, 'the harvesting never sets it')
        self.assertAlmostEqual(answered['elapsedSeconds'], 60, delta=2)
        self.assertAlmostEqual(
            answered['recordsPerMinuteRunning'], 50.0, delta=1)
        self.assertAlmostEqual(
            answered['estimatedSecondsRemaining'], 60 * 105 / 6, delta=3)

    def test_the_estimate_names_the_moment_the_run_is_expected_to_end(self):
        job = self.working_run(waiting=50, made=60)
        answered = self.answered(job)[str(job.pk)]

        expected = now() + timedelta(seconds=answered['estimatedSecondsRemaining'])
        answered_at = datetime.fromisoformat(
            answered['expectedDoneAt'].replace('Z', '+00:00'))
        self.assertAlmostEqual(
            (answered_at - expected).total_seconds(), 0, delta=3,
            msg='the expected end is the estimate added to the same clock')

    def test_an_importing_run_answers_the_records_it_wrote_so_far(self):
        """while a run imports, the files still waiting are what is NOT stored

        100 records, 25 of them still waiting: the run wrote 75. Its steps are
        1 + 10 round trips + 100 - 25 waiting = 86 of 111, so 86 seconds of work
        estimate the remaining 25 steps at 25 seconds.
        """
        job = self.working_run(phase=Phase.RECORDS_TO_DB, waiting=25, made=86)
        answered = self.answered(job)[str(job.pk)]

        self.assertAlmostEqual(
            answered['recordsPerMinuteRunning'], 75 * 60 / 86, delta=1)
        self.assertAlmostEqual(answered['estimatedSecondsRemaining'], 25, delta=1)

    def test_a_run_which_does_not_know_its_records_answers_no_estimate(self):
        """the phase which determines the records has nothing to scale an estimate on"""
        job = self.working_run(
            phase=Phase.GET_TOTAL_RECORDS_COUNT, total_records=None,
            waiting=0, made=30)
        answered = self.answered(job)[str(job.pk)]

        self.assertAlmostEqual(answered['elapsedSeconds'], 30, delta=2)
        self.assertIsNone(answered['estimatedSecondsRemaining'])
        self.assertIsNone(answered['expectedDoneAt'])
        self.assertIsNone(answered['recordsPerMinuteRunning'])

    def test_a_completed_run_answers_no_remaining_time(self):
        """nothing is left of a run which ended, so nothing is left to estimate

        Its elapsed time is the whole duration of the harvest, and its throughput
        of a finished harvest is answered by `recordsPerMinute` (#692).
        """
        job = self.working_run(phase=Phase.COMPLETED, waiting=0, made=120, done_at=10)
        answered = self.answered(job)[str(job.pk)]

        self.assertAlmostEqual(answered['elapsedSeconds'], 110, delta=2)
        self.assertIsNone(answered['estimatedSecondsRemaining'])
        self.assertIsNone(answered['expectedDoneAt'])
        self.assertIsNone(answered['recordsPerMinuteRunning'])

    def test_an_aborted_run_answers_no_remaining_time(self):
        job = self.working_run(phase=Phase.ABORTED, waiting=40, made=120, done_at=5)
        answered = self.answered(job)[str(job.pk)]

        self.assertIsNone(answered['estimatedSecondsRemaining'])
        self.assertIsNone(answered['expectedDoneAt'])
        self.assertIsNone(answered['recordsPerMinuteRunning'])

    def test_the_creation_of_a_run_is_read_from_its_change_log(self):
        """a run of a deployment which has harvested for years answers an elapsed time

        `date_created` is nullable and the harvesting never sets it, so the
        moment the run was made is the first row of its change log - the same
        source which answers who made a run (#693, #1071).
        """
        job = self.working_run(waiting=10, made=90)
        self.assertIsNone(job.date_created)
        self.assertAlmostEqual(
            self.answered(job)[str(job.pk)]['elapsedSeconds'], 90, delta=2)

    def test_the_date_created_of_a_run_wins_over_its_change_log(self):
        """where a creation was set explicitly, it is the moment the run was made

        The row of the change log of this run stays at the moment it was written,
        so the two answers differ and only the earlier one is the creation.
        """
        job = self.working_run(waiting=10, made=180, date_created=True)
        self.assertAlmostEqual(
            self.answered(job)[str(job.pk)]['elapsedSeconds'], 180, delta=2)

    def test_a_request_which_asks_no_measurement_pays_for_none(self):
        """the query of a screen without measurements stays the query of today"""
        job = self.working_run(waiting=50, made=60)
        answered = self.answered(job, fields='id,progress')

        for field in MEASUREMENT_ANSWERS:
            self.assertNotIn(field, answered[str(job.pk)])
        sql = self.queries_for(
            reverse('registry:harvestingjob-list'),
            **{'fields[HarvestingJob]': 'id,progress'})
        self.assertFalse(
            [q for q in sql if 'TO_TIMESTAMP' in q
             or 'historicalharvestingjob' in q],
            'a request which asks no measurement reads no change log')

    def test_the_measurements_aggregate_no_harvested_records(self):
        """what a run has stored comes from its own files, not from its records

        The screen which shows these numbers asks them every few seconds while the
        import of this run writes into the table of the harvested metadata
        relations; the aggregation of that table is what makes watching a harvest
        slow the harvest down (#1071, cf. #1037).
        """
        job = self.working_run(phase=Phase.RECORDS_TO_DB, waiting=25, made=86)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(
                harvesting_job=job, dataset_metadata_record=record,
                collecting_state=State.NEW.value)
            for record in self.records])

        answered = self.answered(job)[str(job.pk)]
        self.assertIsNotNone(answered['estimatedSecondsRemaining'])
        sql = self.queries_for(
            reverse('registry:harvestingjob-list'),
            **{'fields[HarvestingJob]': MEASUREMENTS, 'page[size]': 100})
        self.assertFalse(
            [q for q in sql if '"sums"' in q],
            'the measurements of a run read no aggregation of its harvested records')

    def test_the_durations_of_one_run_read_the_records_of_that_run(self):
        """a request which names one run aggregates no other run's records either

        The statistics of a run are aggregated in one CTE over the whole table of
        the harvested metadata relations and joined ``LEFT OUTER``, which answers
        one row per job anyway (#885). A request whose url names one run answers
        exactly that run, so the aggregation is bounded to its records.
        """
        job = self.working_run(phase=Phase.COMPLETED, waiting=0, made=60, done_at=0)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(
                harvesting_job=job, dataset_metadata_record=record,
                collecting_state=State.NEW.value)
            for record in self.records])
        fields = 'id,fetch_record_duration,md_metadata_file_to_db_duration'

        detail = self.queries_for(
            reverse('registry:harvestingjob-detail', args=[job.pk]),
            **{'fields[HarvestingJob]': fields})
        aggregated = [q for q in detail if '"sums"' in q]
        self.assertTrue(aggregated, 'the durations are answered')
        self.assertTrue(
            [q for q in aggregated if f'"harvesting_job_id" = {job.pk}' in q],
            'the aggregation of the durations of one run is bounded to that run')

        # the narrowing answers the same numbers as the unbounded aggregation
        listed = self.answered(job, fields=fields + ',records_per_minute')
        detailed = self.client.get(
            reverse('registry:harvestingjob-detail', args=[job.pk]),
            {'fields[HarvestingJob]': fields + ',records_per_minute'})
        self.assertEqual(detailed.status_code, 200, detailed.content)
        self.assertEqual(
            listed[str(job.pk)],
            detailed.json()['data']['attributes'],
            'the bounded aggregation answers what the whole table answers')
