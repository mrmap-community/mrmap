.. _docs-release-rehearsal:

==============================================
Documentation release rehearsal (#1610, #1589)
==============================================

:doc:`documentation-hosting` says what the release path is *configured* to do.
This page is about the other half: whether it actually does it, measured once on a
commit rather than asserted from a file. #1610 asks for exactly one non-production
rehearsal of the build-and-host path, and this page is its record — what ran, what
was observed, what the observation does **not** cover, and how to run it again.

The distinction that makes the rehearsal worth running at all is between the two
kinds of statement it can produce. A committed file can prove that the repository
declares no publisher, pins one environment and names one site. Only a run can
prove that the gate refuses a broken tree, that the build attributes itself to the
commit it built, and that the hosted site answers. A page that mixed the two would
be the thing this issue exists to prevent: a lifecycle that reads as validated
because it was described well.

What a rehearsal may never do
=============================

Three rules, all enforced by the tool rather than by this paragraph.

- **No production tag, no publication, no live release.** The only write the tool
  can perform is one tag under the ``docs-rehearsal-`` prefix. A name matching the
  release pattern of ``scripts/release_lifecycle.json`` is refused, and so is a
  tag pushed without ``MRMAP_DOCS_REHEARSAL_PROMOTE`` naming that exact tag —
  publishing is an act on shared infrastructure and is authorised in the
  environment, not on a command line. Cutting the first real tag belongs to
  #1801.
- **It rehearses a candidate, never a working tree.** The tree is exported with
  ``git archive`` and built there. Rehearsing a dirty checkout would report on
  files that are not in any commit, which is the failure mode that let a
  contradictory ``.readthedocs.yaml`` survive: it worked on someone's machine.
- **A skipped build is not a rehearsal.** If Sphinx cannot be imported the run
  exits 2 with a message, and never prints a green summary. ``docs_interpreter()``
  distinguishes "this optional environment has no docs pins" from "you pointed me
  at an interpreter that was supposed to have them", because the second case is a
  broken toolchain pretending to be a passing gate.

How to run it
=============

.. code-block:: bash

    # the pinned docs environment, named once
    export MRMAP_DOCS_PYTHON=/path/to/venv/bin/python   # venv with backend/.requirements/docs.txt

    # the rehearsal of one exact commit, reading the managed host
    python3 scripts/docs_release_rehearsal.py --candidate <sha>

    # gate only, no network, reported as gate-only rather than as a pass
    python3 scripts/docs_release_rehearsal.py --candidate <sha> --skip-host-probe

    # rehearse the merge a release would stand on, keeping the artifact to inspect
    python3 scripts/docs_release_rehearsal.py --candidate <sha> --out /tmp/docs-artifact

``--candidate`` is required and takes one revision; the report names the resolved
SHA, so a report cannot outlive the commit it describes. The hosted site is read
from ``scripts/image_release.py``, the same file whose image metadata already
publishes the documentation URL — one place names the site — and
``MRMAP_DOCS_REHEARSAL_URL`` overrides it for a rehearsal against a project
outside the repository. ``--evidence-out`` must land under
``docs/**/evidence/``, where the recorded live runs of this repository live
(:ref:`docs-hosting` explains why a rehearsal report is reviewed content rather
than a log); anything else is refused before a build starts, so a rehearsal cannot
deposit a report in ``scripts/`` and call it evidence.

The candidate the gate builds is checked against four things, and the strictness
of each is deliberate.

.. list-table::
   :header-rows: 1
   :widths: 26 40 34

   * - What is checked
     - How
     - Why it is not softer
   * - The gate flags
     - ``-b html -E -W --keep-going`` are read out of the build step of
       ``.github/workflows/docs.yml``, and the rehearsal exits 2 if they are not
       there
     - A rehearsal that passed its own flags would be a rehearsal of a gate the CI
       does not run; the flags are read, never repeated
   * - The build of the candidate
     - one Sphinx run over the exported tree, with ``MRMAP_DOCS_REVISION`` naming
       the SHA so provenance attributes the build
     - ``provenance.json`` of the artifact is read back and compared to the
       candidate: a green build of the wrong tree is not evidence
   * - The refusal of a broken candidate
     - the same tree with one toctree entry naming a page that does not exist
     - a gate nobody broke is an untested gate; the fault class is the one a real
       release produces when a page is renamed
   * - The hosted site
     - ``HEAD`` requests of the site, ``/en/stable/`` and ``/en/latest/``
     - a version counts as published only on a ``200``; the service answers an
       inactive version with ``x-rtd-version`` set and a ``404`` body, and reading
       that header as "published" is the false green this probe exists to avoid

What the one rehearsal measured
===============================

Run on 2026-11-27 against ``mrmap-community/mrmap``. The report is
``docs/source/development/evidence/docs-release-rehearsal-1610.json``, and it is
committed rather than paraphrased: it carries the candidate SHA, every check with
its verdict, every measured value and every limitation named below. It reports
**17 of 18** — and the one red is a finding about this repository, not a tool that
failed to run, so the table below states it as the failure it is. The JSON
describes one run of one candidate; the two rows that compare it against a
hand-patched tree and against ``develop`` are measurements of other trees, taken
with the same exported-tree build (``strict_build``) and the same interpreter, and
are recorded in this table rather than in that file.

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - Observed
     - Result
     - Reading
   * - Strict build of the candidate
     - **refused**, exit 1, 13s, 96 pages: two ``toc.not_included`` warnings and
       one ``myst.xref_missing``
     - the mechanical merge of ``develop`` into ``master`` is not a releasable
       documentation state. ``master``'s ``development/index.rst`` is one of the
       141 conflicted paths of that merge, so the merged tree drops the two pages
       ``develop`` added (``vscode-configuration``,
       ``wfs-describe-batching-verdict``); and ``administration/permissions.md``,
       also conflicted, cross-references ``docs/architecture``, which sits outside
       the Sphinx source root. This is what the gate is for, and it is the finding
       this rehearsal exists to produce
   * - Whether that refusal is a three-line typo
     - no: deleting the two dropped entries and rewriting that one link still
       exits 1, on MyST header-level and docutils unindent warnings in the merged
       ``permissions.md``
     - the conflict is a real merge conflict in documentation, and resolving it is
       a human act owned by #1798, not something the rehearsal may invent
   * - The reviewed ``develop`` tree (``b333e15``), same flags, same interpreter
     - accepted, exit 0, 12.6s, 96 pages, provenance naming that SHA
     - the toolchain and the path are sound; what is broken is the unmerged state
       of the two permanent branches, which is exactly the distinction a rehearsal
       has to make before anyone cuts a tag
   * - Provenance of the accepted build
     - ``documented_commit`` equals the candidate; toolchain and source digest
       recorded
     - the artifact can be traced to a commit, which is what the force-push script
       of 2021 could never say
   * - Same tree, one missing toctree entry
     - refused, exit 1, naming ``rehearsal-missing-page``
     - a gate nobody broke is an untested gate; the fault class is the one a real
       release produces when a page is renamed, and the injection targets the first
       real toctree rather than the first indented line, because the landing page
       opens with an RST comment block
   * - The refused build's artifact
     - 96 pages still written
     - **the exit status is the only signal that distinguishes an accepted
       candidate** — nothing that publishes may key on an artifact's existence
   * - ``https://mrmap.readthedocs.io/``
     - 200, served by the managed service
     - the host is live and answers
   * - Served versions
     - ``latest`` only; ``/en/stable/`` answers 404 with ``x-rtd-version: stable``
     - consistent with the measured state in :ref:`docs-hosting`: the repository
       has no tag yet, so there is nothing for the activation rule to activate
   * - The candidate on GitHub
     - not reachable: the candidate is local history, and no Actions record is
       asked for on that path
     - a rehearsal tag on it would be an orphan, which is why the tag half of the
       rehearsal is not exercised here

What this rehearsal does **not** cover
======================================

Named rather than left implicit, because the point of a rehearsal is to say what
it proved and what it did not.

- **The service's administration settings.** Automation rules, the activation
  list, the default version and the redirect rows are not readable from a pull
  request, and no probe can substitute for them. An administrator confirms them
  against the checklist of :ref:`docs-hosting`; the rehearsal proves the gate and
  the served artifact, not the settings behind them.
- **An atomic publication.** Without the project API token the host's build queue
  is not observable, so what is recorded is the artifact the host serves. A
  release must not claim that a tag push and a served page are one event.
- **That a refused build leaves the previous version served.** The refusal is
  proven; the host's behaviour after one is a property of the service. What is
  proven here is stronger than it looks: because a refused build still writes its
  pages, the *only* thing standing between a broken candidate and a published site
  is the exit status — which is why rule 1 of :ref:`docs-hosting` activates on the
  tag, and the tag exists only after the gate (#1798) said yes.
- **``stable``, because it does not exist yet.** The first SemVer tag creates it,
  and #1801 authorises that tag. This rehearsal therefore observes the host, not
  the release.
- **The promotion merge itself.** ``git merge-tree`` reports the ``develop`` →
  ``master`` merge conflicted — 141 paths, 9 of them under ``docs/`` — so at the
  time of this run there is no promotion merge commit to rehearse. The run above
  is therefore recorded as an **isolated equivalent**: a merge of the two
  permanent branches built from their exact trees, declared as such in the report
  (``--isolated-equivalent``, with the reason). The gate result transfers to the
  promotion merge of the same documentation content; the hosting result does not
  extend to a tag that does not exist yet. Resolving that merge is #1798's work,
  and re-running this rehearsal on the real promotion merge is the last thing to
  do before #1801 cuts a tag.

What re-runs it
===============

``scripts/test_docs_release_rehearsal.py`` holds every rule above offline, in
milliseconds, on a throw-away repository the suite builds and discards: the
gate's flags come out of the committed job, a report can only be written under
``docs/**/evidence/``, an empty result is never a pass, a tag outside the
rehearsal prefix can never be pushed, and an inactive version is never reported as
published. Each prohibition is tested by breaking a candidate and requiring the
rehearsal to notice, so a check that stopped noticing goes red in CI rather than at
the next release.

.. code-block:: bash

    python3 scripts/test_docs_release_rehearsal.py

The live half — the real host, the real API, a real rehearsal tag — is exercised
by the tool itself, and this page plus the committed report is its evidence. That
split is the reason the suite needs no network and no credentials: what it can
prove without them is every decision the tool makes about what it observed, which
is where a rehearsal goes wrong.
