.. note::

   Historical evidence retained for existing work. Issue #1592 supersedes the
   mandatory epic branch workflow and its scheduled strict rollout. New work follows
   :doc:`github-flow`; :doc:`github-flow-transition` records remaining operator actions.

.. _epic-branch-resolution:

====================================================
Epic branch resolution and pull request target rules
====================================================

.. sidebar:: Issue #1591

   Part of epic #1588 (enforce epic-based development and integration workflow),
   issue #1591: the executable half of the contract #1590 wrote. That page decides
   *what* an epic branch is and which pull request may target what; this page
   describes the tool that answers those two questions and refuses what the contract
   refuses.

   ``scripts/epic_branch.py`` reads GitHub through ``gh`` and branch heads through
   read-only ``git ls-remote`` / ``git merge-base``. It is host tooling like the rest
   of ``scripts/``: standard library only, offline-testable and not part of the deployed
   application. The QA jobs never see it at all (their container binds only
   ``./backend``); the one place it runs in CI is the transport job described under
   `In CI`_.

What it answers
===============

Two questions, both of which were prose in ``AGENTS.md`` before this tool existed —
"use the designated epic integration branch if applicable", with no definition of
*designated* and no *applicable*, and no workflow that ever looked at a develop-side
base:

* **resolve** — given an issue, which branch does its work start from and what is the
  legal base of its pull request? Answered from the *native* issue hierarchy, the
  relation ``AGENTS.md`` already makes authoritative over any label or title prefix.
* **check-pr** — given a pull request that exists, is it targeting what the contract
  says? Covers the child base (R4/R5), the epic branch's own base (R6, R9), child
  ancestry (R12) and the permanent pair (R13), which ``branch-policy.yml`` already
  guards for ``master`` and which is restated here so the whole target contract has one
  home. The workflow stands: this tool adds coverage and removes none.

The rows it implements, the open questions it inherits and the actor each refusal names
are in :ref:`epic-integration-contract`; this page is about the tool, not a second copy
of the rules.

Reading
-------

.. code-block:: text

   $ python3 scripts/epic_branch.py resolve --issue 1591
   #1591  target epic/epic-integration  row R2
     child of open epic #1588: the base is the epic branch `epic/epic-integration` and
     nothing else (R2)

   $ python3 scripts/epic_branch.py check-pr --pr 1703 --mode strict
   PR #1703  ao/topic/issue-1591-thing -> develop  target epic/epic-integration  row R5  mode strict
     [error] child-targets-develop: PR #1703 (issue #1591) targets the permanent branch
     `develop`, but the resolved target of #1591 is `epic/epic-integration` ... (R4)

Exit codes carry the verdict, so a caller can branch on them: **0** clean, or reported
while a gate is still advisory; **1** a violation, or an unreadable question, from a gate
running in strict mode; **2** a host-side question that could not be answered. ``--json``
prints the machine-readable result (``schema epic-branch/v1``) with the resolved ``row``,
``target``, ``branchSha``, the ``ancestry`` flag, the rollout ``mode`` and the finding
list; that is the shape #1592 reads when AO starts a worker.

Fail closed means: a body that names a parent the API does not report, a slug two epics
share, an ``epic/*`` branch no epic declares, a closed epic whose children cannot be
read, a failing ``gh`` or a failing ``git`` all produce ``status: "error"`` and never a
guess. The consumer of this answer branches from that commit and points a pull
request at it, so an ambiguous answer would be worse than no answer.

Commands
========

.. list-table::
   :header-rows: 1
   :widths: 38 62

   * - Command
     - What it answers
   * - ``resolve --issue N``
     - where the work of issue N belongs (R1, R2, R3, R9, R10, R11)
   * - ``check-pr --pr N``
     - whether pull request N targets what it should (R4-R6, R9, R12, R13)
   * - ``check-branch --epic N``
     - existence, uniqueness and staleness of one epic branch
   * - ``audit``
     - every open epic; ``--scope all-approved`` adds every open PR whose head names an
       issue — the rollout view #1594 needs
   * - ``create-branch --epic N [--write]``
     - create ``epic/<slug>`` at the tip of ``origin/develop``
   * - ``retarget --pr N --base B [--write]``
     - move an open pull request's base onto its target
   * - ``check-pr --no-ancestry``
     - ``check-pr`` without R12, for a shallow checkout (the CI mode; the result records
       that the rule was skipped)
   * - ``codes``
     - every finding code the tool can report
   * - ``check``
     - the tool's own self-test (pure rules, no ``gh``, no git)

Two reads, ``git ls-remote --heads origin`` and ``git merge-base --is-ancestor`` (plus
``git fetch origin <target>`` before an ancestry question), are the only git commands the
read path runs, and both are read-only. ``--repo`` overrides the repository, ``--today``
fixes the clock, ``--mode auto|strict|advisory`` chooses the rollout half.

The two write paths
===================

Both are a person's act, both are idempotent, and both need ``--write``, so an import of
this module cannot cause a write by forgetting a flag. Neither is an approval.

``create-branch`` implements rule 3: ``epic/<slug>`` starts at the tip of
``origin/develop`` at the moment of creation, so the epic branch owes develop nothing but
its own work. It pushes exactly one branch that does **not** exist yet, at a SHA it just
read from ``origin/develop``; a branch that already stands is reported and reused, never
pushed to, moved or deleted. That is why it does not collide with "never push to a
permanent branch" — nothing permanent is rewritten — and why re-running it is always
safe:

.. code-block:: text

   $ python3 scripts/epic_branch.py create-branch --epic 1588
   epic #1588  branch epic/epic-integration  ...
     epic branch `epic/epic-integration` from origin/develop at 3f602ad452 (dry run: nothing pushed)
   $ python3 scripts/epic_branch.py create-branch --epic 1588 --write      # a person

``retarget`` moves an **open** pull request's base, and only onto the base this tool has
resolved for it: a caller cannot point a pull request anywhere it likes through this
door. The single write is the GitHub base patch — no branch content, no approval, no
label, no merge. Rule 15's "a PR into an epic branch is retargeted by a person" is why
the flag is required and why the agent identity is refused:

.. code-block:: text

   $ python3 scripts/epic_branch.py retarget --pr 1703 --base epic/epic-integration --write

Both refuse the ``mrmap-agent-bot`` identity, checked against ``gh api user``. That
check is not an approval and no substitute for one — GitHub's ``author_association``,
the required reviewers and branch protection remain the real gate; it only refuses the
one case the repository has already ruled out.

Finding codes
=============

``scripts/epic_branch.py codes`` prints this list, derived by parsing this tool's own
syntax rather than by searching it, so prose cannot add a code to the vocabulary. The
suite below fails when the two lists drift apart. Each code names the actor who resolves
it — an agent for the ones that say "re-run", a person for the ones that say "register",
"retarget" or "reopen", because rule 15 grants an agent neither a branch nor a retarget
nor a label.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Code
     - What it means
   * - ``child-targets-develop``
     - A child PR points straight at a permanent branch; the epic's work stays on the
       epic branch until it integrates (R4)
   * - ``child-wrong-base``
     - A child PR bases on some other branch — another epic's, or a sibling's (R5)
   * - ``child-not-descendant``
     - The child head no longer descends from the epic head; the author merges the epic
       head in, never a rebase of a branch open for review (R12)
   * - ``fork-head-target``
     - A fork head targets an epic branch; an epic branch is a branch of this repository
       and a fork head can never descend from it (R12)
   * - ``epic-pr-base``
     - An epic branch is based on anything other than develop, or a non-nested parent (R6)
   * - ``nested-epic-base``
     - A nested epic integrates into develop instead of into its parent's branch (R9)
   * - ``master-target-violation``
     - Anything other than this repository's develop targets master (R13)
   * - ``epic-slug-invalid`` / ``epic-slug-too-long``
     - The declared slug is not a valid branch name component; never repaired (rule 1)
   * - ``epic-slug-missing``
     - An open epic declares no slug, so it has no branch identity; its children are on
       develop until it does (R3)
   * - ``epic-slug-conflict``
     - Two epics declare one slug, or a slug collides with a standing branch (rule 2)
   * - ``epic-branch-unclaimed``
     - An ``epic/*`` branch stands that no ``Epic``-labelled issue declares
   * - ``epic-branch-missing``
     - The epic's branch does not exist yet; ``create-branch`` is the protected path (rule 3)
   * - ``epic-branch-stale``
     - The branch still stands although its epic is closed (rule 11)
   * - ``epic-not-open``
     - A branch was asked for on a closed epic
   * - ``epic-parent-closed``
     - A nested epic's parent is closed, so R9 has no upward target
   * - ``epic-abandoned``
     - A closed epic whose children never reached develop; a person reopens or files
       fresh (R11)
   * - ``parent-missing``
     - A body names a parent the native relation does not report — the open question of
       the contract, refused rather than guessed
   * - ``head-branch-no-issue``
     - The head branch names no issue, so the target cannot be derived from it
   * - ``metadata-ambiguous``
     - The PR's issue does not resolve, so no target verdict is possible
   * - ``metadata-unreadable``
     - A ``gh`` or ``git`` call failed; the whole question fails closed
   * - ``pr-not-open``
     - A base was asked to be moved on a PR that is not open
   * - ``wrong-target``
     - ``retarget`` was asked for a base other than the resolved target

Rollout
=======

The same shape #1580 chose for pull request titles: ``--mode auto`` is **advisory**
before ``STRICT_FROM`` and **strict** from it, so no branch open today has its base
called a failure under somebody's feet, and the findings themselves do not change between
the halves — only the exit code does.

The mode is also how rule 16 (bootstrap) is expressed without hard-coding one epic into
the tool: ``resolve`` reports it, so the consumer that starts a worker reads ``advisory``
and keeps the children of an in-flight epic on ``develop``, and reads ``strict`` once this
rollout has landed. No verdict depends on the mode — only what a consumer may do with it.
A gate that is advisory declines to *stop* a pull request over an unreadable ``gh`` call;
it never reports such a run as a pass, and ``resolve`` still exits **2** in either half,
because a caller about to branch from a commit needs a real answer.

.. code-block:: text

   STRICT_FROM     = 2026-12-21            # scripts/epic_branch.py
   STRICT_FROM_ENV = MRMAP_EPIC_STRICT_FROM  # a deployment moves it, or a PR says so

.. _in-ci:

In CI
-----

``.github/workflows/pr-target-policy.yml`` runs ``check-pr`` on a pull request into
``develop`` and passes the exit code through. It is its own workflow rather than a second
job in ``branch-policy.yml`` because Actions filters ``pull_request`` at the workflow
level: reaching a develop-side PR from that file would mean widening its trigger and
gating each job with ``if:``, and an ``if:`` that quietly evaluates false makes the
``master`` protection skip — green, and not running. The permanent-pair check is
byte-identical to what it was; coverage was added beside it, which is the shape that
cannot weaken a protection.

Like ``pr-classification.yml``, the workflow is only transport — the rules live in the
tool, so there is no second copy in a YAML file to drift. It runs with ``--no-ancestry``,
which skips exactly R12 (the one rule that asks git about the head commit) so a run costs
no history deepening; the result records ``ancestry: false``, and the author and the
host-side caller run the same command without the flag.

Two things this tool deliberately does not do, both owned elsewhere. It does not close
the epic-branch CI gap: adding ``epic/**`` to the trigger lists of
``quality-assurance.yml``, ``script-tests.yml``, ``codeql.yml`` and
``pr-classification.yml`` is #1594's rollout decision, and it is an *addition* of
coverage — no path may skip a check for a branch, an author or a label. And it is not the
readiness gate: "every child merged, every cross-epic dependency an ancestor of both
develop and the epic head" (R7, R8) is #1593. ``scripts/next_eligible.py`` stays the
eligibility screen, unmodified; #1592 wires AO to read the answer this tool gives.

Tests
=====

.. code-block:: text

   $ python3 scripts/test_epic_branch.py    # 74 checks, no gh, no network, no real repository

Every ``gh`` and ``git`` call is answered by a fixture, including the two write paths —
the fixture records the push and the base patch it is asked for instead of performing
them, which is how the suite can assert both that ``--write`` writes exactly one thing
and that a dry run writes nothing. The checks that matter are the refusals: the unlinked
parent, the refused slug, the two epics on one slug, the orphan branch, the closed epic
that never integrated, the child PR at develop, the epic branch pointed anywhere but
develop, and every case where GitHub or git cannot be read. ``scripts/check_repo_tooling.sh``
runs it, which is what ``script-tests.yml`` runs.
