.. _development-prebuilt-images:


===========================
Prebuilt Development Images
===========================

.. sidebar:: Epic #959

   Build and reuse of these images is automated in
   ``.github/workflows/dev-images.yml``; the Compose layers are
   ``docker-compose.prebuilt.yml`` (backend) and
   ``docker-compose.prebuilt-frontend.yml`` (frontend). The copy-paste agent
   commands live in ``AGENTS.md`` (root, ``backend/``, ``frontend/``); this page
   is the background: which image carries what, how the fingerprint changes,
   what happens when an image cannot be pulled, and what startup actually costs.

Running the test containers no longer requires building their dependency layers
in every checkout. GitHub Actions builds two small dependency images and
publishes them under the org namespace on ``ghcr.io``; an agent worktree
resolves the tag it
needs and starts testing. Source code never enters an image - it stays
bind-mounted - so ordinary code changes never trigger an image rebuild and
never change the tag.

Which images exist
==================

.. list-table::
   :header-rows: 1
   :widths: 22 30 26 22

   * - Image
     - Contains
     - Built from
     - Tag scheme
   * - ``ghcr.io/mrmap-community/mrmap-backend-dev``
     - The Python/GDAL dependency layers of ``docker/backend/alpine.Dockerfile``
       (dev flavor ``MRMAP_PRODUCTION=False``) shared by ``backend``,
       ``django-tests``, ``behave``, ``pre-commit-check`` and the Celery dev
       services.
     - ``docker/backend/alpine.Dockerfile`` with the build args printed by
       ``scripts/dev_image_id.py --print-build-args``
     - ``:<fp>`` immutable, ``:main`` mutable (humans only)
   * - ``ghcr.io/mrmap-community/mrmap-frontend-dev``
     - The result of ``npm ci`` for ``frontend/package-lock.json`` under
       ``/opt/frontend-deps``, plus the seeding bootstrap entrypoint.
     - ``docker/frontend/tests.Dockerfile``
     - ``:<fp>`` immutable, ``:main`` mutable (humans only)

The fingerprint ``<fp>`` is the first 12 hex digits of a SHA-256 over a
canonical manifest of exactly the inputs the image layers depend on - for the
backend the Dockerfile, ``backend/.requirements/*``, the build args and the
resolved ``FROM`` base references; for the frontend ``docker/frontend/tests.Dockerfile``,
the entrypoint script, ``package.json``, ``package-lock.json`` and the resolved
base reference. Generate it with::

    python3 scripts/dev_image_id.py                  # backend fp
    python3 scripts/dev_image_id.py --image frontend # frontend fp

Publishing happens in ``.github/workflows/dev-images.yml``: a pull request
proves the images build (read-only token, no push) whenever there is something
to prove - a fingerprint that is not published yet - and only pushes to
``master`` or a manual workflow dispatch publish the fp tag (and, on
``master``, move the mutable ``:main`` convenience tag). The publish job runs
with ``contents: read`` plus ``packages: write`` - nothing else. The
pull-request side of that trade is ``What CI builds and what it skips`` below.

Agent startup in one block
==========================

Preferred path per root ``AGENTS.md``; the unique project name, the ``.env``
worktree copy and the cleanup ``trap`` from "Docker ownership and cleanup for
parallel agents" still apply unchanged. From the repository root of the job's
checkout::

    export COMPOSE_PROJECT_NAME=mrmap-agent-<issue>-<run-id>

    # backend checks
    export MRMAP_BACKEND_DEV_FP=$(python3 scripts/dev_image_id.py --resolve --image backend --build)
    export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"

    # frontend checks instead (or additionally)
    export MRMAP_FRONTEND_IMAGE_FP=$(python3 scripts/dev_image_id.py --resolve --image frontend --build)
    export MRMAP_FRONTEND_DEV_IMAGE=ghcr.io/mrmap-community/mrmap-frontend-dev:${MRMAP_FRONTEND_IMAGE_FP}
    # + a job-local override resetting the pinned frontend-tests container_name,
    #   see frontend/AGENTS.md for the exact file

    docker compose up -d postgis redis mapserver     # backend checks only
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test tests.django.registry.tests_update_candidates --noinput

``--resolve`` is the whole image-acquisition policy: use a locally present
image whose tag matches this checkout's fingerprint, else pull the pinned tag,
else - with ``--build`` - run the sanctioned local fallback build under the same
immutable tag (see "Image miss and offline" below). Without ``--build`` it
resolves or exits loudly. The fingerprint is a cheap local hash, so re-running
the resolve line on every job start is normal; only a changed fingerprint does
anything.

Reusable image versus disposable project state
==============================================

The separation the agent rules in ``AGENTS.md`` are built on:

* **Reusable, shared, immutable:** the fp-tagged images and their layers. Every
  stack on the host may use them; tearing a stack down never removes them; they
  are never task cleanup. Do not re-tag or overwrite them - the tag name is the
  dependency contract. (``scripts/dev_image_id.py`` verifies the stamp inside a
  local frontend image and refuses a tag that carries foreign content.)
* **Disposable, per-job, isolated:** everything the project name owns - the
  Compose network, the named volumes (database data, ``frontend-node-modules``),
  one-off containers. Two jobs in fp-tagged prebuilt stacks still never share a
  database or a volume, because project scoping is untouched. ``docker compose
  -p <exact-project> down --volumes`` removes exactly this - for your own
  project - and leaves the images and build caches in place. Never use global
  prunes; they destroy other jobs' state and everyone's reusable cache alike.

The ``node_modules`` volume sits deliberately between the two: it is
project-scoped (disposable, isolated) yet seeded from the image, so a fresh
project pays a file copy instead of an ``npm ci``.

What changes an image (and what does not)
=========================================

* A dependency change - an edited ``backend/.requirements/*``, a Dockerfile
  edit, a Renovate bump, a new ``package-lock.json`` - changes the fingerprint.
  The next CI run on the merged branch publishes a new fp tag; meanwhile the
  resolver's ``--build`` fallback builds the new tag locally from the same
  inputs. Old fp tags stay valid for checkouts that still hash to them, so a
  dependency change invalidates exactly the affected image and nothing else.
* A source change (``backend/`` or ``frontend/`` code, tests, feature files)
  is in no manifest: same fp, same image, no rebuild, and the running stack
  picks it up over the bind mount immediately.
* A base image move (the ``FROM`` reference Docker Hub resolves today differs
  from yesterday's) is a fingerprint input on purpose: agents and CI then
  converge on one fp tag instead of silently disagreeing about the base layers.

The frontend bootstrap is lockfile-aware a second time *inside* the container:
the entrypoint compares ``package.json`` + ``package-lock.json`` + ``node -v`` +
``npm -v`` against the fingerprint baked into the image and against the marker
in the project's ``node_modules`` volume. A fresh, matching volume is seeded by
copying from the image; a changed lockfile on a stale image falls back to a
real ``npm ci``. A changed lockfile can therefore never run on stale modules,
and an unchanged one never reinstalls.

GHCR access: anonymous pull, and the current visibility
=======================================================

The image contract assumes **anonymous** pulls - agents carry no registry
credentials. For public GHCR packages that is the default: no ``docker login``
is needed anywhere.

.. note:: measured 2026-11-04
   Both fp tags ARE published - the master push runs are green (``Dev Images``
   reports ``backend-dev-publish`` and ``frontend-dev-publish``, and
   ``docker buildx`` logs the pushed digest, e.g.
   ``ghcr.io/mrmap-community/mrmap-backend-dev@sha256:a23abf3e...`` for fp
   ``09d7b1080a52``) - yet an anonymous token grant for the repositories is
   refused (``docker pull`` -> ``error from registry: unauthorized``, curl
   against the ``/token`` endpoint -> ``UNAUTHORIZED``). That is GHCR's default
   *private* package visibility at first push, not a missing tag. A maintainer
   must flip ``mrmap-community/mrmap-backend-dev`` and
   ``mrmap-frontend-dev`` to public - requested via the question on issue #964.
   Until then, agents simply take the fallback path below, which needs no
   registry at all.

If an org ever keeps dev packages private, an authenticated pull is
``gh auth token | docker login ghcr.io -u <user> --password-stdin`` with a token
carrying ``read:packages`` - but credential-free pulls are the design goal here,
so prefer flipping the package to public.

Image miss and offline behaviour
================================

Both prebuilt Compose files pin ``pull_policy: missing``: a locally present tag
is used without any registry contact; only an absent tag triggers a pull. When
the pull cannot deliver, ``docker compose run`` exits non-zero with the registry
error - never silently substitutes a local build or the mutable ``:main``.

The resolver turns that loud failure into a decision::

    python3 scripts/dev_image_id.py --resolve [--image frontend] [--build] [--dry-run]

.. list-table:: Resolver exit codes
   :header-rows: 1
   :widths: 12 40 48

   * - Code
     - Meaning
     - What to do
   * - 0
     - fp printed, image is locally usable (hit, pull, or ``--build`` fallback)
     - start the stack
   * - 3
     - tag never published ("manifest unknown"/"denied")
     - run with ``--build`` (sanctioned local fallback build under the same tag) or wait for CI
   * - 4
     - transient registry/network failure - or a registry that refuses anonymous inspection, e.g. a private package (measured 2026-11-04: ``unauthorized`` lands here, as "unknown")
     - retry; ``--build`` gets you a working stack now; if the package is private, see GHCR note above
   * - 5
     - platform mismatch (tag exists, not for this OS/arch)
     - ``--build`` is exactly right; report the missing multi-arch publish
   * - 6
     - the local fallback build itself failed
     - fix the build; nothing was tagged
   * - 7
     - a local fp tag carries a *different* stamped fingerprint (foreign content retagged)
     - rebuild under the tag or remove the foreign tag deliberately

``--build`` marks the only sanctioned case in which local content carries the
contract name; the resolver shouts once when it does. The mutable ``:main`` tag
stays off-limits for agents; the single opt-out ``MRMAP_ALLOW_MUTABLE_DEV_IMAGE=1``
exists for humans and makes the resolver warn loudly. Offline works as long as
the image is already local (``pull_policy: missing`` never contacts the
registry for a present tag); offline with the image absent is exit 4.

Deliberately rejected: ``pull_policy: always`` (a registry round-trip per run
for zero extra safety - an immutable tag cannot change under its name) and the
mutable ``:main`` as an agent default (it moves on every master merge).

What CI builds and what it skips
================================

A fingerprint is a hash of exactly the inputs an image is built from, so a pull
request whose fingerprint is already published asks for an image that already
exists, immutably: rebuilding it proves nothing new and the merge queue pays
minutes for it. Since issue #1057 the two validation jobs therefore ask the
registry before they reach for buildx::

    python3 scripts/dev_image_gate.py --image backend    # or --image frontend

The gate wraps the documented resolver probe - ``--resolve``, never ``--build``,
so a validation run neither builds nor pushes - and turns one exit code into one
output, ``needs_build``:

.. list-table:: Gate decision (issue #1057)
   :header-rows: 1
   :widths: 18 16 66

   * - Resolver exit
     - ``needs_build``
     - Why
   * - 0
     - false
     - the fp tag is published and pulled intact; the build would rebuild bytes that are already immutable
   * - 3
     - true
     - never published: this branch changed a dependency input, so this build IS the validation
   * - 4
     - true
     - transient failure, or a private package refusing an anonymous look - "unchanged" and "could not look" are indistinguishable here, so build
   * - 5, 6, 7
     - true
     - the tag exists but its content proves nothing usable here (wrong platform, a failed build, a retagged foreign image)
   * - anything else, or no answer at all
     - true
     - an inconclusive probe is never read as "already built"

The rule is one-sided on purpose: only exit 0 skips. Reading exit 4 - or a
missing docker CLI, or a timeout - as "unchanged" would silently drop a build
that is really needed and let a broken Dockerfile through; the cost of the other
direction is one unnecessary build. On the fresh ``ubuntu-latest`` runner the
gate runs on, exit 0 can only be a registry hit; a self-hosted runner may answer
it from a leftover local tag, which is the same fingerprint and therefore the
same dependency content by construction. The gate also strips
``MRMAP_ALLOW_MUTABLE_DEV_IMAGE``, because under that human opt-out the resolver
exits 0 without ever looking at the registry.

Two properties keep the gate on the safe side of its own required check. It always
exits ``0``, including when the decision itself raises: a failing step reddens
``backend-dev-build``, which would stop every pull request over a script whose only
purpose is to save minutes, so an internal failure is printed as
``needs_build=true`` instead of raised. And the two gated steps ask
``needs_build != 'false'`` rather than ``== 'true'``, so an answer that never
arrived — a crash before the write, an unwritable ``$GITHUB_OUTPUT`` — leaves the
build running. Only a gate that positively answered "published and pulled intact"
may skip work.

Nothing about the two jobs changed - not their names, and not their conditions:
the ``if:`` sits on their buildx and build *steps*, never on the job. So
``backend-dev-build`` and ``frontend-dev-build`` still start for every pull
request and every merge-group run and still post a terminal green status, with
two steps marked skipped and the gate's reason in the log. A required check
never disappears, which is what the merge queue waits for. The publish jobs are
untouched and unconditional, ``packages: write`` stays on them, and a
pull-request run keeps only ``contents: read`` - it cannot publish either way.
While the two GHCR packages are still private (see "GHCR access: anonymous pull,
and the current visibility") the probe answers exit 4 and CI builds exactly as
it did before this gate; the skipping starts with the visibility flip, and an
unchanged run then pays a checkout plus one anonymous pull of the published tag
instead of a build. The Actions build cache is written by runs that build, and
the publish runs on ``master`` still build unconditionally, so a later
dependency change finds the ``master`` cache as warm as before.

``python3 scripts/test_dev_image_gate.py`` checks the decision table, the probe
invocation and the workflow wiring offline - no docker, no network, no ``gh``.

The ``--build`` trap
====================

With a prebuilt file in ``COMPOSE_FILE``, every covered service has its
``build:`` section ``!reset`` - there is nothing left to rebuild. ``docker
compose run --build`` does **not** fail in that situation; it silently keeps the
pinned image (verified against Compose v5). So never combine ``--build`` with
the prebuilt files: it looks like a rebuild, costs nothing, and changes
nothing. Need different image content? Change the inputs (the fingerprint
moves), or take the resolver path. This trap has burned real debugging time;
the header of ``docker-compose.prebuilt.yml`` repeats it.

Manual rebuild path (no prebuilt files)
=======================================

The local flow is byte-identical to the pre-#959 behavior and stays fully
supported - this is also what a machine without registry access runs end to
end::

    export COMPOSE_PROJECT_NAME=mrmap-agent-<issue>-<run-id>
    export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:/tmp/agent-$COMPOSE_PROJECT_NAME.override.yml"
    docker compose build django-tests    # once per checkout; port/container_name resets in the override
    docker compose up -d postgis redis mapserver
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test tests.django.registry.tests_update_candidates --noinput

A project name doubles as the image prefix, so each fresh project gets its own
``<project>-<service>`` tags and the first ``run`` builds what is missing; with
a warm BuildKit cache that is a layer replay, not a rebuild. To share one local
build across several stacks of one checkout, pin the services to a hand-picked
tag in the job-local override (see root ``AGENTS.md``). A locally built image
of the *contract* name is only produced through
``scripts/dev_image_id.py --resolve --build`` (or the plain ``docker build``
command it prints without ``--build``), never by hand-retagging.

Measured startup
================

All rows were measured on 2026-11-04 on the nightly-runner host (20 cores,
94 GB RAM, docker 29.8.2 with Compose v5, BuildKit cache already warm from
prior agent builds of the same content; the GHCR packages were still private,
see the note in "GHCR access", so the rows time the resolver's sanctioned
fallback and the registry's refusals rather than an anonymous download). The
commands are the copy-paste commands above, run as one sequential script with
teardown traps; the host served a few unrelated containers during the run.
``tests_update_candidates`` is the 5-test targeted module of
``backend/AGENTS.md``; the Behave row is the targeted
``json:api/registry/service/wms`` feature run.

.. list-table:: Backend - prebuilt path (fresh project ``mrmap-agent-964-a``)
   :header-rows: 1
   :widths: 46 18 36

   * - Step
     - Wall clock
     - Note
   * - resolve with ``--build``: tag absent, registry refused, sanctioned
       fallback build under the contract tag
     - 1.1 s
     - full warm-cache hit; a cold BuildKit cache pays the ~2.8 GB layer build
       once per host instead
   * - resolve *without* ``--build`` in the same absent state
     - 0.4 s
     - exit 4, raw docker error and the fallbacks printed - failing fast and
       loudly, no silent substitution
   * - deps up (``up -d postgis redis mapserver``)
     - 3.6 s
     - -
   * - targeted Django tests, cold test DB
     - 77.9 s
     - 5 tests, 1.5 s of run time; the rest is container + DB create + migrations
   * - same tests with ``--keepdb``
     - 69.4 s
     - the DB-create share (~8 s) is what repeats skip
   * - ``pre-commit-check`` service (CI gate) on the prebuilt image
     - 29.4 s
     - green; no job-local override needed here either
   * - targeted Behave run
     - 92.2 s
     - 126 scenarios / 681 steps, all green
   * - unscoped ``docker compose pull`` with the pinned tag present
     - 41.3 s
     - spent entirely on Docker Hub base images of *other* services; the pinned
       tag was not touched (no ghcr line at all) - another reason agents should
       just ``run`` instead of pre-pulling
   * - teardown (``down --volumes``)
     - 1.5 s
     - -

.. list-table:: Backend - local-build fallback (fresh project ``mrmap-agent-964-b``, no prebuilt file)
   :header-rows: 1
   :widths: 46 18 36

   * - ``docker compose build django-tests`` (fresh project tag, warm BuildKit)
     - 1.2 s
     - layer replay, not a rebuild - matches AGENTS.md's "about a minute" upper bound
   * - deps up + same targeted tests, cold DB
     - 3.0 s + 73.0 s
     - test time is the same order as the prebuilt path; the image route saves
       no per-test time, it removes per-checkout builds
   * - teardown
     - 1.6 s
     - -

.. list-table:: Frontend - prebuilt path (fresh project, fresh ``node_modules`` volume)
   :header-rows: 1
   :widths: 46 18 36

   * - resolve with ``--build`` fallback build of the dependency image
     - 1.2 s
     - warm cache; on a host without it this is the one real ``npm ci`` of the
       whole story, inside the image build
   * - first run: bootstrap seeds the volume, then ``npm run type-check``
     - 43.1 s
     - "seeding node_modules from image" - the seed share is ~13 s
   * - second run, same project
     - 30.2 s
     - "node_modules volume is up to date" - no install of any kind
   * - ``npm run lint`` in another fresh project (seeds the volume again)
     - 29 s
     - seed + ESLint on a quiet host
   * - ``npm run test -- --run`` (full suite, 1067 tests, 135 files, green)
     - 80 s
     - warm volume, quiet host; the first attempt measured 79.5 s with a single
       5 s vitest timeout in ``MapViewer.spec.tsx`` while the host served
       concurrent work - a load artifact, green on the uncontended re-measure
   * - targeted Vitest run (HarvestingJob specs)
     - 9.6 s
     - -
   * - lockfile changed (``package.json`` edit): bootstrap falls back to a real
       ``npm ci``, then type-check
     - 53.0 s
     - "mounted lockfile ... differs from image ... running npm ci"; ~23 s above
       the warm run - a changed lockfile can never run on stale modules
   * - old default-command path, ``npm ci`` into a fresh volume
     - 24.2 s
     - the per-project cost the seed replaces
   * - old path again with a warm volume (what the service's *default* command
       pays on every start)
     - 27.3 s
     - -

Context numbers from earlier runs of the same wave, for orientation: a plain
``npm ci`` in ``frontend-tests`` costs 24-26 s, seeding the volume from the
prebuilt image 6-12 s, a warm-cache compose image build about a minute, and a
full dependency layer build about 2.8 GB of downloaded layers on a cold
BuildKit cache. This run confirms the ``npm ci`` band (24.2-27.3 s) and the
seed band (~13 s including container start); the two image builds replayed from
the warm cache in ~1 s each.

Two honest caveats. First, the Django figures sit above the "~18 s cold /
~20 s keepdb" figures in ``backend/AGENTS.md`` - unrelated containers shared
the host during the measurement; treat those documented figures as the quiet
host and these as the loaded one, the *relative* picture is what matters:
prebuilt versus local build changes only the per-checkout build step, never
per-test time. Second, **cold pull versus warm pull is reported as behavior,
not as a stopwatch number**: with the fp tag absent, compose pulls the pinned
tag once per host (~307 MB compressed, 1.44 GB unpacked, per ``docker images``)
and any later stack skips the registry entirely (``pull_policy: missing``,
verified - the second project's runs and even an explicit unscoped
``docker compose pull`` made zero ghcr.io requests). The end-to-end anonymous
download timing against ghcr.io could not be measured in this run because the
package visibility was still private; re-measure this row after the package is
public.

Troubleshooting
===============

* ``Error response from daemon: ... unauthorized`` / ``denied`` on pull -
  either the package is not public (see the GHCR note) or the fp tag was never
  published (exit 3 case). Fix: resolver with ``--build``; ask for the publish
  or the visibility flip. Never paper over it with ``:main``.
* ``required variable DJANGO_SECRET_KEY is missing a value`` - the worktree has
  no ``.env`` (it is ignored, not tracked): copy ``.env`` and
  ``docker/backend/.mrmap.env`` from the main checkout first.
* ``User matching query does not exist`` in Behave or unit tests - the run did
  not pass the admin pair the database was migrated with:
  ``-e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap`` before the service name.
* Container name conflict on ``frontend-tests`` - the dev file pins
  ``container_name``; add the one-service override shown in ``frontend/AGENTS.md``.
* ``manifest unknown`` for a fingerprint that should exist - the dependency
  change has not run through CI yet; ``--resolve --build`` builds it locally,
  the fp tag appears on GHCR once the branch is on ``master``.
* A changed ``package-lock.json`` still runs on old modules? It cannot - the
  bootstrap re-seeds or reinstalls - but if you pinned
  ``MRMAP_FRONTEND_IMAGE_FP`` by hand to a stale value, unset it and let the
  resolver print the current one.
* Suspect a retagged image? ``python3 scripts/dev_image_id.py --resolve --image
  frontend`` compares the stamp inside the local image against the fingerprint
  and exits 7 on mismatch.
* Two stacks, one green one red with unrelated DB errors - you are sharing one
  PostgreSQL between two ``django-tests`` runs: that is the one thing fp reuse
  must not do; give every job its own project (root ``AGENTS.md``).
