.. _development-agent-supervisor:

Agent Supervisor: Approval Gate And Scheduler
=============================================

.. sidebar:: Epic #1052, issues #1058 and #1059

   Code: ``scripts/agent_supervisor/`` (standard library only) with the
   operator command ``scripts/agent-supervisor``. Checks:
   ``python3 scripts/test_agent_supervisor_approvals.py`` and
   ``python3 scripts/test_agent_supervisor_scheduler.py`` and
   ``python3 scripts/test_agent_supervisor_capacity.py`` — none of them needs
   ``gh``, the network or a repository, and none of them can touch one. This
   page documents the gate and the scheduler; the worktree runner and the CI and
   review supervision are the follow-up issues #1060 to #1063 and will extend it.

An OpenCode worker may start work on a MrMap issue when a human has said so.
That sentence is the whole design; everything below is what "a human has said
so" has to mean before an automation can act on it without a human at the
keyboard.

The rule
========

**An issue is eligible when it is open, is not a pull request, does not carry
the pause label, and the last word on the approval label was a person on the
operator's allowlist putting it there.** Everything else — no approval, a
revoked approval, an approval by a bot or by the automation itself, an approval
nobody can be identified from, a label history that cannot be read — is "not
eligible".

The gate is fail-closed by construction. Every state in which the answer cannot
be *proved* is a refusal, because a supervisor that treats "I could not check"
as "nobody objected" produces action that looks like consent. The configuration
has the same property: with no configuration file, an empty allowlist or a file
that contradicts itself, no issue is eligible — never "let everything through".

Two labels, one contract
========================

.. list-table::
   :header-rows: 1
   :widths: 22 40 38

   * - Label
     - Meaning
     - Who may set it
   * - ``agent: approved``
     - a human authorizes automated work on this issue
     - a human on the allowlist, and only in the sense that their act is what
       the gate accepts
   * - ``agent: paused``
     - automated work here is suspended; nothing is decided about the approval
     - anyone who can label an issue; the pause is read as a human brake

Both labels are *created* by ``scripts/agent-supervisor labels --create``, which
defines them and never applies them. Applying ``agent: approved`` is the human
act itself, so the automation that would consume it must not be able to perform
it. There is no code path for it: the package contains no call that labels an
issue, comments, reviews, assigns, closes or merges — a test parses the modules
and fails if one appears.

Why the history, not the label
==============================

The labels on an issue say what is true now. They do not say who made it true,
which is the question a security boundary asks. So the gate reads the issue's
timeline and evaluates the **last** ``labeled``/``unlabeled`` event for
``agent: approved``:

* last event is ``labeled`` by an allowlisted human → eligible;
* last event is ``unlabeled`` → the approval is revoked, effective on the next
  tick without any other signal;
* the label is on the issue but no event for it is in the timeline → refused,
  with ``history-incomplete``. A label that appeared without a witness is
  exactly what a compromised automation would produce.

Re-adding the label after removing it is a fresh act and is judged on its own
event; nothing is inherited from the earlier approval. Events are ordered by
their own timestamp rather than by the order GitHub returns them, and the
timeline is read to the end — a history that cannot be read completely is a
refusal, not a short list.

What an approval must survive
=============================

In the order the gate reaches them, and with the reason code each one produces
(``scripts/agent-supervisor explain 1042`` prints exactly these):

.. list-table::
   :header-rows: 1
   :widths: 34 66

   * - Reason
     - What happened, and what to do
   * - ``config-invalid``
     - the configuration is missing, unparsable, contradicts itself or names an
       empty allowlist. Nothing can be authorized; ``config`` prints the problem
   * - ``issue-unavailable:<kind>``
     - the issue could not be read (``notfound``, ``auth``, ``network``, …)
   * - ``is-pull-request``
     - that number is a pull request, and pull requests are supervised by
       #1061/#1062, not started from this queue
   * - ``not-open``
     - the issue is closed or its state is anything but ``open``
   * - ``paused``
     - ``agent: paused`` is set; removing it resumes work, no new approval
       needed
   * - ``no-approval-label``
     - ``agent: approved`` is not on the issue; a human has to add it
   * - ``allowlist-empty``
     - only reachable by a caller that bypasses the configuration check; the
       loader already refuses this state
   * - ``history-unavailable:<kind>``
     - the timeline could not be read. A rate limit is a *later*, a permission
       error a *never*, and both are refusals now
   * - ``history-incomplete``
     - the label is present with no event behind it
   * - ``approval-revoked``
     - the label was removed after it was added
   * - ``non-human-approver:<login>``
     - GitHub reports the actor as ``Bot``, ``Organization`` or anything but
       ``User``. An AI issue generator labelling its own issue lands here
   * - ``unknown-approver``
     - the event names no account at all
   * - ``self-approval:<login>``
     - the account that set the label is one the automation acts with: either
       listed in ``agent_accounts`` or the login the host's ``gh`` is
       authenticated as. This is the rule that keeps an agent from approving its
       own work
   * - ``unauthorized-approver:<login>``
     - a person, but not one the operator listed
   * - ``unverified-association:<login>``
     - a person on the list, but not in a repository role the operator trusts —
       or a role that could not be looked up
   * - ``approval-too-old``
     - only with ``approval_max_age_days`` set; the default is that an approval
       stands until it is revoked

Blocking relations are not part of this. GitHub's native "blocked by" links are
a scheduling hint for humans; reading them would let an issue that no human
intended to link hold the queue shut. The gate does not request them at all, and
a test asserts that its own reads never include them.

Configuration
=============

One JSON file outside the repository, owned by the operator::

    ~/.config/mrmap-agent-supervisor/config.json      # or $MRMAP_SUPERVISOR_CONFIG

It holds no credentials: GitHub access runs over the host's ``gh`` and the
workers over OpenCode's own authentication, so there is nothing here for a log
line to print. Keep it ``600`` and owned by a user the workers cannot become;
the CLI warns while the file is group- or world-readable, because an allowlist
the automation can rewrite is a suggestion.

.. code-block:: json

    {
      "repo": "mrmap-community/mrmap",
      "authorized_humans": ["your-github-login"],
      "agent_accounts": ["mrmap-agent-bot"],
      "repo_root": "/srv/mrmap/mrmap",
      "worktree_root": "/srv/mrmap/agent-worktrees",
      "state_dir": "/srv/mrmap/agent-state",
      "max_opencode_processes": 2,
      "max_test_stacks": 1,
      "opencode_model": "provider/model",
      "ci_repair_attempts": 2
    }

``scripts/agent-supervisor config --example`` prints this, and
``scripts/agent-supervisor config`` prints what was actually resolved with the
problems and warnings attached. Keys that are not in the known set are a
problem, not a default: a typo in a security setting must not quietly mean
"unset". The example prints only the keys an operator has to decide on; the
scheduling keys below it have working defaults and are listed there.

.. list-table:: The keys that decide eligibility
   :header-rows: 1
   :widths: 30 22 48

   * - Key
     - Default
     - Effect
   * - ``authorized_humans``
     - ``[]`` (refuses everything)
     - logins whose ``labeled`` event counts
   * - ``agent_accounts``
     - ``[]``
     - logins the automation acts with; their approvals never count
   * - ``require_repo_association``
     - ``true``
     - also require a trusted role on the repository, so a stale allowlist entry
       that lost access no longer authorizes
   * - ``trusted_associations``
     - ``OWNER``, ``MEMBER``, ``COLLABORATOR``
     - which roles that is. The role is read from GitHub's permission endpoint,
       which needs push access on the repository to answer; when it cannot
       answer, the role is ``UNKNOWN`` and the approval is refused
   * - ``approval_max_age_days``
     - ``0`` = no expiry
     - set a number to force re-approval after that many days
   * - ``allow_same_account``
     - ``false``
     - the one escape hatch, below

The keys the scheduler adds
---------------------------

The scheduler and runner read the same file, so one set of file permissions
covers the whole supervisor.

.. list-table:: The keys that decide scheduling
   :header-rows: 1
   :widths: 30 22 48

   * - Key
     - Default
     - Effect
   * - ``priority_labels``
     - ``priority: critical``, ``priority: high``
     - these labels are worked before the rest; inside a rank it is oldest first
   * - ``max_candidates_per_tick``
     - ``10``
     - how many issues one tick reads claims and history for. This is the
       rate-limit bound, not the slot count
   * - ``verdict_cache_s``
     - ``600``
     - how long a *refusal* is reused without re-reading the timeline. Never
       applied to a refusal that says GitHub could not be reached
   * - ``retry_backoff_s``
     - ``900``
     - how long an issue waits after a start attempt failed
   * - ``plan_ttl_s``
     - ``900``
     - how long a plan nobody adopted is held before the issue is released
   * - ``max_opencode_processes``
     - ``2``
     - the supervisor's own ceiling on workers, on top of the capacity gate
   * - ``max_test_stacks``
     - ``1``
     - the same for Compose stacks. The capacity gate of ``scripts/agent_capacity``
       still has the last word: these are ceilings, never permissions

The single-account host
=======================

A host where one GitHub account both reviews the issues and pushes the agents'
work has no second login to put in ``agent_accounts``. ``allow_same_account:
true`` relaxes exactly one check — the one that refuses an approval from an
account the automation acts with. The allowlist still has to name that account,
so the switch cannot open anything by itself, and the CLI prints a warning in
every command until it is turned off. What is lost is worth stating plainly:
GitHub can then no longer tell the reviewer and the worker apart, and the model
rests on the human not using the same credential for both roles in the same
session. Two accounts are the correct setup; this is the documented exception.

Asking the gate
===============

::

    scripts/agent-supervisor explain 1042 1043      # why each one may not start
    scripts/agent-supervisor eligible               # what may start right now
    scripts/agent-supervisor labels --create        # define the two labels
    scripts/agent-supervisor config                 # resolved config, problems, warnings

``explain`` is the same code path the scheduler will use, which is the point: the
answer you read is the answer the machine acts on. Exit codes are for scripts —
``0`` yes, ``1`` no, ``2`` the question could not be asked (no ``gh``, unusable
configuration). ``--json`` gives the decision with the facts it was based on:
approver, timestamp, role, the events that were seen.

Scheduling a tick
=================

A tick is one pass over the queue, and it is a *decision procedure*, not a
daemon: the daemon of #1063 only calls it on a timer, so the same code answers
``plan`` in a terminal and runs unattended. The order matters and is fixed:

1. Forget plans that no runner adopted within ``plan_ttl_s``, so an issue is not
   blocked forever by a supervisor that was killed mid-start.
2. Re-ask the gate for every live lease and stop what a human withdrew since the
   last tick (below).
3. List the open issues that carry the approval label — one listing, filtered by
   label, never one request per issue.
4. Order them and keep the first ``max_candidates_per_tick``.
5. Read the claim board once for that candidate set.
6. Ask the gate about every candidate, *then* count the slots.
7. Take a lease and start what fits; report the rest with a reason.

Step 6 is deliberate. Checking the slots first would be cheaper, but it would
make the report say ``no-slot`` about issues nobody ever approved, and "why did
*this* wait?" is the question an operator actually asks. What bounds the reading
is ``max_candidates_per_tick``; the slot count only decides how many of the
eligible ones start.

Two supervisors, one issue
--------------------------

State lives in one SQLite file in ``state_dir`` — leases, verdicts and an event
log, all in WAL mode. The lease table is keyed by issue number, and a lease is
taken inside a ``BEGIN IMMEDIATE`` transaction: two ticks, two processes or two
hosts sharing the file cannot both be told they got #1042. The loser gets
``lease-taken`` in its report and moves on to the next candidate.

A lease carries the identity of the process that took it (host, pid, process
group, Compose project, OpenCode session) and a state — ``planned``,
``running``, ``stopping``, ``released``, ``failed``, ``abandoned``. That is what
makes a restart safe: a supervisor that comes back after a crash reads the same
leases the old one wrote and sees a running worker with a pid rather than
remembering nothing. Nothing is decided from memory, so a restart can neither
lose an issue that is in flight nor resurrect a decision an operator revoked.

Work somebody else started
--------------------------

The board of ``scripts/wip`` is the authority on who works an issue, and it
includes the developer in VS Code, a Codex session and any other OpenCode
client on any machine. A live claim by another client yields
``claimed-elsewhere`` naming the holder; a stale claim does not stop the tick
but is written to the event log, because it is the one signal that says
"somebody's machine died with work in progress".

The supervisor therefore never claims an issue itself. ``scripts/wip claim``
tags a claim by the worktree it runs in, and the tag must be produced by the
client that is going to do the work — a supervisor in a different checkout
would otherwise write a claim its worker cannot heartbeat or release. The worker
claims as its very first act inside its worktree (#1060); the supervisor only
*reads* the board and refuses to double-book it. When the board cannot be read,
the tick starts nothing: a late start costs an hour, a start against a human's
in-progress branch costs their work.

Order, cache and backoff
------------------------

Ordering is by the labels in ``priority_labels`` first, then oldest issue, then
number. It is a pure function of the listing, so two ticks agree on what comes
next and an operator can predict the queue. Oldest-first inside a rank is the
fairness rule: without it, a repository that keeps receiving new issues starves
the old ones forever.

Every answer the gate gives is recorded. A *refusal* whose cause cannot have
changed — nobody has labelled the issue, the approver is not on the allowlist —
is repeated from the cache for ``verdict_cache_s`` instead of reading the whole
label timeline again. A refusal whose cause is GitHub being unreachable or rate
limiting (``history-unavailable``, ``issue-unavailable``) is never cached,
because that excuse may be gone in a minute and caching it would turn a network
blip into a silent freeze of the queue. An *eligibility* is not cached either:
starting work is the act that must be re-proven. A failed start backs that one
issue off by ``retry_backoff_s`` and counts the attempt; the queue keeps moving.

Capacity
--------

Nothing heavy starts without ``scripts/agent_capacity`` agreeing, and the gate's
answer is read as a contract, not as an opinion: the scheduler asks for the job
class it intends to launch (``stack`` for a job that brings up Compose) and
accepts only a verdict that says the class fits. Two ceilings apply on top of
it — ``max_opencode_processes`` for workers and ``max_test_stacks`` for stacks —
minus the leases already live, and the slot count is the smallest of the three.
A capacity gate that cannot be read, or answers in a shape the scheduler cannot
parse, counts as *zero slots*, not as unlimited. The metrics behind the verdict
(load per core, ``MemAvailable``, disk, stacks) go into the report so a refusal
can be read without rerunning anything.

Withdrawal while work is in flight
----------------------------------

The first thing a tick does is ask the gate again about every live lease. A
human who adds ``agent: paused`` or removes the approval label while a worker is
running is answered in the next tick: the lease goes to ``stopping``, the reason
is logged, and the runner is asked to stop the worker. Stopping keeps the
branch, the worktree and the logs — what the human withdrew was the automation's
permission to act, not the value of the work done so far. A runner that cannot
stop its child leaves the lease ``abandoned`` with the error, rather than
pretending the work stopped.

Running the scheduler by hand
-----------------------------

::

    scripts/agent-supervisor plan                  # what a tick would start, starting nothing
    scripts/agent-supervisor status                # state file, live leases, recent events

``plan`` is the same path a tick takes with ``--plan-only``: it lists, orders,
checks the gate and the board, asks the capacity gate and prints its verdict,
but takes no lease and starts nothing. Use it after a configuration change
before letting the daemon act on it. ``status`` answers "what is the supervisor
busy with and what did it decide lately" from the state file alone — it needs no
GitHub read, which is why it still answers while the network is down.

Reason codes in a report
------------------------

``explain`` prints the gate's codes (above); a tick adds its own, all of them
readable as a sentence about one issue:

.. list-table:: Why a tick did not start an issue
   :header-rows: 1
   :widths: 26 74

   * - Code
     - Meaning
   * - ``claimed-elsewhere``
     - another client holds a live claim on the board; the holder is named
   * - ``held-here``
     - this supervisor already has a live lease on it
   * - ``lease-taken``
     - a second supervisor process won the lease in this same tick
   * - ``in-backoff``
     - an earlier start attempt on it failed within ``retry_backoff_s``
   * - ``no-slot``
     - eligible, but this tick's slots are used up
   * - ``per-tick-limit``
     - more candidates than ``max_candidates_per_tick``; the tail waits
   * - ``capacity``
     - the capacity gate refused the job class, or could not be read
   * - ``board-unreadable``
     - the claim board could not be read, so the tick started nothing
   * - ``no-runner``
     - leased and planned, but no runner exists to adopt the plan

What the supervisor does not do
===============================

It never approves anything. It never merges, enqueues or dequeues a pull
request, never resolves a review thread, never applies ``agent: approved``, and
never bypasses branch protection — the package contains no code path that could,
and a test fails if one appears. It changes nothing on the host either: the
capacity gate it consults is read-only by design, so a supervisor that believes
it needs more memory has one answer available, which is to wait.

What is still missing is the part that reaches into a worktree: #1060 runs the
OpenCode worker and performs the claim, #1061 and #1062 watch the pull requests
that come out of it, and #1063 adds the daemon, the systemd unit and the
operator's entry point. Until #1060 lands, a tick that would have started
something says ``no-runner`` and reports the plan instead — the lease is held so
the decision is honest, and aged out after ``plan_ttl_s`` so it cannot block the
issue.
