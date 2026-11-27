#!/usr/bin/env python3
"""docs_release_rehearsal: one real, isolated rehearsal of the docs release (#1610).

Run from the repository root:

    python3 scripts/docs_release_rehearsal.py --candidate <sha> \
        --evidence-out docs/source/development/evidence/docs-release-rehearsal-1610.json

Exit 0 when every ran check passes, 1 when a check contradicts the contract, 2
when the harness itself could not run - no candidate named, a candidate whose
tree carries no buildable portal, an interpreter that cannot import the pinned
Sphinx, an evidence path that would overwrite reviewed content.

Why this exists, and nowhere else
---------------------------------
#1589's acceptance list has exactly one item nobody can satisfy by committing a
file: *one real non-production hosting/release rehearsal*. #1607 committed the
strict build and proved its exit status is the gate, #1608 committed
``.readthedocs.yaml`` and wrote down the rules an administrator has to set, and
#1609 wires the ordinary release job that builds the exact reviewed master merge
SHA. None of those three can answer what this issue asks - what actually happens
when a merge commit is put through the strict build and the managed host is then
asked for by URL - because the answer is not in the repository. It is in
Sphinx's exit status, in the HTTP headers of the hosted site and in the Actions
API. A page of prose claiming all three is exactly the green-that-means-nothing
this repository refuses.

So this is a harness, not a framework: no simulation, no state machine, no
evidence schema of its own, no cache, no orchestrator, no repair loop. It builds
a real commit and reads real answers back, and writes what it observed. What a
worker cannot reach - the managed host's administration and a protected-
environment publication - is named in the report under ``limitations`` rather
than imitated. The one act on shared infrastructure this tool is capable of,
``--promote``, pushes a **rehearsal** tag: off by default, refusing any name the
release policy reserves, and needing the same tag spelled out in the environment.

What it rehearses
-----------------
``--candidate`` names the exact commit a release would stand on - the merge
commit of a develop -> master release pull request, which is what #1798 builds
and nothing else. Its tree is exported with ``git archive``, so the build reads
the candidate's content and never this working tree's, and the SHA is verified
through the object store rather than trusted from the command line.

* **the native gate** - Sphinx is asked twice, with the exact flags
  ``.github/workflows/docs.yml`` runs (read out of that file, not restated): the
  candidate as it is, and the same export with one injected fault. The clean
  candidate must exit 0; the broken one must exit non-zero, must name its fault,
  and must leave the clean artifact standing - which is "keep the previous
  verified live documentation on build failure" checked where it can actually be
  seen: a refused build writes no artifact, so there is nothing new to publish.
* **build identity** - ``provenance.json`` of the accepted build must name this
  candidate SHA, its toolchain and its source digest. A rehearsal that cannot
  say what it built has not rehearsed anything.
* **the absence of a second publisher, in the candidate** - the candidate's own
  ``.github/workflows`` is scanned for a Pages deployment job, a force-push and a
  repository-owned publisher, so a publisher added after the reviewed build
  cannot slip through; and no job may run *full generation* on ordinary
  pull-request or develop traffic.
* **the managed host** - unless ``--skip-host-probe`` declares this rehearsal
  gate-only, the hosted URLs are read and the observed facts recorded: does the
  site answer, which versions does it say it serves, does a stable version exist
  yet, which edge serves it. ``MRMAP_DOCS_REHEARSAL_URL`` points the probe at an
  isolated managed project instead of the production one, and the report says
  which of the two was probed.
* **the run record** - the Actions check runs of the candidate are read back with
  their URLs, because "record run URLs, SHA, version and result" is an acceptance
  line of the issue and a SHA without a run is an unreviewable claim.
* **``--promote``** - the publication act itself: a tag created on the candidate,
  pushed, read back through ``ls-remote`` and the API, and refused outright if the
  name matches ``scripts/release_lifecycle.json``'s ``tag_pattern``.

The committed rules around the tool - what a report must carry, what a rehearsal
tag may never be called, which paths the evidence writer may overwrite - have
their own offline suite, ``scripts/test_docs_release_rehearsal.py``, which CI runs
through ``scripts/check_repo_tooling.sh`` against a synthetic rehearsal it builds.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ISSUE = 1610
PARENT_EPIC = 1589
#: Shape of the report this tool writes. Named here rather than in a schema file
#: because there is one writer and one page that describes it - a schema of its
#: own would be the custom evidence framework #1589 retired.
EVIDENCE_SCHEMA = "mrmap.docs.rehearsal.v1"
REPOSITORY = "mrmap-community/mrmap"
GITHUB_API = "https://api.github.com/"
DOCS_REQUIREMENTS = "backend/.requirements/docs.txt"
WORKFLOWS = ".github/workflows"
#: The only tag prefix this tool may ever push. Below it is obviously a
#: rehearsal; outside it belongs to the release process.
REHEARSAL_TAG_PREFIX = "docs-rehearsal-"
#: Where the release policy's ``tag_pattern`` lives; read, never copied.
LIFECYCLE = "scripts/release_lifecycle.json"
#: Authorises the only write this tool can perform, by naming the exact tag.
PROMOTE_ENVIRONMENT = "MRMAP_DOCS_REHEARSAL_PROMOTE"
#: Points the host probe at an isolated managed project (#1589: "isolated
#: managed-host configuration or official Pages equivalent, no production writes").
HOST_ENVIRONMENT = "MRMAP_DOCS_REHEARSAL_URL"
#: Where a rehearsal of this issue writes its report, beside the other recorded
#: live runs of the repository.
DEFAULT_EVIDENCE_PATH = ("docs/source/development/evidence/"
                         "docs-release-rehearsal-1610.json")

failures: list[str] = []
RESULTS: list[dict] = []
MEASUREMENTS: list[dict] = []
LIMITATIONS: list[str] = []
COMMANDS: list[str] = []


class HarnessError(Exception):
    """The rehearsal could not run; the exit code is 2, never 1."""


class RuleViolation(Exception):
    """A committed rule of this tool is contradicted; 2, not 1."""


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    if not ok:
        failures.append(f"{name}: {detail}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail and not ok else ""))


def measure(name: str, value, unit: str = "", note: str = "") -> None:
    MEASUREMENTS.append({"name": name, "value": value, "unit": unit, "note": note})
    print(f"  ..   {name}: {value}" + (f" {unit}" if unit else "")
          + (f"  ({note})" if note else ""))


def limit(text: str) -> None:
    if text not in LIMITATIONS:
        LIMITATIONS.append(text)
        print(f"  note  not covered: {text}")


# ------------------------------------------------------------------- rules ---
def strict_flags(workflow_text: str) -> list[str]:
    """The flags the committed docs job builds the portal with.

    Read out of ``.github/workflows/docs.yml`` rather than restated: a rehearsal
    whose gate quietly drifted from the gate CI runs rehearses something else.
    """
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if "-m sphinx" in stripped and "-b" in stripped and " html" in stripped:
            return [token for token in stripped.split()[3:]
                    if token.startswith("-") or token == "html"]
    raise RuleViolation("no `python -m sphinx -b html` build step to read the "
                        "gate's flags from")


def release_tag_pattern(lifecycle_text: str) -> str:
    """``tag_pattern`` of the release policy, exactly as committed."""
    try:
        pattern = json.loads(lifecycle_text)["tag_pattern"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        raise RuleViolation(f"{LIFECYCLE} does not carry a tag_pattern: {error}")
    if not isinstance(pattern, str) or not pattern.startswith("^"):
        raise RuleViolation(f"{LIFECYCLE} tag_pattern is not an anchored regex: "
                            f"{pattern!r}")
    return pattern


def is_rehearsal_tag(tag: str, lifecycle_text: str) -> bool:
    """May this tool ever push ``tag``? A release tag is never a rehearsal."""
    if not tag.startswith(REHEARSAL_TAG_PREFIX):
        return False
    # A Git tag ending in "." or "-" is invalid, and the bare prefix names no
    # rehearsal: the suffix is what says which run published it.
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?",
                        tag[len(REHEARSAL_TAG_PREFIX):]):
        return False
    return not re.match(release_tag_pattern(lifecycle_text), tag)


def assert_writable_evidence(path: Path, root: Path = ROOT) -> None:
    """Refuse an evidence path that would write where a rehearsal report may not.

    The report is reviewed content, and a rehearsal that silently rewrites an
    unrelated committed file is a rehearsal that edits the repository under test.
    Only a report under a ``docs/**/evidence/`` directory may be written.
    """
    resolved = path if path.is_absolute() else (root / path)
    try:
        relative = resolved.relative_to(root)
    except ValueError as error:
        raise RuleViolation(f"the report has to stay inside the repository: {error}")
    parts = relative.parts
    if not parts or parts[0] != "docs" or "evidence" not in parts:
        raise RuleViolation(
            f"{relative} is not a rehearsal report: write under "
            f"docs/**/evidence/, where the recorded live runs of this repository "
            f"live")
    if any(part in (".", "..", "") for part in parts):
        raise RuleViolation(f"{relative} is not a clean path")


def ordinary_traffic_generators(workflows: dict[str, str]) -> list[str]:
    """Jobs of a candidate that run *full generation* on ordinary traffic.

    "Ordinary pull-request and develop pushes do not trigger full generation" is
    an acceptance line of #1589. Full generation means what a publisher does - a
    multiversion matrix, a site upload, a Pages deploy, a force-push - while the
    strict single-tree build of ``docs.yml`` is a *check*, belongs on a pull
    request, and is what makes a red reviewable. The rule is about publishing.
    """
    offenders: list[str] = []
    for name, body in workflows.items():
        trigger = re.search(r"(?m)^on:\n((?:.*\n)*?)(?=^\S)", body + "\n")
        scope = trigger.group(1) if trigger else body
        dispatch_only = ("workflow_dispatch" in scope
                         and "pull_request" not in scope and "push" not in scope)
        for token in ("sphinx-multiversion", "deploy-pages",
                      "upload-pages-artifact", "gh-pages", "publish_docs"):
            if token in body and not dispatch_only:
                offenders.append(f"{name} runs {token!r} in a scope ordinary "
                                 f"traffic can reach")
    return offenders


# --------------------------------------------------------------------- git ---
def git(*args: str, cwd: Path | None = None) -> str:
    process = subprocess.run(["git", *args], cwd=str(cwd or ROOT),
                             capture_output=True, text=True)
    if process.returncode != 0:
        raise HarnessError(
            f"git {' '.join(args[:2])} exited {process.returncode}: "
            f"{(process.stderr or process.stdout).strip()[:300]}")
    return process.stdout


def resolve_candidate(revision: str) -> str:
    """The full SHA of ``revision``, verified through the object store.

    A rehearsal of a SHA that is not in this repository would otherwise report a
    pass for a tree nobody has - the failure mode every "we released it" claim
    this issue exists to close has taken.
    """
    out = git("rev-parse", "--verify", f"{revision}^{{commit}}").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", out):
        raise HarnessError(f"{revision} did not resolve to a commit (got {out!r})")
    return out


def is_merge_commit(sha: str) -> bool:
    return len(git("rev-list", "--parents", "-n", "1", sha).split()) > 2


def promotion_merge_status(stable_branch: str = "origin/master",
                           development_branch: str = "origin/develop") -> dict:
    """Would a promotion merge of the two permanent branches be possible today?

    ``git merge-tree`` answers without touching the working tree or the index.
    The answer belongs in a rehearsal report: #1798 promotes by merging
    ``develop`` into ``master``, so if that merge is conflicted there is no
    promotion merge commit to rehearse yet, and a report that did not say so
    would leave a reader believing the missing half of the rehearsal was
    laziness rather than history.
    """
    merge = subprocess.run(["git", "merge-tree", "--write-tree",
                            stable_branch, development_branch],
                           cwd=str(ROOT), capture_output=True, text=True)
    if merge.returncode not in (0, 1):
        return {"mergeable": None,
                "reason": (merge.stderr.strip().splitlines() or ["unknown"])[0]}
    lines = merge.stdout.splitlines()
    if not lines or not re.fullmatch(r"[0-9a-f]{40}", lines[0]):
        # An exit status of 1 with no tree OID means the refs themselves could not
        # be read, which is not the same answer as "these branches conflict".
        return {"mergeable": None,
                "reason": (merge.stderr.strip().splitlines() or ["unknown"])[0]}
    conflicted = sorted({line.split("\t", 1)[1] for line in lines[1:]
                         if re.match(r"^\d{6} [0-9a-f]{40} [123]\t\S*$", line)})
    return {"mergeable": merge.returncode == 0,
            "tree": lines[0],
            "conflicted": conflicted,
            "conflicted_in_docs": [path for path in conflicted
                                   if path.startswith("docs/")]}


def promotion_shape(sha: str, stable_branch: str = "origin/master",
                    development_branch: str = "origin/develop") -> dict:
    """Which merge the candidate is, in the #1798 promotion model.

    A release candidate is the merge commit of a develop -> master release pull
    request: its first parent is reachable from ``master`` and its second from
    ``develop``. Naming the shape matters because a rehearsal of the wrong merge -
    an ordinary pull-request merge into ``develop`` - builds the same kind of tree
    but is not the commit a release would stand on, and a report that called the
    two alike would be a report that could not be reviewed.
    """
    parents = git("rev-list", "--parents", "-n", "1", sha).split()[1:]

    def reachable(rev: str, ref: str) -> bool | None:
        probe = subprocess.run(["git", "merge-base", "--is-ancestor", rev, ref],
                               cwd=str(ROOT), capture_output=True, text=True)
        if probe.returncode == 0:
            return True
        if probe.returncode == 1:
            return False
        return None  # the ref is not in this checkout: unknown, not false

    return {"parents": len(parents),
            "first_parent_in_stable": (reachable(parents[0], stable_branch)
                                       if parents else None),
            "last_parent_in_development": (reachable(parents[-1], development_branch)
                                           if len(parents) > 1 else None)}


def export_tree(sha: str, destination: Path) -> Path:
    """The candidate's tree, exported rather than checked out.

    ``git archive`` is the whole isolation story: the build reads the candidate's
    files, never this working tree's, and the repository is left untouched - no
    checkout, no stash, no detached HEAD a parallel worker could inherit.
    """
    destination.mkdir(parents=True, exist_ok=True)
    pack = subprocess.run(["git", "archive", sha], cwd=str(ROOT),
                          capture_output=True)
    if pack.returncode != 0:
        raise HarnessError(f"git archive {sha[:12]}: "
                           f"{pack.stderr.decode(errors='replace').strip()[:300]}")
    unpack = subprocess.run(["tar", "-x", "-C", str(destination)],
                            input=pack.stdout, capture_output=True)
    if unpack.returncode != 0:
        raise HarnessError(
            f"could not unpack the export of {sha[:12]}: "
            f"{unpack.stderr.decode(errors='replace').strip()[:300]}")
    return destination


def push_url(repository: str) -> str:
    """Credential-free remote URL: the credential is the caller's git helper or
    its exported token, never a password inside a URL."""
    return f"https://github.com/{repository}.git"


# ------------------------------------------------------------------ sphinx ---
def docs_interpreter(explicit: str = "") -> tuple[str | None, str, bool]:
    """The interpreter that can import the pinned Sphinx, or why none can.

    Three answers, mirroring ``test_docs_build._sphinx_interpreter`` because the
    distinction matters more here: a rehearsal that skipped its build for want of
    a venv would still print a report, and a report nobody can tell apart from a
    rehearsal is worse than no report.
    """
    named = (explicit or os.environ.get("MRMAP_DOCS_PYTHON", "")).strip()
    if named:
        if not Path(named).exists():
            return None, f"{named} does not exist", True
        probe = subprocess.run([named, "-c", "import sphinx"],
                               capture_output=True, text=True)
        if probe.returncode != 0:
            tail = probe.stderr.strip().splitlines()
            return (None, f"{named} cannot import sphinx: "
                          f"{tail[-1] if tail else 'no output'}", True)
        return named, "", False
    probe = subprocess.run([sys.executable, "-c", "import sphinx"],
                           capture_output=True, text=True)
    if probe.returncode == 0:
        return sys.executable, "", False
    return None, ("no Sphinx on this interpreter (install "
                  "backend/.requirements/docs.txt, or name one with "
                  "MRMAP_DOCS_PYTHON / --docs-python)"), False


def portal_source(tree: Path) -> str:
    """The portal's source directory inside an exported tree, or ``""``."""
    return "docs/source" if (tree / "docs" / "source" / "conf.py").is_file() else ""


def conf_needs_application(tree: Path, source: str) -> bool:
    """Does this candidate's ``conf.py`` import the application to build?

    True means the tree predates #1597 and cannot be built by the pinned docs
    environment at all - a harness problem to report, not a docs failure to gate.
    """
    conf = tree / Path(*source.split("/")) / "conf.py"
    return bool(re.search(r"^\s*(?:import|from) django\b",
                          conf.read_text(encoding="utf-8"), re.MULTILINE))


def strict_build(interpreter: str, tree: Path, source: str, out: Path,
                 doctrees: Path, flags: list[str],
                 revision: str = "") -> tuple[int, str, float]:
    """Run the committed strict build against one exported tree.

    ``revision`` is handed to the build through ``MRMAP_DOCS_REVISION``, the knob
    ``docs/source/_ext/mrmap_docs.py`` offers for exactly this: an exported tree
    is not a checkout, so ``git rev-parse`` there cannot name the revision and
    provenance would record null. CI names it with ``GITHUB_SHA``; a rehearsal
    names it with the SHA it exported, which is the same act. It is not a way to
    fake the identity check - a tree whose extension does not honour the variable
    records something else and the check goes red.
    """
    environment = dict(os.environ)
    if revision:
        environment["MRMAP_DOCS_REVISION"] = revision
        # GITHUB_SHA wins inside the extension, and on a runner it names this
        # job's checkout rather than the exported candidate: drop it so the
        # rehearsal records the SHA it actually built.
        environment.pop("GITHUB_SHA", None)
    started = time.monotonic()
    process = subprocess.run(
        [interpreter, "-m", "sphinx", *flags, "-d", str(doctrees),
         str(tree / Path(*source.split("/"))), str(out)],
        cwd=str(tree), capture_output=True, text=True, env=environment)
    return (process.returncode,
            (process.stdout or "") + (process.stderr or ""),
            round(time.monotonic() - started, 2))


MISSING_ENTRY = "rehearsal-missing-page"


def inject_fault(tree: Path, source: str) -> str:
    """Add one minimal fault to an exported tree and describe it.

    The same fault class ``test_docs_build._write_fixtures`` uses - a toctree
    entry naming no document - because that is what a real release candidate
    produces when a page is renamed: the build still writes its pages, and only
    ``-W`` turns that into a refusal. The entry goes into the **first real
    toctree block**, not simply after the first indented line: the landing page
    opens with an RST comment block whose continuation lines are indented, and
    editing one of those warns about nothing.
    """
    index = tree / Path(*source.split("/")) / "index.rst"
    if not index.is_file():
        raise HarnessError(f"{source} has no index.rst to break")
    lines = index.read_text(encoding="utf-8").splitlines()
    target = None
    in_toctree = False
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped == ".. toctree::" or stripped.endswith(":toctree::"):
            in_toctree = True
            continue
        if in_toctree:
            if not stripped:
                continue
            if stripped.startswith(":"):
                continue
            if line[:1].isspace():
                target = number
                break
            in_toctree = False
    if target is None:
        lines.extend(["", ".. toctree::", "", f"   {MISSING_ENTRY}", ""])
        index.write_text("\n".join(lines), encoding="utf-8")
        return f"an added toctree naming only '{MISSING_ENTRY}'"
    lines.insert(target, "   " + MISSING_ENTRY)
    index.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return (f"a toctree entry '   {MISSING_ENTRY}' inserted beside the real "
            f"entry '{lines[target + 1].strip()}'")


def read_provenance(out: Path) -> dict:
    path = out / "provenance.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise HarnessError(f"provenance.json of the build is not JSON: {error}")


# -------------------------------------------------------------------- http ---
def http_json(url: str, token: str = "") -> tuple[int, str]:
    """Status and body of one GET. A 404 is a fact, not an exception."""
    headers = {"User-Agent": "mrmap-docs-rehearsal/1 (#1610)",
               "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                    timeout=30) as answer:
            return answer.status, answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HarnessError(f"GET {url} failed: {error}")


def head_url(url: str, redirects: int = 5) -> dict:
    """Status and headers of one URL, following redirects, without the body."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise HarnessError(f"{url} is not an http(s) URL")
    host, path = parts.netloc, (parts.path or "/")
    if parts.query:
        path += "?" + parts.query
    seen = 0
    status, headers = 0, {}
    while True:
        connection = (http.client.HTTPSConnection(host, timeout=30)
                      if parts.scheme == "https"
                      else http.client.HTTPConnection(host, timeout=30))
        try:
            connection.request("HEAD", path, headers={
                "User-Agent": "mrmap-docs-rehearsal/1 (#1610)"})
            answer = connection.getresponse()
            answer.read()
            status = answer.status
            headers = dict(answer.getheaders())
        finally:
            connection.close()
        if status not in (301, 302, 303, 307, 308) or seen >= redirects:
            break
        location = headers.get("Location") or headers.get("location")
        if not location:
            break
        parts = urllib.parse.urlsplit(urllib.parse.urljoin(url, location))
        host, path = parts.netloc, (parts.path or "/")
        if parts.query:
            path += "?" + parts.query
        url = urllib.parse.urljoin(url, location)
        seen += 1
    return {"url": url, "status": status,
            "headers": {k.lower(): v for k, v in headers.items()}}


def probe_host(site: str) -> dict:
    """What the managed host says about itself right now, as observed facts.

    Nothing is asserted beyond "the site answers": the point of the probe is to
    record what the configuration an administrator sets actually produced, which
    is the half of this issue no committed file can hold.
    """
    observed: dict = {"site": site, "requested": []}
    for path in ("", "/en/stable/", "/en/latest/"):
        try:
            answer = head_url(site.rstrip("/") + path)
        except HarnessError as error:
            observed["requested"].append(
                {"url": site.rstrip("/") + path, "error": str(error)})
            continue
        observed["requested"].append({
            "requested": site.rstrip("/") + path, "url": answer["url"],
            "status": answer["status"],
            "headers": {k: v for k, v in answer["headers"].items()
                        if k.startswith(("x-rtd", "server", "via", "content-type"))}})
    answered = [item for item in observed["requested"] if "status" in item]
    observed["answers"] = any(item["status"] == 200 for item in answered)
    observed["has_stable_version"] = any(
        item["status"] == 200 and "/en/stable" in item["url"] for item in answered)
    # Only a 200 counts as a served version: the host answers a request for an
    # inactive version with x-rtd-version set and a 404 body, and reading that as
    # "stable exists" is exactly the false green this probe exists to avoid.
    observed["served_versions"] = sorted({
        item["headers"]["x-rtd-version"] for item in answered
        if item["status"] == 200 and item["headers"].get("x-rtd-version")})
    observed["unknown_versions"] = sorted({
        item["headers"].get("x-rtd-version", "?") for item in answered
        if item["status"] != 200 and item["headers"].get("x-rtd-version")})
    observed["served_by"] = sorted({item["headers"]["server"] for item in answered
                                    if item["headers"].get("server")})
    observed["managed_by_readthedocs"] = any(
        item["headers"].get("x-rtd-project") for item in answered)
    return observed


def check_runs_of(sha: str, repository: str) -> list[dict]:
    """The Actions check runs of a commit, with the URLs a reviewer can open."""
    status, body = http_json(f"{GITHUB_API}repos/{repository}/commits/{sha}"
                             "/check-runs?per_page=100",
                             os.environ.get("GITHUB_TOKEN", ""))
    if status != 200:
        raise HarnessError(f"the check runs of {sha[:12]} answered {status}")
    return [{"name": run.get("name"), "status": run.get("status"),
             "conclusion": run.get("conclusion"), "url": run.get("html_url")}
            for run in json.loads(body).get("check_runs", [])]


def hosted_site(candidate_tree: Path) -> str:
    """The documentation URL the *candidate* publishes in its image metadata."""
    image_release = candidate_tree / "scripts" / "image_release.py"
    if not image_release.is_file():
        return ""
    match = re.search(r'"documentation":\s*"(https://[^"]+)"',
                      image_release.read_text(encoding="utf-8"))
    return match.group(1) if match else ""


# -------------------------------------------------------------- workflows ---
def workflow_texts(tree: Path) -> dict[str, str]:
    directory = tree / WORKFLOWS
    if not directory.is_dir():
        return {}
    return {path.name: path.read_text(encoding="utf-8")
            for path in sorted(directory.glob("*.yml"))}


def workflow_findings(workflows: dict[str, str]) -> tuple[list[str], list[str]]:
    """``(force_pushers, pages_deployers)`` of a candidate's workflows.

    The two prohibitions ``test_docs_build`` holds for the working tree, applied
    to the candidate: a publisher appearing between the reviewed build and the
    tag is exactly what a rehearsal should catch.
    """
    force_pushers = [name for name, body in workflows.items()
                     if "gh-pages" in body
                     and re.search(r"git push[^\n]*(--force|-f)\b", body)]
    deployers: list[str] = []
    for name, body in workflows.items():
        jobs = re.split(r"(?m)^jobs:\s*$", body, maxsplit=1)
        if len(jobs) < 2:
            continue
        for job in re.findall(r"^  ([A-Za-z0-9_-]+):\s*$", jobs[1], re.MULTILINE):
            if re.search(r"pages|deploy", job, re.IGNORECASE):
                deployers.append(f"{name}:{job}")
    return force_pushers, deployers


# --------------------------------------------------------------- promote ---
def promote(sha: str, tag: str, repository: str, lifecycle_text: str) -> dict:
    """Publish one rehearsal tag, read it back, return what happened.

    Guarded three ways, because this is the only act on shared infrastructure the
    tool performs: the caller names the tag, the name has to be a rehearsal name
    (``is_rehearsal_tag`` refuses the release policy's own pattern), and the
    environment has to name the same tag again. Publishing a *release* tag is not
    this tool's decision to make in any mode - #1801 authorises real tags.
    """
    if not is_rehearsal_tag(tag, lifecycle_text):
        raise RuleViolation(
            f"--promote refuses {tag!r}: only names under {REHEARSAL_TAG_PREFIX} "
            f"are rehearsals, and {release_tag_pattern(lifecycle_text)} belongs "
            f"to the release process")
    authorised = os.environ.get(PROMOTE_ENVIRONMENT, "").strip()
    if authorised != tag:
        raise RuleViolation(
            f"{PROMOTE_ENVIRONMENT} is not set to {tag!r}: publishing a tag is an "
            f"act on shared infrastructure and is authorised in the environment, "
            f"not on the command line")
    git("tag", "-f", "-a", tag, sha, "-m", f"docs rehearsal of {sha[:12]} (#1610)")
    remote = push_url(repository)
    pushed = git("push", remote, f"refs/tags/{tag}:refs/tags/{tag}")
    listed = git("ls-remote", remote, f"refs/tags/{tag}").split("\t")[0].strip()
    status, body = http_json(f"{GITHUB_API}repos/{repository}/git/refs/tags/{tag}",
                             os.environ.get("GITHUB_TOKEN", ""))
    return {"tag": tag, "target": sha, "push_output": pushed.strip(),
            "ls_remote_sha": listed, "api_status": status,
            "api_url": f"{GITHUB_API}repos/{repository}/git/refs/tags/{tag}",
            "api_response": json.loads(body) if status == 200 else body[:400]}


# ---------------------------------------------------------------- evidence ---
def write_evidence(path: Path, report: dict, root: Path = ROOT) -> Path:
    assert_writable_evidence(path, root)
    if not report.get("checks"):
        raise HarnessError("an empty results list is never a rehearsal: nothing "
                           "was checked, so nothing may be reported as one")
    resolved = path if path.is_absolute() else (root / path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return resolved


def build_report(sha: str, host: dict, promote_tag: str, site: str,
                 gate_only: bool, shape: dict | None = None,
                 isolated_equivalent: str = "",
                 promotion_merge: dict | None = None) -> dict:
    return {
        "schema": EVIDENCE_SCHEMA,
        "issue": ISSUE,
        "parent": PARENT_EPIC,
        # A report that cannot say when it ran cannot be re-checked: the hosted
        # state it records is a measurement of a service, not of a commit.
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": "gate-only" if gate_only else "managed-host",
        "candidate_sha": sha,
        "candidate_is_merge_commit": is_merge_commit(sha),
        "promotion_merge_shape": shape,
        "promotion_merge_of_branches": promotion_merge,
        "isolated_equivalent_reason": isolated_equivalent or None,
        "hosted_site": site,
        "host": host,
        "promoted_tag": promote_tag or None,
        "promote_authorised_by": PROMOTE_ENVIRONMENT if promote_tag else None,
        "commands": COMMANDS,
        "toolchain": {"python": sys.version.split()[0],
                      "docs_python": os.environ.get("MRMAP_DOCS_PYTHON", "")},
        "checks": RESULTS,
        "measurements": MEASUREMENTS,
        "limitations": LIMITATIONS,
    }


def history_checks(sha: str, repository: str, skip_host_probe: bool,
                   isolated_equivalent: str, shape: dict,
                   promotion_merge: dict) -> None:
    """Is this candidate history a release could stand on, and who reviewed it?

    A function, because it runs on the early return too: a rehearsal whose build
    could not start still owes the reader whether the candidate is the promotion
    merge, reachable on the remote, and green in Actions.
    """
    print("\nthe candidate as release history, and the runs that reviewed it")
    measure("candidate shape", json.dumps(shape, sort_keys=True), "merge",
            "parents / first parent on master / last parent on develop")
    measure("develop -> master merge today", promotion_merge["mergeable"], "bool",
            f"{len(promotion_merge.get('conflicted', []))} conflicted path(s), "
            f"{len(promotion_merge.get('conflicted_in_docs', []))} of them docs")
    if promotion_merge["mergeable"] is not True:
        limit("no promotion merge commit exists yet: git reports the "
              "develop -> master merge "
              f"{'unreadable' if promotion_merge['mergeable'] is None else 'conflicted'}"
              f"{': ' + ', '.join(promotion_merge['conflicted_in_docs'])
               if promotion_merge.get('conflicted_in_docs') else ''}, so #1798 has "
              "no merge SHA to build and this rehearsal can only be of an isolated "
              "equivalent")
    if isolated_equivalent:
        print(f"  note  not a promotion merge, by declaration: {isolated_equivalent}")
        limit(f"the candidate is not the merge commit of a develop -> master "
              f"release pull request; it is an isolated equivalent because "
              f"{isolated_equivalent}. The gate result transfers to the promotion "
              f"merge of the same docs content; the hosting result does not "
              f"extend to a tag that does not exist yet")
    else:
        check("the candidate is a develop -> master promotion merge (#1798)",
              (shape["parents"] > 1 and shape["first_parent_in_stable"] is True
               and shape["last_parent_in_development"] is True),
              f"shape {json.dumps(shape, sort_keys=True)}: pass "
              f"--isolated-equivalent to rehearse a different commit and say why")
    status, body = http_json(f"{GITHUB_API}repos/{repository}/commits/{sha}",
                             os.environ.get("GITHUB_TOKEN", ""))
    reachable = status == 200 and json.loads(body).get("sha") == sha
    measure("candidate reachable on GitHub", reachable, "bool",
            f"commits API answered {status}")
    if skip_host_probe or isolated_equivalent:
        # A gate-only rehearsal, and an isolated equivalent of a promotion merge
        # that has no upstream yet, both run legitimately on history CI has never
        # seen; failing that would discourage the pre-promotion check the gate
        # exists to encourage.
        print(f"  note  candidate reachable on GitHub: {reachable} - local "
              f"history is legitimate for this kind of rehearsal")
        if not reachable:
            limit(f"{sha[:12]} is not reachable on {repository}: a rehearsal tag "
                  f"on it would be an orphan, and #1798 could never have built it")
    else:
        check("the candidate is reachable on GitHub, so a tag on it is history",
              reachable, f"the commits API answered {status} for {sha}")
    if not reachable and (skip_host_probe or isolated_equivalent):
        # A local rehearsal of unpushed history has no Actions record to read;
        # asking for one would discourage running the gate before promoting.
        print("  note  no Actions record asked for: unpushed history")
    else:
        try:
            runs = check_runs_of(sha, repository)
        except HarnessError as error:
            runs = []
            check("the Actions runs of the candidate were readable", False,
                  str(error))
        else:
            docs_runs = [run for run in runs
                         if "portal" in (run["name"] or "").lower()
                         or "documentation" in (run["name"] or "").lower()]
            measure("Actions check runs of the candidate", len(runs), "runs",
                    f"{len(docs_runs)} documentation run(s)")
            for run in docs_runs:
                print(f"  ..   {run['name']}: {run['status']}/{run['conclusion']} "
                      f"{run['url']}")
            green = [run for run in docs_runs if run["conclusion"] == "success"]
            check("the documentation job of the candidate is green",
                  bool(green),
                  ", ".join(f"{run['name']}={run['status']}/{run['conclusion']}"
                            for run in docs_runs)
                  or "no documentation check run for this SHA: the gate never ran "
                     "on it")
            # A red job the documentation rehearsal does not own - release
            # planning, a flake in another suite - is recorded rather than failed:
            # this is the docs rehearsal, and its verdict must not be held hostage
            # by an issue that has its own. What promotion must not do is ignore
            # it: #1798 binds publication to the required checks of the same SHA,
            # so a red here belongs in the report a release author reads.
            red = sorted({str(run["name"]) for run in runs
                          if run["conclusion"] not in (None, "success", "skipped",
                                                       "neutral")})
            measure("red Actions runs of the candidate", len(red), "jobs",
                    ", ".join(red) or "none")
            if red:
                limit(f"{', '.join(red)} is red on this candidate: outside the "
                      f"documentation rehearsal's scope, and promotion (#1798) "
                      f"still requires the checks of this SHA to be green")
    if not reachable:
        limit("the candidate is not reachable on GitHub: a rehearsal tag on it "
              "would be an orphan, so this rehearsal stays local")



# -------------------------------------------------------------------- main ---
def run_rehearsal(candidate: str, docs_python: str, out_dir: Path,
                  promote_tag: str, skip_host_probe: bool,
                  repository: str = REPOSITORY,
                  isolated_equivalent: str = "") -> dict:
    sha = resolve_candidate(candidate)
    kind = "merge" if is_merge_commit(sha) else "single-parent"
    shape = promotion_shape(sha)
    promotion_merge = promotion_merge_status()
    print(f"candidate {sha} ({kind} commit) of {repository}, from {ROOT}")

    gate_file = ROOT / WORKFLOWS / "docs.yml"
    if not gate_file.is_file():
        raise HarnessError(f"{WORKFLOWS}/docs.yml is not there to read the "
                           f"gate's flags from")
    flags = strict_flags(gate_file.read_text(encoding="utf-8"))
    measure("gate flags", " ".join(flags), "sphinx", "read from docs.yml")
    if "-W" not in flags or "--keep-going" not in flags:
        raise RuleViolation(f"the committed gate does not build with -W "
                            f"--keep-going: {flags}")

    with tempfile.TemporaryDirectory(prefix="mrmap-docs-rehearsal-") as tmp:
        base = Path(tmp)
        clean = export_tree(sha, base / "candidate")
        source = portal_source(clean)
        if not source:
            raise HarnessError(
                f"{sha[:12]} carries no portal at docs/source/conf.py: there is "
                f"nothing for the release gate of #1589 to judge")
        if conf_needs_application(clean, source):
            raise HarnessError(
                f"{sha[:12]} imports the application in conf.py, so it predates "
                f"#1597 and cannot be built by the pinned docs environment: name "
                f"a candidate that carries the portal build")

        print("\nthe candidate's own contracts")
        readthedocs = clean / ".readthedocs.yaml"
        rtd = (readthedocs.read_text(encoding="utf-8")
               if readthedocs.is_file() else "")
        check("the candidate carries the managed-host configuration",
              bool(rtd) and "fail_on_warning: true" in rtd)
        check("the candidate builds the hosted site from the single docs pin file",
              DOCS_REQUIREMENTS in rtd and (clean / DOCS_REQUIREMENTS).is_file())
        declared = "\n".join(line for line in rtd.splitlines()
                             if not line.lstrip().startswith("#"))
        check("the candidate declares no second package source for the hosted build",
              "apt_packages" not in declared and "pip install" not in declared)
        check("the candidate has no repository-owned publisher",
              not (clean / "docs" / "publish_docs.sh").exists())
        workflows = workflow_texts(clean)
        force_pushers, deployers = workflow_findings(workflows)
        check("the candidate force-pushes no Pages branch", not force_pushers,
              ", ".join(force_pushers))
        check("the candidate deploys no Pages site beside the managed service",
              not deployers, ", ".join(deployers))
        ordinary = ordinary_traffic_generators(workflows)
        check("no ordinary pull request or develop push triggers full generation",
              not ordinary, "; ".join(ordinary))
        override = os.environ.get(HOST_ENVIRONMENT, "").strip()
        site = override or hosted_site(clean)
        if override:
            print(f"  note  {HOST_ENVIRONMENT} points the probe at the isolated "
                  f"project {site}")
            limit(f"the probe went to {site} named by {HOST_ENVIRONMENT}, an "
                  f"isolated managed project, not to the production site")
        check("the candidate names the site its image metadata publishes",
              bool(site), f"scripts/image_release.py names no documentation URL "
                          f"and {HOST_ENVIRONMENT} is unset")

        interpreter, why_unavailable, is_defect = docs_interpreter(docs_python)
        check("the pinned docs interpreter is available", not is_defect,
              why_unavailable)
        if interpreter is None:
            if is_defect:
                history_checks(sha, repository, skip_host_probe, isolated_equivalent,
                               shape, promotion_merge)
                return build_report(sha, {}, promote_tag, site, skip_host_probe,
                                    shape, isolated_equivalent, promotion_merge)
            raise HarnessError(
                f"the build cannot run: {why_unavailable}. Name the venv that "
                f"installed {DOCS_REQUIREMENTS} with --docs-python: a rehearsal "
                f"that skipped its build is not a rehearsal")

        print("\nthe native gate on the exact candidate")
        out_clean = out_dir / "html"
        code, log, seconds = strict_build(interpreter, clean, source, out_clean,
                                          base / "dt-clean", flags, revision=sha)
        pages = len(list(out_clean.glob("**/*.html")))
        measure("strict build of the candidate", code, "exit status",
                f"{seconds}s, {pages} pages")
        check("the strict build accepts the candidate with exit status 0",
              code == 0, f"exit {code}: {log.strip()[-500:]}")
        provenance = read_provenance(out_clean)
        check("the build recorded the candidate as what it documented",
              provenance.get("documented_commit") == sha,
              f"provenance says {provenance.get('documented_commit')!r}")
        # The same completeness the committed job asserts (docs.yml, "Assert the
        # build recorded its identity") - a rehearsal that checked less than CI
        # would report a weaker artifact as ready to publish.
        incomplete = [key for key in ("schema", "builder", "version", "release",
                                      "toolchain", "source_digest")
                      if not provenance.get(key)]
        check("the build recorded its toolchain and its source digest",
              not incomplete and bool(provenance.get("toolchain", {}).get("sphinx")),
              f"missing {incomplete or ['toolchain.sphinx']}: "
              f"{json.dumps(provenance)[:200]}")
        check("the accepted build wrote the artifact the gate is about",
              (out_clean / "index.html").is_file(), "no index.html")

        print("\nthe native gate refuses a broken candidate")
        broken = export_tree(sha, base / "broken")
        fault = inject_fault(broken, source)
        out_broken = out_dir / "html-broken"
        broken_code, broken_log, _ = strict_build(interpreter, broken, source,
                                                  out_broken, base / "dt-broken",
                                                  flags, revision=sha)
        refused_pages = len(list(out_broken.glob("**/*.html")))
        measure("strict build of the broken candidate", broken_code,
                "exit status", f"{fault}, {refused_pages} page(s) written")
        check("the injected fault is refused by the native exit status",
              broken_code != 0, f"exit {broken_code}: {broken_log.strip()[-400:]}")
        check("the failing build names the fault it found",
              MISSING_ENTRY in broken_log, broken_log.strip()[-400:])
        # The uncomfortable half of "a failed build prevents release": a refused
        # Sphinx build still writes its pages, so an artifact tells nobody
        # whether it was accepted. Publication - here or on the host - may key on
        # the exit status and on nothing else. This pins the behaviour that makes
        # that true: a refusal that wrote nothing would let an artifact-existence
        # check pass for a refused candidate, and a toolchain that stopped
        # writing on refusal would silently soften what the gate has to protect.
        check("the refusal is only visible in the exit status, which is why "
              "nothing else may gate publication",
              broken_code != 0 and refused_pages > 0,
              f"exit {broken_code} after writing {refused_pages} page(s)")
        limit("whether the managed host keeps serving the previous artifact "
              "after a refused build is a property of the service and is not "
              "observable without its API token; what is proven here is that "
              "the gate refuses the candidate, which is what prevents "
              "publication")

    print("\nthe managed host")
    host: dict = {}
    if skip_host_probe:
        # Stated rather than failed: a gate-only rehearsal is a legitimate thing
        # to run - it is what a contributor with no network reaches for - and it
        # must be readable as exactly that, in the report's `kind` and here.
        print("  note  --skip-host-probe: gate-only rehearsal, so this run says "
              "nothing about hosting")
        limit("the host was not probed (--skip-host-probe): served version, "
              "stable activation and redirect behaviour are unobserved here")
    else:
        if not site:
            raise HarnessError("there is no hosted site to probe: the candidate "
                               "names none and the override is unset")
        host = probe_host(site)
        measure("hosted site answers", host["answers"], "bool", site)
        measure("served versions", ",".join(host["served_versions"]) or "-",
                "versions")
        measure("stable version published", host["has_stable_version"], "bool")
        for item in host["requested"]:
            print(f"  ..   {item['url']} -> {item.get('status', item.get('error'))}")
        check("the hosted site answers", host["answers"], json.dumps(host)[:300])
        check("the hosted site is served by the managed service",
              host["managed_by_readthedocs"],
              "no x-rtd-* header: this is not a Read the Docs project")
        if not host["has_stable_version"]:
            limit("no stable version is published yet: the host activates a "
                  "SemVer tag by rule and the repository has never cut one - "
                  "#1801 authorises the first real release")
        limit("the host's automation rules, activation list, default version and "
              "redirect rows are administration settings a pull request cannot "
              "read; an administrator confirms them and they are recorded in "
              "docs/source/development/documentation-hosting.rst")
        limit("an asynchronous host build is not observable without the project "
              "API token, so what is recorded is the artifact the host serves "
              "rather than its build queue; a release must not claim an atomic "
              "publication")

    history_checks(sha, repository, skip_host_probe, isolated_equivalent,
                   shape, promotion_merge)

    if promote_tag:
        print("\npromotion of the rehearsal tag")
        lifecycle_text = (ROOT / LIFECYCLE).read_text(encoding="utf-8")
        if not reachable:
            check("the rehearsal tag was published", False,
                  f"{sha[:12]} is not reachable on GitHub")
        else:
            outcome = promote(sha, promote_tag, repository, lifecycle_text)
            measure("published tag", outcome["ls_remote_sha"] or "-", "sha",
                    outcome["tag"])
            check("the published tag points at the candidate",
                  outcome["ls_remote_sha"] == sha,
                  f"refs/tags/{outcome['tag']} -> {outcome['ls_remote_sha']!r}")
            check("the published tag is readable through the API",
                  outcome["api_status"] == 200,
                  f"{outcome['api_status']}: {str(outcome['api_response'])[:200]}")
            host["tag"] = outcome
    return build_report(sha, host, promote_tag, site, skip_host_probe, shape,
                        isolated_equivalent, promotion_merge)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rehearse the minimal documentation release and hosting of "
                    "#1610 against one exact candidate SHA.")
    parser.add_argument("--candidate", required=True,
                        help="the exact commit to build - the merge commit of a "
                             "develop -> master release pull request")
    parser.add_argument("--docs-python", default="",
                        help="interpreter with the pinned docs environment "
                             "(default: $MRMAP_DOCS_PYTHON, else this one)")
    parser.add_argument("--out", default="",
                        help="keep the built artifact under PATH (default: a "
                             "temporary directory this run removes)")
    parser.add_argument("--evidence-out", default=DEFAULT_EVIDENCE_PATH,
                        help="write the rehearsal report to PATH")
    parser.add_argument("--promote", metavar="TAG", default="",
                        help=f"publish TAG on the candidate; the name must start "
                             f"with {REHEARSAL_TAG_PREFIX} and be repeated in "
                             f"${PROMOTE_ENVIRONMENT}")
    parser.add_argument("--repository", default=REPOSITORY,
                        help="owner/repo to read the candidate and its runs from, "
                             "and to publish a rehearsal tag to")
    parser.add_argument("--skip-host-probe", action="store_true",
                        help="do not read the managed host: a gate-only "
                             "rehearsal, reported as one")
    parser.add_argument("--isolated-equivalent", metavar="WHY", default="",
                        help="rehearse a commit that is not the develop -> master "
                             "promotion merge, and record why it stands in for it")
    arguments = parser.parse_args()

    COMMANDS.append(" ".join(filter(None, (
        "python3 scripts/docs_release_rehearsal.py",
        f"--candidate {arguments.candidate}",
        f"--repository {arguments.repository}"
        if arguments.repository != REPOSITORY else "",
        f"--promote {arguments.promote}" if arguments.promote else "",
        "--skip-host-probe" if arguments.skip_host_probe else "",
        f"--isolated-equivalent {arguments.isolated_equivalent!r}"
        if arguments.isolated_equivalent else ""))))

    out_dir = Path(arguments.out) if arguments.out else Path(
        tempfile.mkdtemp(prefix="mrmap-docs-out-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = run_rehearsal(
            arguments.candidate, arguments.docs_python, out_dir,
            arguments.promote, arguments.skip_host_probe, arguments.repository,
            arguments.isolated_equivalent)
        path = write_evidence(Path(arguments.evidence_out), report)
    except RuleViolation as error:
        print(f"rule: {error}", file=sys.stderr)
        return 2
    except HarnessError as error:
        print(f"harness: {error}", file=sys.stderr)
        return 2

    failed = [item for item in RESULTS if not item["ok"]]
    print(f"\nwrote {path.relative_to(ROOT)}; "
          f"{len(RESULTS) - len(failed)} of {len(RESULTS)} check(s) passed; "
          f"artifact under {out_dir}")
    for item in failed:
        print(f"FAIL  {item['name']}\n      {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
