.. _release-lifecycle-dry-run:

=========================
Release lifecycle dry run
=========================

.. sidebar:: Issue #1586

   Part of epic #1577 (release management), issue #1586: validate the complete
   release lifecycle in a dry run. The promotion that acts on the lifecycle is
   :ref:`release-promotion` (#1798, which replaced the orchestrator #1584 had
   shipped), the gates a candidate passes are
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
prove the promotion steps and those of #1583 prove the gates. The promotion
steps are read out of the committed workflow YAML and run, so what the walk
drives is what CI runs. None of those
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

A synthetic mrmap-shaped repository: ``VERSION``, its generated projection
``backend/MrMap/version.py`` (written by ``canonical_version.render_projection``,
never retyped) and ``.release-please-manifest.json``; a ``CHANGELOG.md``
whose release section is the ``## [<version>] - <date>`` fold ``plan`` demands
and whose ``### Migration notes`` subsection names the migration the range adds;
and a ``backend/`` tree of migration directories carrying the #1180 protected
nodes under exactly the names ``scripts/release_upgrade_baseline.json`` lists,
the marker node among them. The reviewed contract baseline, exceptions ledger and
upgrade constraint files of this checkout are copied in unchanged, as are the
release tools and the lifecycle JSON, so every phase runs the real tool against
real files with real git history. A bare repository plays the remote.

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
   The Version Release PR onto develop. The walk starts where develop starts and
   checks that the merged release files carry the class the range earned. Then it
   runs the promotion's own ``verify`` step against that develop and asserts the
   refusal: with no merged ``develop`` -> ``master`` pull request there is nothing
   to publish, which is the develop-first rule proven rather than claimed.

``build-and-gate`` (actor: CI)
   ``release_gates.py promote`` on the candidate with the report files of #1583 -
   the one attester of the evidence binding, whose digest and provenance contract
   #1799 and #1800 own. Red half on a version move without its folded changelog
   section: ``publish`` refuses the candidate and writes no tag and no release.
   Green half: the attestation binds the candidate SHA, and the version identity check
   of the candidate document is asserted from both sides - the candidate's own
   document passes, a document that says another version is refused. That second
   half is the mock documentation gate contract the scope boundary of #1586
   names.

``promote`` (actor: human, protected environment ``release-stable``)
   The walk performs the reviewed ``develop`` -> ``master`` merge on behalf of a
   person and checks that master carries the candidate's tree without being the
   candidate. Then the ``verify`` step of the workflow accepts the merge - its
   merge commit is master's tip and carries the dispatched version - and the
   ``publish`` step rehearses: with publication disabled, the default until
   #1799/#1800 wire their jobs in front of it, it writes no tag and no release.
   Red half: evidence with a missing class, and evidence gathered for another SHA.

``verify-on-master`` (actor: CI)
   The ``publish`` step with publication on, in the one run the workflow
   requires: the annotated tag is pushed at the verified merge commit and the
   GitHub release created for it in the same run, since a ``GITHUB_TOKEN`` push of
   a tag emits no event anything could catch later. The walk then checks what it
   produced: the tag is annotated and stands on master's tip, the release stands
   on the same commit, and the body carries the reviewed changelog section, both
   image digests and the commit itself. The upgrade gate runs again with master's
   migrations, which is the action the lifecycle names for this phase, and
   ``verify`` re-run answers that the release is already published. Red half: a
   master that moved after the reviewed merge, a digest that is not a digest, a
   changelog whose section was never folded, and a prerelease version - each
   refused before a tag was pushed, which the check after them proves by finding
   no tag and no release at all.

``post-release`` (actor: human)
   The master to develop sync opens as the ordinary reviewed pull request it is -
   the mechanism is ``gh pr create``, not the promotion - and stays open for a
   person to merge; the journal proves no issue-closing call was made. The tag the
   promotion pushed is still at master's tip, which is the anchor the planner
   re-anchors its next window on.

The version policy, which needs a released baseline
===================================================

The bump question - patch, minor, major - is decidable only from a released
baseline, and this checkout has none: Q1 of #1578 names ``v0.2.0`` as the first
published tag and #1800 verifies the oldest supported baseline in front of it,
so ``scripts/release_contract_baseline.json`` stays in ``pre-baseline`` mode and the
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
any mechanism here resolves by last-write-wins. The native mechanism owns no
branch, so the race is the tag: the run that wrote the name first owns it, and
the second run is refused as a conflict with the tag standing where the first
published it and the release still the one it created. A re-run of the refused
dispatch refuses too, so retrying cannot smuggle the move through, and the
journal proves the refused run cost no tag and no release.

A prerelease is refused: the walk dispatches ``0.2.0-rc.1`` at the promotion and
``verify`` stops it, because a stable identity is what this mechanism writes and
#1579's prerelease grammar belongs to the planner and to
``scripts/image_release.py``, not to a stable tag; what it never gets is the
stable identity of its line, which the walk proves by finding no tag and no
release at all. The three places that decide a published identity agree on that
without talking to each other: the top-level ``tag_pattern`` of the lifecycle, which the stable channel
of ``master`` publishes under, matches ``vX.Y.Z`` only, the multiversion
whitelist of ``docs/source/conf.py`` excludes the prerelease pattern, and
``release_gates.py`` refuses a prerelease as the ``version`` of a ``released``
contract baseline. Rolling aliases stay refused while no reviewed alias ledger
exists - Q1 of #1578 (ADR-0002) approved the tag shape and no alias - and the
check that asserts it names the missing ledger, so the check that trips when a
reviewed alias decision lands explains itself.

What a dry run cannot decide offline
====================================

The second half of the report, which the acceptance criteria require. Nothing in
it is a hardcoded list: every entry is derived from a constant of the tooling -
``release_gates.REQUIRED_EVIDENCE``, the CI job names of the walk's payload, the
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
       payload through ``release_gates.py promote``'s own ``--evidence`` seam.
     - the CI jobs behind those classes - today ``unit-tests``,
       ``acceptance-tests``, ``sonarcloud`` and ``SonarCloud Code Analysis``,
       the names the walk's payload carries
   * - The built images the attestation binds
     - The digests of ``mrmap-backend`` and ``mrmap-frontend`` are published by
       #1799; well-formed digests pass the workflow's own ``artifacts`` input
       but cannot be pulled here.
     - #1799 (build and promote images by digest)
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

What a run leaves behind
========================

The walk writes nothing outside the temp directory it runs in and removes that
directory on every exit path, including a failed one. The ``isolation`` block of
the report says so in machine-readable form, and these are properties of how the
walk is built rather than promises: the git remote is a local bare repository, so
no ref of this repository can be written by a walk; ``gh`` is the journaling shim,
so no tag, release, pull request or issue can reach GitHub; and no credential is
read, so nothing can be pushed even by an accident in the code. That is also how
the acceptance criterion of #1586 that asks for no production tags, releases or
images during validation is actually met: the walk has no path to them.

The commands, the SHAs and the digests of each step are in ``exercised``, each
step naming the command that produced it, so a run can be re-checked against its
own report instead of against a description of it.

What the promotion still expects of the repository
==================================================

The dry run exercises the tooling; these are the expectations about the
repository itself that the tooling assumes and that an administrator has to keep
true, because nothing in a temp directory can hold them for the real one:

- ``master`` and ``develop`` are permanent branches: never deleted, renamed,
  force-pushed or rebased, as ``AGENTS.md`` states, and only a person merges into
  them. ``publish`` writes a tag and a release onto a master it believes was
  reached by a reviewed merge it did not perform, so the protection of those
  branches - and the branch protection that makes a required check unskippable -
  is part of the promotion's safety, not an unrelated housekeeping rule.
- the promotion workflow is dispatched behind the protected environment
  ``release-stable`` **with required reviewers**. GitHub creates a missing
  environment unprotected, so an administrator has to create it before the first
  run; the lifecycle JSON names the environment and the suites assert that the
  phase carries it, but no offline run can assert that the reviewers exist.
- the tags that ``publish`` pushes, ``v<version>``, are never moved afterwards.
  A re-run reports the tag that stands rather than moving it, which is what the
  walk asserts; on the real repository that behaviour is only useful if nothing
  else moves or deletes the tag either.
- ``publish`` keeps rehearsing - the input defaults to false - until the required
  build and gate jobs of #1799 and #1800 sit in front of it through ``needs`` and
  are green for the exact commit. Flipping the default is the deliberate act, and
  no offline run can assert that the wiring happened.

The version identities the release tools check are ``VERSION``, its projection
``backend/MrMap/version.py``, ``.release-please-manifest.json``, and
``info.version`` of the candidate OpenAPI document. The walk holds the first one
from both sides with ``canonical_version --check`` - green on the untouched base,
red on a hand-edited ``VERSION``, green again once ``--write`` repairs the drift.
The projection and the manifest are compared by ``plan``, which refuses a
candidate whose release files disagree; the suite of #1584 holds that refusal,
while this walk drives ``plan`` on consistent fixtures alone. The api gate
compares ``info.version`` of the document with ``VERSION`` and the walk asserts
that from both sides - the candidate's own document is accepted, a document that
names another version is refused before any report is written. What it cannot
assert is the version a browser shows or the version of the generated
documentation, because those are built by the docs automation of
#1585 and by the frontend build, neither of which runs here; #1610 owns the
combined run over them.

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
