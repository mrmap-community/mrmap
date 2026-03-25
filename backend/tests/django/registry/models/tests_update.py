
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from MrMap.settings import BASE_DIR
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import WebMapService
from registry.models.update import WebMapServiceUpdateJob
from requests.sessions import Session
from rest_framework import status
from tests.django.utils import MockResponse

REMOTE_RESPONSE = MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(
    Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/fixture_1.3.0.xml')))

SIMPLE_UPDATE_REMOTE_RESPONSE = MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(
    Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/simple_update_fixture_1.3.0.xml')))


class AllowedWebMapServiceOperationModelTest(TestCase):

    fixtures = ['test_users.json', 'test_keywords.json', "test_wms.json"]

    def setUpWms(self):
        self.wms: WebMapService = WebMapService.objects.prefetch_whole_service(
        ).get(
            pk="cd16cc1f-3abb-4625-bb96-fbe80dbe23e3")
        cap_file = open(
            f"{BASE_DIR}/tests/django/test_data/capabilities/wms/fixture_1.3.0.xml", mode="rb")

        self.wms.xml_backup_file = SimpleUploadedFile(
            'capabilitites.xml', cap_file.read())
        self.wms.save()

        cap_file.close()

    def setUp(self):
        self.setUpWms()

        self.update_job = WebMapServiceUpdateJob.objects.create(
            service=self.wms)

    def test_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WebMapServiceUpdateJob.objects.create(
                    service=self.wms)

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[REMOTE_RESPONSE],
    )
    def test_finish_if_document_equals(self, mock):
        self.update_job.update()
        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[SIMPLE_UPDATE_REMOTE_RESPONSE],
    )
    def test_finish_if_document_equals(self, mock):
        self.update_job.update()
        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value)
        self.assertCountEqual(
            list(self.update_job.service.keywords.values_list(
                "keyword", flat=True)),
            ["meteorology", "climatology", "new keyword"]
        )
