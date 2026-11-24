#!/usr/bin/env python3
"""epic_integration_dryrun: end-to-end validation of the epic workflow, offline.

Maintenance tool carried by this repository; run it as
`python3 scripts/epic_integration_dryrun.py --scenario FILE` from the repository
root. It replays a whole epic - native child selection, epic branch creation, child
PRs and their checks, blocker merges, integration readiness, the human-approved
integration merge, cancellation, migration conflicts, rollback and recovery -
against one scenario file, and reports per acceptance line whether the observed
behaviour matches the decision table of
`docs/source/development/epic-integration-contract.rst` (rows R1-R13, rules 1-16)
and the CI contract.

WHY A SCENARIO AND NOT A LIVE REPOSITORY
----------------------------------------
#1595 asks for an *isolated dry run*: nothing here creates a branch, opens a PR,
merges anything, moves a label or touches a running stack. The engine executes no
command at all: every fact it observes - the native parent link, the
`agent: approved` provenance, the commit topology, PR bases and merges, check runs,
claims, workflow triggers - is answered from the scenario, and every read it *would*
have asked GitHub or git is journalled against the read-only allowlist below. A
scenario that needs an answer the engine cannot derive fails closed with exit 2.

WHAT IT DECIDES
---------------
One named check per acceptance line: R1-R4 selection (`child-selection`), the branch
cut from develop (rule 3: `branch-creation`), R2/R12 child start points
(`child-starts-from-epic-head`), the CI contract on child PRs (`child-pr-checks`)
and on epic-base triggers (`epic-ci-coverage`), ancestry-based blockers (R7/R8:
`blocker-satisfied-by-ancestry`, `readiness`), the single human-approved integration
PR (rule 9: `integration-pr`), refused wrong bases with a person as the only
retargeting actor (R5/R6: `wrong-base`, `epic-head-base`), paused and claimed work
(`paused-or-claimed`), rule 14 (`claim-carries-target`), `cancellation`,
`migration-conflict`, the #1577/#1580 semantic history (rule 10:
`release-semantic-history`), `rollback`, `recovery-after-deletion` (R10), the
release-only documentation rule (#1589: `no-docs-job`), the human-authority
invariants (`no-self-approval`, `no-direct-push`), `production-untouched` and
`no-competing-orchestrator` (AO stays the only orchestrator).

Every check id MUST appear in the scenario's `expectations`: a check nobody stated
an expectation for is a check that proved nothing, which is exactly the green that
means nothing this tool exists to refuse.

USAGE
  python3 scripts/epic_integration_dryrun.py --scenario FILE
                                             [--json] [--evidence-out FILE]
                                             [--fail-on-findings]
  python3 scripts/epic_integration_dryrun.py --list-checks

Exit codes: 0 every check observed what the scenario expects (a passing check can
still carry severity "finding", which fails only with --fail-on-findings), 1 a check
did not observe what the scenario expects, 2 the harness could not run - a malformed
scenario, a missing or unknown expectation, a read outside the read-only allowlist.
Exit 2 is a refusal, not a result: no verdicts are reported for a world the tool
could not read.

The offline suite is scripts/test_epic_integration_dryrun.py (the engine driven over
generated scenarios; no `gh`, no network, no git), as every suite under scripts/.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

SCHEMA = "epic-integration-dryrun/v1"
SCENARIO_SCHEMA = "epic-integration-dryrun-scenario/v1"

EPIC_PREFIX = "epic/"
APPROVED_LABEL = "agent: approved"
PAUSED_LABEL = "agent: paused"
PERMANENT = ("develop", "master")

# A documentation build is release-only (#1589); the everyday epic path must never
# run one. Matched against workflow job names, case-insensitively.
DOC_JOB_RE = re.compile(r"(^|[-_/])(docs|documentation|sphinx|readthedocs)([-_/]|$)")
# A scheduler of its own is what the epic objective forbids ("no competing
# scheduler"): AO keeps scheduling, this contract only extends its inputs.
SCHEDULER_FILE_RE = re.compile(r"(^|/)(scheduler|daemon|cron|watcher)", re.I)

# The reads the engine may journal. It executes none of them - the allowlist is the
# guard that a future edit cannot turn the dry run into an actor.
READ_ONLY_COMMANDS = (
    ("gh", "api", "graphql"),
    ("gh", "api", "repos"),
    ("gh", "repo", "view"),
    ("git", "merge-base", "--is-ancestor"),
    ("git", "ls-remote", "--heads"),
    ("git", "rev-parse", "--verify"),
    ("git", "log"),
    ("git", "show"),
)

SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
BRANCH_ISSUE_RE = re.compile(r"(?:^|/)(?:issue[-_]?|#)(\d+)")
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)", re.I)
SLUG_RE = re.compile(r"^\s*slug:\s*([a-z0-9][a-z0-9-]{0,19})\s*$", re.M)
AGENT_ACTOR_RE = re.compile(r"(^|[-_/.])(agent|bot)([-_/.]|$)", re.I)
# The classification carrier of #1580: the '!' has to be on the title that reaches the
# integration history - a footer does not survive a merge-merge.
BREAKING_TITLE_RE = re.compile(r"^[a-z]+(\([^)]*\))?!:")

CHECK_IDS = [
    "child-selection", "branch-creation", "child-starts-from-epic-head",
    "child-pr-checks", "blocker-satisfied-by-ancestry", "readiness", "integration-pr",
    "wrong-base", "epic-head-base", "paused-or-claimed", "claim-carries-target",
    "cancellation", "migration-conflict", "release-semantic-history", "rollback",
    "recovery-after-deletion", "no-docs-job", "epic-ci-coverage", "no-self-approval",
    "no-direct-push", "production-untouched", "no-competing-orchestrator",
]


class HarnessError(Exception):
    """The dry run could not be run at all: a scenario that cannot be read, a check the
    scenario states no expectation for, a read outside the read-only allowlist. Kept
    apart from a failed check, which is a real answer to a real question."""


# --------------------------------------------------------------------- scenario model


class Scenario:
    """The whole world one dry run observes: commits, branches, PRs, claims, CI.

    `commits` maps a sha to {"parents": [sha], "cut_from": branch|null, "cut": bool,
    "sync": bool, "origin": "base"|null}; `branches` maps a branch name to its head
    sha. An ancestor question is answered from that topology and journalled as the git
    command whose answer it is, so the report shows what was verified without the tool
    ever running it.
    """

    def __init__(self, scn):
        self.raw = scn
        self.name = scn["name"]
        self.repo = scn["repo"]
        self.epic = scn["epic"]
        self.issues = {int(k): v for k, v in scn["issues"].items()}
        self.commits = scn.get("commits", {})
        self.branches = scn["branches"]
        self.pulls = {}
        for key, pull in scn["pulls"].items():
            pull = dict(pull)
            pull.setdefault("number", int(key))   # the key is the PR number
            self.pulls[int(key)] = pull
        self.claims = scn.get("claims", {})
        self.workflows = scn.get("workflows", {})
        self.added_files = scn.get("added_files", [])
        self.agent_actor = (scn.get("agent_actor") or "agent-bot").lower()
        self.humans = [h.lower() for h in scn.get("humans", ["jokiefer"])]
        self.expects = scn["expectations"]
        self.baseline_master = scn.get("baseline_master_sha")
        self.facts = scn.get("facts", {})
        self.commands = []

    # ---- journalled reads ---------------------------------------------------
    def ask(self, *argv):
        """Journal one read-only command; the scenario, not the system, answers it."""
        argv = list(argv)
        head = tuple(argv[:3])
        if head not in READ_ONLY_COMMANDS and tuple(argv[:2]) not in READ_ONLY_COMMANDS:
            raise HarnessError("the dry run would have to run `%s`, which is not a "
                               "read-only command - refusing to answer it from a "
                               "scenario" % " ".join(argv))
        self.commands.append(" ".join(argv))

    # ---- topology -----------------------------------------------------------
    def sha(self, ref):
        if ref in self.branches:
            return self.branches[ref]
        if SHA_RE.match(ref or ""):
            return ref
        raise HarnessError("the scenario uses `%s` but carries no such branch or sha" % ref)

    def ancestors(self, ref):
        """Every ancestor sha of a ref, itself included, over all parents.

        Shared ancestors are normal - two children cut from one epic head, or the
        merge of the integration target into a branch - so a repeat is a skip, not a
        cycle. Only a walk longer than the world it walks is refused as a cycle.
        """
        sha = self.sha(ref)
        seen, queue = [], [sha]
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            if len(seen) > len(self.commits) + 1:
                raise HarnessError("the scenario's commit graph cycles at %s" % ref)
            seen.append(current)
            queue.extend((self.commits.get(current) or {}).get("parents", []))
        return seen

    def first_parent_chain(self, ref):
        """The first-parent chain of a ref, used for the branch-cut question."""
        current = self.sha(ref)
        chain = []
        while current:
            if current in chain:
                raise HarnessError("the scenario's commit graph cycles at %s" % ref)
            chain.append(current)
            parents = (self.commits.get(current) or {}).get("parents") or []
            current = parents[0] if parents else None
        return chain

    def is_ancestor(self, sha, ref):
        """`git merge-base --is-ancestor <sha> <ref>`, answered from the topology."""
        self.ask("git", "merge-base", "--is-ancestor", str(sha), str(ref))
        if not SHA_RE.match(sha or ""):
            raise HarnessError("`%s` is not a commit sha - refusing to guess" % sha)
        try:
            return sha in self.ancestors(ref)
        except HarnessError:
            return False              # a ref the world does not have has no ancestors

    def contribution(self, merge_sha):
        """The shas a merge brings in: its ancestors minus what its parents already had.

        This is what git shows as the commits of a merge, and it is the set the
        direct-push check must treat as covered by a PR - the shared history a merge
        merely carries stays somebody else's responsibility.
        """
        try:
            merge = self.sha(merge_sha)
        except HarnessError:
            return set()
        parents = (self.commits.get(merge) or {}).get("parents") or []
        own = set(self.ancestors(merge))
        if not parents:
            return {merge}
        for parent in parents:
            own -= set(self.ancestors(parent))
        return own

    def cut_from(self, ref):
        """The branch a branch was created from, as recorded when it was cut (rule 3)."""
        try:
            chain = self.first_parent_chain(ref)
        except HarnessError:
            return None
        for sha in chain:
            cut = (self.commits.get(sha) or {}).get("cut_from")
            if cut:
                return cut
            if (self.commits.get(sha) or {}).get("origin") == "base":
                return None
        return None

    # ---- issues ---------------------------------------------------------------
    def children(self):
        """The epic's native sub-issues, in number order (the native listing).

        `in_epic: false` marks an issue that is not a child of the epic - a follow-up
        of an integrated epic is a new top-level issue (R10), not a new child.
        """
        return sorted(n for n, i in self.issues.items() if i.get("in_epic", True))

    def top_level(self):
        """Issues of the world that are *not* children of the epic.

        R10: follow-up work on the topic of an integrated epic is a new top-level
        issue, so a scenario marks it `in_epic: false` and the engine judges it under
        R1 - from develop, to develop. It is judged, not skipped: work on a retired
        epic's topic that was cut from the retired branch is the R10 violation.
        """
        return sorted(n for n, i in self.issues.items() if not i.get("in_epic", True))

    def claims_on(self, num):
        return [c for c in self.claims.get(str(num), [])
                if c.get("state") in ("wip", "waiting")]

    # ---- pulls --------------------------------------------------------------
    def pr_for_issue(self, num):
        """The PR representing issue #num: a closing keyword or an `issue-<N>` head."""
        for p in self.pulls.values():
            if num in {int(x) for x in CLOSES_RE.findall(p.get("body") or "")}:
                return p
            m = BRANCH_ISSUE_RE.search(p["head"] or "")
            if m and m.group(1) == str(num):
                return p
        return None

    # ---- expectations ---------------------------------------------------------
    def expect(self, check_id):
        if check_id not in self.expects:
            raise HarnessError("scenario %s states no expectation for check `%s`"
                               % (self.name, check_id))
        return self.expects[check_id] or {}

    # ---- CI contract ----------------------------------------------------------
    def triggers_for(self, base):
        """Workflows whose pull_request branches cover `base` (`epic/**` allowed)."""
        out = []
        for name, spec in self.workflows.items():
            for pattern in spec.get("pull_request_branches", []):
                if pattern == base or (pattern.endswith("/**")
                                       and base.startswith(pattern[:-2])):
                    out.append(name)
                    break
        return sorted(out)

    def required_jobs(self, base):
        jobs = set()
        for name in self.triggers_for(base):
            jobs.update(self.workflows[name].get("jobs", []))
        return sorted(jobs)


def validate_scenario(raw, where="the scenario"):
    if not isinstance(raw, dict):
        raise HarnessError("%s is not an object" % where)
    if raw.get("schema") != SCENARIO_SCHEMA:
        raise HarnessError("%s declares schema %r, expected %r"
                           % (where, raw.get("schema"), SCENARIO_SCHEMA))
    for key in ("name", "repo", "epic", "issues", "pulls", "branches", "expectations"):
        if key not in raw:
            raise HarnessError("%s has no `%s`" % (where, key))
    if raw["repo"].count("/") != 1:
        raise HarnessError("%s: repo must be owner/name, got %r" % (where, raw["repo"]))
    for key in ("number", "title", "body", "state"):
        if key not in raw["epic"]:
            raise HarnessError("%s: the epic has no `%s`" % (where, key))
    for num, pull in raw["pulls"].items():
        for key in ("head", "base", "state"):
            if key not in pull:
                raise HarnessError("%s: pull %s has no `%s`" % (where, num, key))
    missing = [c for c in CHECK_IDS if c not in raw["expectations"]]
    if missing:
        raise HarnessError("%s: expectations missing for %s - a check nobody stated an "
                           "expectation for proves nothing" % (where, ", ".join(missing)))
    unknown = sorted(c for c in raw["expectations"] if c not in CHECK_IDS)
    if unknown:
        raise HarnessError("%s: expectations for unknown checks: %s"
                           % (where, ", ".join(unknown)))
    return raw


def load_scenario(path):
    try:
        with open(path, encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as e:
        raise HarnessError("cannot read the scenario %s: %s" % (path, e))
    except ValueError as e:
        raise HarnessError("the scenario %s is not JSON: %s" % (path, e))
    return Scenario(validate_scenario(raw, where=path))


# ----------------------------------------------------------------------------- engine


class Check:
    def __init__(self, cid, expected, observed, ok, detail="", severity="check"):
        self.id, self.expected, self.observed = cid, expected, observed
        self.ok, self.detail, self.severity = ok, detail, severity

    def as_dict(self):
        return {"id": self.id, "expected": self.expected, "observed": self.observed,
                "ok": self.ok, "severity": self.severity, "detail": self.detail}


def is_agent_actor(actor, scn):
    """A person on the allowlist is not an agent; the named agent actor and any
    agent/bot-shaped login is. An unnamed actor is refused rather than guessed: who
    merged or approved is a fact a scenario has to state, not one this tool invents."""
    if actor is None:
        raise HarnessError("a merge, approval or label actor is not named in the "
                           "scenario - provenance cannot be told, so nothing is green")
    login = str(actor).lower()
    if login in scn.humans:
        return False
    if not login or login == scn.agent_actor:
        return True
    return bool(AGENT_ACTOR_RE.search(login))


def named(d, key, scn):
    """Judge the actor of a fact the scenario states; skip when it states none."""
    if key not in d or d[key] in (None, ""):
        return False
    return is_agent_actor(d[key], scn)


def epic_branch_of(scn):
    m = SLUG_RE.search(scn.epic.get("body") or "")
    return EPIC_PREFIX + m.group(1) if m else None


def select_children(scn, epic_branch):
    """R1-R4: the one legal base for each native child, or None when no work may start."""
    out = {}
    for num in scn.children():
        labels = scn.issues[num].get("labels", [])
        reasons = []
        if scn.epic.get("state") != "OPEN":
            base, why = None, "epic-closed"            # R10/R11: a closed epic takes nothing
        elif APPROVED_LABEL not in labels:
            base, why = None, "not-approved"           # R4: nothing may be scheduled
        elif epic_branch is None or epic_branch not in scn.branches:
            base, why = "develop", "bootstrap-no-branch"  # R3: the branch was never cut
        else:
            base, why = epic_branch, ""                # R2: exactly one legal base
        if why:
            reasons.append(why)
        if PAUSED_LABEL in labels:
            base = None
            reasons.append("paused")
        out[num] = {"base": base, "reasons": reasons}
    for num in scn.top_level():                        # R1/R10: independent work, develop
        start = scn.issues[num].get("starts_from")
        reasons = ["not-a-child"]
        base = "develop"
        if start is not None and scn.cut_from(start) == epic_branch:
            base = None                                # R10: the retired branch is no base
            reasons.append("r10-recreated-branch")
        out[num] = {"base": base, "reasons": reasons}
    return out


def dependency_facts(scn, epic_branch):
    """{"child->blocker": facts} for every native blocked_by edge in the world.

    Rule 7: a dependency counts only when a merged PR's merge commit is an ancestor of
    BOTH the epic head and develop. Closed on GitHub proves nothing; a merge that lives
    only on another private epic branch proves nothing either.
    """
    facts = {}
    for child in scn.children():
        for blocker in scn.issues[child].get("blocked_by", []):
            state = scn.issues[child].get("blocked_by_state", {}).get(str(blocker), "OPEN")
            pr = scn.pr_for_issue(blocker)
            merged = bool(pr) and pr.get("state") == "merged"
            sha = (pr or {}).get("merge_sha")
            facts["%d->%d" % (child, blocker)] = {
                "state": state,
                "merged": merged,
                "on_epic": bool(merged and sha and epic_branch
                                and scn.is_ancestor(sha, epic_branch)),
                "on_develop": bool(merged and sha and scn.is_ancestor(sha, "develop")),
            }
    return facts


def migration_conflicts(scn, epic_branch):
    """`app/number` of every migration slot two children merged into the epic both claim.

    The epic head is where two children's migrations collide first (CI contract); the
    renumbered side settles it, exactly what `migration_graph_smoke.py` reports.
    """
    by_slot = {}
    for p in scn.pulls.values():
        if p.get("base") != epic_branch or p.get("state") != "merged":
            continue
        for mig in p.get("migrations", []):
            slot = (mig["app"], mig["name"].split("_", 1)[0])
            by_slot.setdefault(slot, []).append(bool(p.get("renumbered")))
    return sorted("%s/%s" % (app, number) for (app, number), sides in by_slot.items()
                  if len(sides) > 1 and not any(sides))


def readiness(scn, sel, epic_branch, dep_facts, conflicts):
    """R7: when may the integration PR open; R8: what refuses it."""
    if epic_branch is None or epic_branch not in scn.branches:
        return False, ["no-epic-branch"]
    reasons = []
    for num, v in sorted(sel.items()):
        if v["base"] is None:
            continue                       # owed nothing (unapproved / epic closed)
        pr = scn.pr_for_issue(num)
        if pr is None or pr.get("state") != "merged" or pr.get("base") != epic_branch:
            reasons.append("child-%d-not-merged-into-epic" % num)
            continue
        if pr.get("failing"):
            reasons.append("child-%d-checks-failing" % num)
    for edge, fact in sorted(dep_facts.items()):
        blocker = edge.split("->")[1]
        if fact["state"] != "COMPLETED":
            reasons.append("blocker-%s-not-completed" % blocker)
        elif not fact["on_epic"]:
            reasons.append("dependency-%s-not-in-epic-ancestry" % blocker)
        elif not fact["on_develop"]:
            reasons.append("dependency-%s-not-in-develop" % blocker)
    reasons += ["migration-conflict:%s" % c for c in conflicts]
    return not reasons, reasons


def run_scenario(scn):
    """Every check of the contract against one scenario -> list of Check."""
    checks = []
    epic_branch = epic_branch_of(scn)
    if epic_branch:
        scn.ask("git", "ls-remote", "--heads", "origin", epic_branch)
    sel = select_children(scn, epic_branch)
    dep_facts = dependency_facts(scn, epic_branch)
    conflicts = migration_conflicts(scn, epic_branch)

    def add(cid, observed, ok_fn, detail):
        expected = scn.expect(cid)
        ok, severity = ok_fn(expected, observed)
        checks.append(Check(cid, expected, observed, ok, detail, severity))

    # --- child selection (R1-R4) ----------------------------------------------
    def ok_selection(expected, obs):
        want = {str(k): v for k, v in expected.get("children", {}).items()}
        if set(want) != set(obs):
            return False, "check"
        for num, w in want.items():
            got = obs[num]
            if got["base"] != w.get("base"):
                return False, "check"
            if not set(w.get("reasons", [])) <= set(got["reasons"]):
                return False, "check"
        return True, "check"
    add("child-selection",
        {str(n): {"base": v["base"], "reasons": v["reasons"]} for n, v in sel.items()},
        ok_selection,
        "a child does not get the one base the decision table gives it")

    # --- the epic branch cut (rule 3) ------------------------------------------
    observed = {"exists": bool(epic_branch) and epic_branch in scn.branches,
                "name": epic_branch,
                "cut_from": scn.cut_from(epic_branch) if epic_branch else None}

    def ok_branch(expected, obs):
        if obs["exists"] != expected.get("exists"):
            return False, "check"
        if obs["exists"] and obs["cut_from"] != expected.get("cut_from"):
            return False, "check"      # rule 3: cut from current develop, once, by a person
        return True, "check"
    add("branch-creation", observed, ok_branch,
        "the epic branch is not the canonical branch cut from develop at creation")

    # --- children start from the epic head (R2/R12) ------------------------------
    off_head = []
    for num, v in sorted(sel.items()):
        if v["base"] != epic_branch or epic_branch is None:
            continue
        start = scn.issues[num].get("starts_from")
        if start is None:
            off_head.append(num)
            continue
        scn.ask("git", "rev-parse", "--verify", str(start))
        scn.sha(start)
        if scn.cut_from(start) != epic_branch \
                or not scn.is_ancestor(scn.sha(start), epic_branch):
            off_head.append(num)

    def ok_start(expected, obs):
        if obs["children_off_head"] != expected.get("children_off_head", []):
            return False, "check"
        # A child that moved with the epic did it by merging the epic head - rebasing a
        # branch open for review stays forbidden (rule 5, AGENTS.md).
        return not any(p.get("rebased_open") for p in scn.pulls.values()), "check"
    add("child-starts-from-epic-head", {"children_off_head": off_head}, ok_start,
        "a child does not start from the epic head, or an open branch was rebased "
        "instead of merging the epic head (R12)")

    # --- child PR checks: the CI contract -----------------------------------------
    observed = {}
    for num in scn.children():
        pr = scn.pr_for_issue(num)
        if pr is None:
            continue
        observed[str(pr["number"])] = {
            "jobs": sorted(pr.get("checks", [])),
            "failing": sorted(pr.get("failing", [])),
            "base": pr["base"],
            "required": scn.required_jobs(pr["base"]),
        }

    def ok_child_pr(expected, obs):
        for pr_num, w in expected.items():
            got = obs.get(str(pr_num))
            if got is None:
                return False, "check"
            if got["failing"] != sorted(w.get("failing", [])):
                return False, "check"
            jobs = w.get("jobs")
            if jobs is not None and got["jobs"] != sorted(jobs):
                return False, "check"
            # A PR into an epic branch no workflow triggers for has no required set at
            # all - a green that means nothing (the rollout gap #1594 closes).
            if got["base"].startswith(EPIC_PREFIX) and not got["required"]:
                return False, "check"
            if jobs is not None and sorted(jobs) != got["required"]:
                return False, "check"
        return True, "check"
    add("child-pr-checks", observed, ok_child_pr,
        "a child PR does not carry exactly the required check set its base triggers, "
        "or its base gets no CI at all")

    # --- blockers resolve in the ancestry (R7/R8) -----------------------------------
    add("blocker-satisfied-by-ancestry", dep_facts,
        lambda e, o: (o == e, "check"),
        "a dependency resolves differently than by ancestry: closed is not implemented, "
        "and merged-only-into-another-private-branch is not available either")

    # --- readiness (R7) ---------------------------------------------------------------
    ready, reasons = readiness(scn, sel, epic_branch, dep_facts, conflicts)

    def ok_readiness(expected, obs):
        if obs["ready"] != expected.get("ready"):
            return False, "check"
        return set(obs["reasons"]) == set(expected.get("reasons", [])), "check"
    add("readiness", {"ready": ready, "reasons": reasons}, ok_readiness,
        "readiness does not answer R7: every required child merged INTO the epic, every "
        "dependency an ancestor of the epic head AND of develop, checks green, conflicts "
        "settled")

    # --- the integration PR (rule 9) ---------------------------------------------------
    integration = [p for p in scn.pulls.values() if p.get("head") == epic_branch]
    observed = None
    if integration:
        p = integration[0]
        observed = {"count": len(integration), "base": p["base"], "head": p["head"],
                    "merge": p["state"] == "merged",
                    "merged_by": p.get("merged_by") if p["state"] == "merged" else None}

    def ok_integration(expected, obs):
        if not expected:
            return obs is None, "check"
        if obs is None:
            return False, "check"
        if obs["count"] != 1 or obs["head"] != epic_branch or obs["base"] != "develop":
            return False, "check"                    # R6/R7: exactly one, into develop
        if obs["merge"] != expected.get("merge"):
            return False, "check"
        if obs["merge"] and is_agent_actor(obs["merged_by"], scn):
            return False, "check"                    # rule 9: human-approved, human-merged
        return True, "check"
    add("integration-pr", observed, ok_integration,
        "the epic does not integrate through exactly one human-approved merge commit "
        "into develop (rule 9)")

    # --- wrong bases are refused, and only a person retargets (R5/R6) -------------------
    observed = {}
    for num, v in sorted(sel.items()):
        pr = scn.pr_for_issue(num)
        if pr is None:
            continue
        who = pr.get("retargeted_by")
        observed[str(pr["number"])] = {
            "wrong": v["base"] is not None and pr["base"] != v["base"],
            "by_agent": bool(who) and is_agent_actor(who, scn),
        }

    def ok_wrong_base(expected, obs):
        if any(v["by_agent"] for v in obs.values()):
            return False, "check"        # rule 15: an agent never retargets, whatever else
        # Fail closed: a wrong base the scenario does not list is a wrong base the
        # scenario did not know about, which is a finding, not an absent one.
        if {n for n, v in obs.items() if v["wrong"]} - {str(k) for k in expected}:
            return False, "check"
        for pr_num, w in expected.items():
            got = obs.get(str(pr_num))
            if got is None or got["wrong"] != bool(w.get("wrong")) \
                    or got["by_agent"] != bool(w.get("by_agent")):
                return False, "check"
        return True, "check"
    add("wrong-base", observed, ok_wrong_base,
        "a wrong base was not refused, or an agent retargeted a PR (R5/R6 name a person "
        "as the actor)")

    add("epic-head-base",
        {"pulls": sorted(p["number"] for p in scn.pulls.values()
                         if p.get("head") == epic_branch and p.get("base") != "develop")},
        lambda e, o: (o["pulls"] == sorted(e.get("pulls", [])), "check"),
        "a PR whose head is the epic branch does not target develop (R6)")

    # --- paused and claimed work ---------------------------------------------------------
    observed = {}
    for num in scn.children():
        labels = scn.issues[num].get("labels", [])
        if PAUSED_LABEL in labels or scn.claims_on(num):
            observed[str(num)] = {"paused": PAUSED_LABEL in labels,
                                  "claimed": bool(scn.claims_on(num))}

    def ok_paused(expected, obs):
        if {str(k): v for k, v in expected.items()} != obs:
            return False, "check"
        for n, v in obs.items():
            if v["paused"] and (sel[int(n)]["base"] is not None
                                or scn.issues[int(n)].get("worked_on_while_paused")):
                return False, "check"        # paused work was worked on anyway
        return True, "check"
    add("paused-or-claimed", observed, ok_paused,
        "paused or claimed work was treated as schedulable")

    # --- claims carry the integration target (rule 14) ------------------------------------
    observed = {}
    for num in scn.children():
        for claim in scn.claims_on(num):
            observed[str(num)] = {"target": claim.get("integration_target"),
                                  "decision": sel[num]["base"]}

    def ok_claim(expected, obs):
        want = {str(k): v for k, v in expected.items()}
        if set(want) != set(obs):
            return False, "check"
        return all(obs[n]["target"] == want[n].get("target")
                   and obs[n]["target"] == obs[n]["decision"] for n in want), "check"
    add("claim-carries-target", observed, ok_claim,
        "a claim does not record the integration target the scheduling decision used")

    # --- cancellation -----------------------------------------------------------------------
    open_child_prs = sorted(
        p["number"] for p in scn.pulls.values()
        if p["state"] == "open" and BRANCH_ISSUE_RE.search(p["head"] or "")
        and int(BRANCH_ISSUE_RE.search(p["head"]).group(1)) in scn.children())

    def ok_cancellation(expected, obs):
        if expected.get("epic_state") and obs["epic_state"] != expected["epic_state"]:
            return False, "check"
        return sorted(expected.get("no_open_prs_for", [])) == obs["open_child_prs"], "check"
    add("cancellation", {"epic_state": scn.epic.get("state"),
                         "open_child_prs": open_child_prs}, ok_cancellation,
        "cancelling the epic left a child PR open while the epic is closed")

    # --- migration conflicts on the epic head ---------------------------------------------
    observed = {"conflicts": conflicts,
                "renumbered": sorted({str(p["number"]) for p in scn.pulls.values()
                                      if p.get("renumbered")})}
    add("migration-conflict", observed,
        lambda e, o: (o["conflicts"] == sorted(e.get("conflicts", []))
                      and o["renumbered"] == sorted(e.get("renumbered", [])), "check"),
        "two children's migrations collide on the epic head without the renumbering "
        "that settles it")

    # --- release semantic history (rule 10, #1577/#1580) ------------------------------------
    merged_children = [p for p in scn.pulls.values()
                       if p.get("base") == epic_branch and p.get("state") == "merged"]
    squashed = bool(scn.facts.get("squashed", False))
    breaking_children = [p for p in merged_children if p.get("breaking")]
    integration_merged = [p for p in scn.pulls.values()
                          if p.get("head") == epic_branch and p.get("state") == "merged"]
    observed = {
        "one_integration_entry": len(integration_merged) <= 1,
        "child_titles_survive": all((p.get("title") or "").strip()
                                    for p in merged_children) and not squashed,
        "breaking_survives": all(bool(BREAKING_TITLE_RE.search(p.get("title") or ""))
                                 for p in integration_merged) if breaking_children else True,
        "squashed": squashed,
    }

    def ok_history(expected, obs):
        for key in ("one_integration_entry", "child_titles_survive",
                    "breaking_survives", "squashed"):
            if key in expected and obs[key] != expected[key]:
                return False, "check"
        return True, "check"
    add("release-semantic-history", observed, ok_history,
        "the epic history does not fold into one integration entry whose merge keeps the "
        "epic title while every child merge commit stays reachable and a breaking fact "
        "survives on the title")

    # --- rollback ---------------------------------------------------------------------------
    revert = [p for p in scn.pulls.values()
              if (p.get("title") or "").lower().startswith(("revert", "reverts"))]
    observed = {
        "reverted": any(p["state"] == "merged" for p in revert),
        "revert_merged_into": next((p["base"] for p in revert if p["state"] == "merged"),
                                   None),
        "rewrote_history": bool(scn.facts.get("history_rewritten", False)),
        "force_pushed": bool(scn.facts.get("force_pushed", False)),
    }

    def ok_rollback(expected, obs):
        for key in ("reverted", "revert_merged_into", "rewrote_history", "force_pushed"):
            if key in expected and obs[key] != expected[key]:
                return False, "check"
        # Recovery is a revert PR, never a rewrite or a force-push of a permanent branch.
        return not obs["rewrote_history"] and not obs["force_pushed"], "check"
    add("rollback", observed, ok_rollback,
        "the epic cannot be rolled back with a plain revert PR; a history rewrite or a "
        "force-push is not a recovery")

    # --- recovery after the integration merge (R10) -------------------------------------------
    work_on_develop = (epic_branch in scn.branches
                       and scn.is_ancestor(scn.branches[epic_branch], "develop"))
    observed = {"branch_exists": epic_branch in scn.branches,
                "work_on_develop": work_on_develop,
                "recreated": bool(scn.facts.get("branch_recreated", False))}

    def ok_recovery(expected, obs):
        for key in ("branch_exists", "work_on_develop", "recreated"):
            if key in expected and obs[key] != expected[key]:
                return False, "check"
        return not obs["recreated"], "check"   # R10: a retired branch must not return
    add("recovery-after-deletion", observed, ok_recovery,
        "after the integration merge the topic continues on develop (R10); the epic "
        "branch is retired by the person who merged and never recreated")

    # --- release-only documentation (#1589) ----------------------------------------
    # A doc job is only a violation where an everyday PR path can reach it: the
    # scenario states its whole doc-job inventory, and the engine verifies that none
    # of it sits behind a pull_request trigger.
    doc_jobs = sorted({job for spec in scn.workflows.values()
                       for job in spec.get("jobs", []) if DOC_JOB_RE.search(job)})
    in_pr_path = sorted({job for name, spec in scn.workflows.items()
                         if spec.get("pull_request_branches")
                         for job in spec.get("jobs", []) if DOC_JOB_RE.search(job)})
    add("no-docs-job", {"doc_jobs": doc_jobs, "in_pr_path": in_pr_path},
        lambda e, o: (o["doc_jobs"] == sorted(e.get("doc_jobs", []))
                      and o["in_pr_path"] == sorted(e.get("in_pr_path", [])), "check"),
        "an everyday workflow in the epic path builds documentation - publication is "
        "release-only (#1589)")

    # --- CI triggers cover the epic base (the rollout gap) --------------------------------------
    covered = sorted(name for name, spec in scn.workflows.items()
                     if any(p.startswith(EPIC_PREFIX)
                            for p in spec.get("pull_request_branches", [])))
    expected_required = scn.expect("epic-ci-coverage").get("required", [])
    missing = [w for w in expected_required if w not in covered]

    def ok_ci_coverage(expected, obs):
        return (obs["covered_by"] == sorted(expected.get("covered_by", []))
                and not obs["missing"]), "check"
    add("epic-ci-coverage", {"covered_by": covered, "missing": missing}, ok_ci_coverage,
        "CI does not trigger for the epic base where the contract requires it - a child "
        "PR there would be green without checks")

    # --- human authority (rule 15) ----------------------------------------------------------------
    offenders = sorted(
        {"merge:%s" % p["number"] for p in scn.pulls.values()
         if p["state"] == "merged" and named(p, "merged_by", scn)}
        | {"approval:%d" % n for n, i in scn.issues.items()
           if APPROVED_LABEL in i.get("labels", []) and named(i, "approved_by", scn)}
        | {"label:%s" % p["number"] for p in scn.pulls.values()
           if p["state"] == "merged" and named(p, "labeled_by", scn)}
        | {"claim:%s" % n for n in scn.claims
           if any(named(c, "claimed_by", scn) for c in scn.claims_on(n))})

    def ok_self_approval(expected, obs):
        # Only the empty list is ever acceptable: no agent approves, labels or merges.
        return not obs["offenders"], "check"
    add("no-self-approval", {"offenders": offenders}, ok_self_approval,
        "an agent approved, labelled or merged the work it authored")

    # --- every commit on a permanent branch came through a merged PR ------------------------------
    covered_shas = set()
    for p in scn.pulls.values():
        if p["state"] != "merged":
            continue
        covered_shas.update(scn.contribution(p.get("merge_sha")))
        covered_shas.update(p.get("commits", []))
    permanent_commits = []
    for branch in PERMANENT:
        if branch not in scn.branches:
            continue
        for sha in scn.ancestors(branch):
            node = scn.commits.get(sha) or {}
            # Pre-existing history, the person's cut of the epic branch (rule 3) and a
            # merge of the integration target into a branch (rule 12) carry no content;
            # everything else on a permanent branch owes a merged PR.
            if node.get("origin") == "base" or node.get("cut") or node.get("sync"):
                continue
            if sha in covered_shas:
                continue
            permanent_commits.append(sha)

    def ok_direct_push(expected, obs):
        return obs["permanent_commits"] == sorted(expected.get("permanent_commits", [])), \
            ("finding" if obs["permanent_commits"] else "check")
    add("no-direct-push", {"permanent_commits": sorted(permanent_commits)}, ok_direct_push,
        "a commit reached a permanent branch without a merged PR carrying it")

    # --- production untouched -------------------------------------------------------------------
    master = scn.branches.get("master")
    add("production-untouched", {"master_sha": master,
                                 "master_moved": master != scn.baseline_master},
        lambda e, o: (bool(e) and o["master_moved"] == e.get("master_moved"), "check"),
        "master moved: nothing in this epic may reach production outside the protected "
        "promotion path (#1584)")

    # --- no competing orchestrator ------------------------------------------------------------------
    schedulers = sorted(f for f in scn.added_files if SCHEDULER_FILE_RE.search(f))
    add("no-competing-orchestrator", {"scheduler_files": schedulers},
        lambda e, o: (o["scheduler_files"] == sorted(e.get("scheduler_files", [])), "check"),
        "the integration grew a scheduler of its own instead of extending AO and the "
        "existing eligibility screen")
    return checks


# -------------------------------------------------------------------------- reporting


def build_report(scn, checks):
    return {"schema": SCHEMA, "scenario": scn.name, "repo": scn.repo,
            "epic": scn.epic.get("number"),
            "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": "dry-run", "writes": [],
            "counts": {"branches": len(scn.branches), "pulls": len(scn.pulls),
                       "issues": len(scn.issues), "commits": len(scn.commits)},
            "commands_run": len(scn.commands), "commands": scn.commands,
            "checks": [c.as_dict() for c in checks],
            "ok": all(c.ok for c in checks)}


def render_human(report):
    lines = ["epic integration dry run: %s (epic #%s, repo %s)"
             % (report["scenario"], report["epic"], report["repo"]),
             "  world: %(branches)d branches, %(pulls)d PRs, %(issues)d issues, "
             "%(commits)d commits; %(commands_run)d reads journalled"
             % dict(report["counts"], commands_run=report["commands_run"]), ""]
    width = max((len(c["id"]) for c in report["checks"]), default=0)
    for c in report["checks"]:
        mark = "FAIL" if not c["ok"] else ("find" if c["severity"] == "finding" else "PASS")
        lines.append("  %-4s  %s%s" % (mark, c["id"].ljust(width),
                                       "  " + c["detail"] if not c["ok"] else ""))
    failed = [c["id"] for c in report["checks"] if not c["ok"]]
    lines += ["", "%d/%d checks observed what the contract expects"
              % (len(report["checks"]) - len(failed), len(report["checks"]))]
    if failed:
        lines.append("not as expected: " + ", ".join(failed))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="epic_integration_dryrun", description=__doc__.splitlines()[0],
        epilog="exit 0 every check observed what the scenario expects, 1 a check did not, "
               "2 the dry run could not run (a refusal, not a result)")
    parser.add_argument("--scenario", help="the scenario file to replay")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--evidence-out", metavar="FILE",
                        help="also write the report here (the only file this tool writes)")
    parser.add_argument("--fail-on-findings", action="store_true",
                        help="also exit 1 when a passing check carries severity finding")
    parser.add_argument("--list-checks", action="store_true",
                        help="print the check ids the contract is validated by")
    args = parser.parse_args(argv)

    if args.list_checks:
        print("\n".join(CHECK_IDS))
        return 0
    if not args.scenario:
        parser.error("--scenario is required (or --list-checks)")

    try:
        scn = load_scenario(args.scenario)
        checks = run_scenario(scn)
    except HarnessError as e:
        print("epic_integration_dryrun: cannot run the dry run: %s" % e, file=sys.stderr)
        return 2

    report = build_report(scn, checks)
    if args.evidence_out:
        directory = os.path.dirname(os.path.abspath(args.evidence_out))
        os.makedirs(directory, exist_ok=True)
        with open(args.evidence_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")

    print(json.dumps(report, indent=2, sort_keys=True) if args.json
          else render_human(report))
    if not report["ok"]:
        return 1
    if args.fail_on_findings and any(c.severity == "finding" for c in checks):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
