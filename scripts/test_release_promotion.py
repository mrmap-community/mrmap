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
(also run by scripts/check_repo_tooling.sh). Standard library only; `yaml` is
used for the shape checks and its absence skips those out loud. git and bash are
required; docker, node and the network are not.
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
WORKFLOW = REPO / ".github" / "workflows" / "release-promotion.yml"
RUNBOOK = REPO / "docs" / "source" / "administration" / "release-operator-runbook.rst"
DESIGN = REPO / "docs" / "source" / "development" / "release-promotion.rst"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    return bool(ok)


def skip(name, detail):
    RESULTS.append((name, None, detail))


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
    def run_step(self, doc, job, step_name, env_extra):
        script = step_script(doc, job, step_name)
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

    def verify(self, doc, version=VERSION):
        return self.run_step(doc, "verify",
                             "Verify the reviewed release pull request",
                             {"VERSION": version})

    def publish(self, doc, outputs=None, version=VERSION, publish=True,
                artifacts=ARTIFACTS):
        outputs = outputs or {}
        return self.run_step(doc, "publish",
                             "Publish the tag and the GitHub release",
                             {"VERSION": outputs.get("version", version),
                              "MERGE_COMMIT": outputs.get("merge_commit",
                                                          self.merge_commit or ""),
                              "TAG": outputs.get("tag", f"v{version}"),
                              "PUBLISH": "true" if publish else "false",
                              "ARTIFACTS": artifacts})

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
    try:
        import yaml
    except ImportError:
        return None
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def commands(job, step_name, doc):
    """The step's script without its comment lines.

    A check that a command is absent has to mean absent from what bash runs: the
    header comments of these steps name the very commands they forbid, and a
    substring test over the whole script would fail on the explanation.
    """
    script = step_script(doc, job, step_name)
    return "\n".join(line for line in script.splitlines()
                      if not line.lstrip().startswith("#"))


def step_script(doc, job, step_name):
    for step in doc["jobs"][job]["steps"]:
        if step.get("name") == step_name:
            return step["run"]
    raise AssertionError(f"no step named {step_name!r} in job {job!r}")


# ------------------------------------------------------------------- checks
def shape_checks(doc):
    triggers = doc.get("on", doc.get(True))
    check("the workflow is dispatched by people and callable, never scheduled or push-triggered",
          set(triggers) == {"workflow_dispatch", "workflow_call"}, str(sorted(triggers)))
    check("dispatch requires the reviewed version and defaults publish to off",
          triggers["workflow_dispatch"]["inputs"]["version"]["required"] is True
          and triggers["workflow_dispatch"]["inputs"]["publish"]["default"] is False,
          json.dumps(triggers["workflow_dispatch"]["inputs"]))
    check("the callable inputs mirror the dispatch inputs, so #1609 and #1800 read one interface",
          set(triggers["workflow_call"]["inputs"])
          == set(triggers["workflow_dispatch"]["inputs"]),
          str(sorted(triggers["workflow_call"]["inputs"])))
    check("one promotion runs at a time and a re-dispatch never cancels a run that may have tagged",
          doc["concurrency"] == {"group": "release-promotion",
                                 "cancel-in-progress": False},
          json.dumps(doc["concurrency"]))

    jobs = doc["jobs"]
    check("exactly two jobs, and the publisher needs the verifier",
          set(jobs) == {"verify", "publish"} and jobs["publish"]["needs"] == "verify",
          str(sorted(jobs)))
    check("only the publishing job sits behind the protected environment",
          jobs["publish"].get("environment") == "release-stable"
          and "environment" not in jobs["verify"],
          str({k: v.get("environment") for k, v in jobs.items()}))
    check("least privilege: read at the top, write only where the tag and release are written",
          doc["permissions"] == {"contents": "read"}
          and jobs["verify"].get("permissions", {"contents": "read"}) == {"contents": "read"}
          and jobs["publish"]["permissions"] == {"contents": "write"},
          json.dumps({k: v.get("permissions") for k, v in jobs.items()}))
    check("no job reads a deployment or registry secret",
          not any("secrets." in json.dumps(job) for job in jobs.values()))

    verify_script = commands("verify", "Verify the reviewed release pull request", doc)
    publish_script = commands("publish", "Publish the tag and the GitHub release", doc)
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


def no_merged_pr(doc):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-no-pr-"))
    try:
        proc, _ = w.verify(doc)
        check("verify refuses when no release pull request was merged",
              proc.returncode == 1 and "no merged develop -> master" in proc.stderr + proc.stdout,
              proc.stderr[:200])
        check("and names the human act that is missing",
              "only a person may merge" in proc.stderr + proc.stdout, proc.stderr[:200])
        proc, _ = w.publish(doc)
        check("publish without a verified commit publishes nothing",
              proc.returncode == 1 and w.tags() == [] and w.gh_state()["releases"] == [],
              proc.stderr[:200])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def master_moved(doc):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-moved-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        git_ok("checkout", "-q", "-B", "master", "origin/master", cwd=w.repo)
        (w.repo / "unreviewed.txt").write_text("landed on master alone\n", encoding="utf-8")
        git_ok("add", "-A", cwd=w.repo)
        git_ok("commit", "-q", "-m", "fix: merged straight to master", cwd=w.repo)
        git_ok("push", "-q", "origin", "HEAD:refs/heads/master", cwd=w.repo)
        proc, _ = w.verify(doc)
        check("verify refuses a master that moved without a reviewed release merge",
              proc.returncode == 1 and "is not the merge commit" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("and says plainly that it will not re-anchor onto it",
              "Nothing here moves master" in proc.stderr + proc.stdout, proc.stderr[:220])
        check("no tag was pushed for the unreviewed tip", w.tags() == [])
        git_ok("update-ref", "refs/remotes/origin/master", merge, cwd=w.repo)
        git_ok("push", "-q", "-f", "origin", f"{merge}:refs/heads/master", cwd=w.repo)
        proc, out = w.verify(doc)
        check("the same world verifies once master's tip is the reviewed merge again",
              proc.returncode == 0 and out.get("merge_commit") == merge,
              f"{proc.stderr[-200:]} {out}")
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def version_mismatch(doc):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-version-"))
    try:
        w.prepare_release_pr()
        w.merge_to_master()
        proc, _ = w.verify(doc, version="9.9.9")
        check("verify refuses a dispatch whose version the merged PR does not carry",
              proc.returncode == 1 and "carries VERSION" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("so a reviewed version cannot be published under another name",
              w.tags() == [] and w.gh_state()["releases"] == [])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def malformed_merge_commit(doc):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-malformed-"))
    try:
        w.prepare_release_pr()
        w.merge_to_master()
        w.state["merged_release_prs"] = [{"number": 1700,
                                          "mergedAt": "2026-11-26T00:00:00Z",
                                          "mergeCommit": None}]
        w.save()
        proc, _ = w.verify(doc)
        check("verify refuses rather than guessing when GitHub answers no merge commit",
              proc.returncode == 1 and "no merged develop -> master" in proc.stderr + proc.stdout,
              proc.stderr[:200])
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def immutable_tag(doc):
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
        proc, _ = w.verify(doc)
        check("verify refuses to move a published tag that stands on another commit",
              proc.returncode == 1 and "already stands on" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("and it did not move it", w.tag_commit("v0.2.0") == foreign)
        check("a re-run refuses too, so retrying cannot smuggle it through",
              w.verify(doc)[0].returncode == 1)
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def green_publish(doc):
    w = World(tempfile.mkdtemp(prefix="mrmap-1798-green-"))
    try:
        w.prepare_release_pr()
        merge = w.merge_to_master()
        proc, out = w.verify(doc)
        check("verify passes on the reviewed state", proc.returncode == 0,
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
        check("verify reports the merge commit, the version and the tag as job outputs",
              out.get("merge_commit") == merge and out.get("version") == VERSION
              and out.get("tag") == "v0.2.0", str(out))
        check("the facts a reviewer needs are on the run's own output, not in a file",
              merge[:12] in proc.stdout and "release PR #1700" in proc.stdout,
              proc.stdout[-200:])

        proc, _ = w.publish(doc, out, publish=False)
        check("the rehearsal writes no tag and no release",
              proc.returncode == 0 and w.tags() == [] and w.gh_state()["releases"] == [],
              f"{proc.stdout[-200:]} {proc.stderr[-200:]}")
        check("the rehearsal says that it withheld",
              "rehearsal" in proc.stdout and "nothing was written" in proc.stdout,
              proc.stdout[-200:])
        check("and prints the tag and the body it would have written",
              "v0.2.0" in proc.stdout and BACKEND_DIGEST in proc.stdout,
              proc.stdout[-300:])

        proc, _ = w.publish(doc, out, publish=True)
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

        proc, _ = w.publish(doc, out, publish=True)
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
        proc, _ = w.publish(doc, out, publish=True)
        check("publish re-checks master after the approval and refuses a moved tip",
              proc.returncode == 1 and "moved away from the verified" in proc.stderr + proc.stdout,
              proc.stderr[:220])
        check("so nothing is published onto a commit that was never the reviewed merge",
              w.tag_commit("v0.2.0") == merge)
    finally:
        shutil.rmtree(w.dir, ignore_errors=True)


def measured_and_documented(doc):
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
        print("SKIP  git or bash is unavailable; the promotion checks need both")
        print("OK (0 of 0 checks passed)")
        return 0
    try:
        doc = load_workflow()
    except Exception as exc:            # a workflow that will not parse is red
        check("the promotion workflow parses as YAML", False, str(exc))
        print("FAIL  the promotion workflow parses as YAML - " + str(exc))
        print("FAILED (1 of 1 checks passed)")
        return 1
    if doc is None:
        skip("workflow shape checks", "PyYAML is not importable on this runner")
    else:
        shape_checks(doc)
        for name, fn in (("no merged release PR", no_merged_pr),
                         ("master moved on its own", master_moved),
                         ("version mismatch", version_mismatch),
                         ("malformed merge commit", malformed_merge_commit),
                         ("immutable tag conflict", immutable_tag),
                         ("green publish, rehearsal and rerun", green_publish)):
            try:
                fn(doc)
            except Exception as exc:
                check(name, False, f"raised {type(exc).__name__}: {exc}")
        measured_and_documented(doc)

    failed = [r for r in RESULTS if r[1] is False]
    skipped = [r for r in RESULTS if r[1] is None]
    for name, ok, detail in RESULTS:
        label = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        line = f"{label}  {name}"
        if ok is not True and detail:
            line += f"  - {detail}"
        print(line)
    passed = [r for r in RESULTS if r[1] is True]
    print(f'{"FAILED" if failed else "OK"} ({len(passed)}/'
          f"{len(RESULTS) - len(skipped)} checks passed)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
