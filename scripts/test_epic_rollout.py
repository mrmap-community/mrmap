#!/usr/bin/env python3
"""Offline regression checks for scripts/epic_rollout.py (issue #1594, epic #1588).

Run from the repository root: python3 scripts/test_epic_rollout.py
Exit code 0 means every check passed.

Two things are checked here, and they are different in kind.

The first is the planner's behaviour: which decision row an epic resolves to, which target
its children owe, and who is named as the actor of every owed action. The checks that matter
are the refusals to act - an agent may never create a branch, delete one, retarget a PR or
merge an integration PR (rule 15), so an action that escapes without a `person` in front of
it is the bug this suite exists to catch.

The second is the committed state the rollout depends on: the policy file's dates are
ordered and its exceptions dated, and the four workflows `The CI contract`_ names really
carry the epic namespace in their pull_request trigger. Those read the real repository, so
this suite goes red when the rollout is claimed complete while a child PR would still get
no checks - the one defect that would make an epic branch worse than the status quo.

Every gh and git call of the first part is answered by the fixture below, so it needs no
`gh`, no token and no network, and cannot touch a real repository or a real branch.
"""
import importlib.machinery
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_loader(
    "epic_rollout", importlib.machinery.SourceFileLoader(
        "epic_rollout", os.path.join(HERE, "epic_rollout.py")))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
wip_spec = importlib.util.spec_from_loader(
    "wip", importlib.machinery.SourceFileLoader("wip", os.path.join(HERE, "wip")))
wip = importlib.util.module_from_spec(wip_spec)
wip_spec.loader.exec_module(wip)

POLICY = os.path.join(HERE, "epic_rollout.json")
TODAY = date(2026, 11, 24)


class Fixture:
    """The whole GitHub and git state one plan run observes."""

    def __init__(self):
        self.repo = "o/r"
        self.epics = []          # [{number,title,body,state,children:[{number,state}]}]
        self.pulls = []          # [{number,title,base,head,body,closes}]
        self.branches = []       # origin branch names
        self.claims = {}         # issue -> claim state (wip/waiting/done)
        self.local_trees = []    # local worktree branch names
        self.fail = []           # command substrings that must fail
        self.partial_epics = False
        self.partial_pulls = False
        self.partial_children = False
        self.calls = []

    # ---- state building -----------------------------------------------------
    def epic(self, number, slug=None, children=(), state="OPEN", title=None, labels=("Epic",)):
        body = "slug: %s\n\n## Objective\n" % slug if slug else "## Objective\n"
        self.epics.append({"number": number, "title": title or "epic %d" % number,
                           "body": body, "state": state, "labels": list(labels),
                           "children": [{"number": c, "state": "OPEN", "stateReason": None}
                                        if isinstance(c, int) else dict(c) for c in children]})
        return self

    def child(self, number, state="OPEN"):
        return {"number": number, "state": state, "stateReason": None}

    def pr(self, number, base="develop", head="feature/x", body="", closes=(), title="pr"):
        self.pulls.append({"number": number, "title": title, "base": base, "head": head,
                           "body": body, "closes": list(closes), "author": "dev"})
        return self

    def branch(self, *names):
        self.branches.extend(names)
        return self

    def claim(self, n, state="wip"):
        self.claims[n] = state
        return self

    # ---- the injected runner ------------------------------------------------
    def runner(self, argv):
        cmd = " ".join(argv)
        self.calls.append(cmd)
        for bad in self.fail:
            if bad in cmd:
                err = m.CommandError("simulated: %s" % cmd)
                err.exit_code = 4
                raise err
        if cmd.startswith("gh repo view"):
            return json.dumps({"nameWithOwner": self.repo})
        if cmd.startswith("gh api graphql"):
            return self.graphql(cmd)
        if cmd.startswith("gh issue list"):
            return json.dumps([{"number": n, "title": "wip %d" % n}
                               for n, s in self.claims.items() if s in ("wip", "waiting")])
        if "/comments" in cmd:
            return json.dumps(self.comments(int(re.search(r"/issues/(\d+)/comments", cmd).group(1))))
        if cmd.startswith("git worktree"):
            return "".join("worktree /wt/%s\nbranch refs/heads/%s\n\n" % (b, b)
                           for b in self.local_trees)
        if cmd.startswith("git ls-remote"):
            return "".join("%s\trefs/heads/%s\n" % ("b" * 40, b) for b in self.branches)
        raise AssertionError("the planner ran a command the fixture does not know: " + cmd)

    def comments(self, n):
        state = self.claims.get(n)
        if not state:
            return []
        p = {"v": 1, "client": "other:wt", "issue": n, "branch": "feature/issue-%d-x" % n,
             "worktree": "/wt/x", "state": state, "since": "2026-11-01T00:00:00Z",
             "heartbeat": "2026-11-01T00:00:00Z", "released": None}
        return [{"id": 1, "body": wip.claim_body(p)}]

    def graphql(self, query):
        # Answered by shape, so an unbalanced query would pass here and die on the live API.
        if query.count("{") != query.count("}"):
            raise AssertionError("the planner sent an unbalanced GraphQL query: " + query)
        if "label:" in query and "subIssues" in query:
            nodes = [{"__typename": "Issue", "number": e["number"], "title": e["title"],
                      "state": e["state"], "body": e["body"],
                      "labels": {"totalCount": len(e["labels"]), "pageInfo": {"hasNextPage": False},
                                 "nodes": [{"name": lab} for lab in e["labels"]]},
                      "subIssues": {"totalCount": len(e["children"]),
                                    "pageInfo": {"hasNextPage": self.partial_children},
                                    "nodes": e["children"]}}
                     for e in self.epics if e["state"] == "OPEN"]
            counted = len(nodes) + (5 if self.partial_epics else 0)
            return json.dumps({"data": {"search": {"issueCount": counted,
                                                   "pageInfo": {"hasNextPage": self.partial_epics},
                                                   "nodes": nodes}}})
        if "is:pr" in query:
            nodes = [{"__typename": "PullRequest", "number": p["number"], "title": p["title"],
                      "baseRefName": p["base"], "headRefName": p["head"], "body": p["body"],
                      "author": {"login": p["author"]},
                      "closingIssuesReferences": {"totalCount": len(p["closes"]),
                                                  "pageInfo": {"hasNextPage": False},
                                                  "nodes": [{"number": c} for c in p["closes"]]}}
                     for p in self.pulls]
            counted = len(nodes) + (5 if self.partial_pulls else 0)
            return json.dumps({"data": {"search": {"issueCount": counted,
                                                   "pageInfo": {"hasNextPage": self.partial_pulls},
                                                   "nodes": nodes}}})
        raise AssertionError("the planner sent a GraphQL query the fixture does not know: " + query)


# ---------- running the tool ------------------------------------------------

def plan(fixture, *argv, today=TODAY, policy=POLICY, repo_root=ROOT):
    """Run main() against the fixture -> (exit code, stdout)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = m.main(["--json", "--policy", policy, *argv], runner=fixture.runner,
                      repo_root=repo_root, today=today)
    return code, out.getvalue()


def result(fixture, *argv, **kw):
    code, out = plan(fixture, *argv, **kw)
    assert code != 2, "the planner failed closed: %s" % out
    return json.loads(out)


def human(fixture, *argv, **kw):
    """main() with the human renderer -> (exit code, stdout)."""
    out = io.StringIO()
    argv = [a for a in argv if a != "--json"]
    with redirect_stdout(out):
        code = m.main(["--policy", kw.pop("policy", POLICY), *argv], runner=fixture.runner,
                      repo_root=kw.pop("repo_root", ROOT), today=kw.pop("today", TODAY))
    assert not kw, "unsupported kwargs: %s" % kw
    return code, out.getvalue()


WORKFLOW_FLOWS = """name: w
on:
  pull_request:
    branches: [%s]
    types: [opened, synchronize, reopened]
  schedule:
    - cron: '0 16 * * *'
jobs:
  qa:
    runs-on: ubuntu-latest
"""

WORKFLOW_BLOCKS = """name: w
on:
  pull_request:
    branches:
%s
    types: [opened]
jobs:
  qa:
    runs-on: ubuntu-latest
"""


def workflow_root(patterns, style="flow"):
    """A throwaway repository root whose one workflow triggers on `patterns`.

    Used to hold the CI-coverage guard to its own promise: a trigger must carry a wildcard
    over the epic namespace, not something that merely mentions the word `epic`. It carries
    the contract page the policy cites too, because the policy is validated against this root
    and a root without it must (and does) fail closed.
    """
    root = tempfile.mkdtemp()
    workflows = os.path.join(root, ".github", "workflows")
    os.makedirs(workflows)
    contract = os.path.join(root, "docs", "source", "development")
    os.makedirs(contract)
    with open(os.path.join(contract, "epic-integration-contract.rst"), "w",
              encoding="utf-8") as fh:
        fh.write("Epic integration contract\n=========================\n")
    if style == "flow":
        body = WORKFLOW_FLOWS % ", ".join(patterns)
    else:
        body = WORKFLOW_BLOCKS % "".join("      - %s\n" % p for p in patterns)
    with open(os.path.join(workflows, "w.yml"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return root


def coverage_policy():
    """The committed policy with its CI coverage narrowed to the throwaway workflow."""
    path = os.path.join(tempfile.mkdtemp(), "policy.json")
    narrowed = dict(policy, rollout=dict(policy["rollout"],
                                         ci_coverage=[".github/workflows/w.yml"]))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(narrowed, fh)
    return path


def findings_of(res, token, epic=None):
    return [f for f in res["findings"] if f["token"] == token
            and (epic is None or f.get("epic") == epic)]


def get(obj, dotted, default=None):
    """Dotted lookup that yields default instead of KeyError: absence must FAIL, not abort."""
    for key in dotted.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj


def finding_of(res, token, epic=None):
    """The one finding carrying `token`, or None. Absence is a failed check, not a crash."""
    found = findings_of(res, token, epic)
    return found[0] if len(found) == 1 else None


def actions_of(res, kind, epic=None):
    return [a for a in res["actions"] if a["kind"] == kind
            and (epic is None or a.get("epic") == epic)]


def row_of(res, epic):
    for r in res["epics"]:
        if r["epic"] == epic:
            return r
    raise AssertionError("epic #%s is not in the plan: %s" % (epic, res["epics"]))


results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    # (detail,) so a tuple or list detail prints instead of colliding with % formatting.
    print("  %-4s %s%s" % ("ok" if ok else "FAIL", name, "" if ok else "  - %s" % (detail,)))
    return ok


# ---------- the committed rollout state --------------------------------------
print("the committed rollout state holds together")

policy = json.load(open(POLICY, encoding="utf-8"))

# 1. The contract page the policy cites is the real ADR, and it is listed in the toctree.
check("the policy cites the contract ADR that exists",
      os.path.exists(os.path.join(ROOT, policy["contract"])), policy["contract"])
index = open(os.path.join(ROOT, "docs", "source", "development", "index.rst"),
             encoding="utf-8").read()
check("the contract page is in the development toctree",
      "epic-integration-contract" in index)

# 2. The rollout is time-limited: advisory before strict, and both are real dates.
check("advisory_from precedes strict_from",
      policy["rollout"]["advisory_from"] <= policy["rollout"]["strict_from"],
      "%s / %s" % (policy["rollout"]["advisory_from"], policy["rollout"]["strict_from"]))

# 3. A legacy exception cannot become permanent: every one of them carries a reason, a
#    recording issue and an expiry not later than the strict date.
for entry in policy["legacy_exceptions"]:
    check("the legacy exception of epic #%s is explicit" % entry["epic"],
          bool((entry.get("reason") or "").strip()) and bool((entry.get("recorded_in") or "").strip()),
          entry)
    check("the legacy exception of epic #%s is time-limited" % entry["epic"],
          entry.get("expires") and entry["expires"] <= policy["rollout"]["strict_from"],
          entry.get("expires"))

# 4. The bootstrap exemption names the bootstrapping epic of the epic of this issue and
#    nothing else: a permanent bootstrap is the cycle rule 16 exists to avoid.
check("the bootstrap lists exactly the epic-integration epic",
      policy["bootstrap"]["epics"] == [1588], policy["bootstrap"]["epics"])
check("the bootstrap ends with the integration PR",
      policy["bootstrap"].get("until_integration_pr_merged") is True)

# 5. `The CI contract`_ is delivered: every named workflow's pull_request trigger really
#    carries the epic namespace. This is the hard prerequisite of the rollout - a child PR
#    that merges into an epic branch unchecked is worse than no epic branch at all.
for workflow in policy["rollout"]["ci_coverage"]:
    covered = m.ci_coverage(ROOT, policy)[workflow]
    check("%s runs the required checks for a child PR" % workflow, covered,
          "the pull_request trigger carries no epic/** pattern")

# 6. A child PR is not queued while the integration PR is: the policy records the decision.
check("the merge-queue decision for epic branches is recorded",
      "queue" in (policy.get("branch_lifecycle") or {}).get("merge_queue", "").lower())

# 7. The permanent-branch rules of AGENTS.md are unweakened by the rollout text, and the new
#    rules say who creates the branch. Whitespace and markdown emphasis are normalised away
#    so the checks bind the statement, not the line wrapping that wrote it.
agents = open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8").read()
for phrase in ("Never directly push to `master` or `develop`.",
               "Never delete, rename or force-push permanent branches.",
               "Never delete permanent branches during PR cleanup."):
    check("AGENTS.md still states: %s" % phrase, phrase in agents)


def flatten(text):
    return " ".join(text.replace("**", "").split())


flat_agents = flatten(agents)
check("AGENTS.md states the epic branch rule with its contract source",
      "epic/<slug>" in flat_agents and "epic-integration-contract.rst" in flat_agents)
check("AGENTS.md says a person creates the epic branch from current develop",
      "created by a person from the tip of `origin/develop`" in flat_agents)
check("AGENTS.md keeps retargeting and branch deletion with people",
      "are human acts" in flat_agents and "never performs one" in flat_agents)
check("AGENTS.md ties the exemption to the policy file and a date",
      "scripts/epic_rollout.json" in flat_agents and "expiry" in flat_agents)

# 8. The skill follows AGENTS.md instead of contradicting it (the hierarchy rule of
#    docs/development/agent-skills.md: a skill that contradicts AGENTS.md is a bug).
skill = flatten(open(os.path.join(ROOT, ".opencode", "skills", "mrmap-github-workflow",
                                  "SKILL.md"), encoding="utf-8").read())
check("the workflow skill names the epic branch contract",
      "epic-integration-contract" in skill and "epic_rollout" in skill)
check("the skill keeps branch creation with a person",
      "epic branch is cut by a person from the tip of `origin/develop`" in skill)
check("the skill lists the epic base rows as anti-patterns",
      "R2/R5" in skill and "person-owned acts" in skill)


# ---------- the planner: rows and targets ------------------------------------
print("\nthe planner resolves the decision table")

f = Fixture().epic(10, slug="alpha", children=[11, 12])
res = result(f)
r = row_of(res, 10)
check("an open epic with a slug and no branch resolves to R2 awaiting the branch",
      r["row"] == "R2-pending-branch" and r["target"] == "epic/alpha", r)
check("the owed branch is cut by a person, from current develop",
      actions_of(res, "create-epic-branch", 10)
      and actions_of(res, "create-epic-branch", 10)[0]["actor"] == "person"
      and "origin/develop" in actions_of(res, "create-epic-branch", 10)[0]["detail"])
check("the branch protection decision is owed too",
      actions_of(res, "protect-epic-branch", 10))

f = Fixture().epic(10, slug="alpha", children=[11, 12]).branch("epic/alpha")
res = result(f)
r = row_of(res, 10)
check("with the branch standing the epic is R2 and its target is the epic branch",
      r["row"] == "R2" and r["target"] == "epic/alpha", r)
check("children base on the epic branch only",
      actions_of(res, "children-base-on-epic-branch", 10)
      and "epic/alpha" in actions_of(res, "children-base-on-epic-branch", 10)[0]["detail"])

f = Fixture().epic(10, slug=None, children=[11])
res = result(f)
r = row_of(res, 10)
check("an epic without a slug is R3 on develop (bootstrap row)",
      r["row"] == "R3" and r["target"] == "develop", r)
check("the slug is owed by a person, not invented by an agent",
      actions_of(res, "declare-slug", 10)
      and actions_of(res, "declare-slug", 10)[0]["actor"] == "person")

f = Fixture().epic(1588, slug="epic-integration", children=[1594])
res = result(f)
r = row_of(res, 1588)
check("the bootstrapping epic's own children stay on develop (rule 16)",
      r["row"] == "R3" and r["target"] == "develop", r)
check("no branch creation is owed for the bootstrap epic",
      not actions_of(res, "create-epic-branch", 1588))

f = Fixture().epic(1442, slug=None, children=[20])
res = result(f)
check("the recorded legacy exception keeps its epic on develop",
      row_of(res, 1442)["target"] == "develop", row_of(res, 1442))
check("an active exception is reported but never blocks",
      findings_of(res, "legacy-exception-active", 1442)
      and "legacy-exception-active" not in res["blocking"], res["blocking"])

f = Fixture().epic(1442, slug=None, children=[20])
res = result(f, today=date(2027, 1, 1))
check("the same exception has expired after its date and stops exempting",
      findings_of(res, "legacy-exception-expired", 1442)
      and "legacy-exception-expired" in res["blocking"], res["blocking"])

f = Fixture().epic(10, slug=None, children=[11])
f.epics[0]["body"] = "## Objective\n\nslug: buried\n"
res = result(f)
check("a slug declared off the first body line is not the branch identity (rule 1)",
      findings_of(res, "slug-not-first-line", 10) and row_of(res, 10)["row"] == "R3"
      and not actions_of(res, "create-epic-branch", 10))
check("the misplaced declaration is settled by a person",
      "person" in findings_of(res, "slug-not-first-line", 10)[0]["detail"])

f = Fixture().epic(10, slug="Bad Slug", children=[11])
res = result(f)
check("a slug outside the contract pattern blocks the rollout",
      findings_of(res, "slug-invalid", 10) and "slug-invalid" in res["blocking"])

f = Fixture().epic(10, slug="alpha", children=[11]).epic(12, slug="alpha", children=[13])
res = result(f)
check("two open epics sharing a slug block (rule 2)",
      findings_of(res, "slug-duplicate") and "slug-duplicate" in res["blocking"])

f = Fixture().branch("epic/ghost")
res = result(f)
check("an epic branch no open epic declares is reported for a person to settle (R10/R11)",
      findings_of(res, "orphan-epic-branch") and "orphan-epic-branch" in res["blocking"])
check("an agent is never the one to delete it",
      "person" in findings_of(res, "orphan-epic-branch")[0]["detail"])

f = Fixture().epic(1588, slug="epic-integration", children=[1594]).branch("epic/epic-integration")
res = result(f)
check("a bootstrap branch standing with no integration PR is an unfinished bootstrap",
      findings_of(res, "bootstrap-branch-without-integration-pr", 1588)
      and "bootstrap-branch-without-integration-pr" in res["blocking"])


# ---------- the planner: PR base rows ----------------------------------------
print("\nthe planner reads the PR base rows")

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(500, base="develop", head="feature/issue-11-x")
res = result(f)
check("a child PR based on develop is reported as the wrong base (R5)",
      findings_of(res, "child-pr-wrong-base", 10))
check("a wrong base is a plan item and not a failure, because no agent may fix it",
      "child-pr-wrong-base" not in res["blocking"], res["blocking"])
check("the retarget is owed by a person and never done by an agent",
      "person" in findings_of(res, "child-pr-wrong-base", 10)[0]["detail"]
      and "rewritten" in findings_of(res, "child-pr-wrong-base", 10)[0]["detail"])

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(500, base="develop", head="feature/issue-11-x").claim(11)
res = result(f)
check("a wrong base under a live claim says the retarget waits for the session",
      "claim" in findings_of(res, "child-pr-wrong-base", 10)[0]["detail"])

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(501, base="epic/alpha", head="feature/issue-11-x")
res = result(f)
check("a child PR based on the epic branch is lawful and owed a human review",
      not findings_of(res, "child-pr-wrong-base", 10)
      and actions_of(res, "review-child-pr", 10)
      and actions_of(res, "review-child-pr", 10)[0]["actor"] == "person")
check("the R12 remedy is a merge of the epic head, never a rebase",
      "never a rebase" in actions_of(res, "review-child-pr", 10)[0]["detail"])

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(502, base="develop", head="epic/alpha")
res = result(f)
check("the integration PR of an epic branch is owed a human merge and branch cleanup",
      actions_of(res, "human-merge-integration-pr", 10)
      and actions_of(res, "delete-epic-branch-after-merge", 10)
      and all(a["actor"] == "person" for a in actions_of(res, "human-merge-integration-pr", 10)))

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(503, base="master", head="epic/alpha")
res = result(f)
check("an epic branch targeting anything but develop is refused (R6)",
      findings_of(res, "epic-branch-not-targeting-develop", 10)
      and "epic-branch-not-targeting-develop" in res["blocking"])

f = Fixture().epic(10, slug="alpha", children=[11, 12]).branch("epic/alpha") \
      .pr(504, base="epic/alpha", head="feature/issue-11-x") \
      .pr(505, base="develop", head="housekeeping/issue-12-y")
res = result(f)
check("only the PR that represents the epic is judged on its base",
      len(findings_of(res, "child-pr-wrong-base", 10)) == 1
      and findings_of(res, "child-pr-wrong-base", 10)[0]["pr"] == 505)

f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(506, base="epic/other", head="feature/issue-11-x")
res = result(f)
check("a child PR based on another epic's branch is a wrong base (R5)",
      findings_of(res, "child-pr-wrong-base", 10))


# ---------- the planner: safety properties -----------------------------------
print("\nthe planner fails closed and never claims an action of its own")

f = Fixture().epic(10, slug="alpha", children=[11])
f.fail.append("graphql")
code, out = plan(f)
check("a failing GitHub read fails closed with no plan",
      code == 2 and json.loads(out)["status"] == "error", out[:120])

f = Fixture().epic(10, slug="alpha", children=[11])
f.partial_epics = True
code, out = plan(f)
check("a truncated epic inventory fails closed rather than plan on it",
      code == 2, out[:120])

f = Fixture().epic(10, slug="alpha", children=[11]).pr(500, base="develop", head="feature/x")
f.partial_pulls = True
code, out = plan(f)
check("a truncated PR inventory fails closed", code == 2, out[:120])

f = Fixture().epic(10, slug="alpha", children=[11])
f.partial_children = True
code, out = plan(f)
check("a truncated sub-issue listing fails closed", code == 2, out[:120])

f = Fixture().epic(10, slug="alpha", children=[11])
f.fail.append("ls-remote")
code, out = plan(f)
check("a branch list that cannot be read fails closed instead of planning a cut",
      code == 2, out[:120])

# The rule-15 invariant, stated as a property over every scenario above: nothing in a plan
# is owed by an agent that changes a branch, a PR base, a merge or a protection.
f = Fixture().epic(10, slug="alpha", children=[11, 12]).branch("epic/alpha") \
      .epic(1588, slug="epic-integration", children=[1594]) \
      .pr(500, base="develop", head="feature/issue-11-x") \
      .pr(501, base="epic/alpha", head="feature/issue-12-x") \
      .pr(502, base="develop", head="epic/alpha") \
      .branch("epic/ghost").claim(12)
res = result(f)
FORBIDDEN = ("create", "delete", "retarget", "merge", "protect", "rebase", "force",
             "approve", "label", "close", "push")
agent_overreach = [a for a in res["actions"] if a["actor"] == "agent"
                   and any(w in a["kind"] for w in FORBIDDEN)]
check("no agent-owned action creates, deletes, retargets, merges or protects a branch",
      not agent_overreach, agent_overreach)
check("every action names exactly one lawful actor",
      all(a["actor"] in ("person", "agent") for a in res["actions"]),
      {a["actor"] for a in res["actions"]})
check("the plan itself writes nothing: no gh write call is made",
      not [c for c in f.calls if re.search(r"\b(gh) (issue|pr|api) (create|edit|comment|merge)", c)],
      f.calls)

# The split the tool's docstring promises: a wrong PR base is a plan item that never fails
# the run, while a rollout defect nobody else reports fails it in strict mode.
f = Fixture().epic(10, slug="alpha", children=[11]).branch("epic/alpha") \
      .pr(500, base="develop", head="feature/issue-11-x")
code_advisory, out_advisory = plan(f, today=date(2026, 12, 1))
code_strict, out_strict = plan(f, today=date(2027, 1, 1))
check("a wrong base is reported in both halves of the rollout and blocks in neither",
      findings_of(json.loads(out_advisory), "child-pr-wrong-base", 10)
      and "child-pr-wrong-base" not in json.loads(out_strict)["blocking"]
      and code_advisory == 0 and code_strict == 0, (code_advisory, code_strict))

f = Fixture().branch("epic/ghost")
code_advisory, out_advisory = plan(f, today=date(2026, 12, 1))
code_strict, out_strict = plan(f, today=date(2027, 1, 1))
check("an orphan epic branch blocks in both halves, because only a person can settle it",
      "orphan-epic-branch" in json.loads(out_advisory)["blocking"]
      and "orphan-epic-branch" in json.loads(out_strict)["blocking"])
check("strict mode fails where advisory reports the same defect without failing",
      code_advisory == 0 and code_strict == 1, (code_advisory, code_strict))

# The real repository must plan clean in advisory mode today: the shipped policy and the
# shipped workflows are consistent with each other.
real = Fixture().epic(10, slug="sample", children=[11])
code, out = plan(real)
check("the planner runs clean against the committed policy", code == 0, out[:200])

# A policy that contradicts itself is refused rather than half-read.
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
    bad = dict(policy)
    bad["legacy_exceptions"] = [{"epic": 1442, "reason": "  ", "recorded_in": "#1590",
                                "expires": "2026-12-15"}]
    json.dump(bad, fh)
    badpath = fh.name
try:
    code, out = plan(Fixture().epic(10, slug="alpha", children=[11]), policy=badpath)
    check("an exception without a reason is refused: it is not an explicit exception",
          code == 2, out[:120])
finally:
    os.unlink(badpath)

with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
    bad = dict(policy)
    bad["rollout"] = dict(policy["rollout"], ci_coverage=[])
    json.dump(bad, fh)
    badpath = fh.name
try:
    code, out = plan(Fixture().epic(10, slug="alpha", children=[11]), policy=badpath)
    check("a policy with no CI coverage list is refused", code == 2, out[:120])
finally:
    os.unlink(badpath)

# ---------- what `--epic` may and may not scope --------------------------------
# `--epic` is what AGENTS.md and the skill tell an agent to run before an epic child's PR, so
# the scoped plan is the one that gets believed. It may scope which rows are rendered; it may
# not scope what the repository-wide checks see, or a scoped plan both invents defects about
# other epics and hides the rule 2 collision that would land the agent's work on another
# epic's integration target.

two_epics = (Fixture().epic(10, slug="alpha", children=[11])
             .epic(12, slug="beta", children=[13])
             .branch("epic/alpha", "epic/beta"))

res = result(two_epics)
check("the unscoped plan sees no orphan among two healthy epic branches",
      not findings_of(res, "orphan-epic-branch"), res["blocking"])

res = result(two_epics, "--epic", "10")
check("--epic renders only the epic asked for",
      [r["epic"] for r in res["epics"]] == [10], [r["epic"] for r in res["epics"]])
check("--epic does not invent an orphan out of another epic's healthy branch",
      not findings_of(res, "orphan-epic-branch"), res["blocking"])
check("the inventory stays the repository's whole set under --epic",
      get(res, "inventory.open_epics") == 2, res.get("inventory"))
check("the scope of the rendered rows is named separately, not passed off as the inventory",
      res.get("scope") == {"epic": 10, "rows_rendered": 1}, res.get("scope"))

# The mirror case: the collision is with an epic outside the scope. Scoped away, the two epics
# were compared against themselves and nothing was reported at all.
twin = (Fixture().epic(10, slug="alpha", children=[11])
        .epic(12, slug="alpha", children=[13])
        .epic(14, slug="gamma", children=[15])
        .branch("epic/alpha", "epic/gamma"))
res = result(twin, "--epic", "10")
check("--epic still reports a slug shared with an epic outside the scope",
      findings_of(res, "slug-duplicate"), [f["token"] for f in res["findings"]])
check("a shared slug stays blocking under --epic",
      "slug-duplicate" in res["blocking"], res["blocking"])
dup = finding_of(res, "slug-duplicate")
check("the finding names both epics so the scoped reader knows which is whose",
      dup and "#10" in dup["detail"] and "#12" in dup["detail"], dup)
check("the epic in scope of a duplicate is attributed to it",
      dup and dup["epic"] == 10, dup)

res = result(twin, "--epic", "14")
other = finding_of(res, "slug-duplicate")
check("a collision between two other epics is not attributed to the epic in scope",
      other and other["epic"] is None
      and "concerns #10 and #12, not the epic in scope" in other["detail"], other)

res = result(two_epics, "--epic", "10")
check("--epic does not report a healthy branch of another epic as an orphan",
      not findings_of(res, "orphan-epic-branch"), res["blocking"])

ghosted = (Fixture().epic(10, slug="alpha", children=[11])
           .epic(12, slug="beta", children=[13])
           .branch("epic/alpha", "epic/beta", "epic/gone"))
res = result(ghosted, "--epic", "10")
orphan = finding_of(res, "orphan-epic-branch")
check("a genuinely orphaned epic branch is still reported under --epic",
      orphan and "epic/gone" in orphan["detail"], res["blocking"])
check("an orphan belonging to no epic is honestly marked as not about the one in scope",
      orphan and orphan["epic"] is None and "not the epic in scope" in orphan["detail"],
      orphan)

code, out = plan(Fixture().epic(10, slug="alpha", children=[11]), "--epic", "99")
check("--epic on a number that is not an open epic fails closed instead of planning nothing",
      code == 2 and "not an open" in out, out[:160])

# ---------- what counts as epic coverage in a workflow trigger -----------------
# The guard exists because the contract calls an unchecked child PR the defect most likely to
# sink the design. A pattern that merely contains the word `epic` must not satisfy it.
WEEKLY = ".github/workflows/w.yml"
cov_path = coverage_policy()
cov = json.load(open(cov_path))
for patterns, style, expected, what in [
        (["master", "develop", "'epic/**'"], "flow", True, "quoted wildcard"),
        (["master", "develop", "epic/**"], "flow", True, "bare wildcard"),
        (["master", "develop", "epic/*"], "flow", True, "single-star wildcard"),
        (["master", "develop", "epic"], "flow", False, "the literal branch `epic`"),
        (["master", "develop", "epic*"], "flow", False, "a prefix glob that is not the namespace"),
        (["master", "develop"], "flow", False, "no epic pattern at all"),
        (["master", "develop", "'epic/**'"], "block", True, "the block-list wildcard"),
        (["master", "develop", "epic"], "block", False, "the block-list literal `epic`")]:
    covered = m.ci_coverage(workflow_root(patterns, style), cov)[WEEKLY]
    check("%s in the pull_request trigger counts as coverage: %s" % (what, expected),
          covered is expected, (patterns, style))

f = Fixture().epic(10, slug="alpha", children=[11])
code, out = plan(f, "--mode", "strict", repo_root=workflow_root(["master", "develop", "epic"]),
                 policy=cov_path)
check("the literal-`epic` trigger fails the run in strict mode, where it used to pass",
      code == 1 and "ci-coverage-missing" in get(json.loads(out), "blocking") or [], out[:200])
code, out = plan(f, "--mode", "strict",
                 repo_root=workflow_root(["master", "develop", "epic/**"]), policy=cov_path)
check("a real wildcard still passes, so the guard did not just turn permanently red",
      code == 0 and "ci-coverage-missing" not in json.loads(out)["blocking"], out[:200])

# ---------- the reported source of the rollout date ---------------------------
# A report that tells a person when the rule starts binding must not claim an override that
# nobody set, and must name the override when one is set.
env = policy["rollout"]["strict_from_env"]
saved = os.environ.pop(env, None)
try:
    _, out = human(Fixture().epic(10, slug="alpha", children=[11]), "--mode", "strict")
    header = [line for line in out.splitlines() if "strict from" in line]
    check("--mode strict does not claim an environment override that is not set",
          "overridden" not in out and "environment %s" % env not in out, header)
    check("with no override the committed policy's date is the one printed",
          policy["rollout"]["strict_from"] in "".join(header), header)

    os.environ[env] = "2026-11-01"
    _, out = human(Fixture().epic(10, slug="alpha", children=[11]))
    check("an actual environment override is named as the source of the date",
          "environment %s" % env in out,
          [line for line in out.splitlines() if "strict from" in line])
    res = json.loads(plan(Fixture().epic(10, slug="alpha", children=[11]))[1])
    check("the JSON reports the same source the human renderer prints",
          res["policy"]["strict_from_source"] == "environment %s" % env
          and res["policy"]["strict_from"] == "2026-11-01", res["policy"])
finally:
    os.environ.pop(env, None)
    if saved is not None:
        os.environ[env] = saved

_, out = human(Fixture().epic(10, slug="alpha", children=[11]), "--epic", "10")
check("the scoped run says so on the inventory line instead of letting a slice read complete",
      "planning epic #10" in out and "repository's whole set" in out, out.splitlines()[0])

# ---------- where the policy's repo-relative paths are resolved ----------------
# The contract page and the named workflows are repository paths, so they have to be resolved
# against the repository the plan is about. Resolving them against the process's working
# directory instead made the tool answer only when invoked from the repository root, and made
# a caller that passed its own repo_root get an unrelated "not in the repository" error.
empty = tempfile.mkdtemp()
try:
    m.load_policy(POLICY, repo_root=empty)
    check("a repository root without the cited contract page is refused", False,
          "load_policy accepted a root that has no contract page")
except m.PolicyError as e:
    check("a repository root without the cited contract page is refused",
          "contract" in str(e), str(e))
check("the same policy loads against the real repository root",
      m.load_policy(POLICY, repo_root=ROOT)["branch_prefix"] == "epic/")
saved_cwd = os.getcwd()
os.chdir(empty)
try:
    # repo_root=None lets main() derive it from the file's own location, so nothing here can
    # be satisfied by the working directory the suite happens to run in.
    _, out = human(Fixture().epic(10, slug="alpha", children=[11]), repo_root=None)
finally:
    os.chdir(saved_cwd)
check("the plan answers the same from any working directory, not only the repository root",
      out.splitlines()[0].startswith("repo o/r"), out.splitlines()[0])

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
