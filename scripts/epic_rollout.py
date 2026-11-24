#!/usr/bin/env python3
"""epic_rollout: dry-run migration plan and rollout readiness of the epic branch contract.

Maintenance tool carried by this repository; run it as `python3 scripts/epic_rollout.py`
from the repository root. It answers two questions #1594 (epic #1588) has to answer before
the epic branch contract of #1590 may be turned on: *what would change for the work that
already exists* (the migration plan), and *is the rollout itself complete* (the readiness
report). It is STATELESS and READ-ONLY toward GitHub - it creates no branch, retargets no
PR, writes no comment and no label; its only local side effect is the `git fetch` it never
even does, because `git ls-remote` answers the branch question without writing a ref. It
RUNS ONCE: no daemon, no polling loop, no watcher.

Why a plan and not a check
--------------------------
`docs/source/development/epic-integration-contract.rst` (#1590) is the contract: the
decision table R1-R13 and the sixteen MUST rules. #1591 enforces a row at PR time, #1592
schedules against the row, #1593 gates the integration. What none of them does is look at
the repository *as a whole* and say what turning the rule on would do to the 288 branches,
the open epics and the PRs already in flight - and the contract is explicit that an agent
may not retarget, create or delete anything (rule 15), so that reading has to end in a
plan a person executes rather than in an action. That is this tool's whole job: derive the
rows from the same native facts #1591 will read, name the actor for every owed action, and
be honest when a fact cannot be read.

Advisory first, for the measured reason #1580 gives
---------------------------------------------------
Like the title enforcement of #1580 (`scripts/pr_classify`), the rollout has two halves,
dated in `scripts/epic_rollout.json`: until `advisory_from` nothing here is news to
anybody, from `strict_from` the *readiness* findings fail. The dates are in the policy
file and overridable through `MRMAP_EPIC_ROLLOUT_STRICT_FROM`, because a rollout date is a
deployment's call and a rule's author should not own it.

The split of what may fail is deliberate. A wrong PR base is a *plan item* with a person as
its actor - rule 15 and rows R5/R12 forbid an agent from fixing it, so failing this tool on
it would only teach an agent to go fix it. What fails the tool instead are the defects
nobody else owns: the CI coverage of `The CI contract`_ missing from one of the named
workflows (a child PR that gets no checks is worse than no epic branch), an epic exempted
by an expired legacy entry, a bootstrap epic whose branch stands with no integration PR, a
slug reused across open epics. Those are rollout defects, and they are #1594's.

FAIL CLOSED: nothing is reported on any doubt. An unauthenticated gh, a failing or
permission-denied GitHub call, a null connection or a page that says it has more rows all
produce status "error" with a non-zero exit and no plan - never a partial plan, which is
the shape that would let a person believe an inventory was complete when it was truncated.

Usage:
  python3 scripts/epic_rollout.py [--json] [--dry-run] [--policy PATH] [--today YYYY-MM-DD]
                                  [--epic N] [--mode auto|advisory|strict]

  --json        print the machine-readable plan instead of the table
  --dry-run     the only mode this tool has; accepted so a caller can state its intent
  --policy PATH read the rollout policy from PATH (default: scripts/epic_rollout.json)
  --today D     pretend it is D (date), for the rollout half and for expiry checks
  --epic N      plan one epic instead of every open one
  --mode M      auto (default) picks by the policy dates; advisory/strict force it

Exit codes: 0 the plan is complete and (in strict mode) the rollout has no finding;
1 strict mode with findings; 2 the tool could not answer (fail closed).

The offline suite is scripts/test_epic_rollout.py (fixture-driven, injected command runner,
no gh and no network), as every suite under scripts/.
"""

import argparse
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import date
from subprocess import TimeoutExpired

SCHEMA = "epic-rollout/v1"
POLICY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "epic_rollout.json")
CMD_TIMEOUT = 120
BASE_BRANCH = "develop"
MASTER_BRANCH = "master"
EPIC_LABEL = "Epic"
BRANCH_ISSUE_RE = re.compile(r"(?:^|/)(?:issue[-_]?|#)(\d+)")
SLUG_RE = re.compile(r"^\s*slug:\s*(.+?)\s*$", re.M)
ACTIVE_CLAIM_STATES = ("wip", "waiting")
# Every owed action names who performs it. An action without an actor is a bug in this
# tool, because an unowned action is the one an agent will eventually "helpfully" take.
ACTOR_HUMAN = "person"
ACTOR_AGENT = "agent"
ACTORS = (ACTOR_HUMAN, ACTOR_AGENT)


class CommandError(Exception):
    """A gh or git call failed; the tool fails closed on it."""

    exit_code = None


class RolloutError(Exception):
    """Why the whole plan failed closed; no plan may be published on it."""


class PolicyError(RolloutError):
    """The policy file is missing, unreadable or contradicts the contract it cites."""


def subprocess_runner(argv):
    """Run argv, return stdout, raise CommandError on a non-zero exit or timeout."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=CMD_TIMEOUT)
    except (OSError, TimeoutExpired) as e:
        raise CommandError("%s could not be run: %s" % (" ".join(argv[:2]), e))
    if proc.returncode != 0:
        err = CommandError("%s exited %d: %s" % (" ".join(argv[:2]), proc.returncode,
                                                 (proc.stderr or proc.stdout or "").strip()))
        err.exit_code = proc.returncode
        raise err
    return proc.stdout or ""


# --------------------------------------------------------------------------- the policy


def _date(value, what):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise PolicyError("%s is %r, which is not an ISO date" % (what, value))


def load_policy(path):
    """Read and validate the rollout policy; a policy this tool cannot trust is fatal.

    The validation is not ceremony: this file is what makes the rollout time-limited, so a
    typo in a date would silently make it permanent, and a legacy exception without an
    expiry is the "explicit/time-limited" requirement of #1594 failing quietly. The contract
    page it cites must also exist - a policy that points at a deleted contract leaves the
    reader with a rule and no source.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            policy = json.load(fh)
    except OSError as e:
        raise PolicyError("the rollout policy %s cannot be read: %s" % (path, e))
    except ValueError as e:
        raise PolicyError("the rollout policy %s is not JSON: %s" % (path, e))
    if not isinstance(policy, dict):
        raise PolicyError("the rollout policy %s holds no object" % path)
    if policy.get("schema_version") != 1:
        raise PolicyError("the rollout policy %s declares schema_version %r, this tool reads 1"
                          % (path, policy.get("schema_version")))
    contract = policy.get("contract")
    if not isinstance(contract, str) or not contract:
        raise PolicyError("the rollout policy names no contract page")
    if not os.path.exists(contract):
        raise PolicyError("the rollout policy cites %s, which is not in the repository - the "
                          "contract is the source of every row this tool derives" % contract)
    prefix = policy.get("branch_prefix")
    if prefix != "epic/":
        raise PolicyError("the rollout policy declares branch_prefix %r; the contract fixes "
                          "the namespace as epic/<slug>" % prefix)
    try:
        re.compile(policy.get("slug_pattern") or "(")
    except re.error as e:
        raise PolicyError("the rollout policy carries an unparsable slug_pattern: %s" % e)
    rollout = policy.get("rollout")
    if not isinstance(rollout, dict):
        raise PolicyError("the rollout policy holds no rollout block")
    advisory = _date(rollout.get("advisory_from"), "rollout.advisory_from")
    strict = _date(rollout.get("strict_from"), "rollout.strict_from")
    if advisory > strict:
        raise PolicyError("the rollout would go strict (%s) before it starts advising (%s)"
                          % (strict, advisory))
    coverage = rollout.get("ci_coverage")
    if not isinstance(coverage, list) or not coverage or not all(isinstance(w, str) for w in coverage):
        raise PolicyError("the rollout policy names no ci_coverage workflows; without the check "
                          "list a child PR can be merged into an epic branch unchecked")
    for workflow in coverage:
        if not os.path.exists(workflow):
            raise PolicyError("the rollout policy names %s, which is not in the repository"
                              % workflow)
    bootstrap = policy.get("bootstrap") or {}
    if not isinstance(bootstrap.get("epics"), list):
        raise PolicyError("the rollout policy holds no bootstrap.epics list")
    for entry in policy.get("legacy_exceptions") or []:
        if not isinstance(entry, dict):
            raise PolicyError("a legacy_exceptions entry is not an object")
        if not isinstance(entry.get("epic"), int):
            raise PolicyError("a legacy_exceptions entry names no epic number")
        if not (entry.get("reason") or "").strip():
            raise PolicyError("the legacy exception of epic #%s names no reason - an exception "
                              "a person cannot read is not an explicit one" % entry.get("epic"))
        if not (entry.get("recorded_in") or "").strip():
            raise PolicyError("the legacy exception of epic #%s names no recorded_in issue"
                              % entry.get("epic"))
        _date(entry.get("expires"), "legacy exception of epic #%s expires" % entry.get("epic"))
    return policy


def mode_for(today, policy, mode="auto"):
    """Which half of the rollout a run is in: 'advisory' or 'strict'."""
    if mode in ("advisory", "strict"):
        return mode
    strict_from = os.environ.get(policy["rollout"].get("strict_from_env") or "",
                                 policy["rollout"]["strict_from"])
    return "strict" if str(today) >= str(strict_from) else "advisory"


# --------------------------------------------------------------------------- GitHub reads


def gh_graphql(runner, query):
    """Run one GraphQL query through gh; errors and missing data fail closed."""
    try:
        out = runner(["gh", "api", "graphql", "-f", "query=" + query])
    except CommandError as e:
        raise RolloutError("the GitHub GraphQL call failed (a missing permission reads the "
                           "same way): %s" % e)
    try:
        doc = json.loads(out or "")
    except ValueError:
        raise RolloutError("GitHub GraphQL returned something that is not JSON")
    if not isinstance(doc, dict):
        raise RolloutError("GitHub GraphQL returned no response object")
    if doc.get("errors"):
        raise RolloutError("GitHub GraphQL error: "
                           + "; ".join(str(e.get("message", e)) for e in doc["errors"]))
    if not isinstance(doc.get("data"), dict):
        raise RolloutError("GitHub GraphQL returned no data")
    return doc["data"]


def connection(data, *path, what):
    """The nodes of a GraphQL connection, refusing a partial one.

    A truncated inventory is the dangerous failure mode of a migration plan: a person who
    reads "no PR needs retargeting" from a plan that silently skipped page two would merge
    the epic believing the migration was done.
    """
    cur = data
    for key in path:
        cur = (cur or {}).get(key)
    if not isinstance(cur, dict) or not isinstance(cur.get("nodes"), list) \
            or any(n is None for n in cur["nodes"]):
        raise RolloutError("GraphQL %s connection is null or contains a null node" % what)
    nodes = cur["nodes"]
    total = cur.get("totalCount")
    if not isinstance(total, int) or len(nodes) > total:
        raise RolloutError("GraphQL %s connection reports an inconsistent totalCount" % what)
    page = cur.get("pageInfo") or {}
    if page.get("hasNextPage") or len(nodes) < total:
        raise RolloutError("GraphQL %s connection is not fully readable (%d of %s)"
                           % (what, len(nodes), total))
    return nodes


def search_nodes(data, what):
    """The nodes of a GraphQL `search` connection, refusing a partial one.

    `search` carries `issueCount` where a normal connection carries `totalCount`, so it
    needs its own reader rather than a special case inside `connection`.
    """
    cur = data.get("search")
    if not isinstance(cur, dict) or not isinstance(cur.get("nodes"), list) \
            or any(n is None for n in cur["nodes"]):
        raise RolloutError("GraphQL %s connection is null or contains a null node" % what)
    nodes = cur["nodes"]
    total = cur.get("issueCount")
    if not isinstance(total, int) or len(nodes) > total:
        raise RolloutError("GraphQL %s connection reports an inconsistent issueCount" % what)
    page = cur.get("pageInfo") or {}
    if page.get("hasNextPage") or len(nodes) < total:
        raise RolloutError("GraphQL %s connection is not fully readable (%d of %s)"
                           % (what, len(nodes), total))
    return nodes


def resolve_repo(runner):
    try:
        out = runner(["gh", "repo", "view", "--json", "nameWithOwner"])
    except CommandError as e:
        raise RolloutError("the repository of this checkout cannot be read: %s" % e)
    try:
        return json.loads(out)["nameWithOwner"]
    except (ValueError, KeyError, TypeError):
        raise RolloutError("the repository of this checkout cannot be read")


def origin_branches(runner):
    """Branch names on origin; ls-remote reads them without writing any ref."""
    try:
        out = runner(["git", "ls-remote", "--heads", "origin"])
    except CommandError as e:
        raise RolloutError("git ls-remote origin failed, so the branch inventory is unknown: %s"
                           % e)
    names = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            names.add(parts[1][len("refs/heads/"):])
    return names


def slug_declaration(body):
    """(slug, misplaced) - the epic's declared slug as rule 1 fixes it.

    Rule 1 puts the declaration on the epic's *first body line*, because that is the one
    place a tool and an agent after a context loss both look. A `slug:` line deeper in the
    body is therefore not the identity; it is a declaration in the wrong place, and the plan
    says so instead of either ignoring it or honouring it.
    """
    lines = [line for line in (body or "").splitlines() if line.strip()]
    m = SLUG_RE.match(lines[0]) if lines else None
    if m:
        slug = m.group(1).strip().strip("`*")
        return (slug or None), False
    for line in lines[1:]:
        if SLUG_RE.match(line):
            return None, True
    return None, False


def open_epics(runner, repo, only=None):
    """Open issues carrying the `Epic` label, with their native sub-issues.

    The label is the *triage view* the contract's open questions accept for discovery, and
    the native `subIssues` connection is the fact: an issue labelled Epic with no native
    children has nothing to migrate, and a child is only a child through that connection.
    """
    q = ('{search(query:"repo:%s is:issue is:open label:\\"%s\\"", type:ISSUE, first:100)'
         '{issueCount pageInfo{hasNextPage} nodes{__typename ... on Issue{number title state '
         'body labels(first:100){totalCount pageInfo{hasNextPage} nodes{name}} '
         'subIssues(first:100){totalCount pageInfo{hasNextPage} nodes{number title state '
         'stateReason}}}}}}' % (repo, EPIC_LABEL))
    nodes = search_nodes(gh_graphql(runner, q), "open %s issues" % EPIC_LABEL)
    epics = []
    for n in nodes:
        if not isinstance(n.get("number"), int):
            raise RolloutError("an open epic has no issue number")
        number = n["number"]
        if only is not None and number != only:
            continue
        if n.get("state") != "OPEN":
            raise RolloutError("epic #%s came back %s from an is:open search" % (number,
                                                                                  n.get("state")))
        children = []
        for s in connection(n, "subIssues", what="subIssues of epic #%s" % number):
            if not isinstance(s.get("number"), int):
                raise RolloutError("epic #%s has a sub-issue without a number" % number)
            children.append({"number": s["number"], "title": s.get("title") or "",
                             "state": s.get("state"), "stateReason": s.get("stateReason")})
        labels = [lab.get("name")
                  for lab in connection(n, "labels", what="labels of #%s" % number)
                  if isinstance(lab.get("name"), str)]
        slug, misplaced = slug_declaration(n.get("body"))
        epics.append({"number": number, "title": n.get("title") or "",
                      "slug": slug, "slug_misplaced": misplaced, "labels": labels,
                      "children": children})
    return epics


def open_pulls(runner, repo):
    """Every open pull request: base, head, body, and the issues it closes.

    One listing decides the base-side rows for all epics at once (R5, R6, R12 and the
    integration PR of R7); reading it per epic would multiply the chance of a partial read.
    """
    q = ('{search(query:"repo:%s is:pr is:open", type:ISSUE, first:100)'
         '{issueCount pageInfo{hasNextPage} nodes{__typename ... on PullRequest{number title '
         'baseRefName headRefName body author{login} '
         'closingIssuesReferences(first:100){totalCount pageInfo{hasNextPage} nodes{number}}}}}}'
         % repo)
    pulls = []
    for p in search_nodes(gh_graphql(runner, q), "open pull requests"):
        number = p.get("number")
        if not isinstance(number, int):
            raise RolloutError("an open pull request has no number")
        closes = []
        for i in connection(p, "closingIssuesReferences", what="closing issues of PR #%s" % number):
            if isinstance(i.get("number"), int):
                closes.append(i["number"])
        body = p.get("body") or ""
        head = p.get("headRefName") or ""
        m = BRANCH_ISSUE_RE.search(head)
        pulls.append({"number": number, "title": p.get("title") or "",
                      "base": p.get("baseRefName") or "", "head": head,
                      "author": (p.get("author") or {}).get("login") or "",
                      "closes": closes, "head_issue": int(m.group(1)) if m else None,
                      "mentions": [int(x) for x in
                                   re.findall(r"(?:#|\bissue-)(\d+)", body)]})
    return pulls


def claim_scan(runner, repo):
    """{issue: holder} for issues `scripts/wip ls` would show as actively claimed.

    Reuses scripts/wip's own discovery instead of reimplementing it, exactly as
    next_eligible.py does: a plan that wants to retarget a child PR has to know whether an
    agent is live on that child right now, because rule 15 and the epic objective both
    forbid disrupting an active session.
    """
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wip")
    if not os.path.exists(path):
        raise RolloutError("scripts/wip not found next to this tool - the claim state of "
                           "issues cannot be read")
    spec = importlib.util.spec_from_loader("wip", importlib.machinery.SourceFileLoader("wip", path))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        mod.sh = lambda cmd, input=None, check=True: runner(cmd)
        claimed = {}
        for n, payloads in mod.claims_index(repo, sorted(mod.labeled_issues(repo))).items():
            active = [c for c in mod.active_claims(payloads) if c.get("state") in ACTIVE_CLAIM_STATES]
            if active:
                claimed[n] = active[0].get("client") or "unknown"
        for tree in mod.worktrees():
            n = mod.branch_issue(tree.get("branch", ""))
            if n and n not in claimed:
                claimed[n] = "local worktree %s" % (tree.get("branch") or "?")
        return claimed
    except CommandError as e:
        raise RolloutError("the wip claim scan failed: %s" % e)


# --------------------------------------------------------------------------- CI coverage


def _trigger_blocks(text):
    """The `pull_request:` trigger block of a workflow, by indentation.

    A regex over the whole file would read a `branches:` list of a job step or of another
    trigger (push, merge_group) as the PR coverage, which is exactly the false green this
    check exists to prevent: `branches: [master, develop, epic/**]` under `push:` proves no
    PR check at all.
    """
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if re.match(r"^on:\s*$", l))
    except StopIteration:
        return []
    out, i = [], start + 1
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\S", line):
            break
        out.append(line)
        i += 1
    try:
        pr = next(i for i, l in enumerate(out) if re.match(r"^  pull_request:\s*$", l))
    except StopIteration:
        return []
    block = []
    for line in out[pr + 1:]:
        if re.match(r"^  \S", line):
            break
        block.append(line)
    return block


def ci_coverage(repo_root, policy):
    """{workflow: True/False} - does its pull_request trigger carry the epic namespace.

    `The CI contract`_ of #1590 names this the hard prerequisite of the rollout: a child PR
    into epic/<slug> must run the same required checks as one into develop, because an epic
    branch whose children merge unchecked is how the contract loses to the status quo.
    """
    prefix = policy["branch_prefix"]
    result = {}
    for workflow in policy["rollout"]["ci_coverage"]:
        try:
            with open(os.path.join(repo_root, workflow), encoding="utf-8") as fh:
                text = fh.read()
        except OSError as e:
            raise RolloutError("the workflow %s named by the rollout policy cannot be read: %s"
                               % (workflow, e))
        block = _trigger_blocks(text)
        joined = "\n".join(block)
        # Both shapes GitHub accepts: the flow list `branches: [master, develop, epic/**]`
        # and the block list under `branches:`, and a quoted pattern is the same pattern.
        found = False
        for m in re.finditer(r"branches:\s*\[([^\]]*)\]|^\s*-\s+(.+?)\s*$", joined, re.M):
            if m.group(1) is not None:
                candidates = [c.strip().strip("'\"") for c in m.group(1).split(",")]
            else:
                candidates = [m.group(2).strip().strip("'\"")]
            for cand in candidates:
                if cand in (prefix + "**", prefix + "*", prefix.rstrip("/")):
                    found = True
        result[workflow] = found
    return result


# --------------------------------------------------------------------------- the plan


def _action(kind, actor, detail, **extra):
    if actor not in ACTORS:
        raise RolloutError("an action was emitted without a lawful actor: %r" % actor)
    action = {"kind": kind, "actor": actor, "detail": detail}
    action.update(extra)
    return action


def plan_epic(epic, policy, branches, pulls, claims, today, prefix):
    """The decision-table reading of one open epic, plus the actions it owes.

    Returns (row, target, actions, findings). `actions` are what a person (or, where the
    contract allows it, an agent) has to do; `findings` are rollout defects that make this
    epic's state unsafe to enforce on.
    """
    actions, findings = [], []
    slug = epic["slug"]
    number = epic["number"]
    branch = "%s%s" % (prefix, slug) if slug else None
    children = epic["children"]
    open_children = [c for c in children if c["state"] == "OPEN"]

    # Rule 16: the bootstrap epic integrates itself last, so its children stay on develop.
    if number in (policy.get("bootstrap") or {}).get("epics", []):
        branch_exists = bool(branch and branch in branches)
        integration = [p for p in pulls if p["head"] == branch]
        if branch_exists and not integration:
            # The bootstrap is exempt only while it has no branch standing unused: a branch
            # cut for the bootstrapping epic with no integration PR is the cycle rule 16
            # exists to avoid, arriving anyway.
            findings.append({"token": "bootstrap-branch-without-integration-pr",
                             "detail": "epic #%s is the bootstrap epic but %s stands with no "
                                       "open integration PR - rule 16 exempts the children "
                                       "until that PR exists, and a person owns it"
                                       % (number, branch)})
        row = "R3"
        actions.append(_action("keep-children-on-develop", ACTOR_AGENT,
                               "children of the bootstrap epic #%s target %s (rule 16); this "
                               "epic's own integration PR is the last act and the "
                               "demonstration of R7" % (number, BASE_BRANCH)))
        return row, BASE_BRANCH, actions, findings

    # The recorded, time-limited legacy exemptions of the migration section.
    for entry in policy.get("legacy_exceptions") or []:
        if entry.get("epic") != number:
            continue
        expires = _date(entry["expires"], "legacy exception of epic #%s" % number)
        if today <= expires:
            row = "R3"
            actions.append(_action("keep-children-on-develop", ACTOR_AGENT,
                                   "epic #%s is exempt as recorded in %s until %s: %s"
                                   % (number, entry["recorded_in"], expires, entry["reason"])))
            findings.append({"token": "legacy-exception-active",
                             "detail": "epic #%s exempt until %s (recorded in %s)"
                                       % (number, expires, entry["recorded_in"]),
                             "blocking": False})
            return row, BASE_BRANCH, actions, findings
        findings.append({"token": "legacy-exception-expired",
                         "detail": "the legacy exception of epic #%s expired on %s (recorded "
                                   "in %s); it no longer exempts anything and the epic is "
                                   "judged on the contract's own rows - a person either "
                                   "records a new time-limited exception or drops the entry"
                                   % (number, expires, entry["recorded_in"])})

    if not slug:
        if epic.get("slug_misplaced"):
            findings.append({"token": "slug-not-first-line",
                             "detail": "epic #%s carries a `slug:` line that is not its first "
                                       "body line, so rule 1 does not recognise it as the "
                                       "branch identity; a person moves the declaration to "
                                       "the first line before any branch is cut" % number})
        # R3: no declared slug means no canonical branch identity, so nothing may be cut and
        # no child may be pointed anywhere but develop.
        actions.append(_action("declare-slug", ACTOR_HUMAN,
                               "epic #%s declares no `slug: <kebab-name>` first body line; "
                               "the next actionable child owes it before any branch may be "
                               "cut (rule 1, R3)" % number))
        return "R3", BASE_BRANCH, actions, findings

    if not re.match(policy["slug_pattern"], slug):
        findings.append({"token": "slug-invalid",
                         "detail": "epic #%s declares slug %r, which the contract's slug "
                                   "pattern rejects - a person fixes the declaration before a "
                                   "branch is cut (rule 1)" % (number, slug)})
        return "R3", BASE_BRANCH, actions, findings

    branch_exists = branch in branches
    if not branch_exists:
        # R2 wants the branch; rule 3 says only a person cuts it, from current develop.
        actions.append(_action("create-epic-branch", ACTOR_HUMAN,
                               "cut %s from the tip of origin/%s in the repository's branch "
                               "settings (rule 3); an agent never creates it" % (branch,
                                                                                 BASE_BRANCH)))
        if open_children:
            actions.append(_action("protect-epic-branch", ACTOR_HUMAN,
                                   "protect %s like %s: no force-push, no deletion, required "
                                   "checks, no direct push; decide the merge queue for it "
                                   "explicitly (%s)"
                                   % (branch, BASE_BRANCH,
                                      (policy.get("branch_lifecycle") or {}).get("merge_queue",
                                                                                 ""))))
        row = "R2-pending-branch"
        target = branch
    else:
        row = "R2"
        target = branch
        actions.append(_action("children-base-on-epic-branch", ACTOR_AGENT,
                               "%d open child issue(s) of #%s branch from the tip of %s and "
                               "their PRs base on %s only (R2, R5)"
                               % (len(open_children), number, branch, branch)))

    # Base-side rows, read from the open PRs of the repository.
    for p in pulls:
        involved = (p["head_issue"] in {c["number"] for c in children}
                    or any(c in {c_["number"] for c_ in children} for c in p["closes"])
                    or p["head"] == branch)
        if not involved:
            continue
        if p["head"] == branch:
            if p["base"] != BASE_BRANCH:
                findings.append({"token": "epic-branch-not-targeting-develop",
                                 "detail": "PR #%d has %s as its head and %s as its base; an "
                                           "epic branch integrates into %s and nothing else "
                                           "(R6) - a person retargets or closes it"
                                           % (p["number"], branch, p["base"], BASE_BRANCH)})
            else:
                actions.append(_action("human-merge-integration-pr", ACTOR_HUMAN,
                                       "PR #%d is the integration PR of epic #%s: human-"
                                       "approved, human-merged as a merge commit, and its "
                                       "title carries the epic's release class (rule 9, 10)"
                                       % (p["number"], number)))
                actions.append(_action("delete-epic-branch-after-merge", ACTOR_HUMAN,
                                       "on the merge of PR #%d, %s is deleted by the person "
                                       "who merged and the epic is closed (rule 11); an agent "
                                       "never deletes it" % (p["number"], branch)))
            continue
        if p["base"] == branch:
            actions.append(_action("review-child-pr", ACTOR_HUMAN,
                                   "PR #%d (%s -> %s) is a child PR of epic #%s: human review "
                                   "and merge; if the epic head moved, the author merges %s "
                                   "into the child branch - never a rebase (R12)"
                                   % (p["number"], p["head"], p["base"], number, branch)))
            continue
        # A child PR of this epic based anywhere else is R5. It is a *plan item*, not a
        # failure: rule 15 forbids an agent from fixing it, and every such PR open today
        # predates the rule, so failing the tool on it would only teach an agent to go
        # "helpfully" retarget somebody's base. The person who owes the retarget is named;
        # what fails the tool is a rollout defect nobody else reports (see the module
        # docstring for the split).
        findings.append({"token": "child-pr-wrong-base",
                         "blocking": False,
                         "detail": "PR #%d represents a child of epic #%s but bases on %s; "
                                   "the lawful base is %s (R2, R5) - retargeted by a person, "
                                   "never silently rewritten by an agent"
                                   % (p["number"], number, p["base"],
                                      branch if branch_exists else "%s (once it is cut)" % branch),
                         "pr": p["number"]})
        holder = claims.get(p["number"]) or claims.get(p["head_issue"])
        if holder:
            findings[-1]["detail"] += (" - a live claim (%s) is on this work, so the retarget "
                                       "waits for that session to finish" % holder)
    return row, target, actions, findings


def check_slug_uniqueness(epics, branches, prefix):
    """Rule 2: no two open epics share a slug, and a slug may not read as a standing branch.

    A duplicate slug is not a warning: two open epics would resolve to the same canonical
    branch, so the children of one would land on the other's integration target and read as
    satisfied work.
    """
    findings, seen = [], {}
    for epic in epics:
        slug = epic["slug"]
        if not slug:
            continue
        if slug in seen:
            findings.append({"token": "slug-duplicate",
                             "detail": "epics #%s and #%s both declare slug %r; %s would be "
                                       "one branch for two epics (rule 2) - a person renames "
                                       "one slug or closes one epic"
                                       % (seen[slug], epic["number"], slug, prefix + slug)})
        else:
            seen[slug] = epic["number"]
    declared = {prefix + s for s in seen}
    for name in sorted(branches):
        if not name.startswith(prefix):
            continue
        if name not in declared:
            findings.append({"token": "orphan-epic-branch",
                             "detail": "%s stands on origin but no open epic declares that "
                                       "slug; R10/R11 forbid recreating it and an agent may "
                                       "not delete it - a person either closes it out with its "
                                       "epic or records why it stays" % name})
    return findings


def build_plan(runner, policy, repo_root, today, mode, only=None):
    repo = resolve_repo(runner)
    prefix = policy["branch_prefix"]
    branches = origin_branches(runner)
    pulls = open_pulls(runner, repo)
    claims = claim_scan(runner, repo)
    epics = open_epics(runner, repo, only=only)

    rows, actions, findings = [], [], []
    for epic in epics:
        row, target, epic_actions, epic_findings = plan_epic(epic, policy, branches, pulls,
                                                            claims, today, prefix)
        rows.append({"epic": epic["number"], "title": epic["title"], "slug": epic["slug"],
                     "row": row, "target": target, "branch": ("%s%s" % (prefix, epic["slug"])
                                                               if epic["slug"] else None),
                     "children": len(epic["children"]),
                     "open_children": len([c for c in epic["children"] if c["state"] == "OPEN"]),
                     "actions": [a["kind"] for a in epic_actions]})
        actions += [{"epic": epic["number"], **a} for a in epic_actions]
        findings += [{"epic": epic["number"], **f} for f in epic_findings]

    findings += [{"epic": None, **f} for f in check_slug_uniqueness(epics, branches, prefix)]

    coverage = ci_coverage(repo_root, policy)
    for workflow, covered in sorted(coverage.items()):
        if not covered:
            findings.append({"epic": None,
                             "token": "ci-coverage-missing",
                             "detail": "%s has no %s** pattern in its pull_request trigger, so "
                                       "a child PR into an epic branch gets none of its "
                                       "required checks - the hard prerequisite of the rollout "
                                       "(`The CI contract`_)" % (workflow, prefix)})
    epic_branches = sorted(b for b in branches if b.startswith(prefix))
    blocking = [f for f in findings if f.get("blocking") is not False]
    return {
        "schema": SCHEMA, "status": "ok", "error": None, "repo": repo,
        "policy": {"contract": policy["contract"], "advisory_from": policy["rollout"]["advisory_from"],
                   "strict_from": policy["rollout"]["strict_from"], "mode": mode,
                   "bootstrap_epics": (policy.get("bootstrap") or {}).get("epics", [])},
        "today": str(today),
        "inventory": {"open_epics": len(epics), "open_pulls": len(pulls),
                      "active_claims": len(claims), "epic_branches": epic_branches},
        "ci_coverage": [{"workflow": w, "pull_request_covers_epics": covered}
                        for w, covered in sorted(coverage.items())],
        "epics": rows, "actions": actions, "findings": findings,
        "blocking": [f["token"] for f in blocking],
    }


# --------------------------------------------------------------------------- rendering


def render_json(res):
    return json.dumps(res, indent=2, sort_keys=True)


def render_human(res):
    p = res["policy"]
    lines = ["repo %s   %d open epic(s), %d open PR(s), %d active claim(s)   mode %s"
             % (res["repo"], res["inventory"]["open_epics"], res["inventory"]["open_pulls"],
                res["inventory"]["active_claims"], p["mode"]),
             "policy %s   advisory from %s   strict from %s%s"
             % (p["contract"], p["advisory_from"], p["strict_from"],
                "   (date overridden by environment)" if p["mode"] != "advisory" else ""),
             "epic branches on origin: " + (", ".join(res["inventory"]["epic_branches"]) or "none"),
             "", "  epic  row              target                 open/children  actions",
             "  ----  ----------------  ----------------------  -------------  " + "-" * 40]
    for r in res["epics"]:
        lines.append("%6d  %-16s  %-22s  %5d/%-9d  %s"
                     % (r["epic"], r["row"], r["target"], r["open_children"], r["children"],
                        ", ".join(r["actions"]) or "-"))
    lines += ["", "CI coverage of the epic namespace (pull_request trigger):"]
    for c in res["ci_coverage"]:
        lines.append("  %-45s %s" % (c["workflow"], "yes" if c["pull_request_covers_epics"]
                                     else "NO - child PRs get none of these checks"))
    lines += ["", "Actions owed (actor decides who may do it; an agent never takes a person's):"]
    if not res["actions"]:
        lines.append("  -")
    for a in res["actions"]:
        lines.append("  [%-6s] %s" % (a["actor"], a["detail"]))
    lines += ["", "Findings:"]
    if not res["findings"]:
        lines.append("  none")
    for f in res["findings"]:
        lines.append("  %-34s %s" % (f["token"], f["detail"]))
    if res["blocking"]:
        lines.append("")
        lines.append("%s mode: %d blocking finding(s): %s"
                     % (p["mode"], len(res["blocking"]), ", ".join(res["blocking"])))
        if p["mode"] == "advisory":
            lines.append("ADVISORY: reported without failing, because the rollout is advisory "
                         "until %s." % p["strict_from"])
    return "\n".join(lines)


def main(argv=None, runner=None, repo_root=None, today=None):
    ap = argparse.ArgumentParser(
        prog="epic_rollout.py", formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__.split("Usage:")[0].strip(),
        epilog="Rows and rules: docs/source/development/epic-integration-contract.rst. "
               "This tool only plans; it never creates, retargets, deletes or merges.")
    ap.add_argument("--json", action="store_true", help="print the machine-readable plan")
    ap.add_argument("--dry-run", action="store_true",
                    help="the only mode: read-only evaluation, accepted to state intent")
    ap.add_argument("--policy", default=POLICY_PATH, help="rollout policy file (default: %(default)s)")
    ap.add_argument("--today", default=None, help="pretend it is this ISO date")
    ap.add_argument("--epic", type=int, default=None, help="plan one epic instead of all open ones")
    ap.add_argument("--mode", choices=("auto", "advisory", "strict"), default="auto",
                    help="auto is advisory before the policy's strict_from, strict from it")
    args = ap.parse_args(argv)

    if runner is None:
        runner = subprocess_runner
    if repo_root is None:
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        policy = load_policy(args.policy)
        if args.today is not None:
            today_value = date.fromisoformat(args.today)
        elif today is not None:
            today_value = today if isinstance(today, date) else date.fromisoformat(str(today))
        else:
            today_value = date.today()
        mode = mode_for(today_value, policy, args.mode)
        res = build_plan(runner, policy, repo_root, today_value, mode, only=args.epic)
    except (RolloutError, PolicyError, ValueError) as e:
        if args.json:
            print(render_json({"schema": SCHEMA, "status": "error", "error": str(e)}))
        else:
            print("ERROR - fail closed, plan nothing\n%s" % e)
        return 2
    print(render_json(res) if args.json else render_human(res))
    return 1 if (res["blocking"] and mode == "strict") else 0


if __name__ == "__main__":
    sys.exit(main())
