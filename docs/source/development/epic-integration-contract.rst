.. _epic-integration-contract:

=================================================
Epic integration and migration contract (ADR)
=================================================

.. sidebar:: Issue #1590

   Part of epic #1588 (enforce epic-based development and integration
   workflow), issue #1590: the design deliverable of that epic. It decides
   *what* the epic branch contract is, so that #1591 can enforce it, #1592 can
   schedule against it, #1593 can gate it, #1594 can state it in the agent
   rules and #1595 can validate it end to end.

   This page is a **contract, not a tool**. It changes no production code, no
   workflow, no branch and no label. The normative calls it makes are proposals
   awaiting the maintainer review named under `Status of this page`_; anything
   still open is listed under `Open questions`_ and owned by a follow-up issue.

Status of this page
===================

As on the classification page, three kinds of statement are kept apart:

* **measured** — a command was run against this repository and its result is
  quoted. `Reproducing the audit`_ gives every command.
* **the rule** — the normative statement of what an epic branch is and which
  PR may target what. These are the rows of the decision table plus the MUST
  list. A row is binding only once the maintainer review has accepted it.
* **not decided here** — what this page deliberately leaves open, and which
  issue owns it.

All measurements below were taken on ``origin/develop`` at ``b07e893d1`` on
2026-11-20. Reproducing them is one block of commands at the end of the page.

The review that makes the rows normative is a human act, like branch
protection: an answer to a design question is not the ``agent: approved``
label and is not a pull-request review, and nothing on this page may be
presented as if it granted either.

Why an epic branch at all
=========================

The epic objective (#1588) names the defect this contract removes: an epic's
feature is merged to ``develop`` issue by issue, so ``develop`` carries a
feature that is half implemented for the whole duration of the epic. Three
consequences follow from that, and each one is what the contract has to fix:

1. ``develop`` is not releasable while a multi-issue feature is in flight, so
   every measurement of ``develop`` (the green baselines, the coverage gate,
   the release candidate of #1584) describes a state that does not exist as a
   product.
2. An unfinished feature has to be shipped behind a flag, hidden, or reverted,
   because the merge of child 3 of 6 is not optional once children 1 and 2 are
   on the integration branch and their CI is green.
3. The release notes of #1577 owe one entry per *feature*, not one per merged
   child, and a feature spread over six merges into ``develop`` cannot be
   folded back into one entry.

The remedy is one integration branch per epic, and the price is a second kind
of integration target with all the rules a second target needs: which branch
starts from which, which PR may target which, what "the dependency is done"
means across the boundary, and how the branch gets deleted without destroying
ancestry. Those are the rows of the decision table, and the rest of this page
argues for each one.

Measured starting point
=======================

Everything the contract has to accommodate, as measured:

* **No epic branch exists.** ``git ls-remote --heads origin`` lists 288
  branches; none is named ``epic/*``. The branch names in active use are
  ``ao/<topic>/issue-<N>`` (the AO orchestrator), ``agent/issue-<N>``,
  ``feature/issue-<N>-<topic>``, ``fix/issue-<N>-<topic>``,
  ``housekeeping/issue-<N>-<topic>`` and ``bugfix/issue-<N>-<topic>``. So the
  slug namespace is free and the contract does not have to reconcile a naming
  clash — but it does have to say what happens to the 288 existing branches,
  which is `Migration of existing work`_.
* **The rule already exists as prose and is unenforced.** ``AGENTS.md`` says
  "For epic sub-issues, use the designated epic integration branch if
  applicable" and "Feature, bugfix and housekeeping PRs target ``develop`` or
  their designated epic integration branch", with no definition of
  *designated* and no *applicable*. ``scripts/wip`` contains no occurrence of
  ``epic``, so a claim on an epic child carries no integration target at all.
* **Only ``branch-policy.yml`` cares about targets, and it checks one edge.**
  Its job triggers on ``pull_request`` against ``master`` only, and it asserts
  ``HEAD_BRANCH == "develop" && HEAD_REPO == BASE_REPO``. It runs *only* on a
  PR whose base is ``master``. A PR that targets the wrong develop-side branch
  is never looked at by any workflow: there is no develop-side base check to
  extend, so #1591's enforcement is new coverage, not a modification.
* **CI does not run for a PR into an epic branch.**
  ``quality-assurance.yml``, ``script-tests.yml``, ``codeql.yml`` and
  ``pr-classification.yml`` all restrict ``pull_request`` to
  ``branches: [master, develop]``. A child PR targeting ``epic/<slug>`` would
  get no backend tests, no frontend tests, no Sonar, no CodeQL, no
  classification and no merge queue. This is the hard prerequisite of the
  rollout, and #1594 owns it.
* **The native hierarchy already works and is in use.** Epic #1588 declares
  ``slug: epic-integration`` as its first body line, lists the six children as
  a checklist and registers them natively: ``gh api
  repos/.../issues/1588/sub_issues`` returns exactly #1590-#1595, which is how
  this automation read its own eligibility. ``AGENTS.md`` already makes that
  link authoritative over the title prefix ("When link and prefix disagree,
  fix the prefix"). The contract uses the native relation and adds no parallel
  registry.
* **The eligibility screen is already epic-aware on the native relation.**
  ``scripts/next_eligible.py --help`` documents ``--scope {epic,all-approved}``
  with ``--epic`` defaulting to an epic issue, screening the sub-issues of one
  epic. It is read-only and stateless. What it does not do is *ordering by
  epic branch*: it does not know a child's PR must land on ``epic/<slug>``,
  because no epic branch exists yet. That is #1592's scope.
* **Cross-epic dependencies are already real.** The security epic #1442 has
  seven native sub-issues, all open, and its child #1468 names a dependency on
  #1412 — a top-level issue outside the epic, since closed with its work on
  ``develop`` via merge commit ``77c6a6444``. That is the shape rule 7 has to
  resolve, and today it resolves by luck: #1412 happened to land on
  ``develop``. The failure mode the epic objective names — "dependencies
  outside the epic must be available in develop, not merely closed or merged in
  another private epic branch" — becomes reachable as soon as a second epic
  branch exists, so the readiness check has to resolve dependencies against
  branch ancestry rather than against a closed label. [#1591, #1593]
* **Epic-internal PRs cost CI per merge, and the contract does not hide it.**
  Under an epic branch, six children cost six child-CI runs plus one
  integration run, where today they cost six runs that each validate against
  ``develop`` directly. That is not additional cost so much as the same final
  validation made explicit: today the "does the epic hang together" test
  happens implicitly with the last child's merge, against a ``develop`` that
  also carries every unrelated change since the first child. What the epic
  branch buys is that the final validation happens against the epic alone. The
  budget the rollout has to keep inside is what #1595 measures; `The CI
  contract`_ says which checks have to run where.
* **Approval provenance is already screened.** ``next_eligible.py`` reads the
  approvers from ``AGENT_EPIC_APPROVERS`` (default: one named person) and
  refuses an issue whose ``agent: approved`` label was not applied by that
  allowlist. The epic contract inherits this and weakens nothing: no row of the
  decision table lets an agent approve, merge or retarget anything.

Decision table
==============

The table is the deliverable: it is executable, meaning every row's condition
names a fact readable from GitHub's API or from git ancestry, and every row's
action names one branch. The table is what #1591 encodes as a check, what
#1592 reads when it starts a worker, and what #1593 re-evaluates before the
integration PR. ``DET`` is the target of the *child* PR, ``target`` the branch
the change ultimately reaches.

.. list-table::
   :header-rows: 1
   :widths: 8 32 32 28

   * - #
     - Condition (all must hold)
     - Child branch starts from / PR targets
     - Base for the epic's integration PR

   * - R1
     - Issue has no native parent and no ``slug:``-declaring parent, i.e. it is
       not a sub-issue of any epic
     - starts from ``origin/develop``; PR base is ``develop``
     - n/a — the issue owes no integration PR

   * - R2
     - Issue is a native sub-issue of an open epic whose body declares
       ``slug: <slug>`` and whose acceptance criteria are still open
     - starts from the current head of ``epic/<slug>``; PR base is
       ``epic/<slug>`` **only**
     - not yet; see R7

   * - R3
     - Issue is a native sub-issue of an open epic that declares **no** slug,
       or whose body names no integration branch
     - bootstrap row: same as R1 (``develop``), and the epic's next actionable
       child owes the slug declaration first
     - see R7

   * - R4
     - Issue is a sub-issue of an epic that carries no ``agent: approved``
       label, so no child may be scheduled at all
     - no branch is created by a worker; ``next_eligible.py`` already refuses
       the issue
     - n/a

   * - R5
     - Epic branch exists and a child PR's base is anything other than
       ``epic/<slug>`` of its own epic (``develop``, another epic's branch, a
       sibling child branch)
     - refused by #1591's check; the PR is retargeted by a person, never
       silently rewritten by an agent
     - n/a

   * - R6
     - PR whose head is ``epic/<slug>`` and whose base is not ``develop``
     - refused: an epic branch integrates *into* ``develop`` and nothing else
     - n/a

   * - R7
     - Every required child is merged **into** ``epic/<slug>``, every
       cross-epic dependency is present in ``develop`` **and** an ancestor of
       the epic head, all checks on the epic head are green after the final
       merge, and every decision the epic owes is answered (rule 8 below)
     - children are done; nothing further targets the epic branch
     - integration PR: base ``develop``, head ``epic/<slug>``, merge commit,
       human-approved

   * - R8
     - R7 holds except that a cross-epic dependency is closed on GitHub but
       absent from ``develop``
     - refused readiness: the epic branch merges ``origin/develop`` into itself
       and re-runs the checks, or the dependency's owning PR lands on
       ``develop`` first
     - n/a until R7 holds

   * - R9
     - Epic's native parent is set (a nested epic) — the epic is itself a child
     - the child-epic's ``epic/<slug>`` is merged into its **parent's**
       ``epic/<parent-slug>`` exactly as a normal child merges (R7 with the
       parent as target); the parent then integrates into ``develop`` under R7
     - parent's integration PR: base ``develop``

   * - R10
     - Issue is a sub-issue of a **closed** epic whose integration PR is merged
       (its child work is an ancestor of ``develop``)
     - follow-up work is a new issue: R1, i.e. branch from ``develop``, base
       ``develop``. The old epic branch is gone and must not be recreated
     - n/a

   * - R11
     - Issue is a sub-issue of a **closed** epic whose work was never merged to
       ``develop`` (abandoned epic, branch deleted)
     - refused: a closed epic cannot accept children. A person either reopens
       the epic or files a new top-level issue (R1); an agent files neither
     - n/a

   * - R12
     - PR of an epic child whose base is correct but whose head is not an
       ancestor of the epic head at review time (the epic moved on)
     - the author merges ``epic/<slug>`` into the child branch (never a rebase
       of a branch open for review, per ``AGENTS.md``) and CI re-runs
     - n/a

   * - R13
     - Permanent branch pair only: any PR whose base is ``master``
     - unchanged by this contract
     - ``branch-policy.yml`` stands as measured: head must be ``develop`` in
       the same repository

Three rows carry the whole design and are worth reading twice:

* **R2** is the rule that keeps an incomplete feature off ``develop``. A child
  of an open epic has exactly one legal base. It is not an option with a
  default, and "the epic branch is behind and I just want CI" is R12, not R1.
* **R7** is what *done* means. Every child merged **into** the epic branch is
  necessary and not sufficient: the cross-epic dependency has to be present in
  the *ancestry of the epic head*, which after the merge of R8 is the same
  sentence for both, and it is exactly the failure mode the epic objective
  names. Checking ancestry rather than a closed label is what stops "closed in
  another private epic branch" from counting.
* **R10/R11** close the lifecycle. An epic branch is not a permanent home for
  related work; it exists between the epic's first approved child and its
  merged integration PR, and after that the epic's topic continues on
  ``develop`` like any other change.

Normative rules
===============

The MUST rows are the contract once reviewed. Where a rule needs a tool that
does not exist yet, the owning issue is named in brackets.

1. **One canonical branch per epic.** The identity of an epic integration
   branch is ``epic/<slug>`` where ``<slug>`` is the value of the
   ``slug: <kebab-name>`` first body line of the epic issue. The slug is
   lowercase, kebab-cased and at most 20 characters, for the same reason
   ``AGENTS.md`` imposes it on issue titles: it is a branch name component.
   The slug is declared once, on the epic, and is immutable afterwards — a
   slug edit while children are in flight would orphan every child PR base.
   [#1591 resolves it; the branch is created by a person under branch
   protection, never pushed by an agent.]
2. **Uniqueness.** No two open epics may share a slug, and an epic's slug may
   not equal the branch name of a closed epic that still stands. The check
   reads the slug of every open epic with children against
   ``git ls-remote --heads origin``. [#1591]
3. **First cut.** ``epic/<slug>`` is created from the head of ``origin/develop``
   at the moment of creation, so that the epic branch owes ``develop`` nothing
   but its own work at the start. It is a protected, permanent-for-its-lifetime
   branch: no force-push, no deletion by a worker, no rewrite [#1594: branch
   protection].
4. **Child base is exclusive.** A PR whose head is a child branch of an epic
   must have base ``epic/<slug>`` of its own epic, and no other base [R2, R5;
   enforced by #1591]. A PR into an epic branch is retargeted by a person,
   never rewritten by an agent.
5. **Children start from current epic head.** A child branch is created from
   the tip of ``epic/<slug>`` at creation time, and if the epic moved on while
   the child was open, the fix is a merge of the epic head into the child
   [R12]. Rebasing a branch that is open for review stays forbidden —
   ``AGENTS.md`` already forbids it and this contract does not touch that.
6. **Independent issues are unaffected.** An issue with no epic parent keeps
   the current rule exactly: branch from ``origin/develop``, base ``develop``
   [R1]. Epic branches must not become a reason to route unrelated work.
7. **Cross-epic dependencies resolve in the target.** A dependency of an epic
   child is satisfied only when the dependency's change is an ancestor of the
   branch the child's work will land in. A dependency closed on GitHub but not
   in ``develop`` (or in the epic head) is unsatisfied [R8]. A dependency
   merged only into another epic's branch is unsatisfied, and the correct fix
   is to get it into ``develop``, not to merge the other epic branch.
8. **Readiness.** An epic integrates when R7 holds. Formally: for every
   required sub-issue of the epic, the sub-issue's PR is merged into
   ``epic/<slug>``; for every issue the epic depends on outside itself, the
   dependency's merge commit is an ancestor of both ``origin/develop`` and the
   epic head; the epic head passes the checks of `The CI contract`_ after the
   last child merge; and every decision the epic owes is answered.
   [#1593 implements this as a check.]
9. **Integration PR.** Exactly one PR per epic moves the epic into
   ``develop``: head ``epic/<slug>``, base ``develop``, merged as a merge
   commit, human-approved and human-merged. It is the epic's single release
   note entry, and it is where the release semantics of #1577 are decided: the
   class and the ``!`` marker of that one title decide what the epic consumes
   and whether it breaks [#1593, #1594; classification itself is already
   enforced by ``pr-classification.yml``].
10. **Anatomy of a merge.** Merge ancestry is preserved so that #1577 can read
    the history: the epic branch's merge commits keep each child PR title, the
    integration merge keeps the epic's title, and the commit body on
    ``develop`` stays one line as measured by #1580. Squashing the epic branch
    before integrating is not allowed — it erases the per-child titles the same
    way a folded commit message erases a ``BREAKING CHANGE:`` footer.
11. **After integration: retire the branch.** On the merge of the integration
    PR, ``epic/<slug>`` is deleted by the person who merged, in the same act,
    and the epic is closed. Deletion is safe precisely because the merge commit
    keeps the epic's ancestry reachable from ``develop``. A person may choose to
    keep the branch for an open follow-up; then the epic stays open and R10
    does not fire. An agent never deletes a permanent branch
    (``AGENTS.md`` already forbids it, and this contract keeps that).
12. **Nested epics integrate upward, then once outward.** A sub-epic integrates
    into its parent's branch under the same rules [R9]; exactly one branch of a
    nested tree ever has ``develop`` as a base — the outermost epic's. This
    keeps rule 9 true for the whole tree: one PR, one release note entry per
    top-level feature.
13. **Closed epics are closed.** A closed epic takes no new children [R10,
    R11]. Follow-up work on the same topic is a new top-level issue from
    ``develop``, and if it wants an epic of its own it declares a new slug.
14. **Claims carry the target.** A claim comment of a child issue records the
    integration target the scheduling decision used, so that a later run reads
    the target from the claim instead of re-deriving it from a possibly-edited
    epic body [#1592]. The claim board's existing shape (one comment per
    issue/client, ``status: wip``, the pinned board issue) is not changed.
15. **Human authority is untouched.** No row of the decision table and no rule
    above grants an agent an approval, a merge, a branch creation, a branch
    deletion, a retarget, a label change or a protection change. The rows that
    say "refused" name a person as the actor that resolves the refusal.
16. **Bootstrap before enforcement.** While this epic is itself in flight, its
    own children follow R3 — they run under the currently approved policy and
    target ``develop`` — because enforcing an epic branch on the epic that has
    to build the enforcement is a cycle. Enforcement becomes active for other
    epics when #1594's rollout lands; this epic's own integration PR is the
    last act of the bootstrap and is the demonstration that R7 works.

Bootstrap and migration
=======================

Migration of existing work
--------------------------

Measured against the branch list, the migration is small and it is all
name-based, which is why it is expressible without touching history:

* **Nothing to move.** No epic branch exists and no child PR is currently
  based on one, so no open PR needs retargeting. Verified: no ``epic/*``
  branch in ``git ls-remote --heads origin``, and every open bot PR in this
  run's check targeted ``develop``.
* **The two epics already in flight stay on ``develop``.** Epic #1442
  (security audit) has seven open native sub-issues and its children merge into
  ``develop`` today; epic #1588 is bootstrapping under rule 16.
  Neither is migrated: converting an in-flight epic mid-work would rewrite the
  base of every open child PR, which is the disruption the epic objective
  forbids. They adopt the contract at their next un-started child, if the
  epic is still open when #1594 turns enforcement on.
* **Epic branches created after #1594 are the only ones ever created.** An
  epic whose children are already merged needs no branch retroactively — the
  branch would have no head to integrate.
* **Existing branch names are left alone.** The 288 measured branches are not
  renamed or deleted by this migration; a housekeeping sweep of merged
  branches is a separate concern (#1056 and #1018 own adjacent parts of it) and
  a rename of a merged branch cannot destroy ancestry but also cannot help
  readiness. What changes is forward-looking: an epic child branch of the
  ``ao/<topic>/issue-<N>`` shape gets its base from R1/R2, not its name.
* **Legacy epics without ``slug:``.** R3 handles them: no branch, children on
  ``develop``, and the slug is declared when the epic's next child is
  scheduled; ``scripts/epic_rollout.py`` reports the owed ``declare-slug`` action
  with ``person`` as its actor, so the debt is visible instead of assumed. This
  is why the slug lives in the epic body and not only in a
  branch name: the declaration is the thing a tool can read from an issue
  alone, which is what an agent after a context loss has.
* **Rollout safety.** Enforcement is introduced in advisory mode first, exactly
  as #1580 introduced title enforcement, for the same reason: 99 % of the
  existing branches and every PR already open predate the rule, and nobody
  should have a base changed under their feet. The two dates and the exemptions
  are one reviewed file, ``scripts/epic_rollout.json``, read by
  ``scripts/epic_rollout.py`` — the tool that turns this table into the dry-run
  migration plan. Like #1580's, the date is overridable per deployment
  (``MRMAP_EPIC_ROLLOUT_STRICT_FROM``), because the day a rule stops advising is
  the deployment's call and not the rule author's. [#1594 — delivered]

The CI contract
---------------

This is the constraint most likely to sink the design if it is handled late,
and it is why the gap measured above had to close before the first child PR.
#1594 closed it; the bullets below say what has to stay true.

* A child PR into ``epic/<slug>`` must run the same required checks as one into
  ``develop``. The trigger lists of ``quality-assurance.yml``,
  ``script-tests.yml``, ``codeql.yml`` and ``pr-classification.yml`` were
  restricted to ``[master, develop]``; #1594 added ``epic/**`` to all four, so a
  child PR now runs the QA suites, the ``scripts/`` suites, CodeQL and the title
  classification exactly as a PR into ``develop`` does. This is an *addition* of
  coverage, and it is explicitly not a weakening: no path in any of these
  workflows may skip a check for a branch, an author or a label. The four files
  are named in ``scripts/epic_rollout.json`` and each one's ``pull_request``
  trigger is re-read by ``scripts/test_epic_rollout.py``, which CI runs — so a
  later edit that drops the pattern out of one of them fails a check instead of
  quietly returning the gap this bullet measured. [#1594 — delivered]
* **Migration-graph and merge-queue checks must know the epic head.** The
  one-leaf-per-app guard (#1157, ``scripts/migration_graph_smoke.py``) compares
  (branch ∪ develop); against an epic branch it must treat the epic head as the
  integration target, or two epics each adding a migration will look green.
  The epic branch is where two children's migrations collide first, which is
  the point.
* **Epic-internal CI costs are real and stay real.** Six children cost six
  child-CI runs plus one integration run. The saving the epic objective offers
  is not in check count but in *what is checked where*: the expensive
  documentation and release pipelines move to release-only (#1589), so the
  per-child run keeps quality gates and drops publication work. What the
  rollout may not do is let the per-child run grow; the acceptable chain time
  per epic is a measurement #1595 takes end to end before enforcement turns
  strict.
* **The integration PR re-runs everything against current ``develop``.** That
  is the final integration retest of the epic objective: an epic branch that is
  green against a three-week-old ``develop`` has proved nothing about the
  state it is about to create.

Open questions
==============

Named rather than silently decided, each with the issue that owns it and the
recommendation this page proposes:

* **Who cuts the branch?** Decided by #1594 as recommended: a person, from the
  repository's branch settings, once per epic, when the epic's first child is
  approved and claimed; ``AGENTS.md`` states it and ``scripts/epic_rollout.py``
  emits ``create-epic-branch`` with ``actor: person`` rather than letting an
  agent act. The branch-protection settings themselves are a maintainer act
  GitHub does not let a tool assert, so the plan also owes a
  ``protect-epic-branch`` action for the same person and the suite pins the
  statement in ``AGENTS.md`` rather than the remote settings. [#1594 — decided]
* **Does a child PR get the merge queue?** Decided by #1594 as recommended: no
  for child PRs, yes for the integration PR into ``develop``. The decision is
  recorded in ``scripts/epic_rollout.json`` under ``branch_lifecycle.merge_queue``
  so it is readable next to the protection rule it belongs to, and the
  implementing act is the branch protection of ``epic/<slug>``. [#1594 — decided]
* **Does an epic get one version or do its children?** The baseline of #1578
  (``release-versioning-baseline.rst``) and its ``Q4`` are still Pending. Under
  this contract the answer is structurally the same either way — the epic's
  integration PR is the single candidate event — so the contract does not
  depend on ``Q4``, which is the property that lets this epic and #1577 proceed
  independently. Owner: #1577.
* **Label vs native parent for "is an epic".** Recommendation: the native
  parent/sub-issue relation is the fact, and the ``Epic`` label is only a
  triage view, matching the rule ``AGENTS.md`` already states for sub-issues
  versus title prefixes. Risk accepted: the native relation cannot be enforced
  by an agent (only a person labels and links), so the check in #1591 must
  refuse a child whose *body* names a parent that has no native link, rather
  than guess one. Owner: #1591.
* **Slug uniqueness across *closed* epics.** Recommendation: a slug may be
  reused once its branch is deleted and its epic closed, because R10 forbids
  new children on a closed epic; the risk of reading an old branch as current
  is closed by the "branch still stands" clause of rule 2 rather than by
  reserving slugs forever. Owner: #1591.
* **Hotfix into a stale epic branch.** Decided by #1594 as recommended: it is
  R8-shaped — the epic integrates, or the fix goes to ``develop`` and the epic
  merges ``develop`` — and an agent does not choose. The choosing is a question
  for a person through ``scripts/wip ask``: an agent that finds itself needing a
  change that only exists on ``epic/<slug>`` asks rather than picking a base,
  because both lawful answers are a person's call. [#1594 — decided]

Handoff
=======

What each follow-up issue must read from this page:

* **#1591** (branch resolution and PR target enforcement) — decision rows
  R1-R6, R8-R12, rules 1, 2, 4, 5, 6, 7, 13; the open question about the
  native relation.
* **#1592** (AO integration and claims) — rules 14, 16 and the requirement that
  a claim names the integration target; ``next_eligible.py`` is already
  epic-scoped and read-only, so #1592 extends its output rather than replacing
  it.
* **#1593** (readiness and final integration checks) — decision row R7, rules 8,
  9, 10, 12, and the ancestry definition of a satisfied cross-epic dependency.
* **#1594** (rules and rollout) — rules 3, 11, 15, 16, `The CI contract`_, the
  advisory-then-strict rollout, and the branch-protection and merge-queue
  questions.
* **#1595** (end-to-end validation) — the whole table, validated offline plus on
  a throwaway branch pair in an isolated validation, and the CI-cost budget of
  `The CI contract`_.

Reproducing the audit
=====================

Every measurement above, from the repository root. All read-only toward GitHub.

.. code-block:: text

   # no epic branch exists; the namespace is free
   git ls-remote --heads origin | sed 's#.*refs/heads/##' | grep -c '^epic/'   # 0

   # the only target check runs only on a base of master
   sed -n '/^on:/,/^jobs:/p' .github/workflows/branch-policy.yml

   # CI triggers carry epic/** — the coverage #1594 added to close the gap
   grep -n 'branches:' .github/workflows/quality-assurance.yml \
       .github/workflows/script-tests.yml .github/workflows/codeql.yml \
       .github/workflows/pr-classification.yml

   # the rollout plan itself, and the policy dates behind it
   python3 scripts/epic_rollout.py --dry-run
   python3 -m json.tool scripts/epic_rollout.json

   # the native hierarchy is populated for the epic of this issue
   gh api repos/mrmap-community/mrmap/issues/1588/sub_issues \
     --jq '.[] | "#\(.number) \(.title)"'

   # the eligibility screen is epic-scoped and stateless
   python3 scripts/next_eligible.py --help

   # the claim tool holds no integration target today
   grep -c epic scripts/wip

   # cross-epic dependency hazard: the closure of one epic's approved issues
   gh issue view 1468 --json body --jq .body
