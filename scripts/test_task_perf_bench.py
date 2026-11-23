#!/usr/bin/env python3
"""Offline tests for task_perf_bench, the Celery runtime benchmark reporter (#1396).

Host-side tests of the host-side tool, like ``scripts/test_http_process_bench.py``
for its web-tier sibling: plain unittest, no imports from the application and
nothing from the network, so they run in pre-commit and in CI as fast as an
import costs. The heavy half of #1396 - actually executing a task family - lives
in the Django opt-in suite
``backend/tests/django/system/test_task_runtime_bench.py``; what is tested here
is the reading and the verdict built on top of it.

The subject is the tool's honesty, not its arithmetic:

*   the three durations stay three measurements - an arm which quietly reports
    worker occupancy as broker wait is rejected (#1330's conflation mistake);
*   a percentile nobody sampled is not reported, and an unmeasured thing is
    ``null`` rather than ``0``;
*   two arms of different workloads cannot be compared at all;
*   an unstable arm may not produce a blocking verdict, whatever it measured;
*   and a blocking verdict additionally needs a reviewed baseline entry plus an
    explicit ``--mode block``, which is what keeps the shipped default a warning.

Run from the repository root:
    python3 -m unittest discover -s scripts -p 'test_task_perf_bench.py' -v
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import task_perf_bench  # noqa: E402  (host-side tool of this repository)

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "task_perf_bench.py")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BENCH_SUPPORT = os.path.join(
    REPO_ROOT, "backend", "tests", "django", "system",
    "_task_runtime_bench_support.py")


def unit(active=0.5, wait=0.02, elapsed=None, outcome="success", index=0):
    return {"id": "unit-%d" % index,
            "elapsed_seconds": active + 0.01 if elapsed is None else elapsed,
            "attempts": [{"task_id": "t%d" % index, "attempt_no": 0,
                          "active_seconds": active, "wait_seconds": wait,
                          "outcome": outcome}]}


def workload(units=None, **spec):
    """A workload fixture in the shape the Django bench suite writes."""
    payload = {
        "family": "harvesting.import_chunk",
        "fixture": "typical",
        "scale": "typical",
        "records": 100,
        "chunks": 1,
        "chunk_size": 1000,
        "attempts_per_unit": 1,
        "queue": "harvest-import",
        "mock_responses": "in-process-lxml-200",
        "units": units if units is not None else [unit() for _ in range(30)],
    }
    payload.update(spec)
    return payload


def argv(**overrides):
    """The canonical load invocation, overridable per test."""
    args = {"arm": "baseline", "seed": 20261121, "repeats": "7", "repeat": "1",
            "revision": "abc1234", "now": "2026-11-21T12:00:00+00:00"}
    args.update({key: str(value) for key, value in overrides.items()})
    return args


def write_fixture(directory, payload, name="wl.json"):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def write_records(path, records):
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(task_perf_bench.canonical(record) + "\n")
    return path


def build_record(tmpdir, arm="baseline", repeat=1, repeats="7", units=None,
                 **spec):
    """One record, built by the real CLI path (load without --out)."""
    fixture = write_fixture(tmpdir, workload(units=units, **spec),
                            "wl-%s-%s.json" % (arm, repeat))
    out = io.StringIO()
    with redirect_stdout(out):
        rc = task_perf_bench.main([
            "load", "--arm", arm, "--seed", "20261121", "--repeats", str(repeats),
            "--repeat", str(repeat), "--fixture", fixture, "--revision", "abc1234",
            "--now", "2026-11-21T12:00:00+00:00"])
    assert rc == 0, "load failed"
    return json.loads(out.getvalue())


# --------------------------------------------------------------- sample honesty


class StatisticDefinitionTest(unittest.TestCase):
    """The statistics the report promises, exactly - and not more."""

    def test_percentile_is_nearest_rank(self):
        self.assertEqual(25, task_perf_bench.percentile(
            list(range(1, 101)), 0.25))
        self.assertEqual(50, task_perf_bench.percentile(
            list(range(1, 101)), 0.50))
        self.assertEqual(95, task_perf_bench.percentile(
            list(range(1, 101)), 0.95))
        # nearest rank, the same definition scripts/http_process_bench.py
        # documents: the 99th percentile of 1..100 is 99, not 100
        self.assertEqual(99, task_perf_bench.percentile(
            list(range(1, 101)), 0.99))
        self.assertEqual(1, task_perf_bench.percentile([1], 0.99))

    def test_percentile_of_nothing_is_none_not_zero(self):
        self.assertIsNone(task_perf_bench.percentile([], 0.95))
        self.assertIsNone(task_perf_bench.mean([]))

    def test_coefficient_of_variation_needs_two_samples(self):
        self.assertIsNone(task_perf_bench.coefficient_of_variation([1.0]))
        self.assertIsNone(task_perf_bench.coefficient_of_variation([]))
        self.assertAlmostEqual(0.0, task_perf_bench.coefficient_of_variation(
            [2.0, 2.0, 2.0]), places=9)
        self.assertAlmostEqual(2 ** 0.5 / 2,
                               task_perf_bench.coefficient_of_variation(
                                   [1.0, 3.0]), places=6,
                               msg="the sample stdev (n-1) over the mean")

    def test_thin_sample_reports_median_and_never_a_percentile(self):
        """The acceptance bullet: p50/p95/p99 when adequately sampled."""
        block = task_perf_bench.duration_stats([0.5] * 5, "active")
        self.assertEqual(5, block["n"])
        self.assertEqual(0.5, block["p50"])
        self.assertIsNone(block["p95"], "5 samples are not a p95")
        self.assertIsNone(block["p99"])
        self.assertEqual(["p50", "mean", "min", "max"], block["reported"])

    def test_p95_appears_at_its_own_floor(self):
        block = task_perf_bench.duration_stats([0.5] * 20, "active")
        self.assertIsNotNone(block["p95"])
        self.assertIsNone(block["p99"], "20 samples are still not a p99")

    def test_p99_appears_at_its_own_floor(self):
        block = task_perf_bench.duration_stats([0.5] * 100, "active")
        self.assertIsNotNone(block["p99"])

    def test_an_empty_sample_list_is_a_block_of_none(self):
        block = task_perf_bench.duration_stats([], "queue")
        self.assertEqual(0, block["n"])
        for key in ("min", "mean", "p50", "p95", "p99", "max"):
            self.assertIsNone(block[key], "%s must stay unknown, not 0" % key)


class WorkloadIdentityTest(unittest.TestCase):
    """Reproducibility: same seed and same workload, or no comparison."""

    def test_same_workload_same_digest(self):
        first = task_perf_bench.workload_digest(workload())
        second = task_perf_bench.workload_digest(workload(ts="ignored"))
        self.assertEqual(first, second)

    def test_every_identity_field_changes_the_digest(self):
        base = task_perf_bench.workload_digest(workload())
        for key, value in (("scale", "large"), ("records", 200),
                           ("chunk_size", 500), ("seed", 7),
                           ("mock_responses", "real-remote"),
                           ("queue", "default")):
            changed = task_perf_bench.workload_digest(
                workload(**{key: value}))
            self.assertNotEqual(base, changed,
                                "%s is part of the workload identity" % key)

    def test_timings_do_not_change_the_digest(self):
        """Two arms of one workload differ in duration and nothing else."""
        slow = task_perf_bench.workload_digest(
            workload(units=[unit(active=9.0) for _ in range(30)]))
        fast = task_perf_bench.workload_digest(
            workload(units=[unit(active=0.1) for _ in range(30)]))
        self.assertEqual(slow, fast)

    def test_auto_repeats_and_the_cap(self):
        self.assertEqual((7, None), task_perf_bench.resolve_repeats("7"))
        self.assertEqual((0, "auto"), task_perf_bench.resolve_repeats("auto"))
        self.assertEqual((1, None), task_perf_bench.resolve_repeats(0))
        with self.assertRaises(SystemExit):
            task_perf_bench.resolve_repeats("seven")


class ValidationHonestyTest(unittest.TestCase):
    """A record which lies about itself is refused on read and on write."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.record = build_record(self.tmp.name)

    def test_a_valid_record_validates(self):
        self.assertIs(task_perf_bench.validate_record(self.record),
                      self.record)

    def test_missing_seed_is_refused(self):
        broken = dict(self.record)
        broken.pop("seed")
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("seed", str(caught.exception))

    def test_unknown_family_is_refused(self):
        broken = dict(self.record)
        broken["family"] = "harvesting.whatever"
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("harvesting.import_chunk", str(caught.exception))

    def test_a_percentile_from_too_few_samples_is_refused(self):
        """The floor is enforced on read, not only produced on write."""
        broken = json.loads(json.dumps(self.record))
        broken["durations"]["active"]["p99"] = 1.0
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("p99", str(caught.exception))

    def test_an_unknown_evidence_label_is_refused(self):
        broken = json.loads(json.dumps(self.record))
        broken["durations"]["active"]["evidence"] = "vibes"
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("vibes", str(caught.exception))

    def test_truncated_window_without_a_note_is_refused(self):
        broken = json.loads(json.dumps(self.record))
        broken["quality"]["retention_truncated"] = True
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("retention", str(caught.exception))

    def test_worker_occupancy_may_not_be_reported_as_broker_wait(self):
        """#1330's conflation mistake, caught structurally."""
        broken = json.loads(json.dumps(self.record))
        broken["durations"]["queue"] = dict(broken["durations"]["active"])
        broken["durations"]["queue"]["label"] = "queue"
        broken["durations"]["queue"]["evidence"] = "derived"
        broken["durations"]["active"]["evidence"] = "derived"
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.validate_record(broken)
        self.assertIn("broker wait", str(caught.exception))

    def test_a_record_without_its_revision_is_refused(self):
        broken = dict(self.record)
        broken["revision"] = ""
        with self.assertRaises(SystemExit):
            task_perf_bench.validate_record(broken)
        broken["revision"] = None          # git cannot answer: that is honest
        task_perf_bench.validate_record(broken)

    def test_a_malformed_line_is_a_hard_error_not_a_skip(self):
        """A silently dropped line is how a flaky gate is born."""
        path = os.path.join(self.tmp.name, "broken.jsonl")
        write_records(path, [self.record])
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("{not json}\n")
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.load_records(path)
        self.assertIn("not JSON", str(caught.exception))


# ------------------------------------------------------------------- the report


class ReportTest(unittest.TestCase):
    """The report shows the sample size beside every number it prints."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _jsonl(self, records, name="perf.jsonl"):
        return write_records(os.path.join(self.tmp.name, name), records)

    def test_report_prints_sample_counts_and_labels_missing_coverage(self):
        records = [build_record(self.tmp.name, arm="baseline", repeat=index)
                   for index in range(1, 8)]
        out = io.StringIO()
        with redirect_stdout(out):
            rc = task_perf_bench.main(["report", "--in", self._jsonl(records)])
        self.assertEqual(0, rc)
        printed = out.getvalue()
        self.assertIn("(30)", printed, "the sample count travels with the cell")
        self.assertIn("cov", printed)
        self.assertIn("broker_pressure_unmeasured", printed)
        self.assertIn("instrumentation_overhead_unmeasured", printed)
        self.assertIn("digest=", printed, "a report names the workload it read")

    def test_the_repeatability_column_reads_the_whole_arm(self):
        """CV is a property of an arm's repeats together, not of one row."""
        varying = [build_record(self.tmp.name, arm="noisy", repeat=index,
                                units=[unit(active=0.5 + 0.1 * index)] * 30)
                   for index in range(1, 8)]
        out = io.StringIO()
        with redirect_stdout(out):
            task_perf_bench.main(["report", "--in", self._jsonl(varying)])
        rows = [line for line in out.getvalue().splitlines()
                if line.startswith("harvesting.import_chunk")]
        self.assertTrue(rows)
        covs = {line.split()[-1] for line in rows}
        self.assertEqual(1, len(covs), "every repeat shows the arm's CV")
        self.assertNotEqual("-", covs.pop())

    def test_report_filters_by_family_arm_and_scale(self):
        records = ([build_record(self.tmp.name, arm="baseline", repeat=index)
                    for index in range(1, 3)]
                   + [build_record(self.tmp.name, arm="candidate", repeat=index,
                                   scale="large", records=1000)
                      for index in range(1, 3)])
        out = io.StringIO()
        with redirect_stdout(out):
            task_perf_bench.main(["report", "--in", self._jsonl(records),
                                  "--arm", "candidate"])
        printed = out.getvalue()
        self.assertIn("candidate", printed)
        self.assertNotIn(" baseline ", printed)

    def test_an_empty_selection_is_a_clear_error(self):
        records = [build_record(self.tmp.name)]
        with self.assertRaises(SystemExit):
            task_perf_bench.main(["report", "--in",
                                  self._jsonl(records), "--arm", "nothing"])


# ---------------------------------------------------------------- compare/verdict


class CompareTest(unittest.TestCase):
    """Before/after for two arms - or no verdict at all."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _jsonl(self, records, name="perf.jsonl"):
        return write_records(os.path.join(self.tmp.name, name), records)

    def _pair(self, slow_factor=2.2):
        baseline = [build_record(self.tmp.name, arm="baseline", repeat=index)
                    for index in range(1, 8)]
        candidate = [build_record(
            self.tmp.name, arm="sql-n-plus-one", repeat=index,
            units=[unit(active=0.5 * slow_factor)] * 30)
            for index in range(1, 8)]
        return self._jsonl(baseline + candidate)

    def _verdict(self, path, baseline="baseline", candidate="sql-n-plus-one"):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = task_perf_bench.main([
                "compare", "--in", path, "--baseline", baseline,
                "--candidate", candidate,
                "--now", "2026-11-21T12:00:00+00:00"])
        self.assertEqual(0, rc)
        return json.loads(out.getvalue())

    def test_a_regression_is_a_number_a_human_can_read(self):
        verdict = self._verdict(self._pair())
        metrics = verdict["metrics"]["active_p50"]
        self.assertAlmostEqual(2.2, metrics["ratio"], places=2)
        self.assertIsNotNone(metrics["baseline"])
        self.assertEqual("baseline", verdict["baseline"])
        self.assertEqual(7, verdict["repeats"]["candidate"])
        self.assertIsNotNone(verdict["repeatability"]["cv_active_candidate"])

    def test_queue_wait_and_end_to_end_are_their_own_rows(self):
        verdict = self._verdict(self._pair())
        self.assertIn("queue_p50", verdict["metrics"])
        self.assertIn("end_to_end_p50", verdict["metrics"])
        self.assertIsNotNone(verdict["metrics"]["queue_p50"]["baseline"])

    def test_comparing_different_workloads_is_refused(self):
        path = self._jsonl(
            [build_record(self.tmp.name, arm="baseline", repeat=1)]
            + [build_record(self.tmp.name, arm="sql-n-plus-one", repeat=1,
                            records=1000, scale="large")])
        with self.assertRaises(SystemExit) as caught:
            self._verdict(path)
        self.assertIn("different workloads", str(caught.exception))

    def test_a_missing_arm_says_which_one(self):
        path = self._jsonl([build_record(self.tmp.name, arm="baseline")])
        with self.assertRaises(SystemExit) as caught:
            self._verdict(path)
        self.assertIn("candidate", str(caught.exception))

    def test_verdict_carries_its_coverage_labels(self):
        verdict = self._verdict(self._pair())
        self.assertIn("broker_pressure_unmeasured",
                      verdict["coverage"]["candidate"])
        self.assertNotIn("repeatability_unmeasured",
                         verdict["coverage"]["candidate"],
                         "seven repeats do answer repeatability")


# --------------------------------------------------------------------------- gate


def baseline_file(entries, stability=None):
    payload = {"schema": task_perf_bench.SCHEMA_VERSION,
               "kind": "baseline",
               "stability": stability or {"max_cv": 0.03},
               "entries": entries}
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "baseline.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    return path


def entry_for(record, metrics=None, **spec):
    """A reviewed baseline entry for one arm, defaulting to the arm's own numbers.

    The defaults are what an approving human signs off on: the arm's measured
    p50 and p95 as the reviewed baseline. A test of a regression passes its own
    ``metrics`` to say "the review happened against something else".
    """
    durations = record.get("durations") or {}
    active = durations.get("active") or {}
    metrics = metrics or {"active_p50": active.get("p50", 0.5),
                          "active_p95": active.get("p95") or active.get("p50", 0.55)}
    entry = {"family": record["family"], "arm": record["arm"],
             "scale": record.get("scale"),
             "workload_digest": record["digest"],
             "metrics": metrics,
             "ratio": 1.25, "block": False,
             "approved_by": "performance maintainer",
             "reviewed_at": "2026-11-21"}
    entry.update(spec)
    return entry


def reviewed_entry(rows, reviewed_for=None, **spec):
    """A baseline entry whose reviewed numbers come from a real run.

    ``reviewed_for`` is the arm the entry belongs to, when that is not the arm
    ``rows`` came from - which is exactly what a regression report is: the
    candidate's entry holding the numbers a human reviewed against some other
    (usually earlier, usually faster) run. Without it the entry reviews the arm's
    own pooled p50/p95, which is what an approving maintainer signs off on after
    looking at a run of that arm.
    """
    summary = task_perf_bench.arm_summary(rows)
    active = summary["active"]
    entry = entry_for(reviewed_for or rows[0],
                      metrics={"active_p50": active["p50"],
                               "active_p95": active["p95"] or active["p50"]},
                      **spec)
    entry.setdefault("reviewed", True)
    return entry


class GateTest(unittest.TestCase):
    """The nonflaky half: what may block, and what may only warn."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _jsonl(self, records):
        path = os.path.join(self.tmp.name, "perf.jsonl")
        return write_records(path, records)

    def _gate(self, path, baseline, mode="warn", extra=()):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main(
                ["gate", "--in", path, "--baseline", baseline, "--mode", mode,
                 "--now", "2026-11-21T12:00:00+00:00", *extra])
        return rc, json.loads(out.getvalue())

    def _stable_arm(self, arm="baseline", active=0.5, repeats=7):
        return [build_record(self.tmp.name, arm=arm, repeat=index,
                             repeats=repeats,
                             units=[unit(active=active)] * 30)
                for index in range(1, repeats + 1)]

    def test_no_baseline_entry_can_never_block(self):
        records = self._stable_arm()
        path = self._jsonl(records)
        baseline = baseline_file([])
        rc, report = self._gate(path, baseline, mode="block")
        self.assertEqual(0, rc, "an unreviewed benchmark may not gate")
        self.assertEqual(["skip"], [check["verdict"] for check in
                                    report["checks"]])
        self.assertIn("no baseline entry", report["checks"][0]["reason"])

    def test_a_stable_arm_inside_the_budget_passes(self):
        records = self._stable_arm()
        baseline = baseline_file([reviewed_entry(records)])
        rc, report = self._gate(self._jsonl(records), baseline, mode="block")
        self.assertEqual(0, rc)
        self.assertEqual("pass", report["checks"][0]["verdict"])

    def test_a_regression_in_warn_mode_warns_and_exits_zero(self):
        records = self._stable_arm(arm="baseline") + self._stable_arm(
            arm="sql-n-plus-one", active=1.6)
        baseline = baseline_file([
            reviewed_entry(records[:7]),
            reviewed_entry(records[:7], reviewed_for=records[-1], block=True)])
        rc, report = self._gate(self._jsonl(records), baseline, mode="warn")
        self.assertEqual(0, rc, "warn never fails a job")
        candidate = [check for check in report["checks"]
                     if check["arm"] == "sql-n-plus-one"][0]
        self.assertEqual("warn", candidate["verdict"])
        self.assertIn("grew", candidate["reason"])

    def test_a_regression_blocks_only_when_approved_and_asked(self):
        records = self._stable_arm(arm="baseline") + self._stable_arm(
            arm="sql-n-plus-one", active=1.6)
        # the candidate's thresholds were reviewed against the fast baseline
        # run - which is what a regression report is
        baseline = baseline_file([
            reviewed_entry(records[:7]),
            reviewed_entry(records[:7], reviewed_for=records[-1], block=True)])
        rc, report = self._gate(self._jsonl(records), baseline, mode="block")
        self.assertEqual(1, rc)
        candidate = [check for check in report["checks"]
                     if check["arm"] == "sql-n-plus-one"][0]
        self.assertEqual("block", candidate["verdict"])
        self.assertIn("sql-n-plus-one", str(report["approval_required"]))

    def test_an_unstable_arm_may_not_block_however_slow(self):
        """A noisy machine gets a warning, never a red check."""
        slow_noisy = [build_record(self.tmp.name, arm="baseline", repeat=index,
                                   units=[unit(active=2.0 * (1 + index))] * 30)
                      for index in range(1, 8)]
        # the thresholds would block: reviewed against a fast baseline, and
        # only the noise of the arm keeps the check from being red
        fast = [build_record(self.tmp.name, arm="baseline", repeat=index,
                             units=[unit(active=0.5)] * 30)
                for index in range(1, 8)]
        baseline = baseline_file([reviewed_entry(fast, block=True)])
        rc, report = self._gate(self._jsonl(slow_noisy), baseline, mode="block")
        self.assertEqual(0, rc)
        self.assertEqual("unstable", report["checks"][0]["verdict"])
        self.assertIn("CV", report["checks"][0]["reason"])
        self.assertGreater(report["checks"][0]["stability"]["cv"], 0.0,
                           "the arm really was noisy, and it stayed a warning")

    def test_an_incomplete_arm_is_unstable_not_a_verdict(self):
        # seven repeats were planned, three were delivered: no verdict
        records = [build_record(self.tmp.name, arm="baseline", repeat=index,
                                repeats=7, units=[unit(active=0.5)] * 30)
                   for index in range(1, 4)]
        baseline = baseline_file([reviewed_entry(records, block=True)])
        rc, report = self._gate(self._jsonl(records), baseline, mode="block")
        self.assertEqual(0, rc)
        self.assertEqual("unstable", report["checks"][0]["verdict"])
        self.assertIn("incomplete", report["checks"][0]["reason"])

    def test_a_single_repeat_cannot_state_repeatability(self):
        records = self._stable_arm(repeats=1)
        baseline = baseline_file([reviewed_entry(records, block=True)])
        rc, report = self._gate(self._jsonl(records), baseline, mode="block")
        self.assertEqual(0, rc)
        self.assertEqual("unstable", report["checks"][0]["verdict"])
        self.assertIn("repeatability", report["checks"][0]["reason"])

    def test_a_stale_workload_digest_skips_the_comparison(self):
        records = self._stable_arm()
        stale = entry_for(records[0], workload_digest="0" * 16)
        rc, report = self._gate(self._jsonl(records), baseline_file([stale]))
        self.assertEqual(0, rc)
        self.assertEqual("skip", report["checks"][0]["verdict"])
        self.assertIn("digest", report["checks"][0]["reason"])

    def test_a_per_family_floor_from_the_baseline_file_is_used(self):
        """A family whose own floor is loose cannot be gated at 3 %."""
        noisy = [build_record(self.tmp.name, arm="baseline", repeat=index,
                              units=[unit(active=0.5 * (1 + 0.1 * index))] * 30)
                 for index in range(1, 8)]
        tight = baseline_file([reviewed_entry(noisy, block=True)],
                              stability={"max_cv": 0.001})
        loose = baseline_file([reviewed_entry(noisy, block=True, max_cv=0.50)],
                              stability={"max_cv": 0.001})
        path = self._jsonl(noisy)
        _, strict = self._gate(path, tight)
        self.assertEqual("unstable", strict["checks"][0]["verdict"])
        _, allowed = self._gate(path, loose)
        self.assertEqual("pass", allowed["checks"][0]["verdict"])

    def test_worker_loss_downgrades_a_pass_to_a_warning(self):
        records = self._stable_arm()
        for record in records:
            record["quality"]["worker_loss"] = 1
            record["digest"] = task_perf_bench.workload_digest(record)
        baseline = baseline_file([reviewed_entry(records)])
        _, report = self._gate(self._jsonl(records), baseline)
        self.assertEqual("warn", report["checks"][0]["verdict"])
        self.assertIn("worker_loss", report["checks"][0]["reason"])

    def test_the_baseline_file_must_be_a_baseline_file(self):
        path = os.path.join(self.tmp.name, "not-a-baseline.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"entries": "nope"}, handle)
        with self.assertRaises(SystemExit):
            self._gate(self._jsonl(self._stable_arm()), path)

    def test_an_unreviewed_entry_reports_and_does_not_gate(self):
        records = self._stable_arm(active=3.0)
        entry = reviewed_entry(records, reviewed=False)
        rc, report = self._gate(self._jsonl(records), baseline_file([entry]),
                                mode="block")
        self.assertEqual(0, rc)
        self.assertEqual("skip", report["checks"][0]["verdict"])
        self.assertIn("reviewed", report["checks"][0]["reason"])

    def test_the_committed_baseline_ships_unreviewed(self):
        """No mandatory performance gate exists until a human approves one."""
        shipped = os.path.join(REPO_ROOT, "scripts", "task_perf_baseline.json")
        with open(shipped, encoding="utf-8") as handle:
            payload = json.load(handle)
        self.assertIn("entries", payload)
        self.assertTrue(payload["entries"],
                        "the shipped file names what the runbook measures")
        self.assertEqual([], [entry for entry in payload["entries"]
                              if entry.get("block")],
                         "a shipped baseline may not pre-approve a blocking gate")
        self.assertEqual([], [entry for entry in payload["entries"]
                              if entry.get("reviewed")],
                         "thresholds need a human signature, which the shipped "
                         "file must not fake")
        for entry in payload["entries"]:
            self.assertIn(entry["family"], task_perf_bench.FAMILIES)
        self.assertTrue(payload.get("stability", {}).get("max_cv"))


# --------------------------------------------------------------------- detectors


class DetectTest(unittest.TestCase):
    """The acceptance bullet: injected defects must actually be detected."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _ladder(self, statements_for, arm="candidate"):
        """Records at the 1 / 10 / 100 rungs, paying ``statements_for(size)``.

        A constant cost per unit is the reviewed shape; a per-unit cost which
        itself grows with the size of the workload is what an N+1 looks like from
        outside the code - which is the level the epic asks the detection to work
        at, since a statement guard already covers the inside (#1395).
        """
        records = []
        for size in (1, 10, 100):
            record = build_record(
                self.tmp.name, arm=arm, repeat=1, records=size,
                units=[unit()] * size,
                sql={"statements": {"value": statements_for(size),
                                    "evidence": "measured"}})
            records.append(record)
        return records

    def _jsonl(self, records, name="perf.jsonl"):
        return write_records(os.path.join(self.tmp.name, name), records)

    def _detect(self, path, arm, extra=()):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main(
                ["detect", "--in", path, "--arm", arm,
                 "--now", "2026-11-21T12:00:00+00:00", *extra])
        return rc, json.loads(out.getvalue())

    def _finding(self, report, kind):
        return [finding for finding in report["findings"]
                if finding["kind"] == kind]

    def test_a_flat_statement_shape_is_not_an_n_plus_one(self):
        """The baseline of the detection: constant work per unit is green."""
        _rc, report = self._detect(self._jsonl(self._ladder(lambda size: size)), "candidate")
        n_plus_one = self._finding(report, "sql_n_plus_one")
        self.assertTrue(n_plus_one, "the ladder answered, so the detector spoke")
        self.assertFalse(n_plus_one[0]["detected"])
        self.assertNotIn("sql_n_plus_one", report["detected"])

    def test_an_injected_sql_n_plus_one_is_detected(self):
        _rc, report = self._detect(
            self._jsonl(self._ladder(lambda size: size * size)), "candidate")
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertTrue(finding["detected"])
        self.assertGreater(finding["per_unit_at_max"], finding["per_unit_at_min"])
        # a finding without its numbers is not a finding
        self.assertEqual([1, 10, 100], finding["sizes"])
        self.assertEqual("measured", finding["evidence"])
        self.assertIn("sql_n_plus_one", report["detected"])

    def _size_ladder(self, statements_for, arm="candidate", samples=1):
        """The ladder the Django bench actually writes: sizes grow, samples do not.

        One fire over a 1000-row backlog produces ONE timing and a thousand
        statements, so a detector that keyed its ladder on the sample count would
        see one rung and stay silent about a per-row cost - which is exactly the
        shape the real bench suite produced for ``housekeeping.system``.
        """
        records = []
        for size in (1, 100, 1000):
            records.append(build_record(
                self.tmp.name, arm=arm, repeat=1, records=size,
                units=[unit()] * samples,
                sql={"statements": {"value": statements_for(size),
                                    "evidence": "measured"}}))
        return records

    def test_a_per_row_cost_shows_on_a_ladder_of_one_sample_per_rung(self):
        """The regression the first real run found, kept as a test.

        ``records`` is the size of the workload; the sample count is not. With an
        expectation of one statement per row, a cost that grows faster than that
        is named even though every rung carries a single timing.
        """
        _rc, report = self._detect(
            self._jsonl(self._size_ladder(lambda size: 1 + size)), "candidate",
            extra=["--expected-statements-per-unit", "1"])
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertEqual([1, 100, 1000], finding["sizes"],
                         "the ladder is the workload size, not the sample count")
        self.assertAlmostEqual(1.0, finding["slope"], places=3)
        self.assertFalse(
            finding["detected"],
            "one statement per row is the reviewed contract, not a defect")

    def test_a_second_statement_per_row_is_an_n_plus_one_at_any_sample_count(self):
        _rc, report = self._detect(
            self._jsonl(self._size_ladder(lambda size: 1 + 2 * size)),
            "candidate", extra=["--expected-statements-per-unit", "1"])
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertTrue(finding["detected"])
        self.assertAlmostEqual(1.0, finding["excess_per_unit"], places=3)

    def test_a_per_row_cost_is_not_cleared_by_a_falling_per_unit_figure(self):
        """The exact shape the first real run produced, kept as a test.

        A fixed cost plus a per-row cost divided by a growing size *falls*: the
        first real ``housekeeping.system`` ladder read 2.29 statements per row at
        one row and 0.15 at a thousand, and a detector comparing those two
        numbers called a genuine per-row injection flat. The totals say
        otherwise - the slope is the reading, and the falling per-unit figure is
        reported beside it rather than being the verdict.
        """
        _rc, report = self._detect(
            self._jsonl(self._size_ladder(lambda size: 1000 + 2 * size)),
            "candidate", extra=["--expected-statements-per-unit", "1"])
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertLess(finding["per_unit_at_max"], finding["per_unit_at_min"],
                        "per-unit falls, which is what fooled the first version")
        self.assertAlmostEqual(2.0, finding["slope"], places=3)
        self.assertTrue(finding["detected"],
                        "two statements per row over a contract of one is the N+1")

    def test_super_linear_growth_is_named_without_an_expectation(self):
        """Quadratic growth cannot be legitimate per-unit work, so it needs no input."""
        _rc, report = self._detect(
            self._jsonl(self._size_ladder(lambda size: 1 + size * size)),
            "candidate")
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertTrue(finding["superlinear"])
        self.assertIn("sql_n_plus_one", report["detected"])

    def test_a_failing_repeat_does_not_average_a_per_row_cost_away(self):
        """Five empty repeats of a rung do not make a per-row cost disappear.

        A statement count is a property of the workload; the repeat which found
        the backlog is the one that shows its shape. Averaging the runs which
        found an empty table into the verdict is a false green.
        """
        records = []
        for size in (1, 100, 1000):
            for repeat in range(1, 5):
                paid = 1 + 3 * size if repeat == 1 else 1
                records.append(build_record(
                    self.tmp.name, arm="candidate", repeat=repeat, records=size,
                    units=[unit()],
                    sql={"statements": {"value": paid, "evidence": "measured"}}))
        _rc, report = self._detect(self._jsonl(records), "candidate",
                                   extra=["--expected-statements-per-unit", "1"])
        finding = self._finding(report, "sql_n_plus_one")[0]
        self.assertTrue(finding["detected"],
                        "the repeat which did the work decides the shape")
        self.assertEqual(4, finding["repeats_at_max"])

    def test_a_second_budget_is_applied_per_scale_cell(self):
        """A budget names one workload; it may not be charged to a bigger one.

        The 1000-record rung of a family legitimately costs more than its
        1-record rung. Pooling the two and comparing the pool to a budget set for
        the small cell reports the size of the workload as a defect.
        """
        small = build_record(self.tmp.name, arm="baseline", repeat=1,
                             records=1, units=[unit(active=0.01)] * 25)
        large = build_record(self.tmp.name, arm="baseline", repeat=1,
                             records=1000, units=[unit(active=5.0)] * 25)
        _rc, report = self._detect(self._jsonl([small, large]), "baseline",
                                   extra=["--slow-body-seconds", "1"])
        verdicts = {finding["records"]: finding["detected"]
                    for finding in self._finding(report, "slow_task_body")}
        self.assertEqual({1: False, 1000: True}, verdicts)

    def _body_pair(self, baseline_active, arm_active, arm="candidate",
                   budget="1000", records=1000, scale="large"):
        """A cell and its baseline, timed, for a second budget far above both."""
        base = build_record(self.tmp.name, arm="baseline", repeat=1,
                            records=records, scale=scale,
                            units=[unit(active=baseline_active)] * 25)
        cand = build_record(self.tmp.name, arm=arm, repeat=1, records=records,
                            scale=scale, units=[unit(active=arm_active)] * 25)
        return self._jsonl([base, cand]), ["--slow-body-seconds", budget]

    def test_a_body_doubled_below_its_budget_is_a_regression(self):
        """What the fixed 0.05 s burn of the bench suite could never show.

        An absolute budget is a ceiling a human set, so a burn below it passes
        while having doubled the task's own runtime - the real run measured a
        50 ms injection on a 4.2 s chunk at 1.03x and called it clean. The
        regression a pull request introduces is RELATIVE to what the task cost
        before, so the same cell's baseline arm decides alongside the budget.
        """
        path, extra = self._body_pair(0.020, 0.060)
        _rc, report = self._detect(path, "candidate", extra=extra)
        finding = self._finding(report, "slow_task_body")[0]
        self.assertTrue(finding["detected"],
                        "3x the same cell of the baseline is a regression")
        self.assertAlmostEqual(3.0, finding["ratio_to_baseline"], places=1)
        self.assertEqual(1000.0, finding["budget_seconds"],
                         "the budget was nowhere near reached")
        self.assertIn("slow_task_body", report["detected"])

    def test_a_body_which_grew_within_noise_is_not_a_regression(self):
        """1.1x of a chunk is a busy runner; 2x of a millisecond is the noise floor."""
        path, extra = self._body_pair(4.2, 4.2 * 1.1)
        _rc, report = self._detect(path, "candidate", extra=extra)
        self.assertNotIn("slow_task_body", report["detected"])
        path, extra = self._body_pair(0.0005, 0.0012)
        _rc, report = self._detect(path, "candidate", extra=extra)
        finding = self._finding(report, "slow_task_body")[0]
        self.assertGreater(finding["ratio_to_baseline"], task_perf_bench.SLOW_BODY_RATIO)
        self.assertFalse(finding["detected"],
                         "doubling of a sub-millisecond body is below the floor")

    def test_a_slow_body_of_one_family_is_not_measured_against_another(self):
        """Why the arm is judged one family at a time.

        A run without ``--family`` holds every family of the run. Fitting one
        slope over all of them asks how the cost of a probe grows with the size
        of an import chunk, and pooling the durations reads the slowest family
        as the shape of all of them - which flagged four clean arms at once.
        """
        rows = []
        for family, base, cand in (("harvesting.import_chunk", 4.2, 4.4),
                                   ("monitoring.wms", 0.02, 0.09)):
            for arm, active in (("baseline", base), ("candidate", cand)):
                record = build_record(self.tmp.name, arm=arm, repeat=1,
                                      records=100, scale="large", units=[
                                          unit(active=active)] * 25)
                record["family"] = family
                record["digest"] = task_perf_bench.workload_digest(record)
                rows.append(record)
        path = self._jsonl(rows)
        _rc, report = self._detect(path, "candidate",
                                   extra=["--slow-body-seconds", "1000"])
        slow = {finding["family"]: finding["detected"]
                for finding in self._finding(report, "slow_task_body")}
        self.assertEqual({"harvesting.import_chunk": False,
                          "monitoring.wms": True}, slow,
                         "each family is judged against its own baseline")
        self.assertEqual(2, len(slow),
                         "every family of the arm is reported, none pooled away")

    def test_a_duplicate_which_duplicates_at_every_size_needs_the_baseline(self):
        """The reading the real ``harvesting.fan_out`` run forced.

        A call duplicated at every rung is LINEAR: 1 call at 50 records, 2 at
        5000. No slope sees it and a per-unit expectation only sees it if the
        caller happens to know the legitimate count. The workload's own baseline
        arm knows it, because that arm is what the same task costs when it is
        correct - so a doubling against it is the duplicate.
        """
        records = []
        for arm, calls in (("baseline", 1), ("duplicate-remote-call", 2)):
            for size in (50, 5000):
                record = build_record(self.tmp.name, arm=arm, repeat=1,
                                      records=size, units=[unit()] * 2)
                record["http"] = {"calls": {"value": calls,
                                            "evidence": "measured"}}
                record["digest"] = task_perf_bench.workload_digest(record)
                records.append(record)
        path = self._jsonl(records)
        _rc, clean = self._detect(path, "baseline")
        _rc, dup = self._detect(path, "duplicate-remote-call")
        finding = self._finding(dup, "duplicate_remote_call")[0]
        self.assertFalse(any(f["detected"] for f in clean["findings"]),
                         "the clean arm is clean")
        self.assertTrue(finding["detected"])
        self.assertEqual(1.0, finding["baseline_total_at_max"])
        self.assertEqual(2.0, finding["total_at_max"])
        self.assertIn("duplicate_remote_call", dup["detected"])

    def test_more_calls_than_the_baseline_are_not_a_duplicate_when_not_doubled(self):
        """A retry also makes more calls; only the doubling signature counts."""
        records = []
        for arm, calls in (("baseline", 10), ("candidate", 15)):
            for size in (50, 5000):
                record = build_record(self.tmp.name, arm=arm, repeat=1,
                                      records=size, units=[unit()] * 2)
                record["http"] = {"calls": {"value": calls,
                                            "evidence": "measured"}}
                record["digest"] = task_perf_bench.workload_digest(record)
                records.append(record)
        _rc, report = self._detect(self._jsonl(records), "candidate")
        self.assertNotIn("duplicate_remote_call", report["detected"],
                         "1.5x is a retry, 2x is a duplicate")

    def test_a_duplicate_remote_call_is_detected_against_its_expectation(self):
        records = []
        for size in (1, 10, 100):
            record = build_record(self.tmp.name, arm="candidate", repeat=1,
                                  records=size, units=[unit()] * size)
            record["http"] = {"calls": {"value": 2 * size,
                                        "evidence": "measured"}}
            record["digest"] = task_perf_bench.workload_digest(record)
            records.append(record)
        _rc, report = self._detect(self._jsonl(records), "candidate",
                                   extra=["--expected-http-per-unit", "1"])
        finding = self._finding(report, "duplicate_remote_call")[0]
        self.assertTrue(finding["detected"])
        self.assertEqual(1, finding["expected_per_unit"])
        self.assertAlmostEqual(1.0, finding["excess_per_unit"], places=6)

    def test_a_single_remote_call_per_unit_is_not_a_duplicate(self):
        records = []
        for size in (1, 10, 100):
            record = build_record(self.tmp.name, arm="candidate", repeat=1,
                                  records=size, units=[unit()] * size)
            record["http"] = {"calls": {"value": size, "evidence": "measured"}}
            record["digest"] = task_perf_bench.workload_digest(record)
            records.append(record)
        _rc, report = self._detect(self._jsonl(records), "candidate",
                                   extra=["--expected-http-per-unit", "1"])
        self.assertNotIn("duplicate_remote_call", report["detected"])

    def test_a_slow_task_body_is_detected_against_a_budget(self):
        slow = [build_record(self.tmp.name, arm="slow-body", repeat=index,
                             units=[unit(active=5.0)] * 30)
                for index in range(1, 4)]
        fast = [build_record(self.tmp.name, arm="baseline", repeat=index)
                for index in range(1, 4)]
        path = self._jsonl(slow + fast)
        _, slow_report = self._detect(path, "slow-body",
                                      extra=["--slow-body-seconds", "1"])
        _, fast_report = self._detect(path, "baseline",
                                      extra=["--slow-body-seconds", "1"])
        self.assertIn("slow_task_body", slow_report["detected"])
        self.assertNotIn("slow_task_body", fast_report["detected"])
        finding = self._finding(slow_report, "slow_task_body")[0]
        self.assertEqual(3 * 30, finding["n"],
                         "the sample size of the whole arm travels with it")
        self.assertEqual("p95", finding["percentile"])

    def test_queue_wait_is_reported_apart_from_the_body(self):
        """A message which waited is not a slow task (#1330)."""
        records = [build_record(self.tmp.name, arm="baseline", repeat=index,
                                units=[unit(active=0.05, wait=30.0)] * 30)
                   for index in range(1, 4)]
        _rc, report = self._detect(self._jsonl(records), "baseline",
                                   extra=["--slow-body-seconds", "1"])
        kinds = {finding["kind"] for finding in report["findings"]}
        self.assertIn("queue_wait_inflation", kinds)
        self.assertNotIn("slow_task_body", report["detected"],
                         "the wait must not be blamed on the body")
        wait = self._finding(report, "queue_wait_inflation")[0]
        self.assertGreater(wait["queue_p50_seconds"],
                           wait["active_p50_seconds"])
        self.assertIn("apart", wait["note"])

    def test_a_detector_without_its_input_says_nothing_instead_of_guessing(self):
        """One rung of the ladder cannot state a slope; the arm stays silent."""
        records = [build_record(self.tmp.name, arm="baseline", repeat=1)]
        _rc, report = self._detect(self._jsonl(records), "baseline")
        self.assertEqual([], self._finding(report, "sql_n_plus_one"))

    def test_fail_on_is_the_opt_in_ci_seam(self):
        path = self._jsonl(self._ladder(lambda size: size * size))
        rc, _report = self._detect(path, "candidate", extra=["--fail-on"])
        self.assertEqual(1, rc)
        rc, _report = self._detect(path, "candidate")
        self.assertEqual(0, rc,
                         "detection is a report unless it is asked to fail")

    def test_detect_can_write_its_finding_report(self):
        path = self._jsonl(self._ladder(lambda size: size * size))
        out = os.path.join(self.tmp.name, "findings.json")
        self._detect(path, "candidate", extra=["--out", out])
        with open(out, encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual("detect", written["kind"])
        self.assertIn("sql_n_plus_one", written["detected"])


# ------------------------------------------------------------------------ CLI I/O


class CliContractTest(unittest.TestCase):
    """The artifacts other tools read must stay exactly parseable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fixture = write_fixture(self.tmp.name, workload())

    def test_load_writes_one_canonical_line_per_fixture(self):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main([
                "load", "--arm", "baseline", "--seed", "20261121",
                "--fixture", self.fixture, "--revision", "abc1234"])
        self.assertEqual(0, rc)
        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(1, len(lines),
                         "a human summary in stdout would corrupt the artifact")
        record = json.loads(lines[0])
        self.assertEqual("mrmap.task-perf.v1", record["schema"])
        self.assertEqual("abc1234", record["revision"])
        self.assertIn("family=harvesting.import_chunk", err.getvalue())

    def test_load_appends_every_fixture_of_a_directory_in_order(self):
        directory = os.path.join(self.tmp.name, "fixtures")
        os.makedirs(directory)
        for name in ("b.json", "a.json"):
            write_fixture(directory, workload(scale=name), name)
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            task_perf_bench.main(["load", "--arm", "baseline", "--seed", "1",
                                  "--fixture-dir", directory])
        scales = [json.loads(line)["scale"]
                  for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(["a.json", "b.json"], scales)

    def test_record_revalidates_what_a_runner_produced(self):
        record = build_record(self.tmp.name)
        path = os.path.join(self.tmp.name, "one.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        broken = dict(record)
        broken.pop("seed")
        broken_path = os.path.join(self.tmp.name, "broken.json")
        with open(broken_path, "w", encoding="utf-8") as handle:
            json.dump(broken, handle)
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main(["record", "--in", path, "--out",
                                       os.path.join(self.tmp.name, "all.jsonl")])
        self.assertEqual(0, rc)
        with self.assertRaises(SystemExit):
            task_perf_bench.main(["record", "--in", broken_path])

    def test_load_needs_a_workload_to_read(self):
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.main(["load", "--arm", "baseline", "--seed", "1"])
        self.assertIn("--fixture", str(caught.exception))

    def test_an_unknown_family_on_the_command_line_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            task_perf_bench.main(["load", "--arm", "baseline", "--seed", "1",
                                  "--family", "harvesting.nope",
                                  "--fixture", self.fixture])
        self.assertIn("harvesting.nope", str(caught.exception))

    def test_the_aggregate_knobs_land_in_the_right_block(self):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            task_perf_bench.main([
                "load", "--arm", "baseline", "--seed", "1",
                "--fixture", self.fixture, "--sql-ms", "120.5",
                "--sql-count", "42", "--http-calls", "3",
                "--outliers", '{"import_backlog_stall": 1}', "--retry", "2",
                "--abandoned", "1", "--retained-truncated", "--worker-loss", "1"])
        record = json.loads(out.getvalue())
        self.assertEqual(120.5, record["sql"]["total_ms"]["value"])
        self.assertEqual(42, record["sql"]["statements"]["value"])
        self.assertEqual(3, record["http"]["calls"]["value"])
        self.assertEqual({"import_backlog_stall": 1},
                         record["pressure"]["outliers"])
        self.assertEqual(2, record["outcomes"]["retry"]["count"])
        self.assertEqual(1, record["uncertain"]["abandoned"]["count"])
        self.assertTrue(record["quality"]["retention_truncated"])
        self.assertIn("retention_note", record["quality"])
        task_perf_bench.validate_record(record, source="test")

    def test_an_outlier_blob_must_be_a_json_object(self):
        with self.assertRaises(SystemExit):
            task_perf_bench.main(["load", "--arm", "baseline", "--seed", "1",
                                  "--fixture", self.fixture,
                                  "--outliers", "[1,2]"])

    def test_the_environment_is_documented_not_invented(self):
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            task_perf_bench.main(["load", "--arm", "baseline", "--seed", "1",
                                  "--fixture", self.fixture, "--postgis",
                                  "18-3.6", "--cpu", "EPYC", "--cores", "8",
                                  "--cgroup-limit", str(4 * 1024 ** 3)])
        environment = json.loads(out.getvalue())["environment"]
        self.assertEqual("18-3.6", environment["postgis"])
        self.assertEqual("EPYC", environment["cpu"])
        self.assertEqual(8, environment["cores"])
        self.assertEqual(4 * 1024 ** 3, environment["cgroup_limit_bytes"])
        self.assertIn("platform", environment)

    def test_the_cgroup_limit_reader_prefers_v2_and_ignores_the_v1_sentinel(self):
        def fake_open(target, *args, **kwargs):
            class Handle:
                def __enter__(self):
                    return self

                def __exit__(self, *_exc):
                    return False

                def read(self):
                    if target.endswith("memory.max"):
                        return "max\n"
                    return "9223372036854771712\n"
            return Handle()

        with mock.patch("builtins.open", side_effect=fake_open):
            self.assertIsNone(task_perf_bench.read_first_cgroup_limit())

        def fake_open_real(target, *args, **kwargs):
            class Handle:
                def __enter__(self):
                    return self

                def __exit__(self, *_exc):
                    return False

                def read(self):
                    return "4294967296" if target.endswith("memory.max") else "0"
            return Handle()

        with mock.patch("builtins.open", side_effect=fake_open_real):
            self.assertEqual(4294967296,
                             task_perf_bench.read_first_cgroup_limit())

    def _jsonl(self, records, name="perf.jsonl"):
        return write_records(os.path.join(self.tmp.name, name), records)

    def test_summary_prints_one_line_per_cell_with_its_ratio(self):
        records = ([build_record(self.tmp.name, arm="baseline", repeat=index)
                    for index in range(1, 4)]
                   + [build_record(self.tmp.name, arm="sql-n-plus-one",
                                   repeat=index,
                                   units=[unit(active=1.5)] * 30)
                      for index in range(1, 4)])
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main(["summary", "--in",
                                       self._jsonl(records)])
        self.assertEqual(0, rc)
        lines = [line for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(2, len(lines),
                         "one line per (family, scale, arm), not per repeat")
        candidate = [line for line in lines if "sql-n-plus-one" in line][0]
        self.assertIn("x3.0 over baseline", candidate)
        baseline = [line for line in lines if "baseline " in line][0]
        self.assertIn("against no baseline arm", baseline,
                      "the baseline is not compared against itself")

    def test_summary_marks_a_detection_on_its_cell(self):
        records = []
        for size in (1, 10, 100):
            records.append(build_record(
                self.tmp.name, arm="candidate", repeat=1, records=size,
                units=[unit()] * size,
                sql={"statements": {"value": size * size,
                                    "evidence": "measured"}}))
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            task_perf_bench.main(["summary", "--in", self._jsonl(records)])
        printed = out.getvalue() + err.getvalue()
        self.assertIn("DETECTED: sql_n_plus_one", printed)

    def test_summary_can_write_its_artifact_and_fail_on_a_detection(self):
        records = [build_record(self.tmp.name, arm="baseline", repeat=index,
                                units=[unit(active=5.0)] * 30)
                   for index in range(1, 4)]
        path = os.path.join(self.tmp.name, "summary.txt")
        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = task_perf_bench.main(["summary", "--in",
                                       self._jsonl(records), "--out", path,
                                       "--fail-on", "--slow-body-seconds", "1"])
        self.assertEqual(1, rc, "--fail-on is the opt-in CI seam here too")
        with open(path, encoding="utf-8") as handle:
            self.assertIn("slow_task_body", handle.read())

    def test_summary_refuses_an_unmatched_selection(self):
        records = [build_record(self.tmp.name)]
        with self.assertRaises(SystemExit):
            task_perf_bench.main(["summary", "--in", self._jsonl(records),
                                  "--family", "monitoring.wms"])

    def test_families_lists_the_first_party_workloads(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = task_perf_bench.main(["families"])
        printed = out.getvalue()
        self.assertEqual(0, rc)
        for family in ("harvesting.import_chunk", "harvesting.fan_out",
                       "monitoring.wms", "monitoring.wfs", "monitoring.csw",
                       "monitoring.artifact_purge", "update.wms", "update.wfs",
                       "update.csw", "update.sweep", "housekeeping.system",
                       "housekeeping.notify", "security.log_analysis",
                       "validation"):
            self.assertIn(family, printed)
        for retired in ("conformity", "etf", "inspire_atlas"):
            self.assertNotIn(retired, printed,
                             "the retired legacy conformity tasks (#1527/#1458/"
                             "#1530) have no task left to benchmark")

    def test_a_bench_module_names_only_declared_families(self):
        """The generator and the analyzer agree on the family vocabulary."""
        with open(BENCH_SUPPORT, encoding="utf-8") as handle:
            support = handle.read()
        bench_file = os.path.join(
            REPO_ROOT, "backend", "tests", "django", "system",
            "test_task_runtime_bench.py")
        with open(bench_file, encoding="utf-8") as handle:
            bench = handle.read()
        import ast
        tree = ast.parse(bench)
        families = {node.value.value for node in ast.walk(tree)
                    if isinstance(node, ast.Assign)
                    for target in node.targets
                    if isinstance(target, ast.Name) and target.id == "family"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is not None}
        self.assertTrue(families)
        self.assertTrue(families.issubset(set(task_perf_bench.FAMILIES)),
                        "a bench family the analyzer does not know would be "
                        "refused by validate_record")
        self.assertIn("WORKLOAD_KEYS", support)

    def test_workload_keys_match_the_generator(self):
        """The digest is computed on both sides; both must hash the same keys."""
        import ast
        with open(BENCH_SUPPORT, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        keys = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name)
                    and target.id == "WORKLOAD_KEYS" for target in node.targets):
                keys = tuple(node.value.elts)
        self.assertIsNotNone(keys, "the generator must name its workload keys")
        self.assertEqual(list(task_perf_bench.WORKLOAD_KEYS),
                         [key.value for key in keys])

    def test_the_nightly_workflow_reports_and_never_gates(self):
        """The other half of "nonflaky CI performance regression reports".

        The report is the product of the nightly; a verdict is not. Two properties
        keep it nonflaky, and both are worth a red test rather than a review note:

        * it never triggers on ``pull_request`` - medians measured on a shared
          runner belong to the neighbour, and a threshold tuned on a quiet machine
          reddens on a busy one, which is the flakiness #1396 is about;
        * the artifact upload says ``if-no-files-found: error`` - an empty artifact
          is a nightly that measured nothing and looked like it did.
        """
        path = os.path.join(REPO_ROOT, ".github", "workflows",
                            "task-performance.yml")
        with open(path, encoding="utf-8") as handle:
            workflow = handle.read()
        self.assertNotIn("pull_request:", workflow,
                         "a per-PR performance check on a shared runner is the "
                         "flaky red the issue asks to avoid")
        self.assertIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertIn("--mode warn", workflow)
        self.assertNotIn("--mode block", workflow,
                         "no mandatory gate exists until a human approves one "
                         "in the baseline file, not in a workflow")
        self.assertIn("contents: read", workflow)
        for artifact in ("task-perf.jsonl", "report.txt", "summary.txt"):
            self.assertIn(artifact, workflow,
                          "the report a reviewer reads without re-running is "
                          "the artifact")

    def test_the_runner_holds_the_detect_invocation_the_workflow_shares(self):
        """CI holds a call and no logic, so the logic has to be in the script.

        If the four arms were detected in YAML the documented local invocation and
        the CI one would be two different measurements - and if the verdict line
        were thrown away, `detected=none` would be readable only in a file after
        the job was already green.
        """
        path = os.path.join(REPO_ROOT, "scripts", "task_perf_runner.sh")
        with open(path, encoding="utf-8") as handle:
            runner = handle.read()
        for arm in ("baseline", "sql-n-plus-one", "duplicate-remote-call",
                    "slow-body"):
            self.assertIn(arm, runner)
        self.assertIn("detect-$arm.json", runner)
        self.assertIn("detect-$arm.txt", runner,
                      "the verdict belongs on the console, not only in an artifact")
        self.assertIn("--mode warn", runner)
        # the flag has to be absent from the INVOCATION; the header explains at
        # length why it is absent, and that prose is the reason it stays absent
        invoked = [line for line in runner.splitlines()
                   if not line.lstrip().startswith("#")]
        self.assertTrue(any("--keepdb" in line for line in invoked))
        self.assertFalse(any("--parallel" in line for line in invoked),
                         "four Django workers on one PostGIS measure contention, "
                         "not the task")

    def test_every_declared_contract_is_measured(self):
        """A contract is a claim about a workload, so a run must be able to check it.

        A family the analyzer has expectations for but the bench suite never runs
        would report `detected=none` for a defect nobody measured - the false
        green the registry exists to prevent, arriving from the other side.
        """
        bench_file = os.path.join(
            REPO_ROOT, "backend", "tests", "django", "system",
            "test_task_runtime_bench.py")
        with open(bench_file, encoding="utf-8") as handle:
            bench = handle.read()
        for family, spec in task_perf_bench.FAMILIES.items():
            if spec.get("contract"):
                self.assertIn(family, bench,
                              "%s carries a detector contract no workload measures"
                              % family)

    def test_end_to_end_through_subprocesses(self):
        """load -> report -> compare -> gate as CI calls them."""
        out_dir = self.tmp.name
        jsonl = os.path.join(out_dir, "perf.jsonl")
        for arm, active in (("baseline", 0.5), ("sql-n-plus-one", 1.4)):
            for repeat in range(1, 8):
                fixture = write_fixture(
                    out_dir,
                    workload(units=[unit(active=active)] * 30),
                    "wl-%s-%s.json" % (arm, repeat))
                subprocess.run(  # nosec B603 B607 - this repository's own tool
                    [sys.executable, SCRIPT, "load", "--arm", arm, "--seed",
                     "20261121", "--repeat", str(repeat), "--fixture", fixture,
                     "--out", jsonl, "--revision", "abc1234"],
                    check=True, capture_output=True)
        report = subprocess.run(  # nosec B603 - repository's own tool
            [sys.executable, SCRIPT, "report", "--in", jsonl],
            check=True, capture_output=True, text=True)
        self.assertIn("sql-n-plus-one", report.stdout)
        verdict = subprocess.run(  # nosec B603 - repository's own tool
            [sys.executable, SCRIPT, "compare", "--in", jsonl, "--baseline",
             "baseline", "--candidate", "sql-n-plus-one"],
            check=True, capture_output=True, text=True)
        parsed = json.loads(verdict.stdout)
        self.assertAlmostEqual(2.8, parsed["metrics"]["active_p50"]["ratio"],
                               delta=0.1)
        gate = subprocess.run(  # nosec B603 - repository's own tool
            [sys.executable, SCRIPT, "gate", "--in", jsonl, "--baseline",
             os.path.join(REPO_ROOT, "scripts", "task_perf_baseline.json")],
            check=True, capture_output=True, text=True)
        self.assertIn("gate mode=warn", gate.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
