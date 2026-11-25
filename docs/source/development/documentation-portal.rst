.. _development-documentation-portal:


====================
Documentation portal
====================

.. sidebar:: Issue #1597 (epic #1589)

   The build is ``.github/workflows/docs.yml``, the offline checks are
   ``scripts/test_docs_build.py``, the generated section is
   ``scripts/gen_docs_design.py``. This page is the background: what one build
   produces, how to run it, what it refuses, and which part of it is generated
   rather than written.

The documentation is one Sphinx project with one theme and one navigation tree,
covering the five sections the issue names - user, administration, developer, API
reference and release notes - over the corpus that already existed. Nothing about
a page's URL changed: ``usage/index.html``, ``installation/index.html``,
``development/index.html`` and the rest keep the addresses links from the README,
from issues and from deployed instances already point at. What changed is that the
sections are now grouped by audience, registered in a toctree, and built on every
pull request.

Publishing is not part of this issue. There is no deployment here, no artifact
pushed anywhere, and no gh-pages branch written; the portal is built, checked and
uploaded as a reviewable artifact and nothing more.

Building it
===========

The build needs one file and no application:

.. code-block:: bash

    python3 -m venv /tmp/docsenv
    /tmp/docsenv/bin/python -m pip install -r backend/.requirements/docs.txt
    /tmp/docsenv/bin/python -m sphinx -b html -E -W --keep-going \
        -d /tmp/doctrees docs/source docs/build/html

or, equivalently, ``make -C docs html`` for a build that reports rather than
refuses. ``backend/.requirements/docs.txt`` is the whole toolchain, transitive
dependencies included; there is no second source of Sphinx in the repository. The
previous pin set was internally contradictory - Sphinx 4.5 beside
sphinxcontrib-* 2.x, which require Sphinx >= 5.0 - and aborted in about a second,
which nobody saw because no job built the documentation on an ordinary change.

Three facts about that environment are deliberate and worth keeping:

- **It installs nothing of the application.** No Django, no GDAL, no database
  client. ``docs/source/conf.py`` reads the version and otherwise does not import
  the backend, which is what lets the docs image, the Read the Docs build and a
  contributor's venv be three builds of one environment.
- **It is offline.** No renderer is fetched over the network during a build. See
  :ref:`docs-portal-diagrams`.
- **It is pinned, transitively.** The ADR-0001 gate V-11 is "the committed pins
  build"; an unpinned transitive upgrade cannot move under a pinned Sphinx again.

Strictness
==========

``-W`` turns every warning into a failure, and ``--keep-going`` lists all of them
instead of stopping at the first. That is the difference between a documentation
build that publishes quietly broken pages and one that says so. The classes of
fault it catches, all of which were reproduced while this issue was implemented:

.. list-table::
   :header-rows: 1
   :widths: 40 32 28

   * - Fault
     - Without ``-W``
     - Caught by
   * - A page no toctree leads to
     - builds and publishes, unreachable
     - the build, and the suite
   * - An ``{include}`` whose file is not there
     - a *file not found* line in the log and an empty page
     - the build, and the suite
   * - An RST ``.. toctree::`` inside a ``.md`` file
     - a paragraph where the navigation should be
     - the suite
   * - A ``:ref:`` to a label nobody defines
     - the reference renders as its text
     - the build, and the suite
   * - An image the build cannot find
     - a warning in the log
     - the build

``scripts/test_docs_build.py`` runs the same structural questions without Sphinx,
in milliseconds and without the docs environment, so a pull request is refused
before a build is scheduled. It also holds the generated pages against their
generator: a hand-edited generated page fails, which is the point - see
:ref:`docs-portal-generated`.

.. _docs-portal-layout:

Layout and audiences
====================

``docs/source/index.rst`` carries one toctree per audience. The audiences are not
invented for the documentation: cataloguer, administrator, integrator, developer
and operator are the permission classes and endpoint groups already in the code,
which is what keeps the navigation from drifting away from the product.

A page belongs to exactly one section. Listing a page twice is not a way to make
it discoverable in two places - Sphinx picks one parent and the navigation a
reader sees then depends on dictionary order. The autodoc indexes
(:ref:`models`, :ref:`managers`, :ref:`modules`) hang off :ref:`api-reference`,
the page that explains why their content depends on the build, rather than
appearing beside it.

``orphan_warnings`` is not relied on; the suite walks the toctrees itself, because
an orphan is silent otherwise. That is how the eight design notes under ``docs/``
stayed invisible for the whole life of the corpus - built, published, linked from
no navigation - while the README quoted them as authority.

.. _docs-portal-dialect:

Two dialects, one rule
======================

Markdown and reStructuredText are both source formats (``source_suffix``), and
which one a page is written in is decided by what it needs: prose authored by
people who file issues in Markdown stays Markdown, pages that need
``list-table``, ``code-block`` and the autodoc roles stay RST.

One rule decides the syntax of a *directive*, and it is the file's suffix:

.. code-block:: markdown

    ```{toctree}
    :maxdepth: 2

    architecture
    ```

.. code-block:: rest

    .. toctree::
       :maxdepth: 2

       architecture

A MyST fence carries its target on the fence line and its entries flush left. The
indentation the RST form requires is part of the
document name inside a fenced block, so an indented entry resolves to nothing and
the section publishes with an empty navigation. Both mistakes are checked, in both
directions, by the suite.

.. _docs-portal-corpus:

The authored corpus under ``docs/``
===================================

The design notes, the architecture decision records and the screenshot manifests
live under ``docs/`` rather than in ``docs/source/``, and stay there:
``AGENTS.md``, the README and the project skills quote those paths, and the notes
are historical sources the portal *consumes* rather than pages it owns.

They reach the portal through generated pages that ``{include}`` them, with
``:relative-docs:`` and ``:relative-images:`` so their internal links and
screenshots keep working from their new location. A note is included exactly once -
the suite counts - and the include target is resolved before the build, because a
MyST include one directory level off is reported as *file not found* while still
writing a page, and a reader sees a heading with nothing under it.

.. _docs-portal-generated:

What is generated
=================

``scripts/gen_docs_design.py`` writes the design section, the decision-record
index, the image manifests and the release-notes page:

.. code-block:: bash

    python3 scripts/gen_docs_design.py

The generated pages are committed, the way ``backend/MrMap/version.py`` is: a
reader of a pull request sees the page a reviewer would otherwise have to build to
read, and the suite fails the moment the committed page and the generator disagree.
Edit the generator, never the output. If a generated page needs different prose,
the prose belongs in the source note it includes.

.. _docs-portal-references:

Cross-references
================

Labels are written explicitly - ``.. _development-prebuilt-images:`` rather than
generated from a section title - for two reasons: renaming a heading does not
break the dozen pages that point at it, and a reference to a label that was never
written is a fault the suite can name before a reader finds it.

``autosectionlabel_prefix_document`` means two sections may both have a section
called "Configuration" without one shadowing the other.

.. _docs-portal-diagrams:

Diagrams
========

``mrmap_docs`` (``docs/source/_ext/mrmap_docs.py``) owns both diagram families, and
its default is the one that is safe on a laptop and in CI: **static**. A ``mermaid``
or ``graphviz`` block renders as a visible, labelled block carrying its own source.
It is honest - the reader sees exactly what the diagram says - and it needs no
renderer, so a build cannot reach the network for one.

``MRMAP_DOCS_DIAGRAMS=render`` asks for real rendering. Graphviz then uses ``dot``;
mermaid uses ``sphinxcontrib.mermaid`` against a **vendored** copy of the renderer
named by ``MRMAP_DOCS_MERMAID_JS``. Without that file the build fails rather than
fetching one, which is what keeps the offline promise checkable rather than
aspirational.

A diagram that neither renders nor degrades is a warning, and ``-W`` makes a
warning a failure.

.. _docs-portal-autodoc:

What autodoc may claim
======================

A portal build runs without the application importable - no database, no GDAL, no
``import django``. Under ``MRMAP_DOCS_AUTODOC=auto`` (the default) a module that
cannot be imported produces a placeholder that *names the module* and says its
reference was not generated, instead of an empty section a reader might mistake for
"there is nothing here".

.. code-block:: bash

    MRMAP_DOCS_AUTODOC=on  # a module that cannot be imported is a build error

This strict mode is available for a build environment that can import the
application; the docs image and Read the Docs currently use the default
``auto`` mode. A green build under ``on`` is evidence the reference really was
generated. The page itself tells the reader which of the two it is looking at.

.. _docs-portal-identity:

Build identity
==============

Every HTML build writes ``provenance.json`` beside its output:

.. code-block:: json

    {
      "schema": "mrmap.docs.provenance.v1",
      "project": "MrMap",
      "version": "0.1.0",
      "builder": "html",
      "documented_commit": "ed59757495c704464ef452ed359edd629fe28579",
      "toolchain": {"sphinx": "8.2.3", "myst-parser": "4.0.1"},
      "source_digest": "sha256:97aba388...",
      "autodoc": "placeholders:django-not-installed",
      "diagrams": "static",
      "pages": 81
    }

An artifact that cannot say what it was built from cannot be reviewed, and an
operator reading a page about their own deployment is entitled to know which
commit answered. ``.github/workflows/docs.yml`` asserts the file exists and is
complete, so an identity that stopped being written is a red build rather than a
missing field. ``SOURCE_DATE_EPOCH`` is honoured, so two builders of one commit get
one artifact.

Version and language navigation
===============================

``sphinx-multiversion`` documents the released tags - the two-component names the
repository published before the SemVer policy (``v0.2``) and the full names
promotion creates today (``v0.2.0``) - with ``develop`` as the branch build. The
selection is bound to ``scripts/release_lifecycle.json`` rather than to a regex
somebody has to remember to update; ``scripts/test_release_lifecycle.py`` holds it.

The release string in the sidebar comes from the canonical ``VERSION`` file through
the surface #1579 designates, so a bump reaches this consumer with the other three.
When the application is not importable it comes from the same file the projection is
generated from, and ``provenance.json`` records which of the two named it - the same
value either way, and a reader of the artifact can tell how it was obtained.

Links
=====

``linkcheck`` runs on every pull request and is reported rather than gated: a
broken upstream URL is real information for whoever owns the page, and it is not a
reason to refuse a pull request that never touched it. It is gated in
``docker/docs/entrypoint.sh``, where the whole corpus is checked as a deployment
condition.

localhost and 127.0.0.1 are ignored, because a development instance is not
reachable from a runner and a runbook page that names one is not broken.

What is deliberately absent
===========================

- **Publishing.** No deployment, no gh-pages push, no artifact uploaded to a
  registry. That is #1604 and #1586.
- **Screenshots of a running instance and behavioural claims about one.** Those
  need a stack and browser evidence; #1601 and #1602 own them and the portal
  declares them as stubs rather than writing prose that looks like a test result.
- **The Python reference content itself.** Under the offline default it is a
  placeholder naming the module - see :ref:`docs-portal-autodoc`.
- **Translations.** The corpus is English; ``sphinx-intl`` has no catalogues to
  build yet, so a language switcher would list one language. When a second locale
  exists it is a ``mrmap_locales`` entry and a ``locale/`` directory, and the
  theme's language navigation appears with it.
