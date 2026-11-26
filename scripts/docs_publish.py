#!/usr/bin/env python3
"""docs_publish: publish immutable versioned documentation artifacts to Pages.

Run from the repository root as ``python3 scripts/docs_publish.py <subcommand>``
(issue #1608, epic #1589; ADR-0001 section 12). Standard library only, plus the
local ``git`` CLI for every repository fact and the ``gh`` CLI for every GitHub
artifact fact - no container, no database, no other network. Exit 0 when the
asked step is done or already done, 1 when it decides against the input, 2 when
it could not run (an unreachable remote, a missing ``gh``, a missing artifact) -
"could not run" is never a pass.

What this tool replaces
-----------------------
``docs/publish_docs.sh`` was a 2021 script that rebuilt the portal inside the
job and ``git push --force`` the result onto ``gh-pages``. ADR-0001 section 12
retires it, because every property the epic requires of publication is the
opposite of what a force-push gives: ``--force`` rewrites the only copy of what
is published, so a bad run does not leave the previous version served, and
ADR-0001 section 11 says failure means *no new publication*, never a
*downgraded* one; a tree built inside the publisher cannot be reproduced from
anything, so "exact version/SHA/digests" has nothing to name; and the
credentials that build the docs are the credentials that write the website.

Publication therefore becomes: download the immutable artifact, verify it, and
write it onto the Pages tree as **one new commit whose parent is the commit that
stands there now**. The Pages object store is a private bare repository under
the temp directory keyed by the remote URL, refreshed with ``git fetch``: it
holds no branch and no worktree, so the force-push model is not merely
discouraged here, it is unavailable, and producing a commit cannot write a
source file.

What is published where
-----------------------
The four path families of the acceptance criteria, chosen by ``--channel``:

``--channel version``  ``/vX.Y.Z/`` - one artifact, written once and never
                       again. ``revisions`` lists them, and gate V-17 asserts
                       their bytes stay identical forever.
``--channel stable``   the reviewed stable: its ``/vX.Y.Z/`` directory plus
                       ``/stable/``, served as a *copy* of that tree so that
                       dropping an old version directory can never drop
                       ``/stable/`` with it. ``/stable/`` only ever moves
                       forward to a higher SemVer version.
``--channel develop``  ``/develop/`` - the last *validated* candidate build of
                       develop. Publishing it requires a gate report that
                       passed, so a candidate that fails validation never
                       displaces what is served today.
``--allow-prerelease`` the optional ``/vX.Y.Z-rc.N/`` directory, which
                       ``scripts/release_lifecycle.json`` excludes by default.

A directory counts as published when it carries ``.docs-version.json``, naming
its version, its ``docs_manifest``, its ``documented_commit``, its
``candidate_sha`` and the digest of its own tree. The root ``.docs-version.json``
is the version index the multiversion build and a health check read, refreshed
with every publication, which is what keeps historical versions selectable.

The reuse key
-------------
ADR-0001 section 6 fixes the identity of a documentation artifact as
``docs_manifest``: ``sha256`` over the version, the candidate tree, the
dependency lockfiles, the locales, the generator and the evidence digest - and
nothing else. A rerun of an identical candidate resolves to one manifest and
publishes nothing new ("verified artifact reuse only when inputs match"), and a
locale edit, a ``package-lock.json`` change or a generator bump moves the key
and forces a fresh artifact instead of a lucky reuse. Lockfile, locale and
generator digests are read from the candidate tree through ``git show``, never
from the working copy, which on CI is the merge commit of a pull request and not
the candidate at all. An artifact whose ``provenance.json`` names a different
version or tree than the one it is published for is refused rather than
reinterpreted.

Serialized, atomic, idempotent
------------------------------
CI runs every publication in one non-cancelling concurrency group, and the tool
re-reads the Pages tip *after* taking it; ``--expect-revision`` catches the
window between ``plan`` and ``publish``, so a publisher that would overwrite a
commit it never read refuses instead of writing. Idempotence is per path: the
same artifact published twice is a skip that writes nothing, and a second
artifact for a version directory that already stands is a refusal, not an
overwrite. Because one publication is one commit, a failed publication leaves
the previous revision in place by construction - the negative case of the
acceptance criteria needs no rollback code.

Where the privilege lives
-------------------------
The tool holds no credential: ``gh`` answers every GitHub fact and the push uses
``git``'s own credential helper, so a build job needs read access to artifacts
and nothing else. The write belongs to the separate human-gated privileged job
of ``.github/workflows/docs-pages.yml``, which consumes artifacts and never
builds (ADR-0001 section 12). And the tool refuses to be a source writer: no
subcommand writes under the repository, which the offline suite checks from the
real working tree rather than from a promise.

How the suites fake it, honestly
---------------------------------
``--git-bin`` and ``--gh-bin`` are the seams the offline suite injects - the
same seams ``scripts/test_release_promotion.py`` uses. The "remote" is a local
bare repository on the file transport and the Pages branch is a ref inside it,
so the assertions read what actually landed there; ``gh`` is a PATH-shimmed
fixture that journals every call and serves artifacts from a directory the test
wrote. Nothing in the suite talks to GitHub, and nothing in the suite publishes
to a real site.

Subcommands
-----------
``artifact-digest``  ``name=sha256:...`` of a file, for the attestation
``manifest``         the ``docs_manifest`` reuse key of an artifact
``plan``             per-path publish / skip / refuse, each with its reason
``publish``          write the plan as one commit and push it
``verify``           published bytes against the artifact they claim
``status``           what is published, machine-readable
``revisions``        every published directory with its identity
``archive``          the retention record of one artifact
``bootstrap``        create the Pages branch once, with the root index only
``extract``          export a published revision, for comparison
``retire``           check the obsolete force-push publisher stayed retired
"""
import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
_spec = importlib.util.spec_from_file_location("release_gates",
                                               SCRIPTS / "release_gates.py")
release_gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_gates)

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

PAGES_BRANCH = "gh-pages"
PUBLISHER_IDENTITY = "mrmap-docs-publisher"
MARKER_NAME = ".docs-version.json"
PROVENANCE_SCHEMA = "mrmap.docs.provenance.v1"
MANIFEST_SCHEMA = "mrmap.docs.manifest.v1"
MARKER_SCHEMA = "mrmap.docs.published.v1"
INDEX_SCHEMA = "mrmap.docs.pages.index.v1"
STATUS_SCHEMA = "mrmap.docs.pages.status.v1"
ARCHIVE_SCHEMA = "mrmap.docs.artifact.v1"
#: The dependency inputs named by ADR-0001 section 6. A changed lockfile moves
#: the reuse key, so its artifact is no longer the verified one.
LOCKFILES = (
    "backend/.requirements/base.txt",
    "backend/.requirements/requirements.txt",
    "backend/.requirements/docs.txt",
    "frontend/package-lock.json",
)
GENERATOR = "scripts/gen_docs_design.py"
STABLE_PATH = "/stable/"
DEVELOP_PATH = "/develop/"
CHANNELS = ("develop", "stable", "version")
ACCEPTED_GATE_RESULTS = {"pass", "passed", "green", "ok"}
BLOCKING_GATE_RESULTS = {"fail", "failed", "error", "blocked", "skipped"}


class PublishRefused(Exception):
    """The tool decided against this input; exit 1, nothing was written."""


class PublishCannotRun(Exception):
    """The tool could not run; exit 2. Never reported as a pass."""


# --------------------------------------------------------------- subprocesses

BASE_GIT_ENV = dict(os.environ,
                    GIT_CONFIG_GLOBAL="/dev/null",
                    GIT_CONFIG_SYSTEM="/dev/null",
                    GIT_TERMINAL_PROMPT="0",
                    LC_ALL="C")


def run(argv, cwd=None, env=None, stdin=None):
    proc = subprocess.run([str(a) for a in argv],
                          cwd=str(cwd) if cwd else None, env=env, input=stdin,
                          capture_output=True)
    return proc.returncode, proc.stdout, proc.stderr


def gitlet(args, *argv, git_dir=None, env_extra=None, allow_fail=False,
           stdin=None):
    """One git call, bytes in and bytes out, so artifact content survives it."""
    command = [args.git_bin]
    if git_dir is not None:
        command += ["--git-dir", str(git_dir)]
    command += [str(a) for a in argv]
    env = dict(BASE_GIT_ENV)
    env.update(env_extra or {})
    code, out, err = run(command, cwd=args.root, env=env, stdin=stdin)
    if code != 0 and not allow_fail:
        raise PublishCannotRun(
            f"git {' '.join(str(a) for a in argv)}: "
            f"{err.decode('utf-8', 'replace').strip()}")
    return code, out, err


def git_text(args, *argv, **kwargs):
    return gitlet(args, *argv, **kwargs)[1].decode("utf-8", "replace")


def gh(args, *argv, allow_fail=False):
    env = dict(os.environ, GH_REPO=args.repository)
    code, out, err = run([args.gh_bin, *argv], cwd=args.root, env=env)
    text_out = out.decode("utf-8", "replace")
    text_err = err.decode("utf-8", "replace")
    if code != 0 and not allow_fail:
        raise PublishCannotRun(
            f"gh {' '.join(argv[:2])}: {(text_err or text_out).strip()}")
    return code, text_out, text_err


# -------------------------------------------------------------------- digests


def is_hex_digest(value):
    return bool(re.fullmatch(r"sha256:[0-9a-f]{64}", str(value or "")))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def sha256_bytes(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str)


def digest_of_json(payload):
    return "sha256:" + hashlib.sha256(
        canonical_json(payload).encode("utf-8")).hexdigest()


def json_text(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_json(path, required=True):
    path = Path(path)
    if not path.is_file():
        if required:
            raise PublishRefused(f"no such file: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PublishRefused(f"{path} is not valid JSON: {exc}")


def parse_digests(entries):
    """``name=sha256:<hex>`` pairs, the shape release_promotion already uses."""
    found = {}
    for entry in entries or []:
        entry = entry.strip()
        if not entry:
            continue
        if "=" not in entry:
            raise PublishRefused(
                f"--digests entry {entry!r} is not name=sha256:...")
        name, digest = entry.split("=", 1)
        if not is_hex_digest(digest):
            raise PublishRefused(f"--digests entry {entry!r} carries no "
                                 f"sha256:<64 hex> digest")
        found[name.strip()] = digest.strip()
    return found


def remove_tree(path):
    path = Path(path)
    for child in sorted(path.rglob("*"), reverse=True):
        (child.unlink() if child.is_file() else child.rmdir())
    if path.exists():
        path.rmdir()


def semver_key(version):
    """Sort key of a SemVer string; a prerelease ranks below its release."""
    match = release_gates.SEMVER_RE.match(str(version or ""))
    if not match:
        raise PublishRefused(f"{version!r} is not a SemVer version")
    major, minor, patch = (int(match.group(index)) for index in (1, 2, 3))
    prerelease = match.group(4)
    return (major, minor, patch, 0 if prerelease is None else -1,
            prerelease or "")


# ------------------------------------------------------ the pages object store


def pages_dir(args):
    """The private bare repository that stands in for the Pages branch.

    Keyed by the remote, so two publishers of one repository share one object
    store and both fetch the same tip. It holds no branch and no worktree: the
    only thing a publisher can do with it is add a commit on top of the tip it
    just fetched.
    """
    if args.pages_dir:
        return Path(args.pages_dir)
    key = hashlib.sha256(args.remote.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"mrmap-docs-pages-{key}"


def ensure_pages_repo(args):
    directory = pages_dir(args)
    git_dir = directory
    if not (git_dir / "HEAD").exists():
        directory.mkdir(parents=True, exist_ok=True)
        gitlet(args, "init", "-q", "--bare", str(directory))
    for name, value in (("core.bare", "true"),
                        ("user.name", PUBLISHER_IDENTITY),
                        ("user.email",
                         f"{PUBLISHER_IDENTITY}@users.noreply.github.com"),
                        ("remote.origin.fetch",
                         f"+refs/heads/{PAGES_BRANCH}:refs/remotes/origin/"
                         f"{PAGES_BRANCH}")):
        gitlet(args, "config", name, value, git_dir=git_dir)
    if gitlet(args, "remote", "get-url", "origin", git_dir=git_dir,
              allow_fail=True)[0] != 0:
        gitlet(args, "remote", "add", "origin", args.remote, git_dir=git_dir)
    else:
        gitlet(args, "remote", "set-url", "origin", args.remote,
               git_dir=git_dir)
    refspec = (f"+refs/heads/{PAGES_BRANCH}:refs/remotes/origin/"
               f"{PAGES_BRANCH}")
    code, _out, err = gitlet(args, "fetch", "-q", "origin", refspec,
                             git_dir=git_dir, allow_fail=True)
    detail = err.decode("utf-8", "replace")
    if code != 0 and not re.search(r"couldn't find remote ref|no such ref",
                                   detail, re.IGNORECASE):
        raise PublishCannotRun(
            f"cannot fetch {PAGES_BRANCH} from {args.remote}: {detail.strip()}")
    return git_dir


def pages_revision(args, git_dir):
    """The revision the Pages branch points at, or None when none is published."""
    code, out, _err = gitlet(args, "rev-parse", "--verify", "--quiet",
                             f"refs/remotes/origin/{PAGES_BRANCH}",
                             git_dir=git_dir, allow_fail=True)
    revision = out.decode().strip()
    if code == 0 and re.fullmatch(r"[0-9a-f]{40}", revision):
        return revision
    return None


def published_files(args, git_dir, revision):
    """``{path: bytes}`` of a published tree, exported with ``git archive``.

    Extraction goes through ``git archive`` rather than a file walk, so
    ``verify`` checks exactly what an operator can get out of the Pages branch,
    and a tree no archiver can export is caught before a release rather than
    after one.
    """
    payload = gitlet(args, "archive", "--format=tar", revision,
                     git_dir=git_dir)[1]
    files = {}
    with tarfile.open(fileobj=io.BytesIO(payload)) as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise PublishCannotRun(
                    "the published tree carries an unsafe path: "
                    f"{member.name}")
            handle = archive.extractfile(member)
            files[member.name] = handle.read() if handle else b""
    return files


def write_tree(args, git_dir, files):
    """One tree object from ``{path: bytes}``, through an isolated index file.

    Written through an index instead of a checkout for the same reason the
    object store is bare: producing the commit touches no working tree, so
    neither the repository nor the artifact can be modified on the way.
    """
    with tempfile.TemporaryDirectory(prefix="mrmap-docs-index-") as scratch:
        env_extra = {"GIT_INDEX_FILE": str(Path(scratch) / "index")}
        gitlet(args, "read-tree", "--empty", git_dir=git_dir,
               env_extra=env_extra)
        for path in sorted(files):
            blob = gitlet(args, "hash-object", "-w", "--stdin",
                          git_dir=git_dir, env_extra=env_extra,
                          stdin=files[path])[1].decode().strip()
            gitlet(args, "update-index", "--add", "--cacheinfo",
                   f"100644,{blob},{path}", git_dir=git_dir,
                   env_extra=env_extra)
        return gitlet(args, "write-tree", git_dir=git_dir,
                      env_extra=env_extra)[1].decode().strip()


def commit_tree(args, git_dir, tree, message, parents):
    """One commit whose parent is the revision this run read - never a force-push.

    ``SOURCE_DATE_EPOCH`` is honoured, as the portal build honours it, so a
    rerun of one verified publication is reproducible down to the commit date.
    """
    email = f"{PUBLISHER_IDENTITY}@users.noreply.github.com"
    env_extra = {"GIT_AUTHOR_NAME": PUBLISHER_IDENTITY,
                 "GIT_AUTHOR_EMAIL": email,
                 "GIT_COMMITTER_NAME": PUBLISHER_IDENTITY,
                 "GIT_COMMITTER_EMAIL": email}
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch and re.fullmatch(r"\d{9,12}", epoch):
        env_extra["GIT_AUTHOR_DATE"] = f"@{int(epoch)} +0000"
        env_extra["GIT_COMMITTER_DATE"] = f"@{int(epoch)} +0000"
    argv = ["commit-tree", tree, "-m", message]
    for parent in parents:
        argv += ["-p", parent]
    return gitlet(args, *argv, git_dir=git_dir,
                  env_extra=env_extra)[1].decode().strip()


def push_commit(args, git_dir, commit):
    """Push one forward commit. There is no ``--force`` in this function."""
    code, _out, err = gitlet(args, "push", "origin",
                             f"{commit}:refs/heads/{PAGES_BRANCH}",
                             git_dir=git_dir, allow_fail=True)
    detail = err.decode("utf-8", "replace").strip()
    if code != 0:
        if re.search(r"non-fast-forward|fetch first|stale info", detail,
                     re.IGNORECASE):
            raise PublishRefused(
                f"{PAGES_BRANCH} moved while this run was publishing: {detail}. "
                f"Nothing was written - re-run plan and publish. The "
                f"publication is serialized, so this means the concurrency "
                f"group did not hold")
        raise PublishCannotRun(
            f"cannot push to {PAGES_BRANCH} of {args.remote}: {detail}")


def publication_subject(channel, path, manifest):
    return f"docs-pages: publish {channel} {path} from docs-artifact {manifest}"


# -------------------------------------------------------------------- artifact


class Artifact:
    """One verified documentation artifact as it was handed over.

    ADR-0001 section 7 fixes the shape: ``portal/`` is the publishable tree,
    ``provenance.json`` names what it was built from and ``report.json`` is what
    the gate read. ``docs_gate.py`` already refuses an artifact missing one of
    them, so publication refuses too - and names which of the two failures it
    saw, because "the download broke" and "the build is broken" are paged
    differently.
    """

    def __init__(self, directory, name=None, repository=None):
        self.path = Path(directory)
        if not self.path.is_dir():
            raise PublishCannotRun(
                f"artifact {self.path} is not a directory; the publisher "
                f"downloads it first, which docs-pages.yml does")
        self.name = name or self.path.name
        self.repository = repository
        self.portal = self.path / "portal"
        if not self.portal.is_dir():
            raise PublishRefused(
                f"artifact {self.name} carries no portal/ tree: that is the "
                f"artifact-shape rule of scripts/docs_gate.py, not a download "
                f"failure")
        self.provenance = load_json(self.path / "provenance.json")
        if self.provenance.get("schema") != PROVENANCE_SCHEMA:
            raise PublishRefused(
                f"artifact {self.name} carries provenance schema "
                f"{self.provenance.get('schema')!r}; publication consumes "
                f"{PROVENANCE_SCHEMA}, written by "
                f"docs/source/_ext/mrmap_docs.py")
        self.report = load_json(self.path / "report.json", required=False)

    @property
    def version(self):
        return str(self.provenance.get("version") or "")

    @property
    def documented_commit(self):
        return self.provenance.get("documented_commit")

    @property
    def source_digest(self):
        return self.provenance.get("source_digest")

    @property
    def pages_build(self):
        """The channel the build says it was produced for, when it says."""
        return self.provenance.get("pages_build")

    @property
    def run_id(self):
        return self.provenance.get("run_id")

    def provenance_digest(self):
        """Digest of the build identity, excluding its own digest field.

        ``mrmap_docs`` writes no ``digest`` field, so an artifact from before
        this tool digests identically here and inside ``docs_gate.py``:
        publication adds a binding to the archive rather than minting a second
        identity for one build.
        """
        payload = {key: value for key, value in self.provenance.items()
                   if key != "digest"}
        return digest_of_json(payload)

    def gate_result(self):
        if self.report is None:
            return None
        return str(self.report.get("result")
                   or self.report.get("status") or "").strip().lower()

    def files(self):
        """The publishable tree as ``{relative path: Path}``."""
        found = {}
        for path in sorted(p for p in self.portal.rglob("*") if p.is_file()):
            relative = path.relative_to(self.portal).as_posix()
            if Path(relative).name == MARKER_NAME:
                raise PublishRefused(
                    f"artifact {self.name} carries {relative}: the version "
                    f"selector is written by the publisher, so a build must "
                    f"not name the version it gets served as")
            found[relative] = path
        if not found:
            raise PublishRefused(f"artifact {self.name} has an empty portal/ "
                                 f"tree; there is nothing to publish")
        return found

    def tree_digest(self):
        """Digest over (path, content) of the publishable tree.

        Paths are digested as well as bytes, the way the portal's own
        ``mrmap_digests`` does for the sources: a rename moves a URL, so it
        changes the identity.
        """
        digest = hashlib.sha256()
        for relative, path in sorted(self.files().items()):
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return "sha256:" + digest.hexdigest()


def download_artifact(args):
    """``gh run download`` into a private directory, then check every digest.

    This is "verified artifact reuse": the digests come from the caller - the
    attestation of the run that produced the artifact - and a download that does
    not match them is refused instead of published.
    """
    if args.run is None:
        raise PublishRefused("downloading an artifact needs --run")
    dest = Path(args.download_dir) if args.download_dir else Path(
        tempfile.mkdtemp(prefix="mrmap-docs-artifact-"))
    if dest.exists():
        remove_tree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    code, out, err = gh(args, "run", "download", str(args.run),
                        "--name", args.name, "--dir", str(dest),
                        allow_fail=True)
    if code != 0:
        raise PublishCannotRun(
            f"run {args.run} carries no artifact named {args.name!r}: "
            f"{(err or out).strip()}")
    attested = parse_digests(args.digests)
    checked = 0
    for name, digest in sorted(attested.items()):
        for candidate in (dest / name, dest / "portal" / name):
            if candidate.is_file():
                if sha256_file(candidate) != digest:
                    raise PublishRefused(
                        f"artifact {args.name}: {name} is not {digest}; the "
                        f"download does not match its attestation, so it is "
                        f"not the verified artifact")
                checked += 1
                break
        else:
            raise PublishRefused(
                f"artifact {args.name} does not carry {name}, which its "
                f"attestation says it does")
    return Artifact(dest, name=args.name, repository=args.repository), checked


# --------------------------------------------------------------- the reuse key


def tree_file(args, tree, relative):
    """A file of the candidate tree through ``git show``, never the working copy."""
    code, out, _err = gitlet(args, "show", f"{tree}:{relative}",
                             allow_fail=True)
    return out if code == 0 else None


def lockfile_digests(args, tree):
    entries = []
    for relative in LOCKFILES:
        payload = tree_file(args, tree, relative) if tree else None
        entries.append([relative,
                        sha256_bytes(payload) if payload is not None else None])
    return canonical_json(entries)


def locales_digest(args, tree):
    """Sorted catalogue names of the candidate tree, or None while there are none.

    The corpus is English and ``sphinx-intl`` has no catalogues to build yet, so
    this is None today. It stays in the key because ADR-0001 section 6 names
    locales: a locale that lands later must invalidate a reuse rather than hide
    behind an old artifact that never had it.
    """
    if not tree:
        return None
    listing = gitlet(args, "ls-tree", "-r", "--name-only", tree,
                     allow_fail=True)[1].decode("utf-8", "replace")
    names = sorted({line.split("/")[2] for line in listing.splitlines()
                    if line.startswith("docs/source/locale/")
                    and len(line.split("/")) > 2})
    return canonical_json(names) if names else None


def generator_digest(args, tree):
    payload = tree_file(args, tree, GENERATOR) if tree else None
    return sha256_bytes(payload) if payload is not None else None


def docs_manifest(args, artifact, candidate=None):
    """``sha256`` over (version, tree, lockfiles, locales, generator, evidence).

    One implementation of the ADR-0001 section 6 key, so the reuse decision and
    the archive record cannot disagree. The artifact names its version and its
    evidence; the candidate tree names the inputs a build cannot be trusted to
    report about itself.
    """
    evidence = artifact.provenance.get("evidence_digest")
    parts = {
        "schema": MANIFEST_SCHEMA,
        "version": artifact.version,
        "tree": candidate or artifact.documented_commit,
        "lockfiles": artifact.provenance.get("lockfile_digests")
        or (lockfile_digests(args, candidate) if candidate else None),
        "locales": artifact.provenance.get("locales_digest")
        or (locales_digest(args, candidate) if candidate else None),
        "generator": artifact.provenance.get("generator_digest")
        or (generator_digest(args, candidate) if candidate else None),
        "evidence": canonical_json(evidence) if evidence is not None else None,
        "provenance": artifact.provenance_digest(),
    }
    return digest_of_json(parts), parts


# ------------------------------------------------------------- path selection


def classify(version, allow_prerelease=False):
    """The version directory a version is served from, and whether it may be.

    ``scripts/release_lifecycle.json`` says prereleases carry no published
    documentation, so an RC needs the explicit reviewed exception rather than a
    version string that happens to look like one.
    """
    match = release_gates.SEMVER_RE.match(str(version or ""))
    if not match:
        raise PublishRefused(
            f"{version!r} is not a vX.Y.Z version; the tag grammar of "
            f"scripts/release_lifecycle.json is the only grammar here")
    core = f"v{match.group(1)}.{match.group(2)}.{match.group(3)}"
    prerelease = match.group(4)
    if prerelease:
        if not allow_prerelease:
            raise PublishRefused(
                f"{version} is a prerelease and release_lifecycle.json "
                f"excludes prereleases from published documentation; the "
                f"optional RC directory needs --allow-prerelease")
        return f"/{core}-{prerelease}/"
    return f"/{core}/"


def primary_path(args, artifact):
    """The directory an artifact's tree is written to, for this channel."""
    if args.channel not in CHANNELS:
        raise PublishRefused(
            f"--channel must be one of {', '.join(CHANNELS)}")
    declared = artifact.pages_build
    if declared and declared != args.channel:
        raise PublishRefused(
            f"artifact {artifact.name} was built as {declared!r} and cannot be "
            f"published as {args.channel!r}: a develop candidate never becomes "
            f"a stable publication by being asked, which is why the channel is "
            f"the publisher's decision and not the build's")
    if args.channel == "develop":
        return DEVELOP_PATH
    return classify(artifact.version, args.allow_prerelease)


def marker_payload(artifact, manifest, candidate_sha, channel, path, args,
                   unvalidated=False):
    """The version selector of one published directory.

    The multiversion build offers the highest version in the tree, so a
    directory that is being served has to name itself. The digests are what make
    "immutable versioned artifact" checkable afterwards: ``verify`` re-downloads
    the artifact and compares bytes, and an operator reading a page about their
    own deployment can ask which build answered.
    """
    payload = {
        "schema": MARKER_SCHEMA,
        "path": path,
        "channel": channel,
        "version": artifact.version,
        "docs_manifest": manifest,
        "documented_commit": artifact.documented_commit,
        "candidate_sha": candidate_sha,
        "source_digest": artifact.source_digest,
        "artifact_digest": artifact.provenance_digest(),
        "portal_digest": artifact.tree_digest(),
        "artifact_name": artifact.name,
        "run_id": artifact.run_id,
        "repository": args.repository,
        "publisher": PUBLISHER_IDENTITY,
    }
    if unvalidated:
        payload["unvalidated"] = True
    return payload


def read_marker(files, path):
    """The marker of one published directory, or None when it is not published."""
    payload = files.get(f"{path.strip('/')}/{MARKER_NAME}")
    if payload is None:
        return None
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def published_paths(files):
    """``{path: marker}`` of every published directory, the root index excluded."""
    found = {}
    for name, payload in files.items():
        if name == MARKER_NAME or Path(name).name != MARKER_NAME:
            continue
        try:
            parsed = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict) and parsed.get("schema") == MARKER_SCHEMA:
            directory = "/"
            directory += name.rsplit("/" + MARKER_NAME, 1)[0].lstrip("/") + "/"
            found[directory] = parsed
    return found


def is_version_path(path):
    return path not in (STABLE_PATH, DEVELOP_PATH)


def index_payload(versions, stable, develop):
    """The root selector: what the version dropdown and a health check read."""
    return {
        "schema": INDEX_SCHEMA,
        "branch": PAGES_BRANCH,
        "branches": {"stable": STABLE_PATH, "development": DEVELOP_PATH},
        "stable": stable,
        "develop": develop,
        "versions": sorted(versions, key=semver_key) if versions else [],
        "publisher": PUBLISHER_IDENTITY,
    }


def build_tree(args, git_dir, base_files, additions, replaces=()):
    """One tree object: today's published content plus this change, minus prefixes.

    Built from the fetched revision rather than from a checkout, so the commit a
    publisher makes is exactly the current tree plus its own change. Historical
    version directories are inherited by construction - that is the acceptance
    criterion "preserve historical versions/URLs" - and no path outside the ones
    named here can move.
    """
    files = dict(base_files)
    for prefix in replaces:
        boundary = prefix.strip("/") + "/"
        for name in [name for name in files if name.startswith(boundary)]:
            del files[name]
    files.update(additions)
    return write_tree(args, git_dir, files)


def tree_prefix(path):
    """The tree key of a published directory: no leading slash.

    ``/v1.2.3/`` is how a path is written to a person and stored in a marker;
    git names the same directory ``v1.2.3/``, and an index entry with a leading
    slash is refused outright.
    """
    return path.strip("/") + "/"


def artifact_additions(args, artifact, manifest, candidate_sha, channel, path,
                       unvalidated=False):
    """Every file one artifact contributes, including its own marker."""
    additions = {}
    prefix = tree_prefix(path)
    for relative, source in sorted(artifact.files().items()):
        additions[f"{prefix}{relative}"] = source.read_bytes()
    additions[f"{prefix}{MARKER_NAME}"] = json_text(marker_payload(
        artifact, manifest, candidate_sha, channel, path, args,
        unvalidated)).encode("utf-8")
    return additions


# ------------------------------------------------------------- the gate before


def require_gate(artifact, allow_unvalidated=False):
    """A candidate that failed validation is never served, on any channel.

    ``/develop/`` is the last *validated* candidate, so the preview channel
    enforces the same report a stable publication does. ``--allow-unvalidated``
    exists for a preview off a fork and says so in the log and in the marker.
    """
    result = artifact.gate_result()
    if result in BLOCKING_GATE_RESULTS:
        raise PublishRefused(
            f"artifact {artifact.name} reports gate result {result!r}: "
            f"ADR-0001 section 11 forbids publishing content whose validation "
            f"did not pass, on the preview channel too")
    if result not in ACCEPTED_GATE_RESULTS and not allow_unvalidated:
        raise PublishRefused(
            f"artifact {artifact.name} has no passing gate report "
            f"(report.json says {result!r}); /develop/ serves the last "
            f"validated candidate, so a build that cannot show it passed is "
            f"not published. scripts/docs_gate.py gate writes that report")
    return result


def require_binding(args, artifact, candidate):
    """An artifact must be attributable to the inputs it is published for."""
    commit = artifact.documented_commit
    if not re.fullmatch(r"[0-9a-f]{40}", str(commit or "")):
        raise PublishRefused(
            f"artifact {artifact.name} does not name a documented_commit; an "
            f"artifact that cannot say what it was built from is not "
            f"published (mrmap_docs records null rather than a guess)")
    if candidate and commit != candidate:
        raise PublishRefused(
            f"artifact {artifact.name} was built from {commit}, not the "
            f"candidate {candidate}: verified artifact reuse needs matching "
            f"inputs, so the artifact of another sha is refused rather than "
            f"repurposed")
    if not release_gates.SEMVER_RE.match(artifact.version):
        raise PublishRefused(
            f"artifact {artifact.name} names version {artifact.version!r}; "
            f"publication needs the canonical VERSION value of #1579")
    if artifact.source_digest and not is_hex_digest(artifact.source_digest):
        raise PublishRefused(
            f"artifact {artifact.name} carries a malformed source_digest "
            f"{artifact.source_digest!r}")


def open_artifact(args):
    if args.artifact_dir:
        return (Artifact(args.artifact_dir,
                         name=args.artifact_name or Path(args.artifact_dir).name,
                         repository=args.repository), 0)
    return download_artifact(args)


# --------------------------------------------------------------- the decision


def plan_decisions(args, git_dir, artifacts, candidate=None):
    """The per-path decision, computed without writing anything.

    ``plan`` and ``publish`` share this function, so the decision a reviewer
    reads is the decision ``publish`` acts on; a second implementation would
    only be a second thing to get wrong.
    """
    revision = pages_revision(args, git_dir)
    base = published_files(args, git_dir, revision) if revision else {}
    decisions = []
    for artifact in artifacts:
        require_gate(artifact, args.allow_unvalidated)
        require_binding(args, artifact, candidate)
        path = primary_path(args, artifact)
        channel = args.channel
        manifest, _parts = docs_manifest(args, artifact, candidate)
        marker = read_marker(base, path)
        decision = {"channel": channel, "path": path,
                    "version": artifact.version, "artifact": artifact.name,
                    "docs_manifest": manifest,
                    "documented_commit": artifact.documented_commit}
        if marker and marker.get("docs_manifest") == manifest:
            decision.update(action="skip", reason=(
                f"{path} already serves this docs_manifest; a rerun of an "
                f"identical candidate writes nothing"))
        elif channel == "version" and marker:
            decision.update(action="refuse", reason=(
                f"{path} is already published from docs_manifest "
                f"{marker.get('docs_manifest')}; a version directory is "
                f"immutable (ADR-0001 section 7, gate V-17)"))
        elif channel == "stable":
            served = (read_marker(base, STABLE_PATH) or {}).get("version")
            if served and semver_key(artifact.version) <= semver_key(served):
                decision.update(action="refuse", reason=(
                    f"{STABLE_PATH} already serves {served}; publication only "
                    f"moves the stable channel forward to a higher version"))
            else:
                decision["also_stable"] = True
                decision.update(action="publish",
                                reason=f"{path} and {STABLE_PATH} from this "
                                       f"artifact")
        else:
            decision.update(action="publish",
                            reason=f"new docs_manifest for {path}")
        decisions.append(decision)
    return revision, decisions


# --------------------------------------------------------------- subcommands


def cmd_artifact_digest(args):
    path = Path(args.file)
    if not path.is_file():
        raise PublishCannotRun(f"no such file: {path}")
    print(f"{path.name}={sha256_file(path)}")
    return EXIT_OK


def cmd_manifest(args):
    artifact, _checked = open_artifact(args)
    manifest, parts = docs_manifest(args, artifact, candidate=args.candidate)
    if args.json:
        print(json.dumps({"docs_manifest": manifest, "parts": parts},
                         indent=2, sort_keys=True))
    else:
        print(manifest)
    return EXIT_OK


def cmd_plan(args):
    git_dir = ensure_pages_repo(args)
    artifact, _checked = open_artifact(args)
    revision, decisions = plan_decisions(args, git_dir, [artifact],
                                         candidate=args.candidate)
    report = {"schema": "mrmap.docs.publish-plan.v1",
              "pages_branch": PAGES_BRANCH, "pages_revision": revision,
              "decisions": decisions}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        shown = revision[:12] if revision else "(nothing published yet)"
        print(f"{PAGES_BRANCH} at {shown}")
        for decision in decisions:
            print(f"  {decision['action']:7s} {decision['channel']:8s} "
                  f"{decision['path']:16s} {decision['version']:14s} "
                  f"{decision['reason']}")
    return EXIT_FAIL if any(d["action"] == "refuse"
                            for d in decisions) else EXIT_OK


def cmd_publish(args):
    git_dir = ensure_pages_repo(args)
    artifact, checked = open_artifact(args)
    revision, decisions = plan_decisions(args, git_dir, [artifact],
                                         candidate=args.candidate)
    decision = decisions[0]
    if decision["action"] == "refuse":
        raise PublishRefused(decision["reason"])
    if decision["action"] == "skip":
        print(f"skip    {decision['path']}: {decision['reason']}")
        return EXIT_OK
    if revision is None:
        raise PublishRefused(
            f"{PAGES_BRANCH} has no published revision yet; run "
            f"'docs_publish.py bootstrap' once first, so the first publication "
            f"has a parent commit and Pages has a root file to build")
    if args.expect_revision and revision != args.expect_revision:
        raise PublishRefused(
            f"{PAGES_BRANCH} moved: plan read {args.expect_revision}, it now "
            f"stands at {revision}. This run would overwrite a commit it never "
            f"read, so it writes nothing - re-run plan and publish")
    base = published_files(args, git_dir, revision)
    path, channel, manifest = (decision["path"], decision["channel"],
                               decision["docs_manifest"])
    unvalidated = (args.allow_unvalidated
                   and artifact.gate_result() not in ACCEPTED_GATE_RESULTS)
    candidate_sha = args.candidate or artifact.documented_commit
    additions = artifact_additions(args, artifact, manifest, candidate_sha,
                                   channel, path, unvalidated=unvalidated)
    replaces = [path]
    if decision.get("also_stable"):
        # /stable/ is a copy of the stable tree rather than a pointer to a
        # version directory: retention can then drop /vX.Y.Z/ without taking
        # /stable/ down with it, and a reader of /stable/ gets the exact bytes
        # that were gated.
        source_prefix = tree_prefix(path)
        additions.update({tree_prefix(STABLE_PATH) + name[len(source_prefix):]:
                          payload for name, payload in additions.items()})
        additions[f"{tree_prefix(STABLE_PATH)}{MARKER_NAME}"] = json_text(
            marker_payload(artifact, manifest, candidate_sha, "stable",
                           STABLE_PATH, args, unvalidated)).encode("utf-8")
        replaces.append(STABLE_PATH)

    versions = [marker["version"]
                for directory, marker in published_paths(base).items()
                if is_version_path(directory) and marker.get("version")]
    if channel != "develop":
        versions.append(artifact.version)
    served_stable = (read_marker(base, STABLE_PATH) or {}).get("version")
    if channel == "stable":
        served_stable = artifact.version
    if channel == "develop":
        served_develop = {"version": artifact.version,
                          "docs_manifest": manifest,
                          "candidate_sha": candidate_sha}
    else:
        served_develop = read_marker(base, DEVELOP_PATH)
    additions[MARKER_NAME] = json_text(index_payload(
        versions, served_stable, served_develop)).encode("utf-8")

    tree = build_tree(args, git_dir, base, additions, replaces=replaces)
    subject = publication_subject(channel, path, manifest)
    commit = commit_tree(args, git_dir, tree, subject, [revision])
    if args.dry_run:
        print(f"dry-run {channel} {path}: tree {tree[:12]} on top of "
              f"{revision[:12]}, {len(additions)} file(s); nothing pushed")
        return EXIT_OK
    push_commit(args, git_dir, commit)
    print(f"publish {channel} {path}: {revision[:12]} -> {commit[:12]} "
          f"({len(additions)} file(s), docs_manifest {manifest[:19]}...)"
          + (f", {checked} attested digest(s) checked" if checked else "")
          + (" [unvalidated preview]" if unvalidated else ""))
    return EXIT_OK


def cmd_verify(args):
    git_dir = ensure_pages_repo(args)
    revision = pages_revision(args, git_dir)
    if revision is None:
        if args.allow_empty:
            print(f"{PAGES_BRANCH} publishes nothing yet")
            return EXIT_OK
        print(f"FAIL  {PAGES_BRANCH} publishes nothing")
        return EXIT_FAIL
    files = published_files(args, git_dir, revision)
    problems = []
    rows = []
    for path, marker in sorted(published_paths(files).items()):
        boundary = path.strip("/") + "/"
        digest = hashlib.sha256()
        count = 0
        for name in sorted(files):
            if not name.startswith(boundary) or Path(name).name == MARKER_NAME:
                continue
            digest.update(name[len(boundary):].encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[name])
            digest.update(b"\0")
            count += 1
        published = "sha256:" + digest.hexdigest()
        rows.append({"path": path, "channel": marker.get("channel"),
                     "version": marker.get("version"),
                     "docs_manifest": marker.get("docs_manifest"),
                     "documented_commit": marker.get("documented_commit"),
                     "files": count, "portal_digest": published})
        if marker.get("portal_digest") != published:
            problems.append(
                f"{path}: the published bytes are not the bytes its marker "
                f"records ({marker.get('portal_digest')})")
        if not is_hex_digest(marker.get("docs_manifest")):
            problems.append(f"{path}: its marker names no docs_manifest")
    if args.artifact_dir:
        artifact = Artifact(args.artifact_dir, name=args.artifact_name,
                            repository=args.repository)
        path = primary_path(args, artifact)
        marker = read_marker(files, path)
        expected = docs_manifest(args, artifact, args.candidate)[0]
        if marker is None:
            problems.append(f"{path} is not published, although artifact "
                            f"{artifact.name} asked to be verified against it")
        elif marker.get("docs_manifest") != expected:
            problems.append(
                f"{path} is published from another docs_manifest than "
                f"{artifact.name} carries: the site and the artifact disagree")
    report = {"schema": "mrmap.docs.published.v1",
              "pages_branch": PAGES_BRANCH, "pages_revision": revision,
              "paths": rows, "problems": problems}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"{PAGES_BRANCH} at {revision[:12]}")
        for row in rows:
            print(f"  {row['path']:16s} {str(row['version']):14s} "
                  f"{row['files']:4d} file(s)  portal "
                  f"{row['portal_digest'][:19]}...")
        for problem in problems:
            print(f"  MISMATCH  {problem}")
    return EXIT_FAIL if problems else EXIT_OK


def cmd_status(args):
    git_dir = ensure_pages_repo(args)
    revision = pages_revision(args, git_dir)
    status = {"schema": STATUS_SCHEMA, "pages_branch": PAGES_BRANCH,
              "pages_revision": revision, "stable": None, "develop": None,
              "versions": [], "paths": []}
    if revision:
        files = published_files(args, git_dir, revision)
        markers = published_paths(files)
        stable = read_marker(files, STABLE_PATH) or {}
        status["stable"] = stable.get("version")
        status["develop"] = read_marker(files, DEVELOP_PATH)
        status["versions"] = sorted(
            {marker["version"] for directory, marker in markers.items()
             if is_version_path(directory) and marker.get("version")},
            key=semver_key)
        status["paths"] = sorted(markers)
    if args.json:
        print(json.dumps(status, indent=2, sort_keys=True))
        return EXIT_OK
    shown = revision[:12] if revision else "(nothing)"
    print(f"{PAGES_BRANCH} at {shown}")
    print(f"  stable   {status['stable'] or '(never published)'}")
    develop = status["develop"] or {}
    line = f"  develop  {develop.get('version') or '(never published)'}"
    if develop.get("candidate_sha"):
        line += f"  candidate {str(develop['candidate_sha'])[:12]}"
    print(line)
    print(f"  versions {', '.join(status['versions']) or '(none)'}")
    return EXIT_OK


def cmd_revisions(args):
    git_dir = ensure_pages_repo(args)
    revision = pages_revision(args, git_dir)
    rows = []
    if revision:
        files = published_files(args, git_dir, revision)
        for path, marker in sorted(published_paths(files).items()):
            rows.append({"path": path, "channel": marker.get("channel"),
                         "version": marker.get("version"),
                         "docs_manifest": marker.get("docs_manifest"),
                         "documented_commit": marker.get("documented_commit"),
                         "candidate_sha": marker.get("candidate_sha"),
                         "portal_digest": marker.get("portal_digest"),
                         "immutable": is_version_path(path)})
    print(json.dumps({"pages_revision": revision, "revisions": rows},
                     indent=2, sort_keys=True))
    return EXIT_OK


def cmd_archive(args):
    """The retention record of one artifact, keyed by its reuse identity.

    Intermediates live as long as the CI retention window; the release artifact
    set is what outlives it (ADR-0001 section 7). This record is a row of that
    set - name, digests and inputs - so an old URL can be traced back to the
    build that owes it, and a missing artifact can be named rather than guessed
    at when someone asks what a published page was made from.
    """
    artifact, _checked = open_artifact(args)
    manifest, parts = docs_manifest(args, artifact, candidate=args.candidate)
    entry = {
        "schema": ARCHIVE_SCHEMA,
        "store": "docs-artifact/v1",
        "docs_manifest": manifest,
        "repository": args.repository,
        "run_id": args.run if args.run is not None else artifact.run_id,
        "artifact_name": artifact.name,
        "version": artifact.version,
        "documented_commit": artifact.documented_commit,
        "source_digest": artifact.source_digest,
        "portal_digest": artifact.tree_digest(),
        "artifact_digest": artifact.provenance_digest(),
        "gate_result": artifact.gate_result(),
        "files": len(artifact.files()),
        "inputs": sorted(parts),
    }
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json_text(entry), encoding="utf-8")
        print(f"wrote {destination}")
        return EXIT_OK
    print(json.dumps(entry, indent=2, sort_keys=True))
    return EXIT_OK


def cmd_bootstrap(args):
    """Create the Pages branch once, with the root index and nothing else.

    GitHub Pages reports a build error for a branch with no root file, and a
    publication needs a parent commit; one bootstrap commit carrying the version
    selector solves both. It refuses when the branch already stands, because
    rewriting a published branch is not this command's decision to make.
    """
    git_dir = ensure_pages_repo(args)
    revision = pages_revision(args, git_dir)
    if revision is not None:
        print(f"{PAGES_BRANCH} already stands at {revision[:12]}; nothing to "
              f"bootstrap")
        return EXIT_OK
    tree = write_tree(args, git_dir, {
        MARKER_NAME: json_text(index_payload([], None, None)).encode("utf-8"),
        ".nojekyll": b"",
    })
    commit = commit_tree(args, git_dir, tree,
                         "docs-pages: bootstrap the documentation portal", [])
    push_commit(args, git_dir, commit)
    print(f"bootstrap {PAGES_BRANCH}: {commit[:12]} "
          f"({MARKER_NAME}, .nojekyll)")
    return EXIT_OK


def cmd_extract(args):
    """Export a published revision, to compare what is served with an artifact."""
    git_dir = ensure_pages_repo(args)
    revision = pages_revision(args, git_dir)
    if revision is None:
        raise PublishRefused(f"{PAGES_BRANCH} publishes nothing to extract")
    dest = Path(args.output)
    if dest.exists():
        remove_tree(dest)
    files = published_files(args, git_dir, args.revision or revision)
    for name in sorted(files):
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])
    print(f"extracted {len(files)} file(s) from "
          f"{(args.revision or revision)[:12]} to {dest}")
    return EXIT_OK


def cmd_retire(args):
    """Check that the force-push publisher stayed retired, from the repository.

    ADR-0001 section 12 retires ``docs/publish_docs.sh`` and the workflow that
    called it. A retired script that crept back would come back with ``--force``
    in it, so the check reads the tree and the history rather than a note in a
    document.
    """
    obsolete = ROOT / "docs" / "publish_docs.sh"
    deleted = subprocess.run(
        ["git", "--no-pager", "log", "--oneline", "--diff-filter=D", "--",
         "docs/publish_docs.sh"],
        cwd=str(ROOT), capture_output=True, text=True)
    workflow = ROOT / ".github" / "workflows" / "docs-pages.yml"
    checks = [
        ("the force-push script is gone", not obsolete.exists(),
         f"{obsolete.relative_to(ROOT)} still exists"),
        ("its deletion is in the history", bool(deleted.stdout.strip()),
         "no commit deletes docs/publish_docs.sh"),
        ("no workflow force-pushes the Pages branch",
         not workflows_force_push_pages(),
         "a committed workflow still pushes gh-pages with --force"),
        ("the privileged publisher is a workflow", workflow.is_file(),
         str(workflow.relative_to(ROOT))),
    ]
    failed = [name for name, ok, _detail in checks if not ok]
    for name, ok, detail in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
              + ("" if ok else f"  - {detail}"))
    return EXIT_FAIL if failed else EXIT_OK


def workflows_force_push_pages():
    """True when a committed workflow still force-pushes the Pages branch."""
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        if PAGES_BRANCH in text and re.search(r"git push[^\n]*(--force|-f)\b",
                                              text):
            return True
    return False


# ------------------------------------------------------------------------- CLI


def build_parser():
    parser = argparse.ArgumentParser(
        prog="docs_publish", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT),
                        help="the repository root (default: this file's parent)")
    parser.add_argument("--repository",
                        default=os.environ.get("GITHUB_REPOSITORY",
                                               "mrmap-community/mrmap"))
    parser.add_argument("--remote",
                        default=os.environ.get(
                            "MRMAP_DOCS_PAGES_REMOTE",
                            "https://github.com/mrmap-community/mrmap.git"),
                        help="where the Pages branch lives")
    parser.add_argument("--pages-dir", default=None,
                        help="object store for the Pages branch (default: a "
                             "private directory keyed by the remote)")
    parser.add_argument("--git-bin", default="git")
    parser.add_argument("--gh-bin", default="gh")

    # The artifact and publication options belong to the subcommand, so that an
    # operator writes `publish --channel stable --run 123` rather than learning
    # which half of the grammar each flag lives on.
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--run", type=int, default=None,
                        help="workflow run that uploaded the artifact")
    shared.add_argument("--name", default="documentation-portal",
                        help="artifact name within the run")
    shared.add_argument("--artifact-dir", default=None,
                        help="an artifact already downloaded and verified")
    shared.add_argument("--artifact-name", default=None)
    shared.add_argument("--download-dir", default=None)
    shared.add_argument("--digests", action="extend", nargs="+", default=[],
                        metavar="NAME=sha256:HEX",
                        help="attested digest of an artifact file; the download "
                             "is refused when it does not match. Repeatable, "
                             "and takes several pairs at once")
    shared.add_argument("--candidate", default=None,
                        help="the frozen candidate sha the artifact must be "
                             "built from")
    shared.add_argument("--expect-revision", default=None,
                        help="the Pages revision plan read; refuse when it "
                             "moved (serialized publication)")
    shared.add_argument("--allow-prerelease", action="store_true",
                        help="the optional RC directory, which "
                             "release_lifecycle.json excludes by default")
    shared.add_argument("--allow-unvalidated", action="store_true",
                        help="publish despite a missing gate report; a preview "
                             "for a fork, never for a release")
    shared.add_argument("--dry-run", action="store_true")
    shared.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def with_channel(parser_):
        parser_.add_argument("--channel", choices=CHANNELS, default=None,
                             help="which path family this artifact serves")

    sp = sub.add_parser("artifact-digest", help="name=sha256 digest of a file")
    sp.add_argument("--file", required=True)
    sp.set_defaults(func=cmd_artifact_digest)

    sp = sub.add_parser("manifest", parents=[shared],
                        help="the docs_manifest reuse key")
    with_channel(sp)
    sp.set_defaults(func=cmd_manifest)

    sp = sub.add_parser("plan", parents=[shared],
                        help="what would be published, with reasons")
    with_channel(sp)
    sp.set_defaults(func=cmd_plan)

    sp = sub.add_parser("publish", parents=[shared],
                        help="write and push one publication commit")
    with_channel(sp)
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("verify", parents=[shared],
                        help="published bytes against the artifact")
    with_channel(sp)
    sp.add_argument("--allow-empty", action="store_true")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("status", parents=[shared],
                        help="what is published, machine-readable")
    sp.set_defaults(func=cmd_status)

    sp = sub.add_parser("revisions", parents=[shared],
                        help="every published directory with its identity")
    sp.set_defaults(func=cmd_revisions)

    sp = sub.add_parser("archive", parents=[shared],
                        help="the retention record of an artifact")
    with_channel(sp)
    sp.add_argument("--output", default=None)
    sp.set_defaults(func=cmd_archive)

    sp = sub.add_parser("bootstrap", help="create the Pages branch once")
    sp.set_defaults(func=cmd_bootstrap)

    sp = sub.add_parser("extract", parents=[shared],
                        help="export a published revision to disk")
    sp.add_argument("--revision", default=None)
    sp.add_argument("--output", required=True)
    sp.set_defaults(func=cmd_extract)

    sp = sub.add_parser("retire",
                        help="check the obsolete force-push publisher is gone")
    sp.set_defaults(func=cmd_retire)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.root = Path(args.root).resolve()
    if not (args.root / "scripts" / "docs_publish.py").is_file():
        print(f"docs_publish: {args.root} is not a repository root "
              f"(no scripts/docs_publish.py)", file=sys.stderr)
        return EXIT_FAIL
    try:
        return args.func(args)
    except PublishRefused as error:
        print(f"docs_publish: refused: {error}", file=sys.stderr)
        return EXIT_FAIL
    except PublishCannotRun as error:
        print(f"docs_publish: cannot run: {error}", file=sys.stderr)
        return EXIT_CANNOT


if __name__ == "__main__":
    sys.exit(main())
