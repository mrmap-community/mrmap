#!/usr/bin/env python3
"""Offline checks for scripts/release_promotion (issue #1584, epic #1577).

Runs without docker, without network and without a GitHub token: the tool is
driven against throw-away git repositories whose "origin" is a local bare
repository (the file transport the migration-graph suite already uses), and
every GitHub fact answers from a `gh` shim that journals its calls to a file
and keeps open PRs and published releases in a small JSON state. No check here
pretends to talk to GitHub; `--git-bin`/`--gh-bin` are the same seams a real
operator could point at a mirror, and the assertions read what the tool
actually sent through them.

The suite's duty is the issue's acceptance lines, red first: a candidate that
was not planned, evidence of another sha, a frozen branch elsewhere, a master
whose tree diverged from the tested one, a tag already standing on a foreign
commit, a missing digest - each must be seen REFUSED, and refused BEFORE the
tool touched a tag or a release. Then the same worlds run the promotion to
green, and every step is re-run to prove the reconcile path ("already done"
is a skip, never a duplicate).

Run from the repository root: `python3 scripts/test_release_promotion.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROMO = HERE / "release_promotion.py"
TOOLS = ["release_promotion.py", "release_gates.py", "canonical_version.py"]

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def promo_module():
    """The tool as a module, for checks that need no repository at all."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("release_promotion", PROMO)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "canonical_version", HERE / "canonical_version.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CANON = canonical_module()

# ---------------------------------------------------------------- git plumbing

GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null",
               GIT_CONFIG_SYSTEM="/dev/null")


def git(*argv, cwd=None):
    proc = subprocess.run(["git", *argv], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, env=GIT_ENV)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_ok(*argv, cwd=None):
    proc = subprocess.run(["git", *argv], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, env=GIT_ENV)
    return proc.returncode


def candidate_files(version, folded=True, projection=None, manifest=None):
    """The five-file shape of a planned release, as path -> content."""
    changelog = "# Changelog\n\n"
    if folded:
        changelog += f"## [{version}] - 2026-11-20\n\n### Added\n\n- work\n"
    else:
        changelog += "### Added\n\n- work\n"
    return {
        "VERSION": version + "\n",
        "backend/MrMap/version.py": (
            projection if projection is not None
            else CANON.render_projection(version)),
        ".release-please-manifest.json": json.dumps(
            manifest or {".": version}) + "\n",
        "CHANGELOG.md": changelog,
        "app.txt": f"state of {version}\n",
    }


def write_files(root, files):
    for rel, content in files.items():
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


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


class World:
    """A clone, its bare origin, and the journaling gh that answers for it."""

    def __init__(self, tmp, name, with_candidate=True):
        self.dir = Path(tmp) / name
        origin = self.dir / "origin.git"
        self.clone = self.dir / "clone"
        self.gh = self.dir / "gh"
        self.state = self.dir / "gh-state.json"
        self.journal = self.dir / "gh-journal.jsonl"
        self.dir.mkdir(parents=True)
        self.gh.write_text(GH_SHIM, encoding="utf-8")
        self.gh.chmod(0o755)
        self.state.write_text('{"prs": [], "releases": []}', encoding="utf-8")
        git("init", "--bare", "--initial-branch=develop", str(origin))
        git("clone", "-q", str(origin), str(self.clone))
        for key, value in (("user.email", "t@t"), ("user.name", "t"),
                           ("commit.gpgsign", "false")):
            git("config", key, value, cwd=self.clone)
        write_files(self.clone, candidate_files("0.1.0", folded=False))
        git("add", "-A", cwd=self.clone)
        git("commit", "-qm", "base", cwd=self.clone)
        self.base_sha = git("rev-parse", "HEAD", cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.clone)
        if with_candidate:
            self.candidate_sha = self.add_candidate("0.2.0")
        else:
            self.candidate_sha = None

    def add_candidate(self, version, **kwargs):
        write_files(self.clone, candidate_files(version, **kwargs))
        git("add", "-A", cwd=self.clone)
        git("commit", "-qm", f"release {version}", cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.clone)
        return git("rev-parse", "HEAD", cwd=self.clone)

    def journal_calls(self):
        if not self.journal.exists():
            return []
        return [json.loads(line)
                for line in self.journal.read_text().splitlines() if line]

    def remote_sha(self, ref):
        out = git("ls-remote", "origin", ref, cwd=self.clone)
        for line in out.splitlines():
            sha, name = line.split("\t", 1)
            if name == ref:
                return sha
        return None

    def promo(self, *argv):
        env = dict(GIT_ENV, GH_STATE=str(self.state),
                   GH_JOURNAL=str(self.journal))
        cmd = [sys.executable, str(PROMO), "--root", str(self.clone),
               "--gh-bin", str(self.gh), *argv]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)


def reports(tmpdir, version="0.2.0"):
    """Synthetic gate reports in the shape release_gates promote reads."""
    paths = {}
    for name, extra in (("api", {}),
                        ("version", {"candidate_version": version}),
                        ("upgrade", {})):
        path = Path(tmpdir) / f"{name}-report.json"
        path.write_text(json.dumps({"gate": name, "ok": True,
                                    "mode": "pre-baseline", **extra}),
                        encoding="utf-8")
        paths[name] = str(path)
    return paths


GREEN_CHECKS = [
    {"name": "unit-tests", "conclusion": "success", "html_url": "u-tests"},
    {"name": "acceptance-tests", "conclusion": "success",
     "html_url": "u-accept"},
    {"name": "sonarcloud", "conclusion": "success", "html_url": "u-sonar"},
]
BACKEND = "sha256:" + "a" * 64
FRONTEND = "sha256:" + "b" * 64
ARTIFACTS = ["--artifact=mrmap-backend=" + BACKEND,
             "--artifact=mrmap-frontend=" + FRONTEND]


def evidence_file(world, path, sha=None):
    checks = Path(str(path) + ".checks.json")
    checks.write_text(json.dumps(GREEN_CHECKS), encoding="utf-8")
    proc = world.promo("evidence", "--sha", sha or world.candidate_sha,
                       "--checks-file", str(checks),
                       "--manual", "dependencies=https://deps.test/audit",
                       *ARTIFACTS, "--output", str(path))
    return proc


def human_merge_release_pr(world):
    """What the acceptance criteria reserve to people, simulated here with
    plain git: a merge commit onto master carrying the candidate. Where the
    frozen release branch exists it is what gets merged; worlds that test
    finalize without the open step merge the candidate sha directly - the
    merge commit's tree is the point either way."""
    git("fetch", "-q", "origin", cwd=world.clone)
    git("checkout", "-q", "-B", "master", "origin/master", cwd=world.clone)
    if world.remote_sha("refs/heads/release/v0.2.0"):
        rev = "origin/release/v0.2.0"
    else:
        rev = world.candidate_sha
    git("merge", "--no-ff", "-m", "chore: release v0.2.0", rev,
        cwd=world.clone)
    git("push", "-q", "origin", "master", cwd=world.clone)
    return git("rev-parse", "master", cwd=world.clone)


# ------------------------------------------------------------------ the checks


def test_plan_reads_a_planned_candidate(tmp):
    w = World(tmp, "plan-ok")
    proc = w.promo("plan")
    check("plan: a planned candidate is read with its version and steps",
          proc.returncode == 0
          and "planned 0.2.0 release" in proc.stdout
          and "changelog: [0.2.0] folded" in proc.stdout
          and "manifest: 0.2.0" in proc.stdout, proc.stderr)


def test_plan_refuses_unplanned_commits(tmp):
    w = World(tmp, "plan-changelog")
    sloppy = w.add_candidate("0.3.0", folded=False)
    proc = w.promo("plan", "--sha", sloppy)
    check("plan: a VERSION move without its folded changelog section is "
          "refused", proc.returncode == 1
          and "CHANGELOG.md" in proc.stderr, proc.stderr + proc.stdout)

    w2 = World(tmp, "plan-manifest")
    drift = w2.add_candidate("0.3.0", manifest={".": "0.1.0"})
    proc = w2.promo("plan", "--sha", drift)
    check("plan: VERSION moved while the release manifest stayed is refused",
          proc.returncode == 1 and "manifest" in proc.stderr, proc.stderr)

    w3 = World(tmp, "plan-projection")
    drift = w3.add_candidate("0.3.0", projection="# not regenerated\n")
    proc = w3.promo("plan", "--sha", drift)
    check("plan: a projection that is not the projection of VERSION is "
          "refused", proc.returncode == 1 and "projection" in proc.stderr,
          proc.stderr)

    w4 = World(tmp, "plan-side")
    write_files(w4.clone, candidate_files("0.9.0"))
    git("add", "-A", cwd=w4.clone)
    git("commit", "-qm", "side", cwd=w4.clone)
    side = git("rev-parse", "HEAD", cwd=w4.clone)
    proc = w4.promo("plan", "--sha", side)
    check("plan: a commit develop itself does not carry is refused",
          proc.returncode == 1 and "reachable" in proc.stderr, proc.stderr)

    w5 = World(tmp, "plan-expect")
    proc = w5.promo("plan", "--expect-version", "9.9.9")
    check("plan: the expected version must BE the candidate's version",
          proc.returncode == 1 and "9.9.9" in proc.stderr, proc.stderr)


def test_evidence_binds_ci_to_the_candidate(tmp):
    w = World(tmp, "evidence")
    checks = Path(w.dir) / "checks.json"
    checks.write_text(json.dumps(GREEN_CHECKS), encoding="utf-8")
    proc = w.promo("evidence", "--sha", w.candidate_sha,
                   "--checks-file", str(checks),
                   "--manual", "dependencies=https://deps.test/audit",
                   *ARTIFACTS)
    ok = proc.returncode == 0
    evidence = json.loads(proc.stdout) if ok else {}
    classes = evidence.get("checks", {})
    check("evidence: green CI plus digests and manual dependencies assembles "
          "all four required classes", ok
          and all(name in classes for name in
                  ("tests", "sonar", "dependencies", "artifacts"))
          and classes.get("artifacts", {}).get("images", {}).get(
              "mrmap-backend", {}).get("digest") == BACKEND, proc.stderr)

    proc = w.promo("evidence", "--sha", w.candidate_sha,
                   "--checks-file", str(checks), "--manual",
                   "dependencies=https://deps.test/audit")
    check("evidence: without artifact digests the collector reports the "
          "missing class and exits 1", proc.returncode == 1
          and "artifacts" in proc.stderr, proc.stderr)


def test_preflight_is_the_one_promoter(tmp):
    w = World(tmp, "preflight")
    ev = Path(w.dir) / "evidence.json"
    proc = evidence_file(w, ev)
    check("preflight: complete evidence of the candidate attests it",
          proc.returncode == 0, proc.stderr)
    rep = reports(w.dir)
    att = Path(w.dir) / "attestation.json"
    proc = w.promo("preflight", "--evidence", str(ev),
                   "--report", f"api={rep['api']}",
                   "--report", f"version={rep['version']}",
                   "--report", f"upgrade={rep['upgrade']}",
                   "--actor", "suite", "--output", str(att))
    text = att.read_text(encoding="utf-8") if att.exists() else ""
    check("preflight: release_gates promote is the attester and its shape "
          "survives", proc.returncode == 0
          and '"mrmap-release-candidate/1"' in text
          and w.candidate_sha in text and '"0.2.0"' in text, proc.stderr)

    proc = w.promo("preflight", "--evidence", str(ev),
                   "--report", f"api={rep['api']}",
                   "--report", f"upgrade={rep['upgrade']}")
    check("preflight: a gate report that was never run stops the promotion",
          proc.returncode == 1 and "version" in proc.stderr, proc.stderr)

    ev2 = Path(w.dir) / "evidence-base.json"
    evidence_file(w, ev2, sha=w.base_sha)
    with open(ev2, encoding="utf-8") as fh:
        other = json.load(fh)
    other["candidate"] = {"sha": w.base_sha, "version": "0.2.0"}
    with open(ev2, "w", encoding="utf-8") as fh:
        json.dump(other, fh)
    proc = w.promo("preflight", "--sha", w.base_sha, "--evidence", str(ev2),
                   "--report", f"api={rep['api']}",
                   "--report", f"version={rep['version']}",
                   "--report", f"upgrade={rep['upgrade']}")
    check("preflight: the base commit is not a planned candidate and is "
          "refused before any attestation", proc.returncode == 1,
          proc.stderr)


def test_open_release_pr_freezes_and_opens(tmp):
    w = World(tmp, "open-pr")
    proc = w.promo("open-release-pr")
    frozen = w.remote_sha("refs/heads/release/v0.2.0")
    created = [c for c in w.journal_calls() if c[:2] == ["pr", "create"]]
    check("open-release-pr: the candidate is frozen at a release branch and "
          "one PR to master is opened", proc.returncode == 0
          and frozen == w.candidate_sha
          and len(created) == 1
          and created[0][created[0].index("--base") + 1] == "master",
          proc.stderr + str(created))
    proc = w.promo("open-release-pr")
    created = [c for c in w.journal_calls() if c[:2] == ["pr", "create"]]
    check("open-release-pr: re-running finds the open PR and opens nothing "
          "twice", proc.returncode == 0 and "already open" in proc.stdout
          and len(created) == 1, proc.stdout + proc.stderr)

    w2 = World(tmp, "open-pr-conflict")
    git("push", "-q", "origin",
        f"{w2.base_sha}:refs/heads/release/v0.2.0", cwd=w2.clone)
    proc = w2.promo("open-release-pr")
    check("open-release-pr: a release branch already standing at another "
          "commit is a conflict the tool refuses, never a move",
          proc.returncode == 1 and "never moves" in proc.stderr, proc.stderr)


def test_finalize_before_and_after_the_merge(tmp):
    w = World(tmp, "finalize")
    proc = w.promo("finalize", *ARTIFACTS)
    check("finalize: before a person merged, master does not carry the "
          "candidate and publishing is refused", proc.returncode == 1
          and "unmerged" in proc.stderr, proc.stderr)

    proc = w.promo("finalize", "--alias", "latest", *ARTIFACTS)
    check("finalize: rolling aliases stay refused while Q1 of #1578 is "
          "Pending", proc.returncode == 1 and "alias" in proc.stderr.lower(),
          proc.stderr)

    tip = human_merge_release_pr(w)
    proc = w.promo("finalize", *ARTIFACTS)
    tagged = w.remote_sha("refs/tags/v0.2.0")
    released = [c for c in w.journal_calls()
                if c[:2] == ["release", "create"]]
    check("finalize: after the reviewed merge the tree check passes, the "
          "annotated tag stands on master's tip and the release is published",
          proc.returncode == 0 and tagged is not None
          and w.remote_sha("refs/tags/v0.2.0^{}") == tip
          and len(released) == 1, proc.stderr + str(released))

    proc = w.promo("finalize", *ARTIFACTS)
    released = [c for c in w.journal_calls()
                if c[:2] == ["release", "create"]]
    check("finalize: re-running skips the tag and leaves the release body "
          "untouched - nothing is published twice", proc.returncode == 0
          and "already at the expected commit" in proc.stdout
          and "already exists" in proc.stdout and len(released) == 1,
          proc.stdout + proc.stderr)

    proc = w.promo("finalize", "--artifact=mrmap-backend=nonsense",
                   "--artifact=mrmap-frontend=" + FRONTEND)
    check("finalize: a digest that is not sha256:<64 hex> is refused",
          proc.returncode == 1 and "sha256:" in proc.stderr, proc.stderr)

    proc = w.promo("gate")
    check("gate: with tag, release and merged tree all in place the "
          "promotion answers green", proc.returncode == 0
          and '"status": "green"' in proc.stdout, proc.stderr + proc.stdout)

    w2 = World(tmp, "finalize-nodigest")
    human_merge_release_pr(w2)
    proc = w2.promo("finalize")
    check("finalize: missing artifact digests stop the run BEFORE any tag "
          "was pushed", proc.returncode == 1
          and "mrmap-backend" in proc.stderr
          and w2.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    w3 = World(tmp, "finalize-foreign-tag")
    human_merge_release_pr(w3)
    git("tag", "-a", "-m", "standing elsewhere", "v0.2.0", w3.base_sha,
        cwd=w3.clone)
    git("push", "-q", "origin", "refs/tags/v0.2.0", cwd=w3.clone)
    proc = w3.promo("finalize", *ARTIFACTS)
    check("finalize: a tag already standing on a foreign commit is a "
          "conflict; the tool never moves it", proc.returncode == 1
          and "never moves a tag" in proc.stderr
          and w3.remote_sha("refs/tags/v0.2.0^{}") == w3.base_sha,
          proc.stderr)

    w4 = World(tmp, "finalize-diverged")
    human_merge_release_pr(w4)
    (Path(w4.clone) / "late").write_text("hot on master\n", encoding="utf-8")
    git("add", "-A", cwd=w4.clone)
    git("commit", "-qm", "commit after the merge", cwd=w4.clone)
    git("push", "-q", "origin", "master", cwd=w4.clone)
    proc = w4.promo("finalize", *ARTIFACTS)
    check("finalize: a master whose tip tree diverged from the tested "
          "candidate tree refuses the release", proc.returncode == 1
          and "candidate's tree" in proc.stderr
          and w4.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)


def test_sync_and_status(tmp):
    w = World(tmp, "sync")
    proc = w.promo("sync")
    check("sync: while develop already contains master no sync PR is owed",
          proc.returncode == 0 and "no sync PR owed" in proc.stdout,
          proc.stderr)
    human_merge_release_pr(w)
    evidence_file(w, Path(w.dir) / "ev.json")
    rep = reports(w.dir)
    w.promo("preflight", "--evidence", str(Path(w.dir) / "ev.json"),
            "--report", f"api={rep['api']}",
            "--report", f"version={rep['version']}",
            "--report", f"upgrade={rep['upgrade']}",
            "--output", str(Path(w.dir) / "att.json"))
    w.promo("finalize", *ARTIFACTS)
    proc = w.promo("sync")
    opened = [c for c in w.journal_calls()
              if c[:2] == ["pr", "create"]
              and c[c.index("--base") + 1] == "develop"]
    check("sync: after the release the master -> develop sync PR is opened "
          "from a branch at master's tip", proc.returncode == 0
          and len(opened) == 1
          and w.remote_sha("refs/heads/master-sync-v0.2.0")
          == w.remote_sha("refs/heads/master"), proc.stderr + str(opened))
    proc = w.promo("sync")
    opened = [c for c in w.journal_calls()
              if c[:2] == ["pr", "create"]
              and c[c.index("--base") + 1] == "develop"]
    check("sync: re-running finds the open sync PR and stacks nothing",
          proc.returncode == 0 and "already open" in proc.stdout
          and len(opened) == 1, proc.stdout + proc.stderr)
    proc = w.promo("status")
    check("status: the reconcile view names every step and where it stands",
          proc.returncode == 0 and "at-master-tip" in proc.stdout
          and "github_release" in proc.stdout and "exists" in proc.stdout,
          proc.stdout + proc.stderr)
    proc = w.promo("gate", "--simulate")
    check("gate --simulate: the dry-run answer says simulated and touches "
          "no remote", proc.returncode == 0
          and '"simulated"' in proc.stdout
          and w.remote_sha("refs/tags/v0.2.0") is not None, proc.stdout)


def test_tool_shape(tmp):
    m = promo_module()
    check("tool: one SemVer grammar is shared with release_gates",
          m.SEMVER_RE is m.release_gates.SEMVER_RE)
    check("tool: the required image set is the one image_release publishes",
          m.REQUIRED_IMAGES == m.release_gates.REQUIRED_IMAGES,
          str(m.REQUIRED_IMAGES))


def main():
    tmp = tempfile.mkdtemp(prefix="test_release_promotion.",
                           dir=os.environ.get("TMPDIR", "/tmp"))
    tmp = Path(tmp)
    for fn in (
            test_plan_reads_a_planned_candidate,
            test_plan_refuses_unplanned_commits,
            test_evidence_binds_ci_to_the_candidate,
            test_preflight_is_the_one_promoter,
            test_open_release_pr_freezes_and_opens,
            test_finalize_before_and_after_the_merge,
            test_sync_and_status,
            test_tool_shape,
    ):
        try:
            fn(tmp)
        except Exception as exc:  # a broken world is a failed check, not a crash
            check(f"{fn.__name__} raised", False, repr(exc))
    failed = 0
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}"
              + (f"  [{detail[:400]}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
