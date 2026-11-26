.. _release-operator-runbook:

========================
Release Operator Runbook
========================

A runbook for the human who operates a MrMap instance across releases: what
a release is in this project, what has to be true before one can arrive,
what happens while it does, and what is in the operator's own hands. Every
step below is taken from committed tooling - the scripts, workflows and
policy documents named as sources - not from aspiration.

The machine-readable form of this lifecycle, consumed by the documentation
automation (#1604) and tested by the interface tests (#1586), is
``scripts/release_lifecycle.json``; ``scripts/test_release_lifecycle.py``
holds that description and this page against the same reality.

Sources
=======

- :ref:`Release planning and the release-please interface <release-planning>`
  - who cuts a version and what the Version Release PR is.
- :ref:`Release promotion and lifecycle automation <release-promotion>` - the
  gate and the promotion dispatch, step by step.
- :ref:`Release compatibility gates <release-compatibility-gates>` - the
  evidence a candidate must carry.
- :ref:`Versioning and upgrade policy <release-versioning-baseline>` - which
  change class moves which version component, and how migrations are rated.
- :ref:`Versioned images <versioned-images>` - the image tags, digests and the
  deployment-manifest overlay.
- :ref:`Canonical version <canonical-version>` - the one place the version
  number lives.

Lifecycle
=========

.. code-block:: text

    develop ── release-please PR ──► merged ──► candidate commit on develop
                                                  │
                                     build & attest images (digests)
                                                  │
                              promotion gates (contract, version, upgrade)
                                                  │
                     "Release promotion" dispatch (environment: release-stable)
                                                  │
        develop -> master release PR ── human merge ──► tag vX.Y.Z on master
                                                  │
                    promote stable tag by digest ──► instance pulls, migrates

1. **Pre-release.** Contributors change code only; nobody bumps versions by
   hand. The canonical version is the root ``VERSION`` file
   (:ref:`canonical version <canonical-version>`); the CI drift gate rejects a
   PR that edits it.
2. **Cut.** When a release is wanted, release-please opens the Version
   Release PR against develop (:ref:`release planning <release-planning>`). A
   human approves and merges it. That merge changes develop and nothing else:
   it produces no ``vX.Y.Z`` tag and does not advance ``master``, which is
   reachable only through the release PR of step 4 (#1798); release notes and
   ``CHANGELOG.md`` are maintained by that PR, never by hand.
3. **Build and promote.** The candidate commit's images are built and their
   digests attested - the commit, not a tag, since the tag of step 4 is what
   the attested digests must still match; the compatibility gates
   (:ref:`release gates <release-compatibility-gates>`) judge the candidate.
   Promotion itself runs by digest through ``scripts/image_release.py
   --promote`` - the tested bytes get the stable tag, never a rebuild - and is
   dispatched manually - see
   :ref:`release promotion <release-promotion>` for the gate's evidence
   requirements. Until a publisher workflow is wired (deliberately open,
   #1581), no tag has attestable digests, so no promotion can pass its gate;
   the first candidate is the ``0.2.0`` cut.
4. **Verify on master.** The promotion step re-runs the version upgrade gate
   against master with the candidate's migrations before anything is called
   stable, and records a machine- and human-readable report as a run
   artifact. A blocked gate pauses the promotion for a human; the step never
   publishes to master, closes issues or advances anything on its own.
5. **Post-release.** The release issue family closes, and the next
   maintenance versions are announced (:ref:`release planning
   <release-planning>`).

Prerequisites
=============

Before the first promotion dispatch, an organisation administrator must
create the ``release-stable`` GitHub environment and give it required
reviewers - the dispatch is gated on that approval and cannot run without it.
The dispatching role needs ``workflow_dispatch`` on the *Release promotion*
workflow and read access to the Actions evidence of the candidate build. The
operator instance needs an image pin of its own (step 3 of *Receiving an
upgrade*) and a current database backup taken with its own backup routine
before the upgrade - no committed tooling backs up an instance; that duty is
the operator's, described under *Backup obligations*.

Receiving an upgrade
====================

An instance upgrades by switching its pinned image references to the new
release, then letting the deployment run the migrations:

1. **Read the release notes first.** The Version Release PR's changelog names
   the breaking-class changes; the upgrade policy
   (:ref:`versioning baseline <release-versioning-baseline>`) states what each
   change class means for you. Only major releases may require manual
   intervention; minor and patch releases are backward compatible, and
   migration reversibility is human-reviewed per migration.
2. **Back up the database** with the operator's own routine (see *Backup
   obligations* below) before pointing at the new version.
3. **Pin the new version.** Follow :ref:`versioned images
   <versioned-images>`: set ``image: <registry>/mrmap-backend:<version>`` and
   ``mrmap-frontend:<version>`` in an overlay. Pin the digest
   (``<version>@sha256:...``) too if the release report provides it; the
   digest is what the promotion attested.
4. **Let the deployment migrate.** The compose deployment runs
   ``python manage.py migrate --noinput`` inside the backend container after
   the new image is up (see the installation guide, :ref:`installation
   <installation>`). Never run migrations against a database that the old
   images are still serving.
5. **Smoke-test.** Log in, open a map and a resource, start an export. The
   promotion run's own report records what the gate checked against the
   candidate.

Backup obligations
==================

The platform's persistent state is the PostgreSQL/PostGIS database (the
``database`` service volume), the media volume and the Redis services. The
documented way to take a consistent database dump from a compose deployment
is a one-shot container against the running database service - the
``database`` service comment in ``docker-compose.yml`` shows the invocation
(``pg_dumpall`` through ``docker compose exec -T``); run it on a schedule the
operator's recovery target requires, and store the dump outside the host.
Media files are ordinary files: back them up with any file-level routine.

Redis carries no durable state that must be restored: the broker queue should
be empty at rest and the result backend is periodically purged (see
:ref:`celery result backend <celery-result-backend>`).

Rollback
========

Rolling back an instance means moving the pinned image references back to the
previous release and redeploying. The limitation is the database: a migration
that has run is only reversible if its reversibility review said so
(:ref:`versioning baseline <release-versioning-baseline>` rates migration
reversibility per class). Therefore:

- Roll back *within* a minor line (``0.2.1`` back to ``0.2.0``) is expected to
  work: no new destructive migrations are allowed to be irreversible
  unnoticed, and the compatibility gates block a destructive or unrated
  migration from reaching a stable tag.
- Rolling back across a migration that rewrote data requires restoring the
  pre-upgrade backup. There is no automatic downgrade; treat the backup as
  the rollback path.
- The stable channel pointer itself is moved forward by promotion only; a
  release is never unpublished. If a stable release must be withdrawn, the
  pointer moves back - instance operators decide for their instance.

Security fixes
==============

There is no standalone security policy document in this repository yet. What
is committed is the classification: a security fix is a ``fix(security):``
commit and moves the patch version
(:ref:`commit classification <commit-classification>`,
:ref:`versioning baseline <release-versioning-baseline>`). A breaking security
fix - one that must change an API shape to close the hole - is a breaking
change and moves the major version. Operators should read release notes of
patch releases for the ``security`` section of the changelog.

Troubleshooting
===============

- **Migrations were not applied after an upgrade.** The deployment runs the
  migrate step inside the backend container; check that step's log
  (:ref:`installation <installation>`). Static assets that look stale after
  an upgrade are the collectstatic case:
  :ref:`collect static <installation-static-assets>`.
- **Background jobs stopped after an upgrade.** A queued task must be
  identical on both sides of the upgrade - check
  :ref:`background jobs <background-jobs>` for the queue layout, and the
  promotion report for the candidate's queue evidence. A clogged result
  backend is cleared per :ref:`celery result backend
  <celery-result-backend>`.
- **The promotion dispatch reports a blocked gate.** The run artifact names
  the missing evidence (contract diff, version gate, upgrade gate or registry
  attestation). Nothing was published; the gate is paused for the operator or
  maintainer who dispatched it - see :ref:`release promotion
  <release-promotion>`.
