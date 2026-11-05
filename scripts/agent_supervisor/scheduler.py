"""The queue: one tick, one decision per issue, one lease per start.

A tick is a small, boring loop, and the boringness is the point:

1. forget plans whose runner never showed up (a supervisor killed mid-start),
2. look at what is already running and stop anything a human just un-approved,
3. list the open issues carrying the approval label - one call, not one per issue,
4. put them in a deterministic order, drop the ones the gate refuses, the ones
   somebody else claimed, the ones this host already holds and the ones in backoff,
5. ask the capacity gate whether the host still fits a job, and
6. start at most what both the configured ceilings and the gate allow.

Everything outside those six steps belongs to somebody else: the gate decides
eligibility (#1058), ``scripts/wip`` decides who holds an issue,
``scripts/agent_capacity`` decides whether the host fits one more job, and the
runner decides how an OpenCode process is born (#1060). This module decides
*order and permission* and remembers the result in SQLite, so that a restart
cannot start the same issue twice.

Two of the acceptance points of #1059 and where they come from:

*Two ticks, or two supervisor processes, cannot start one issue.* Locally that
is the lease table: its primary key is the issue number and ``claim_lease`` is
one immediate transaction, so the second claimer is told "no". Across hosts it
is the claim board: the runner files ``scripts/wip claim`` inside its own worktree
before it edits a file, and wip refuses a foreign live claim there.

*External claims are respected.* A live claim by any other client - a human in VS
Code, a Codex session, another machine's supervisor - is enough to skip the
issue. A stale claim only warns, because that is wip's own rule and the
supervisor is one client among others, not above them.
"""

import time

from . import approvals
from .capacity import Capacity, NEED_STACK
from .claims import Claims
from . import gh
from .gh import GhError
from .store import LIVE_STATES, Store, human_age


class StartError(Exception):
    """A start that was allowed and then could not be performed. The scheduler
    records the attempt, backs that issue off and moves on: one broken worktree
    must not end the tick, and one unavailable registry must not stop the queue."""


class Job:
    """Everything the runner needs about one issue, and nothing else."""

    def __init__(self, number, title, branch, worktree, project, needs=NEED_STACK):
        self.number = number
        self.title = title
        self.branch = branch
        self.worktree = worktree
        self.project = project
        self.needs = needs

    def as_dict(self):
        return {"issue": self.number, "title": self.title, "branch": self.branch,
                "worktree": self.worktree, "project": self.project, "needs": self.needs}

    def __repr__(self):
        return f"<Job #{self.number} {self.branch}>"


class Scheduler:
    """``runner`` is the seam #1060 fills: ``start(job)`` returns a handle and
    ``cancel(lease, reason)`` asks a running worker to leave. Without one the tick
    still lists, orders, leases and reports - which is all this issue can
    honestly claim to have verified."""

    def __init__(self, cfg, store=None, capacity=None, claims=None, runner=None):
        self.cfg = cfg
        self.store = store or Store.for_config(cfg)
        self.capacity = capacity or Capacity(cfg)
        self.claims = claims or Claims(cfg)
        self.runner = runner

    # -- listing and ordering ----------------------------------------------

    def candidates(self):
        """Open issues carrying the approval label, as one listing.

        Prefiltered by label rather than read one by one: the gate checks each
        candidate properly, but the *listing* is the expensive request and a
        repository's whole open-issue list is not something to fetch once per
        issue per tick.
        """
        try:
            return gh.list_paginated(
                f"repos/{self.cfg.repo}/issues",
                {"state": "open", "labels": self.cfg.get("approved_label")})
        except GhError as exc:
            self.store.event("list-failed", f"{exc.kind}: {exc}")
            return []

    def order(self, issues):
        """Priority labels first, then the oldest, then the number.

        Deterministic means one listing always produces one order, so two ticks
        agree and an operator can predict what runs next. Oldest-first inside a
        rank is the fairness rule - without it, a queue fed with new issues would
        starve the old ones forever.
        """
        wanted = [str(x).lower() for x in (self.cfg.get("priority_labels") or [])]

        def rank(issue):
            names = {(one.get("name") or "").lower() for one in (issue.get("labels") or [])}
            for position, label in enumerate(wanted):
                if label in names:
                    return position
            return len(wanted)

        return sorted(issues, key=lambda item: (rank(item), item.get("created_at") or "",
                                                item.get("number") or 0))

    # -- the tick -----------------------------------------------------------

    def tick(self, plan_only=False):
        """One pass. The report is what `supervisor tick` prints and what the
        daemon of #1063 logs; every field is a list of printable tuples."""
        report = {"started": [], "planned": [], "skipped": [], "stopping": [],
                  "errors": [], "capacity": None, "considered": 0}
        if not self.cfg.ok:
            report["errors"].extend(self.cfg.problems)
            self.store.event("config-invalid", "; ".join(self.cfg.problems))
            return report

        self._forget_dead_plans()
        report["stopping"] = self._sweep_running()

        issues = self.candidates()
        report["considered"] = len(issues)
        if not issues:
            self.store.event("tick", self._summary_line(report))
            return report

        limit = max(1, int(self.cfg.get("max_candidates_per_tick") or 10))
        candidates = self.order(issues)[:limit]
        if len(issues) > limit:
            report["skipped"].append(("<rest>", "per-tick-limit",
                                      f"{len(issues) - limit} issue(s) wait for the next tick"))

        # One board read for the candidate set, before any per-issue work: reading
        # claims costs one call per issue, so it is done for the issues that got
        # this far and not for the ones the gate had already refused.
        board = self._claims_on([item["number"] for item in candidates])
        if board is None:
            report["errors"].append("the claim board could not be read; nothing is started "
                                    "in a tick that cannot tell who already holds an issue")
            self.store.event("tick", self._summary_line(report) + ", board unreadable")
            return report

        slots = self._slots(report)
        # Decide every candidate before choosing between them. Checking the slot
        # first would be cheaper but would make the tick report say "no slot"
        # about issues nobody ever approved, and "why did this one wait?" is the
        # question an operator actually asks. `max_candidates_per_tick` is what
        # bounds the reading, not the slot count.
        verdicts = [(issue, self._reason_not_started(issue["number"], issue,
                                                     board.get(issue["number"])))
                    for issue in candidates]
        taken = 0
        for issue, blocked in verdicts:
            number = issue["number"]
            if blocked:
                report["skipped"].append((number,) + blocked)
                continue
            if taken >= slots:
                report["skipped"].append((number, "no-slot",
                                          f"{slots} job(s) fit this tick"))
                continue
            taken += 1
            self._start(issue, report, plan_only=plan_only)

        self.store.event("tick", self._summary_line(report))
        return report

    def _summary_line(self, report):
        parts = [f"considered {report.get('considered', 0)}",
                 f"started {len(report['started'])}", f"planned {len(report['planned'])}",
                 f"stopping {len(report['stopping'])}", f"skipped {len(report['skipped'])}"]
        if report.get("capacity"):
            parts.append(f"capacity {report['capacity']['verdict']}")
        if report.get("errors"):
            parts.append(f"errors {len(report['errors'])}")
        return ", ".join(parts)

    # -- what keeps an issue from starting ------------------------------------

    def _reason_not_started(self, number, issue, payloads):
        """The first reason this issue does not start now, or None.

        The gate first: its answer is the one no shortcut further down may
        bypass. Then the board, then our own state.
        """
        cached = self._cached_refusal(number)
        if cached:
            return cached

        decision = approvals.decide(self.cfg, number, issue=issue)
        self.store.record_verdict(number, decision.eligible, decision.reason)
        if not decision.eligible:
            return (decision.code, decision.detail)

        fresh, stale = self.claims.holders(payloads)
        others = [holder for holder in fresh if holder != self._client_tag(number)]
        if others:
            return ("claimed-elsewhere", f"{', '.join(sorted(others))} holds a live claim")
        if stale:
            self.store.event("stale-claim", f"{', '.join(stale)} on #{number}", issue=number)

        lease = self.store.lease(number)
        if lease and lease["state"] in LIVE_STATES:
            return ("held-here", f"lease is {lease['state']} since "
                                 f"{human_age(lease['started_at'])}")
        if not self.store.ready_for_retry(number):
            return ("in-backoff", "an earlier attempt on this issue failed recently")
        return None

    def _cached_refusal(self, number):
        """Reuse a refusal that cannot have changed within `verdict_cache_s`.

        The rate-limit measure: a refusal whose cause is a human who has not
        labelled the issue yet gains nothing from a fresh timeline read every
        minute, while a refusal whose cause is GitHub being unreachable or
        rate-limiting may be gone by the next tick and is never cached.
        """
        row = self.store.verdict(number)
        if not row or row["eligible"]:
            return None
        window = float(self.cfg.get("verdict_cache_s") or 0)
        if time.time() - (row["decided_at"] or 0) > window:
            return None
        kind = (row["reason"] or "").split(":", 1)[0]
        if kind in (approvals.HISTORY_UNAVAILABLE, approvals.ISSUE_UNAVAILABLE):
            return None
        return (kind, f"(cached {row['reason']}, {human_age(row['decided_at'])} ago)")

    # -- capacity ------------------------------------------------------------

    def _slots(self, report):
        """How many jobs may start this tick: the smaller of the configured
        ceilings and the capacity gate's answer. A gate that cannot answer counts
        as zero, not as unlimited."""
        live = self.store.active_leases()
        stacks = [lease for lease in live if lease.get("needs") == NEED_STACK]
        free_processes = max(0, int(self.cfg.get("max_opencode_processes") or 1) - len(live))
        free_stacks = max(0, int(self.cfg.get("max_test_stacks") or 1) - len(stacks))
        verdict = self.capacity.evaluate(NEED_STACK)
        report["capacity"] = verdict
        if not verdict["fits"]:
            self.store.event("capacity", verdict["explanation"])
            return 0
        return max(0, min(free_processes, free_stacks))

    # -- starting and stopping ----------------------------------------------

    def _start(self, issue, report, plan_only):
        number = issue["number"]
        job = self._job(issue)
        if plan_only:
            report["planned"].append((number, job.branch, job.needs))
            self.store.event("planned", f"{job.branch} ({job.needs})", issue=number)
            return
        if not self.store.claim_lease(number, self.cfg.repo, job.needs,
                                      branch=job.branch, worktree=job.worktree,
                                      project=job.project):
            report["skipped"].append((number, "lease-taken",
                                      "another supervisor process took it first"))
            return
        if self.runner is None:
            # The runner is #1060. Until it exists, a plan is the honest answer,
            # and a plan nobody adopts is aged out so the issue is not blocked.
            report["planned"].append((number, job.branch, job.needs))
            self.store.event("no-runner", "no runner configured; the lease stays planned "
                                          "until one adopts it", issue=number)
            return
        try:
            handle = self.runner.start(job) or {}
        except StartError as exc:
            attempts = self.store.note_attempt(number,
                                               float(self.cfg.get("retry_backoff_s") or 900))
            self.store.release_lease(number, state="failed", detail=str(exc))
            report["errors"].append(f"#{number}: {exc}")
            self.store.event("start-failed", f"attempt {attempts}: {exc}", issue=number)
            return
        self.store.update_lease(number, state="running", pid=handle.get("pid"),
                                pgid=handle.get("pgid"), session=handle.get("session"),
                                project=handle.get("project"), worktree=handle.get("worktree"),
                                branch=handle.get("branch"), detail="")
        self.store.reset_attempts(number)
        self.store.event("started", f"{job.branch} pid={handle.get('pid')}", issue=number)
        report["started"].append((number, job.branch, handle.get("pid")))

    def _sweep_running(self):
        """Stop what a human just withdrew.

        The gate is asked again for every live lease: a pause, a removed label or
        a closed issue *mid-flight* is exactly the case nobody remembers to
        handle, and the acceptance of #1058 says a withdrawal is effective on the
        next read. Stopping itself is the runner's act and it keeps the branch,
        the worktree and the logs - what the human withdrew was the automation's
        permission to act, not the value of the work done so far.
        """
        stopping = []
        for lease in self.store.active_leases():
            if lease["state"] == "stopping":
                stopping.append((lease["issue"], "already stopping"))
                continue
            decision = approvals.decide(self.cfg, lease["issue"])
            if decision.eligible:
                continue
            self.store.update_lease(lease["issue"], state="stopping",
                                    detail=f"withdrew: {decision.reason}")
            self.store.event("cancelling", decision.reason, issue=lease["issue"])
            if self.runner is not None:
                try:
                    self.runner.cancel(lease, decision.reason)
                except Exception as exc:            # a runner that cannot stop it
                    self.store.update_lease(lease["issue"], state="abandoned",
                                            detail=f"the runner could not stop it: {exc}")
                    self.store.event("cancel-failed", str(exc), issue=lease["issue"])
            stopping.append((lease["issue"], decision.reason))
        return stopping

    def _forget_dead_plans(self):
        dropped = self.store.age_out_plans(float(self.cfg.get("plan_ttl_s") or 900))
        if dropped:
            self.store.event("aged-out", f"{dropped} planned lease(s) never started")

    # -- small helpers -------------------------------------------------------

    def _job(self, issue):
        number = issue["number"]
        return Job(number=number, title=issue.get("title") or "",
                   branch=f"agent/issue-{number}-{_slug(issue.get('title'))}",
                   worktree=f"{self.cfg.worktree_root}/issue-{number}",
                   project=f"mrmap-agent-{number}-{int(time.time())}")

    def _client_tag(self, number):
        return self.claims.our_client_tag(f"{self.cfg.worktree_root}/issue-{number}")

    def _claims_on(self, numbers):
        """{issue: claim payloads}, or None when the board cannot be read - in
        which case the tick starts nothing. A late start costs an hour; a start
        against a human's in-progress branch costs their work."""
        try:
            return self.claims.claims_on(numbers)
        except Exception as exc:
            self.store.event("board-unreadable", str(exc))
            return None


def _slug(title, limit=32):
    """A branch-safe echo of the issue title. Meaningful, not unique - the number
    in front of it is what makes the branch unique."""
    text = "".join(char if char.isalnum() else "-" for char in (title or "").lower())
    while "--" in text:
        text = text.replace("--", "-")
    return text.strip("-")[:limit].rstrip("-") or "work"
