.. _canonical-version:

===================
Canonical version
===================

One file names the application version. Everything else reads a projection of
it. Issue #1579 established this; the audit that motivated it is
:ref:`release-versioning-baseline` (#1578).

The source
==========

The file ``VERSION`` at the repository root holds one line: the version in
`SemVer 2.0.0 <https://semver.org>`_ exactly as the specification defines it.
Prereleases (``0.2.0-rc.1``) and an exact build revision as build metadata
(``0.2.0-rc.1+9f8e7d6``) are expressible, so a release candidate can name the
commit it was built from inside its own version.

A missing or invalid file is an error, not a fallback: the build that cannot
name its version must fail, and every validator below refuses instead of
inventing a number. The rules are stated three times by necessity (Python,
JavaScript, and the CI sweep) and are checked identical in
``scripts/test_canonical_version.py``.

Changing the version is ``vi`` plus one command:

.. code:: console

    $ echo 0.2.0 > VERSION
    $ python3 scripts/canonical_version.py --write
    canonical_version: wrote backend/MrMap/version.py with 0.2.0

Both files go into the same commit. ``python3 scripts/canonical_version.py
--check`` (run by ``scripts/test_canonical_version.py`` in the script-tests CI
job) is what tells you that you forgot.

The projections
===============

``backend/MrMap/version.py`` - generated
    The backend image ships no application code: every backend container
    receives ``backend/`` as a bind mount of the checkout. A version that must
    reach the installed, containerised runtime therefore has to live inside
    ``backend/`` and must not consult git or the working directory. The
    generator writes the one-line module; ``MrMap/__init__.py`` imports it, so
    the historical names ``MrMap.VERSION`` and ``MrMap.__version__`` keep
    answering and the existing consumers stay untouched:

    * ``MrMap/settings.py`` -> ``SPECTACULAR_SETTINGS['VERSION']`` becomes
      ``info.version`` of the OpenAPI document,
    * the ``local-memory`` schema cache key
      (``extras/schema_views.py``) is versioned, so a bump invalidates the
      cached document,
    * ``/api/system/info`` answers it as ``mrmap_release`` (admin-only,
      #1445),
    * the Sphinx build imports ``MrMap.VERSION`` in ``docs/source/conf.py``
      and names its ``release`` after it.

The frontend bundle - built in
    ``frontend/vite.config.mjs`` reads the canonical file at build time and
    ``define``\\ s it into the bundle as ``import.meta.env.VITE_APP_VERSION``.
    The file is addressed as ``../VERSION`` relative to the config, and each
    flow carries it to exactly that spot: the repository root on a checkout,
    ``/VERSION`` in the nginx compile image (``COPY ./VERSION /VERSION`` of
    ``docker/nginx/nginx.Dockerfile``), ``/opt/mrmap/VERSION`` in the
    ``frontend-tests`` container (bind in ``docker-compose.dev.yml``). A build
    without a valid file throws; there is no ``npm run build`` of an unnamed
    version.

    The builder can additionally stamp the exact revision of the bundle
    through the ``MRMAP_BUILD_REVISION`` build argument
    (``docker-compose.yml`` passes the ``.env`` value into
    ``docker/nginx/nginx.Dockerfile``). An unstamped build reads as
    ``"dev"``.

The About display
=================

The footer shows the frontend's own version - ``AppVersionInfo``
(``frontend/src/components/Layout/``). The backend's answer is already in the
page: the OpenAPI document the schema layer loads carries ``info.version``,
the same canonical value, so no endpoint was added (#1579's "avoid new
endpoints"). The display distinguishes the three states an operator needs to
tell apart:

* both sides equal - one version is named;
* frontend and backend differ - a warning icon appears and the tooltip (and
  the accessible name) quote both sides: the deployment mixes two builds;
* the bundle carries no stamped revision - it is marked as a *development
  revision* instead of pretending to be an exact build.

``frontend/src/components/Layout/appVersion.ts`` holds the rules; its spec
pins them against the real catalogs and the real canonical file.

Guards
======

``scripts/test_canonical_version.py`` (CI job *script-tests*, host Python,
offline) is the sweep that keeps the split honest: the canonical file valid,
the committed projection exactly what the generator writes for it, no literal
version in ``MrMap/__init__.py``, no second ``version`` field in
``frontend/package.json``, the mounts and arguments above still in place, and
the docs still importing ``MrMap.VERSION`` instead of a literal. The frontend
specs pin ``APP_VERSION`` against the canonical file itself, so a bundle and
the file it claims to be built from cannot disagree unnoticed.
