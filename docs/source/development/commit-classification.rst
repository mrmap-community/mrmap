.. _commit-classification:

=================================================
Pull request and commit classification
=================================================

.. sidebar:: Issue #1580

   Part of epic #1577 (release management), issue #1580: the classification rule
   of the :ref:`Release and versioning baseline (ADR) <release-versioning-baseline>` made enforceable. The tool is
   ``scripts/pr_classify``, the CI check is ``.github/workflows/pr-classification.yml``,
   and the offline suite is ``python3 scripts/test_pr_classify.py``.

   The tool reads. It approves nothing, merges nothing, resolves nothing and
   bypasses no branch rule — those acts belong to a person. The normative calls
   of #1578 (``Q1``..``Q6``) are still **Pending** in that page's decision
   register, and nothing here pre-empts them: this page enforces *that a change
   is classifiable*, never *which version a change consumes*.

Status of this page
===================

As on the baseline page, three kinds of statement are kept apart:

* **measured** — a command was run against this repository and its output is
  quoted. `Reproducing the measurements`_ gives every command.
* **the rule** — what the tool enforces, and why it is enforced that way.
* **not enforced** — what the tool deliberately does not decide, and which
  follow-up issue owns it.

All measurements below were taken on ``origin/develop`` at ``0ac18ad93`` on
2026-11-19. The repository had no tag and no release at that time (#1578).

Why the pull request title is what gets enforced
================================================

The rule sounds arbitrary — Conventional Commits is a *commit* convention, and
this checks a *title*. The reason is a measurement about how this repository
integrates code, and it decides the whole design.

GitHub writes the pull request title into the merge commit as its body, and
that is the entire body:

.. code-block:: text

   $ git log -1 --format='%s' c0fe2183b
   Merge pull request #1649 from mrmap-community/ao/mrmap-1849/issue-1434-mcp-setup-env-read

   $ git log -1 --format='%b' c0fe2183b
   mcp-setup: reads the slot's env by key instead of sourcing it (#1434)

Measured over all 840 GitHub-authored merge commits on ``develop``: **825 of
them (98 %) carry a body of at most one line.** No commit list, no description,
nothing but the title. The consequence is unavoidable and is the axis of this
page:

* A marker that is written into a commit message — a ``BREAKING CHANGE:``
  footer, a ``!`` on a commit header — **does not reach** ``develop``. It is
  folded away at the merge and is invisible to any reader afterwards, including
  the release tool of #1581.
* The title is the only string that survives, so the title is where the class
  has to be, and where ``!`` has to be.
* Consequently, a pull request that marks itself breaking in a commit and not
  on the title is reported as an **error**, not as a style nit. It is not a
  formatting complaint: the fact would be lost. This is the finding
  ``breaking-lost-at-merge``.

Nothing in this repository's merge settings was changed for this issue, and no
setting was assumed. The rule above holds for a merge commit; under a squash the
class would travel in the squashed subject instead, which the tool reads too
(`squash-subject`). Both readings are supported, so no decision about squash
versus merge is required to enforce the classification.

What is enforced
================

The header shape is Conventional Commits: ``<type>[(<scope>)][!]: <summary>``.
The type vocabulary and the release semantics behind it are the matrix proposed
by :ref:`release-versioning-baseline` (#1578); this page does not restate the
matrix, it applies it.

.. list-table::
   :header-rows: 1
   :widths: 18 30 52

   * - position
     - rule
     - why
   * - type
     - one of the approved classes: ``feat``, ``fix``, ``perf``, ``refactor``,
       ``revert``, ``build``, ``chore``, ``ci``, ``docs``, ``style``, ``test``
     - a type outside the list classifies nothing. A release tool cannot put an
       entry under a heading it cannot name.
   * - scope
     - optional, free-form, kebab-case
     - this is where a component name belongs. See below.
   * - ``!``
     - required whenever anything in the pull request declares a breaking change
     - the merge keeps the title only, so the marker has to be on it.
   * - summary
     - non-empty; a heading, not a sentence
     - it becomes the release note line.

The most common invalid title in this repository is not a missing class, it is a
**component name in the type position**. Measured: 267 subjects on ``develop``
parse as a header but name something that is not a class — ``Frontend:`` (55
times), ``MapContextEditor:`` (25), ``MapContext:`` (20), ``WmsSecuritySettings:``
(16), ``RuleForm:`` (14), ``mcp-setup:``. The checker names that reading out loud
and answers with the correction, rather than just rejecting the string:

.. code-block:: text

   1. ERROR: 'mcp-setup' is not a change class; it reads as a component name in the type position.
      fix:   name the class and move the component into a scope: 'feat(mcp-setup): <summary>'

Rejected names are not left bare either. ``security``, ``sec``, ``deps``,
``wip``, ``hotfix``, ``release``, ``fixup!`` and ``debug`` each carry a written
alternative in the tool's hint table, because a rejection that does not say what
to write instead only produces a second attempt that also fails. ``fix(security):``
is the accepted spelling of the first two: a security fix **is** a fix, and
``security`` is a scope, not a class — the same for ``build(deps)`` and
``chore(deps)``.

Enforced, reported, and not decided
-----------------------------------

The issue asks for the release-relevant classes to be validated, and that is
what happens. What it does *not* do is arithmetic:

* **class — enforced.** Can this change be put in a release note, and under
  which heading? That is decidable from the title alone, and it is what fails
  the check.
* ``consumes_version`` — **reported, never gated.** The tool prints whether the
  class consumes a version, but no check fails or passes on it, because #1578's
  ``Q1``..``Q6`` (what counts as a breaking change, how pre-release versions are
  handled) are still Pending and the version rule itself is #1581's. Gating on
  an unanswered normative question would be a decision by a bot.
* **diff-aware dependency detection** — not attempted. ``build(deps)`` is
  trusted as written. Nothing here inspects a lock file.
* **changelog generation, version calculation, tags, releases** — #1581, #1584,
  and the canonical version of #1579. This issue produces classifiable input and
  stops there.

The tool as a command
=====================

Host Python, standard library only. No ``gh``, no network, no application, no
GDAL, no container, no write to the repository: every git call is a read-only
``git log`` (`--repo` selects which repository, for a suite or a second clone).

.. code-block:: console

   $ python3 scripts/pr_classify types           # the vocabulary, with what each class consumes
   $ python3 scripts/pr_classify title "fix(proxy-security): closes the open redirect"
   $ python3 scripts/pr_classify pr --title "$TITLE" --body-file body.txt --commits-json commits.json
   $ python3 scripts/pr_classify history --range origin/develop~300..origin/develop
   $ python3 scripts/pr_classify check           # the tool's own self-test

Exit codes: ``0`` pass, ``1`` a finding fails in strict mode, ``2`` usage.
``--json`` answers in machine-readable form — that payload, not the prose, is
what #1581 will read.

How a history is read
=====================

``history`` answers the question a release asks of a range: *what changed,
counted once*. #1580's acceptance names the two failure modes — counting
duplicates, and losing breaking changes — and both fall out of one traversal.

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - role
     - what it means, and what happens to it
   * - carrier
     - a pull request's own merge commit, or a squash subject ``summary (#NNNN)``.
       It owns the entry, classified by the title GitHub wrote into it.
   * - folded
     - a commit the carrier introduced. Not an entry: one pull request is one
       change, not one per commit. Its words are still read, for one thing — the
       breaking fact — which is then unioned into the carrier.
   * - sync
     - a merge of the base into a branch (``Merge remote-tracking branch
       'origin/develop' into …``, or a prose "merge develop into the issue-…
       branch"). Measured: 326 of them on ``develop``, and none of their
       subjects parses. It contributes **nothing** — its side of the merge was
       already counted by the pull requests that brought it.
   * - self
     - a commit that reaches the branch with no pull request behind it. Its own
       entry, and its own warning if it carries no class.

Three further rules carry the rest of the acceptance:

* **a nested carrier keeps its own entry.** This is the multi-feature epic: an
   epic branch merged into ``develop`` answers one entry per feature pull
   request — not one for the epic plus one per feature, and not one for the
   epic alone. A commit under a nested carrier belongs to *that* carrier, not
   to the outer one; attributing it outward is how a feature's breaking marker
   lands on the wrong change.
* **the same pull request entering twice is one change.** The copy that entered
   first is the entry and the later copy nets to nothing (``--seen FILE`` carries
   the memory across reports, which is how a ``develop`` → ``master`` promotion
   is recognised as a re-carry rather than new work). One exception: if only the
   later copy carries ``!``, the breaking copy wins and the disagreement is
   reported — a duplicate merge may not quietly drop a breaking marker.
* **a revert pairs with what it reverts, inside the window it is read in.** A
   feature added and taken back between two releases ships nothing, so the pair
   nets to no entry *and* answers no breaking note. A revert whose target is
   outside the window is a change in its own right — that is what an operator
   who upgraded will read about.

Where a fold is not claimed
---------------------------

A fold is asserted only where a **merge edge proves it**. A commit that only a
plain parent edge leads to stays an entry of its own. That is a deliberate
under-report: answering which pull request such a commit belongs to would mean
guessing across a rebase or a sync, and this tool would rather see one change
twice than attribute somebody's work to the wrong change. The direction of the
error is chosen so that it can only ever be safe — an unattributed commit still
stands as its own entry, so it is never lost.

The rollout
===========

Measured on the same commit: **53 of 7641 commits (0.7 %) name an approved
class**, **26 of 840 pull request titles survive the merge with one**, and
**no commit in the history of this repository has ever carried a
``BREAKING CHANGE:`` footer**. Every pull request already open when this check
lands is written in the old style.

So the check arrives in two halves, on a date rather than on an opinion:

.. list-table::
   :header-rows: 1
   :widths: 26 12 62

   * - phase
     - exit
     - behaviour
   * - advisory, until ``STRICT_FROM``
     - ``0``
     - every finding is printed and annotated as ``::warning::``, including the
       ones that will later be errors, and the verdict says how long it has left.
   * - strict, from ``STRICT_FROM``
     - ``1``
     - an error fails the check. The findings themselves are unchanged — the
       same words, with ``::error::`` in front of them.

``STRICT_FROM`` is ``2026-12-07`` (three weeks out), overridable per deployment
with ``MRMAP_PR_CLASSIFICATION_STRICT_FROM``, and ``--today`` fixes the clock in
a test so both halves of the boundary are exercised offline. ``--mode`` overrides
the date entirely, in either direction.

What the rollout explicitly does **not** do:

* It does not rewrite history, and it does not require it. The 7588 commits that
  do not classify stay as they are; #1581 will have to read a range that begins
  unclassified, and that is a fact about the past, not a defect to hide.
* It does not retitle a branch that is already under review, and does not ask
  anyone to. An existing pull request gets the advisory report, and the date is
  public, so the author chooses when — retitling a pull request is free at any
  time and touches no commit.
* It does not change CI or branch protection. Whether this check is *required*
  for a merge is a branch-protection setting, and only a person sets it. Until
  they do, the check is informational on the required-status view and strict on
  its own terms from the date.
* It does not approve, merge, resolve a thread, or grant access. There is no
  code path here for any of those.

Reading a failing check
=======================

A failure is always a specific sentence with a place and a fix:

.. code-block:: text

   2. ERROR: a commit of this pull request declares a breaking change (aaaaaaaaaa)
      while the title carries no '!' marker.
        where: commit aaaaaaaaaa
        fix:   add '!' to the title - a merge keeps the title only, so the marker
               written in the commit is lost at the merge

The finding codes are stable and are what the suite pins:
``empty``, ``no-header``, ``malformed-header``, ``unknown-type``, ``security-named``,
``scope``, ``scope-case``, ``empty-summary``, ``summary-start``, ``summary-period``,
``missing-space``, ``breaking-not-on-title``, ``breaking-lost-at-merge``,
``breaking-non-release-class``, ``breaking-without-note``, ``breaking-in-duplicate``,
``breaking-folded-up``, ``breaking-reverted-in-window``, ``revert-names-nothing``,
``commit-class-differs``, ``carrier-unclassified``, ``commit-unclassified``. Run
``python3 scripts/pr_classify types`` for the vocabulary; the verdict line names both.

Two findings are worth knowing before they are seen:

* ``commit-class-differs`` is a **warning**, not an error. A commit inside a pull
  request may keep the repository's existing house style (a short lowercase
  summary) — the title carries the class for all of them. It is raised because a
  commit that really is a *different* class is usually a second change riding
  along, which is the one-PR-one-issue rule of #1580's scope.
* ``commit-unclassified`` on a commit inside a pull request is not raised at all.
  Only a commit that reaches the branch with no pull request title behind it is
  asked for a header.

CI and where the rule lives
===========================

``.github/workflows/pr-classification.yml`` runs on a bare runner
(``pull_request``: opened, reopened, synchronize, edited — against ``develop``
and ``master``) and does one thing: hand the tool the title, the body and the
commits, and pass its exit code through. Title and body come from the event
payload, not from the checkout, so a branch cannot choose the text its own check
reads. There is no ``merge_group`` trigger: the queue merges a branch that
already answered for itself, and a rule that fails only in the queue reports the
wrong person.

The rule itself lives in ``scripts/pr_classify``, not in the workflow. That is
why the whole thing is testable: the workflow's exact input — GitHub's
``pulls/<n>/commits`` JSON — can be piped into the same command from a file, and
``scripts/test_pr_classify.py`` does exactly that.

The check reads its commits from the API rather than from the checkout, and that
is not an accident of convenience: a ``pull_request`` checkout is shallow, so a
``HEAD~40`` style range does not exist on the runner at all. Measured on a
depth-1 clone. The tool now says so when a range fails there — naming the
shallow clone and pointing at ``--commits-json`` — instead of quoting git's
"unknown commit", and the suite pins that message on a shallow checkout.

Verification
============

``scripts/`` is bound to no QA container (those see only ``./backend``), so its
suites run in one bare-runner job. ``python3 scripts/test_pr_classify.py`` runs
alone; ``scripts/check_repo_tooling.sh`` runs it with the rest, and CI runs that.

The suite covers, in the order of the acceptance criteria:

* valid and invalid titles, and that every hint's suggested correction is itself
  a title the checker would accept (a hint table that drifts from the vocabulary
  is a hint table that sends people to a second failure);
* ``!`` and every footer spelling, and the two loss cases — a breaking body and a
  breaking commit with no ``!`` on the title;
* ``fix(security)``, ``build(deps)``/``chore(deps)``, the non-release classes, and
  the four ways a revert may name what it reverts;
* merge, squash, sync, promotion, re-merge, multi-feature epic, and revert
  histories, each counted once;
* both halves of the rollout date, and both exit codes;
* GitHub's commit-API shape, a plain list, and the ``git log`` record stream, in
  either arrival order — the tool sorts over the parent edges itself;
* the traversal once against a **throw-away git repository with real merge
  commits**, so what is tested is the parentage the folding depends on and not a
  hand-drawn picture of it.

Reproducing the measurements
============================

.. code-block:: console

   # the title is the whole merge body, and how often that is true
   $ git log -1 --format='%b' c0fe2183b
   $ git log --merges --format='%s' origin/develop | grep -c '^Merge pull request'

   # how much history classifies, and how much of it is a component name
   $ python3 scripts/pr_classify history --range origin/develop --mode advisory
   $ python3 scripts/pr_classify history --range origin/develop --json | jq '.counts'

   # the whole offline suite, and the tooling job CI runs
   $ python3 scripts/test_pr_classify.py
   $ scripts/check_repo_tooling.sh

Where this leaves the epic
==========================

#1580 is the input side of #1577: after it, a change on ``develop`` carries a
class, and a breaking change carries a marker that survived the merge. It leaves
for others, deliberately:

* **#1581** — read the classes and compute a version. The ``--json`` payload and
  the ``consumes_version`` field are its input; the Pending ``Q1``..``Q6`` are
  its blockers, not this page's to answer.
* **#1579** — the canonical version string.
* **#1584** — changelog and release notes, which are what the ``changelog``
  column of every entry is there for.
* A person, when they choose to: making this check *required* in branch
  protection, and moving ``STRICT_FROM`` for a deployment.
