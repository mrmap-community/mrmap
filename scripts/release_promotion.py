#!/usr/bin/env python3
"""release_promotion: the protected path a planned version takes from develop to master.

Host-side tool carried by this repository; run it as `python3
scripts/release_promotion.py <subcommand>` from the repository root (issue
#1584, epic #1577). Standard library only, plus the local `git` CLI for every
repository fact and the `gh` CLI for every GitHub fact - no container, no
database, no other network. Exit 0 when the asked step is done or already
done, 1 when it decides against the candidate, 2 when it could not run (an
unreachable remote, a missing `gh`) - "could not run" is never a pass.

What this tool is, and what it refuses to be
--------------------------------------------
#1581 made the plan: the planner opens a release pull request against develop
that moves VERSION, its projection and the changelog section together. #1583
made the gates that judge a candidate. What was missing - and what this issue
lands - is the promotion in between: the sequence that turns one reviewed
commit of develop into a published stable release on master, step by step,
each step small enough to be a human act and checked hard enough that
automating the run around it cannot skip a person.

#1798 reconciled it with the policy it has to live under, which it may not
bend. Three rules follow, and they are load-bearing:

* the pull request onto master has the SAME REPOSITORY'S develop as its head.
  Not a release branch: `.github/workflows/branch-policy.yml` answers any
  head but develop's onto master with "Only develop may target master" and
  AGENTS.md says the same, so the `release/v<version>` -> master PR this tool
  opened before #1798 could never have been merged. Nothing replaces it: the
  reviewed candidate identity is carried by the attestation preflight writes
  (sha, version, digests, evidence urls) instead of by a ref, so the freeze
  needs no branch at all;
* the identity is checked against reality at every step. If develop advances
  past the reviewed candidate the candidate is INVALIDATED: opening is
  refused until `evidence` and `preflight` have attested the new tip, an open
  release PR whose head no longer resolves to the attested candidate is
  reported STALE instead of "open", and no step trusts a ref name - each
  resolves the candidate and the PR head to an exact commit before deciding
  anything, and a merged PR's merge commit must be master's tip;
* publication needs evidence that was not produced on the way to publication.
  `open-release-pr`, `finalize` and `gate` take the `mrmap-release-candidate/1`
  attestation preflight wrote and REFUSE without it, or with one for another
  sha or version, or with digests that are not the attested ones. `gate
  --simulate` is a dry-run answer, is reported as simulated, and can never
  read as green.

The tool therefore drives, never decides-for:

* it never pushes to develop or master. The develop-to-master PR and the
  master-to-develop sync PR are OPENED by the tool and MERGED by a person,
  exactly as the git conventions of AGENTS.md demand ("only the same
  repository's develop branch may target master", "only the same repository's
  develop may be maintained by maintainer-directed sync from master"). The
  release PR's head IS develop, so the tool pushes no branch for it at all;
* it changes no branch protection and writes no permanent ref. Protection is
  the platform setting of a person; the only refs this tool ever writes are
  the annotated tag of a release it has proven and, for the sync PR, one
  branch at master's tip that it never moves again;
* it never moves or deletes an existing tag. A tag that exists somewhere else
  than where this promotion would put it is a CONFLICT the tool reports and
  stops on - tags are the planner's anchor (#1581) and a released deployment's
  identity; reconciling means completing missing steps, never overwriting
  present ones;
* it writes no rolling alias. Q1 of #1578 is Pending, so "approved rolling
  aliases" from the acceptance criteria is the empty set today; `finalize`
  refuses `--alias` outright until an approved ledger exists, the same way
  `image_release.py` refuses aliases without a reviewed decision;
* it produces no evidence of its own. Tests, Sonar, dependency and artifact
  evidence are collected from CI (`evidence`) and judged by
  `release_gates.py promote` (imported as a module, one promoter like one
  classifier); the attestation is that command's, unchanged.

The steps, and why they are separate dispatches
------------------------------------------------
The acceptance criteria name a protected manual approval. GitHub enforces an
environment between jobs, but a job that *waits* across days holds a runner
and blurs which human approved which act, and the tag-push event of a
GITHUB_TOKEN push triggers no workflow at all - a design that hinged on a tag
event would silently skip publication. So the promotion is five idempotent
steps, each its own dispatch behind the protected environment, each safe to
re-run at any point (that is the "reconcile partial failures" criterion as
working code):

  plan            read-only. Is this sha a planned candidate: VERSION, the
                  projection, the manifest and the release section of the
                  changelog all agree, and the version gate's answer for it
                  is green?
  preflight       the evidence of THIS sha goes through release_gates promote
                  and comes back as the mrmap-release-candidate/1 attestation.
                  No evidence, no attestation; evidence of another sha, none.
                  That attestation IS the reviewed candidate identity - sha,
                  version, artifact digests, evidence urls - which is why no
                  release branch is needed to freeze anything.
  open-release-pr the same repository's develop -> master, which is the only
                  head branch-policy.yml admits, titled `chore: release
                  v<version>` and with the attested candidate quoted in its
                  body. Refused without the attestation of exactly that sha,
                  and refused while develop has moved past the attested
                  candidate: a candidate the tip no longer is owes a fresh
                  evidence+preflight pair, never a silently re-anchored PR.
                  A person reviews and merges - that merge is the decision.
  finalize        after the merge, and refused without the attestation: it
                  must name this sha and version, and the digests about to be
                  published must be the digests it attested. Refused without
                  a MERGED release PR of this version at all - master moving
                  on its own is not a reviewed act. Master's tip must then be
                  that PR's merge commit, must carry the candidate, and must
                  hold the candidate's EXACT tree. Only then: tag v<version>
                  on that commit and the GitHub release quoting the
                  attestation and the digests. An existing tag or release at
                  the expected place is a skip, anywhere else a conflict.
  sync            the reviewed master -> develop sync PR after the release,
                  so develop's next plan window starts from the released state.

`gate` answers the callable contract #1609 asked for - reviewed candidate
source/version, the attested artifact digests, whether master really carries
them and whether the reviewed release PR is what landed - with `--simulate`
for the dry-run suites of the documentation epic; a simulated answer says
`simulated`, never `green`.

How the suites fake it, honestly
---------------------------------
Everything is one subprocess wide: `git` runs against a synthetic repository
whose "origin" is a local bare repo (the file-transport remote the migration
graph suite already uses), `gh` is a PATH-shimmed fixture journaling its
calls. No test file pretends to talk to GitHub; `--git-bin` and `--gh-bin`
are the seams the suite injects, and they are the same code path CI runs.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "canonical_version", SCRIPTS / "canonical_version.py")
canonical_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canonical_version)
_spec = importlib.util.spec_from_file_location(
    "release_gates", SCRIPTS / "release_gates.py")
release_gates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_gates)

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2
SEMVER_RE = release_gates.SEMVER_RE  # one SemVer grammar, #1579's
REQUIRED_IMAGES = ("mrmap-backend", "mrmap-frontend")
# CI job names whose green verdict the evidence collector accepts as the
# "tests" and "sonar" classes of release_gates.REQUIRED_EVIDENCE. The names
# are what `gh pr checks` answers on today's develop (measured on #1663);
# a missing job is a missing class, never a guess.
CHECK_CLASSES = {
    "unit-tests": "tests",
    "acceptance-tests": "tests",
    "sonarcloud": "sonar",
    "SonarCloud Code Analysis": "sonar",
}
# The attestation `release_gates.py promote` (#1583) writes and every step from
# open-release-pr onwards consumes. That command owns the schema; this tool only
# ever reads the file, never writes one, so "attested" always means "attested by
# the one promoter" and never "claimed by the thing that publishes".
ATTESTATION_SCHEMA = "mrmap-release-candidate/1"
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")
# A release section of CHANGELOG.md, in BOTH shapes this repository carries.
# The hand-written history uses the Keep-a-Changelog form,
#   ## [0.1.0] - 2023-03-23
# and what the planner of #1681 actually writes today is a LINKED heading whose
# date sits in parentheses of its own,
#   ## [0.2.0](https://github.com/OWNER/REPO/compare/v0.1.0...v0.2.0) (2026-11-20)
# The matcher before #1798 asked for the first form only, so it refused every
# section the planner generates. The version is captured from inside the
# brackets and compared EXACTLY afterwards - `[0.2.0]` is satisfied neither by
# the prefix `[0.2.0` of `[0.2.10]` nor by the prerelease `[0.2.0-rc.1]` of the
# same line - and the date is required in the shape that follows the brackets,
# which is what keeps `## [Unreleased]`-style headings out without naming them.
RELEASE_HEADING_RE = re.compile(
    r"^## \[(?P<version>[^\]\s]+)\]"
    r"(?:"
    r"(?:[ \t]*[-\u2010-\u2015][ \t]*)(?P<date>[0-9]{4}-[0-9]{2}-[0-9]{2})"
    r"|"
    r"\([^\t\n]*?\)[ \t]*\((?P<date_generated>[0-9]{4}-[0-9]{2}-[0-9]{2})\)"
    r")[ \t]*$",
    re.M)
# `### Migration notes` is the curated subsection the repository keeps above the
# generated ones on purpose (its own note at the top of CHANGELOG.md says so, and
# `release_gates.py` reads the notes up to that name). It is therefore allowed in
# a generated release section but is never generated, so it is never judged.
CURATED_SUBSECTIONS = ("Migration notes",)
# What release-please names the breaking facts of a window (its own heading, with
# the warning sign it writes), and the curated spelling the UNRELEASED section of
# this repository uses. Both are accepted readings of "the release names its
# breaking changes"; neither is generated by the `changelog-sections` table, so
# both are exempt from the hand-edit judgement below.
BREAKING_SUBSECTIONS = ("\u26a0 BREAKING CHANGES", "BREAKING CHANGES")
# The PR title of a release PR is its identity in `gh pr list`: one title per
# version, so a re-run finds the PR it opened instead of opening a second one.
RELEASE_PR_TITLE = "chore: release v{version}"


class PromotionCannotRun(Exception):
    """The step could not be decided - exit 2, never reported as a pass."""


class PromotionRefused(Exception):
    """The step is decided against - exit 1, with the reason printed by main."""


def run(argv, cwd=None, input=None):
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          input=input)
    return proc.returncode, proc.stdout, proc.stderr


def gitlet(args, root, *argv, allow_fail=False):
    code, out, err = run([args.git_bin, "-C", str(root), *argv])
    if code != 0 and not allow_fail:
        raise PromotionCannotRun(f"git {' '.join(argv)}: {err.strip()}")
    if code != 0:
        return None
    return out.strip()


def is_ancestor(args, root, a, b):
    """git merge-base --is-ancestor as a decision, not as an exit code."""
    code, _, err = run([args.git_bin, "-C", str(root), "merge-base",
                        "--is-ancestor", a, b])
    if code not in (0, 1):
        raise PromotionCannotRun(f"git merge-base --is-ancestor {a} {b}: "
                                 f"{err.strip()}")
    return code == 0


def gh(args, *argv, input_text=None):
    code, out, err = run([args.gh_bin, *argv], input=input_text)
    if code != 0:
        raise PromotionCannotRun(f"gh {' '.join(argv[:2])}: {err.strip()}")
    return out.strip()


# ---------------------------------------------------------------------------
# candidate identity: the five files #1581 moves together ARE the candidate


def show(args, root, sha, path):
    return gitlet(args, root, "show", f"{sha}:{path}")


def candidate_version_at(args, root, sha):
    return show(args, root, sha, "VERSION").strip()


def check_candidate(args, root, sha, expect_version=None, require_folded=True):
    """Every fact a planned candidate must carry, as (ok, text) lines."""
    results = []
    version = candidate_version_at(args, root, sha)
    if not SEMVER_RE.match(version):
        raise PromotionRefused(f"VERSION at {sha[:12]} is {version!r}, not "
                               f"strict SemVer - a candidate must be planned")
    results.append(f"VERSION: {version}")
    if expect_version and version != expect_version:
        raise PromotionRefused(
            f"the candidate VERSION is {version}, not the expected "
            f"{expect_version}")
    projection = show(args, root, sha, "backend/MrMap/version.py")
    want = canonical_version.render_projection(version)
    if projection.strip() != want.strip():
        raise PromotionRefused(
            "backend/MrMap/version.py at the candidate is not the projection "
            "of VERSION - regenerate with canonical_version.py --write")
    results.append("projection: matches")
    manifest = json.loads(show(args, root, sha,
                               ".release-please-manifest.json"))
    if manifest.get(".") != version:
        raise PromotionRefused(
            f"the release manifest at the candidate still says "
            f"{manifest.get('.')!r} while VERSION is {version} - the planner "
            "moves them together, so this commit is not a planned release")
    results.append("manifest: " + manifest.get("."))
    changelog = show(args, root, sha, "CHANGELOG.md")
    heading, reason = find_release_section(changelog, version)
    if heading is None:
        if require_folded:
            raise PromotionRefused(
                f"CHANGELOG.md at the candidate has no release section for "
                f"exactly {version} ({reason}) - the planner's release "
                "section is what the GitHub release body and the tag "
                "annotation ship")
    else:
        results.append(f"changelog: {heading}")
    if not is_ancestor(args, root, sha, args.develop_ref):
        raise PromotionRefused(
            f"the candidate {sha[:12]} is not reachable from "
            f"{args.develop_ref} - only a commit develop itself carries is a "
            "planned candidate")
    results.append(f"carrier: reachable from {args.develop_ref}")
    return version, results


# ---------------------------------------------------------------------------
# the changelog's release sections
#
# Two shapes, both real in this repository (see RELEASE_HEADING_RE): the
# hand-written `## [0.1.0] - 2023-03-23` of the existing history and the
# linked, generated `## [0.2.0](<compare url>) (2026-11-20)` of #1681. The
# version is captured and then compared exactly, so a heading of the line
# (`0.2.0-rc.1`) or a longer digit run (`0.2.10`) never answers a request for
# `0.2.0` - the matching is bounded at the closing bracket on the left and at
# the required date on the right.


def release_headings(changelog):
    """[(version, match)] for every release heading, in file order.

    A heading whose bracketed text is not strict SemVer is not a release
    section at all, which is what keeps the curated `## Unreleased` heading (a
    bare word, no date) out of every answer below.
    """
    found = []
    for match in RELEASE_HEADING_RE.finditer(changelog):
        version = match.group("version")
        if SEMVER_RE.match(version):
            found.append((version, match))
    return found


def find_release_section(changelog, version):
    """The heading line of the section for EXACTLY `version`, or (None, why)."""
    headings = [match.group(0).strip() for value, match
                in release_headings(changelog) if value == version]
    if not headings:
        seen = sorted({value for value, _ in release_headings(changelog)})
        return None, ("the release headings it does carry are "
                      + (", ".join(f"[{value}]" for value in seen)
                         if seen else "none"))
    return headings[0], None


def release_section_text(changelog, version):
    """A release section with its heading, ending at the next `## ` heading."""
    for value, match in release_headings(changelog):
        if value != version:
            continue
        rest = changelog[match.end():]
        nxt = re.search(r"^##(?:[ \t]|$)", rest, re.M)
        end = match.end() + (nxt.start() if nxt else len(rest))
        return changelog[match.start():end]
    return None


def subsection_names(section):
    return [match.group(1).strip() for match in
            re.finditer(r"^### ([^\n]+?)[ \t]*$", section, re.M)]


def generated_subsection_names(config_path=None):
    """The `### ` headings the planner is allowed to write, from ITS OWN config.

    Read out of release-please-config.json rather than hardcoded here, so the
    claim "the generated notes were verified" is checked against the reviewer's
    contract (the `changelog-sections` table) instead of against a copy of it
    in this file. Returns None when the config cannot be read: a caller must
    then report what it saw and judge nothing, which is less verified rather
    than falsely verified.
    """
    path = Path(config_path) if config_path else (
        SCRIPTS.parent / "release-please-config.json")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sections = config.get("changelog-sections")
    if not isinstance(sections, list):
        return None
    names = {entry.get("section") for entry in sections
             if isinstance(entry, dict) and entry.get("section")}
    return names or None


def verify_generated_notes(changelog, version, breaking=None,
                           config_path=None):
    """What a release section owes before its bytes become a tag annotation.

    Returns (ok, findings). Two judgements, both about provenance rather than
    taste:

    * every `### ` subsection is one the planner's own config generates, or
      the curated `### Migration notes`. Anything else means a hand edited a
      generated release section, which AGENTS.md and the `changelog`
      constraint of release_lifecycle.json reserve to the planner's PR - no
      hand edits of generated versions;
    * a window the version gate counted breaking changes in says so in what
      ships. release-please answers that with its own `###
      \u26a0 BREAKING CHANGES` section; the curated `**Breaking:**` line of the
      UNRELEASED section is the other accepted spelling. Neither present and
      the promotion stops - this is exactly where the bang-title gap of
      docs/source/development/release-planning.rst bites, because a `feat!:`
      title alone reaches the planner as neither note nor bump.

    `breaking` is the count the version gate reports, or None when the caller
    has no version report to consult; then the breaking claim is not demanded,
    and the findings say so instead of implying it was checked.
    """
    section = release_section_text(changelog, version)
    if section is None:
        return False, [f"no release section for {version} to verify"]
    names = subsection_names(section)
    allowed = generated_subsection_names(config_path)
    findings = [f"release section subsections: "
                f"{', '.join(names) if names else 'none'}"]
    problems = []
    unknown = [name for name in names
               if name not in CURATED_SUBSECTIONS
               and name not in BREAKING_SUBSECTIONS
               and (allowed is None or name not in allowed)]
    for name in unknown:
        problems.append(
            f"'### {name}' is neither a section release-please-config.json "
            "generates nor the curated Migration notes - a generated release "
            "section is never hand-edited")
    if allowed is None:
        findings.append("planner config unreadable - subsection names "
                        "reported, not judged")
    if breaking:
        if not any(name in BREAKING_SUBSECTIONS for name in names) \
                and "**Breaking:**" not in section:
            problems.append(
                f"{breaking} breaking change(s) in the window, but the "
                f"release section for {version} names none of them - no "
                "generated breaking section and no '**Breaking:**' line. The "
                "bang-title gap of release-planning.rst means a `feat!:` "
                "title alone generates neither note nor bump, so this release "
                "would ship a breaking change it never mentions")
    elif breaking is None:
        findings.append("no version report supplied - the breaking claim of "
                        "the release section was not checked")
    return not problems, findings + problems


# ---------------------------------------------------------------------------
# the attestation: the reviewed candidate identity every later step reads
#
# One file, written by `release_gates.py promote` (#1583) through `preflight`.
# It binds the reviewed develop SHA, the version, the artifact digests and the
# evidence urls of exactly that SHA, which is the "freeze candidate identity"
# the acceptance criteria ask for - and it is why no release branch has to
# exist: what is frozen is a statement about a commit, verified against the
# commit, not a ref that could be moved.


def load_attestation(path, step):
    """Read and shape-check the attestation file a step was handed."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise PromotionCannotRun(f"{step}: cannot read the attestation at "
                                 f"{path}: {exc}")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PromotionCannotRun(f"{step}: the attestation at {path} is not "
                                 f"JSON: {exc}")
    if document.get("attestation") != ATTESTATION_SCHEMA:
        raise PromotionRefused(
            f"{step}: {path} is not a {ATTESTATION_SCHEMA} attestation "
            f"(it says {document.get('attestation')!r}) - run `preflight`, "
            "which is the one place the promoter writes one")
    candidate = document.get("candidate") or {}
    sha = candidate.get("sha")
    version = candidate.get("version")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PromotionRefused(f"{step}: the attestation names candidate sha "
                               f"{sha!r}, which is not 40 hex - a candidate "
                               "identity is an exact commit")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise PromotionRefused(f"{step}: the attestation names version "
                               f"{version!r}, which is not strict SemVer")
    return document, text, sha, version


def require_attestation(args, root, sha, version, step, digests=None):
    """The fail-closed question every publishing step asks.

    Refuses when no attestation was handed over, when it names another sha or
    version than the step is about to publish, or when the digests it attested
    are not the digests being published. `digests` is the set finalize is
    about to put into the release body; `gate` passes None because it reports
    rather than publishes, but still refuses to call anything green without
    the document.
    """
    path = getattr(args, "attestation", None)
    if not path:
        raise PromotionRefused(
            f"{step}: no attestation was supplied - publish nothing that "
            "was not attested first. Run `evidence` for this sha and "
            "`preflight`, then pass the file it wrote with --attestation")
    document, text, attested_sha, attested_version = load_attestation(
        path, step)
    if attested_sha != sha:
        raise PromotionRefused(
            f"{step}: the attestation is for {attested_sha[:12]}, not for the "
            f"candidate {sha[:12]} - a reviewed identity belongs to one "
            "commit; re-run evidence and preflight for the candidate this "
            "step is actually about")
    if attested_version != version:
        raise PromotionRefused(
            f"{step}: the attestation says version {attested_version}, the "
            f"candidate says {version} - the planner moves VERSION, its "
            "projection, the manifest and the release section together, so "
            "one of the two is not the reviewed candidate")
    attested_digests = document.get("digests") or {}
    for name, digest in sorted(attested_digests.items()):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise PromotionRefused(
                f"{step}: the attestation carries digest {digest!r} for "
                f"{name}, which is not sha256:<64 hex>")
    if digests is None:
        return document, text, attested_digests
    if digests != attested_digests:
        missing = sorted(set(attested_digests) - set(digests))
        extra = sorted(set(digests) - set(attested_digests))
        changed = sorted(name for name in set(digests) & set(attested_digests)
                         if digests[name] != attested_digests[name])
        raise PromotionRefused(
            f"{step}: the digests about to be published are not the attested "
            f"ones (missing {missing}, extra {extra}, different {changed}) - "
            "the attestation is the contract between the build and the "
            "release, and the release does not get to rewrite it")
    return document, text, attested_digests


# ---------------------------------------------------------------------------
# plan


def cmd_plan(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version, facts = check_candidate(args, root, sha, args.expect_version)
    tag = f"v{version}"
    print(f"plan: candidate {sha[:12]} is a planned {version} release")
    for fact in facts:
        print(f"  {fact}")
    tip = gitlet(args, root, "rev-parse", args.develop_ref)
    print(f"  tip: candidate {'IS' if tip == sha else 'is NOT'} "
          f"{args.develop_ref} - only a tip is a reviewable candidate")
    print("  steps this tool drives, one dispatch each, each idempotent:")
    print("    1. preflight        evidence of this sha -> attestation "
          "(the reviewed identity)")
    print(f"    2. open-release-pr  {develop_branch(args)} -> master, refused "
          "without that attestation")
    print("    3. (a person reviews and merges the release PR)")
    print(f"    4. finalize         attestation + merged-PR + tree check, tag "
          f"{tag}, GitHub release")
    print("    5. sync             reviewed master -> develop sync PR")
    return EXIT_OK


# ---------------------------------------------------------------------------
# evidence collection from CI, then the ONE promoter: release_gates promote


def build_evidence(check_runs, sha, artifacts, manual_urls):
    classes = {}
    for run_entry in check_runs:
        name = run_entry.get("name") or run_entry.get("context") or ""
        klass = CHECK_CLASSES.get(name)
        conclusion = run_entry.get("conclusion") or run_entry.get("status")
        url = run_entry.get("html_url") or run_entry.get("details_url") or ""
        if klass is None:
            continue
        if klass in classes and conclusion != "success":
            continue
        if conclusion == "success":
            classes[klass] = {"status": "pass", "sha": sha, "url": url}
    for name, url in manual_urls.items():
        classes[name] = {"status": "pass", "sha": sha, "url": url}
    if artifacts:
        classes["artifacts"] = {
            "status": "pass", "sha": sha,
            "url": manual_urls.get("artifacts", ""),
            "images": {name: {"digest": digest}
                       for name, digest in sorted(artifacts.items())},
        }
    evidence = {"candidate": {"sha": sha, "version": None},
                "checks": classes}
    missing = [name for name in release_gates.REQUIRED_EVIDENCE
               if name not in classes]
    return evidence, missing


def cmd_evidence(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version = args.version or candidate_version_at(args, root, sha)
    if args.checks_file:  # the suite's seam: a saved `gh api` payload
        payload = json.loads(Path(args.checks_file).read_text(encoding="utf-8"))
        runs = payload.get("check_runs", payload) if isinstance(payload, dict) \
            else payload
    else:
        raw = gh(args, "api",
                 f"repos/{args.repository}/commits/{sha}/check-runs",
                 "--paginate", "--jq", ".check_runs[]")
        runs = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(raw):
            while idx < len(raw) and raw[idx] in " \n\r\t":
                idx += 1
            if idx >= len(raw):
                break
            value, idx = decoder.raw_decode(raw, idx)
            runs.append(value)
    artifacts = {}
    for spec in args.artifact or []:
        if "=" not in spec:
            raise PromotionCannotRun(f"--artifact {spec!r} is not name=sha256:...")
        name, digest = spec.split("=", 1)
        artifacts[name] = digest
    manual = {}
    for spec in args.manual or []:
        if "=" not in spec:
            raise PromotionCannotRun(f"--manual {spec!r} is not name=url")
        manual[spec.split("=", 1)[0]] = spec.split("=", 1)[1]
    evidence, missing = build_evidence(runs, sha, artifacts, manual)
    evidence["candidate"]["version"] = version
    text = json.dumps(evidence, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    for name in missing:
        print(f"evidence: missing {name!r} - no attestation without it",
              file=sys.stderr)
    return EXIT_OK if not missing else EXIT_FAIL


def read_gate_report(spec, step):
    """One `name=path` gate report, as the promoter's caller must read it."""
    if "=" not in spec:
        raise PromotionCannotRun(f"{step}: --gate {spec!r} is not name=path")
    name, path = spec.split("=", 1)
    try:
        return name, json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise PromotionCannotRun(f"{step}: cannot read gate report {name} at "
                                 f"{path}: {exc}")
    except json.JSONDecodeError as exc:
        raise PromotionCannotRun(f"{step}: gate report {name} at {path} is "
                                 f"not JSON: {exc}")


def cmd_preflight(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version, _ = check_candidate(args, root, sha, args.expect_version)
    for name in ("api", "version", "upgrade"):
        if not any(spec.startswith(f"{name}=") for spec in args.report or []):
            raise PromotionRefused(
                f"the {name} gate report is not supplied - run "
                "`release_gates.py " + name + " --report ...` against the "
                "candidate and pass it here")
    # The generated notes are verified HERE, where the gate reports are on hand
    # to say what the window actually contained - not at finalize, where a
    # refusal would arrive after a person already merged.
    # The reports are read for what the window CONTAINED, not re-judged: a red
    # report is `promote`'s decision to make (one promoter, one classifier), and
    # reading it here only says whether the release section has to name any
    # breaking change.
    reports = dict(read_gate_report(spec, "preflight")
                   for spec in args.report or [])
    breaking = reports.get("version", {}).get("breaking")
    ok, findings = verify_generated_notes(
        show(args, root, sha, "CHANGELOG.md"), version, breaking=breaking,
        config_path=args.changelog_config)
    for finding in findings:
        print(f"preflight: {finding}")
    if not ok:
        raise PromotionRefused(
            "the release section of CHANGELOG.md is not what the planner "
            f"generates for {version} - see the findings above")
    argv = [sys.executable, str(Path(__file__).parent / "release_gates.py"),
            "promote", "--sha", sha, "--version", version,
            "--channel", args.channel, "--evidence", args.evidence]
    for spec in args.report or []:
        argv += ["--gate", spec]
    if args.actor:
        argv += ["--actor", args.actor]
    if args.output:
        argv += ["--output", args.output]
    code, out, err = run(argv)
    sys.stdout.write(out)
    sys.stderr.write(err)
    if code != EXIT_OK:
        return code
    print(f"preflight: attested {version} at {sha[:12]} - this attestation IS "
          f"the reviewed candidate identity; run open-release-pr with it, let "
          f"a person merge, then finalize with the same file")
    return EXIT_OK


# ---------------------------------------------------------------------------
# the release PR: the same repository's develop -> master


def remote_ref(args, root, ref):
    code, out, _ = run([args.git_bin, "-C", str(root), "ls-remote",
                        args.remote, ref])
    if code != 0:
        raise PromotionCannotRun(f"git ls-remote {args.remote} {ref} failed")
    lines = [line for line in out.splitlines() if line.endswith(f"\t{ref}")]
    return lines[0].split()[0] if lines else None


def develop_branch(args):
    """The branch NAME behind `--develop-ref` (`origin/develop` -> `develop`).

    The release PR's head has to be named the way GitHub names it, and the
    tool is run against a clone whose develop is a remote-tracking ref; the
    name is derived rather than configured twice, so a mirror or fork test can
    point `--develop-ref` somewhere else and the PR follows it.
    """
    return args.develop_ref.rsplit("/", 1)[-1]


def release_prs(args, version):
    """Every PR onto master that carries this version's release title.

    The title is the identity (#RELEASE_PR_TITLE): one per version, whatever
    branch shape it came from, which is what lets a re-run find the PR it
    opened and lets finalize prove that a PERSON merged a release PR at all.
    `headRefOid` is resolved here rather than trusted from the listing when a
    caller has to compare it with a commit - a stale listing is exactly the
    failure mode this path cannot afford.
    """
    title = RELEASE_PR_TITLE.format(version=version)
    listed = json.loads(gh(args, "pr", "list", "--repo", args.repository,
                           "--base", "master", "--state", "all", "--json",
                           "number,state,title,headRefName,headRefOid")
                        or "[]")
    return [pr for pr in listed if pr.get("title") == title]


def candidate_from_attestation(args, root, step):
    """The commit a step is about: `--sha`, else what the attestation names.

    Defaulting to the attestation rather than to develop's tip is the whole
    point of #1798: the reviewed candidate identity is the promoter's answer,
    and a step that silently fell back to "whatever develop is now" would
    promote an unjudged commit the moment develop moved.
    """
    if getattr(args, "sha", None):
        return args.sha
    path = getattr(args, "attestation", None)
    if path:
        _, _, sha, _ = load_attestation(path, step)
        return sha
    return gitlet(args, root, "rev-parse", args.develop_ref)


def resolve_pr_head(args, root, pr):
    """The commit a PR's head branch points at NOW, on the remote."""
    name = pr.get("headRefName")
    if not name:
        return pr.get("headRefOid")
    return remote_ref(args, root, f"refs/heads/{name}") or pr.get("headRefOid")


def cmd_open_release_pr(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = candidate_from_attestation(args, root, "open-release-pr")
    version, _ = check_candidate(args, root, sha, args.expect_version)
    require_attestation(args, root, sha, version, "open-release-pr")
    title = RELEASE_PR_TITLE.format(version=version)
    for pr in release_prs(args, version):
        # The head of a develop -> master PR MOVES with develop, so it is
        # resolved from the remote rather than read off the listing: "the PR is
        # still open" is worthless if what it now carries is not what was
        # attested.
        head = resolve_pr_head(args, root, pr)
        if pr["state"] == "OPEN":
            if head != sha:
                raise PromotionRefused(
                    f"release PR #{pr['number']} is open but its head resolves "
                    f"to {head[:12] if head else 'nothing'}, not to the "
                    f"attested candidate {sha[:12]} - that PR is STALE, and a "
                    "stale release PR is not an open one. A person closes it; "
                    "the new tip owes its own evidence and preflight")
            print(f"open-release-pr: release PR #{pr['number']} already open "
                  f"for {version} at {sha[:12]} - nothing to open, a person "
                  "reviews and merges")
            return EXIT_OK
        if pr["state"] == "MERGED":
            # No head comparison here: the head of a develop -> master PR is
            # develop itself, which moves on the moment anybody merges anything.
            # What finalize checks instead is the fact that survives - that
            # master's tip is the merge commit that carries THIS candidate.
            print(f"open-release-pr: release PR #{pr['number']} for {version} "
                  "is already merged - the next step is finalize")
            return EXIT_OK
        raise PromotionRefused(
            f"a CLOSED release PR #{pr['number']} for {version} exists - "
            "reopening a release PR is a human act, do it deliberately and "
            "re-run")
    # About to open: the reviewed identity has to still BE develop's tip,
    # because the head of a develop -> master PR IS develop. develop keeps
    # moving while a release PR waits, and the answer is not to move the
    # candidate out from under the review - it is to stop and make the new tip
    # earn its own evidence and attestation.
    tip = gitlet(args, root, "rev-parse", args.develop_ref)
    if tip != sha:
        raise PromotionRefused(
            f"{args.develop_ref} moved to {tip[:12]} - the attested candidate "
            f"{sha[:12]} is no longer develop's tip, so it is no longer the "
            "reviewed candidate. A release PR here would merge commits nobody "
            "judged: run evidence and preflight for the new tip first")
    body = (f"Promotion of the planned version {version} (#1584, reconciled "
            f"with the develop-first policy by #1798).\n\n"
            f"Head is **this repository's `{develop_branch(args)}`** - the "
            "only head `.github/workflows/branch-policy.yml` admits onto "
            "master - at this exact commit:\n\n"
            f"- reviewed candidate `{sha}`\n- attestation "
            f"`{ATTESTATION_SCHEMA}`, written by `release_gates.py promote` "
            "at preflight\n\n"
            "The merge is the reviewed act that decides the release. "
            "`finalize` afterwards refuses unless the attestation names this "
            "sha and version, its digests are the digests it publishes, this "
            "PR is the merged release PR, master's tip is that merge commit "
            "and master's tree EQUALS the candidate's tree.\n\n"
            "A develop -> master PR follows develop's tip, so it is only as "
            "frozen as develop is: if develop advances past this commit, "
            "re-running `open-release-pr` reports the PR STALE and refuses, "
            "and `finalize` refuses the merge - the candidate is invalidated "
            "rather than silently re-anchored, so what merges is what was "
            "judged.")
    url = gh(args, "pr", "create", "--repo", args.repository,
             "--base", "master", "--head", develop_branch(args),
             "--title", title, "--body", body)
    print(f"open-release-pr: opened {url} ({develop_branch(args)} -> master "
          f"at {sha[:12]}) - waiting for a human merge")
    return EXIT_OK


# ---------------------------------------------------------------------------
# finalize: tree equality, tag, release. Never a move, never an alias.


def tag_state(args, root, tag):
    """The COMMIT a tag points at. Annotated tags carry a tag object whose
    sha is not the commit's; `ls-remote` lists both, and the `^{}` line is
    the peeled commit - comparing the tag-object sha with master's tip would
    read our own tag as being "elsewhere"."""
    peeled = remote_ref(args, root, f"refs/tags/{tag}^{{}}")
    return peeled or remote_ref(args, root, f"refs/tags/{tag}")


def merged_parents(args, root, commit):
    """The parents of a commit, [] when it is not a merge."""
    out = gitlet(args, root, "log", "-1", "--pretty=%P", commit) or ""
    return out.split()


def cmd_finalize(args):
    root = Path(args.root)
    if args.alias:
        raise PromotionRefused(
            "rolling aliases are refused: Q1 of #1578 is Pending and the "
            "approved-aliases ledger does not exist yet - the first release "
            "that may carry one needs that answer on record first")
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    sha = candidate_from_attestation(args, root, "finalize")
    version, _ = check_candidate(args, root, sha, args.expect_version)
    # Every judgement is made BEFORE the first push: a tag is the point of no
    # easy return, so a missing attestation or a wrong digest must stop the run
    # while it still can.
    digests = {}
    for spec in args.artifact or []:
        if "=" not in spec:
            raise PromotionCannotRun(f"--artifact {spec!r} is not name=sha256:...")
        name, digest = spec.split("=", 1)
        if not DIGEST_RE.fullmatch(digest):
            raise PromotionRefused(f"artifact {name} digest {digest!r} is not "
                                   "sha256:<64 hex> - digests are the whole "
                                   "point of the release body")
        digests[name] = digest
    for name in REQUIRED_IMAGES:
        if name not in digests:
            raise PromotionRefused(
                f"artifact digest for {name} was not supplied - the release "
                "must quote both first-party images or say nothing")
    _, attestation_text, attested_digests = require_attestation(
        args, root, sha, version, "finalize", digests=digests)
    # What publishes is what a person merged - so a merged release PR has to
    # exist, and its head has to be the commit the attestation names. master
    # advancing on its own is not a reviewed act.
    merged = [pr for pr in release_prs(args, version) if pr["state"] == "MERGED"]
    if not merged:
        open_prs = [pr for pr in release_prs(args, version)
                    if pr["state"] == "OPEN"]
        raise PromotionRefused(
            f"no MERGED release PR for {version} exists"
            + (f" (#{open_prs[0]['number']} is still open)" if open_prs else "")
            + " - finalize publishes only what a person reviewed and merged, "
            "so it refuses a master that moved without a release PR")
    # A MERGED PR's head is not compared with the candidate: that head is
    # develop, and develop moved the moment anybody merged anything after the
    # release. What survives the merge, and what is checked below instead, is
    # that master's tip IS the merge commit that carries the candidate.
    pr = merged[-1]
    tag = f"v{version}"
    master = gitlet(args, root, "rev-parse", args.master_ref)
    parents = merged_parents(args, root, master)
    if len(parents) < 2:
        raise PromotionRefused(
            f"master's tip {master[:12]} is not a merge commit - a release "
            "lands on master through the reviewed merge of the release PR "
            "(AGENTS.md: merge commits when synchronizing permanent "
            "branches); a direct push or a squash is not that act")
    if sha not in parents:
        raise PromotionRefused(
            f"master's tip {master[:12]} is a merge, but not of the candidate "
            f"{sha[:12]} (parents: {[p[:12] for p in parents]}) - finalize "
            "tags the merge commit that carries the tested commit as a parent")
    if not is_ancestor(args, root, sha, master):
        raise PromotionRefused(
            f"master does not carry the candidate {sha[:12]} yet - the "
            "release PR is unmerged or master moved past it; finalize "
            "publishes only what a person has merged")
    diff = gitlet(args, root, "diff", "--stat", sha, master)
    if diff:
        raise PromotionRefused(
            "master's tip does not carry the candidate's tree: git diff "
            f"{sha[:12]} {args.master_ref} is not empty:\n{diff}\n"
            "finalize releases EXACTLY the tested tree; a diverged master "
            "means the reviewed merge is not what it promised to be")
    tag_commit = master  # the merge commit that landed the tree is the tag owner
    here = tag_state(args, root, tag)
    if here and here != tag_commit:
        raise PromotionRefused(
            f"tag {tag} already exists at {here[:12]}, not at master's tip "
            f"{tag_commit[:12]} - the tool never moves a tag; resolve the "
            "two identities of the version by hand")
    if here:
        print(f"finalize: tag {tag} already at the expected commit - skipped")
    else:
        annotation = (f"mrmap {version}: promoted from the reviewed release "
                      f"PR #{pr['number']}; candidate {sha}; tree-verified "
                      f"against master at {tag_commit}; attestation "
                      f"{ATTESTATION_SCHEMA} (#1584, #1798)")
        gitlet(args, root, "tag", "-a", "-m", annotation, tag, tag_commit)
        gitlet(args, root, "push", args.remote, f"refs/tags/{tag}")
        print(f"finalize: tagged {tag} at {tag_commit[:12]}")
    body = (f"Stable release {version}, promoted by the protected path of "
            f"#1584 (#1798).\n\n- reviewed candidate `{sha}`\n- release commit "
            f"`{tag_commit}` (the merge of release PR #{pr['number']}, "
            "tree-identical to the candidate)\n\n**Artifacts "
            "(digests, ghcr.io/mrmap-community):**\n")
    for name, digest in sorted(digests.items()):
        body += f"- `{name}`: `{digest}`\n"
    body += ("\nAttested by `release_gates.py promote` "
             f"for {'/'.join(sorted(attested_digests))}.\n")
    body += ("\n<details><summary>promotion attestation "
             f"({ATTESTATION_SCHEMA})</summary>\n\n```json\n"
             + attestation_text + "```\n\n</details>\n")
    try:
        view = gh(args, "release", "view", tag, "--repo", args.repository,
                  "--json", "tagName,url")
    except PromotionCannotRun:
        view = ""
    if view:
        info = json.loads(view)
        print(f"finalize: GitHub release for {info['tagName']} already exists "
              "- body left untouched (immutable by policy), skipped")
    else:
        gh(args, "release", "create", tag, "--repo", args.repository,
           "--target", tag_commit, "--title", f"mrmap {version}", "--notes",
           body)
        print(f"finalize: published the GitHub release for {tag}")
    print("finalize: done - next is the reviewed sync PR (subcommand sync)")
    return EXIT_OK


# ---------------------------------------------------------------------------
# sync


def cmd_sync(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    version = args.version or candidate_version_at(
        args, root, gitlet(args, root, "rev-parse", args.develop_ref))
    master = gitlet(args, root, "rev-parse", args.master_ref)
    if is_ancestor(args, root, master, args.develop_ref):
        print("sync: develop already contains master - no sync PR owed, "
              "the release landed develop's own work and nothing else")
        return EXIT_OK
    branch = f"master-sync-v{version}"
    existing = remote_ref(args, root, f"refs/heads/{branch}")
    if existing and existing != master:
        raise PromotionRefused(
            f"{branch} exists at {existing[:12]} but master moved to "
            f"{master[:12]} - a sync branch is never moved; a person deletes "
            "or reuses it deliberately")
    if not existing:
        gitlet(args, root, "push", args.remote, f"{master}:refs/heads/{branch}")
    listed = gh(args, "pr", "list", "--repo", args.repository, "--head",
                branch, "--base", "develop", "--state", "all", "--json",
                "number,state")
    for pr in json.loads(listed or "[]"):
        if pr["state"] == "OPEN":
            print(f"sync: sync PR #{pr['number']} already open - a person "
                  "reviews and merges")
            return EXIT_OK
    url = gh(args, "pr", "create", "--repo", args.repository,
             "--base", "develop", "--head", branch,
             "--title", f"chore: sync master back to develop after v{version}",
             "--body", ("Maintainer-directed synchronization from master back "
                        f"to develop after the release of v{version} (the "
                        "git conventions of AGENTS.md). Review it as the "
                        "act that rebases the planner's next window onto the "
                        "released state."))
    print(f"sync: opened {url}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# reconcile / status / gate


def reconcile_state(args, root, version, sha):
    """Where each step of this promotion stands, as one dict per step.

    Nothing here trusts a name. The release PR is found by its title and its
    head is RESOLVED against the remote, because the head of a develop ->
    master PR is develop - which is exactly how a promotion goes stale.
    """
    tag = f"v{version}"
    master = gitlet(args, root, "rev-parse", args.master_ref)
    steps = {}
    steps["candidate_is_tip"] = (
        gitlet(args, root, "rev-parse", args.develop_ref) == sha)
    prs = release_prs(args, version)
    steps["release_pr"] = prs[0]["state"].lower() if prs else "none"
    head = resolve_pr_head(args, root, prs[0]) if prs else None
    steps["release_pr_head"] = ("none" if head is None else
                                "candidate" if head == sha else
                                f"stale@{head[:12]}")
    parents = merged_parents(args, root, master)
    steps["master_is_merge_of_candidate"] = (len(parents) >= 2
                                             and sha in parents)
    steps["master_carries_candidate"] = is_ancestor(args, root, sha, master)
    steps["master_tree_matches_candidate"] = not gitlet(
        args, root, "diff", "--stat", sha, master, allow_fail=True)
    here = tag_state(args, root, tag)
    steps["tag"] = ("absent" if here is None else
                    "at-master-tip" if here == master else "elsewhere")
    try:
        gh(args, "release", "view", tag, "--repo", args.repository,
           "--json", "tagName")
        steps["github_release"] = "exists"
    except PromotionCannotRun:
        steps["github_release"] = "absent"
    return steps


def cmd_status(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    # "status of the promotion" means the promotion of the reviewed candidate,
    # so the candidate comes from the attestation when one was handed over; a
    # status that always re-read develop's tip would report a moved-past
    # candidate as if it were still current.
    sha = candidate_from_attestation(args, root, "status")
    version = args.version or candidate_version_at(args, root, sha)
    steps = reconcile_state(args, root, version, sha)
    print(f"status of the {version} promotion (candidate {sha[:12]}):")
    for name, state in steps.items():
        print(f"  {name:28} {state}")
    return EXIT_OK


def cmd_gate(args):
    """The callable contract of #1609: what is reviewed, what master carries.

    Green needs all of: the attestation of exactly this candidate (which is
    the frozen source/version/digest identity #1609 asks the gate to name), a
    merged release PR, master's tip as that merge, the candidate's tree on
    master, the tag at master's tip and the release. `--simulate` answers for
    the dry-run suites and can never be green: a simulated answer that could
    satisfy a gate is not a dry run.
    """
    root = Path(args.root)
    if args.simulate:
        print(json.dumps({
            "gate": "release-promotion", "status": "simulated",
            "green": False,
            "note": "a dry-run answer: nothing was read from a remote and "
                    "nothing here can satisfy a publication decision - the "
                    "documentation epic must not schedule real pages on it",
            "candidate": {"sha": args.sha, "version": args.version},
        }, indent=2))
        return EXIT_OK
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    sha = candidate_from_attestation(args, root, "gate")
    version = args.version or candidate_version_at(args, root, sha)
    steps = reconcile_state(args, root, version, sha)
    # No attestation, no green - and a missing file is a REFUSED answer, not a
    # missing fact to be argued about. The digests the attestation names are
    # the digests this gate reports as carried by master.
    _, _, attested_digests = require_attestation(args, root, sha, version,
                                                 "gate")
    green = (steps["release_pr"] == "merged"
             and steps["release_pr_head"] == "candidate"
             and steps["master_is_merge_of_candidate"]
             and steps["master_carries_candidate"]
             and steps["master_tree_matches_candidate"]
             and steps["tag"] == "at-master-tip"
             and steps["github_release"] == "exists")
    print(json.dumps({
        "gate": "release-promotion",
        "status": "green" if green else "pending",
        "frozen": {"sha": sha, "version": version,
                   "source": args.repository,
                   "carrier": develop_branch(args),
                   "attestation": ATTESTATION_SCHEMA,
                   "digests": attested_digests},
        "master": {"tip": gitlet(args, root, "rev-parse", args.master_ref),
                   "carries_candidate": steps["master_carries_candidate"],
                   "tree_matches_candidate":
                       steps["master_tree_matches_candidate"],
                   "is_merge_of_candidate":
                       steps["master_is_merge_of_candidate"]},
        "release_pr": steps["release_pr"],
        "release_pr_head": steps["release_pr_head"],
        "candidate_is_tip": steps["candidate_is_tip"],
        "tag": steps["tag"], "github_release": steps["github_release"],
    }, indent=2))
    return EXIT_OK if green else EXIT_FAIL


# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="release_promotion",
        description=__doc__.splitlines()[0],
        epilog="exit 0 done or already done, 1 the step is decided against "
               "the candidate, 2 the step could not run")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--repository",
                        default="mrmap-community/mrmap")
    parser.add_argument("--develop-ref", default="origin/develop")
    parser.add_argument("--master-ref", default="origin/master")
    parser.add_argument("--git-bin", default="git")
    parser.add_argument("--gh-bin", default="gh")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--sha", default=None)
        sp.add_argument("--version", default=None)
        sp.add_argument("--expect-version", default=None)

    sp = sub.add_parser("plan")
    common(sp)
    sp.set_defaults(func=cmd_plan)
    sp = sub.add_parser("evidence")
    common(sp)
    sp.add_argument("--checks-file", default=None)
    sp.add_argument("--artifact", action="append", default=[])
    sp.add_argument("--manual", action="append", default=[])
    sp.add_argument("--output", default=None)
    sp.set_defaults(func=cmd_evidence)
    sp = sub.add_parser("preflight")
    common(sp)
    sp.add_argument("--evidence", required=True)
    sp.add_argument("--report", action="append", default=[])
    sp.add_argument("--channel", default="stable")
    sp.add_argument("--actor", default=None)
    sp.add_argument("--output", default=None)
    sp.add_argument("--changelog-config", default=None,
                    help="release-please config to judge generated subsections "
                         "against (default: the committed one)")
    sp.set_defaults(func=cmd_preflight)
    sp = sub.add_parser("open-release-pr")
    common(sp)
    sp.add_argument("--attestation", default=None,
                    help="the mrmap-release-candidate/1 file preflight wrote; "
                         "without it nothing is opened")
    sp.set_defaults(func=cmd_open_release_pr)
    sp = sub.add_parser("finalize")
    common(sp)
    sp.add_argument("--artifact", action="append", default=[])
    sp.add_argument("--attestation", default=None,
                    help="the mrmap-release-candidate/1 file preflight wrote; "
                         "without it nothing is published")
    sp.add_argument("--alias", action="append", default=[])
    sp.set_defaults(func=cmd_finalize)
    sp = sub.add_parser("sync")
    common(sp)
    sp.set_defaults(func=cmd_sync)
    sp = sub.add_parser("status")
    common(sp)
    sp.add_argument("--attestation", default=None,
                    help="report the promotion of the candidate this "
                         "attestation names, not develop's current tip")
    sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("gate")
    common(sp)
    sp.add_argument("--attestation", default=None,
                    help="the mrmap-release-candidate/1 file to report as the "
                         "frozen identity; without it the gate cannot be green")
    sp.add_argument("--simulate", action="store_true")
    sp.set_defaults(func=cmd_gate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PromotionRefused as exc:
        print(f"{args.command}: REFUSED - {exc}", file=sys.stderr)
        return EXIT_FAIL
    except PromotionCannotRun as exc:
        print(f"{args.command}: CANNOT RUN - {exc}", file=sys.stderr)
        return EXIT_CANNOT


if __name__ == "__main__":
    sys.exit(main())
