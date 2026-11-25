.. _release-versioning-baseline:

=================================================
Release and versioning baseline (ADR)
=================================================

.. sidebar:: Issue #1578

   Part of epic #1577 (release management), issue #1578: the audit of what the
   repository does today about versions, plus the policy proposal that
   #1579..#1586 build on. The normative calls are asked of a human through
   ``scripts/decisions`` (Q1..Q6 below) and the register is **Pending** while
   they are unanswered. Nothing on this page is approved, and no tag, release
   or workflow was created to write it.

Status of this page
===================

Three kinds of statements are kept apart on purpose:

* **measured** - a command was run against this repository or against the tool
  and its output is quoted. Every number below names what produced it, and
  `Reproducing the measurements`_ gives the commands.
* **proposed** - the page's recommendation, with the reason. Where the
  question is normative (what a standard or a product promise requires) it is
  asked as ``Qn`` and the row says so.
* **not measured** - a gap that is named instead of filled. Release Please's
  release-PR and promotion behaviour cannot be measured without writing to
  GitHub, which this issue forbids; see `What could not be measured`_.

The audit ran on ``origin/develop`` at ``0aeec58d3`` on 2026-11-19, with the
tool measurements of release-please ``17.11.2``.

The baseline, as measured
=========================

Tags and releases
-----------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - question
     - answer
     - how it was answered
   * - Git tags
     - **none** (0)
     - ``git tag -l | wc -l`` after ``git fetch --tags``
   * - GitHub releases
     - **none** (0)
     - ``gh api repos/mrmap-community/mrmap/releases`` returned an empty list
   * - published application images
     - **none**
     - no workflow pushes a runtime image; see `Workflows`_
   * - so what does "0.1.0 released 2023-03-23" mean?
     - a CHANGELOG heading and a Python constant, never a tag, never an
       artifact, never a registry entry
     - ``CHANGELOG.md:120``, ``backend/MrMap/__init__.py:10``

This resolves the "0.1.0 constant vs published versions" part of the scope
statement: there is no published version to reconcile with. The open half of
that sentence - which version to start publishing - is Q1.

Who reads the version today
---------------------------

One constant, four readers. ``backend/MrMap/__init__.py:10-11`` holds
``__version__ = '0.1.0'`` and the ``VERSION`` synonym; everything else imports
it.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - reader
     - path
     - what it does with it
     - is that a contract?
   * - the OpenAPI document
     - ``backend/MrMap/settings.py:26`` -> ``SPECTACULAR_SETTINGS['VERSION']``
       at ``:1178``
     - becomes ``info.version`` of the published json:api schema
     - yes - it is machine-readable output of the API
   * - the system status view
     - ``backend/system/views.py:13,138-139``
     - answers it twice, as ``id`` and as ``mrmap_release``
     - yes - an operator reads it to ask "which build is this"
   * - the schema cache key
     - ``backend/extras/schema_views.py:53,131``
     - ``openapi-document:<version>:<lang>`` inside the ``local-memory`` cache
     - no - internal, but it means a version bump invalidates the cached
       document, so the value is not cosmetic
   * - the Sphinx build
     - ``docs/source/conf.py:26,49``
     - ``release = VERSION``
     - no - but it is what the versioned docs are named after

There is no other version source: ``frontend/package.json`` declares
``"private": true`` and **no version field** (measured: ``version`` is not a
key of the parsed file), and there is no ``setup.py``, no ``backend/pyproject.toml``
and no root ``VERSION`` file. ``backend/MrMap/settings.py:845`` carrying
``"version": 1`` is the ``LOGGING`` dict, not a product version - it is named
here because a grep for "version" finds it and a future audit should not have
to re-derive that.

Docs, changelog, and the tag trap
---------------------------------

* ``CHANGELOG.md`` declares SemVer and Keep a Changelog at ``:5-6``, has
  ``## Unreleased`` at the top and one released heading
  ``## [0.1.0] - 2023-03-23``. The curated unreleased heading deliberately
  has no version or brackets (#1581): the release planner inserts generated
  releases before the first version heading. The unreleased section is long and
  contains breaking changes, which is the material the first real release has
  to curate rather than generate blindly.
* ``docs/source/conf.py:108`` sets ``smv_tag_whitelist = r'^v\d+\.\d+$'``,
  i.e. ``sphinx_multiversion`` would pick up tags shaped like ``v2.1`` and
  **silently ignore** ``v0.2.0``. ``smv_branch_whitelist`` is ``^develop$``
  at ``:109``. Any tag shape with a patch part therefore needs the whitelist
  widened in the same change that publishes the first tag, or the release
  exists in GitHub and in the images and not in the docs. This is Q1's
  option A wording.

Workflows
---------

Measured triggers of all seven workflow files (``awk`` over the ``on:`` block):

.. list-table::
   :header-rows: 1
   :widths: auto

   * - workflow
     - triggers
     - release-relevant behaviour
   * - ``quality-assurance.yml``
     - push, merge queue and PR to ``master`` and ``develop``, weekly schedule
     - the gate every release candidate must already pass; writes nothing
   * - ``codeql.yml``
     - push, merge queue, PR to ``master`` and ``develop``, weekly schedule
     - security scan, no publishing
   * - ``script-tests.yml``
     - push, merge queue, PR
     - the ``scripts/`` suites on a bare runner
   * - ``dev-images.yml``
     - push to ``master`` only, plus merge queue, PR, manual
     - **the only publisher today**: builds and pushes the two dependency
       images, tags ``:<fingerprint>`` always and ``:main`` on ``master``
       (``:108-110``). It is not an application release and is deliberately
       not one.
   * - ``branch-policy.yml``
     - PR to ``master``
     - enforces the permanent-branch rules a release promotion has to respect
   * - ``project-overview-sync.yml``
     - schedule, issue events
     - historical board maintenance; removed by #1593 in favor of native/manual Projects

And nowhere in ``.github/workflows`` does a ``release:`` trigger, a ``tags:``
filter or a ``gh release`` call exist (measured by grepping for them): there is
no release machinery to reuse, only the publishing pattern of
``dev-images.yml`` - log in to ``ghcr.io``, tag on ``master`` - to copy.

Published artifacts and deployment
----------------------------------

* Published: ``ghcr.io/mrmap-community/mrmap-backend-dev`` and
  ``mrmap-frontend-dev``, tagged by dependency fingerprint (contract of #959);
  ``:main`` moves on ``master`` only. These are build dependencies, not
  releases.
* ``docker-compose.yml`` pins every third-party image to an exact version
  (``postgis/postgis:18-3.6-alpine``, ``library/redis:8.10.3-alpine``,
  ``haproxy:3.4-alpine``, ``victoriametrics/victoria-logs:v1.53.0``,
  ``grafana/grafana:13.3.0``, ``dpage/pgadmin4:9.19``, ``mher/flower:2.2``).
* The project's own services - ``backend``, ``celery-worker``, ``celery-beat``,
  ``frontend`` - are ``build:`` sections with no image reference at all, so a
  deployment today is "build from a checkout", not "pull a tagged artifact".
  Turning that into a versioned artifact is #1582; this page only records
  that the baseline has nothing to migrate from.

The history an automated release would read
===========================================

Classification today is the fact that decides whether a tool can compute a
version at all, so it was counted rather than estimated.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - measure
     - value
   * - commits on ``origin/develop``
     - 7585
   * - commits since the ``0.1.0`` changelog date (2023-03-23)
     - 2691
   * - commits whose subject parses as Conventional Commits
     - **53** (0.7 % of all)
   * - same, limited to the last 30 days (1724 commits)
     - 53 (3.1 %)
   * - merge commits titled ``Merge pull request #...``
     - 833
   * - squash-shaped subjects ending in ``(#NNNN)``
     - **0** - the repository merge-merges, it does not squash
   * - merged-PR branch prefixes
     - ``feature`` 180, ``ao`` 170, ``housekeeping`` 87, ``fix`` 66,
       ``renovate`` 47, ``bugfix`` 47, ``docs`` 9, ``refactor`` 7,
       ``bug-fix`` 5, ``jk`` 4, ``improvement`` 4, ``frontend`` 3
   * - commit convention in force
     - ``AGENTS.md``: "short lowercase summaries", e.g. "adds ..."

Two conclusions follow from those numbers, both about the *source* of the
classification (Q3). A branch-prefix rule cannot work as its own source:
``ao`` names a client rather than a change class (170 merges) and
``housekeeping`` means chore and refactor at once (87). And a rule that only
reads commit subjects would find nothing to classify in 99.3 % of the history,
which is not a clean slate but a config decision - see the next section for
what the tool actually does about it.

What the tool does with that history
====================================

Measured against release-please ``17.11.2``, ``DefaultVersioningStrategy``,
starting version ``0.1.0`` - the version the repository claims. The probe
calls the library's own ``parseConventionalCommits`` and ``bump`` and is kept
in ``/tmp/opencode/1578/rp/rules.cjs`` (output: ``rules-out.txt``); a second
probe, ``merges.cjs``, runs the merge shapes this repository really produces.

Version bumps per change class
------------------------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - change class
     - parsed as
     - bump, defaults
     - bump, ``bumpMinorPreMajor``
     - bump, ``bumpPatchForMinorPreMajor``
   * - ``feat:`` (a feature)
     - ``feat``
     - 0.2.0
     - 0.2.0
     - 0.1.1
   * - ``fix:``, ``fix(scope):``, ``fix(security):``
     - ``fix``
     - 0.1.1
     - 0.1.1
     - 0.1.1
   * - ``perf:``, ``refactor:``, ``docs:``, ``test:``, ``chore:``, ``ci:``,
       ``style:``
     - itself
     - 0.1.1
     - 0.1.1
     - 0.1.1
   * - ``build(deps):`` / ``chore(deps):`` (a dependency bump)
     - ``build`` / ``chore``
     - 0.1.1
     - 0.1.1
     - 0.1.1
   * - ``feat!:`` or ``fix!:`` (the breaking marker)
     - ``feat!`` / ``fix!``
     - **1.0.0**
     - 0.2.0
     - **1.0.0**
   * - ``BREAKING CHANGE:`` footer (any type)
     - type + breaking
     - **1.0.0**
     - 0.2.0
     - **1.0.0**
   * - ``Release-As: 0.4.0`` footer
     - forced
     - 0.4.0
     - 0.4.0
     - 0.4.0
   * - ``BEGIN_COMMIT_OVERRIDE`` in the PR body
     - its own header
     - 0.2.0 (feat)
     - 0.2.0 (feat)
     - 0.1.1 (feat)
   * - mixed ``feat`` + ``fix``
     - both
     - 0.2.0 (the max wins)
     - 0.2.0
     - 0.1.1
   * - docs and chores only
     - ``docs``, ``chore``
     - 0.1.1
     - 0.1.1
     - 0.1.1
   * - the repository's own convention ("adds the ...")
     - **nothing** (parse error, logged)
     - 0.1.1 anyway
     - 0.1.1 anyway
     - 0.1.1 anyway

The last row is the one to read twice: a history nothing parses **still
bumps the patch**, because the strategy falls through to patch when it found
neither a feature nor a breaking change. Unconfigured adoption therefore
produces a new application version with an empty changelog. That is the
concrete cost behind Q4, and it is also why "just turn it on" is not a
zero-risk change.

Merge shapes, which is what actually reaches ``master``
-------------------------------------------------------

The subjects of merge commits never parse; the **body** is split and every
conventional header inside it becomes a commit of its own. Measured with the
real subjects from ``git log --merges`` of this repository:

.. list-table::
   :header-rows: 1
   :widths: auto

   * - shape
     - commits release-please sees
     - bump from 0.1.0
   * - ``Merge pull request #1641 from ...`` with a ``feat:`` body
     - 1 (``feat``)
     - 0.2.0
   * - ``Merge pull request #1639 from ...`` with a repo-style body
     - 0
     - 0.1.1 (fallthrough)
   * - ``Merge remote-tracking branch 'origin/develop' into <branch>`` (a sync
       merge)
     - 0
     - 0.1.1 (fallthrough)
   * - ``merge develop into the issue-1481 branch to resolve the changelog
       conflict`` (a stated merge)
     - 0
     - 0.1.1 (fallthrough)
   * - ``Merge branch epic/<name> into develop`` with two conventional bodies
     - 2 (``feat`` + ``fix``)
     - 0.2.0
   * - the same epic merge, repo-style bodies
     - 0
     - 0.1.1 (fallthrough)
   * - ``Merge develop into master`` carrying PR bodies (a promotion merge)
     - 2 (``feat`` + ``fix``)
     - 0.2.0

Three design consequences, each of which the acceptance asks for:

* **Sync and epic merges are harmless to the version number and invisible to
  the changelog.** They contribute no commits, so a develop-with-epic-branches
  workflow (#1588) needs no special case in the release tool. Their content
  still counts, because the individual commits or the PR bodies of that epic
  are in the same window.
* **Instrument one branch, not two.** A promotion merge re-carries the same
  conventional bodies, so running the tool on ``develop`` *and* ``master``
  feeds the same work twice. Measured at the bump level that is harmless
  (the bump is the maximum over the types, so a duplicate cannot raise it),
  which is exactly why the damage would be silent: the changelog would list
  the same change twice while the version stays correct. See `What could not
  be measured`_ for the half that was not measurable.
* **A merge subject is never the classifier.** Since this repository
  merge-merges rather than squash-merges (measured: 0 squash-shaped subjects,
  833 ``Merge pull request`` commits), a rule that reads the PR title only
  works if either merges become squashes or the PR body carries the header.
  Switching the repository to squash-merges is a repository settings change -
  a human act, like branch protection - so #1580 must ask it explicitly
  instead of assuming it. Both routes are measured to work: squash makes the
  title the commit subject, and ``BEGIN_COMMIT_OVERRIDE`` in the body is read
  as its own header.

The classification matrix
=========================

What #1580 has to enforce and #1581 has to compute, per class of change the
acceptance names. "Consumes a version" is the proposal of Q4 option A, not
today's behaviour.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - change class
     - header to write
     - section in the changelog
     - bump (proposed 0.x policy, Q2 A)
     - consumes a version (Q4 A)
   * - feature
     - ``feat:`` / ``feat(scope):``
     - Added
     - MINOR
     - yes
   * - feature that changes a contract
     - ``feat!:`` or ``feat:`` + ``BREAKING CHANGE:``
     - Breaking Changes (mandatory whenever it exists) + Added
     - MINOR while major is 0
     - yes
   * - bug fix
     - ``fix:`` / ``fix(scope):``
     - Fixed
     - PATCH
     - yes
   * - security fix
     - ``fix(security):``
     - Fixed, security named in the line
     - PATCH
     - yes
   * - breaking security fix (an API shape must change to close it)
     - ``fix!:`` + ``BREAKING CHANGE:``
     - Breaking Changes
     - MINOR while major is 0
     - yes
   * - performance work with no behaviour change
     - ``perf:``
     - Changed
     - PATCH
     - yes
   * - refactor with no behaviour change
     - ``refactor:``
     - Changed, or omitted from notes
     - PATCH
     - yes
   * - dependency update
     - ``build(deps):`` or the ``renovate`` branch's PR
     - Dependencies
     - PATCH, MINOR if it drops a supported version
     - yes
   * - documentation only
     - ``docs:``
     - not in the release notes
     - none
     - no
   * - tests only
     - ``test:``
     - not in the release notes
     - none
     - no
   * - CI, tooling, formatting
     - ``ci:``, ``chore:``, ``style:``
     - not in the release notes
     - none
     - no
   * - database migration with a deprecation
     - ``feat:`` or ``fix:`` + a migration note line
     - the migration/deprecation section the curated notes keep
     - as its own type
     - yes
   * - anything else
     - rejected by the PR-title check of #1580
     - -
     - -
     - -

The proposed policy
===================

Each row is the agent recommendation; the last column names what a human has to
answer for it to become policy. The row is not policy while it reads Pending.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - topic
     - proposal
     - decision
   * - start version and tag shape
     - stay 0.x, first real tag ``v0.2.0``, tags ``vMAJOR.MINOR.PATCH``, widen
       ``smv_tag_whitelist`` in the same change; no retro-tagging of 2023
     - Q1, Pending
   * - 0.x breaking knob
     - ``bumpMinorPreMajor=true``: breaking and feature both bump MINOR below
       1.0.0, breaking is read from the mandatory Breaking Changes section
     - Q2, Pending
   * - classification source
     - Conventional header on the PR title, checked in CI; commit messages
       keep the lowercase summary style ``AGENTS.md`` requires
     - Q3, Pending
   * - version churn
     - a release is cut only for ``fix``/``perf``/``feat``/breaking; docs,
       tests, CI, chores do not consume a number
     - Q4, Pending
   * - upgrade window
     - single hop from any earlier release, migrations never squashed,
       deprecations removed two MINORs after they appear
     - Q5, Pending
   * - contract version
     - no second version axis while 0.x; the application version plus the OGC
       version negotiation are the contract
     - Q6, Pending
   * - channels
     - one channel (stable) for the first releases; RC tags only once the
       upgrade window of Q5 exists, because an RC is only useful to somebody
       who can test an upgrade
     - proposed here, asked when Q1 and Q5 are answered
   * - #1180 Release A/B sequencing
     - depends on the window: "the accepted compatibility period" of #1180
       needs the unit Q5 defines before A (transition release) and B
       (removal release) can be dated
     - deferred to #1180 with Q5's answer as input

Release promotion design
========================

The concrete tool, merge and trigger shape. It is a design, not a change that
was run: no workflow file was added, no tag created, no release published.

Where the tool runs
-------------------

* One release line, on ``master`` only. ``develop`` never carries a tag and
  never runs the tool. Measured reason: a promotion merge re-carries the
  commit bodies of what it promotes, so two instrumented branches silently
  double-count into the changelog.
* ``develop`` stays the integration branch it is, with the protection rules
  ``branch-policy.yml`` and the merge queue already enforce. Promotion
  ``develop`` -> ``master`` stays a human act on a permanent branch: no agent
  merges it, and the same merge-gate rules of ``scripts/wip`` apply.
* The release itself is an ordinary PR from the tool's branch into
  ``master``, reviewed and merged by a person. Its merge commit is the object
  the tag points at, so the tag identity is a commit a human approved.
* The tag is what triggers publication (below), so "merged" and "published"
  are two events and a failed publication is retried without a second merge.

Triggers, once this exists (the shape #1584 implements)
-------------------------------------------------------

.. list-table::
   :header-rows: 1
   :widths: auto

   * - event
     - what runs
     - why here
   * - push to the tool's release branch, weekly schedule
     - open or update the release PR against ``master``; it writes the
       version bump, the CHANGELOG head and the release notes
     - the PR is the review artifact: a human reads the notes before the
       version exists
   * - merge of that PR into ``master``
     - ``github-release`` step: create the tag ``v<version>`` on the merge
       commit and the GitHub release with the same notes
     - one writer of tags, and it is the merge, not a cron
   * - ``release`` published / tag created
     - build and push the application images for that exact tag, plus the
       deployment manifest (#1582); build the versioned docs (#1585)
     - the artifact identity is the tag's SHA, so a rebuild is reproducible;
       this is the pattern ``dev-images.yml`` already uses for fingerprints
   * - no eligible commits in the window
     - no PR, no version, no tag; the run says so and ends
     - Q4 option A is the rule that makes this the common case for a
       docs-only window rather than an accident
   * - publication fails after the tag exists
     - delete the tag, fix forward on ``master``, re-run the tag step; a
       published tag is never moved
     - never rewriting a tag is the same rule as never force-pushing a branch
       under review

Frozen candidate identity (what #1584 must expose and #1585/#1586 consume)
--------------------------------------------------------------------------

A release candidate is the tuple ``(sha, version, channel)``, not a branch.
The documentation gate of #1589 is called with that tuple, and #1584 offers
it as a mockable contract so #1585 and #1586 can be built independently -
that is the non-cyclical dependency the epic's coordination section asks for.
Full documentation jobs run only for a frozen candidate and for a stable tag,
never for an ordinary PR.

What could not be measured
==========================

Named as gaps, with the issue that has to close each one. Nothing below was
substituted by an assumption.

* **The release-PR and promotion behaviour of release-please.** ``release-pr``
  and ``github-release`` talk to GitHub; running them here would be a
  production write, which #1578 forbids. release-please ``17.x`` also has no
  ``versioning`` command to compute a bump offline - the CLI's subcommand list
  (measured) offers ``release-pr``, ``github-release``, ``manifest-pr``,
  ``manifest-release``, ``bootstrap``, ``debug-config``. So: the *rules* are
  measured (this page), the *orchestration* is not - which commits the tool
  picks up on a real branch, whether a PR opens for a docs-only window, and
  how the changelog renders a promotion merge. #1581 measures it against a
  throw-away repository, #1586 validates the lifecycle in a dry run.
* **Whether the suppression of docs/chore-only releases is a config knob.**
  Q4 option A is what we want; the exact mechanism in ``release-please`` was
  not probed, and assuming a key that turns out not to suppress the
  fallthrough would ship the churn anyway. #1581 measures it and reports the
  config it verified, or selects an alternative tool - which its scope already
  allows ("select alternative if incompatible").
* **The double-count effect on real release notes.** Feeding one commit twice
  does not raise the version (measured); what it does to the notes of a real
  release PR was not.
* **Any behaviour of a hosted release-please Action against this
  repository's branch protection.** The rules of ``branch-policy.yml``, the
  merge queue and the required checks interact with a bot opening PRs, which
  is only visible by trying it in a fork or scratch repository.

Deliberately not done
=====================

* No history rewrite, no retro-tag, no filter or plugin that hides the 7532
  non-conventional commits. They stay what they are: unparseable input that
  contributes nothing but a fallthrough patch bump, which Q4 is about.
* No workflow, tag, release, registry artifact or branch protection change.
* No change to ``backend/MrMap/__init__.py``. Choosing one canonical version
  source is #1579's own scope and it has to move the constant, not this page.
* No claim that any option below was accepted. The register is the record.

Decision register
=================

Asked on #1578 through ``scripts/decisions``; answers come from an OWNER,
MEMBER or COLLABORATOR account and are verified by the tool. Answering is a
design decision, not the ``agent: approved`` label and not a pull request
review.

.. list-table::
   :header-rows: 1
   :widths: auto

   * - question
     - subject
     - evidence
     - status
   * - Q1
     - initial release version and tag shape
     - 0 tags, 0 releases, ``smv_tag_whitelist`` trap
     - Pending
   * - Q2
     - the breaking-change knob below 1.0.0
     - measured matrix: defaults jump to 1.0.0, the knob gives 0.2.0
     - Pending
   * - Q3
     - where the change type comes from
     - 53 of 7585 commits parse; ``ao`` 170 and ``housekeeping`` 87 prefixes
     - Pending
   * - Q4
     - may docs/chore-only history consume a version
     - measured fallthrough: every class bumps PATCH unconfigured
     - Pending
   * - Q5
     - supported upgrade window
     - #1530's reverse-path failure, the no-squash migration rule
     - Pending
   * - Q6
     - a separate external contract version
     - four version consumers, ``SUPPORTED_CSW_VERSIONS`` already negotiates
     - Pending

Reproducing the measurements
============================

The baseline is host-side git plus ``gh``, read-only:

.. code:: console

    git fetch origin --tags
    git tag -l | wc -l                                             # 0
    gh api repos/mrmap-community/mrmap/releases --jq '.[].tag_name' # empty
    git rev-list --count origin/develop                             # 7585
    git rev-list --count --since=2023-03-23 origin/develop           # 2691
    git log --format='%s' origin/develop \
      | grep -cE '^(feat|fix|chore|docs|refactor|perf|test|build|ci|style|sec|revert)(\([^)]*\))?!?: '
    git log --merges --format='%s' origin/develop \
      | sed -nE 's#^Merge pull request #[0-9]+ from mrmap-community/([a-zA-Z0-9_.-]+)/.*#\1#p' \
      | sort | uniq -c | sort -rn

The tool measurements run against the installed library inside the frontend
dependency image, offline, in a scratch directory:

.. code:: console

    docker run --rm -v /tmp/opencode/1578/rp:/work --entrypoint sh \
      ghcr.io/mrmap-community/mrmap-frontend-dev:7073737f729c \
      -lc 'cd /work && node rules.cjs && node merges.cjs'

``rules.cjs`` walks the change classes through ``parseConventionalCommits``
and ``DefaultVersioningStrategy.bump`` from version ``0.1.0``; ``merges.cjs``
does the same for the merge subjects copied out of this repository's history.
Both write only to stdout.

Follow-up map
=============

.. list-table::
   :header-rows: 1
   :widths: auto

   * - issue
     - takes from this page
   * - #1579 canonical version
     - the four consumers table, and the fact that no second source exists
   * - #1580 classification
     - the classification matrix, the history audit, and the measured fact
       that merge subjects never parse (so squash or body override, decided by
       a person)
   * - #1581 version calculation
     - the measured matrix, the two open mechanism questions in
       `What could not be measured`_, the fallthrough behaviour
   * - #1582 versioned artifacts
     - the ``build:`` services with no image reference, the ``dev-images``
       publish pattern
   * - #1583 compatibility gates
     - Q5's window once answered, and the migration-authoring constraint
   * - #1584 promotion and publication
     - `Release promotion design`_ and the frozen candidate tuple
   * - #1585 docs and runbook
     - the ``smv_tag_whitelist`` fix, the tag-triggered docs build, the gate
       contract
   * - #1586 lifecycle dry run
     - everything under `What could not be measured`_ as its work list
