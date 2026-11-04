from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum as State, HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob, HarvestingLog, TemporaryMdMetadataFile
from registry.models.metadata import (ApplicationMetadataRecord,
                                      DatasetMetadataRecord,
                                      MetadataContact, ServiceMetadataRecord)
from registry.models.service import CatalogueService, WebFeatureService
from registry.querys.harvest_history import complete_harvest, complete_snapshots
from registry.views.harvesting import HarvestedMetadataRelationViewSet
from registry.views.service import CatalogueServiceViewSet
from registry.views.historical import FeatureTypeHistoricalViewSet
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory


class HarvestHistoryTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='History contact')
        cls.service = CatalogueService(id='11111111-1111-1111-1111-111111111111', title='Catalogue', version=202, origin=1,
            service_url='https://example.com/csw', metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([cls.service])
        cls.dataset = DatasetMetadataRecord(metadata_contact=contact, dataset_contact=contact, title='Dataset')
        cls.metadata = ServiceMetadataRecord(metadata_contact=contact, title='Service metadata')
        cls.application = ApplicationMetadataRecord(metadata_contact=contact, application_contact=contact, title='Application')
        DatasetMetadataRecord.objects.bulk_create([cls.dataset])
        ServiceMetadataRecord.objects.bulk_create([cls.metadata])
        ApplicationMetadataRecord.objects.bulk_create([cls.application])
        cls.previous = HarvestingJob(service=cls.service, total_records=2, phase=Phase.COMPLETED, done_at=now()-timedelta(days=1))
        HarvestingJob.objects.bulk_create([cls.previous])
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=cls.previous, dataset_metadata_record=cls.dataset, collecting_state=State.NEW),
            HarvestedMetadataRelation(harvesting_job=cls.previous, service_metadata_record=cls.metadata, collecting_state=State.NEW),
        ])

    def job(self, **kwargs):
        job = HarvestingJob(service=self.service, total_records=0, phase=Phase.RECORDS_TO_DB)
        for key, value in kwargs.items():
            setattr(job, key, value)
        HarvestingJob.objects.bulk_create([job])
        return job

    def removed(self, job):
        return HarvestedMetadataRelation.objects.filter(harvesting_job=job, collecting_state=State.REMOVED)

    def test_catalogue_counts_linked_records_once_across_harvests(self):
        self.dataset.harvested_through.add(self.service)
        self.metadata.harvested_through.add(self.service)
        job = self.job()
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.UPDATED),
        ])
        view = CatalogueServiceViewSet()
        for fields in ([], ['harvestedTotalCount'], ['harvestedDatasetCount'], ['harvestedServiceCount']):
            with self.subTest(fields=fields):
                view.sparse_fields = {'CatalogueService': fields}
                record = view.with_harvesting_stats(CatalogueService.objects.filter(pk=self.service.pk)).get()
                if not fields or 'harvestedTotalCount' in fields:
                    self.assertEqual(record.harvested_total_count, 2)
                if not fields or 'harvestedTotalCount' in fields or 'harvestedDatasetCount' in fields:
                    self.assertEqual(record.harvested_dataset_count, 1)
                if not fields or 'harvestedTotalCount' in fields or 'harvestedServiceCount' in fields:
                    self.assertEqual(record.harvested_service_count, 1)

    def test_catalogue_counts_follow_record_links_and_return_zero_without_links(self):
        self.dataset.harvested_through.add(self.service)
        self.metadata.harvested_through.add(self.service)
        self.dataset.harvested_through.remove(self.service)
        self.metadata.harvested_through.remove(self.service)
        view = CatalogueServiceViewSet()
        view.sparse_fields = {'CatalogueService': ['harvestedTotalCount']}
        record = view.with_harvesting_stats(CatalogueService.objects.filter(pk=self.service.pk)).get()
        self.assertEqual(record.harvested_dataset_count, 0)
        self.assertEqual(record.harvested_service_count, 0)
        self.assertEqual(record.harvested_total_count, 0)

    def test_empty_full_harvest_records_both_removals_and_is_idempotent(self):
        job = self.job()
        complete_harvest(job.pk)
        complete_harvest(job.pk)
        self.assertEqual(self.removed(job).count(), 2)
        self.assertTrue(DatasetMetadataRecord.objects.filter(pk=self.dataset.pk).exists())
        self.assertTrue(ServiceMetadataRecord.objects.filter(pk=self.metadata.pk).exists())
        next_job = self.job()
        complete_harvest(next_job.pk)
        self.assertEqual(self.removed(next_job).count(), 0)

    def test_existing_and_updated_records_are_not_removed(self):
        job = self.job(total_records=1)
        HarvestedMetadataRelation.objects.create(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.UPDATED)
        complete_harvest(job.pk)
        self.assertEqual(list(self.removed(job).values_list('service_metadata_record_id', flat=True)), [self.metadata.pk])

    def test_a_finished_harvest_keeps_its_step_size_on_the_catalogue(self):
        """the catalogue is the memory of the size its remote service answers: the run which
        finished leaves the size it worked with at the catalogue, so the next run starts from what
        this service proved instead of from a default nobody chose (#691)"""
        CatalogueService.objects.filter(pk=self.service.pk).update(max_step_size=50)
        complete_harvest(self.job(max_step_size=300).pk)
        self.service.refresh_from_db()
        self.assertEqual(self.service.max_step_size, 300)

    def test_a_harvest_which_did_not_finish_leaves_the_size_of_the_catalogue_alone(self):
        """a run which broke tells nothing about the size the service answers with"""
        CatalogueService.objects.filter(pk=self.service.pk).update(max_step_size=120)
        complete_harvest(self.job(max_step_size=300, phase=Phase.ABORTED).pk)
        self.service.refresh_from_db()
        self.assertEqual(self.service.max_step_size, 120)

    def test_incomplete_partial_failed_and_aborted_jobs_do_not_record_removals(self):
        for overrides in [dict(total_records=1), dict(harvest_services=False), dict(harvest_datasets=False), dict(phase=Phase.ABORTED), dict(phase=Phase.ABORT)]:
            with self.subTest(overrides=overrides):
                job = self.job(**overrides)
                complete_harvest(job.pk)
                self.assertFalse(self.removed(job).exists())
                HarvestingJob.objects.filter(pk=job.pk).update(done_at=now())
        for failure in ['log', 'file']:
            job = self.job()
            if failure == 'log':
                HarvestingLog.objects.create(harvesting_job=job, level=1, description='Download failed')
            else:
                TemporaryMdMetadataFile.objects.create(job=job, has_import_error=True)
            complete_harvest(job.pk)
            self.assertFalse(self.removed(job).exists())

    def test_failed_snapshot_is_skipped_as_baseline(self):
        failed = self.job(total_records=1, phase=Phase.COMPLETED, done_at=now()-timedelta(hours=1))
        job = self.job()
        complete_harvest(job.pk)
        self.assertEqual(self.removed(job).count(), 2)

    def test_first_snapshot_does_not_infer_removals(self):
        HarvestedMetadataRelation.objects.filter(harvesting_job=self.previous).delete()
        job = self.job()
        complete_harvest(job.pk)
        self.assertFalse(self.removed(job).exists())

    def test_all_three_buckets_account_for_the_snapshot(self):
        """a run which stored the dataset, the service and the application the catalogue
        counted is a complete snapshot: application records neither hide in it nor make it
        read incomplete (#903, #827)"""
        HarvestedMetadataRelation.objects.filter(harvesting_job=self.previous).delete()
        job = self.job(total_records=3)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.NEW),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.NEW),
            HarvestedMetadataRelation(harvesting_job=job, application_metadata_record=self.application, collecting_state=State.NEW),
        ])
        complete_harvest(job.pk)
        snapshot = complete_snapshots(self.service.pk).get(pk=job.pk)
        self.assertEqual(
            (snapshot.dataset_count, snapshot.service_count, snapshot.application_count),
            (1, 1, 1))

    def test_a_run_which_loses_the_application_count_is_not_a_snapshot(self):
        """the catalogue counted three but the run only accounts for two - the application
        record the index promised did not land - so the run is no snapshot and stores no
        removals; the count which is short cannot be trusted to decide about records (#827)"""
        job = self.job(total_records=3)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
        ])
        complete_harvest(job.pk)
        self.assertFalse(complete_snapshots(self.service.pk).filter(pk=job.pk).exists())
        self.assertFalse(self.removed(job).exists())

    def test_a_run_which_stores_more_than_the_catalogue_counted_is_not_a_snapshot(self):
        """the other direction: the count of the catalogue did not carry the application
        which the run stored - the run cannot be a snapshot either"""
        job = self.job(total_records=2)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, application_metadata_record=self.application, collecting_state=State.EXISTING),
        ])
        complete_harvest(job.pk)
        self.assertFalse(complete_snapshots(self.service.pk).filter(pk=job.pk).exists())

    def test_a_run_without_applications_keeps_the_legacy_snapshot_semantics(self):
        """harvest_applications=False means the run never asked for applications; the two
        existing buckets decide its completeness alone, exactly as before #827 - and its
        snapshot does not claim the third flag the run never carried"""
        HarvestedMetadataRelation.objects.filter(harvesting_job=self.previous).delete()
        job = self.job(total_records=2, harvest_applications=False)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
        ])
        complete_harvest(job.pk)
        # the flag subset the run carries is a condition of the snapshot, so a run which
        # never asked for applications is not one of the three-type snapshots this query answers
        self.assertFalse(complete_snapshots(self.service.pk).filter(pk=job.pk).exists())

    def test_an_application_record_missing_from_the_next_snapshot_is_removed(self):
        """a complete snapshot which no longer answers an application the previous one
        carried removes it like any other record; the application bucket travels with the
        removal loop the dataset and service columns already drove (#827)"""
        previous = self.job(total_records=3, phase=Phase.COMPLETED,
                            done_at=now() - timedelta(hours=1))
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=previous, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=previous, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=previous, application_metadata_record=self.application, collecting_state=State.EXISTING),
        ])
        job = self.job(total_records=2)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
        ])
        complete_harvest(job.pk)
        removed = self.removed(job)
        self.assertEqual(
            list(removed.values_list('application_metadata_record_id', flat=True)),
            [self.application.pk])
        self.assertIsNone(removed.get().dataset_metadata_record_id)
        self.assertIsNone(removed.get().service_metadata_record_id)

    def test_an_application_record_the_snapshot_keeps_is_not_removed(self):
        """the application the new snapshot still answers stays - the removal only names
        what the previous snapshot carried and this one lost"""
        previous = self.job(total_records=3, phase=Phase.COMPLETED,
                            done_at=now() - timedelta(hours=1))
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=previous, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=previous, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=previous, application_metadata_record=self.application, collecting_state=State.EXISTING),
        ])
        job = self.job(total_records=3)
        HarvestedMetadataRelation.objects.bulk_create([
            HarvestedMetadataRelation(harvesting_job=job, dataset_metadata_record=self.dataset, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, service_metadata_record=self.metadata, collecting_state=State.EXISTING),
            HarvestedMetadataRelation(harvesting_job=job, application_metadata_record=self.application, collecting_state=State.EXISTING),
        ])
        complete_harvest(job.pk)
        self.assertFalse(self.removed(job).exists())

    def test_history_endpoint_filters_catalogue_states_and_sorts_date(self):
        job = self.job()
        complete_harvest(job.pk)
        view = HarvestedMetadataRelationViewSet()
        view.action = 'list'
        view.kwargs = {}
        view.request = Request(APIRequestFactory().get('/', {
            'filter[harvestingJob.service]': str(self.service.pk),
            'filter[collectingState.in]': '4', 'sort': '-historyDate',
        }))
        rows = list(view.filter_queryset(view.get_queryset()))
        self.assertEqual({row.pk for row in rows}, set(self.removed(job).values_list('pk', flat=True)))
        self.assertGreaterEqual(rows[0].history_date, rows[-1].history_date)

    def test_feature_history_service_filter(self):
        contact = MetadataContact.objects.first()
        service = WebFeatureService(title='WFS', version=200, origin=1, service_url='https://example.com/wfs', metadata_contact=contact, service_contact=contact)
        WebFeatureService.objects.bulk_create([service])
        view = FeatureTypeHistoricalViewSet()
        view.action = 'list'
        view.kwargs = {}
        view.request = Request(APIRequestFactory().get('/', {'filter[service]': str(service.pk)}))
        query = view.filter_queryset(view.get_queryset())
        self.assertIn(str(service.pk).replace('-', ''), str(query.query).replace('-', ''))
