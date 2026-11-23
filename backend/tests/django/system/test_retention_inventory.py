"""The read-only persistent-data inventory of #1498.

Two halves, tested separately because they fail differently.

The **declarations** (``system/retention_datasets.py``) are content a reviewer
agrees with, so their tests are integrity checks: every declared model and field
must resolve, every retention setting name must exist somewhere the code reads
it, every dataset must state an owner, a lifecycle and a policy answer, and every
dataset proposed for a policy must either be gated or state what a test has to
show. A declaration which silently rots — a renamed model, a renamed field — is
the failure these pin, because an inventory pointing at a table that no longer
exists answers "nothing" where the truth is "I do not know".

The **measurements** (``system/retention_inventory.py``) run against the real
database and the real filesystem, because an unknown-that-looks-like-a-zero is
precisely the bug this module exists not to have. The tests assert that a window
without rows is a *reason* and not a zero, that a table the planner never
analysed answers as an estimate rather than as zero rows, that a bounded walk
says it stopped, that a path trying to leave the storage root is reported instead
of opened, and — outside the ``TestCase`` transaction, in ``ReadOnlyEnforcement-
Tests`` — that the report's own transaction really does refuse a write.
"""

import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.core.files.storage import FileSystemStorage
from django.core.management import CommandError, call_command
from django.db import connection
from django.db import utils as db_utils
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from notify.models import BackgroundProcess, BackgroundProcessLog
from system import retention_inventory as inventory
from system.models import CeleryTaskAttempt
from system.retention_datasets import (CLASSIFICATIONS, DATASETS,
                                       DECLARATION_VERSION, GROWTH_TYPES,
                                       POLICY_CANDIDATES,
                                       RETENTION_SETTING_NAMES, STORAGE_SOURCES,
                                       dataset_for, dataset_for_model,
                                       datasets_for_policy, gated_datasets,
                                       growing_datasets)

#: the source the filesystem tests drive: a FileField whose upload_to a test can
#: satisfy, so a real reference and a real file are cheap to create
LOG_SOURCE = next(source for source in STORAGE_SOURCES
                  if source.id == "background_process_attachments")
#: the source whose reference set spans several tables, for the union test
XML_SOURCE = next(source for source in STORAGE_SOURCES
                  if source.id == "xml_backup_documents")


def attempt(**overrides):
    """One attempt row of #1330; its required fields are all text or a stamp."""
    fields = {"task_id": f"task-{os.urandom(4).hex()}",
              "task_name": "registry.tasks.harvest.create_harvesting_job",
              "started_at": timezone.now()}
    fields.update(overrides)
    return CeleryTaskAttempt.objects.create(**fields)


def process_log(name, body=b"<xml/>"):
    """A ``BackgroundProcessLog`` whose FileField names ``name``, file included.

    The name is given rather than generated because the test asserts on the
    storage layout: the declared prefix must be the layout the ``upload_to``
    produces, and this is where that is pinned.
    """
    process = BackgroundProcess.objects.create(
        phase="done", process_type="harvesting", description="inventory test")
    log = BackgroundProcessLog.objects.create(
        background_process=process, log_type="info", extented_description=name)
    root = inventory._storage_location(
        BackgroundProcessLog._meta.get_field(
            "extented_description").storage)
    target = os.path.join(root, name)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(body)
    return log


def _source_fields(source):
    """The (model, field) pairs one storage source declares."""
    pairs = []
    for app_label, model_name, field_name in (
            ((source.app_label, source.model_name, source.field_name),)
            + tuple(source.reference_fields)):
        for model in inventory.concrete_descendants(
                inventory.model_class(app_label, model_name)):
            pairs.append((model, field_name))
    return pairs


def redirect_storages(sources, location):
    """Point every FileField of ``sources`` at ``location``; return the undo."""
    saved = {}
    for source in sources:
        for model, field_name in _source_fields(source):
            field = model._meta.get_field(field_name)
            saved.setdefault((model, field_name), field.storage)
            field.storage = FileSystemStorage(location=location)
    return saved


def restore_storages(saved):
    for (model, field_name), storage in saved.items():
        model._meta.get_field(field_name).storage = storage


class DeclarationIntegrityTests(SimpleTestCase):
    """The declarations resolve, or the inventory is lying."""

    def test_every_declared_model_resolves(self):
        for dataset in DATASETS:
            with self.subTest(dataset=dataset.id):
                for label in dataset.model_names:
                    inventory.model_class(*label.split(".", 1))

    def test_every_dataset_names_at_least_one_table(self):
        """A dataset which measures nothing would report a false zero."""
        for dataset in DATASETS:
            with self.subTest(dataset=dataset.id):
                self.assertTrue(inventory.dataset_tables(dataset), dataset.id)

    def test_a_family_is_measured_over_every_table_of_its_chain(self):
        """MTI spreads one row over base and subclass tables."""
        probes = dataset_for("probe_result")
        self.assertGreater(len(inventory.dataset_tables(probes)), 1,
                           "a probe row lives in the base and in the kind "
                           "table; one of them is not the whole footprint")
        for dataset in DATASETS:
            with self.subTest(dataset=dataset.id):
                growth = inventory.table_of_field(dataset, dataset.time_field)
                if dataset.time_field:
                    self.assertIn(
                        growth, inventory.dataset_tables(dataset),
                        f"{dataset.id} declares {dataset.time_field}, which "
                        f"no table of the dataset physically holds")

    def test_every_storage_source_names_a_real_file_field(self):
        for source in STORAGE_SOURCES:
            with self.subTest(source=source.id):
                fields = ((source.app_label, source.model_name,
                           source.field_name),) + tuple(
                               source.reference_fields)
                for app_label, model_name, field_name in fields:
                    model = inventory.model_class(app_label, model_name)
                    for concrete in inventory.concrete_descendants(model):
                        try:
                            field = concrete._meta.get_field(field_name)
                        except FieldDoesNotExist as error:
                            self.fail(f"{source.id}: {error}")
                    self.assertIn(
                        field.get_internal_type(), ("FileField", "ImageField"),
                        f"{source.id}: {app_label}.{model_name}.{field_name} "
                        f"is not a file field")

    def test_a_shared_prefix_declares_every_table_that_writes_into_it(self):
        """The xml tree holds record backups *and* capability documents."""
        referencing = {f"{app}.{model}.{field}"
                       for app, model, field in XML_SOURCE.reference_fields}
        self.assertIn("registry.DatasetMetadataRecord.xml_backup_file",
                      referencing)
        self.assertIn("registry.WebMapService.xml_backup_file", referencing)
        self.assertGreater(len(referencing), 5)

    def test_every_source_prefix_is_a_relative_subtree(self):
        for source in STORAGE_SOURCES:
            with self.subTest(source=source.id):
                self.assertFalse(os.path.isabs(source.prefix))
                self.assertNotIn("..", source.prefix.split("/"))

    def test_nested_prefixes_are_declared_as_their_own_source(self):
        """The registration tree lives below the harvest tree (#1263)."""
        self.assertEqual(["temporary_md_metadata_file/registration"],
                         inventory._nested_prefixes(
                             "temporary_md_metadata_file"))

    def test_every_dataset_is_fully_attributed(self):
        """#1498's acceptance: owner, lifecycle, policy candidate, holds."""
        for dataset in DATASETS:
            with self.subTest(dataset=dataset.id):
                self.assertTrue(dataset.owner, dataset.id)
                self.assertTrue(dataset.lifecycle, dataset.id)
                self.assertIn(dataset.classification, CLASSIFICATIONS)
                self.assertIn(dataset.growth, GROWTH_TYPES)
                self.assertIn(dataset.policy_candidate, POLICY_CANDIDATES)
                if dataset.policy_candidate == "none":
                    continue
                self.assertTrue(
                    dataset.test_expectations,
                    f"{dataset.id} proposes a policy without stating what a "
                    f"test must show")
                self.assertTrue(
                    dataset.protected_dependencies,
                    f"{dataset.id} proposes a policy without naming what "
                    f"holds it back")
                self.assertTrue(
                    dataset.decision_gate or dataset.time_field,
                    f"{dataset.id} proposes a policy with no time field and "
                    f"no gate, so nothing could ever be selected")

    def test_ids_are_unique(self):
        ids = [dataset.id for dataset in DATASETS]
        self.assertEqual(len(ids), len(set(ids)))
        source_ids = [source.id for source in STORAGE_SOURCES]
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_every_retention_setting_exists_somewhere_the_code_reads_it(self):
        """A renamed knob must fail here, not default to "keep forever"."""
        self.assertEqual(
            [], [name for name in RETENTION_SETTING_NAMES
                 if inventory.setting_value(name)[1] is None])

    def test_accessors_separate_policy_from_no_policy(self):
        self.assertTrue(all(dataset.policy_candidate != "none"
                            for dataset in datasets_for_policy()))
        self.assertTrue(all(dataset.decision_gate
                            for dataset in gated_datasets()))
        self.assertTrue(gated_datasets(),
                        "the inventory is meant to carry open decisions")
        self.assertTrue(growing_datasets())
        self.assertIsNone(dataset_for("no-such-dataset"))
        self.assertIsNotNone(dataset_for("harvesting_job"))
        self.assertTrue(dataset_for_model("registry", "HarvestingJob"))
        self.assertEqual((), dataset_for_model("registry", "NoSuchModel"))

    def test_a_family_declaration_covers_its_concrete_subclasses(self):
        """A base table alone would read as "this dataset holds nothing"."""
        monitoring = dataset_for("monitoring_run")
        self.assertGreater(len(monitoring.model_names), 1)
        self.assertTrue(
            dataset_for_model("registry", "WebMapServiceMonitoringRun"))
        # the rows are in the subclasses, the stamps are on the base, so both
        # are part of the footprint and the growth is asked of the base
        tables = inventory.dataset_tables(monitoring)
        self.assertIn(inventory.db_table("registry", "WebMapServiceMonitoringRun"), tables)
        self.assertEqual(tables[0],
                         inventory.table_of_field(monitoring,
                                                  monitoring.time_field))

    def test_declaration_version_is_a_number(self):
        self.assertIsInstance(DECLARATION_VERSION, int)
        self.assertGreaterEqual(DECLARATION_VERSION, 1)


class AnswerShapeTests(SimpleTestCase):
    """``measured`` and ``unavailable`` are the whole honesty of the report."""

    def test_measured_answer(self):
        self.assertEqual({"measured": True, "value": 12, "reason": None,
                          "how": "count"},
                         inventory.measured(12, how="count"))

    def test_unavailable_answer_is_never_a_zero(self):
        answer = inventory.unavailable(inventory.REASON_NOT_POSTGRESQL)
        self.assertFalse(answer["measured"])
        self.assertIsNone(answer["value"])
        self.assertEqual(inventory.REASON_NOT_POSTGRESQL, answer["reason"])

    def test_report_renders_an_unmeasured_value_as_a_dash_not_a_zero(self):
        self.assertEqual("—", inventory._from(inventory.unavailable("why")))
        self.assertEqual("—", inventory._count({"measured": True,
                                                "value": None}))
        self.assertEqual("1.5KiB", inventory._bytes(1536))

    def test_redact_keeps_the_shape_and_drops_the_credential(self):
        self.assertEqual("redis://***@broker:6379/1",
                         inventory._redact("redis://user:pw@broker:6379/1"))
        self.assertEqual("redis://broker:6379/1",
                         inventory._redact("redis://broker:6379/1"))
        self.assertIsNone(inventory._redact(None))

    def test_provenance_names_what_cannot_be_measured(self):
        """A reader must see the edges of the report, or a gap reads as a zero."""
        provenance = inventory._provenance(True)
        self.assertEqual(
            {"heap_index_toast_split", "broker_and_result_backend_bytes",
             "per_table_wal", "media_on_object_storage",
             "deleted_space_reclaim"},
            set(provenance["not_measured"]))
        self.assertTrue(provenance["read_only_enforced"])


class PathSafetyTests(SimpleTestCase):
    """The walk reads names, never bodies — and never outside the root."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_is_within_accepts_only_resolved_children(self):
        self.assertTrue(inventory._is_within(self.root, self.root))
        self.assertTrue(inventory._is_within(
            self.root, os.path.join(self.root, "a", "b.xml")))
        self.assertFalse(inventory._is_within(
            self.root, os.path.join(self.root, "..", "etc", "passwd")))
        self.assertFalse(inventory._is_within(self.root, "/etc/passwd"))
        link = os.path.join(self.root, "link")
        os.symlink("/etc", link)
        self.assertFalse(inventory._is_within(self.root, link))

    def test_walk_does_not_follow_symlinks(self):
        outside = tempfile.mkdtemp()
        try:
            with open(os.path.join(outside, "big.xml"), "wb") as handle:
                handle.write(b"x" * 4096)
            prefix = os.path.join(self.root, "prefix")
            os.makedirs(prefix)
            with open(os.path.join(prefix, "own.xml"), "wb") as handle:
                handle.write(b"y" * 10)
            os.symlink(outside, os.path.join(prefix, "escape"))
            total, files, entries, truncated = inventory._walk(
                self.root, "prefix", [1000])
            self.assertEqual(10, total)
            self.assertEqual(1, files)
            self.assertFalse(truncated)
            self.assertEqual(["prefix/own.xml"], [name for name, _ in entries])
        finally:
            shutil.rmtree(outside, ignore_errors=True)

    def test_walk_reports_budget_exhaustion_instead_of_a_short_answer(self):
        prefix = os.path.join(self.root, "prefix")
        os.makedirs(prefix)
        for index in range(30):
            with open(os.path.join(prefix, f"r{index}.xml"), "wb") as handle:
                handle.write(b"z" * 100)
        total, files, _, truncated = inventory._walk(self.root, "prefix", [5])
        self.assertTrue(truncated,
                        "a walk which stopped must not look complete")
        self.assertLessEqual(files, 5)
        self.assertLess(total, 3000)

    def test_size_below_never_leaves_the_root(self):
        self.assertIsNone(inventory._size_below(self.root, "../etc/passwd"))
        self.assertIsNone(inventory._size_below(self.root, "absent.xml"))


class CacheAndDiskTests(SimpleTestCase):

    def test_cache_facts_reports_the_configured_bound(self):
        facts = inventory.cache_facts()
        self.assertIn("default", facts["caches"])
        self.assertIsNotNone(facts["celery_result_expires_seconds"])
        self.assertNotIn("pw", str(facts["celery_broker_url"] or ""))

    def test_disk_facts_of_a_missing_directory_says_the_directory_is_absent(
            self):
        """No log dir yet is not "no space problem" — it is the filesystem below."""
        with self.settings(LOG_DIR="/nonexistent/mrmap/logs"):
            facts = inventory.disk_facts()
        log_dir = facts["log_dir"]
        self.assertTrue(log_dir["measured"],
                        "the filesystem the logs would land on is answerable")
        self.assertFalse(log_dir["exists"],
                         "and the answer says the directory is not there")

    def test_settings_facts_report_the_source_and_never_a_default(self):
        facts = inventory.retention_settings()
        self.assertEqual(set(RETENTION_SETTING_NAMES), set(facts))
        for name, entry in facts.items():
            self.assertTrue(entry["declared"], name)
            self.assertIsNotNone(entry["value"], name)
        self.assertEqual("settings", facts["RESPONSE_CACHE_TIME"]["source"])
        self.assertEqual(
            "registry.settings",
            facts["REGISTRATION_ORPHAN_FILE_GRACE_SECONDS"]["source"],
            "the storage knobs live in the app module too; reporting only "
            "django.conf.settings would call them absent")

    def test_an_absent_setting_is_reported_as_absent(self):
        value, source = inventory.setting_value("NO_SUCH_RETENTION_KNOB")
        self.assertIsNone(value)
        self.assertIsNone(source)


class LogDirectoryTests(SimpleTestCase):
    """The deployment's own writes: bounded by a sweep, unreferenced by design."""

    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_missing_directory_reports_absent(self):
        with self.settings(LOG_DIR="/nonexistent/mrmap/logs"):
            answer = inventory.measure_log_directory()
        self.assertEqual(inventory.REASON_DIRECTORY_ABSENT,
                         answer["total_bytes"]["reason"])
        self.assertIsNone(answer["total_bytes"]["value"])

    def test_dumps_count_as_unreferenced_from_the_databases_point_of_view(self):
        dumps = os.path.join(self.root, inventory.SLOW_REQUEST_DUMP_SUBDIR)
        os.makedirs(dumps)
        with open(os.path.join(dumps, "slow-1.log"), "wb") as handle:
            handle.write(b"s" * 1234)
        with self.settings(LOG_DIR=self.root):
            answer = inventory.measure_log_directory()
        self.assertEqual(1234, answer["total_bytes"]["value"])
        self.assertEqual(1, answer["files"]["value"])
        self.assertEqual(0, answer["referenced_bytes"]["value"])
        # unreferenced is a statement about the reference set, and the answer
        # says who owns this tree (#1508 migrates the sweep, does not duplicate)
        self.assertIn("sweep", answer["unreferenced_bytes"]["detail"])

    def test_no_media_leaves_every_source_unrequested(self):
        media = inventory.measure_media(include_media=False)
        for source in media["sources"]:
            self.assertEqual(inventory.REASON_NOT_REQUESTED,
                             source["total_bytes"]["reason"])
        self.assertFalse(media["total_bytes"]["measured"])


@mock.patch.object(inventory, "is_postgresql", lambda: False)
class NonPostgresTests(SimpleTestCase):
    """The report must still be produced, with every gap named."""

    def test_table_measurements_answer_the_engine_reason(self):
        answers = inventory.measure_tables(["registry_harvestingjob"])
        answer = answers["registry_harvestingjob"]
        self.assertEqual(inventory.REASON_NOT_POSTGRESQL,
                         answer["total_bytes"]["reason"])
        self.assertIsNone(answer["total_bytes"]["value"])
        self.assertEqual([], answer["indexes"])

    def test_undeclared_tables_answer_empty_not_wrong(self):
        self.assertEqual([], inventory.undeclared_tables())


class MediaMeasurementTests(TestCase):
    """One declared prefix: its bytes, its references, its orphans, its gaps."""

    def setUp(self):
        super().setUp()
        self.root = tempfile.mkdtemp()
        self._saved = redirect_storages(STORAGE_SOURCES, self.root)

    def tearDown(self):
        restore_storages(self._saved)
        shutil.rmtree(self.root, ignore_errors=True)
        super().tearDown()

    def test_referenced_bytes_are_the_bytes_a_row_names(self):
        process_log("BackgroundProcessLog/1/report.txt", b"x" * 500)
        answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertEqual(500, answer["total_bytes"]["value"])
        self.assertEqual(500, answer["referenced_bytes"]["value"])
        self.assertEqual(0, answer["unreferenced_bytes"]["value"])
        self.assertEqual(0, answer["undetermined_bytes"]["value"])

    def test_bytes_no_row_names_are_reported_as_unreferenced(self):
        """The orphan finding #1501 owns: reported here, never deleted."""
        process_log("BackgroundProcessLog/1/report.txt", b"x" * 500)
        orphan = os.path.join(self.root, "BackgroundProcessLog", "424242")
        os.makedirs(orphan)
        with open(os.path.join(orphan, "left-behind.xml"), "wb") as handle:
            handle.write(b"o" * 250)
        answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertEqual(750, answer["total_bytes"]["value"])
        self.assertEqual(500, answer["referenced_bytes"]["value"])
        self.assertEqual(250, answer["unreferenced_bytes"]["value"])
        self.assertEqual(1, answer["unreferenced_bytes"]["files"])

    def test_a_reference_whose_file_is_gone_is_a_reason_not_zero_bytes(self):
        """#1150's finding: the row exists and its document does not."""
        log = process_log("BackgroundProcessLog/2/report.txt", b"x" * 100)
        os.remove(os.path.join(self.root, log.extented_description.name))
        answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertFalse(answer["undetermined_bytes"]["measured"])
        self.assertEqual(inventory.REASON_MISSING_REFERENCES,
                         answer["undetermined_bytes"]["reason"])
        self.assertEqual(1, answer["undetermined_bytes"]["files"])
        self.assertIn(log.extented_description.name,
                      answer["undetermined_bytes"]["examples"])
        # the gone file is counted neither as referenced bytes nor as an orphan
        self.assertEqual(0, answer["total_bytes"]["value"])
        self.assertEqual(0, answer["unreferenced_bytes"]["value"])

    def test_a_path_outside_the_storage_root_is_reported_not_opened(self):
        process_log("BackgroundProcessLog/3/report.txt", b"z" * 9)
        log = BackgroundProcessLog.objects.filter(
            extented_description="BackgroundProcessLog/3/report.txt").first()
        log.extented_description = "../escape.txt"
        log.save()
        answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertIn("../escape.txt", answer["paths_outside_storage_root"])
        self.assertIn(inventory.REASON_PATH_OUTSIDE_ROOT, answer["reasons"])
        # an escaping reference is not counted as referenced bytes either
        self.assertEqual(0, answer["referenced_bytes"]["value"])

    def test_a_storage_without_a_filesystem_reports_the_reason(self):
        """Object storage must read as a gap, never as zero bytes."""
        field = BackgroundProcessLog._meta.get_field("extented_description")
        field.storage = object()
        answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertEqual(inventory.REASON_UNSUPPORTED_STORAGE,
                         answer["total_bytes"]["reason"])
        self.assertIsNone(answer["total_bytes"]["value"])

    def test_an_unreadable_reference_column_stops_the_orphan_answer(self):
        """A partially migrated deployment must not produce an orphan claim.

        The report is the evidence #1501 would delete by: a reference column it
        could not read would turn every file of that prefix into a false orphan.
        """
        record = apps.get_model("registry", "DatasetMetadataRecord")
        field = record._meta.get_field("xml_backup_file")
        root = inventory._storage_location(field.storage)
        target = os.path.join(root, "xml_documents/42/record.xml")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(b"x" * 40)
        reference = next(entry for entry in XML_SOURCE.reference_fields
                         if entry[1] == "DatasetMetadataRecord")
        broken = XML_SOURCE.__class__(
            id=XML_SOURCE.id, app_label=XML_SOURCE.app_label,
            model_name=XML_SOURCE.model_name,
            field_name=XML_SOURCE.field_name, prefix=XML_SOURCE.prefix,
            kind=XML_SOURCE.kind, owner=XML_SOURCE.owner,
            lifecycle=XML_SOURCE.lifecycle,
            policy_candidate=XML_SOURCE.policy_candidate,
            reference_fields=(("registry", "NoSuchTable", "xml_backup_file"),
                              reference))
        answer = inventory.measure_media_source(broken)
        self.assertFalse(answer["unreferenced_bytes"]["measured"],
                         "the prefix may not be called orphaned on a partial "
                         "reference set")
        self.assertEqual(inventory.REASON_QUERY_FAILED,
                         answer["unreferenced_bytes"]["reason"])
        self.assertIn("NoSuchTable", answer["unreferenced_bytes"]["detail"])
        self.assertEqual(40, answer["total_bytes"]["value"],
                         "the bytes themselves are still measured")

    def test_a_stale_declaration_fails_in_the_report(self):
        broken = STORAGE_SOURCES[0].__class__(
            id="broken", app_label="registry", model_name="NoSuchModel",
            field_name="nope", prefix="xml_documents", kind="xml",
            owner="x", lifecycle="x", policy_candidate="none")
        answer = inventory.measure_media_source(broken)
        self.assertEqual(inventory.REASON_QUERY_FAILED,
                         answer["total_bytes"]["reason"])
        self.assertTrue(answer["reasons"])

    def test_reference_limit_makes_the_orphan_answer_unavailable(self):
        process_log("BackgroundProcessLog/4/a.txt", b"a")
        process_log("BackgroundProcessLog/5/b.txt", b"b")
        with mock.patch.object(inventory, "MEDIA_REFERENCE_LIMIT", 1):
            answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertFalse(answer["referenced_bytes"]["measured"])
        self.assertEqual(inventory.REASON_REFERENCE_LIMIT_EXHAUSTED,
                         answer["referenced_bytes"]["reason"])
        self.assertIn(inventory.REASON_REFERENCE_LIMIT_EXHAUSTED,
                      answer["reasons"])

    def test_scan_budget_makes_the_byte_answer_unavailable(self):
        process_log("BackgroundProcessLog/6/a.txt", b"a")
        process_log("BackgroundProcessLog/7/b.txt", b"b")
        with mock.patch.object(inventory, "MEDIA_SCAN_NODE_BUDGET", 1):
            answer = inventory.measure_media_source(LOG_SOURCE)
        self.assertEqual(inventory.REASON_SCAN_BUDGET_EXHAUSTED,
                         answer["total_bytes"]["reason"])
        self.assertEqual(inventory.REASON_SCAN_BUDGET_EXHAUSTED,
                         answer["unreferenced_bytes"]["reason"])

    def test_media_totals_stay_honest_when_a_source_cannot_answer(self):
        media = inventory.measure_media()
        broken = [source for source in media["sources"]
                  if not source["total_bytes"]["measured"]]
        if broken:
            self.assertFalse(media["total_bytes"]["measured"])
            self.assertEqual(len(broken), media["sources_not_measured"])
            self.assertIsNotNone(media["total_bytes"]["bytes_counted"])
        else:
            self.assertTrue(media["total_bytes"]["measured"])

    def test_a_shared_tree_is_counted_by_neither_parent_nor_child_twice(self):
        """The registration subtree is a source of its own below the harvest one."""
        registry_dir = os.path.join(self.root, "temporary_md_metadata_file",
                                    "registration", "1")
        os.makedirs(registry_dir)
        with open(os.path.join(registry_dir, "doc.xml"), "wb") as handle:
            handle.write(b"r" * 300)
        harvest = inventory.measure_media_source(
            next(source for source in STORAGE_SOURCES
                 if source.id == "harvest_temporary_records"))
        registration = inventory.measure_media_source(
            next(source for source in STORAGE_SOURCES
                 if source.id == "registration_documents"))
        self.assertEqual(0, harvest["total_bytes"]["value"])
        self.assertEqual(300, registration["total_bytes"]["value"])


class PostgreSQLInventoryTests(TestCase):
    """The real database answers, and every answer says how it was reached."""

    def test_every_declared_table_exists_in_the_database(self):
        """The declarations resolve against the migrated schema, not only Django."""
        for dataset in DATASETS:
            with self.subTest(dataset=dataset.id):
                for table in inventory.dataset_tables(dataset):
                    self.assertTrue(inventory.table_exists(table), table)

    def test_a_window_with_rows_is_measured_and_carries_its_window(self):
        started = timezone.now() - timedelta(days=1)
        for index in range(5):
            attempt(started_at=started + timedelta(minutes=index))
        answers = inventory.measure_tables(
            ["system_celerytaskattempt"],
            {"system_celerytaskattempt": "started_at"},
            timezone.now() - timedelta(days=30), timezone.now())
        window = answers["system_celerytaskattempt"]["window_rows"]
        self.assertTrue(window["measured"], window)
        self.assertEqual(5, window["value"])
        self.assertEqual(30, window["window_days"])
        self.assertEqual("started_at", window["time_field"])
        self.assertEqual(60.0, float(window["median_gap_seconds"]),
                         "five rows one minute apart have a one minute median")
        self.assertLessEqual(window["sampled_rows"],
                             inventory.GROWTH_SAMPLE_LIMIT)
        self.assertIsNotNone(window["sample_limit"])

    def test_an_empty_window_is_a_reason_and_never_a_measured_zero(self):
        attempt(started_at=timezone.now() - timedelta(days=400))
        answers = inventory.measure_tables(
            ["system_celerytaskattempt"],
            {"system_celerytaskattempt": "started_at"},
            timezone.now() - timedelta(days=30), timezone.now())
        window = answers["system_celerytaskattempt"]["window_rows"]
        self.assertFalse(window["measured"])
        self.assertEqual(inventory.REASON_NO_ROWS_IN_WINDOW, window["reason"])
        self.assertIsNone(window["value"])

    def test_a_table_without_a_declared_time_field_says_so(self):
        answers = inventory.measure_tables(
            ["registry_servicealert"], {},
            timezone.now() - timedelta(days=30), timezone.now())
        window = answers["registry_servicealert"]["window_rows"]
        self.assertFalse(window["measured"])
        self.assertEqual(inventory.REASON_NO_TIME_FIELD_DECLARED,
                         window["reason"])

    def test_a_stale_time_field_declaration_is_reported_as_stale(self):
        answers = inventory.measure_tables(
            ["system_celerytaskattempt"],
            {"system_celerytaskattempt": "column_which_does_not_exist"},
            timezone.now() - timedelta(days=30), timezone.now())
        window = answers["system_celerytaskattempt"]["window_rows"]
        self.assertFalse(window["measured"])
        self.assertEqual(inventory.REASON_NO_TIME_FIELD_DECLARED,
                         window["reason"])
        self.assertIn("stale", window["detail"])

    def test_never_analysed_table_answers_estimate_only_not_zero_rows(self):
        """``reltuples = -1`` is "nobody looked", which is not "no rows"."""
        attempt()
        answers = inventory.measure_tables(["system_celerytaskattempt"])
        estimate = answers["system_celerytaskattempt"]["estimated_rows"]
        if not estimate["measured"]:
            self.assertEqual(inventory.REASON_ROW_ESTIMATE_ONLY,
                             estimate["reason"])
            self.assertIsNone(estimate["value"])
            self.assertIn("count of the window", estimate["detail"])
        else:
            self.assertGreaterEqual(estimate["value"], 0)

    def test_sizes_come_from_the_catalog(self):
        attempt()
        answers = inventory.measure_tables(["system_celerytaskattempt"])
        total = answers["system_celerytaskattempt"]["total_bytes"]
        self.assertTrue(total["measured"], total)
        self.assertGreater(total["value"], 0,
                           "heap plus indexes plus TOAST is never 0")

    def test_vacuum_state_travels_with_the_size(self):
        """#1498 asks for the vacuum state: a DELETE returns space to
        PostgreSQL, not to the operating system, until vacuum reclaims it."""
        answers = inventory.measure_tables(["system_celerytaskattempt"])
        vacuum = answers["system_celerytaskattempt"]["vacuum"]
        self.assertTrue(vacuum["measured"], vacuum)
        for key in ("last_vacuum", "last_autovacuum", "last_analyze",
                    "last_autoanalyze"):
            self.assertIn(key, vacuum)

    def test_indexes_are_read_from_the_catalog(self):
        """The index needs of #1498's acceptance: can a policy select cheaply?"""
        answers = inventory.measure_tables(["registry_harvestingjob"])
        indexes = answers["registry_harvestingjob"]["indexes"]
        self.assertTrue(indexes, "the job table is indexed; the inventory must "
                                 "show what a policy could select on")
        self.assertIn("name", indexes[0])
        self.assertIn("definition", indexes[0])
        self.assertIsInstance(answers["registry_harvestingjob"]["triggers"],
                              list)

    def test_an_absent_table_is_a_reason_not_zero_bytes(self):
        answers = inventory.measure_tables(["no_such_table_here"])
        self.assertEqual(
            inventory.REASON_TABLE_ABSENT,
            answers["no_such_table_here"]["total_bytes"]["reason"])

    def test_wal_bytes_is_a_reason_until_it_is_asked_for(self):
        answers = inventory.measure_tables(["system_celerytaskattempt"],
                                           with_wal=False)
        wal = answers["system_celerytaskattempt"]["wal_bytes"]
        self.assertFalse(wal["measured"])
        self.assertEqual(inventory.REASON_NOT_REQUESTED, wal["reason"])
        answers = inventory.measure_tables(["system_celerytaskattempt"],
                                           with_wal=True)
        wal = answers["system_celerytaskattempt"]["wal_bytes"]
        if not wal["measured"]:
            # a role without the privilege: the reason names what is missing
            self.assertEqual(inventory.REASON_NO_WAL_ACCESS, wal["reason"])
            self.assertIn("pg_read_all_stats", wal["detail"])

    def test_postgresql_facts_reports_the_maintenance_settings(self):
        facts = inventory.postgresql_facts()
        self.assertTrue(facts["settings"]["measured"], facts["settings"])
        self.assertIn("autovacuum", facts["settings"]["value"])
        self.assertIn("max_wal_size", facts["settings"]["value"])
        self.assertIsNotNone(facts["role"])

    def test_undeclared_tables_lists_tables_no_declaration_covers(self):
        declared = {name for dataset in DATASETS
                    for name in inventory.dataset_tables(dataset)}
        undeclared = inventory.undeclared_tables()
        names = [row["table"] for row in undeclared]
        for row in undeclared:
            self.assertNotIn(row["table"], declared)
            self.assertEqual(inventory.REASON_UNDECLARED, row["reason"])
        self.assertIn("registry_periodicharvestingjob", names,
                      "a table of an inventoried app with no declaration must "
                      "be visible rather than silently absent")

    def test_deletion_graph_comes_from_the_model_metadata(self):
        """#1497: a selection must know its FK graph before it selects."""
        rows = {row["id"]: row for row in inventory.dataset_rows()}
        incoming = {(entry["from"], entry["on_delete"])
                    for entry in rows["harvesting_job"]["references"]
                    ["incoming"]}
        self.assertIn(("registry.harvestedmetadatarelation", "CASCADE"),
                      incoming,
                      "a run's harvested records follow it; a policy must "
                      "know before it selects")
        outgoing = rows["http_request_log"]["references"]["outgoing"]
        self.assertIn("PROTECT", [entry["on_delete"] for entry in outgoing],
                      "the proxy logs protect the user and the service, which "
                      "is a retention finding in itself")

    def test_report_is_json_and_names_the_declaration_the_gaps_and_the_gates(self):
        report = inventory.build_inventory(window_days=7)
        parsed = json.loads(inventory.format_report(report, "json"))
        self.assertEqual(1, parsed["inventory"]["schema_version"])
        self.assertEqual(DECLARATION_VERSION,
                         parsed["inventory"]["declaration_version"])
        self.assertEqual(len(DATASETS), len(parsed["growth"]))
        self.assertTrue(parsed["gates"])
        self.assertTrue(parsed["provenance"]["not_measured"])
        for item in parsed["growth"]:
            if item["rows_per_day"] is None:
                self.assertIsNotNone(
                    item["window_reason"],
                    f"{item['id']} reports no rate without a reason")

    def test_report_ranks_only_what_it_measured(self):
        for _ in range(4):
            attempt()
        # the byte rate needs an average row size, and the average needs a
        # planner which has looked at the table: an unanalysed table answers as
        # an estimate gap, so this test asks for the statistics first
        with connection.cursor() as cursor:
            cursor.execute("analyze system_celerytaskattempt")
        report = inventory.build_inventory(window_days=30)
        ranked = [item for item in report["growth"] if item["rank"]]
        self.assertTrue(ranked)
        for item in ranked:
            self.assertIsNotNone(item["bytes_per_day"], item["id"])
        values = [item["bytes_per_day"] for item in ranked]
        self.assertEqual(sorted(values, reverse=True), values)
        self.assertTrue([item for item in report["growth"] if not item["rank"]],
                        "a table with nothing in its window stays unranked "
                        "rather than being ranked by an invented number")

    def test_a_narrowed_run_measures_only_what_was_named(self):
        report = inventory.build_inventory(datasets=["celery_task_attempt"])
        self.assertEqual(["system_celerytaskattempt"],
                         sorted(report["measurements"]))
        self.assertEqual(1, len(report["growth"]))

    def test_a_family_dataset_narrows_to_its_whole_family(self):
        report = inventory.build_inventory(datasets=["monitoring_run"])
        self.assertGreater(len(report["measurements"]), 1,
                           "a family is one policy question over every table "
                           "of the inheritance chain")

    def test_an_unknown_dataset_or_table_raises_instead_of_answering_empty(self):
        with self.assertRaises(inventory.RetentionInventoryError) as caught:
            inventory.build_inventory(datasets=["nope"])
        self.assertIn("no dataset named", str(caught.exception))
        with self.assertRaises(inventory.RetentionInventoryError):
            inventory.build_inventory(tables=["no_such_table_at_all"])


class CommandTests(TestCase):
    """The operator's path: it reports, and it never offers a second mode."""

    def _run(self, *args):
        out, err = io.StringIO(), io.StringIO()
        call_command("retention_inventory", *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_text_report_prints_the_honest_summary(self):
        out, err = self._run()
        self.assertIn("#1498", out)
        self.assertIn("harvesting_job", out)
        self.assertIn("xml_backup_documents", out)
        self.assertIn("Undeclared tables", out)
        self.assertIn("Unresolved decisions", out)
        self.assertIn("gated", err,
                      "the gates are the one thing an operator must not miss "
                      "on the way to a sweep")

    def test_json_report_is_machine_readable(self):
        out, _ = self._run("--format", "json")
        parsed = json.loads(out)
        for key in ("datasets", "media", "growth", "postgresql", "settings",
                    "provenance"):
            self.assertIn(key, parsed)

    def test_no_media_skips_the_filesystem(self):
        out, _ = self._run("--format", "json", "--no-media")
        for source in json.loads(out)["media"]["sources"]:
            self.assertEqual("not_requested", source["total_bytes"]["reason"])

    def test_an_unknown_dataset_fails_loudly(self):
        with self.assertRaises(CommandError) as caught:
            call_command("retention_inventory", "--dataset", "nope",
                         stdout=io.StringIO(), stderr=io.StringIO())
        self.assertIn("no dataset named", str(caught.exception))

    def test_an_absurd_window_is_refused(self):
        for flag in ("--window-days", "--horizon-days"):
            with self.assertRaises(CommandError):
                call_command("retention_inventory", flag, "0",
                             stdout=io.StringIO(), stderr=io.StringIO())

    def test_output_file_is_the_only_file_created(self):
        directory = tempfile.mkdtemp()
        target = os.path.join(directory, "inventory.json")
        try:
            call_command("retention_inventory", "--format", "json",
                         "--output", target, stdout=io.StringIO(),
                         stderr=io.StringIO())
            with open(target, encoding="utf-8") as handle:
                self.assertIn("provenance", json.load(handle))
            self.assertEqual(["inventory.json"], os.listdir(directory))
        finally:
            shutil.rmtree(directory, ignore_errors=True)

    def test_the_command_offers_no_way_to_write(self):
        """No --confirm, no --force, no --dry-run: there is no second mode."""
        from system.management.commands.retention_inventory import Command

        parser = mock.Mock()
        Command().add_arguments(parser)
        flags = [call.args[0] for call in parser.add_argument.call_args_list]
        self.assertNotIn("--confirm", flags)
        self.assertNotIn("--force", flags)
        self.assertNotIn("--dry-run", flags)
        self.assertIn("--output", flags)


class ReadOnlyEnforcementTests(unittest.TestCase):
    """The guarantee #1498 asks for, checked the only way it can be checked.

    ``TestCase`` wraps each test in a read-write transaction, and PostgreSQL will
    not downgrade a transaction which has already written; this is therefore a
    plain ``unittest`` case against the real connection, outside any transaction,
    which is also the posture of the management command.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise unittest.SkipTest("the inventory measures PostgreSQL")

    def tearDown(self):
        connection.rollback()
        super().tearDown()

    def test_the_report_runs_in_a_read_only_transaction(self):
        self.assertFalse(connection.in_atomic_block)
        with inventory.read_only_report() as enforced:
            self.assertTrue(enforced)
            with connection.cursor() as cursor:
                cursor.execute("show transaction_read_only")
                self.assertEqual("on", cursor.fetchone()[0])
        connection.rollback()

    def test_a_write_inside_the_report_raises_instead_of_happening(self):
        self.assertFalse(connection.in_atomic_block)
        with self.assertRaises(db_utils.DatabaseError):
            with inventory.read_only_report():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "insert into system_celerytaskattempt "
                        "(task_id, attempt_no, task_name, queue, worker, "
                        "root_id, parent_id, periodic_name, started_at, "
                        "outcome, quality, recorded_at) "
                        "values ('would-write', 0, 'n', '', '', '', '', '', "
                        "now(), '', '{}', now())")
        connection.rollback()
        self.assertEqual(
            0, CeleryTaskAttempt.objects.filter(task_id="would-write").count())

    def test_the_statement_timeout_is_set_for_the_report(self):
        """Bounded reads are a property, not an intention."""
        with inventory.read_only_report():
            with connection.cursor() as cursor:
                cursor.execute("show statement_timeout")
                self.assertNotEqual("0", cursor.fetchone()[0])
        connection.rollback()
