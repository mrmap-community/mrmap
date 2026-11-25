#!/usr/bin/env python3
"""Offline checks for scripts/epic_integration_dryrun.py (issue #1595, epic #1588).

Runs without docker, without network, without `gh` and without git: the engine is
driven over generated scenario files, and the acceptance lines of the issue decide
what is asserted. The checks that matter are the ones where the world is WRONG on
purpose - a child PR on develop, a blocker closed but never on develop, a migration
slot two children claim, an agent that merged or retargeted its own work, a
documentation job in the everyday path - each must be SEEN, and the happy world must
be green without any of them.

Two refusals are asserted too, because they are the difference between a validator
and a rubber stamp: a scenario with no expectation for a check is refused (a check
nobody stated proves nothing), and the engine's read allowlist refuses a write.

Run from the repository root: `python3 scripts/test_epic_integration_dryrun.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import importlib.util
import io
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE / "epic_integration_dryrun.py"
TMP = Path(tempfile.mkdtemp(prefix="test_epic_integration_dryrun."))

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def module():
    spec = importlib.util.spec_from_file_location("epic_integration_dryrun", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = module()

# ------------------------------------------------------------------ the happy world
#
# Epic #1588 (slug `epic-integration`), two approved children, the epic branch cut
# from develop, both children merged into it, an external dependency merged into
# develop and reachable from the epic head, and exactly one human-approved
# integration PR. Commits are hex shas; `origin: base` marks the pre-existing
# history so the direct-push check does not report it as a push.

A = "a" * 40                       # pre-existing history
DEP = "2" * 40                     # dependency PR merge, develop's tip at the cut
EPIC_CUT = "3" * 40                # the person's cut of the epic branch (rule 3)
C1, M1 = "c" * 40, "d" * 40        # child 1591 work, its merge into the epic
C2, M2 = "f" * 40, "1" * 40        # child 1593 work, its merge into the epic
EPIC_HEAD = "4" * 40               # the epic after merging develop into itself (R8)
INTEGRATION = "5" * 40             # the integration merge commit on develop

REQUIRED = ["classify", "codeql-required", "frontend-tests", "repo-tooling", "unit-tests"]
PR_PATH = ["codeql", "pr-classification", "qa", "script-tests"]   # the contract's four
EPIC_BRANCH = "epic/epic-integration"


def happy(second=True):
    """The validated world; `second=False` is the same epic before child #1593 started."""
    scn = {
        "schema": M.SCENARIO_SCHEMA,
        "name": "epic-1588-happy",
        "repo": "mrmap-community/mrmap",
        "agent_actor": "mrmap-agent-bot",
        "humans": ["jokiefer"],
        "baseline_master_sha": A,
        "epic": {"number": 1588, "title": "Epic: epic workflow",
                 "body": "slug: epic-integration\n\n## Acceptance\n- green",
                 "state": "OPEN"},
        "issues": {
            "1591": {"labels": ["agent: approved"], "approved_by": "jokiefer",
                     "starts_from": C1, "blocked_by": [1412],
                     "blocked_by_state": {"1412": "COMPLETED"}},
            "1593": {"labels": ["agent: approved"], "approved_by": "jokiefer",
                     "starts_from": C2},
        },
        "commits": {
            A: {"parents": [], "origin": "base"},
            DEP: {"parents": [A]},
            EPIC_CUT: {"parents": [DEP], "cut_from": "develop", "cut": True},
            C1: {"parents": [EPIC_CUT], "cut_from": EPIC_BRANCH},
            M1: {"parents": [EPIC_CUT, C1]},
            C2: {"parents": [M1], "cut_from": EPIC_BRANCH},
            M2: {"parents": [M1, C2]},
            EPIC_HEAD: {"parents": [M2, DEP], "sync": True},
            INTEGRATION: {"parents": [DEP, EPIC_HEAD]},
        },
        "branches": {"develop": INTEGRATION, "master": A, EPIC_BRANCH: EPIC_HEAD},
        "pulls": {
            "900": {"head": "housekeeping/issue-1412-legacy", "base": "develop",
                    "state": "merged", "merged_by": "jokiefer", "merge_sha": DEP,
                    "title": "fix: the legacy part (#1412)", "checks": REQUIRED,
                    "body": "Closes #1412"},
            "901": {"head": "feature/issue-1591-resolve", "base": EPIC_BRANCH,
                    "state": "merged", "merged_by": "jokiefer", "merge_sha": M1,
                    "title": "feat(epic-integration): resolve the target (#1591)",
                    "checks": REQUIRED, "body": "Closes #1591", "commits": [C1],
                    "migrations": [{"app": "registry", "name": "0002_target"}]},
            "902": {"head": "feature/issue-1593-readiness", "base": EPIC_BRANCH,
                    "state": "merged", "merged_by": "jokiefer", "merge_sha": M2,
                    "breaking": True,
                    "title": "feat(epic-integration)!: gate readiness (#1593)",
                    "checks": REQUIRED, "body": "Closes #1593", "commits": [C2],
                    "migrations": [{"app": "registry", "name": "0003_readiness"}]},
            "950": {"head": EPIC_BRANCH, "base": "develop", "state": "merged",
                    "merged_by": "jokiefer", "merge_sha": INTEGRATION,
                    "title": "feat(epic-integration)!: epic integration workflow (#1588)",
                    "body": "Integrates the epic as one entry.", "checks": REQUIRED},
        },
        "claims": {"1591": [{"state": "wip", "integration_target": EPIC_BRANCH}]},
        "workflows": {
            "qa": {"pull_request_branches": ["master", "develop", "epic/**"],
                   "jobs": ["unit-tests", "frontend-tests"]},
            "script-tests": {"pull_request_branches": ["master", "develop", "epic/**"],
                             "jobs": ["repo-tooling"]},
            "codeql": {"pull_request_branches": ["master", "develop", "epic/**"],
                       "jobs": ["codeql-required"]},
            "pr-classification": {"pull_request_branches": ["master", "develop", "epic/**"],
                                  "jobs": ["classify"]},
            "release-docs": {"pull_request_branches": [], "jobs": ["docs-build"]},
        },
        "expectations": {
            "child-selection": {"children": {
                "1591": {"base": EPIC_BRANCH, "reasons": []},
                "1593": {"base": EPIC_BRANCH, "reasons": []}}},
            "branch-creation": {"exists": True, "cut_from": "develop"},
            "child-starts-from-epic-head": {"children_off_head": []},
            "child-pr-checks": {"901": {"jobs": REQUIRED, "failing": []},
                                "902": {"jobs": REQUIRED, "failing": []}},
            "blocker-satisfied-by-ancestry": {"1591->1412": {
                "state": "COMPLETED", "merged": True, "on_epic": True, "on_develop": True}},
            "readiness": {"ready": True, "reasons": []},
            "integration-pr": {"count": 1, "base": "develop", "head": EPIC_BRANCH,
                               "merge": True, "merged_by": "jokiefer"},
            "wrong-base": {},
            "epic-head-base": {"pulls": []},
            "paused-or-claimed": {"1591": {"paused": False, "claimed": True}},
            "claim-carries-target": {"1591": {"target": EPIC_BRANCH}},
            "cancellation": {"epic_state": "OPEN", "no_open_prs_for": []},
            "migration-conflict": {"conflicts": [], "renumbered": []},
            "release-semantic-history": {"one_integration_entry": True,
                                         "child_titles_survive": True,
                                         "breaking_survives": True, "squashed": False},
            "rollback": {"reverted": False, "revert_merged_into": None,
                         "rewrote_history": False, "force_pushed": False},
            "recovery-after-deletion": {"branch_exists": True, "work_on_develop": True,
                                        "recreated": False},
            "no-docs-job": {"doc_jobs": ["docs-build"], "in_pr_path": []},
            "epic-ci-coverage": {"covered_by": ["codeql", "pr-classification", "qa",
                                                "script-tests"],
                                 "required": ["codeql", "pr-classification", "qa",
                                              "script-tests"]},
            "no-self-approval": {"offenders": []},
            "no-direct-push": {"permanent_commits": []},
            "production-untouched": {"master_moved": False},
            "no-competing-orchestrator": {"scheduler_files": []},
        },
    }
    if not second:
        # Nothing of the epic has reached a branch yet: the epic head is just the
        # person's cut with develop merged into it, and develop never left its tip.
        scn["issues"].pop("1593")
        scn["pulls"].pop("902")
        scn["pulls"].pop("950")
        scn["expectations"]["child-selection"]["children"].pop("1593")
        scn["expectations"]["child-pr-checks"].pop("902")
        scn["expectations"]["integration-pr"] = {}
        scn["commits"].pop(C2)
        scn["commits"].pop(M2)
        scn["commits"].pop(INTEGRATION)
        scn["commits"][EPIC_HEAD]["parents"] = [EPIC_CUT, DEP]
        scn["branches"]["develop"] = DEP
        scn["claims"] = {}
        scn["expectations"]["paused-or-claimed"] = {}
        scn["expectations"]["claim-carries-target"] = {}
        scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                          "work_on_develop": False,
                                                          "recreated": False}
        scn["expectations"]["release-semantic-history"] = {
            "one_integration_entry": True, "child_titles_survive": True,
            "breaking_survives": True, "squashed": False}
    return scn


def run(scn, *argv):
    """Replay one scenario -> (exit code, report or None, stderr text)."""
    path = TMP / ("%s.json" % scn.get("name", "scenario"))
    path.write_text(json.dumps(scn), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(["--scenario", str(path), "--json"] + list(argv))
    text = out.getvalue()
    try:
        return code, json.loads(text), err.getvalue()
    except ValueError:
        return code, None, err.getvalue()


def failed_ids(report):
    return sorted(c["id"] for c in report["checks"] if not c["ok"])


def observed(report, cid):
    return next(c["observed"] for c in report["checks"] if c["id"] == cid)


# 1. The happy world: the whole contract validated end to end, every check green.
code, report, err = run(happy())
check("the happy epic validates end to end",
      code == 0 and report and failed_ids(report) == [],
      "code=%s failed=%s err=%s" % (code, failed_ids(report) if report else None, err[:300]))
check("the happy world reports one check per acceptance line",
      report is not None and sorted(c["id"] for c in report["checks"])
      == sorted(M.CHECK_IDS),
      str(sorted(c["id"] for c in report["checks"]) if report else None))
check("every read the engine journalled is read-only",
      report is not None and all(
          cmd.split()[0] in ("git", "gh") and "push" not in cmd
          and not cmd.startswith("git checkout") for cmd in report["commands"]),
      str(report["commands"] if report else None))
check("the dry run writes nothing into the world it validates",
      report is not None and report["mode"] == "dry-run" and report["writes"] == [])

# 2. R2/R5: a child PR based on develop while the epic branch stands is a wrong base.
scn = happy()
scn["name"] = "child-on-develop"
scn["pulls"]["901"]["base"] = "develop"
scn["expectations"]["wrong-base"] = {"901": {"wrong": True, "by_agent": False}}
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["child-1591-not-merged-into-epic"]}
code, report, _ = run(scn)
check("a child PR based on develop is reported as a wrong base",
      code == 0 and "wrong-base" not in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "child-on-develop-unexpected"
scn["pulls"]["901"]["base"] = "develop"
code, report, _ = run(scn)
check("a child PR based on develop does not stay green when the scenario expects R2",
      code == 1 and "readiness" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 3. R4: an unapproved child gets no base at all.
scn = happy(second=False)
scn["name"] = "child-unapproved"
scn["issues"]["1591"]["labels"] = []
scn["pulls"]["901"]["state"] = "open"
scn["pulls"]["901"]["merge_sha"] = None
scn["expectations"]["child-selection"]["children"] = {
    "1591": {"base": None, "reasons": ["not-approved"]}}
scn["expectations"]["child-pr-checks"] = {"901": {"jobs": REQUIRED, "failing": []}}
scn["expectations"]["cancellation"] = {"epic_state": "OPEN", "no_open_prs_for": [901]}
code, report, _ = run(scn)
check("an unapproved child is not scheduled at all (R4)",
      code == 0 and observed(report, "child-selection")["1591"]["base"] is None
      and "not-approved" in observed(report, "child-selection")["1591"]["reasons"],
      "code=%s obs=%s failed=%s" % (code, observed(report, "child-selection"),
                                    failed_ids(report)))

# 4. A bot that applied `agent: approved` is an offender, whatever the scenario hopes.
scn = happy()
scn["name"] = "bot-approval"
scn["issues"]["1591"]["approved_by"] = "mrmap-agent-bot"
code, report, _ = run(scn)
check("an approval applied by the agent's own login fails the run",
      code == 1 and "no-self-approval" in failed_ids(report)
      and "approval:1591" in observed(report, "no-self-approval")["offenders"],
      "code=%s failed=%s" % (code, failed_ids(report)))

# 5. R7/R8: a dependency closed on GitHub but absent from develop does not count.
scn = happy()
scn["name"] = "dependency-not-on-develop"
# The dependency's PR merged, its commit exists, but develop never got it: exactly the
# failure mode the epic objective names ("closed, not available").
scn["branches"]["develop"] = A
scn["commits"][DEP] = {"parents": []}
scn["commits"][EPIC_CUT] = {"parents": [A], "cut_from": "develop", "cut": True}
scn["commits"][EPIC_HEAD] = {"parents": [M2, DEP], "sync": True}
del scn["pulls"]["950"]
scn["expectations"]["blocker-satisfied-by-ancestry"]["1591->1412"] = {
    "state": "COMPLETED", "merged": True, "on_epic": True, "on_develop": False}
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["dependency-1412-not-in-develop"]}
scn["expectations"]["integration-pr"] = {}
scn["expectations"]["release-semantic-history"] = {"one_integration_entry": True,
                                                  "child_titles_survive": True,
                                                  "breaking_survives": True,
                                                  "squashed": False}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
code, report, _ = run(scn)
check("a dependency closed but not on develop refuses readiness (R8)",
      code == 0 and observed(report, "readiness")["ready"] is False
      and observed(report, "readiness")["reasons"] == ["dependency-1412-not-in-develop"],
      "code=%s obs=%s failed=%s" % (code, observed(report, "readiness") if report else None,
                                    failed_ids(report) if report else None))

# 5b. A dependency merged only into another private epic branch is not available either.
scn = happy()
scn["name"] = "dependency-in-other-epic"
other = "epic/other"
scn["branches"][other] = DEP
scn["commits"][DEP] = {"parents": [A], "cut_from": "develop"}
scn["pulls"]["900"]["base"] = other
scn["branches"]["develop"] = A
scn["commits"][EPIC_CUT] = {"parents": [A], "cut_from": "develop", "cut": True}
scn["commits"][EPIC_HEAD] = {"parents": [M2, DEP], "sync": True}
del scn["pulls"]["950"]
scn["expectations"]["blocker-satisfied-by-ancestry"]["1591->1412"] = {
    "state": "COMPLETED", "merged": True, "on_epic": True, "on_develop": False}
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["dependency-1412-not-in-develop"]}
scn["expectations"]["integration-pr"] = {}
scn["expectations"]["release-semantic-history"] = {"one_integration_entry": True,
                                                  "child_titles_survive": True,
                                                  "breaking_survives": True,
                                                  "squashed": False}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
code, report, _ = run(scn)
check("a dependency merged only into another epic branch is unsatisfied (rule 7)",
      code == 0 and observed(report, "readiness")["reasons"] == [
          "dependency-1412-not-in-develop"],
      "code=%s obs=%s" % (code, observed(report, "readiness") if report else None))

# 6. A child whose PR never merged into the epic keeps the epic not ready.
scn = happy()
scn["name"] = "child-open"
scn["pulls"]["902"]["state"] = "open"
scn["pulls"]["902"]["merge_sha"] = None
del scn["pulls"]["950"]
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["child-1593-not-merged-into-epic"]}
scn["expectations"]["integration-pr"] = {}
scn["expectations"]["child-pr-checks"]["902"] = {"jobs": REQUIRED, "failing": []}
scn["expectations"]["migration-conflict"] = {"conflicts": [], "renumbered": []}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
scn["expectations"]["release-semantic-history"] = {
    "one_integration_entry": True, "child_titles_survive": True,
    "breaking_survives": True, "squashed": False}
code, report, _ = run(scn)
check("an unmerged child keeps readiness closed (R7)",
      observed(report, "readiness")["reasons"] == ["child-1593-not-merged-into-epic"],
      str(observed(report, "readiness")))

# 7. A child PR with a failing check is refused even when it merged.
scn = happy()
scn["name"] = "child-checks-failing"
scn["pulls"]["902"]["failing"] = ["unit-tests"]
scn["expectations"]["child-pr-checks"]["902"]["failing"] = ["unit-tests"]
scn["expectations"]["readiness"] = {"ready": False, "reasons": ["child-1593-checks-failing"]}
scn["expectations"]["integration-pr"] = {}
del scn["pulls"]["950"]
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
code, report, _ = run(scn)
check("a merged child with failing checks refuses readiness",
      observed(report, "readiness")["reasons"] == ["child-1593-checks-failing"],
      str(observed(report, "readiness")))

# 8. Two children claiming the same migration slot collide on the epic head.
scn = happy()
scn["name"] = "migration-collision"
scn["pulls"]["902"]["migrations"] = [{"app": "registry", "name": "0002_other"}]
scn["expectations"]["migration-conflict"] = {"conflicts": ["registry/0002"],
                                             "renumbered": []}
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["migration-conflict:registry/0002"]}
scn["expectations"]["integration-pr"] = {}
del scn["pulls"]["950"]
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
code, report, _ = run(scn)
check("two children's migrations in one slot refuse readiness",
      observed(report, "migration-conflict")["conflicts"] == ["registry/0002"]
      and observed(report, "readiness")["reasons"] == ["migration-conflict:registry/0002"],
      str(observed(report, "migration-conflict")))

# 8b. The collision is settled once the side develop does not carry renumbers.
scn["pulls"]["902"]["renumbered"] = True
scn["pulls"]["902"]["migrations"] = [{"app": "registry", "name": "0004_readiness"}]
scn["expectations"]["migration-conflict"] = {"conflicts": [], "renumbered": ["902"]}
scn["expectations"]["readiness"] = {"ready": True, "reasons": []}
scn["pulls"]["950"] = {"head": EPIC_BRANCH, "base": "develop", "state": "merged",
                       "merged_by": "jokiefer", "merge_sha": INTEGRATION,
                       "title": "feat(epic-integration)!: epic integration (#1588)",
                       "checks": REQUIRED}
scn["expectations"]["integration-pr"] = {"count": 1, "base": "develop", "head": EPIC_BRANCH,
                                         "merge": True, "merged_by": "jokiefer"}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": True,
                                                 "recreated": False}
code, report, _ = run(scn)
check("renumbering the later migration clears the conflict",
      code == 0 and failed_ids(report) == [], "code=%s failed=%s" % (code, failed_ids(report)))

# 9. Rule 9: an agent merging its own integration PR is refused, however it is dressed.
scn = happy()
scn["name"] = "agent-merges"
scn["pulls"]["950"]["merged_by"] = "mrmap-agent-bot"
code, report, _ = run(scn)
check("an agent merging the integration PR fails the run",
      code == 1 and {"integration-pr", "no-self-approval"} <= set(failed_ids(report)),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 10. R5/R6: an agent that retargets a PR is refused - only a person retargets.
scn = happy()
scn["name"] = "agent-retargets"
scn["pulls"]["901"]["base"] = "develop"
scn["pulls"]["901"]["retargeted_by"] = "mrmap-agent-bot"
scn["expectations"]["wrong-base"] = {"901": {"wrong": True, "by_agent": True}}
code, report, _ = run(scn)
check("an agent that retargeted a child PR fails the run",
      code == 1 and "wrong-base" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 11. R6: the epic branch may only integrate into develop.
scn = happy()
scn["name"] = "epic-into-master"
scn["pulls"]["950"]["base"] = "master"
code, report, _ = run(scn)
check("an epic branch PR into master is refused (R6)",
      code == 1 and {"integration-pr", "epic-head-base"} <= set(failed_ids(report)),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 12. A second PR with the epic head is not "exactly one integration PR".
scn = happy()
scn["name"] = "two-integration-prs"
scn["pulls"]["951"] = {"head": EPIC_BRANCH, "base": "master", "state": "open",
                       "title": "also the epic", "checks": []}
code, report, _ = run(scn)
check("more than one PR out of the epic branch is refused",
      code == 1 and "integration-pr" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 13. Rule 14: a claim without the integration target, or with another one.
scn = happy()
scn["name"] = "claim-without-target"
scn["claims"]["1591"] = [{"state": "wip"}]
code, report, _ = run(scn)
check("a claim that does not name the integration target fails (rule 14)",
      code == 1 and "claim-carries-target" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "claim-on-develop"
scn["claims"]["1591"] = [{"state": "wip", "integration_target": "develop"}]
scn["expectations"]["claim-carries-target"] = {"1591": {"target": "develop"}}
code, report, _ = run(scn)
check("a claim pointing at develop is refused when the decision says the epic branch",
      code == 1 and "claim-carries-target" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 14. Paused work is not schedulable.
scn = happy(second=False)
scn["name"] = "child-paused"
scn["issues"]["1591"]["labels"] = ["agent: approved", "agent: paused"]
scn["pulls"]["901"]["state"] = "open"
scn["pulls"]["901"]["merge_sha"] = None
scn["expectations"]["child-selection"]["children"] = {
    "1591": {"base": None, "reasons": ["paused"]}}
scn["expectations"]["child-pr-checks"] = {"901": {"jobs": REQUIRED, "failing": []}}
scn["expectations"]["cancellation"] = {"epic_state": "OPEN", "no_open_prs_for": [901]}
scn["expectations"]["paused-or-claimed"] = {"1591": {"paused": True, "claimed": False}}
code, report, _ = run(scn)
check("a paused child is not offered a base (R13)",
      code == 0 and "paused-or-claimed" not in failed_ids(report)
      and observed(report, "child-selection")["1591"]["base"] is None,
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "paused-still-scheduled"
scn["issues"]["1593"]["labels"] = ["agent: approved", "agent: paused"]
scn["issues"]["1593"]["worked_on_while_paused"] = True
scn["expectations"]["paused-or-claimed"] = {"1591": {"paused": False, "claimed": True},
                                            "1593": {"paused": True, "claimed": False}}
scn["expectations"]["readiness"] = {"ready": False,
                                    "reasons": ["child-1593-not-merged-into-epic"]}
del scn["pulls"]["950"]
scn["expectations"]["integration-pr"] = {}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": False,
                                                 "recreated": False}
code, report, _ = run(scn)
check("a paused child that was still worked on is reported",
      code == 1 and "paused-or-claimed" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 15. R12: a child that did not start from the epic head.
scn = happy()
scn["name"] = "child-off-head"
scn["issues"]["1593"]["starts_from"] = A
scn["commits"][C2]["parents"] = [A]
scn["commits"][C2]["cut_from"] = "develop"
code, report, _ = run(scn)
check("a child that does not start from the epic head is reported (R12)",
      code == 1 and "child-starts-from-epic-head" in failed_ids(report)
      and observed(report, "child-starts-from-epic-head")["children_off_head"] == [1593],
      "code=%s failed=%s" % (code, failed_ids(report)))

# 15b. Rebasing an open branch instead of merging the epic head is refused.
scn = happy()
scn["name"] = "open-branch-rebased"
scn["pulls"]["902"]["rebased_open"] = True
code, report, _ = run(scn)
check("rebasing a branch that is open for review is refused (rule 5)",
      code == 1 and "child-starts-from-epic-head" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 16. The CI contract: a child PR whose epic base triggers no workflow is not green.
scn = happy()
scn["name"] = "no-ci-on-epic-base"
for wf in scn["workflows"].values():
    wf["pull_request_branches"] = ["master", "develop"]
scn["expectations"]["child-pr-checks"]["901"]["jobs"] = []
scn["expectations"]["child-pr-checks"]["902"]["jobs"] = []
scn["expectations"]["epic-ci-coverage"] = {"covered_by": [], "required": PR_PATH}
code, report, _ = run(scn)
check("a child PR into an untriggered epic base is not accepted as green",
      code == 1 and "child-pr-checks" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 16b. A child PR with a check outside its base's required set is reported.
scn = happy()
scn["name"] = "child-extra-check"
scn["pulls"]["901"]["checks"] = list(REQUIRED) + ["stale-sonar"]
code, report, _ = run(scn)
check("a child PR with a check outside its base's required set is reported",
      code == 1 and "child-pr-checks" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 17. #1589: a documentation job in the everyday PR path is a finding this tool refuses.
scn = happy()
scn["name"] = "docs-in-pr-path"
scn["workflows"]["release-docs"]["pull_request_branches"] = ["master", "develop", "epic/**"]
code, report, _ = run(scn)
check("a documentation build in the everyday epic path is reported (#1589)",
      code == 1 and "no-docs-job" in failed_ids(report)
      and observed(report, "no-docs-job")["in_pr_path"] == ["docs-build"],
      "code=%s failed=%s" % (code, failed_ids(report)))

# 18. Rule 15: a direct push to develop is reported, and only as a finding by default.
scn = happy()
scn["name"] = "direct-push"
stray = "9" * 40
scn["commits"][stray] = {"parents": [DEP]}
scn["commits"][INTEGRATION]["parents"] = [stray, EPIC_HEAD]
code, report, _ = run(scn)
check("a commit on develop with no PR carrying it is reported",
      "no-direct-push" in failed_ids(report)
      and stray in observed(report, "no-direct-push")["permanent_commits"],
      "failed=%s observed=%s" % (failed_ids(report), observed(report, "no-direct-push")))

scn["expectations"]["no-direct-push"] = {"permanent_commits": [stray]}
code, report, _ = run(scn)
check("the same commit passes as a stated finding and fails with --fail-on-findings",
      code == 0 and run(scn, "--fail-on-findings")[0] == 1,
      "code=%s strict=%s" % (code, run(scn, "--fail-on-findings")[0]))

# 19. Production stays untouched.
scn = happy()
scn["name"] = "master-moved"
scn["branches"]["master"] = INTEGRATION
code, report, _ = run(scn)
check("a moved master is reported: nothing here publishes to production",
      code == 1 and "production-untouched" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 20. Rollback is a revert PR, never a rewrite.
scn = happy()
scn["name"] = "revert-is-a-pr"
scn["pulls"]["960"] = {"head": "revert/issue-1595-integration", "base": "develop",
                       "state": "merged", "merged_by": "jokiefer",
                       "merge_sha": "6" * 40, "title": "revert: epic integration (#950)",
                       "checks": REQUIRED, "commits": ["6" * 40]}
scn["commits"]["6" * 40] = {"parents": [INTEGRATION]}
scn["branches"]["develop"] = "6" * 40
scn["expectations"]["rollback"] = {"reverted": True, "revert_merged_into": "develop",
                                   "rewrote_history": False, "force_pushed": False}
code, report, _ = run(scn)
check("the epic rolls back with a revert PR into develop",
      code == 0 and "rollback" not in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "history-rewritten"
scn["facts"] = {"history_rewritten": True}
scn["expectations"]["rollback"] = {"reverted": False, "revert_merged_into": None,
                                   "rewrote_history": True, "force_pushed": False}
code, report, _ = run(scn)
check("recovering by rewriting history is refused",
      code == 1 and "rollback" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "force-pushed"
scn["facts"] = {"force_pushed": True}
scn["expectations"]["rollback"] = {"reverted": False, "revert_merged_into": None,
                                   "rewrote_history": False, "force_pushed": True}
code, report, _ = run(scn)
check("recovering by force-push is refused",
      code == 1 and "rollback" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 21. R10: after the merge the topic continues on develop, the branch is not recreated.
scn = happy()
scn["name"] = "branch-retired"
del scn["branches"][EPIC_BRANCH]
scn["issues"]["1600"] = {"labels": ["agent: approved"], "approved_by": "jokiefer",
                         "starts_from": "7" * 40, "in_epic": False}
scn["commits"]["7" * 40] = {"parents": [INTEGRATION], "cut_from": "develop"}
code, report, _ = run(scn)
check("a follow-up after integration branches from develop, not the retired epic",
      code == 1 and "child-selection" in failed_ids(report)
      and observed(report, "child-selection")["1600"]["base"] == "develop",
      "code=%s failed=%s observed=%s" % (code, failed_ids(report),
                                         observed(report, "child-selection")
                                         if report else None))

scn = happy()
scn["name"] = "branch-recreated"
scn["facts"] = {"branch_recreated": True}
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": True,
                                                 "work_on_develop": True,
                                                 "recreated": True}
code, report, _ = run(scn)
check("recreating a retired epic branch is refused (R10)",
      code == 1 and "recovery-after-deletion" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 22. Cancellation: a closed epic with an open child PR is inconsistent.
scn = happy()
scn["name"] = "cancelled-with-open-pr"
scn["epic"]["state"] = "CLOSED"
scn["pulls"]["902"]["state"] = "open"
scn["pulls"]["902"]["merge_sha"] = None
for num in ("1591", "1593"):
    scn["expectations"]["child-selection"]["children"][num] = {
        "base": None, "reasons": ["epic-closed"]}
del scn["pulls"]["950"]
scn["expectations"]["integration-pr"] = {}
scn["expectations"]["readiness"] = {"ready": False, "reasons": ["no-epic-branch"]}
scn["expectations"]["cancellation"] = {"epic_state": "CLOSED", "no_open_prs_for": [1593]}
scn["expectations"]["branch-creation"] = {"exists": False, "cut_from": None}
scn["branches"].pop(EPIC_BRANCH)
scn["expectations"]["recovery-after-deletion"] = {"branch_exists": False,
                                                 "work_on_develop": False,
                                                 "recreated": False}
scn["expectations"]["release-semantic-history"] = {"one_integration_entry": True,
                                                  "child_titles_survive": True,
                                                  "breaking_survives": True,
                                                  "squashed": False}
scn["expectations"]["child-pr-checks"]["901"] = {"jobs": REQUIRED, "failing": []}
scn["expectations"]["child-pr-checks"]["902"] = {"jobs": REQUIRED, "failing": []}
scn["expectations"]["blocker-satisfied-by-ancestry"] = {}
scn["expectations"]["wrong-base"] = {}
scn["expectations"]["claim-carries-target"] = {}
scn["expectations"]["paused-or-claimed"] = {}
del scn["claims"]["1591"]
code, report, _ = run(scn)
check("a cancelled epic with a child PR still open is reported",
      code == 1 and "cancellation" in failed_ids(report)
      and observed(report, "cancellation")["open_child_prs"] == [902],
      "code=%s failed=%s" % (code, failed_ids(report)))

# 23. No competing orchestrator: a scheduler appearing in the change set is reported.
scn = happy()
scn["name"] = "scheduler-creep"
scn["added_files"] = ["scripts/epic_scheduler.py", "scripts/wip"]
scn["expectations"]["no-competing-orchestrator"] = {"scheduler_files": [
    "scripts/epic_scheduler.py"]}
code, report, _ = run(scn)
check("a new scheduler is reported as a competing orchestrator",
      code == 0 and observed(report, "no-competing-orchestrator")["scheduler_files"]
      == ["scripts/epic_scheduler.py"],
      "code=%s obs=%s" % (code, observed(report, "no-competing-orchestrator")
                          if report else None))

# The regex must bite on the stem, not only on the path start - the previous
# (^|/) anchor let scripts/epic_scheduler.py through unseen (review finding 3).
scn = happy()
scn["name"] = "scheduler-stems"
scn["added_files"] = ["scripts/epic_scheduler.py", "scripts/epic_daemon.py",
                      "scripts/epic_orchestrator.py", "scripts/a-watcher.sh",
                      "scripts/wip", "docs/scheduler.rst"]
scn["expectations"]["no-competing-orchestrator"] = {"scheduler_files": [
    "docs/scheduler.rst", "scripts/a-watcher.sh", "scripts/epic_daemon.py",
    "scripts/epic_scheduler.py"]}
code, report, _ = run(scn)
check("stem-shaped scheduler files are seen, not just path-initial ones",
      code == 0 and observed(report, "no-competing-orchestrator")["scheduler_files"]
      == ["docs/scheduler.rst", "scripts/a-watcher.sh", "scripts/epic_daemon.py",
          "scripts/epic_scheduler.py"],
      "code=%s obs=%s" % (code, observed(report, "no-competing-orchestrator")
                          if report else None))

# A scenario that claims no scheduler over a world with one is refused, not agreed with.
scn["expectations"]["no-competing-orchestrator"] = {"scheduler_files": []}
code, report, _ = run(scn)
check("a scenario that claims no scheduler despite the planted ones fails",
      code == 1 and "no-competing-orchestrator" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 24. The harness refuses a scenario that states no expectation for a check.
scn = happy()
scn["name"] = "missing-expectation"
del scn["expectations"]["readiness"]
code, report, err = run(scn)
check("a scenario without an expectation for a check is refused (exit 2)",
      code == 2 and report is None and "readiness" in err, err[:200])

scn = happy()
scn["name"] = "unknown-expectation"
scn["expectations"]["readiness-of-the-moon"] = {}
code, report, err = run(scn)
check("an expectation for an unknown check is refused (exit 2)",
      code == 2 and "unknown" in err, err[:200])

scn = happy()
scn["name"] = "wrong-schema"
scn["schema"] = "epic-integration-dryrun-scenario/v0"
code, report, err = run(scn)
check("a scenario of another schema is refused (exit 2)", code == 2 and report is None,
      "code=%s" % code)

scn = happy()
scn["name"] = "unknown-ref"
scn["issues"]["1591"]["starts_from"] = "not-a-sha"
code, report, err = run(scn)
check("a scenario naming a ref it does not carry is refused (exit 2)",
      code == 2 and report is None and "not-a-sha" in err, err[:200])

# 25. The engine runs no command: every journalled read is on the allowlist, and a
#     write is refused outright.
scn_obj = M.Scenario(happy())
try:
    scn_obj.ask("git", "push", "origin", "HEAD:refs/heads/develop")
    check("a write command is refused by the read-only allowlist", False, "no refusal")
except M.HarnessError as e:
    check("a write command is refused by the read-only allowlist", "push" in str(e))
try:
    M.Scenario(happy()).ask("gh", "pr", "merge", "950")
    check("a GitHub write is refused by the read-only allowlist", False, "no refusal")
except M.HarnessError:
    check("a GitHub write is refused by the read-only allowlist", True)

# 26. Determinism: the same world answers the same way twice.
first = run(happy())
second = run(happy())
check("two runs over the same world give the same answer",
      first[0] == second[0]
      and [c["ok"] for c in first[1]["checks"]] == [c["ok"] for c in second[1]["checks"]])

# 27. The tool exposes its check list, which is what the evidence document cites.
out = io.StringIO()
with redirect_stdout(out):
    code = M.main(["--list-checks"])
check("--list-checks prints the contract's acceptance lines",
      code == 0 and out.getvalue().split() == M.CHECK_IDS, out.getvalue()[:200])

# 28. The committed evidence is reproducible: the two scenario files and the report
#     in docs/source/development/evidence/ are what this tool says they are. A report
#     that no longer matches its scenario is the drift this check exists for.
EVIDENCE = HERE.parent / "docs" / "source" / "development" / "evidence"
happy_path = EVIDENCE / "epic-integration-dryrun-scenario.json"
gap_path = EVIDENCE / "epic-integration-pre-rollout-gap.json"
report_path = EVIDENCE / "epic-integration-dryrun-report.json"
check("the committed evidence files are present",
      happy_path.exists() and gap_path.exists() and report_path.exists(),
      str(EVIDENCE))
if happy_path.exists():
    code, report, _ = run(json.loads(happy_path.read_text(encoding="utf-8")))
    check("the committed happy scenario validates 22/22",
          code == 0 and len(report["checks"]) == len(M.CHECK_IDS)
          and failed_ids(report) == [],
          "code=%s failed=%s" % (code, failed_ids(report) if report else None))
    if report_path.exists() and report:
        committed = json.loads(report_path.read_text(encoding="utf-8"))
        fresh = [(c["id"], c["ok"], c["severity"]) for c in report["checks"]]
        stored = [(c["id"], c["ok"], c["severity"]) for c in committed["checks"]]
        check("the committed report is what a fresh run produces",
              stored == fresh and committed["scenario"] == report["scenario"]
              and committed["mode"] == "dry-run" and committed["writes"] == [],
              "stored=%s fresh=%s" % (stored[:3], fresh[:3]))
if gap_path.exists():
    code, report, _ = run(json.loads(gap_path.read_text(encoding="utf-8")))
    check("the committed pre-rollout scenario fails on the CI checks of its base",
          code == 1 and failed_ids(report) == ["child-pr-checks", "epic-ci-coverage"],
          "code=%s failed=%s" % (code, failed_ids(report) if report else None))

# 27b. An expectation emptied of content does not silence its check (review finding 2):
#      child-pr-checks covers every child PR that exists, stated or not.
scn = happy()
scn["name"] = "emptied-child-pr-expectation"
scn["expectations"]["child-pr-checks"] = {}
code, report, _ = run(scn)
check("an emptied child-pr-checks expectation does not pass over the world",
      code == 1 and "child-pr-checks" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "epic-base-without-required-jobs"
scn["pulls"]["901"]["checks"] = []          # merged child PR with no checks at all
scn["expectations"]["child-pr-checks"]["901"]["jobs"] = []
code, report, _ = run(scn)
check("a child PR into the epic branch must carry its base's required set even if "
      "the scenario expects none",
      code == 1 and "child-pr-checks" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 27c. The human-authority laundering the review demonstrated is refused (finding 1).
scn = happy()
scn["name"] = "agent-listed-as-human"
scn["humans"] = ["jokiefer", "mrmap-agent-bot"]
scn["pulls"]["950"]["merged_by"] = "mrmap-agent-bot"
code, report, _ = run(scn)
check("listing the agent login among the humans does not launder its merge",
      code == 1 and {"integration-pr", "no-self-approval"} <= set(failed_ids(report)),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn = happy()
scn["name"] = "sync-flag-hides-smuggled-commit"
stray = "8" * 40
scn["commits"][stray] = {"parents": [DEP], "sync": True}   # claimed rule-12 sync, not one
scn["commits"][INTEGRATION]["parents"] = [stray, EPIC_HEAD]
scn["expectations"]["no-direct-push"] = {"permanent_commits": []}
code, report, _ = run(scn)
check("a smuggled commit marked sync is still reported by no-direct-push",
      code == 1 and stray in observed(report, "no-direct-push")["permanent_commits"],
      "code=%s obs=%s" % (code, observed(report, "no-direct-push") if report else None))

scn = happy()
scn["name"] = "cut-flag-hides-smuggled-commit"
stray = "7" * 40
scn["commits"][stray] = {"parents": [DEP], "cut": True}    # claimed rule-3 cut, not one
scn["commits"][INTEGRATION]["parents"] = [stray, EPIC_HEAD]
scn["expectations"]["no-direct-push"] = {"permanent_commits": []}
code, report, _ = run(scn)
check("a smuggled commit marked cut is still reported by no-direct-push",
      code == 1 and stray in observed(report, "no-direct-push")["permanent_commits"],
      "code=%s obs=%s" % (code, observed(report, "no-direct-push") if report else None))

# the genuine sync stays exempt (EPIC_HEAD in the happy world is such a merge) - the
# tightened condition must not break the legitimate case, and a genuine cut does too.
check("the genuine rule-12 sync and rule-3 cut stay exempt",
      run(happy())[0] == 0, "the happy world stopped validating")

# 27c-2. The shape the rule exists to catch: `git push origin <sha>:develop` puts a
# single-parent commit on develop's tip. Flagging it as the rule-3 cut must not
# exempt it for ANY cut_from value (re-review finding A) - a genuine cut reaches
# develop only through a merge, a pushed tip does not.
for cut_from in ("develop", "master", EPIC_BRANCH, "nope/branch"):
    scn = happy()
    scn["name"] = "pushed-tip-claimed-cut-" + cut_from.replace("/", "-")
    stray = "e" * 40
    scn["commits"][stray] = {"parents": [DEP], "cut": True, "cut_from": cut_from}
    scn["branches"]["develop"] = stray
    scn["expectations"]["no-direct-push"] = {"permanent_commits": [stray]}
    code, report, _ = run(scn)
    check("a commit pushed onto develop's tip is reported despite claiming cut_from=%s"
          % cut_from,
          code == 1 and stray in observed(report, "no-direct-push")["permanent_commits"],
          "code=%s obs=%s" % (code, observed(report, "no-direct-push")
                              if report else None))

# one commit deeper (tip Z over the claimed cut Y) is still a pushed chain: neither
# owes nothing, because develop carries both without ever passing a merge below them.
scn = happy()
scn["name"] = "pushed-chain-claimed-cut"
y, z = "b" * 40, "c" * 39 + "1"
scn["commits"][y] = {"parents": [DEP], "cut": True, "cut_from": "develop"}
scn["commits"][z] = {"parents": [y]}
scn["branches"]["develop"] = z
scn["expectations"]["no-direct-push"] = {"permanent_commits": [y, z]}
code, report, _ = run(scn)
check("a claimed cut one commit below a pushed tip is reported too",
      code == 1 and set(observed(report, "no-direct-push")["permanent_commits"]) == {y, z},
      "code=%s obs=%s" % (code, observed(report, "no-direct-push") if report else None))

# and the honest exemption is still load-bearing in the other direction: removing
# the merge-path requirement would report the happy world's genuine cut, so a
# scenario asserting none over the happy world must fail (the cut IS exempt).
scn = happy()
scn["expectations"]["no-direct-push"] = {"permanent_commits": ["3" * 40]}
code, report, _ = run(scn)
check("the genuine rule-3 cut is exempt - claiming it as a direct push fails",
      code == 1 and "no-direct-push" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

# 27d. production-untouched cannot be green-washed by declaring the move (finding 5).
scn = happy()
scn["name"] = "master-moved-declared"
scn["branches"]["master"] = INTEGRATION
scn["expectations"]["production-untouched"] = {"master_moved": True}
code, report, _ = run(scn)
check("declaring the moved master does not green production-untouched",
      code == 1 and "production-untouched" in failed_ids(report),
      "code=%s failed=%s" % (code, failed_ids(report)))

scn["expectations"]["production-untouched"] = {
    "master_moved": True,
    "promotion_waiver": "release promotion runbook of #1584, run 2026-11-25"}
code, report, _ = run(scn)
check("a waiver naming the promotion runbook lets it pass as a stated finding",
      code == 0 and run(scn, "--fail-on-findings")[0] == 1,
      "code=%s strict=%s" % (code, run(scn, "--fail-on-findings")[0]))

shutil.rmtree(TMP, ignore_errors=True)

failed = 0
for name, ok, detail in RESULTS:
    if not ok:
        failed += 1
    print("PASS  %s" % name if ok else "FAIL  %s   [%s]" % (name, detail[:400]))
print("%d/%d checks passed" % (len(RESULTS) - failed, len(RESULTS)))
sys.exit(1 if failed else 0)
