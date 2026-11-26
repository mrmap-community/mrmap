.. _versioned-images:

=================
Versioned images
=================

What a released MrMap *is* as an artifact: two image names, one tag per version,
labels that name the commit, and a manifest that pins a deployment to the bytes
that were tested. Issue #1582 of epic #1577 added this; the version these names
carry is the canonical file of :ref:`canonical-version` (#1579), and the audit of
what a release policy has to decide is
:ref:`release-versioning-baseline` (#1578).

One tool holds all of it, because every one of these facts is a second place to
compute a value that somebody else could compute differently:

.. code:: console

    $ python3 scripts/image_release.py --inventory

Host Python, standard library only. It builds and pushes only what it is
explicitly told to build, and only to the registry named on the command line.
**One workflow calls it today**: ``.github/workflows/candidate-images.yml``
(:ref:`release-candidate-images`, #1799) builds and publishes the *candidate* tags
of one dispatched, reviewed commit and writes the digest evidence the promotion
consumes. It still writes no version tag - ``--promote`` does that, from the
protected promotion dispatch, and nothing else can. See `Not wired on purpose`_.

The inventory
=============

Two Dockerfiles build everything a production MrMap runs on:

.. list-table::
   :header-rows: 1
   :widths: 12 34 26 28

   * - image
     - built from
     - serves (``docker-compose.yml``)
     - published today
   * - ``backend``
     - ``docker/backend/alpine.Dockerfile``, context ``./backend``
     - ``backend``, ``celery-worker``, ``celery-beat``
     - no - no ``image:`` reference exists
   * - ``frontend``
     - ``docker/nginx/nginx.Dockerfile``, context ``./``
     - ``frontend``
     - no - no ``image:`` reference exists

Three services, one backend image: the worker and the beat differ only by
command, so a release must never run them from different builds. Neither service
had an ``image:`` line before this issue, which is what #1578 measured as "a
deployment is a checkout, not a version": the deployment manifest below is what
changes that.

Left alone on purpose
    ``mrmap-backend-dev`` and ``mrmap-frontend-dev`` are the *dependency* images
    of epic #959 - tagged by dependency fingerprint, published by
    ``dev-images.yml``, resolved by ``scripts/dev_image_id.py``. They carry test
    tooling (``django-tests``, ``behave``, ``pre-commit-check``, the
    ``frontend-tests`` node modules), not the application, and a release build
    must not disturb the prebuilt cache every agent stack resolves through. That
    contract, its tags and its workflow are untouched here.

    ``postgis``, ``redis``, ``haproxy``, ``victoria-logs``, ``grafana``,
    ``pgadmin4`` and ``flower`` are pinned to exact versions in
    ``docker-compose.yml`` and are versioned by their upstream and Renovate. A
    release manifest never writes them: a second place to change one is a second
    way to be wrong. ``--check-manifest`` reads those pins in order to refuse a
    manifest that overrode one unnoticed.

Names and tags
==============

The version always comes from ``VERSION`` through ``canonical_version.py``; the
kind of build says what may be written under it:

.. list-table::
   :header-rows: 1
   :widths: 14 22 64

   * - ``--kind``
     - tag of ``0.2.0``
     - properties
   * - ``stable``
     - ``mrmap-backend:0.2.0``
     - immutable. Once a registry serves this tag for a digest, ``image_release``
       refuses to point it at any other content; there is no ``--force``.
   * - ``prerelease``
     - ``mrmap-backend:0.2.0-rc.1``
     - immutable too, and never allowed to move a stable alias.
   * - ``dev``
     - ``mrmap-backend:dev-<12 hex of the commit>``
     - movable: a dev revision is not a product. It can never carry an alias,
       which is the whole "dev and RC must not overwrite stable" rule in one
       line.
   * - ``candidate``
     - ``mrmap-backend:candidate-<12 hex of the commit>``
     - the tag ``.github/workflows/candidate-images.yml`` publishes for one
       dispatched, reviewed commit (#1799). Named by its commit like a dev build -
       it is a build of a revision, not yet a release - but kept out of the
       ``dev-`` namespace so a candidate is never mistaken for the movable build
       of a branch, and refused every alias for the same reason. See
       :ref:`release-candidate-images`.

Build metadata is dropped from the tag and kept in the labels. ``0.1.0+9f8e7d6``
is a valid SemVer version, but the distribution reference grammar allows
``[a-zA-Z0-9_.-]`` in a tag - a ``+`` would fail the push with a message about
invalid characters. So the tag is ``0.1.0`` and
``org.opencontainers.image.version`` carries the full ``0.1.0+9f8e7d6``, which is
where an exact build is identified anyway.

Rolling aliases are opt-in and default to none:

.. code:: console

    $ python3 scripts/image_release.py --promote --alias latest

``latest``, ``stable``, ``main`` and ``prod`` are the aliases that promise "the
current release". A dev build may not write any alias and a prerelease may not
write one of those: an upgrade candidate must not become what an operator pulls
by default. Q1 of #1578 fixed the tag shape and approved no rolling alias
(ADR-0002), so the default is that it does not; publishing one would be its own
reviewed decision.

Labels
======

Every build carries:

* ``org.opencontainers.image.title`` - which of the two images it is,
* ``org.opencontainers.image.version`` - the canonical version, metadata included,
* ``org.opencontainers.image.revision`` - the full commit SHA,
* ``org.opencontainers.image.source`` and ``.documentation``,
* ``io.github.mrmap.dependency-fingerprint`` - **backend image only**: the
  fingerprint ``dev_image_id.py`` computes for that same Dockerfile and
  requirement set, so a runtime image names the dependency layers it stands on.

Two deliberate absences. The frontend image carries no dependency fingerprint,
because #962's frontend manifest describes ``docker/frontend/tests.Dockerfile``
and not the nginx image - a label claiming a fingerprint of a different input set
is worse than no label. And the build timestamp is not the wall clock: ``--build``
exports ``SOURCE_DATE_EPOCH`` of the commit, so two builders of one commit get one
digest, which is what makes "promote the bytes that were tested" mean the same
thing on two machines.

Multi-arch is not offered. Nothing in this repository passes ``--platform``
today, so both images are of the builder's own platform; advertising
``linux/arm64`` would publish a promise nothing tests. The tag and manifest
shapes do not block adding it later.

Build once, promote the tested digest
=====================================

A release is two steps, and the second one runs no compiler:

.. code:: console

    $ python3 scripts/image_release.py --build --push --kind dev
    $ python3 scripts/image_release.py --promote --kind stable \
        --digest backend=sha256:... --digest frontend=sha256:...

``--promote`` creates the version tag registry-side from the **digest** with
``docker buildx imagetools create``, so no compiler runs again and the content
cannot differ from the one that was tested. It is idempotent, and aiming it at a
tag that already holds other content is refused - there is no ``--force``.

What "the same content" means had to be measured, because the two digests involved
are not equal:

.. code:: console

    $ python3 scripts/image_release.py --promote --kind stable --digest backend=$CAND
    image_release: promoted: .../mrmap-backend:0.1.0
    $ python3 scripts/image_release.py --promote --kind stable --digest backend=$CAND
    image_release: already promoted: .../mrmap-backend:0.1.0

``docker buildx build`` pushes a bare ``application/vnd.oci.image.manifest.v1+json``
while ``imagetools create`` copies those same bytes into a new
``...image.index.v1+json`` around them, so the released tag carries a **different
digest for identical content** - measured in an isolated registry: candidate
``0d24dce2…`` became index ``da504ede…``, whose only child is ``0d24dce2…``. A
promotion comparing manifest digests would therefore report its own second run as
a conflicting release. Identity here is the **set of child manifests**, falling
back to the manifest digest for a bare image manifest: the same image, whichever
wrapper a publisher happened to choose.

The deployment manifest
=======================

.. code:: console

    $ python3 scripts/image_release.py --manifest mrmap-0.2.0.yml --kind stable

which resolves each release tag in the registry and pins the digest it answers -
the digest an operator will actually pull - and writes an overlay in the shape
``docker-compose.prebuilt.yml`` established:

.. code:: yaml

      backend:
        image: ghcr.io/mrmap-community/mrmap-backend:0.2.0@sha256:...
        build: !reset null

and an operator runs:

.. code:: console

    $ docker compose -f docker-compose.yml -f mrmap-0.2.0.yml up -d

``build: !reset null`` is what makes "pinned" true rather than likely: with a
build section left in place, a compose run that cannot pull silently builds from
whatever checkout the host happens to have - which, before this manifest existed,
was the whole deployment story of MrMap. Compose itself confirms the semantics;
the suite asks it (see `Guards`_).

Checking one is a command, not a review:

.. code:: console

    $ python3 scripts/image_release.py --check-manifest mrmap-0.2.0.yml \
        --verify --version 0.2.0
    image_release: mrmap-0.2.0.yml is coherent for 0.2.0 and every pinned
    artifact confirms its own version

It refuses a service left unpinned (it would keep building from a checkout), two
versions in one manifest, a foreign repository, a reference without a digest, a
live ``build:`` section, an overridden third-party pin and a credential-shaped
value.

``--verify`` then asks the registry, without pulling anything, two questions that
fail differently - and asks them of two separate references:

* resolving ``repo:0.2.0`` answers *is this still what was released*, which is how
  a moved, republished or raced tag is caught;
* resolving ``repo@sha256:…`` and reading its ``org.opencontainers.image.version``
  label answers *are these the bytes of this release*.

Asking the combined ``repo:0.2.0@sha256:…`` form would ask neither: measured in an
isolated registry, a distribution resolves that reference **by the digest and
ignores the tag**, so a digest comparison against it compares a value with itself
and always passes. That is the check this page documented before it was measured,
and the suite now pins both questions by name.

The label question is the one nothing else can answer. A promotion cannot see that
it was handed the previous release's bytes; a manifest cannot see that its tag was
moved; and one hand-edited line is a backend and its worker on two versions
against one database. The artifact's own label is the answer that comes from the
bytes rather than from the file being checked.

Not wired on purpose
=====================

* **No automatic publication of a version tag.** #1582's scope said the publisher
  stays unwired, and #1799 wired the half of it that needs no approval: the
  candidate build. ``.github/workflows/candidate-images.yml``
  (:ref:`release-candidate-images`) publishes candidate tags for one dispatched,
  reviewed commit and cannot write a version tag - the tag is created only by
  ``--promote``, from the protected ``release-promotion.yml`` dispatch behind
  ``release-stable``, where a person approves. The trigger design belongs to
  #1581/#1586. Q1 (start version and tag shape) and Q4 (a docs-only window
  consumes no version) of #1578 are answered policy now (ADR-0002), and a
  recorded answer publishes nothing by itself: the readiness gates #1798..#1801
  and #1610 stand between this tool and a first tag. What is here is everything a
  workflow would need to *decide*: names, tags, labels, the immutability rule,
  the manifest.
* **Rolling aliases exist as an option, not as a default**, for the same reason:
  Q1 approved no alias, and a candidate build refuses them outright.
* ``docker/docs/Dockerfile`` builds nothing and pulls nothing: no compose file,
  workflow or script names it (Read the Docs builds the docs through
  ``.readthedocs.yaml``). It is left in place and named here, because an
  inventory that silently drops a first-party Dockerfile is how the next audit
  starts over.
* **Multi-arch**, as above: not supported by any build path today.

Guards
======

``scripts/test_image_release.py`` (117 checks, host Python, offline, run by
``scripts/check_repo_tooling.sh`` in the *script-tests* CI job) pins the policy
and the refusals: build metadata never becomes a tag, a dev build never gets an
alias, a prerelease never moves ``latest``, the fingerprint label is on the
backend image and not on the frontend one, the frontend build refuses to run
without its API address, and every manifest failure above is refused by name.

Two of its checks are not offline and say so out loud when they skip. One reads
the live ``docker-compose.yml`` and asserts the inventory matches its ``build:``
sections **in both directions** - a service added later cannot quietly miss a
release. The other asks Compose, where docker is present, to render
``docker-compose.yml`` plus a generated manifest and asserts that the four
services come back with the pinned image and **no** ``build:`` section: the whole
overlay rests on that merge behaviour, so it is tested against the thing it
describes rather than asserted in a comment.

The registry-facing rules are held with the module's registry doors stubbed, so
they need no registry to run: re-promoting identical content reports ``already
promoted`` (which is the index re-wrap above, not a digest match), another image's
content under a released tag is refused, an unpublished digest cannot be tagged at
all, a prerelease and a dev build cannot promote their way onto a stable alias -
and each of the two ``--verify`` questions has its own failure pinned, including
the moved tag the combined reference would have waved through.

The end to end proof - two real images built, published to an isolated registry,
promoted, verified, and both refusals fired against real registry answers - is
recorded on #1582.
