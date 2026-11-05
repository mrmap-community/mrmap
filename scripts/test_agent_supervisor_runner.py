"""Offline regression checks for the worker runner of the agent supervisor (#1060).

Run from the repository root: python3 scripts/test_agent_supervisor_runner.py
Exit code 0 means every check passed. Needs no `gh`, no model, no network and no
container, and cannot touch a real repository: the repository here is a throwaway
git repo in a temporary directory, OpenCode is a shell script in this file, and
docker is a script that only records what it was asked to run.

What these checks are really about is the one promise the runner cannot break:
**a worker it started is a worker it can account for afterwards.** Every failure
mode below is a way that promise could silently fail - a claim filed for a worktree
that never runs, a process group nobody can stop, a branch that was cleaned up
although the work was unfinished, a stack torn down that belonged to somebody
else, a restarted supervisor starting an issue a second time.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import approvals, config, runner as runner_module  # noqa: E402
from agent_supervisor.runner import Runner, StartError, is_our_project  # noqa: E402
from agent_supervisor.scheduler import Job  # noqa: E402
from agent_supervisor.store import Store  # noqa: E402

PASS = FAIL = 0
FAILURES = []
TMP = tempfile.mkdtemp(prefix="supervisor-runner-")

# The behaviour the fake OpenCode is told to imitate, through the environment the
# runner passes through from this process.
FAKE = os.path.join(TMP, "opencode")
FAKE_ARGV = os.path.join(TMP, "argv.txt")
FAKE_ENV = os.path.join(TMP, "env.txt")
FAKE_BEHAVIOUR = os.environ["FAKE_BEHAVIOUR"] = os.environ.get("FAKE_BEHAVIOUR", "end")
os.environ["FAKE_ARGV"] = FAKE_ARGV
os.environ["FAKE_ENV"] = FAKE_ENV
FAKE_READY = os.environ["FAKE_READY"] = os.path.join(TMP, "ready.txt")

FAKE_OPENCODE = r"""#!/bin/sh
# A stand-in for `opencode run`. Records what it was asked with, then behaves as
# FAKE_BEHAVIOUR says. It never calls a model, so a test that looks like a running
# worker still costs milliseconds.
#
# The signal behaviour is installed FIRST and only then reported through
# $FAKE_READY: a process that has not installed its handlers yet dies on TERM like
# any other process would, so a check about a worker that ignores TERM has to wait
# for the handler to exist rather than race it.
case "$FAKE_BEHAVIOUR" in
  term)  trap 'exit 0' TERM;;
  hang)  trap '' TERM;;
esac
[ -n "$FAKE_READY" ] && : > "$FAKE_READY"
echo "$*" >> "$FAKE_ARGV"
env | grep -E '^(OPENCODE_DB|OPENCODE_CONFIG_CONTENT|XDG_|COMPOSE_|MRMAP_AGENT)' \
    | sed 's/\\(CONTENT=\\).*/\\1<json>/' | sort >> "$FAKE_ENV"
session=""
while [ $# -gt 0 ]; do
  [ "$1" = "--session" ] && session="$2"
  shift
done
case "$FAKE_BEHAVIOUR" in
  end)   printf '{"type":"step_finish","sessionID":"%s"}\n' "$session"; exit 0;;
  error) printf '{"type":"error","sessionID":"%s"}\n' "$session"; exit 1;;
  cut)   printf '{"type":"tool_use","sessionID":"%s"}\n' "$session"; exit 0;;
  term)  while :; do sleep 0.2; done;;
  hang)  while :; do sleep 0.2; done;;
  *)     exit 0;;
esac
"""


FAKE_DOCKER = """#!/bin/sh
echo "$*" >> "%s"
exit %s
"""


def write_fake_opencode():
    """The stand-in binary itself, written once.

    It is written to disk rather than mocked in-process because the point of these
    checks is how a *real* child process behaves: whether it lands in its own
    process group, whether the prompt reaches its stdin, whether TERM is enough.
    """
    with open(FAKE, "w") as handle:
        handle.write(FAKE_OPENCODE)
    os.chmod(FAKE, 0o755)


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


def git(root, *args):
    return subprocess.run(["git", "-C", root] + list(args), capture_output=True,
                          text=True, check=False)


def make_repo():
    """A throwaway repository with a remote, because `git worktree add ...
    origin/master` has to have an origin/master to mean anything."""
    origin = os.path.join(TMP, "origin.git")
    clone = os.path.join(TMP, "clone")
    subprocess.run(["git", "init", "--bare", "-b", "master", origin],
                   capture_output=True, check=True)
    subprocess.run(["git", "clone", origin, clone], capture_output=True, check=True)
    with open(os.path.join(clone, "README.md"), "w") as handle:
        handle.write("mrmap under test\n")
    # As in the real repository: the files Compose needs are ignored, so a fresh
    # worktree does not have them. Without this the runner would look like a
    # broken secret copier when in fact git handed the file over itself.
    with open(os.path.join(clone, ".gitignore"), "w") as handle:
        handle.write(".env\ndocker/backend/.mrmap.env\n")
    with open(os.path.join(clone, ".env"), "w") as handle:
        handle.write("DJANGO_SECRET_KEY=geheim\n")
    os.makedirs(os.path.join(clone, "docker", "backend"), exist_ok=True)
    with open(os.path.join(clone, "docker", "backend", ".mrmap.env"), "w") as handle:
        handle.write("DB_PASSWORD=auchgeheim\n")
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    git(clone, *identity, "add", "-A")
    git(clone, *identity, "-c", "commit.gpgsign=false", "commit", "-m", "start")
    git(clone, "push", "-u", "origin", "master")
    return origin, clone


ORIGIN, CLONE = make_repo()
# The secrets live in the checkout the supervisor branches from, and are the
# repository's own ignored files - they exist only to be copied, never read here.
os.chmod(os.path.join(CLONE, ".env"), 0o600)


class FakeClaims:
    """The board, as the runner meets it: a claim that succeeds, and one that does
    not, and a line left behind when a job is stopped."""

    def __init__(self, ok=True, reason="another client holds this"):
        self.ok = ok
        self.reason = reason
        self.claimed = []
        self.waited = []

    def claim(self, worktree, issue, reason=""):
        self.claimed.append((worktree, issue))
        return self.ok, (f"claimed #{issue}" if self.ok else self.reason)

    def wait(self, worktree, reason):
        self.waited.append((worktree, reason))
        return True, ""

    def our_client_tag(self, worktree):
        return "this-host:mrmap-" + os.path.basename(worktree)


class Harness:
    """One supervisor configuration, in its own directory, with the fakes wired.

    Each harness gets its own issue number because git is the honest referee
    here: a branch can be checked out in one worktree at a time, so two harnesses
    pretending to be the same issue would fail for a reason that has nothing to do
    with the runner. The number is also what the lease is keyed by, so a distinct
    number per harness is what makes "one issue, one worker" testable at all.
    """

    _numbers = iter(range(1042, 9000))

    def __init__(self, label, claims=None, number=None, **overrides):
        home = os.path.join(TMP, label)
        os.makedirs(home, exist_ok=True)
        self.number = number or next(self._numbers)
        data = {
            "repo": "o/r",
            "authorized_humans": ["human"],
            "agent_accounts": ["agent-bot"],
            "repo_root": CLONE,
            "worktree_root": os.path.join(home, "worktrees"),
            "state_dir": os.path.join(home, "state"),
            "opencode_command": FAKE,
            "opencode_model": "provider/model",
            "require_repo_association": False,
            "worker_timeout_s": 0,
            "cancel_grace_s": 1,
        }
        data.update(overrides)
        path = os.path.join(home, "config.json")
        with open(path, "w") as handle:
            json.dump(data, handle)
        os.chmod(path, 0o600)
        self.cfg = config.load(path)
        self.store = Store.for_config(self.cfg)
        self.claims = claims or FakeClaims()
        self.runner = Runner(self.cfg, store=self.store, claims=self.claims)
        self.home = home

    def job(self, number=None, needs="stack"):
        number = number or self.number
        worktree = os.path.join(self.cfg.worktree_root, f"issue-{number}")
        return Job(number=number, title="Runner does the thing", needs=needs,
                   branch=f"agent/issue-{number}-runner-does-the-thing",
                   worktree=worktree, project=f"mrmap-agent-{number}-100")

    def start(self, **kwargs):
        job = self.job(**kwargs)
        # A stale ready-file from a previous worker would let the wait return
        # before this one has installed its handlers, which is the race the file
        # exists to avoid.
        if os.path.exists(FAKE_READY):
            os.remove(FAKE_READY)
        handle = self.runner.start(job)
        if os.environ.get("FAKE_BEHAVIOUR") in ("term", "hang"):
            wait_until_ready()
        return job, handle

    def lease(self, number=None):
        return self.store.lease(number or self.number)

    def log_file(self, number=None):
        number = number or self.number
        directory = os.path.join(self.cfg.state_dir, "logs")
        if not os.path.isdir(directory):
            return None
        names = [os.path.join(directory, n) for n in os.listdir(directory)
                 if n.startswith(f"issue-{number}-")]
        return sorted(names, key=os.path.getmtime)[-1] if names else None


def behaviour(how):
    os.environ["FAKE_BEHAVIOUR"] = how


def recorded_argv():
    if not os.path.exists(FAKE_ARGV):
        return ""
    with open(FAKE_ARGV) as handle:
        return handle.read()


def recorded_env():
    if not os.path.exists(FAKE_ENV):
        return ""
    with open(FAKE_ENV) as handle:
        return handle.read()


def fresh_fakes():
    for path in (FAKE_ARGV, FAKE_ENV, FAKE_READY):
        if os.path.exists(path):
            os.remove(path)


def wait_until_ready(limit=5.0):
    """Wait for the fake to report its signal handlers are installed.

    Bounded, and it waits for a fact rather than for a fixed time: without it, a
    check about ignoring TERM would sometimes catch the worker before the handler
    exists and conclude that TERM was enough.
    """
    deadline = time.time() + limit
    while time.time() < deadline and not os.path.exists(FAKE_READY):
        time.sleep(0.02)
    return os.path.exists(FAKE_READY)


def wait_gone(lease, runner, limit=3.0):
    deadline = time.time() + limit
    while time.time() < deadline and runner.alive(lease):
        time.sleep(0.05)
    return not runner.alive(lease)


# ---------------------------------------------------------------------------
# starting a worker


def test_start():
    fresh_fakes()
    behaviour("end")
    harness = Harness("start")
    check("the runner's own configuration is usable", harness.cfg.ok,
          str(harness.cfg.problems))
    job, handle = harness.start()

    check("the worktree was created on its own branch",
          os.path.isdir(os.path.join(job.worktree, ".git")) or
          os.path.isfile(os.path.join(job.worktree, ".git")), str(job.worktree))
    head = git(job.worktree, "rev-parse", "--abbrev-ref", "HEAD")
    check("and it is the branch of this issue, not master",
          head.stdout.strip() == job.branch, head.stdout.strip())

    copied = os.path.join(job.worktree, ".env")
    check("the ignored .env was handed over", os.path.exists(copied), copied)
    check("with a mode that keeps it private",
          stat.S_IMODE(os.stat(copied).st_mode) == 0o600,
          oct(stat.S_IMODE(os.stat(copied).st_mode)))
    nested = os.path.join(job.worktree, "docker", "backend", ".mrmap.env")
    check("including the nested env file", os.path.exists(nested), nested)

    check("the claim was filed inside the worktree",
          harness.claims.claimed == [(job.worktree, job.number)],
          str(harness.claims.claimed))

    argv = recorded_argv()
    check("the worker is started non-interactively on a fixed session",
          "--session" in argv and "--auto" in argv and "--format json" in argv, argv)
    check("and it is given its own session id", handle["session"] in argv, argv)
    check("the model comes from the configuration", "--model provider/model" in argv, argv)

    env = recorded_env()
    worker_db = os.path.join(harness.cfg.state_dir, "workers", f"issue-{harness.number}",
                             "data", "opencode.db")
    check("the worker gets its own database, not the shared one",
          f"OPENCODE_DB={worker_db}" in env, env[:400])
    check("and its own XDG homes", "XDG_DATA_HOME=" in env and "XDG_CACHE_HOME=" in env,
          env[:400])
    check("Compose is pinned to this job's project",
          f"COMPOSE_PROJECT_NAME={job.project}" in env, env[:400])
    check("the prebuilt files are the ones offered",
          "COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"
          in env, env[:400])
    check("the deny rules are handed to the client as configuration",
          "OPENCODE_CONFIG_CONTENT=" in env, env[:400])

    lease = harness.lease()
    check("the lease records the process group, not only a pid",
          lease["pgid"] == handle["pgid"] and lease["pid"] == handle["pid"], str(dict(lease)))
    check("it records the session that can be resumed",
          lease["session"] == handle["session"], str(dict(lease)))
    check("it records the Compose project that must be cleaned up",
          lease["project"] == job.project, str(dict(lease)))
    check("and the state is running", lease["state"] == "running", lease["state"])

    wait_gone(lease, harness.runner)
    log = harness.log_file()
    check("the worker wrote its own log under the state directory",
          log and os.path.exists(log), str(log))
    check("with a mode that keeps it private",
          stat.S_IMODE(os.stat(log).st_mode) == 0o600,
          oct(stat.S_IMODE(os.stat(log).st_mode)) if log else "no log")
    check("the log holds what the worker reported",
          "step_finish" in open(log).read(), open(log).read()[:120] if log else "")
    check("no secret value ever reached the recorded environment",
          "geheim" not in recorded_env() and "auchgeheim" not in recorded_env(),
          recorded_env()[:200])


def test_claim_refused_stops_everything():
    behaviour("end")
    claims = FakeClaims(ok=False, reason="mrmap-999 holds a live claim")
    harness = Harness("refused", claims=claims)
    job = harness.job()
    fresh_fakes()
    try:
        harness.runner.start(job)
        check("a refused claim stops the start", False, "start returned normally")
    except StartError as exc:
        check("a refused claim stops the start", True)
        check("and names who holds the issue", "mrmap-999" in str(exc), str(exc))
    check("nothing was spawned", recorded_argv() == "", recorded_argv()[:200])
    check("the worktree was created but no branch was touched by a worker",
          os.path.isdir(job.worktree), job.worktree)
    lease = harness.lease()
    check("no lease is left claiming the issue is taken",
          lease and lease["state"] == "abandoned" and "mrmap-999" in (lease["detail"] or ""),
          str(dict(lease)) if lease else "no lease")


def test_two_supervisors_one_issue():
    """Two supervisors, one issue: first the store, then the runner, then git.

    Each layer is checked separately because each is the last line of defence for
    a different accident: the lease keeps two daemons from planning the same
    issue, the running-process check keeps a hand-started tick from editing a
    worktree that somebody is already editing, and git itself refuses the same
    branch in two worktrees.
    """
    behaviour("hang")
    harness = Harness("double")
    job, handle = harness.start()
    other = Runner(harness.cfg, store=Store(os.path.join(harness.cfg.state_dir,
                                                         "supervisor.sqlite3")),
                   claims=FakeClaims())
    check("the lease is held by the supervisor that started the worker",
          harness.lease()["pgid"] == handle["pgid"], str(harness.lease()))
    check("a second supervisor cannot take the lease of a live one",
          other.store.claim_lease(job.number, "o/r", "stack") is False,
          "claim_lease returned True")
    fresh_fakes()
    try:
        other.start(job)
        check("a second supervisor does not start a leased issue beside the first",
              False, "the fake opencode was called")
    except StartError as exc:
        check("a second supervisor does not start a leased issue beside the first",
              recorded_argv() == "" and "already running" in str(exc), str(exc))
    check("git itself would also refuse the branch in a second worktree",
          git(job.worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == job.branch,
          "the first worktree still owns the branch")
    harness.runner.cancel(harness.lease(), "cleanup")


# ---------------------------------------------------------------------------
# stopping a worker


def test_cancel():
    behaviour("term")
    harness = Harness("cancel")
    job, handle = harness.start()
    lease = harness.lease()
    check("a running worker's group is alive", harness.runner.alive(lease), str(lease))
    outcome = harness.runner.cancel(lease, "the approval was withdrawn")
    check("TERM reaches the process group", outcome["stopped"] and not outcome["forced"],
          str(outcome))
    check("and the group is gone", not harness.runner.alive(harness.lease()),
          str(harness.lease()))
    check("the lease is released as cancelled",
          harness.lease()["state"] == "cancelled", str(harness.lease()["state"]))
    check("the board is told why the job stopped",
          harness.claims.waited and "withdrawn" in harness.claims.waited[0][1],
          str(harness.claims.waited))
    check("the branch survives the stop", os.path.isdir(job.worktree), job.worktree)
    check("the worktree survives it too",
          os.path.isfile(os.path.join(job.worktree, "README.md")), job.worktree)


def test_cancel_of_a_worker_that_ignores_term():
    behaviour("hang")
    harness = Harness("force")
    _, handle = harness.start()
    lease = harness.lease()
    check("a worker that ignores TERM is treated as alive", harness.runner.alive(lease),
          str(lease))
    outcome = harness.runner.cancel(lease, "paused by an operator")
    check("a worker that ignores TERM is killed", outcome["forced"], str(outcome))
    check("and it is then gone", not harness.runner.alive(harness.lease()),
          str(harness.lease()))
    check("the kill went to the group, not to one pid",
          handle["pgid"] == handle["pid"] and lease["pgid"], str(dict(lease)))


def test_pause_and_resume():
    behaviour("term")
    harness = Harness("pauseresume")
    _, handle = harness.start()
    harness.runner.pause(harness.number, "operator wanted a look")
    check("pause stops the worker", not harness.runner.alive(harness.lease()),
          str(harness.lease()))
    check("pause leaves the lease as cancelled",
          harness.lease()["state"] == "cancelled", harness.lease()["state"])

    # resume is the gate's decision, not the runner's: a paused issue stays stopped
    original = approvals.decide
    fresh_fakes()

    def denied(cfg, number, issue=None, now=None):
        return approvals.Decision(number, False, approvals.PAUSED, "agent: paused is set")

    approvals.decide = denied
    try:
        harness.runner.resume(harness.number)
        check("a withdrawn issue is not resumed", False, "resume returned normally")
    except StartError as exc:
        check("a withdrawn issue is not resumed", "paused" in str(exc).lower(), str(exc))
    finally:
        approvals.decide = original

    check("nothing was spawned by the refused resume",
          recorded_argv() == "", recorded_argv())

    # and with the gate agreeing again, the same session continues in the same worktree
    def allowed(cfg, number, issue=None, now=None):
        return approvals.Decision(number, True, approvals.ELIGIBLE, "", {})

    fresh_fakes()
    behaviour("end")
    harness.store.update_lease(harness.number, state="planned", detail="reconciled")
    approvals.decide = allowed
    try:
        resumed = harness.runner.resume(harness.number)
    finally:
        approvals.decide = original
    check("an eligible issue resumes on its recorded session",
          resumed["session"] == handle["session"], str(resumed))
    check("resuming spawns exactly one worker",
          recorded_argv().count("--session") == 1, recorded_argv())
    check("the lease is running again with a new process",
          harness.lease()["state"] == "running", str(harness.lease()))
    check("and it records the new pid, not the dead one",
          harness.lease()["pid"] != 0, str(harness.lease()["pid"]))


def test_resume_refused_while_running():
    behaviour("hang")
    harness = Harness("resumewhilealive")
    harness.start()

    def allowed(cfg, number, issue=None, now=None):
        return approvals.Decision(number, True, approvals.ELIGIBLE, "", {})

    original = approvals.decide
    approvals.decide = allowed
    try:
        harness.runner.resume(harness.number)
        check("a live worker cannot be resumed beside itself", False, "resume succeeded")
    except StartError as exc:
        check("a live worker cannot be resumed beside itself",
              "still running" in str(exc), str(exc))
    finally:
        approvals.decide = original
    harness.runner.cancel(harness.lease(), "cleanup")


# ---------------------------------------------------------------------------
# crash and restart


def test_reconcile_after_crash():
    behaviour("error")
    harness = Harness("reconcile-error")
    harness.start()
    time.sleep(0.2)
    rows = harness.runner.reconcile()
    check("a session that ended in an error is read as failed",
          rows and rows[0]["reading"] == "failed", str(rows))
    check("and the lease is abandoned, not silently retried",
          harness.lease()["state"] == "abandoned", harness.lease()["state"])

    behaviour("end")
    harness = Harness("reconcile-end")
    harness.start()
    time.sleep(0.2)
    rows = harness.runner.reconcile()
    check("a session that ended cleanly is read as finished",
          rows and rows[0]["reading"] == "finished", str(rows))
    check("and the lease is released",
          harness.lease()["state"] == "finished", harness.lease()["state"])

    behaviour("cut")
    harness = Harness("reconcile-cut")
    _, handle = harness.start()
    time.sleep(0.2)
    rows = harness.runner.reconcile()
    check("a run cut off mid-event is resumable, not judged",
          rows and rows[0]["reading"] == "resumable", str(rows))
    check("its lease stays live so the issue cannot be taken twice",
          harness.lease()["state"] == "planned", harness.lease()["state"])
    check("and the session that can be continued is kept",
          harness.lease()["session"] == handle["session"], str(harness.lease()))

    # a live worker must be left alone: that is the duplicate-execution guard
    behaviour("hang")
    harness = Harness("reconcile-alive")
    harness.start()
    rows = harness.runner.reconcile()
    check("a worker that is still running is left alone",
          rows and rows[0]["reading"] == "running", str(rows))
    check("its lease stays running", harness.lease()["state"] == "running",
          harness.lease()["state"])
    harness.runner.cancel(harness.lease(), "cleanup")


def test_timeout():
    behaviour("hang")
    harness = Harness("timeout", worker_timeout_s=1)
    harness.start()
    time.sleep(1.2)
    rows = harness.runner.reconcile()
    check("a worker past its timeout is stopped",
          rows and rows[0]["reading"] == "timed out", str(rows))
    check("and it really is gone", not harness.runner.alive(harness.lease()),
          str(harness.lease()))
    check("the lease says cancelled", harness.lease()["state"] == "cancelled",
          harness.lease()["state"])


def test_alive_without_a_record():
    harness = Harness("alive")
    check("no lease means no live worker", not harness.runner.alive(None), "None")
    check("a lease without a process group is not alive",
          not harness.runner.alive({"pgid": None}), "pgid None")
    check("a process group that does not exist is not alive",
          not harness.runner.alive({"pgid": 999999}), "pgid 999999")


# ---------------------------------------------------------------------------
# cleanup


def test_cleanup_only_own_stack():
    log = os.path.join(TMP, "docker-calls.txt")
    runner_module.DOCKER_COMMAND = os.path.join(TMP, "dockerfake")
    with open(runner_module.DOCKER_COMMAND, "w") as handle:
        handle.write(FAKE_DOCKER % (log, 0))
    os.chmod(runner_module.DOCKER_COMMAND, 0o755)

    harness = Harness("cleanup")
    own = f"mrmap-agent-{harness.number}-77"
    for foreign in ("mrmap-community-mrmap", f"mrmap-agent-{harness.number + 1}-77",
                    "mrmap-dev", "", None):
        try:
            harness.runner.cleanup_stack(harness.number, foreign)
            check(f"{foreign!r} is refused without a docker call", False, "it ran")
        except StartError:
            check(f"{foreign!r} is refused without a docker call", True)
    check("not one docker command was built for a foreign project",
          not os.path.exists(log), open(log).read() if os.path.exists(log) else "")

    harness.runner.cleanup_stack(harness.number, own)
    ran = open(log).read() if os.path.exists(log) else ""
    check("the project of this issue is torn down by name",
          f"compose -p {own} down --volumes" in ran, ran)
    check("and never with a global prune or orphan removal",
          "prune" not in ran and "orphans" not in ran, ran)

    with open(log, "w"):
        pass
    with open(runner_module.DOCKER_COMMAND, "w") as handle:
        handle.write(FAKE_DOCKER % (log, 1))
    os.chmod(runner_module.DOCKER_COMMAND, 0o755)
    try:
        harness.runner.cleanup_stack(harness.number, f"mrmap-agent-{harness.number}-78")
        check("a failing teardown is reported, not swallowed", False, "it claimed success")
    except StartError as exc:
        check("a failing teardown is reported, not swallowed", "could not be torn down"
              in str(exc), str(exc))
    runner_module.DOCKER_COMMAND = "docker"


def test_project_name_shape():
    check("an agent project of the right issue is ours",
          is_our_project("mrmap-agent-1042-77", 1042), "should be ours")
    check("another issue's agent project is not ours",
          not is_our_project("mrmap-agent-1042-77", 999), "wrong issue")
    check("the developer's own project is not ours",
          not is_our_project("mrmap-community-mrmap", 1042), "developer stack")
    check("a prefix that only looks similar is not ours",
          not is_our_project("mrmap-agent-10427-77", 1042), "lookalike")


# ---------------------------------------------------------------------------
# what must never happen in a worktree


def test_master_is_fetched_only_for_new_worktrees():
    behaviour("end")
    harness = Harness("fetch-once")
    job, handle = harness.start()
    worktree = job.worktree
    before = git(worktree, "rev-parse", "HEAD").stdout.strip()

    # master moves in the remote while this job works
    identity = ["-c", "user.name=test", "-c", "user.email=test@example.invalid"]
    with open(os.path.join(CLONE, "LATER.md"), "w") as handle2:
        handle2.write("moved on\n")
    git(CLONE, *identity, "add", "-A")
    git(CLONE, *identity, "-c", "commit.gpgsign=false", "commit", "-m", "master moved")
    git(CLONE, "push", "origin", "master")

    harness.runner.cancel(harness.lease(), "cleanup")

    # a second job in the same worktree must not have master merged into it
    fresh = Runner(harness.cfg, store=Store(os.path.join(harness.cfg.state_dir,
                                                         "supervisor.sqlite3")),
                   claims=FakeClaims())
    job2 = Job(number=1043, title="Second", needs="stack",
               branch="agent/issue-1043-second",
               worktree=os.path.join(harness.cfg.worktree_root, "issue-1043"),
               project="mrmap-agent-1043-101")
    fresh.start(job2)
    still = git(worktree, "rev-parse", "HEAD").stdout.strip()
    check("an existing worktree keeps its own history while master moves",
          still == before, f"{still} != {before}")
    check("a new worktree is created from the remote master, so it does carry the move",
          git(job2.worktree, "rev-parse", "HEAD").stdout.strip()
          == git(CLONE, "rev-parse", "origin/master").stdout.strip(),
          "new worktree base")
    fresh.cancel(fresh.store.lease(1043), "cleanup")
    harness.runner.cancel(harness.lease(), "cleanup")


def test_no_write_paths_in_the_runner():
    """The runner starts processes; it must not reach into GitHub itself."""
    root = os.path.dirname(os.path.abspath(__file__))
    source = open(os.path.join(root, "agent_supervisor", "runner.py")).read()
    tree_ok = all(part not in source for part in
                  ("/comments", "/reviews", "/merge", "/assignees", "gh_json"))
    check("the runner performs no GitHub request of its own", tree_ok,
          "found a REST path or gh call")
    check("the runner never merges", "gh pr merge" not in source, "a merge call")
    check("the runner never prunes docker globally",
          "system prune" not in source and "container prune" not in source,
          "a global prune")
    check("the runner never removes a worktree", "worktree remove" not in source,
          "a worktree removal")
    check("the runner never removes volumes except through one named project",
          source.count("--volumes") == 1, str(source.count("--volumes")))


def main():
    write_fake_opencode()
    for fn in (test_start, test_claim_refused_stops_everything,
               test_two_supervisors_one_issue, test_cancel,
               test_cancel_of_a_worker_that_ignores_term, test_pause_and_resume,
               test_resume_refused_while_running, test_reconcile_after_crash,
               test_timeout, test_alive_without_a_record, test_cleanup_only_own_stack,
               test_project_name_shape, test_master_is_fetched_only_for_new_worktrees,
               test_no_write_paths_in_the_runner):
        try:
            fn()
        except Exception as exc:                       # a crash is a failed check
            check(f"{fn.__name__} raised", False, f"{type(exc).__name__}: {exc}")
    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    os.environ["FAKE_BEHAVIOUR"] = "end"
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
