#!/usr/bin/env python3
"""Offline checks for scripts/release_gates (issue #1583, epic #1577).

Runs without docker, without network and without `gh`: the api gate is driven
on synthetic OpenAPI documents, the promote gate on synthetic evidence, and
the version/upgrade gates end to end against throw-away git repositories in
temporary directories that hold exactly the situation each rule is about - the
fake migration, the unapproved RemoveField, the missing migration note, the
wrong bump, the gone protected node.

The suite's duty mirrors the issue's acceptance line "test intentional
failures as well as the successful path": every gate is woken up RED at least
once with the finding it names, and the SAME scenario is then run GREEN with
the reviewed exception, marker or digest added. A gate that was never seen
red here is a decoration nobody would notice die.

Run from the repository root: `python3 scripts/test_release_gates.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATES = HERE / "release_gates.py"
TOOLS = ["release_gates.py", "pr_classify", "migration_graph_smoke.py",
         "canonical_version.py", "release_contract_baseline.json",
         "release_contract_exceptions.json", "release_upgrade_baseline.json"]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def run_gates(args, root="."):
    proc = subprocess.run(
        [sys.executable, str(GATES), "--root", str(root)] + args,
        capture_output=True, text=True, cwd=str(root))
    return proc.returncode, proc.stdout, proc.stderr


def gates_module():
    """The tool as a module, for checks of its pure functions (the version
    comparison is decided by `semver_cmp` and is worth pinning without
    building a repository around it)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("release_gates", GATES)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------- api fixtures


def doc(paths, version="0.1.0"):
    return {"openapi": "3.0.3", "info": {"version": version, "title": "t"},
            "paths": paths, "components": {"schemas": {}}}


def resp(schema, status="200"):
    content = {"application/json": {"schema": schema}}
    return {status: {"description": "ok", "content": content}}


OBJ = {"type": "object", "properties": {"a": {"type": "string"},
                                        "b": {"type": "integer"}},
       "required": ["a"]}
OBJ_GONE_B = {"type": "object", "properties": {"a": {"type": "string"}},
              "required": ["a"]}
_OBJ_B_REQUIRED = {"type": "object",
                   "properties": {"a": {"type": "string"},
                                  "b": {"type": "integer"}},
                   "required": ["a", "b"]}
OBJ_B_STRING = {"type": "object",
                "properties": {"a": {"type": "string"},
                               "b": {"type": "string"}}}
OBJ_ENUM = {"type": "object", "properties": {"a": {"type": "string"},
                                             "b": {"type": "integer"},
                                             "c": {"type": "string",
                                                   "enum": ["x", "y", "z"]}}}
OBJ_ENUM_NARROW = {"type": "object",
                   "properties": {"a": {"type": "string"},
                                  "b": {"type": "integer"},
                                  "c": {"type": "string", "enum": ["x", "y"]}}}


def scenario(tmp, baseline_manifest, baseline_doc, candidate_doc,
             exceptions=None):
    """One api-gate fixture: manifest, baseline snapshot, candidate, ledger."""
    root = Path(tmp)
    (root / "VERSION").write_text("0.1.0\n", encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps(baseline_manifest),
                                        encoding="utf-8")
    if baseline_doc is not None:
        (root / "baseline.openapi.json").write_text(json.dumps(baseline_doc),
                                                    encoding="utf-8")
    (root / "candidate.openapi.json").write_text(json.dumps(candidate_doc),
                                                 encoding="utf-8")
    (root / "ledger.json").write_text(json.dumps(
        {"exceptions": exceptions or []}), encoding="utf-8")
    return ["api", "--baseline", "manifest.json", "--exceptions", "ledger.json",
            "--candidate", str(root / "candidate.openapi.json")]


def released_manifest(**extra):
    m = {"mode": "released", "version": "0.1.0", "source": "v0.1.0",
         "document": "baseline.openapi.json", "policy": {}}
    m.update(extra)
    return m


def pre_baseline_manifest():
    return {"mode": "pre-baseline", "version": None, "source": None,
            "document": None,
            "policy": {"reviewed_0_x": True, "breaking_below_1_0": "minor",
                       "declared_on": ["#1583"]}}


def test_api_identical_is_green():
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        ops = {"/api/x": {"get": {
            "operationId": "getX",
            "parameters": [{"name": "p", "in": "query", "required": False}],
            "responses": resp(OBJ)}}}
        args = scenario(tmp, released_manifest(), doc(ops), doc(ops))
        code, out, err = run_gates(args, tmp)
        check("api: an identical candidate is green",
              code == 0, err)


def test_api_removed_operation_needs_review():
    base = {"/api/x": {"get": {"operationId": "getX",
                               "responses": resp(OBJ)}},
            "/api/notify/task-results": {"delete": {
                "operationId": "delTR", "responses": resp(OBJ)}}}
    cand = {"/api/x": {"get": {"operationId": "getX",
                               "responses": resp(OBJ)}}}
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        args = scenario(tmp, released_manifest(), doc(base), doc(cand))
        code, out, err = run_gates(args, tmp)
        check("api: a removed endpoint without review fails",
              code == 1 and "removed-operation" in err
              and "DELETE /api/notify/task-results" in err, err)

        reviewed = [{"id": "E1", "kind": "removed-operation",
                     "target": "DELETE /api/notify/task-results",
                     "refs": ["#1180"], "note": "announced cutover"}]
        args = scenario(tmp, released_manifest(), doc(base), doc(cand),
                        exceptions=reviewed)
        code, out, err = run_gates(args, tmp)
        check("api: the same removal passes once a human reviewed it in the ledger",
              code == 0, err)
        report = Path(tmp) / "report.json"
        code, out, err = run_gates(args + ["--report", str(report)], tmp)
        data = json.loads(report.read_text(encoding="utf-8"))
        check("api: the covered finding records which exception covers it",
              data["ok"] and data["breaking"] == []
              and data["mode"] == "released", out + err)


def test_api_stale_exception_fails():
    base = {"/api/x": {"get": {"operationId": "getX", "responses": resp(OBJ)}}}
    cand = {"/api/y": {"get": {"operationId": "getY", "responses": resp(OBJ)}}}
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        reviewed = [{"id": "E1", "kind": "removed-operation",
                     "target": "GET /api/long-gone", "refs": ["#1"]}]
        args = scenario(tmp, released_manifest(), doc(base), doc(cand),
                        exceptions=reviewed)
        code, out, err = run_gates(args, tmp)
        check("api: an exception matching no finding is stale and fails",
              code == 1 and "stale" in err, err)


def test_api_surface_findings():
    cases = [
        ("removed response property", OBJ, OBJ_GONE_B,
         "removed-property"),
        ("newly required response property", OBJ, _OBJ_B_REQUIRED,
         "new-required-property"),
        ("property type change", OBJ, OBJ_B_STRING,
         "property-type-change"),
        ("narrowed enum", OBJ_ENUM, OBJ_ENUM_NARROW, "enum-narrowed"),
    ]
    for label, base_schema, cand_schema, kind in cases:
        with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
            base = {"/api/x": {"get": {"operationId": "g",
                                       "responses": resp(base_schema)}}}
            cand = {"/api/x": {"get": {"operationId": "g",
                                       "responses": resp(cand_schema)}}}
            args = scenario(tmp, released_manifest(), doc(base), doc(cand))
            code, out, err = run_gates(args, tmp)
            check(f"api: {kind} ({label}) fails",
                  code == 1 and kind in err, f"exit {code}: {err}")

    # and the same surface, changed the other way, is green
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        base = {"/api/x": {"get": {"operationId": "g",
                                   "responses": resp(OBJ_GONE_B)}}}
        cand = {"/api/x": {"get": {"operationId": "g",
                                   "responses": resp(OBJ)}}}
        args = scenario(tmp, released_manifest(), doc(base), doc(cand))
        code, out, err = run_gates(args, tmp)
        check("api: adding a property (widening) passes", code == 0, err)


def test_api_params_and_status():
    base = {"/api/x": {"get": {
        "operationId": "g",
        "parameters": [{"name": "p", "in": "query", "required": False},
                       {"name": "q", "in": "query", "required": True}],
        "responses": {**resp(OBJ), "202": {"description": "x"}}}}}
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        cand = {"/api/x": {"get": {
            "operationId": "g",
            "parameters": [{"name": "p", "in": "query", "required": True}],
            "responses": resp(OBJ)}}}
        args = scenario(tmp, released_manifest(), doc(base), doc(cand))
        code, out, err = run_gates(args, tmp)
        check("api: removed parameter, newly required parameter and removed "
              "status code are all findings",
              code == 1 and "removed-parameter" in err
              and "new-required-parameter" in err
              and "removed-response-status" in err, err)
        reviewed = [{"id": "E1", "kind": "removed-parameter",
                     "target": "GET /api/x: query parameter 'q'",
                     "refs": ["#2"]},
                    {"id": "E2", "kind": "new-required-parameter",
                     "target": "GET /api/x: query parameter 'p'",
                     "refs": ["#2"]},
                    {"id": "E3", "kind": "removed-response-status",
                     "target": "GET /api/x: status 202", "refs": ["#2"]}]
        args = scenario(tmp, released_manifest(), doc(base), doc(cand),
                        exceptions=reviewed)
        code, out, err = run_gates(args, tmp)
        check("api: the reviewed trio passes", code == 0, err)


def test_api_additive_counts():
    base = {"/api/x": {"get": {"operationId": "g", "responses": resp(OBJ)}}}
    cand = {"/api/x": {"get": {"operationId": "g", "responses": resp(OBJ)}},
            "/api/new": {"post": {"operationId": "new",
                                  "responses": resp(OBJ)}}}
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        report = Path(tmp) / "report.json"
        args = scenario(tmp, released_manifest(), doc(base), doc(cand))
        code, out, err = run_gates(args + ["--report", str(report)], tmp)
        data = json.loads(report.read_text(encoding="utf-8"))
        check("api: a new operation is additive, counted, never failed",
              code == 0 and data["additive_operations"] == 1
              and len(data["behavioral_blindspots"]) == 6, out + err)


def test_api_modes():
    cand = doc({"/api/only": {"get": {
        "operationId": "o", "responses": resp(OBJ)}}})
    base = doc({"/api/old": {"get": {
        "operationId": "o", "responses": resp(OBJ)}}})
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        args = scenario(tmp, pre_baseline_manifest(), None, cand)
        code, out, err = run_gates(args, tmp)
        check("api: pre-baseline answers with the reviewed 0.x note, not a diff",
              code == 0 and "pre-baseline" in out, out + err)

        m = pre_baseline_manifest()
        del m["policy"]["reviewed_0_x"]
        args = scenario(tmp, m, None, cand)
        code, out, err = run_gates(args, tmp)
        check("api: pre-baseline WITHOUT the reviewed 0.x declaration cannot run",
              code == 2 and "reviewed_0_x" in err, err)

        m = released_manifest()
        m["document"] = None
        args = scenario(tmp, m, base, cand)
        code, out, err = run_gates(args, tmp)
        check("api: released mode without a committed document cannot run",
              code == 2, err)


def test_api_stale_candidate_refused():
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        args = scenario(tmp, pre_baseline_manifest(), None,
                        doc({}, version="9.9.9"))
        code, out, err = run_gates(args, tmp)
        check("api: a candidate naming another version than the checkout is refused",
              code == 1 and "stale" in err, err)
        code, out, err = run_gates(args + ["--skip-version-check"], tmp)
        check("api: the version check can only be skipped for the gate's own tests",
              code == 0, err)


def test_api_ledger_validation():
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        args = scenario(tmp, pre_baseline_manifest(), None, doc({}),
                        exceptions=[{"id": "E1", "kind": "removed-operation",
                                     "target": "GET /x", "refs": []}])
        code, out, err = run_gates(args, tmp)
        check("api: an exception without refs is not approval and cannot run",
              code == 2 and "refs" in err, err)

    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        # one reviewed entry must not become a blanket approval for its kind
        base = {"/api/x": {"get": {"operationId": "g", "responses": resp(OBJ)}}}
        args = scenario(tmp, released_manifest(), doc(base), doc({}),
                        exceptions=[{"id": "E1", "kind": "removed-operation",
                                     "target": "*", "refs": ["#1583"]}])
        code, out, err = run_gates(args, tmp)
        check("api: a ledger target of '*' is a wildcard over the whole kind "
              "and cannot run (exit 2), not a covering exception",
              code == 2 and "wildcard" in err, err)

        # the matcher itself cannot over-cover either, validated or not
        rg = gates_module()
        blanket = [{"id": "E1", "kind": "removed-operation",
                    "target": "*", "refs": ["#1583"]}]
        check("api: match_exception never lets a bare '*' cover a finding",
              rg.match_exception("removed-operation", "GET /anything",
                                 blanket) is None, "")

    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        # a BOUNDED prefix stays legal: it names the family a human reviewed
        base = {"/api/x": {"get": {
            "operationId": "g",
            "parameters": [{"name": "p", "in": "query", "required": False},
                           {"name": "q", "in": "query", "required": False}],
            "responses": resp(OBJ)}}}
        cand = {"/api/x": {"get": {
            "operationId": "g",
            "parameters": [{"name": "p", "in": "query", "required": False}],
            "responses": resp(OBJ)}}}
        args = scenario(tmp, released_manifest(), doc(base), doc(cand),
                        exceptions=[{"id": "E1", "kind": "removed-parameter",
                                     "target": "GET /api/x*",
                                     "refs": ["#1583"]}])
        code, out, err = run_gates(args, tmp)
        check("api: a bounded prefix target ('GET /api/x*') still covers the "
              "family it names", code == 0, err)


def test_api_ref_resolution():
    base_schema = {"$ref": "#/components/schemas/Pet"}
    cand_schema = {"$ref": "#/components/schemas/PetBroken"}
    base_doc = doc({"/api/pets": {"get": {"operationId": "p",
                                          "responses": resp(base_schema)}}})
    base_doc["components"]["schemas"]["Pet"] = OBJ
    cand_doc = doc({"/api/pets": {"get": {"operationId": "p",
                                          "responses": resp(cand_schema)}}})
    cand_doc["components"]["schemas"]["PetBroken"] = OBJ_GONE_B
    with tempfile.TemporaryDirectory(prefix="rg-api-") as tmp:
        args = scenario(tmp, released_manifest(), base_doc, cand_doc)
        code, out, err = run_gates(args, tmp)
        check("api: $ref surfaces are resolved and diffed, not skipped",
              code == 1 and "removed-property" in err, err)


# ------------------------------------------------------------- git fixtures


def git(repo, *args):
    subprocess.run(("git", "-C", str(repo)) + args, check=True,
                   capture_output=True)


MIG_HEAD = ("from django.db import migrations\n\n\n"
            "class Migration(migrations.Migration):\n"
            "    dependencies = [\n%s    ]\n\n"
            "    operations = [\n%s    ]\n")


def migration(app, name, deps, ops):
    dep_src = "".join(f"        ('{a}', '{n}'),\n" for a, n in deps)
    return MIG_HEAD % (dep_src, ops)


ADD_FIELD = ("        migrations.AddField(model_name='x', name='y', "
             "field=None),\n")
EMPTY_OPS = ""


def make_repo(tmp, changelog_notes=True, compose_extra="", settings_extra="",
              version="0.1.0"):
    """A throw-away checkout shaped like mrmap: the sibling tools, a VERSION,
    a CHANGELOG with an UNRELEASED section, Compose and settings, and a notify
    app with its #1180-protected nodes 0001 and 0006 (the constraints file the
    tests pass names only these two)."""
    repo = Path(tmp) / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    for tool in TOOLS:
        shutil.copy2(HERE / tool, repo / "scripts" / tool)
    (repo / "VERSION").write_text(version + "\n", encoding="utf-8")
    notes = ("### Migration notes\n"
             "- notify.0007_a_new_column records what it changes (#1583)\n"
             "- NEW_SECRET_VAR must be set by the operator before start (#1583)\n"
             if changelog_notes else "")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [0.x.x] - UNRELEASED\n\n### Added\n- a thing (#1)\n"
        f"\n{notes}\n## [0.1.0] - 2023-03-23\n\n- old\n", encoding="utf-8")
    (repo / "docker-compose.yml").write_text(
        "services:\n  backend:\n    environment:\n"
        "      EXTERNAL_BASE_URL: \"${EXTERNAL_BASE_URL:?set me}\"\n"
        + compose_extra, encoding="utf-8")
    (repo / "backend").mkdir()
    (repo / "backend" / "MrMap").mkdir()
    (repo / "backend" / "MrMap" / "settings.py").write_text(
        "INSTALLED_APPS = ['registry', 'notify']\n" + settings_extra,
        encoding="utf-8")
    mig = repo / "backend" / "notify" / "migrations"
    mig.mkdir(parents=True)
    (mig / "0001_initial.py").write_text(
        migration("notify", "0001_initial", [], ADD_FIELD), encoding="utf-8")
    (mig / "0006_remove_backgroundprocess_threads.py").write_text(
        migration("notify", "0006_remove_backgroundprocess_threads",
                  [("notify", "0001_initial")], ADD_FIELD), encoding="utf-8")
    (repo / "constraints.json").write_text(json.dumps({
        "oldest_supported_baseline": "x", "marker_migration":
        "notify/0006_remove_backgroundprocess_threads",
        "protected_nodes": ["notify/0001_initial",
                            "notify/0006_remove_backgroundprocess_threads"],
        "retired_apps": ["django_celery_results"]}), encoding="utf-8")
    git(repo, "init", "-b", "develop")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "chore: baseline of the fixture")
    return repo


def branch_from_develop(repo, name="feature/thing"):
    git(repo, "checkout", "-b", name)
    return repo


def commit_all(repo, message):
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)


def add_migration(repo, name, ops=ADD_FIELD, deps=(("notify",
                  "0006_remove_backgroundprocess_threads"),)):
    path = repo / "backend" / "notify" / "migrations" / f"{name}.py"
    path.write_text(migration("notify", name, deps, ops), encoding="utf-8")
    return path


# --------------------------------------------------------------- version gate


def test_version_empty_range():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        code, out, err = run_gates(
            ["version", "--base", "develop", "--exceptions",
             "scripts/release_contract_exceptions.json"], repo)
        check("version: develop itself (empty range) is green", code == 0, err)


def test_version_migration_needs_a_note():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp, changelog_notes=False)
        branch_from_develop(repo)
        add_migration(repo, "0007_a_new_column")
        commit_all(repo, "feat: a new column")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a new migration without a migration note fails",
              code == 1 and "0007_a_new_column" in err, err)

        (repo / "CHANGELOG.md").write_text(
            (repo / "CHANGELOG.md").read_text(encoding="utf-8").replace(
                "### Added",
                "### Migration notes\n- notify.0007_a_new_column (#1583)\n\n"
                "### Added"), encoding="utf-8")
        commit_all(repo, "docs: note the migration")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: the same migration passes once the note names it",
              code == 0, err)


def test_version_required_config_needs_a_note():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp, changelog_notes=False)
        branch_from_develop(repo)
        (repo / "docker-compose.yml").write_text(
            (repo / "docker-compose.yml").read_text(encoding="utf-8")
            + "      NEW_SECRET_VAR: \"${NEW_SECRET_VAR:?set me}\"\n",
            encoding="utf-8")
        commit_all(repo, "feat: a setting the deployment must carry")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a new required setting without a note fails",
              code == 1 and "NEW_SECRET_VAR" in err, err)


def test_version_breaking_needs_a_breaking_line():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp, changelog_notes=False)
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat!: drop a public field")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a breaking range without '**Breaking:**' fails",
              code == 1 and "Breaking" in err, err)
        (repo / "CHANGELOG.md").write_text(
            (repo / "CHANGELOG.md").read_text(encoding="utf-8").replace(
                "### Added", "### Changed\n- **Breaking:** the field is gone\n\n"
                "### Added"), encoding="utf-8")
        commit_all(repo, "docs: breaking note")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: pre-baseline reports the bump as advisory but notes "
              "the breaking change", code == 0, err)


def _released_repo(tmp, policy=None, version="0.2.0"):
    """A fixture whose baseline manifest names a released 0.1.0; the
    changelog already carries the '**Breaking:**' line so these tests decide
    the BUMP question and not the note question."""
    repo = make_repo(tmp, changelog_notes=True, version=version)
    (repo / "CHANGELOG.md").write_text(
        (repo / "CHANGELOG.md").read_text(encoding="utf-8").replace(
            "### Added", "### Changed\n- **Breaking:** the fixture change\n\n"
            "### Added"), encoding="utf-8")
    _set_manifest(repo, policy)
    return repo


def _set_manifest(repo, policy=None, version="0.1.0"):
    policy_default = {"breaking_below_1_0": "major"}
    manifest = {"mode": "released", "version": version, "source": "v0.1.0",
                "document": None,
                "policy": policy if policy is not None else policy_default}
    (repo / "scripts" / "release_contract_baseline.json").write_text(
        json.dumps(manifest), encoding="utf-8")
    (repo / "scripts" / "release_contract_exceptions.json").write_text(
        json.dumps({"exceptions": []}), encoding="utf-8")


def test_version_bump_policy():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = _released_repo(tmp)
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat!: breaking thing")
        # 0.1.0 -> 0.2.0 while the knob reads major: not enough for breaking
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: with a released baseline, breaking without a major "
              "bump fails", code == 1 and "major" in err, err)

        # the reviewed 0.x reading (minor while major is 0) accepts it
        _set_manifest(repo, policy={"breaking_below_1_0": "minor"})
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: the reviewed 0.x minor reading accepts 0.1.0 -> 0.2.0 "
              "for a breaking change", code == 0, err)


def test_version_equal_and_backwards():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = _released_repo(tmp, version="0.1.0")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a feature with no version movement fails",
              code == 1 and "same precedence" in err, err)

    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = _released_repo(tmp, version="0.2.0")
        # baseline in manifest is 0.1.0; make it 0.3.0 to test backwards
        manifest = json.loads((repo / "scripts" /
                               "release_contract_baseline.json"
                               ).read_text(encoding="utf-8"))
        manifest["version"] = "0.3.0"
        (repo / "scripts" / "release_contract_baseline.json").write_text(
            json.dumps(manifest), encoding="utf-8")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a candidate behind its baseline fails",
              code == 1 and "BEHIND" in err, err)


def test_semver_precedence_not_dot_splitting():
    """canonical_version.py allows `0.2.0-rc.1` and `0.2.0+9f8e7d6` on purpose
    (#1579) and image_release.py tags rc candidates, so the gate reads versions
    by SemVer precedence. Splitting on '.' yields int("0-rc") and a traceback,
    which exits 1 - the code this tool reserves for a decision AGAINST a
    candidate (#1677 review)."""
    rg = gates_module()
    chain = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
             "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
    ordered = all(rg.semver_cmp(a, b) < 0 for a, b in zip(chain, chain[1:]))
    check("version: the SemVer 11 precedence chain orders correctly "
          "(numeric identifiers below alphanumeric, beta.2 < beta.11, "
          "rc.1 < release)", ordered, str(chain))
    check("version: build metadata is ignored for precedence (SemVer 10)",
          rg.semver_cmp("1.2.3+9f8e7d6", "1.2.3") == 0
          and rg.semver_cmp("0.2.0-rc.1", "0.2.0+b") < 0, "")
    try:
        rg.semver_parse("1.2", "the fixture version")
        check("version: a version the gate cannot read is a cannot-run, "
              "not a crash", False, "no GateCannotRun raised")
    except rg.GateCannotRun as exc:
        check("version: a version the gate cannot read is a cannot-run, "
              "not a crash", "not strict SemVer" in str(exc), str(exc))


def test_version_prerelease_candidate():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        # the rc of the version the range MOVES TO is a real minor bump
        repo = _released_repo(tmp, version="0.2.0-rc.1")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: an rc candidate of the next version is a valid "
              "minor bump (baseline 0.1.0 -> 0.2.0-rc.1)",
              code == 0 and "Traceback" not in err, err)

    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        # the rc of the BASELINE's own version is below it, not equal to it
        repo = _released_repo(tmp, version="0.2.0-rc.1")
        _set_manifest(repo, version="0.2.0")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a prerelease of the baseline version is BEHIND it, "
              "not equal to it (0.2.0-rc.1 < 0.2.0)",
              code == 1 and "BEHIND" in err and "Traceback" not in err, err)

    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        # a new build of the baseline version is not a bump
        repo = _released_repo(tmp, version="0.1.0+9f8e7d6")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: build metadata does not move a version ahead",
              code == 1 and "same precedence" in err
              and "Traceback" not in err, err)


def test_version_baseline_must_be_stable():
    """The contract baseline is the previous SUPPORTED stable release; an rc
    announces a release instead of being one (image_release.py refuses the
    stable aliases for a prerelease). Before, a prerelease here reached the
    version arithmetic and died with a ValueError."""
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = _released_repo(tmp, version="0.2.0")
        _set_manifest(repo, version="0.2.0-rc.1")
        branch_from_develop(repo)
        (repo / "backend" / "notify" / "x.py").write_text("X = 1\n",
                                                          encoding="utf-8")
        commit_all(repo, "feat: a feature")
        code, out, err = run_gates(["version", "--base", "develop"], repo)
        check("version: a prerelease baseline cannot run (exit 2), naming the "
              "stable-release rule",
              code == 2 and "stable release" in err
              and "Traceback" not in err, err)


# ---------------------------------------------------------------- upgrade gate


def test_upgrade_clean_migration_passes():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        add_migration(repo, "0007_a_new_column")
        commit_all(repo, "feat: a new column")
        code, out, err = run_gates(
            ["upgrade", "--base", "develop", "--constraints",
             "constraints.json"], repo)
        check("upgrade: a new migration with real operations passes",
              code == 0, err)


def test_upgrade_fake_migration_fails_then_marked_passes():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        add_migration(repo, "0007_a_hollow_node", ops=EMPTY_OPS)
        commit_all(repo, "chore: a node that changes nothing")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a new empty migration is a fake and fails",
              code == 1 and "fake migration" in err, err)

        path = repo / "backend" / "notify" / "migrations" / "0007_a_hollow_node.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "from django.db",
            "# release-gates: empty-operations -- refs #1583\nfrom django.db",
        ), encoding="utf-8")
        commit_all(repo, "chore: approve the placeholder in the file")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: the reviewed marker makes the placeholder legitimate",
              code == 0, err)


def test_upgrade_noop_runpython_is_fake():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        add_migration(repo, "0007_silent",
                      ops="        migrations.RunPython("
                          "migrations.RunPython.noop, "
                          "migrations.RunPython.noop),\n")
        commit_all(repo, "chore: a noop pretending to migrate")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a noop-only RunPython is a fake migration",
              code == 1 and "fake migration" in err, err)


def test_upgrade_destructive_needs_approval():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp, changelog_notes=False)
        branch_from_develop(repo)
        add_migration(repo, "0007_drop_a_column",
                      ops="        migrations.RemoveField("
                          "model_name='x', name='y'),\n")
        commit_all(repo, "feat!: drop a column")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a destructive operation without review fails",
              code == 1 and "destructive change without approval" in err
              and "RemoveField" in err, err)

        target = "notify.0007_drop_a_column: RemoveField ?"
        (repo / "scripts" / "release_contract_exceptions.json").write_text(
            json.dumps({"exceptions": [{
                "id": "D1", "kind": "destructive-migration",
                "target": target, "refs": ["#1583"], "note": "approved"}]}),
            encoding="utf-8")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: the ledger entry with refs approves it",
              code == 0, err)

        # a blanket waiver of the whole kind is not a reviewable entry
        (repo / "scripts" / "release_contract_exceptions.json").write_text(
            json.dumps({"exceptions": [{
                "id": "D3", "kind": "destructive-migration",
                "target": "*", "refs": ["#1583"]}]}), encoding="utf-8")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a '*' destructive target cannot run - one approved "
              "drop is not approval for every future one",
              code == 2 and "wildcard" in err, err)

        # the bounded prefix stays legal here too
        (repo / "scripts" / "release_contract_exceptions.json").write_text(
            json.dumps({"exceptions": [{
                "id": "D4", "kind": "destructive-migration",
                "target": "notify.0007_*", "refs": ["#1583"]}]}),
            encoding="utf-8")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a bounded prefix target approves the migration it "
              "names", code == 0, err)

        # an exception for a migration nobody added is stale
        (repo / "scripts" / "release_contract_exceptions.json").write_text(
            json.dumps({"exceptions": [{
                "id": "D2", "kind": "destructive-migration",
                "target": "notify.0099_ghost: RemoveField ?",
                "refs": ["#1"], "note": "gone"}]}), encoding="utf-8")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a stale destructive exception fails",
              code == 1 and "stale" in err, err)


def test_upgrade_protected_node_gone_fails():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        gone = repo / "backend" / "notify" / "migrations" / "0006_remove_backgroundprocess_threads.py"
        git(repo, "rm", "-q", str(gone.relative_to(repo)))
        # keep the graph legal: 0007 would parent on it - retime 0001 as leaf
        commit_all(repo, "chore: delete a protected node")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a deleted #1180 protected node fails",
              code == 1 and "protected node" in err, err)


def test_upgrade_retired_app_named_again():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        (repo / "backend" / "MrMap" / "settings.py").write_text(
            (repo / "backend" / "MrMap" / "settings.py").read_text(
                encoding="utf-8").rstrip()
            + "\nINSTALLED_APPS.append(\"django_celery_results\")\n",
            encoding="utf-8")
        commit_all(repo, "chore: bring the package back")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: a retired app named as a Django app again fails",
              code == 1 and "django_celery_results" in err, err)
        # and documentation ABOUT the retired app is not a hit
        settings = repo / "backend" / "MrMap" / "settings.py"
        settings.write_text(
            (repo / "backend" / "MrMap" / "settings.py").read_text(
                encoding="utf-8").replace(
                "INSTALLED_APPS.append(\"django_celery_results\")",
                "# django_celery_results was retired by #1180"),
            encoding="utf-8")
        commit_all(repo, "docs: prose is not a dependency")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: prose about the retired app stays green", code == 0, err)


def test_upgrade_graph_conflict_caught():
    with tempfile.TemporaryDirectory(prefix="rg-repo-") as tmp:
        repo = make_repo(tmp)
        branch_from_develop(repo)
        add_migration(repo, "0007_a", deps=[("notify", "0001_initial")])
        add_migration(repo, "0007_b", deps=[("notify", "0001_initial")])
        commit_all(repo, "feat: two leaves of one app")
        code, out, err = run_gates(["upgrade", "--base", "develop",
                                    "--constraints", "constraints.json"], repo)
        check("upgrade: two leaves of one app fail the reused graph gate",
              code == 1 and "leaves" in err, err)


# ---------------------------------------------------------------- promote gate


def good_evidence(sha="0" * 40, version="0.2.0"):
    return {"candidate": {"sha": sha, "version": version},
            "checks": {
                "tests": {"status": "pass", "sha": sha, "url": "u1"},
                "sonar": {"status": "pass", "sha": sha, "url": "u2"},
                "dependencies": {"status": "pass", "sha": sha, "url": "u3"},
                "artifacts": {"status": "pass", "sha": sha, "images": {
                    "mrmap-backend": {"digest": "sha256:" + "a" * 64},
                    "mrmap-frontend": {"digest": "sha256:" + "b" * 64}}}}}


def green_gate_reports(tmp):
    reports = []
    paths = {}
    for gate, extra in (("api", {"mode": "released"}),
                        ("version", {"candidate_version": "0.2.0",
                                     "mode": "released"}),
                        ("upgrade", {})):
        payload = {"gate": gate, "ok": True}
        payload.update(extra)
        path = Path(tmp) / f"{gate}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        reports += ["--gate", f"{gate}={path}"]
        paths[gate] = path
    return reports, paths


def test_promote_full_evidence():
    with tempfile.TemporaryDirectory(prefix="rg-promote-") as tmp:
        evidence = Path(tmp) / "evidence.json"
        evidence.write_text(json.dumps(good_evidence()), encoding="utf-8")
        gates, _ = green_gate_reports(tmp)
        out_file = Path(tmp) / "attestation.json"
        code, out, err = run_gates(
            ["promote", "--evidence", str(evidence), *gates,
             "--actor", "tester", "--output", str(out_file)], tmp)
        data = json.loads(out_file.read_text(encoding="utf-8"))
        check("promote: complete evidence attests the exact sha and digests",
              code == 0 and data["candidate"]["sha"] == "0" * 40
              and data["digests"]["mrmap-backend"].startswith("sha256:"), out)

        code, out, err = run_gates(
            ["promote", "--evidence", str(evidence), *gates,
             "--expect-version", "0.3.0"], tmp)
        check("promote: a candidate that is not the expected version is refused",
              code == 1 and "expected" in err, err)


def test_promote_refuses_gaps():
    with tempfile.TemporaryDirectory(prefix="rg-promote-") as tmp:
        gates, _ = green_gate_reports(tmp)

        def run(evidence, extra=()):
            path = Path(tmp) / "e.json"
            path.write_text(json.dumps(evidence), encoding="utf-8")
            return run_gates(["promote", "--evidence", str(path), *gates,
                              *extra], tmp)

        bad = good_evidence()
        bad["checks"]["tests"]["sha"] = "1" * 40
        code, out, err = run(bad)
        check("promote: evidence gathered for another SHA cannot promote",
              code == 1 and "another build" in err, err)

        bad = good_evidence()
        del bad["checks"]["dependencies"]
        code, out, err = run(bad)
        check("promote: missing dependency/vulnerability evidence fails",
              code == 1 and "dependencies" in err, err)

        bad = good_evidence()
        bad["checks"]["artifacts"]["images"]["mrmap-frontend"] = {"tag": "0.2.0"}
        code, out, err = run(bad)
        check("promote: an artifact without an exact digest fails",
              code == 1 and "digest" in err, err)

        bad = good_evidence()
        bad["checks"]["sonar"]["status"] = "none"
        code, out, err = run(bad)
        check("promote: a red Sonar gate is refused",
              code == 1 and "did not pass" in err, err)

        (Path(tmp) / "upgrade.json").write_text(
            json.dumps({"gate": "upgrade", "ok": False}), encoding="utf-8")
        code, out, err = run(good_evidence())
        check("promote: a red upgrade gate report is refused",
              code == 1 and "upgrade" in err and "red" in err, err)

        (Path(tmp) / "upgrade.json").write_text(
            json.dumps({"gate": "upgrade", "ok": True}), encoding="utf-8")
        code, out, err = run(good_evidence(version="not-semver"))
        check("promote: a candidate that is not strict SemVer is refused",
              code == 1 and "SemVer" in err, err)

        code, out, err = run(good_evidence(),
                             extra=["--sha", "deadbeef"])
        check("promote: a sha that is not 40 hex cannot be attested",
              code == 1 and "40 hex" in err, err)

        code, out, err = run_gates(
            ["promote", "--evidence", str(Path(tmp) / "e.json")], tmp)
        check("promote: attesting without the gate reports fails, "
              "it is not a formality", code == 1 and "gate report" in err, err)


# ---------------------------------------------------------------------- main


def main():
    for fn in (
            test_api_identical_is_green,
            test_api_removed_operation_needs_review,
            test_api_stale_exception_fails,
            test_api_surface_findings,
            test_api_params_and_status,
            test_api_additive_counts,
            test_api_modes,
            test_api_stale_candidate_refused,
            test_api_ledger_validation,
            test_api_ref_resolution,
            test_version_empty_range,
            test_version_migration_needs_a_note,
            test_version_required_config_needs_a_note,
            test_version_breaking_needs_a_breaking_line,
            test_version_bump_policy,
            test_version_equal_and_backwards,
            test_semver_precedence_not_dot_splitting,
            test_version_prerelease_candidate,
            test_version_baseline_must_be_stable,
            test_upgrade_clean_migration_passes,
            test_upgrade_fake_migration_fails_then_marked_passes,
            test_upgrade_noop_runpython_is_fake,
            test_upgrade_destructive_needs_approval,
            test_upgrade_protected_node_gone_fails,
            test_upgrade_retired_app_named_again,
            test_upgrade_graph_conflict_caught,
            test_promote_full_evidence,
            test_promote_refuses_gaps,
    ):
        fn()

    failed = 0
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}"
              + (f"  [{detail[:400]}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
