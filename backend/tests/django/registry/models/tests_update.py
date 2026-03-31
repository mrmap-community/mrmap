
from pathlib import Path
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from MrMap.settings import BASE_DIR
from registry.enums.update import UpdateJobStatusEnum
from registry.models.metadata import ReferenceSystem, Style
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
        self.update_job.refresh_from_db()

        node1 = self.update_job.service.layers.prefetch_related(
            'keywords', 'styles', 'reference_systems', 'time_extents').get(identifier="node1")

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value,
                         "Job should be finished with status updated")

        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists(),
                         "No update candidate should exist after update")

        self.assertCountEqual(
            list(self.update_job.service.keywords.values_list(
                "keyword", flat=True)),
            ["meteorology", "climatology", "new keyword"],
            "Keywords should be updated"
        )

        self.assertCountEqual(
            list(self.update_job.service.layers.values_list(
                "title", flat=True)),
            ["node1_new", "node1.1_new", "node1.1.1_new", "node1.1.2_new", "node1.1.3_new",
                "node1.2_new", "node1.3_new", "node1.3.1_new"],
            "Layer titles should be updated"
        )

        self.assertCountEqual(
            [crs.code for crs in node1.reference_systems.all()],
            ["4326", "4325"],
            "Reference systems should be updated"
        )
        self.assertCountEqual(
            [str(extent) for extent in node1.time_extents.all()],
            ["2025-10-06 15:10:00+00:00;2025-10-20 15:10:00+00:00;0:05:00"],
            "Time extents should be updated"
        )
        self.assertCountEqual(
            [kw.keyword for kw in node1.keywords.all()],
            ["meteorology", "climatology"],
            "Layer keywords should be updated"
        )
        self.assertCountEqual(
            [style.name for style in node1.styles.all()],
            ["style node 1", "style node 1.2"],
            "Layer styles should be updated"
        )

        self.assertEqual(
            node1.abstract,
            "new abstract",
            "Layer abstract should be updated"
        )

        self.assertEqual(
            str(node1.bbox_lat_lon),
            'SRID=4326;POLYGON ((-180 -90, -180 50, 170 50, 170 -90, -180 -90))',
            "Layer bounding box should be updated"
        )

        self.assertEqual(
            node1.scale_min,
            100,
            "Layer scale min should be updated"
        )
        self.assertEqual(
            node1.scale_max,
            10000,
            "Layer scale max should be updated"
        )

        self.assertFalse(
            node1.is_queryable,
            "Layer should not be queryable"
        )
        self.assertFalse(
            node1.is_opaque,
            "Layer should not be opaque"
        )
        self.assertFalse(
            node1.is_cascaded,
            "Layer should not be cascaded"
        )
