"""The hand that starts a worker, and the only place that is allowed to.

The scheduler decided that this issue may start; this module turns that decision
into a process and keeps enough information about it to undo that later. Three
things shaped it, in order of how much they cost to get wrong:

**A worker is a process group, not a process.** ``opencode run --standalone``
starts a child server, and a subagent started by the model is a grandchild of
that. Killing the pid we spawned leaves the server serving and the subagent
editing files in a worktree nobody supervises any more, so every worker is
started in its own session (``setsid``) and stopped by ``kill(-pgid)``. The
record keeps both numbers because after a host restart the pid is gone and the
group id is the only thing a log line can still point at.

**The claim belongs to the worker.** ``scripts/wip`` names a client by the
worktree it runs in, so the claim is filed here, as the first act inside the
worktree, before a single file is touched. A claim the supervisor filed from its
own checkout would have a heartbeat this worker cannot refresh and a ``done`` it
cannot release. If the claim is refused, nothing else happens: no worktree
branch is created, no file is edited, and the scheduler is told this was not
ours to start.

**Losing a worker must be recoverable, not guessed.** After a crash or a reboot
the process is gone and its exit code with it. Rather than pretend to know
whether it finished, reconciliation looks at what is left: whether the process
group still answers, whether the session log ends in an end event or an error,
and whether the claim on the board is still live. A worker that died with a live
claim and an unfinished log is resumable - the same OpenCode session id, in the
same worktree, started again by the same lease - and an issue is never run twice
at once because the lease that carries the session id is the thing being
reconciled, and the board is still the arbiter across hosts.

Nothing here edits source code, opens pull requests or answers a reviewer: it
starts a process, stops a process, and remembers what it did.
"""

import json
import os
import signal
import subprocess
import time

from . import config as config_module
from .claims import Claims
from .scheduler import StartError
from .store import Store

# Where a worker's private state lives, under state_dir. Separate from the
# supervisor's own because OpenCode writes its session database, its config and
# its cache into these directories, and two clients sharing one database is a
# corruption waiting to happen rather than a surprise.
WORKER_DIRS = ("data", "config", "state", "cache")

# The files the repository keeps out of git but every Compose command needs, and
# what to fall back to when the configuration names none. They carry
# credentials, so they are copied with a mode that keeps them private and their
# contents are never read into a log line or an error message.
SECRET_FILES = (".env", os.path.join("docker", "backend", ".mrmap.env"))

# What a session log's last event says about the worker that wrote it.
LOG_END = ("step_finish", "session_end", "end")
LOG_ERROR = ("error",)

# The docker binary, overridable the way the capacity gate is: the checks of this
# module have to prove that a foreign project is refused before a command is
# built, and a fake binary is the only honest way to watch what would have run.
DOCKER_COMMAND = os.environ.get("MRMAP_DOCKER_COMMAND") or "docker"


def project_name(number, run_id):
    """The Compose project name of one job, in the shape ``scripts/wip`` and the
    repository's cleanup rules both expect: ``mrmap-agent-<issue>-<run>``."""
    return f"mrmap-agent-{number}-{run_id}"


def is_our_project(project, number=None):
    """Whether a project name is one this supervisor could have created.

    The cleanup rules of the repository forbid tearing down a stack this job did
    not create, and the only defence a host-side tool has is the name. Anything
    that does not start with the agent prefix - and, when the issue is known,
    does not carry its number - is refused before a ``docker`` command is built.
    """
    if not project or not str(project).startswith("mrmap-agent-"):
        return False
    if number is None:
        return True
    return str(project).startswith(f"mrmap-agent-{number}-")


class Runner:
    """Starts, stops and reconciles the workers of one supervisor.

    ``store`` and ``claims`` are injectable because the tests of this module are
    the whole point of writing it the way it is written: a fake ``opencode``
    script and a fake board let the checks cover start, cancellation, crash
    recovery and the refusal to clean up somebody else's stack, without a model,
    a repository write or a container anywhere near them.
    """

    def __init__(self, cfg, store=None, claims=None):
        self.cfg = cfg
        self.store = store or Store.for_config(cfg)
        self.claims = claims or Claims(cfg)

    # -- starting ------------------------------------------------------------

    def start(self, job):
        """Launch the worker for ``job`` and return what identifies it later.

        Raises StartError for anything that stops the job before it runs. The
        scheduler records the attempt, backs the issue off and moves on, so an
        error message here is written for the operator who will read it in the
        event log, not for a stack trace.
        """
        run_id = self._run_id()
        branch = job.branch or f"agent/issue-{job.number}"
        worktree = job.worktree or os.path.join(self.cfg.worktree_root, f"issue-{job.number}")
        project = job.project or project_name(job.number, run_id)
        if not is_our_project(project, job.number):
            raise StartError(f"{project} is not a project name this job may own")
        existing = self.store.lease(job.number)
        if self.alive(existing):
            # The scheduler serialises through the lease, so reaching this line
            # means a second supervisor or a hand-started tick is beside the one
            # that already owns the branch. Refusing here is the last place where
            # two clients editing one worktree can still be stopped.
            raise StartError(f"#{job.number} is already running here "
                             f"(process group {existing['pgid']})")
        if existing is None and not self.store.claim_lease(
                job.number, self.cfg.repo, job.needs, branch=branch,
                worktree=worktree, project=project):
            # Either another supervisor took it in the last millisecond, or a
            # crashed one left a live row that has not aged out yet. Both mean the
            # same thing: this issue is somebody's, and a worktree for it must not
            # be created to find that out later.
            raise StartError(f"#{job.number} is leased to another supervisor on this host")

        took_lease = existing is None
        try:
            self._worktree(worktree, branch)
            self._hand_over_secrets(worktree)
            self._claim(worktree, job)
        except StartError as exc:
            if took_lease:
                # The lease was only a placeholder for this attempt. Leaving it
                # live would keep the issue blocked until the plan ages out, for a
                # job that never started and will not start again on its own.
                self.store.release_lease(job.number, state="abandoned", detail=str(exc))
            raise

        # Only now is the job ours: everything above is reversible or inert.
        self.store.update_lease(job.number, state="starting", branch=branch,
                                worktree=worktree, project=project,
                                detail=f"run {run_id}")
        session = self._session(job.number, run_id)
        log = self._log_path(job.number, run_id)
        command = self._command(job, session)
        env = self._environment(job.number, worktree, project)

        handle = subprocess.Popen(                      # noqa: S603 (fixed argv)
            command, cwd=worktree, env=env, stdin=subprocess.PIPE,
            stdout=open(log, "ab"), stderr=subprocess.STDOUT,
            start_new_session=True)
        with handle.stdin:
            handle.stdin.write(self._prompt(job).encode("utf-8"))
        self.store.update_lease(job.number, state="running", pid=handle.pid,
                                pgid=handle.pid, session=session, project=project,
                                worktree=worktree, branch=branch, detail=f"log {log}")
        self.store.event("worker-started",
                         f"pid={handle.pid} pgid={handle.pid} session={session} "
                         f"project={project}", issue=job.number)
        return {"pid": handle.pid, "pgid": handle.pid, "session": session,
                "project": project, "worktree": worktree, "branch": branch, "log": log}

    def resume(self, number):
        """Start the worker of an existing lease again, on its own session.

        The approval is asked again before anything starts: a paused issue, a
        removed label or a closed issue does not get to continue just because a
        process used to run for it.
        """
        from . import approvals

        lease = self.store.lease(number)
        if not lease:
            raise StartError(f"#{number} has no lease here, so there is nothing to resume")
        if self.alive(lease):
            raise StartError(f"#{number} is still running (pgid {lease['pgid']})")
        decision = approvals.decide(self.cfg, number)
        if not decision.eligible:
            raise StartError(f"not resumed: {decision.reason} - {decision.detail}")
        if not lease.get("session"):
            raise StartError(f"#{number} has no recorded session to resume")

        job = self._job_of(lease)
        worktree, project = lease["worktree"], lease["project"]
        log = self._log_path(number, self._run_id())
        env = self._environment(number, worktree, project)
        handle = subprocess.Popen(                      # noqa: S603 (fixed argv)
            self._command(job, lease["session"]), cwd=worktree, env=env,
            stdin=subprocess.PIPE, stdout=open(log, "ab"), stderr=subprocess.STDOUT,
            start_new_session=True)
        with handle.stdin:
            handle.stdin.write("Continue where you stopped. Check the current state of "
                               "the branch and the checks before doing anything else."
                               .encode("utf-8"))
        self.store.update_lease(number, state="running", pid=handle.pid, pgid=handle.pid,
                                project=project, detail=f"resumed, log {log}")
        self.store.event("worker-resumed", f"pid={handle.pid} session={lease['session']}",
                         issue=number)
        return {"pid": handle.pid, "pgid": handle.pid, "session": lease["session"],
                "project": project, "worktree": worktree, "log": log}

    # -- stopping ------------------------------------------------------------

    def cancel(self, lease, reason=""):
        """Ask the worker to leave, then make it leave.

        The group gets ``TERM`` first because a worker that is allowed to finish
        the tool call it is inside commits nothing half-written; the grace window
        is short because the human who withdrew the approval is already waiting.
        Branch, worktree, logs and claim are left exactly as they are - what was
        withdrawn was permission to act, not the value of the work so far - and
        the board is told in one line why the job stopped.
        """
        number = lease["issue"]
        grace = float(self.cfg.get("cancel_grace_s") or 30)
        stopped = self._signal(lease, signal.SIGTERM)
        deadline = time.time() + grace
        while stopped and time.time() < deadline and self.alive(lease):
            time.sleep(0.2)
        forced = False
        if self.alive(lease):
            forced = self._signal(lease, signal.SIGKILL)
        self.store.release_lease(number, state="cancelled",
                                 detail=f"cancelled: {reason}" if reason else "cancelled")
        self.store.event("worker-cancelled",
                         f"pgid={lease['pgid']} forced={forced}", issue=number)
        self.claims.wait(lease["worktree"], f"stopped by the supervisor: {reason or 'withdrawn'}")
        return {"stopped": stopped, "forced": forced}

    def pause(self, number, reason=""):
        """Stop the worker of one issue and leave the rest of its work standing."""
        lease = self.store.lease(number)
        if not lease:
            raise StartError(f"#{number} has no lease here")
        outcome = self.cancel(lease, reason or "paused by an operator")
        self.store.event("paused", reason or "paused by an operator", issue=number)
        return outcome

    # -- reconciling ---------------------------------------------------------

    def alive(self, lease):
        """Whether the worker itself is still working, not whether its group has
        any member left.

        The distinction is what makes cancellation honest: a process group
        outlives its leader for as long as a grandchild takes to notice, so a
        supervisor that read the group as the answer would report a stopped job as
        running and escalate to ``KILL`` against a process that is already gone.

        Two properties of Unix make the question non-trivial, and both were found
        by running the thing rather than reading it. A process that has exited is a
        zombie until its parent reaps it, and a zombie answers ``kill(pid, 0)`` -
        so "the pid is there" is not the question. And the worker is a child of
        *this* python process, where ``subprocess`` reaps it in the background, so
        ``waitpid`` here reports ECHILD for a worker that has only just exited:
        this method must not reap, must not trust ``kill(pid, 0)``, and has to read
        the state out of ``/proc`` itself. After a host restart the pid is not a
        child any more and the process group is all a log line can still point at.
        """
        pgid = lease.get("pgid") if lease else None
        if not pgid:
            return False
        pid = lease.get("pid")
        if pid:
            try:
                os.kill(int(pid), 0)
                return _process_state(int(pid)) != "Z"
            except ProcessLookupError:
                pass                          # gone here: a restart leaves the group
            except (OSError, ValueError):
                return False
        try:
            os.killpg(int(pgid), 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True                     # exists, owned by somebody else
        except (OSError, ValueError):
            return False
        return _group_has_live_member(int(pgid))

    def reconcile(self):
        """What a restart or a crash left behind, per live lease.

        Returns one row per lease with the reading and what was done about it.
        This never starts anything by itself: the reading ``resumable`` leaves the
        lease for the next tick, which will start under the same lease and
        therefore under the same session. Each lease is read once - a worker cannot
        be both "left alone" and "timed out" in the same pass, which is why the
        timeout is asked here rather than in a second sweep over the same rows.
        """
        rows = []
        limit = float(self.cfg.get("worker_timeout_s") or 0)
        for lease in self.store.active_leases():
            if self.alive(lease):
                if limit > 0 and time.time() - (lease["started_at"] or 0) >= limit:
                    self.cancel(lease, f"ran longer than {int(limit)}s")
                    rows.append({"issue": lease["issue"], "reading": "timed out",
                                 "action": "cancelled", "detail": f"limit {int(limit)}s"})
                    continue
                rows.append({"issue": lease["issue"], "reading": "running",
                             "action": "left alone", "detail": f"pgid {lease['pgid']}"})
                continue
            ending = self._log_ending(lease)
            if ending == "error":
                self.store.update_lease(lease["issue"], state="abandoned",
                                        detail="the session log ends in an error")
                rows.append({"issue": lease["issue"], "reading": "failed",
                             "action": "lease abandoned", "detail": ending})
            elif ending == "end" and lease["state"] == "running":
                self.store.release_lease(lease["issue"], state="finished",
                                         detail="the session log ends cleanly")
                rows.append({"issue": lease["issue"], "reading": "finished",
                             "action": "lease released", "detail": ending})
            else:
                self.store.update_lease(lease["issue"], state="planned",
                                        detail=f"reconciled: {ending}, session "
                                               f"{lease.get('session')} is resumable")
                rows.append({"issue": lease["issue"], "reading": "resumable",
                             "action": "lease held for the next tick",
                             "detail": f"session {lease.get('session')}"})
            self.store.event("reconciled", f"{rows[-1]['reading']}: {rows[-1]['detail']}",
                             issue=lease["issue"])
        return rows

    # -- the pieces of a start ------------------------------------------------

    def _worktree(self, worktree, branch):
        """Create the worktree from current master, or use the one that exists.

        ``fetch`` happens only when a worktree is created. A job that merged
        master before every push would race every other job on the host and make
        each run's base different from the one CI reviews; the repository's own
        rule is to merge master when opening the pull request, and that is what
        the worker does at the end, not what the supervisor does repeatedly here.
        """
        if os.path.isdir(worktree):
            return worktree
        os.makedirs(self.cfg.worktree_root, exist_ok=True)
        root = self.cfg.repo_root
        self._git(root, ["fetch", "origin", "master"])
        exists = self._git(root, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                           check=False)
        if exists.returncode == 0:
            self._git(root, ["worktree", "add", worktree, branch])
        else:
            self._git(root, ["worktree", "add", "-b", branch, worktree, "origin/master"])
        return worktree

    def _hand_over_secrets(self, worktree):
        """Copy the ignored files Compose needs, without ever reading them.

        A worktree has no ``.env`` because git does not track it, and every
        Compose command in it then fails on a missing variable. The list is the
        configured one (``worktree_env_files``) because which files a deployment
        keeps out of git is an operator fact, not a fact about this repository.
        The copy is made through the file API and given mode 0600; the contents
        never reach a variable that could be interpolated into a message, because
        an exception here names paths only.
        """
        wanted = self.cfg.get("worktree_env_files") or list(SECRET_FILES)
        for relative in wanted:
            source = os.path.join(self.cfg.repo_root, str(relative))
            target = os.path.join(worktree, str(relative))
            if not os.path.exists(source) or os.path.exists(target):
                continue
            os.makedirs(os.path.dirname(target) or worktree, exist_ok=True)
            shutil_filecopy(source, target)
            os.chmod(target, 0o600)

    def _claim(self, worktree, job):
        """File the claim as the worker, before anything is edited."""
        ok, output = self.claims.claim(worktree, job.number,
                                       reason=f"supervisor run for #{job.number}")
        if not ok:
            raise StartError(f"the claim for #{job.number} was refused: "
                             f"{_last_line(output)}")

    def _command(self, job, session):
        """The argv of one worker, with nothing interpolated from the issue.

        The title and body of an issue are attacker-readable text; they reach the
        model through the prompt, never through a shell. The model is configured,
        not guessed, and the session id is the one recorded in the lease so a
        restart can resume the same conversation.
        """
        binary = self.cfg.get("opencode_command") or "opencode"
        argv = [binary, "run", "--standalone", "--session", session, "--auto",
                "--format", "json", "--title", f"issue #{job.number}"]
        model = str(self.cfg.get("opencode_model") or "")
        if model:
            argv += ["--model", model]
        agent = str(self.cfg.get("opencode_agent") or "")
        if agent:
            argv += ["--agent", agent]
        return argv

    def _prompt(self, job):
        return (f"Work on mrmap issue #{job.number}: {job.title}\n"
                "You are running unattended in your own worktree and Compose stack. "
                "Read the nearest AGENTS.md first, claim your work with scripts/wip if it "
                "is not claimed yet, keep the branch of this worktree, run the checks the "
                "area documents, and open a pull request that links this issue. Do not "
                "merge, approve or enqueue anything, and do not touch another job's "
                "stacks, branches or worktrees.")

    def _environment(self, number, worktree, project):
        """A private home for one worker, so two of them cannot share a database.

        OpenCode keeps its session database and its caches under the XDG
        directories; two clients writing one database is a corruption that shows
        up as a mysterious failure in whichever client lost the race. Compose is
        pointed at the job's own project and at the prebuilt files, which is what
        keeps the stack from rebuilding dependencies per run.
        """
        home = os.path.join(self.cfg.state_dir, "workers", f"issue-{number}")
        env = dict(os.environ)
        env.update({
            "XDG_DATA_HOME": os.path.join(home, "data"),
            "XDG_CONFIG_HOME": os.path.join(home, "config"),
            "XDG_STATE_HOME": os.path.join(home, "state"),
            "XDG_CACHE_HOME": os.path.join(home, "cache"),
            "OPENCODE_DB": os.path.join(home, "data", "opencode.db"),
            "COMPOSE_PROJECT_NAME": project,
            "COMPOSE_FILE": "docker-compose.yml:docker-compose.dev.yml:"
                            "docker-compose.prebuilt.yml",
            "MRMAP_AGENT_ISSUE": str(number),
            "MRMAP_AGENT_WORKTREE": worktree,
            # The last line of defence, and the reason it is here rather than in
            # the prompt: `--auto` approves what a worker asks for, so what it
            # must never do is stated as a deny rule the model cannot argue with.
            # Deny wins over allow, so a merge or a force-push is refused by the
            # client even if the prompt, the issue text or a tool result asks for
            # it in the same breath.
            "OPENCODE_CONFIG_CONTENT": json.dumps(
                {"permissions": self.cfg.get("worker_permissions")
                 or config_module.WORKER_DENY_PERMISSIONS}, sort_keys=True),
        })
        for directory in WORKER_DIRS:
            os.makedirs(os.path.join(home, directory), exist_ok=True)
        os.makedirs(home, exist_ok=True)
        os.chmod(home, 0o700)
        return env

    def _job_of(self, lease):
        from .scheduler import Job

        return Job(number=lease["issue"], title="", branch=lease["branch"] or "",
                   worktree=lease["worktree"], project=lease["project"],
                   needs=lease["needs"] or "stack")

    def _session(self, number, run_id):
        prefix = str(self.cfg.get("session_prefix") or "mrmap")
        return f"ses_{prefix}-{number}-{run_id}"

    def _log_path(self, number, run_id):
        directory = self.cfg.log_dir
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, f"issue-{number}-{run_id}.ndjson")
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
        return path

    def _run_id(self):
        return str(int(time.time()))

    def _git(self, root, args, check=True):
        proc = subprocess.run(["git", "-C", root] + args, capture_output=True,
                              text=True, timeout=300)
        if check and proc.returncode != 0:
            raise StartError(f"git {' '.join(args[:1])} failed: {_last_line(proc.stderr)}")
        return proc

    def _signal(self, lease, signal_number):
        """Signal the worker's group, never a pid we only believe we own."""
        pgid = lease.get("pgid")
        if not pgid:
            return False
        try:
            os.killpg(int(pgid), signal_number)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            self.store.event("cancel-refused", f"pgid {pgid} belongs to another user",
                             issue=lease["issue"])
            return False

    def _log_ending(self, lease):
        """What the last line of the worker's own log says how it ended.

        ``error`` and ``end`` are what OpenCode's NDJSON reports; anything else -
        no log, an unreadable last line, a run cut off mid-event - is
        ``unfinished``, which is the reading that keeps the issue resumable
        instead of declaring a verdict nobody measured.
        """
        directory = self.cfg.log_dir
        if not os.path.isdir(directory) or not lease.get("session"):
            return "unfinished"
        candidate = sorted(
            (os.path.join(directory, name) for name in os.listdir(directory)
             if name.startswith(f"issue-{lease['issue']}-")),
            key=os.path.getmtime)
        if not candidate:
            return "unfinished"
        try:
            with open(candidate[-1], "rb") as handle:
                last = _tail_line(handle)
        except OSError:
            return "unfinished"
        try:
            event = json.loads(last)
        except ValueError:
            return "unfinished"
        kind = str(event.get("type") or event.get("event") or "")
        if kind in LOG_ERROR:
            return "error"
        if kind in LOG_END:
            return "end"
        return "unfinished"

    # -- what an operator asks for --------------------------------------------

    def logs(self, number, tail=40):
        """The worker's own log, newest lines first in reading order."""
        directory = self.cfg.log_dir
        if not os.path.isdir(directory):
            return "", None
        files = sorted((os.path.join(directory, name) for name in os.listdir(directory)
                        if name.startswith(f"issue-{number}-")), key=os.path.getmtime)
        if not files:
            return "", None
        with open(files[-1], "r", errors="replace") as handle:
            lines = handle.read().splitlines()
        return "\n".join(lines[-int(tail):]), files[-1]

    def cleanup_stack(self, number, project, volumes=True):
        """Tear down the stack of one job, and only that stack.

        The name is the whole safety argument, so it is checked twice: the shape
        of an agent project, and that it is the project of this issue. There is
        no ``--remove-orphans`` and no global prune here, because the repository's
        own rule is that those commands have wiped foreign stacks by matching on
        the compose file rather than the project.
        """
        if not is_our_project(project, number):
            raise StartError(f"refusing to tear down {project}: not the project of "
                             f"#{number}")
        argv = [DOCKER_COMMAND, "compose", "-p", project, "down"]
        if volumes:
            argv.append("--volumes")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600)
        self.store.event("stack-torn-down",
                         f"{project} rc={proc.returncode}", issue=number)
        if proc.returncode != 0:
            raise StartError(f"the stack {project} could not be torn down: "
                             f"{_last_line(proc.stderr or proc.stdout)}")
        return True


def shutil_filecopy(source, target):
    """One file, contents never in memory longer than the buffer needs."""
    with open(source, "rb") as read_handle, open(target, "wb") as write_handle:
        while True:
            block = read_handle.read(65536)
            if not block:
                break
            write_handle.write(block)


def _tail_line(handle, limit=64 * 1024):
    """The last non-empty line of a growing log, without reading the whole file."""
    try:
        size = os.fstat(handle.fileno()).st_size
        handle.seek(max(0, size - limit))
        data = handle.read()
    except OSError:
        return ""
    lines = [one for one in data.decode("utf-8", "replace").splitlines() if one.strip()]
    return lines[-1] if lines else ""


def _process_state(pid):
    """The one-letter process state from ``/proc/<pid>/stat``, or "" if unknown.

    The fields are read after the last ``)`` because the command name can contain
    spaces and parentheses, which is exactly where a naive split() goes wrong.
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as handle:
            tail = handle.read().decode("utf-8", "replace").rsplit(")", 1)[-1].split()
    except OSError:
        return ""
    return tail[0] if tail else ""


def _group_has_live_member(pgid):
    """Whether any member of the process group is a process rather than a zombie.

    Only needed for a worker this process did not start - after a restart, the
    group is all that is left of it. Reading the process table is cheap and it is
    the only reading that does not mistake a zombie for a worker.
    """
    for entry in _numeric_proc_dirs():
        try:
            with open(f"/proc/{entry}/stat", "rb") as handle:
                fields = handle.read().decode("utf-8", "replace").rsplit(")", 1)[-1].split()
        except OSError:
            continue
        # after the command name: state, ppid, pgrp, ...
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
            return True
    return False


def _numeric_proc_dirs():
    try:
        return [one for one in os.listdir("/proc") if one.isdigit()]
    except OSError:
        return []


def _last_line(text):
    lines = [one for one in (text or "").splitlines() if one.strip()]
    return lines[-1][:200] if lines else "no output"
