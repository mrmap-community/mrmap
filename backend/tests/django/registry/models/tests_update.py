from pathlib import Path
from unittest.mock import patch

from celery.exceptions import Retry
from lxml import etree
from requests.exceptions import ConnectionError

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule
from MrMap.settings import BASE_DIR
from notify.enums import ProcessStatusEnum
from registry.enums.update import UpdateJobStatusEnum
from registry.models.service import FeatureType, Layer, WebFeatureService, WebMapService
from registry.models.monitoring import WebMapServiceMonitoringRun, WebMapServiceMonitoringSetting
from registry.models.update import (WebFeatureServiceUpdateJob, WebMapServiceUpdateJob,
                                    WebMapServiceUpdateSetting)
from registry.tasks.update import create_wms_update_job, run_wms_update
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

ONE_NEW_STRUCTURE_UPDATE_REMOTE_RESPONSE = MockResponse(status_code=status.HTTP_200_OK, content=Path(Path.joinpath(
    Path(__file__).parent.resolve(), '../../test_data/capabilities/wms/one_new_structure_update_fixture_1.3.0.xml')))

RENAMED_LAYER_UPDATE_REMOTE_RESPONSE = MockResponse(
    content=REMOTE_RESPONSE.text.replace("<Name>node1.3.1</Name>", "<Name>node1.3.1_renamed</Name>"),
)

WFS_REMOTE_RESPONSE = MockResponse(
    status_code=status.HTTP_200_OK,
    content=Path(Path.joinpath(Path(__file__).parent.resolve(), "../../test_data/capabilities/wfs/fixture_2.0.0.xml")),
)
WFS_SIMPLE_UPDATE_REMOTE_RESPONSE = MockResponse(
    status_code=status.HTTP_200_OK,
    content=Path(
        Path.joinpath(
            Path(__file__).parent.resolve(), "../../test_data/capabilities/wfs/simple_update_fixture_2.0.0.xml"
        )
    ),
)
WFS_ONE_NEW_FEATURETYPE_UPDATE_REMOTE_RESPONSE = MockResponse(
    status_code=status.HTTP_200_OK,
    content=Path(
        Path.joinpath(
            Path(__file__).parent.resolve(),
            "../../test_data/capabilities/wfs/one_new_featuretype_update_fixture_2.0.0.xml",
        )
    ),
)
WFS_ONE_REMOVED_FEATURETYPE_UPDATE_REMOTE_RESPONSE = MockResponse(
    status_code=status.HTTP_200_OK,
    content=Path(
        Path.joinpath(
            Path(__file__).parent.resolve(),
            "../../test_data/capabilities/wfs/one_removed_featuretype_update_fixture_2.0.0.xml",
        )
    ),
)

WFS_RENAMED_FEATURETYPE_UPDATE_REMOTE_RESPONSE = MockResponse(
    content=WFS_REMOTE_RESPONSE.text.replace("<Name>node3</Name>", "<Name>node3_renamed</Name>"),
)


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

    @patch("registry.tasks.update.run_wms_update.apply_async")
    def test_schedule_recovers_unfinished_job_after_commit(self, enqueue):
        interval = IntervalSchedule.objects.create(every=1, period="days")
        setting = WebMapServiceUpdateSetting.objects.create(
            service=self.wms, interval=interval,
        )
        with self.captureOnCommitCallbacks(execute=True):
            job_id = create_wms_update_job(name=setting.name)
            enqueue.assert_not_called()
        self.assertEqual(job_id, self.update_job.pk)
        self.assertEqual(self.wms.update_jobs.count(), 1)
        enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})

    @patch("registry.tasks.update.run_wms_update.apply_async")
    def test_schedule_creates_job_after_previous_job_finished(self, enqueue):
        self.update_job.finish()
        interval = IntervalSchedule.objects.create(every=1, period="days")
        setting = WebMapServiceUpdateSetting.objects.create(
            service=self.wms, interval=interval,
        )
        with self.captureOnCommitCallbacks(execute=True):
            job_id = create_wms_update_job(name=setting.name)
            enqueue.assert_not_called()
        self.assertNotEqual(job_id, self.update_job.pk)
        self.assertEqual(self.wms.update_jobs.count(), 2)
        enqueue.assert_called_once_with(kwargs={"update_job_id": job_id})

    @patch.object(Session, "send", side_effect=ConnectionError("unavailable"))
    def test_transient_failure_retries_without_finishing_job(self, remote):
        # Invoke directly: Celery's task signals close connections, which would
        # discard the outer transaction owned by Django's TestCase.
        with patch.object(run_wms_update, "retry", side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                run_wms_update(update_job_id=self.update_job.pk)
        retry.assert_called_once()
        self.assertIsInstance(retry.call_args.kwargs["exc"], ConnectionError)
        self.update_job.refresh_from_db()
        self.assertIsNone(self.update_job.done_at)
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value)

    @patch.object(Session, "send", return_value=RENAMED_LAYER_UPDATE_REMOTE_RESPONSE)
    @patch("registry.tasks.update.run_wms_update.apply_async")
    def test_recovered_job_preserves_pending_review(self, enqueue, remote):
        run_wms_update(update_job_id=self.update_job.pk)
        interval = IntervalSchedule.objects.create(every=1, period="days")
        setting = WebMapServiceUpdateSetting.objects.create(service=self.wms, interval=interval)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(create_wms_update_job(name=setting.name), self.update_job.pk)
        enqueue.assert_called_once_with(kwargs={"update_job_id": self.update_job.pk})
        run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertIsNone(self.update_job.done_at)
        self.assertTrue(self.update_job.mappings.filter(is_confirmed=False).exists())
        remote.assert_called_once()

    @patch.object(Session, "send", side_effect=[SIMPLE_UPDATE_REMOTE_RESPONSE, SIMPLE_UPDATE_REMOTE_RESPONSE])
    def test_interrupted_update_rolls_back_and_can_run_again(self, remote):
        with patch.object(WebMapServiceUpdateJob, "update_layers", side_effect=RuntimeError("interrupted")):
            with self.assertRaisesMessage(RuntimeError, "interrupted"):
                run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.WAITING_FOR_PROCESSING.value)
        self.assertIsNone(self.update_job.done_at)
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists())
        self.assertFalse(self.update_job.mappings.exists())

        run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertIsNotNone(self.update_job.done_at)

    @patch.object(Session, "send", side_effect=[RENAMED_LAYER_UPDATE_REMOTE_RESPONSE])
    @patch("registry.models.update.run_wms_update.apply_async")
    def test_review_completion_runs_after_commit(self, enqueue, remote):
        original_layer_id = self.wms.layers.get(identifier="node1.3.1").pk
        self.update_job.update()
        self.update_job.refresh_from_db()
        self.assertIsNone(self.update_job.done_at)

        interval = IntervalSchedule.objects.create(every=1, period="days")
        candidate_setting = WebMapServiceMonitoringSetting.objects.create(
            service=self.update_job.new_service, interval=interval,
        )
        # bulk_create avoids queuing unrelated monitoring tasks in this test.
        run = WebMapServiceMonitoringRun.objects.bulk_create([
            WebMapServiceMonitoringRun(setting=candidate_setting),
        ])[0]

        # Pending reviews must leave the candidate and mappings intact.
        run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)

        mapping = self.update_job.mappings.get(is_confirmed=False)
        self.assertIsNone(mapping.old_layer_id)
        with self.captureOnCommitCallbacks(execute=True):
            mapping.old_layer_id = original_layer_id
            mapping.is_confirmed = True
            mapping.save(update_fields=["old_layer", "is_confirmed"])
            enqueue.assert_not_called()
        enqueue.assert_called_once_with(kwargs={"update_job_id": self.update_job.pk})

        run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertIsNotNone(self.update_job.done_at)
        self.assertFalse(self.update_job.mappings.exists())
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists())
        self.assertEqual(self.wms.layers.get(identifier="node1.3.1_renamed").pk, original_layer_id)
        candidate_setting.refresh_from_db()
        self.assertEqual(candidate_setting.service_id, self.wms.pk)
        self.assertFalse(candidate_setting.enabled)
        self.assertTrue(WebMapServiceMonitoringRun.objects.filter(pk=run.pk).exists())

        # Duplicate deliveries must not try to update a deleted candidate.
        done_at = self.update_job.done_at
        run_wms_update(update_job_id=self.update_job.pk)
        self.update_job.refresh_from_db()
        self.assertEqual(self.update_job.done_at, done_at)

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
    def test_automatically_finishes_if_one_layer_is_added(self, mock):
        original_ids = dict(self.wms.layers.values_list("identifier", "pk"))
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value,
                         "An addition without removals should finish automatically")
        self.assertIsNotNone(self.update_job.done_at)
        self.update_job.background_process.refresh_from_db()
        self.assertEqual(self.update_job.background_process.status, ProcessStatusEnum.COMPLETED.value)
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists(),
                         "Update candidate should not exist after update")

        self.assertEqual(
            self.update_job.mappings.count(),
            0,
            "There should be 0 mappings after update")
        self.assertEqual(
            dict(self.wms.layers.exclude(identifier="node1.4").values_list("identifier", "pk")),
            original_ids,
        )
        added_layer = self.wms.layers.get(identifier="node1.4")
        self.assertFalse(added_layer.is_active)
        self.assertFalse(added_layer.is_searchable)
        addition_history = Layer.change_log.get(id=added_layer.pk, service_id=self.wms.pk, history_type="+")
        self.assertEqual(addition_history.history_type, "+")
        self.assertEqual(addition_history.history_change_reason, self.update_job.default_change_reason)

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

    def test_automatically_adopts_new_parent_and_child_layers(self):
        original_ids = dict(self.wms.layers.values_list("identifier", "pk"))
        response = MockResponse(content=ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text.replace(
            "<Name>node1.4</Name>",
            "<Name>node1.4</Name><Layer><Title>node1.4.1</Title><Name>node1.4.1</Name></Layer>",
        ))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertFalse(self.update_job.mappings.exists())
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists())
        parent = self.wms.layers.get(identifier="node1.4")
        child = self.wms.layers.get(identifier="node1.4.1")
        root = self.wms.layers.get(identifier="node1")
        self.assertEqual(parent.mptt_parent_id, root.pk)
        self.assertEqual(child.mptt_parent_id, parent.pk)
        self.assertEqual(parent.mptt_tree_id, root.mptt_tree_id)
        self.assertEqual(child.mptt_tree_id, root.mptt_tree_id)
        self.assertEqual((parent.mptt_lft, parent.mptt_rgt, parent.mptt_depth), (16, 19, 1))
        self.assertEqual((child.mptt_lft, child.mptt_rgt, child.mptt_depth), (17, 18, 2))
        self.assertEqual(root.mptt_rgt, 20)
        self.assertEqual(
            dict(self.wms.layers.exclude(identifier__in=["node1.4", "node1.4.1"]).values_list("identifier", "pk")),
            original_ids,
        )
        for layer in (parent, child):
            with self.subTest(identifier=layer.identifier):
                addition_history = Layer.change_log.get(id=layer.pk, service_id=self.wms.pk, history_type="+")
                self.assertEqual(addition_history.history_type, "+")
                self.assertEqual(addition_history.history_change_reason, self.update_job.default_change_reason)

    def test_addition_preserves_existing_unnamed_root(self):
        root = self.wms.layers.get(identifier="node1")
        Layer.objects.filter(pk=root.pk).update(identifier=None)
        self.wms.xml_backup_file = SimpleUploadedFile(
            "capabilities.xml", REMOTE_RESPONSE.text.replace("<Name>node1</Name>", "").encode("UTF-8"),
        )
        self.wms.save()
        response = MockResponse(content=ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text.replace("<Name>node1</Name>", ""))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertEqual(self.wms.layers.get(mptt_parent=None).pk, root.pk)
        self.assertEqual(self.wms.layers.get(identifier="node1.4").mptt_parent_id, root.pk)
        self.assertFalse(WebMapService.objects.filter(update_candidate_of=self.wms).exists())

    def test_new_unnamed_group_requires_review(self):
        response = MockResponse(content=ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text.replace("<Name>node1.4</Name>", ""))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertIsNone(self.update_job.done_at)
        mapping = self.update_job.mappings.get(is_confirmed=False)
        self.assertIsNone(mapping.old_layer_id)
        self.assertIsNone(mapping.new_layer.identifier)
        self.assertEqual(Layer.objects.filter(service=self.wms).count(), 8)

    def test_unnamed_root_is_not_matched_to_new_unnamed_child(self):
        root = self.wms.layers.get(identifier="node1")
        Layer.objects.filter(pk=root.pk).update(identifier=None)
        self.wms.xml_backup_file = SimpleUploadedFile(
            "capabilities.xml", REMOTE_RESPONSE.text.replace("<Name>node1</Name>", "").encode("UTF-8"),
        )
        self.wms.save()
        response = MockResponse(content=ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text.replace("<Name>node1.4</Name>", ""))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertFalse(self.update_job.mappings.filter(old_layer_id=root.pk).exists())
        mapping = self.update_job.mappings.get(new_layer__identifier__isnull=True)
        self.assertIsNone(mapping.old_layer_id)
        self.assertFalse(mapping.is_confirmed)

    def test_unnamed_root_is_matched_when_new_unnamed_group_requires_review(self):
        root = self.wms.layers.get(identifier="node1")
        Layer.objects.filter(pk=root.pk).update(identifier=None)
        self.wms.xml_backup_file = SimpleUploadedFile(
            "capabilities.xml", REMOTE_RESPONSE.text.replace("<Name>node1</Name>", "").encode("UTF-8"),
        )
        self.wms.save()
        response = MockResponse(content=ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text.replace(
            "<Name>node1</Name>", "",
        ).replace("<Name>node1.4</Name>", ""))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        root_mapping = self.update_job.mappings.get(new_layer__mptt_parent=None)
        self.assertEqual(root_mapping.old_layer_id, root.pk)
        self.assertTrue(root_mapping.is_confirmed)
        mapping = self.update_job.mappings.get(is_confirmed=False)
        self.assertIsNone(mapping.old_layer_id)
        self.assertIsNone(mapping.new_layer.identifier)

    def test_unnamed_group_moved_to_different_parent_requires_review(self):
        group = self.wms.layers.get(identifier="node1.1")
        Layer.objects.filter(pk=group.pk).update(identifier=None)
        namespaces = {"wms": "http://www.opengis.net/wms"}
        document = etree.fromstring(REMOTE_RESPONSE.content)
        xml_group = document.xpath("//wms:Layer[wms:Name='node1.1']", namespaces=namespaces)[0]
        xml_group.remove(xml_group.find("wms:Name", namespaces))
        self.wms.xml_backup_file = SimpleUploadedFile("capabilities.xml", etree.tostring(document))
        self.wms.save()
        new_parent = document.xpath("//wms:Layer[wms:Name='node1.3']", namespaces=namespaces)[0]
        new_parent.append(xml_group)
        response = MockResponse(content=etree.tostring(document, encoding="unicode"))
        with patch.object(Session, "send", return_value=response):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertFalse(self.update_job.mappings.filter(old_layer_id=group.pk).exists())
        mapping = self.update_job.mappings.get(is_confirmed=False)
        self.assertIsNone(mapping.old_layer_id)
        self.assertIsNone(mapping.new_layer.identifier)
        group.refresh_from_db()
        self.assertEqual(group.mptt_parent_id, self.wms.layers.get(identifier="node1").pk)

    def test_ambiguous_unnamed_groups_require_review(self):
        unnamed_ids = set(self.wms.layers.filter(identifier__in=["node1.1", "node1.3"]).values_list("pk", flat=True))
        Layer.objects.filter(pk__in=unnamed_ids).update(identifier=None)
        old_document = REMOTE_RESPONSE.text
        new_document = ONE_NEW_LAYER_UPDATE_REMOTE_RESPONSE.text
        for identifier in ("node1.1", "node1.3"):
            old_document = old_document.replace(f"<Name>{identifier}</Name>", "")
            new_document = new_document.replace(f"<Name>{identifier}</Name>", "")
        self.wms.xml_backup_file = SimpleUploadedFile("capabilities.xml", old_document.encode("UTF-8"))
        self.wms.save()
        with patch.object(Session, "send", return_value=MockResponse(content=new_document)):
            self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertIsNone(self.update_job.done_at)
        self.assertEqual(self.update_job.mappings.filter(
            new_layer__identifier__isnull=True, old_layer__isnull=True, is_confirmed=False,
        ).count(), 2)
        self.assertEqual(set(self.wms.layers.filter(identifier=None).values_list("pk", flat=True)), unnamed_ids)
        self.assertFalse(self.wms.layers.filter(identifier="node1.4").exists())

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[ONE_REMOVED_LAYER_UPDATE_REMOTE_RESPONSE],
    )
    def test_interupt_if_one_layer_where_removed(self, mock):
        removed_layer_id = self.wms.layers.get(identifier="node1.3.1").pk

        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertFalse(Layer.objects.filter(pk=removed_layer_id).exists())
        deletion_history = Layer.change_log.get(
            id=removed_layer_id, history_type="-")
        self.assertEqual(
            deletion_history.history_change_reason,
            self.update_job.default_change_reason,
        )

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value,
                         "Job should be finished with status updated after confirming all layer mappings")

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
                ('node1', 1, 14, 0, 1),
                ('node1.1', 2, 9, 1, 1),
                ('node1.1.1', 3, 4, 2, 1),
                ('node1.1.2', 5, 6, 2, 1),
                ('node1.1.3', 7, 8, 2, 1),
                ('node1.2', 10, 11, 1, 1),
                ('node1.3', 12, 13, 1, 1),
            ],
            "MPTT Tree structure should be correct after update"
        )

    @patch.object(
        target=Session,
        attribute="send",
        side_effect=[ONE_NEW_STRUCTURE_UPDATE_REMOTE_RESPONSE],
    )
    def test_new_structure_update_processing(self, mock):
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

        """
        node1       -> node1
        node1.1     ->
                    -> node1.1_new
        node1.1.1   -> node1.1.1
        node1.1.2   ->
        node1.1.3   ->
        node1.2     -> node1.2
        node1.3     -> node1.3
        node1.3.1   -> node1.3.1
                    -> node1.3.1.1
        """
        self.assertEqual(
            self.update_job.mappings.count(),
            7,
            "There should be 7 mappings")
        self.update_job.mappings.filter(new_layer__identifier="node1.1_new").update(
            old_layer=Layer.objects.get(service=self.update_job.service, identifier="node1.1"))

        self.update_job.mappings.update(is_confirmed=True)

        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status,
                         UpdateJobStatusEnum.UPDATED.value,
                         "Job should be finished with status updated after confirming all layer mappings")

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
                ('node1', 1, 14, 0, 1),
                ('node1.1_new', 2, 5, 1, 1),
                ('node1.1.1', 3, 4, 2, 1),
                ('node1.2', 6, 7, 1, 1),
                ('node1.3', 8, 13, 1, 1),
                ('node1.3.1', 9, 12, 2, 1),
                ('node1.3.1.1', 10, 11, 3, 1)
            ],
            "MPTT Tree structure should be correct after update"
        )


class WfsUpdateJobTest(TestCase):
    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json", "test_wfs.json"]

    def setUpWfs(self):
        self.wfs = WebFeatureService.objects.get(pk="9cc4889d-0cd4-4c3b-8975-58de6d30db41")
        with open(f"{BASE_DIR}/tests/django/test_data/capabilities/wfs/fixture_2.0.0.xml", mode="rb") as cap_file:
            self.wfs.xml_backup_file = SimpleUploadedFile("capabilitites.xml", cap_file.read())
        self.wfs.save()

    def setUp(self):
        self.setUpWfs()

        self.update_job = WebFeatureServiceUpdateJob.objects.create(service=self.wfs)

    def test_unique_constraint(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                WebFeatureServiceUpdateJob.objects.create(service=self.wfs)

    @patch.object(target=Session, attribute="send", side_effect=[WFS_REMOTE_RESPONSE])
    def test_finish_if_document_equals(self, mock):
        self.update_job.update()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.NO_UPDATE_NEEDED.value)

    @patch.object(target=Session, attribute="send", side_effect=[WFS_SIMPLE_UPDATE_REMOTE_RESPONSE])
    def test_finish_if_document_not_equals_but_simple_changes(self, mock):
        self.update_job.update()
        self.update_job.refresh_from_db()

        featuretype_node3: FeatureType = self.update_job.service.featuretypes.get(identifier="node3")

        self.assertEqual(
            self.update_job.status, UpdateJobStatusEnum.UPDATED.value, "Job should be finished with status updated"
        )

        self.assertFalse(
            WebFeatureService.objects.filter(update_candidate_of=self.wfs).exists(),
            "No update candidate should exist after update",
        )

        self.assertEqual(self.update_job.service.title, "DWD GeoServer WFS Neu", "Service title should be updated")

        self.assertCountEqual(
            list(self.update_job.service.keywords.values_list("keyword", flat=True)),
            ["meteorology", "climatology", "new keyword"],
            "Keywords should be updated",
        )

        self.assertEqual(
            featuretype_node3.title, "2m Temperatur an RBSN Stationen Neu", "Feature type title should be updated"
        )
        self.assertEqual(featuretype_node3.abstract, "new abstract", "Feature type abstract should be updated")

        self.assertCountEqual(
            list(featuretype_node3.keywords.values_list("keyword", flat=True)),
            ["Beobachtungssystem", "Geographischer Ort", "Lufttemperatur", "Meteorologie", "SYNOP"],
            "Keywords should be updated",
        )

        self.assertEqual(
            featuretype_node3.default_reference_system.code, "4326", "Default reference system should be updated"
        )
        self.assertCountEqual(
            featuretype_node3.reference_systems.values_list("code", flat=True),
            ["25832", "25833"],
            "Reference systems should be updated",
        )

        self.assertEqual(
            str(featuretype_node3.bbox_lat_lon),
            "SRID=4326;POLYGON ((7.02439799999999 14.950565, 7.02439799999999 54.010987, 47.398578 54.010987, 47.398578 14.950565, 7.02439799999999 14.950565))",
            "FeatureType bounding box should be updated",
        )

    @patch.object(target=Session, attribute="send", side_effect=[WFS_SIMPLE_UPDATE_REMOTE_RESPONSE])
    def test_update_applies_configured_metadata_but_not_advertised_operation_urls(self, mock):
        service = self.update_job.service
        urls_before = list(service.operation_urls.values_list("url", flat=True))
        self.update_job.update()
        self.update_job.refresh_from_db()
        service.refresh_from_db()
        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertEqual(service.title, "DWD GeoServer WFS Neu", "Configured metadata is applied")
        self.assertCountEqual(
            list(service.operation_urls.values_list("url", flat=True)), urls_before,
            "The update copies only the configured fields; advertised operation urls and their stored "
            "output formats remain as registered until the service is re-registered",
        )
        # The update candidate which carries the freshly advertised AllowedValues
        # formats is created and removed again within the same run.
        self.assertFalse(WebFeatureService.objects.filter(update_candidate_of=service).exists())

    @patch.object(target=Session, attribute="send", side_effect=[WFS_ONE_NEW_FEATURETYPE_UPDATE_REMOTE_RESPONSE])
    def test_automatically_finishes_if_one_featuretype_is_added(self, mock):
        original_ids = dict(self.wfs.featuretypes.values_list("identifier", "pk"))
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(
            self.update_job.status,
            UpdateJobStatusEnum.UPDATED.value,
            "An addition without removals should finish automatically",
        )
        self.assertIsNotNone(self.update_job.done_at)
        self.update_job.background_process.refresh_from_db()
        self.assertEqual(self.update_job.background_process.status, ProcessStatusEnum.COMPLETED.value)
        self.assertFalse(
            WebFeatureService.objects.filter(update_candidate_of=self.wfs).exists(),
            "Update candidate should not exist after update",
        )

        self.assertEqual(self.update_job.mappings.count(), 0, "There should be 0 mappings after update")
        self.assertEqual(self.wfs.featuretypes.count(), 5)
        self.assertEqual(
            dict(self.wfs.featuretypes.exclude(identifier="node+").values_list("identifier", "pk")),
            original_ids,
        )
        added_featuretype = self.wfs.featuretypes.get(identifier="node+")
        self.assertFalse(added_featuretype.is_active)
        self.assertFalse(added_featuretype.is_searchable)
        addition_history = FeatureType.change_log.get(id=added_featuretype.pk, service_id=self.wfs.pk, history_type="+")
        self.assertEqual(addition_history.history_type, "+")
        self.assertEqual(addition_history.history_change_reason, self.update_job.default_change_reason)

    @patch.object(Session, "send", return_value=WFS_RENAMED_FEATURETYPE_UPDATE_REMOTE_RESPONSE)
    def test_rename_requires_review_and_preserves_uuid_after_confirmation(self, remote):
        original_ids = dict(self.wfs.featuretypes.values_list("identifier", "pk"))
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.REVIEW_REQUIRED.value)
        self.assertIsNone(self.update_job.done_at)
        self.assertTrue(WebFeatureService.objects.filter(update_candidate_of=self.wfs).exists())
        self.assertEqual(dict(self.wfs.featuretypes.values_list("identifier", "pk")), original_ids)
        mapping = self.update_job.mappings.get(is_confirmed=False)
        self.assertEqual(mapping.new_featuretype.identifier, "node3_renamed")
        self.assertIsNone(mapping.old_featuretype_id)

        with patch("registry.models.update.run_wfs_update.apply_async") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                mapping.old_featuretype_id = original_ids["node3"]
                mapping.is_confirmed = True
                mapping.save(update_fields=["old_featuretype", "is_confirmed"])
                enqueue.assert_not_called()
            enqueue.assert_called_once_with(kwargs={"update_job_id": self.update_job.pk})
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertEqual(self.update_job.status, UpdateJobStatusEnum.UPDATED.value)
        self.assertIsNotNone(self.update_job.done_at)
        self.assertFalse(self.update_job.mappings.exists())
        self.assertFalse(WebFeatureService.objects.filter(update_candidate_of=self.wfs).exists())
        self.assertEqual(self.wfs.featuretypes.get(identifier="node3_renamed").pk, original_ids.pop("node3"))
        self.assertEqual(
            dict(self.wfs.featuretypes.exclude(identifier="node3_renamed").values_list("identifier", "pk")),
            original_ids,
        )
        remote.assert_called_once()

    @patch.object(target=Session, attribute="send", side_effect=[WFS_ONE_REMOVED_FEATURETYPE_UPDATE_REMOTE_RESPONSE])
    def test_interupt_if_one_featuretype_is_removed(self, mock):
        removed_featuretype_id = self.wfs.featuretypes.get(identifier="node2").pk
        self.update_job.update()
        self.update_job.refresh_from_db()

        self.assertFalse(FeatureType.objects.filter(pk=removed_featuretype_id).exists())
        deletion_history = FeatureType.change_log.get(id=removed_featuretype_id, history_type="-")
        self.assertEqual(deletion_history.history_change_reason, self.update_job.default_change_reason)
        self.assertEqual(
            self.update_job.status,
            UpdateJobStatusEnum.UPDATED.value,
            "Job should be finished with status updated after confirming all featuretype mappings",
        )
        self.assertFalse(
            WebFeatureService.objects.filter(update_candidate_of=self.wfs).exists(),
            "Update candidate should not exist after update",
        )
        self.assertEqual(self.update_job.mappings.count(), 0, "There should be 0 mappings after update")
        self.assertEqual(
            self.update_job.service.featuretypes.count(),
            3,
            "There should be 3 featuretypes in the new service after removing one",
        )
