#!/usr/bin/env python3
"""Offline checks for scripts/docs_publish (issue #1608, epic #1589).

Runs without docker, without network and without a GitHub token. The tool is
driven against throw-away git repositories whose "origin" is a local bare
repository (the file transport the migration-graph and promotion suites
already use), the Pages branch is a ref inside that bare repository, and every
GitHub fact answers from a ``gh`` shim that journals its calls and serves
artifacts from a directory the test wrote. No check pretends to talk to GitHub:
the assertions read what actually landed in the Pages branch of the fake
remote, and every refused case is asserted BEFORE anything was written.

The duty of this suite is the acceptance criteria of #1608, red first:

* candidate/stable isolation      - the same artifact published to ``/develop/``
                                    and to ``/stable/`` stays separate, and a
                                    stable promotion never rewrites the develop
                                    preview or an older version directory;
* failed publication loses no docs - a refusal, a wrong-sha artifact, a failed
                                    gate report, a moved Pages branch and a
                                    tampered download each leave the previously
                                    published revision byte-identical (gate
                                    V-17's negative case);
* immutability                    - a second artifact for a standing version
                                    directory is refused, and the bytes of a
                                    published version never change;
* verified reuse only on match    - an identical candidate reruns as a skip
                                    that writes nothing, while a locale edit, a
                                    lockfile edit or a generator edit moves the
                                    reuse key and forces a new publication;
* no source writes, least privilege - the real working tree of the repository
                                    is unchanged by every subcommand, and the
                                    Pages object store is bare, so nothing in
                                    the tool can hold a force-push.

Run from the repository root: ``python3 scripts/test_docs_publish.py``.
Exit 0 when every check passes, 1 with the failed ones listed.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "docs_publish.py"
REPO = HERE.parent
MARKER = ".docs-version.json"

RESULTS = []
SKIPPED = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def skip(name, reason):
    SKIPPED.append((name, reason))


GIT_ENV = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null",
               GIT_CONFIG_SYSTEM="/dev/null", GIT_TERMINAL_PROMPT="0",
               LC_ALL="C")


def git(*argv, cwd=None):
    proc = subprocess.run(["git", *argv], cwd=str(cwd) if cwd else None,
                          env=GIT_ENV, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)}: {proc.stderr.strip()}")
    return proc.stdout.strip()


GH_SHIM = '''#!/usr/bin/env python3
"""Journal every gh call; answer artifact downloads from a directory tree.

Only the two calls docs_publish makes are implemented. A download is a copy of
<GH_ARTIFACTS>/<run>/<name>/ into --dir, which is what `gh run download` does;
an unknown run or name fails, the way the real one does.
"""
import json, os, shutil, sys

argv = sys.argv[1:]
with open(os.environ["GH_JOURNAL"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")

def flag(name):
    return argv[argv.index(name) + 1] if name in argv else None

if argv[:2] == ["run", "download"]:
    run, name, dest = argv[2], flag("--name"), flag("--dir")
    src = os.path.join(os.environ["GH_ARTIFACTS"], run, name)
    if not os.path.isdir(src):
        sys.stderr.write("could not download any artifacts\\n")
        sys.exit(1)
    os.makedirs(dest, exist_ok=True)
    for entry in os.listdir(src):
        target = os.path.join(dest, entry)
        if os.path.isdir(os.path.join(src, entry)):
            shutil.copytree(os.path.join(src, entry), target, dirs_exist_ok=True)
        else:
            shutil.copy(os.path.join(src, entry), target)
    sys.exit(0)

sys.stderr.write("gh shim: unsupported call %r\\n" % (argv,))
sys.exit(2)
'''


BOOTSTRAP_SUBJECT = "docs-pages: bootstrap the documentation portal"


def sha256_bytes(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


CANDIDATE_FILES = {
    "VERSION": "1.2.3\n",
    "backend/.requirements/base.txt": "django==5.2\n",
    "backend/.requirements/requirements.txt": "gunicorn==23.0.0\n",
    "backend/.requirements/docs.txt": "sphinx==8.2.3\n",
    "frontend/package-lock.json": '{"name":"mrmap","lockfileVersion":3}\n',
    "scripts/gen_docs_design.py": "# generator v1\n",
}


class World:
    """One fake origin, one candidate commit, one Pages object store."""

    def __init__(self, keep=False):
        self.tmp = Path(tempfile.mkdtemp(prefix="mrmap-docs-publish-"))
        self.origin = self.tmp / "origin.git"
        self.work = self.tmp / "work"
        self.artifacts = self.tmp / "artifacts"
        self.pages_dir = self.tmp / "pages.git"
        self.journal = self.tmp / "gh-journal.jsonl"
        self.shim = self.tmp / "gh"
        self.keep = keep
        self._build_origin()
        self._build_shim()

    # -- the remote ----------------------------------------------------------
    def _build_origin(self):
        self.origin.mkdir(parents=True)
        git("init", "-q", "--bare", str(self.origin))
        self.work.mkdir()
        git("init", "-q", str(self.work))
        git("config", "user.name", "Test Author", cwd=self.work)
        git("config", "user.email", "test@example.invalid", cwd=self.work)
        self.write(CANDIDATE_FILES)
        git("add", "-A", cwd=self.work)
        git("commit", "-q", "-m", "candidate content", cwd=self.work)
        git("branch", "-M", "develop", cwd=self.work)
        git("remote", "add", "origin", str(self.origin), cwd=self.work)
        git("push", "-q", "origin", "develop", cwd=self.work)
        git("push", "-q", "origin", f"develop:master", cwd=self.work)
        self.develop = git("rev-parse", "develop", cwd=self.work)

    def write(self, files):
        for rel, content in files.items():
            path = self.work / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def amend_candidate(self, files):
        """Move develop to a new candidate commit and return its sha."""
        self.write(files)
        git("add", "-A", cwd=self.work)
        # --allow-empty: an input the key reads need not change any build
        # output, and a candidate whose content is identical is still a new
        # revision of the tree.
        git("commit", "-q", "--allow-empty", "-m", "candidate changed",
            cwd=self.work)
        git("push", "-q", "origin", "develop", cwd=self.work)
        self.develop = git("rev-parse", "develop", cwd=self.work)
        return self.develop

    # -- the gh shim ---------------------------------------------------------
    def _build_shim(self):
        self.artifacts.mkdir(parents=True)
        self.shim.write_text(GH_SHIM, encoding="utf-8")
        self.shim.chmod(0o755)

    def artifact(self, version, commit=None, files=None, report=None,
                 provenance=None, run="111", name="documentation-portal",
                 write=True):
        """An artifact directory shaped as ADR-0001 section 7 fixes it."""
        payload = {
            "schema": "mrmap.docs.provenance.v1",
            "project": "MrMap",
            "version": version,
            "builder": "html",
            "documented_commit": commit or self.develop,
            "toolchain": {"sphinx": "8.2.3"},
            "source_digest": sha256_bytes(("docs:" + version).encode()),
            "pages_build": None,
        }
        payload.update(provenance or {})
        payload = {k: v for k, v in payload.items() if v is not None}
        portal = files or {"index.html": f"<html>{version}</html>",
                           "gen/index.html": f"<p>{version} page</p>"}
        tree = {"provenance.json": json.dumps(payload, indent=2, sort_keys=True),
                "report.json": json.dumps(report if report is not None
                                          else {"result": "pass"})}
        for rel, content in portal.items():
            tree[f"portal/{rel}"] = content
        if not write:
            return tree
        root = self.artifacts / run / name
        for rel, content in tree.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return tree

    def remove_artifact(self, run="111", name="documentation-portal"):
        target = self.artifacts / run / name
        if target.exists():
            shutil.rmtree(target)

    # -- running the tool ----------------------------------------------------
    def run(self, *argv, env_extra=None, expect=None):
        command = [sys.executable, str(TOOL), "--root", str(REPO),
                   "--repository", "mrmap-community/mrmap",
                   "--remote", str(self.origin),
                   "--pages-dir", str(self.pages_dir),
                   "--git-bin", "git", "--gh-bin", str(self.shim)]
        command += [str(a) for a in argv]
        env = dict(GIT_ENV, GH_JOURNAL=str(self.journal),
                   GH_ARTIFACTS=str(self.artifacts))
        env.update(env_extra or {})
        proc = subprocess.run(command, env=env, capture_output=True, text=True)
        out = {"code": proc.returncode, "out": proc.stdout, "err": proc.stderr,
               "combined": proc.stdout + proc.stderr}
        if expect is not None and proc.returncode != expect:
            out["unexpected"] = (f"expected exit {expect}, got "
                                 f"{proc.returncode}: "
                                 f"{(proc.stdout + proc.stderr).strip()[:400]}")
        return out

    # -- reading what was published -----------------------------------------
    def fetch_pages(self):
        """Read the Pages branch from the origin, not from the tool's store."""
        mirror = self.tmp / f"mirror-{os.getpid()}-{len(RESULTS)}"
        if mirror.exists():
            shutil.rmtree(mirror)
        mirror.mkdir()
        git("init", "-q", "--bare", str(mirror))
        git("fetch", "-q", str(self.origin),
            "+refs/heads/gh-pages:refs/remotes/origin/gh-pages", cwd=mirror)
        code = subprocess.run(["git", "rev-parse", "--verify", "--quiet",
                               "refs/remotes/origin/gh-pages"],
                              cwd=str(mirror), env=GIT_ENV,
                              capture_output=True, text=True).returncode
        if code != 0:
            return None, {}, []
        revision = git("rev-parse", "refs/remotes/origin/gh-pages", cwd=mirror)
        listing = git("ls-tree", "-r", "--name-only", revision, cwd=mirror)
        files = {}
        for name in listing.splitlines():
            files[name] = git("show", f"{revision}:{name}", cwd=mirror)
        subjects = git("log", "--format=%s", revision, cwd=mirror).splitlines()
        return revision, files, subjects

    def marker(self, path):
        _revision, files, _subjects = self.fetch_pages()
        payload = files.get(f"{path.strip('/')}/{MARKER}")
        if payload is None:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {"invalid": payload}

    def digests(self, name="documentation-portal", run="111", keys=None):
        root = self.artifacts / run / name
        wanted = keys or sorted(
            str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())
        return [f"{key}={sha256_bytes((root / key).read_bytes())}"
                for key in wanted]

    def snapshot_origin(self):
        return (git("rev-parse", "develop", cwd=self.work),
                sorted(p.relative_to(self.origin).as_posix()
                       for p in self.origin.rglob("*") if p.is_file()))

    def close(self):
        if not self.keep and self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)


def bootstrap(world):
    return world.run("bootstrap")


# ---------------------------------------------------------------------------


def test_happy_path_stable_and_preview():
    world = World()
    try:
        check("bootstrap on an empty Pages branch succeeds",
              bootstrap(world)["code"] == 0, bootstrap(world).get("unexpected"))
        revision, files, subjects = world.fetch_pages()
        check("bootstrap commits the root selector and .nojekyll",
              revision is not None and MARKER in files and ".nojekyll" in files,
              str(sorted(files))[:200])
        check("bootstrap is a skip the second time",
              bootstrap(world)["code"] == 0
              and "already stands" in world.run("bootstrap")["out"])

        world.artifact("1.2.3", run="111")
        plan = world.run("plan", "--channel", "stable", "--run", "111",
                         "--name", "documentation-portal", "--json",
                         "--candidate", world.develop)
        check("plan of a first stable is a publish", plan["code"] == 0,
              plan.get("unexpected"))
        decisions = []
        try:
            decisions = json.loads(plan["out"]).get("decisions") or []
        except json.JSONDecodeError as exc:
            check("plan prints JSON", False, str(exc))
        check("plan names the version and the stable path",
              [d.get("path") for d in decisions] == ["/v1.2.3/"],
              str(decisions)[:300])
        check("plan does not write anything",
              world.fetch_pages()[2] == subjects, "plan wrote a commit")

        published = world.run("publish", "--channel", "stable", "--run", "111",
                              "--candidate", world.develop,
                              "--digests", *world.digests())
        check("publish of a verified artifact succeeds",
              published["code"] == 0, published.get("unexpected"))
        revision, files, subjects = world.fetch_pages()
        check("the stable channel wrote one commit",
              len(subjects) == 2 and subjects[0].startswith("docs-pages: publish stable"),
              str(subjects))
        check("the commit subject names the artifact and its docs_manifest",
              "from docs-artifact sha256:" in subjects[0], subjects[0])
        check("the version directory carries the artifact's own bytes",
              files.get("v1.2.3/index.html") == "<html>1.2.3</html>",
              str(files.get("v1.2.3/index.html")))
        check("/stable/ is a copy, not a pointer",
              files.get("stable/index.html") == "<html>1.2.3</html>",
              str(files.get("stable/index.html")))
        version_marker = world.marker("/v1.2.3/") or {}
        stable_marker = world.marker("/stable/") or {}
        check("the version marker names version, commit and digests",
              version_marker.get("version") == "1.2.3"
              and version_marker.get("documented_commit") == world.develop
              and str(version_marker.get("portal_digest", "")).startswith("sha256:")
              and str(version_marker.get("docs_manifest", "")).startswith("sha256:"),
              str(version_marker)[:300])
        check("the stable marker says it is the stable channel",
              stable_marker.get("channel") == "stable"
              and stable_marker.get("path") == "/stable/",
              str(stable_marker)[:200])
        index = json.loads(files.get(MARKER, "{}"))
        check("the root index offers the version and the stable channel",
              index.get("versions") == ["1.2.3"]
              and index.get("stable") == "1.2.3", str(index)[:300])

        verify = world.run("verify", "--channel", "stable",
                           "--artifact-dir", str(world.artifacts / "111" / "documentation-portal"),
                           "--candidate", world.develop, "--json")
        check("verify passes against the artifact it was published from",
              verify["code"] == 0, verify.get("unexpected"))
        status = world.run("status", "--json")
        check("status reports the stable version and the version directory",
              json.loads(status["out"]).get("stable") == "1.2.3"
              and json.loads(status["out"]).get("versions") == ["1.2.3"],
              status["out"][:300])
    finally:
        world.close()


def test_develop_preview_is_a_separate_channel():
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("0.0.0-dev", commit=candidate, run="201",
                       files={"index.html": "<html>candidate</html>"})
        published = world.run("publish", "--channel", "develop", "--run", "201",
                              "--candidate", candidate)
        check("publishing the develop preview succeeds",
              published["code"] == 0, published.get("unexpected"))
        _revision, files, subjects = world.fetch_pages()
        check("the preview writes only /develop/",
              sorted({p.split("/")[0] for p in files
                      if p != MARKER and p != ".nojekyll"}) == ["develop"],
              str(sorted(files))[:200])
        check("the preview commit says develop",
              subjects[0].startswith("docs-pages: publish develop /develop/"),
              subjects[0])
        marker = world.marker("/develop/") or {}
        check("the preview marker carries the candidate sha",
              marker.get("candidate_sha") == candidate
              and marker.get("channel") == "develop", str(marker)[:250])
        check("no version directory came from a develop build",
              not any(p.startswith("v0.0.0-dev") for p in files),
              str(sorted(files))[:200])
        check("the root index does not offer a develop build as a version",
              json.loads(files.get(MARKER, "{}")).get("versions") == [],
              str(files.get(MARKER))[:200])

        # A second, newer candidate replaces the preview and nothing else.
        newer = world.amend_candidate({"VERSION": "0.0.0-dev\n"})
        world.artifact("0.0.0-dev", commit=newer, run="202",
                       files={"index.html": "<html>newer</html>"})
        second = world.run("publish", "--channel", "develop", "--run", "202",
                           "--candidate", newer)
        check("a newer candidate replaces the preview",
              second["code"] == 0, second.get("unexpected"))
        _revision, files, _subjects = world.fetch_pages()
        check("the preview now serves the newer candidate",
              files.get("develop/index.html") == "<html>newer</html>",
              str(files.get("develop/index.html")))
    finally:
        world.close()


def test_candidate_and_stable_isolation():
    """The acceptance criterion "test candidate/stable isolation"."""
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("0.0.0-dev", commit=candidate, run="301",
                       files={"index.html": "<html>candidate</html>"})
        world.artifact("1.2.3", commit=candidate, run="302",
                       files={"index.html": "<html>stable</html>"},
                       provenance={"pages_build": "stable"})
        world.artifact("1.3.0", commit=candidate, run="303",
                       files={"index.html": "<html>newer stable</html>"},
                       provenance={"pages_build": "stable"})
        check("the develop preview publishes",
              world.run("publish", "--channel", "develop", "--run", "301",
                        "--candidate", candidate)["code"] == 0)
        preview_before = world.marker("/develop/")
        check("the stable channel publishes its version and /stable/",
              world.run("publish", "--channel", "stable", "--run", "302",
                        "--candidate", candidate)["code"] == 0)
        _revision, files, _subjects = world.fetch_pages()
        check("the stable publication leaves the preview bytes alone",
              files.get("develop/index.html") == "<html>candidate</html>",
              str(files.get("develop/index.html")))
        check("the stable publication does not touch the preview marker",
              world.marker("/develop/") == preview_before,
              "the develop marker moved when stable was published")
        check("a stable build cannot be published as the develop preview",
              world.run("publish", "--channel", "develop", "--run", "302",
                        "--candidate", candidate)["code"] == 1)
        check("a develop build cannot be published as stable",
              world.run("publish", "--channel", "stable", "--run", "301",
                        "--candidate", candidate)["code"] == 1)
        # The backwards case has to be a version directory that does not stand
        # yet: with /v1.2.3/ already published, immutability answers before the
        # stable ordering rule does, and that case is checked in
        # test_immutable_history_and_no_force_push.
        world.artifact("1.1.0", commit=candidate, run="304",
                       files={"index.html": "<html>older</html>"},
                       provenance={"pages_build": "stable"})
        backwards = world.run("publish", "--channel", "stable", "--run", "304",
                              "--candidate", candidate)
        check("the stable channel refuses to move backwards",
              backwards["code"] == 1 and "forward" in backwards["combined"],
              backwards["combined"][:250])
        _revision, files, _subjects = world.fetch_pages()
        check("a refused backward stable wrote no version directory",
              "v1.1.0/index.html" not in files, str(sorted(files))[:250])
        before = world.fetch_pages()[0]
        check("a newer stable publishes forward",
              world.run("publish", "--channel", "stable", "--run", "303",
                        "--candidate", candidate)["code"] == 0)
        _revision, files, _subjects = world.fetch_pages()
        check("the newer stable moved /stable/ forward",
              files.get("stable/index.html") == "<html>newer stable</html>",
              str(files.get("stable/index.html")))
        check("the older stable version directory is preserved",
              files.get("v1.2.3/index.html") == "<html>stable</html>",
              str(files.get("v1.2.3/index.html")))
        check("the preview survived both stable publications",
              files.get("develop/index.html") == "<html>candidate</html>",
              str(files.get("develop/index.html")))
        check("publication moved the Pages branch forward",
              world.fetch_pages()[0] != before, "the Pages revision did not move")
        index = json.loads(files.get(MARKER, "{}"))
        check("the root index offers both stable versions",
              index.get("versions") == ["1.2.3", "1.3.0"]
              and index.get("stable") == "1.3.0", str(index)[:300])
    finally:
        world.close()


def test_immutable_history_and_no_force_push():
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="401", files={"index.html": "<html>one</html>"})
        # Same version, different build identity: a different docs_manifest, so
        # this is a *second artifact* for one version and must be refused
        # rather than overwrite what stands. (An artifact with the same reuse
        # key is by definition the same artifact, which is the skip below.)
        world.artifact("1.0.0", run="402", files={"index.html": "<html>one</html>"},
                       provenance={"evidence_digest":
                                   {"screenshots": "sha256:" + "c" * 64}})
        world.artifact("1.1.0", run="403", files={"index.html": "<html>two</html>"})
        check("the first version publishes",
              world.run("publish", "--channel", "version", "--run", "401",
                        "--candidate", candidate)["code"] == 0)
        first = world.fetch_pages()[0]
        refused = world.run("publish", "--channel", "version", "--run", "402",
                            "--candidate", candidate)
        check("a second artifact for a standing version directory is refused",
              refused["code"] == 1, refused.get("unexpected"))
        check("the refusal names immutability",
              "immutable" in refused["combined"], refused["combined"][:300])
        check("the refusal wrote nothing", world.fetch_pages()[0] == first,
              "the Pages branch moved on a refusal")
        check("a rerun of the identical artifact is a skip",
              world.run("publish", "--channel", "version", "--run", "401",
                        "--candidate", candidate)["code"] == 0
              and "skip" in world.run("publish", "--channel", "version",
                                      "--run", "401",
                                      "--candidate", candidate)["out"])
        check("a skip leaves the Pages revision exactly where it was",
              world.fetch_pages()[0] == first, "an idempotent rerun wrote a commit")
        check("the next version publishes",
              world.run("publish", "--channel", "version", "--run", "403",
                        "--candidate", candidate)["code"] == 0)
        _revision, files, subjects = world.fetch_pages()
        check("the old version still serves its own bytes",
              files.get("v1.0.0/index.html") == "<html>one</html>",
              str(files.get("v1.0.0/index.html")))
        check("the new version is served beside it",
              files.get("v1.1.0/index.html") == "<html>two</html>",
              str(files.get("v1.1.0/index.html")))
        publications = [s for s in subjects if s != BOOTSTRAP_SUBJECT]
        check("every publication is a forward commit, never a rewrite",
              publications and all(s.startswith("docs-pages: publish ")
                                   for s in publications), str(subjects))
        check("the Pages object store is bare, so no branch exists to force-push",
              (world.pages_dir / "HEAD").is_file()
              and not (world.pages_dir / "index.html").exists()
              and subprocess.run(
                  ["git", "--git-dir", str(world.pages_dir), "show-ref"],
                  capture_output=True, text=True).stdout.count(
                      "refs/heads/") == 0,
              subprocess.run(["git", "--git-dir", str(world.pages_dir),
                              "show-ref"], capture_output=True,
                             text=True).stdout[:200])
        # The history of the published version is intact across later runs.
        check("the immutable version is reachable from the current tip",
              subprocess.run(
                  ["git", "--git-dir", str(world.pages_dir), "cat-file", "-e",
                   f"{world.fetch_pages()[0]}^{{tree}}"],
                  capture_output=True, text=True).returncode == 0)
    finally:
        world.close()


def test_failed_publication_keeps_the_previous_docs():
    """The acceptance criterion "failed publication without losing old docs"."""
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="501", files={"index.html": "<html>keep me</html>"})
        check("a first publication succeeds",
              world.run("publish", "--channel", "version", "--run", "501",
                        "--candidate", candidate)["code"] == 0)
        before_revision, before_files, _subjects = world.fetch_pages()

        def stays_intact(name, result):
            revision, files, _ = world.fetch_pages()
            check(f"{name}: nothing was written",
                  revision == before_revision and files == before_files,
                  f"exit {result.get('code')}; Pages moved to "
                  f"{str(revision)[:12]}")

        # The artifact does not belong to the candidate it is published for.
        world.artifact("1.1.0", commit="f" * 40, run="502")
        wrong = world.run("publish", "--channel", "version", "--run", "502",
                          "--candidate", candidate)
        check("an artifact of another sha is refused", wrong["code"] == 1,
              wrong.get("unexpected"))
        check("the refusal names the mismatching sha", "candidate" in wrong["combined"],
              wrong["combined"][:200])
        stays_intact("wrong candidate sha", wrong)

        # The gate did not pass: fail closed, keep the old docs served.
        world.artifact("1.1.0", run="503", report={"result": "fail"})
        failed = world.run("publish", "--channel", "version", "--run", "503",
                           "--candidate", candidate)
        check("an artifact whose gate failed is refused", failed["code"] == 1,
              failed.get("unexpected"))
        check("the refusal names fail-closed publication",
              "validation" in failed["combined"], failed["combined"][:200])
        stays_intact("failed gate report", failed)
        check("even the preview channel refuses a failed gate",
              world.run("publish", "--channel", "develop", "--run", "503",
                        "--candidate", candidate)["code"] == 1)

        # No gate report at all: nothing validated, so nothing is served.
        world.artifact("1.1.0", run="504", report={})
        missing = world.run("publish", "--channel", "develop", "--run", "504",
                            "--candidate", candidate)
        check("an artifact with no gate report is refused", missing["code"] == 1,
              missing.get("unexpected"))
        stays_intact("missing gate report", missing)

        # The artifact cannot say what it was built from.
        world.artifact("1.1.0", run="505", provenance={"documented_commit": None})
        anonymous = world.run("publish", "--channel", "version", "--run", "505",
                              "--candidate", candidate)
        check("an unattributable artifact is refused", anonymous["code"] == 1,
              anonymous.get("unexpected"))
        stays_intact("artifact without a documented commit", anonymous)

        # A tampered download is not the verified artifact.
        world.artifact("1.1.0", run="506", files={"index.html": "<html>new</html>"})
        digests = world.digests(run="506")
        tampered = [d.split("=")[0] + "=" + "sha256:" + ("a" * 64)
                    for d in digests]
        bad = world.run("publish", "--channel", "version", "--run", "506",
                        "--candidate", candidate, "--digests", *tampered)
        check("a download that fails its attested digest is refused",
              bad["code"] == 1, bad.get("unexpected"))
        check("the refusal says the download does not match",
              "attestation" in bad["combined"], bad["combined"][:200])
        stays_intact("tampered download", bad)

        # A build that never produced a portal is not a publication.
        world.artifact("1.1.0", run="507")
        shutil.rmtree(world.artifacts / "507" / "documentation-portal" / "portal")
        shapeless = world.run("publish", "--channel", "version", "--run", "507",
                              "--candidate", candidate)
        check("an artifact with no portal/ tree is refused",
              shapeless["code"] == 1, shapeless.get("unexpected"))
        stays_intact("artifact without a portal tree", shapeless)

        # The Pages branch moved between plan and publish.
        moved = world.run("publish", "--channel", "version", "--run", "506",
                          "--candidate", candidate,
                          "--expect-revision", "0" * 40)
        check("a publisher whose Pages revision moved refuses",
              moved["code"] == 1, moved.get("unexpected"))
        stays_intact("moved Pages revision", moved)

        # The run itself is gone: cannot run, which is never a pass.
        world.remove_artifact(run="999")
        gone = world.run("publish", "--channel", "version", "--run", "999",
                         "--candidate", candidate)
        check("a missing artifact run is 'cannot run', not a pass",
              gone["code"] == 2, f"exit {gone.get('code')}")
        stays_intact("missing artifact run", gone)

        check("the previously published version is still served after all of it",
              before_files.get("v1.0.0/index.html") == "<html>keep me</html>"
              and world.fetch_pages()[1].get("v1.0.0/index.html")
              == "<html>keep me</html>", "the old docs were lost")
    finally:
        world.close()


def test_verified_reuse_only_when_inputs_match():
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.2.3", run="601", files={"index.html": "<html>a</html>"})
        first = world.run("manifest", "--channel", "version", "--run", "601",
                          "--candidate", candidate)
        check("the reuse key prints", first["code"] == 0, first.get("unexpected"))
        manifest = first["out"].strip()
        check("the reuse key is a sha256 digest",
              manifest.startswith("sha256:") and len(manifest) == 71, manifest)
        again = world.run("manifest", "--channel", "version", "--run", "601",
                          "--candidate", candidate)["out"].strip()
        check("one identical candidate has one reuse key", again == manifest,
              f"{manifest} != {again}")

        # An identical rerun publishes nothing.
        check("the first publication happens",
              world.run("publish", "--channel", "version", "--run", "601",
                        "--candidate", candidate)["code"] == 0)
        revision, _files, subjects = world.fetch_pages()
        rerun = world.run("publish", "--channel", "version", "--run", "601",
                          "--candidate", candidate)
        check("an identical rerun is a skip",
              rerun["code"] == 0 and rerun["out"].startswith("skip"),
              rerun["combined"][:200])
        check("the skip wrote no commit",
              world.fetch_pages()[0] == revision
              and world.fetch_pages()[2] == subjects, "a rerun published again")

        # A changed input moves the key, so the artifact is not reusable.
        for label, change in (
                ("a locale catalogue lands", {"docs/source/locale/de/LC_MESSAGES/docs.po": "msgid \"x\"\nmsgstr \"y\"\n"}),
                ("a dependency is bumped", {"frontend/package-lock.json": '{"name":"mrmap","lockfileVersion":3,"packages":{}}\n'}),
                ("the generator is edited", {"scripts/gen_docs_design.py": "# generator v2\n"})):
            moved = world.amend_candidate(change)
            world.artifact("1.2.3", run="602", files={"index.html": "<html>a</html>"},
                           provenance={"documented_commit": moved})
            second = world.run("manifest", "--channel", "version", "--run", "602",
                               "--candidate", moved)["out"].strip()
            check(f"{label}: the reuse key moves",
                  second != manifest and second.startswith("sha256:"), second)
            refused = world.run("publish", "--channel", "version", "--run", "602",
                                "--candidate", moved)
            check(f"{label}: the old version still refuses the new artifact",
                  refused["code"] == 1 and "immutable" in refused["combined"],
                  refused["combined"][:200])
            check(f"{label}: nothing was written",
                  world.fetch_pages()[0] == revision, "a refused publish wrote")
            world.remove_artifact(run="602")
            # roll the candidate back so the next input is the only difference
            world.amend_candidate({k: v for k, v in CANDIDATE_FILES.items()})
        # A different version of the same tree is a different artifact.
        other = world.amend_candidate({"VERSION": "1.2.4\n"})
        world.artifact("1.2.4", run="603", files={"index.html": "<html>b</html>"})
        third = world.run("manifest", "--channel", "version", "--run", "603",
                          "--candidate", other)["out"].strip()
        check("a different version has a different reuse key",
              third != manifest and third.startswith("sha256:"), third)
        check("and it publishes beside the first",
              world.run("publish", "--channel", "version", "--run", "603",
                        "--candidate", other)["code"] == 0)
        _revision, files, _subjects = world.fetch_pages()
        check("both immutable versions are served",
              "v1.2.3/index.html" in files and "v1.2.4/index.html" in files,
              str(sorted(files))[:300])
    finally:
        world.close()


def test_serialized_publication():
    """The acceptance criterion "serialized atomic/idempotent publication"."""
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="701", files={"index.html": "<html>a</html>"})
        world.artifact("1.1.0", run="702", files={"index.html": "<html>b</html>"})
        plan = world.run("plan", "--channel", "version", "--run", "701",
                         "--candidate", candidate, "--json")
        revision = json.loads(plan["out"] or "{}").get("pages_revision")
        check("plan reports the Pages revision it read",
              bool(revision), str(plan["out"])[:200])
        # A second publisher lands first: a stale publisher must refuse.
        check("the other candidate publishes in between",
              world.run("publish", "--channel", "version", "--run", "702",
                        "--candidate", candidate)["code"] == 0)
        stale = world.run("publish", "--channel", "version", "--run", "701",
                          "--candidate", candidate, "--expect-revision", revision)
        check("a publisher holding a stale Pages revision refuses",
              stale["code"] == 1 and "moved" in stale["combined"],
              stale["combined"][:250])
        tip, files, _subjects = world.fetch_pages()
        check("the refusal published nothing of its own",
              "v1.0.0/index.html" not in files, "a stale publisher wrote a version")
        check("the concurrent publication is intact",
              files.get("v1.1.0/index.html") == "<html>b</html>",
              str(files.get("v1.1.0/index.html")))
        check("the later publisher can publish once it re-reads the tip",
              world.run("publish", "--channel", "version", "--run", "701",
                        "--candidate", candidate)["code"] == 0)
    finally:
        world.close()


def test_recovery_when_pages_is_unreachable():
    """The acceptance criterion "recovery if Pages fails"."""
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="801", files={"index.html": "<html>a</html>"})
        check("a first publication works",
              world.run("publish", "--channel", "version", "--run", "801",
                        "--candidate", candidate)["code"] == 0)
        before = world.fetch_pages()
        world.artifact("1.1.0", run="802", files={"index.html": "<html>b</html>"})
        broken = World(keep=False)
        broken.close()
        # Point the remote at a directory that is not a repository: a failed
        # fetch is "cannot run", never a green publication and never a loss.
        unreachable = str(world.tmp / "not-a-repository")
        Path(unreachable).mkdir(exist_ok=True)
        failed = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(REPO),
             "--remote", unreachable, "--pages-dir", str(world.tmp / "other.git"),
             "--gh-bin", str(world.shim), "--git-bin", "git",
             "publish", "--channel", "version", "--run", "802",
             "--candidate", candidate],
            env=dict(GIT_ENV, GH_JOURNAL=str(world.journal),
                     GH_ARTIFACTS=str(world.artifacts)),
            capture_output=True, text=True)
        check("an unreachable Pages remote is 'cannot run'", failed.returncode == 2,
              f"exit {failed.returncode}: {(failed.stdout + failed.stderr)[:300]}")
        check("the published docs survived the unreachable Pages host",
              world.fetch_pages()[1] == before[1], "the old docs were lost")
        check("the publication can be completed once Pages answers again",
              world.run("publish", "--channel", "version", "--run", "802",
                        "--candidate", candidate)["code"] == 0)
        _revision, files, _subjects = world.fetch_pages()
        check("and both versions are then served",
              files.get("v1.0.0/index.html") == "<html>a</html>"
              and files.get("v1.1.0/index.html") == "<html>b</html>",
              str(sorted(files))[:300])
    finally:
        world.close()


def test_no_source_writes_and_least_privilege():
    """The acceptance criteria "no source writes" and "least privilege"."""
    world = World()
    try:
        before = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(REPO), env=GIT_ENV, capture_output=True, text=True).stdout
        tracked = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                                 env=GIT_ENV, capture_output=True,
                                 text=True).stdout.strip()
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="901", files={"index.html": "<html>a</html>"})
        world.artifact("0.0.0-dev", run="902", files={"index.html": "<html>d</html>"})
        for argv in (["plan", "--channel", "version", "--run", "901",
                      "--candidate", candidate],
                     ["publish", "--channel", "version", "--run", "901",
                      "--candidate", candidate],
                     ["publish", "--channel", "develop", "--run", "902",
                      "--candidate", candidate],
                     ["verify", "--channel", "version", "--artifact-dir",
                      str(world.artifacts / "901" / "documentation-portal"),
                      "--candidate", candidate],
                     ["status", "--json"],
                     ["revisions"],
                     ["archive", "--channel", "version", "--run", "901",
                      "--candidate", candidate],
                     ["extract", "--output", str(world.tmp / "extracted")]):
            result = world.run(*argv)
            check(f"{argv[0]} exits cleanly", result["code"] in (0, 1),
                  result.get("unexpected"))
        after = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(REPO), env=GIT_ENV, capture_output=True, text=True).stdout
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO),
                              env=GIT_ENV, capture_output=True,
                              text=True).stdout.strip()
        check("no subcommand touched the working tree", after == before,
              f"before={before!r} after={after!r}")
        check("no subcommand moved HEAD", head == tracked, f"{tracked} -> {head}")
        check("docs/ holds nothing the publisher added",
              not (REPO / "docs" / "publish_docs.sh").exists()
              and not list((REPO / "docs").glob("*.sh")),
              str([p.name for p in (REPO / "docs").glob("*.sh")]))
        journal = world.journal.read_text(encoding="utf-8").splitlines()
        verbs = [json.loads(line)[:2] for line in journal]
        check("every GitHub call the tool makes is a download",
              all(v == ["run", "download"] for v in verbs), str(verbs)[:300])
        check("the tool never calls gh with a write verb",
              not any(v[0] in {"api", "release", "pr", "workflow"}
                      for v in verbs), str(verbs)[:300])
    finally:
        world.close()


def test_archive_and_retention():
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="1001",
                       provenance={"run_id": 1001,
                                   "evidence_digest": {"screenshots": "sha256:"
                                                                     + "b" * 64}})
        archived = world.run("archive", "--channel", "version", "--run", "1001",
                             "--candidate", candidate)
        check("the archive record is written", archived["code"] == 0,
              archived.get("unexpected"))
        try:
            record = json.loads(archived["out"])
        except json.JSONDecodeError as exc:
            check("the archive record is JSON", False, str(exc))
            record = {}
        check("the archive record names its store and identity",
              record.get("schema") == "mrmap.docs.artifact.v1"
              and record.get("store") == "docs-artifact/v1"
              and record.get("run_id") == 1001
              and record.get("documented_commit") == candidate,
              str(record)[:300])
        check("the archive record carries the digests an old URL is traced by",
              str(record.get("portal_digest", "")).startswith("sha256:")
              and str(record.get("artifact_digest", "")).startswith("sha256:")
              and str(record.get("source_digest", "")).startswith("sha256:"),
              str(record)[:300])
        check("the record names the inputs of the reuse key",
              set(record.get("inputs", [])) >= {"lockfiles", "locales",
                                                "generator", "evidence",
                                                "provenance"},
              str(record.get("inputs"))[:200])
        check("the artifact digest excludes its own digest field",
              record.get("artifact_digest") == sha256_bytes(
                  json.dumps(
                      {k: v for k, v in json.loads(
                          (world.artifacts / "1001" / "documentation-portal"
                           / "provenance.json").read_text()).items()
                       if k != "digest"},
                      sort_keys=True, separators=(",", ":"),
                      default=str).encode()),
              str(record.get("artifact_digest")))
        out = world.tmp / "archive" / "record.json"
        written = world.run("archive", "--channel", "version", "--run", "1001",
                            "--candidate", candidate, "--output", str(out))
        check("the archive record can be written to a file",
              written["code"] == 0 and out.is_file(), written["combined"][:200])
    finally:
        world.close()


def test_retire_subcommand():
    """The obsolete force-push publisher must stay retired (ADR-0001 section 12)."""
    result = subprocess.run(
        [sys.executable, str(TOOL), "--root", str(REPO), "retire"],
        cwd=str(REPO), env=GIT_ENV, capture_output=True, text=True)
    check("retire passes on this checkout", result.returncode == 0,
          (result.stdout + result.stderr)[:400])
    check("the force-push script is gone from the tree",
          not (REPO / "docs" / "publish_docs.sh").exists())
    check("the privileged publisher workflow is committed",
          (REPO / ".github" / "workflows" / "docs-pages.yml").is_file())


def test_dry_run_writes_nothing():
    world = World()
    try:
        bootstrap(world)
        candidate = world.develop
        world.artifact("1.0.0", run="1101", files={"index.html": "<html>a</html>"})
        before = world.fetch_pages()
        dry = world.run("publish", "--channel", "version", "--run", "1101",
                        "--candidate", candidate, "--dry-run")
        check("dry-run succeeds", dry["code"] == 0, dry.get("unexpected"))
        check("dry-run says it pushed nothing", "nothing pushed" in dry["out"],
              dry["out"][:200])
        check("dry-run wrote no Pages commit", world.fetch_pages()[1] == before[1],
              "a dry run published")
    finally:
        world.close()


def test_bootstrap_is_needed_first():
    world = World()
    try:
        candidate = world.develop
        world.artifact("1.0.0", run="1201")
        result = world.run("publish", "--channel", "version", "--run", "1201",
                           "--candidate", candidate)
        check("publishing onto an empty Pages branch refuses rather than orphans a commit",
              result["code"] == 1 and "bootstrap" in result["combined"],
              result["combined"][:250])
        check("verify reports an empty Pages branch as a failure",
              world.run("verify", "--channel", "version")["code"] == 1)
        check("and as a pass when the caller allows an empty site",
              world.run("verify", "--channel", "version",
                        "--allow-empty")["code"] == 0)
    finally:
        world.close()


def main():
    print("docs_publish.py holds against the acceptance criteria of #1608")
    for suite in (test_happy_path_stable_and_preview,
                  test_develop_preview_is_a_separate_channel,
                  test_candidate_and_stable_isolation,
                  test_immutable_history_and_no_force_push,
                  test_failed_publication_keeps_the_previous_docs,
                  test_verified_reuse_only_when_inputs_match,
                  test_serialized_publication,
                  test_recovery_when_pages_is_unreachable,
                  test_no_source_writes_and_least_privilege,
                  test_archive_and_retention,
                  test_dry_run_writes_nothing,
                  test_bootstrap_is_needed_first,
                  test_retire_subcommand):
        print(f"\n{suite.__name__}")
        try:
            suite()
        except Exception as exc:  # a suite must report, not die
            check(f"{suite.__name__} ran", False, f"{type(exc).__name__}: {exc}")
    failed = [name for name, ok, _detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        if not ok:
            print(f"FAIL  {name}  - {detail}")
    for name, reason in SKIPPED:
        print(f"skip  {name}  - {reason}")
    print(f"\n{len(failed)} failed of {len(RESULTS)} checks"
          + (f" ({len(SKIPPED)} skipped)" if SKIPPED else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
