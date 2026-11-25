#!/usr/bin/env python3
"""epic_branch: resolve an issue's epic integration branch and police PR targets.

Host-side check carried by this repository; run it as `python3 scripts/epic_branch.py
<command>` from the repository root. Standard library only. It reads GitHub through
`gh`, reads branch heads through read-only `git ls-remote` / `git merge-base`, and
writes nothing unless a write subcommand names `--write`. Exit 0 when the answer is
clean, 1 when a violation is reported in strict mode, 2 when the question could not be
answered at all - the fail-closed exit.

WHY THIS EXISTS
---------------
docs/source/development/epic-integration-contract.rst (#1590) is the contract; this is
the executable half of it (#1591). Before this tool exactly one target edge was checked
anywhere: `.github/workflows/branch-policy.yml` fires only on a PR whose base is
`master` and asserts the head is `develop` in the same repository. Everything else the
contract calls a rule was prose in `AGENTS.md` - "use the designated epic integration
branch if applicable", with no definition of *designated* and no *applicable* - and no
workflow ever looked at a develop-side base. This tool is new coverage; it modifies no
existing check and weakens none.

WHAT IT DECIDES
---------------
`resolve` answers, from the native issue hierarchy alone, which branch the work of an
issue belongs on, per the decision table of the contract:

  R1  no native parent                                -> base develop
  R2  native parent is an OPEN epic declaring `slug:` -> base epic/<slug>
  R3  native parent is an OPEN epic without a slug    -> develop (bootstrap row)
  R9  that epic is itself a sub-issue                 -> epic/<parent-slug>
  R10 closed epic whose children are on develop       -> develop (follow-up is a new issue)
  R11 closed epic whose work never reached develop    -> refuse; a person decides

`check-pr` answers the same contract from the pull request side: R4/R5 (a child PR's
base is its own epic branch and nothing else, so a child PR straight to `develop`, to
`master`, or into another epic's branch is refused), R6 (an epic branch integrates into
`develop`, or nested into its parent's branch, and nothing else), R12 (the child head
must still descend from the epic head), and the one edge `branch-policy.yml` already
guards, restated so the whole target contract has a single home.

Anything the tool cannot read, or cannot read unambiguously, is an error and never a
guess, because the consumer of this answer branches from that commit and points a PR at
it: a missing/ambiguous parent link, a body that names a parent the API does not report,
a malformed or over-long slug, a slug two open epics share, an `epic/*` branch no open
epic claims, a closed epic whose children cannot be read, a failing `gh` or `git`.

WHAT IT MAY WRITE
-----------------
Two subcommands, both human-invoked, both idempotent, neither of them an approval:

  create-branch --epic N --write  create `epic/<slug>` at the tip of origin/develop
                                  (rule 3), or report that it stands and reuse it
  retarget --pr N --base B --write  move an OPEN pull request's base onto its resolved
                                    target, and only onto that target

`create-branch` pushes exactly one branch that does not exist yet, at a SHA it just read
from `origin/develop`. It never pushes to, moves, deletes or force-pushes a branch that
already stands - an existing epic branch can only be reused - so the `AGENTS.md` rules
about permanent branches are untouched rather than extended. `retarget` patches a PR's
base and nothing else: no push, no approval, no merge, no label. Both refuse the agent
bot identity, and both need `--write`, so nothing that imports this module writes by
forgetting a flag.

WHAT IT DELIBERATELY IS NOT
---------------------------
* not an approver: it says where a PR belongs, never whether it should merge. Approval,
  merge, branch protection and `agent: approved` stay with people (rule 15).
* not a bypass: no branch, author or label skips a check, and no finding is softened
  for a draft PR.
* not the scheduler: `scripts/next_eligible.py` remains the eligibility screen and is
  not modified here; #1592 wires AO to read this answer.
* not the readiness gate: R7/R8 - every child merged, every cross-epic dependency an
  ancestor of both develop and the epic head - is #1593.
* not the QA matrix: `.github/workflows/pr-target-policy.yml` carries `check-pr` on a PR
  into `develop`, and nothing else. Adding `epic/**` to the QA workflows' trigger lists is
  #1594's rollout decision, which is also the issue that owns `STRICT_FROM` below.

ROLLOUT
-------
Superseded by #1592. Auto remains advisory on every date, including when a legacy
strict-date environment override is present. Explicit --mode strict is retained only
for historical diagnostics pending removal in #1593. This tool is not a prerequisite
for GitHub Flow; see docs/source/development/github-flow.rst.

Commands
--------
  resolve       --issue N [--json]          where does this issue's work belong
  check-pr      --pr N [--no-ancestry]      is this pull request targeting what it should
  check-branch  --epic N [--json]           R6 and uniqueness of one epic branch
  audit [--scope epic|all-approved]         open epics, and open PRs, for the rollout
  create-branch --epic N [--write]          create epic/<slug> from origin/develop
  retarget      --pr N --base B [--write]   move an open PR's base onto its target
  codes                                     every finding code this tool can report
  check                                     the tool's own self-test

The offline suite is scripts/test_epic_branch.py (fixture-driven, injected command
runner, no `gh`, no network, no real repository), as every suite under scripts/.
"""

import argparse
import ast
import functools
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from subprocess import TimeoutExpired

SCHEMA = "epic-branch/v1"

# Historical date, superseded by #1592. It remains in diagnostic output only;
# neither this date nor its environment override can activate automatic strict mode.
STRICT_FROM = "2026-12-21"
STRICT_FROM_ENV = "MRMAP_EPIC_STRICT_FROM"

PERMANENT_BRANCHES = ("master", "develop")
EPIC_PREFIX = "epic/"
DEVELOP = "develop"
MASTER = "master"
# A slug is a branch name component, so it carries AGENTS.md's rule for those:
# lowercase, kebab-cased, at most 20 characters, and at least two characters because a
# one-character branch name is not an identity anybody can read.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,18}[a-z0-9]$")
# The *shape* of a declaration, deliberately looser than SLUG_RE: a first line that
# reads `slug:` but carries a value the contract refuses must be an error, not silently
# "no declaration" - the second reading routes an epic's children to develop, which is
# exactly the silent re-routing rule 1 exists to prevent.
SLUG_LINE_RE = re.compile(r"^\s*(?:<!--\s*)?slug:\s*(\S.*?)\s*(?:-->)?\s*$", re.I)
# "Parent: #1588", "Part of epic #1588" - the readable echo the native link is
# authoritative over. A body that names a parent the API does not report is not a
# second opinion to average with the first: it is unverifiable metadata, so the tool
# refuses rather than choosing which parent an issue has.
PARENT_PROSE_RE = re.compile(r"(?i)\b(?:parent|epic)\b[^\n#]{0,24}#(\d+)")
# The repository's branch convention, shared with scripts/wip and next_eligible: a path
# segment starting with issue-<N>. A bare digit run inside a slug names no issue.
CHILD_ISSUE_RE = re.compile(r"(?:^|/)(?:issue[-_]?|#)(\d+)")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
DENIED_LOGINS = {"mrmap-agent-bot"}
CMD_TIMEOUT = 120
DEFAULT_PAGE = 100


class CommandError(Exception):
    """A gh or git call failed; the tool fails closed on it.

    exit_code carries the command's exit status when there was one, so a caller can
    read a defined non-zero status (git merge-base answers 1 for "not an ancestor")
    without parsing text.
    """

    exit_code = None


class EpicBranchError(Exception):
    """Why the whole question could not be answered; the caller fails closed.

    `code` names the refusal when the tool knows which rule was hit - an `epic/*` head
    no open epic declares is a rule-2 refusal, not a `gh` hiccup - and stays
    `metadata-unreadable` for everything the tool simply could not read. The gated
    commands copy it into their error result, so a fail-closed answer keeps the code a
    reader can act on instead of collapsing every refusal into one label.
    """

    code = "metadata-unreadable"

    def __init__(self, message, code=None):
        Exception.__init__(self, message)
        if code:
            self.code = code


class Finding(object):
    """One reported problem.

    `code` is the machine-readable contract of this tool: the suite beside this file,
    CI annotations and the documentation page all name findings by it, and `codes`
    prints the vocabulary derived from this file's own syntax.
    """

    def __init__(self, code, message, severity="error"):
        self.code = code
        self.message = message
        self.severity = severity

    def as_dict(self):
        return {"code": self.code, "message": self.message, "severity": self.severity}


# --------------------------------------------------------------------------- runners


def subprocess_runner(argv):
    """Run argv, return stdout, raise CommandError on a non-zero exit or timeout.

    A command that hangs is a failure like any other: the caller fails closed with a
    status=error result instead of waiting on a stuck gh or a stuck network.
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except (OSError, TimeoutExpired) as e:
        raise CommandError("%s could not be run: %s" % (" ".join(argv[:3]), e))
    if proc.returncode != 0:
        err = CommandError("%s exited %d: %s" % (" ".join(argv[:3]), proc.returncode,
                                                 (proc.stderr or proc.stdout or "").strip()))
        err.exit_code = proc.returncode
        raise err
    return proc.stdout or ""


def gh_graphql(runner, query):
    """Run one GraphQL query through gh; errors and missing data fail closed."""
    try:
        out = runner(["gh", "api", "graphql", "-f", "query=" + query])
    except CommandError as e:
        raise EpicBranchError("the GitHub GraphQL call failed (a missing permission "
                              "reads the same way): %s" % e)
    try:
        doc = json.loads(out or "")
    except ValueError:
        raise EpicBranchError("GitHub GraphQL returned something that is not JSON")
    if not isinstance(doc, dict):
        raise EpicBranchError("GitHub GraphQL returned no response object")
    if doc.get("errors"):
        raise EpicBranchError("GitHub GraphQL error: "
                              + "; ".join(str(e.get("message", e)) for e in doc["errors"]))
    if not isinstance(doc.get("data"), dict):
        raise EpicBranchError("GitHub GraphQL returned no data")
    return doc["data"]


def gh_rest_items(runner, path):
    """All items of a paginated REST listing; a truncated listing fails closed.

    Pagination is not a nicety here: the uniqueness rule and the closed-epic rule are
    both "for every epic/PR", and a check that read only page one could report an
    absent collision.
    """
    try:
        out = runner(["gh", "api", path, "--paginate"])
    except CommandError as e:
        raise EpicBranchError("GitHub REST %s failed: %s" % (path, e))
    items, dec, pos = [], json.JSONDecoder(), 0
    while pos < len(out):
        while pos < len(out) and out[pos] in " \n\r\t":
            pos += 1
        try:
            obj, pos = dec.raw_decode(out, pos)
        except ValueError:
            raise EpicBranchError("GitHub REST %s returned something that is not JSON" % path)
        items.extend(obj if isinstance(obj, list) else [obj])
    return items


def resolve_repo(runner):
    try:
        out = runner(["gh", "repo", "view", "--json", "nameWithOwner"])
    except CommandError as e:
        raise EpicBranchError("could not ask gh which repository this checkout is: %s" % e)
    try:
        return json.loads(out)["nameWithOwner"]
    except (ValueError, KeyError, TypeError):
        raise EpicBranchError("could not read the repository of this checkout")


def origin_heads(runner):
    """{branch: sha} on origin; ls-remote reads the heads without writing any ref."""
    try:
        out = runner(["git", "ls-remote", "--heads", "origin"])
    except CommandError as e:
        raise EpicBranchError("git ls-remote origin failed, so no branch head can be "
                              "trusted: %s" % e)
    heads = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            heads[parts[1][len("refs/heads/"):]] = parts[0].strip()
    return heads


def is_ancestor(runner, sha, rev):
    """True when `sha` is an ancestor of `rev`; anything but 0 or 1 from git fails closed."""
    if not SHA_RE.match(sha or ""):
        raise EpicBranchError("%r is not a commit SHA - refusing to guess" % sha)
    try:
        runner(["git", "merge-base", "--is-ancestor", sha, rev])
        return True
    except CommandError as e:
        if getattr(e, "exit_code", None) == 1:
            return False
        raise EpicBranchError("git merge-base --is-ancestor %s %s failed: %s" % (sha, rev, e))
    except TimeoutExpired as e:
        raise EpicBranchError("git merge-base --is-ancestor %s %s timed out: %s" % (sha, rev, e))


def fetch_ref(runner, ref):
    """Update one remote ref so an ancestry question can actually be answered."""
    try:
        runner(["git", "fetch", "origin", ref])
    except CommandError as e:
        raise EpicBranchError("git fetch origin %s failed, so merge ancestry cannot be "
                              "trusted: %s" % (ref, e))


# ------------------------------------------------------------------------ slug rules


def slug_findings(raw, epic_number=None):
    """The findings a declared-but-refused slug carries, or None when it is valid.

    Never repaired: a tool that "cleaned up" `My_Slug` into `my-slug` would silently mint
    a second identity for one epic, and R2 keys every child PR base off that identity.
    """
    who = " of epic #%d" % epic_number if epic_number else ""
    reason = ("a slug is a branch name component: lowercase kebab-case of 2 to 20 "
              "characters, per the rule AGENTS.md already imposes on it (rule 1)")
    if raw != raw.lower():
        return Finding("epic-slug-invalid",
                       "slug `%s`%s is not lowercase; %s" % (raw, who, reason))
    if len(raw) > 20:
        return Finding("epic-slug-too-long",
                       "slug `%s`%s is %d characters, over the 20 a branch name component "
                       "may carry" % (raw, who, len(raw)))
    if not SLUG_RE.match(raw):
        return Finding("epic-slug-invalid",
                       "slug `%s`%s is not kebab-case; %s" % (raw, who, reason))
    return None


def parse_slug(body):
    """The `slug:` declaration of an epic body: (slug, Finding or None).

    The declaration is the first content line of the body - markdown headings and blank
    lines do not count, because a body that opens with `# Title` still declares its slug
    where `AGENTS.md` says to. That is why the identity is readable from the issue alone,
    the one artifact an agent still holds after a context loss. A line that reads `slug:`
    but carries a refused value is an error, never "no declaration": the second reading
    routes the epic's children to develop, which is exactly the silent re-routing rule 1
    exists to prevent.
    """
    for line in (body or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        m = SLUG_LINE_RE.match(line)
        if not m:
            return None, None
        raw = m.group(1)
        finding = slug_findings(raw)
        return (None, finding) if finding else (raw, None)
    return None, None


def epic_branch(slug):
    return EPIC_PREFIX + slug


def branch_slug(branch):
    """The slug a branch name claims, or None when it is not an epic branch."""
    if isinstance(branch, str) and branch.startswith(EPIC_PREFIX):
        return branch[len(EPIC_PREFIX):]
    return None


# --------------------------------------------------------------------- issue reading


def issue_node(runner, repo, number, fields):
    """One issue through GraphQL; a missing issue is a fail-closed error."""
    owner, name = repo.split("/")
    q = ('{repository(owner:"%s",name:"%s"){issue(number:%d){%s}}}'
         % (owner, name, number, fields))
    issue = (gh_graphql(runner, q).get("repository") or {}).get("issue")
    if not isinstance(issue, dict):
        raise EpicBranchError("issue #%d was not found in %s" % (number, repo))
    return issue


def epic_facts(runner, repo, number):
    """Everything needed to treat one issue as an epic.

    `bodyParent` is the number the issue's own body names as ITS parent. It is read so
    that "the body names a parent the API does not report" (a refusal) can be told apart
    from "the body names this very epic" (agreement) - the native relation stays the
    only admissible source of parentage.
    """
    node = issue_node(runner, repo, number,
                      'number title state stateReason bodyText '
                      'labels(first:100){nodes{name}}')
    labels = [lab.get("name") for lab in ((node.get("labels") or {}).get("nodes") or [])
              if isinstance(lab, dict) and isinstance(lab.get("name"), str)]
    slug, slug_finding = parse_slug(node.get("bodyText") or "")
    body_parent = None
    for cand in PARENT_PROSE_RE.findall(node.get("bodyText") or ""):
        if int(cand) != number:
            body_parent = int(cand)
            break
    return {"number": number, "title": node.get("title") or "", "state": node.get("state"),
            "stateReason": node.get("stateReason"), "labels": labels,
            "slug": slug, "slugFinding": slug_finding, "bodyParent": body_parent}


def native_parent(runner, repo, number):
    """The native parent number of an issue, or None.

    `Issue.parent` is the far side of the sub-issue relation - the same fact
    `sub_issues` answers from the epic side, and the relation `AGENTS.md` already makes
    authoritative over any label or title prefix. A node that reports itself as its own
    parent is contradictory data, not a hierarchy to interpret.
    """
    node = issue_node(runner, repo, number, 'parent{number}')
    parent = node.get("parent")
    if parent is None:
        return None
    num = parent.get("number") if isinstance(parent, dict) else None
    if not isinstance(num, int):
        raise EpicBranchError("#%d reports a parent without a readable number" % number)
    if num == number:
        raise EpicBranchError("#%d reports itself as its own parent - the native "
                              "hierarchy is inconsistent" % number)
    return num


def epic_children(runner, repo, epic_number):
    """The native sub-issue numbers of an epic, in GitHub's curated listing order."""
    node = issue_node(runner, repo, epic_number,
                      'subIssues(first:100){totalCount pageInfo{hasNextPage} '
                      'nodes{number state}}')
    conn = node.get("subIssues") or {}
    nodes = conn.get("nodes")
    if not isinstance(nodes, list) or any(not isinstance(n, dict) for n in nodes):
        raise EpicBranchError("the sub-issue listing of epic #%d is not readable" % epic_number)
    if (conn.get("pageInfo") or {}).get("hasNextPage"):
        raise EpicBranchError("the sub-issue listing of epic #%d spans more than one page; "
                              "refusing to decide on a partial listing" % epic_number)
    total = conn.get("totalCount")
    if isinstance(total, int) and total != len(nodes):
        raise EpicBranchError("the sub-issue listing of epic #%d reads %d of %s"
                              % (epic_number, len(nodes), total))
    return [n.get("number") for n in nodes if isinstance(n.get("number"), int)]


def epic_listing(runner, repo, listings=None):
    """Every `Epic`-labelled issue with its declared slug, open and closed.

    The label is the triage view and the native relation is the fact - the contract says
    so, and this tool obeys it for parentage. But slug uniqueness can only be measured
    over the set of issues that *claim* to be epics: the native relation cannot answer
    "does another epic already use this slug, and does its branch still stand?". Closed
    epics are included because rule 2 names one explicitly - a slug may not collide with
    "the branch name of a closed epic that still stands" - and because a closed epic's own
    standing branch is stale (rule 11), not unowned. Cached per (runner, repo): the
    uniqueness rule asks it once per candidate.
    """
    listings = listings if listings is not None else {}
    if repo in listings:
        return listings[repo]
    items = gh_rest_items(runner, "repos/%s/issues?state=all&labels=Epic&per_page=%d"
                          % (repo, DEFAULT_PAGE))
    out = []
    for it in items:
        if not isinstance(it, dict) or "pull_request" in it:
            continue  # the REST issues listing includes pull requests
        num = it.get("number")
        if not isinstance(num, int):
            raise EpicBranchError("an `Epic`-labelled listing entry has no issue number")
        slug, finding = parse_slug(it.get("body") or "")
        out.append({"number": num, "state": (it.get("state") or "OPEN").upper(),
                    "slug": slug, "slugFinding": finding})
    listings[repo] = out
    return out


def open_epics(runner, repo, listings=None):
    """The open epics of `epic_listing` - the set an integration branch may belong to."""
    return [e for e in epic_listing(runner, repo, listings) if e["state"] == "OPEN"]


# ------------------------------------------------------------------ target resolution


def _result(**kw):
    base = {"schema": SCHEMA, "status": "ok", "error": None, "mode": None,
            "strict_from": None, "command": None, "row": None, "issue": None,
            "epic": None, "parentEpic": None, "target": None, "branch": None,
            "branchSha": None, "findings": [], "reason": ""}
    base.update(kw)
    return base


def _verb(name):
    """Stamp an envelope with the subcommand that produced it.

    `render_human` chooses its shape from this field and never from which optional keys
    happen to be filled, so an unstamped result is not merely bland but wrong: a
    `resolve` of an independent issue rendered as an epic branch of epic #None, and a
    `retarget` lost the base transition it exists to report. Stamping every return of
    the six public builders - the clean answer and the fail-closed one alike - is what
    makes the renderer's keying total rather than best effort; a result that still
    arrives without a verb is reported as unrecognised, never guessed at.
    """
    def decorate(builder):
        @functools.wraps(builder)
        def stamped(*args, **kwargs):
            result = builder(*args, **kwargs)
            result["command"] = name
            return result
        stamped._verb = name
        return stamped
    return decorate


def _err(message, code="metadata-unreadable", row=None, command=None):
    return _result(status="error", error=message, row=row, command=command,
                   findings=[Finding(code, message).as_dict()])


@_verb("resolve")
def resolve_issue(runner, issue, repo=None, heads=None, ancestry=True, mode=None,
                  today=None, _cache=None, _listings=None):
    """The decision table for one issue: where its branch starts, what its PR bases on.

    `status` is "error" whenever the metadata cannot be read or is ambiguous; the caller
    must then branch nothing and open nothing.

    The result carries `mode`, which is what makes rule 16 (bootstrap) expressible without
    hard-coding one epic into the tool. Enforcement of these rows starts on the same date
    the pull-request gate does, so a consumer that must not move an in-flight epic's
    children yet reads `advisory` and keeps them on `develop`, and reads `strict` once the
    rollout has landed. The verdict itself never depends on the mode - only what a consumer
    is allowed to do with it does. Unlike the gated commands, `resolve` still exits 2 on an
    unreadable or ambiguous answer in either half: nothing here is a check somebody's pull
    request has to survive, and a caller about to branch needs a real answer.
    """
    mode = mode or mode_for(today_or(today))
    try:
        res = _resolve_issue(runner, issue, repo=repo, heads=heads, ancestry=ancestry,
                             _cache=_cache, _listings=_listings)
    except EpicBranchError as e:
        res = _err(str(e), command="resolve")
    res["mode"] = mode
    res["strict_from"] = strict_from()
    return res


def _resolve_issue(runner, issue, repo=None, heads=None, ancestry=True, _cache=None,
                   _listings=None):
    if repo is None:
        repo = resolve_repo(runner)
    if heads is None:
        heads = origin_heads(runner)
    cache = _cache if _cache is not None else {}
    listings = _listings if _listings is not None else {}

    node = issue_node(runner, repo, issue, 'number title bodyText')
    prose = [int(n) for n in PARENT_PROSE_RE.findall(node.get("bodyText") or "")
             if int(n) != issue]
    try:
        parent = native_parent(runner, repo, issue)
    except EpicBranchError as e:
        return _err(str(e))

    if parent is None:
        if prose:
            return _err("#%d names parent #%d in its body but GitHub reports no native "
                        "sub-issue parent; register the link with `gh issue edit <child> "
                        "--add-sub-issue %d` - the tool will not pick an epic out of "
                        "prose" % (issue, prose[0], prose[0]), "parent-missing")
        return _result(row="R1", issue=issue, target=DEVELOP, branch=DEVELOP,
                       branchSha=heads.get(DEVELOP),
                       reason="no native parent: an independent issue keeps the current "
                              "rule and integrates into develop (R1)")

    epic = _epic_of(runner, repo, parent, cache)
    result = _result(issue=issue, epic=parent)
    if epic["state"] == "OPEN":
        return _resolve_open_epic(runner, repo, heads, epic, result, cache, listings)
    if epic["state"] != "CLOSED":
        return _err("epic #%d reports state %r, which is neither OPEN nor CLOSED"
                    % (parent, epic["state"]))
    return _resolve_closed_epic(runner, repo, heads, epic, result, ancestry)


def _epic_of(runner, repo, number, cache):
    if number not in cache:
        cache[number] = epic_facts(runner, repo, number)
    return cache[number]


def _slug_conflict(runner, repo, epic_number, slug, heads, listings=None):
    """Rule 2: one slug identifies one epic, and its branch belongs to that epic.

    Two open epics sharing a slug would silently merge two features into one integration
    branch, and an `epic/<slug>` head that no open epic declares is a branch nobody can
    account for. Both are refusals rather than decisions - the tool cannot know which
    epic owns the name, and guessing is how an unrelated branch becomes an integration
    target.
    """
    listing = epic_listing(runner, repo, listings)
    branch = epic_branch(slug)
    standing = branch in heads
    for other in listing:
        if other["number"] == epic_number or other["slug"] != slug:
            continue
        # A closed epic whose branch is gone frees its slug for reuse; one whose branch
        # still stands does not, and an open epic never shares a slug at all (rule 2).
        if other["state"] == "OPEN" or standing:
            return Finding("epic-slug-conflict",
                           "slug `%s` is declared by epic #%d (%s) as well; one slug is "
                           "one integration branch, so one of the declarations is wrong "
                           "(rule 2)" % (slug, other["number"], other["state"].lower()))
    if standing and not any(e["number"] == epic_number for e in listing):
        return Finding("epic-branch-unclaimed",
                       "`%s` stands on origin but #%d is not an `Epic`-labelled issue "
                       "carrying the matching `slug:` declaration - a branch nobody owns "
                       "is not an integration target" % (branch, epic_number))
    return None


def _resolve_open_epic(runner, repo, heads, epic, result, cache, listings):
    epic_number = epic["number"]
    if epic["slugFinding"]:
        finding = epic["slugFinding"]
        return _result(status="error", error=finding.message,
                       findings=[finding.as_dict()])
    if not epic["slug"]:
        result.update(row="R3", target=DEVELOP, branch=DEVELOP, branchSha=heads.get(DEVELOP),
                      reason="epic #%d declares no `slug:` on its first body line: "
                             "bootstrap row - the child integrates into develop and the "
                             "slug declaration is owed first (R3)" % epic_number)
        return result

    slug = epic["slug"]
    conflict = _slug_conflict(runner, repo, epic_number, slug, heads, listings)
    if conflict:
        return _result(status="error", error=conflict.message,
                       findings=[conflict.as_dict()])

    # R9: a nested epic integrates upward, so its children work on the PARENT's branch;
    # exactly one branch of a nested tree ever has develop as its base.
    try:
        grandparent = native_parent(runner, repo, epic_number)
    except EpicBranchError as e:
        return _err("the parent of epic #%d cannot be read: %s" % (epic_number, e))
    if grandparent is None and epic["bodyParent"] and epic["bodyParent"] != epic["number"]:
        # R9 routes a nested epic's children onto the PARENT's branch, so an unlinked
        # parent claim cannot be treated as cosmetic here: the child PR base would be
        # picked from a hierarchy GitHub does not report.
        return _err("epic #%d names #%d as its parent in its body but GitHub reports no "
                    "native parent; nesting decides which branch its children work on, so "
                    "register the link with `gh issue edit %d --add-sub-issue %d` first"
                    % (epic_number, epic["bodyParent"], epic_number, epic["bodyParent"]),
                    "parent-missing")
    if grandparent is None:
        branch = epic_branch(slug)
        result["parentEpic"] = None
        reason = ("child of open epic #%d: the base is the epic branch `%s` and nothing "
                  "else (R2)" % (epic_number, branch))
    else:
        gp = _epic_of(runner, repo, grandparent, cache)
        if gp["state"] != "OPEN":
            return _err("epic #%d is a sub-issue of epic #%d, which is %s; a nested epic "
                        "integrates into its open parent's branch (R9), so a person "
                        "decides what an epic under a closed parent means"
                        % (epic_number, grandparent, gp["state"]), "epic-parent-closed")
        if gp["slugFinding"]:
            nested = gp["slugFinding"]
            return _result(status="error",
                           error="epic #%d is nested under #%d, whose own slug the "
                                 "contract refuses: %s" % (epic_number, grandparent,
                                                           nested.message),
                           findings=[nested.as_dict()])
        if not gp["slug"]:
            result.update(row="R3", target=DEVELOP, branch=DEVELOP,
                          branchSha=heads.get(DEVELOP),
                          reason="epic #%d is nested under #%d, which declares no slug: "
                                 "bootstrap row until the parent declares one (R3, R9)"
                                 % (epic_number, grandparent))
            return result
        branch = epic_branch(gp["slug"])
        result["parentEpic"] = {"number": grandparent, "slug": gp["slug"]}
        reason = ("epic #%d is nested under #%d: its child works on the parent epic's "
                  "branch `%s` (R9)" % (epic_number, grandparent, branch))

    sha = heads.get(branch)
    if sha is None:
        result.update(row="R9" if result["parentEpic"] else "R2", target=branch,
                      branch=branch, branchSha=None,
                      findings=[Finding(
                          "epic-branch-missing",
                          "epic branch `%s` of epic #%d does not exist on origin; a person "
                          "creates it from origin/develop with `scripts/epic_branch.py "
                          "create-branch --epic %d --write` before its children are "
                          "branched (rule 3)" % (branch, epic_number, epic_number)).as_dict()],
                      reason=reason + "; the branch does not exist yet")
        return result
    result.update(row="R9" if result["parentEpic"] else "R2", target=branch, branch=branch,
                  branchSha=sha, reason=reason)
    return result


def _resolve_closed_epic(runner, repo, heads, epic, result, ancestry):
    """R10 / R11: did the closed epic's work actually reach develop?

    "Closed" is not "shipped", and this is the row that stops an abandoned epic from
    silently becoming a permanent home for follow-up work. The reading that decides is
    ancestry, not the closed label: if none of the epic's own merged children is
    reachable from origin/develop, the epic never integrated.
    """
    epic_number = epic["number"]
    develop = heads.get(DEVELOP)
    if not develop:
        return _err("origin/%s is not readable, so the closure of epic #%d cannot be "
                    "classified as integrated or abandoned" % (DEVELOP, epic_number))
    if not ancestry:
        result.update(row="R10", target=DEVELOP, branch=DEVELOP, branchSha=develop,
                      reason="epic #%d is closed and its children were not re-checked for "
                             "ancestry in this run (--no-ancestry); follow-up work is "
                             "treated as a new top-level issue on develop (R10)"
                             % epic_number)
        return result
    try:
        children = epic_children(runner, repo, epic_number)
    except EpicBranchError as e:
        return _err("epic #%d is closed but its native children cannot be read: %s"
                    % (epic_number, e))
    fetch_ref(runner, DEVELOP)
    merged = []
    for child in children:
        try:
            state = issue_node(runner, repo, child, 'number state').get("state")
        except EpicBranchError:
            state = None
        if state != "CLOSED":
            continue
        pr = _merged_pr_of(runner, repo, child)
        if pr and pr.get("merge_sha") and is_ancestor(runner, pr["merge_sha"],
                                                      "origin/" + DEVELOP):
            merged.append(child)
    if not children or merged:
        result.update(row="R10", target=DEVELOP, branch=DEVELOP, branchSha=develop,
                      reason="epic #%d is closed and its merged children are ancestors of "
                             "%s: follow-up work is a new top-level issue from develop, "
                             "and the old epic branch must not be recreated (R10)"
                             % (epic_number, DEVELOP))
        return result
    message = ("epic #%d is closed but none of its native children is merged into origin/"
               "%s - the epic's work never integrated (R11). A person reopens the epic or "
               "files a new top-level issue; an agent files neither"
               % (epic_number, DEVELOP))
    return _err(message, "epic-abandoned", row="R11")


def _merged_pr_of(runner, repo, number):
    """The merged PR whose timeline cross-references an issue, or None.

    Deliberately generous about *finding* the candidate and strict about what counts:
    the candidate comes from the timeline (GitHub leaves the native closing relation
    empty whenever an issue was closed by hand on a non-default branch), and only a PR
    that actually merged, with a merge commit, is returned - the ancestry question is
    then asked of git, not of a label.
    """
    try:
        events = gh_rest_items(runner, "repos/%s/issues/%d/timeline?per_page=%d"
                               % (repo, number, DEFAULT_PAGE))
    except EpicBranchError:
        return None
    for ev in events:
        if not isinstance(ev, dict) or ev.get("event") != "cross-referenced":
            continue
        src = (ev.get("source") or {}).get("issue") or {}
        num = src.get("number")
        if not src.get("pull_request") or not isinstance(num, int):
            continue
        if ("/%s/" % repo) not in (src.get("html_url") or ""):
            continue  # issue numbers are per-repository; another repo's #N is not this one
        try:
            view = json.loads(runner(["gh", "api", "repos/%s/pulls/%d" % (repo, num)]))
        except (CommandError, ValueError):
            continue
        if view.get("merged_at"):
            return {"number": num, "merge_sha": view.get("merge_commit_sha"),
                    "base": (view.get("base") or {}).get("ref")}
    return None


# ------------------------------------------------------------------------ PR checks


def pr_facts(runner, repo, number):
    """The REST view of one PR, narrowed to the fields the target rules read."""
    try:
        out = runner(["gh", "api", "repos/%s/pulls/%d" % (repo, number)])
    except CommandError as e:
        raise EpicBranchError("reading pull request #%d failed: %s" % (number, e))
    try:
        view = json.loads(out)
    except ValueError:
        raise EpicBranchError("pull request #%d is not readable as JSON" % number)
    head, base = view.get("head") or {}, view.get("base") or {}
    if not isinstance(head.get("ref"), str) or not isinstance(base.get("ref"), str):
        raise EpicBranchError("pull request #%d reports no head or base branch" % number)
    return {"number": number, "state": view.get("state"), "title": view.get("title") or "",
            "draft": bool(view.get("draft")), "head": head["ref"], "headSha": head.get("sha"),
            "headRepo": (head.get("repo") or {}).get("full_name"),
            "base": base["ref"], "baseRepo": (base.get("repo") or {}).get("full_name")}


@_verb("check-pr")
def check_pr(runner, pr_number, repo=None, mode=None, today=None, heads=None,
             ancestry=True):
    """Every target rule the contract gives a pull request, on one PR.

    Read-only toward GitHub. The findings are identical in advisory and strict mode;
    only the exit code depends on the mode, exactly as #1580 does it, so a rollout flip
    cannot change what is reported.

    `ancestry=False` skips only R12, the one rule that asks git whether the head commit
    descends from the epic head - needed on a shallow checkout, where that object may
    not be present. It is never defaulted off, and the result says so, so a run that
    skipped a rule cannot be read as a run that passed it.
    """
    mode = mode or mode_for(today_or(today))
    if repo is None:
        try:
            repo = resolve_repo(runner)
        except EpicBranchError as e:
            return _pr_error(pr_number, None, mode, str(e), e.code)
    try:
        if heads is None:
            heads = origin_heads(runner)
        pr = pr_facts(runner, repo, pr_number)
        listings = {}
        findings, row, target, epic = _pr_findings(runner, repo, pr, heads, listings,
                                                   ancestry)
    except EpicBranchError as e:
        # `e.code` is the whole point here: an unowned `epic/*` head is a rule-2 refusal
        # the author can act on, and a `gh` hiccup is not. Dropping the code would fold
        # the refusal back into `metadata-unreadable` and the CI annotation would say
        # "could not read" about a pull request that can be read perfectly well.
        return _pr_error(pr_number, repo, mode, str(e), e.code)
    errors = [f for f in findings if f.severity == "error"]
    return {"schema": SCHEMA, "status": "ok", "error": None, "pr": pr_number, "repo": repo,
            "mode": mode, "strict_from": strict_from(), "head": pr["head"],
            "headRepo": pr["headRepo"], "base": pr["base"], "baseRepo": pr["baseRepo"],
            "row": row, "target": target, "epic": epic, "ancestry": bool(ancestry),
            "findings": [f.as_dict() for f in findings],
            "exit_code": 1 if (errors and mode == "strict") else 0}


def _pr_error(pr_number, repo, mode, message, code=None):
    """The gated fail-closed answer: an unreadable or unowned head is an error result, and
    it only stops the check from going red while the rollout is advisory.

    `code` is the refusing rule where the tool knows it (`epic-branch-unclaimed` for an
    `epic/*` head no `Epic`-labelled issue declares), and `metadata-unreadable` for
    everything it simply could not read - so the CI annotation names what to fix. Both
    are spelled as literal Finding calls because `codes` derives the vocabulary from this
    file's own syntax, and a code held only in a variable drops out of it silently.
    """
    finding = (Finding(code, message) if code
               else Finding("metadata-unreadable", message))
    return {"schema": SCHEMA, "status": "error", "error": message, "pr": pr_number,
            "repo": repo, "mode": mode, "strict_from": strict_from(), "row": None,
            "target": None, "findings": [finding.as_dict()],
            "exit_code": 1 if mode == "strict" else 0}


def _pr_findings(runner, repo, pr, heads, listings=None, ancestry=True):
    """The decision table read from the pull request side: R1-R6, R9-R13.

    The reported row is the row `resolve_issue` decided on, not a label chosen here:
    #1594's rollout reads `row` to find out what still has to be migrated, so collapsing
    "genuinely independent issue" (R1) and "epic child still bootstrapping on develop"
    (R3, R10) into one name would hide exactly the population whose slug declaration is
    owed.
    """
    findings = []
    head, base, number = pr["head"], pr["base"], pr["number"]

    # R13 - the edge branch-policy.yml already guards, restated here so the target
    # contract has one home. The workflow stands; this tool never replaces or relaxes it.
    if base == MASTER:
        if head != DEVELOP or pr["headRepo"] != repo:
            findings.append(Finding(
                "master-target-violation",
                "PR #%d targets %s from `%s`%s; only this repository's `%s` may target "
                "`%s` (R13)" % (number, MASTER, head,
                                "" if pr["headRepo"] == repo
                                else " of fork `%s`" % pr["headRepo"], DEVELOP, MASTER)))
        return findings, "R13", MASTER, None

    if head.startswith(EPIC_PREFIX):
        return _epic_head_findings(runner, repo, pr, findings, listings, heads)

    m = CHILD_ISSUE_RE.search(head)
    if not m:
        findings.append(Finding(
            "head-branch-no-issue",
            "PR #%d has head branch `%s`, which names no issue: the target cannot be "
            "derived from it, so the branch must carry the issue number or the PR must "
            "say what it closes" % (number, head)))
        return findings, None, None, None

    issue = int(m.group(1))
    res = resolve_issue(runner, issue, repo=repo, heads=heads, _cache={},
                        _listings=listings)
    if res["status"] == "error":
        findings.append(Finding(
            "metadata-ambiguous",
            "PR #%d represents #%d, whose epic target cannot be resolved: %s"
            % (number, issue, res["error"])))
        return findings, res.get("row"), None, res.get("epic")
    target = res["target"]

    if base != target:
        # R4/R5: the two shapes carry different codes because the reader acts on them
        # differently - a child pointed straight at a permanent branch is the defect the
        # epic exists to remove, a base on some other branch is usually a copied PR. Both
        # are written as literals, because `codes` derives the vocabulary from the literal
        # Findings in this file and a code built in a variable would silently drop out of
        # the documented list.
        if base in PERMANENT_BRANCHES:
            findings.append(Finding(
                "child-targets-develop",
                "PR #%d (issue #%d) targets the permanent branch `%s`, but the resolved "
                "target of #%d is `%s`: an epic's child work stays on the epic branch "
                "until the epic integrates (R4); a PR into an epic branch is retargeted by "
                "a person, never silently rewritten by an agent - `scripts/epic_branch.py "
                "retarget --pr %d --base %s --write`"
                % (number, issue, base, issue, target, number, target)))
        else:
            findings.append(Finding(
                "child-wrong-base",
                "PR #%d (issue #%d) bases on `%s`, but the resolved target of #%d is `%s`; "
                "a child PR bases on its own epic branch and no other (R5) - `scripts/"
                "epic_branch.py retarget --pr %d --base %s --write`"
                % (number, issue, base, issue, target, number, target)))
        return findings, "R5", target, res.get("epic")

    if target.startswith(EPIC_PREFIX):
        # Fork identity: an epic integration branch is a branch of THIS repository, so a
        # head from a fork is not a descendant of the epic head and can never be proven
        # one - the ancestry question below cannot even be asked of git here. Epic work
        # is internal integration work; it is branched in the repository, not forked in.
        if pr["headRepo"] != repo:
            findings.append(Finding(
                "fork-head-target",
                "PR #%d integrates issue #%d into the epic branch `%s` but its head comes "
                "from `%s`; an epic branch is a branch of this repository and a fork head "
                "can never descend from it (R12)" % (number, issue, target,
                                                     pr["headRepo"])))
            return findings, "R12", target, res.get("epic")
        # R12: the epic moved on while the child was open. The fix is a merge of the
        # epic head into the child - never a rebase of a branch open for review.
        sha = res.get("branchSha") or heads.get(target)
        if pr.get("headSha") and sha and ancestry:
            fetch_ref(runner, target)
            if not is_ancestor(runner, pr["headSha"], "origin/" + target):
                findings.append(Finding(
                    "child-not-descendant",
                    "PR #%d bases on `%s` but its head commit %s does not descend from the "
                    "head of `%s`; the author merges `%s` into `%s` and CI re-runs (R12)"
                    % (number, target, pr["headSha"][:10], target, target, head)))
                return findings, "R12", target, res.get("epic")
        # The clean answer carries the row `resolve_issue` chose, so R2 and R9 stay
        # distinguishable on the PR side as they are on the resolve side.
        return findings, res.get("row") or "R2", target, res.get("epic")
    return findings, res.get("row") or "R1", target, res.get("epic")


def _epic_head_findings(runner, repo, pr, findings, listings=None, heads=None):
    """R6 and R9 for a PR whose HEAD is an epic branch.

    A name under `epic/` is only an integration branch if an `Epic`-labelled issue
    declares it, so this path asks the ownership question before it blesses anything:
    an unowned `epic/*` head fails closed with the same rule-2 refusal `resolve` answers
    through `_slug_conflict`, because the CI job that runs `check-pr` is the one place
    the rule was previously silent about. Ownership is measured over open *and* closed
    epics exactly as `_slug_conflict` measures it, so the branch of a closed epic is the
    stale branch of rule 11 - its own finding, a person's decision - and not rule 2's
    unowned one.
    """
    head, base, number = pr["head"], pr["base"], pr["number"]
    slug = branch_slug(head)
    claimants = [e for e in epic_listing(runner, repo, listings)
                 if slug and e["slug"] == slug]
    if not claimants:
        raise EpicBranchError(
            "PR #%d has `%s` as its head but no `Epic`-labelled issue declares the slug "
            "`%s`: an `epic/*` branch nobody owns is not an integration target (rule 2). "
            "The epic either never declared its slug or the branch was cut by hand - "
            "`check-branch --epic N` names which epic owns which branch"
            % (number, head, slug or "-"), "epic-branch-unclaimed")
    epic = _epic_for_branch(runner, repo, head, listings)
    if epic is None:
        findings.append(Finding(
            "epic-branch-stale",
            "PR #%d merges `%s`, whose epic #%d is %s; rule 11 retires the branch in the "
            "same act as the integration merge, so a person decides whether this pull "
            "request or the epic's closure is what is wrong (R6, R11)"
            % (number, head, claimants[0]["number"], claimants[0]["state"].lower())))
        return findings, "R6", None, None
    # Fork identity guards the integration edge exactly as it guards the child edge: an
    # epic branch is a branch of THIS repository, so a head that merely carries such a
    # name from a fork is not the epic's integration and cannot be proven one.
    if pr["headRepo"] != repo:
        findings.append(Finding(
            "fork-head-target",
            "PR #%d presents `%s` as the epic's integration into `%s` but its head comes "
            "from `%s`; an epic branch is a branch of this repository, so integration "
            "work is branched here and not forked in (R12)"
            % (number, head, base, pr["headRepo"])))
        return findings, "R12", None, epic
    if head not in heads:
        # The name is owned and the PR exists, but no such head stands on origin: the
        # branch was deleted under the pull request, so there is no integration to bless.
        findings.append(Finding(
            "epic-branch-missing",
            "PR #%d merges `%s`, which no longer exists on origin although epic #%d "
            "declares it; `create-branch --epic %d --write` is the protected path that "
            "puts such a branch back (rule 3)"
            % (number, head, epic["number"], epic["number"])))
        return findings, "R6", None, epic
    if base != DEVELOP and not base.startswith(EPIC_PREFIX):
        findings.append(Finding(
            "epic-pr-base",
            "PR #%d has the epic branch `%s` as its head but `%s` as its base; an epic "
            "branch integrates into `%s` and nothing else (R6)"
            % (number, head, base, DEVELOP)))
        return findings, "R6", None, epic
    if base == DEVELOP:
        if epic and epic.get("parent"):
            findings.append(Finding(
                "nested-epic-base",
                "PR #%d integrates nested epic `%s` into `%s`, but the epic is a sub-issue "
                "of #%d: it merges into `%s` first, and only the outermost epic's branch "
                "may base on `%s` (R9)" % (number, head, DEVELOP, epic["parent"]["number"],
                                           epic_branch(epic["parent"]["slug"]), DEVELOP)))
            return findings, "R9", epic_branch(epic["parent"]["slug"]), epic
        return findings, "R6", DEVELOP, epic
    if epic and epic.get("parent") and base == epic_branch(epic["parent"]["slug"]):
        return findings, "R9", base, epic
    findings.append(Finding(
        "epic-pr-base",
        "PR #%d merges the epic branch `%s` into `%s`; epic branches merge only into `%s` "
        "or, when nested, into their parent epic's branch (R6, R9)"
        % (number, head, base, DEVELOP)))
    return findings, "R6", None, epic


def _epic_for_branch(runner, repo, branch, listings=None):
    """The open epic that declares `branch`, or None; shared slugs are an error."""
    slug = branch_slug(branch)
    if not slug:
        return None
    claimants = [e for e in open_epics(runner, repo, listings) if e["slug"] == slug]
    if not claimants:
        return None
    if len(claimants) > 1:
        raise EpicBranchError("`%s` is declared by %d open epics (%s); one slug is one "
                              "branch (rule 2)" % (branch, len(claimants),
                                                   ", ".join("#%d" % c["number"]
                                                             for c in claimants)))
    epic = claimants[0]
    parent = native_parent(runner, repo, epic["number"])
    if parent is None:
        return {"number": epic["number"], "slug": slug, "parent": None}
    gp = _epic_of(runner, repo, parent, {})
    return {"number": epic["number"], "slug": slug,
            "parent": {"number": parent, "slug": gp["slug"]} if gp["slug"] else None}


@_verb("check-branch")
def check_branch(runner, epic_number, repo=None, mode=None, today=None, heads=None,
                 listings=None):
    """Existence, uniqueness and staleness of one epic's integration branch."""
    mode = mode or mode_for(today_or(today))
    if repo is None:
        try:
            repo = resolve_repo(runner)
        except EpicBranchError as e:
            return _branch_error(epic_number, None, mode, str(e))
    try:
        if heads is None:
            heads = origin_heads(runner)
        listings = listings if listings is not None else {}
        epic = _epic_of(runner, repo, epic_number, {})
        findings = []
        if epic["slugFinding"]:
            findings.append(epic["slugFinding"])
            branch = sha = None
        elif not epic["slug"]:
            branch = sha = None
            if epic["state"] == "OPEN":
                findings.append(Finding(
                    "epic-slug-missing",
                    "epic #%d declares no `slug:` on its first body line, so it has no "
                    "integration branch identity; its children run on develop until it "
                    "does (R3)" % epic_number))
        else:
            branch = epic_branch(epic["slug"])
            sha = heads.get(branch)
            conflict = _slug_conflict(runner, repo, epic_number, epic["slug"], heads,
                                      listings)
            if conflict:
                findings.append(conflict)
            if sha is None and epic["state"] == "OPEN":
                findings.append(Finding(
                    "epic-branch-missing",
                    "epic branch `%s` of open epic #%d does not exist on origin; "
                    "create-branch is the protected path (rule 3)" % (branch, epic_number)))
            if sha is not None and epic["state"] != "OPEN":
                findings.append(Finding(
                    "epic-branch-stale",
                    "epic branch `%s` still stands although epic #%d is %s; rule 11 retires "
                    "the branch in the same act as the integration merge, so a person "
                    "decides whether it is kept" % (branch, epic_number, epic["state"])))
        return {"schema": SCHEMA, "status": "ok", "error": None, "repo": repo, "mode": mode,
                "strict_from": strict_from(), "epic": epic_number, "slug": epic["slug"],
                "branch": branch, "branchSha": sha,
                "findings": [f.as_dict() for f in findings],
                "exit_code": 1 if (mode == "strict"
                                   and any(f.severity == "error" for f in findings)) else 0}
    except EpicBranchError as e:
        return _branch_error(epic_number, repo, mode, str(e), e.code)


def _branch_error(epic_number, repo, mode, message, code=None):
    """The gated fail-closed answer of `check-branch`, with the same code rule as
    `_pr_error`: the refusing rule when it is known, `metadata-unreadable` otherwise."""
    finding = (Finding(code, message) if code
               else Finding("metadata-unreadable", message))
    return {"schema": SCHEMA, "status": "error", "error": message, "repo": repo,
            "mode": mode, "strict_from": strict_from(), "epic": epic_number,
            "findings": [finding.as_dict()],
            "exit_code": 1 if mode == "strict" else 0}


@_verb("audit")
def audit(runner, repo=None, mode=None, today=None, scope="epic"):
    """Every open epic, and with scope all-approved every open PR, in one report.

    #1594 needs exactly this listing to decide what has to be migrated before the flip:
    a per-PR check cannot answer "how much of the repository already violates R4".
    """
    mode = mode or mode_for(today_or(today))
    if repo is None:
        repo = resolve_repo(runner)
    heads = origin_heads(runner)
    report = {"schema": SCHEMA, "status": "ok", "error": None, "repo": repo, "mode": mode,
              "strict_from": strict_from(), "scope": scope, "epics": [], "pulls": [],
              "findings": []}
    listings = {}
    for e in open_epics(runner, repo, listings):
        one = check_branch(runner, e["number"], repo=repo, mode=mode, heads=heads,
                           listings=listings)
        report["epics"].append(one)
        report["findings"] += one["findings"]
    if scope != "all-approved":
        return report
    for pr in gh_rest_items(runner, "repos/%s/pulls?state=open&per_page=%d"
                            % (repo, DEFAULT_PAGE)):
        if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
            continue
        head = (pr.get("head") or {}).get("ref") or ""
        if not (CHILD_ISSUE_RE.search(head) or head.startswith(EPIC_PREFIX)):
            continue
        one = check_pr(runner, pr["number"], repo=repo, mode=mode, heads=heads)
        report["pulls"].append(one)
        report["findings"] += one["findings"]
    return report


# ----------------------------------------------------------------------------- writes


def _require_human(runner):
    """A write subcommand is a person's act, so check who this gh session is.

    Not an approval and no substitute for one: it refuses only the case the repository
    has already ruled out, the agent identity performing a branch creation or a retarget
    itself. GitHub's `author_association`, the required reviewers and branch protection
    remain the real gate.
    """
    try:
        login = (json.loads(runner(["gh", "api", "user"])) or {}).get("login") or ""
    except (CommandError, ValueError):
        raise EpicBranchError("the identity of this gh session cannot be read "
                              "(gh api user failed), so no write is attempted")
    if not login:
        raise EpicBranchError("gh reports no authenticated user, so no write is attempted")
    if login.lower() in DENIED_LOGINS:
        raise EpicBranchError("`%s` is the agent identity: creating an integration branch "
                              "and retargeting a pull request are a person's acts "
                              "(rule 15)" % login)
    return login


@_verb("create-branch")
def create_branch(runner, epic_number, write=False, repo=None, heads=None):
    """Rule 3: `epic/<slug>` from the tip of origin/develop - or reuse what already stands.

    Idempotent and deliberately narrow. An existing branch is never pushed to, moved or
    deleted, only reported and reused; the single push this performs creates a branch
    that does not exist yet at a SHA just read from `origin/develop`. That is why it does
    not collide with "never push to a permanent branch": nothing permanent is rewritten,
    the content is develop's own, and `--write` plus a human gh identity are required.
    """
    if repo is None:
        repo = resolve_repo(runner)
    if heads is None:
        heads = origin_heads(runner)
    try:
        epic = _epic_of(runner, repo, epic_number, {})
        if epic["slugFinding"]:
            finding = epic["slugFinding"]
            return _result(status="error",
                           error="no branch is named after a refused slug: %s"
                                 % finding.message,
                           findings=[finding.as_dict()])
        if not epic["slug"]:
            return _err("epic #%d declares no `slug:` on its first body line; nothing is "
                        "created from an undeclared identity (R3)" % epic_number,
                        "epic-slug-missing")
        if epic["state"] != "OPEN":
            return _err("epic #%d is %s; a branch is never created for an epic that is not "
                        "open (R10, R11)" % (epic_number, epic["state"]), "epic-not-open")
        conflict = _slug_conflict(runner, repo, epic_number, epic["slug"], heads, {})
        if conflict:
            return _result(status="error", error=conflict.message,
                           findings=[conflict.as_dict()])
        slug, branch = epic["slug"], epic_branch(epic["slug"])
        if branch in heads:
            return _result(row="R2", epic=epic_number, slug=slug, target=branch,
                           branch=branch, branchSha=heads[branch], created=False,
                           write=bool(write),
                           reason="epic branch `%s` already stands at %s and is reused "
                                  "(rule 3, idempotent - nothing was pushed)"
                                  % (branch, heads[branch][:10]))
        fetch_ref(runner, DEVELOP)
        try:
            develop = runner(["git", "rev-parse", "origin/" + DEVELOP]).strip()
        except CommandError as e:
            raise EpicBranchError("origin/%s cannot be read: %s" % (DEVELOP, e))
        if not SHA_RE.match(develop):
            raise EpicBranchError("origin/%s did not resolve to a commit SHA" % DEVELOP)
        out = _result(row="R3", epic=epic_number, slug=slug, target=branch, branch=branch,
                      branchSha=develop, created=bool(write), write=bool(write),
                      reason="epic branch `%s` from origin/%s at %s%s"
                             % (branch, DEVELOP, develop[:10],
                                "" if write else " (dry run: nothing pushed)"))
        if not write:
            return out
        _require_human(runner)
        try:
            runner(["git", "push", "origin", "%s:refs/heads/%s" % (develop, branch)])
        except CommandError as e:
            raise EpicBranchError("creating `%s` failed; nothing else was touched and no "
                                  "partial branch is left behind: %s" % (branch, e))
        return out
    except EpicBranchError as e:
        return _err(str(e))


@_verb("retarget")
def retarget(runner, pr_number, base, write=False, repo=None):
    """Move an OPEN pull request's base onto its resolved target.

    Refuses unless the resolved target is exactly `base`, so this is not a door through
    which a caller can point a PR anywhere it likes. The single write is the GitHub base
    patch: no branch content, no approval, no label, no merge.
    """
    if repo is None:
        repo = resolve_repo(runner)
    try:
        heads = origin_heads(runner)
        pr = pr_facts(runner, repo, pr_number)
        if pr["state"] != "open":
            return _err("PR #%d is %s; only an open pull request has a base to move"
                        % (pr_number, pr["state"]), "pr-not-open")
        m = CHILD_ISSUE_RE.search(pr["head"])
        if not m:
            return _err("the head branch `%s` of PR #%d names no issue, so its target "
                        "cannot be resolved and nothing is retargeted"
                        % (pr["head"], pr_number), "head-branch-no-issue")
        res = resolve_issue(runner, int(m.group(1)), repo=repo, heads=heads, _cache={})
        if res["status"] == "error":
            return _err("PR #%d cannot be retargeted because #%d does not resolve: %s"
                        % (pr_number, int(m.group(1)), res["error"]))
        if res["target"] != base:
            return _err("PR #%d resolves to target `%s`, not `%s`: refusing to move a base "
                        "the contract does not name" % (pr_number, res["target"], base),
                        "wrong-target")
        out = _result(row="R4", pr=pr_number, target=base, base=pr["base"],
                      epic=res.get("epic"), retargeted=bool(write), write=bool(write),
                      reason="PR #%d: base `%s` -> `%s`%s"
                             % (pr_number, pr["base"], base,
                                "" if write else " (dry run: nothing written)"))
        if not write:
            return out
        _require_human(runner)
        owner, name = repo.split("/")
        try:
            runner(["gh", "api", "-X", "PATCH",
                    "repos/%s/%s/pulls/%d" % (owner, name, pr_number),
                    "-f", "base=" + base])
        except CommandError as e:
            raise EpicBranchError("retargeting PR #%d failed: %s" % (pr_number, e))
        return out
    except EpicBranchError as e:
        return _err(str(e))


# ------------------------------------------------------------------------------- cli


def strict_from():
    return os.environ.get(STRICT_FROM_ENV) or STRICT_FROM


def mode_for(today, mode="auto"):
    if mode != "auto":
        return mode
    # #1592 supersedes the dated rollout; explicit strict is legacy diagnostics only.
    return "advisory"


def today_or(value):
    return value or date.today().isoformat()


def _pr_head(res):
    return "PR #%s  %s -> %s  target %s  row %s  mode %s" % (
        res["pr"], res.get("head"), res.get("base"), res.get("target") or "-",
        res.get("row") or "-", res.get("mode"))


def _audit_head(res):
    return "audit of %s  scope %s  mode %s  epics %d  pulls %d  findings %d" % (
        res.get("repo"), res.get("scope"), res.get("mode"), len(res.get("epics") or []),
        len(res.get("pulls") or []), len(res.get("findings") or []))


def _epic_branch_head(res):
    # `check-branch` and both write verbs report an epic and its branch; the two write
    # verbs are not gates and carry no mode.
    return "epic #%s  branch %s  sha %s%s" % (
        res.get("epic"), res.get("branch") or "-",
        (res.get("branchSha") or "-")[:10],
        "" if res.get("mode") is None else "  mode %s" % res["mode"])


def _resolve_head(res):
    return "#%s  target %s  row %s  mode %s" % (
        res.get("issue"), res.get("target") or "-", res.get("row") or "-",
        res.get("mode") or "-")


def _retarget_head(res):
    return "PR #%s  base %s -> %s  row %s  mode %s" % (
        res.get("pr"), res.get("base") or "-", res.get("target") or "-",
        res.get("row") or "-", res.get("mode") or "-")


def _unknown_head(res):
    """An envelope whose verb is not one of the six: named as unknown, not guessed at.

    Guessing here is what printed `epic #None branch develop` for an independent issue -
    a header about an epic that does not exist. Saying the shape is unrecognised cannot
    mislead the person reading it before a gated write.
    """
    return "unrecognised result%s  status %s  findings %d" % (
        " (command %s)" % res["command"] if res.get("command") else "",
        res.get("status"), len(res.get("findings") or []))


_HEADS = {"resolve": _resolve_head, "check-pr": _pr_head, "check-branch": _epic_branch_head,
          "create-branch": _epic_branch_head, "retarget": _retarget_head,
          "audit": _audit_head}


def render_human(res):
    """The verdict line, the reason and the findings - one shape per subcommand.

    The shape comes from the `command` every result carries, never from which optional
    keys happen to be filled: a `resolve` of an issue with no parent carries
    ``branch: develop`` and no epic, and a `retarget` carries an `epic` and no findings,
    so a renderer that sniffed the keys described the first as an epic branch of epic
    #None and dropped the base transition the second exists to report.
    """
    if res["status"] == "error":
        return "ERROR - fail closed, decide nothing\n%s" % res.get("error")
    head = _HEADS.get(res.get("command"), _unknown_head)(res)
    lines = [head]
    if res.get("reason"):
        lines.append("  %s" % res["reason"])
    for f in res.get("findings") or []:
        lines.append("  [%s] %s: %s" % (f["severity"], f["code"], f["message"]))
    return "\n".join(lines)


def exit_code(res):
    """0 clean or advisory, 1 a violation in strict mode, 2 an unanswered question.

    A gated command (`check-pr`, `check-branch`) carries its own `exit_code`, computed
    where the mode is known; everything else answers 2 on `status: "error"` whatever the
    mode says. That distinction is the whole rollout story: the gate may stay advisory so a
    `gh` hiccup does not turn a pull request that predates the rule red, but a host-side
    `resolve` that could not read the hierarchy must not answer 0, because its caller is
    about to branch from an answer it never got. Neither case ever reads as an OK - the
    result still says `status: "error"` with its finding either way.
    """
    if "exit_code" in res:
        return res["exit_code"]
    if res["status"] == "error":
        return 2
    return 1 if (res.get("mode") == "strict"
                 and any(f["severity"] == "error" for f in res.get("findings") or [])) else 0


SELF_CASES = [
    ("lowercase kebab slug", "slug: epic-integration\nbody", "epic-integration", None),
    ("html comment slug", "<!-- slug: auto-docs -->\nbody", "auto-docs", None),
    ("no slug line", "## Goal\nbody", None, None),
    ("empty body", "", None, None),
    ("uppercase slug", "slug: Epic_Integration", None, "epic-slug-invalid"),
    ("underscore slug", "slug: epic_integration", None, "epic-slug-invalid"),
    ("too long slug", "slug: " + "a" * 21, None, "epic-slug-too-long"),
    ("one character slug", "slug: a", None, "epic-slug-invalid"),
    ("leading dash slug", "slug: -epic", None, "epic-slug-invalid"),
    ("trailing dash slug", "slug: epic-", None, "epic-slug-invalid"),
    ("slug after heading", "## Goal\nslug: epic-integration", "epic-integration", None),
    ("slug after prose", "some prose\nslug: epic-integration", None, None),
]


def self_test():
    """The pure rules, checked without gh or git - same shape as pr_classify's `check`."""
    ok = True
    for name, body, want_slug, want_code in SELF_CASES:
        slug, finding = parse_slug(body)
        got = finding.code if finding else None
        good = slug == want_slug and got == want_code
        print("%-32s %s" % (name, "ok" if good else "FAIL slug=%r code=%r" % (slug, got)))
        ok = ok and good
    for branch, want in (("epic/epic-integration", "epic-integration"),
                         ("develop", None), (EPIC_PREFIX, ""), ("ao/x/issue-1", None)):
        got = branch_slug(branch)
        print("%-32s %s" % ("branch_slug(%s)" % branch,
                            "ok" if got == want else "FAIL %r" % got))
        ok = ok and got == want
    for mode, today, want in (("auto", "2026-12-20", "advisory"),
                              ("auto", STRICT_FROM, "advisory"),
                              ("auto", "2027-01-01", "advisory"),
                              ("strict", "2020-01-01", "strict")):
        got = mode_for(today, mode)
        print("%-32s %s" % ("mode_for(%s, %s)" % (mode, today),
                            "ok" if got == want else "FAIL %s" % got))
        ok = ok and got == want
    return 0 if ok else 1


def emitted_codes():
    """Every finding code this file can report, read from this file's own syntax.

    Derived by parsing rather than searching, so prose in a docstring cannot add a code
    to the public vocabulary - the same trick `scripts/pr_classify` uses to keep its
    documented list and its real list from drifting apart.
    """
    try:
        tree = ast.parse(Path(__file__).read_text())
    except (OSError, SyntaxError):
        return set()
    codes = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name == "Finding" and node.args:
            arg = node.args[0]
        elif name == "_err" and len(node.args) > 1:
            arg = node.args[1]
        else:
            continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            codes.add(arg.value)
    return codes


EMITTED_CODES = emitted_codes()


def main(argv=None, runner=None):
    if runner is None:
        runner = subprocess_runner
    ap = argparse.ArgumentParser(
        prog="scripts/epic_branch.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Resolve an issue's epic integration branch and enforce pull request "
                    "targets (#1591; contract: docs/source/development/"
                    "epic-integration-contract.rst).")
    sub = ap.add_subparsers(dest="command")

    p = sub.add_parser("resolve", help="which branch does this issue's work belong on")
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--repo", default=None)
    p.add_argument("--no-ancestry", action="store_true",
                   help="do not ask git whether a closed epic's children reached develop")
    p.add_argument("--mode", choices=("auto", "strict", "advisory"), default="auto",
                   help="recorded in the result; while it is advisory, rule 16 keeps an "
                        "in-flight epic's children on develop")
    p.add_argument("--today", default=None, help="fix the clock (YYYY-MM-DD)")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check-pr", help="is this pull request targeting what it should")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--repo", default=None)
    p.add_argument("--mode", choices=("auto", "strict", "advisory"), default="auto")
    p.add_argument("--today", default=None, help="fix the clock (YYYY-MM-DD)")
    p.add_argument("--no-ancestry", action="store_true",
                   help="skip R12, the one rule that asks git about the head commit "
                        "(for a shallow checkout); the result records that it was skipped")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("check-branch", help="existence, uniqueness and staleness of one "
                                            "epic branch")
    p.add_argument("--epic", type=int, required=True)
    p.add_argument("--repo", default=None)
    p.add_argument("--mode", choices=("auto", "strict", "advisory"), default="auto")
    p.add_argument("--today", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("audit", help="every open epic, and with --scope all-approved "
                                     "every open PR")
    p.add_argument("--scope", choices=("epic", "all-approved"), default="epic")
    p.add_argument("--repo", default=None)
    p.add_argument("--mode", choices=("auto", "strict", "advisory"), default="auto")
    p.add_argument("--today", default=None)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("create-branch", help="create epic/<slug> from origin/develop "
                                             "(rule 3)")
    p.add_argument("--epic", type=int, required=True)
    p.add_argument("--repo", default=None)
    p.add_argument("--write", action="store_true", help="actually push the new branch")
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("retarget", help="move an open PR's base onto its resolved target")
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--base", required=True, help="must be the resolved target")
    p.add_argument("--repo", default=None)
    p.add_argument("--write", action="store_true", help="actually patch the pull request")
    p.add_argument("--json", action="store_true")

    sub.add_parser("codes", help="every finding code this tool can report")
    sub.add_parser("check", help="the tool's own self-test")

    args = ap.parse_args(argv)
    if args.command == "check":
        return self_test()
    if args.command == "codes":
        print("\n".join(sorted(EMITTED_CODES)))
        return 0

    repo = getattr(args, "repo", None)
    mode = getattr(args, "mode", None)
    today = getattr(args, "today", None)
    try:
        if args.command == "resolve":
            res = resolve_issue(runner, args.issue, repo=repo,
                                ancestry=not args.no_ancestry, mode=mode, today=today)
        elif args.command == "check-pr":
            res = check_pr(runner, args.pr, repo=repo, mode=mode, today=today,
                           ancestry=not args.no_ancestry)
        elif args.command == "check-branch":
            res = check_branch(runner, args.epic, repo=repo, mode=mode, today=today)
        elif args.command == "audit":
            res = audit(runner, repo=repo, mode=mode, today=today, scope=args.scope)
        elif args.command == "create-branch":
            res = create_branch(runner, args.epic, write=args.write, repo=repo)
        elif args.command == "retarget":
            res = retarget(runner, args.pr, args.base, write=args.write, repo=repo)
        else:
            ap.print_help()
            return 2
    except EpicBranchError as e:
        res = _err(str(e))
    print(json.dumps(res, indent=2, sort_keys=True) if getattr(args, "json", False)
          else render_human(res))
    return exit_code(res)


if __name__ == "__main__":
    sys.exit(main())
