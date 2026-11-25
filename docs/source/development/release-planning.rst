.. _release-planning:

================
Release planning
================

Issue #1581 of epic #1577 wires the release planner: `release-please`_ reads the
integration history of ``develop`` and prepares the next version and its
changelog entry as a **pull request against ``develop``, and nothing else**.
Cutting a tag or a GitHub release is the promotion of a reviewed version
(issue #1584) and stays an act of people; the baseline it promotes from is the
one #1578 approved and #1579 made canonical (see
:ref:`release-versioning-baseline` and :ref:`canonical-version`).

The four files that carry this
------------------------------

``release-please-config.json``
    the plan: one root component of release type ``simple``, the canonical
    ``VERSION`` as its ``version-file``, the generated projection
    ``backend/MrMap/version.py`` as an ``extra-file``, the Keep a Changelog
    section table, the window anchor, ``skip-github-release``.
``.release-please-manifest.json``
    the last planned version, keyed ``"."``; it must equal ``VERSION`` (pinned
    by ``scripts/test_release_planning.py``) because #1579 made ``VERSION`` the
    single canonical source, and a release PR is exactly the commit that moves
    ``VERSION`` together with its projections.
``.github/workflows/release-planning.yml``
    the transport only: push to ``develop``, a weekly sweep and a manual
    dispatch. It re-reads the config from the branch, holds no secret, has no
    environment and cannot deploy.
``docs/source/development/release-planning.rst``
    this file: the measurements behind every knob. When a key changes, its
    sentence here and its expectation in
    ``scripts/test_release_planning.py`` change in the same pull request.

How a plan is computed, measured on 17.11.2
--------------------------------------------

All of it was measured against ``release-please@17.11.2``, supplied to the
synthetic replay through ``MRMAP_RELEASE_PLEASE_JS``. The workflow pins
``release-please-action@v5.0.0``, which declares ``release-please@^17.6.0``;
the replay's measured version is independent of the action's bundled version.
The synthetic histories replay the shapes #1578 counted on
``develop``: 7585 commits of which 53 parse, 833 GitHub merge commits whose
whole body is the pull request title, and zero tags and zero releases ever
cut. The replay itself is ``scripts/test_release_planning_synthetic.py``; the
raw matrices below were probed the same way.

The window
    release-please computes each plan from the commits between an anchor and
    the branch tip. With ``skip-github-release`` there is never a GitHub
    release on ``develop`` to anchor on, so the anchor comes from two places,
    in this order:

    1. **While no release has ever been promoted** (today's state): the
       configured ``last-release-sha``, measured as
       ``git rev-list -1 --first-parent --before=2023-03-24 origin/develop``
       → ``e4b59b976f`` ("Update django.po, list_permissions.feature, and 39
       more files..."). Its own commit date is 2023-03-24 09:47+01:00 - one
       day after the changelog baseline of ``0.1.0`` (2023-03-23) - and an
       exact date rule cannot be applied on this history: merge commits carry
       old committer dates (the same walk with an explicit
       ``--before=2023-03-24T00:00:00Z`` lands on a merge whose committer
       date is 2021-07-08), so the filter is quoted exactly rather than a
       rule that would not reproduce. The day of the boundary is
       plan-neutral anyway: the anchor and its neighbours are prose-era 2023
       commits that never parse (#1578: 53 of 7585 parse, the conventional
       era starts years later), so no note and no bump hangs on which
       2023-03-2x commit carries the boundary. Everything merged after the
       anchor is unreleased, which is the baseline's meaning: the first
       planned release collects it all. ``commit-search-depth`` (6000) must
       stay larger than the distance between anchor and tip - the offline
       suite measures the distance on every run and fails when the depth
       stops spanning it, because a window that silently truncates is the
       one failure mode that would drop a change from the changelog forever.
    2. **From the first promoted release on** (after #1584): a plain **git
       tag** - nothing else. Verified: with no GitHub release, the planner
       backfills the release from the tag whose name matches the manifest
       version (``v0.2.0`` for a root component with the default tag
       settings), and the window restarts at that tag's commit. The tag is
       created on the release branch by #1584; what makes it visible to the
       ``develop`` plan is that the tag's commit reaches ``develop`` with the
       ordinary ``master`` → ``develop`` synchronisation the git conventions
       already allow. Until that merge lands, the ``develop`` window replays
       from the old anchor - not a wrong number, but a reason to synchronise
       promptly after a promotion.

    The merged-but-untagged guard: if a release PR is merged on the target
    branch and no tag matches it, the planner refuses to open new release PRs
    ("untagged, merged release PRs outstanding - aborting",
    ``manifest.js::createPullRequests``). Merging the planner's pull request is
    therefore not a stand-alone act: it belongs to the promotion run that
    answers it with a tag. The planner never invents the missing tag itself -
    which is exactly the property #1581 requires of ``develop``.

The parsing
    A commit contributes only what ``conventional-commits-parser`` reads from
    its message. The repository's carriers contribute through the body: the
    merge commit subject never parses, the first body line - the pull request
    title - is split out and parsed, and a footer paragraph travelling in the
    same merge message (``BREAKING CHANGE: ...``, ``Release-As: ...``) parses
    with it. Legacy prose contributes nothing, forever; that history stays
    what #1578 said it is. A pull request's own commits are folded into its
    carrier and contribute notes only through the carrier.

The bump
    ``DefaultVersioningStrategy``, measured from the parse above:

    ======================================  =============  ===========  ======================================
    window                                  default        this config  why
    ======================================  =============  ===========  ======================================
    ``feat``                                0.1.0 → 0.2.0  0.2.0        minor
    ``fix`` / ``perf`` / ``refactor`` /     0.1.1          0.1.1        patch
    hidden-but-parsed types
    ``feat`` + ``fix``                      0.2.0          0.2.0        highest wins
    ``feat!`` or a ``BREAKING CHANGE``      1.0.0          0.2.0        ``bump-minor-pre-major``: below 1.0.0
                                                                        a breaking change is the minor this
                                                                        project promised
    ``docs``/``chore``/… only               0.1.1          -            notes empty → no PR at all
    ======================================  =============  ===========  ======================================

    ``bump-minor-pre-major`` is the ADR recommendation of #1578 (Q2) kept as a
    one-key reversible choice while Q2 stays Pending: without it, the first
    breaking window would jump the pre-1.0 project to ``1.0.0`` - a major
    release nobody planned. ``bump-patch-for-minor-pre-major`` stays off: it
    would also demote ``feat`` to patch.

The notes
    ``changelog-sections`` is the release-facing echo of ``scripts/pr_classify``
    (measured output: ``### Added`` for the feat carrier, ``### Fixed`` for the
    fix carrier, each entry linking its commit - and its pull request, since
    the hosted reader associates the merged pull request with the carrier
    commit through the same query). ``feat``→Added, ``fix``→Fixed,
    ``perf``/``refactor``/``revert``→Changed; the six classes the #1578 matrix
    keeps out of the release notes are ``hidden``. A hidden class still parses:
    a ``chore``-only window *bumps* nothing visible because empty notes mean no
    pull request (strategies/base.js returns no candidate) - verified with the
    ``docs and chore windows prepare nothing`` scenario. This is the Q4A
    suppression, kept reversible the same way as Q2's knob.

What the config must not be read to decide
-------------------------------------------
Prereleases: nothing here produces one; the SemVer grammar of #1579 carries
``-rc.1`` fine and #1584 owns whether a prerelease is ever cut. Q1-Q6 of #1578
stay Pending until a person answers them through ``scripts/decisions``; the two
config knobs that touch them are documented above and one key each away from
the alternative reading.

The found gap: a bang title that only GitHub sees
---------------------------------------------------
Measured, and not fixable from the config: a merge carrier whose title carries
the bang marker (``feat!: ...``) is **not** parsed - release-please 17.11.2
splits the pull-request title out of the merge message with a regex that knows
``type(scope):`` but not ``type!:`` - so a breaking change announced *only* by
a bang in the title contributes neither note nor bump. The repository's own
``PR Classification`` check still reports the bang and the breaking fact on the
pull request, so nothing is lost between people; what the planner needs is the
fact in a place it can read. Three reviewed ways, in order of preference:

* write the breaking fact where the merge message carries it: let the title
  stay ``feat:`` and put ``BREAKING CHANGE: ...`` as the explanatory paragraph
  of the pull request description *into the merge commit message* (GitHub
  shows it there and release-please reads it there - measured: type ``feat!``,
  bump 0.2.0 with this config);
* ``BEGIN_COMMIT_OVERRIDE`` in the pull request description - read from the
  pull request body and measured to parse a bang header (``feat!``);
* the manual dispatch of the workflow, which passes a reviewed explicit
  ``release_as`` - measured to override the computed bump (``0.9.0``).

The synthetic suite pins the gap itself (``a bang title alone prepares nothing
and says so in the log``) so that a future release-please that closes it shows
up as a failing scenario, not as a silent change of behaviour.

Operational notes
------------------
* Checks on the PR the planner opens: GitHub does not run workflows for the
  first push of a pull request created by ``GITHUB_TOKEN``; they run on every
  later push, and reopening triggers them. A reviewer who wants the green
  badge before merging pushes an empty commit or closes and reopens.
* A re-run is a recomputation, not a second pull request: the planner updates
  its own open PR (branch ``release-please--branches--develop``), and the
  concurrency group in the workflow keeps one run at a time against the tip.
* ``release-as`` (dispatch input) is the reviewed override; so are the
  ``Release-As`` footer and ``BEGIN_COMMIT_OVERRIDE`` in a description that
  travels into the merge message. Everything else stays the history's answer.
* Merging the release PR belongs to a promotion run of #1584 (see the guard
  above); an uncoordinated merge freezes the planner with a loud warning
  rather than double-planning.
* When the window distance nears ``commit-search-depth``, raise the key - or,
  better, land the promotion that anchors windows on tags; the offline suite
  fails before a truncation can ever happen.

Running the suites
-------------------
.. code-block:: console

    $ python3 scripts/test_release_planning.py
    # config/manifest/workflow/changelog/projection coherence; offline, stdlib,
    # seconds; part of scripts/check_repo_tooling.sh

    $ npm install --prefix /tmp/rp release-please@17.11.2
    $ MRMAP_RELEASE_PLEASE_JS=/tmp/rp/node_modules/release-please/build/src/bin/release-please.js \
        python3 scripts/test_release_planning_synthetic.py
    # replays the shipped config over synthetic histories: bump arithmetic,
    # suppression, the bang gap, the no-op window, the reviewed override and
    # the post-promotion re-anchor with no repeated note - dry runs against a
    # mock GitHub that answers reads and writes nothing anywhere

Without node or the package the synthetic suite reports SKIP per scenario with
the command that makes it real, like the docker-probing suites of
``scripts/`` before it.

What could not be measured
---------------------------
Two behaviours speak through APIs the offline mock does not carry, and are
recorded from the tool's source instead of from a run: the merged-but-untagged
guard (it reads the pull-request search API) and the pull-request link in a
changelog entry (the local mode used by the dry runs associates pull requests
by regex on the subject and links the commit; the hosted action reads the
association from the same GraphQL query that carries the commit message, so
the entry links the pull request). Both belong to the first real planning run
on ``develop`` as its first observable, and that run is what review of this
issue's pull request prepares.

.. _release-please: https://github.com/googleapis/release-please
