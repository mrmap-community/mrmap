from pathlib import Path
from unittest.mock import mock_open, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test.utils import override_settings
from MrMap.settings import BASE_DIR
from registry.models.harvest import HarvestingJob, TemporaryMdMetadataFile
from registry.models.metadata import DatasetMetadata
from registry.models.service import CatalogueService
from registry.tasks.harvest import (call_fetch_records,
                                    call_fetch_total_records,
                                    call_md_metadata_file_to_db)
from rest_framework import status
from tests.django.utils import MockResponse


def side_effect(request, timeout):
    if "GetRecords" in request.url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/get_records.xml')))
    elif "hits" in request.url:
        return MockResponse(
            status_code=status.HTTP_200_OK,
            content=Path(Path.joinpath(Path(__file__).parent.resolve(),
                                       '../../test_data/csw/hits.xml')))


def setup_capabilitites_file():
    csw: CatalogueService = CatalogueService.objects.get(
        pk="3df586c6-b89b-4ce5-980a-12dc3ca23df2")

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

    csw.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    csw.save()


class HarvestingGetHitsTaskTest(TestCase):

    fixtures = ['test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("ows_lib.client.mixins.OgcClient.send_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        call_fetch_total_records.delay(harvesting_job_id=1)
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.total_records, 447773)


class HarvestingGetRecordsTaskTest(TestCase):

    fixtures = ['test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("ows_lib.client.mixins.OgcClient.send_request", side_effect=side_effect)
    def test_success(self, mocked_run_checks):
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        temporary_md_files_count: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.filter(
            job__id=1).count()
        self.assertEqual(temporary_md_files_count, 10)


class TemporaryMdMetadataFileToDbTaskTest(TestCase):

    fixtures = ['test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_EAGER_PROPAGATES_EXCEPTIONS=True,
                       CELERY_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("os.path.isfile", return_value=True)
    @patch("django.db.models.fields.files.FieldFile.path", return_value="")
    def test_success(self, mocked_is_file, mocked_path):

        md_metadata_file = Path(Path.joinpath(Path(__file__).parent.resolve(),
                                              '../../test_data/csw/md_metadata.xml'))

        in_file = open(md_metadata_file, "rb")
        content: bytes = in_file.read()
        in_file.close()

        str_content = content.decode("UTF-8")

        with patch("django.db.models.fields.files.FieldFile.open", mock_open(read_data=str_content)):
            temporary_md_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
                pk="1")
            harvesting_job: HarvestingJob = temporary_md_file.job

            call_md_metadata_file_to_db.delay(
                md_metadata_file_id="1")

            # temporary object was deleted
            self.assertEqual(
                TemporaryMdMetadataFile.objects.filter(job__id=2).count(), 0)
            # job is done
            self.assertFalse(harvesting_job.done_at, None)
            # dataset metadata object was created
            self.assertEqual(DatasetMetadata.objects.count(), 1)
