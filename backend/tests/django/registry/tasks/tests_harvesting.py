from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase
from django.test.utils import override_settings
from MrMap.settings import BASE_DIR
from registry.enums.harvesting import LogKindEnum
from registry.models.harvest import (HarvestingJob, HarvestingLog,
                                     TemporaryMdMetadataFile)
from registry.models.metadata import DatasetMetadataRecord
from registry.models.service import CatalogueService
from registry.ows_lib.client.core import OgcClient
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
    csw_2: CatalogueService = CatalogueService.objects.get(
        pk="3df586c6-b89b-4ce5-980a-12dc3ca23df2")
    csw_3: CatalogueService = CatalogueService.objects.get(
        pk="57cf66c2-3bde-49ad-b76e-bae49da57516")

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

    csw_2.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    csw_2.save()

    cap_file = open(
        f"{BASE_DIR}/tests/django/test_data/capabilities/csw/2.0.2.xml", mode="rb")

    csw_3.xml_backup_file = SimpleUploadedFile(
        'capabilitites.xml', cap_file.read())
    csw_3.save()

    cap_file.close()


class HarvestingGetHitsTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch("django.db.transaction.on_commit", side_effect=lambda f: f())
    @patch("celery.canvas.Signature.apply_async", return_value=None)
    @patch("celery.canvas.Signature.apply", return_value=None)
    @patch("celery.canvas.chord.apply_async", return_value=None)
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_success(self, mocked_send_request, mocked_chord_apply_async, mocked_apply, mocked_apply_async, mocked_on_commit):
        call_fetch_total_records.delay(harvesting_job_id=1)
        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        self.assertEqual(harvesting_job.total_records, 447773)


class HarvestingGetRecordsTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(
        target=OgcClient,
        attribute="send_request",
        side_effect=side_effect
    )
    def test_success(self, mocked_run_checks):

        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        temporary_md_files_count: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.filter(
            job__id=1).count()
        self.assertEqual(temporary_md_files_count, 10)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_recovered_page_is_not_duplicated(self, send_request):
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        before = list(TemporaryMdMetadataFile.objects.filter(job_id=1).values_list('pk', flat=True))
        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)
        self.assertCountEqual(
            TemporaryMdMetadataFile.objects.filter(job_id=1).values_list('pk', flat=True), before)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_recovered_page_is_not_requested_again(self, send_request):
        """a page which is stored is complete, so a redelivery of it asks nothing of the remote
        service - the deduplication must be visible in the requests sent and not only in the rows
        left behind (#688)"""
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        self.assertEqual(send_request.call_count, 1)

        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)
        call_fetch_records.delay(harvesting_job_id=1, start_position=1, recovering=True)

        self.assertEqual(send_request.call_count, 1)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request", side_effect=side_effect)
    def test_page_which_is_missing_is_requested_when_recovering(self, send_request):
        """the recovery of a worker restart still downloads the pages which never arrived"""
        call_fetch_records.delay(harvesting_job_id=1, start_position=1)
        call_fetch_records.delay(harvesting_job_id=1, start_position=11, recovering=True)

        self.assertEqual(send_request.call_count, 2)
        self.assertEqual(TemporaryMdMetadataFile.objects.filter(job_id=1).count(), 20)

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    @patch.object(OgcClient, "send_request")
    def test_a_refused_page_leaves_a_trace_of_the_records_it_did_not_deliver(self, send_request):
        """a page which the catalogue refuses is not nothing: the records it should have carried
        are missing from this snapshot, and only a run which says so can be answered as an
        incomplete one (#690)"""
        def refused(request, timeout):
            response = MockResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content='<ExceptionReport><Exception exceptionCode="TooLargeBestRecords"'
                        ' exceptionText="maxRecords too large"/></ExceptionReport>')
            response.request = request
            return response
        send_request.side_effect = refused

        harvesting_job: HarvestingJob = HarvestingJob.objects.get(pk=1)
        harvesting_job.total_records = 100
        harvesting_job.save()

        call_fetch_records.delay(harvesting_job_id=1, start_position=1)

        self.assertEqual(TemporaryMdMetadataFile.objects.filter(job_id=1).count(), 0)
        short_pages = HarvestingLog.objects.filter(
            harvesting_job_id=1, kind=LogKindEnum.COUNT_MISSMATCH.value)
        self.assertEqual(short_pages.count(), 1)
        self.assertEqual(short_pages.first().description, "0<50")
        logged = short_pages.first().extented_description.read().decode("UTF-8")
        self.assertIn("Only 0 received from 50 possible records.", logged)
        self.assertIn("startPosition=1", logged)


class TemporaryMdMetadataFileToDbTaskTest(TransactionTestCase):

    fixtures = ['test_users.json', 'test_keywords.json', 'test_csw.json']

    def setUp(self):
        setup_capabilitites_file()

    @override_settings(CELERY_TASK_EAGER_PROPAGATES=True,
                       CELERY_TASK_ALWAYS_EAGER=True,
                       BROKER_BACKEND='memory')
    def test_success(self, ):

        md_file = open(
            f"{BASE_DIR}/tests/django/test_data/csw/md_metadata.xml", mode="rb")

        temporary_md_file: TemporaryMdMetadataFile = TemporaryMdMetadataFile.objects.get(
            pk="1")

        temporary_md_file.md_metadata_file = SimpleUploadedFile(
            'capabilitites.xml', md_file.read())
        temporary_md_file.save()
        md_file.close()

        harvesting_job: HarvestingJob = temporary_md_file.job

        call_md_metadata_file_to_db.delay(
            md_metadata_file_id="1")

        # temporary object was deleted
        self.assertEqual(
            TemporaryMdMetadataFile.objects.filter(job__id=2).count(), 0)
        # job is done
        self.assertFalse(harvesting_job.done_at, None)
        # dataset metadata object was created
        self.assertEqual(DatasetMetadataRecord.objects.count(), 1)
