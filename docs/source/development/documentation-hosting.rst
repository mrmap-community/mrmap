.. _docs-hosting:

=====================================
Documentation hosting (Read the Docs)
=====================================


The portal is hosted by Read the Docs, and hosting is **configuration in this
repository plus settings in the Read the Docs project** - there is no publisher
script here, no artifact hand-off, and no ``gh-pages`` branch to keep straight.
That is the decision of #1589 as revised on 2026-11-26: the managed service
already has the version switcher, the per-version storage and the build queue,
and a repository-owned publisher would have had to rebuild all three and then
keep the two publishers agreeing. Section 12 of ADR-0001,
``docs/architecture/decisions/ADR-0001-autonomous-documentation-architecture-and-coverage-contract.md``,
is the record of that correction, and :doc:`documentation-portal` stays the page
about *building* the portal.

What the configuration is
=========================

Everything the service needs to build the site lives in ``.readthedocs.yaml``,
and it is deliberately short.

.. code-block:: yaml

    version: 2
    build:
      os: ubuntu-24.04
      tools:
        python: "3.13"
      jobs:
        pre_build:
          - python -m sphinx -b linkcheck -E --keep-going docs/source _build/linkcheck
    python:
      install:
        - requirements: backend/.requirements/docs.txt
    sphinx:
      builder: html
      configuration: docs/source/conf.py
      fail_on_warning: true

Four things about it are load-bearing rather than taste.

- **One pin file.** ``backend/.requirements/docs.txt`` is the same file the docs
  image and ``.github/workflows/docs.yml`` install, so the hosted site, the
  image and a contributor's venv are three builds of one environment. An
  ``apt_packages:`` entry here would be a second source of a tool and is
  refused for the same reason: nothing in the corpus needs GDAL.
- **The interpreter is the one the pins were frozen with.** The configuration
  before #1597 named ``ubuntu-20.04`` and Python 3.8 while the committed pins
  required Sphinx 8; it could not have built the toolchain it was pointing at,
  which is one reason the contradictory pins survived.
- ``fail_on_warning: true``. CI builds with ``-W --keep-going`` (see
  :ref:`docs-portal-identity` for why it lists every warning instead of
  stopping at the first); the hosted build uses Sphinx's own flag for the same
  rule. A site that publishes a broken cross reference because a warning was
  tolerated is not reviewable.
- **Which revisions exist is not decided here either.** The service keeps its own
  activation list; the ``smv_tag_whitelist`` and ``smv_branch_whitelist`` in
  ``docs/source/conf.py`` are what the *other* consumer - the docs image, which
  calls ``sphinx-multiversion`` directly - honours for the same tags. The two
  lists have to name the same released tags, and only the second one is bound to
  ``scripts/release_lifecycle.json`` and held by
  ``scripts/test_release_lifecycle.py``. A tag the release policy publishes and
  the service has not activated is therefore invisible to a test and visible to
  a reader - which is why activating tags is rule 1 of the checklist below
  rather than an assumption.

Versions, and what builds on what
=================================

The service creates **every** Git tag and branch as an *inactive* version, and an
inactive version has no content and cannot be built. Nothing is public until a
rule or an administrator activates it, which is what makes "publish only what a
release approved" a property of the platform rather than of a script: a branch
cannot leak a page, only an activation can.

Two versions are managed by the service itself and cannot be renamed.

- ``latest`` follows the repository's **default branch**, which is ``develop``.
  That is the version answering ``https://mrmap.readthedocs.io/`` today, so a
  reader at the root is reading *development* documentation.
- ``stable`` tracks the greatest stable semantic version **tag** the repository
  has, with tags taking preference over branches of the same name. The
  repository has no tags yet, which is why ``/en/stable/`` does not exist.

.. list-table::
   :header-rows: 1
   :widths: 18 24 30 28

   * - Version
     - Source
     - How it comes into being
     - Public?
   * - ``stable``
     - the greatest stable SemVer tag, e.g. ``v0.2.0``
     - managed by the service; activated by rule 1 below when the tag appears
     - yes - the site readers should get
   * - ``vX.Y.Z``
     - an approved release tag; the historical two-component ``v0.2`` names
       count as SemVer too
     - rule 1 activates and builds it on the tag push
     - yes - the switcher lists it
   * - ``master``
     - the promotion branch of the #1577 flow
     - no rule activates it; a push there is the promotion of an already
       published tag, whose documentation rule 1 already built
     - no - leave it inactive
   * - ``latest``
     - the default branch, ``develop``
     - exists by default and is the current default version
     - **no** - hide it and set the default version to ``stable``, or readers
       keep landing on development documentation
   * - ``develop``
     - the pull-request branch
     - nothing automatic; build it on demand from the Versions page, or opt in
       with rule 2
     - hidden preview only, if enabled at all
   * - a pull request
     - an open pull request
     - pull-request builds are a separate feature and stay off for ordinary
       traffic
     - no

Because a push to an *active* version builds it automatically, the way ordinary
branch and pull-request traffic stops spending a build is to declare what may
build: as soon as one rule with the **Trigger build for version** action is
enabled, builds are gated by the rules, and an incoming event that matches none
triggers nothing.

.. _docs-hosting-automation-rules:

Automation rules
----------------

Three rules under **Admin → Automation Rules** express the table above. Rules are
evaluated in list order; every matching *version* action runs, but only the
**first** matching *build* rule triggers a build - so a build rule that is meant
to be the gate has to be the only one, and version actions belong above it.

.. list-table::
   :header-rows: 1
   :widths: 8 24 22 46

   * - #
     - Match
     - Type / Action
     - Why
   * - 1
     - **SemVer versions**
     - | Type: ``Tag``
       | Action: **Activate version**
     - The row that publishes a release without a human pressing a button. A tag
       is only reachable after the exact master SHA passed the pre-release
       Sphinx gate (#1798), so activating on the tag cannot publish something
       untested.
   * - 2
     - **Custom match** ``^develop$``
     - | Type: ``Branch``
       | Action: **Hide version**
     - Optional, and off by default. ``Hide version`` activates and builds the
       version but keeps it out of the flyout, which is what "develop preview
       explicit only" means here. Delete the rule to spend nothing on it.
   * - 3
     - **Any version**
     - | Types: ``Tag``, ``Branch``, ``Pull request``
       | Action: **Trigger build for version**
       | Changed files: ``docs/*``, ``docs/**``,
         ``.readthedocs.yaml``, ``backend/.requirements/docs.txt``
     - The gate. With a changed-files filter it builds only when documentation
       actually changed, which is the criterion "ordinary branch and PR events do
       not trigger full builds" stated as configuration.

Set **Default version** to ``stable`` (**Admin → Versions**) once rule 1 has
produced it, and keep **Pre-build version** (Advanced settings) on ``stable``
rather than ``latest``: a release builds its documentation against the
documentation an operator is actually running.

Webhook filters - the changed-files and commit-message conditions of rule 3 -
are only evaluated for a project connected through the **GitHub App
integration**, which is the connection the issue asks to validate; a webhook
from a legacy OAuth integration delivers no file list, so the filter would
silently never match and no rule would ever fire.

Manual setup an administrator has to do
=======================================

None of this is reachable from a pull request, and none of it is scripted here
on purpose - it is a handful of settings in the service's own administration,
and the repository's job is to keep them few and to say what they must be.

#. **Confirm the connection is the GitHub App integration**, not a legacy
   service hook. The project already exists, so nothing re-imports it; this is a
   check, and it is a precondition for the changed-files filter of rule 3 rather
   than a preference - without the App integration no file list is delivered and
   the gate never fires.
#. **Create rule 1** of :ref:`docs-hosting-automation-rules` (SemVer tag →
   Activate version). This is the one rule publication depends on, and nothing
   in the repository can observe it.
#. **Create rule 3**, the changed-files build gate. Leave rule 2 out until a
   candidate preview is actually wanted.
#. **Hide** ``latest`` **and leave** ``master`` **inactive** (**Admin →
   Versions**), so the only public documentation is release documentation.
   ``latest`` is the default version today, so until the next step the root of
   the site serves development documentation.
#. **Set the default version to** ``stable``. This can only be done once a
   SemVer tag exists, which the repository does not have yet: ``VERSION`` is
   ``0.1.0`` and no tag has been cut, so ``/en/stable/`` answers *Documentation
   version not found* and rule 1 has nothing to activate. This is the one step
   that waits for the first release rather than for an administrator.
#. **Add one native redirect**, ``/en/latest/`` to ``/en/stable/`` (**Admin →
   Redirects**). A hidden version is still served to anyone holding a bookmark or
   a link, and a link written before this decision points at development
   documentation; a redirect is a row in the service rather than a rewrite rule
   in a publisher, which is the whole point of not owning one.
#. **Confirm the domain** is ``https://mrmap.readthedocs.io``, the URL the image
   metadata of ``scripts/image_release.py`` already publishes; a rename there and
   here has to be one change, not two.

The first approved release tag is then the first real publication, and it needs
no action from a human beyond the tag itself.

Compatibility of what is already published
------------------------------------------

Two sites answer today, and the measured state of both matters here because the
checklist above is what closes the gap between them.

.. list-table::
   :header-rows: 1
   :widths: 26 40 34

   * - Site
     - Measured state (2026-11-26)
     - Consequence
   * - GitHub Pages
     - ``build_type: legacy``, source branch ``gh-pages``, no custom domain; the
       branch holds ``master/``, ``develop/`` and ``feature/`` directories, each
       a full Sphinx tree, served under
       ``https://mrmap-community.github.io/mrmap/<branch>/<section>/<page>.html``
     - the artifact of the force-push script; still live, and untouched by this
       change
   * - Read the Docs
     - ``https://mrmap.readthedocs.io/`` redirects to ``/en/latest/``, which
       serves a built portal - and ``latest`` follows the **default branch**,
       ``develop``, so the public root is development documentation;
       ``/en/stable/`` answers *Documentation version not found*
     - the project exists and builds, but **no stable version exists yet** - the
       tag that would create it has not been cut, and rules 1 and 3 above are not
       configured

Within a hosted site the corpus keeps its addresses: ``docs/source/index.rst`` is
the root document and no page is renamed or moved by this change, so
``docs/source/development/documentation-portal.rst`` stays
``…/development/documentation-portal.html`` and the ``.. _labels:`` anchors that
links from the README, from issues and from deployed instances point at do not
move.

What *cannot* be configured from this repository is a redirect of the old Pages
URLs: they live on ``github.io``, a different host, and an RTD redirect row only
applies to paths of its own project. So the two shapes differ in host **and**
prefix, and no setting here bridges them. Retiring ``gh-pages`` therefore means
either accepting that URLs written against it stop resolving, or a maintainer
decision to leave a redirect stub on the branch - an act on a live site, and
#1609's to schedule, not this change's. Nothing here deletes a site or a branch;
``gh-pages`` is a published artifact rather than source, and it stays exactly as
it is while this page describes a site that does not depend on it.

Evidence from a non-production check
------------------------------------

What is checkable without touching either site is held by
``scripts/test_docs_build.py``, which asserts this file exists and names the
automation rules, that ``.readthedocs.yaml`` still builds from the one pin file
with ``fail_on_warning``, that no workflow force-pushes a Pages branch, and that
no Pages deployment job has appeared beside the service. Run it with:

.. code-block:: bash

    python3 scripts/test_docs_build.py

The remaining acceptance criteria are visible only in the service, so the
evidence for them is the two HTTP facts in the table above plus the settings an
administrator confirms; they are stated as observed rather than asserted so that
the first release tag (#1609) is the moment they become provable.

What one non-production run of the whole path measured - the gate refusing a
broken candidate, the provenance of the accepted build, and which versions the
service actually serves - is the record of #1610 in
:doc:`documentation-release-rehearsal`, together with what that run could not
observe from a pull request.

What is deliberately absent
===========================

- **A publisher script, an artifact download, an archive layout, a Pages
  workflow.** ``docs/publish_docs.sh`` was a 2021 script that ``git push
  --force``d a build onto ``gh-pages``: it could not say which version or SHA a
  published page came from, it could not reuse a verified build, and a failed
  run replaced good documentation with nothing. Under the revised #1589 a
  repository-owned replacement is not wanted at all - the service provides those
  properties - so the script is deleted with this change and nothing takes its
  place.
- **A dual publisher or a fallback that is also wired up.** If Read the Docs
  cannot serve the minimum needs, the fallback is the *official* GitHub Actions
  artifact upload and Pages deploy actions for the latest stable only, and
  switching to it is an approved change to this page - not a second path that
  runs alongside.
- **Direct Upload as a publishing path.** It stays a possibility for a build of
  a *pre-release gate* artifact and is left disabled until an actual need for it
  exists; naming it here is not wiring it up.
- **A custom build for the multiversion matrix.** Read the Docs calls Sphinx
  itself; the historical versions come from the activated tags. The docs image
  at ``docker/docs/entrypoint.sh`` is a separate consumer and keeps calling
  ``sphinx-multiversion`` directly, which is what it exists for.
- **Publishing from this change.** Nothing here is live. What is checkable from
  the repository is held by ``scripts/test_docs_build.py``; what is only visible
  in the service is the checklist above, and the first release tag is the first
  publication (#1609 owns that step).
