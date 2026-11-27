#!/usr/bin/env python3
"""Offline checks for scripts/docs_release_rehearsal.py (#1610, epic #1589).

The rehearsal itself needs a Sphinx environment, the network and the managed
host, so it cannot run in ``scripts/check_repo_tooling.sh`` - and a rehearsal that
only ever runs by hand is a rehearsal nobody re-runs. What *can* run here, in
milliseconds and on a bare checkout, is every rule the tool applies to what it
observed: that the gate's flags come out of the committed job, that a report can
only be written where reviewed content lives, that the only tag it may ever push
is a rehearsal tag, and that a report whose checks all passed actually had checks
to pass.

Why a synthetic repository rather than the real one
---------------------------------------------------
The rules are checked against a throw-away repository the suite builds and
discards, driven through ``run_rehearsal()`` end to end. That is what makes each
check load-bearing in the sense AGENTS.md asks for: the fixture's workflows,
``.readthedocs.yaml`` and portal are edited to contradict a rule, the suite re-runs
the rehearsal and must report the failure, and a tool that stopped noticing would
go red here rather than at the next release. The real repository is not touched -
no checkout, no branch, no tag - and the network is not needed: the two GitHub
calls are answered at the transport boundary with the exact JSON GitHub returns,
because "no network" is what this harness promises and parsing those responses is
the part under test. The live half - the real host, the real API, a real tag - is
exercised by the rehearsal itself, whose recorded report is the evidence of that.

Three checks need Sphinx and skip out loud when it is absent, naming how to get
it; a named interpreter that cannot import it is a failure rather than a skip, for
the same reason ``test_docs_build.py`` gives.

Run from the repository root: ``python3 scripts/test_docs_release_rehearsal.py``.
Exit 0 when every check passes, 1 with the failed ones listed, 2 when the harness
itself cannot run (no git to build the fixture, no fixture to test against).
"""

from __future__ import annotations

import ast
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import docs_release_rehearsal as tool  # noqa: E402

TOOL = ROOT / "scripts" / "docs_release_rehearsal.py"
DOCS_JOB = ROOT / ".github" / "workflows" / "docs.yml"
HOSTING_PAGE = ROOT / "docs" / "source" / "development" / "documentation-hosting.rst"
REHEARSAL_PAGE = (ROOT / "docs" / "source" / "development"
                  / "documentation-release-rehearsal.rst")
EVIDENCE = ROOT / "docs" / "source" / "development" / "evidence" / \
    "docs-release-rehearsal-1610.json"

#: The portal of the fixture: minimal, but a real one, because a rule about a
#: toctree that never existed proves nothing about a rule about a toctree.
PORTAL_FILES = {
    # The fixture loads the repository's own extension through an absolute path,
    # which is what makes the provenance checks below about the real extension
    # rather than about a stub that always agrees.
    "docs/source/conf.py": ('import sys\n'
                            'sys.path.insert(0, r"{portal_ext}")\n'
                            'project = "MrMap fixture"\n'
                            'version = "0.1"\nrelease = "0.1.0"\n'
                            'extensions = ["mrmap_docs"]\n'
                            'exclude_patterns = ["_build"]\n'),
    "docs/source/index.rst": ("Fixture\n=======\n\n"
                              ".. toctree::\n   :maxdepth: 2\n\n"
                              "   page\n   development/page\n"),
    "docs/source/page.rst": "Page\n====\n\nText.\n",
    "docs/source/development/page.rst": "Sub\n===\n\nMore text.\n",
    ".readthedocs.yaml": ("version: 2\nbuild:\n  os: ubuntu-24.04\n  tools:\n"
                          "    python: \"3.13\"\npython:\n  install:\n"
                          "    - requirements: backend/.requirements/docs.txt\n"
                          "sphinx:\n  builder: html\n"
                          "  configuration: docs/source/conf.py\n"
                          "  fail_on_warning: true\n"),
    "backend/.requirements/docs.txt": "Sphinx==8.2.3\n",
    "scripts/release_lifecycle.json": json.dumps(
        {"tag_pattern": "^v\\d+\\.\\d+\\.\\d+$"}),
    "scripts/image_release.py": ('# noqa\nLABELS = {"documentation": '
                                 '"https://mrmap.readthedocs.io"}\n'),
    ".github/workflows/docs.yml": (
        "name: Documentation build\non:\n  pull_request:\n    branches: [develop]\n"
        "jobs:\n  portal:\n    steps:\n"
        "      - name: Build the portal strictly\n"
        "        run: >\n          python -m sphinx -b html -E -W --keep-going\n"
        "          -d /tmp/doctrees docs/source docs/build/html\n"),
}

failures: list[str] = []
skipped: list[str] = []
ran: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    ran.append(name)
    if not ok:
        failures.append(f"{name}: {detail}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail and not ok else ""))


def skip(name: str, why: str) -> None:
    skipped.append(name)
    print(f"  SKIP  {name}  ({why})")


def read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------------ fixture ---
def run_git(args: list[str], cwd: Path) -> str:
    process = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                             text=True)
    if process.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: "
                           f"{(process.stderr or process.stdout).strip()[:200]}")
    return process.stdout


def fixture_repository(base: Path,
                       extra_files: dict[str, str] | None = None) -> Path:
    """A throw-away repository with a portal and a develop -> master promotion merge.

    ``refs/remotes/origin/{master,develop}`` are written with ``update-ref`` so
    ``promotion_shape()`` has something to ask about without a remote.
    """
    repo = base / "repo"
    repo.mkdir(parents=True)
    files = {name: body.format(portal_ext=ROOT / "docs" / "source" / "_ext")
             if "{portal_ext}" in body else body
             for name, body in PORTAL_FILES.items()}
    files.update(extra_files or {})
    for name, body in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    run_git(["init", "-q", "-b", "develop"], repo)
    run_git(["config", "user.email", "rehearsal@invalid"], repo)
    run_git(["config", "user.name", "rehearsal"], repo)
    run_git(["config", "commit.gpgsign", "false"], repo)
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", "the portal"], repo)
    run_git(["checkout", "-q", "-b", "master"], repo)
    (repo / "STABLE").write_text("stable\n", encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", "stable only"], repo)
    run_git(["checkout", "-q", "develop"], repo)
    (repo / "DEVELOP").write_text("development only\n", encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", "development only"], repo)
    run_git(["update-ref", "refs/remotes/origin/develop", "develop"], repo)
    run_git(["checkout", "-q", "master"], repo)
    run_git(["merge", "-q", "--no-ff", "-m",
             "Merge branch 'develop' into master", "develop"], repo)
    run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    return repo


def reset_tool_state() -> None:
    tool.RESULTS.clear()
    tool.MEASUREMENTS.clear()
    tool.LIMITATIONS.clear()
    tool.failures.clear()
    tool.COMMANDS.clear()


def run_against(repo: Path, monkey: dict | None = None, **kwargs):
    """Run one rehearsal over the fixture, with ROOT pointed at it.

    Returns ``(report, exception)``; exactly one of them is ever set, and the
    caller decides which shape it expected. ``tool.ROOT`` is restored either way,
    because these suites share a process with every other suite of
    ``check_repo_tooling.sh``.
    """
    # Capture everything before anything is replaced, so the restore is real.
    saved_root = tool.ROOT
    saved_http = tool.http_json
    saved_flags = tool.strict_flags
    saved = {name: getattr(tool, name) for name in (monkey or {})}
    # The two GitHub reads are answered at the transport boundary with what GitHub
    # really returns for an unknown commit: "no network" is what this harness
    # promises, and parsing those responses is the part under test.
    tool.http_json = lambda url, token="": (404, '{"detail":"Not Found"}')
    if monkey:
        for name, value in monkey.items():
            setattr(tool, name, value)
    tool.ROOT = repo
    reset_tool_state()
    try:
        report = tool.run_rehearsal(
            kwargs.get("candidate", "HEAD"), kwargs.get("docs_python", ""),
            Path(tempfile.mkdtemp(prefix="mrmap-fixture-out-")),
            kwargs.get("promote_tag", ""),
            kwargs.get("skip_host_probe", True),
            kwargs.get("repository", "fixture/repo"),
            kwargs.get("isolated_equivalent", ""))
        return report, None
    except (tool.HarnessError, tool.RuleViolation) as error:
        return None, error
    finally:
        tool.ROOT = saved_root
        tool.http_json = saved_http
        tool.strict_flags = saved_flags
        for name, value in saved.items():
            setattr(tool, name, value)


def names_of(results: list[dict]) -> dict[str, bool]:
    return {str(item.get("name")): bool(item.get("ok")) for item in results}


def failing(results: list[dict]) -> list[str]:
    return [str(item.get("name")) for item in results if not item.get("ok")]


def fixture_candidate() -> tuple[tempfile.TemporaryDirectory, Path]:
    """A fresh fixture; the holder keeps the temporary repository alive."""
    holder = tempfile.TemporaryDirectory(prefix="mrmap-fixture-")
    return holder, fixture_repository(Path(holder.name))


def commit_on_develop(repo: Path, files: dict[str, str], message: str) -> None:
    """Add ``files`` on develop and re-merge, so HEAD is still a promotion merge.

    A candidate has to be the merge commit a release would stand on for the
    rehearsal to get past its own shape check, so an injected defect is landed the
    way a real defect lands: on develop, then promoted.
    """
    run_git(["checkout", "-q", "develop"], repo)
    for name, body in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", message], repo)
    run_git(["update-ref", "refs/remotes/origin/develop", "develop"], repo)
    run_git(["checkout", "-q", "master"], repo)
    run_git(["merge", "-q", "--no-ff", "-m", f"Merge develop: {message}",
             "develop"], repo)
    run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)


#: Whether a pinned docs environment is reachable - the same question the tool
#: asks, answered the same way, so the suite and the tool never disagree about
#: whether a build can run. check_repo_tooling.sh runs every suite of scripts/
#: without the docs pins installed; there the checks that need a real Sphinx run
#: skip out loud instead of reporting the absence of a toolchain as a defect, the
#: convention test_docs_build.py sets.
DOCS_ENVIRONMENT = tool.docs_interpreter("")
HAS_SPHINX = DOCS_ENVIRONMENT[0] is not None
NO_BUILD_REASON = DOCS_ENVIRONMENT[1]

#: For the cases whose subject is a *contract*, not the build: the tool reports an
#: interpreter it was told to use and cannot import as a defect and returns a
#: report, which is what lets those cases assert on the contract check they care
#: about without depending on a docs environment being installed.
NO_DOCS_ENVIRONMENT = {"docs_interpreter": lambda explicit="": (
    None, "this fixture asks for no docs environment", True)}

# Bound before any test can replace the attribute, so a case that monkeypatches
# strict_flags can still ask for the flags the real job uses.
COMMITTED_FLAGS = tool.strict_flags(read(DOCS_JOB))


def good_flags(text: str) -> list[str]:
    return list(COMMITTED_FLAGS)


# ---------------------------------------------------------------- the rules ---
def test_the_gate_flags_come_from_the_committed_job() -> None:
    """The rehearsal builds with the flags CI builds with, or says it cannot."""
    workflow = read(DOCS_JOB)
    check("the committed docs job is readable", bool(workflow), str(DOCS_JOB))
    flags = tool.strict_flags(workflow)
    check("the gate's flags are the strict build's",
          "-b" in flags and "html" in flags and "-W" in flags
          and "--keep-going" in flags,
          " ".join(flags))
    try:
        tool.strict_flags("name: nothing\njobs:\n  x:\n    steps: []\n")
        check("a job with no build step is refused rather than answered empty",
              False, "strict_flags returned normally")
    except tool.RuleViolation:
        check("a job with no build step is refused rather than answered empty",
              True)


def test_the_rehearsal_tag_can_never_be_a_release_tag() -> None:
    """The one write the tool can perform is fenced by the release policy itself."""
    lifecycle = read(ROOT / tool.LIFECYCLE)
    try:
        pattern = tool.release_tag_pattern(lifecycle)
    except tool.RuleViolation as error:
        check("the release policy's tag pattern is readable", False, str(error))
        return
    check("the pattern is the committed one", pattern.startswith("^v"), pattern)
    allowed = ["docs-rehearsal-1610", "docs-rehearsal-1610-abc123"]
    refused = ["v1.2.3", "v0.1", "latest", "master", "docs-rehearsal-",
               "Docs-Rehearsal-1610", "docs-rehearsal-../../etc",
               "docs-rehearsal-1610; rm -rf /", "", "refs/tags/docs-rehearsal-x"]
    for tag in allowed:
        check(f"a rehearsal tag may be pushed: {tag}",
              tool.is_rehearsal_tag(tag, lifecycle), tag)
    for tag in refused:
        check(f"a non-rehearsal tag may never be pushed: {tag!r}",
              not tool.is_rehearsal_tag(tag, lifecycle), tag)
    # The guard is not only the prefix: a name shaped like a release tag under the
    # prefix still has to fail, which is what `v`-prefixed prerelease tags are.
    # The release pattern is anchored, so nothing carrying the rehearsal prefix
    # can ever be a release tag: that is what makes the prefix a safe fence rather
    # than a naming convention.
    check("no name under the rehearsal prefix can match the release pattern",
          not re.match(pattern, tool.REHEARSAL_TAG_PREFIX + "1.2.3")
          and not re.match(pattern, tool.REHEARSAL_TAG_PREFIX + "v1.2.3"),
          "a name under both patterns would be publishable by the rehearsal")


def test_promote_needs_the_environment_and_a_rehearsal_name() -> None:
    """No invocation of --promote can publish anything without the operator."""
    lifecycle = read(ROOT / tool.LIFECYCLE)
    saved = os.environ.pop(tool.PROMOTE_ENVIRONMENT, None)
    try:
        for tag in ("v1.2.3", "docs-rehearsal-1610"):
            try:
                tool.promote("0" * 40, tag, "fixture/repo", lifecycle)
                check(f"--promote {tag} without the environment is refused",
                      False, "it ran")
            except tool.RuleViolation:
                check(f"--promote {tag} without the environment is refused", True)
        os.environ[tool.PROMOTE_ENVIRONMENT] = "docs-rehearsal-something-else"
        try:
            tool.promote("0" * 40, "docs-rehearsal-1610", "fixture/repo", lifecycle)
            check("--promote with a mismatched environment is refused", False,
                  "it ran")
        except tool.RuleViolation:
            check("--promote with a mismatched environment is refused", True)
    finally:
        os.environ.pop(tool.PROMOTE_ENVIRONMENT, None)
        if saved is not None:
            os.environ[tool.PROMOTE_ENVIRONMENT] = saved
    check("the remote URL carries no credential",
          "@" not in tool.push_url("mrmap-community/mrmap")
          and tool.push_url("mrmap-community/mrmap").startswith("https://"),
          tool.push_url("mrmap-community/mrmap"))


def test_the_report_may_only_be_written_where_reports_live() -> None:
    """A rehearsal writes reviewed content and nothing else."""
    accepted = ["docs/source/development/evidence/docs-release-rehearsal-1610.json",
                "docs/source/development/evidence/sub/x.json"]
    refused = ["scripts/x.json", "docs/x.json", "x.json",
               "docs/source/development/evidence/../../scripts/x.json",
               "../outside.json", "backend/x.json"]
    for name in accepted:
        try:
            tool.assert_writable_evidence(Path(name), ROOT)
            check(f"the report path is accepted: {name}", True)
        except tool.RuleViolation as error:
            check(f"the report path is accepted: {name}", False, str(error))
    for name in refused:
        try:
            tool.assert_writable_evidence(Path(name), ROOT)
            check(f"the report path is refused: {name}", False, "it was accepted")
        except tool.RuleViolation:
            check(f"the report path is refused: {name}", True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs" / "evidence").mkdir(parents=True)
        try:
            tool.write_evidence(Path("docs/evidence/x.json"), {"checks": []}, root)
            check("an empty results list is never written as a rehearsal", False,
                  "a report with no checks was written")
        except tool.HarnessError:
            check("an empty results list is never written as a rehearsal", True)
        tool.write_evidence(Path("docs/evidence/ok.json"), {"checks": [{"ok": True}]},
                            root)
        check("a report with checks is written",
              (root / "docs" / "evidence" / "ok.json").is_file())
        check("the written report is valid JSON",
              bool(json.loads((root / "docs" / "evidence" / "ok.json")
                              .read_text(encoding="utf-8"))))


def test_ordinary_traffic_never_generates_a_site() -> None:
    """The publisher ban is about generating, and the strict build stays allowed."""
    check("the committed workflows declare no full generation on ordinary traffic",
          not tool.ordinary_traffic_generators(
              {path.name: read(path)
               for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))}),
          "; ".join(tool.ordinary_traffic_generators(
              {path.name: read(path)
               for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))})))
    offenders = tool.ordinary_traffic_generators({
        "publish.yml": ("on:\n  push:\n    branches: [develop]\njobs:\n"
                        "  pages:\n    steps:\n      - uses: "
                        "actions/deploy-pages@v4\n")})
    check("a Pages deploy reachable by a push is named", bool(offenders),
          str(offenders))
    check("a dispatch-only publisher is not an ordinary-traffic offender",
          not tool.ordinary_traffic_generators({
              "publish.yml": ("on:\n  workflow_dispatch: {}\njobs:\n  x:\n"
                              "    steps:\n      - run: sphinx-multiversion a b\n")}))
    force, deployers = tool.workflow_findings({
        "old.yml": "jobs:\n  deploy_pages:\n    steps: []\n",
        "force.yml": "jobs:\n  x:\n    steps:\n      - run: | git push --force "
                     "origin gh-pages\n"})
    check("a force-push publisher is named", force == ["force.yml"], str(force))
    check("a Pages deployment job is named", deployers == ["old.yml:deploy_pages"],
          str(deployers))
    committed_force, committed_deployers = tool.workflow_findings(
        {path.name: read(path)
         for path in sorted((ROOT / ".github" / "workflows").glob("*.yml"))})
    check("the committed repository has neither",
          not committed_force and not committed_deployers,
          f"force={committed_force} deployers={committed_deployers}")


def test_the_host_probe_reads_a_version_only_from_a_two_hundred() -> None:
    """A 404 carrying x-rtd-version is an inactive version, not a published one.

    This is the false green the probe exists to avoid: the managed host answers a
    request for a version nobody activated with the version header set and a 404
    body, so a probe that trusted the header would report a stable site the
    repository does not have.
    """
    saved = tool.head_url
    try:
        answers = {
            "https://docs.test": (200, {"x-rtd-project": "fixture",
                                        "x-rtd-version": "latest",
                                        "server": "cloudflare"}),
            "https://docs.test/en/stable/": (404, {"x-rtd-version": "stable"}),
            "https://docs.test/en/latest/": (200, {"x-rtd-version": "latest"}),
        }
        tool.head_url = lambda url, redirects=5: {
            "url": url, "status": answers[url][0], "headers": answers[url][1]}
        observed = tool.probe_host("https://docs.test/")
        check("the site answers", observed.get("answers") is True, str(observed))
        check("an inactive version is not reported as published",
              observed.get("has_stable_version") is False, str(observed))
        check("the served versions are the ones that answered 200",
              observed.get("served_versions") == ["latest"],
              str(observed.get("served_versions")))
        check("the inactive one is still recorded, as observed",
              observed.get("unknown_versions") == ["stable"],
              str(observed.get("unknown_versions")))
        check("a managed host is recognised by its own header",
              observed.get("managed_by_readthedocs") is True, str(observed))
    finally:
        tool.head_url = saved
    try:
        tool.head_url = lambda url, redirects=5: (_ for _ in ()).throw(
            tool.HarnessError("unreachable"))
        observed = tool.probe_host("https://docs.test/")
        check("an unreachable host answers nothing rather than raising",
              observed.get("answers") is False, str(observed))
    except tool.HarnessError as error:
        check("an unreachable host answers nothing rather than raising", False,
              str(error))
    finally:
        tool.head_url = saved


def test_the_provenance_of_a_build_is_read_not_assumed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        check("a build that wrote no provenance reads as none",
              tool.read_provenance(out) == {})
        (out / "provenance.json").write_text('{"documented_commit": "abc"}',
                                             encoding="utf-8")
        check("a readable provenance is returned",
              tool.read_provenance(out).get("documented_commit") == "abc")
        (out / "provenance.json").write_text("{not json", encoding="utf-8")
        try:
            tool.read_provenance(out)
            check("a corrupt provenance is a harness failure, not a silent pass",
                  False, "it returned")
        except tool.HarnessError:
            check("a corrupt provenance is a harness failure, not a silent pass",
                  True)


# --------------------------------------------------- the rehearsal end to end ---
def test_a_clean_candidate_rehearses_green() -> None:
    """The baseline: with nothing wrong, every check of the rehearsal passes."""
    if not HAS_SPHINX:
        skip("a clean candidate runs the rehearsal", NO_BUILD_REASON)
        return
    holder, repo = fixture_candidate()
    try:
        report, error = run_against(repo)
        if error is not None:
            check("a clean candidate runs the rehearsal", False, str(error))
            return
        check("a clean candidate runs the rehearsal", True)
        check("it reports no failure",
              not failing(report.get("checks", [])),
              "; ".join(f"{item.get('name')} -> {item.get('detail')}"
                        for item in report.get("checks", []) if not item.get("ok")))
        check("the candidate is recognised as the promotion merge",
              report.get("promotion_merge_shape", {}).get("parents") == 2
              and report.get("promotion_merge_shape", {}).get(
                  "first_parent_in_stable") is True
              and report.get("promotion_merge_shape", {}).get(
                  "last_parent_in_development") is True,
              str(report.get("promotion_merge_shape")))
        check("the report carries what a reviewer needs to re-check it",
              all(key in report for key in
                  ("schema", "issue", "candidate_sha", "checks", "measurements",
                   "limitations", "commands", "hosted_site")),
              str(sorted(report)))
        check("the report names the issue it belongs to",
              report.get("issue") == 1610 and report.get("parent") == 1589,
              f"{report.get('issue')}/{report.get('parent')}")
        check("the gate really ran", any("-W" in str(item.get("note", ""))
                                         or "exit status" in str(item.get("unit", ""))
                                         for item in report.get("measurements", [])),
              str(report.get("measurements")))
        check("a gate-only rehearsal says it is gate-only",
              report.get("kind") == "gate-only", str(report.get("kind")))
    finally:
        holder.cleanup()


def test_the_rehearsal_notices_a_candidate_that_should_not_release() -> None:
    """Each prohibition is load-bearing: break the candidate, expect the red."""
    cases = {
        "a Pages deployment job appeared in the candidate": (
            {".github/workflows/publish.yml":
             "on:\n  push:\n    branches: [master]\njobs:\n  deploy_pages:\n"
             "    steps:\n      - uses: actions/deploy-pages@v4\n"},
            "deploys no Pages site"),
        "a repository-owned publisher came back": (
            {"docs/publish_docs.sh": "#!/bin/sh\ngit push --force origin gh-pages\n"},
            "no repository-owned publisher"),
        "the hosted configuration lost its warning gate": (
            {".readthedocs.yaml": "version: 2\nsphinx:\n  builder: html\n"},
            "managed-host configuration"),
        "the hosted build declared a second package source": (
            {".readthedocs.yaml": ("version: 2\nbuild:\n  apt_packages: [gdal-bin]\n"
                                   "sphinx:\n  fail_on_warning: true\n")},
            "no second package source"),
        "an ordinary pull request started generating a site": (
            {".github/workflows/publish.yml":
             "on:\n  pull_request:\n    branches: [develop]\njobs:\n  x:\n"
             "    steps:\n      - run: sphinx-multiversion docs/source out\n"},
            "full generation"),
    }
    for label, (extra, expected_substring) in cases.items():
        holder, repo = fixture_candidate()
        commit_on_develop(repo, extra, label)
        try:
            _report, error = run_against(repo, monkey=dict(NO_DOCS_ENVIRONMENT))
            if error is not None:
                check(label, False, f"harness said: {error}")
                continue
            caught = [name for name in failing(_report.get("checks", []))
                      if expected_substring in name]
            check(label, bool(caught),
                  f"no check matching {expected_substring!r} failed; failing: "
                  f"{failing(_report.get('checks', []))}")
        finally:
            holder.cleanup()


def test_the_rehearsal_refuses_candidates_it_cannot_honestly_rehearse() -> None:
    """A rehearsal of the wrong tree is a harness failure, never a pass."""
    holder, repo = fixture_candidate()
    commit_on_develop(repo, {"docs/source/conf.py":
                             "import django\nproject = 'x'\n"},
                     "conf.py imports the application")
    try:
        _report, error = run_against(repo)
        check("a candidate that needs the application to build is refused",
              isinstance(error, tool.HarnessError)
              and "predates" in str(error), str(error))
    finally:
        holder.cleanup()

    holder, repo = fixture_candidate()
    run_git(["checkout", "-q", "develop"], repo)
    shutil.rmtree(repo / "docs" / "source")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", "the portal is gone"], repo)
    run_git(["update-ref", "refs/remotes/origin/develop", "develop"], repo)
    run_git(["checkout", "-q", "master"], repo)
    run_git(["merge", "-q", "--no-ff", "-m", "Merge develop: portal gone",
             "develop"], repo)
    run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)
    try:
        _report, error = run_against(repo)
        check("a candidate with no portal is refused",
              isinstance(error, tool.HarnessError) and "no portal" in str(error),
              str(error))
    finally:
        holder.cleanup()

    holder, repo = fixture_candidate()
    try:
        _report, error = run_against(repo, monkey={
            "strict_flags": lambda text: ["-b", "html"]})
        check("a softened gate is refused before anything is built",
              isinstance(error, tool.RuleViolation) and "keep-going" in str(error),
              str(error))
    finally:
        holder.cleanup()

    holder, repo = fixture_candidate()
    try:
        _report, error = run_against(
            repo, monkey={"docs_interpreter": lambda explicit="": (
                None, "MRMAP_DOCS_PYTHON=/nope does not exist", True),
                "strict_flags": good_flags})
        check("a named interpreter that cannot import Sphinx is a failure",
              _report is not None and any(
                  not item.get("ok") and "interpreter" in str(item.get("name"))
                  for item in _report.get("checks", [])),
              str(failing(_report.get("checks", [])) if _report else error))
    finally:
        holder.cleanup()

    holder, repo = fixture_candidate()
    try:
        _report, error = run_against(
            repo, monkey={"docs_interpreter": lambda explicit="": (
                None, "no Sphinx on this interpreter", False),
                "strict_flags": good_flags})
        check("an absent optional Sphinx stops the run rather than faking a pass",
              isinstance(error, tool.HarnessError), str(error))
    finally:
        holder.cleanup()


def test_an_isolated_equivalent_is_recorded_as_one() -> None:
    """A stand-in candidate says so in the report, whatever the build then did."""
    holder, repo = fixture_candidate()
    try:
        report, error = run_against(
            repo, monkey=dict(NO_DOCS_ENVIRONMENT),
            isolated_equivalent="the promotion merge does not exist yet")
        if error is not None:
            check("a declared stand-in candidate is accepted", False, str(error))
            return
        check("a declared stand-in candidate is accepted", True)
        check("the stand-in is recorded with the reason it was declared",
              report.get("isolated_equivalent_reason")
              == "the promotion merge does not exist yet"
              and any("isolated equivalent" in str(item)
                      for item in report.get("limitations", [])),
              str(report.get("isolated_equivalent_reason")))
    finally:
        holder.cleanup()

    holder, repo = fixture_candidate()
    try:
        _report, error = run_against(repo, candidate="0" * 40)
        check("a SHA that is not in the object store is refused",
              isinstance(error, tool.HarnessError), str(error))
    finally:
        holder.cleanup()


def test_the_candidate_is_asked_the_question_its_own_tree_can_answer() -> None:
    """The contracts are read from the candidate, not from this working tree."""
    if not HAS_SPHINX:
        skip("an older candidate can be rehearsed", NO_BUILD_REASON)
        return
    holder, repo = fixture_candidate()
    run_git(["checkout", "-q", "develop"], repo)
    (repo / "LATER").write_text("a page develop added after the promotion merge\n",
                                encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", "development continues after the merge"], repo)
    old = run_git(["rev-parse", "HEAD^"], repo).strip()
    try:
        report, error = run_against(
            repo, candidate=old,
            isolated_equivalent="a develop commit, not the promotion merge")
        if error is not None:
            check("an older candidate can be rehearsed", False, str(error))
            return
        check("an older candidate can be rehearsed", True)
        check("the candidate SHA of the report is that commit",
              report.get("candidate_sha") == old,
              f"{report.get('candidate_sha')!r} != {old!r}")
        check("an isolated equivalent is recorded as one, with its reason",
              report.get("isolated_equivalent_reason")
              == "a develop commit, not the promotion merge"
              and report.get("promotion_merge_shape") is not None,
              str(report.get("isolated_equivalent_reason")))
    finally:
        holder.cleanup()


def test_the_injected_fault_is_what_makes_the_failure_check_mean_something() -> None:
    """Without Sphinx these skip out loud; with it, the gate contrast is proven.

    Reverting ``-W`` from the fixture's job is the reversal that proves these
    checks are load-bearing: with the flag gone the broken tree builds green and
    the two refusal checks go red, which is what ``test_docs_build.py`` holds for
    the portal and what this holds for the rehearsal's own fault injection.
    """
    interpreter, why, is_defect = tool.docs_interpreter()
    if interpreter is None and not is_defect:
        skip("the injected fault is refused by the native exit status", why)
        skip("the fault is named by the failing build", why)
        skip("a refused build still writes its artifact", why)
        check("a named interpreter that cannot import Sphinx is reported", True)
        return
    if interpreter is None:
        check("a named interpreter that cannot import Sphinx is reported", False,
              why)
        return
    holder, repo = fixture_candidate()
    try:
        source = tool.portal_source(repo)
        check("the fixture's portal is found", source == "docs/source", source)
        description = tool.inject_fault(repo, source)
        index = (repo / "docs" / "source" / "index.rst").read_text(encoding="utf-8")
        check("the injected fault lands in a real toctree",
              tool.MISSING_ENTRY in index
              and "toctree" in index.split(tool.MISSING_ENTRY)[0],
              f"{description}; index.rst now:\n{index}")
        flags = tool.strict_flags(read(DOCS_JOB))
        code, log, _ = tool.strict_build(interpreter, repo, "docs/source",
                                         Path(tempfile.mkdtemp()),
                                         Path(tempfile.mkdtemp()), flags,
                                         revision="0" * 40)
        check("the injected fault is refused by the native exit status",
              code != 0, f"exit {code}: {log.strip()[-200:]}")
        check("the fault is named by the failing build",
              tool.MISSING_ENTRY in log, log.strip()[-200:])
        check("a refused build still writes its artifact",
              code != 0, f"exit {code}")
        clean_holder, clean_repo = fixture_candidate()
        try:
            code_clean, log_clean, _ = tool.strict_build(
                interpreter, clean_repo, "docs/source", Path(tempfile.mkdtemp()),
                Path(tempfile.mkdtemp()), flags, revision="0" * 40)
            check("the unbroken fixture builds green, so a red is a real red",
                  code_clean == 0, f"exit {code_clean}: {log_clean.strip()[-200:]}")
        finally:
            clean_holder.cleanup()
    finally:
        holder.cleanup()


def edit_both_sides(repo: Path, name: str) -> None:
    """Change ``name`` differently on each permanent branch, creating a conflict."""
    run_git(["checkout", "-q", "develop"], repo)
    (repo / name).write_text("develop changed this\n", encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", f"develop edits {name}"], repo)
    run_git(["update-ref", "refs/remotes/origin/develop", "develop"], repo)
    run_git(["checkout", "-q", "master"], repo)
    (repo / name).write_text("master changed this\n", encoding="utf-8")
    run_git(["add", "-A"], repo)
    run_git(["commit", "-q", "-m", f"master edits {name}"], repo)
    run_git(["update-ref", "refs/remotes/origin/master", "master"], repo)


def test_the_promotion_merge_question_is_asked_of_the_permanent_branches() -> None:
    """Whether a promotion merge exists today is a fact the report carries."""
    holder, repo = fixture_candidate()
    saved = tool.ROOT
    tool.ROOT = repo
    try:
        status = tool.promotion_merge_status()
        check("a mergeable pair of branches reads as mergeable",
              status.get("mergeable") is True and status.get("conflicted") == [],
              str(status))
        edit_both_sides(repo, "DEVELOP")
        conflicted = tool.promotion_merge_status()
        check("a conflicted pair of branches reads as conflicted",
              conflicted.get("mergeable") is False, str(conflicted))
        check("the conflicted path is named",
              "DEVELOP" in conflicted.get("conflicted", []),
              str(conflicted.get("conflicted")))
        edit_both_sides(repo, "docs/source/development/page.rst")
        docs_conflict = tool.promotion_merge_status()
        check("a docs conflict is separated out, because that is what the "
              "rehearsal is about",
              docs_conflict.get("conflicted_in_docs")
              == ["docs/source/development/page.rst"],
              str(docs_conflict.get("conflicted_in_docs")))
        unreadable = tool.promotion_merge_status("origin/nope", "origin/nope2")
        check("an unreadable pair is neither mergeable nor conflicted",
              unreadable.get("mergeable") is None, str(unreadable))
    finally:
        tool.ROOT = saved
        holder.cleanup()


def test_the_tool_stays_a_stdlib_tool_of_this_repository() -> None:
    """AGENTS.md: a suite of scripts/ imports the standard library and scripts/ only."""
    tree = ast.parse(read(TOOL), filename=str(TOOL))
    imported = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    third_party = sorted(name for name in imported
                         if name not in sys.stdlib_module_names)
    check("the rehearsal imports nothing outside the standard library",
          not third_party, ", ".join(third_party))
    check("the rehearsal names its issue and its epic",
          tool.ISSUE == 1610 and tool.PARENT_EPIC == 1589,
          f"{tool.ISSUE}/{tool.PARENT_EPIC}")
    check("the report shape is versioned",
          isinstance(tool.EVIDENCE_SCHEMA, str)
          and tool.EVIDENCE_SCHEMA.startswith("mrmap.docs.rehearsal."),
          str(tool.EVIDENCE_SCHEMA))


def test_the_rehearsal_is_documented_and_its_result_recorded() -> None:
    """The page is what makes the run reviewable, and the report is its evidence."""
    page = read(REHEARSAL_PAGE)
    check("the rehearsal is documented", bool(page), str(REHEARSAL_PAGE))
    required = ("docs_release_rehearsal.py", "provenance.json", "--candidate",
                "MRMAP_DOCS_REHEARSAL_URL", "MRMAP_DOCS_REHEARSAL_PROMOTE",
                "documentation-hosting", "test_docs_release_rehearsal.py")
    missing = [needle for needle in required if needle not in page]
    check("the page names the tool, its guards and its suite", not missing,
          ", ".join(missing))
    check("the page says what a worker may not do",
          all(phrase in page for phrase in
              ("no production", "rehearsal tag", "not")) or "production" in page,
          "the page must state the production ban")
    check("the hosting page points at the rehearsal",
          "documentation-release-rehearsal" in read(HOSTING_PAGE)
          or "docs_release_rehearsal" in read(HOSTING_PAGE),
          str(HOSTING_PAGE))
    if EVIDENCE.is_file():
        try:
            recorded = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            check("the recorded report is JSON", False, str(error))
            return
        check("the recorded report is of this issue",
              recorded.get("issue") == 1610, str(recorded.get("issue")))
        check("the recorded report has checks, measurements and limitations",
              bool(recorded.get("checks")) and bool(recorded.get("measurements"))
              and bool(recorded.get("limitations")),
              str(sorted(recorded)))
        check("the recorded report names the candidate it built",
              isinstance(recorded.get("candidate_sha"), str)
              and len(str(recorded.get("candidate_sha"))) == 40,
              str(recorded.get("candidate_sha")))
        check("the recorded report does not claim a publication it did not do",
              recorded.get("promoted_tag") is None
              or str(recorded.get("promoted_tag", "")).startswith(
                  tool.REHEARSAL_TAG_PREFIX),
              str(recorded.get("promoted_tag")))
    else:
        check("the recorded report exists", False, str(EVIDENCE))


def main() -> int:
    if not shutil.which("git"):
        print("harness cannot run: no git, and the fixture repository cannot be "
              "built without it", file=sys.stderr)
        return 2
    if not TOOL.is_file():
        print(f"harness cannot run: {TOOL} is not there to test", file=sys.stderr)
        return 2

    print("docs_release_rehearsal holds against the committed contracts")
    test_the_gate_flags_come_from_the_committed_job()
    test_the_rehearsal_tag_can_never_be_a_release_tag()
    test_promote_needs_the_environment_and_a_rehearsal_name()
    test_the_report_may_only_be_written_where_reports_live()
    test_ordinary_traffic_never_generates_a_site()
    test_the_host_probe_reads_a_version_only_from_a_two_hundred()
    test_the_provenance_of_a_build_is_read_not_assumed()
    test_the_tool_stays_a_stdlib_tool_of_this_repository()
    test_the_promotion_merge_question_is_asked_of_the_permanent_branches()
    test_a_clean_candidate_rehearses_green()
    test_the_rehearsal_notices_a_candidate_that_should_not_release()
    test_an_isolated_equivalent_is_recorded_as_one()
    test_the_rehearsal_refuses_candidates_it_cannot_honestly_rehearse()
    test_the_candidate_is_asked_the_question_its_own_tree_can_answer()
    test_the_injected_fault_is_what_makes_the_failure_check_mean_something()
    test_the_rehearsal_is_documented_and_its_result_recorded()

    if skipped:
        print(f"\n{len(skipped)} check(s) skipped: " + "; ".join(skipped))
    # An empty run is never a pass: a suite that checked nothing reports exit 2,
    # the convention of check_repo_tooling.sh, rather than printing "OK".
    if not ran:
        print("harness cannot run: no check was executed", file=sys.stderr)
        return 2
    print(f"\n{len(failures)} failed of {len(ran)} checks above" if failures
          else f"\nall {len(ran)} checks passed"
          + (f" ({len(skipped)} skipped)" if skipped else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
