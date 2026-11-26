.. _release-promotion:

=================
Release promotion
=================

Issue #1584 of epic #1577 wires the promotion: the protected path that turns
ONE reviewed commit of ``develop`` into a published stable release on
``master`` — release branch, merge, tag, GitHub release, sync — step by step,
each step an idempotent act, each judgement checked hard enough that running
the sequence cannot skip a person. The planner (#1581,
:ref:`release-planning`) prepares the version; the gates (#1583,
:ref:`release-compatibility-gates`) judge a candidate; this is what happens
between a green judgement and a tag, and after it.

The tool is `scripts/release_promotion.py`, run host-side as `python3
scripts/release_promotion.py <subcommand>` with the local `git` CLI for every
repository fact and the `gh` CLI for every GitHub fact. Exit codes are those
of every tool in ``scripts/``: **0** done or already done, **1** the step is
decided against the candidate, **2** it could not run — "could not run" is
never reported as a pass.

What this is, and what it refuses to be
=======================================

* it never pushes to ``develop`` or ``master``. Both pull requests it needs —
  the release PR and the sync PR — it OPENS; a person reviews and merges, per
  the git conventions of ``AGENTS.md``;
* it never moves or deletes an existing tag or release branch. Something
  standing where the promotion would put something, at a different commit, is
  a CONFLICT it reports and stops on: reconcile means completing missing
  steps, never overwriting present ones;
* it writes no rolling alias. Q1 of #1578 is Pending, so the approved-alias
  set is empty today and `finalize` refuses `--alias` outright until a
  recorded answer exists — the same reading `image_release.py` applies to
  image aliases;
* it produces no evidence and no attestation of its own. CI collects the
  evidence (`evidence`), `release_gates.py promote` is the ONE attester
  (`preflight` invokes it; its `mrmap-release-candidate/1` shape survives
  unchanged into the release body), and the gates' reports are consumed as
  files, never recomputed here.

The five steps
==============

Each step is its own dispatch and safe to re-run at any point — that is the
"reconcile partial failures" acceptance criterion as working code. The
workflow `.github/workflows/release-promotion.yml` exposes them behind the
protected ``release-stable`` environment with `workflow_dispatch` as its ONLY
trigger; there is deliberately no scheduled or push trigger that could promote
anything on its own.

1. ``plan`` — read-only. Is this sha a planned candidate: the five files the
   planner moves together (`VERSION`, its projection `backend/MrMap/version.py`,
   `.release-please-manifest.json`, the folded `## [<version>] - <date>`
   changelog section) all agree at it, and develop itself carries it. A
   VERSION that moved without its folded section is refused — the folded
   section is what the GitHub release body quotes.
2. ``evidence`` + ``preflight`` — `evidence` assembles the four classes
   `release_gates promote` requires (tests and sonar from CI's own check
   conclusions, dependencies from a manual URL, artifacts from
   `name=sha256:<64 hex>` digests) for one exact sha. `preflight` feeds that
   file plus the three gate reports (api, version, upgrade) to
   `release_gates.py promote` and writes its attestation. Evidence of another
   sha gets no attestation, and a gate whose report was never produced stops
   the promotion. These two run where the gates run (host or the
   release-gates job), not in the protected workflow — the attestation file
   they produce is an INPUT of finalize.
3. ``open-release-pr`` — the freeze: push `release/v<version>` at the exact
   candidate sha (develop moves on; the PR must not drift with it) and open
   `release/v<version>` → ``master``. An existing branch at another sha is a
   conflict, never a reset. A person reviews and merges — the merge IS the
   release decision.
4. ``finalize`` — after the merge. Master must carry the candidate, and
   `git diff <candidate> master` must be EMPTY: the reviewed merge must have
   landed exactly the tested tree, or publication is refused. Every judgement
   (alias refusal, digest shape, digest completeness, tree equality, tag
   placement) is made BEFORE the first push — a tag is the point of no easy
   return. Then: annotated tag `v<version>` on master's tip (peeled comparison
   — a tag object's sha is not its commit's), and the GitHub release quoting
   candidate, release commit, artifact digests and the attestation, in the
   SAME run as the tag push, because a `GITHUB_TOKEN` tag push emits no
   workflow events for a later run to catch. An existing tag or release at the
   expected place is a skip; anywhere else a conflict.
5. ``sync`` — the reviewed ``master`` → ``develop`` sync PR after the release,
   so the planner's next window starts from the released state. While develop
   already contains master there is nothing to sync and the step says so.

``status`` prints the reconcile view of all of it (frozen branch, release PR
state, whether master carries the candidate, where the tag stands, whether the
release exists); ``gate`` answers the callable contract #1609 asked for —
frozen source/version, whether master really carries it — with `--simulate`
for dry-run suites that must not touch a remote.

Where the artifact digests come from
====================================

`evidence`, `gate` and `finalize` need the digest of each first-party image of
the candidate, and they read it from a **file the build wrote** rather than from
text typed into a dispatch (#1799):

.. code:: console

    $ python3 scripts/release_promotion.py gate --sha 8a57e9a78f5f… \
        --candidate-evidence candidate-images.json --simulate

That file is the `mrmap-candidate-images/1` evidence
``scripts/image_release.py --attest`` produced for the candidate and
`.github/workflows/candidate-images.yml` published as the
`candidate-images-<sha>` artifact (:ref:`release-candidate-images`). The
workflow exposes it as the ``candidate_run`` dispatch input: name the run, and
the artifact is downloaded and passed as ``--candidate-evidence`` — the only
thing an operator types about a digest.

Both doors stay open, and they are not two ways to override each other. A
``--artifact name=sha256:…`` line that contradicts the file is REFUSED as a
conflict: two identities for one release means nobody knows which candidate is
being published. The file itself is refused unless it names this sha, this
version and this registry, and its digest is then re-read from the registry
before anything is tagged — evidence of another build, of another version, of
another namespace, or of bytes the registry no longer serves each fail with the
image and the disagreement named.

The protected environment
=========================

The workflow references the environment ``release-stable``; its required
reviewers ARE the manual approval the acceptance criteria demand. Two facts
before the first run, because GitHub cannot know them:

* an administrator must create the environment **with required reviewers
  before the first dispatch** — GitHub auto-creates a referenced-but-missing
  environment UNPROTECTED, which is exactly the hole this issue exists to
  close;
* the dispatch answer to "who approved this release" is the environment
  deployment log: one approval per step, one step per run, never one run
  waiting across days for an approval that blurs who approved what.

Why five dispatches instead of one waiting job
==============================================

A GitHub job can wait for an environment approval, but a job that waits for
days holds a runner and records one approval for many acts; and a design that
hinged on the tag-push event would silently skip publication, because pushes
of tags made with `GITHUB_TOKEN` trigger no workflow at all. So approval
granularity is job granularity (one act per dispatch), idempotence is the
retry story (every step re-runnable, skips named in its output), and the
journal of steps is the run list itself.

Offline checks
==============

`scripts/test_release_promotion.py` (31 checks, in
`scripts/check_repo_tooling.sh`) drives the tool against throw-away
repositories whose "origin" is a local bare repo and a journaling `gh` shim:
the unplanned candidate, evidence of another sha, the missing gate report, the
frozen branch elsewhere, the master whose tree diverged, the tag standing on a
foreign commit, the missing digest — each seen REFUSED, and refused before a
tag was touched — then the same worlds promoted to green, every step re-run to
prove "already done" is a skip and never a duplicate.

Deliberate limits, named
========================

* **No prereleases.** The planner may propose one (#1579's grammar carries
  `-rc.1`); whether one is ever cut is this issue's to own and Q1-Q6 of #1578
  stay Pending — so the stable path is complete and prerelease semantics stay
  unanswered rather than invented here.
* **The tag is the anchor.** The planner re-anchors `last-release-sha` from
  the tag itself (see :ref:`release-planning`); promotion emits the tag and
  the release in one run rather than reacting to events.
* **Digests are typed by hand into the protected workflow** until the
  registry-publish side (#1582's `image_release.py --promote`) is wired to
  hand them over automatically; the shape validation (`sha256:<64 hex>`, both
  first-party images or nothing) is what a typed-by-hand mistake can still not
  survive.
* **`wip done` before the merge of anything** — the claim board rule
  unaffected: an agent opens, a person reviews, merges and approves the
  environment deployment.
