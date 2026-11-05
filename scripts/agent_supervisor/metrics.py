"""What the supervisor has run, waited for, and cost - without inventing numbers.

The epic asks for queue wait, active slots, per-issue duration, PR CI time, retry
counts, OOM events and worktree/Compose leftovers. All of them are answerable
from state the supervisor already keeps: the lease table, the verdict table, the
CI and review watch rows, the host's capacity gate. None of them needs a second
accounting system, and the design rule here follows from that: **a number is
either read from its real source or reported as unknown** - never a zero. A
``0`` in a metrics report has to mean "measured, none", because after a week of
nightly runs the operator's question is "did it ever happen" and a default
indistinguishable from "not measured" answers that wrong.

Two deliberate absences:

* No GitHub reads. This module runs from the SQLite file, the capacity gate and
  two host commands, so it is cheap enough to run beside every tick and honest
  about the boundary: exact CI wall-clock belongs to GitHub; what is here is
  *when the watcher saw what it saw*, and every field says which of the two it
  is.
* No mutation. Not one cleanup here deletes anything; leftovers are reported
  with their exact names and the command that would review them, because the
  ownership rules in ``AGENTS.md`` make deletion a per-project decision, not a
  periodic sweep's.

Durations and identity note: the lease table keys on the issue and a re-claim
overwrites the row, so a per-issue duration is *the last run on record*, not a
lifetime sum. The field name says so.
"""

import json
import os
import statistics
import subprocess
import time

from .capacity import Capacity
from .daemon import status as daemon_status
from .store import LIVE_STATES, Store

# Host commands have to die before the report does. The cap is per command, and
# a timeout is reported as unknown, not as an empty list.
COMMAND_TIMEOUT_S = 10


def _duration(seconds):
    """Seconds as a printable duration, or None for "nothing measured"."""
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds / 3600:.1f}h"


def _median(values):
    return statistics.median(values) if values else None


def collect(cfg, store=None, capacity=None, now=None):
    """The whole report, one dict, JSON-shaped. Never raises on a bad source."""
    now = now if now is not None else time.time()
    store = store or Store.for_config(cfg)
    state = store.status()
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "daemon": daemon_status(cfg),
        "slots": _slots(cfg, store),
        "queue": _queue(state, now),
        "runs": _runs(state, now),
        "ci": _ci(state["pulls"], store),
        "reviews": _reviews(state),
        "retries": _retries(state, now),
        "host": _host(capacity or Capacity(cfg)),
        "leftovers": _leftovers(cfg, store),
    }


# ---------------------------------------------------------------------------
# what the state file knows

def _slots(cfg, store):
    live = store.active_leases()
    running = [one for one in live if one["state"] == "running"]
    planned = [one for one in live if one["state"] == "planned"]
    stacks = [one for one in running if one.get("needs") == "stack"]
    return {
        "workers_running": len(running),
        "workers_max": int(cfg.get("max_opencode_processes") or 0),
        "stacks_running": len(stacks),
        "stacks_max": int(cfg.get("max_test_stacks") or 0),
        "planned_waiting_runner": len(planned),
        "issues": sorted(one["issue"] for one in running),
    }


def _queue(state, now):
    """How long approved issues have waited since their last gate decision.

    Honest about what it measures: ``decided_at`` is the last time the gate
    answered for that issue, so the wait is "eligible since", not "approved
    since". The difference is the verdict cache, and it is in the name of the
    field rather than hidden under a prettier one.
    """
    live = {one["issue"] for one in state["leases"] if one["state"] in LIVE_STATES}
    waiting = []
    for row in state["verdicts"]:
        if not row["eligible"] or row["issue"] in live:
            continue
        waiting.append({"issue": row["issue"], "since_last_decision_s":
                        max(0, int(now - row["decided_at"])), "reason": row["reason"]})
    waits = [one["since_last_decision_s"] for one in waiting]
    return {
        "eligible_waiting": len(waiting),
        "oldest_wait": _duration(max(waits) if waits else None),
        "median_wait": _duration(_median(waits)),
        "detail": sorted(waiting, key=lambda one: -one["since_last_decision_s"])[:10],
    }


def _runs(state, now):
    """Per-issue worker duration for the lease rows still on record."""
    live = {one["issue"] for one in state["leases"] if one["state"] in LIVE_STATES}
    rows = []
    for lease in state["leases"]:
        start = lease.get("started_at")
        if not start:
            continue
        end = lease.get("finished_at")
        rows.append({
            "issue": lease["issue"], "state": lease["state"],
            "last_run_duration": _duration((end or now) - start),
            "measured": "running" if lease["issue"] in live else lease["state"],
        })
    durations = [one["finished_at"] - one["started_at"] for one in state["leases"]
                 if one.get("finished_at") and one.get("started_at")]
    return {
        "runs_on_record": len(rows),
        "completed_on_record": len(durations),
        "median_completed": _duration(_median(durations)),
        "longest_completed": _duration(max(durations) if durations else None),
        "per_issue": sorted(rows, key=lambda one: one["issue"]),
        "note": "the lease row is per issue and a re-claim overwrites it: this is "
                "the last run on record, not a lifetime sum",
    }


def _ci(rows, store):
    """What the CI watcher saw, per pull request, from its own tables.

    ``ci_seen`` records the checks that *needed doing something* (a repair or an
    escalation) plus their time, and ``pull_requests.last_seen`` moves on every
    pass that could read the PR. So the report can honestly say when trouble was
    first and last seen and when the watcher saw all-green; the exact wall-clock
    of a GitHub pipeline stays on GitHub.
    """
    seen = store.ci_seen_summary()
    per_pr = {}
    for row in seen:
        bucket = per_pr.setdefault(row["pr"], {"first_finding": row["seen_at"],
                                               "last_finding": row["seen_at"],
                                               "findings": 0, "heads": set()})
        bucket["first_finding"] = min(bucket["first_finding"], row["seen_at"])
        bucket["last_finding"] = max(bucket["last_finding"], row["seen_at"])
        bucket["findings"] += 1
        bucket["heads"].add((row["head_sha"] or "")[:8])
    out = []
    for row in rows:
        watch = per_pr.get(row["pr"], {})
        green_at = row["last_seen"] if row["state"] == "green" else None
        span = None
        if watch and (green_at or watch.get("last_finding")):
            span = (green_at or watch["last_finding"]) - watch["first_finding"]
        out.append({
            "issue": row["issue"], "pr": row["pr"], "state": row["state"],
            "repair_cycles": row["attempts"],
            "escalated": row["escalated_at"] is not None,
            "first_finding_seen": _stamp(watch["first_finding"]) if watch else None,
            "watch_span": _duration(span) if span and span > 0 else None,
            "heads_with_findings": sorted(watch.get("heads", set())),
        })
    return {
        "watched": len(rows),
        "green": sum(1 for one in rows if one["state"] == "green"),
        "repair_cycles_total": sum(one["attempts"] for one in rows),
        "escalated_total": sum(1 for one in rows if one["escalated_at"] is not None),
        "per_pr": out,
    }


def _reviews(state):
    rows = state.get("reviews", [])
    return {
        "watched": len(rows),
        "answer_cycles_total": sum(one["attempts"] for one in rows),
        "answered": sum(1 for one in rows if one["state"] == "responded"),
        "waiting_human": sum(1 for one in rows if one["state"] == "waiting-human"),
        "states": sorted({one["state"] for one in rows}),
    }


def _retries(state, now):
    verdicts = state["verdicts"]
    return {
        "gate_refusals_total": sum(one["attempts"] for one in verdicts),
        "in_backoff": sum(1 for one in verdicts if one["next_try_at"] > now),
        "ci_repairs_total": sum(one["attempts"] for one in state["pulls"]),
        "review_answers_total": sum(one["attempts"] for one in state.get("reviews", [])),
    }


def _stamp(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


# ---------------------------------------------------------------------------
# what the host knows

def _host(capacity):
    """The capacity gate's own numbers, including the OOM counters it reads.

    One call, the class a worker most cares about (``process``: another worker
    without a stack). The gate never raises, and a gate that is not installed
    says so as ``verdict: unknown`` instead of an empty section.
    """
    answer = capacity.evaluate(need="process")
    metrics = answer.get("metrics") or {}
    keep = ("load_per_core", "mem_effective_gb", "mem_host_available_gb",
            "mem_cgroup_limit_gb", "mem_cgroup_headroom_gb", "mem_cgroup_used_pct",
            "mem_pressure_avg10", "disk_free_gb", "stacks", "stacks_max",
            "processes", "processes_max", "oom_events", "pids")
    return {
        "verdict": answer.get("verdict"),
        "fits": answer.get("fits"),
        "explanation": answer.get("explanation"),
        "metrics": {key: metrics[key] for key in keep if key in metrics},
    }


def _leftovers(cfg, store):
    """Worktrees and Compose projects that no live lease accounts for.

    Both reads are capped and both are report-only. The lease table is the
    ownership ledger here: a path or project a live lease names is *in use*,
    anything else under the agent roots is a candidate the operator reviews -
    deletion needs the per-project ownership check the AGENTS.md rules demand,
    which a periodic table cannot do.
    """
    return {"worktrees": _worktrees(cfg, store), "compose": _compose(cfg, store)}


def _worktrees(cfg, store):
    root = cfg.worktree_root
    owned = {one.get("worktree") for one in store.active_leases() if one.get("worktree")}
    repo = cfg.repo_root
    if not repo or not os.path.isdir(repo):
        return {"reading": "unknown", "reason": f"repo_root {repo or '(unset)'} is not "
                                                "a directory, so nothing was listed"}
    raw, problem = _run(["git", "-C", repo, "worktree", "list", "--porcelain"])
    if problem:
        return {"reading": "unknown", "reason": problem}
    paths = [line[len("worktree "):] for line in raw.splitlines()
             if line.startswith("worktree ")]
    under = [one for one in paths if root and os.path.abspath(one).startswith(
        os.path.abspath(root) + os.sep)]
    orphans = [one for one in under if one not in owned]
    return {"reading": "ok", "under_worktree_root": len(under),
            "not_owned_by_a_lease": orphans,
            "review_with": f"git -C {repo} worktree prune -n"}


def _compose(cfg, store):
    if not _docker_present():
        return {"reading": "unavailable", "reason": "no docker socket the CLI can reach"}
    raw, problem = _run(["docker", "ps", "-a", "--format",
                         "{{.Label \"com.docker.compose.project\"}}\t{{.Names}}\t"
                         "{{.Status}}"])
    if problem:
        return {"reading": "unknown", "reason": problem}
    owned = {one.get("project") for one in store.active_leases() if one.get("project")}
    rows = []
    for line in raw.splitlines():
        project, _, rest = line.partition("\t")
        name, _, status = rest.partition("\t")
        # The runner's own prefix is the identifier; see runner.project_name.
        if project.startswith("mrmap-agent-") or name.startswith("mrmap-agent-"):
            rows.append({"project": project, "container": name, "status": status,
                         "owned_by_a_lease": project in owned})
    orphans = sorted({one["project"] for one in rows if not one["owned_by_a_lease"]})
    return {"reading": "ok", "agent_containers": len(rows), "projects": orphans,
            "review_with": "docker ps -a --filter "
                           "label=com.docker.compose.project=<project> before removing"}


def _docker_present():
    raw, problem = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    return not problem


def _run(argv):
    """Run with a cap; return (stdout, None) or ("", reason). Never raises."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              timeout=COMMAND_TIMEOUT_S)
    except FileNotFoundError:
        return "", f"{argv[0]} is not installed"
    except subprocess.TimeoutExpired:
        return "", f"{argv[0]} did not answer within {COMMAND_TIMEOUT_S}s"
    except OSError as exc:
        return "", f"{argv[0]} could not run: {exc}"
    if proc.returncode != 0:
        return "", f"{argv[0]} exited {proc.returncode}: " \
                   f"{(proc.stderr or '').strip()[:200]}"
    return proc.stdout, None


# ---------------------------------------------------------------------------
# printing

def as_text(report):
    """The ``metrics`` command's output: one line per section, unknown printed."""
    lines = []
    daemon = report["daemon"]
    state = "running" if daemon["running"] else "not running"
    if daemon.get("pid"):
        state += f", pid {daemon['pid']}"
    if daemon["paused"]:
        state += f", PAUSED: {(daemon.get('paused') or {}).get('reason', '')}"
    config = "ok" if daemon["config_ok"] else "refusing: " + "; ".join(daemon["problems"])
    lines.append(f"daemon: {state}; config {config}")
    slots = report["slots"]
    planned = (f", {slots['planned_waiting_runner']} planned waiting for a runner"
               if slots["planned_waiting_runner"] else "")
    lines.append(f"slots: {slots['workers_running']}/{slots['workers_max']} workers, "
                 f"{slots['stacks_running']}/{slots['stacks_max']} stacks{planned}")
    queue = report["queue"]
    lines.append(f"queue: {queue['eligible_waiting']} eligible waiting, oldest "
                 f"{queue['oldest_wait'] or '-'}, median {queue['median_wait'] or '-'}"
                 " (since the last gate decision)")
    runs = report["runs"]
    lines.append(f"runs on record: {runs['completed_on_record']} completed, "
                 f"median {runs['median_completed'] or '-'}, longest "
                 f"{runs['longest_completed'] or '-'}")
    ci = report["ci"]
    lines.append(f"ci: {ci['watched']} pr(s) watched, {ci['green']} seen green, "
                 f"{ci['repair_cycles_total']} repair cycle(s), "
                 f"{ci['escalated_total']} escalated")
    reviews = report["reviews"]
    lines.append(f"reviews: {reviews['watched']} watched, "
                 f"{reviews['answer_cycles_total']} answer cycle(s), "
                 f"{reviews['waiting_human']} waiting for a human")
    retries = report["retries"]
    lines.append(f"retries: {retries['gate_refusals_total']} gate refusal attempt(s), "
                 f"{retries['in_backoff']} in backoff")
    host = report["host"]
    oom = (host.get("metrics") or {}).get("oom_events") or {}
    lines.append(f"host: capacity {host['verdict']}"
                 f"{', ' + str(host['explanation']) if host.get('explanation') else ''}")
    lines.append(f"oom events: cgroup {oom.get('oom', 'unknown')}, "
                 f"oom-kill {oom.get('oom_kill', 'unknown')}"
                 f"{', max ' + str(oom['max']) if oom.get('max') is not None else ''}")
    worktrees = report["leftovers"]["worktrees"]
    if worktrees["reading"] == "ok":
        lines.append(f"worktrees: {worktrees['under_worktree_root']} under the agent root, "
                     f"{len(worktrees['not_owned_by_a_lease'])} not owned by a lease"
                     + (": " + ", ".join(worktrees["not_owned_by_a_lease"])
                        if worktrees["not_owned_by_a_lease"] else ""))
    else:
        lines.append(f"worktrees: {worktrees['reading']} ({worktrees['reason']})")
    compose = report["leftovers"]["compose"]
    if compose["reading"] == "ok":
        lines.append(f"compose: {compose['agent_containers']} agent container(s), "
                     f"projects no lease owns: "
                     f"{', '.join(compose['projects']) or 'none'}")
    else:
        lines.append(f"compose: {compose['reading']} ({compose['reason']})")
    return "\n".join(lines)


def as_json(report):
    """Exactly one JSON document - the contract every --json command keeps."""
    return json.dumps(report, indent=2, default=str)
