from django.test import SimpleTestCase
from registry.enums.harvesting import HarvestingPhaseEnum
from registry.models.harvest import HarvestingJob
from registry.serializers.harvesting import HarvestingJobSerializer


class HarvestingPhaseLabelTests(SimpleTestCase):
    def test_phase_label_is_read_only_and_preserves_numeric_phase(self):
        job = HarvestingJob(phase=HarvestingPhaseEnum.DOWNLOAD_RECORDS)
        serializer = HarvestingJobSerializer()
        label = serializer.fields['phase_label']
        phase = serializer.fields['phase']
        self.assertTrue(label.read_only)
        self.assertEqual(label.to_representation(label.get_attribute(job)), 'download records')
        self.assertEqual(phase.to_representation(phase.get_attribute(job)), 2)
