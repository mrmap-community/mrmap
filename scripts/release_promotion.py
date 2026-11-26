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

The tool therefore drives, never decides-for:

* it never pushes to develop or master. The develop-to-master PR and the
  master-to-develop sync PR are OPENED by the tool and MERGED by a person,
  exactly as the git conventions of AGENTS.md demand ("only the same
  repository's develop branch may target master", "only the same repository's
  develop may be maintained by maintainer-directed sync from master");
* it never moves or deletes an existing tag. A tag that exists somewhere else
  than where this promotion would put it is a CONFLICT the tool reports and
  stops on - tags are the planner's anchor (#1581) and a released deployment's
  identity; reconciling means completing missing steps, never overwriting
  present ones;
* it writes no rolling alias. Q1 of #1578 is answered (first published tag
  `v0.2.0`, tags `vMAJOR.MINOR.PATCH` - ADR-0002) and it approved no alias, so
  "approved rolling aliases" from the acceptance criteria is still the empty
  set: `finalize` refuses `--alias` outright until a reviewed alias ledger
  exists, the same way `image_release.py` refuses aliases without a reviewed
  decision;
* it produces no evidence of its own. Tests, Sonar, dependency and artifact
  evidence are collected from CI (`evidence`) and judged by
  `release_gates.py promote` (imported as a module, one promoter like one
  classifier); the attestation is that command's, unchanged.
* it takes the artifact digests from the file that produced them. `--artifact`
  stays for an operator, `--candidate-evidence` reads the
  `mrmap-candidate-images/1` file `image_release.py --attest` wrote in the run
  that published the candidate (#1799), so the digests of a release travel from
  the build to the tag without being pasted by anybody. The file is checked
  against the sha and version under review, a `--artifact` line that contradicts
  it is a conflict rather than an override, and `image_release.py --promote
  --candidate-evidence` re-reads every digest from the registry before it writes
  a tag - the promotion never trusts a digest it was only told about.

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
                  projection, the manifest and the folded changelog section
                  all agree, and the version gate's answer for it is green?
  preflight       the evidence of THIS sha goes through release_gates promote
                  and comes back as the mrmap-release-candidate/1 attestation.
                  No evidence, no attestation; evidence of another sha, none.
  open-release-pr freeze: push refs/heads/release/v<version> at the candidate
                  (a fresh branch at one exact sha - develop keeps moving and
                  the PR must not drift with it; an existing branch at another
                  sha is refused, never reset) and open develop-side
                  release/v<version> -> master. A person reviews and merges.
  finalize        after the merge: master's tip must be a merge commit whose
                  tree EQUALS the candidate's tree (the "reviewed master
                  commit/tree" check - the tested bytes are what lands), then
                  tag v<version> on that commit, then create the GitHub
                  release quoting the attestation and the artifact digests.
                  An existing tag or release at the expected place is a skip,
                  anywhere else a conflict.
  sync            the reviewed master -> develop sync PR after the release,
                  so develop's next plan window starts from the released state.

`gate` answers the callable contract #1609 asked for - frozen candidate
source/version, the artifact digests, whether master really carries them, with
`--simulate` for the dry-run suites of the documentation epic.

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
_spec = importlib.util.spec_from_file_location(
    "image_release", SCRIPTS / "image_release.py")
image_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(image_release)

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
    sections = re.findall(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}$",
                          changelog, re.M)
    if not sections:
        if require_folded:
            raise PromotionRefused(
                f"CHANGELOG.md at the candidate has no '## [{version}] - "
                "<date>' section - the planner's folded release section is "
                "what the GitHub release body and the tag annotation ship")
    else:
        results.append(f"changelog: [{version}] folded")
    if not is_ancestor(args, root, sha, args.develop_ref):
        raise PromotionRefused(
            f"the candidate {sha[:12]} is not reachable from "
            f"{args.develop_ref} - only a commit develop itself carries is a "
            "planned candidate")
    results.append(f"carrier: reachable from {args.develop_ref}")
    return version, results


# ---------------------------------------------------------------------------
# plan


def cmd_plan(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version, facts = check_candidate(args, root, sha, args.expect_version)
    tag = f"v{version}"
    branch = f"release/v{version}"
    print(f"plan: candidate {sha[:12]} is a planned {version} release")
    for fact in facts:
        print(f"  {fact}")
    print("  steps this tool drives, one dispatch each, each idempotent:")
    print("    1. preflight        evidence of this sha -> attestation")
    print(f"    2. open-release-pr  freeze {branch}, open {branch} -> master")
    print("    3. (a person reviews and merges the release PR)")
    print(f"    4. finalize         tree check, tag {tag}, GitHub release")
    print("    5. sync             reviewed master -> develop sync PR")
    return EXIT_OK


# ---------------------------------------------------------------------------
# artifact digests: the file CI wrote, or a person's own lines


def artifact_digests(args, sha=None, version=None):
    """The artifact digests of THIS candidate, as ``{repository: digest}``.

    Two doors, deliberately. ``--candidate-evidence`` reads the
    ``mrmap-candidate-images/1`` file ``image_release.py --attest`` wrote in the
    run that published the candidate, so the digests of a release travel from the
    build to the tag without being pasted by anybody (#1799). ``--artifact``
    stays for an operator naming a digest by hand. Both bind the answer to the
    candidate, and an explicit line that contradicts the build's own file is a
    conflict rather than an override - two identities for one release means
    nobody knows which candidate is being published.

    Only what the FILE can answer is checked here: shape, binding, registry and
    repository names. Whether the registry still serves each digest is answered
    by ``image_release.py`` itself, twice - by ``--attest`` when the file was
    written, and by ``--promote --candidate-evidence`` when the tag is created.
    That is why the promotion needs no docker of its own.
    """
    digests = {}
    for spec in args.artifact or []:
        if "=" not in spec:
            raise PromotionCannotRun(f"--artifact {spec!r} is not name=sha256:...")
        name, digest = spec.split("=", 1)
        digests[name] = digest
    path = getattr(args, "candidate_evidence", None)
    if not path:
        return digests
    # The registry the file was written for has to be the registry this promotion
    # promotes into: a digest only means anything inside the registry that wrote
    # it. Both are usually the default, and pointing a candidate at an isolated
    # registry - the documented way to rehearse the path (#1799) - names both.
    registry_base = (getattr(args, "registry_base", None)
                     or image_release.REGISTRY_BASE)
    try:
        document, problems = image_release.validate_candidate_evidence(
            path, version, sha, registry_base, sorted(image_release.IMAGES))
    except image_release.ReleaseError as exc:
        raise PromotionRefused(f"candidate evidence: {exc}") from None
    for problem in problems:
        raise PromotionRefused(f"candidate evidence: {problem}")
    for image in sorted(document.get("images") or {}):
        entry = document["images"][image]
        name = entry.get("repository") or image
        digest = entry["digest"]
        if digests.get(name) and digests[name] != digest:
            raise PromotionRefused(
                f"--artifact {name}={digests[name]} contradicts the candidate "
                f"evidence, which says {digest} - the build's own file and the "
                "hand-typed line are two identities for one release; resolve "
                "which candidate this promotion is actually for")
        digests[name] = digest
    return digests


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
    artifacts = artifact_digests(args, sha, version)
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
    print(f"preflight: attested {version} at {sha[:12]} - run "
          f"open-release-pr, let a person merge, then finalize")
    return EXIT_OK


# ---------------------------------------------------------------------------
# freeze and release PR


def remote_ref(args, root, ref):
    code, out, _ = run([args.git_bin, "-C", str(root), "ls-remote",
                        args.remote, ref])
    if code != 0:
        raise PromotionCannotRun(f"git ls-remote {args.remote} {ref} failed")
    lines = [line for line in out.splitlines() if line.endswith(f"\t{ref}")]
    return lines[0].split()[0] if lines else None


def cmd_open_release_pr(args):
    root = Path(args.root)
    gitlet(args, root, "fetch", "--quiet", args.remote)
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version, _ = check_candidate(args, root, sha, args.expect_version)
    branch = f"release/v{version}"
    existing = remote_ref(args, root, f"refs/heads/{branch}")
    if existing and existing != sha:
        raise PromotionRefused(
            f"{branch} already exists at {existing[:12]}, a different commit "
            f"than the candidate {sha[:12]} - the tool never moves a frozen "
            "release branch; a person resolves which freeze survives")
    if not existing:
        gitlet(args, root, "push", args.remote,
               f"{sha}:refs/heads/{branch}")
        print(f"open-release-pr: froze {branch} at {sha[:12]}")
    else:
        print(f"open-release-pr: {branch} already frozen at {sha[:12]}")
    existing_pr = gh(args, "pr", "list", "--repo", args.repository,
                     "--head", branch, "--base", "master",
                     "--state", "all", "--json", "number,state,headRefOid")
    for pr in json.loads(existing_pr or "[]"):
        if pr["state"] == "OPEN":
            print(f"open-release-pr: release PR #{pr['number']} already open "
                  "- nothing to open, a person reviews and merges")
            return EXIT_OK
        if pr["state"] == "MERGED":
            print(f"open-release-pr: release PR #{pr['number']} is already "
                  "merged - the next step is finalize")
            return EXIT_OK
        raise PromotionRefused(
            f"a closed PR #{pr['number']} from {branch} to master exists - "
            "reopening a release PR is a human act, do it deliberately and "
            "re-run")
    body = (f"Promotion of the planned version {version} (issue #1584).\n\n"
            f"Head is the frozen branch `{branch}` at the exact candidate "
            f"`{sha}` - develop moves on, this PR does not.\n"
            "The merge is the reviewed act that decides the release; "
            "`finalize` afterwards only turns THAT commit into tag, release "
            "and digests, and refuses to move anything.\n\n"
            "Preconditions checked before opening: VERSION, its projection, "
            "the release manifest and the folded changelog section agree at "
            "the candidate, and the three release gates plus the evidence "
            "attestation were green at preflight.")
    url = gh(args, "pr", "create", "--repo", args.repository,
             "--base", "master", "--head", branch,
             "--title", f"chore: release v{version}",
             "--body", body)
    print(f"open-release-pr: opened {url} - waiting for a human merge")
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


def cmd_finalize(args):
    root = Path(args.root)
    if args.alias:
        raise PromotionRefused(
            "rolling aliases are refused: the approved-aliases ledger does "
            "not exist yet, and Q1 of #1578 (ADR-0002) approved the tag shape "
            "but no alias - the first release that may carry one needs a "
            "reviewed alias decision on record first")
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version, _ = check_candidate(args, root, sha, args.expect_version)
    tag = f"v{version}"
    master = gitlet(args, root, "rev-parse", args.master_ref)
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
    # Every judgement finalize makes is made BEFORE it touches anything: a
    # tag push is the point of no easy return, so a missing or malformed
    # digest must stop the run while it still can.
    digests = {}
    for name, digest in sorted(artifact_digests(args, sha, version).items()):
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise PromotionRefused(f"artifact {name} digest {digest!r} is not "
                                   "sha256:<64 hex> - digests are the whole "
                                   "point of the release body")
        digests[name] = digest
    for name in REQUIRED_IMAGES:
        if name not in digests:
            raise PromotionRefused(
                f"artifact digest for {name} was not supplied - the release "
                "must quote both first-party images or say nothing")
    attestation_text = ""
    if args.attestation:
        attestation_text = Path(args.attestation).read_text(encoding="utf-8")
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
                      f"PR; candidate {sha}; tree-verified against master at "
                      f"{tag_commit} (#1584)")
        gitlet(args, root, "tag", "-a", "-m", annotation, tag, tag_commit)
        gitlet(args, root, "push", args.remote, f"refs/tags/{tag}")
        print(f"finalize: tagged {tag} at {tag_commit[:12]}")
    body = (f"Stable release {version}, promoted by the protected path of "
            f"#1584.\n\n- candidate `{sha}`\n- release commit `{tag_commit}` "
            "(tree-identical to the candidate)\n\n**Artifacts "
            "(digests, ghcr.io/mrmap-community):**\n")
    for name, digest in sorted(digests.items()):
        body += f"- `{name}`: `{digest}`\n"
    if attestation_text:
        body += ("\n<details><summary>promotion attestation "
                 "(mrmap-release-candidate/1)</summary>\n\n```json\n"
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
    tag = f"v{version}"
    branch = f"release/v{version}"
    master = gitlet(args, root, "rev-parse", args.master_ref)
    steps = {}
    steps["frozen_branch"] = bool(remote_ref(args, root, f"refs/heads/{branch}"))
    prs = json.loads(gh(args, "pr", "list", "--repo", args.repository,
                        "--head", branch, "--base", "master", "--state",
                        "all", "--json", "number,state") or "[]")
    steps["release_pr"] = prs[0]["state"].lower() if prs else "none"
    steps["master_carries_candidate"] = is_ancestor(args, root, sha, master)
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
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version = candidate_version_at(args, root, sha)
    steps = reconcile_state(args, root, version, sha)
    print(f"status of the {version} promotion (candidate {sha[:12]}):")
    for name, state in steps.items():
        print(f"  {name:26} {state}")
    return EXIT_OK


def cmd_gate(args):
    """The callable contract of #1609: what is frozen, what master carries."""
    root = Path(args.root)
    # Read in both modes: `--simulate` promises that no REMOTE is consulted, not
    # that the caller's file goes unread, and the contract asks for the digests of
    # the candidate in either answer. Absent digests are reported as absent - a
    # gate that invented them would be the hand-pasted digest again, one level up.
    digests = artifact_digests(args, args.sha, args.version)
    if args.simulate:
        print(json.dumps({
            "gate": "release-promotion", "status": "simulated",
            "note": "a dry-run answer: nothing was read from a remote, the "
                    "documentation epic must not schedule real pages on it",
            "candidate": {"sha": args.sha, "version": args.version},
            "artifacts": digests or None,
        }, indent=2))
        return EXIT_OK
    gitlet(args, root, "fetch", "--quiet", args.remote)
    gitlet(args, root, "fetch", "--quiet", args.remote, "master")
    sha = args.sha or gitlet(args, root, "rev-parse", args.develop_ref)
    version = args.version or candidate_version_at(args, root, sha)
    steps = reconcile_state(args, root, version, sha)
    green = (steps["master_carries_candidate"] and
             steps["tag"] == "at-master-tip" and
             steps["github_release"] == "exists")
    print(json.dumps({
        "gate": "release-promotion",
        "status": "green" if green else "pending",
        "frozen": {"sha": sha, "version": version,
                   "branch": f"release/v{version}",
                   "source": args.repository},
        "master": {"tip": gitlet(args, root, "rev-parse", args.master_ref),
                   "carries_candidate": steps["master_carries_candidate"]},
        "tag": steps["tag"], "github_release": steps["github_release"],
        # In the real answer too, not only in `--simulate`: this JSON is the
        # callable contract of #1609, and a caller decides from it. A gate that
        # reads the candidate's artifacts and reports them nowhere lets a
        # `green` answer say nothing about which bytes it was green for.
        "artifacts": digests or None,
    }, indent=2))
    return EXIT_OK if green else EXIT_FAIL


# ---------------------------------------------------------------------------


# The tool-wide options, and the default each carries. They are accepted on
# either side of the subcommand, which is not argparse's default behaviour and
# has to be asked for on purpose: `release-promotion.yml` has always assembled
# `--root . … gate` and `candidate-images.yml` assembles `gate … --root .`
# (#1799), and a caller should not have to know which half of a parser a flag
# was declared on. Declaring them plainly on both sides would be a trap - a
# subparser writes its own defaults over whatever the main parser collected -
# so the subparser copies default to SUPPRESS and stay out of the way, and the
# real defaults live on the main parser alone.
GLOBAL_OPTIONS = (
    ("--root", dict(type=Path, default=Path("."))),
    ("--remote", dict(default="origin")),
    ("--repository", dict(default="mrmap-community/mrmap")),
    ("--develop-ref", dict(default="origin/develop")),
    ("--master-ref", dict(default="origin/master")),
    ("--git-bin", dict(default="git")),
    ("--gh-bin", dict(default="gh")),
)


def add_global_opts(parser, defaults=True):
    for flag, kwargs in GLOBAL_OPTIONS:
        kwargs = dict(kwargs)
        if not defaults:
            kwargs["default"] = argparse.SUPPRESS
        parser.add_argument(flag, **kwargs)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="release_promotion",
        description=__doc__.splitlines()[0],
        epilog="exit 0 done or already done, 1 the step is decided against "
               "the candidate, 2 the step could not run")
    add_global_opts(parser)
    sub = parser.add_subparsers(dest="command", required=True)

    def subcommand(name):
        """A subcommand that also accepts the tool-wide options.

        ``defaults=False`` is what makes this work: a subparser parses into the
        namespace the main parser already filled, and an ordinary option would
        write its own default over a value given before the subcommand. SUPPRESS
        keeps a subparser silent about an option it was not handed.
        """
        sp = sub.add_parser(name)
        add_global_opts(sp, defaults=False)
        return sp

    def common(sp):
        sp.add_argument("--sha", default=None)
        sp.add_argument("--version", default=None)
        sp.add_argument("--expect-version", default=None)

    def artifacts_opt(sp):
        """Where the artifact digests of the candidate come from.

        Either door may be empty; ``artifact_digests`` merges them and refuses a
        contradiction between the two rather than preferring one.
        ``--registry-base`` belongs with them because a digest only means
        anything inside the registry that wrote it, and a candidate rehearsed in
        an isolated registry is the documented way to prove the path without a
        production push (#1799).
        """
        sp.add_argument("--artifact", action="append", default=[])
        sp.add_argument("--candidate-evidence", default=None, metavar="PATH",
                        dest="candidate_evidence",
                        help="the JSON evidence file image_release.py --attest "
                             "wrote for THIS candidate; its digests are used "
                             "instead of hand-pasted --artifact lines")
        sp.add_argument("--registry-base", default=None, dest="registry_base",
                        metavar="NAMESPACE",
                        help="registry and namespace the evidence file was "
                             "written for (default: the release registry of "
                             "image_release.py)")

    sp = subcommand("plan")
    common(sp)
    sp.set_defaults(func=cmd_plan)
    sp = subcommand("evidence")
    common(sp)
    sp.add_argument("--checks-file", default=None)
    artifacts_opt(sp)
    sp.add_argument("--manual", action="append", default=[])
    sp.add_argument("--output", default=None)
    sp.set_defaults(func=cmd_evidence)
    sp = subcommand("preflight")
    common(sp)
    sp.add_argument("--evidence", required=True)
    sp.add_argument("--report", action="append", default=[])
    sp.add_argument("--channel", default="stable")
    sp.add_argument("--actor", default=None)
    sp.add_argument("--output", default=None)
    sp.set_defaults(func=cmd_preflight)
    sp = subcommand("open-release-pr")
    common(sp)
    sp.set_defaults(func=cmd_open_release_pr)
    sp = subcommand("finalize")
    common(sp)
    artifacts_opt(sp)
    sp.add_argument("--attestation", default=None)
    sp.add_argument("--alias", action="append", default=[])
    sp.set_defaults(func=cmd_finalize)
    sp = subcommand("sync")
    common(sp)
    sp.set_defaults(func=cmd_sync)
    sp = subcommand("status")
    common(sp)
    sp.set_defaults(func=cmd_status)
    sp = subcommand("gate")
    common(sp)
    artifacts_opt(sp)
    sp.add_argument("--simulate", action="store_true")
    sp.set_defaults(func=cmd_gate)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
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
