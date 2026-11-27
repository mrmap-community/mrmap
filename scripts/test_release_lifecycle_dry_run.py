#!/usr/bin/env python3
"""test_release_lifecycle_dry_run: replay the whole release lifecycle offline.

Issue #1586 (epic #1577). #1585 committed the machine-readable lifecycle
(`scripts/release_lifecycle.json`) and #1584 the promotion tool that acts on it;
#1585's own suite holds that description against the files it names, and the
suites of #1583 and #1584 prove each tool in isolation. None of them answers the
question this issue asks: do the documented phases, the actors they name and the
systems they depend on fit together for one complete release, and what blocks a
dry run?

This suite walks a synthetic mrmap-shaped repository through every phase of
`release_lifecycle.json` from `pre-release` to `post-release` with real git, the
real gate tools, the real promotion tool and the journaling `gh` shim of #1584.
Nothing here talks to GitHub: no tag, release or image is published anywhere,
the only refs that ever exist live in a throw-away directory, and no credential
is read. `git` runs with `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` pointed at
/dev/null, so no developer identity or credential helper can leak into the walk.

The answer this suite owes is a report of two halves, and the acceptance
criteria require both:

  what the dry run exercised   every phase it walked, with the command it
                               actually ran and the verdict that command
                               answered - never an assumed pass, because a phase
                               that was skipped or mocked must not be presented
                               as verified;
  what still needs a real stack  every item that cannot be decided offline, each
                               naming the mechanism that owns it. The runtime
                               evidence of the promotion gate needs the QA
                               containers (GDAL plus `manage.py spectacular` for
                               the candidate document, the real CI job names
                               behind `unit-tests`, `acceptance-tests` and
                               `sonarcloud`, the built images whose digests the
                               attestation binds); the CI upgrade run from the
                               oldest supported baseline and the rollback drill
                               need a PostgreSQL that does not exist here; and
                               the human acts - the cut, the protected-environment
                               approval, the merge, the sync - are listed as
                               reserved to people, since an automation that could
                               perform them would not have tested the constraint
                               that reserves them.

Every item of the second half is derived, not hardcoded: it names the lifecycle's
own phase evidence strings, `release_gates.REQUIRED_EVIDENCE`, the CI job names
`release_promotion.CHECK_CLASSES` maps to them, the gate reports the promoter
demands and the protected environment of the lifecycle's `promote` phase. So a
phase whose mechanism becomes drivable offline cannot keep sitting in the blocked
list unnoticed.

The honest-red rule of `scripts/test_release_gates.py` applies to the walk: a
phase is only proven when it was also seen to stop a wrong candidate. So
`build-and-gate` is walked red on a VERSION move without its folded changelog
section, `promote` red on a missing evidence class and on evidence gathered for
another sha, `verify-on-master` red on a master whose tree diverged and on a
missing artifact digest. The walk refuses rolling aliases while no reviewed
alias ledger exists, and cuts a prerelease without ever letting it take the
stable identity of its line.

Run from the repository root:
    python3 scripts/test_release_lifecycle_dry_run.py [--report report.json]

Exit 0 when every phase walked with the verdict the lifecycle promises, 1 when a
phase broke or the report lost a half, 2 when the harness could not run.
"""
import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import workflow_steps
LIFECYCLE = HERE / "release_lifecycle.json"
PROMOTION_WORKFLOW = REPO / ".github" / "workflows" / "release-promotion.yml"
# The documentation gate the promotion calls for its required portal build (#1609).
DOCS_GATE_WORKFLOW = REPO / ".github" / "workflows" / "docs-release-gate.yml"
VERIFY_STEP = "Verify the reviewed release pull request"
PUBLISH_STEP = "Publish the tag and the GitHub release"
GATE_REVISION_STEP = "Refuse a release build that cannot name its revision"
GATE_NAME_STEP = "Name the build"
GATE_PROVENANCE_STEP = "Assert the build documented the reviewed revision"
TIME_BUDGET_S = float(os.environ.get("RELEASE_DRY_RUN_TIMEOUT_S", "600"))
TOOLS = ["release_gates.py", "canonical_version.py",
         "pr_classify", "migration_graph_smoke.py",
         "release_contract_baseline.json", "release_contract_exceptions.json",
         "release_upgrade_baseline.json", "release_lifecycle.json"]
# the runtime facts the promotion gate owes, and which nothing here may fabricate
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64
MANUAL = ["--manual=dependencies=https://github.example.test/dependency-audit"]
ARTIFACTS = ["--artifact=mrmap-backend=" + BACKEND_DIGEST,
             "--artifact=mrmap-frontend=" + FRONTEND_DIGEST]
RESULTS = []
STARTED = datetime.now(timezone.utc)


class HarnessCannotRun(Exception):
    """The dry run could not run at all - exit 2, never reported as a pass."""


class PhaseFailed(Exception):
    """A walked phase answered something other than what the lifecycle promises.
    That is a finding of the dry run, not a harness fault."""


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GATES = module(HERE / "release_gates.py", "release_gates")
CANON = module(HERE / "canonical_version.py", "canonical_version")

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null",
               GIT_CONFIG_SYSTEM="/dev/null")


def git(*argv, cwd=None, check_ok=True):
    proc = subprocess.run(["git", *argv], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, env=GIT_ENV)
    if check_ok and proc.returncode != 0:
        raise HarnessCannotRun(f"git {' '.join(argv)}: {proc.stderr.strip()}")
    return proc


def stdout_head(value, limit=200):
    """A report line for a tool that answers text, not JSON."""
    text = value if isinstance(value, str) else json.dumps(value)
    return text.strip().replace("\n", " | ")[:limit]


def stderr_head(proc, limit=200):
    return (proc.stderr or proc.stdout)[:limit].replace("\n", " ")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def elapsed():
    return (datetime.now(timezone.utc) - STARTED).total_seconds()


def read_lifecycle():
    try:
        return json.loads(LIFECYCLE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HarnessCannotRun(f"cannot read {LIFECYCLE}: {error}")


def within_budget(minutes):
    return elapsed() < minutes * 60


# ------------------------------------------------------------------ gh shim

GH_SHIM = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
state_path = os.environ["GH_STATE"]
with open(os.environ["GH_JOURNAL"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")
try:
    state = json.load(open(state_path, encoding="utf-8"))
except FileNotFoundError:
    state = {"prs": [], "releases": []}


def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None


def save():
    json.dump(state, open(state_path, "w", encoding="utf-8"))


if argv[:2] == ["pr", "list"]:
    out = [p for p in state["prs"]
           if p["headRefName"] == flag("--head")
           and p["baseRefName"] == flag("--base")]
    if flag("--jq") is not None:
        # the promotion workflow asks for the merged release pull request of a
        # base/head pair and reads its merge commit; answering the query it
        # actually makes is what keeps the walk honest about what is missing
        want = (flag("--base"), flag("--head"), flag("--state"))
        if want != ("master", "develop", "merged"):
            sys.stderr.write("gh shim: unexpected pr list query %r\\n" % (want,))
            sys.exit(1)
        merged = [p for p in out
                  if p.get("mergedAt") and (p.get("mergeCommit") or {}).get("oid")]
        if not merged:
            print("")
        else:
            latest = sorted(merged, key=lambda p: p["mergedAt"])[-1]
            print("%d %s" % (latest["number"], latest["mergeCommit"]["oid"]))
    else:
        print(json.dumps(out))
elif argv[:2] == ["pr", "create"]:
    n = 100 + len(state["prs"]) + 1
    state["prs"].append({"number": n, "state": "OPEN",
                         "headRefName": flag("--head"),
                         "baseRefName": flag("--base"),
                         "title": flag("--title")})
    save()
    print("https://github.example.test/pull/%d" % n)
elif argv[:2] == ["release", "view"]:
    tag = argv[2]
    found = next((r for r in state["releases"] if r["tagName"] == tag), None)
    if found:
        print(json.dumps(found))
    else:
        sys.stderr.write("release %s not found\\n" % tag)
        sys.exit(1)
elif argv[:2] == ["release", "create"]:
    tag = argv[2]
    state["releases"].append({"tagName": tag,
                              "url": "https://github.example.test/r/" + tag})
    save()
    print("https://github.example.test/r/" + tag)
else:
    sys.stderr.write("gh shim: unhandled call: " + " ".join(argv) + "\\n")
    sys.exit(1)
"""


# ------------------------------------------------------------- repo fixtures

ADD_FIELD = ("        migrations.AddField(model_name='x', name='y', "
             "field=None),\n")
EMPTY_OPS = ""
MIG_HEAD = ("from django.db import migrations\n\n\n"
            "class Migration(migrations.Migration):\n"
            "    dependencies = [\n%s    ]\n\n"
            "    operations = [\n%s    ]\n")


def migration_file(deps, ops):
    dep_src = "".join(f"        ('{app}', '{name}'),\n" for app, name in deps)
    return MIG_HEAD % (dep_src, ops)


def write_files(root, files):
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def commit_all(root, message):
    git("add", "-A", cwd=root)
    git("commit", "-qm", message, cwd=root)


BASE_VERSION = "0.1.0"
CANDIDATE_VERSION = "0.2.0"
PRERELEASE_VERSION = "0.2.0-rc.1"


def base_files(version):
    """The mrmap-shaped base: the real tools, the real reviewed contract content
    of this checkout, a canonical version with its projection, and the migration
    baseline the upgrade gate protects."""
    files = {
        "VERSION": version + "\n",
        "backend/MrMap/version.py": CANON.render_projection(version),
        ".release-please-manifest.json": json.dumps({".": version}) + "\n",
        "CHANGELOG.md": (
            "# Changelog\n\n## Unreleased\n\n"
            "\n## [0.1.0] - 2023-03-23\n\n- the first shape of it all\n"),
        "backend/MrMap/settings.py": "INSTALLED_APPS = ['registry', 'notify']\n",
        "app.txt": f"state of {version}\n",
    }
    # the migration graph of the walk carries every node the committed #1180
    # constraints protect, under exactly those names, with the marker node among
    # them: the upgrade gate then has the same boundaries to find as in mrmap.
    chain = ["0001_initial",
             "0002_alter_backgroundprocess_date_created_and_more",
             "0003_backgroundprocess_status",
             "0004_backgroundprocess_bgproc_date_created_idx",
             "0005_alter_backgroundprocess_process_type",
             "0006_remove_backgroundprocess_threads"]
    mig = "backend/notify/migrations"
    previous = None
    for name in chain:
        files[f"{mig}/{name}.py"] = migration_file(
            [] if previous is None else [("notify", previous)], ADD_FIELD)
        previous = name
    files["backend/registry/migrations/0001_initial.py"] = migration_file(
        [], ADD_FIELD)
    for rel in ("scripts/release_contract_baseline.json",
                "scripts/release_contract_exceptions.json",
                "scripts/release_upgrade_baseline.json"):
        files[rel] = (REPO / rel).read_text(encoding="utf-8")
    for tool in TOOLS:
        files[f"scripts/{tool}"] = (HERE / tool).read_text(encoding="utf-8")
    return files


def planned_release_files(version, notes=True):
    """The five files of a planned release plus the migration its notes name."""
    files = {
        "VERSION": version + "\n",
        "backend/MrMap/version.py": CANON.render_projection(version),
        ".release-please-manifest.json": json.dumps({".": version}) + "\n",
        "CHANGELOG.md": (
            "# Changelog\n\n## Unreleased\n\n"
            + ("### Migration notes\n\n- notify.0007_a_new_column records "
               "what it changes (#1586)\n\n" if notes else "")
            + f"## [{version}] - 2026-11-20\n\n"
            "### Features\n\n- a reviewed feature\n\n"
            "\n## [0.1.0] - 2023-03-23\n\n- the first shape of it all\n"),
        "backend/notify/migrations/0007_a_new_column.py": migration_file(
            [("notify", "0006_remove_backgroundprocess_threads")], ADD_FIELD),
        "app.txt": f"state of {version}\n",
    }
    return files


def openapi_doc(version):
    """A candidate document shaped like what `manage.py spectacular` answers.

    The api gate refuses a document whose `info.version` is not the checkout's
    VERSION, so the version travels with the fixture and a stale file is a
    scenario of its own.
    """
    return {
        "openapi": "3.0.3",
        "info": {"title": "mrmap", "version": version},
        "paths": {
            "/api/registry/wms": {"get": {
                "operationId": "webmapservice_list",
                "parameters": [{"name": "filter[title]", "in": "query",
                                "required": False,
                                "schema": {"type": "string"}}],
                "responses": {"200": {"description": "ok", "content": {
                    "application/vnd.api+json": {"schema": {
                        "type": "object", "properties": {
                            "data": {"type": "array"}}}}}}}}}},
        "components": {"schemas": {}},
    }


def checks_payload():
    """What `gh run list --json ...` answers for a candidate whose CI is green:
    the job names of #1584's CHECK_CLASSES, the artifact job and the dependency
    audits."""
    return [
        {"name": "unit-tests", "conclusion": "success",
         "html_url": "https://github.example.test/run/unit"},
        {"name": "acceptance-tests", "conclusion": "success",
         "html_url": "https://github.example.test/run/accept"},
        {"name": "sonarcloud", "conclusion": "success",
         "html_url": "https://github.example.test/run/sonar"},
        {"name": "dependency-audit", "conclusion": "success",
         "html_url": "https://github.example.test/run/deps"},
        {"name": "security-scan", "conclusion": "success",
         "html_url": "https://github.example.test/run/scan"},
        {"name": "build-and-push", "conclusion": "success",
         "html_url": "https://github.example.test/run/build"},
    ]


# ------------------------------------------------------------------ the walk

class DryRun:
    """One isolated lifecycle walk through a throw-away, mrmap-shaped repo.

    `repo` is the clone and `origin` its local bare remote: no ref this walk
    writes ever leaves that directory. `gh` is the journaling shim above, so the
    journal doubles as the audit trail the issue asks to record - and anything
    the tools ask GitHub beyond its small table fails loudly instead of quietly
    doing nothing.
    """

    def __init__(self, tmp, name, version=BASE_VERSION):
        self.dir = Path(tmp) / name
        self.dir.mkdir(parents=True)
        origin = self.dir / "origin.git"
        self.repo = self.dir / "clone"
        self.gh = self.dir / "gh"
        self.state = self.dir / "gh-state.json"
        self.journal = self.dir / "gh-journal.jsonl"
        self.gh.write_text(GH_SHIM, encoding="utf-8")
        self.gh.chmod(0o755)
        self.state.write_text('{"prs": [], "releases": []}', encoding="utf-8")
        git("init", "--bare", "--initial-branch=develop", str(origin))
        git("clone", "-q", str(origin), str(self.repo))
        for key, value in (("user.email", "dryrun@example.invalid"),
                           ("user.name", "dry run"),
                           ("commit.gpgsign", "false")):
            git("config", key, value, cwd=self.repo)
        self.version = version
        self.steps = []
        self.blocked = {}
        write_files(self.repo, base_files(version))
        commit_all(self.repo, "chore: the shape of a deployment")
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.repo)
        git("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.repo)
        git("branch", "master", "origin/master", cwd=self.repo)
        self.baseline_commit = git(
            "rev-parse", "HEAD", cwd=self.repo).stdout.strip()

    # -- recording ---------------------------------------------------------

    def record(self, phase, verdict, what, means, note=""):
        self.steps.append({"phase": phase, "verdict": verdict, "what": what,
                           "means": means, "note": note})

    def blocked_on(self, key, text):
        self.blocked.setdefault(key, text)

    # -- driving the tools -------------------------------------------------

    def sh(self, argv):
        env = dict(GIT_ENV, GH_TOKEN="",
                   PATH=f"{self.dir}" + os.pathsep + os.environ.get("PATH", ""))
        env.update(GH_STATE=str(self.state), GH_JOURNAL=str(self.journal))
        return subprocess.run(argv, cwd=str(self.repo), env=env,
                              capture_output=True, text=True)

    def canonical(self, *argv):
        return self.sh([sys.executable, str(self.repo / "scripts"
                                            / "canonical_version.py"),
                        "--root", str(self.repo), *argv])

    def gates(self, *argv):
        return self.sh([sys.executable, str(self.repo / "scripts"
                                            / "release_gates.py"),
                        "--root", str(self.repo), *argv])

    # -- driving the promotion workflow -------------------------------------
    #
    # The promotion has no tool any more, so the walk drives the thing itself:
    # the step scripts are read out of the committed workflow YAML and run under
    # bash with the same environment Actions would give them. There is no
    # `promote` command to call and no state to seed first, because that is the
    # point of #1798 - the two facts that decide publication are GitHub's and
    # git's, and this walk can only supply them the way the runner does.

    def _step(self, job, step_name, env_extra, workflow=PROMOTION_WORKFLOW):
        # scripts/workflow_steps.py reads the `run:` block: PyYAML is no stdlib
        # dependency and no runner has it, which is how this walk once failed
        # shut in CI. A step that is not there is an error from the reader, not
        # a silently empty script.
        script = workflow_steps.step_script(
            workflow.read_text(encoding="utf-8"), job, step_name)
        path = self.dir / f"step-{job}-{abs(hash(step_name))}.sh"
        path.write_text(script, encoding="utf-8")
        env = dict(GIT_ENV, GH_TOKEN="",
                   GITHUB_REPOSITORY="mrmap-community/mrmap",
                   GITHUB_OUTPUT=str(self.dir / "gh-output"),
                   RUNNER_TEMP=str(self.dir),
                   PATH=f"{self.dir}" + os.pathsep + os.environ.get("PATH", ""))
        env.update(GH_STATE=str(self.state), GH_JOURNAL=str(self.journal))
        env.update(env_extra)
        (self.dir / "gh-output").write_text("", encoding="utf-8")
        proc = subprocess.run(["bash", str(path)], cwd=str(self.repo), env=env,
                              capture_output=True, text=True)
        outputs = {}
        for line in (self.dir / "gh-output").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                outputs[key] = value
        return proc, outputs

    def verify_step(self, version):
        return self._step("verify", VERIFY_STEP, {"VERSION": version})

    def gate_step(self, step_name, env_extra):
        """One shell step of the documentation gate's portal job (#1609)."""
        return self._step("portal", step_name, env_extra,
                          workflow=DOCS_GATE_WORKFLOW)

    def docs_gate(self, sha, tag, release):
        """Drive the gate the promotion calls, for one revision (#1609).

        The gate is one callable job whose strict build IS the release gate, so
        the walk runs its own shell rather than describing it: the refusal of a
        call that cannot name its revision, the naming of the build, and the
        provenance assertion. Sphinx itself is not run offline - that is the
        pinned toolchain of the portal job, and it is listed as blocked - so the
        artifact a build leaves behind is handed over in exactly the shape the
        project's own Sphinx extension writes it
        (docs/source/_ext/mrmap_docs.py).
        """
        base = {"MRMAP_DOCS_PYTHON": sys.executable,
                "GITHUB_EVENT_NAME": "workflow_call",
                "INPUT_TAG": tag}
        proc, _ = self.gate_step(GATE_REVISION_STEP, dict(base, REVISION=sha))
        expect(proc.returncode == 0, "promote",
               f"the gate refused the revision it was called with: "
               f"{proc.stdout}{proc.stderr}")
        proc, named = self.gate_step(GATE_NAME_STEP, base)
        expect(proc.returncode == 0 and named.get("tag") == tag, "promote",
               f"the gate did not name the build for {tag}: {named}")
        self.write_portal(sha, release)
        proc, proven = self.gate_step(GATE_PROVENANCE_STEP, dict(base, REVISION=sha))
        expect(proc.returncode == 0
               and proven.get("documented_commit") == sha, "promote",
               f"the gate refused its own portal: {proc.stdout}{proc.stderr}")
        return named, proven

    def write_portal(self, sha, release):
        """The artifact a strict portal build leaves behind, in the shape the
        project's own Sphinx extension writes (docs/source/_ext/mrmap_docs.py)."""
        build = self.repo / "docs" / "build" / "html"
        build.mkdir(parents=True, exist_ok=True)
        (build / "provenance.json").write_text(json.dumps({
            "schema": "mrmap.docs.provenance.v1", "builder": "html",
            "version": release, "release": release,
            "documented_commit": sha, "toolchain": {"sphinx": "8.2.3"},
            "source_digest": "sha256:" + "0" * 64,
        }), encoding="utf-8")

    def publish_step(self, verified, publish=True, artifacts=None,
                     docs_commit=None, docs_release=None):
        if artifacts is None:
            artifacts = "\n".join(
                line.removeprefix("--artifact=") for line in ARTIFACTS)
        merge = verified.get("merge_commit", "")
        version = verified.get("version", "")
        return self._step("publish", PUBLISH_STEP, {
            "VERSION": version,
            "MERGE_COMMIT": merge,
            "TAG": verified.get("tag", ""),
            "PUBLISH": "true" if publish else "false",
            "ARTIFACTS": artifacts,
            # The two outputs the required documentation job hands down (#1609).
            # Green by default - the gate built the candidate - so every existing
            # world keeps testing what it tested; pass another answer for a
            # refusal.
            "DOCS_COMMIT": merge if docs_commit is None else docs_commit,
            "DOCS_RELEASE": version if docs_release is None else docs_release})

    # -- repo moves --------------------------------------------------------

    def write(self, files):
        write_files(self.repo, files)

    def commit(self, message):
        commit_all(self.repo, message)

    def advance(self, message="feat: a reviewed feature",
                version=CANDIDATE_VERSION, notes=True):
        """What the Version Release PR of the `cut` phase lands on develop."""
        git("checkout", "-q", "-B", "develop", "origin/develop", cwd=self.repo)
        self.write({"app.txt": f"state of {version} after a reviewed change\n"})
        self.commit(message)
        self.write(planned_release_files(version, notes=notes))
        self.commit(f"chore(release): release {version}")
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.repo)
        self.candidate = git(
            "rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        self.candidate_version = version
        return self.candidate

    def merge_release_pr(self, version, diverge=False, force=False):
        """The person's reviewed develop -> master merge, landed the way GitHub
        lands it: a merge commit whose parents are master's tip and develop's
        tip, so master carries the candidate's tree without being the candidate.
        The merge is also what makes the release pull request answerable, so the
        pull request record and its mergeCommit are written here and nowhere
        else. `diverge` lands one more commit on master afterwards, which is the
        state the promotion must refuse."""
        git("fetch", "-q", "origin", cwd=self.repo)
        git("checkout", "-q", "-B", "master", "origin/master", cwd=self.repo)
        if force:
            git("revert", "--no-edit", "HEAD", cwd=self.repo)
        else:
            git("merge", "--no-ff", "-q",
                "-m", f"Merge pull request #{self.next_pr_number()} from "
                      "mrmap-community/develop",
                "-m", f"release: promote {version}",
                "origin/develop", cwd=self.repo)
        tip = git("rev-parse", "HEAD", cwd=self.repo).stdout.strip()
        if not force and diverge:
            # the state the promotion has to refuse: master moved after the
            # reviewed merge, so the merge commit and master's tip differ
            self.write({"hotfix.txt": "an unreviewed extra on master\n"})
            self.commit("fix: something landed on master that was not "
                        "reviewed")
        git("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.repo)
        git("checkout", "-q", "-B", "develop", "origin/develop", cwd=self.repo)
        if not force:
            state = self.gh_state()
            state["prs"].append({"number": self.next_pr_number(), "state": "MERGED",
                                 "headRefName": "develop", "baseRefName": "master",
                                 "title": f"release: promote {version}",
                                 "mergedAt": now(),
                                 "mergeCommit": {"oid": tip}})
            self.state.write_text(json.dumps(state), encoding="utf-8")
        return tip

    def next_pr_number(self):
        return 100 + len(self.gh_state()["prs"]) + 1

    def open_sync_pr(self):
        """The master -> develop sync as the ordinary reviewed pull request #1798
        leaves it: gh opens it, a person merges it. Returns the shim's record."""
        proc = self.sh([str(self.gh), "pr", "create", "--head", "master",
                        "--base", "develop", "--title",
                        "chore: sync master back into develop"])
        if proc.returncode != 0:
            return None
        return next((p for p in self.gh_state()["prs"]
                     if p["baseRefName"] == "develop" and p["state"] == "OPEN"),
                    None)

    # -- reading the world back --------------------------------------------

    def journal_calls(self):
        if not self.journal.exists():
            return []
        return [json.loads(line) for line in
                self.journal.read_text(encoding="utf-8").splitlines() if line]

    def remote_ref(self, ref):
        out = git("ls-remote", "origin", ref, cwd=self.repo, check_ok=False)
        for line in out.stdout.splitlines():
            sha, name = line.split("\t", 1)
            if name == ref:
                return sha
        return None

    def tree_of(self, ref):
        return git("rev-parse", f"{ref}^{{tree}}", cwd=self.repo).stdout.strip()

    def remote_tree(self, ref):
        sha = self.remote_ref(ref)
        return self.tree_of(sha) if sha else None

    def remote_tag_commit(self, tag):
        """The COMMIT an annotated tag points at, not the tag object."""
        return (self.remote_ref(f"refs/tags/{tag}^{{}}")
                or self.remote_ref(f"refs/tags/{tag}"))

    def remote_tags(self):
        out = git("ls-remote", "--tags", "origin", cwd=self.repo,
                  check_ok=False)
        return sorted(line.split("\t")[-1].replace("refs/tags/", "")
                      for line in out.stdout.splitlines()
                      if line.split("\t")[-1].startswith("refs/tags/")
                      and not line.split("\t")[-1].endswith("^{}"))

    def gh_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def git_restore(self):
        """Undo an uncommitted experiment; the repo is throw-away, so a full
        checkout of the tracked tree is the cheapest honest undo."""
        git("checkout", "--", ".", cwd=self.repo)

    def commits_touching(self, path):
        return [line for line in git("log", "--pretty=%s", "HEAD", "--", path,
                                     cwd=self.repo).stdout.splitlines()]


# ----------------------------------------------------- derived blocked items


def blocked_items(lifecycle):
    """What a dry run cannot decide offline, derived from the tools' own names.

    Nothing here is a fixed list: every entry is built from a constant of the
    tooling (the evidence classes, the CI job names, the required images, the
    protected environment, the oldest supported baseline), so a mechanism that
    becomes drivable offline drops out of this list by itself.
    """
    items = []
    jobs = sorted({entry["name"] for entry in checks_payload()})
    items.append({
        "item": "runtime evidence of the promotion gate",
        "why": "the candidate OpenAPI document needs GDAL and `manage.py "
               "spectacular`, and the classes "
               + "/".join(GATES.REQUIRED_EVIDENCE)
               + " come from real CI runs; here they are a saved payload fed "
               "through release_gates' own --evidence seam",
        "owner": ", ".join(jobs),
    })
    items.append({
        "item": "the built images the attestation binds",
        "why": "digests of " + ", ".join(GATES.REQUIRED_IMAGES)
               + " are published by the build of #1799 and bound by #1800; the "
               "walk passes well-formed digests through the release body but "
               "cannot pull them",
        "owner": "#1799 (build and promote images by digest)",
    })
    constraints = json.loads(
        (REPO / "scripts" / "release_upgrade_baseline.json")
        .read_text(encoding="utf-8"))
    items.append({
        "item": "the CI upgrade run from the oldest supported baseline",
        "why": "the upgrade gate checks the graph and the boundaries offline, "
               "but the actual migrate of a deployment needs PostgreSQL; the "
               "baseline is " + str(constraints["oldest_supported_baseline"])
               + " (marker " + constraints["marker_migration"] + ")",
        "owner": ".github/workflows/quality-assurance.yml",
    })
    items.append({
        "item": "the rollback drill",
        "why": "a rollback is a database operation, and no PostgreSQL exists "
               "in an offline suite",
        "owner": lifecycle["operator_runbook"]["page"] + " (Rollback)",
    })
    env = lifecycle["phases"][PHASE_INDEX["promote"]].get("environment")
    if env:
        items.append({
            "item": "the protected-environment approval of the promotion",
            "why": f"the publishing job of the promotion runs behind {env!r}, "
                   "whose required reviewers are people; the walk runs the same "
                   "steps with gh pointed at a shim, so the steps are exercised "
                   "but the approval is not",
            "owner": f"GitHub environment {env}",
        })
    humans = sorted({phase["actor"] for phase in lifecycle["phases"]
                    if phase["actor"] == "human"})
    if humans:
        items.append({
            "item": "the human acts of those phases",
            "why": "the phases whose actor is " + "/".join(humans) + " ("
                   + ", ".join(
                       phase["id"] for phase in lifecycle["phases"]
                       if phase["actor"] == "human")
                   + ") are simulated by git moves the walk performs on behalf "
                   "of a person; the constraint that reserves them ("
                   + lifecycle["constraints"]["approvals"]
                   + ") is asserted, never exercised",
            "owner": lifecycle["constraints"]["approvals"],
        })
    return items


# ------------------------------------------------------------ phase machinery

PHASE_INDEX = {}


def expect(cond, phase, detail):
    if not cond:
        raise PhaseFailed(f"{phase}: {detail}")



def write_evidence(w, sha, version, checks=None, path=None):
    """The CI conclusions bound to one sha, in the shape release_gates promotes.

    #1799 builds the images and #1800 binds the jobs; until then the walk feeds
    the committed aggregation the payload it would receive, and the sha inside it
    is the point: evidence gathered for another commit must not promote this one.
    """
    checks = checks_payload() if checks is None else checks
    payload = w.dir / "checks.json"
    payload.write_text(json.dumps(checks), encoding="utf-8")
    evidence = path or (w.dir / f"evidence-{sha[:12]}.json")
    # Which class a job answers for is the mapping #1800 will own; here the
    # job's own name decides it, so dropping a job from the payload really does
    # drop its class instead of shifting the next job into its place.
    classes = {"unit-tests": "tests", "acceptance-tests": "tests",
               "sonarcloud": "sonar", "dependency-audit": "dependencies",
               "security-scan": "dependencies"}
    checks_map = {}
    for entry in checks:
        klass = classes.get(entry["name"])
        if klass:
            checks_map[klass] = {"status": "pass", "sha": sha,
                                 "url": entry.get("html_url",
                                                  "https://github.example.test/ci")}
    images = {}
    for line in ARTIFACTS:
        name, _, digest = line.removeprefix("--artifact=").partition("=")
        images[name] = {"digest": digest, "sha": sha}
    checks_map["artifacts"] = {"status": "pass", "sha": sha, "images": images}
    evidence.write_text(json.dumps({
        "candidate": {"sha": sha, "version": version},
        "checks": checks_map,
    }), encoding="utf-8")
    return evidence


def phase_pre_release(w, lifecycle):
    """Code changes only, no version question yet."""
    expect(lifecycle["phases"][0]["actor"] == "contributor", "pre-release",
           "the lifecycle no longer says who performs this phase")
    proc = w.canonical("--check")
    expect(proc.returncode == 0, "pre-release",
           f"canonical_version --check on the untouched base: {proc.stderr}")
    w.record("pre-release", "ok", "canonical version and projection agree",
             "scripts/canonical_version.py --check")
    # the drift scenario of #1581's version gate, driven as the pre-release
    # phase itself must be judged: a hand-edited VERSION is refused.
    w.write({"VERSION": "9.9.9\n"})
    proc = w.canonical("--check")
    expect(proc.returncode == 1, "pre-release",
           "a hand-edited VERSION passed the drift check")
    check("pre-release refuses a hand-edited VERSION",
          "does not match" in proc.stderr + proc.stdout,
          (proc.stderr + proc.stdout)[:160])
    w.git_restore()
    proc = w.canonical("--write")
    expect(proc.returncode == 0, "pre-release", "canonical --write failed")
    proc = w.canonical("--check")
    expect(proc.returncode == 0, "pre-release",
           "the regenerated projection still drifts")
    w.record("pre-release", "ok",
             "the drift is repaired by the tool, not by hand",
             "scripts/canonical_version.py --write")
    w.git_restore()
    # a phase of code changes only: no bump is owed and no notes are missing
    proc = w.gates("version", "--report", str(w.dir / "version-0.json"))
    expect(proc.returncode == 0, "pre-release",
           f"the version gate refused a range that adds nothing: {proc.stderr}")
    w.record("pre-release", "ok",
             "no bump and no migration notes owed by a plain code change",
             "scripts/release_gates.py version")
    proc = w.gates("upgrade", "--report", str(w.dir / "upgrade-0.json"))
    expect(proc.returncode == 0, "pre-release",
           f"the upgrade gate refused the untouched graph: {proc.stderr}")
    w.record("pre-release", "ok", "one leaf per app, protected nodes present",
             "scripts/release_gates.py upgrade")
    # and the honest red half of the upgrade gate: a fake node is refused, the
    # reviewed marker makes it green again.
    fake = "backend/notify/migrations/0008_a_hollow_node.py"
    w.write({fake: migration_file(
        [("notify", "0006_remove_backgroundprocess_threads")], EMPTY_OPS)})
    w.commit("feat: a hollow migration node")
    proc = w.gates("upgrade")
    expect(proc.returncode == 1, "pre-release",
           "a migration with no operations passed the upgrade gate")
    check("upgrade gate refuses a fake migration node",
          "fake migration" in proc.stderr, proc.stderr[:160])
    w.write({fake: "# release-gates: empty-operations -- refs #1586\n"
                   + (w.repo / fake).read_text(encoding="utf-8")})
    w.commit("chore: the marker a human reviews")
    proc = w.gates("upgrade")
    expect(proc.returncode == 0, "pre-release",
           f"the marker did not make the node reviewable: {proc.stderr}")
    w.record("pre-release", "ok",
             "red on a fake node, green once the reviewed marker names it",
             "scripts/release_gates.py upgrade")


def phase_cut(w, lifecycle):
    """The Version Release PR: proposed by the planner, merged by a person."""
    expect(lifecycle["phases"][1]["actor"] == "human", "cut",
           "the lifecycle no longer reserves the cut to a person")
    # the cut is the Version Release PR onto develop: what a person merges
    # there is what moves the version, so the walk starts where develop starts.
    check("cut: develop starts at the base version",
          (w.repo / "VERSION").read_text(encoding="utf-8").strip()
          == BASE_VERSION, (w.repo / "VERSION").read_text(encoding="utf-8"))
    w.advance()
    w.record("cut", "ok",
             "the Version Release PR merged onto develop carries the release "
             "files (simulated merge, the constraint is asserted not exercised)",
             "git merge of the planned release files into develop")
    check("cut: the version bump is the class the range earned",
          w.candidate_version == CANDIDATE_VERSION,
          f"a feat range must move the minor above the base {BASE_VERSION}, "
          f"the release files carry {w.candidate_version}")
    # Nothing may be published before a person merges the reviewed release pull
    # request, and the walk proves the promotion says so rather than asserting
    # it: the verify step runs against a develop whose release PR is unmerged.
    proc, _ = w.verify_step(w.candidate_version)
    expect(proc.returncode == 1, "cut",
           f"verify published before anyone merged: {proc.stdout}{proc.stderr}")
    expect("no merged develop -> master release pull request" in proc.stdout,
           "cut", stderr_head(proc))
    w.record("cut", "ok",
             "the planned release is refused by verify while no person has "
             "merged it to master",
             "the verify step of .github/workflows/release-promotion.yml",
             proc.stdout.strip().splitlines()[0])


def phase_build_and_gate(w, lifecycle):
    """The candidate is judged by the three gates and attested."""
    reports = []
    doc = w.dir / "candidate.openapi.json"
    doc.write_text(json.dumps(openapi_doc(w.candidate_version)), encoding="utf-8")
    for name in ("api", "version", "upgrade"):
        report = w.dir / f"{name}.json"
        argv = [name, "--report", str(report)]
        if name == "api":
            argv += ["--candidate", str(doc)]
        proc = w.gates(*argv)
        expect(proc.returncode == 0, "build-and-gate",
               f"the {name} gate refused the candidate: {proc.stderr}")
        reports.append(f"{name}={report}")
        w.record("build-and-gate", "ok", f"the {name} gate passes the candidate",
                 f"scripts/release_gates.py {name}")
    proc = w.sh([sys.executable, str(w.repo / "scripts" / "release_gates.py"),
                 "--root", str(w.repo), "api", "--candidate", str(doc),
                 "--skip-version-check"])
    expect(proc.returncode == 0, "build-and-gate",
           "the pre-baseline reading is not in force")
    check("build-and-gate: the committed baseline is read as pre-baseline",
          "pre-baseline" in proc.stdout, proc.stdout[:160])
    # The candidate's attestation is #1799/#1800's work - digests from the real
    # build and upstream signed provenance. The walk still exercises the
    # committed evidence aggregation so the phase is not described as something
    # nothing enforces, and names whose it becomes.
    evidence = write_evidence(w, w.candidate, w.candidate_version)
    attestation = w.dir / "attestation.json"
    proc = w.gates("promote", "--sha", w.candidate, "--version",
                   w.candidate_version, "--evidence", str(evidence),
                   *[f"--gate={spec}" for spec in reports],
                   "--output", str(attestation))
    expect(proc.returncode == 0, "build-and-gate",
           f"the evidence aggregation refused the candidate: {proc.stderr}")
    attested = json.loads(attestation.read_text(encoding="utf-8"))
    expect(attested["candidate"]["sha"] == w.candidate
           and attested["candidate"]["version"] == w.candidate_version,
           "build-and-gate",
           f"the attestation is not bound to the candidate: {attested['candidate']}")
    w.attestation = attestation
    w.reports = reports
    w.record("build-and-gate", "ok",
             f"attested {attested['candidate']['version']} at "
             f"{attested['candidate']['sha'][:12]} with "
             f"{len(attested['digests'])} image digest(s)",
             "scripts/release_gates.py promote",
             "the digest and provenance contract belongs to #1799/#1800")



def phase_promote(w, lifecycle):
    """The one protected dispatch: verify the reviewed merge, then rehearse."""
    env = lifecycle["phases"][PHASE_INDEX["promote"]].get("environment")
    w.merge_release_pr(w.candidate_version)
    check("promote: the walk merged the release PR as a person, and says so",
          w.remote_tree("refs/heads/master") == w.tree_of(w.candidate)
          and w.remote_ref("refs/heads/master") != w.candidate,
          "master does not carry the candidate's tree after the merge")
    w.record("promote", "ok",
             "the reviewed develop -> master PR merged (simulated merge, the "
             "constraint that reserves it to a person is asserted not exercised)",
             "git merge of develop into master")
    proc, verified = w.verify_step(w.candidate_version)
    expect(proc.returncode == 0, "promote",
           f"verify refused the reviewed merge: {proc.stdout}{proc.stderr}")
    expect(verified.get("merge_commit") == w.remote_ref("refs/heads/master")
           and verified.get("tag") == f"v{w.candidate_version}", "promote",
           f"verify did not report the reviewed merge: {verified}")
    w.verified = verified
    w.record("promote", "ok",
             "one dispatch verifies the merged release pull request: its merge "
             "commit is master's tip and carries the dispatched version",
             "the verify step of .github/workflows/release-promotion.yml",
             f"the job would run behind environment {env}")

    # The required documentation build of the run (#1609): the promotion calls the
    # committed gate workflow with the commit verify proved, and publish needs the
    # answer. Driven here through the gate's own shell, because the gate is that
    # shell plus the pinned strict Sphinx build.
    named, portal = w.docs_gate(verified["merge_commit"], verified["tag"],
                               verified["version"])
    check("promote: the documentation gate names the build for the release tag",
          named.get("tag") == verified["tag"]
          and portal.get("release") == verified["version"],
          f"{named} {portal}")
    w.record("promote", "ok",
             "the required documentation job builds the portal strictly from the "
             "verified merge commit and answers with its provenance",
             "the portal job of .github/workflows/docs-release-gate.yml, called by "
             "the docs job of .github/workflows/release-promotion.yml",
             "the strict Sphinx run itself belongs to the pinned docs toolchain")

    # Publication stays disabled until #1799/#1800 wire their gates: the
    # approved job rehearses and writes no ref, which is what lets the workflow
    # exist before the gates do.
    proc, _ = w.publish_step(verified, publish=False)
    expect(proc.returncode == 0 and w.remote_tags() == []
           and w.gh_state()["releases"] == [], "promote",
           f"the rehearsal wrote something: {w.remote_tags()} "
           f"{w.gh_state()['releases']} {proc.stdout} {proc.stderr}")
    check("promote: the rehearsal names what it withheld",
          "rehearsal" in proc.stdout and "nothing was written" in proc.stdout,
          stdout_head(proc.stdout))
    w.record("promote", "ok",
             "the approved job rehearses while publication is disabled: no tag, "
             "no release", "the publish step of .github/workflows/release-promotion.yml",
             "publish=false is the default until #1799/#1800")


def phase_verify_on_master(w, lifecycle):
    """Publish: the tag and the release stand on the verified merge commit."""
    proc, _ = w.publish_step(w.verified, publish=True)
    expect(proc.returncode == 0, "verify-on-master",
           f"publish refused a clean master: {proc.stdout} {proc.stderr}")
    tip = w.remote_ref("refs/heads/master")
    tag = w.remote_tag_commit("v0.2.0")
    expect(tag == tip, "verify-on-master",
           f"the tag points at {tag}, not at master's tip {tip}")
    expect(w.remote_ref("refs/tags/v0.2.0") != tip, "verify-on-master",
           "the tag is lightweight; an annotated tag is what carries a release")
    releases = [r["tagName"] for r in w.gh_state()["releases"]]
    expect(releases == ["v0.2.0"], "verify-on-master",
           f"the GitHub release is missing: {releases}")
    published = [c for c in w.journal_calls() if c[:2] == ["release", "create"]]
    expect(published and tip in published[0], "verify-on-master",
           f"the release does not stand on the verified commit: {published}")
    notes_path = published[0][published[0].index("--notes-file") + 1]
    notes = Path(notes_path).read_text(encoding="utf-8")
    expect(all(digest in notes for digest in (BACKEND_DIGEST, FRONTEND_DIGEST))
           and tip in notes and "a reviewed feature" in notes,
           "verify-on-master",
           f"the release body does not carry what an operator audits: {notes[:200]}")
    w.record("verify-on-master", "ok",
             "v0.2.0 tagged annotated at master's tip and its release published "
             "with the changelog section, both image digests and the commit",
             "the publish step of .github/workflows/release-promotion.yml")
    git("fetch", "-q", "origin", "master", cwd=w.repo)
    git("checkout", "-q", "-B", "master", "origin/master", cwd=w.repo)
    proc = w.gates("upgrade", "--base", "origin/develop")
    expect(proc.returncode == 0, "verify-on-master",
           f"the migrations do not hold on master: {proc.stderr}")
    w.record("verify-on-master", "ok",
             "the upgrade gate re-runs against master's migrations",
             "scripts/release_gates.py upgrade (HEAD on master)")
    git("checkout", "-q", "-B", "develop", "origin/develop", cwd=w.repo)
    proc, again = w.verify_step(w.candidate_version)
    expect(proc.returncode == 0 and "already stands on the verified commit"
           in proc.stdout, "verify-on-master",
           f"a complete release is not reported as already tagged: {proc.stdout}")
    w.record("verify-on-master", "ok",
             "re-dispatching after a complete release reports it published",
             "the verify step of .github/workflows/release-promotion.yml")


def phase_post_release(w, lifecycle):
    """The sync PR to develop; closing issues stays with a person."""
    # The sync back to develop is an ordinary reviewed pull request - the
    # mechanism is github-flow's, not the promotion's - and the tag the
    # promotion pushed is what the planner re-anchors on, so the walk checks
    # both instead of driving a sync command.
    sync = w.open_sync_pr()
    expect(sync is not None, "post-release",
           f"no master->develop sync PR: {w.gh_state()['prs']}")
    w.record("post-release", "ok",
             f"sync PR {sync['number']} opened to develop and left open for a "
             "person to merge", "gh pr create (the ordinary sync of github-flow)")
    expect(w.remote_tag_commit("v0.2.0") == w.remote_ref("refs/heads/master"),
           "post-release", "the planner's anchor is gone from master's tip")
    w.record("post-release", "ok",
             "the tag the promotion pushed is the anchor the planner re-anchors on",
             "docs/source/development/release-planning.rst")

# ------------------------------------------------------------- red scenarios

def scenario_no_release_changes(tmp):
    """Changes with no version class earn no release: the first acceptance line.

    The class of a range is decided by `release_gates.py version`, which reads
    the commit classes of a range: a range of `chore:` commits owes no bump and
    the gate is green with `required_bump: null`. The red half of the same rule
    is the range that earned more than its VERSION says: a merged `feat:` with
    the version unmoved is refused, because that is the one shape the gate can
    see. What nothing here refuses is the reverse -- an unearned bump upward is
    a `cut` decision, and it is listed as reserved, not as verified.
    """
    w = DryRun(tmp, "no-release")
    git("checkout", "-q", "-B", "develop", "origin/develop", cwd=w.repo)
    w.write({"app.txt": "a housekeeping change\n"})
    w.commit("chore: housekeeping only")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    sha = git("rev-parse", "HEAD", cwd=w.repo).stdout.strip()
    report = w.dir / "version-unearned.json"
    proc = w.gates("version", "--report", str(report))
    verdict = json.loads(report.read_text(encoding="utf-8"))
    check("class-less changes earn no version bump",
          proc.returncode == 0 and verdict["required_bump"] is None
          and verdict["candidate_version"] == BASE_VERSION,
          f"{proc.returncode} {verdict['problems']} {verdict['required_bump']}")
    proc, _ = w.verify_step(BASE_VERSION)
    check("and nothing can be published while develop owes no release",
          proc.returncode == 1
          and "no merged develop -> master release pull request" in proc.stdout,
          stdout_head(proc.stdout))
    # the red half of the same rule, and what actually guards it: the bump
    # question is only decidable against a RELEASED baseline (Q1 of #1578 names
    # v0.2.0 as the first one, and #1800 stands in front of it). While the
    # committed manifest says pre-baseline a missing minor bump is an advisory;
    # the refusal needs the reviewed manifest that names a version.
    w.write({"app.txt": "a reviewed feature\n"})
    w.commit("feat: something a deployment can ask for")
    proc = w.gates("version", "--report", str(w.dir / "version-advisory.json"))
    advisory = json.loads((w.dir / "version-advisory.json")
                          .read_text(encoding="utf-8"))
    check("while the baseline is pre-baseline a missing bump is an advisory",
          proc.returncode == 0 and advisory["required_bump"] == "minor"
          and advisory["problems"] == [] and advisory["advisories"],
          f"{proc.returncode} {advisory['problems']} {advisory['advisories']}")
    w.record("pre-release", "ok",
             "no bump owed by a class-less range; a feat's missing bump is an "
             "advisory while no tag is published (Q1 of #1578: v0.2.0 is the "
             "first one)",
             "scripts/release_gates.py version")
    manifest = json.loads((w.repo / "scripts/release_contract_baseline.json")
                          .read_text(encoding="utf-8"))
    manifest["mode"] = "released"
    manifest["version"] = BASE_VERSION
    manifest["source"] = "v" + BASE_VERSION
    w.write({"scripts/release_contract_baseline.json":
             json.dumps(manifest, indent=2) + "\n"})
    proc = w.gates("version")
    check("with a released baseline the same feat is refused",
          proc.returncode == 1 and "same precedence as the baseline" in
          proc.stderr, stderr_head(proc))
    w.git_restore()



def scenario_missing_changelog(tmp):
    """A VERSION move whose changelog section was never folded must not publish.

    The folded section is what the GitHub release body ships, so the promotion
    refuses the candidate before a tag or a release is written - while the
    version gate, which decides the bump from the commit classes of a range, has
    no reason to look at the fold and stays green. Recording both halves is what
    tells a reviewer which mechanism guards it.
    """
    w = DryRun(tmp, "no-changelog")
    w.advance()
    sha_before = w.candidate
    unfolded = (w.repo / "CHANGELOG.md").read_text(encoding="utf-8").replace(
        f"## [{CANDIDATE_VERSION}] - 2026-11-20", "## Unreleased", 1)
    w.write({"CHANGELOG.md": unfolded})
    w.commit("chore(release): the version moved but nothing was folded")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    w.merge_release_pr(w.candidate_version)
    proc, verified = w.verify_step(w.candidate_version)
    check("the fold-less candidate still is the reviewed merge",
          proc.returncode == 0, f"{proc.stdout} {proc.stderr}")
    proc, _ = w.publish_step(verified)
    check("the release body refuses a candidate whose section was never folded",
          proc.returncode == 1 and "carries no" in proc.stdout
          and w.remote_tags() == [] and w.gh_state()["releases"] == [],
          stdout_head(proc.stdout))
    check("and the refusal wrote nothing an operator could mistake for a release",
          w.remote_tags() == [] and w.gh_state()["releases"] == [],
          f"{w.remote_tags()} {w.gh_state()['releases']}")
    proc = w.gates("version", "--base", sha_before)
    check("the version gate is not what guards the fold",
          proc.returncode == 0, stderr_head(proc))


def scenario_evidence_red(tmp):
    """The evidence aggregation stops on an incomplete or foreign payload.

    The aggregation itself belongs to #1800; the walk keeps exercising the
    committed one so the lifecycle does not describe a phase nothing enforces,
    and the sha binding is the half that matters here: conclusions gathered for
    another build must not stand in for this candidate's.
    """
    w = DryRun(tmp, "evidence-red")
    w.advance()
    doc = w.dir / "candidate.openapi.json"
    doc.write_text(json.dumps(openapi_doc(CANDIDATE_VERSION)), encoding="utf-8")
    green = []
    for name in ("api", "version", "upgrade"):
        report = w.dir / f"gate-{name}.json"
        argv = [name, "--report", str(report)]
        if name == "api":
            argv += ["--candidate", str(doc)]
        expect(w.gates(*argv).returncode == 0, "red: evidence",
               f"the {name} gate refused the candidate")
        green.append(f"--gate={name}={report}")
    missing = [c for c in checks_payload() if c["name"] != "sonarcloud"]
    evidence = write_evidence(w, w.candidate, w.candidate_version, checks=missing)
    proc = w.gates("promote", "--sha", w.candidate, "--version",
                   CANDIDATE_VERSION, "--evidence", str(evidence), *green)
    check("missing evidence class stops the attestation",
          proc.returncode == 1 and "sonar" in proc.stderr, proc.stderr[:200])
    foreign = write_evidence(w, w.baseline_commit, w.candidate_version)
    proc = w.gates("promote", "--sha", w.candidate, "--version",
                   CANDIDATE_VERSION, "--evidence", str(foreign))
    check("the aggregation refuses evidence of a foreign sha",
          proc.returncode == 1 and "gathered for sha" in proc.stderr,
          proc.stderr[:200])


def scenario_docs_gate_red(tmp):
    """A portal that is not the candidate's stops the release (#1609).

    `needs` proves the documentation job was green; only the answer it hands
    `publish` proves it was green for the commit being tagged. Both halves of
    that are driven here: the gate refusing a call that cannot name its
    revision, and the promotion refusing a portal of another tree - each read
    before a ref was written.
    """
    w = DryRun(tmp, "docs-gate-red")
    w.advance()
    w.merge_release_pr(w.candidate_version)
    proc, verified = w.verify_step(w.candidate_version)
    expect(proc.returncode == 0, "red: docs gate",
           f"verify refused the reviewed merge: {proc.stdout} {proc.stderr}")

    base = {"MRMAP_DOCS_PYTHON": sys.executable,
            "GITHUB_EVENT_NAME": "workflow_call", "INPUT_TAG": verified["tag"]}
    proc, _ = w.gate_step(GATE_REVISION_STEP, dict(base, REVISION=""))
    check("the gate refuses a call that cannot name the revision to document",
          proc.returncode == 1 and "cannot name" in proc.stdout + proc.stderr,
          stdout_head(proc.stdout))
    proc, _ = w.gate_step(GATE_REVISION_STEP, dict(base, REVISION="a" * 39))
    check("and a revision that is not a full sha",
          proc.returncode == 1, stdout_head(proc.stdout))

    # The gate built, but built something else: the strict run is the pinned
    # toolchain's, so the artifact is handed over in the shape the project's own
    # Sphinx extension writes it, with another revision recorded in it.
    w.write_portal("f" * 40, w.candidate_version)
    proc, _ = w.gate_step(GATE_PROVENANCE_STEP,
                          dict(base, REVISION=verified["merge_commit"]))
    check("the gate refuses a portal of another tree, naming both revisions",
          proc.returncode == 1 and "not the reviewed" in proc.stdout + proc.stderr
          and "f" * 12 in proc.stdout + proc.stderr,
          stdout_head(proc.stdout))
    (w.repo / "docs" / "build" / "html" / "provenance.json").unlink()
    proc, _ = w.gate_step(GATE_PROVENANCE_STEP,
                          dict(base, REVISION=verified["merge_commit"]))
    check("and a build that cannot say what it documented",
          proc.returncode == 1 and "cannot say what it built"
          in proc.stdout + proc.stderr, stdout_head(proc.stdout))

    # The promotion's own half: an answer of the wrong shape or of the wrong
    # tree is refused before a tag or a release exists.
    for label, kwargs, needle in (
            ("no answer", {"docs_commit": ""}, "no 40-hex documented_commit"),
            ("another commit's answer", {"docs_commit": "e" * 40},
             "not of the reviewed"),
            ("another version's answer", {"docs_release": "9.9.9"},
             "disagree about the version")):
        proc, _ = w.publish_step(verified, **kwargs)
        check(f"publish refuses the documentation gate's {label}",
              proc.returncode == 1 and needle in proc.stdout + proc.stderr,
              stdout_head(proc.stdout))
        check(f"and wrote nothing for {label}",
              w.remote_tags() == [] and w.gh_state()["releases"] == [],
              f"{w.remote_tags()} {w.gh_state()['releases']}")

    # The green path of the same world, so the refusals above are read as the
    # difference rather than as a broken step.
    named, portal = w.docs_gate(verified["merge_commit"], verified["tag"],
                                verified["version"])
    proc, _ = w.publish_step(verified, publish=False)
    check("with the portal of the candidate the rehearsal is green again",
          proc.returncode == 0 and named.get("tag") == verified["tag"]
          and portal.get("documented_commit") == verified["merge_commit"]
          and w.remote_tags() == [],
          f"{proc.stdout[-160:]} {named} {portal}")


def scenario_publish_red(tmp):
    """publish refuses a moved master, a malformed digest and a foreign tag."""
    w = DryRun(tmp, "publish-red")
    w.advance()
    w.merge_release_pr(w.candidate_version, diverge=True)
    proc, _ = w.verify_step(w.candidate_version)
    check("verify refuses a master that moved after the reviewed merge",
          proc.returncode == 1 and "is not the merge commit" in proc.stdout,
          stdout_head(proc.stdout))
    check("a refused promotion published nothing",
          w.remote_tags() == [] and w.gh_state()["releases"] == [],
          f"{w.remote_tags()} {w.gh_state()['releases']}")

    # The release body quotes image digests, and an operator audits them against
    # the registry: a malformed digest is a broken audit trail, so it stops the
    # release rather than reaching the page.
    w2 = DryRun(tmp, "publish-red-digest")
    w2.advance()
    w2.merge_release_pr(w2.candidate_version)
    proc, verified = w2.verify_step(w2.candidate_version)
    expect(proc.returncode == 0, "red: malformed digest",
           f"verify refused the reviewed merge: {proc.stdout} {proc.stderr}")
    check("publish refuses a master that moved without a reviewed merge",
          proc.returncode == 0, "")
    proc, _ = w2.publish_step(verified, artifacts="mrmap-backend=sha256:deadbeef")
    check("a digest that is not a digest stops the release",
          proc.returncode == 1
          and "has no sha256:<64 hex> digest" in proc.stdout
          and w2.remote_tags() == [] and w2.gh_state()["releases"] == [],
          stdout_head(proc.stdout))

def scenario_missing_migration_notes(tmp):
    """The release files are complete except the notes: the gate stops the walk.

    The migration of a release is written together with its VERSION, so the
    scenario moves both on the baseline: measured from the commit before them,
    the range contains the migration and owes its note. Cutting the base to the
    candidate would measure an empty range and prove nothing.
    """
    w = DryRun(tmp, "no-notes")
    git("checkout", "-q", "-B", "develop", "origin/develop", cwd=w.repo)
    base = git("rev-parse", "HEAD", cwd=w.repo).stdout.strip()
    w.write(planned_release_files(CANDIDATE_VERSION, notes=False))
    w.commit("chore(release): 0.2.0 whose migration was never explained")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    report = w.dir / "version.json"
    proc = w.gates("version", "--base", base, "--report", str(report))
    check("a migration in the range without its notes fails the version gate",
          proc.returncode == 1 and "Migration notes" in proc.stderr,
          stderr_head(proc))
    text = report.read_text(encoding="utf-8")
    check("the red report names the migration it missed",
          json.loads(text)["ok"] is False and "notify.0007_a_new_column" in text,
          stdout_head(text))
    # the other two gates and the evidence are green: the refusal below is
    # owed to the version report alone.
    api = w.dir / "api.json"
    doc = w.dir / "candidate.openapi.json"
    doc.write_text(json.dumps(openapi_doc(CANDIDATE_VERSION)), encoding="utf-8")
    expect(w.gates("api", "--candidate", str(doc), "--report", str(api))
           .returncode == 0, "red: missing migration notes",
           "the api gate refused the candidate")
    upgrade = w.dir / "upgrade.json"
    expect(w.gates("upgrade", "--report", str(upgrade)).returncode == 0,
           "red: missing migration notes",
           "the upgrade gate refused the candidate")
    sha = git("rev-parse", "HEAD", cwd=w.repo).stdout.strip()
    evidence = write_evidence(w, sha, CANDIDATE_VERSION)
    proc = w.gates("promote", "--sha", sha, "--expect-version", CANDIDATE_VERSION,
                   "--evidence", str(evidence),
                   f"--gate=version={report}", f"--gate=api={api}",
                   f"--gate=upgrade={upgrade}")
    check("and the promotion refuses a candidate whose version gate is red",
          proc.returncode == 1 and "gate version is red" in proc.stderr,
          stderr_head(proc))
    # the green half: the same range with the same migration is accepted once
    # the notes name it, which is what makes the refusal above about the notes.
    w.write(planned_release_files(CANDIDATE_VERSION))
    w.commit("docs: the note the range owed")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    green = w.dir / "version-green.json"
    proc = w.gates("version", "--base", base, "--report", str(green))
    check("naming the migration in the notes makes the same range green",
          proc.returncode == 0
          and json.loads(green.read_text(encoding="utf-8"))["ok"] is True,
          stderr_head(proc))


def scenario_prerelease(tmp):
    """The lifecycle says prereleases carry no stable publication."""
    w = DryRun(tmp, "prerelease")
    lifecycle = read_lifecycle()
    pattern = lifecycle["tag_pattern"]
    check("the stable tag grammar excludes a prerelease",
          re.match(pattern, "v0.2.0-rc.1") is None
          and re.match(pattern, "v0.2.0") is not None, pattern)
    git("checkout", "-q", "-B", "develop", "origin/develop", cwd=w.repo)
    w.write(planned_release_files(PRERELEASE_VERSION))
    w.commit("chore(release): an rc on develop")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    w.merge_release_pr(PRERELEASE_VERSION)
    proc, _ = w.verify_step(PRERELEASE_VERSION)
    check("a prerelease is never a promotion candidate",
          proc.returncode == 1
          and "is not a reviewed MAJOR.MINOR.PATCH version" in proc.stdout,
          stdout_head(proc.stdout))
    check("a prerelease never cuts the stable tag of its line",
          w.remote_tags() == [] and w.gh_state()["releases"] == [],
          f"{w.remote_tags()} {w.gh_state()['releases']}")


def bump_walk(tmp, name, message, version, *, notes=None, policy=None):
    """One commit class, planned onto a released baseline; returns its report.

    Each class gets its own walk on purpose: the version gate reads the RANGE
    from the base to HEAD, so several classes measured from one shared base
    would each be judged by every earlier class too, and a patch bump would read
    as a feature. One walk per class keeps the answer about one commit.
    `policy` overrides the 0.x knob, which is how the manifest's own reading is
    exercised without editing the reviewed file of this checkout.
    """
    committed = json.loads(
        (REPO / "scripts" / "release_contract_baseline.json").read_text(
            encoding="utf-8"))
    manifest = dict(committed, mode="released", version=BASE_VERSION,
                    source="v" + BASE_VERSION, document=None)
    if policy:
        manifest["policy"] = dict(committed["policy"], **policy)
    w = DryRun(tmp, name)
    w.write({"scripts/release_contract_baseline.json":
             json.dumps(manifest, indent=2) + "\n"})
    w.commit("chore: the reviewed PR that flips the baseline to released")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    base = git("rev-parse", "HEAD", cwd=w.repo).stdout.strip()
    w.write({"VERSION": version + "\n",
             "backend/MrMap/version.py": CANON.render_projection(version),
             ".release-please-manifest.json":
                 json.dumps({".": version}) + "\n",
             "app.txt": f"state at {version}\n"})
    if notes is not None:
        w.write({"CHANGELOG.md": notes})
    w.commit(message)
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    path = w.dir / "report.json"
    proc = w.gates("version", "--base", base, "--report", str(path))
    return proc, json.loads(path.read_text(encoding="utf-8"))


BREAKING_NOTES = (
    "# Changelog\n\n## Unreleased\n\n**Breaking:** the public surface moved "
    "(#1586)\n\n## [0.1.0] - 2023-03-23\n\n- the first shape of it all\n")
SILENT_NOTES = ("# Changelog\n\n## Unreleased\n\n"
                "## [0.1.0] - 2023-03-23\n\n- the first shape of it all\n")


def scenario_bump_policy(tmp):
    """What each commit class demands of a version, against a released baseline.

    The bump question of the version gate is decidable only from a released
    baseline, and this checkout has none (Q1 of #1578 fixed v0.2.0 as the first
    published tag and #1800 verifies the oldest baseline before it), so the green
    walk alone cannot show the class rules of the issue: patch, minor, major and
    the reviewed 0.x reading. The scenario therefore runs the tools against a
    copy of the manifest in `released` mode at 0.1.0 - the content the first
    published release will commit - and asserts the committed pre-baseline
    reading first, which is what stands in today.
    """
    committed = json.loads(
        (REPO / "scripts" / "release_contract_baseline.json").read_text(
            encoding="utf-8"))
    w = DryRun(tmp, "bump-pre-baseline")
    report = w.dir / "pre.json"
    w.write(planned_release_files(CANDIDATE_VERSION))
    w.commit("feat: a feature on a pre-baseline develop")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    proc = w.gates("version", "--base", w.baseline_commit, "--report", str(report))
    pre = json.loads(report.read_text(encoding="utf-8"))
    check("the committed pre-baseline manifest still reports the required class",
          proc.returncode == 0 and pre["mode"] == "pre-baseline"
          and committed["mode"] == "pre-baseline"
          and pre["baseline_version"] is None and pre["required_bump"] == "minor"
          and any("no released baseline" in note for note in pre["advisories"]),
          f"{pre['mode']} {pre['required_bump']} {pre['advisories']}")

    proc, minor = bump_walk(tmp, "bump-minor",
                            "feat: a feature worthy of a minor bump", "0.2.0")
    check("a feature demands a minor bump, and 0.1.0 -> 0.2.0 is one",
          proc.returncode == 0 and minor["required_bump"] == "minor"
          and minor["breaking"] == 0, stderr_head(proc))

    proc, patch = bump_walk(tmp, "bump-patch",
                            "fix: a fix worthy of a patch bump", "0.1.1")
    check("a fix demands a patch bump, and 0.1.0 -> 0.1.1 is one",
          proc.returncode == 0 and patch["required_bump"] == "patch",
          stderr_head(proc))

    proc, none = bump_walk(tmp, "bump-none",
                           "docs: a change of no release class", "0.1.0")
    check("a class-less range demands no bump and may keep the baseline version",
          proc.returncode == 0 and none["required_bump"] is None,
          stderr_head(proc))

    proc, stalled = bump_walk(tmp, "bump-stalled",
                              "fix: a fix that forgot to move the version",
                              "0.1.0")
    check("a patch-worthy range that keeps the baseline version is refused",
          proc.returncode == 1
          and "same precedence as the baseline"
          in " ".join(stalled["problems"]), stderr_head(proc))

    proc, back = bump_walk(tmp, "bump-backwards",
                           "fix: a fix that moved the version the wrong way",
                           "0.0.9")
    check("a candidate behind the baseline is refused, not floored to it",
          proc.returncode == 1
          and "BEHIND the baseline" in " ".join(back["problems"]),
          stderr_head(proc))

    proc, zero_x = bump_walk(tmp, "bump-0x", "feat!: a breaking change below 1.0",
                             "0.2.0", notes=BREAKING_NOTES)
    check("a breaking change below 1.0 passes as the reviewed 0.x minor",
          proc.returncode == 0 and zero_x["required_bump"] == "major"
          and zero_x["breaking"] == 1, stderr_head(proc))

    proc, silent = bump_walk(tmp, "bump-silent",
                             "feat!: a breaking change whose notes stay silent",
                             "0.2.0", notes=SILENT_NOTES)
    check("the 0.x reading still refuses a breaking change with no Breaking line",
          proc.returncode == 1 and "Breaking:" in " ".join(silent["problems"]),
          stderr_head(proc))

    proc, major = bump_walk(tmp, "bump-major",
                            "feat!: the breaking change that becomes 1.0.0",
                            "1.0.0", notes=BREAKING_NOTES)
    check("the major path stays open for a breaking change under that reading",
          proc.returncode == 0 and major["required_bump"] == "major"
          and major["candidate_version"] == "1.0.0", stderr_head(proc))

    proc, strict = bump_walk(tmp, "bump-strict",
                             "feat!: a breaking change below 1.0", "0.2.0",
                             notes=BREAKING_NOTES,
                             policy={"breaking_below_1_0": "major"})
    check("without the reviewed 0.x knob the same minor move is refused",
          proc.returncode == 1
          and "requires a major bump" in " ".join(strict["problems"]),
          stderr_head(proc))
    check("the class rules ran on a copy: this checkout's manifest is untouched",
          json.loads((REPO / "scripts" / "release_contract_baseline.json")
                     .read_text(encoding="utf-8"))["mode"] == "pre-baseline",
          "the scenario edited reviewed content")


def scenario_stale_candidate_document(tmp):
    """A candidate document that is not the candidate's is refused, not diffed.

    The mock documentation gate of #1584 has exactly this job: `info.version` of
    the document must be the checkout's VERSION, so a file saved from an older
    build cannot become the contract comparison of a new candidate. The refusal
    happens before the report is written, so a red gate cannot leave a file the
    promotion would consume.
    """
    w = DryRun(tmp, "stale-document")
    w.advance()
    stale = w.dir / "stale.openapi.json"
    stale.write_text(json.dumps(openapi_doc(BASE_VERSION)), encoding="utf-8")
    report = w.dir / "api-stale.json"
    proc = w.gates("api", "--candidate", str(stale), "--report", str(report))
    check("a document of another version is refused, not diffed",
          proc.returncode == 1 and "info.version" in proc.stderr,
          stderr_head(proc))
    check("the refused gate leaves no report for the promotion to consume",
          not report.exists(), report.read_text(encoding="utf-8")[:120]
          if report.exists() else "no file")
    # the seam is deliberate: --skip-version-check is a reviewer's inspection
    # switch, so the promotion must not use it - and preflight does not.
    skipped = w.dir / "api-skipped.json"
    proc = w.gates("api", "--candidate", str(stale), "--skip-version-check",
                   "--report", str(skipped))
    read = json.loads(skipped.read_text(encoding="utf-8"))
    check("--skip-version-check is the only way a stale file gets through",
          proc.returncode == 0 and read["info_version"] == BASE_VERSION,
          stderr_head(proc))
    check("no promotion step passes that switch",
          "--skip-version-check" not in PROMOTION_WORKFLOW.read_text(encoding="utf-8"),
          "the promotion workflow drives the api gate with the switch on")
    fresh = w.dir / "fresh.openapi.json"
    fresh.write_text(json.dumps(openapi_doc(CANDIDATE_VERSION)), encoding="utf-8")
    proc = w.gates("api", "--candidate", str(fresh),
                   "--report", str(w.dir / "api-fresh.json"))
    check("the candidate's own document is accepted",
          proc.returncode == 0, stderr_head(proc))



def scenario_immutable_tag(tmp):
    """Two promotions of one version: the second conflicts, and nothing moves.

    The native mechanism owns no branch and no journal, so the race that used to
    be a frozen branch is now the tag: whoever writes the name first owns it, and
    the second run refuses instead of moving it. The journal is the proof that
    the refused run cost no tag and no release.
    """
    w = DryRun(tmp, "immutable-tag")
    w.advance()
    w.merge_release_pr(w.candidate_version)
    proc, verified = w.verify_step(w.candidate_version)
    expect(proc.returncode == 0, "red: immutable tag",
           f"verify refused the first promotion: {proc.stdout} {proc.stderr}")
    proc, _ = w.publish_step(verified)
    expect(proc.returncode == 0, "red: immutable tag",
           f"the first promotion failed: {proc.stdout} {proc.stderr}")
    standing = w.remote_tag_commit("v0.2.0")

    # A rival run that wants the same name for a different commit: develop moved
    # and was merged again, which is the shape of a re-cut release.
    git("checkout", "-q", "-B", "develop", "origin/develop", cwd=w.repo)
    w.write({"app.txt": "a later commit that did not move the version\n"})
    w.commit("chore: a second promotion attempt of the same version")
    git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=w.repo)
    w.merge_release_pr(w.candidate_version)
    expect(w.remote_ref("refs/heads/master") != standing, "red: immutable tag",
           "the rival merge did not move master, so the scenario proves nothing")
    proc, _ = w.verify_step(w.candidate_version)
    check("the second promotion of one version is refused as a tag conflict",
          proc.returncode == 1 and "already stands on" in proc.stdout,
          stdout_head(proc.stdout))
    check("the refusal moved nothing: the tag and the release stand as published",
          w.remote_tag_commit("v0.2.0") == standing
          and [r["tagName"] for r in w.gh_state()["releases"]] == ["v0.2.0"],
          str(w.remote_tag_commit("v0.2.0")))
    proc, _ = w.verify_step(w.candidate_version)
    check("a re-run refuses too, so retrying cannot smuggle the move through",
          proc.returncode == 1, stdout_head(proc.stdout))

# ------------------------------------------------------------------- the run

WALK = [("pre-release", phase_pre_release),
        ("cut", phase_cut),
        ("build-and-gate", phase_build_and_gate),
        ("promote", phase_promote),
        ("verify-on-master", phase_verify_on_master),
        ("post-release", phase_post_release)]

SCENARIOS = [("no release from class-less changes", scenario_no_release_changes),
             ("VERSION move without its fold", scenario_missing_changelog),
             ("incomplete or foreign evidence", scenario_evidence_red),
             ("publish's refusals", scenario_publish_red),
             ("a portal that is not the candidate's", scenario_docs_gate_red),
             ("a range that owes its migration notes",
              scenario_missing_migration_notes),
             ("prerelease carries no stable publication", scenario_prerelease),
             ("what each commit class demands of a version",
              scenario_bump_policy),
             ("a stale candidate document", scenario_stale_candidate_document),
             ("two promotions of one version", scenario_immutable_tag)]

PER_PHASE_S = float(os.environ.get("RELEASE_DRY_RUN_PHASE_TIMEOUT_S", "150"))


def call_with_timeout(fn, argv, limit, what):
    """Run one step under a wall-clock limit, so a wedged git or python
    subprocess is a named timeout finding and never a suite that stops answering
    the CI runner. A thread cannot be killed, so the executor is shut down with
    `wait=False` afterwards: a wedged child is reported and abandoned rather
    than hanging the report with it."""
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fn, *argv)
        try:
            return future.result(timeout=limit), None
        except concurrent.futures.TimeoutError:
            future.cancel()
            return None, f"{what}: timed out after {limit:.0f} s"
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def run_green_walk(tmp, lifecycle):
    """Walk the lifecycle end to end; return (steps, unfinished-reason)."""
    w = DryRun(tmp, "full-release")
    steps_before = 0
    for phase_id, fn in WALK:
        limit = min(PER_PHASE_S, max(30.0, TIME_BUDGET_S - elapsed()))
        try:
            _, timeout = call_with_timeout(fn, (w, lifecycle), limit, phase_id)
        except PhaseFailed as failure:
            check(f"phase {phase_id} walks as described", False, str(failure))
            return w.steps, f"{phase_id} failed: {failure}"
        except HarnessCannotRun:
            raise
        except Exception as failure:  # a tool crash is a finding, not a pass
            check(f"phase {phase_id} walks as described", False,
                  f"{type(failure).__name__}: {failure}")
            return w.steps, f"{phase_id} crashed: {failure}"
        if timeout:
            check(f"phase {phase_id} walks as described", False, timeout)
            return w.steps, timeout
        if len(w.steps) == steps_before:
            check(f"phase {phase_id} records what it exercised", False,
                  "the phase ran but recorded nothing")
            return w.steps, f"{phase_id} recorded nothing"
        steps_before = len(w.steps)
        check(f"phase {phase_id} walks as described", True,
              "; ".join(step["means"] for step in w.steps[steps_before:]))
    return w.steps, None


def interface_checks(lifecycle, steps):
    """The #1586 interface half: the description of #1585 against a walk."""
    described = [phase["id"] for phase in lifecycle["phases"]]
    check("every described phase is walked",
          described == [phase for phase, _ in WALK],
          f"described {described} walked {[p for p, _ in WALK]}")
    walked = {step["phase"] for step in steps}
    check("the walk covered every phase of the lifecycle",
          walked == set(described), f"walked {sorted(walked)}")
    actors = {phase["id"]: phase["actor"] for phase in lifecycle["phases"]}
    check("the walk assigns every phase the actor the lifecycle names",
          all(actors[phase] in ("human", "ci", "contributor")
              for phase in described),
          json.dumps(actors))
    check("the lifecycle's own actor rule is the one enforced here",
          actors["cut"] == "human" and actors["promote"] == "human"
          and actors["verify-on-master"] == "ci",
          json.dumps(actors))
    for phase in lifecycle["phases"]:
        evidence = phase["evidence"]
        named = any(token in step["means"] for step in steps
                    for token in evidence.split() if token.endswith(".yml")
                    or token.startswith("scripts/"))
        check(f"phase {phase['id']} names a mechanism the walk can drive",
              "scripts/" in evidence or ".github/" in evidence or named,
              evidence)
    grammar = lifecycle["tag_pattern"]
    check("the described tag grammar is the one the tool writes",
          re.match(grammar, "v0.2.0") is not None, grammar)
    version_grammar = lifecycle["version_pattern"]
    check("the described version grammar is strict SemVer, not a loose one",
          re.match(version_grammar, "0.2.0") is not None
          and re.match(version_grammar, "0.2.0-rc.1") is None, version_grammar)


def print_report(report):
    print("=" * 78)
    print("release lifecycle dry run - what the walk exercised")
    print("=" * 78)
    for step in report["exercised"]:
        print(f"  [{step['phase']:<17}] {step['verdict']:<8} {step['what']}")
        print(f"  {'':<17} {'':<8} via: {step['means']}"
              + (f" ({step['note']})" if step["note"] else ""))
    print()
    print("=" * 78)
    print("release lifecycle dry run - what still needs a real stack or a person")
    print("=" * 78)
    for item in report["blocked"]:
        print(f"  - {item['item']}")
        print(f"      why:     {item['why']}")
        print(f"      owner:   {item['owner']}")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="test_release_lifecycle_dry_run")
    parser.add_argument("--report", default=None,
                        help="also write the machine-readable report here")
    args = parser.parse_args(argv)

    try:
        lifecycle = read_lifecycle()
        for index, phase in enumerate(lifecycle["phases"]):
            PHASE_INDEX[phase["id"]] = index
    except HarnessCannotRun as failure:
        print(f"harness cannot run: {failure}", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="mrmap-lifecycle-dry-run-"))
    try:
        try:
            steps, incomplete = run_green_walk(tmp, lifecycle)
        except HarnessCannotRun as failure:
            print(f"harness cannot run: {failure}", file=sys.stderr)
            return 2
        if incomplete:
            check("the walk reached every phase", False, incomplete)
        for name, scenario in SCENARIOS:
            limit = max(30.0, TIME_BUDGET_S - elapsed())
            try:
                _, timeout = call_with_timeout(scenario, (tmp,), limit, name)
            except PhaseFailed as failure:
                check(f"scenario {name}", False, str(failure))
                continue
            except HarnessCannotRun as failure:
                print(f"harness cannot run: {failure}", file=sys.stderr)
                return 2
            except Exception as failure:
                check(f"scenario {name}", False,
                      f"{type(failure).__name__}: {failure}")
                continue
            if timeout:
                check(f"scenario {name}", False, timeout)
        blocked = blocked_items(lifecycle)
        interface_checks(lifecycle, steps)
        report = {
            "generated": now(),
            "lifecycle": str(LIFECYCLE.relative_to(REPO)),
            "phases": [phase["id"] for phase in lifecycle["phases"]],
            "exercised": steps,
            "blocked": blocked,
            "incomplete_walk": incomplete,
            "isolation": {"network": "none - gh is a journaling shim, git "
                                     "remotes are local bare repositories",
                          "published": "nothing: no tag, release, image or "
                                       "issue touched outside a temp dir",
                          "identity": "git runs with GIT_CONFIG_GLOBAL and "
                                      "GIT_CONFIG_SYSTEM set to /dev/null"},
        }
        print_report(report)
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [name for name, ok, _ in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL {name}: {detail}", file=sys.stderr)
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed "
          f"in {elapsed():.1f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
