"""Watch the CI of the pull requests this supervisor's workers opened (#1061).

A worker's job ends at a pull request; the checks that decide whether it can be
merged run for another ten minutes after the process is gone. Without a watcher
that gap looks like a finished task, and with a naive watcher it looks like an
agent that keeps pushing at a red pipeline. This module is the difference between
those two, and it comes down to one question per pass: *is this red something the
worker can still act on?*

The asymmetry that decides every rule below: acting on a failure that is really
infrastructure costs code churn against a broken runner - commits that fix
nothing, a branch that drifts, a reviewer who cannot tell what was ever wrong.
Missing a real code failure costs a human noticing one red check they were going
to read anyway. So a repair cycle needs *positive* evidence that the failure
names a test, a lint rule or a build, and everything else is reported rather than
repaired.

What it never does: approve, review, enqueue, merge, close a review thread,
rerun a workflow, or touch branch protection. There is no call here that can
write to a pull request at all - the only writes reachable from this module are
`scripts/wip`'s own question comment and the worker process the runner starts in
the issue's own worktree. And it never follows a pull request the supervisor does
not own: a row in `pull_requests` only appears from a lease this supervisor took.

Merge-queue runs are deliberately out of reach. A `merge_group` run belongs to a
merge commit GitHub builds itself, combining this branch with other pull requests
- a failure there may have nothing to do with this branch, and the fix is not
this worker's to make. The monitor reports `mergeStateStatus` and acts on nothing
but the pull request's own head SHA.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from . import gh                                              # noqa: E402
from .claims import Claims                                    # noqa: E402
from .config import WORKER_DENY_PERMISSIONS                   # noqa: E402
from .store import Store                                      # noqa: E402

# Text that names a real code failure. Matching is on lower-cased text of the
# check's own title, summary and annotations - what GitHub shows a reader - and
# each entry is here because it names a *result*, not a transport: a failing
# assertion is a fact about this branch, a timeout is a fact about a runner.
CODE_SIGNALS = (
    "assertionerror", "assert ", "failed tests", "failures=", "test suite failed",
    "failed test", "expected ", "did you forget", "no such table", "does not exist",
    "undefined symbol", "type error", "error ts", "ts[0-9]", "flake8", "e7[0-9][0-9]",
    "f8[0-9][0-9]", "pre-commit", "eslint", "npm err! cypress", "migration",
    "migrations for the following apps", "unexpected status", "html expected",
    "coverage report", "coverage threshold",
)

# Text that says the pipeline, not the branch, had a problem. Everything matched
# here ends up in front of a human, never in front of a worker.
INFRA_SIGNALS = (
    "could not resolve host", "temporary failure in name resolution", "no such host",
    "connection timed out", "connection refused", "tls handshake timeout",
    "i/o timeout", "network is unreachable", "econnreset", "eai_again",
    "bad gateway", "gateway timeout", "service unavailable", "internal server error",
    "503", "504", "429", "toomanyrequests", "rate limit",
    "no space left on device", "disk quota exceeded",
    "runner could not be found", "a runner with the following labels",
    "failed to complete the job", "job was cancelled", "stuck job",
    "cache service", "artifact service", "failed to download", "unable to retrieve",
    "cannot connect to the docker daemon", "docker daemon is not running",
    "buildx could not connect", "oomkilled", "exit code 137", "exit code 143",
)

# Conclusions that mean "this is not finished yet". A pending check is the normal
# state of a healthy pull request, so it is never news.
PENDING_STATES = ("queued", "in_progress", "waiting", "requested", "pending", "action_required")
# Conclusions that mean "nothing to do". `skipped` and `neutral` carry no verdict
# about the branch; `cancelled` means a human or GitHub stopped the run, which is
# a decision someone made on purpose and not a defect to repair.
QUIET = ("success", "skipped", "neutral")

# How long a finished lease is still looked up for a pull request it never got a
# row for. No MrMap pull request is opened thirty days after its worker stopped,
# and without a bound every pass would ask about every lease this supervisor ever
# took - the first thing a rate limit buys is a pass that reports nothing at all.
# Overridable the way the capacity gate's thresholds are.
LOOKBACK_S = float(os.environ.get("MRMAP_CI_LOOKBACK_S") or 30 * 86400)


def _haystack(check):
    """The text a reader of this check would see, lower-cased."""
    out = check.get("output") or {}
    parts = [check.get("name") or "", check.get("title") or "", check.get("message") or "",
             out.get("title") or "", out.get("summary") or "", out.get("text") or ""]
    for annotation in check.get("annotations") or []:
        parts.append(annotation.get("message") or "")
        parts.append(annotation.get("title") or "")
    return " ".join(parts).lower()


def _hits(text, signals):
    return [needle for needle in signals if needle in text]


def classify(check):
    """One check -> one verdict: green | pending | cancelled | code | infra | unknown.

    `unknown` is a real answer and the most common wrong-looking one: a check that
    fails with a message that names neither a test nor a transport problem stays
    with the human. Guessing "probably the agent's fault" is exactly the input
    that turns a flaky runner into a branch full of meaningless commits.
    """
    status = (check.get("status") or "").lower()
    conclusion = (check.get("conclusion") or check.get("code") or "").lower()
    if status in PENDING_STATES and not conclusion:
        return "pending", "still running"
    if conclusion in QUIET:
        return "green", conclusion
    if conclusion == "cancelled":
        return "cancelled", "someone cancelled this run - not a defect to repair"
    if conclusion == "timed_out":
        # A run that hit the workflow's own timeout is a runner story more often
        # than a branch story, and it is never worth a commit to find out.
        return "infra", "the run timed out at the workflow level"
    if conclusion in ("failure", "startup_failure", "stale"):
        text = _haystack(check)
        infra = _hits(text, INFRA_SIGNALS)
        code = _hits(text, CODE_SIGNALS)
        if infra and not code:
            return "infra", f"names the pipeline: {', '.join(infra[:3])}"
        if code and not infra:
            return "code", f"names the branch: {', '.join(code[:3])}"
        if code and infra:
            # Both readings are on the table. The human decides; a worker that
            # edits code while the runner is also on fire cannot tell which one it
            # fixed, and neither can the reviewer.
            return "infra", ("names both a test and the pipeline "
                             f"({', '.join(code[:2])} / {', '.join(infra[:2])})")
        return "unknown", "the failure text names neither a test nor a transport problem"
    if not conclusion:
        return "pending", f"no conclusion yet (status {status or 'unknown'})"
    return "unknown", f"conclusion {conclusion} is not classified here"


def line(check):
    """A short human-readable line about one check, for logs and for the question."""
    name = check.get("name") or check.get("context") or "?"
    conclusion = check.get("conclusion") or check.get("status") or "?"
    url = check.get("html_url") or check.get("target_url") or ""
    return f"{name}: {conclusion}{f' - {url}' if url else ''}"


class Monitor:
    """One pass over the pull requests the supervisor's own leases produced.

    `runner` is there for two honest reasons: to refuse a repair while a worker of
    that issue is still alive, and to restart it on its own session in its own
    worktree when a failure really is actionable. `ask` is `scripts/wip`'s
    question flow, which is how a human hears about this - the board, not a
    comment on the pull request.
    """

    def __init__(self, cfg, store=None, runner=None, claims=None):
        self.cfg = cfg
        self.store = store or Store.for_config(cfg)
        self.runner = runner
        self.claims = claims or Claims(cfg)

    # -- finding the pull request --------------------------------------------

    def find_pr(self, branch):
        """The open pull request whose head is `branch`, or None.

        Looked up by head ref, not by "linked issues": a pull request that forgot
        to write `Closes #123` is still the pull request of that branch, and the
        branch is the one thing this supervisor chose itself.
        """
        owner, _, name = self.cfg.repo.partition("/")
        data = gh.gh_json(f"repos/{self.cfg.repo}/pulls",
                          {"state": "open", "head": f"{owner}:{branch}", "per_page": 10})
        if not data:
            return None
        return max(data, key=lambda pr: int(pr.get("number") or 0))

    def pr_detail(self, number):
        return gh.gh_json(f"repos/{self.cfg.repo}/pulls/{number}")

    def checks(self, head_sha):
        """Check runs plus legacy commit statuses for one head SHA.

        Both endpoints, because a repository can mix them and a watcher that reads
        only one decides "all green" about a check it never saw. The head SHA is
        the reference - not `latest` and not the merge commit - so a `merge_group`
        run cannot sneak in here.
        """
        runs = ((gh.gh_json(f"repos/{self.cfg.repo}/commits/{head_sha}/check-runs",
                            {"per_page": 100}) or {}).get("check_runs") or [])
        statuses = ((gh.gh_json(f"repos/{self.cfg.repo}/commits/{head_sha}/status")
                     or {}).get("statuses") or [])
        folded = []
        for run in runs:
            folded.append({"name": run.get("name"), "status": run.get("status"),
                           "conclusion": run.get("conclusion"), "output": run.get("output"),
                           "html_url": run.get("html_url"), "id": run.get("id")})
        for status in statuses:
            folded.append({"name": status.get("context"), "status": "completed",
                           "conclusion": status.get("state"),
                           "title": status.get("description"),
                           "html_url": status.get("target_url"), "id": status.get("id")})
        return folded

    def track(self, issue=None):
        """Record the pull request of every lease this supervisor took.

        Finished leases count: a worker opens its pull request and exits, and the
        review that follows is precisely the gap this watcher is for. What is *not*
        followed is whatever else is open in the repository - a row only ever comes
        from a lease of this supervisor.

        Two bounds keep this from becoming a scan of history, because a pass that
        asks about every lease ever taken is a pass that runs into the rate limit
        and then reports nothing at all. A pull request already recorded as closed
        is not looked up again, and a lease that never produced a row is asked
        about for ``LOOKBACK_S`` after its last update. Naming an issue explicitly
        bypasses both: an operator who asks about one number gets an answer.
        """
        if issue:
            candidates = [self.store.lease(issue)]
            explicit = True
        else:
            candidates = self.store.status()["leases"]
            explicit = False
        leases = [lease for lease in candidates
                  if lease and lease.get("branch") and lease.get("session")]
        found, missing = [], []
        for lease in leases:
            row = self.store.pr_row(lease["issue"])
            if not explicit:
                if row and row["state"] == "closed":
                    continue
                if not row and time.time() - float(lease["updated_at"]) > LOOKBACK_S:
                    continue
            try:
                pr = self.find_pr(lease["branch"])
            except gh.GhError as exc:
                missing.append((lease["issue"], f"pull request lookup failed: {exc}"))
                continue
            if not pr:
                missing.append((lease["issue"], f"no open pull request on {lease['branch']}"))
                continue
            found.append(self.store.track_pr(lease["issue"], self.cfg.repo, int(pr["number"]),
                                             lease["branch"],
                                             (pr.get("head") or {}).get("sha") or ""))
        return found, missing

    # -- one pass ------------------------------------------------------------

    def watch(self, issue=None, dry_run=False):
        """Look at every tracked pull request once. Returns the report, changes nothing else."""
        tracked, missing = self.track(issue)
        report = []
        for row in tracked:
            report.append(self._one(row, dry_run))
        for number, why in missing:
            report.append({"issue": number, "action": "untracked", "detail": why})
        return report

    def _one(self, row, dry_run=False):
        issue, number = row["issue"], row["pr"]
        result = {"issue": issue, "pr": number, "action": "waiting", "detail": ""}
        try:
            detail = self.pr_detail(number)
            head = (detail.get("head") or {}).get("sha") or row.get("head_sha") or ""
            state = detail.get("state") or "open"
        except gh.GhError as exc:
            # A GitHub that will not answer is not a green pull request. Report it
            # and change nothing: the next pass asks again.
            result.update(action="unreadable", detail=str(exc))
            self.store.update_pr(issue, state="watching",
                                 detail=f"could not read the pull request: {exc}")
            return result
        if state != "open":
            self.store.update_pr(issue, state="closed", head_sha=head,
                                 detail=f"pull request is {state}")
            result.update(action="closed", detail=f"pull request is {state}")
            return result

        found = self.checks(head)
        verdicts = [classify(check) for check in found]
        buckets = {}
        for check, (verdict, why) in zip(found, verdicts):
            buckets.setdefault(verdict, []).append((check, why))
        summary = ", ".join(f"{name} {len(items)}" for name, items in sorted(buckets.items()))
        # Read, reported, never acted on: `mergeable_state` is GitHub's word about
        # the merge queue's view (behind, blocked, dirty, unstable), which is a
        # statement about other pull requests and branch protection. A queue run
        # belongs to a merge commit this worker never wrote, so repairing one would
        # mean editing this branch to answer somebody else's conflict.
        merge_state = detail.get("mergeable_state") or "unknown"
        result.update(head=head[:8], checks=len(found), verdicts=summary,
                      mergeable=merge_state)
        self.store.update_pr(issue, head_sha=head, detail=f"{summary} / {merge_state}")

        if buckets.get("code"):
            return self._repair(issue, number, head, buckets["code"], row, dry_run, result)
        if buckets.get("infra") or buckets.get("unknown"):
            return self._escalate(issue, number, head, buckets, row, dry_run, result)
        if buckets.get("pending") or buckets.get("cancelled"):
            self.store.update_pr(issue, state="waiting-ci")
            result.update(detail="nothing actionable" + (f": {summary}" if summary else ""))
            return result
        if not found:
            # No checks at all usually means the run has not registered yet.
            self.store.update_pr(issue, state="waiting-ci", detail="no checks reported yet")
            result.update(detail="no checks reported for this head yet")
            return result
        self.store.update_pr(issue, state="green")
        result.update(action="green", detail="all checks green - waiting for a human review")
        return result

    # -- the two actions ------------------------------------------------------

    def _budget(self, row, head):
        """Why a repair may not run, or "" when it may.

        Two limits, because they fail in different ways: the lifetime budget stops
        a pull request from consuming the supervisor forever, the per-head rule
        stops one red commit from being repaired twice - once by the pass that saw
        it and once by the pass that sees the same red check again while the worker
        is still pushing nothing.
        """
        attempts = int(row.get("attempts") or 0)
        budget = int(self.cfg.get("ci_repair_attempts") or 0)
        if attempts >= budget:
            return (f"budget spent ({attempts}/{budget} repair cycles for this pull request)")
        if row.get("repair_sha") == head:
            return f"head {head[:8]} was already repaired - a second repair needs a new commit"
        if self.runner is not None:
            lease = self.store.lease(row["issue"])
            if lease and self.runner.alive(lease):
                return "the worker of this issue is still running"
        return ""

    def _repair(self, issue, number, head, failures, row, dry_run, result):
        blocked = self._budget(row, head)
        names = [line(check) for check, _ in failures]
        if blocked:
            result.update(action="held", detail=blocked, failures=names)
            self.store.update_pr(issue, detail=blocked)
            return result
        prompt = self.prompt(number, head, failures)
        if dry_run:
            result.update(action="would-repair", detail=f"{len(failures)} actionable check(s)")
            return result
        try:
            started = self.runner.resume(issue, prompt=prompt)
        except Exception as exc:                      # a resume that cannot happen is reported
            result.update(action="repair-refused", detail=str(exc), failures=names)
            self.store.event("ci-repair-refused", f"pr={number} {exc}", issue=issue)
            return result
        attempts = int(row.get("attempts") or 0) + 1
        for check, why in failures:
            self.store.note_ci_seen(number, head, check.get("name") or "?", "code",
                                    check.get("id"))
        self.store.update_pr(issue, state="repairing", attempts=attempts, repair_sha=head,
                             detail=f"repaired on {head[:8]}: {', '.join(names)[:200]}")
        self.store.event("ci-repair", f"pr={number} attempt={attempts} "
                         f"checks={len(failures)} pid={started.get('pid')}", issue=issue)
        result.update(action="repairing", detail=f"attempt {attempts}, pid {started.get('pid')}",
                      failures=names)
        return result

    def _escalate(self, issue, number, head, buckets, row, dry_run, result):
        """Tell a human through the claim board, once per head SHA.

        The marker of "already told you" is written only after the question went
        out: a `wip ask` that failed must not leave the pull request looking
        reported, because then nobody would ever be told.
        """
        counted = (buckets.get("infra") or []) + (buckets.get("unknown") or [])
        seen = self.store.ci_seen(number, head)
        fresh = [(check, why) for check, why in counted
                 if (check.get("name") or "?") not in seen]
        names = [line(check) for check, _ in counted]
        if not fresh:
            result.update(action="reported",
                          detail="already reported to a human for this head")
            self.store.update_pr(issue, state="waiting-human",
                                 detail="escalated earlier for this head")
            return result
        reason = "; ".join(f"{check.get('name')}: {why}" for check, why in fresh)[:400]
        if dry_run:
            result.update(action="would-escalate", detail=reason, failures=names)
            return result
        question = (
            f"CI on PR #{number} ({self.cfg.repo}) reports failures that this agent will not "
            f"repair, at head {head[:8]}:\n\n"
            + "\n".join(f"- {item}" for item in names)
            + f"\n\nWhy not repaired: {reason}\n\n"
            "A worker is only resumed for failures that name a test, a lint rule or a build. "
            "These read as infrastructure or are unclassified, so the branch is untouched and "
            "awaits a human decision - rerun the job, fix the pipeline, or say so here and the "
            "agent will take another look.")
        try:
            self.claims.wip.cmd_ask(question, issue_arg=issue)
        except Exception as exc:                  # board unreachable: say so, retry next pass
            result.update(action="escalation-failed", detail=str(exc), failures=names)
            self.store.event("ci-escalate-failed", f"pr={number} {exc}", issue=issue)
            return result
        for check, _ in counted:
            self.store.note_ci_seen(number, head, check.get("name") or "?", "escalated",
                                    check.get("id"))
        self.store.update_pr(issue, state="waiting-human", escalated_at=time.time(),
                             detail=reason)
        self.store.event("ci-escalated", f"pr={number} checks={len(counted)}", issue=issue)
        result.update(action="escalated", detail=reason, failures=names)
        return result

    def prompt(self, number, head, failures):
        """What the resumed worker is told. Specific by design: the failing checks
        and their URLs, the rules it must not cross, and no license to touch
        anything outside its own stack."""
        checks = "\n".join(f"- {line(check)} ({why})" for check, why in failures)
        denies = ", ".join(sorted({item["resource"] for item in WORKER_DENY_PERMISSIONS}))
        return (
            f"CI for pull request #{number} is red at head {head}. Actionable failures:\n"
            f"{checks}\n\n"
            "Work in this worktree and this Compose project only. Reproduce the named check "
            "first, fix the cause, and push as ordinary commits on top - never rebase or "
            "force-push a branch that is open for review. Do not touch branch protection, "
            "required checks or anyone else's stack. You may not: " + denies + ".\n"
            "If the named check is not reproducible here and reads as infrastructure, stop and "
            "run scripts/wip wait with what you need instead of pushing a guess. The rules of "
            "this checkout's AGENTS.md still apply, and the deny list above is enforced by "
            "configuration, not by wording.")
