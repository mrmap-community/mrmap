#!/usr/bin/env python3
"""test_release_promotion: the native promotion workflow does what it claims.

Issue #1798 (epic #1577). The custom promotion orchestrator of #1584 is gone;
.github/workflows/release-promotion.yml is now two jobs of shell - `verify`
proves one commit is the reviewed release, `publish` tags it and creates its
release behind the protected `release-stable` environment. The workflow IS the
implementation, so the checks below run the workflow's own step scripts. They
are read out of the YAML rather than copied: a suite holding its own copy of a
step proves nothing about the file CI runs.

What is exercised, and how far it goes
--------------------------------------
The steps are driven with bash against a throw-away repository whose "origin"
is a local bare repo, with the journaling `gh` shim the lifecycle dry run uses
for the same reason: no network, no credential, and every GitHub answer a step
needs comes from a table this file controls. Each refusal the criteria name is
seen BEFORE a ref was written:

  no merged release PR                    verify refuses, publish publishes nothing
  master's tip is not the merge commit    verify refuses (master moved on its own)
  VERSION there is another version        verify refuses (not the prepared version)
  gh answers no merge commit              verify refuses rather than guessing
  the tag already stands elsewhere        verify refuses (a published tag never moves)

and then the same world publishes: annotated tag on master's tip, one GitHub
release standing on that commit, whose body carries the version, the changelog
section of that commit, both image digests and the verified sha. Publication is
still disabled upstream, so the rehearsal is pinned separately: `publish=false`
writes no tag and no release yet prints both, which is what lets this workflow
land while #1799 and #1800 wire their gates. A run whose approval queued behind
something that moved master is checked as a refusal too, because the environment
approval is granted before the write, not at it.

Shape checks come last and are cheap: the triggers people and #1609/#1800 need,
the single `needs` edge, the protected environment on the writing job and not on
the reading one, the permissions each job actually uses, and the two upstream
facts that make release-please's own `github-release` unusable here - measured
in docs/source/development/release-promotion.rst, pinned so that swapping those
commands back in without re-measuring goes red.

Run from the repository root:  python3 scripts/test_release_promotion.py
(also run by scripts/check_repo_tooling.sh). Standard library only: the steps
come from scripts/workflow_steps.py, because PyYAML is no stdlib dependency and
a runner without it must not be able to report this suite green without having
run it. git and bash are required; docker, node and the network are not.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
import workflow_steps
WORKFLOW = REPO / ".github" / "workflows" / "release-promotion.yml"
DOCS_GATE = REPO / ".github" / "workflows" / "docs-release-gate.yml"
RUNBOOK = REPO / "docs" / "source" / "administration" / "release-operator-runbook.rst"
DESIGN = REPO / "docs" / "source" / "development" / "release-promotion.rst"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    return bool(ok)


GIT_ENV = dict(os.environ,
               GIT_AUTHOR_NAME="release test", GIT_AUTHOR_EMAIL="ci@example.invalid",
               GIT_COMMITTER_NAME="release test", GIT_COMMITTER_EMAIL="ci@example.invalid",
               GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null",
               GIT_TERMINAL_PROMPT="0")


def git(*argv, cwd):
    return subprocess.run(["git", *argv], cwd=str(cwd), env=GIT_ENV,
                          capture_output=True, text=True)


def git_ok(*argv, cwd):
    proc = git(*argv, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


# ------------------------------------------------------------------ gh shim
#
# The contract test_release_lifecycle_dry_run.py uses for the same reason: state
# in a JSON file, every call appended to a journal, and an unhandled call is an
# error rather than a silent success. `pr list` answers only the query the
# workflow actually makes, so a step that asked GitHub something else gets an
# empty answer and refuses - the honest direction for a promotion tool to fail.
GH_SHIM = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["GH_JOURNAL"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")
state = json.load(open(os.environ["GH_STATE"], encoding="utf-8"))


def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None


if argv[:2] == ["pr", "list"]:
    want = (flag("--base"), flag("--head"), flag("--state"))
    if want != ("master", "develop", "merged"):
        sys.stderr.write("gh shim: unexpected pr list query %r\\n" % (want,))
        sys.exit(1)
    rows = state["merged_release_prs"]
    if flag("--jq") is not None:
        # answers the workflow's own jq program by reading the table rather than
        # by reimplementing jq: a null mergeCommit is dropped, the newest
        # mergedAt wins.
        rows = [r for r in rows if (r.get("mergeCommit") or {}).get("oid")]
        if not rows:
            print("")
        else:
            latest = sorted(rows, key=lambda r: r["mergedAt"])[-1]
            print("%d %s" % (latest["number"], latest["mergeCommit"]["oid"]))
    else:
        print(json.dumps(rows))
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
    if any(r["tagName"] == tag for r in state["releases"]):
        sys.stderr.write("gh shim: release %s already exists\\n" % tag)
        sys.exit(1)
    state["releases"].append({"tagName": tag, "target": flag("--target"),
                              "title": flag("--title"),
                              "notes_file": flag("--notes-file")})
    json.dump(state, open(os.environ["GH_STATE"], "w", encoding="utf-8"))
    print("https://github.example.test/releases/" + tag)
else:
    sys.stderr.write("gh shim: unhandled call: " + " ".join(argv) + "\\n")
    sys.exit(1)
"""

VERSION = "0.2.0"
BACKEND_DIGEST = "sha256:" + "a" * 64
FRONTEND_DIGEST = "sha256:" + "b" * 64
ARTIFACTS = f"mrmap-backend={BACKEND_DIGEST}\nmrmap-frontend={FRONTEND_DIGEST}"

CHANGELOG = """# Changelog

## Unreleased

### Added
- Curated entry written by a human.

## [0.2.0](https://github.example.test/compare/v0.1.0...v0.2.0) (2026-11-26)

### Added

* the first planned feature

### Fixed

* a repair worth a note

## [0.1.0] - 2023-03-23

### Added
- The old released baseline.
"""


# ---------------------------------------------------------------- test world
class World:
    """One throw-away repository plus the GitHub answers the workflow reads.

    `origin` is a local bare repo, so no ref a run writes ever leaves the
    temporary directory. `merged_release_prs` is what `gh pr list` answers, so
    the state under test is exactly the state the step is being asked about.
    """

    def __init__(self, tmp):
        self.dir = Path(tmp)
        origin = self.dir / "origin.git"
        self.repo = self.dir / "clone"
        self.gh = self.dir / "gh"
        self.state_path = self.dir / "gh-state.json"
        self.journal_path = self.dir / "gh-journal.jsonl"
        self.gh.write_text(GH_SHIM, encoding="utf-8")
        self.gh.chmod(0o755)
        self.state = {"merged_release_prs": [], "releases": []}
        self.save()
        self.journal_path.write_text("", encoding="utf-8")
        git_ok("init", "--bare", "--initial-branch=develop", str(origin), cwd=self.dir)
        git_ok("clone", "-q", str(origin), str(self.repo), cwd=self.dir)
        for key, value in (("user.email", "ci@example.invalid"),
                           ("user.name", "release test"),
                           ("commit.gpgsign", "false")):
            git_ok("config", key, value, cwd=self.repo)
        (self.repo / "VERSION").write_text("0.1.0\n", encoding="utf-8")
        (self.repo / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
        (self.repo / "app.txt").write_text("baseline\n", encoding="utf-8")
        git_ok("add", "-A", cwd=self.repo)
        git_ok("commit", "-q", "-m", "chore: the shape of a deployment", cwd=self.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.repo)
        self.release_pr_number = 1700
        self.merge_commit = None

    def save(self):
        self.state_path.write_text(json.dumps(self.state), encoding="utf-8")

    def gh_state(self):
        """Always re-read the file: the shim writes there, so the in-memory
        dict is only what this world asked GitHub, never what it answered."""
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    # -- the history the planner and the reviewed merge would have produced --
    def prepare_release_pr(self, version=VERSION):
        git_ok("checkout", "-q", "-B", "develop", "origin/develop", cwd=self.repo)
        (self.repo / "VERSION").write_text(version + "\n", encoding="utf-8")
        git_ok("add", "-A", cwd=self.repo)
        git_ok("commit", "-q", "-m", f"chore: release {version}", cwd=self.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.repo)
        return git_ok("rev-parse", "HEAD", cwd=self.repo)

    def merge_to_master(self):
        """The reviewed develop -> master merge, landed the way GitHub lands it:
        a merge commit whose parents are master's tip and develop's tip, so
        master carries the candidate's tree without being the candidate."""
        git_ok("fetch", "-q", "origin", cwd=self.repo)
        git_ok("checkout", "-q", "-B", "master", "origin/master", cwd=self.repo)
        git_ok("merge", "--no-ff", "-q", "-m",
               f"Merge pull request #{self.release_pr_number} from mrmap-community/develop",
               "-m", "release: promote 0.2.0", "origin/develop", cwd=self.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.repo)
        self.merge_commit = git_ok("rev-parse", "HEAD", cwd=self.repo)
        self.state["merged_release_prs"] = [{
            "number": self.release_pr_number,
            "mergedAt": "2026-11-26T00:00:00Z",
            "mergeCommit": {"oid": self.merge_commit},
        }]
        self.save()
        return self.merge_commit

    # -- the steps under test ----------------------------------------------
    def run_step(self, text, job, step_name, env_extra):
        script = step_script(text, job, step_name)
        path = self.dir / f"{job}.sh"
        path.write_text(script, encoding="utf-8")
        env = dict(GIT_ENV,
                   GH_TOKEN="",
                   GITHUB_REPOSITORY="mrmap-community/mrmap",
                   GITHUB_OUTPUT=str(self.dir / "gh-output"),
                   RUNNER_TEMP=str(self.dir),
                   PATH=f"{self.dir}" + os.pathsep + os.environ.get("PATH", ""))
        env.update(GH_STATE=str(self.state_path), GH_JOURNAL=str(self.journal_path))
        env.update(env_extra)
        (self.dir / "gh-output").write_text("", encoding="utf-8")
        proc = subprocess.run(["bash", str(path)], cwd=str(self.repo), env=env,
                              capture_output=True, text=True, timeout=180)
        outputs = {}
        for line in (self.dir / "gh-output").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, _, value = line.partition("=")
                outputs[key] = value
        return proc, outputs

    def verify(self, text, version=VERSION):
        return self.run_step(text, "verify",
                             "Verify the reviewed release pull request",
                             {"VERSION": version})

    def publish(self, text, outputs=None, version=VERSION, publish=True,
                artifacts=ARTIFACTS, docs_commit=None, docs_release=None):
        outputs = outputs or {}
        merge = outputs.get("merge_commit", self.merge_commit or "")
        return self.run_step(text, "publish",
                             "Publish the tag and the GitHub release",
                             {"VERSION": outputs.get("version", version),
                              "MERGE_COMMIT": merge,
                              "TAG": outputs.get("tag", f"v{version}"),
                              "PUBLISH": "true" if publish else "false",
                              "ARTIFACTS": artifacts,
                              # What the `docs` job of the run hands `publish`
                              # through its outputs (#1609). The gate built the
                              # candidate by default; the worlds below pass
                              # another answer to test the refusals.
                              "DOCS_COMMIT": (merge if docs_commit is None
                                              else docs_commit),
                              "DOCS_RELEASE": (version if docs_release is None
                                               else docs_release)})

    # -- the documentation gate job of the same run -------------------------
    def docs_step(self, job, step_name, env_extra):
        return self.run_step(DOCS_GATE.read_text(encoding="utf-8"),
                             job, step_name, env_extra)

    # -- reading the world back --------------------------------------------
    def journal(self):
        return [json.loads(line) for line in
                self.journal_path.read_text(encoding="utf-8").splitlines() if line]

    def remote_ref(self, ref):
        for line in git("ls-remote", "origin", ref, cwd=self.repo).stdout.splitlines():
            sha, name = line.split("\t", 1)
            if name == ref:
                return sha
        return None

    def tag_commit(self, tag):
        return (self.remote_ref(f"refs/tags/{tag}^{{}}")
                or self.remote_ref(f"refs/tags/{tag}"))

    def master(self):
        return self.remote_ref("refs/heads/master")

    def tags(self):
        out = git("ls-remote", "--tags", "origin", cwd=self.repo)
        return sorted(line.split("\t")[-1].replace("refs/tags/", "")
                      for line in out.stdout.splitlines()
                      if "->" not in line and not line.endswith("^{}"))


# ---------------------------------------------------------- workflow reading
def load_workflow():
    """The workflow text the steps are read out of.

    Not a parse: scripts/workflow_steps.py reads the `run:` blocks, and it
    raises rather than guessing at a shape it does not read, which main()
    reports as a failure. A runner without PyYAML gets the same checks as one
    with it, because there is nothing here left to skip.
    """
    return WORKFLOW.read_text(encoding="utf-8")


def commands(job, step_name, text):
    """The step's script without its comment lines.

    A check that a command is absent has to mean absent from what bash runs: the
    header comments of these steps name the very commands they forbid, and a
    substring test over the whole script would fail on the explanation.
    """
    script = step_script(text, job, step_name)
    return "\n".join(line for line in script.splitlines()
                      if not line.lstrip().startswith("#"))


def step_script(text, job, step_name):
    return workflow_steps.step_script(text, job, step_name)


def needs_of(block):
    """The `needs:` of a job block, whether written as one job name or a list.

    Actions accepts both shapes; the checks about the gate wiring have to read
    both, because a `needs` nobody parses reads as "nothing is required".
    """
    lines = block.splitlines() if isinstance(block, str) else list(block)
    for index, line in enumerate(lines):
        if line.strip() == "needs:" and (len(line) - len(line.lstrip(" "))) == 4:
            out = []
            for follow in lines[index + 1:]:
                if not follow.strip():
                    continue
                if (len(follow) - len(follow.lstrip(" "))) <= 4:
                    break
                out.append(follow.strip().lstrip("- ").strip())
            return out
        if line.strip().startswith("needs:") \
                and (len(line) - len(line.lstrip(" "))) == 4:
            return [line.split(":", 1)[1].strip().strip("'\"")]
    return []


# ------------------------------------------------------------------- checks
def shape_checks(text):
    """The wiring the criteria depend on, read out of the file CI runs.

    Through scripts/workflow_steps.py rather than a YAML library: PyYAML is no
    stdlib dependency and no runner carries it, so a suite that skipped its
    checks for want of it would report green having tested nothing - which is
    how this suite first behaved in CI.
    """
    def reads(block, key, indent):
        lines = block.splitlines() if isinstance(block, str) else block
        return (any(l.strip().startswith(key + ":") for l in lines)
                and workflow_steps.scalar(block, key, indent))

    on = workflow_steps.region(text, "on", 0)
    triggers = workflow_steps.keys(on, 2)
    check("the workflow is dispatched by people and callable, never scheduled or push-triggered",
          set(triggers) == {"workflow_dispatch", "workflow_call"}, str(sorted(triggers)))

    dispatch_inputs = workflow_steps.region(
        workflow_steps.region(on, "workflow_dispatch", 2), "inputs", 4)
    names = workflow_steps.keys(dispatch_inputs, 6)
    check("dispatch requires the reviewed version and defaults publish to off",
          {"version", "publish"} <= set(names)
          and reads(workflow_steps.region(dispatch_inputs, "version", 6),
                    "required", 8) == "true"
          and reads(workflow_steps.region(dispatch_inputs, "publish", 6),
                    "default", 8) == "false",
          str(names))
    callable_inputs = workflow_steps.region(
        workflow_steps.region(on, "workflow_call", 2), "inputs", 4)
    check("the callable inputs mirror the dispatch inputs, so #1609 and #1800 read one interface",
          workflow_steps.keys(callable_inputs, 6) == names,
          str(workflow_steps.keys(callable_inputs, 6)))

    concurrency = workflow_steps.region(text, "concurrency", 0)
    check("one promotion runs at a time and a re-dispatch never cancels a run that may have tagged",
          reads(concurrency, "group", 2) == "release-promotion"
          and reads(concurrency, "cancel-in-progress", 2) == "false",
          str(concurrency))

    jobs = workflow_steps.keys(workflow_steps.region(text, "jobs", 0), 2)
    blocks = {job: workflow_steps.job_block(text, job) for job in jobs}
    check("verify, the documentation gate and publish, each needing what it needs",
          set(jobs) == {"verify", "docs", "publish"}
          and needs_of(blocks["docs"]) == ["verify"]
          and sorted(needs_of(blocks["publish"])) == ["docs", "verify"],
          str({job: needs_of(block) for job, block in blocks.items()}))
    # The documentation gate of #1609 is a reusable job and not a second copy of
    # the portal steps: the release consumes the same callable workflow an operator
    # dispatches, so there is one build to fix when the portal breaks.
    check("the documentation job calls the committed gate workflow with the verified commit",
          "uses: ./.github/workflows/docs-release-gate.yml" in blocks["docs"]
          and "sha: ${{ needs.verify.outputs.merge_commit }}" in blocks["docs"]
          and "runs-on" not in blocks["docs"] and "steps." not in blocks["docs"],
          blocks["docs"][:200])
    check("only the publishing job sits behind the protected environment",
          reads(blocks["publish"], "environment", 4) == "release-stable"
          and "environment" not in blocks["verify"]
          and "environment" not in blocks["docs"],
          str({job: ("release-stable" if "environment" in block else None)
               for job, block in blocks.items()}))
    check("least privilege: read at the top, write only where the tag and release are written",
          reads(workflow_steps.region(text, "permissions", 0), "contents", 2) == "read"
          and reads(workflow_steps.region(blocks["publish"], "permissions", 4),
                    "contents", 6) == "write"
          and not any("contents: write" in block
                      for job, block in blocks.items() if job != "publish"),
          str({job: ("write" if "contents: write" in block else "read")
               for job, block in blocks.items()}))
    check("no job reads a deployment or registry secret",
          not any("secrets." in block for block in blocks.values()),
          [job for job, block in blocks.items() if "secrets." in block])

    verify_script = commands("verify", "Verify the reviewed release pull request", text)
    publish_script = commands("publish", "Publish the tag and the GitHub release", text)
    check("verify asks GitHub for the merged develop -> master PR, the only head the policy admits",
          all(part in verify_script for part in
              ("--base master", "--head develop", "--state merged")))
    check("verify reads master's tip and that commit's VERSION rather than trusting a ref name",
          "refs/heads/master" in verify_script
          and 'git show "$MERGE_COMMIT:VERSION"' in verify_script)
    check("verify answers the immutable-tag conflict before writing anything",
          "refs/tags/$TAG" in verify_script and "already stands on" in verify_script
          and "git push" not in verify_script and "release create" not in verify_script)
    check("verify needs no write permission to answer", "contents: write" not in verify_script)
    check("publish re-reads master and the tag after the approval",
          "refs/heads/master" in publish_script and "refs/tags/$TAG" in publish_script)
    check("a stable release is never published without one digest per first-party image",
          "mrmap-backend mrmap-frontend" in publish_script
          and all(part in publish_script
                  for part in ('for image in', 'exit 1', '"$PUBLISH" = "true"')))
    check("publish pushes an annotated tag, never a forced one, and creates the release",
          "git tag -a" in publish_script and "gh release create" in publish_script
          and "--force" not in publish_script)
    # The documentation gate of #1609: `needs: docs` gives the ordering, and this
    # is the part that cannot be delegated to the edge - an approved run may have
    # queued behind anything, and the portal must be the one built from the commit
    # this job is about to tag.
    check("publish demands the documentation gate's answer about the same commit",
          'DOCS_COMMIT: ${{ needs.docs.outputs.documented_commit }}'
          in blocks["publish"]
          and '"$DOCS_COMMIT" != "$MERGE_COMMIT"' in publish_script
          and '"$DOCS_RELEASE" != "$VERSION"' in publish_script,
          [l for l in publish_script.splitlines() if "DOCS_" in l][:4])
    check("the documentation gate is answered before anything is written",
          publish_script.index('"$DOCS_COMMIT"')
          < publish_script.index('git tag -a'),
          "the portal answer is checked after the tag is pushed")
    check("the rehearsal exits without writing when publish is off",
          'if [ "$PUBLISH" != "true" ]' in publish_script)
    check("the release body quotes the verified commit and the image digests",
          'git show "$MERGE_COMMIT:CHANGELOG.md"' in publish_script
          and "Published images" in publish_script)
    both = verify_script + "\n" + publish_script
    check("the mechanism is Actions, gh and git - no repository tool is called",
          not any(f"{runner} scripts/" in both
                  for runner in ("python3", "python", "bash", "sh"))
          and "release_promotion" not in both,
          [l for l in both.splitlines() if "scripts/" in l][:3])


def docs_gate_shape_checks(text=""):
    """The gate workflow of #1609, read out of the file CI runs.

    The promotion consumes this workflow, so its contract is part of the release:
    what may trigger it, what it builds with, what it refuses, and - the boundary
    the revised epic #1589 draws - what it must never do, which is publish.
    """
    if not DOCS_GATE.is_file():
        check("the documentation gate workflow exists", False, str(DOCS_GATE))
        return ""
    text = DOCS_GATE.read_text(encoding="utf-8")

    on = workflow_steps.region(text, "on", 0)
    check("the gate is callable and operator-dispatched, never scheduled or push-triggered",
          set(workflow_steps.keys(on, 2)) == {"workflow_call", "workflow_dispatch"},
          str(workflow_steps.keys(on, 2)))
    called = workflow_steps.region(on, "workflow_call", 2)
    call_inputs = workflow_steps.region(called, "inputs", 4)
    check("a release build must name the revision it documents",
          "sha" in workflow_steps.keys(call_inputs, 6)
          and workflow_steps.scalar(
              workflow_steps.region(call_inputs, "sha", 6), "required", 8) == "true",
          str(workflow_steps.keys(call_inputs, 6)))
    check("the answer a caller reads is the provenance, not a file on disk",
          "documented_commit" in workflow_steps.keys(
              workflow_steps.region(called, "outputs", 4), 6),
          str(workflow_steps.keys(workflow_steps.region(called, "outputs", 4), 6)))

    jobs = workflow_steps.keys(workflow_steps.region(text, "jobs", 0), 2)
    check("one job, so the gate is the build", jobs == ["portal"], str(jobs))
    check("least privilege: the gate reads the repository and writes nothing",
          workflow_steps.scalar(workflow_steps.region(text, "permissions", 0),
                                "contents", 2) == "read"
          and "contents: write" not in text,
          "the portal job has no reason to write")
    check("one gate per revision, and a re-run never cancels a waiting promotion",
          workflow_steps.scalar(workflow_steps.region(text, "concurrency", 0),
                                "cancel-in-progress", 2) == "false"
          and "docs-release-gate-" in workflow_steps.scalar(
              workflow_steps.region(text, "concurrency", 0), "group", 2),
          workflow_steps.region(text, "concurrency", 0)[:3])

    scripts = workflow_steps.scripts_of(text, "portal")
    build = [line for line in scripts.splitlines() if "-m sphinx" in line]
    check("the gate builds the portal strictly, with the portal job's own flags",
          any(all(flag in line for flag in
                  ("-b html", "-E", "-W", "--keep-going")) for line in build),
          "; ".join(build) or "no sphinx invocation")
    check("the release build installs the one pinned docs environment",
          "backend/.requirements/docs.txt" in scripts
          and "pip install -r" in scripts and "apt" not in scripts,
          "the pin file is the whole toolchain")
    check("the gate needs no credential, database or container",
          "secrets." not in text and "docker compose" not in text
          and "POSTGRES" not in text,
          "the docs environment is the one pin file")
    # One expression names the revision everywhere, so the checkout, the
    # provenance and the assertion cannot drift to three different answers.
    revision_reads = [line.strip() for line in text.splitlines()
                      if "${{ inputs.sha || github.sha }}" in line]
    check("every revision the job reads comes from the one expression",
          len(revision_reads) >= 3
          and any(l.startswith("ref:") for l in revision_reads)
          and any(l.startswith("MRMAP_DOCS_REVISION:") for l in revision_reads)
          and any(l.startswith("REVISION:") for l in revision_reads),
          str(revision_reads))
    # The provenance of a *called* workflow would otherwise record the caller's
    # dispatch SHA (docs/source/_ext/mrmap_docs.py reads GITHUB_SHA first), so the
    # build has to name the revision it checked out under both names the extension
    # reads - otherwise the gate refuses its own correct build, and only in a
    # release.
    check("the strict build names the documented revision under both spellings",
          all(f"{name}: ${{{{ inputs.sha || github.sha }}}}" in text
              for name in ("GITHUB_SHA", "MRMAP_DOCS_REVISION")),
          [l.strip() for l in text.splitlines()
           if "MRMAP_DOCS_REVISION" in l or "GITHUB_SHA" in l])
    # The boundary of #1589 and #1608: a gate builds, the managed service hosts.
    published = [needle for needle in
                 ("actions/deploy-pages", "upload-pages-artifact", "gh-pages",
                  "sphinx-multiversion", "docker build", "rsync", "curl ",
                  "readthedocs")
                 if needle in scripts]
    check("the gate publishes nothing, in either dialect of that word",
          not published, ", ".join(published))
    # `uses:` is step metadata, not script, so this reads the file: exactly the
    # three ordinary actions of a build, and the artifact stays an artifact - the
    # gate neither downloads a build to consume it nor uploads it anywhere a
    # deployment reads.
    check("the only things it uses are checkout, python and its own artifact",
          len([l for l in text.splitlines() if "uses:" in l]) == 3
          and text.count("uses: actions/upload-artifact@v4") == 1
          and "uses: actions/checkout@v7" in text
          and "uses: actions/setup-python@v7" in text
          and "download-artifact" not in text
          and "uses: actions/" not in scripts,
          [l.strip() for l in text.splitlines() if "uses:" in l])
    check("a build that cannot name its revision fails the job rather than the review",
          'grep -Eq \'^[0-9a-f]{40}$\'' in scripts
          and "cannot name" in scripts
          and "continue-on-error" not in text,
          "a reported-only gate is not a gate")
    return text


def docs_gate_steps(text=""):
    """The gate's two shell steps, executed rather than quoted.

    Same convention as the promotion steps: what the runner runs is read out of
    the YAML and run under bash, so a check cannot pass against a copy.
    `MRMAP_DOCS_PYTHON` is the workflow's own hook for the interpreter, the one
    scripts/test_docs_build.py uses for the same reason.
    """
    w = World(tempfile.mkdtemp(prefix="mrmap-1609-gate-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        good = {"MRMAP_DOCS_PYTHON": sys.executable,
                "GITHUB_EVENT_NAME": "workflow_call"}

        proc, _ = w.docs_step("portal",
                              "Refuse a release build that cannot name its revision",
                              dict(good, REVISION=merge))
        check("the gate accepts a build that names its revision",
              proc.returncode == 0 and merge[:12] in proc.stdout,
              f"{proc.stdout[-160:]} {proc.stderr[-160:]}")
        proc, _ = w.docs_step("portal",
                              "Refuse a release build that cannot name its revision",
                              dict(good, REVISION=""))
        check("the gate refuses a call whose revision is empty",
              proc.returncode == 1 and "cannot name" in proc.stdout + proc.stderr,
              f"{proc.stdout[-160:]} {proc.stderr[-160:]}")
        proc, _ = w.docs_step("portal",
                              "Refuse a release build that cannot name its revision",
                              dict(good, REVISION="not-a-sha"))
        check("and refuses a revision that is not one",
              proc.returncode == 1, proc.stdout[-160:])

        proc, named = w.docs_step("portal", "Name the build",
                                  dict(good, INPUT_TAG="v0.2.0"))
        check("the build carries the release tag its caller named",
              proc.returncode == 0 and named.get("tag") == "v0.2.0", str(named))
        proc, named = w.docs_step("portal", "Name the build",
                                  dict(good, INPUT_TAG="latest"))
        check("a name that is not a release tag names nothing",
              proc.returncode == 0 and named.get("tag") == "", str(named))
        proc, named = w.docs_step("portal", "Name the build", dict(good, INPUT_TAG=""))
        check("and no input invents a tag the commit does not carry",
              proc.returncode == 0 and named.get("tag") == "", str(named))

        def provenance(**over):
            record = {"schema": "mrmap.docs.provenance.v1", "builder": "html",
                      "release": VERSION, "documented_commit": merge,
                      "toolchain": {"sphinx": "8.2.3"},
                      "source_digest": "sha256:" + "0" * 64}
            record.update(over)
            out = w.repo / "docs" / "build" / "html"
            out.mkdir(parents=True, exist_ok=True)
            (out / "provenance.json").write_text(json.dumps(record), encoding="utf-8")

        provenance()
        proc, out = w.docs_step("portal",
                                "Assert the build documented the reviewed revision",
                                dict(good, REVISION=merge))
        check("a portal built from the reviewed revision answers with its identity",
              proc.returncode == 0 and out.get("documented_commit") == merge
              and out.get("release") == VERSION,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]} {out}")

        provenance(documented_commit="f" * 40)
        proc, _ = w.docs_step("portal",
                              "Assert the build documented the reviewed revision",
                              dict(good, REVISION=merge))
        check("a portal of another tree is refused, and both shas are named",
              proc.returncode == 1 and "not the reviewed" in proc.stdout + proc.stderr
              and "f" * 12 in proc.stdout + proc.stderr,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")

        provenance(documented_commit=None)
        proc, _ = w.docs_step("portal",
                              "Assert the build documented the reviewed revision",
                              dict(good, REVISION=merge))
        check("a portal that cannot say what it built is refused",
              proc.returncode == 1, f"{proc.stdout[-200:]} {proc.stderr[-200:]}")

        provenance(toolchain={})
        proc, _ = w.docs_step("portal",
                              "Assert the build documented the reviewed revision",
                              dict(good, REVISION=merge))
        check("a portal without its toolchain is refused",
              proc.returncode == 1 and "sphinx" in proc.stdout + proc.stderr,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")

        (w.repo / "docs" / "build" / "html" / "provenance.json").unlink()
        proc, _ = w.docs_step("portal",
                              "Assert the build documented the reviewed revision",
                              dict(good, REVISION=merge))
        check("no provenance at all is refused too",
              proc.returncode == 1 and "cannot say what it built"
              in proc.stdout + proc.stderr,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def publish_refuses_an_unattributed_portal(text=""):
    """`publish` re-reads the gate's answer rather than trusting the `needs` edge.

    The edge proves the build was green; only this proves it was green FOR the
    commit being tagged - which is the one thing a release of documentation
    claims. Each refusal is read BEFORE a ref was written.
    """
    for label, kwargs, needle in (
            ("no answer at all", {"docs_commit": ""}, "no 40-hex documented_commit"),
            ("the answer of another commit", {"docs_commit": "e" * 40},
             "not of the reviewed"),
            ("an answer shaped wrongly", {"docs_commit": "abc"},
             "no 40-hex documented_commit"),
            ("an answer about another version", {"docs_release": "9.9.9"},
             "disagree about the version")):
        w = World(tempfile.mkdtemp(prefix=f"mrmap-1609-{abs(hash(label)) % 1000}-"))
        try:
            w.prepare_release_pr()
            w.merge_to_master()
            proc, out = w.verify(text)
            check(f"the world of {label} verifies", proc.returncode == 0,
                  f"{proc.stdout[-160:]} {proc.stderr[-160:]}")
            proc, _ = w.publish(text, out, **kwargs)
            check(f"publish refuses a documentation gate with {label}",
                  proc.returncode == 1 and needle in proc.stdout + proc.stderr,
                  f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
            check(f"and nothing is written for {label}",
                  w.tags() == [] and w.gh_state()["releases"] == [],
                  f"{w.tags()} {w.gh_state()['releases']}")
            # A rehearsal is not exempt: a release whose documentation is not the
            # candidate's must read red in the rehearsal too, or the rehearsal
            # teaches an operator to trust a broken release.
            proc, _ = w.publish(text, out, publish=False, **kwargs)
            check(f"the rehearsal refuses it too, for {label}",
                  proc.returncode == 1 and w.tags() == [], proc.stdout[-160:])
        finally:
            shutil.rmtree(w.dir, ignore_errors=True)


def no_merged_pr(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-no-pr-"))
    try:
        proc, _ = w.verify(text)
        check("verify refuses when no release pull request was merged",
              proc.returncode == 1 and "no merged develop -> master" in proc.stderr + proc.stdout,
              proc.stderr[:200])
        check("and names the human act that is missing",
              "only a person may merge" in proc.stderr + proc.stdout, proc.stderr[:200])
        proc, _ = w.publish(text)
        check("publish without a verified commit publishes nothing",
              proc.returncode == 1 and w.tags() == [] and w.gh_state()["releases"] == [],
              proc.stderr[:200])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def master_moved(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-moved-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        git_ok("checkout", "-q", "-B", "master", "origin/master", cwd=w.repo)
        (w.repo / "unreviewed.txt").write_text("landed on master alone\n", encoding="utf-8")
        git_ok("add", "-A", cwd=w.repo)
        git_ok("commit", "-q", "-m", "fix: merged straight to master", cwd=w.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/master", cwd=w.repo)
        proc, _ = w.verify(text)
        check("verify refuses a master that moved without a reviewed release merge",
              proc.returncode == 1 and "is not the merge commit" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("and says plainly that it will not re-anchor onto it",
              "Nothing here moves master" in proc.stderr + proc.stdout, proc.stderr[:220])
        check("no tag was pushed for the unreviewed tip", w.tags() == [])
        git_ok("update-ref", "refs/remotes/origin/master", merge, cwd=w.repo)
        git_ok("push", "-q", "-f", "origin", f"{merge}:refs/heads/master", cwd=w.repo)
        proc, out = w.verify(text)
        check("the same world verifies once master's tip is the reviewed merge again",
              proc.returncode == 0 and out.get("merge_commit") == merge,
              f"{proc.stderr[-200:]} {out}")
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def version_mismatch(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-version-"))
    try:
        w.prepare_release_pr()
        w.merge_to_master()
        proc, _ = w.verify(text, version="9.9.9")
        check("verify refuses a dispatch whose version the merged PR does not carry",
              proc.returncode == 1 and "carries VERSION" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("so a reviewed version cannot be published under another name",
              w.tags() == [] and w.gh_state()["releases"] == [])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def malformed_merge_commit(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-malformed-"))
    try:
        w.prepare_release_pr()
        w.merge_to_master()
        w.state["merged_release_prs"] = [{"number": 1700,
                                          "mergedAt": "2026-11-26T00:00:00Z",
                                          "mergeCommit": None}]
        w.save()
        proc, _ = w.verify(text)
        check("verify refuses rather than guessing when GitHub answers no merge commit",
              proc.returncode == 1 and "no merged develop -> master" in proc.stderr + proc.stdout,
              proc.stderr[:200])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def immutable_tag(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-foreign-tag-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        # A tag of this name already standing on another commit: the conflict the
        # criteria name, and it must be answered before anything is written.
        git_ok("checkout", "-q", "-B", "elsewhere", merge + "^1", cwd=w.repo)
        (w.repo / "other.txt").write_text("a different release\n", encoding="utf-8")
        git_ok("add", "-A", cwd=w.repo)
        git_ok("commit", "-q", "-m", "chore: an unrelated commit", cwd=w.repo)
        foreign = git_ok("rev-parse", "HEAD", cwd=w.repo)
        git_ok("tag", "-a", "-m", "v0.2.0", "v0.2.0", cwd=w.repo)
        git_ok("push", "-q", "origin", "refs/tags/v0.2.0", cwd=w.repo)
        proc, _ = w.verify(text)
        check("verify refuses to move a published tag that stands on another commit",
              proc.returncode == 1 and "already stands on" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("and it did not move it", w.tag_commit("v0.2.0") == foreign)
        check("a re-run refuses too, so retrying cannot smuggle it through",
              w.verify(text)[0].returncode == 1)
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def green_publish(text):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-green-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        proc, out = w.verify(text)
        check("verify passes on the reviewed state", proc.returncode == 0,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
        check("verify reports the merge commit, the version and the tag as job outputs",
              out.get("merge_commit") == merge and out.get("version") == VERSION
              and out.get("tag") == "v0.2.0", str(out))
        check("the facts a reviewer needs are on the run's own output, not in a file",
              merge[:12] in proc.stdout and "release PR #1700" in proc.stdout,
              proc.stdout[-200:])

        proc, _ = w.publish(text, out, publish=False)
        check("the rehearsal writes no tag and no release",
              proc.returncode == 0 and w.tags() == [] and w.gh_state()["releases"] == [],
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
        check("the rehearsal says that it withheld",
              "rehearsal" in proc.stdout and "nothing was written" in proc.stdout,
              proc.stdout[-200:])
        check("and prints the tag and the body it would have written",
              "v0.2.0" in proc.stdout and BACKEND_DIGEST in proc.stdout,
              proc.stdout[-300:])

        proc, _ = w.publish(text, out, publish=True)
        check("publish tags master's tip",
              proc.returncode == 0 and w.tag_commit("v0.2.0") == merge,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
        tag_object = w.remote_ref("refs/tags/v0.2.0")
        check("with an annotated tag, so the tag object carries the release",
              tag_object is not None and tag_object != merge, f"{tag_object} vs {merge}")
        releases = w.gh_state()["releases"]
        check("and creates exactly one GitHub release standing on that commit",
              [r["tagName"] for r in releases] == ["v0.2.0"]
              and releases[0]["target"] == merge, json.dumps(releases))
        notes = Path(releases[0]["notes_file"]).read_text(encoding="utf-8")
        check("the release body carries the version, that commit's changelog section, "
              "both digests and the verified sha",
              "[0.2.0]" in notes and "the first planned feature" in notes
              and "a repair worth a note" in notes
              and BACKEND_DIGEST in notes and FRONTEND_DIGEST in notes
              and merge in notes, notes[:300])
        check("and invents nothing from the unreleased window into it",
              "Curated entry written by a human" not in notes, notes[:200])
        check("every GitHub call the steps made is journaled, so the run is auditable",
              any(c[:2] == ["release", "create"] for c in w.journal()),
              str(w.journal())[:200])

        proc, _ = w.publish(text, out, publish=True)
        check("re-running publish is a skip and never a duplicate",
              proc.returncode == 0 and "nothing to do" in proc.stdout
              and [r["tagName"] for r in w.gh_state()["releases"]] == ["v0.2.0"],
              proc.stdout[-200:])
        check("and the tag still stands where it was written",
              w.tag_commit("v0.2.0") == merge)

        # The approval queued behind something that moved master.
        git_ok("checkout", "-q", "-B", "master", "origin/master", cwd=w.repo)
        (w.repo / "late.txt").write_text("merged after the approval\n", encoding="utf-8")
        git_ok("add", "-A", cwd=w.repo)
        git_ok("commit", "-q", "-m", "fix: landed while this run was approved", cwd=w.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/master", cwd=w.repo)
        proc, _ = w.publish(text, out, publish=True)
        check("publish re-checks master after the approval and refuses a moved tip",
              proc.returncode == 1 and "moved away from the verified" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("so nothing is published onto a commit that was never the reviewed merge",
              w.tag_commit("v0.2.0") == merge)
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def measured_and_documented(text):
    """The two measurements that decide this design, pinned so a swap back to
    release-please's own github-release has to be re-measured, not asserted."""
    design = DESIGN.read_text(encoding="utf-8")
    check("the rehearsal and the two upstream facts are documented",
          "github-release" in design and "skip-github-release" in design
          and "base branch" in design, design[:120])
    check("the runbook still sends an operator to the release-stable environment",
          "release-stable" in RUNBOOK.read_text(encoding="utf-8"))
    # The registry must not name the retired tool. It does name its own test
    # suite, whose path ends in the same words, so match the tool's path.
    check("nothing still ships the superseded promotion tool or its registry entry",
          not (REPO / "scripts" / "release_promotion.py").exists()
          and "scripts/release_promotion.py" not in
              (REPO / "scripts" / "release_lifecycle.json").read_text(encoding="utf-8"))
    check("and the lifecycle still names the workflow as the promotion mechanism",
          "release-promotion.yml" in
          (REPO / "scripts" / "release_lifecycle.json").read_text(encoding="utf-8"))


def main():
    if not shutil.which("git") or not shutil.which("bash"):
        # Exit 2 is the "the harness cannot run" answer the lifecycle dry run
        # uses for the same case, and check_repo_tooling.sh reports it as a
        # failure. It is deliberately not an OK: a suite that executed nothing
        # must never report a pass, and "OK (0/0 checks passed)" is exactly how
        # this file once hid that it had run no check at all.
        print("harness cannot run: git and bash are both required to execute "
              "the workflow's steps")
        return 2
    try:
        text = load_workflow()
        shape_checks(text)
    except workflow_steps.WorkflowReadingError as exc:
        # The steps ARE the implementation, so a workflow whose steps cannot be
        # read is a failure to report, never a reason to skip the suite.
        check("the promotion workflow's steps can be read", False, str(exc))
        print(f"FAIL  the promotion workflow's steps can be read - {exc}")
        print(f"FAILED ({sum(1 for r in RESULTS if r[1])}/{len(RESULTS)} "
              "checks passed)")
        return 1

    for name, fn in (("no merged release PR", no_merged_pr),
                     ("master moved on its own", master_moved),
                     ("version mismatch", version_mismatch),
                     ("malformed merge commit", malformed_merge_commit),
                     ("immutable tag conflict", immutable_tag),
                     ("green publish, rehearsal and rerun", green_publish),
                     ("documentation gate shape", docs_gate_shape_checks),
                     ("documentation gate steps", docs_gate_steps),
                     ("publish without an attributed portal",
                      publish_refuses_an_unattributed_portal)):
        try:
            fn(text)
        except workflow_steps.WorkflowReadingError as exc:
            # The gate workflow is part of the release contract too: unreadable
            # steps there are as much a failure as unreadable steps here.
            check(f"{name} reads the committed workflow", False, str(exc))
        except Exception as exc:
            check(name, False, f"raised {type(exc).__name__}: {exc}")
    measured_and_documented(text)

    # No SKIP label: this suite has nothing a runner could lack and still let
    # the promotion be checked, so a missing prerequisite is the exit-2 answer
    # above rather than a check that reports itself skipped.
    failed = [r for r in RESULTS if r[1] is False]
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  - {detail}"
                                                      if not ok and detail else ""))
    passed = [r for r in RESULTS if r[1] is True]
    print(f'{"FAILED" if failed or not RESULTS else "OK"} ({len(passed)}/'
          f"{len(RESULTS)} checks passed)")
    if not RESULTS:
        # Nothing reached check(), so nothing was tested. An empty run is never
        # a pass, whatever else went wrong on the way here.
        print("harness cannot run: no check was executed")
        return 2
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
