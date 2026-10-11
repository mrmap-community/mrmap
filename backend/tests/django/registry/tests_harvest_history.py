from datetime import timedelta
from django.test import TestCase
from django.utils.timezone import now
from registry.enums.harvesting import CollectingStatenEnum as State, HarvestingPhaseEnum as Phase
from registry.models.harvest import HarvestedMetadataRelation, HarvestingJob, HarvestingLog, TemporaryMdMetadataFile
from registry.models.metadata import MetadataContact, DatasetMetadataRecord, ServiceMetadataRecord
from registry.models.service import CatalogueService, WebFeatureService
from registry.querys.harvest_history import complete_harvest
from registry.views.harvesting import HarvestedMetadataRelationViewSet
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
        DatasetMetadataRecord.objects.bulk_create([cls.dataset])
        ServiceMetadataRecord.objects.bulk_create([cls.metadata])
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

    def test_history_endpoint_filters_catalogue_states_and_sorts_date(self):
        job = self.job()
        complete_harvest(job.pk)
        view = HarvestedMetadataRelationViewSet()
        view.action = 'list'
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
        view.request = Request(APIRequestFactory().get('/', {'filter[service]': str(service.pk)}))
        query = view.filter_queryset(view.get_queryset())
        self.assertIn(str(service.pk).replace('-', ''), str(query.query).replace('-', ''))
