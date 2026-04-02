
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

ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE = MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(
    Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/one_new_layer_update_fixture_1.3.0.xml')))

ONE_REMOVED_LAYER_UPDATE_REMOTE_RESPONSE = MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(
    Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/one_removed_layer_update_fixture_1.3.0.xml')))


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
    def test_finish_if_document_not_equals_but_simple_changes(self, mock):
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

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE],
    )
    def test_interupt_if_one_layer_where_added(self, mock):
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.REVIEW_REQUIRED.value,
                         "Job should be interrupted with status review required")

        self.assertTrue(WebMapService.objects.filter(update_candidate_of=self.wms).exists(),
                        "Update candidate should exist after update")

        self.assertEqual(
            self.update_job.new_service.layers.count(),
            9,
            "There should be 9 layers in the new service")
        self.assertEqual(
            self.update_job.mappings.count(),
            9,
            "There should be 9 mappings")

        self.update_job.mappings.update(is_confirmed=True)
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value,
                         "Job should be finished with status updated after confirming the new layer")
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists(),
                         "Update candidate should not exist after update")

        self.assertEqual(
            self.update_job.mappings.count(),
            0,
            "There should be 0 mappings after update")

        self.assertListEqual(
            list(self.update_job.service.layers.values_list(
                "identifier", "mptt_lft", "mptt_rgt", "mptt_depth", "mptt_tree_id")),
            [
                ('node1', 1, 18, 0, 1),
                ('node1.1', 2, 9, 1, 1),
                ('node1.1.1', 3, 4, 2, 1),
                ('node1.1.2', 5, 6, 2, 1),
                ('node1.1.3', 7, 8, 2, 1),
                ('node1.2', 10, 11, 1, 1),
                ('node1.3', 12, 15, 1, 1),
                ('node1.3.1', 13, 14, 2, 1),
                ('node1.4', 16, 17, 1, 1)
            ],
            "MPTT Tree structure should be correct after update"
        )

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[ONE_REMOVED_LAYER_UPDATE_REMOTE_RESPONSE],
    )
    def test_interupt_if_one_layer_where_removed(self, mock):
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.REVIEW_REQUIRED.value,
                         "Job should be interrupted with status review required")

        self.assertTrue(WebMapService.objects.filter(update_candidate_of=self.wms).exists(),
                        "Update candidate should exist after update")

        self.assertEqual(
            self.update_job.new_service.layers.count(),
            7,
            "There should be 7 layers in the new service")
        self.assertEqual(
            self.update_job.mappings.count(),
            7,
            "There should be 7 mappings")

        # TODO: add correct mappings with confirmed flag and run update again
