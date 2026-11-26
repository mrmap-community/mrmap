.. _release-candidate-images:

========================
Candidate image builds
========================

.. sidebar:: Issue #1799, epic #1577

   ``.github/workflows/candidate-images.yml`` is the publisher added here: one
   explicitly dispatched, reviewed commit becomes two **candidate** artifacts in
   the project's own namespace, and the digests of those artifacts reach the
   release without being typed by anybody. The tool behind it is
   ``scripts/image_release.py`` (:ref:`versioned-images`, #1582); the promotion
   that turns a candidate into a release is
   ``.github/workflows/release-promotion.yml`` (:ref:`release-promotion`, #1609).

A MrMap release is now three separate acts, each with its own trigger and its own
permission, so that no single one of them can produce a release alone:

.. code:: text

    dispatch            dispatch                    dispatch (protected)
    candidate-images    release-promotion           release-promotion
        |                   |                           |
        v                   v                           v
    candidate-<sha>  ->  preflight/gate  ->  v<X.Y.Z> git tag + GitHub release
    + evidence file      (release-stable)      by release_promotion.py finalize

                                             and, by hand, the version tag of the
                                             same version in the registry:
                                             image_release.py --promote (#1581)

This page is about the first column: what a candidate is, how one gets built,
what the run publishes, and what an operator does when a run goes red.

What a candidate is, and what it is not
=======================================

A candidate is the artifact of **one commit that develop itself carries**, built
under a tag that names that commit:

.. code:: text

    ghcr.io/mrmap-community/mrmap-backend:candidate-8a57e9a78f5f
    ghcr.io/mrmap-community/mrmap-frontend:candidate-8a57e9a78f5f

It is not a release. Only ``scripts/image_release.py --promote`` creates a
version tag in the registry, and no workflow dispatches it: an operator runs it by
hand, because the protected trigger that would is #1581's and #1586's to record and
the readiness gates #1798..#1801 and #1610 still stand between this tool and a
first tag. The protected ``release-stable`` environment of
``release-promotion.yml`` (#1609) gates the *git* tag and the GitHub release, not
this push. There is
deliberately no input to the candidate workflow that could name a version tag: the
build is always ``--kind candidate``, so the failure this whole design is built
around - an automation publishing a release nobody approved - has no code path
here rather than a check that could be edited away.

It is also not the dependency images of epic #959. ``mrmap-backend-dev`` and
``mrmap-frontend-dev`` are tagged by dependency fingerprint, published by
``dev-images.yml``, and untouched by anything on this page.

Dispatching a build
===================

**Actions → Candidate images → Run workflow**, with:

.. list-table::
   :header-rows: 1
   :widths: 18 20 62

   * - input
     - example
     - what it decides
   * - ``sha``
     - ``8a57e9a78f5f…`` (40 hex)
     - the commit to build. The run refuses anything that is not 40 hex, not an
       object of the repository, or not reachable from ``develop`` - the same
       carrier rule ``release_promotion.py plan`` applies, so a candidate is never
       an artifact of a commit the release path would not promote.
   * - ``version``
     - ``0.2.0`` (or empty)
     - the version the candidate claims. Empty means "whatever ``VERSION`` says at
       that commit". Naming it and having ``VERSION`` disagree is refused: the
       artifact's ``org.opencontainers.image.version`` would not be the version
       under review, which is exactly the label an operator later asks.
   * - ``images``
     - ``both`` / ``backend`` / ``frontend``
     - one image or both. A release needs both; building one alone is for
       debugging a single Dockerfile.
   * - ``registry_base``
     - ``ghcr.io/mrmap-community``
     - where to publish. Pointing it at an isolated registry runs the entire path
       - build, publish, attest, hand over - without touching the project
       namespace. That is how the path is rehearsed, and it is the documented
       answer to "prove it without a production push".

Three things follow from those inputs that no input can override: the build runs
from a checkout **at** that SHA (so the Dockerfiles, requirement pins and version
are the candidate's own), the tags come from ``image_release.py`` (never
computed in the workflow), and the build's timestamp is the commit's own
``SOURCE_DATE_EPOCH``.

What the run produces
=====================

Two candidate tags, one evidence file, and one attestation per image.

**The candidate tags** carry the OCI labels of #1582 - ``.version`` (full canonical
version, build metadata included), ``.revision`` (the full SHA), ``.source``,
``.documentation``, plus ``io.github.mrmap.dependency-fingerprint`` on the backend
image only. The build is the tool's own ``--build --push``, i.e. the same command
``--plan`` prints and the offline suite holds.

**The evidence file**, ``candidate-images-<sha>/candidate-images.json``, is what
the promotion consumes. It is written by the tool, from the registry:

.. code:: json

    {
      "evidence": "mrmap-candidate-images/1",
      "generated_at": "2026-11-25T19:41:02+00:00",
      "generated_by": "releaser",
      "candidate": {"sha": "8a57e9a7…", "version": "0.2.0", "kind": "candidate"},
      "registry_base": "ghcr.io/mrmap-community",
      "images": {
        "backend": {
          "repository": "mrmap-backend",
          "repository_ref": "ghcr.io/mrmap-community/mrmap-backend",
          "candidate_ref": "ghcr.io/mrmap-community/mrmap-backend:candidate-8a57e9a78f5f",
          "digest": "sha256:d387…",
          "identity": ["sha256:fd41…"],
          "labels": {"org.opencontainers.image.revision": "8a57e9a7…", "…": "…"}
        },
        "frontend": {"…": "…"}
      }
    }

The digest in it is **the digest the tag resolves to**, read back from the
registry, not the value the build printed; ``identity`` is the child manifest
inside the index a promotion will wrap around it. The run refuses to write the
file at all when the artifact contradicts the candidate it is supposed to attest -
another revision (a stale tag left by an older run), another version, no version
label, or a digest that does not resolve on its own.

**The attestation** is raised over each digest by
``actions/attest-build-provenance`` and pushed to the registry, in a job that
holds ``id-token: write`` and nothing else the build needs.

No digest is ever pasted by a person. The promotion's own reader is exercised on
the same file inside the same run (``release_promotion.py gate
--candidate-evidence … --simulate``), so a mismatch between the two ends of the
path turns this run red instead of surprising somebody during a release.

Promoting from it
=================

.. code:: console

    $ python3 scripts/image_release.py --promote --kind stable --version 0.2.0 \
        --revision 8a57e9a78f5f… --candidate-evidence candidate-images.json
    image_release: promoted: ghcr.io/mrmap-community/mrmap-backend:0.2.0
    image_release: promoted: ghcr.io/mrmap-community/mrmap-frontend:0.2.0

and, on the promotion side, the same file answers #1609's gate:

.. code:: console

    $ python3 scripts/release_promotion.py finalize --sha 8a57e9a78f5f… \
        --candidate-evidence candidate-images.json

Two doors stay open on purpose: ``--candidate-evidence`` for the file CI wrote,
``--artifact``/``--digest`` for an operator naming a digest by hand. They are not
two ways to override each other - a hand-typed line that contradicts the build's
own file is refused as a conflict, because two identities for one release mean
nobody knows which candidate is being released.

What is checked, and by whom
============================

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - question
     - answered by
     - when it fails
   * - is this commit on develop, and does ``VERSION`` say what was claimed
     - the dispatch step, from git
     - the run is red before docker runs
   * - do the bytes carry the version and revision they claim
     - the tool, asking the registry (``--attest``, ``--promote``,
       ``--check-manifest --verify``)
     - no evidence file, or no tag
   * - does the digest still resolve, on its own
     - the tool, twice: at attestation and at promotion
     - no evidence file, or no tag
   * - is this tag already somebody else's content
     - the registry, through the tool's identity comparison
     - refused, with no ``--force``
   * - is the evidence file for this sha, this version, this registry, these
     - ``release_promotion.py`` reading the file
     - the promotion refuses, naming what disagreed

The offline half of that list is pinned by ``scripts/test_image_release.py`` with
the module's registry doors stubbed, so it runs in CI without a registry. The
live half - two real images built, published to an isolated registry, attested,
promoted, re-promoted, and each refusal fired against real registry answers - was
rehearsed for this issue and is summarised below.

Reproducibility, and why the build pushes no provenance
========================================================

``--build`` exports ``SOURCE_DATE_EPOCH`` as the commit's own committer timestamp,
so two builders of one commit get one digest. Measured in an isolated registry,
rebuilding the same candidate reproduced both digests exactly.

Provenance is deliberately **not** written by buildx. Same commit, same
``SOURCE_DATE_EPOCH``, three runs:

.. code:: text

    --provenance=true     ->  sha256:3036fd70…  then  sha256:025a3062…
    --provenance=mode=min ->  sha256:ff729f08…
    --provenance=false    ->  sha256:d8949d18…  then  sha256:d8949d18…

buildx embeds its attestation in the pushed index, so the artifact's digest moves
with every rebuild. A candidate whose digest moves when nothing about it changed
is a candidate a promotion cannot check - the digest in the evidence file stops
being an answer about the commit. So the build pushes no provenance, and
``actions/attest-build-provenance`` raises it afterwards over the finished digest,
without rewriting a byte. GitHub only accepts those attestations for ``ghcr.io``,
which is why the attestation job is skipped - not failed - on an isolated-registry
rehearsal.

Multi-arch is not offered: nothing in the repository passes ``--platform``, so
both images are of the builder's own platform, and advertising ``linux/arm64``
would publish a promise nothing tests.

Least privilege
===============

``permissions: {contents: read}`` at the top, and one escalation per job: the
build job adds ``packages: write``, the attestation job adds ``packages: write``
and ``id-token: write``, the evidence job has none. No job holds both an image
push and an OIDC token. The workflow triggers only on ``workflow_dispatch``;
nothing here runs on a merge or a push. Registry credentials come from
``docker/login-action`` with the run's own token scoped to the namespace named on
the dispatch - no secret is stored for this workflow.

Recovering a red run
====================

Re-dispatch is the recovery step, and it is safe by construction: the concurrency
group per SHA uses ``cancel-in-progress: false``, so a re-run never overtakes a
run that already pushed one of the two candidate tags, and rebuilding an existing
candidate is a re-push of identical bytes under the same name rather than the move
of a release. Nothing is deleted, and nothing needs to be.

.. list-table::
   :header-rows: 1
   :widths: 30 35 35

   * - what failed
     - what it means
     - what to do
   * - ``the candidate SHA must be 40 hex characters`` / ``not reachable from
       develop``
     - the dispatch asked for something that is not a candidate; the runner
       refuses to resolve a short sha on your behalf
     - re-dispatch with the full SHA of a commit on develop
   * - ``VERSION at <sha> is X but the dispatch claims Y``
     - the version under review is not the version that commit carries; the label
       on the artifact would have been the wrong one
     - re-dispatch with the version ``VERSION`` says, or with it empty, or build
       the commit that does carry the claimed version
   * - ``the frontend image bakes its API address into the bundle``
     - a step cleared or overrode the ``EXTERNAL_*`` variables of the workflow
       environment
     - re-dispatch; if it recurs, the workflow's ``env`` block changed
   * - the build step itself
     - the builder's own output above the failure says why - a Dockerfile, a
       requirement pin, or a base image that could not be pulled
     - fix the cause on develop, re-dispatch against the **new** SHA. A candidate
       is never a re-run of an outdated commit
   * - ``answers revision …, not the candidate …`` at ``--attest``
     - the candidate tag in the registry is the artifact of a different commit, or
       the dispatch named a commit whose candidate was built by an older run of a
       moved branch
     - re-dispatch against the SHA you actually mean; the stale tag stays as the
       history of the commit that made it and harms nothing
   * - ``carries no org.opencontainers.image.version label``
     - something other than this tool published under that candidate name
     - stop and read the registry: ``ghcr.io`` package settings show who published
       it. A release name written by anything but ``image_release.py`` is the
       finding, not the obstacle
   * - ``the digest … does not resolve on its own``
     - the tag resolved to a digest the registry will not serve under that digest
     - re-dispatch; if it persists, the registry is inconsistent and this is the
       moment to stop rather than promote
   * - ``could not be read`` for a digest at promotion
     - the artifact is gone, or the registry is unreachable
     - re-dispatch the promotion; if the artifact was deleted, build a new
       candidate
   * - the attestation job only, on a ``ghcr.io`` run
     - the OIDC token could not be obtained (transient), or the package is
       private and does not accept attestation references
     - re-dispatch. A candidate without an attestation is still a candidate with
       verified labels and digests; fix the package settings before relying on
       ``cosign verify-blob-attestation``

What the registry looks like after any run: candidate tags for the commits that
were built, at most one version tag per promoted version, no aliases, no deleted
artifacts. A failed run leaves a candidate tag behind, and that is correct - the
tag is the history of the commit that built it, and a promotion cannot pick it up
unless the evidence file and the registry agree about it.

Swapping the builder
====================

The build step calls the tool rather than a ``docker/build-push-action`` block
because the tool is where the tag, label and build-arg policy lives, and a
workflow that computed any of them would be a second place where the name of a
release image is decided - the drift #1582 exists to prevent. The tool's build is
the same shape the maintained upstream action supports, and ``--print`` is what
hands that action the tool's decision, one key per call, the same service
``dev_image_id.py --print-build-args`` performs for the dependency images:

.. code:: yaml

    - uses: docker/setup-buildx-action@v4        # pinned by SHA in the workflow
    - uses: docker/login-action@v4               # ghcr.io, github.actor, github.token
    - uses: docker/build-push-action@v7
      with:
        context: ${{ steps.plan.outputs.context }}
        file: ${{ steps.plan.outputs.dockerfile }}
        tags: ${{ steps.plan.outputs.tags }}             # --print tags
        build-args: ${{ steps.plan.outputs.build_args }} # --print build-args
        labels: ${{ steps.plan.outputs.labels }}         # --print labels, one k=v per line
        cache-from: type=gha,scope=backend-candidate
        provenance: false                        # see the measurement above
        push: true
      env:
        SOURCE_DATE_EPOCH: ${{ steps.plan.outputs.source_date_epoch }}

``steps.plan`` is the workflow's own "read what to build from the release tool"
step, which asks for each key once. If this action ever gains a first-class
``SOURCE_DATE_EPOCH`` input, moving the build to it is a step rewrite here and no
change to the tool - the evidence file, the tag policy and the promotion checks
are the same either way.

What is still not wired
=======================

* **The registry push is still a human act.** The version tag is written only by
  ``image_release.py --promote``, and no workflow dispatches that flag today - an
  operator runs it, by hand, against the digest the evidence file names. Wiring
  the dispatch behind ``release-stable`` is #1581's and #1586's decision to
  record, not something to invent here. This workflow cannot reach ``--promote``,
  and no input here can ask it to.
* **No rolling aliases.** Q1 of #1578 approved no alias (ADR-0002), ``--kind
  candidate`` refuses them, and ``release_promotion.py finalize`` refuses
  ``--alias`` until a reviewed alias ledger exists.
* **Multi-arch**, as above.
* **A required status check on releases.** Making this workflow's evidence job
  required for a release PR is #1609's and #1604's decision to record, not this
  issue's to assume.
