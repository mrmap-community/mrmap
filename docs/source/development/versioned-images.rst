Versioned application images
============================

The epic #1577 line: what #1582 turned the four build-only compose services
into, and the rules that keep it true. The dependency images of
``dev-images.yml`` (see :doc:`prebuilt-images`) stay exactly what they are:
build caches named after a dependency fingerprint, never releases. This page
is about the **application artifacts** — the images a deployment pulls.

The inventory
=============

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Image
     - Built by
     - Status after #1582
   * - ``mrmap-backend``
     - last stage ``production-image`` of ``docker/backend/alpine.Dockerfile``
       (code baked to ``/opt/mrmap``)
     - artifact: labels + channel-gated tags
   * - ``mrmap-frontend``
     - ``docker/nginx/nginx.Dockerfile`` (SPA bundle and ``mrmap.conf`` baked)
     - artifact, with the API-address caveat below
   * - dev dependency images
     - ``runtime-image`` stage of the same backend Dockerfile (every dev
       compose service, ``dev-images.yml``, ``dev_image_id.py`` all pin
       ``target: runtime-image``)
     - unchanged: fingerprint-cached build inputs
   * - ``docker/docs/Dockerfile``
     - nothing; it references the removed ``./mrmap/`` layout
     - legacy, untouched

The identity
============

One identity per build, from the two canonical sources of #1579: the strict
SemVer in the root ``VERSION`` and the exact commit. Both images carry it as
OCI labels — ``org.opencontainers.image.version``, ``.revision``, ``.source``,
``.licenses`` (MIT) — plus ``io.github.mrmap.channel``. The backend stage
**refuses to build** an artifact from a missing or invalid ``VERSION`` or a
revision that is not a full 40-hex commit SHA; the frontend refuses a missing
``VERSION`` through vite (the build of #1579). ``latest``, a branch name or
"unknown" appears nowhere in an artifact's self-description.

Tag rules live in exactly one place, ``scripts/image_version.py`` — the
workflows and the docs both link here instead of copying the table:

.. code-block:: text

    channel dev          -> dev-<exact-commit-sha>
    channel prerelease   -> <version> (VERSION carries -rc.N) and dev-<sha>
    channel stable       -> <version>          (immutable)

``--guard`` refuses a tag set that does not match the identity **exactly**: a
dev or prerelease build can never carry a stable-shaped tag, an unapproved
rolling alias is refused for every channel, and ``APPROVED_ROLLING_ALIASES``
in the script is the human decision surface — empty by design, extended only
by a person through a reviewed change, stable channel only. A dev build that
wants a branch name under a personal prefix is the alternative to an alias;
it needs no policy change.

The same tool prints what the builders need so the rules are never
re-implemented: ``--build-args`` for the docker build arguments,
``--labels`` for the OCI labels, ``--manifest`` for the coherent image set,
``--check-deploy`` for the deployment surface, ``--verify-image`` for
reading an image's labels back, ``--digest`` for the registry digest a tag
resolves to, and ``--self-check`` for the offline self-test of every rule.

One build, promoted by digest
=============================

A candidate is built once and its **digest** is what promotion retags:

.. code-block:: console

    $ docker buildx imagetools inspect ghcr.io/mrmap-community/mrmap-backend:dev-<sha>
    Digest: sha256:...
    $ docker buildx imagetools create \
        -t ghcr.io/mrmap-community/mrmap-backend:0.2.0 \
        ghcr.io/mrmap-community/mrmap-backend@sha256:...

A name moves by digest — never by a rebuild of "the same" code, which would
produce different bytes and a different digest. The publish jobs of
``.github/workflows/app-images.yml`` print exactly these commands with the
real digests into the run summary; the **protected promotion** step that
applies them on an approval is #1584, which consumes that workflow through
its ``workflow_call`` inputs. The guard runs before any push job can start,
so a push step can only ever carry tags the identity was checked against.

The frontend caveat
===================

An SPA bundle bakes its API address at build time and a changed address is
expected to rebuild the bundle (#922, #1027, #1036 — the product contract,
not an accident). There is therefore no deployment-neutral frontend artifact:
``app-images.yml`` pushes ``mrmap-frontend`` only when the caller explicitly
names ``frontend_api_base_url`` (dispatch input, or #1584's release flow);
every other run builds it unpushed as a build proof. A deployment with its
own address checks out the exact tag the backend artifact was built from and
runs ``docker compose build frontend`` — same commit, this deployment's
address, the pinned name.

The deployment manifest
=======================

``deploy/docker-compose.images.yml`` plus ``deploy/images.env.example``:

.. code-block:: console

    $ docker compose -f docker-compose.yml \
        -f deploy/docker-compose.images.yml up -d

The four mrmap services share the **one** variable ``MRMAP_IMAGE_TAG`` — an
exact stable, prerelease or ``dev-<sha>`` tag — so the set moves as one
version or it does not deploy. Optional per-repository digest pins
(``MRMAP_BACKEND_IMAGE_DIGEST``, ``MRMAP_FRONTEND_IMAGE_DIGEST``) turn the
pull into an exact-bytes pull. The backend services are pull-only
(``build: !reset null``) and the ``./backend`` → ``/opt/mrmap`` checkout bind
is **gone**: the artifact bakes the code at that path, and a bind mount there
would be the #922 stale-shadow failure relocated — the volume wins, the
image loses, and the deployment silently runs bytes that are not the artifact
it names. The overlay keeps the frontend's build section on purpose (the
address contract above). Third-party images (postgis, redis, haproxy,
victoria-logs, grafana, pgadmin, flower) stay pinned in
``docker-compose.yml``, independent of the artifact set: each moves with its
own CVE or feature decision. Secrets are structurally out: the base file
interpolates them from the operator's ``.env``, and nothing under ``deploy/``
carries one.

``python3 scripts/image_version.py --check-deploy`` enforces all of this
(plus that every third-party reference is pinned); CI runs it and refuses a
deployment file that would let two services run two versions.

Multi-architecture
==================

Not claimed, deliberately. ``release-versioning-baseline.rst`` measured that
nothing in this repository builds multi-arch today, and the CI runners are
linux/amd64; adding ``platforms`` without a builder and a test matrix for the
other architecture publishes images nobody verified. The extension point,
when someone supports more than linux/amd64, is the buildx ``platforms``
input of the publish jobs — the tag and digest discipline above is
arch-agnostic already.

What a Dockerfile change costs the dev cache
============================================

The dependency fingerprint hashes the Dockerfile's bytes, so any change to
``docker/backend/alpine.Dockerfile`` — this issue added a stage — moves the
fingerprint once: every stack misses the published image until CI republishes
on the next master push, and ``--resolve --build`` answers locally meanwhile.
That is the documented mechanism of :doc:`prebuilt-images`, not a defect;
#1583 stops rebuilds for pulls that do not need them.

Testing
=======

- ``python3 scripts/test_image_version.py`` — the offline guard: the rule
  engine's self-check, the repo wiring (targets, labels, the refuse rule,
  workflow push-gating), the live deployment surface, and sabotage cases
  (split tag variable, floating tag, re-added bind mount). No docker, no
  network; run by ``scripts/check_repo_tooling.sh`` and CI.
- Every PR build of ``app-images.yml`` builds both artifacts and verifies
  their OCI labels against the identity it claims (``--verify-image``) —
  the mismatched-versions scenario is tested, not assumed.
- A recipe for a human proof against an isolated registry (nothing
  production-adjacent):

  .. code-block:: console

      $ docker run -d -p 5060:5000 --name iso-reg --label ao.session=$AO_SESSION_ID registry:2
      $ docker build --target production-image -f docker/backend/alpine.Dockerfile \
          -t localhost:5060/mrmap-backend:dev-$(git rev-parse HEAD) \
          --build-args ... $(python3 scripts/image_version.py --build-args) ./backend
      $ docker push localhost:5060/mrmap-backend:dev-$(git rev-parse HEAD)
      $ docker buildx imagetools create -t localhost:5060/mrmap-backend:0.2.0 \
            localhost:5060/mrmap-backend@$(python3 scripts/image_version.py --digest \
            localhost:5060/mrmap-backend:dev-$(git rev-parse HEAD))
      $ docker pull localhost:5060/mrmap-backend:0.2.0
      $ python3 scripts/image_version.py --verify-image \
            localhost:5060/mrmap-backend:0.2.0 --channel stable
      $ docker rm -f iso-reg

  The promoted tag resolves to the same digest the dev tag has; a deliberately
  wrong ``--build-arg`` makes ``--verify-image`` name the exact label.
