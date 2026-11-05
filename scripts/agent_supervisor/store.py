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

WAL mode and one write transaction per decision: the state is small, and the
failure mode we design for is a killed process, not a crowd of writers.
"""

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
        return {"leases": leases, "verdicts": verdicts, "pulls": pulls, "path": self.path}

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
        """Set the given columns of one tracked pull request."""
        unknown = set(fields) - {"pr", "branch", "head_sha", "state", "attempts",
                                 "repair_sha", "escalated_at", "detail"}
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
