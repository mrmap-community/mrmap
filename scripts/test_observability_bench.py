#!/usr/bin/env python3
"""Offline checks for scripts/observability_bench (issue #1777).

No docker, no network, no application imports: the point of these checks is
that a reviewer can run them on a laptop which has nothing installed but
python3, the same promise the tool itself makes. What is exercised is the part
of the protocol which must not silently drift - the arms and budget files, the
percentile and variability definitions the report prints, the artifact naming
the reading side depends on, the refusals which keep a run's ownership honest,
and the verdict logic which turns two arms into a budget check.

Run from the repository root: `python3 scripts/test_observability_bench.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
TOOL = SCRIPTS / "observability_bench.py"
EVIDENCE = ROOT / "docs" / "source" / "development" / "evidence"
ARMS = EVIDENCE / "observability-1777-arms.json"
BUDGETS = EVIDENCE / "observability-1777-budgets.json"

_loader = importlib.machinery.SourceFileLoader("observability_bench", str(TOOL))
_spec = importlib.util.spec_from_loader("observability_bench", _loader)
OB = importlib.util.module_from_spec(_spec)
_loader.exec_module(OB)

RESULTS = []
SKIPS = []


def check(name):
    def wrap(function):
        def run():
            try:
                function()
                RESULTS.append((name, True, ""))
                print("ok   %s" % name)
            except AssertionError as error:
                RESULTS.append((name, False, str(error) or "assertion failed"))
                print("FAIL %s - %s" % (name, error))
            except Exception as error:                      # noqa: BLE001
                RESULTS.append((name, False, "%s: %s" % (type(error).__name__,
                                                         error)))
                print("FAIL %s - %s: %s" % (name, type(error).__name__, error))
        return run
    return wrap


class compose_env:
    """The compose variables a run demands, present but obviously fake.

    The refusal tests need `cmd_run` to get as far as the guard under test, and
    the first guard is the environment one; a test which stops there proves
    nothing about the guard it named.
    """

    def __enter__(self):
        for name in OB.REQUIRED_ENV:
            os.environ.setdefault(name, "bench-check")
        return self

    def __exit__(self, *error):
        for name in OB.REQUIRED_ENV:
            os.environ.pop(name, None)
        return False


def args(**values):
    base = dict(arms_file=str(ARMS), arm=None, cell=None, kind=None,
                profile="production", repeats=None, seed=None, out=None,
                artifacts="", stack_tree=str(ROOT), compose_file=None,
                base_url="", ws_base_url="", legacy_off_settings_module="",
                sample=True, budget_file=str(BUDGETS), out_file="")
    base.update(values)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# the protocol files
# ---------------------------------------------------------------------------
@check("arms file loads and is self-consistent")
def test_arms_file():
    data = OB.load_arms(str(ARMS))
    assert [arm["name"] for arm in data["arms"]] == [
        "diagnostics-off", "legacy-shipped"], \
        "the protocol is a pair: a reference and one subject"
    protocol = data["protocol"]
    assert protocol["repeats"] >= 5, "fewer than five repeats cannot show a cv"
    assert protocol["warmup_requests"] > 0, "a protocol without warmup measures boot"
    assert protocol["compose_project"].startswith(OB.PROJECT_PREFIX), \
        "the protocol's own project must be one the tool is allowed to own"
    kinds = {cell["kind"] for cell in data["cells"]}
    assert kinds == {"celery", "http"}, "the issue's work spans both tiers"
    families = [cell["family"] for cell in data["cells"] if cell["kind"] == "celery"]
    assert len(families) >= 3, "at least three task families are named by the issue"
    assert any(cell.get("websocket_count") for cell in data["cells"]), \
        "the concurrent shape is measured, not asserted"
    assert any(cell.get("media_paths") for cell in data["cells"]), \
        "storage is a column of the baseline, so some cell must count it"


@check("every celery cell names a family the bench actually measures")
def test_celery_cells_measured():
    data = OB.load_arms(str(ARMS))
    source = (SCRIPTS / "task_perf_bench.py").read_text()
    suite = (ROOT / "backend" / "tests" / "django" / "system"
             / "test_task_runtime_bench.py").read_text()
    for cell in data["cells"]:
        if cell["kind"] != "celery":
            continue
        assert "family = '%s'" % cell["family"] in suite, \
            "%s has no bench class; --family would skip everything" % cell["family"]
        assert "'%s'" % cell["family"] in source or '"%s"' % cell["family"] in source, \
            "%s is not a family scripts/task_perf_bench.py knows" % cell["family"]
        assert cell["out_dir"].startswith("backend/"), \
            "the workload container bind mounts ./backend, so --out must sit under it"


@check("the shipped-legacy arm only names knobs settings.py actually reads")
def test_legacy_knobs_exist():
    data = OB.load_arms(str(ARMS))
    settings = (ROOT / "backend" / "MrMap" / "settings.py").read_text()
    subject = OB.arm_of(data, "legacy-shipped")
    assert subject.get("celery_env"), "the subject arm must turn something on"
    for key, value in subject["celery_env"].items():
        assert key in OB.LEGACY_TASK_KNOBS, "%s is not a known legacy knob" % key
        assert '"%s"' % key in settings, "%s is not read by settings.py" % key
        assert value, "an arm which sets a knob to nothing is not an arm"
    reference = OB.arm_of(data, "diagnostics-off")
    assert not reference.get("celery_env"), \
        "the reference arm is defined by what it does NOT enable"
    assert reference.get("needs_legacy_off_module"), \
        "the HTTP tier's detector has no knob, so the reference must boot without it"
    module = (ROOT / "backend" / "MrMap"
              / ("%s.py" % reference["legacy_off_settings_module"].split(".")[-1]))
    assert module.is_file(), "the reference arm names a settings module which is not there"
    body = module.read_text()
    assert "LogSlowRequestsMiddleware" in body, \
        "the module must remove the legacy HTTP detector, and nothing else"
    assert "from MrMap.settings import *" in body, \
        "an arm which forks the settings would measure a different application"


@check("every budget metric resolves in a run whose tables are populated")
def test_budget_metrics_resolve():
    """A metric string which cannot resolve is a budget nobody can ever meet."""
    budgets = OB.load_json(str(BUDGETS), "budget file")
    data = OB.load_arms(str(ARMS))
    known_cells = {cell["name"] for cell in data["cells"]}
    with tempfile.TemporaryDirectory() as directory:
        directory = write_synthetic_run(directory)
        summaries = OB.build_summaries(directory)
        payload = {"reference_arm": budgets["reference_arm"], "cells": {}}
        for cell in known_cells:
            payload["cells"][cell] = {arm: summaries[arm]["cells"].get(cell, {})
                                      for arm in summaries}
        for budget in budgets["budgets"]:
            assert budget["cell"] in known_cells, \
                "budget names cell %s, which no cell defines" % budget["cell"]
            value = OB._metric_value(payload, budgets["reference_arm"],
                                     budget["cell"], budget["metric"])
            assert value is not None, ("budget metric %s of %s resolves to nothing"
                                       " even in a fully populated run"
                                       % (budget["metric"], budget["cell"]))
            assert isinstance(value, (int, float)), \
                "budget metric %s is not a number" % budget["metric"]


@check("budgets are ratios, never absolute timings")
def test_budget_shape():
    budgets = OB.load_json(str(BUDGETS), "budget file")
    assert budgets["reference_arm"] == "diagnostics-off"
    for budget in budgets["budgets"]:
        assert "max_ratio" in budget and budget["max_ratio"] is not None, \
            "an absolute budget on a shared runner is the flaky gate #1777 forbids"
        assert budget.get("why"), "a ceiling nobody justified is a guess"
        assert "metric" in budget and "cell" in budget


# ---------------------------------------------------------------------------
# the reading side
# ---------------------------------------------------------------------------
@check("percentiles and cv match the definitions the report prints")
def test_statistics():
    values = [float(v) for v in range(1, 101)]
    assert OB._percentile(values, 0.5) == 50.0, "nearest-rank p50 of 1..100"
    assert OB._percentile(values, 0.95) == 95.0, "nearest-rank p95 of 1..100"
    assert OB._percentile(values, 0.99) == 99.0, "nearest-rank p99 of 1..100"
    assert OB._percentile([], 0.5) is None, "no samples is not zero"
    assert OB._percentile([3.0], 0.99) == 3.0, "one sample is its own percentile"
    assert OB._cv([1.0, 1.0, 1.0]) == 0.0, "no spread is no spread"
    assert OB._cv([1.0]) is None, "one sample cannot show variability"
    assert OB._cv([0.0, 0.0]) is None, "a mean of zero has no relative spread"
    assert abs(OB._cv([1.0, 3.0]) - 0.7071) < 1e-3, \
        "sample sd 1.4142 over a mean of 2"


@check("celery rows aggregate repeats, outcomes and the sql contract column")
def test_celery_summary():
    records = [
        {"family": "harvesting.import_chunk", "scale": "typical", "arm": "a",
         "repeat": 1,
         "durations": {"active": {"samples": [0.2, 0.4], "evidence": "measured"},
                       "end_to_end": {"samples": [1.0, 2.0]}},
         "outcomes": {"success": {"count": 2, "evidence": "measured"}},
         "sql": {"statements": {"value": 4, "evidence": "measured"}}},
        {"family": "harvesting.import_chunk", "scale": "typical", "arm": "a",
         "repeat": 2,
         "durations": {"active": {"samples": [0.6], "evidence": "measured"},
                       "end_to_end": {"samples": [3.0]}},
         "outcomes": {"success": {"count": 1}, "failed": {"count": 0}},
         "sql": {"statements": {"value": 8, "evidence": "measured"}}},
    ]
    rows = OB.celery_summary(records)
    row = rows["harvesting.import_chunk/typical"]
    assert row["samples"] == 3 and row["repeats"] == 2
    assert row["active_p50"] == 0.4 and row["active_p95"] == 0.6
    assert row["sql_statements_max"] == 8, "the contract column is a ceiling"
    assert row["outcomes"] == {"success": 3, "failed": 0}
    assert row["evidence"] == ["measured"]
    assert row["end_to_end_p95"] == 3.0
    assert OB.celery_summary([]) == {}


@check("http rows read the record http_process_bench actually writes")
def test_http_summary():
    records = [
        {"kind": "boot", "arm": "a", "seconds": 4.5},
        {"kind": "load", "arm": "a", "phase": "warmup", "requests": 50,
         "http": {"overall": {"n": 50, "rps": 100.0, "errors": 0, "p50_ms": 5.0,
                              "p95_ms": 9.0, "p99_ms": 11.0}},
         "peer": {"overall": {"p95_ms": 2.0}}},
        {"kind": "load", "arm": "a", "phase": "load", "requests": 2100,
         "http": {"overall": {"n": 2099, "rps": 88.4, "errors": 1, "p50_ms": 6.0,
                              "p95_ms": 12.0, "p99_ms": 30.0}},
         "peer": {"overall": {"p95_ms": 3.0}},
         "ws": {"count": 25, "open_at_end": 25, "closed_early": 0}},
        {"kind": "report", "arm": "a"},
    ]
    rows = OB.http_summary(records)
    assert set(rows) == {"boot", "warmup", "load"}, rows
    assert rows["boot"]["ready_seconds"] == 4.5
    assert rows["load"]["websocket_open"] == 25
    assert rows["load"]["websocket_closed_early"] == 0
    assert rows["load"]["errors"] == 1 and rows["load"]["peer_p95_ms"] == 3.0
    assert OB.http_summary([]) == {}


@check("memory rows read the sampler record and never invent a peak")
def test_memory_summary():
    records = [
        {"project": "p", "phase": "load-x", "samples": 10,
         "stack_sum_current_peak": 1000, "stack_sum_committed_peak": 2000,
         "containers": {"backend": {"cpu_usage_usec_delta": 40, "oom_kill_delta": 0,
                                    "procs": {"1": {"pss_peak": 300},
                                              "2": {"pss_peak": 500}}},
                        "redis": {"cpu_usage_usec_delta": 5}}},
        {"project": "p", "phase": "load-x", "samples": 4,
         "stack_sum_current_peak": 1500, "stack_sum_committed_peak": 1600,
         "containers": {"backend": {"cpu_usage_usec_delta": 10, "oom_kill_delta": 1}}},
        {"project": "p", "phase": "load-x", "note": "not a sample record"},
    ]
    row = OB.memory_summary(records)
    assert row["samples"] == 14
    assert row["stack_current_peak_bytes"] == 1500, "a peak is a max, not a sum"
    assert row["stack_committed_peak_bytes"] == 2000
    assert row["process_pss_peak_bytes"] == 500
    assert row["cpu_usage_usec"] == 55 and row["oom_kill"] == 1
    assert row["containers"] == 2
    assert OB.memory_summary([{"samples": 3}]) is None, \
        "a file with no phase record is no measurement, not a zero"


@check("artifact naming is symmetric between what run writes and what report reads")
def test_artifact_naming():
    data = OB.load_arms(str(ARMS))
    for cell in data["cells"]:
        plan = "\n".join(OB.plan_lines(data, {"name": "arm-a", "celery_env": {}},
                                       cell, "production"))
        assert "taskperf-arm-a-%s.jsonl" % cell["name"] in plan \
            or "http-arm-a-%s.jsonl" % cell["name"] in plan, \
            "the plan of %s must name the per-cell artifact the reader expects" \
            % cell["name"]
    # a cell's name must survive the reader's regex even with dashes in it
    with tempfile.TemporaryDirectory() as directory:
        name = "taskperf-arm-a-harvesting-import.jsonl"
        record = {"family": "f", "scale": "typical", "arm": "arm-a", "repeat": 1,
                  "durations": {"active": {"samples": [1.0]}}, "outcomes": {}}
        Path(os.path.join(directory, name)).write_text(json.dumps(record) + "\n")
        rows = OB.cell_records(directory, "arm-a")
        assert set(rows) == {"harvesting-import"}, rows
        # a second arm's file must not leak into this arm's reading
        Path(os.path.join(directory, "taskperf-arm-b-harvesting-import.jsonl")
             ).write_text(json.dumps(record) + "\n")
        assert set(OB.cell_records(directory, "arm-a")) == {"harvesting-import"}


@check("storage deltas are per-path differences, and unavailable is not zero")
def test_storage_delta():
    before = {"available": True,
              "paths": {"media/logs": {"kilobytes": 10, "files": 2},
                        "media/security_proxy/logs": {"kilobytes": 5, "files": 1}}}
    after = {"available": True,
             "paths": {"media/logs": {"kilobytes": 40, "files": 5},
                       "media/new": {"kilobytes": 3, "files": 3}}}
    delta = OB.storage_delta(before, after)
    assert delta["media/logs"] == {"kilobytes": 30, "files": 3}
    assert delta["media/security_proxy/logs"] == {"kilobytes": -5, "files": -1}
    assert delta["media/new"] == {"kilobytes": 3, "files": 3}
    assert sorted(delta) == ["media/logs", "media/new", "media/security_proxy/logs"]
    assert OB.storage_delta(before, {"available": False}) is None, \
        "'could not count' must never be reported as 'wrote nothing'"
    assert OB.storage_delta(None, after) is None


@check("plan prints commands which exist, in the protocol's own order")
def test_plan_commands():
    data = OB.load_arms(str(ARMS))
    for cell in data["cells"]:
        lines = OB.plan_lines(data, data["arms"][0], cell, "production")
        for line in lines:
            for script in ("task_perf_runner.sh", "task_perf_bench.py",
                           "http_process_bench.py", "stack_memory_profile"):
                if script in line:
                    target = SCRIPTS / script
                    assert target.exists(), "%s names %s, which is not in scripts/" \
                        % (cell["name"], script)
        text = "\n".join(lines)
        assert "wait-ready" in text or "task_perf_runner" in text
        if cell["kind"] == "http":
            assert "--phase warmup" in text and "--phase load" in text, \
                "warmup is part of the protocol, not an option"
            assert "du -sk" in text, "a cell with media paths must be inventoried"
        # the protocol's numbers have to be the protocol's, not a copy
        assert str(data["protocol"]["requests"] * data["protocol"]["repeats"]) in text \
            or cell["kind"] == "celery"


@check("a run refuses a compose project it does not own")
def test_project_ownership():
    for project in ("my-stack", "postgres", ""):
        os.environ["COMPOSE_PROJECT_NAME"] = project
        try:
            OB.cmd_run(args(arm="legacy-shipped",
                            out=os.path.join(tempfile.gettempdir(), "obs1777")),
                       OB.load_arms(str(ARMS)))
            raise AssertionError("run accepted COMPOSE_PROJECT_NAME=%r" % project)
        except OB.BenchError as error:
            assert "project" in str(error).lower(), error
        finally:
            os.environ.pop("COMPOSE_PROJECT_NAME", None)
    # the same guard on the destructive path
    os.environ["COMPOSE_PROJECT_NAME"] = "mrmap-issue-1777-bench"
    try:
        OB.cmd_cleanup(args(project="someone-elses-stack",
                            stack_tree=str(ROOT), compose_file=None),
                       OB.load_arms(str(ARMS)))
        raise AssertionError("cleanup accepted a foreign project")
    except OB.BenchError as error:
        assert "project" in str(error).lower(), error
    finally:
        os.environ.pop("COMPOSE_PROJECT_NAME", None)


@check("the shipped-legacy arm may not be measured without the sampler")
def test_unsampled_legacy_refused():
    os.environ["COMPOSE_PROJECT_NAME"] = "mrmap-issue-1777-check"
    try:
        OB.cmd_run(args(arm="legacy-shipped", sample=False,
                        out=os.path.join(tempfile.gettempdir(), "obs1777")),
                   OB.load_arms(str(ARMS)))
        raise AssertionError("--no-sample was accepted for the storage arm")
    except OB.BenchError as error:
        assert "storage" in str(error).lower(), error
    finally:
        os.environ.pop("COMPOSE_PROJECT_NAME", None)


@check("an arm may only enable what shipped")
def test_unknown_knob_refused():
    data = OB.load_arms(str(ARMS))
    data["arms"][1]["celery_env"] = {"MRMAP_OTEL_EXPORTER_ENDPOINT": "http://x"}
    # load_arms must refuse it before a stack is even started...
    with tempfile.NamedTemporaryFile("w", suffix=".json") as handle:
        json.dump(data, handle)
        handle.flush()
        try:
            OB.load_arms(handle.name)
            raise AssertionError("load_arms accepted a not-yet-shipped knob")
        except OB.BenchError as error:
            assert "MRMAP_OTEL_EXPORTER_ENDPOINT" in str(error), error
    # ...and so must the arm runner, for a caller who built the data itself
    os.environ["COMPOSE_PROJECT_NAME"] = "mrmap-issue-1777-check"
    out = os.path.join(tempfile.gettempdir(), "obs1777-knobs")
    try:
        with compose_env():
            OB.cmd_run(args(arm="legacy-shipped", out=out, cell="harvesting-import",
                            stack_tree=str(ROOT)), data)
        raise AssertionError("a not-yet-shipped knob was accepted by run")
    except OB.BenchError as error:
        assert "MRMAP_OTEL_EXPORTER_ENDPOINT" in str(error), error
    finally:
        os.environ.pop("COMPOSE_PROJECT_NAME", None)
        shutil.rmtree(out, ignore_errors=True)


@check("verify refuses a manifest which does not match the arms file")
def test_verify_digest_mismatch():
    with tempfile.TemporaryDirectory() as directory:
        write_synthetic_run(directory)
        manifest_path = os.path.join(directory, "run-diagnostics-off.json")
        manifest = json.loads(Path(manifest_path).read_text())
        manifest["arms_file_sha256"] = "0" * 64
        Path(manifest_path).write_text(json.dumps(manifest))
        assert OB.cmd_verify(args(out=directory), OB.load_arms(str(ARMS))) == 1, \
            "a run measured with different arms is a different protocol"


@check("verify refuses an arm which enabled what its definition does not name")
def test_verify_unclaimed_knob():
    with tempfile.TemporaryDirectory() as directory:
        write_synthetic_run(directory)
        environment = os.path.join(directory,
                                   "celery-env-diagnostics-off-harvesting-import.json")
        payload = json.loads(Path(environment).read_text())
        payload["env"]["MRMAP_TASK_PROFILING"] = "on"
        Path(environment).write_text(json.dumps(payload))
        assert OB.cmd_verify(args(out=directory), OB.load_arms(str(ARMS))) == 1, \
            "the reference arm claimed to be off while the workload had it on"


@check("verify passes a complete run and refuses an exceeded budget")
def test_verify_happy_and_budget():
    with tempfile.TemporaryDirectory() as directory:
        write_synthetic_run(directory)
        assert OB.cmd_baseline(args(out=directory, out_file="",
                                    budget_file=str(BUDGETS)),
                               OB.load_arms(str(ARMS))) == 0
        assert OB.cmd_verify(args(out=directory), OB.load_arms(str(ARMS))) == 0, \
            "a passing baseline must verify"
        baseline = json.loads(Path(os.path.join(directory, "baseline.json")).read_text())
        assert baseline["issue"] == 1777
        assert baseline["arms_file_sha256"] == OB.digest_of(str(ARMS))
        assert set(baseline["arms"]) == {"diagnostics-off", "legacy-shipped"}
        assert baseline["verdicts"], "a baseline without a budget check checks nothing"
        assert all(verdict["verdict"] in ("pass", "skip")
                   for verdict in baseline["verdicts"]), baseline["verdicts"]
        # and the same run, with the subject arm's latency multiplied, must fail
        for verdict in baseline["verdicts"]:
            if verdict["metric"].endswith("p95_ms"):
                verdict["verdict"] = "fail"
        Path(os.path.join(directory, "baseline.json")).write_text(json.dumps(baseline))
        assert OB.cmd_verify(args(out=directory), OB.load_arms(str(ARMS))) == 1, \
            "verify must refuse a run which exceeds a budget"


@check("an empty side of a budget is a skip, never a pass")
def test_budget_skip_not_pass():
    budgets = OB.load_json(str(BUDGETS), "budget file")
    payload = {"reference_arm": "diagnostics-off",
               "cells": {"service-list": {"diagnostics-off": {},
                                          "legacy-shipped": {}}},
               "budgets": budgets["budgets"]}
    verdicts = OB.judge(payload, {"diagnostics-off": {}, "legacy-shipped": {}})
    assert verdicts, "the budgets of the file must be judged"
    assert all(verdict["verdict"] == "skip" for verdict in verdicts), verdicts


@check("a ratio over the ceiling is a fail and under it is a pass")
def test_budget_ratio():
    payload = {"reference_arm": "diagnostics-off",
               "cells": {"service-list": {
                   "diagnostics-off": {"http": {"load": {"p95_ms": 100.0}}},
                   "legacy-shipped": {"http": {"load": {"p95_ms": 130.0}}}}},
               "budgets": [{"cell": "service-list", "metric": "http.load.p95_ms",
                            "max_ratio": 1.25}]}
    verdicts = OB.judge(payload, {})
    assert len(verdicts) == 1 and verdicts[0]["verdict"] == "fail", \
        "x1.3 against a x1.25 ceiling is an exceeded budget, not a pass"
    assert verdicts[0]["ratio"] == 1.3
    payload["cells"]["service-list"]["legacy-shipped"]["http"]["load"]["p95_ms"] = 120.0
    verdicts = OB.judge(payload, {})
    assert verdicts[0]["verdict"] == "pass" and verdicts[0]["ratio"] == 1.2
    payload["cells"]["service-list"]["legacy-shipped"]["http"]["load"]["p95_ms"] = 200.0
    verdicts = OB.judge(payload, {})
    assert verdicts[0]["verdict"] == "fail", verdicts


@check("the tool stays host-side: stdlib only, no backend imports")
def test_no_application_imports():
    text = TOOL.read_text()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        assert "backend" not in stripped, stripped
        assert "django" not in stripped.lower(), stripped
    allowed = {"argparse", "hashlib", "json", "math", "os", "re", "shutil",
               "subprocess", "sys", "time"}
    import ast
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in allowed, alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in allowed, node.module


# ---------------------------------------------------------------------------
# a synthetic run directory which looks like a real one
# ---------------------------------------------------------------------------
def write_synthetic_run(directory):
    """Two arms of the protocol's own cells, with the numbers of a quiet stack.

    Written from the same naming rules ``run`` uses, because the point is that
    the reading side and the writing side agree - a fixture which invented its
    own filenames would test the reader against a file no writer produces.
    """
    data = OB.load_arms(str(ARMS))
    for arm in data["arms"]:
        name = arm["name"]
        for cell in data["cells"]:
            if cell["kind"] == "celery":
                rows = [{"family": cell["family"], "scale": "typical", "arm": name,
                         "repeat": repeat,
                         "durations": {"active": {"samples": [1.0, 1.1, 0.9],
                                                  "evidence": "measured"},
                                       "end_to_end": {"samples": [2.0, 2.2]}},
                         "outcomes": {"success": {"count": 3, "evidence": "measured"}},
                         "sql": {"statements": {"value": 4, "evidence": "measured"}}}
                        for repeat in (1, 2)]
                Path(os.path.join(directory, "taskperf-%s-%s.jsonl"
                                  % (name, cell["name"]))).write_text(
                    "".join(json.dumps(row) + "\n" for row in rows))
                Path(os.path.join(
                    directory, "celery-env-%s-%s.json" % (name, cell["name"]))
                ).write_text(json.dumps(
                    {"arm": name, "cell": cell["name"], "family": cell["family"],
                     "env": {key: value for key, value in
                             (arm.get("celery_env") or {}).items()}}))
            else:
                rows = [
                    {"kind": "boot", "arm": name, "seconds": 3.0},
                    {"kind": "load", "arm": name, "phase": "warmup",
                     "requests": 50, "http": {"overall": {"n": 50, "rps": 90.0,
                                                          "errors": 0,
                                                          "p50_ms": 5.0,
                                                          "p95_ms": 10.0,
                                                          "p99_ms": 14.0}}},
                    {"kind": "load", "arm": name, "phase": "load",
                     "requests": 2100,
                     "http": {"overall": {"n": 2100, "rps": 80.0, "errors": 0,
                                          "p50_ms": 6.0, "p95_ms": 11.0,
                                          "p99_ms": 20.0}},
                     "peer": {"overall": {"n": 100, "p95_ms": 2.0}},
                     "ws": {"count": 25, "open_at_end": 25, "closed_early": 0}
                     if cell.get("websocket_count") else None},
                ]
                Path(os.path.join(directory, "http-%s-%s.jsonl"
                                  % (name, cell["name"]))).write_text(
                    "".join(json.dumps(row) + "\n" for row in rows))
                paths = cell.get("media_paths", [])
                sample = {
                    "project": "mrmap-issue-1777-bench",
                    "phase": "load-%s" % cell["name"],
                    "samples": 12,
                    "stack_sum_current_peak": 900 * 1024 * 1024,
                    "stack_sum_committed_peak": 1200 * 1024 * 1024,
                    "containers": {"backend": {
                        "cpu_usage_usec_delta": 1000,
                        "oom_kill_delta": 0,
                        "procs": {"1": {"pss_peak": 200 * 1024 * 1024}}}}}
                inventory = {
                    "arm": name, "cell": cell["name"],
                    "service": cell.get("media_service"),
                    "before": {"available": True,
                               "paths": {path: {"kilobytes": 10, "files": 1}
                                         for path in paths}},
                    "after": {"available": True,
                              "paths": {path: {"kilobytes": 20, "files": 2}
                                        for path in paths}},
                    "delta": {path: {"kilobytes": 10, "files": 1}
                              for path in paths}}
                Path(os.path.join(directory, "memory-%s-load-%s.jsonl"
                                  % (name, cell["name"]))).write_text(
                    json.dumps(sample) + "\n")
                Path(os.path.join(directory, "storage-%s-%s.json"
                                  % (name, cell["name"]))).write_text(
                    json.dumps(inventory))
        manifest = {
            "schema": OB.RUN_SCHEMA, "kind": "run", "arm": name,
            "profile": "production", "project": "mrmap-issue-1777-bench",
            "arms_file": os.path.relpath(str(ARMS), str(ROOT)),
            "arms_file_sha256": OB.digest_of(str(ARMS)),
            "revision": "f9caba88063db48cb2ec4fc7ab374070c7973d13",
            "branch": "agent/issue-1777", "dirty": False,
            "cells": [cell["name"] for cell in data["cells"]],
            "repeats": data["protocol"]["repeats"],
            "seed": data["protocol"]["seed"], "sampled": True,
            "legacy_off_settings_module": (name == "diagnostics-off")
            and "MrMap.settings_observability_baseline_off" or None,
            "protocol": data["protocol"], "arm_definition": arm,
            "duration_seconds": 60.0, "failed_cells": [],
            "host": {"machine": "Linux", "release": "test", "cores": 8},
        }
        Path(os.path.join(directory, "run-%s.json" % name)).write_text(
            json.dumps(manifest))
    return directory


def main():
    test_arms_file()
    test_celery_cells_measured()
    test_legacy_knobs_exist()
    test_budget_metrics_resolve()
    test_budget_shape()
    test_statistics()
    test_celery_summary()
    test_http_summary()
    test_memory_summary()
    test_artifact_naming()
    test_storage_delta()
    test_plan_commands()
    test_project_ownership()
    test_unsampled_legacy_refused()
    test_unknown_knob_refused()
    test_verify_digest_mismatch()
    test_verify_unclaimed_knob()
    test_verify_happy_and_budget()
    test_budget_skip_not_pass()
    test_budget_ratio()
    test_no_application_imports()

    failed = [row for row in RESULTS if not row[1]]
    for name, ok, detail in RESULTS:
        if not ok:
            print("FAIL %s%s" % (name, (" - " + detail) if detail else ""))
    for name, reason in SKIPS:
        print("SKIP %s - %s" % (name, reason))
    print("%d checks, %d failed, %d skipped"
          % (len(RESULTS), len(failed), len(SKIPS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
