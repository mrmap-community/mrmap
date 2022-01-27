from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.test.utils import override_settings
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import DatasetMetadata
from registry.tasks.harvest import (get_hits_task, get_records_task,
                                    temporary_md_metadata_file_to_db)
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(url, timeout):
    if "GetRecords" in url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/get_records.xml')))
    elif "hits" in url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/hits.xml')))


class HarvestingGetHitsTaskTest(TestCase):

    fixtures = ['test_csw.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.models.service.CatalougeService.send_get_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        get_hits_task.delay(harvesting_job_id=1)
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.total_records, 447773)


class HarvestingGetRecordsTaskTest(TestCase):

    fixtures = ['test_csw.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.models.service.CatalougeService.send_get_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        get_records_task.delay(harvesting_job_id=1, start_position=1)
        temporary_md_files_count: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.filter(
            job__id=1).count()
        self.assertEqual(temporary_md_files_count, 10)


class TemporaryMdMetadataFileToDbTaskTest(TestCase):

    fixtures = ['test_csw.json']

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("registry.models.harvest.TemporaryMdMetadataFile.md_metadata_file.open")
    def test_success(self, mocked_open_func):
        md_metadata_file = Path(Path.joinpath(Path(__file__).parent.resolve(),
                                              '../../test_data/csw/md_metadata.xml'))

        in_file = open(md_metadata_file, "rb")
        content: bytes = in_file.read()
        in_file.close()
        mocked_open_func.return_value = content

        temporary_md_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
            pk=1)
        harvesting_job: HarvestingJob = temporary_md_file.job

        temporary_md_metadata_file_to_db.delay(md_metadata_file_id=2)

        # temporary object was deleted
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job__id=2).count(), 0)
        # job is done
        self.assertFalse(harvesting_job.done_at, None)
        # dataset metadata object was created
        self.assertEqual(DatasetMetadata.objects.objects.count(), 1)
