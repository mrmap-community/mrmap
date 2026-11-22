.. _release-lifecycle-dry-run:

=========================
Release lifecycle dry run
=========================

.. sidebar:: Issue #1586

   Part of epic #1577 (release management), issue #1586: validate the complete
   release lifecycle in a dry run. The promotion that acts on the lifecycle is
   :ref:`release-promotion` (#1584), the gates a candidate passes are
   :ref:`release-compatibility-gates` (#1583) and the planner that proposes the
   version is :ref:`release-planning` (#1581); the lifecycle itself is
   ``scripts/release_lifecycle.json``, described for operators in
   :ref:`release-operator-runbook`. The tool is
   ``scripts/test_release_lifecycle_dry_run.py``.

What this is, in one line
=========================

One command that replays a whole stable release - every phase of
``scripts/release_lifecycle.json``, from ``pre-release`` to ``post-release`` -
against a throw-away repository, and prints two halves: what it actually
exercised, and what a dry run cannot decide offline. It publishes nothing. It
needs no network, no credential and no container.

Why it exists
=============

Each tool of the release path has its own suite: ``scripts/test_release_lifecycle.py``
holds the lifecycle description against the files it names, the suites of #1584
prove the promotion steps and those of #1583 prove the gates. None of those
answers the question of #1586: do the phases, the actors they name and the
systems they depend on fit together for one complete release, and what blocks a
dry run? That is a question about the sequence, so it needs a run of the
sequence.

Run it
======

From the repository root, on host Python with nothing but the ``git`` CLI:

.. code-block:: console

   $ python3 scripts/test_release_lifecycle_dry_run.py
   $ python3 scripts/test_release_lifecycle_dry_run.py --report /tmp/lifecycle.json

The exit codes are those of every tool in ``scripts/``: **0** every check
passed, **1** a check failed, **2** the harness could not run - and "could not
run" is never reported as a pass. The suite is picked up by
``scripts/check_repo_tooling.sh``, which is the job CI runs for ``scripts/``, so
``bash scripts/check_repo_tooling.sh`` is the wider command.

``--report`` writes the report the terminal shows as JSON: ``exercised`` (the
phase, the verdict, the command that ran and what it answered), ``blocked`` and
the ``isolation`` note. That file is the evidence this issue asks for - commands,
SHAs and digests included - and it is a report, not a gate: nothing consumes it
to decide a release.

What the walk actually is
=========================

A synthetic mrmap-shaped repository: ``VERSION``, the projection
``backend/MrMap/version.py``, ``.release-please-manifest.json``, ``CHANGELOG.md``
with the ``# Pre-1.0 Compatibility Baseline`` section, an ``X-CLIENT-VERSION``
openapi component, and a ``backend/`` tree with migration directories including
the #1180 constraint files and the markers of #1178 and #1179. A bare repository
plays the remote; the lifecycle JSON and the release tools are copied into it, so
every phase runs the real tool against real files with real git history.

The isolation is how the walk is built, not a claim in a comment:

- ``gh`` is the journaling shim of #1584. Every GitHub call is written to a log
  and answered from a local state file, so a tag, a release, a pull request or an
  issue exists only inside a temp directory. That same journal is what proves the
  promotion path never calls anything that closes an issue.
- the git remote is a local bare repository, so no ref of this repository can be
  written by a walk.
- ``GIT_CONFIG_GLOBAL`` and ``GIT_CONFIG_SYSTEM`` point at ``/dev/null``, so no
  developer identity and no credential helper can leak into the commits it makes.
- no credential is read and no socket is opened.

Every phase is looked up by the ``id`` of the lifecycle JSON, so a rename fails
the walk out loud instead of quietly skipping a phase.

The phases and what each one proves
===================================

``pre-release`` (actor: contributor)
   A code change that owes nothing: ``canonical_version --check`` is green, a
   hand-edited ``VERSION`` is refused, ``--write`` repairs the drift, and both
   gates answer green for a range that raises no version question. Red half: a
   migration node with no operations is refused as a fake node, and green again
   once the reviewed ``release-gates: empty-operations`` marker names it.

``cut`` (actor: human)
   The Version Release PR onto develop. The walk starts where develop starts,
   checks that the merged release files carry the class the range earned, and
   then asks the promotion tool what it sees: ``plan`` names the version,
   ``status`` reports the candidate planned but not frozen, no pull request, no
   tag.

``build-and-gate`` (actor: CI)
   ``preflight`` on the candidate with the report files of #1583 - the
   composition #1584 defines. Red half on a version move without its folded
   changelog section: the candidate is refused and writes no attestation. Green
   half: the attestation binds the candidate SHA, and the version identity check
   of the candidate document is asserted from both sides - the candidate's own
   document passes, a document that says another version is refused. That second
   half is the mock documentation gate contract the scope boundary of #1586
   names.

``promote`` (actor: human, protected environment ``release-stable``)
   ``open-release-pr`` freezes ``release/v<version>`` at the candidate and opens
   one pull request to master; the gate stays ``pending`` while that pull request
   is unmerged; ``finalize`` refuses to tag a master that does not carry the
   candidate; the step is idempotent. Then the walk performs the merge on behalf
   of a person and checks that master carries the candidate's tree while the gate
   still reports no tag. Red half: evidence with a missing class, and evidence
   gathered for another SHA.

``verify-on-master`` (actor: CI)
   ``finalize`` in one run, as #1584 requires: master's tree is checked against
   the tested candidate before ``verify``, the tag and the GitHub release are
   published, master has moved to the tag's commit, the version equality check
   ``verify`` runs is asserted from both sides, and the release body carries the
   attestation and the version. Red half: a master whose tree diverged, a missing
   image digest, a rolling alias.

``post-release`` (actor: human)
   ``sync`` opens the master to develop pull request and leaves it open for a
   person to merge; the journal proves no issue-closing call was made.

The version policy, which needs a released baseline
===================================================

The bump question - patch, minor, major - is decidable only from a released
baseline, and this checkout has none: Q1 of #1578 is Pending, so
``scripts/release_contract_baseline.json`` is in ``pre-baseline`` mode and the
committed reading reports the required class as an advisory. The walk alone
cannot show the class rules, and the suite does not pretend otherwise. It asserts
the committed pre-baseline reading first, then runs the same tools against a copy
of the manifest in ``released`` mode at the baseline version - the content the
first published release will commit - for each class:

- a feature demands a minor bump, and ``0.1.0 -> 0.2.0`` is one;
- a fix demands a patch bump, and ``0.1.0 -> 0.1.1`` is one;
- a class-less range demands no bump and may keep the baseline version, while a
  patch-worthy range that keeps it is refused and a candidate behind the baseline
  is refused rather than floored to it;
- a breaking change below 1.0 passes as the reviewed 0.x minor reading of the
  manifest's own ``breaking_below_1_0`` knob - but only with the evidence the
  gate names: the same candidate whose notes stay silent is still refused;
- a breaking change that becomes ``1.0.0`` keeps the major path open;
- with that knob read as ``major``, the very same minor move is refused.

One walk per class, deliberately: the gate judges the range from the base to
``HEAD``, so several classes measured from one shared base would each be judged
by every earlier class too, and a patch bump would read as a feature.

Concurrency, prereleases and what stays refused
===============================================

Two runs that both believe they hold the candidate of one version is not a race
the tool resolves by last-write-wins: the second freeze is refused as a conflict,
and the check that follows proves nothing moved - the frozen branch still points
where the first freeze put it, and there is still no tag and no release. Three
attempts at the freeze cost one pull request, which is what the journal counts.
The promotion stays resumable afterwards: the merge and the publication of the
run that owns the freeze are unaffected by the refused attempt.

A prerelease version is refused by ``release_gates.py`` and by
``release_promotion.py`` alike, the tag pattern of the lifecycle accepts only
``vX.Y.Z``, and the multiversion selection of ``docs/source/conf.py`` excludes
the prerelease pattern - the three agree, and the walk reads all three. Rolling
aliases stay refused while Q1 of #1578 is Pending, and the check that asserts it
names Q1, so the check that trips when the answer lands explains itself.

What a dry run cannot decide offline
====================================

The second half of the report, which the acceptance criteria require. Nothing in
it is a hardcoded list: every entry is derived from a constant of the tooling -
``release_gates.REQUIRED_EVIDENCE``, ``release_promotion.CHECK_CLASSES``, the
images whose digests the attestation binds, the gate reports the promoter
demands, the protected environment of the lifecycle's own ``promote`` phase and
the oldest supported baseline of the #1180 constraint file. A mechanism that
becomes drivable offline therefore drops out of the blocked list by itself
instead of sitting there unnoticed.

.. list-table::
   :header-rows: 1
   :widths: 28 47 25

   * - What stays blocked
     - Why an offline walk cannot decide it
     - Who owns it
   * - Runtime evidence of the promotion gate
     - The candidate OpenAPI document needs GDAL and ``manage.py spectacular``,
       and the evidence classes come from real CI runs; the walk feeds a saved
       payload through the tool's own ``--checks-file`` seam.
     - ``unit-tests``, ``acceptance-tests``, ``sonarcloud``
   * - The built images the attestation binds
     - The digests of ``mrmap-backend`` and ``mrmap-frontend`` are published by
       CI; well-formed digests pass the same ``--artifact`` seam but cannot be
       pulled here.
     - ``scripts/image_release.py``
   * - The CI upgrade run from the oldest supported baseline
     - The upgrade gate checks the migration graph and the #1180 boundaries
       offline; migrating a deployment needs PostgreSQL.
     - ``.github/workflows/quality-assurance.yml``
   * - The rollback drill
     - A rollback is a database operation, and no PostgreSQL exists in an offline
       suite.
     - the :ref:`operator runbook <release-operator-runbook>`
   * - The protected-environment approval
     - The promotion runs behind ``release-stable``, whose required reviewers are
       people. The walk drives the same steps through a ``--gh-bin`` shim, so the
       gate is exercised and the approval is not.
     - the GitHub environment ``release-stable``
   * - The human acts of ``cut``, ``promote`` and ``post-release``
     - Those merges are simulated by git moves the walk performs on behalf of a
       person. The constraint that reserves them is asserted, never exercised: an
       automation that could perform them would not have tested the rule that
       reserves them.
     - humans alone approve, merge and resolve

Reading a run
=============

A step is recorded with the command that produced it, and a red observation is a
step like any other, because a phase that was skipped or mocked must not read as
verified. The line ``N of M checks passed`` is the verdict, and ``N < M`` prints
every failed check name to stderr before it.

When it should be re-run
========================

Any change to the lifecycle JSON, to its phase list, or to the evidence class map
of one of the tools should make this suite say something - by walking a new phase
or by dropping an entry from the blocked list. If it stays silent about such a
change, that is a gap in the suite: the phase list is asserted complete against
the file, so a phase no function of the walk handles fails it rather than being
skipped.

The dry run publishes nothing, and this page is no licence to publish either. A
real release stays what the lifecycle says it is: a version a person cuts, a gate
a person approves, a merge a person performs, and a first real release for which
the maintainer's separate authorization is still outstanding.
