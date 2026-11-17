#!/usr/bin/env python3
"""Offline tests for scripts/orm_lint.py - the #1398 static ORM rules.

Run from the repository root:  python3 scripts/test_orm_lint.py

The analyzer is exercised through its real entry point against a synthetic
mini-repository in a temporary directory: positive and negative fixtures for
every rule, on the shapes MrMap actually carries (Celery decorators with
arguments, QuerySet/Manager plan methods, chained helpers, bounded pages,
model relations). Nothing here needs docker, Django, a database or the
network; the fixture code is parsed, never imported.

Exit code 0 = all ran checks passed.
"""

import importlib.util
import json
import re
import shutil
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_spec = importlib.util.spec_from_file_location("orm_lint", SCRIPTS / "orm_lint.py")
orm_lint = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(orm_lint)

RESULTS = []

TEXT_LINE = re.compile(
    r"^(?P<path>[\w./\-]+):(?P<line>\d+):(?P<col>\d+): "
    r"(?P<sev>warning|notice) (?P<rule>MRMAP-ORM-[0-9A-Z]+): (?P<msg>.*)$")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


MODELS_PY = '''
from django.db import models


class ProbeSetting(models.Model):
    name = models.CharField(max_length=100)


class Service(models.Model):
    title = models.CharField(max_length=100)


class Tag(models.Model):
    label = models.CharField(max_length=100)


class MonitoringRun(models.Model):
    setting = models.ForeignKey(ProbeSetting, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    tags = models.ManyToManyField(Tag)
    description = models.TextField()
'''

# The destination of rule 001: plans inside a QuerySet class are the
# convention itself, never findings; and their eager-load fields must be
# visible to the call site in the task module (the plan index).
PLANS_PY = '''
from django.db import models


class MonitoringRunQuerySet(models.QuerySet):
    def for_monitoring_task(self):
        return self.select_related("setting")

    def custom_with_tags(self):
        return self.prefetch_related(Prefetch("tags"))


class MonitoringRunManager(models.Manager):
    def get_queryset(self):
        return MonitoringRunQuerySet(self.model, using=self._db)
'''

TASKS_PY = '''
from celery import shared_task

from fixture_app.models import MonitoringRun, Service


@shared_task
def run_ok():
    # negative 001: the #1397 contract call site, and a harmless lookup
    run = MonitoringRun.objects.for_monitoring_task().get(pk=1)
    other = Service.objects.get(pk=2)
    return run, other


@shared_task
def run_inline_plan():
    # positive 001
    return MonitoringRun.objects.select_related("setting").get(pk=1)


@shared_task
def run_via_helper():
    # positive 001 through the same-module transitive helper chain
    return _helper_a()


def _helper_a():
    return _helper_b()


def _helper_b():
    return MonitoringRun.objects.prefetch_related("tags").count()


def orphan_helper():
    # negative scope: not reachable from any task in this module
    return MonitoringRun.objects.select_related("service").get(pk=3)


@shared_task(queue="db-routines", bind=True, base=None)
def run_loop_gets(self):
    total = 0
    for i in range(3):
        # positive 004; negative for a non-ORM receiver of the same name
        total += Service.objects.get(pk=i).pk
        total += _config.get("key", 0)
    return total


@shared_task
def run_chain_once():
    for i in range(3):
        # positive 004, reported once for the whole chain, on the evaluating
        # method of the chain
        if MonitoringRun.objects.filter(description=i).exists():
            pass


@shared_task
def run_bounded_page(ids):
    # negative 004: the page is queried OUTSIDE the loop, inside is pure Python
    rows = list(Service.objects.filter(pk__in=ids))
    done = []
    for row in rows:
        done.append(row.title)
    return done


@shared_task
def run_outer_inner():
    # positive 004: the inner queryset evaluates once per outer iteration
    for i in range(2):
        for s in Service.objects.all():
            pass


@shared_task
def run_comprehension():
    # positive 004 in a comprehension
    return [Service.objects.get(pk=i).pk for i in range(3)]


@shared_task
def run_iter_source():
    # negative 004: the queryset IS the iterable of this very loop
    for run in MonitoringRun.objects.iterator():
        pass


@shared_task
def run_lazy_relation():
    # positive 005: FK access per row without eager loading in the expression
    out = []
    for run in MonitoringRun.objects.filter(description="x"):
        out.append(run.setting.name)
    return out


@shared_task
def run_eager_relation():
    # negative 005: the loop expression eager-loads the relation (and it is
    # itself a 001 finding: the plan is still inline in the task)
    out = []
    for run in MonitoringRun.objects.filter(description="x").select_related("setting"):
        out.append(run.setting.name)
    return out


@shared_task
def run_planned_relation():
    # negative 005: the plan lives in the QuerySet method (cross-file plan index)
    out = []
    for run in MonitoringRun.objects.for_monitoring_task():
        out.append(run.setting.name)
    return out


@shared_task
def run_custom_planned_relation():
    out = []
    for run in MonitoringRun.objects.custom_with_tags():
        out.append(run.tags)
    return out


@shared_task
def run_unknown_manager_method():
    # negative 005: an unresolvable custom method makes the plan unknown -
    # the tool must not guess
    out = []
    for run in MonitoringRun.objects.some_unseen_manager_method():
        out.append(run.setting.name)
    return out


@shared_task
def run_id_and_column_access():
    # negative 005: id cache, pk and plain columns are not relation reads
    out = []
    for run in MonitoringRun.objects.filter(description="x"):
        out.append((run.setting_id, run.pk, run.description))
    return out


@shared_task
def run_reverse_untracked(service_ids):
    # negative 005: reverse names are not in the forward model map - unknown,
    # and unknown is never a finding
    out = []
    for service in Service.objects.filter(pk__in=service_ids):
        out.append(service.monitoringrun_set.all())
    return out


@shared_task
def run_m2m_lazy():
    # positive 005, M2M flavour naming prefetch_related
    out = []
    for run in MonitoringRun.objects.all():
        out.append(run.tags)
    return out
'''

# dotted decorator forms and the relative celery module
APP_TASKS_PY = '''
from .celery import app
import celery


@app.task(name="a")
def via_app_task():
    from fixture_app.models import MonitoringRun
    return MonitoringRun.objects.select_related("setting").get(pk=1)


@celery.shared_task
def via_imported_celery():
    from fixture_app.models import MonitoringRun
    return MonitoringRun.objects.select_related("setting").get(pk=1)
'''

NO_TASK_PY = '''
from fixture_app.models import MonitoringRun


def not_a_task():
    # negative scope: an inline plan in a module with no Celery task at all
    # is out of the task-scope of #1398 - the audit placed these elsewhere
    return MonitoringRun.objects.select_related("setting").get(pk=1)
'''

EXCLUDED_DIR_PY = '''
from celery import shared_task


@shared_task
def in_migrations():
    from fixture_app.models import MonitoringRun
    return MonitoringRun.objects.select_related("setting").get(pk=1)
'''

SUPPRESSIONS_PY = '''
from celery import shared_task

from fixture_app.models import MonitoringRun


@shared_task
def sup_same_line():
    return MonitoringRun.objects.select_related("setting").get(pk=1)  # orm-lint: ignore MRMAP-ORM-001 -- one-off lookup by design, reviewed in #1388


@shared_task
def sup_above_line():
    # orm-lint: ignore MRMAP-ORM-001 -- one-off lookup by design, reviewed in #1388
    return MonitoringRun.objects.select_related("setting").get(pk=1)


@shared_task
def sup_missing_justification():
    return MonitoringRun.objects.select_related("setting").get(pk=1)  # orm-lint: ignore MRMAP-ORM-001


@shared_task
def sup_missing_rule():
    return MonitoringRun.objects.select_related("setting").get(pk=1)  # orm-lint: ignore -- because


@shared_task
def sup_all_rules():
    return MonitoringRun.objects.select_related("setting").get(pk=1)  # orm-lint: ignore all -- silence please


@shared_task
def sup_unknown_rule():
    return MonitoringRun.objects.select_related("setting").get(pk=1)  # orm-lint: ignore MRMAP-ORM-999 -- a rule that does not exist
'''

BROKEN_PY = "def broken(:\n    pass\n"


def build_fixture_root():
    root = Path(tempfile.mkdtemp(prefix="orm-lint-fixture-"))
    (root / "scripts").mkdir()
    backend = root / "backend" / "fixture_app"
    backend.mkdir(parents=True)
    (backend / "models.py").write_text(MODELS_PY)
    (backend / "plans.py").write_text(PLANS_PY)
    (backend / "tasks_mod.py").write_text(TASKS_PY)
    (backend / "app_tasks.py").write_text(APP_TASKS_PY)
    (backend / "no_task.py").write_text(NO_TASK_PY)
    (root / "backend" / "migrations").mkdir()
    (root / "backend" / "migrations" / "0001_initial.py").write_text(EXCLUDED_DIR_PY)
    return root


def run_text(root, *args):
    """Run the analyzer in text mode; return (exit code, parsed findings)."""
    buf = StringIO()
    code = None
    try:
        with redirect_stdout(buf):
            code = orm_lint.main(["--root", str(root), "--format", "text", *args])
    except SystemExit as exc:  # argparse errors surface here
        code = exc.code
    findings = []
    for line in buf.getvalue().splitlines():
        m = TEXT_LINE.match(line)
        if m:
            d = m.groupdict()
            d["grandfathered"] = "[grandfathered]" in d["msg"]
            findings.append(d)
    return code, findings


def findings_for(findings, rule):
    return [f for f in findings if f["rule"] == rule]


def _run_quiet(argv):
    with redirect_stdout(StringIO()):
        return orm_lint.main(argv)


def main():
    root = build_fixture_root()
    try:
        code, findings = run_text(root, "--fail-on", "nothing")
        by_rule = {r: findings_for(findings, r) for r in
                   ("MRMAP-ORM-001", "MRMAP-ORM-004", "MRMAP-ORM-005",
                    "MRMAP-ORM-SUP")}

        # -- rule 001 ----------------------------------------------------
        paths = {f["path"] for f in by_rule["MRMAP-ORM-001"]}
        check("001 fires in task modules",
              paths == {"backend/fixture_app/tasks_mod.py",
                        "backend/fixture_app/app_tasks.py"},
              str(paths))
        check("001 finds exactly three findings in tasks_mod "
              "(inline, same-module helper chain, and the eager-iteration "
              "loop whose plan is also inline)",
              sum(1 for f in by_rule["MRMAP-ORM-001"]
                  if f["path"].endswith("tasks_mod.py")) == 3,
              str([f["line"] for f in by_rule["MRMAP-ORM-001"]
                   if f["path"].endswith("tasks_mod.py")]))
        check("001 reaches the task through same-module helpers",
              any("run_via_helper" not in f["msg"] and "_helper_b" in f["msg"]
                  for f in by_rule["MRMAP-ORM-001"]
                  if f["path"].endswith("tasks_mod.py")),
              str([f["msg"][:60] for f in by_rule["MRMAP-ORM-001"]]))
        check("001 finds both dotted decorator forms in app_tasks",
              sum(1 for f in by_rule["MRMAP-ORM-001"]
                  if f["path"].endswith("app_tasks.py")) == 2)
        check("001 negative: contract call site and plain get(pk=) stay unflagged",
              all("run_ok" not in f["msg"] for f in by_rule["MRMAP-ORM-001"]))
        check("001 negative: plans inside the QuerySet class are not findings",
              not any(f["path"].endswith("plans.py")
                      for f in by_rule["MRMAP-ORM-001"]))
        check("001 negative: module without any Celery task is out of scope",
              not any(f["path"].endswith("no_task.py")
                      for f in by_rule["MRMAP-ORM-001"]))
        check("001 negative: helper not reachable from a task is out of scope",
              all("orphan_helper" not in f["msg"]
                  for f in by_rule["MRMAP-ORM-001"]))
        check("migrations directory is excluded",
              not any("migrations" in f["path"] for f in findings))

        # -- rule 004 ----------------------------------------------------
        m4 = by_rule["MRMAP-ORM-004"]
        check("004 positive: get-in-for, evaluating chain, inner-loop queryset, "
              "comprehension element",
              len(m4) == 4, str([(f["path"].split("/")[-1], f["line"], f["msg"][:30])
                                 for f in m4]))
        check("004 chain dedupe: one finding, reporting the evaluating method",
              sum(1 for f in m4 if "`.exists(" in f["msg"]) == 1
              and sum(1 for f in m4 if "`.filter(" in f["msg"]) == 0,
              str([f["line"] for f in m4]))
        check("004 negative: dict.get and precomputed pages are not flagged",
              all("_config" not in f["msg"] for f in m4)
              and all("run_bounded_page" not in f["msg"] for f in m4))
        check("004 negative: the queryset that IS the loop iterable is not an access per iteration",
              all("run_iter_source" not in f["msg"] for f in m4))

        # -- rule 005 ----------------------------------------------------
        m5 = by_rule["MRMAP-ORM-005"]
        check("005 positive: lazy FK and M2M access in queryset iteration",
              len(m5) == 2, str([(f["line"], f["msg"][:40]) for f in m5]))
        check("005 names prefetch_related for the M2M field",
              any("prefetch_related" in f["msg"] for f in m5))
        check("005 says candidate, not proven cost",
              all("unproven" in f["msg"] or "CANDIDATE" in f["msg"] for f in m5))
        check("005 negative: eager expression, plan method, custom plan, id/pk/columns, "
              "reverse names and unknown manager methods are not flagged",
              len(m5) == 2
              and all("run_eager_relation" not in f["msg"] and
                      "run_planned_relation" not in f["msg"] and
                      "run_custom_planned_relation" not in f["msg"] and
                      "run_id_and_column_access" not in f["msg"] and
                      "run_reverse_untracked" not in f["msg"] and
                      "run_unknown_manager_method" not in f["msg"]
                      for f in m5))

        # -- gate: baseline, blocking, fail-on ----------------------------
        # (runs before the suppression fixtures are added, so only the rule
        # findings of the first run are in play)
        code0, _ = run_text(root)
        check("gate: new blocking (001) findings fail the default gate",
              code0 == 1, str(code0))
        buf = StringIO()
        with redirect_stdout(buf):
            code_b = orm_lint.main(["--root", str(root), "--update-baseline"])
        baseline = json.loads((root / "scripts" / "orm_lint_baseline.json")
                              .read_text())
        check("baseline: --update-baseline writes the current findings "
              "(and still reports this first run as new)",
              code_b == 1 and len(baseline["findings"]) == len(findings),
              "rc=%s entries=%d findings=%d"
              % (code_b, len(baseline["findings"]), len(findings)))
        code_a, findings_a = run_text(root)
        grand = [f for f in findings_a if f["grandfathered"]]
        check("baseline: grandfathered findings are marked and no longer new",
              code_a == 0 and len(grand) == len(baseline["findings"]),
              "rc=%s grandfathered=%d" % (code_a, len(grand)))

        # a NEW violation next to the baseline fails the gate
        (root / "backend" / "fixture_app" / "brand_new.py").write_text(
            "from celery import shared_task\n"
            "from fixture_app.models import MonitoringRun\n"
            "\n"
            "\n"
            "@shared_task\n"
            "def new_offender():\n"
            "    return MonitoringRun.objects.select_related('service').get(pk=1)\n")
        code_new, findings_new = run_text(root)
        new001 = [f for f in findings_new
                  if f["rule"] == "MRMAP-ORM-001" and not f["grandfathered"]
                  and f["path"].endswith("brand_new.py")]
        check("gate: a new violation beside a full baseline is new and fails",
              code_new == 1 and len(new001) == 1, str(code_new))

        # advisory rules alone do not fail the default gate but do with --fail-on advisory
        (root / "backend" / "fixture_app" / "brand_new.py").write_text(
            "from celery import shared_task\n"
            "from fixture_app.models import MonitoringRun\n"
            "\n"
            "\n"
            "@shared_task\n"
            "def new_offender(pks):\n"
            "    for i in pks:\n"
            "        MonitoringRun.objects.get(pk=i)\n")
        code_adv, findings_adv = run_text(root)
        new004 = [f for f in findings_adv
                  if f["rule"] == "MRMAP-ORM-004" and not f["grandfathered"]
                  and f["path"].endswith("brand_new.py")]
        code_ad, _ = run_text(root, "--fail-on", "advisory")
        code_no, _ = run_text(root, "--fail-on", "nothing")
        check("gate: a new advisory finding passes the blocking gate "
              "and fails --fail-on advisory; --fail-on nothing passes",
              code_adv == 0 and code_ad == 1 and code_no == 0
              and len(new004) == 1,
              "%s %s %s" % (code_adv, code_ad, code_no))

        # -- machine-readable reports --------------------------------------
        sonar_path = root / "sonar.json"
        with redirect_stdout(StringIO()):
            orm_lint.main(["--root", str(root), "--format", "sonar",
                           "-o", str(sonar_path), "--no-baseline"])
        sonar = json.loads(sonar_path.read_text())
        issues = sonar["issues"]
        first = issues[0]
        loc = first["primaryLocation"]
        schema_ok = (all(k in first for k in ("engineId", "ruleId", "severity",
                                              "type", "primaryLocation"))
                     and loc["filePath"].startswith("backend/")
                     and "textRange" in loc
                     and {r["id"] for r in sonar["rules"]} == set(orm_lint.RULES))
        check("sonar generic format: schema, project-relative path, rule metadata",
              schema_ok,
              str(sorted({r["id"] for r in sonar["rules"]})))
        check("sonar: every rule id known, severity mapping sane",
              all(i["ruleId"] in orm_lint.RULES and
                  i["severity"] == orm_lint.RULES[i["ruleId"]]["sonarSeverity"]
                  for i in issues))
        check("sonar: 004 findings carry the loop as a secondary location",
              any(i["ruleId"] == "MRMAP-ORM-004" and
                  i.get("secondaryLocations") for i in issues))

        with redirect_stdout(StringIO()):
            orm_lint.main(["--root", str(root), "--format", "sonar",
                           "-o", str(sonar_path)])
        sonar_gb = json.loads(sonar_path.read_text())
        check("sonar: grandfathered findings are not published to Sonar",
              all(not any(f["rule"] == i["ruleId"]
                          and f["line"] == i["primaryLocation"]["textRange"]["startLine"]
                          and f["path"] == i["primaryLocation"]["filePath"]
                          and f["grandfathered"]
                          for f in findings_a)
                  for i in sonar_gb["issues"]),
              str(len(sonar_gb["issues"])))

        sarif_path = root / "run.sarif"
        with redirect_stdout(StringIO()):
            orm_lint.main(["--root", str(root), "--format", "sarif",
                           "-o", str(sarif_path), "--no-baseline"])
        sarif = json.loads(sarif_path.read_text())
        check("sarif: 2.1.0 with rules and results",
              sarif["version"] == "2.1.0"
              and sarif["runs"][0]["tool"]["driver"]["name"] == orm_lint.ENGINE_ID
              and {r["id"] for r in sarif["runs"][0]["tool"]["driver"]["rules"]}
              == set(orm_lint.RULES)
              and len(sarif["runs"][0]["results"]) == len(issues))

        buf = StringIO()
        with redirect_stdout(buf):
            orm_lint.main(["--root", str(root), "--format", "github"])
        gh_lines = [ann for ann in buf.getvalue().splitlines()
                    if ann.startswith("::")]
        check("github format: annotations only for new findings",
              len(gh_lines) == 1
              and gh_lines[0].startswith("::notice file=backend/fixture_app/brand_new.py"),
              str(gh_lines))

        # -- determinism ---------------------------------------------------
        _, a = run_text(root, "--no-baseline")
        _, b = run_text(root, "--no-baseline")
        check("determinism: two runs report identical findings", a == b)

        # -- unreadable source ---------------------------------------------
        (root / "backend" / "fixture_app" / "broken.py").write_text(BROKEN_PY)
        code_x, _ = run_text(root, "--fail-on", "nothing")
        check("a source file that cannot be parsed exits 2", code_x == 2,
              str(code_x))
        (root / "backend" / "fixture_app" / "broken.py").unlink()

        # -- suppression (added last: SUP findings are blocking and would
        #    skew every earlier gate assertion) -----------------------------
        (root / "backend" / "fixture_app" / "suppressions.py").write_text(SUPPRESSIONS_PY)
        sup_code, sup_findings = run_text(root, "--fail-on", "nothing")
        sup = [f for f in sup_findings if f["path"].endswith("suppressions.py")]
        sup001 = [f for f in sup if f["rule"] == "MRMAP-ORM-001"]
        supsup = [f for f in sup if f["rule"] == "MRMAP-ORM-SUP"]
        check("suppression: valid ignores (same line and line above) remove the findings",
              len(sup001) == 4 and len(sup) == 4 + 4,
              str([(f["rule"], f["line"]) for f in sup]))
        check("suppression hygiene: missing justification, missing rule, `all`, "
              "unknown rule each produce a SUP finding",
              len(supsup) == 4
              and sum(1 for f in supsup if "no justification" in f["msg"]) == 1
              and sum(1 for f in supsup if "no rule ID" in f["msg"]) == 1
              and sum(1 for f in supsup if "all rules" in f["msg"]) == 1
              and sum(1 for f in supsup if "unknown" in f["msg"]) == 1,
              str([f["msg"][:60] for f in supsup]))
        sup_code_gate, _ = run_text(root)
        check("gate: malformed suppressions are blocking and fail the gate",
              sup_code_gate == 1, str(sup_code_gate))

        check("regression on the real repository stays green",
              _run_quiet(["--root", str(ROOT)]) == 0,
              "the repository's own baseline must stay clean at HEAD")

    finally:
        shutil.rmtree(root, ignore_errors=True)

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print("%s %s%s" % ("PASS" if ok else "FAIL", name,
                           (" - " + detail) if detail and not ok else ""))
    print("orm_lint suite: %d checks, %d failed" % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
