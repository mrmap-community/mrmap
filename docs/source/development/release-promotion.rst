.. _release-promotion:

=================
Release promotion
=================

Issue #1798 of epic #1577 reconciles the promotion with the develop-first
policy: ONE reviewed ``develop`` → ``master`` pull request per release, the
build, the approval and the publication all bound to that pull request's
**merge commit**, and no orchestrator of our own in between. The planner
(#1581, :ref:`release-planning`) prepares the version on ``develop``; the
gates (#1583, :ref:`release-compatibility-gates`) judge a candidate; this is
what happens once a person has merged, and it is two jobs of one workflow.

The mechanism is `.github/workflows/release-promotion.yml`: ``verify`` and
``publish``, wired through ``needs``, guarded by one ``concurrency`` group and
one protected environment, written with nothing but the ``git`` and ``gh``
CLIs that already run on a runner. ``workflow_dispatch`` is the only trigger
that can promote, and ``workflow_call`` exposes the same two jobs to the
consumers of #1609 and #1800 so nobody maintains a second copy of them. There
is no promotion script, no subcommand to run host-side, no state file and no
journal: the run list is the record, and re-dispatching is the retry story.

Why there is no orchestrator
============================

This is the part of #1798 that removed code, so it is worth stating as
positively as the parts that added it.

* **One dispatch answers and, when approved, publishes.** Nothing sits
  half-done waiting for a later dispatch to notice. ``verify`` decides one
  question about one commit; ``publish`` consumes the answer through ``needs``.
  A state machine exists to be reconciled, and reconciling it was the work.
* **The facts that decide publication are GitHub's, read through ``gh``.** A
  release happens when the reviewed release pull request is merged and
  ``master``'s tip *is* that pull request's merge commit. Both answers are
  fetched, never remembered — which is exactly what a state machine had to
  keep in sync and could get wrong.
* **A required check cannot be bypassed, so the workflow does not
  re-implement one.** A pull request becomes merged only through branch
  protection, and protection refuses the merge while a required check is
  missing, pending or red. ``merged`` with a ``mergeCommit`` therefore *is* the
  evidence that the commit was built and tested on the reviewed tree. Naming
  the specific jobs and pinning the built image digests to that commit is
  #1800; producing them is #1799. This workflow trusts the one thing GitHub
  cannot be talked out of.
* **Approval is the environment, and the environment covers the one job that
  writes.** Splitting the write across jobs would mean either an approval per
  job — a person clicking twice for one act — or a job that writes without an
  approval at all.
* **Publication is not a side effect of a rerun.** ``publish`` re-reads the tag
  at the moment of writing and refuses a tag that stands on another commit, so
  a rerun cannot move, duplicate or quietly complete a release somebody else
  already made.

What the rehearsal measured
===========================

release-please's own ``github-release`` command is the supported way to turn a
merged release pull request into a tag and a release, and it was rehearsed here
end to end on a throw-away repository before deciding. Two upstream facts make
it unusable for *this* repository as it is configured today, and both are worth
recording because they are the reason ``verify`` is a step at all:

* it creates the tag on the release pull request's **base branch** — which for
  us is ``develop``, because #1581 plans on ``develop``. It can therefore only
  ever tag ``develop``, the one thing #1577 and #1581 forbid. Measured:
  ``--target-branch master`` finds no releases to build and POSTs no ref,
  because ``master`` carries no release pull request of its own.
* with ``skip-github-release: true`` — which #1581 sets precisely so
  ``develop`` stays tag-free — it builds no release at all. Measured: 0 refs
  and 0 releases POSTed for a merged release pull request.

Everything upstream still owns stays upstream's: the plan, the version, the
changelog, the release pull request and the merge. Only the tag and the GitHub
release are written here, with ``git tag`` and ``gh release create``, standing
on the commit ``verify`` proved.

The two jobs
============

``verify`` answers, in order, and stops on the first no:

1. is the dispatched version a reviewed ``MAJOR.MINOR.PATCH`` — a prerelease is
   never a promotion candidate;
2. is there a **merged** ``develop`` → ``master`` pull request, and what is its
   merge commit (the newest such pull request, since that is the release);
3. is ``master``'s tip still exactly that merge commit — if ``master`` moved
   after the reviewed merge, this run publishes nothing;
4. does that commit carry the dispatched ``VERSION``; and
5. if a ``v<version>`` tag already exists, does it stand exactly on that
   commit. Anywhere else is a conflict, and a published tag is never moved.

It writes nothing. Its outputs — merge commit, version, tag — are what
``publish`` receives through ``needs``.

``publish`` runs behind the protected environment and re-reads ``master`` and
the tag rather than trusting what ``verify`` saw minutes or hours earlier:

* with ``publish`` false, the default, it is a **rehearsal**: it builds the
  release body, prints it, and writes no ref;
* with ``publish`` true it requires one ``sha256:<64 hex>`` digest per
  first-party image before writing anything — a release body whose digests are
  missing or malformed is an audit trail that dead-ends — and refuses a
  changelog with no ``## [<version>]`` section, because the notes a person
  reviewed *are* the release body;
* then the annotated tag ``v<version>`` on the verified commit, peeled for the
  comparison (a tag object's sha is not its commit's), and the
  ``gh release create`` for it **in the same run**: a ``GITHUB_TOKEN`` push of
  a tag emits no workflow event, so nothing may hinge on catching one later;
* if the tag and its release already stand where this run would put them, the
  run is a skip and duplicates nothing.

The protected environment
=========================

``publish`` runs behind the environment ``release-stable``; its required
reviewers ARE the manual approval the acceptance criteria demand, and the
environment deployment log is the answer to "who approved this release".

Two facts before the first run, because GitHub cannot know them:

* an administrator must create the environment **with required reviewers
  before the workflow is first used** — GitHub auto-creates a
  referenced-but-missing environment UNPROTECTED on the first run, which is
  exactly the hole this issue exists to close;
* publication stays rehearsing until the required build and gate jobs of #1799
  and #1800 sit in front of ``publish`` through ``needs`` and are green for the
  exact commit. Flipping the input is the deliberate act, and it belongs to
  that wiring, not to an operator's convenience. Until then a green run here
  means "the rehearsal passed", never "a release exists".

Offline checks
==============

`scripts/test_release_promotion.py` runs the **workflow's own step scripts**:
they are read out of the committed YAML and executed against throw-away
repositories whose "origin" is a local bare repo, with a journaling ``gh`` shim
in ``PATH``. A test cannot pass by drifting from the workflow, because there is
no second copy of the logic to drift from. It pins each refusal — no merged
release pull request, ``master`` moved after the merge, the version the commit
does not carry, the tag on a foreign commit, the malformed or missing digest,
the unfolded changelog section — seen REFUSED with nothing written, then the
same worlds promoted to green, with the re-run proving that "already published"
is a skip. `scripts/test_release_lifecycle_dry_run.py` drives the same scripts
through the whole lifecycle. Both run in `scripts/check_repo_tooling.sh`.

Deliberate limits, named
========================

* **No prereleases.** The planner may propose one (#1579's grammar carries
  ``-rc.1``); ``verify`` refuses one. Q1-Q6 of #1578 are answered policy now
  (ADR-0002) and Q5 makes a release candidate conditional on a supported,
  tested upgrade baseline, which #1800 has to verify first — so the stable path
  is complete and prerelease semantics stay unopened rather than invented here.
* **No rolling aliases.** Q1 of #1578 answered the tag shape and approved no
  alias, so no stable version tag moves once written and ``image_release.py``
  keeps refusing image aliases until a reviewed alias ledger is on record.
* **The tag is the anchor.** The planner re-anchors ``last-release-sha`` from
  the tag itself (see :ref:`release-planning`); promotion emits the tag and the
  release in one run rather than reacting to events.
* **Digests are passed in by hand** until #1799's build job hands its outputs
  down automatically; the shape validation (``sha256:<64 hex>``, both
  first-party images or nothing published) is what a typed-by-hand mistake
  still cannot survive.
* **``wip done`` before the merge of anything** — the claim board rule
  unaffected: an agent opens, a person reviews, merges and approves the
  environment deployment.
