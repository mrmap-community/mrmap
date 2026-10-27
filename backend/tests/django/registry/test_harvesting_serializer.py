from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob
from registry.models.metadata import MetadataContact
from registry.models.service import CatalogueService
from registry.serializers.harvesting import (CreateHarvestingJobSerializer,
                                             HarvestingJobSerializer)
from registry.serializers.service import CatalogueServiceSerializer
from rest_framework.exceptions import ValidationError as InvalidInput


class HarvestingPhaseLabelTests(SimpleTestCase):
    def test_phase_label_is_read_only_and_preserves_numeric_phase(self):
        job = HarvestingJob(phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS)
        serializer = HarvestingJobSerializer()
        label = serializer.fields['phase_label']
        phase = serializer.fields['phase']
        self.assertTrue(label.read_only)
        self.assertEqual(label.to_representation(label.get_attribute(job)), 'download records')
        self.assertEqual(phase.to_representation(phase.get_attribute(job)), 2)


class HarvestingStepSizeTest(TestCase):
    """Tests the step size a harvesting run is started with and the size a catalogue keeps.

    The catalogue is the memory of the size its remote service answers while a job stays the record
    of one run: a harvest which names no step size starts from the value of its catalogue, an
    explicit value of the request still wins and a value which no run can carry is answered as
    invalid input instead of breaking while the run divides its round trips by it (#691).
    """

    @classmethod
    def setUpTestData(cls):
        contact = MetadataContact.objects.create(name='Step size contact')
        cls.service = CatalogueService(
            title='Catalogue', version=202, origin=1,
            service_url='https://example.com/csw',
            metadata_contact=contact, service_contact=contact,
            max_step_size=120)
        CatalogueService.objects.bulk_create([cls.service])

    def serializer(self, **data):
        """the serializer which answers a harvest which is started by the api"""
        return CreateHarvestingJobSerializer(data={
            'service': {'id': str(self.service.pk), 'type': 'CatalogueService'},
            **data})

    def test_a_harvest_without_a_step_size_starts_from_the_catalogue(self):
        serializer = self.serializer()
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['max_step_size'], 120)

    def test_an_explicit_step_size_wins_and_stays_the_record_of_the_job(self):
        serializer = self.serializer(max_step_size=30)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['max_step_size'], 30)

    def test_a_step_size_which_no_run_can_carry_is_no_server_error(self):
        """a size of 0 divides the round trips of a run by zero and a size above the smallint of
        the job leaves the database with a data error - both are input the api answers"""
        for size in (0, 40000):
            with self.subTest(size=size):
                serializer = self.serializer(max_step_size=size)
                self.assertFalse(serializer.is_valid())
                self.assertIn('max_step_size', serializer.errors)

    def test_a_catalogue_answers_its_step_size_only_in_range(self):
        """the value of the catalogue is what a run starts from, so the catalogue itself answers a
        size which no run can carry as invalid - at the api as well as on the model"""
        for size in (0, 40000):
            with self.subTest(size=size):
                field = CatalogueServiceSerializer().fields['max_step_size']
                with self.assertRaises(InvalidInput):
                    field.run_validation(size)
                service = CatalogueService.objects.get(pk=self.service.pk)
                service.max_step_size = size
                with self.assertRaises(ValidationError):
                    service.full_clean()

    def test_the_size_a_run_starts_with_is_the_size_of_the_catalogue(self):
        """the boundaries of the range are the sizes a run is started with"""
        for size in (1, 32767):
            with self.subTest(size=size):
                CatalogueService.objects.filter(
                    pk=self.service.pk).update(max_step_size=size)
                serializer = self.serializer()
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertEqual(serializer.validated_data['max_step_size'], size)
