from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django_celery_beat.models import CrontabSchedule
from registry.models.harvest import HarvestingJob, PeriodicHarvestingJob
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService
from registry.serializers.harvesting import (CreateHarvestingJobSerializer,
                                             PeriodicHarvestingJobSerializer)
from registry.serializers.service import CatalogueServiceSerializer
from registry.settings import MRMAP_CSW_PK
from registry.tasks.harvest import create_harvesting_job


class InternalCswHarvestingTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Harvesting contact')
        cls.external = CatalogueService(
            title='External catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact)
        cls.internal = CatalogueService(
            pk=MRMAP_CSW_PK, title='Internal catalogue', version=202, origin=1,
            metadata_contact=contact, service_contact=contact)
        CatalogueService.objects.bulk_create([cls.external, cls.internal], ignore_conflicts=True)
        cls.crontab = CrontabSchedule.objects.create(minute='0', hour='2')

    def test_catalogues_expose_their_harvesting_capability(self):
        field = CatalogueServiceSerializer().fields['is_harvestable']
        self.assertTrue(field.read_only)
        self.assertFalse(field.get_attribute(self.internal))
        self.assertTrue(field.get_attribute(self.external))

    def test_api_rejects_internal_harvests_and_even_disabled_schedules(self):
        for serializer_class, extra in (
            (CreateHarvestingJobSerializer, {}),
            (PeriodicHarvestingJobSerializer, {'scheduling': '0 2 * * *', 'enabled': False}),
        ):
            with self.subTest(serializer=serializer_class.__name__):
                serializer = serializer_class(data={
                    'service': {'type': 'CatalogueService', 'id': MRMAP_CSW_PK}, **extra})
                self.assertFalse(serializer.is_valid())
                self.assertIn('service', serializer.errors)

    def test_api_rejects_reassigning_an_external_schedule_to_the_internal_csw(self):
        schedule = PeriodicHarvestingJob.objects.create(service=self.external, crontab=self.crontab)
        serializer = PeriodicHarvestingJobSerializer(schedule, partial=True, data={
            'service': {'type': 'CatalogueService', 'id': MRMAP_CSW_PK}})
        self.assertFalse(serializer.is_valid())
        self.assertIn('service', serializer.errors)

    def test_database_rejects_internal_harvests_before_dispatching_tasks(self):
        with patch('registry.tasks.harvest.call_fetch_total_records.apply_async') as dispatch:
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    HarvestingJob.objects.create(service=self.internal)
            dispatch.assert_not_called()

    def test_database_rejects_bulk_insert_and_reassignment_of_internal_harvests(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            HarvestingJob.objects.bulk_create([HarvestingJob(service=self.internal)])
        job = HarvestingJob(service=self.external)
        HarvestingJob.objects.bulk_create([job])
        with self.assertRaises(IntegrityError), transaction.atomic():
            HarvestingJob.objects.filter(pk=job.pk).update(service=self.internal)

    def test_database_rejects_disabled_internal_schedules_and_reassignment(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodicHarvestingJob.objects.create(service=self.internal, crontab=self.crontab, enabled=False)
        schedule = PeriodicHarvestingJob.objects.create(service=self.external, crontab=self.crontab)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodicHarvestingJob.objects.filter(pk=schedule.pk).update(service=self.internal)

    def test_file_imports_without_a_service_remain_allowed(self):
        job = HarvestingJob()
        HarvestingJob.objects.bulk_create([job])
        self.assertIsNone(HarvestingJob.objects.get(pk=job.pk).service_id)

    def test_scheduled_task_ignores_the_internal_csw_without_dispatching_a_harvest(self):
        with patch('registry.tasks.harvest.call_fetch_total_records.delay') as dispatch:
            self.assertIsNone(create_harvesting_job.run(service_id=MRMAP_CSW_PK))
            dispatch.assert_not_called()
        self.assertFalse(HarvestingJob.objects.filter(service=self.internal).exists())
