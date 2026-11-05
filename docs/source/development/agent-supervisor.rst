.. _development-agent-supervisor:


====================================
Agent Supervisor: The Approval Gate
====================================

.. sidebar:: Epic #1052, issue #1058

   Code: ``scripts/agent_supervisor/`` (standard library only) with the
   operator command ``scripts/agent-supervisor``. Checks:
   ``python3 scripts/test_agent_supervisor_approvals.py`` — no ``gh``, no
   network, no repository touched. This page documents the gate; the scheduler,
   the worktree runner and the CI and review supervision are the follow-up
   issues #1059 to #1063 and will extend this page.

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
"unset". The keys the scheduler and runner will use are already listed here so
one file — and one set of permissions around it — covers the whole supervisor.

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

What this branch does not do
===========================

It starts nothing. The gate answers questions; #1059 schedules against it,
#1060 runs a worker in a worktree, #1061 and #1062 supervise pull requests,
#1063 adds the daemon, the systemd unit and the operator entry point. Nothing in
this branch approves, merges, enqueues, resolves a review thread or bypasses
branch protection — and, as above, the package has no code path that could.
