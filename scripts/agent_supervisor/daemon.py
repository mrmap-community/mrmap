"""Run the supervisor on a timer, and stop it again in one piece (#1063).

Everything before this module was a command a human ran. This is the hand that runs
it without one: a tick, a sleep, and a repeat - the scheduler starting what is
approved and fits, the CI watcher, the review watcher. Four properties decide the
shape of the code, and each of them is here because the naive version fails in a
specific way:

*One daemon per state file.* Two supervisors over one SQLite file are the double
scheduling the lease's primary key was meant to prevent, and the claim board cannot
see a second local process in time. So the loop holds ``flock`` on a lock file in
the state directory for its whole life: the second daemon learns about it before it
reads GitHub, and that is also what ``daemon start`` uses to answer "is one
running?".

*A stop must not be a disaster.* The workers are the work; a daemon that takes them
down on ``systemctl stop`` destroys forty minutes of an agent's run for the crime of
restarting the service. So a stop request sets a flag, the current tick finishes its
stage boundaries, the loop exits, and the running workers are left alone - the next
start adopts them through ``reconcile``, which is the same path a reboot takes.

*A bad stage must not kill the loop.* GitHub answers a rate limit, Compose is busy,
one issue's payload has a shape nobody predicted: a daemon that dies on that needs a
human every night, which is the thing this issue exists to remove. Every stage runs
inside its own containment, its failure is recorded as an event and in the tick
report, and the next stage still runs. What is *not* contained is the approval gate:
a stage that cannot tell whether an issue is authorized starts nothing, and the
refusal is the report.

*Paused means no writes, not no looking.* While the pause marker exists the watchers
still read and still record, and the scheduler still plans - all of them in
report-only mode. An operator who paused the supervisor wants the queue to keep
making sense and wants nothing to happen; a pause that posts a question comment is
neither.

The log is one rotating file next to the state, mode ``0600``, with a filter that
redacts anything credential-shaped before it is written. The supervisor holds no
credentials itself - GitHub goes through the host's ``gh``, OpenCode through its own
- so the filter is not the design, it is the guarantee that a future log line cannot
undo the design.
"""

import fcntl
import json
import logging
import logging.handlers
import os
import random
import re
import signal
import subprocess
import sys
import threading
import time

from .ci_monitor import Monitor
from .config import CONFIG_ENV
from .reviews import Reviews
from .runner import Runner
from .scheduler import Scheduler
from .store import Store

PAUSE_FILE = "paused"
PID_FILE = "supervisor.pid"
LOCK_FILE = "supervisor.lock"
LOG_FILE = "supervisor.log"

# What one tick runs, in the order that spends the cheapest information first: the
# scheduler needs the slots the running workers occupy, and the watchers should see
# a pull request whose worker was stopped by this same tick only on the next pass.
STAGES = ("plan", "ci", "reviews")


class AlreadyRunning(Exception):
    """Another daemon holds the state directory's lock."""


def paths(cfg):
    """The four files one supervisor owns, all inside its state directory."""
    return {"log": os.path.join(cfg.state_dir, LOG_FILE),
            "pid": os.path.join(cfg.state_dir, PID_FILE),
            "lock": os.path.join(cfg.state_dir, LOCK_FILE),
            "pause": os.path.join(cfg.state_dir, PAUSE_FILE)}


# ---------------------------------------------------------------------------
# logging

CREDENTIAL_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"),
    # Before the key-value pattern: "Authorization: Bearer <token>" would
    # otherwise lose the word "Bearer" to it and write the token out whole.
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{12,}"),
    # Any key whose *name* says it holds a secret, in either shape a line can
    # carry it: "token: x" or "OPENCODE_AUTH=x". The lookahead keeps "author" -
    # a column the review watcher really logs - out of the match.
    re.compile(r"(?i)\b\w*(?:token|secret|password|passwd|credential|api[-_ ]?key"
               r"|authorization|auth(?!or))\w*\s*[:=]\s*\S+"),
)


class RedactingFilter(logging.Filter):
    """Never let a credential reach the file, whatever a later line logs.

    The supervisor holds no credentials by design, so this filter should never fire.
    It exists because "should never" is not a property of a log file: one debug line
    added a year from now that prints an environment or a request header would
    otherwise sit in a 0600 file that an operator backs up.
    """

    def filter(self, record):
        message = record.getMessage()
        # Several passes, because one pattern's replacement can expose the next
        # one's shape; the loop stops when a pass changes nothing.
        for _ in range(len(CREDENTIAL_PATTERNS) + 1):
            before = message
            for pattern in CREDENTIAL_PATTERNS:
                message = pattern.sub("[redacted]", message)
            if message == before:
                break
        if message != record.getMessage():
            record.msg = message
            record.args = ()
            record.__dict__["redacted"] = True
        return True


def setup_logging(cfg, foreground=False):
    """The daemon's logger: one rotating file, plus stderr in the foreground.

    The file is created with mode ``0600`` *before* the handler opens it, because a
    log line naming worktree paths and issue titles is operator material, and the
    state directory's default permissions are not a promise about this file.
    """
    log_path = paths(cfg)["log"]
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    if not os.path.exists(log_path):
        handle = os.open(log_path, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o600)
        os.close(handle)
    logger = logging.getLogger("mrmap-agent-supervisor")
    logger.setLevel(logging.INFO)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                  datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    rotating = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=int(cfg.get("log_max_bytes") or 0),
        backupCount=int(cfg.get("log_backups") or 0))
    rotating.setFormatter(formatter)
    rotating.addFilter(RedactingFilter())
    logger.addHandler(rotating)
    if foreground:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        stream.addFilter(RedactingFilter())
        logger.addHandler(stream)
    logger.propagate = False
    return logger


# ---------------------------------------------------------------------------
# the pause marker - module level, because pausing is a filesystem act

def pause(cfg, reason="operator paused the supervisor"):
    """Stop all writes, keep reading. Filesystem, not signal: it survives a
    restart, which is the difference between a pause and a pause until reboot.

    A daemon does not have to be running for this to mean something - pausing
    while nothing runs is how an operator says "whatever starts next, start
    quiet".
    """
    payload = {"at": time.time(), "reason": reason, "by_pid": os.getpid()}
    os.makedirs(cfg.state_dir, exist_ok=True)
    with open(paths(cfg)["pause"], "w") as handle:
        json.dump(payload, handle)
    return payload


def resume(cfg):
    """Undo ``pause``. Returns whether there was anything to undo."""
    try:
        os.unlink(paths(cfg)["pause"])
    except FileNotFoundError:
        return False
    return True


def paused(cfg):
    """The pause marker's content, or ``None`` when nothing is paused.

    An unreadable marker counts as paused: a half-written file means somebody
    meant to stop the writes, and the wrong-direction mistake is to keep acting.
    """
    try:
        with open(paths(cfg)["pause"]) as handle:
            return json.load(handle) or {}
    except FileNotFoundError:
        return None
    except (ValueError, OSError):
        return {"reason": "the pause marker could not be read, read as paused"}


# ---------------------------------------------------------------------------
# the loop

class Daemon:
    """One process's worth of supervisor: plan, watch, sleep, repeat."""

    def __init__(self, cfg, store=None, runner=None, scheduler=None, ci=None,
                 reviews=None, log=None):
        self.cfg = cfg
        self.store = store or Store.for_config(cfg)
        self.runner = runner or Runner(cfg, store=self.store)
        self.scheduler = scheduler or Scheduler(cfg, store=self.store, runner=self.runner)
        self.ci = ci or Monitor(cfg, store=self.store, runner=self.runner)
        self.reviews = reviews or Reviews(cfg, store=self.store, runner=self.runner)
        self.log = log or setup_logging(cfg)
        self._stopping = threading.Event()
        self._quiet_ticks = 0
        self._lock = None
        self._stop_reason = ""
        self.last_report = None

    # -- pause marker (the module functions are the act; these are the calls
    # a running loop makes, with the event log it owes the operator)

    def pause(self, reason="operator paused the supervisor"):
        payload = pause(self.cfg, reason)
        self.store.event("daemon-paused", reason)
        self.log.info("paused: %s", reason)
        return payload

    def resume(self):
        """Undo ``pause``. Returns whether there was anything to undo."""
        if not resume(self.cfg):
            return False
        self.store.event("daemon-resumed", "watchers and starts are active again")
        self.log.info("resumed: watchers and starts are active again")
        return True

    def paused(self):
        return paused(self.cfg)

    # -- one tick

    def tick(self, dry_run=False):
        """Plan, then follow CI, then follow review feedback - each contained.

        ``dry_run`` and the pause marker both turn the whole tick into report-only
        mode. The two are the same code path on purpose: what a dry run refuses to
        do is exactly what a paused supervisor must not do, and one flag keeps the
        two from drifting apart.
        """
        quiet = self.paused() is not None or dry_run
        report = {"at": time.time(), "paused": self.paused() is not None,
                  "dry_run": bool(dry_run), "stages": {}, "acted": 0, "failed": []}
        report["stages"]["plan"] = self._stage("plan", quiet)
        report["stages"]["ci"] = self._stage("ci", quiet)
        report["stages"]["reviews"] = self._stage("reviews", quiet)
        for stage in report["stages"].values():
            report["acted"] += stage.get("acted", 0)
            if stage.get("error"):
                report["failed"].append(stage["error"])
        self._record(report)
        return report

    def _stage(self, name, quiet):
        """Run one stage so that its failure is a line in a report, not a dead loop.

        The containment is deliberately per stage and not per loop: an error that is
        reported with its stage name is actionable, and one that takes the process
        down is remembered only as "the service restarted again".
        """
        try:
            if name == "plan":
                report = self.scheduler.tick(plan_only=quiet)
                # `tick` reports tuples, not rows: (number, branch, needs). During a
                # quiet pass the scheduler fills "planned" instead of "started", so
                # the summary has to read the key that matches the mode.
                started = report.get("started", [])
                planned = report.get("planned", [])
                errors = report.get("errors", [])
                parts = []
                if started:
                    parts.append(self._plan_summary(started))
                if planned:
                    parts.append(f"would start {len(planned)}: "
                                 + ", ".join(f"#{one[0]}" for one in planned))
                if report.get("skipped"):
                    parts.append(f"skipped {len(report['skipped'])}")
                if errors:
                    parts.append(f"errors: {'; '.join(errors)}")
                # A tick that could not even read the board is a state an operator
                # has to hear about; the plan report is where that lands.
                return {"acted": len(started), "count": report.get("considered", 0),
                        "waiting": len(errors),
                        "summary": " / ".join(parts) or "nothing eligible"}
            if name == "ci":
                rows = self.ci.watch(dry_run=quiet)
                acted = [one for one in rows if one.get("action") in ("repairing", "escalated")]
                waiting = [one for one in rows if one.get("action") in
                           ("escalated", "escalation-failed", "held", "repair-refused")]
                return {"acted": len(acted), "count": len(rows), "waiting": len(waiting),
                        "summary": ", ".join(sorted({one.get("action", "?") for one in rows}))
                        or "nothing watched"}
            rows = self.reviews.watch(dry_run=quiet)
            acted = [one for one in rows if one.get("action") in ("responding", "escalated")]
            waiting = [one for one in rows if one.get("action") in
                       ("escalated", "escalation-failed", "held", "respond-refused")]
            return {"acted": len(acted), "count": len(rows), "waiting": len(waiting),
                    "summary": ", ".join(sorted({one.get("action", "?") for one in rows}))
                    or "nothing watched"}
        except Exception as exc:                            # the loop outlives its stages
            self.log.error("%s failed: %s", name, exc)
            self.store.event("daemon-stage-error", f"{name}: {exc}")
            return {"acted": 0, "error": f"{name}: {exc}"}

    def _plan_summary(self, started):
        return ", ".join(f"#{one[0]} {one[1]}".strip() for one in started)

    def _record(self, report):
        """An event for anything that happened, and a heartbeat for the quiet.

        Logging every tick would bury the events an operator reads; logging nothing
        between actions leaves "is it still running" unanswerable after a restart.
        So: an event whenever a tick acted or a stage failed, and otherwise one
        heartbeat per ``heartbeat_ticks`` quiet ticks.
        """
        if report["acted"] or report["failed"]:
            self.store.event("daemon-tick", self._line(report), issue=None)
            self._quiet_ticks = 0
            return
        self._quiet_ticks += 1
        if self._quiet_ticks >= int(self.cfg.get("heartbeat_ticks") or 1):
            self.store.event("daemon-idle", f"{self._quiet_ticks} quiet tick(s), "
                                            f"{self._line(report)}")
            self._quiet_ticks = 0

    def _line(self, report):
        parts = []
        for name in STAGES:
            stage = report["stages"].get(name, {})
            parts.append(f"{name} {stage.get('summary', '-')}")
        return ("paused; report only - " if report["paused"] else "") + " | ".join(parts)

    # -- the loop itself

    def run(self, once=False, dry_run=False):
        """The tick loop. Returns the exit code the timer contract wants.

        Exit codes: ``0`` stopped cleanly with nothing waiting (or ``--once`` with
        nothing waiting), ``1`` stopped cleanly while something needs a human - a
        timer that reads this can page, ``3`` another daemon holds the lock, and
        ``4`` the configuration refuses to authorize anything at all.
        """
        if not self.cfg.ok:
            # Before even taking the lock: a broken configuration must not be
            # able to lock a healthy supervisor out of the state directory.
            self.log.error("configuration problems, refusing to run: %s",
                           "; ".join(self.cfg.problems))
            print(f"configuration is not usable: {'; '.join(self.cfg.problems)}",
                  file=sys.stderr)
            return 4
        try:
            self.acquire()
        except AlreadyRunning as exc:
            self.log.error("%s", exc)
            print(str(exc), file=sys.stderr)
            return 3
        self.write_pid()
        self._install_signals()
        self.log.info("supervisor started: repo %s, tick %ss, state %s%s",
                      self.cfg.repo, self.cfg.get("tick_seconds"), self.cfg.state_dir,
                      ", report only" if dry_run else "")
        self.store.event("daemon-start", f"pid {os.getpid()}, tick "
                                         f"{self.cfg.get('tick_seconds')}s"
                                         f"{', report only' if dry_run else ''}")
        # Before scheduling anything, work out what the last process left behind -
        # this is the reboot path: a worker still running under the old daemon is
        # adopted, a dead one is closed, and a second supervisor never starts
        # beside a live worker on the same branch.
        self._adopt()
        last = 0
        try:
            while True:
                report = self.tick(dry_run=dry_run)
                self.last_report = report
                last = 1 if self._waiting(report) else 0
                if once:
                    return last
                self._sleep()
                if self._stopping.is_set():
                    break
        finally:
            self.log.info("supervisor stopped: %s", self._stop_line())
            self.store.event("daemon-stop", self._stop_line())
            self._leave_pid()
        return last

    def _adopt(self):
        """Run the runner's reconcile once and log what it read."""
        try:
            rows = self.runner.reconcile()
        except Exception as exc:                                # startup must not die here
            self.log.error("reconcile failed at startup: %s", exc)
            self.store.event("daemon-stage-error", f"reconcile: {exc}")
            return []
        for row in rows:
            self.log.info("adopted #%-6s %-10s -> %s", row["issue"],
                          row["reading"], row["action"])
        return rows

    def _waiting(self, report):
        """Whether a human owes an answer after this tick (the timer's signal)."""
        return any(stage.get("waiting") for stage in report["stages"].values())

    def _sleep(self):
        """Wait out the tick interval, wakeable by a stop request or a signal.

        A plain ``time.sleep`` swallows the interval on a signal and comes back
        sleeping, so a ``systemctl stop`` during a five-minute wait would sit out the
        remainder. An event's ``wait`` returns the moment the handler sets it.
        """
        seconds = float(self.cfg.get("tick_seconds") or 60)
        jitter = float(self.cfg.get("tick_jitter_s") or 0)
        if jitter:
            seconds += random.uniform(-jitter, jitter)          # noqa: S311 (not secret)
        self._stopping.wait(max(1.0, seconds))

    def _install_signals(self):
        for number in (signal.SIGTERM, signal.SIGINT):
            signal.signal(number, self._on_signal)

    def _on_signal(self, signum, _frame):
        name = signal.Signals(signum).name
        if self._stopping.is_set():
            return                                          # a second TERM is not louder
        self.log.info("%s received: finishing the current tick, leaving workers alone",
                      name)
        self.request_stop(reason=f"signal {name}")

    def request_stop(self, reason=""):
        """Ask the loop to stop after the tick it is in."""
        self._stop_reason = reason or self._stop_reason or "requested"
        self._stopping.set()

    def _stop_line(self):
        running = [lease["issue"] for lease in self.store.active_leases()
                   if lease.get("state") == "running"]
        return (f"{self._stop_reason or 'finished'}; {len(running)} worker(s) left "
                f"running and will be adopted by reconcile: "
                f"{', '.join('#%d' % number for number in running) or 'none'}")

    # -- one daemon per state directory

    def acquire(self):
        """Take the state directory's lock, or say who appears to be running.

        ``flock`` is held by the *file descriptor*, so a daemon that is SIGKILLed
        loses it with the process and the next start takes over. The pid file is a
        hint for a human; the lock is the answer.
        """
        path = paths(self.cfg)["lock"]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handle = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(handle)
            raise AlreadyRunning(
                f"another supervisor already runs on {self.cfg.state_dir} "
                f"(pid {read_pid(self.cfg) or '?'}); `agent-supervisor daemon stop` "
                "stops it")
        os.ftruncate(handle, 0)
        os.write(handle, f"{os.getpid()}\n".encode())
        os.fsync(handle)
        self._lock = handle

    def write_pid(self):
        with open(paths(self.cfg)["pid"], "w") as handle:
            handle.write(f"{os.getpid()}\n")

    def _leave_pid(self):
        try:
            if read_pid(self.cfg) in (os.getpid(), None):
                os.unlink(paths(self.cfg)["pid"])
        except OSError:
            pass


# ---------------------------------------------------------------------------
# control from the command line

def read_pid(cfg):
    """The pid a running daemon wrote, or ``None``. Checked against /proc:
    a pid file is a hint, and pid reuse is why it is only ever a hint."""
    try:
        with open(paths(cfg)["pid"]) as handle:
            pid = int((handle.read() or "0").strip() or 0)
    except (FileNotFoundError, ValueError):
        return None
    if pid <= 0 or not os.path.exists(f"/proc/{pid}"):
        return None
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as handle:
            command = handle.read().decode("utf-8", "replace")
    except OSError:
        return pid
    if "agent-supervisor" in command or "agent_supervisor" in command:
        return pid
    return None


def lock_held(cfg):
    """Whether some process holds the state lock - the honest "is it running?".

    Trying the lock non-blockingly is the only test that cannot lie: a stale pid
    file, a killed daemon and a daemon whose pid was reused all answer correctly
    here, and none of them answer correctly from a file.
    """
    path = paths(cfg)["lock"]
    if not os.path.exists(path):
        return False
    try:
        handle = os.open(path, os.O_RDWR)
    except OSError:
        return True
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(handle)
    return False


def status(cfg):
    """What ``daemon status`` answers, without needing the daemon's own help."""
    running = lock_held(cfg)
    return {"running": running, "pid": read_pid(cfg) if running else None,
            "paused": paused(cfg), "state_dir": cfg.state_dir,
            "log": paths(cfg)["log"], "systemd": unit_status(),
            "config": cfg.path, "config_ok": cfg.ok, "problems": cfg.problems}


def spawn(cfg, argv=None):
    """Start ``agent-supervisor run`` detached, for a host without systemd.

    A new session, no controlling terminal, standard streams into the daemon's own
    log file: the same shape systemd gives it, so the difference between the two is
    which hand sends the TERM.
    """
    if lock_held(cfg):
        return {"started": False,
                "reason": f"a supervisor already runs on {cfg.state_dir}"}
    log_path = paths(cfg)["log"]
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    command = argv or [sys.executable, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "agent-supervisor"), "run"]
    env = dict(os.environ)
    env[CONFIG_ENV] = cfg.path
    os.makedirs(cfg.state_dir, exist_ok=True)
    with open(log_path, "ab") as sink:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=sink,
                                stderr=sink, env=env, start_new_session=True,
                                cwd=cfg.state_dir)
    return {"started": True, "pid": proc.pid, "command": " ".join(command),
            "log": log_path}


def stop(cfg, timeout_s=60.0):
    """TERM the daemon's session leader and wait for it to finish its tick.

    Only the daemon is signalled, never a worker group: #1060's leases record the
    workers' own process groups, and stopping the supervisor is not a reason to
    destroy a run in flight.
    """
    pid = read_pid(cfg)
    if pid is None:
        return {"stopped": not lock_held(cfg), "reason": "no daemon pid to signal",
                "running": lock_held(cfg)}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"stopped": True, "reason": f"pid {pid} was already gone", "pid": pid}
    except PermissionError:
        return {"stopped": False, "running": True, "pid": pid,
                "reason": f"pid {pid} belongs to another account and will not take "
                          "the signal"}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not lock_held(cfg):
            return {"stopped": True, "pid": pid, "reason": "terminated"}
        time.sleep(0.2)
    return {"stopped": False, "pid": pid, "running": True,
            "reason": f"pid {pid} did not exit within {int(timeout_s)}s; it is still "
                      "finishing a stage or it is wedged - check the log before "
                      "reaching for KILL"}


UNIT_FILE = os.path.expanduser("~/.config/systemd/user/mrmap-agent-supervisor.service")
UNIT_SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "systemd",
                           "mrmap-agent-supervisor.service")


def unit_status():
    """Whether the unit is installed for this account, and whether it is running.

    Read-only: ``systemctl --user is-active`` answers, and a host without systemd
    (a container, a CI box) answers "unknown" instead of being talked about as a
    failure.
    """
    installed = os.path.exists(os.path.expanduser(UNIT_FILE))
    state = "unknown"
    if installed:
        try:
            proc = subprocess.run(["systemctl", "--user", "is-active",
                                   "mrmap-agent-supervisor"],
                                  capture_output=True, text=True, timeout=10)
            state = (proc.stdout or "").strip() or "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            state = "systemd is not reachable"
    return {"installed": installed, "path": UNIT_FILE, "active": state,
            "shipped_at": os.path.normpath(UNIT_SOURCE)}
