"""The throughput a completed harvest of a catalogue measured (#692).

The size a harvest asks a catalogue with is only worth keeping on the catalogue
as long as it is the size the records come fastest with. That is measurable with
the runs a catalogue already has behind it: every run names the size it asked
with, and every record of it carries the time its download and its way into the
database measured. Which size is the better one is therefore answered by the runs
themselves and not by a default somebody typed.

The throughput is an annotation, because it is the answer of a grouped
aggregation over the harvested records of a run and not a column of a row. What
it must not answer is part of its contract and tested here as well: a run which
never finished, a run whose records carry no durations and the records a snapshot
only bookkeeps as removed all say nothing about how fast a harvest is.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import DatasetMetadataRecord, MetadataContact
from registry.models.service import CatalogueService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
CATALOGUE = '22222222-2222-2222-2222-222222222222'
FIELDS = 'id,max_step_size,records_per_minute'


class HarvestingThroughputTest(TestCase):
    """The throughput of the runs a catalogue answers, measured by their records.

    A run is made of the records it harvested, so a run is created here with as
    many records as it harvested and with the duration of a single record - which
    is what `download_duration` is: the time of a response spread over the records
    of that response.
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Throughput contact')
        cls.service = CatalogueService(
            id=CATALOGUE, title='Catalogue', version=202, origin=1,
            service_url='https://example.com/csw', metadata_contact=contact,
            service_contact=contact)
        CatalogueService.objects.bulk_create([cls.service])
        cls.records = DatasetMetadataRecord.objects.bulk_create([
            DatasetMetadataRecord(
                metadata_contact=contact, dataset_contact=contact,
                title=f'Dataset {number}')
            for number in range(10)])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username='throughput', password='test'))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def new_run(self, records=5, step_size=50, download=timedelta(seconds=6),
                processing=timedelta(seconds=6), phase=Phase.COMPLETED,
                done_at='now'):
        """A harvesting run of the catalogue which harvested the given records.

        The durations are the ones of a single record, like the model names them:
        the run stored `records` records, each of them measuring `download` to
        arrive and `processing` to be written to the database.

        Args:
            records: how many records the run stored
            step_size: the page size the run asked the catalogue with
            download: the measured download time of one record
            processing: the measured database time of one record
            phase: the phase the run ended in
            done_at: the end of the run, 'now' or None for a run which never ended

        Returns:
            HarvestingJob: the run, with its records
        """
        job = HarvestingJob(
            service=self.service, total_records=records,
            max_step_size=step_size, phase=phase,
            done_at=now() if done_at == 'now' else done_at)
        HarvestingJob.objects.bulk_create([job])
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(
                harvesting_job=job, dataset_metadata_record=record,
                collecting_state=State.NEW, download_duration=download,
                processing_duration=processing)
            for record in self.records[:records]])
        return job

    def answered_runs(self, **params):
        """The runs the endpoint of the harvesting jobs answers.

        Args:
            **params: the query parameters of the request

        Returns:
            dict: the answered attributes of the runs by their id
        """
        response = self.client.get(
            reverse('registry:harvestingjob-list'),
            {'filter[service__id]': CATALOGUE, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return {
            row['id']: row['attributes'] for row in response.json()['data']}

    def throughput(self, *jobs):
        """The attributes the endpoint answers for the given runs.

        Args:
            *jobs: the runs to ask the throughput of

        Returns:
            dict: the answered attributes of every run by its id
        """
        answered = self.answered_runs(**{'fields[HarvestingJob]': FIELDS})
        return {
            str(job.pk): answered[str(job.pk)] for job in jobs}

    def test_the_throughput_of_a_run_are_its_records_per_measured_minute(self):
        """5 records which measured 6 seconds each are 10 records per minute"""
        job = self.new_run(records=5, download=timedelta(seconds=3),
                           processing=timedelta(seconds=3))
        answered = self.throughput(job)[str(job.pk)]
        self.assertAlmostEqual(answered['recordsPerMinute'], 10.0, places=2)
        self.assertEqual(answered['maxStepSize'], 50)

    def test_two_runs_at_different_sizes_answer_their_own_throughput(self):
        """the runs of a catalogue compare themselves by the size each asked with

        Both runs stored 10 records; the one which asked with 25 measured half the
        time per record, so it answers twice the records per minute.
        """
        wide = self.new_run(records=10, step_size=50,
                            download=timedelta(seconds=2),
                            processing=timedelta(seconds=2))
        narrow = self.new_run(records=10, step_size=25,
                              download=timedelta(seconds=1),
                              processing=timedelta(seconds=1))
        wide, narrow = (self.throughput(wide, narrow)[str(job.pk)]
                        for job in (wide, narrow))
        self.assertAlmostEqual(wide['recordsPerMinute'], 15.0, places=2)
        self.assertAlmostEqual(narrow['recordsPerMinute'], 30.0, places=2)

    def test_a_run_which_never_finished_answers_no_throughput(self):
        """the sums of a run which stopped half way name work, not throughput"""
        job = self.new_run(records=5, phase=Phase.RECORDS_TO_DB, done_at=None)
        self.assertIsNone(
            self.throughput(job)[str(job.pk)]['recordsPerMinute'])

    def test_an_aborted_run_answers_no_throughput(self):
        """a run which broke answers what it happened to do, which is no harvest"""
        job = self.new_run(records=5, phase=Phase.ABORTED)
        self.assertIsNone(
            self.throughput(job)[str(job.pk)]['recordsPerMinute'])

    def test_a_run_whose_records_measured_nothing_answers_no_throughput(self):
        """nothing measured must not be answered as a throughput of nothing"""
        job = self.new_run(records=5, download=None, processing=None)
        self.assertIsNone(
            self.throughput(job)[str(job.pk)]['recordsPerMinute'])

    def test_records_which_only_a_snapshot_bookkeeps_do_not_count(self):
        """a completed snapshot records the records which are gone since the last one

        Those rows are bookkeeping of the snapshot, never records the run fetched,
        so they are neither a record of the throughput nor a measured duration.
        """
        job = self.new_run(records=5, download=timedelta(seconds=3),
                           processing=timedelta(seconds=3))
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(
                harvesting_job=job, dataset_metadata_record=record,
                collecting_state=State.REMOVED)
            for record in self.records[5:]])
        answered = self.throughput(job)[str(job.pk)]
        self.assertAlmostEqual(answered['recordsPerMinute'], 10.0, places=2)

    def test_the_endpoint_answers_every_run_of_the_catalogue(self):
        """the runs of a catalogue answer their own throughput with their own size"""
        completed = self.new_run(records=10, step_size=50,
                                 download=timedelta(seconds=2),
                                 processing=timedelta(seconds=2))
        unfinished = self.new_run(records=4, phase=Phase.RECORDS_TO_DB,
                                  done_at=None)
        answered = self.throughput(completed, unfinished)
        self.assertAlmostEqual(
            answered[str(completed.pk)]['recordsPerMinute'], 15.0, places=2)
        self.assertIsNone(
            answered[str(unfinished.pk)]['recordsPerMinute'])

    def test_the_runs_of_a_catalogue_can_be_ordered_by_their_end(self):
        """the end of a run is orderable, its creation is not a usable order

        The harvesting never sets `date_created`, so the runs a harvesting made over
        a year cannot be told apart by it. The screen which recommends a page size
        asks the runs which finished last, so the end of a run has to be an order of
        the endpoint (#692).
        """
        oldest = self.new_run(done_at=now() - timedelta(days=2))
        newest = self.new_run(done_at=now() - timedelta(hours=1))
        response = self.client.get(
            reverse('registry:harvestingjob-list'),
            {'filter[service__id]': CATALOGUE,
             'fields[HarvestingJob]': 'id',
             'sort': '-doneAt'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [row['id'] for row in response.json()['data']],
            [str(newest.pk), str(oldest.pk)])

    def test_a_request_which_asks_no_throughput_answers_none(self):
        """the runs answer the throughput only to those who ask for it

        The aggregation over the harvested records of a run is gated on the field,
        like the durations of the runs already are, so the screens which never
        show a throughput do not pay for it.
        """
        job = self.new_run()
        answered = self.answered_runs(
            **{'fields[HarvestingJob]': 'id,max_step_size'})
        self.assertNotIn('recordsPerMinute', answered[str(job.pk)])
