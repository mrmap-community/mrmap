"""Offline regression checks for the CI watcher of the agent supervisor (#1061).

Run from the repository root: python3 scripts/test_agent_supervisor_ci.py
Exit code 0 means every check passed. Needs no `gh`, no network, no docker and no
OpenCode: every GitHub read is a stub in this file, the worker is a stub that
records what it was told, and the claim board is a stub that records the questions.

The acceptance of #1061 is one sentence with three hard halves: *one failing check
triggers one bounded repair cycle, green PR waits for human review, infrastructure
failures do not cause uncontrolled code churn*. The checks below are written as the
ways those halves break - a red runner read as a red branch, the same failure
waking a worker twice, a budget that resets on restart, a watcher that follows a
pull request nobody asked it to work on, and a "helpful" rerun or approve hidden in
the read-only path.
"""

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import gh                                      # noqa: E402
from agent_supervisor.ci_monitor import Monitor, classify, line     # noqa: E402
from agent_supervisor.config import load as load_config             # noqa: E402
from agent_supervisor.runner import StartError                      # noqa: E402
from agent_supervisor.store import Store                            # noqa: E402

PASS = FAIL = 0
FAILURES = []
TMP = tempfile.mkdtemp(prefix="supervisor-ci-tests-")
OWNER = "o"
REPO = "o/r"
HEAD = "abc123def456abc123def456abc123def456abc1"
OTHER_HEAD = "9999999999999999999999999999999999999999"
QUEUE_SHA = "7777777777777777777777777777777777777777"


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


# ---------------------------------------------------------------------------
# stubs

class FakeGh:
    """Answers the three reads the watcher makes and records every path it was
    asked for, so "this module cannot write" is a checked fact and not a promise."""

    def __init__(self):
        self.branch_prs = {}          # "o:branch" -> [pr payload]
        self.prs = {}                 # number -> pr payload
        self.check_runs = {}          # head sha -> [check run payloads]
        self.statuses = {}            # head sha -> [commit status payloads]
        self.reads = []               # (path, params, method)
        self.fail_read = set()        # path fragments that must raise

    def pr(self, number, branch, sha=HEAD, state="open", mergeable="clean"):
        payload = {"number": number, "state": state, "mergeable_state": mergeable,
                   "head": {"sha": sha}, "html_url": f"https://github.com/{REPO}/pull/{number}"}
        self.prs[number] = payload
        self.branch_prs.setdefault(f"{OWNER}:{branch}", []).append(payload)
        return payload

    def checks_for(self, sha, runs=(), statuses=()):
        self.check_runs[sha] = list(runs)
        self.statuses[sha] = list(statuses)

    def gh_json(self, path, params=None, method="GET", accept=None, timeout=None):
        self.reads.append((path, dict(params or {}), method))
        for fragment in self.fail_read:
            if fragment in path:
                raise gh.GhError(f"stub: cannot read {path}", "network")
        if path.endswith("/pulls") and method == "GET":
            return self.branch_prs.get(params.get("head"), [])
        if "/pulls/" in path and "/check-runs" not in path:
            return self.prs[int(path.rsplit("/", 1)[1])]
        if path.endswith("/check-runs"):
            return {"check_runs": self.check_runs.get(params.get("ref")
                                                      or path.split("/")[-2], [])}
        if path.endswith("/status"):
            return {"statuses": self.statuses.get(path.split("/")[-2], [])}
        raise gh.GhError(f"stub: unhandled {path}", "api")


def run(name, conclusion="failure", title="", summary="", annotations=(), kind="check",
        url=None, status="completed"):
    """One check run as GitHub reports it."""
    payload = {"name": name, "status": status,
               "conclusion": conclusion if kind == "check" else None,
               "output": {"title": title, "summary": summary, "text": summary},
               "annotations": [{"message": a} for a in annotations],
               "html_url": url or f"https://github.com/{REPO}/runs/{name}", "id": abs(hash(name))}
    if kind == "status":
        return {"context": name, "state": conclusion, "description": summary,
                "target_url": payload["html_url"], "id": payload["id"]}
    return payload


class FakeRunner:
    """A worker that remembers what it was woken up with."""

    def __init__(self, store, alive=False, raises=None):
        self.store = store
        self.alive_flag = alive
        self.raises = raises
        self.resumed = []                      # [(issue, prompt)]

    def alive(self, lease):
        return self.alive_flag

    def resume(self, issue, prompt=None):
        self.resumed.append((issue, prompt))
        if self.raises:
            raise self.raises
        return {"pid": 4000 + len(self.resumed), "pgid": 4000 + len(self.resumed),
                "session": f"mrmap-{issue}", "worktree": "/srv/wt", "log": "/tmp/log"}


class FakeWip:
    """The board's question flow, recorded instead of posted."""

    def __init__(self, raises=None):
        self.asked = []                        # [(issue, question)]
        self.raises = raises

    def cmd_ask(self, question, issue_arg=None, force=False):
        self.asked.append((issue_arg, question))
        if self.raises:
            raise self.raises


class FakeClaims:
    def __init__(self, wip):
        self.wip = wip


_STORES = [0]


def harness(**overrides):
    data = {"repo": REPO, "authorized_humans": ["human"], "state_dir": TMP,
            "repo_root": "/srv/mrmap", "opencode_model": "p/m", "ci_repair_attempts": 2}
    data.update(overrides)
    path = os.path.join(TMP, f"cfg-{abs(hash(json.dumps(data, sort_keys=True)))}.json")
    with open(path, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)
    return load_config(path)


def make(cfg=None, fake=None, alive=False, resume_raises=None, ask_raises=None, store=None):
    """A watcher over fresh stubs; `store` is passed twice by the restart checks."""
    cfg = cfg or harness()
    fake = fake or FakeGh()
    gh.gh_json = fake.gh_json
    _STORES[0] += 1
    store = store or Store(os.path.join(TMP, f"state-{_STORES[0]}.sqlite3"))
    wip = FakeWip(raises=ask_raises)
    runner = FakeRunner(store, alive=alive, raises=resume_raises)
    return Monitor(cfg, store=store, runner=runner, claims=FakeClaims(wip)), fake, runner, wip


def lease(store, issue=7, branch="feature/issue-7-thing", state="finished"):
    """A lease in the shape the runner leaves one behind: worktree, branch, session."""
    store.claim_lease(issue, REPO, "stack", branch=branch,
                      worktree=f"/srv/wt/issue-{issue}", project=f"mrmap-agent-{issue}-1")
    store.update_lease(issue, state="running", session=f"mrmap-{issue}", pid=1, pgid=1)
    store.release_lease(issue, state=state, detail="pull request opened")
    return store.lease(issue)


# ---------------------------------------------------------------------------
# classification: what may wake a worker, and what may not

def test_classification():
    queued = classify(run("build", conclusion=None, status="queued"))
    check("a queued check is not news", queued[0] == "pending")
    check("an in_progress check is not news",
          classify(run("build", conclusion=None, status="in_progress"))[0] == "pending")
    check("a success is green", classify(run("build", conclusion="success"))[0] == "green")
    check("a skipped check is green, not a failure to explain",
          classify(run("publish", conclusion="skipped"))[0] == "green")
    check("a neutral status is green", classify(run("legacy", conclusion="neutral"))[0] == "green")
    check("a cancelled run is not a defect",
          classify(run("build", conclusion="cancelled"))[0] == "cancelled")
    check("a workflow-level timeout reads as infrastructure",
          classify(run("build", conclusion="timed_out"))[0] == "infra")

    verdict, why = classify(run("backend unit tests", summary="FAILED tests/django/test_x.py::y",
                                annotations=["AssertionError: 404 != 200"]))
    check("a named test failure is actionable", verdict == "code", why)
    verdict, why = classify(run("pre-commit", summary="backend/foo.py:12:1: F401 unused import"))
    check("a lint failure is actionable", verdict == "code", why)
    verdict, why = classify(run("tsc", summary="src/x.ts(12,3): error TS2345: Argument type"))
    check("a type error is actionable", verdict == "code", why)
    drift_summary = "Your models have changes required for the following apps"
    verdict, why = classify(run("migration drift", summary=drift_summary))
    check("a migration-drift failure is actionable", verdict == "code", why)

    verdict, why = classify(run("docker build", title="Build failed",
                                summary="dial tcp: lookup ghcr.io: Temporary failure in "
                                        "name resolution"))
    check("a DNS failure is infrastructure", verdict == "infra", why)
    verdict, why = classify(run("checkout", summary="Error: Failed to download runner "
                                                    "container: 503 Service Unavailable"))
    check("a runner download failure is infrastructure", verdict == "infra", why)
    verdict, why = classify(run("behave", summary="got: no space left on device"))
    check("a full disk is infrastructure", verdict == "infra", why)
    verdict, why = classify(run("docker build", summary="Error response from daemon: "
                                                        "toomanyrequests: Rate exceeded"))
    check("a registry rate limit is infrastructure", verdict == "infra", why)

    both = classify(run("backend unit tests",
                        summary="FAILED tests/django/test_x.py and then: "
                                "no space left on device"))
    check("a failure naming both is NOT repaired", both[0] == "infra", both[1])
    verdict, why = classify(run("something we do not know", title="Something went wrong",
                                summary="exit status 1"))
    check("an unexplained failure is not repaired", verdict == "unknown", why)
    verdict, why = classify(run("legacy status", conclusion="failure",
                                summary="Cannot connect to the Docker daemon"))
    check("an infrastructure read works on a legacy status too", verdict == "infra", why)

    check("line() names the check, its conclusion and where to look",
          "backend unit tests" in line(run("backend unit tests"))
          and "github.com" in line(run("backend unit tests")))


# ---------------------------------------------------------------------------
# one failing check -> one bounded repair cycle

def test_one_repair():
    mon, fake, runner, wip = make()
    lease(mon.store)
    fake.pr(41, "feature/issue-7-thing")
    fake.checks_for(HEAD, runs=[run("backend unit tests",
                                    summary="FAILED tests/django/test_x.py::y AssertionError")])
    report = mon.watch()
    check("one failing check is reported as a repair",
          report and report[0]["action"] == "repairing", str(report))
    check("exactly one worker start", len(runner.resumed) == 1, str(len(runner.resumed)))
    check("the worker of the right issue was woken", runner.resumed[0][0] == 7)
    prompt = runner.resumed[0][1] or ""
    check("the prompt names the failing check", "backend unit tests" in prompt, prompt[:120])
    check("the prompt carries the check's URL", "github.com" in prompt)
    check("the prompt names the head SHA that is red", HEAD in prompt)
    check("the prompt repeats the rules of the worktree",
          "this worktree" in prompt.lower() and "compose project" in prompt.lower())
    check("the prompt forbids rebasing a branch under review", "never rebase" in prompt.lower())
    check("the prompt names what the worker may not do", "gh pr merge" in prompt)
    row = mon.store.pr_row(7)
    check("the repair is attributed to the issue's pull request", row["pr"] == 41)
    check("one attempt counted", row["attempts"] == 1, str(row["attempts"]))
    check("the repaired head is recorded", row["repair_sha"] == HEAD)
    check("the state says a repair is under way", row["state"] == "repairing")

    # The same red check again, with nothing pushed in between.
    report = mon.watch()
    check("the same head is not repaired twice",
          report[0]["action"] == "held" and len(runner.resumed) == 1, str(report))
    check("and the reason names the budget rule", "already repaired" in report[0]["detail"],
          report[0]["detail"])

    # A human pushed: a new head SHA is a new finding.
    fake.pr(41, "feature/issue-7-thing", sha=OTHER_HEAD)
    fake.checks_for(OTHER_HEAD, runs=[run("frontend tests",
                                          summary="error TS2345: not assignable")])
    report = mon.watch()
    check("a new commit may be repaired again", report[0]["action"] == "repairing", str(report))
    check("and that was the second worker start", len(runner.resumed) == 2)

    # Budget spent: a third head gets no worker, and a human hears why.
    third = "5555555555555555555555555555555555555555"
    fake.pr(41, "feature/issue-7-thing", sha=third)
    fake.checks_for(third, runs=[run("backend unit tests", summary="AssertionError again")])
    report = mon.watch()
    check("the third failure gets no worker", report[0]["action"] == "held", str(report))
    check("the reason is the lifetime budget", "budget spent" in report[0]["detail"],
          report[0]["detail"])
    check("still only two worker starts", len(runner.resumed) == 2)
    check("no human was asked about a repairable failure", wip.asked == [], str(wip.asked))


def test_budget_of_one():
    mon, fake, runner, wip = make(cfg=harness(ci_repair_attempts=1))
    lease(mon.store, issue=8, branch="feature/issue-8-x")
    fake.pr(42, "feature/issue-8-x")
    fake.checks_for(HEAD, runs=[run("flake8", summary="E501 line too long")])
    check("the configured budget is honoured, not the default",
          mon.watch()[0]["action"] == "repairing")
    fake.pr(42, "feature/issue-8-x", sha=OTHER_HEAD)
    fake.checks_for(OTHER_HEAD, runs=[run("flake8", summary="E501 line too long")])
    report = mon.watch()
    check("a second cycle needs permission the operator did not give",
          report[0]["action"] == "held" and len(runner.resumed) == 1, str(report))


def test_budget_survives_a_restart():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=9, branch="feature/issue-9-x")
    fake.pr(43, "feature/issue-9-x")
    fake.checks_for(HEAD, runs=[run("behave", summary="AssertionError: expected 200")])
    check("the first pass repairs", mon.watch()[0]["action"] == "repairing")
    again, fake2, runner2, _ = make(store=mon.store, fake=fake)
    fake.pr(43, "feature/issue-9-x", sha=OTHER_HEAD)
    fake.checks_for(OTHER_HEAD, runs=[run("behave", summary="AssertionError: expected 200")])
    report = again.watch()
    check("a restarted supervisor still knows the budget was used",
          report[0]["action"] == "repairing" and runner2.resumed[0][1], str(report))
    third = "5555555555555555555555555555555555555555"
    fake.pr(43, "feature/issue-9-x", sha=third)
    fake.checks_for(third, runs=[run("behave", summary="AssertionError")])
    again.watch()
    third_report = None
    again2, _, runner3, _ = make(store=mon.store, fake=fake)
    fourth = "6666666666666666666666666666666666666666"
    fake.pr(43, "feature/issue-9-x", sha=fourth)
    fake.checks_for(fourth, runs=[run("behave", summary="AssertionError")])
    third_report = again2.watch()
    check("and after two restarts the budget is still spent",
          third_report[0]["action"] == "held" and not runner3.resumed, str(third_report))


# ---------------------------------------------------------------------------
# green, pending, closed: nothing happens

def test_quiet_states():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=11, branch="feature/issue-11-x")
    fake.pr(44, "feature/issue-11-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", conclusion="success"),
                                run("frontend tests", conclusion="success"),
                                run("publish", conclusion="skipped")])
    report = mon.watch()
    check("a green pull request waits for a human review",
          report[0]["action"] == "green", str(report))
    check("green wakes no worker", not runner.resumed)
    check("green asks no question", not wip.asked)
    check("green is recorded as green", mon.store.pr_row(11)["state"] == "green")

    fake.checks_for(HEAD, runs=[run("backend unit tests", conclusion=None, status="in_progress")])
    report = mon.watch()
    check("a running check is just waiting", report[0]["action"] == "waiting", str(report))
    check("waiting wakes nothing", not runner.resumed)
    check("a pull request whose checks are still running is not green",
          mon.store.pr_row(11)["state"] == "waiting-ci")

    fake.checks_for(HEAD, runs=[])
    report = mon.watch()
    check("no checks at all is still waiting, not green",
          report[0]["action"] == "waiting" and "no checks" in report[0]["detail"], str(report))

    fake.checks_for(HEAD, runs=[run("nightly", conclusion="cancelled")])
    report = mon.watch()
    check("a cancelled run starts no repair", report[0]["action"] == "waiting"
          and not runner.resumed, str(report))

    fake.pr(44, "feature/issue-11-x", state="closed")
    report = mon.watch()
    check("a closed pull request is dropped from the watch",
          report[0]["action"] == "closed", str(report))
    check("and it is not repaired", not runner.resumed)
    check("closed is remembered so the row is not mistaken for untracked",
          mon.store.pr_row(11)["state"] == "closed")
    check("a closed pull request is no longer in the watched list",
          mon.store.watched_prs() == [])


# ---------------------------------------------------------------------------
# infrastructure and unknown: a human hears about it, the branch does not move

def test_infrastructure_is_reported_not_repaired():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=12, branch="feature/issue-12-x")
    fake.pr(45, "feature/issue-12-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests",
                                    summary="Could not resolve host: registry-1.docker.io")])
    report = mon.watch()
    check("an infrastructure failure never wakes a worker",
          not runner.resumed and report[0]["action"] == "escalated", str(report))
    check("it is asked about once", len(wip.asked) == 1)
    issue_arg, question = wip.asked[0]
    check("the question goes to the issue, not the pull request", issue_arg == 12)
    check("the question names the check", "backend unit tests" in question)
    check("the question says why no repair happened", "will not" in question
          or "not repaired" in question)
    check("the question offers the human the next step", "rerun" in question.lower())
    check("the state is waiting for a human", mon.store.pr_row(12)["state"] == "waiting-human")

    report = mon.watch()
    check("the same head is not escalated twice",
          report[0]["action"] == "reported" and len(wip.asked) == 1, str(report))

    mon, fake, runner, wip = make()
    lease(mon.store, issue=13, branch="feature/issue-13-x")
    fake.pr(46, "feature/issue-13-x")
    fake.checks_for(HEAD, runs=[run("something odd", summary="exit status 1")])
    report = mon.watch()
    check("an unclassified failure is escalated, not repaired",
          report[0]["action"] == "escalated" and not runner.resumed, str(report))


def test_escalation_retries_when_the_board_was_unreachable():
    mon, fake, runner, wip = make(ask_raises=gh.GhError("stub: board unreachable", "network"))
    lease(mon.store, issue=14, branch="feature/issue-14-x")
    fake.pr(47, "feature/issue-14-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="Could not resolve host")])
    report = mon.watch()
    check("a failed escalation says so", report[0]["action"] == "escalation-failed", str(report))
    check("and it did not write the 'already reported' marker",
          mon.store.ci_seen(47, HEAD) == {}, str(mon.store.ci_seen(47, HEAD)))
    # Same watcher, board reachable now: the human must still be told.
    mon.claims = FakeClaims(FakeWip())
    report = mon.watch()
    check("the next pass tells the human after all", report[0]["action"] == "escalated",
          str(report))
    check("and only then is it marked reported", len(mon.store.ci_seen(47, HEAD)) == 1)


# ---------------------------------------------------------------------------
# who is watched, and what the watcher cannot do

def test_only_our_own_pull_requests():
    mon, fake, runner, wip = make()
    report = mon.watch()
    check("without a lease there is nothing to watch",
          report == [] or all(row["action"] == "untracked" for row in report), str(report))
    check("and nothing was resumed", not runner.resumed)

    lease(mon.store, issue=15, branch="feature/issue-15-x")
    report = mon.watch()
    check("a branch with no open pull request is reported, not invented",
          report[0]["action"] == "untracked" and "no open pull request" in report[0]["detail"],
          str(report))

    fake.pr(48, "feature/issue-15-x", sha=QUEUE_SHA)
    fake.checks_for(QUEUE_SHA, runs=[run("backend unit tests", summary="AssertionError")])
    report = mon.watch()
    check("the pull request of the lease's branch is the one followed",
          report[0]["pr"] == 48 and report[0]["action"] == "repairing", str(report))
    asked_for = [path for path, _, _ in fake.reads]
    check("checks are read for the head SHA, never for a merge commit",
          any(QUEUE_SHA in path for path in asked_for)
          and not any("merge_queue" in path or "queue" in path for path in asked_for),
          str(asked_for[-3:]))


def test_a_running_worker_is_not_disturbed():
    mon, fake, runner, wip = make(alive=True)
    lease(mon.store, issue=16, branch="feature/issue-16-x", state="running")
    fake.pr(49, "feature/issue-16-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="AssertionError")])
    report = mon.watch()
    check("a failure while the worker still runs is held, not doubled",
          report[0]["action"] == "held" and not runner.resumed, str(report))
    check("the reason names the running worker", "still running" in report[0]["detail"],
          report[0]["detail"])


def test_a_resume_that_cannot_happen_is_reported():
    mon, fake, runner, wip = make(resume_raises=StartError("#17 has no recorded session"))
    lease(mon.store, issue=17, branch="feature/issue-17-x")
    fake.pr(50, "feature/issue-17-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="AssertionError")])
    report = mon.watch()
    check("a refused resume is reported as refused",
          report[0]["action"] == "repair-refused", str(report))
    check("and it costs no repair attempt", mon.store.pr_row(17)["attempts"] == 0,
          str(mon.store.pr_row(17)))
    kinds = [event["kind"] for event in mon.store.recent_events(5)]
    check("the refusal is in the event log", "ci-repair-refused" in kinds, str(kinds))


def test_unreadable_github_changes_nothing():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=18, branch="feature/issue-18-x")
    fake.pr(51, "feature/issue-18-x")
    fake.fail_read.add("/pulls/51")
    report = mon.watch()
    check("a GitHub that will not answer is not read as green",
          report[0]["action"] == "unreadable", str(report))
    check("nothing is resumed on an unreadable read", not runner.resumed)
    check("and nothing is escalated", not wip.asked)
    check("the state stays watchable", mon.store.pr_row(18)["state"] == "watching")


def test_dry_run_changes_nothing():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=19, branch="feature/issue-19-x")
    fake.pr(52, "feature/issue-19-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="AssertionError")])
    report = mon.watch(dry_run=True)
    check("dry-run says what it would do", report[0]["action"] == "would-repair", str(report))
    check("dry-run resumes nobody", not runner.resumed)
    check("dry-run asks nobody", not wip.asked)
    fake.checks_for(HEAD, runs=[run("build", summary="503 Service Unavailable")])
    report = mon.watch(dry_run=True)
    check("dry-run would escalate but does not",
          report[0]["action"] == "would-escalate" and not wip.asked, str(report))


def test_the_watcher_has_no_write_path():
    mon, fake, runner, wip = make()
    lease(mon.store, issue=20, branch="feature/issue-20-x")
    fake.pr(53, "feature/issue-20-x")
    green = run("behave", conclusion="success")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="AssertionError"), green])
    mon.watch()
    fake.checks_for(HEAD, runs=[run("build", summary="Bad gateway")])
    mon.watch()
    methods = {method for _, _, method in fake.reads}
    check("every GitHub call the watcher made was a GET", methods == {"GET"}, str(methods))
    forbidden = ("merge", "review", "comments", "enqueue", "rerun", "dispatch",
                 "requested_reviewers", "check-suites")
    hits = [path for path, _, _ in fake.reads if any(word in path for word in forbidden)]
    check("and no path it read is a merge, review, comment, queue or rerun endpoint",
          hits == [], str(hits))
    check("the only write is the board question", len(wip.asked) == 1, str(len(wip.asked)))
    source = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "agent_supervisor", "ci_monitor.py")).read()
    for word in ("gh pr merge", "gh pr review", "gh pr edit", "gh run rerun", "gh pr comment",
                 "branch-protection", "--admin"):
        check(f"the module never mentions {word}", word not in source)


# ---------------------------------------------------------------------------
# the store's own promises

def test_store_rules():
    store = Store(os.path.join(TMP, "store-rules.sqlite3"))
    store.track_pr(21, REPO, 60, "feature/issue-21-x", HEAD)
    store.update_pr(21, attempts=1, repair_sha=HEAD, state="repairing")
    store.track_pr(21, REPO, 60, "feature/issue-21-x", OTHER_HEAD)
    row = store.pr_row(21)
    check("re-tracking a pull request keeps the repair budget", row["attempts"] == 1,
          str(row))
    check("re-tracking records the new head", row["head_sha"] == OTHER_HEAD)
    check("re-tracking does not lose the repaired head", row["repair_sha"] == HEAD)

    store.update_pr(21, state="closed")
    store.track_pr(21, REPO, 61, "feature/issue-21-x", OTHER_HEAD)
    row = store.pr_row(21)
    check("a reopened pull request starts over as a subject", row["pr"] == 61
          and row["state"] == "watching", str(row))
    check("but its budget did not evaporate", row["attempts"] == 1)

    store.track_pr(22, REPO, 62, "feature/issue-22-x", HEAD)
    store.update_pr(22, state="closed")
    check("a closed subject is not in the watched list",
          22 not in [row["issue"] for row in store.watched_prs()])

    check("a finding is new exactly once",
          store.note_ci_seen(60, HEAD, "backend unit tests", "escalated") is True
          and store.note_ci_seen(60, HEAD, "backend unit tests", "escalated") is False)
    check("the same check on another head is new again",
          store.note_ci_seen(60, OTHER_HEAD, "backend unit tests", "escalated") is True)
    check("ci_seen answers for one head only",
          set(store.ci_seen(60, HEAD)) == {"backend unit tests"}
          and set(store.ci_seen(60, OTHER_HEAD)) == {"backend unit tests"})
    try:
        store.update_pr(21, state="merged")
        check("an invented pull-request state is refused", False)
    except ValueError as exc:
        check("an invented pull-request state is refused", True, str(exc))
    try:
        store.update_pr(21, merged=True)
        check("an unknown pull-request column is refused", False)
    except ValueError as exc:
        check("an unknown pull-request column is refused", True, str(exc))
    check("status() reports the pull requests too", "pulls" in store.status())


def test_the_operator_commands_show_it():
    """`prs`, `watch-prs --dry-run` and `status` over a seeded state file.

    These are what a human types at 8 am, so the checks are about what the
    operator sees: the escalated pull request has to be visible without a
    `--json`, and the dry run must not reach for the board at all.
    """
    import io
    from contextlib import redirect_stdout

    from agent_supervisor import cli

    cfg_dir = os.path.join(TMP, "cli-state")
    os.makedirs(cfg_dir, exist_ok=True)
    cfg = harness(state_dir=cfg_dir)
    store = Store(os.path.join(cfg_dir, "supervisor.sqlite3"))
    store.claim_lease(23, REPO, "stack", branch="feature/issue-23-x",
                      worktree="/srv/wt/issue-23", project="mrmap-agent-23-1")
    store.update_lease(23, state="running", session="mrmap-23", pid=1, pgid=1)
    store.release_lease(23, state="finished", detail="pull request opened")
    store.track_pr(23, REPO, 70, "feature/issue-23-x", HEAD)
    store.update_pr(23, state="waiting-human", detail="build: names the pipeline: 503")

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "prs", "--json"])
    rows = json.loads(out.getvalue())
    check("prs --json answers with the tracked pull request",
          code == 0 and len(rows) == 1 and rows[0]["pr"] == 70, out.getvalue()[:200])

    store.track_pr(24, REPO, 71, "feature/issue-24-x", HEAD)
    store.update_pr(24, state="closed", detail="pull request is merged")
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["--config", cfg.path, "prs"])
    printed = out.getvalue()
    check("a closed pull request is hidden from prs", "pr #71" not in printed, printed)
    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["--config", cfg.path, "prs", "--all"])
    check("prs --all still shows it, because the row is an audit trail",
          "pr #71" in out.getvalue(), out.getvalue())

    out = io.StringIO()
    with redirect_stdout(out):
        cli.main(["--config", cfg.path, "status"])
    printed = out.getvalue()
    check("status shows the pull request under watch", "pr #70" in printed, printed[-300:])
    check("status names the one waiting for a human",
          "waiting for a human: #23" in printed, printed[-300:])

    # A red pipeline through the real command, dry: nothing may be asked.
    fake = FakeGh()
    gh.gh_json = fake.gh_json
    fake.pr(70, "feature/issue-23-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", summary="AssertionError: 500 != 200")])
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "watch-prs", "--dry-run", "--issue", "23"])
    printed = out.getvalue()
    check("watch-prs --dry-run previews the repair",
          "would-repair" in printed, printed[-200:])
    check("and the preview exits 0", code == 0, str(code))
    methods = {method for _, _, method in fake.reads}
    check("the preview read only", methods == {"GET"}, str(methods))
    check("the preview left the state as previewing",
          store.pr_row(23)["state"] == "waiting-human", str(store.pr_row(23)))

    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(["--config", cfg.path, "watch-prs", "--dry-run", "--issue", "23",
                         "--json"])
    try:
        rows = json.loads(out.getvalue())
        parsed = len(rows) == 1 and rows[0]["action"] == "would-repair"
    except ValueError:
        parsed = False
    check("watch-prs --json is exactly one JSON document the daemon can read",
          parsed and code == 0, out.getvalue()[-160:])


def test_history_does_not_become_a_scan():
    """The two bounds that keep a pass cheap enough to finish.

    A watcher that asks about every lease it ever took is a watcher that runs into
    the rate limit and then reports nothing at all. Both bounds are here so a
    daemon can run this every few minutes (#1063), and the escape hatch is naming
    the issue.
    """
    import sqlite3
    import time as clock

    from agent_supervisor.ci_monitor import LOOKBACK_S
    mon, fake, runner, wip = make()
    lease(mon.store, issue=25, branch="feature/issue-25-x")
    fake.pr(72, "feature/issue-25-x")
    fake.checks_for(HEAD, runs=[run("backend unit tests", conclusion="success")])
    check("a tracked pull request is looked up while it is being watched",
          mon.watch()[0]["action"] == "green", "seed")
    mon.store.update_pr(25, state="closed", detail="pull request is merged")
    before = len(fake.reads)
    report = mon.watch()
    check("a closed pull request is never looked up again",
          len(fake.reads) == before and report == [], str(report))
    check("and it wakes nothing", not runner.resumed)

    # A finished lease that never produced a row is only asked about for a while.
    mon.store.claim_lease(26, REPO, "stack", branch="feature/issue-26-x",
                          worktree="/srv/wt/issue-26", project="mrmap-agent-26-1")
    mon.store.update_lease(26, state="running", session="mrmap-26", pid=1, pgid=1)
    mon.store.release_lease(26, state="finished", detail="gave up, no pull request")
    old = clock.time() - LOOKBACK_S - 86400
    with sqlite3.connect(mon.store.path) as db:
        db.execute("UPDATE leases SET updated_at=? WHERE issue=?", (old, 26))
    before = len(fake.reads)
    mon.watch()
    check("a lease older than the lookup window is not asked about",
          len(fake.reads) == before, str(fake.reads[before:]))
    report = mon.watch(issue=26)
    check("naming the issue still answers, window or not",
          report[0]["action"] == "untracked" and "no open pull request" in report[0]["detail"],
          str(report))


def main():
    test_classification()
    test_one_repair()
    test_budget_of_one()
    test_budget_survives_a_restart()
    test_quiet_states()
    test_infrastructure_is_reported_not_repaired()
    test_escalation_retries_when_the_board_was_unreachable()
    test_only_our_own_pull_requests()
    test_a_running_worker_is_not_disturbed()
    test_a_resume_that_cannot_happen_is_reported()
    test_unreadable_github_changes_nothing()
    test_dry_run_changes_nothing()
    test_the_watcher_has_no_write_path()
    test_store_rules()
    test_history_does_not_become_a_scan()
    test_the_operator_commands_show_it()

    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL  {failure}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
