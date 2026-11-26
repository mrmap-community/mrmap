#!/usr/bin/env python3
"""Offline checks for scripts/release_promotion.

Issue #1584 (epic #1577) landed the promotion; issue #1798 reconciled it with
the develop-first policy of AGENTS.md and with what Release Please actually
writes. This suite covers both, and runs without docker, without network and
without a GitHub token: the tool is driven against throw-away git repositories
whose "origin" is a local bare repository (the file transport the
migration-graph suite already uses), and every GitHub fact answers from a `gh`
shim that journals its calls to a file and keeps PRs and releases in a small
JSON state. No check here pretends to talk to GitHub; `--git-bin`/`--gh-bin` are
the same seams a real operator could point at a mirror, and the assertions read
what the tool actually sent through them.

The duty is the acceptance lines of #1584 plus the reconciliation of #1798, red
first. Each of these must be seen REFUSED, and refused BEFORE the tool touched
a tag or a release:

  * a candidate that was not planned - VERSION, its projection, the manifest or
    the release section of the changelog out of agreement;
  * a changelog written in the legacy `## [x] - date` shape and one written the
    way the planner of #1681 really writes it (`## [0.2.0](compare url)
    (2026-11-20)`) - both must be READ, and the prerelease heading of the same
    line must never answer for the stable version;
  * a release section whose subsections the planner's own config does not
    generate (a hand-edited generated section), and one that stays silent about
    the breaking changes its window contained;
  * evidence of another sha, a missing gate report, no attestation at all, an
    attestation of another sha or version, digests that are not the attested
    ones;
  * a release PR whose head is no longer the attested commit (STALE), a master
    that moved without any merged release PR, a master tip that is not a merge,
    a merge that does not carry the candidate, a tree that diverged;
  * anything that tries to be `gate --simulate` and reads as green.

Then the same worlds run the promotion to green, and every step is re-run to
prove the reconcile path ("already done" is a skip, never a duplicate).

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


# The release section of a planned release in the shape the planner of #1681
# really writes: a LINKED heading whose date sits in parentheses of its own.
# The compare URL names this repository's tags, which is what makes the heading
# recognisable as a generated one rather than a hand-written title.
COMPARE_URL = ("https://github.com/mrmap-community/mrmap/compare/"
               "v0.1.0...v{version}")
GENERATED_RELEASE_SECTION = (
    "## [{version}](" + COMPARE_URL + ") ({date})\n\n"
    "### Added\n\n* a reviewed feature ([1111111](u))\n\n"
    "### Fixed\n\n* a reviewed fix ([2222222](u))\n")
LEGACY_RELEASE_SECTION = "## [{version}] - {date}\n\n### Added\n\n- work\n"


def candidate_files(version, shape="generated", projection=None,
                    manifest=None, breaking_line=False, notes=False):
    """The five-file shape of a planned release, as path -> content.

    ``shape`` picks the changelog grammar under test: ``generated`` is what
    release-please writes today (#1681), ``legacy`` the hand-written
    ``## [x] - date`` of the existing history, ``none`` no release section at
    all. ``breaking_line`` adds the curated breaking marker and ``notes`` the
    curated Migration notes subsection, both of which a release section may
    carry beside the generated ones.
    """
    if shape == "none":
        section = ""
    else:
        template = (LEGACY_RELEASE_SECTION if shape == "legacy"
                    else GENERATED_RELEASE_SECTION)
        section = template.format(version=version, date="2026-11-20")
        if breaking_line:
            section += "\n**Breaking:** one API shape moved.\n"
        if notes:
            section += ("\n### Migration notes\n\n- notify.0007_a_new_column "
                        "records what it changes (#1798)\n")
    changelog = (
        "# Changelog\n\n"
        "## Unreleased\n\n"
        "Curated entries for changes without a classifiable carrier.\n\n"
        "### Added\n\n- curated, not yet released\n\n"
        + section)
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
    # Filter on whatever the caller named. The sync step names --head and
    # --base; the release-PR step names --base master alone and selects by
    # title itself, because the title is the identity of a release PR and its
    # head is develop, which carries every title at once.
    out = state["prs"]
    for name in ("--head", "--base"):
        value = flag(name)
        if value is not None:
            key = {"--head": "headRefName", "--base": "baseRefName"}[name]
            out = [p for p in out if p.get(key) == value]
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

    def __init__(self, tmp, name, with_candidate=True, shape="generated"):
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
        write_files(self.clone, candidate_files("0.1.0", shape="legacy"))
        git("add", "-A", cwd=self.clone)
        git("commit", "-qm", "base", cwd=self.clone)
        self.base_sha = git("rev-parse", "HEAD", cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/master", cwd=self.clone)
        if with_candidate:
            self.candidate_sha = self.add_candidate("0.2.0", shape=shape)
        else:
            self.candidate_sha = None

    def add_candidate(self, version, **kwargs):
        write_files(self.clone, candidate_files(version, **kwargs))
        return self.commit_and_push(f"release {version}")

    def commit_and_push(self, message):
        git("add", "-A", cwd=self.clone)
        git("commit", "-qm", message, cwd=self.clone)
        git("push", "-q", "origin", "HEAD:refs/heads/develop", cwd=self.clone)
        return git("rev-parse", "HEAD", cwd=self.clone)

    def advance_develop(self, name="later"):
        """A commit lands on develop AFTER the candidate was reviewed."""
        name = name.replace(" ", "_")
        (Path(self.clone) / f"{name}.txt").write_text("a later commit\n",
                                                      encoding="utf-8")
        return self.commit_and_push(f"chore: {name}")

    def edit(self, rel, new_text):
        write_files(self.clone, {rel: new_text})
        return self.commit_and_push(f"edit {rel}")

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

    def changelog(self):
        return (Path(self.clone) / "CHANGELOG.md").read_text(encoding="utf-8")

    def gh_state(self):
        return json.loads(self.state.read_text(encoding="utf-8"))

    def set_pr_state(self, number, state):
        """What a person does on GitHub, simulated in the shim's state."""
        doc = self.gh_state()
        for pr in doc["prs"]:
            if pr["number"] == number:
                pr["state"] = state
        self.state.write_text(json.dumps(doc), encoding="utf-8")

    def release_prs(self, title):
        return [pr for pr in self.gh_state()["prs"]
                if pr["baseRefName"] == "master" and pr["title"] == title]

    def promo(self, *argv):
        env = dict(GIT_ENV, GH_STATE=str(self.state),
                   GH_JOURNAL=str(self.journal))
        cmd = [sys.executable, str(PROMO), "--root", str(self.clone),
               "--gh-bin", str(self.gh), *argv]
        return subprocess.run(cmd, capture_output=True, text=True, env=env)


def reports(tmpdir, version="0.2.0", breaking=0, tag=""):
    """Synthetic gate reports in the shape release_gates promote reads."""
    paths = {}
    base = Path(tmpdir)
    for name, extra in (("api", {}),
                        ("version", {"candidate_version": version,
                                     "breaking": breaking}),
                        ("upgrade", {})):
        path = base / f"{name}-report-{version}-{breaking}-{tag}.json"
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


def tip_of(world):
    return world.remote_sha("refs/heads/develop") or world.candidate_sha


def evidence_file(world, path, sha=None):
    # The promoter refuses evidence of another build, so evidence and
    # attestation must always name the same commit - the current tip of
    # develop, which is what a world's edit just moved.
    checks = Path(str(path) + ".checks.json")
    checks.write_text(json.dumps(GREEN_CHECKS), encoding="utf-8")
    return world.promo("evidence", "--sha", sha or tip_of(world),
                       "--checks-file", str(checks),
                       "--manual", "dependencies=https://deps.test/audit",
                       *ARTIFACTS, "--output", str(path))


def preflight(world, ev, rep, sha=None, output=None):
    # A world that edited its changelog changed develop's tip; attestation and
    # evidence must speak about THAT commit, not the one the world was built
    # with.
    return world.promo("preflight", "--sha", sha or tip_of(world),
                       "--evidence", str(ev),
                       "--report", f"api={rep['api']}",
                       "--report", f"version={rep['version']}",
                       "--report", f"upgrade={rep['upgrade']}",
                       "--actor", "suite",
                       *(["--output", str(output)] if output else []))


def attest(world, version="0.2.0", sha=None, breaking=0, tag="att"):
    """Drive evidence + preflight for a world and return its attestation.

    That file is the reviewed candidate identity every later step reads; a
    scenario that wants to publish without it must pass no file at all rather
    than an empty one.
    """
    sha = sha or tip_of(world)
    ev = Path(world.dir) / f"evidence-{tag}.json"
    proc = evidence_file(world, ev, sha=sha)
    if proc.returncode != 0:
        raise RuntimeError(f"evidence failed: {proc.stderr}")
    rep = reports(world.dir, version=version, breaking=breaking, tag=tag)
    att = Path(world.dir) / f"attestation-{tag}.json"
    proc = preflight(world, ev, rep, sha=sha, output=att)
    if proc.returncode != 0:
        raise RuntimeError(f"preflight failed: {proc.stderr}{proc.stdout}")
    return att


def record_merged_release_pr(world, title="chore: release v0.2.0"):
    """A release PR that exists on GitHub already MERGED, in the shim state."""
    doc = world.gh_state()
    number = 100 + len(doc["prs"]) + 1
    doc["prs"].append({"number": number, "state": "MERGED",
                       "headRefName": "develop", "baseRefName": "master",
                       "title": title})
    world.state.write_text(json.dumps(doc), encoding="utf-8")
    return number


def human_merge_release_pr(world, sha=None, title="chore: release v0.2.0",
                           with_pr=True):
    """What the acceptance criteria reserve to people, simulated with plain git
    plus one state write. GitHub lands a release PR as a merge commit on master
    whose second parent is the head the PR carried.

    ``with_pr=False`` is the world where master moved WITHOUT a release PR -
    the situation finalize must refuse, because a merge commit on master is not
    by itself evidence that a person reviewed a release."""
    git("fetch", "-q", "origin", cwd=world.clone)
    git("checkout", "-q", "-B", "master", "origin/master", cwd=world.clone)
    git("merge", "--no-ff", "-m", "Merge pull request from develop",
        sha or world.candidate_sha, cwd=world.clone)
    git("push", "-q", "origin", "master", cwd=world.clone)
    prs = world.release_prs(title)
    if not prs and with_pr:
        # worlds that test finalize without the open step still owe a merged
        # release PR - that is the reviewed act finalize publishes on.
        doc = world.gh_state()
        number = 100 + len(doc["prs"]) + 1
        doc["prs"].append({"number": number, "state": "OPEN",
                           "headRefName": "develop",
                           "baseRefName": "master", "title": title})
        world.state.write_text(json.dumps(doc), encoding="utf-8")
        prs = world.release_prs(title)
    for pr in prs:
        world.set_pr_state(pr["number"], "MERGED")
    return git("rev-parse", "master", cwd=world.clone)


# ------------------------------------------------------------------ the checks


def test_plan_reads_a_planned_candidate(tmp):
    w = World(tmp, "plan-ok")
    proc = w.promo("plan")
    check("plan: a planned candidate is read with its version and steps",
          proc.returncode == 0
          and "planned 0.2.0 release" in proc.stdout
          and "changelog: ## [0.2.0]" in proc.stdout
          and "manifest: 0.2.0" in proc.stdout
          and "IS origin/develop" in proc.stdout, proc.stderr)


def test_changelog_grammars(tmp):
    """#1798's matcher bug, pinned from both sides.

    Before #1798 the matcher asked only for `## [version] - date`, the legacy
    shape, so every heading the planner of #1681 generates was refused as "no
    folded release section" - the promotion could never have run against a real
    planned release. Both grammars must be read, and the version inside them
    must be matched exactly and bounded.
    """
    m = promo_module()
    generated = ("## [0.2.0](" + COMPARE_URL.format(version="0.2.0")
                 + ") (2026-11-20)\n\n### Added\n\n* work\n")
    legacy = "## [0.1.0] - 2023-03-23\n\n### Added\n\n- work\n"
    both = generated + "\n" + legacy
    check("changelog: the linked heading the planner of #1681 writes is read",
          m.find_release_section(both, "0.2.0")[0] is not None,
          str(m.find_release_section(both, "0.2.0")))
    check("changelog: the legacy `## [x] - date` heading is still read",
          m.find_release_section(both, "0.1.0")[0] is not None,
          str(m.find_release_section(both, "0.1.0")))
    check("changelog: a heading is matched EXACTLY - 0.2.10 is not 0.2.0",
          m.find_release_section(both.replace("[0.2.0]", "[0.2.10]"),
                                 "0.2.0")[0] is None)
    check("changelog: the prerelease of the line is not the stable version",
          m.find_release_section(
              both.replace("[0.2.0](", "[0.2.0-rc.1]("), "0.2.0")[0] is None)
    check("changelog: the curated `## Unreleased` heading is never a release",
          m.find_release_section(both, "Unreleased")[0] is None
          and "Unreleased" not in [v for v, _ in m.release_headings(both)])
    check("changelog: an undated heading is not a generated release section",
          m.find_release_section("## [0.3.0] hand written\n\n### Added\n",
                                 "0.3.0")[0] is None)

    w = World(tmp, "changelog-generated", shape="generated")
    proc = w.promo("plan")
    check("plan: a generated linked release section makes a planned candidate",
          proc.returncode == 0 and "planned 0.2.0 release" in proc.stdout,
          proc.stderr + proc.stdout)
    w2 = World(tmp, "changelog-legacy", shape="legacy")
    proc = w2.promo("plan")
    check("plan: a legacy dated release section makes a planned candidate too",
          proc.returncode == 0 and "planned 0.2.0 release" in proc.stdout,
          proc.stderr + proc.stdout)
    w3 = World(tmp, "changelog-rc-only", with_candidate=False)
    sha = w3.add_candidate("0.2.0", shape="none")
    w3.edit("CHANGELOG.md", w3.changelog().replace(
        "## Unreleased",
        "## [0.2.0-rc.1](" + COMPARE_URL.format(version="0.2.0-rc.1")
        + ") (2026-11-19)\n\n### Added\n\n* rc\n\n## Unreleased", 1))
    proc = w3.promo("plan", "--sha", sha)
    check("plan: the prerelease heading of the line does not make the stable "
          "version a planned candidate",
          proc.returncode == 1 and "0.2.0" in proc.stderr, proc.stderr)


def test_generated_notes_are_verified(tmp):
    """The generated notes must stay generated, and must name what broke."""
    w = World(tmp, "notes-handedit", shape="generated")
    ev = Path(w.dir) / "ev-handedit.json"
    check("preflight: fixture evidence for a clean candidate builds",
          evidence_file(w, ev).returncode == 0)
    rep = reports(w.dir, tag="hand")
    w.edit("CHANGELOG.md", w.changelog().replace("### Fixed",
                                                 "### Handwritten things"))
    proc = preflight(w, ev, rep)
    check("preflight: a subsection the planner does not generate is refused",
          proc.returncode == 1
          and "never hand-edited" in proc.stderr + proc.stdout,
          proc.stderr + proc.stdout)

    w2 = World(tmp, "notes-curated", shape="generated")
    w2.edit("CHANGELOG.md", w2.changelog().replace(
        "### Fixed", "### Migration notes\n\n- run migrate\n\n### Fixed"))
    ev2 = Path(w2.dir) / "ev-curated.json"
    evidence_file(w2, ev2)
    rep2 = reports(w2.dir, tag="curated")
    proc = preflight(w2, ev2, rep2,
                     output=Path(w2.dir) / "att-curated.json")
    check("preflight: the curated Migration notes subsection survives",
          proc.returncode == 0, proc.stderr + proc.stdout)

    # The documented bang-title gap: what the gate counted, the notes must name.
    w3 = World(tmp, "notes-breaking", shape="generated")
    ev3 = Path(w3.dir) / "ev-breaking.json"
    evidence_file(w3, ev3)
    rep3 = reports(w3.dir, breaking=2, tag="brk")
    proc = preflight(w3, ev3, rep3)
    check("preflight: breaking changes the window contained but the release "
          "section never names are refused (the bang-title gap)",
          proc.returncode == 1
          and "breaking" in (proc.stderr + proc.stdout).lower(),
          proc.stderr + proc.stdout)
    rep4 = reports(w3.dir, breaking=0, tag="brk-ok")
    proc = preflight(w3, ev3, rep4, output=Path(w3.dir) / "att-brk-ok.json")
    check("preflight: the same section is attested when nothing broke",
          proc.returncode == 0, proc.stderr + proc.stdout)

    w4 = World(tmp, "notes-breaking-generated", shape="generated")
    w4.edit("CHANGELOG.md", w4.changelog().replace(
        "### Fixed",
        "### \u26a0 BREAKING CHANGES\n\n* one API shape moved\n\n### Fixed"))
    ev4 = Path(w4.dir) / "ev-brk-gen.json"
    evidence_file(w4, ev4)
    rep5 = reports(w4.dir, breaking=2, tag="brkgen")
    proc = preflight(w4, ev4, rep5, output=Path(w4.dir) / "att-brk-gen.json")
    check("preflight: the generated breaking section satisfies the demand",
          proc.returncode == 0, proc.stderr + proc.stdout)

    w5 = World(tmp, "notes-breaking-curated", shape="generated")
    w5.edit("CHANGELOG.md", w5.changelog().replace(
        "### Fixed",
        "### Fixed\n\n* a reviewed fix ([2222222](u))\n\n"
        "**Breaking:** one API shape moved."))
    ev5 = Path(w5.dir) / "ev-brk-curated.json"
    evidence_file(w5, ev5)
    rep6 = reports(w5.dir, breaking=1, tag="brkcur")
    proc = preflight(w5, ev5, rep6, output=Path(w5.dir) / "att-brk-cur.json")
    check("preflight: the curated **Breaking:** line satisfies the demand too",
          proc.returncode == 0, proc.stderr + proc.stdout)


def test_plan_refuses_unplanned_commits(tmp):
    w = World(tmp, "plan-changelog", with_candidate=False)
    sloppy = w.add_candidate("0.3.0", shape="none")
    proc = w.promo("plan", "--sha", sloppy)
    check("plan: a VERSION move without its release section is refused",
          proc.returncode == 1 and "CHANGELOG.md" in proc.stderr,
          proc.stderr + proc.stdout)

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
    git("commit", "-qm", "a commit develop never got", cwd=w4.clone)
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
    rep = reports(w.dir, tag="one")
    att = Path(w.dir) / "attestation.json"
    proc = preflight(w, ev, rep, output=att)
    text = att.read_text(encoding="utf-8") if att.exists() else ""
    check("preflight: release_gates promote is the attester and its shape "
          "survives", proc.returncode == 0
          and '"mrmap-release-candidate/1"' in text
          and w.candidate_sha in text and '"0.2.0"' in text
          and BACKEND in text, proc.stderr)

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


def test_open_release_pr_is_develop_to_master(tmp):
    """#1798: develop is the only head branch-policy.yml admits onto master.

    Before #1798 the tool pushed `release/v<version>` and opened that onto
    master, which .github/workflows/branch-policy.yml refuses on sight - the
    promotion had no mergeable shape at all. It now opens develop -> master and
    the reviewed identity lives in the attestation instead of in a ref, so
    nothing needs freezing and no permanent branch is written.
    """
    w = World(tmp, "open-pr")
    att = attest(w)
    proc = w.promo("open-release-pr", "--attestation", str(att))
    created = [c for c in w.journal_calls() if c[:2] == ["pr", "create"]]
    check("open-release-pr: the PR is develop -> master and named for the "
          "version", proc.returncode == 0
          and len(created) == 1
          and created[0][created[0].index("--base") + 1] == "master"
          and created[0][created[0].index("--head") + 1] == "develop"
          and created[0][created[0].index("--title") + 1]
          == "chore: release v0.2.0", proc.stderr + str(created))
    check("open-release-pr: the promotion writes no release branch at all",
          w.remote_sha("refs/heads/release/v0.2.0") is None
          and all(r["headRefName"] == "develop"
                  for r in w.gh_state()["prs"]),
          str([r["headRefName"] for r in w.gh_state()["prs"]]))
    body = created[0][created[0].index("--body") + 1]
    check("open-release-pr: the body quotes the exact reviewed candidate",
          w.candidate_sha in body and "mrmap-release-candidate/1" in body,
          body[:200])
    proc = w.promo("open-release-pr", "--attestation", str(att))
    created = [c for c in w.journal_calls() if c[:2] == ["pr", "create"]]
    check("open-release-pr: re-running finds the open PR and opens nothing "
          "twice", proc.returncode == 0 and "already open" in proc.stdout
          and len(created) == 1, proc.stdout + proc.stderr)

    w2 = World(tmp, "open-pr-noatt")
    proc = w2.promo("open-release-pr")
    check("open-release-pr: without an attestation nothing is opened",
          proc.returncode == 1 and "no attestation" in proc.stderr.lower()
          and not [c for c in w2.journal_calls()
                   if c[:2] == ["pr", "create"]], proc.stderr)

    # an attestation of another commit is not this candidate's identity
    w3 = World(tmp, "open-pr-wrongatt")
    doc = json.loads(attest(w3).read_text(encoding="utf-8"))
    doc["candidate"]["sha"] = w3.base_sha
    forged = Path(w3.dir) / "attestation-forged.json"
    forged.write_text(json.dumps(doc), encoding="utf-8")
    proc = w3.promo("open-release-pr", "--sha", w3.base_sha,
                    "--attestation", str(forged))
    check("open-release-pr: an attestation for another sha is refused",
          proc.returncode == 1, proc.stderr)

    w4 = World(tmp, "open-pr-wongschema")
    bogus = Path(w4.dir) / "attestation-bogus.json"
    bogus.write_text(json.dumps({"attestation": "something-else/1",
                                 "candidate": {"sha": w4.candidate_sha,
                                               "version": "0.2.0"}}),
                     encoding="utf-8")
    proc = w4.promo("open-release-pr", "--attestation", str(bogus))
    check("open-release-pr: a file that is not the promoter's schema is "
          "refused, not trusted", proc.returncode == 1
          and "mrmap-release-candidate/1" in proc.stderr, proc.stderr)


def test_stale_candidate_is_invalidated(tmp):
    """#1798: develop keeps moving, and a moved-past candidate is not a candidate.

    The head of a develop -> master PR IS develop, so the shape #1584 shipped
    could quietly merge commits nobody judged. The answer is not to re-anchor
    the PR behind the review: the candidate is invalidated and the new tip owes
    its own evidence and attestation.
    """
    w = World(tmp, "stale-open")
    att = attest(w)
    w.advance_develop("a commit nobody reviewed")
    proc = w.promo("open-release-pr", "--attestation", str(att))
    check("open-release-pr: develop advancing past the attested candidate "
          "refuses the PR", proc.returncode == 1
          and "no longer develop's tip" in proc.stderr
          and not [c for c in w.journal_calls() if c[:2] == ["pr", "create"]],
          proc.stderr)

    w2 = World(tmp, "stale-head")
    att = attest(w2)
    w2.promo("open-release-pr", "--attestation", str(att))
    tip = w2.advance_develop("a merge nobody judged for this release")
    proc = w2.promo("open-release-pr", "--attestation", str(att))
    check("open-release-pr: an open release PR whose head moved is STALE, "
          "not open", proc.returncode == 1 and "STALE" in proc.stderr,
          proc.stderr + proc.stdout)
    proc = w2.promo("status", "--attestation", str(att))
    view = {}
    for line in proc.stdout.splitlines()[1:]:
        parts = line.strip().split(None, 1)
        if len(parts) == 2:
            view[parts[0]] = parts[1]
    check("status: the reconcile view names the stale head and the lost tip",
          proc.returncode == 0 and view.get("release_pr_head", "").startswith(
              "stale@") and view.get("candidate_is_tip") == "False"
          and view.get("release_pr") == "open", proc.stdout)
    proc = w2.promo("finalize", "--attestation", str(att), *ARTIFACTS)
    check("finalize: the stale candidate cannot publish either",
          proc.returncode == 1
          and w2.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    # the new tip can still be promoted - by re-attesting, never by re-anchoring
    att2 = attest(w2, sha=tip, tag="tip")
    proc = w2.promo("open-release-pr", "--attestation", str(att2))
    check("open-release-pr: re-attesting the new tip is the way forward",
          proc.returncode == 0 and "already open" in proc.stdout,
          proc.stderr + proc.stdout)


def test_finalize_before_and_after_the_merge(tmp):
    w = World(tmp, "finalize")
    att = attest(w)
    proc = w.promo("finalize", "--attestation", str(att), *ARTIFACTS)
    check("finalize: before a person merged, publishing is refused",
          proc.returncode == 1 and "no MERGED release PR" in proc.stderr,
          proc.stderr)

    proc = w.promo("finalize", "--alias", "latest", "--attestation", str(att),
                   *ARTIFACTS)
    check("finalize: rolling aliases stay refused while Q1 of #1578 is "
          "Pending", proc.returncode == 1 and "alias" in proc.stderr.lower(),
          proc.stderr)

    w_nopr = World(tmp, "finalize-nopr")
    att_nopr = attest(w_nopr)
    human_merge_release_pr(w_nopr, with_pr=False)
    proc = w_nopr.promo("finalize", "--attestation", str(att_nopr), *ARTIFACTS)
    check("finalize: a master that moved without a MERGED release PR is "
          "refused - a merge commit alone is not a reviewed act",
          proc.returncode == 1 and "no MERGED release PR" in proc.stderr
          and w_nopr.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    tip = human_merge_release_pr(w)
    proc = w.promo("finalize", "--attestation", str(att), *ARTIFACTS)
    tagged = w.remote_sha("refs/tags/v0.2.0")
    released = [c for c in w.journal_calls()
                if c[:2] == ["release", "create"]]
    check("finalize: after the reviewed merge the tree check passes, the "
          "annotated tag stands on master's tip and the release is published",
          proc.returncode == 0 and tagged is not None
          and w.remote_sha("refs/tags/v0.2.0^{}") == tip
          and len(released) == 1, proc.stderr + str(released))
    notes = released[0][released[0].index("--notes") + 1]
    check("finalize: the release body carries the candidate, both digests and "
          "the attestation itself", w.candidate_sha in notes
          and BACKEND in notes and FRONTEND in notes
          and "mrmap-release-candidate/1" in notes, notes[:300])

    proc = w.promo("finalize", "--attestation", str(att), *ARTIFACTS)
    released = [c for c in w.journal_calls()
                if c[:2] == ["release", "create"]]
    check("finalize: re-running skips the tag and leaves the release body "
          "untouched - nothing is published twice", proc.returncode == 0
          and "already at the expected commit" in proc.stdout
          and "already exists" in proc.stdout and len(released) == 1,
          proc.stdout + proc.stderr)

    proc = w.promo("finalize", "--attestation", str(att),
                   "--artifact=mrmap-backend=nonsense",
                   "--artifact=mrmap-frontend=" + FRONTEND)
    check("finalize: a digest that is not sha256:<64 hex> is refused",
          proc.returncode == 1 and "sha256:" in proc.stderr, proc.stderr)

    proc = w.promo("gate", "--attestation", str(att))
    check("gate: with attestation, merged PR, tag, release and equal trees "
          "the promotion answers green", proc.returncode == 0
          and '"status": "green"' in proc.stdout
          and BACKEND in proc.stdout, proc.stderr + proc.stdout)

    proc = w.promo("gate")
    check("gate: without the attestation the gate cannot be green",
          proc.returncode == 1 and "no attestation" in proc.stderr.lower(),
          proc.stderr)

    proc = w.promo("gate", "--simulate")
    check("gate --simulate: a dry-run answer says simulated and can never "
          "read as green", proc.returncode == 0 and '"simulated"' in proc.stdout
          and '"green": false' in proc.stdout
          and '"status": "green"' not in proc.stdout, proc.stdout)

    w2 = World(tmp, "finalize-nodigest")
    att2 = attest(w2)
    human_merge_release_pr(w2)
    proc = w2.promo("finalize", "--attestation", str(att2))
    check("finalize: missing artifact digests stop the run BEFORE any tag "
          "was pushed", proc.returncode == 1
          and "mrmap-backend" in proc.stderr
          and w2.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    w3 = World(tmp, "finalize-foreign-tag")
    att3 = attest(w3)
    human_merge_release_pr(w3)
    git("tag", "-a", "-m", "standing elsewhere", "v0.2.0", w3.base_sha,
        cwd=w3.clone)
    git("push", "-q", "origin", "refs/tags/v0.2.0", cwd=w3.clone)
    proc = w3.promo("finalize", "--attestation", str(att3), *ARTIFACTS)
    check("finalize: a tag already standing on a foreign commit is a "
          "conflict; the tool never moves it", proc.returncode == 1
          and "never moves a tag" in proc.stderr
          and w3.remote_sha("refs/tags/v0.2.0^{}") == w3.base_sha,
          proc.stderr)

    w4 = World(tmp, "finalize-diverged")
    att4 = attest(w4)
    # master carries something of its own, so the reviewed merge lands a tree
    # that is NOT the tested candidate tree - exactly what must stop a release.
    git("fetch", "-q", "origin", cwd=w4.clone)
    git("checkout", "-q", "-B", "master", "origin/master", cwd=w4.clone)
    (Path(w4.clone) / "only-on-master").write_text("not in the candidate\n",
                                                   encoding="utf-8")
    git("add", "-A", cwd=w4.clone)
    git("commit", "-qm", "content master carries on its own", cwd=w4.clone)
    git("push", "-q", "origin", "master", cwd=w4.clone)
    git("checkout", "-q", "develop", cwd=w4.clone)
    human_merge_release_pr(w4)
    proc = w4.promo("finalize", "--attestation", str(att4), *ARTIFACTS)
    check("finalize: a master whose tip tree diverged from the tested "
          "candidate tree refuses the release", proc.returncode == 1
          and "candidate's tree" in proc.stderr
          and w4.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    w5 = World(tmp, "finalize-squash")
    att5 = attest(w5)
    git("fetch", "-q", "origin", cwd=w5.clone)
    git("checkout", "-q", "-B", "master", "origin/master", cwd=w5.clone)
    git("cherry-pick", w5.candidate_sha, cwd=w5.clone)
    git("push", "-q", "origin", "master", cwd=w5.clone)
    record_merged_release_pr(w5)
    proc = w5.promo("finalize", "--attestation", str(att5), *ARTIFACTS)
    check("finalize: a master tip that is not the reviewed MERGE commit (a "
          "direct push or a squash) is refused", proc.returncode == 1
          and "not a merge commit" in proc.stderr
          and w5.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)


def test_attested_digests_are_the_published_ones(tmp):
    """The attestation is the contract between the build and the release."""
    w = World(tmp, "digest-mismatch")
    att = attest(w)
    human_merge_release_pr(w)
    other = "sha256:" + "c" * 64
    proc = w.promo("finalize", "--attestation", str(att),
                   "--artifact=mrmap-backend=" + other,
                   "--artifact=mrmap-frontend=" + FRONTEND)
    check("finalize: a digest that is not the attested one is refused before "
          "any tag", proc.returncode == 1
          and "not the attested" in proc.stderr
          and w.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    proc = w.promo("finalize", "--attestation", str(att),
                   "--artifact=mrmap-backend=" + BACKEND)
    check("finalize: publishing fewer digests than were attested is refused",
          proc.returncode == 1
          and ("not the attested" in proc.stderr
               or "was not supplied" in proc.stderr)
          and w.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)

    doc = json.loads(att.read_text(encoding="utf-8"))
    doc["candidate"]["version"] = "9.9.9"
    forged = Path(w.dir) / "attestation-wrongversion.json"
    forged.write_text(json.dumps(doc), encoding="utf-8")
    proc = w.promo("finalize", "--attestation", str(forged), *ARTIFACTS)
    check("finalize: an attestation whose version differs from the "
          "candidate's is refused", proc.returncode == 1
          and "version" in proc.stderr
          and w.remote_sha("refs/tags/v0.2.0") is None, proc.stderr)


def test_sync_and_status(tmp):
    w = World(tmp, "sync")
    proc = w.promo("sync")
    check("sync: while develop already contains master no sync PR is owed",
          proc.returncode == 0 and "no sync PR owed" in proc.stdout,
          proc.stderr)
    att = attest(w)
    w.promo("open-release-pr", "--attestation", str(att))
    human_merge_release_pr(w)
    w.promo("finalize", "--attestation", str(att), *ARTIFACTS)
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
          and "github_release" in proc.stdout and "exists" in proc.stdout
          and "master_tree_matches_candidate" in proc.stdout
          and "release_pr_head" in proc.stdout
          and "candidate" in proc.stdout, proc.stdout + proc.stderr)


def test_two_promotions_of_one_version(tmp):
    """Two runs that both believe they hold the release of one version.

    There is no frozen branch to fight over any more, so what can collide is the
    pull request (exactly one per version, whichever run got there first) and
    the tag. The reviewed candidate is the attestation, so the run whose
    attestation names a commit develop no longer carries is the one refused -
    invalidated, not overridden - and nothing publishes twice.
    """
    w = World(tmp, "concurrent")
    att = attest(w)
    proc = w.promo("open-release-pr", "--attestation", str(att))
    check("concurrent: the first promotion opens the release PR",
          proc.returncode == 0, proc.stderr)
    rival = w.advance_develop("a rival attempt at the same version")
    rival_att = attest(w, sha=rival, tag="rival")
    proc = w.promo("open-release-pr", "--attestation", str(rival_att))
    created = [c for c in w.journal_calls() if c[:2] == ["pr", "create"]]
    check("concurrent: a rival promotion of one version opens no second PR",
          proc.returncode == 0 and len(created) == 1
          and "already open" in proc.stdout, proc.stderr + str(created))
    # the run whose candidate develop no longer carries is the refused one
    proc = w.promo("open-release-pr", "--attestation", str(att))
    check("concurrent: the invalidated run is refused, not obeyed",
          proc.returncode == 1 and "STALE" in proc.stderr, proc.stderr)
    human_merge_release_pr(w, sha=rival)
    proc = w.promo("finalize", "--attestation", str(rival_att), *ARTIFACTS)
    check("concurrent: the promotion completes on the candidate that is "
          "really tip", proc.returncode == 0
          and w.remote_sha("refs/tags/v0.2.0^{}")
          == w.remote_sha("refs/heads/master"), proc.stderr)
    # the invalidated attestation cannot republish over the standing tag
    proc = w.promo("finalize", "--attestation", str(att), *ARTIFACTS)
    check("concurrent: the invalidated attestation cannot publish anything",
          proc.returncode == 1
          and w.remote_sha("refs/tags/v0.2.0^{}")
          == w.remote_sha("refs/heads/master"), proc.stderr)
    releases = [c for c in w.journal_calls() if c[:2] == ["release", "create"]]
    check("concurrent: one version, one release, whatever the number of runs",
          len(releases) == 1, str(releases))


def test_tool_shape(tmp):
    m = promo_module()
    check("tool: one SemVer grammar is shared with release_gates",
          m.SEMVER_RE is m.release_gates.SEMVER_RE)
    check("tool: the required image set is the one release_gates requires",
          m.REQUIRED_IMAGES == m.release_gates.REQUIRED_IMAGES,
          str(m.REQUIRED_IMAGES))
    check("tool: the reviewed identity is the promoter's schema, named once",
          m.ATTESTATION_SCHEMA == "mrmap-release-candidate/1"
          and m.RELEASE_PR_TITLE.format(version="0.2.0")
          == "chore: release v0.2.0")
    check("tool: the planner's own config is the contract for generated notes",
          m.generated_subsection_names() is not None
          and {"Added", "Fixed", "Changed"} <= m.generated_subsection_names(),
          str(m.generated_subsection_names()))
    source = PROMO.read_text(encoding="utf-8")
    check("tool: no step pushes a release branch any more",
          "refs/heads/release/" not in source
          and 'f"release/v{version}"' not in source,
          "a release branch ref remains")


def main():
    tmp = tempfile.mkdtemp(prefix="test_release_promotion.",
                           dir=os.environ.get("TMPDIR", "/tmp"))
    tmp = Path(tmp)
    for fn in (
            test_plan_reads_a_planned_candidate,
            test_changelog_grammars,
            test_generated_notes_are_verified,
            test_plan_refuses_unplanned_commits,
            test_evidence_binds_ci_to_the_candidate,
            test_preflight_is_the_one_promoter,
            test_open_release_pr_is_develop_to_master,
            test_stale_candidate_is_invalidated,
            test_finalize_before_and_after_the_merge,
            test_attested_digests_are_the_published_ones,
            test_sync_and_status,
            test_two_promotions_of_one_version,
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
