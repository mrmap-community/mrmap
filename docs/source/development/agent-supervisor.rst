.. _development-agent-supervisor:

Agent Supervisor: Approval Gate, Scheduler And Worker
=====================================================

.. sidebar:: Epic #1052, issues #1058 to #1061

   Code: ``scripts/agent_supervisor/`` (standard library only) with the
   operator command ``scripts/agent-supervisor``. Checks:
   ``python3 scripts/test_agent_supervisor_approvals.py``,
   ``..._scheduler.py``, ``..._capacity.py``, ``..._runner.py`` and ``..._ci.py``
   — none of them needs ``gh``, the network, a container or a model, and none of
   them can touch a repository. This page documents the gate, the scheduler, the
   worktree runner and the CI watcher; answering review feedback and the daemon
   that ties them to a timer are the follow-up issues #1062 and #1063 and will
   extend it.

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

Names are compared the way GitHub compares them: case-insensitively, and with
inner runs of blanks folded, because a label created through the API can carry a
double space that no one sees in the web UI. ``Agent:  Approved`` is therefore
the approval label; ``AGENT:APPROVED`` is a different label, and an issue
carrying only that one stays ineligible with ``no-approval-label``.

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
     - that number is a pull request, and pull requests are supervised by the CI
       watcher and #1062, not started from this queue
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

The scheduler, runner and CI watcher read the same file, so one set of file
permissions covers the whole supervisor.

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
   * - ``ci_repair_attempts``
     - ``2``
     - how many repair cycles the CI watcher may start for one pull request over
       its whole lifetime; ``0`` means "watch and report, never repair"

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

The supervisor therefore never claims an issue from its own checkout.
``scripts/wip claim`` tags a claim by the worktree it runs in, and the tag must be
produced by the client that is going to do the work — a supervisor in a different
checkout would otherwise write a claim its worker cannot heartbeat or release.
What the runner (#1060) does instead is run ``scripts/wip claim`` *inside* the new
worktree, as the first act of that worker and before a file is edited, so the tag,
the heartbeat and the eventual ``done`` all belong to the process that is doing the
work. The scheduling code only *reads* the board and refuses to double-book it.
When the board cannot be read, the tick starts nothing: a late start costs an hour,
a start against a human's in-progress branch costs their work.

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

``plan --start`` is the same tick with the hand attached: it reconciles what a
crash left behind, then starts what the tick decides to start. It is the command
to watch when a daemon is not installed yet, and the one an operator can run by
hand because it prints every decision it makes on the way.

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

Starting a worker
=================

The scheduler decides; the runner (#1060) is the only part that touches a
worktree, a process and a container. That separation is not decoration: the
decision "this issue may start" is a read-only question with a testable answer,
while starting is the act that can destroy work, so it happens in one place with
its own checks (``python3 scripts/test_agent_supervisor_runner.py``, 87 of them,
needing neither a model nor a container nor a repository write).

What one start does
-------------------

::

    scripts/agent-supervisor plan --start          # reconcile, then start what the tick decides

For each issue the tick chose, in this order:

#. The **lease** is taken first (``claim_lease``), so two supervisors cannot both
   reach the expensive steps. A lease that is live and whose process is still
   running refuses the start outright — a second client editing one branch is the
   accident the whole chapter exists to prevent.
#. The **worktree** is created from ``origin/master`` on its own branch
   (``agent/issue-<N>-<topic>``, or the branch the scheduler planned). ``git
   fetch`` runs *only* when a worktree is created: a job that merged master before
   every push would race every other job on the host and make each run's base
   different from the one CI reviews, so master comes in when the worker opens its
   pull request, which is the repository's own rule.
#. The **ignored files** a Compose stack needs (``worktree_env_files``: ``.env``
   and ``docker/backend/.mrmap.env``) are copied from ``repo_root`` with mode
   ``0600``. They are copied through the file API and never read, so no credential
   can reach a log line or an exception message — which names paths only.
#. The **claim** is filed inside that worktree (``scripts/wip claim``), as the
   first act of the worker, before a single file is edited. This is the supervisor
   acting *as* the worker, which is the only way the claim's heartbeat belongs to
   the process that can refresh it and to release it. A refused claim stops the
   start, the lease goes to ``abandoned`` with the reason, and no branch is
   touched.
#. Only then is **OpenCode** started: ``run --standalone --session <id> --auto
   --format json``, with the model from the configuration, the prompt on stdin
   (an issue's title and body are text for the model, never parts of a shell
   command line), and its own private home.

One worker, one home
--------------------

Each worker gets ``XDG_DATA_HOME``, ``XDG_CONFIG_HOME``, ``XDG_STATE_HOME``,
``XDG_CACHE_HOME`` and ``OPENCODE_DB`` under ``state_dir/workers/issue-<N>``, with
mode ``0700``. Two OpenCode clients writing one session database is a corruption
that shows up as a mysterious failure in whichever client lost the race, and the
supervisor runs several on purpose.

``COMPOSE_PROJECT_NAME`` is pinned to ``mrmap-agent-<issue>-<run>`` and
``COMPOSE_FILE`` to the standard files plus ``docker-compose.prebuilt.yml``, which
is what keeps a stack from rebuilding dependencies per run.

What a worker may not do is a configuration fact, not a prompt. ``--auto``
approves what a worker asks for, so the deny rules travel in
``OPENCODE_CONFIG_CONTENT`` — deny wins over allow, so a merge, a review, a force
push or a ``gh api`` write is refused by the client even when the prompt, the
issue text or a tool result asks for it in the same breath.
``worker_permissions`` replaces the list; empty means the built-in
``WORKER_DENY_PERMISSIONS`` of the package. An operator who weakens it weakens it
in one place, visibly.

A worker is a process group
---------------------------

``opencode run --standalone`` starts a child server, and a subagent is a grandchild
of that. Killing the pid that was spawned leaves the server serving and a subagent
editing files in a worktree nobody supervises, so every worker is started in its
own session and stopped with ``kill(-pgid)``. The lease records pid *and* pgid:
after a restart the pid is gone and the group is the only thing a log line can
still point at.

Whether a worker is alive is a harder question than ``kill(pid, 0)``, and both
traps were found by running the thing rather than reading it. A process that has
exited is a zombie until its parent reaps it, and a zombie answers signal 0 — so
"the pid is there" is not the question. And the worker is a child of the supervisor
process, where ``subprocess`` reaps it in the background, so ``waitpid`` reports
``ECHILD`` for a worker that has only just exited. The runner therefore does not
reap, does not trust signal 0, and reads the state out of ``/proc``.

Cancellation sends ``TERM`` to the group, waits ``cancel_grace_s`` (30 s by
default) and then ``KILL``s. A worker that may finish the tool call it is inside
commits nothing half-written; the window is short because the human who withdrew
the approval is already waiting. Branch, worktree, logs and claim are left exactly
as they are — what was withdrawn was permission to act, not the value of the work —
and the board gets one line saying why the job stopped.

After a crash or a restart
--------------------------

::

    scripts/agent-supervisor reconcile              # what is unaccounted for, and what was done

A process that is gone took its exit code with it, so reconciliation reads what is
left: whether the group still answers, whether the session log ends in an end event
or an error, and how long the lease has been live.

.. list-table:: What reconciliation reads
   :header-rows: 1
   :widths: 22 34 44

   * - Reading
     - Because
     - What happens
   * - ``running``
     - the group still answers
     - left alone; this is the duplicate-execution guard
   * - ``timed out``
     - live past ``worker_timeout_s``
     - cancelled like a withdrawal, because a stuck worker holds a slot an
       operator believes usable
   * - ``failed``
     - the session log ends in an ``error`` event
     - lease ``abandoned``; a deterministic failure is not retried forever
   * - ``finished``
     - the session log ends cleanly
     - lease released; the pull request, not the supervisor, is the evidence
   * - ``resumable``
     - the log ends mid-event (killed by a restart, host reset)
     - lease kept, session kept: the next tick continues the *same* OpenCode
       session in the same worktree

The last row is the reason the session id is recorded at the moment of the start.
Resuming the same conversation is the difference between "the host rebooted and 40
minutes of reasoning about this branch is gone" and a worker that continues.

What an operator can ask for
----------------------------

::

    scripts/agent-supervisor logs 1042 --tail 80    # the worker's own log, newest last
    scripts/agent-supervisor pause 1042 --reason "operator wants a look"
    scripts/agent-supervisor resume 1042
    scripts/agent-supervisor reconcile
    scripts/agent-supervisor stack-down 1042        # tear down that job's Compose stack

``logs`` reads from the state directory, not from the worktree: a branch that was
never pushed still has to explain itself, and the log is the only record of a run
that died before it could comment anywhere. Logs are written with mode ``0600``.

``resume`` asks the gate again. A paused issue, a removed approval or a closed
issue does not get to continue just because a process used to run for it.

``stack-down`` is the only place that runs ``docker compose down``, and the project
name is its whole safety argument: the name must have the agent shape *and* carry
this issue's number, or the command is refused before it is built. There is no
``--remove-orphans`` and no global prune anywhere in the package — the repository's
own cleanup rules record that orphans match by compose-file path rather than by
project, which once wiped a foreign stack despite an exact ``-p``.

Watching the checks of a pull request
=====================================

A worker's job ends at a pull request; the checks that decide whether it can be
merged keep running for another ten minutes after the process is gone. Without a
watcher that gap looks like a finished task, and with a naive watcher it looks
like an agent that keeps pushing at a red pipeline. ``watch-prs`` is the pass that
looks at them:

::

    scripts/agent-supervisor watch-prs --dry-run      # report only, wake nobody
    scripts/agent-supervisor watch-prs                # act: repair or escalate
    scripts/agent-supervisor prs                      # what it knows, per issue

Both commands read GitHub. The two writes reachable from them are the worker
process the runner starts in the issue's own worktree and ``scripts/wip``'s
question comment on the issue. There is no call anywhere in the watcher that could
approve, review, merge, enqueue, rerun a workflow or resolve a review thread, and
a check fails if a non-``GET`` path appears among its reads.

Which pull requests are followed
--------------------------------

Rows come from the supervisor's own leases, never from "whatever is open": the
watcher looks up the open pull request whose head is the lease's branch and
remembers it in the ``pull_requests`` table. A finished lease counts — a worker
opens its pull request and exits, and the review that follows is exactly the gap
this is for. A pull request that came back closed leaves the watch by itself but
keeps its row, because "closed" and "never tracked" are different answers.

Checks are read for the **pull request's head SHA**, plus the legacy commit
statuses, because a repository can mix the two and a watcher that reads only one
decides "all green" about a check it never saw. Not ``latest``, not the merge
commit.

A pass stays cheap enough to finish, which matters as soon as a timer runs it: a
pull request already recorded closed is never looked up again, and a lease that
never produced one is asked about for thirty days after its last update
(``MRMAP_CI_LOOKBACK_S``). ``--issue`` bypasses both bounds — an operator who names
a number wants an answer, not a policy.

What may wake a worker
----------------------

The asymmetry that decides every row of the table below: acting on a failure that
is really infrastructure costs code churn against a broken runner — commits that
fix nothing, a branch that drifts, a reviewer who cannot tell what was ever wrong.
Missing a real code failure costs a human noticing one red check they were going
to read anyway. So a repair cycle needs *positive* evidence that the failure names
a test, a lint rule or a build, and everything else is reported instead.

.. list-table:: The six answers one check gets
   :header-rows: 1
   :widths: 16 34 50

   * - Verdict
     - When
     - What happens
   * - ``green``
     - ``success``, ``skipped``, ``neutral``
     - recorded green, waits for a human review. Nothing is ever approved here
   * - ``pending``
     - queued, in progress, waiting
     - the normal state of a healthy pull request, never news
   * - ``cancelled``
     - someone stopped the run
     - a decision somebody made on purpose, not a defect to repair
   * - ``code``
     - the text names an assertion, a failed test, a lint rule, a type error, a
       migration or a coverage threshold
     - one repair cycle, if the budget allows it
   * - ``infra``
     - the text names DNS, a timeout, a 5xx, a rate limit, a full disk, a missing
       runner, a cache or artifact service or a docker daemon — or the run hit the
       workflow's own ``timed_out``
     - escalated to a human; the branch is not touched
   * - ``unknown``
     - a failure that names neither of the two
     - escalated. Guessing "probably the agent's fault" is exactly the input that
       turns a flaky runner into a branch full of meaningless commits

A failure whose text names *both* — a red test and "no space left on device" —
counts as ``infra``. A worker that edits code while the runner is also on fire
cannot tell which one it fixed, and neither can the reviewer.

Two budgets, because they fail differently
------------------------------------------

The lifetime budget is ``ci_repair_attempts`` (2 by default): how many repair
cycles one pull request may cost over its whole life. The per-head rule is stricter
and not configurable: one repair per head SHA. Without it one red commit is
repaired twice — once by the pass that saw it and once by the pass that sees the
same red check again while the worker has pushed nothing yet. And no repair starts
while a worker of that issue is still alive; the watcher holds the failure instead
of doubling the process.

A repair that may not run is reported as ``held`` with its reason ("budget spent
(2/2 repair cycles for this pull request)"), not swallowed: an operator reading
``prs`` should see a decision, not silence.

What a repair is
----------------

Not a new agent with a summary of the situation: the resume wakes the **same
OpenCode session** in the same worktree and Compose project, and the approval gate
is asked again first — a paused issue, a removed approval or a closed issue does
not get to continue just because a process used to run for it. The prompt names
the failing checks with their URLs and the head SHA that is red, tells the worker
to reproduce the named check before changing anything, to push as ordinary commits
on top rather than rebasing a branch that is open for review, and to stop with
``scripts/wip wait`` instead of pushing a guess when the check does not reproduce.
What the worker may not do stays the deny configuration of #1060, which applies to
a resumed worker exactly as it does to a started one: it is a configuration fact,
not wording.

A resume that cannot happen — no recorded session, a gate that now refuses — is
reported as ``repair-refused`` and costs no attempt: a budget is for failures that
were really tried.

Escalation goes to the board, not to the pull request
-----------------------------------------------------

``scripts/wip ask`` posts the whole question as one machine-managed comment on the
**issue** and puts the claim under *Needs user*. That is where the operator already
looks, and it is idempotent per client, so a watcher that runs every few minutes
cannot stack five copies of the same complaint. Escalation happens once per head
SHA: the marker of "already told you" is a row in ``ci_seen``, and it is written
only *after* the question went out — a board that was unreachable must not leave a
pull request looking reported, because then nobody would ever be told.

Merge-queue runs are not this worker's business
-----------------------------------------------

A ``merge_group`` run belongs to a merge commit GitHub builds itself, combining
this branch with other pull requests. A failure there may have nothing to do with
this branch, and "fixing" it would mean editing this branch to answer somebody
else's conflict. The watcher reports ``mergeable_state`` in every pass and acts on
nothing but the pull request's own head. The merge queue stays the merge queue:
nothing here enqueues, dequeues or reruns it.

What survives a restart
-----------------------

Both tables live in the supervisor's SQLite file next to the leases.
``pull_requests``: which pull request belongs to which issue, the head it was last
seen at, the budget already spent. ``ci_seen``: every *check, head SHA, verdict*
triple already dealt with. After a crash the answer to "have we already acted on
this one?" comes from disk, so a supervisor that comes back does not read last
night's red check as news and wake the worker a third time. Re-tracking a pull
request keeps ``attempts`` and ``repair_sha`` — losing the budget at the moment the
worker pushes a new commit is how a bounded budget becomes an unlimited one.

Exit codes are for a timer
--------------------------

``0`` nothing waits for anybody; ``1`` at least one pull request is red in a way
only a human can settle; ``2`` the question could not be asked at all. That is the
whole contract the timer of #1063 needs.

What the supervisor does not do
===============================

It never approves anything. It never merges, enqueues or dequeues a pull
request, never resolves a review thread, never applies ``agent: approved``, and
never bypasses branch protection — the package contains no code path that could,
and a test fails if one appears. It changes nothing on the host either: the
capacity gate it consults is read-only by design, so a supervisor that believes
it needs more memory has one answer available, which is to wait. It never removes
a worktree, a branch or a volume it did not create, and one test per rule keeps it
that way.

What is still missing is the rest of what a worker leaves behind: #1062 answers
review feedback on the pull request, and #1063 adds the daemon, the systemd unit
and the operator's entry point. Until #1063 lands, running a tick means running
``plan --start`` and watching CI means running ``watch-prs`` — by hand, or under a
supervisor of one's choosing. Both are one command with an exit code, which is
what makes that substitution safe rather than improvised.
