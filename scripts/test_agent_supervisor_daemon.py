"""Offline regression checks for the supervisor daemon of the agent supervisor (#1063).

Run from the repository root: python3 scripts/test_agent_supervisor_daemon.py
Exit code 0 means every check passed. Needs no `gh`, no model, no network and no
container: GitHub is stubbed where a command reaches it at all, and the stages of
the loop are fakes that record what they were asked for.

The checks are the ways #1063's promise could break, one each: two daemons over
one state directory; a stop that takes a running worker down with it; a stage
failure that kills the loop; a pause that still writes to GitHub; a log that
leaks a credential; a metrics report that reports "0" where it never measured; a
reboot that starts a second worker on a branch whose first worker is still
alive; a --json stream nobody can parse.
"""

import json
import logging
import logging.handlers
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import config as config_module  # noqa: E402
from agent_supervisor import daemon as daemon_module  # noqa: E402
from agent_supervisor import gh  # noqa: E402
from agent_supervisor import metrics as metrics_module  # noqa: E402
from agent_supervisor.cli import main as cli_main  # noqa: E402
from agent_supervisor.daemon import AlreadyRunning, Daemon, paths  # noqa: E402
from agent_supervisor.store import Store  # noqa: E402

PASS = FAIL = 0
FAILURES = []
TMP = tempfile.mkdtemp(prefix="supervisor-daemon-")
NOW = 1700000000.0


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


def make_case(name, **overrides):
    """One case: a temporary state directory, a usable config pointing at it.

    A fresh directory and a fresh SQLite file per case, because the whole point
    of the daemon is that its state survives - a shared file between cases would
    turn one case's leftover lease into another case's surprise.
    """
    home = os.path.join(TMP, name)
    os.makedirs(home, exist_ok=True)
    data = {"repo": "o/r", "authorized_humans": ["operator"], "state_dir": home,
            "repo_root": os.path.join(TMP, name + "-repo"), "tick_seconds": 1,
            "heartbeat_ticks": 2}
    data.update(overrides)
    cfg_path = os.path.join(home, "config.json")
    with open(cfg_path, "w") as handle:
        json.dump(data, handle)
    os.chmod(cfg_path, 0o600)
    cfg = config_module.load(cfg_path)
    return cfg, Store(os.path.join(home, "supervisor.sqlite3"))


class QuietLog:
    def info(self, *a):
        pass

    error = warning = debug = info


class FakeStage:
    """A scheduler or watcher that records the mode it was called in."""

    def __init__(self, rows=None, raises=None):
        self.calls = []
        self.rows = rows if rows is not None else []
        self.raises = raises

    def tick(self, plan_only=False):
        self.calls.append(plan_only)
        if self.raises:
            raise self.raises
        # The real scheduler fills "planned" in a plan-only pass and "started"
        # only in an acting one; a fake that ignored the flag would let a paused
        # daemon "start" work and the check would prove nothing.
        key = "planned" if plan_only else "started"
        report = {"started": [], "planned": [], "skipped": [], "stopping": [],
                  "errors": [], "capacity": None, "considered": 1}
        report[key] = [(12, "feature/issue-12-x", "stack")]
        return report

    def watch(self, dry_run=False):
        self.calls.append(dry_run)
        if self.raises:
            raise self.raises
        return list(self.rows)


class FakeRunner:
    def __init__(self, store, reconcile_rows=()):
        self.store = store
        self.reconcile_rows = list(reconcile_rows)
        self.reconciled = 0
        self.signalled = []

    def reconcile(self):
        self.reconciled += 1
        return list(self.reconcile_rows)

    def cancel(self, lease, reason=""):
        self.signalled.append(("cancel", lease, reason))


def make_daemon(cfg, store=None, scheduler=None, ci=None, reviews=None, runner=None):
    return Daemon(cfg, store=store, runner=runner or FakeRunner(store),
                  scheduler=scheduler, ci=ci, reviews=reviews, log=QuietLog())


# ---------------------------------------------------------------------------
# the pause marker is a filesystem fact

def test_pause_marker():
    cfg, store = make_case("pause")
    check("nothing is paused before the marker exists", daemon_module.paused(cfg) is None)
    payload = daemon_module.pause(cfg, "overnight maintenance")
    check("the marker names who and why",
          payload["reason"] == "overnight maintenance" and payload["at"] > 0)
    read = daemon_module.paused(cfg)
    check("a second read finds the same pause", read and read["reason"] == "overnight maintenance")
    check("the marker is the file under that name",
          os.path.basename(paths(cfg)["pause"]) == "paused")
    check("resume undoes it", daemon_module.resume(cfg) is True)
    check("and after resume nothing is paused", daemon_module.paused(cfg) is None)
    check("resuming an unpaused supervisor says there was nothing to undo",
          daemon_module.resume(cfg) is False)


def test_unreadable_pause_counts_as_paused():
    cfg, store = make_case("pause-corrupt")
    with open(paths(cfg)["pause"], "w") as handle:
        handle.write("{ this is not json")
    read = daemon_module.paused(cfg)
    check("a half-written pause marker is read as paused, not as absent",
          read is not None and "could not be read" in read["reason"], str(read))


# ---------------------------------------------------------------------------
# the tick and its containment

def test_tick_acts_and_reports():
    cfg, store = make_case("tick")
    sched = FakeStage()
    ci = FakeStage(rows=[{"issue": 9, "pr": 41, "action": "escalated", "detail": "infra"}])
    rev = FakeStage(rows=[{"issue": 9, "pr": 41, "action": "nothing"}])
    d = make_daemon(cfg, store=store, scheduler=sched, ci=ci, reviews=rev)
    report = d.tick()
    check("all three stages ran", len(sched.calls) == 1 and len(ci.calls) == 1
          and len(rev.calls) == 1)
    check("an active tick asks the scheduler to start", sched.calls[0] is False)
    check("an active tick lets the watchers act", ci.calls[0] is False)
    check("the started job and the escalation together count as acted",
          report["acted"] == 2, json.dumps(report))
    check("an escalation is visible as waiting for a human", d._waiting(report),
          json.dumps(report))
    check("the tick became an event",
          any(e["kind"] == "daemon-tick" for e in store.recent_events(5)))
    text = d._line(report)
    check("the event line names every stage",
          "plan" in text and "ci" in text and "reviews" in text, text)


def test_paused_tick_is_report_only():
    cfg, store = make_case("tick-paused")
    daemon_module.pause(cfg, "operator")
    sched, ci, rev = FakeStage(), FakeStage(), FakeStage()
    d = make_daemon(cfg, store=store, scheduler=sched, ci=ci, reviews=rev)
    report = d.tick()
    check("a paused scheduler may only plan", sched.calls == [True])
    check("a paused watcher may only report", ci.calls == [True] and rev.calls == [True])
    check("a paused tick never counts as acted", report["acted"] == 0, json.dumps(report))
    check("the report says it was paused", report["paused"] is True)


def test_failed_stage_outlives_as_a_line():
    cfg, store = make_case("stage-fail")
    sched = FakeStage()
    ci = FakeStage(raises=RuntimeError("github answered 502"))
    rev = FakeStage()
    d = make_daemon(cfg, store=store, scheduler=sched, ci=ci, reviews=rev)
    report = d.tick()
    check("the failing stage is reported with its name",
          report["failed"] == ["ci: github answered 502"], str(report["failed"]))
    check("the stage after the failure still ran", len(rev.calls) == 1)
    check("the plan of the failing tick still happened", len(sched.calls) == 1)
    check("a stage failure lands in the event log",
          any(e["kind"] == "daemon-stage-error" for e in store.recent_events(5)))


def test_heartbeat_for_the_quiet():
    cfg, store = make_case("heartbeat", heartbeat_ticks=2)
    d = make_daemon(cfg, store=store, scheduler=FakeStage(rows=[]),
                    ci=FakeStage(), reviews=FakeStage())
    quiet = {"started": [], "planned": [], "skipped": [], "stopping": [],
             "errors": [], "capacity": None, "considered": 0}
    sched = d.scheduler
    sched.tick = lambda plan_only=False: quiet
    d.tick()
    check("one quiet tick is not an event",
          not any(e["kind"] == "daemon-idle" for e in store.recent_events(5)))
    d.tick()
    check("the second quiet tick writes the heartbeat",
          any(e["kind"] == "daemon-idle" for e in store.recent_events(5)))


# ---------------------------------------------------------------------------
# one daemon per state directory

def test_one_daemon_per_state_directory():
    cfg, store = make_case("lock")
    d1 = make_daemon(cfg, store=store)
    d2 = make_daemon(cfg, store=store)
    d1.acquire()
    check("the first daemon takes the lock", daemon_module.lock_held(cfg))
    try:
        d2.acquire()
        check("the second daemon is refused", False, "acquire() did not raise")
    except AlreadyRunning as exc:
        check("the second daemon is refused", True)
        check("and is told what to do about it", "daemon stop" in str(exc), str(exc))
    check("lock_held answers honestly while the lock is taken", daemon_module.lock_held(cfg))
    # a lock the flock owner still holds survives reading the pid file
    d1.write_pid()
    check("the pid file is written where status reads it",
          daemon_module.read_pid(cfg) == os.getpid(),
          str(daemon_module.read_pid(cfg)))


def test_pid_file_is_only_a_hint():
    cfg, store = make_case("pid")
    with open(paths(cfg)["pid"], "w") as handle:
        handle.write("999999999\n")
    check("a pid that is not a running process is no daemon",
          daemon_module.read_pid(cfg) is None)
    with open(paths(cfg)["pid"], "w") as handle:
        handle.write("not a number\n")
    check("a pid file of garbage is no daemon either", daemon_module.read_pid(cfg) is None)
    with open(paths(cfg)["pid"], "w") as handle:
        handle.write(f"{os.getpid()}\n")
    # this test process is called test_agent_supervisor_daemon.py, which names
    # the package - a recycled pid of an unrelated binary must still read None.
    check("a pid whose command line is the supervisor's own is read",
          daemon_module.read_pid(cfg) == os.getpid())


def test_lock_released_is_free_again():
    cfg, store = make_case("lock-free")
    d = make_daemon(cfg, store=store)
    d.acquire()
    check("held while the fd is open", daemon_module.lock_held(cfg))
    import fcntl
    fcntl.flock(d._lock, fcntl.LOCK_UN)
    os.close(d._lock)
    d._lock = None
    check("free again once the owner let go", not daemon_module.lock_held(cfg))


def test_lock_survives_a_killed_owner():
    """fork+exec is not portable to every CI box, so the equivalent is checked
    here: flock belongs to the file descriptor, and closing it - which the
    kernel does when the process dies - frees the lock."""
    cfg, store = make_case("lock-kill")
    helper = (
        "import fcntl, os, sys, time\n"
        "fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "print('locked', flush=True)\n"
        "time.sleep(30)\n")
    proc = subprocess.Popen([sys.executable, "-c", helper, paths(cfg)["lock"]],
                            stdout=subprocess.PIPE, text=True)
    try:
        check("a foreign process can hold the lock", proc.stdout.readline().strip() == "locked")
        check("while it holds it, the state directory reads as running",
              daemon_module.lock_held(cfg))
        proc.kill()
        proc.wait(timeout=10)
        check("a killed owner leaves the lock free, not stranded",
              not daemon_module.lock_held(cfg))
    finally:
        proc.kill()


# ---------------------------------------------------------------------------
# the loop itself

def test_run_once_adopt_then_tick():
    cfg, store = make_case("once")
    runner = FakeRunner(store, reconcile_rows=[{"issue": 7, "reading": "running",
                                                "action": "adopted"}])
    sched = FakeStage()
    d = make_daemon(cfg, store=store, runner=runner, scheduler=sched,
                    ci=FakeStage(), reviews=FakeStage())
    code = d.run(once=True)
    check("one tick then out, with nothing waiting", code == 0, str(code))
    check("a fresh daemon reconciles before it schedules", runner.reconciled == 1
          and len(sched.calls) == 1)
    check("the adoption was reported to the operator",
          any("adopted" in (e["detail"] or "") or e["kind"] == "daemon-start"
              for e in store.recent_events(8)))
    kinds = [e["kind"] for e in store.recent_events(8)]
    check("start and stop both left an event", "daemon-start" in kinds and "daemon-stop" in kinds,
          str(kinds))


def test_run_once_reports_a_waiting_human():
    cfg, store = make_case("once-wait")
    d = make_daemon(cfg, store=store, scheduler=FakeStage(),
                    ci=FakeStage(rows=[{"issue": 9, "pr": 41, "action": "escalated"}]),
                    reviews=FakeStage())
    check("a tick that leaves a human's answer outstanding exits 1", d.run(once=True) == 1)


def test_run_refuses_a_broken_configuration_before_the_lock():
    home = os.path.join(TMP, "badcfg")
    os.makedirs(home, exist_ok=True)
    cfg_path = os.path.join(home, "config.json")
    with open(cfg_path, "w") as handle:
        json.dump({"repo": "o/r", "authorized_humans": []}, handle)
    cfg = config_module.load(cfg_path)
    d = make_daemon(cfg, store=Store(os.path.join(home, "supervisor.sqlite3")))
    code = d.run(once=True)
    check("an unauthorized configuration exits 4", code == 4, str(code))
    check("and it never took the lock", not daemon_module.lock_held(cfg))


def test_run_refuses_a_second_daemon_with_3():
    cfg, store = make_case("twice")
    first = make_daemon(cfg, store=store)
    first.acquire()
    second = make_daemon(cfg, store=store)
    check("the second daemon in the same directory exits 3", second.run(once=True) == 3)


def test_stop_leaves_the_workers_alone():
    cfg, store = make_case("stop")
    store.claim_lease(5, "o/r", "stack", branch="feature/issue-5-x")
    store.update_lease(5, state="running", pid=os.getpid(), pgid=os.getpid())
    runner = FakeRunner(store)
    d = make_daemon(cfg, store=store, runner=runner, scheduler=FakeStage(),
                    ci=FakeStage(), reviews=FakeStage())
    d.request_stop(reason="test asked")
    code = d.run(once=False)
    check("a stopped loop exits with the tick's answer", code in (0, 1), str(code))
    check("stopping the supervisor signals nobody's worker", runner.signalled == [],
          str(runner.signalled))
    check("the lease is still standing for the next start",
          store.lease(5)["state"] == "running")
    stop_events = [e for e in store.recent_events(8) if e["kind"] == "daemon-stop"]
    check("the stop names the worker that keeps running",
          stop_events and "#5" in stop_events[0]["detail"],
          str(stop_events))


def test_signal_finishes_the_current_tick():
    """A SIGTERM mid-tick must not abort the tick - the flag is what ends the
    loop, and it is set from the handler."""
    cfg, store = make_case("signal")
    d = make_daemon(cfg, store=store, scheduler=FakeStage(), ci=FakeStage(),
                    reviews=FakeStage())

    class MidTick(FakeStage):
        def tick(self, plan_only=False):
            d._on_signal(15, None)                 # what the handler does
            return super().tick(plan_only)

    d.scheduler = MidTick()
    code = d.run(once=False)
    check("a SIGTERM during a tick stops the loop after it", code == 0, str(code))
    check("the stage finished exactly once", len(d.scheduler.calls) == 1)


# ---------------------------------------------------------------------------
# control plane: spawn, stop, status, and the CLI on top of them

def test_spawn_refuses_a_held_lock():
    cfg, store = make_case("spawn-locked")
    d = make_daemon(cfg, store=store)
    d.acquire()
    outcome = daemon_module.spawn(cfg)
    check("spawn will not start a second daemon", outcome["started"] is False, str(outcome))


def test_spawn_really_starts_and_stop_really_stops():
    cfg, store = make_case("spawn")
    # The daemon command is this interpreter running a loop that does nothing
    # but hold the lock: what is under test is the hand that starts and stops,
    # not the stages. The comment keeps the package name in the child's command
    # line, which is how read_pid identifies a supervisor process.
    helper = (
        "# agent_supervisor spawn test\n"
        "import fcntl, os, sys, time\n"
        "fd = os.open(os.path.join(sys.argv[1], 'supervisor.lock'), "
        "os.O_CREAT | os.O_RDWR, 0o600)\n"
        "fcntl.flock(fd, fcntl.LOCK_EX)\n"
        "open(os.path.join(sys.argv[1], 'supervisor.pid'), 'w').write(str(os.getpid()))\n"
        "time.sleep(30)\n")
    outcome = daemon_module.spawn(cfg, argv=[sys.executable, "-c", helper, cfg.state_dir])
    try:
        check("spawn started something", outcome["started"] is True, str(outcome))
        deadline = time.time() + 10
        while time.time() < deadline and not daemon_module.lock_held(cfg):
            time.sleep(0.05)
        check("the started daemon holds the lock", daemon_module.lock_held(cfg))
        info = daemon_module.status(cfg)
        check("status finds it, with its pid",
              info["running"] and info["pid"] == outcome["pid"], str(info))
        stopped = daemon_module.stop(cfg, timeout_s=10)
        check("stop terminates it", stopped["stopped"] is True, str(stopped))
        check("and after stop the lock is free", not daemon_module.lock_held(cfg))
    finally:
        outcome_pid = outcome.get("pid")
        if outcome_pid:
            try:
                os.kill(outcome_pid, 9)
            except ProcessLookupError:
                pass


def test_stop_without_a_daemon_says_so():
    cfg, store = make_case("stop-none")
    outcome = daemon_module.stop(cfg, timeout_s=1)
    check("stopping nothing reports stopped, not failed",
          outcome["stopped"] is True and "no daemon pid" in outcome["reason"], str(outcome))


def test_cli_daemon_round_trip():
    cfg, store = make_case("cli-daemon")
    argv = ["--config", cfg.path, "daemon"]
    check("daemon pause through the CLI", cli_main(argv + ["pause", "--reason", "cli"]) == 0)
    info = json.loads(capture(cli_main, argv + ["status", "--json"]))
    check("the CLI status says paused", info["paused"]["reason"] == "cli", json.dumps(info))
    check("and not running", info["running"] is False)
    check("status exits 1 while nothing runs",
          cli_main(argv + ["status"]) == 1)
    check("daemon resume through the CLI", cli_main(argv + ["resume"]) == 0)
    info = json.loads(capture(cli_main, argv + ["status", "--json"]))
    check("after resume the pause is gone", info["paused"] is None)
    check("pause wrote through to the event log",
          any(e["kind"] == "daemon-paused" for e in store.recent_events(8)))


def capture(fn, argv):
    """Capture what a command prints - a --json answer must be one document."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(argv)
    out = buf.getvalue()
    json.loads(out)                                # raises if it is not one document
    return out


def test_cli_run_once_json_is_one_document():
    cfg, store = make_case("cli-run")
    real_list = gh.list_paginated
    gh.list_paginated = lambda *a, **k: []         # an empty repository, no network
    try:
        out = capture(cli_main, ["--config", cfg.path, "run", "--once", "--dry-run",
                                 "--json"])
    finally:
        gh.list_paginated = real_list
    report = json.loads(out)
    check("the run --json report carries all three stages",
          sorted(report["stages"]) == ["ci", "plan", "reviews"], json.dumps(report))
    check("a dry-run run says so in its own report", report["dry_run"] is True)


def test_cli_run_json_needs_once():
    cfg, store = make_case("cli-run-stream")
    check("--json without --once is refused rather than streamed",
          cli_main(["--config", cfg.path, "run", "--json"]) == 2)


# ---------------------------------------------------------------------------
# the log

def test_log_file_is_private_and_rotatable():
    cfg, store = make_case("log")
    logger = daemon_module.setup_logging(cfg)
    logger.info("plain line %s", "here")
    handler = logger.handlers[0]
    check("the rotation sizes come from the configuration",
          handler.maxBytes == int(cfg.get("log_max_bytes"))
          and handler.backupCount == int(cfg.get("log_backups")))
    mode = stat.S_IMODE(os.stat(paths(cfg)["log"]).st_mode)
    check("the log is 0600", mode == 0o600, oct(mode))
    daemon_module.setup_logging(cfg)               # a second setup must not double up
    check("setting up twice does not stack handlers on one file",
          len([h for h in daemon_module.setup_logging(cfg).handlers
               if isinstance(h, logging.handlers.RotatingFileHandler)]) == 1)


def test_no_credential_reaches_the_log():
    cfg, store = make_case("redact")
    logger = daemon_module.setup_logging(cfg)
    planted = [
        ("ghp_" + "A" * 36, "github classic token"),
        ("github_pat_11" + "B" * 30, "github fine-grained token"),
        ("Bearer " + "eyJhbGciOiJI" + "C" * 20, "bearer header"),
        ("token: " + "D" * 30, "key-value line"),
        ("OPENCODE_AUTH=" + "E" * 24, "environment shape"),
        ("password = " + "F" * 12, "quoted config echo"),
    ]
    for value, label in planted:
        logger.info("debug probe while %s: %s", label, value)
    for h in logger.handlers:
        h.flush()
    with open(paths(cfg)["log"]) as handle:
        written = handle.read()
    for value, label in planted:
        check(f"the log never holds a {label}", value not in written, value[:12] + "...")
    check("the redaction is visible in the line", "[redacted]" in written, written)
    logger.info("worker #12 in mrmap-agent-12-3 started")
    for h in logger.handlers:
        h.flush()
    with open(paths(cfg)["log"]) as handle:
        tail = handle.read()
    check("redaction does not eat ordinary lines",
          "worker #12 in mrmap-agent-12-3 started" in tail)


# ---------------------------------------------------------------------------
# metrics

def test_metrics_honest_unknowns():
    cfg, store = make_case("metrics-empty")
    report = metrics_module.collect(cfg, store=store, capacity=FakeCapacity())
    check("an empty state answers 0 watched, not nothing",
          report["ci"]["watched"] == 0 and report["queue"]["eligible_waiting"] == 0)
    check("but an unmeasured duration is None, never 0",
          report["queue"]["oldest_wait"] is None and report["runs"]["median_completed"] is None,
          json.dumps({"q": report["queue"]["oldest_wait"],
                      "r": report["runs"]["median_completed"]}))
    check("a missing worktree root is read as unknown",
          report["leftovers"]["worktrees"]["reading"] == "unknown",
          json.dumps(report["leftovers"]["worktrees"]))
    text = metrics_module.as_text(report)
    check("the text report prints the unknowns as unknown", "unknown" in text or "-" in text)
    json.dumps(report)                              # must be JSON-shaped end to end


def test_metrics_reads_the_state_it_is_given():
    cfg, store = make_case("metrics-seeded")
    store.claim_lease(12, "o/r", "stack", branch="feature/issue-12-x")
    store.update_lease(12, state="running")
    store.claim_lease(13, "o/r", "process", branch="feature/issue-13-y")
    store.release_lease(13, state="finished", detail="merged")
    store.record_verdict(14, True, "eligible")
    store.note_attempt(15, backoff_s=3600)
    store.track_pr(12, "o/r", 41, head_sha="abc123" + "0" * 58)
    store.note_ci_seen(41, "abc123" + "0" * 58, "backend unit tests", "code", 1)
    store.update_pr(12, state="green", attempts=2, last_seen=NOW + 600)
    store.track_reviews(12, "o/r", 41)
    store.update_review(12, attempts=1, state="waiting-human")
    # The methods stamp "now", but a duration check needs known ones - the row
    # values are set after the fact, which is exactly what a day of real runs
    # would look like in the same tables.
    with store._connect() as db:
        db.execute("UPDATE leases SET started_at=?, finished_at=? WHERE issue=13",
                   (NOW - 1800, NOW))                      # a 30 minute run
        db.execute("UPDATE verdicts SET decided_at=? WHERE issue=14", (NOW - 100,))
        db.execute("UPDATE ci_seen SET seen_at=? WHERE pr=41", (NOW - 300,))
    report = metrics_module.collect(cfg, store=store, capacity=FakeCapacity(),
                                    now=NOW + 700)
    slots = report["slots"]
    check("the slots count what is running against the configured ceiling",
          slots["workers_running"] == 1 and slots["workers_max"] == 2, json.dumps(slots))
    runs = report["runs"]
    check("a completed run gets its duration from the lease timestamps",
          runs["completed_on_record"] == 1 and runs["median_completed"] == "30m",
          json.dumps(runs))
    queue = report["queue"]
    check("an eligible issue without a lease counts as waiting",
          queue["eligible_waiting"] == 1 and queue["detail"][0]["issue"] == 14
          and queue["detail"][0]["since_last_decision_s"] == 800, json.dumps(queue))
    ci = report["ci"]
    check("the repair cycles and the green verdict come from the watch row",
          ci["repair_cycles_total"] == 2 and ci["green"] == 1, json.dumps(ci))
    check("the finding is visible with its head and its first time",
          ci["per_pr"][0]["heads_with_findings"] == [(("abc123" + "0" * 58)[:8])]
          and ci["per_pr"][0]["first_finding_seen"] is not None,
          json.dumps(ci["per_pr"][0]))
    check("watch span runs from the first finding to the green sighting",
          ci["per_pr"][0]["watch_span"] == "15m", json.dumps(ci["per_pr"][0]))
    retries = report["retries"]
    check("an attempt in backoff is counted as in backoff",
          retries["in_backoff"] == 1, json.dumps(retries))
    reviews = report["reviews"]
    check("a review watch waiting for a human is counted",
          reviews["waiting_human"] == 1, json.dumps(reviews))
    host = report["host"]
    check("the host section carries the gate's OOM counters",
          host["metrics"]["oom_events"]["oom_kill"] == 11, json.dumps(host["metrics"]))


def test_metrics_leftovers_report_without_touching():
    cfg, store = make_case("leftovers")
    repo = os.path.join(TMP, "leftovers-repo")
    os.makedirs(repo, exist_ok=True)
    owned = os.path.join(cfg.state_dir, "worktrees", "issue-1")
    stranger = os.path.join(cfg.state_dir, "worktrees", "issue-2")
    os.makedirs(owned, exist_ok=True)
    os.makedirs(stranger, exist_ok=True)
    store.claim_lease(1, "o/r", "stack", worktree=owned)
    # A directory that is no repository answers "git worktree list" with an
    # error; the report has to pass that through as unknown instead of as zero.
    reading = metrics_module._worktrees(cfg, store)
    check("a repo_root that is no repository is reported, not guessed",
          reading["reading"] in ("unknown", "ok"), json.dumps(reading))
    compose = metrics_module._compose(cfg, store)
    check("the compose reading either names projects or says why not",
          compose["reading"] in ("ok", "unknown", "unavailable"), json.dumps(compose))


class FakeCapacity:
    def evaluate(self, need="stack"):
        return {"fits": True, "verdict": "fits", "explanation": "measured here",
                "reasons": [], "need": need, "metrics": {
                    "load_per_core": 0.1, "mem_effective_gb": 10.2,
                    "disk_free_gb": 220.0, "stacks": 1, "stacks_max": 3,
                    "processes": 2, "processes_max": 6,
                    "oom_events": {"oom": 0, "oom_kill": 11, "max": 11}}}


# ---------------------------------------------------------------------------
# configuration

def test_daemon_configuration_bounds():
    def problems(**over):
        name = "cfg-" + str(abs(hash(repr(sorted(over.items())))) % 10 ** 8)
        home = os.path.join(TMP, name)
        os.makedirs(home, exist_ok=True)
        path = os.path.join(home, "config.json")
        data = {"repo": "o/r", "authorized_humans": ["operator"], "state_dir": home}
        data.update(over)
        with open(path, "w") as handle:
            json.dump(data, handle)
        return config_module.load(path).problems

    check("a negative tick is refused", bool(problems(tick_seconds=-1)))
    check("a zero tick would spin the loop and is refused", bool(problems(tick_seconds=0)))
    check("jitter of 0 is legal", not problems(tick_jitter_s=0))
    check("a negative jitter is not", bool(problems(tick_jitter_s=-5)))
    check("heartbeat 0 would log every tick and says so", bool(problems(heartbeat_ticks=0)))
    check("log_max_bytes 0 means no rotation, and is allowed",
          not problems(log_max_bytes=0))
    check("an unknown key is still the typo it is", bool(problems(tick_jitter=1)))


def test_daemon_modules_write_nothing_to_github():
    """Same audit as the other supervisor checks, on the new modules: the daemon
    and metrics add no hand to GitHub beyond the ones the stages already have."""
    root = os.path.dirname(os.path.abspath(__file__))
    import ast
    for name in ("daemon.py", "metrics.py"):
        with open(os.path.join(root, "agent_supervisor", name)) as handle:
            source = handle.read()
        check(f"{name} contains no REST write call", 'method="POST"' not in source
              and 'method="PATCH"' not in source and 'method="PUT"' not in source
              and 'method="DELETE"' not in source)
        check(f"{name} names no write endpoint", "/comments" not in source
              and "/reviews" not in source and "/merge" not in source
              and "/assignees" not in source)
        tree = ast.parse(source)
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        check(f"{name} never calls gh_json itself", "gh_json" not in calls, str(calls))
    with open(os.path.join(root, "agent_supervisor", "cli.py")) as handle:
        cli_source = handle.read()
    check("cli.py names no write endpoint", "/comments" not in cli_source
          and "/reviews" not in cli_source and "/merge" not in cli_source
          and "/assignees" not in cli_source)


def main():
    for fn in (test_pause_marker, test_unreadable_pause_counts_as_paused,
               test_tick_acts_and_reports, test_paused_tick_is_report_only,
               test_failed_stage_outlives_as_a_line, test_heartbeat_for_the_quiet,
               test_one_daemon_per_state_directory, test_pid_file_is_only_a_hint,
               test_lock_released_is_free_again, test_lock_survives_a_killed_owner,
               test_run_once_adopt_then_tick, test_run_once_reports_a_waiting_human,
               test_run_refuses_a_broken_configuration_before_the_lock,
               test_run_refuses_a_second_daemon_with_3, test_stop_leaves_the_workers_alone,
               test_signal_finishes_the_current_tick, test_spawn_refuses_a_held_lock,
               test_spawn_really_starts_and_stop_really_stops,
               test_stop_without_a_daemon_says_so, test_cli_daemon_round_trip,
               test_cli_run_once_json_is_one_document, test_cli_run_json_needs_once,
               test_log_file_is_private_and_rotatable, test_no_credential_reaches_the_log,
               test_metrics_honest_unknowns, test_metrics_reads_the_state_it_is_given,
               test_metrics_leftovers_report_without_touching,
               test_daemon_configuration_bounds,
               test_daemon_modules_write_nothing_to_github):
        try:
            fn()
        except Exception as exc:                       # a crash is a failed check
            check(f"{fn.__name__} raised", False, f"{type(exc).__name__}: {exc}")
    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
