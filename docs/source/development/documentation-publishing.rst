.. _development-documentation-publishing:


=========================
Documentation publishing
=========================

.. sidebar:: Issue #1608 (epic #1589)

   The publisher is ``scripts/docs_publish.py``, the privileged job is
   ``.github/workflows/docs-pages.yml``, the offline checks are
   ``scripts/test_docs_publish.py``. The build that produces what gets
   published is ``.github/workflows/docs.yml``
   (:ref:`development-documentation-portal`), and the contract this page
   implements is ADR-0001 section 12.

Publishing documentation is the one documentation job that writes something
people read. Everything before it - building, validating, checking coverage -
can be wrong without anyone outside the repository noticing; this cannot. So the
rule the whole page follows is ADR-0001 section 11: **a failure means no new
publication, never a downgraded publication.** A red documentation run blocks a
release and leaves yesterday's docs served. It does not publish a partial tree,
and it does not "roll back" either, because the previous revision was never
moved in the first place.

What replaced ``publish_docs.sh``
=================================

``docs/publish_docs.sh`` was a 2021 script. It rebuilt the portal inside the job
and then ``git push --force``d the result onto ``gh-pages``. It is deleted by
this issue, and not because a force push is unfashionable - each property the
epic asks for is the exact opposite of what that script does:

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Requirement
     - ``publish_docs.sh``
     - ``docs_publish.py``
   * - A failed run keeps the previous version served
     - ``--force`` rewrote the only copy; a bad build replaced good docs
     - one commit whose parent is the fetched tip; a refusal writes nothing
   * - Exact version, SHA and digests
     - the tree was built inside the publisher, so nothing named its inputs
     - the artifact names them, and every one is checked before a write
   * - Verified reuse only when inputs match
     - rebuild everything, every time, and hope
     - one ``docs_manifest`` per input set; an identical rerun writes nothing
   * - Least privilege
     - the credentials that built the docs wrote the website
     - the build job reads artifacts; only the gated job can write Pages
   * - Historical versions and URLs
     - whatever survived the last force push
     - older directories are inherited by construction, never deleted

Publication is now two jobs that cannot be conflated: ``docs.yml`` builds and
uploads an artifact with ``contents: read``, and ``docs-pages.yml`` - behind the
``docs-pages`` environment, dispatched by a person - downloads an artifact and
publishes it with ``contents: write``. The publisher never builds, which is what
ADR-0001 section 12 means by "a separate privileged step that consumes artifacts
and never runs a model".

The four path families
======================

``--channel`` is required rather than read from the artifact. A build that could
name where it would be published is a build that could publish itself, and that
is the arrangement that produced the force push:

.. list-table::
   :header-rows: 1
   :widths: 22 24 54

   * - Channel
     - Serves
     - Rule
   * - ``version``
     - ``/vX.Y.Z/``
     - written once, never again; a second artifact for a standing directory is
       refused (gate V-17)
   * - ``stable``
     - ``/vX.Y.Z/`` and ``/stable/``
     - the version directory plus a *copy* of it at ``/stable/``, which only
       ever moves forward to a higher SemVer version
   * - ``develop``
     - ``/develop/``
     - the last **validated** candidate; a gate report that did not pass is
       refused here too

An optional ``/vX.Y.Z-rc.N/`` directory needs ``--allow-prerelease``, because
``scripts/release_lifecycle.json`` states that prereleases carry no published
documentation, and the exception should be a flag a reviewer sees rather than a
version string that happens to look like a release candidate.

A channel mismatch is a refusal. An artifact whose ``provenance.json`` says
``pages_build: develop`` cannot be published as ``stable`` no matter who asks,
which is the acceptance criterion "candidate/stable isolation" enforced at the
only moment it can be - the write.

``/stable/`` is a copy, not a pointer
=====================================

It would be tidier to serve ``/stable/`` as a symlink or a redirect to the
version directory. It is a copy on purpose: retention can then drop an old
``/vX.Y.Z/`` directory without taking ``/stable/`` down with it, and a reader of
``/stable/`` is served the exact bytes that passed the gate rather than a
redirection whose target depends on what else happens to be published.

Identifying what is published
=============================

Every published directory carries ``.docs-version.json``:

.. code-block:: json

    {
      "schema": "mrmap.docs.published.v1",
      "channel": "stable",
      "path": "/stable/",
      "version": "1.2.3",
      "docs_manifest": "sha256:9f2c...",
      "documented_commit": "4c1a...",
      "candidate_sha": "4c1a...",
      "source_digest": "sha256:71ab...",
      "artifact_digest": "sha256:07ec...",
      "portal_digest": "sha256:5d40...",
      "artifact_name": "documentation-portal",
      "run_id": 1001,
      "publisher": "mrmap-docs-publisher"
    }

That file is two things at once. It is what tells a reader and a health check
which build answers a path - the theme's own version switcher is generated by
``sphinx_multiversion`` when a ref is built, so this marker is the independent
record of what the *publisher* wrote, which is exactly why it can be trusted to
disagree with a build. And it is the assertion ``verify`` checks: re-download the
artifact, digest its tree the same way, compare. If the bytes a reader gets are
not the bytes the artifact produced, that is a failure with a name, not a
suspicion.

The root ``.docs-version.json`` is the same idea for the site: which versions are
served, which one is stable, which candidate is the current preview. It is
rewritten with every publication, so "what does this site claim to publish" has
one answer that ``status`` prints and a monitoring probe can read.

The reuse key
=============

``docs_manifest`` is the identity ADR-0001 section 6 fixes, and it is the whole
reuse rule:

.. code-block:: text

    sha256( version, candidate tree, dependency lockfiles,
            locales, generator, evidence digest, provenance digest )

Read that list as the set of things that can make a documentation build lie about
being current. A rerun of an identical candidate produces one key, so it is a
skip that writes nothing - "verified artifact reuse only when inputs match", and
the reason a rerun is free. A locale landing, a ``package-lock.json`` change or
a generator edit moves the key, so the old artifact is *not* the artifact of this
candidate and cannot be published for it.

The lockfile, locale and generator digests are read from the candidate tree with
``git show``, never from the working copy. On CI the working copy is the merge
commit of a pull request, which is not the candidate and never will be; a key
computed from it would silently change under a green build.

Downloaded bytes are checked against the attestation the caller passes
(``--digests name=sha256:...``) before anything is published. A download that
does not match is not republished with a warning, because "the artifact I
downloaded is not the artifact that was verified" is precisely the case a
publisher exists to catch.

Serialized, atomic, idempotent
==============================

Three separate mechanisms, because three different races exist.

*Serialized.* ``docs-pages.yml`` runs every publication in one concurrency group
that does not cancel. The tool re-reads the Pages tip *after* acquiring it, and
``--expect-revision`` catches the window between ``plan`` and ``publish``: a
publisher that would overwrite a commit it never read refuses and writes nothing.

*Atomic.* One publication is one ``git`` commit, written from the fetched
revision plus its own change through an isolated index. Either all of an
artifact's files appear or none does, and no path outside the published
directory can move - which is why "preserve historical versions" needs no code.

*Idempotent.* Per path, by ``docs_manifest``. Publishing the same artifact twice
prints ``skip`` and creates no commit; a rerun after a partial failure completes
what is missing and leaves what is done alone.

The Pages branch lives in a private bare repository under the runner's temp
directory, keyed by the remote URL and refreshed with ``git fetch``. There is no
local branch and no worktree, so ``--force`` is not forbidden by policy - it is
not reachable. ``retire`` checks that no committed workflow pushes ``gh-pages``
with ``--force`` either, which is what keeps the retired script retired.

Running it
==========

.. code-block:: bash

    # what a publication would do, with the reason per path; writes nothing
    python3 scripts/docs_publish.py plan     --channel stable --run 1001 \
        --candidate 4c1a... --digests portal/index.html=sha256:...

    # the same decision, executed as one commit
    python3 scripts/docs_publish.py publish  --channel stable --run 1001 \
        --candidate 4c1a... --digests ...

    # what is served, and whether it matches the artifacts it claims
    python3 scripts/docs_publish.py status    --json
    python3 scripts/docs_publish.py revisions
    python3 scripts/docs_publish.py verify    --channel stable \
        --artifact-dir /tmp/artifact --candidate 4c1a...

    # one-off maintenance
    python3 scripts/docs_publish.py bootstrap    # the Pages branch, once
    python3 scripts/docs_publish.py archive --run 1001 --output docs-artifact.json
    python3 scripts/docs_publish.py retire       # the force-push era stayed over

Exit codes follow the repository's convention: **0** done or already done, **1**
refused (the tool decided against the input), **2** could not run (no ``gh``,
unreachable remote, missing artifact). "Could not run" is never a pass - a
publisher that silently treats a network failure as success is how a release
ends up shipping documentation from an earlier commit.

Before the first run
====================

Two operator actions, both of them settings rather than code:

1. **Settings → Pages**: "Deploy from a branch", branch ``gh-pages``, root
   ``/``. This repository has carried that branch since the force-push era. If
   it were empty, ``bootstrap`` creates the root selector once - Pages reports a
   build error for a branch with no root file, and a publication needs a parent
   commit to sit on.
2. **Settings → Environments**: create ``docs-pages`` **with required
   reviewers**. GitHub auto-creates a referenced-but-missing environment
   *unprotected* on the first run, so the gap is silent: the publisher would run
   with no approval at all. This is the same trap ``release-promotion.yml``
   documents for ``release-stable``, for the same reason.

Then run ``plan`` first. It reads the artifact and the Pages tip and reports the
per-path decision without writing, so the question "what would this publish" is
answered by the tool rather than by reading the diff.

What is deliberately absent
===========================

* **A trigger other than a human.** No push, pull request, merge group or
  schedule. The release-only contract of the epic forbids publication on an
  ordinary change, and ``docs.yml`` remains the job that runs on one.
* **A live publication in this change.** The dry run the acceptance criteria
  name is ``plan`` plus ``--dry-run``, and the suite proves the negative case
  against a local bare repository. Activating publication stays an approved
  maintainer act - #1609 wires it into the release path, #1610 performs the
  end-to-end validation.
* **A credential of its own.** ``gh`` answers every GitHub fact and the push
  uses ``git``'s credential helper. Nothing here reads a token from a file.
* **A rollback command.** There is nothing to roll back: a refused or failed
  publication never moved the branch, and the suite asserts byte-for-byte that
  the previously published tree is intact after every way a publication can
  fail.

Testing
=======

``python3 scripts/test_docs_publish.py`` runs 129 offline checks: throw-away git
repositories whose "origin" is a local bare repository, a journaling ``gh`` shim
for artifact downloads, no docker, no network, no token. It asserts the
acceptance criteria rather than the happy path - candidate and stable isolation,
an immutable version directory, reuse only on a matching key, serialized
publication against a publisher that moved the branch first, and that each of
seven different failures leaves the published bytes unchanged. The real working
tree of the repository is snapshotted before and after every subcommand, which
is how "no source writes" is a check rather than a claim.
