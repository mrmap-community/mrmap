"""The runs of a catalogue count the application records they harvested (#830).

The sums a harvesting run answers over its records were built for the dataset and
the service record; the application record arrived with #827 and the run still
answered nothing about it. The counts of all three kinds now share one CTE helper
of ``registry.views.harvesting`` - which makes two promises worth pinning:

* the application counts answer with the states the relations carry, gated on the
  sparse fieldsets like every other aggregated field, and
* the counts the dataset and the service record answered before are answered
  unchanged - a shared helper must not move a single number.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum as State
from registry.enums.harvesting import HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord, MetadataContact,
                                      ServiceMetadataRecord)
from registry.models.service import CatalogueService
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"
CATALOGUE = '44444444-4444-4444-4444-444444444444'

ALL_COUNTS = 'id,' + ','.join(
    f'{state}_{kind}_metadata_count'
    for kind in ('dataset', 'service', 'application')
    for state in ('new', 'updated', 'existing', 'duplicated'))

STATES = {'new': State.NEW, 'updated': State.UPDATED, 'existing': State.EXISTING,
          'duplicated': State.DUPLICATED, 'removed': State.REMOVED}


class HarvestingApplicationCountsTest(TestCase):
    """The per-state counts a run answers, for every kind of record it harvested.

    A run is made of its relations, so a run is created here with exactly the
    relations whose counts are asserted.
    """

    fixtures = ["test_users.json"]

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Counts contact')
        cls.service = CatalogueService(
            id=CATALOGUE, title='Catalogue', version=202, origin=1,
            service_url='https://example.com/csw', metadata_contact=contact,
            service_contact=contact)
        CatalogueService.objects.bulk_create([cls.service])
        cls.datasets = DatasetMetadataRecord.objects.bulk_create([
            DatasetMetadataRecord(
                metadata_contact=contact, dataset_contact=contact,
                title=f'Dataset {number}')
            for number in range(4)])
        cls.services = ServiceMetadataRecord.objects.bulk_create([
            ServiceMetadataRecord(
                metadata_contact=contact, title=f'Service record {number}',
                code=f'service-record-{number}')
            for number in range(4)])
        cls.applications = ApplicationMetadataRecord.objects.bulk_create([
            ApplicationMetadataRecord(
                metadata_contact=contact, application_contact=contact,
                title=f'Application {number}')
            for number in range(4)])

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(get_user_model().objects.create_superuser(
            username='counts-admin', password='test'))
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def new_run(self, dataset_states=(), service_states=(), application_states=()):
        """A harvesting run of the catalogue with one record per named state.

        Args:
            dataset_states: the collecting states the dataset relations carry
            service_states: the collecting states the service relations carry
            application_states: the collecting states the application relations
                carry; the application records are reused when the states are
                more than the records

        Returns:
            HarvestingJob: the run, with its relations
        """
        total = len(dataset_states) + len(service_states) + len(application_states)
        job = HarvestingJob(
            service=self.service, total_records=total, phase=Phase.COMPLETED,
            done_at=now())
        HarvestingJob.objects.bulk_create([job])
        relations = []
        for kind, states, records in (
                ('dataset_metadata_record', dataset_states, self.datasets),
                ('service_metadata_record', service_states, self.services),
                ('application_metadata_record', application_states, self.applications)):
            for number, state in enumerate(states):
                relations.append(HarvestedMetadataRelation(
                    harvesting_job=job, collecting_state=STATES[state],
                    **{kind: records[number % len(records)]}))
        HarvestedMetadataRelation.objects.bulk_create(relations)
        return job

    def counts(self, job, fields=ALL_COUNTS):
        """The attributes the endpoint answers for the given run.

        Args:
            job: the run to ask the counts of
            fields: the sparse fieldset of the request

        Returns:
            dict: the answered attributes of the run
        """
        response = self.client.get(
            reverse('registry:harvestingjob-list'),
            {'filter[service__id]': CATALOGUE, 'fields[HarvestingJob]': fields})
        self.assertEqual(response.status_code, 200, response.content)
        answered = {
            row['id']: row['attributes'] for row in response.json()['data']}
        return answered[str(job.pk)]

    def test_a_run_counts_the_application_records_of_every_state(self):
        """one relation per state is one record counted in that state

        The record which only a snapshot bookkeeps as removed is counted by none
        of the four states - the promise the dataset counts already made.
        """
        job = self.new_run(application_states=(
            'new', 'updated', 'existing', 'duplicated', 'removed'))
        answered = self.counts(job)
        self.assertEqual(answered['newApplicationMetadataCount'], 1)
        self.assertEqual(answered['updatedApplicationMetadataCount'], 1)
        self.assertEqual(answered['existingApplicationMetadataCount'], 1)
        self.assertEqual(answered['duplicatedApplicationMetadataCount'], 1)

    def test_the_dataset_and_service_counts_stay_unchanged(self):
        """the shared helper moves no number of the counts which came before"""
        job = self.new_run(
            dataset_states=('new', 'new', 'updated'),
            service_states=('existing', 'duplicated', 'removed'))
        answered = self.counts(job)
        self.assertEqual(answered['newDatasetMetadataCount'], 2)
        self.assertEqual(answered['updatedDatasetMetadataCount'], 1)
        self.assertEqual(answered['existingDatasetMetadataCount'], 0)
        self.assertEqual(answered['duplicatedDatasetMetadataCount'], 0)
        self.assertEqual(answered['newServiceMetadataCount'], 0)
        self.assertEqual(answered['updatedServiceMetadataCount'], 0)
        self.assertEqual(answered['existingServiceMetadataCount'], 1)
        self.assertEqual(answered['duplicatedServiceMetadataCount'], 1)

    def test_all_twelve_counts_answer_from_one_request(self):
        """the three kinds share one CTE and one answer

        One relation of every kind in a different state: every count names its
        own state and none of them borrows from another kind.
        """
        job = self.new_run(
            dataset_states=('new',),
            service_states=('updated',),
            application_states=('existing',))
        answered = self.counts(job)
        self.assertEqual(answered['newDatasetMetadataCount'], 1)
        self.assertEqual(answered['updatedServiceMetadataCount'], 1)
        self.assertEqual(answered['existingApplicationMetadataCount'], 1)
        for count in (
                'updatedDatasetMetadataCount', 'existingDatasetMetadataCount',
                'duplicatedDatasetMetadataCount', 'newServiceMetadataCount',
                'existingServiceMetadataCount', 'duplicatedServiceMetadataCount',
                'newApplicationMetadataCount', 'updatedApplicationMetadataCount',
                'duplicatedApplicationMetadataCount'):
            self.assertEqual(answered[count], 0, count)

    def test_a_run_without_application_records_counts_them_as_zero(self):
        """a run which harvested no application record answers zero, not nothing"""
        job = self.new_run(dataset_states=('new',))
        answered = self.counts(job)
        self.assertEqual(answered['newDatasetMetadataCount'], 1)
        self.assertEqual(answered['newApplicationMetadataCount'], 0)
        self.assertEqual(answered['duplicatedApplicationMetadataCount'], 0)

    def test_the_application_counts_answer_only_to_those_who_ask(self):
        """the aggregation over the application records is gated on the fields

        A screen which never shows the records of one kind does not pay for
        their aggregation - the promise the dataset counts already made.
        """
        job = self.new_run(application_states=('new',))
        answered = self.counts(
            job, fields='id,new_dataset_metadata_count')
        self.assertNotIn('newApplicationMetadataCount', answered)
        self.assertIn('newDatasetMetadataCount', answered)

    def test_the_run_answers_its_application_records_below_itself(self):
        """the nested endpoint of the run lists the application records of it"""
        job = self.new_run(application_states=('new', 'updated'))
        response = self.client.get(
            reverse('registry:harvestingjob-harvestedapplicationmetadata-list',
                    args=[job.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['data']
        self.assertEqual({row['type'] for row in rows}, {'ApplicationMetadataRecord'})
        self.assertEqual(
            {row['id'] for row in rows},
            {str(record.pk) for record in self.applications[:2]})

    def test_the_harvested_relations_of_applications_can_be_filtered(self):
        """the relation endpoint knows the application relation of a run and row"""
        job = self.new_run(application_states=('new',), dataset_states=('new',))
        response = self.client.get(
            reverse('registry:harvestedmetadatarelation-list'),
            {'filter[harvesting_job__id]': str(job.pk),
             'filter[application_metadata_record__isnull]': 'false'})
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.json()['data']
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(
            rows[0]['relationships']['applicationMetadataRecord']['data']['id'],
            str(self.applications[0].pk))
