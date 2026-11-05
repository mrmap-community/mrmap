"""Offline regression checks for the scheduler of the agent supervisor (#1059).

Run from the repository root: python3 scripts/test_agent_supervisor_scheduler.py
Exit code 0 means every check passed. Needs no `gh`, no network, no docker and no
OpenCode: GitHub reads, the claim board, the capacity gate and the runner are all
stubs in this file, and the SQLite state lives in a temporary directory.

The scheduler is where "may we?" meets "should we, now?". These checks follow the
acceptance of #1059 and are written as the failures that matter: starting an
issue nobody approved, starting an issue somebody else holds, starting the same
issue twice from two processes or across a restart, starting a heavy stack the
host cannot carry, and running on after a human withdrew the approval.
"""

import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import gh                                       # noqa: E402
from agent_supervisor.capacity import NEED_STACK                     # noqa: E402
from agent_supervisor.config import load as load_config              # noqa: E402
from agent_supervisor.scheduler import Scheduler, StartError         # noqa: E402
from agent_supervisor.store import Store                             # noqa: E402

PASS = FAIL = 0
FAILURES = []
NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
TMP = tempfile.mkdtemp(prefix="supervisor-scheduler-tests-")


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
    """Answers the issue listing, the issue, the timeline and the permission
    lookup, and counts what was read so the rate-limit behaviour is checkable."""

    def __init__(self):
        self.issues = {}            # number -> issue payload
        self.events = {}            # number -> [label events]
        self.unreadable_timeline = set()
        self.reads = []
        self.list_reads = 0

    def add(self, number, labels=("agent: approved",), state="open", created="2026-11-01T10:00:00Z",
            approver="human", action="labeled", actor_type="User", title=None,
            blocked_by=None, events=None):
        payload = {"number": number, "state": state, "created_at": created,
                   "title": title or f"issue {number}",
                   "labels": [{"name": name} for name in labels]}
        if blocked_by:
            payload["dependencies"] = {"blocked_by": blocked_by}
        self.issues[number] = payload
        if events is not None:
            self.events[number] = events
        else:
            self.events[number] = [label_event(approver, action, actor_type)]

    def gh_json(self, path, params=None, method="GET", accept=None, timeout=None):
        self.reads.append(path)
        if path == "user":
            return {"login": "mrmap-agent-bot"}
        if path.startswith("repos/o/r/issues/") and path.endswith("/timeline"):
            number = _number_of(path)
            if number in self.unreadable_timeline:
                raise gh.GhError("stub: rate limited", "ratelimit")
            if number not in self.events:
                raise gh.GhError("stub: no timeline", "notfound")
            return self.events[number]
        if path.startswith("repos/o/r/issues/"):
            number = _number_of(path)
            if number not in self.issues:
                raise gh.GhError("stub: no such issue", "notfound")
            return self.issues[number]
        if "/collaborators/" in path:
            return {"permission": "admin", "role_name": "Admin"}
        raise gh.GhError(f"stub: unhandled {path}", "api")

    def list_paginated(self, path, params=None):
        if path == "repos/o/r/issues":
            self.reads.append(path)
            self.list_reads += 1
            return [issue for number, issue in sorted(self.issues.items())
                    if issue["state"] == "open"]
        if path.endswith("/timeline"):
            # no extra read entry: gh_json records the call this page loop makes
            return self.gh_json(path, params)
        raise gh.GhError(f"stub: unhandled list {path}", "api")


class FakeClaims:
    """The board: which issues somebody else holds."""

    def __init__(self, fresh=None, stale=None, unreadable=False):
        self.fresh = {int(k): v for k, v in (fresh or {}).items()}
        self.stale = {int(k): v for k, v in (stale or {}).items()}
        self.unreadable = unreadable
        self.calls = 0

    def claims_on(self, numbers):
        self.calls += 1
        if self.unreadable:
            raise RuntimeError("gh: board is not answering")
        out = {}
        for number in numbers:
            entries = [("c%d" % i, {"client": holder, "state": "wip"})
                       for i, holder in enumerate(self.fresh.get(number, []) +
                                                  self.stale.get(number, []))]
            out[number] = entries
        return out

    def holders(self, payloads):
        stale_names = {holder for holders in self.stale.values() for holder in holders}
        fresh, stale = [], []
        for _comment_id, payload in (payloads or []):
            holder = payload.get("client")
            (stale if holder in stale_names else fresh).append(holder)
        return fresh, stale

    def stale_claims(self, payloads):
        return self.holders(payloads)[1]

    def blocked_by_other(self, payloads, our_client=None):
        fresh, _stale = self.holders(payloads)
        return any(holder != our_client for holder in fresh)

    def our_client_tag(self, worktree):
        return "this-host:mrmap-" + os.path.basename(worktree)


class FakeCapacity:
    """Answers like scripts/agent_capacity (#1053) does; the adapter around the
    real script is checked by scripts/test_agent_supervisor_capacity.py."""

    def __init__(self, fits=True, explanation="mem 11.2G of 16.0G (cgroup), stacks 0/3"):
        self.fits = fits
        self.explanation = explanation
        self.asks = []

    def evaluate(self, need=NEED_STACK):
        self.asks.append(need)
        if self.fits is None:
            return {"fits": False, "verdict": "error", "explanation": "the gate did not answer",
                    "reasons": [], "need": need, "metrics": {}, "source": "refused"}
        return {"fits": self.fits, "verdict": "fits" if self.fits else "busy",
                "explanation": self.explanation,
                "reasons": [] if self.fits else ["the host is full"],
                "need": need,
                "metrics": {"need": need, "mem_effective_gb": 11.2, "stacks": 0,
                            "stacks_max": 1, "load_per_core": 0.3},
                "source": "json"}


class FakeRunner:
    def __init__(self, fail=None):
        self.started = []
        self.cancelled = []
        self.fail = fail or {}

    def start(self, job):
        if job.number in self.fail:
            raise StartError(self.fail[job.number])
        self.started.append(job)
        return {"pid": 4000 + job.number, "pgid": 5000 + job.number,
                "session": f"ses_{job.number}", "project": job.project,
                "worktree": job.worktree, "branch": job.branch}

    def cancel(self, lease, reason):
        self.cancelled.append((lease["issue"], reason))


def label_event(who="human", action="labeled", actor_type="User", when=NOW,
                name="agent: approved"):
    return {"event": action, "label": {"name": name},
            "actor": {"login": who, "type": actor_type},
            "created_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")}


def _number_of(path):
    return int(path.split("/issues/")[1].split("/")[0])


def harness(**overrides):
    """A configuration file, a state file and a scheduler over the given stubs."""
    data = {"repo": "o/r", "authorized_humans": ["human"], "agent_accounts": ["mrmap-agent-bot"],
            "repo_root": "/srv/mrmap", "opencode_model": "p/m",
            "require_repo_association": False, "verdict_cache_s": 0,
            "state_dir": TMP, "worktree_root": "/srv/agent-worktrees"}
    data.update(overrides)
    path = os.path.join(TMP, f"cfg-{abs(hash(json.dumps(data, sort_keys=True)))}.json")
    with open(path, "w") as handle:
        json.dump(data, handle)
    os.chmod(path, 0o600)
    return load_config(path)


_STORES = [0]


def make(cfg, fake, claims=None, capacity=None, runner=None, store=None):
    """A scheduler over fresh stubs. A state file of its own unless one is given:
    checks about leases and restarts pass the same Store twice, everything else
    must not inherit another check's leases."""
    gh.gh_json = fake.gh_json
    gh.list_paginated = fake.list_paginated
    if store is None:
        _STORES[0] += 1
        store = Store(os.path.join(TMP, f"state-{_STORES[0]}.sqlite3"))
    return Scheduler(cfg, store=store, capacity=capacity or FakeCapacity(),
                     claims=claims or FakeClaims(), runner=runner)


def started(report):
    """Every issue this tick would run or did run. Most checks below do not care
    whether a runner exists - they care that the *decision* was to take the issue."""
    return sorted({entry[0] for entry in report["started"]}
                  | {entry[0] for entry in report["planned"]})


def skipped(reason, report):
    return [number for number, kind, _detail in report["skipped"] if kind == reason]


# ---------------------------------------------------------------------------

def test_never_starts_unapproved():
    fake = FakeGh()
    fake.add(1001, approver="human")
    fake.add(1002, labels=())                       # nobody approved this one
    fake.add(1003, approver="stranger")             # a person, but not an approver
    fake.add(1004, actor_type="Bot")                # a bot approved it
    fake.add(1005, action="unlabeled")              # approved, then revoked
    fake.add(1006, labels=("agent: approved", "agent: paused"))
    fake.add(1007, state="closed")
    scheduler = make(harness(), fake)
    report = scheduler.tick()
    check("only the approved issue starts", started(report) == [1001], str(report["started"]))
    check("an unlabelled issue is refused", 1002 in skipped("no-approval-label", report),
          str(report["skipped"]))
    check("a stranger's approval is refused",
          1003 in skipped("unauthorized-approver", report), str(report["skipped"]))
    check("a bot's approval is refused",
          1004 in skipped("non-human-approver", report), str(report["skipped"]))
    check("a revoked approval is refused",
          1005 in skipped("approval-revoked", report), str(report["skipped"]))
    check("a paused issue is refused", 1006 in skipped("paused", report), str(report["skipped"]))


def test_blocking_links_are_ignored():
    fake = FakeGh()
    fake.add(1010, blocked_by=[{"number": 999, "state": "open"}])
    scheduler = make(harness(), fake)
    report = scheduler.tick()
    check("a blocked-by relation does not hold the queue", started(report) == [1010],
          str(report["started"]))
    check("the scheduler never reads blocking relations",
          not [p for p in fake.reads if "depend" in p or "block" in p], str(fake.reads))


def test_claims():
    fake = FakeGh()
    fake.add(1020)
    fake.add(1021)
    claims = FakeClaims(fresh={1021: ["vscode-codex:mrmap"]})
    scheduler = make(harness(), fake, claims=claims)
    report = scheduler.tick()
    check("a live claim by another client is respected", started(report) == [1020],
          str(report["started"]))
    check("the reason names the holder",
          any("vscode-codex" in detail for number, kind, detail in report["skipped"]),
          str(report["skipped"]))

    claims = FakeClaims(stale={1021: ["old-host:mrmap"]})
    report = make(harness(max_test_stacks=2, max_opencode_processes=2), fake,
                  claims=claims).tick()
    check("a stale claim only warns", started(report) == [1020, 1021], str(report["started"]))

    claims = FakeClaims(unreadable=True)
    report = make(harness(), fake, claims=claims).tick()
    check("an unreadable board starts nothing", not report["started"], str(report["started"]))
    check("and says why", any("board" in error for error in report["errors"]),
          str(report["errors"]))


def test_whose_claim_is_it():
    """A claim is judged by who filed it, not by whose machine it came from.

    `scripts/wip` names a client after the machine and the worktree, so two
    things that look alike have to be told apart: the worker this supervisor
    started, filing its claim from the worktree it was given, and a developer
    sitting at the same host with their own checkout of the same issue. The
    second one is exactly the work a supervisor must not double, so a host
    prefix buys no priority - only the worktree the job was assigned does.
    """
    fake = FakeGh()
    fake.add(1040)
    cfg = harness()
    store = Store(os.path.join(TMP, "whose-claim.sqlite3"))
    report = make(cfg, fake, runner=FakeRunner(), store=store).tick()
    check("the first tick starts it", started(report) == [1040], str(report["started"]))

    # the fake's rule is "this-host:mrmap-" + worktree basename, and the
    # supervisor assigns <worktree_root>/issue-<number>, which is what the worker
    # will file its claim under
    our_tag = "this-host:mrmap-issue-1040"
    claims = FakeClaims(fresh={1040: [our_tag]})
    report = make(cfg, fake, runner=FakeRunner(), store=store, claims=claims).tick()
    check("our own worker's claim does not read as somebody else's work",
          1040 not in [n for n, reason, _ in report["skipped"]
                       if reason == "claimed-elsewhere"], str(report["skipped"]))
    check("and the reason that is given is the lease", 1040 in skipped("held-here", report),
          str(report["skipped"]))

    other = FakeGh()
    other.add(1041)
    same_host = FakeClaims(fresh={1041: ["this-host:mrmap-1041"]})
    report = make(cfg, other, claims=same_host).tick()
    check("a claim from this machine's own editor still stops the start",
          1041 in skipped("claimed-elsewhere", report), str(report["skipped"]))
    check("and it names the holder", "this-host:mrmap-1041"
          in str([detail for _n, _r, detail in report["skipped"]]), str(report["skipped"]))


def test_no_double_start():
    fake = FakeGh()
    fake.add(1030)
    cfg = harness()
    store = Store(os.path.join(TMP, "double.sqlite3"))
    runner = FakeRunner()
    first = make(cfg, fake, runner=runner, store=store)
    report = first.tick()
    check("the first tick starts it once", started(report) == [1030], str(report["started"]))
    report = first.tick()
    check("a second tick does not start it again", not report["started"]
          and 1030 in skipped("held-here", report), str(report["skipped"]))

    # a second process: same state file, its own Scheduler object
    runner_b = FakeRunner()
    other = make(cfg, fake, runner=runner_b, store=Store(os.path.join(TMP, "double.sqlite3")))
    report = other.tick()
    check("a second process does not start it either", not report["started"], str(report))
    check("only one runner was ever called", len(runner.started) + len(runner_b.started) == 1,
          f"{len(runner.started)} + {len(runner_b.started)}")

    # restart safety across a fresh Store on the same file, after a crash
    store.update_lease(1030, state="running", pid=1234)
    revived = make(cfg, fake, runner=FakeRunner(), store=Store(os.path.join(TMP, "double.sqlite3")))
    report = revived.tick()
    check("a restart does not start a running issue again", not report["started"], str(report))


def test_capacity():
    fake = FakeGh()
    fake.add(1040)
    busy = FakeCapacity(fits=False, explanation="mem 1.2G effective of 16G -> busy")
    report = make(harness(), fake, capacity=busy).tick()
    check("a busy host starts nothing", not report["started"], str(report))
    check("and the reason is the gate's own line",
          busy.explanation in report["capacity"]["explanation"], str(report["capacity"]))

    broken = FakeCapacity(fits=None)
    report = make(harness(), fake, capacity=broken).tick()
    check("a gate that cannot answer is not permission", not report["started"], str(report))

    capacity = FakeCapacity(fits=True)
    make(harness(), fake, capacity=capacity).tick()
    check("the heavy class is what is asked for", capacity.asks == [NEED_STACK], str(capacity.asks))

    # a running stack already fills the single configured slot
    store = Store(os.path.join(TMP, "slots.sqlite3"))
    store.claim_lease(1041, "o/r", NEED_STACK, branch="agent/issue-1041-x")
    store.update_lease(1041, state="running")
    runner = FakeRunner()
    report = make(harness(max_test_stacks=1, max_opencode_processes=2), fake,
                  capacity=FakeCapacity(True), runner=runner, store=store).tick()
    check("a second stack is refused at max_test_stacks", not report["started"], str(report))

    store2 = Store(os.path.join(TMP, "slots2.sqlite3"))
    store2.claim_lease(1042, "o/r", NEED_STACK, branch="agent/issue-1042-x")
    store2.update_lease(1042, state="running")
    report = make(harness(max_test_stacks=2, max_opencode_processes=1), fake,
                  capacity=FakeCapacity(True), runner=FakeRunner(), store=store2).tick()
    check("the process ceiling is respected too", not report["started"], str(report))


def test_order_and_limits():
    fake = FakeGh()
    fake.add(1050, created="2026-10-01T10:00:00Z")
    fake.add(1051, created="2026-09-01T10:00:00Z")
    fake.add(1052, created="2026-11-01T10:00:00Z", labels=("agent: approved", "priority: critical"))
    store = Store(os.path.join(TMP, "order.sqlite3"))
    runner = FakeRunner()
    cfg = harness(max_test_stacks=3, max_opencode_processes=3)
    report = make(cfg, fake, capacity=FakeCapacity(True), runner=runner, store=store).tick()
    check("priority first, then oldest, then by number",
          [number for number, _b, _n in report["started"]] == [1052, 1051, 1050],
          str(report["started"]))

    fake = FakeGh()
    for number in range(1060, 1070):
        fake.add(number)
    cfg = harness(max_candidates_per_tick=3, max_test_stacks=9, max_opencode_processes=9)
    store = Store(os.path.join(TMP, "limit.sqlite3"))
    report = make(cfg, fake, capacity=FakeCapacity(True), runner=FakeRunner(), store=store).tick()
    check("one tick reads a bounded number of issues", len(report["started"]) == 3,
          str(report["started"]))
    check("the rest is reported as waiting, not lost",
          any(kind == "per-tick-limit" for _n, kind, _d in report["skipped"]), str(report["skipped"]))


def test_withdrawal_midflight():
    fake = FakeGh()
    fake.add(1080)
    runner = FakeRunner()
    store = Store(os.path.join(TMP, "withdraw.sqlite3"))
    cfg = harness()
    scheduler = make(cfg, fake, runner=runner, store=store)
    scheduler.tick()
    lease = store.lease(1080)
    check("the lease remembers the worktree and branch",
          lease["worktree"].endswith("issue-1080") and lease["branch"].startswith("agent/"),
          str(lease))

    fake.issues[1080]["labels"].append({"name": "agent: paused"})
    report = make(cfg, fake, runner=runner, store=store).tick()
    check("a pause mid-flight stops the work", [number for number, _ in report["stopping"]] == [1080],
          str(report["stopping"]))
    check("the runner is asked to cancel, with the reason",
          runner.cancelled and runner.cancelled[0][0] == 1080
          and "paused" in runner.cancelled[0][1], str(runner.cancelled))
    after = store.lease(1080)
    check("the branch and worktree survive the stop",
          after["worktree"] == lease["worktree"] and after["branch"] == lease["branch"], str(after))
    check("the lease is marked stopping, not deleted", after["state"] == "stopping", str(after))

    # the human then removes the approval as well: still one stop, not two
    fake.events[1080] = [label_event("human"), label_event("human", action="unlabeled")]
    second = make(cfg, fake, claims=FakeClaims(), runner=runner, store=store).tick()
    check("a second tick does not cancel it twice",
          [reason for number, reason in second["stopping"]] == ["already stopping"],
          str(second["stopping"]))
    check("and the runner is asked once", len(runner.cancelled) == 1, str(runner.cancelled))


def test_failure_and_backoff():
    fake = FakeGh()
    fake.add(1090)
    store = Store(os.path.join(TMP, "backoff.sqlite3"))
    runner = FakeRunner(fail={1090: "the worktree could not be created"})
    report = make(harness(retry_backoff_s=600), fake, runner=runner, store=store).tick()
    check("a failed start is reported, not swallowed", report["errors"], str(report))
    check("a failed start releases the lease", store.lease(1090)["state"] == "failed",
          str(store.lease(1090)))
    report = make(harness(retry_backoff_s=600), fake, runner=FakeRunner(), store=store).tick()
    check("the issue is not retried immediately", 1090 in skipped("in-backoff", report),
          str(report["skipped"]))
    store.reset_attempts(1090)
    report = make(harness(retry_backoff_s=600), fake, runner=FakeRunner(), store=store).tick()
    check("and it is tried again once the backoff passed", started(report) == [1090],
          str(report["started"]))
    check("a successful start clears the attempt counter",
          (store.verdict(1090) or {}).get("attempts", 0) == 0, str(store.verdict(1090)))


def test_plan_only_and_auditing():
    fake = FakeGh()
    fake.add(1100)
    store = Store(os.path.join(TMP, "plan.sqlite3"))
    runner = FakeRunner()
    report = make(harness(), fake, runner=runner, store=store).tick(plan_only=True)
    check("plan mode reports the plan", [number for number, _b, _n in report["planned"]] == [1100],
          str(report["planned"]))
    check("plan mode starts nothing", not runner.started, str(runner.started))
    check("plan mode takes no lease", store.lease(1100) is None, str(store.status()["leases"]))

    make(harness(), fake, runner=runner, store=store).tick()
    kinds = [event["kind"] for event in store.recent_events(limit=30)]
    check("every decision is in the event log",
          {"started", "tick"} <= set(kinds), str(kinds))
    check("the audit trail says what was considered",
          any("considered" in (event.get("detail") or "") for event in store.recent_events(30)),
          str(kinds))


def test_rate_limit_politeness():
    """One listing per tick, and a refusal nobody could have changed since the
    last tick is not read again."""
    fake = FakeGh()
    fake.add(1110, events=[])                        # labelled, but no history at all
    cfg = harness(verdict_cache_s=600)
    store = Store(os.path.join(TMP, "polite.sqlite3"))
    make(cfg, fake, store=store).tick()
    first = [read for read in fake.reads if read.endswith("/timeline")]
    check("a refusal with no history is read once", len(first) == 1, str(fake.reads))
    before = len(fake.reads)
    make(cfg, fake, store=store).tick()
    check("the second tick does not read it again",
          not [read for read in fake.reads[before:] if read.endswith("/timeline")],
          str(fake.reads[before:]))
    check("and still only lists the candidates once per tick",
          sum(1 for read in fake.reads[before:] if read == "repos/o/r/issues") == 1,
          str(fake.reads[before:]))

    # a refusal whose cause is GitHub being unreadable must be tried again
    fake2 = FakeGh()
    fake2.add(1120, events=[])
    fake2.unreadable_timeline = {1120}
    store2 = Store(os.path.join(TMP, "polite2.sqlite3"))
    make(cfg, fake2, store=store2).tick()
    before = len(fake2.reads)
    make(cfg, fake2, store=store2).tick()
    check("a transient refusal is never cached",
          [read for read in fake2.reads[before:] if read.endswith("/timeline")],
          str(fake2.reads[before:]))

    # expiry: after the window the same refusal is read again
    aged = Store(os.path.join(TMP, "polite3.sqlite3"))
    make(harness(verdict_cache_s=600), fake, store=aged).tick()
    aged.record_verdict(1110, False, "history-incomplete")
    with aged() as db:
        db.execute("UPDATE verdicts SET decided_at=? WHERE issue=1110", (0,))
    before = len(fake.reads)
    make(harness(verdict_cache_s=600), fake, store=aged).tick()
    check("a stale cache entry is refreshed",
          [read for read in fake.reads[before:] if read.endswith("/timeline")],
          str(fake.reads[before:]))


def main():
    for fn in (test_never_starts_unapproved, test_blocking_links_are_ignored, test_claims,
               test_whose_claim_is_it, test_no_double_start, test_capacity,
               test_order_and_limits, test_withdrawal_midflight, test_failure_and_backoff,
               test_plan_only_and_auditing, test_rate_limit_politeness):
        out = io.StringIO()
        with redirect_stdout(out):
            fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
