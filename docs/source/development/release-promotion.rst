.. _release-promotion:

=================
Release promotion
=================

Issue #1584 of epic #1577 wires the promotion: the protected path that turns
ONE reviewed commit of ``develop`` into a published stable release on
``master`` — release PR, merge, tag, GitHub release, sync — step by step,
each step an idempotent act, each judgement checked hard enough that running
the sequence cannot skip a person. The planner (#1581,
:ref:`release-planning`) prepares the version; the gates (#1583,
:ref:`release-compatibility-gates`) judge a candidate; this is what happens
between a green judgement and a tag, and after it.

Issue #1798 reconciled that path with the two things it has to live under and
may not bend: the develop-first policy of ``AGENTS.md`` and
``branch-policy.yml``, and what Release Please actually writes. Three rules
follow from it, and they are load-bearing:

* the pull request onto ``master`` has this repository's ``develop`` as its
  head. Nothing else: ``.github/workflows/branch-policy.yml`` answers any head
  but develop's onto master with "Only develop may target master", so the
  ``release/v<version>`` → ``master`` PR #1584 opened could never have been
  merged. Nothing is lost by dropping it — the reviewed candidate identity
  (sha, version, digests, evidence urls) is carried by the attestation
  ``preflight`` writes, so the freeze needs no ref at all and the tool writes
  no permanent branch;
* identity is checked against reality at every step. If ``develop`` advances
  past the reviewed candidate, that candidate is INVALIDATED: opening is
  refused until ``evidence`` and ``preflight`` have attested the new tip, an
  open release PR whose head no longer resolves to the attested commit is
  reported STALE rather than "open", and no step trusts a ref name — each
  resolves the candidate and the PR head to an exact commit, and requires
  master's tip to be the merged release PR's merge commit;
* publication needs evidence that was not produced on the way to publication.
  ``open-release-pr``, ``finalize`` and ``gate`` take the
  ``mrmap-release-candidate/1`` attestation and REFUSE without it, or with one
  for another sha or version, or with digests that are not the attested ones.
  Shape alone is what a copy-paste has, so the file is additionally checked
  against what only ``release_gates.py promote`` binds into it: each required
  evidence class present, ``pass``, and gathered for exactly this commit; each
  required gate report present and green; a named ``generated_by``. A file
  written by hand that merely agrees with what is about to be published is
  refused. ``gate --simulate`` is a dry-run answer, says ``simulated``, and can
  never read as green.

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
* it never moves or deletes an existing tag. Something standing where the
  promotion would put its tag, at a different commit, is a CONFLICT it reports
  and stops on: reconcile means completing missing steps, never overwriting
  present ones;
* it writes no rolling alias. Q1 of #1578 answered the tag shape (`v0.2.0`
  first, `vMAJOR.MINOR.PATCH` — ADR-0002) and approved no alias, so the
  approved-alias set is still empty and `finalize` refuses `--alias` outright
  until a reviewed alias decision is on record — the same reading
  `image_release.py` applies to image aliases;
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
   `.release-please-manifest.json`, the release section of ``CHANGELOG.md``)
   all agree at it, develop itself carries it, and it says whether the sha is
   still develop's tip. A VERSION that moved without its release section is
   refused — that section is what the GitHub release body quotes. Since #1798
   the matcher reads BOTH shapes this repository carries: the hand-written
   `## [0.1.0] - 2023-03-23` of the history and the linked, generated
   `## [0.2.0](<compare url>) (2026-11-20)` of #1681. The version is captured
   and compared exactly, so neither the prerelease `[0.2.0-rc.1]` nor the
   longer digit run `[0.2.10]` of the line answers for `0.2.0`.
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
3. ``open-release-pr`` — this repository's ``develop`` → ``master``, titled
   `chore: release v<version>` and quoting the attested candidate in its body.
   Refused without the attestation of exactly that sha and version, and refused
   while develop has moved past it: a candidate the tip no longer is owes a
   fresh ``evidence`` + ``preflight`` pair, never a silently re-anchored PR.
   A PR whose head no longer resolves to the attested commit is STALE and a
   person closes it. The title is the PR's identity, so one version costs one
   pull request however often the step is re-run. A person reviews and merges —
   the merge IS the release decision.
4. ``finalize`` — after the merge, and refused without the attestation: it must
   name this sha and version, and the digests about to be published must be the
   digests it attested. It is also refused without a MERGED release PR for this
   version — master moving on its own, even by a merge commit, is not a
   reviewed act. Master's tip must then be that merge commit, must carry the
   candidate as a parent, and `git diff <candidate> master` must be EMPTY: the
   reviewed merge must have landed exactly the tested tree. Every judgement
   (alias refusal, digest shape, digest completeness, attestation, merged PR,
   merge-commit shape, tree equality, tag placement) is made BEFORE the first
   push — a tag is the point of no easy return. Then: annotated tag
   `v<version>` on master's tip (peeled comparison — a tag object's sha is not
   its commit's), and the GitHub release quoting candidate, release commit,
   artifact digests and the attestation, in the SAME run as the tag push,
   because a `GITHUB_TOKEN` tag push emits no workflow events for a later run
   to catch. An existing tag or release at the expected place is a skip;
   anywhere else a conflict.
5. ``sync`` — the reviewed ``master`` → ``develop`` sync PR after the release,
   so the planner's next window starts from the released state. While develop
   already contains master there is nothing to sync and the step says so.

``status`` prints the reconcile view of all of it (whether the candidate is
still develop's tip, release PR state and where its head resolves, whether
master's tip is that PR's merge, whether master carries the candidate and holds
its exact tree, where the tag stands, whether the release exists); ``gate``
answers the callable contract #1609 asked for — reviewed source/version and the
attested digests, whether master really carries them and whether the reviewed
release PR is what landed — with `--simulate` for dry-run suites that must not
touch a remote. A simulated answer reports `simulated` and `green: false`:
nothing that did not read reality can satisfy a publication decision.

Green is the conjunction of the published facts — a merged release PR, master's
tip as that PR's merge, the candidate carried by master, master's tree equal to
the candidate's, the tag at master's tip, the release — plus the attestation.
The PR's head is deliberately **not** one of them: the head of a merged
``develop`` → ``master`` PR is develop, and develop moves the moment anybody
merges anything after the release, so requiring it to still point at the
candidate would report a fully published version as not green forever. That is
the same reasoning `finalize` and `open-release-pr` apply to a merged PR. The
head is resolved and reported, and ``stale@<sha>`` is reserved for the
``open`` case, where a moved head really does mean the reviewed candidate was
invalidated; a merged PR whose head has moved reads ``develop@<sha>``, because
operators are told to treat ``stale@`` as an invalidation.

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

`scripts/test_release_promotion.py` (103 checks) and the promotion phases of
`scripts/test_release_lifecycle_dry_run.py` (72 checks, both in
`scripts/check_repo_tooling.sh`) drive the tool against throw-away repositories
whose "origin" is a local bare repo and a journaling `gh` shim: the unplanned
candidate, both changelog grammars and the prerelease of the line, a hand-edited
generated release section, a section that stays silent about its breaking
changes, evidence of another sha, the missing gate report, no attestation at
all, an attestation of another sha, version or digest, an attestation written by
hand rather than by the promoter (no evidence section, no gates, a class that
did not pass, evidence of another commit, a red gate, no named generator), a
release PR whose head moved while it was open (STALE), a master that moved
without a merged release PR, a master tip that is not a merge, a master whose
tree diverged, the tag standing on a foreign commit, the missing digest — each
seen REFUSED, and refused before a tag was touched — then the same worlds
promoted to green, every step re-run to prove "already done" is a skip and never
a duplicate, and the gate re-read after an unrelated merge advanced develop, so
that a published version is shown to stay green.

Deliberate limits, named
========================

* **No prereleases.** The planner may propose one (#1579's grammar carries
  `-rc.1`); whether one is ever cut is this issue's to own. Q1-Q6 of #1578 are
  answered policy now (ADR-0002) and Q5 makes a release candidate conditional
  on a supported, tested upgrade baseline, which #1800 has to verify first — so
  the stable path is complete and prerelease semantics stay unopened rather
  than invented here.
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
