"""What the supervisor remembers: one SQLite file, no server, no migration tool.

Why state at all, when GitHub holds the truth about approvals and the claim
board holds the truth about who works on what? Because the supervisor has to
survive being restarted *while it is working*. A worker that was launched and
then lost from memory is a worker nobody cleans up; a failure that is not
remembered is retried every minute until the host is buried in branches. So
three things live here and nothing else:

*   **leases** - one row per issue the supervisor itself has started, with the
    worktree, branch, Compose project and process group the runner (#1060) will
    need in order to stop it cleanly. The primary key *is* the issue number: two
    supervisor processes on one host cannot both hold it, and that is the whole
    answer to double scheduling locally. Across hosts the claim board stays the
    arbiter, because that is what it is for.
*   **verdicts** - the last answer the gate gave per issue, with a backoff after
    a failed attempt. This is the anti rate-limit-storm measure: an issue that
    failed twice is not retried every tick, and an issue that is not eligible is
    not re-read until the next listing says it might be.
*   **events** - what the supervisor decided and why, in order. A daemon that
    starts agents is audited or it is not trustworthy; this table is also what
    makes `supervisor status` explainable after a restart.
*   **the watch on what a worker left behind** - which pull request belongs to
    which issue, which findings and review comments have already been dealt with,
    and how much of each budget is spent (#1061, #1062). Without these rows a
    restart reads last night's red check and last week's review as news.

WAL mode and one write transaction per decision: the state is small, and the
failure mode we design for is a killed process, not a crowd of writers.
"""

import hashlib
import os
import sqlite3
import time
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS leases (
    issue        INTEGER PRIMARY KEY,
    repo         TEXT NOT NULL,
    state        TEXT NOT NULL,
    branch       TEXT,
    worktree     TEXT,
    project      TEXT,
    pgid         INTEGER,
    pid          INTEGER,
    session      TEXT,
    needs        TEXT,
    started_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    finished_at  REAL,
    detail       TEXT
);
CREATE TABLE IF NOT EXISTS verdicts (
    issue       INTEGER PRIMARY KEY,
    eligible    INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    decided_at  REAL NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    next_try_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      REAL NOT NULL,
    issue   INTEGER,
    kind    TEXT NOT NULL,
    detail  TEXT
);
CREATE INDEX IF NOT EXISTS events_issue ON events(issue, id);
CREATE TABLE IF NOT EXISTS pull_requests (
    issue          INTEGER PRIMARY KEY,
    repo           TEXT NOT NULL,
    pr             INTEGER NOT NULL,
    branch         TEXT,
    head_sha       TEXT,
    state          TEXT NOT NULL DEFAULT 'watching',
    attempts       INTEGER NOT NULL DEFAULT 0,
    repair_sha     TEXT,
    escalated_at   REAL,
    last_seen      REAL,
    detail         TEXT
);
CREATE TABLE IF NOT EXISTS ci_seen (
    pr        INTEGER NOT NULL,
    head_sha  TEXT NOT NULL,
    name      TEXT NOT NULL,
    verdict   TEXT NOT NULL,
    run_id    INTEGER,
    seen_at   REAL NOT NULL,
    PRIMARY KEY (pr, head_sha, name)
);
CREATE TABLE IF NOT EXISTS review_items (
    repo         TEXT NOT NULL,
    pr           INTEGER NOT NULL,
    issue        INTEGER,
    kind         TEXT NOT NULL,
    github_id    TEXT NOT NULL,
    thread_id    TEXT,
    author       TEXT,
    association  TEXT,
    trusted      INTEGER NOT NULL DEFAULT 0,
    path         TEXT,
    line         INTEGER,
    state        TEXT,
    url          TEXT,
    body         TEXT,
    body_hash    TEXT,
    stamped_at   REAL,
    seen_at      REAL,
    status       TEXT NOT NULL DEFAULT 'pending',
    detail       TEXT,
    PRIMARY KEY (repo, pr, kind, github_id)
);
CREATE TABLE IF NOT EXISTS review_state (
    issue        INTEGER PRIMARY KEY,
    repo         TEXT NOT NULL,
    pr           INTEGER NOT NULL,
    head_sha     TEXT,
    state        TEXT NOT NULL DEFAULT 'watching',
    attempts     INTEGER NOT NULL DEFAULT 0,
    acted_sha    TEXT,
    acted_at     REAL,
    last_seen    REAL,
    detail       TEXT
);
"""

# A lease in one of these states both occupies the issue and occupies capacity:
# `planned` is reserved briefly while the runner is being handed the job, and
# `stopping` still holds a live process until it is gone. Anything else is
# terminal - the issue is free again, and nothing here deletes what the worker
# left behind.
LIVE_STATES = ("planned", "starting", "running", "stopping")
TERMINAL_STATES = ("finished", "failed", "cancelled", "abandoned")

# What the CI monitor knows about a pull request it follows (#1061). `watching`
# means "tracked, no verdict recorded yet"; `waiting-ci` and `green` need no
# action; `repairing` names the head SHA a worker was last woken for, which is
# what keeps one failure from waking it twice; `waiting-human` is the escalated
# state, and `closed` is left in the table on purpose - a PR that came back
# closed must not look like one that was never tracked.
PR_STATES = ("watching", "waiting-ci", "green", "repairing", "waiting-human",
             "unknown", "closed")

# What the review watcher of #1062 knows about one pull request. `responding` is
# the state while a resumed worker is answering feedback, `responded` that it did
# and is waiting for the human to look again.
REVIEW_STATES = ("watching", "responding", "responded", "waiting-human", "closed",
                 "unknown")

# One piece of feedback, as the ledger knows it. `pending` is work nobody has
# acted on; `context` is feedback from an account that may not direct the worker
# (a bot, a stranger) and is therefore recorded but never acted on; `escalated`
# is feedback that asks for something an agent may not do; `settled` is a thread a
# human closed themselves; `dropped` and `stale` are the two shapes a deletion
# takes - never acted on, versus already answered when the human removed it.
REVIEW_ITEM_STATUSES = ("pending", "acted", "context", "escalated", "settled", "held",
                        "dropped", "stale")


def body_digest(text):
    """The digest that decides whether a comment is the same text as last time.

    An edit is new instructions, so identity means content: two comments with one
    GitHub id and different digests are two things to read, not one thing seen
    twice.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def utc_stamp(value=None):
    return time.time() if value is None else value


class Store:
    """The state file, opened per use. `path` is under the configured
    ``state_dir``, so one operator setting decides where all of it lives.

    Every method opens and closes its own connection: the supervisor holds no
    long-lived handle, so a lease written by the CLI and read by the daemon, or
    by two processes at once, is read from the same file and nothing has to be
    refreshed. Autocommit throughout, with the one transaction that needs
    isolation spelled out in claim_lease - sqlite3's implicit begin-on-DML is the
    part of its Python interface that surprises people.
    """

    def __init__(self, path):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)

    @classmethod
    def for_config(cls, cfg):
        return cls(os.path.join(cfg.state_dir, "supervisor.sqlite3"))

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        return db

    def __call__(self):
        return self._connect()

    # -- leases -------------------------------------------------------------

    def lease(self, issue):
        with self._connect() as db:
            row = db.execute("SELECT * FROM leases WHERE issue=?", (issue,)).fetchone()
        return dict(row) if row else None

    def active_leases(self):
        """Everything the supervisor still has a worker (or a plan) for."""
        marks = ",".join("?" * len(LIVE_STATES))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM leases WHERE state IN ({marks}) ORDER BY issue",
                LIVE_STATES).fetchall()
        return [dict(r) for r in rows]

    def count_active(self, needs=None):
        rows = self.active_leases()
        if needs:
            rows = [r for r in rows if r.get("needs") == needs]
        return len(rows)

    def claim_lease(self, issue, repo, needs, branch="", worktree="", project=""):
        """Take the lease for an issue, or return False if it is taken.

        A single INSERT with the primary key doing the locking, inside an
        immediate transaction: a second supervisor trying the same issue gets
        False rather than an exception, and a crash before the worker exists
        leaves a `planned` row that the next tick can either adopt or age out.
        """
        now = utc_stamp()
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT state FROM leases WHERE issue=?", (issue,)).fetchone()
                if row and row["state"] in LIVE_STATES:
                    return False
                if row:
                    db.execute(
                        "UPDATE leases SET repo=?, state='planned', branch=?, worktree=?, "
                        "project=?, needs=?, started_at=?, updated_at=?, finished_at=NULL, "
                        "pgid=NULL, pid=NULL, session=NULL, detail='' "
                        "WHERE issue=?",
                        (repo, branch, worktree, project, needs, now, now, issue))
                else:
                    db.execute(
                        "INSERT INTO leases (issue, repo, state, branch, worktree, project, "
                        "needs, started_at, updated_at) VALUES (?,?,'planned',?,?,?,?,?,?)",
                        (issue, repo, branch, worktree, project, needs, now, now))
            return True
        except sqlite3.IntegrityError:
            return False

    def update_lease(self, issue, **fields):
        """Set the given columns; `state` is checked, a typo must not invent a state."""
        unknown = set(fields) - {"state", "branch", "worktree", "project", "pgid", "pid",
                                 "session", "needs", "detail", "finished_at"}
        if unknown:
            raise ValueError(f"unknown lease columns: {', '.join(sorted(unknown))}")
        if "state" in fields and fields["state"] not in LIVE_STATES + TERMINAL_STATES:
            raise ValueError(f"not a lease state: {fields['state']}")
        fields["updated_at"] = utc_stamp()
        if fields.get("state") in TERMINAL_STATES and not fields.get("finished_at"):
            fields["finished_at"] = utc_stamp()
        columns = ", ".join(f"{key}=?" for key in fields)
        with self._connect() as db:
            db.execute(f"UPDATE leases SET {columns} WHERE issue=?",
                       tuple(fields.values()) + (issue,))

    def release_lease(self, issue, state="finished", detail=""):
        """Give the issue up. The branch, worktree and logs stay where they are:
        a released lease is a bookkeeping act, never a deletion."""
        self.update_lease(issue, state=state, detail=detail)

    def age_out_plans(self, older_than_s):
        """A `planned` lease whose runner never showed up is a crashed supervisor.
        Free it after a grace period so the issue is not blocked forever."""
        cutoff = utc_stamp() - older_than_s
        with self._connect() as db:
            cur = db.execute(
                "UPDATE leases SET state='abandoned', detail='planned lease never started', "
                "updated_at=?, finished_at=? WHERE state='planned' AND started_at < ?",
                (utc_stamp(), utc_stamp(), cutoff))
            return cur.rowcount

    # -- verdicts and backoff ----------------------------------------------

    def verdict(self, issue):
        with self._connect() as db:
            row = db.execute("SELECT * FROM verdicts WHERE issue=?", (issue,)).fetchone()
        return dict(row) if row else None

    def record_verdict(self, issue, eligible, reason):
        """Remember the gate's answer. The reason is stored verbatim because it
        is what `status` shows a human, and it is how an operator notices that
        something changed between two ticks."""
        with self._connect() as db:
            db.execute(
                "INSERT INTO verdicts (issue, eligible, reason, decided_at) VALUES (?,?,?,?) "
                "ON CONFLICT(issue) DO UPDATE SET eligible=excluded.eligible, "
                "reason=excluded.reason, decided_at=excluded.decided_at",
                (issue, 1 if eligible else 0, reason, utc_stamp()))

    def note_attempt(self, issue, backoff_s):
        """Count a start attempt and push the next try out. Failure backoff is
        per issue, because the host being out of memory is not the issue's
        fault and retrying it every minute is how a queue becomes a storm."""
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO verdicts (issue, eligible, reason, decided_at) "
                       "VALUES (?,0,'attempt',?)", (issue, utc_stamp()))
            db.execute(
                "UPDATE verdicts SET attempts=attempts+1, next_try_at=? WHERE issue=?",
                (utc_stamp() + backoff_s, issue))
            row = db.execute("SELECT attempts FROM verdicts WHERE issue=?", (issue,)).fetchone()
        return row["attempts"]

    def ready_for_retry(self, issue, now=None):
        row = self.verdict(issue)
        if not row:
            return True
        return (row["next_try_at"] or 0) <= utc_stamp(now)

    def reset_attempts(self, issue):
        with self._connect() as db:
            db.execute("UPDATE verdicts SET attempts=0, next_try_at=0 WHERE issue=?", (issue,))

    # -- events -------------------------------------------------------------

    def event(self, kind, detail="", issue=None):
        with self._connect() as db:
            db.execute("INSERT INTO events (at, issue, kind, detail) VALUES (?,?,?,?)",
                       (utc_stamp(), issue, kind, detail))

    def recent_events(self, limit=20):
        with self._connect() as db:
            rows = db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- reporting ----------------------------------------------------------

    def status(self):
        """Everything `supervisor status` prints, in one read."""
        with self._connect() as db:
            leases = [dict(r) for r in db.execute(
                "SELECT * FROM leases ORDER BY issue").fetchall()]
            verdicts = [dict(r) for r in db.execute(
                "SELECT * FROM verdicts ORDER BY issue").fetchall()]
            pulls = [dict(r) for r in db.execute(
                "SELECT * FROM pull_requests ORDER BY issue").fetchall()]
            reviews = [dict(r) for r in db.execute(
                "SELECT * FROM review_state ORDER BY issue").fetchall()]
        return {"leases": leases, "verdicts": verdicts, "pulls": pulls,
                "reviews": reviews, "path": self.path}

    def waiting_for_human(self):
        """Leases whose detail says the worker stopped to ask a human - the
        supervisor's side of `scripts/wip wait`."""
        return [lease for lease in self.active_leases()
                if (lease.get("detail") or "").startswith("waiting:")]

    # -- pull requests under CI watch (#1061) --------------------------------

    def track_pr(self, issue, repo, pr, branch="", head_sha=""):
        """Record (or refresh) which pull request belongs to an issue.

        Keyed by the issue, one row per issue: the supervisor's unit of work is
        the issue, and a branch that gets a second PR after a force push is not
        two things to watch. `attempts` and `repair_sha` survive a refresh -
        they are the repair budget, and losing them at the moment the worker
        pushes a new commit is how a bounded budget becomes an unlimited one.
        """
        now = utc_stamp()
        with self._connect() as db:
            row = db.execute("SELECT pr, state FROM pull_requests WHERE issue=?",
                             (issue,)).fetchone()
            if row is None:
                db.execute("INSERT INTO pull_requests (issue, repo, pr, branch, head_sha, "
                           "state, last_seen) VALUES (?,?,?,?,?,'watching',?)",
                           (issue, repo, pr, branch, head_sha, now))
            elif row["pr"] != pr or row["state"] == "closed":
                # A different PR number, or one that was closed and came back: the
                # previous verdict describes a different object, so the row starts
                # over. The budget columns do not - see the note above.
                db.execute("UPDATE pull_requests SET repo=?, pr=?, branch=?, head_sha=?, "
                           "state='watching', escalated_at=NULL, last_seen=? WHERE issue=?",
                           (repo, pr, branch, head_sha, now, issue))
            else:
                db.execute("UPDATE pull_requests SET repo=?, branch=?, head_sha=?, last_seen=? "
                           "WHERE issue=?", (repo, branch, head_sha, now, issue))
            row = db.execute("SELECT * FROM pull_requests WHERE issue=?", (issue,)).fetchone()
        return dict(row)

    def pr_row(self, issue):
        with self._connect() as db:
            row = db.execute("SELECT * FROM pull_requests WHERE issue=?", (issue,)).fetchone()
        return dict(row) if row else None

    def watched_prs(self):
        """Every pull request still under watch; a closed one is not watched."""
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM pull_requests WHERE state != 'closed' ORDER BY issue").fetchall()
        return [dict(r) for r in rows]

    def update_pr(self, issue, **fields):
        """Set the given columns of one tracked pull request.

        ``last_seen`` is written on every call unless the caller names a value
        itself - which tests and the metrics seeding legitimately do.
        """
        unknown = set(fields) - {"pr", "branch", "head_sha", "state", "attempts",
                                 "repair_sha", "escalated_at", "last_seen", "detail"}
        if unknown:
            raise ValueError(f"unknown pull request columns: {', '.join(sorted(unknown))}")
        if "state" in fields and fields["state"] not in PR_STATES:
            raise ValueError(f"not a pull request state: {fields['state']}")
        if "last_seen" not in fields:
            fields["last_seen"] = utc_stamp()
        columns = ", ".join(f"{key}=?" for key in fields)
        with self._connect() as db:
            db.execute(f"UPDATE pull_requests SET {columns} WHERE issue=?",
                       tuple(fields.values()) + (issue,))

    def note_ci_seen(self, pr, head_sha, name, verdict, run_id=None):
        """Remember one (check, head SHA, conclusion) triple.

        Returns True the first time it is seen and False on a repeat. That single
        bit is what keeps a restart from reading the same red check as news and
        waking the worker again: after a crash the rows are still here, so the
        answer to "have we already dealt with this one" does not depend on
        anything having been in memory before.
        """
        with self._connect() as db:
            cur = db.execute(
                "INSERT OR IGNORE INTO ci_seen (pr, head_sha, name, verdict, run_id, seen_at) "
                "VALUES (?,?,?,?,?,?)", (pr, head_sha, name, verdict, run_id, utc_stamp()))
            return cur.rowcount > 0

    def ci_seen(self, pr, head_sha):
        """The recorded findings for one head SHA, as {name: verdict}.

        Rows for other head SHAs stay in the table - they are the audit trail of
        what the supervisor already decided about this branch - but they answer
        nothing: a check that failed on a commit nobody pushed any more is not a
        reason to wake anybody.
        """
        with self._connect() as db:
            rows = db.execute("SELECT name, verdict FROM ci_seen WHERE pr=? AND head_sha=?",
                              (pr, head_sha)).fetchall()
        return {r["name"]: r["verdict"] for r in rows}

    def ci_seen_summary(self):
        """Every recorded finding with its time - the metrics read (#1063).

        The whole table, not one head: the question here is "what has the watcher
        seen of this pull request over its life", which is exactly what the
        per-head method above refuses to answer.
        """
        with self._connect() as db:
            rows = db.execute("SELECT pr, head_sha, name, verdict, seen_at "
                              "FROM ci_seen ORDER BY pr, seen_at").fetchall()
        return [dict(r) for r in rows]

    # -- review feedback under supervision (#1062) --------------------------

    def track_reviews(self, issue, repo, pr, head_sha=""):
        """Record (or refresh) the review watch of an issue's pull request.

        Same rule as ``track_pr``: the budget columns survive a refresh. A pull
        request whose head moved is a new commit to answer, not a fresh subject
        with a fresh allowance.
        """
        now = utc_stamp()
        with self._connect() as db:
            row = db.execute("SELECT pr, state FROM review_state WHERE issue=?",
                             (issue,)).fetchone()
            if row is None:
                db.execute("INSERT INTO review_state (issue, repo, pr, head_sha, state, "
                           "last_seen) VALUES (?,?,?,?, 'watching', ?)",
                           (issue, repo, pr, head_sha, now))
            elif row["pr"] != pr or row["state"] == "closed":
                db.execute("UPDATE review_state SET repo=?, pr=?, head_sha=?, "
                           "state='watching', acted_at=NULL, last_seen=? WHERE issue=?",
                           (repo, pr, head_sha, now, issue))
            else:
                db.execute("UPDATE review_state SET repo=?, head_sha=?, last_seen=? "
                           "WHERE issue=?", (repo, head_sha, now, issue))
            row = db.execute("SELECT * FROM review_state WHERE issue=?", (issue,)).fetchone()
        return dict(row)

    def review_row(self, issue):
        with self._connect() as db:
            row = db.execute("SELECT * FROM review_state WHERE issue=?", (issue,)).fetchone()
        return dict(row) if row else None

    def reviewed_prs(self):
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM review_state WHERE state != 'closed' ORDER BY issue").fetchall()
        return [dict(r) for r in rows]

    def update_review(self, issue, **fields):
        """Set the given columns of one review watch.

        ``last_seen`` is written on every call unless the caller names a value
        itself.
        """
        unknown = set(fields) - {"pr", "head_sha", "state", "attempts", "acted_sha",
                                 "acted_at", "last_seen", "detail"}
        if unknown:
            raise ValueError(f"unknown review columns: {', '.join(sorted(unknown))}")
        if "state" in fields and fields["state"] not in REVIEW_STATES:
            raise ValueError(f"not a review state: {fields['state']}")
        if "last_seen" not in fields:
            fields["last_seen"] = utc_stamp()
        columns = ", ".join(f"{key}=?" for key in fields)
        with self._connect() as db:
            db.execute(f"UPDATE review_state SET {columns} WHERE issue=?",
                       tuple(fields.values()) + (issue,))

    def record_review_item(self, issue, repo, pr, kind, github_id, status="pending",
                           detail="", **fields):
        """Put one piece of feedback in the ledger.

        Returns ``new``, ``changed``, ``promoted`` or ``same``.

        Identity is *(kind, GitHub's own id)* and nothing else: GitHub keeps those
        ids stable across edits and paging, so de-duplication does not depend on
        timestamps matching to the second, and a comment that was edited comes
        back as ``changed`` - new instructions under an id already seen, which is
        exactly the case a watcher that only looks at new ids misses.
        ``promoted`` is the fourth shape: the text is unchanged, but the author has
        become an account that may direct work, so the row that was filed as
        context becomes work.

        The returned bit is the whole anti-replay mechanism. The rows are the
        record of what has been answered, so after a restart the answer to "have
        we already done this review" comes from disk.
        """
        allowed = {"thread_id", "author", "association", "trusted", "path", "line",
                   "state", "url", "body", "stamped_at"}
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"unknown review item columns: {', '.join(sorted(unknown))}")
        if status not in REVIEW_ITEM_STATUSES:
            raise ValueError(f"not a review item status: {status}")
        digest = body_digest(fields.get("body"))
        now = utc_stamp()
        with self._connect() as db:
            row = db.execute("SELECT * FROM review_items WHERE repo=? AND pr=? AND kind=?"
                             " AND github_id=?", (repo, pr, kind, str(github_id))).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO review_items (repo, pr, issue, kind, github_id, body_hash,"
                    " seen_at, status, detail, stamped_at, author, association, trusted,"
                    " thread_id, path, line, state, url, body)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (repo, pr, issue, kind, str(github_id), digest, now, status, detail,
                     fields.get("stamped_at"), fields.get("author"),
                     fields.get("association"), 1 if fields.get("trusted") else 0,
                     fields.get("thread_id"), fields.get("path"), fields.get("line"),
                     fields.get("state"), fields.get("url"), fields.get("body")))
                outcome = "new"
            elif row["body_hash"] != digest:
                # Same id, different text: an edit is new instructions, so the row
                # goes back to pending even if it was answered once.
                db.execute(
                    "UPDATE review_items SET body=?, body_hash=?, stamped_at=?, author=?,"
                    " association=?, trusted=?, thread_id=?, path=?, line=?, state=?, url=?,"
                    " status='pending', detail='edited on GitHub', seen_at=?"
                    " WHERE repo=? AND pr=? AND kind=? AND github_id=?",
                    (fields.get("body"), digest, fields.get("stamped_at"),
                     fields.get("author"), fields.get("association"),
                     1 if fields.get("trusted") else 0, fields.get("thread_id"),
                     fields.get("path"), fields.get("line"), fields.get("state"),
                     fields.get("url"), now, repo, pr, kind, str(github_id)))
                outcome = "changed"
            else:
                # An account that was a stranger when the comment arrived and holds
                # a trusted role now must not stay ignored forever: the status is
                # what encodes "may not direct", so it is what has to change.
                promote = ", status='pending', detail='author is trusted now'" \
                    if row["status"] == "context" and fields.get("trusted") else ""
                db.execute("UPDATE review_items SET seen_at=?, thread_id=?, trusted=?,"
                           " association=?" + promote +
                           " WHERE repo=? AND pr=? AND kind=? AND github_id=?",
                           (now, fields.get("thread_id"), 1 if fields.get("trusted") else 0,
                            fields.get("association"), repo, pr, kind, str(github_id)))
                outcome = "promoted" if promote else "same"
        return outcome

    def review_items(self, pr, statuses=None):
        """The ledger of one pull request, oldest feedback first."""
        wanted = tuple(statuses or REVIEW_ITEM_STATUSES)
        marks = ",".join("?" * len(wanted))
        with self._connect() as db:
            rows = db.execute(
                f"SELECT * FROM review_items WHERE pr=? AND status IN ({marks}) "
                "ORDER BY stamped_at", (pr,) + wanted).fetchall()
        return [dict(r) for r in rows]

    def mark_review_items(self, pr, keys, status, detail=""):
        """Move feedback out of pending, once it has really been dealt with.

        Called only after the action that deals with it succeeded: a refused
        resume or a question that never reached GitHub must not leave the items
        marked, or the pull request looks answered and nobody is told.
        """
        if status not in REVIEW_ITEM_STATUSES:
            raise ValueError(f"not a review item status: {status}")
        moved = 0
        with self._connect() as db:
            for kind, github_id in keys:
                moved += db.execute(
                    "UPDATE review_items SET status=?, detail=? WHERE pr=? AND kind=?"
                    " AND github_id=?", (status, detail, pr, kind, str(github_id))).rowcount
        return moved

    def reopen_review_items(self, pr, keys, detail=""):
        """Bring back feedback a human has re-opened.

        Un-resolving a thread is GitHub's own way of saying "not settled yet", and
        nothing else in a payload says it: the comment's id and text are identical.
        Only ``settled`` rows are touched - an item the worker already answered
        stays answered, because the reply a human writes after that is a new
        comment with a new id, and that one arrives as work on its own.
        """
        reopened = 0
        with self._connect() as db:
            for kind, github_id in keys:
                reopened += db.execute(
                    "UPDATE review_items SET status='pending', detail=? WHERE pr=? AND"
                    " kind=? AND github_id=? AND status='settled'",
                    (detail, pr, kind, str(github_id))).rowcount
        return reopened

    def review_items_gone(self, repo, pr, visible):
        """Notice feedback that is no longer there, and return what dropped.

        A deleted comment is not a request any more. `visible` is the set of
        *(kind, id)* GitHub still lists for this pull request, so anything the
        ledger holds and the answer lacks was deleted. The two cases differ in
        whether a worker had already answered: pending rows drop, answered rows
        go stale, and neither is ever acted on again.
        """
        dropped = []
        with self._connect() as db:
            rows = db.execute("SELECT kind, github_id, status FROM review_items "
                              "WHERE repo=? AND pr=?", (repo, pr)).fetchall()
            for row in rows:
                key = (row["kind"], str(row["github_id"]))
                if key in visible:
                    continue
                if row["status"] in ("pending", "held"):
                    outcome = "dropped"
                elif row["status"] in ("acted", "escalated"):
                    outcome = "stale"
                else:
                    continue
                db.execute("UPDATE review_items SET status=?, detail=? WHERE repo=? AND pr=?"
                           " AND kind=? AND github_id=?",
                           (outcome, "no longer on GitHub", repo, pr, row["kind"],
                            row["github_id"]))
                dropped.append((row["kind"], str(row["github_id"]), outcome))
        return dropped


def human_age(value):
    """Seconds ago as a short phrase, for status output."""
    if not value:
        return "never"
    seconds = max(0, int(utc_stamp() - value))
    if seconds < 120:
        return f"{seconds}s"
    if seconds < 7200:
        return f"{seconds // 60}m"
    if seconds < 172800:
        return f"{seconds // 3600}h"
    return datetime.fromtimestamp(value, timezone.utc).date().isoformat()
