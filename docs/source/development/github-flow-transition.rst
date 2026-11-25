.. _github-flow-transition:

======================
GitHub Flow transition
======================

Status: prepared for maintainer review under #1592, **cutover not approved or
performed**. Snapshot: 2026-11-25, against ``origin/develop`` at ``e2c76a15e``.
Live settings and in-flight work were read only. Re-read the inventory before
acting; an empty assignment or old heartbeat is not evidence that work is free.

The canonical workflow is :doc:`github-flow`. #1593 owns deletion of obsolete
epic/project-sync tooling after the approved transition; #1753 owns claim and
eligibility retirement after owners reconcile active work. No replacement
scheduler, helper, feature flag or provenance mechanism is introduced.

Urgent target-check cutover
===========================

Two different deadlines existed: ``scripts/epic_rollout.json`` named
2026-12-15, while ``scripts/epic_branch.py`` named 2026-12-21. This change cancels
both automatic activations: auto remains advisory even with old date environment
overrides. Explicit strict mode remains solely for reproducing legacy diagnostics
until #1593 removes the tools; their branch answers are not instructions for new
work. Historical dates remain in the manifest for evidence.

``pr-target-policy.yml`` retains the existing **Validate PR target** context as
a retirement notice, without invoking an epic target resolver. The effective
required-check lists below do not require this context. Keeping its name avoids
stranding an unobserved consumer until the operator rechecks settings and #1593
removes the obsolete workflow. It is not QA evidence. Existing master-edge
``branch-policy.yml`` and all QA/security/release workflows remain intact,
including ``epic/**`` coverage for legacy branches.

A person must merge the reviewed cutover before **2026-12-15**. A local patch
cannot cancel enforcement on the live default branch or in older checkouts.
External callers explicitly using strict mode must stop treating it as authority;
do not stop or rewrite an active worker to accomplish this.

Effective protection and rights audit
=====================================

The REST rules endpoints, rather than just classic branch protection, were read.
Classic ``branches/develop/protection`` returns 404 while rulesets are effective;
that response does not mean develop is unprotected.

.. list-table:: Live rulesets
   :header-rows: 1
   :widths: 20 35 45

   * - ID
     - Applies to
     - Effective behavior / proposed action
   * - 27451777, 27450482
     - Both exact develop and master
     - Duplicate deletion/force-push bans; no bypass actors. Retain both until
       an administrator reviews equivalence; consolidation is optional.
   * - 26961802
     - Exact develop (name is ``develop/**``)
     - Deletion/force-push ban, seven checks, one approval, Code Owner review,
       stale-review dismissal and resolved threads required.
   * - 26682013
     - Exact master
     - Same seven checks and review rules, plus merge queue. Preserve release
       behavior and investigate source-policy check settings separately.
   * - 26682016, 26682018, 26682020
     - bugfix/**, feature/**, housekeeping/**
     - Deletion/force-push bans; human user ID 17874616 bypasses these. Do not
       delete or rewrite protected task branches automatically.
   * - 26682015
     - gh-pages
     - Deletion/force-push bans, no bypass. Outside this cutover.

Both permanent branches require these exact contexts:
``acceptance-tests``, ``backend-coverage``, ``frontend-tests``,
``pre-commit-checks``, ``unit-tests``, ``SonarCloud Code Analysis`` (integration
12526), and ``sonarcloud``. The other six contexts use integration 15368
(GitHub Actions). No check is removed or renamed by this change.

Neither ``Validate PR target`` nor ``Validate Branch Policy`` is currently a
required context. CodeQL and repository-tooling jobs run in workflows but are
also absent from the live required list. Proposal for an administrator: assess
adding the existing security/tooling contexts after proving they run for each
applicable PR/merge-group event; do not require a conditionally absent job or
remove current checks to make a PR mergeable. Preserve the master source rule;
coordinate it with the release candidate path of #1577 rather than changing
release implementation here.

Develop and master rulesets permit the human user 17874616 (jokiefer) to bypass
checks/reviews, but the overlapping permanent-branch rulesets still ban deletion
and force pushes without bypass. Review dismissal is restricted to user IDs
17874616, 1188234 and 210026995. Actual collaborator roles: armin11, jokiefer and
karlbrink are admins; mrmap-agent-bot has write, with no admin/maintain role.
No repository teams were returned. Other collaborators have write. These roles
are access evidence, never permission for an agent to review or merge.

Actions currently defaults to **write** workflow permissions and
``can_approve_pull_request_reviews=true``. Proposal: an operator inventories
release/project-sync consumers, then explicitly confirms disabling Actions PR
approval and using read defaults with narrowly scoped workflow permissions.
Retain every release permission actually needed. This patch changes no token,
role, bypass actor, repository setting or ruleset.

Per-item work inventory and plan
================================

All five open PRs are non-Draft, have no assignees and target develop already.
Keep each PR, its branch, commits and reviews in place; assignment is a human
coordination action, not automatic reassignment.

.. list-table:: Open PRs
   :header-rows: 1
   :widths: 12 34 54

   * - PR / issue
     - Head
     - Owner action
   * - #1774 / #1474
     - agent/issue-1474
     - Keep security design review and REVIEW_REQUIRED state; human identifies
       owner and confirms the design before implementation.
   * - #1772
     - renovate/frontend-non-major-dependencies
     - Keep Renovate work and checks; human reviews dependency changes.
   * - #1738 / #1498
     - agent/issue-1498
     - Keep retention inventory and REVIEW_REQUIRED state; human confirms owner.
   * - #1732 / #1391
     - agent/issue-1391
     - Preserve active foreign worker/claim and REVIEW_REQUIRED state; coordinate
       with its owner before assignment, retargeting or cleanup.
   * - #1681
     - release-please--branches--develop
     - Keep planned release and REVIEW_REQUIRED state; #1577 human release
       process remains authoritative.

Only one remote epic branch exists: ``epic/epic-integration`` for #1588.
``compare/develop...epic/epic-integration`` reported behind by 81 commits,
**ahead by zero**, with no unique commits at audit time. No open integration
PR targets or originates from it. Proposal: leave it untouched through review;
a person may retire it only after a fresh unique-commit check and owner sign-off.
This is not authorization to delete it. No temporary epic-target exception is
needed for the observed open PRs. If a previously unobserved owner needs an
existing arrangement to finish, record the branch, PRs, owner, reason and explicit
retirement condition here before accepting that temporary exception.

Open native epics, all unassigned, each retain their parent/sub-issue links:

* #1775 observability: no epic branch; future children use develop.
* #1687 systemtest-bdd: no epic branch; future children use develop.
* #1612 runtime-memory: no epic branch; future children use develop.
* #1589 auto-docs: no epic branch; coordinate docs build policy without editing
  documentation CI here.
* #1588 epic-integration: retain its existing branch pending owner review;
  #1592, #1593 and #1753 use develop under their revised issue scopes.
* #1536 csw-client: no epic branch; future children use develop.
* #1497 retention: preserve #1738 review; other children use develop.
* #1442 hardening: preserve #1774 review; other children use develop.
* #1387 Celery performance: preserve #1732 and its worker; other children use develop.
* #1291 MapContext v2: no epic branch; future children use develop.
* #1280 MapContext v1: no epic branch; future children use develop.
* #1104 operational events: no epic branch; future children use develop.
* #727 roles: no epic branch; future children use develop.
* #681 assisted monitoring: no epic branch; future children use develop.
* #669 discovery: no epic branch; future children use develop.

All five open PRs were non-Draft, unassigned, and based on develop. Keep their
existing branches, commits, reviews and base; no retarget is needed:

.. list-table:: Per-PR transition plan
   :header-rows: 1
   :widths: 16 36 48

   * - PR / issue
     - Head
     - Owner action
   * - #1774 / #1474
     - agent/issue-1474
     - Preserve the SSRF design review; request human assignment before resuming.
   * - #1772
     - renovate/frontend-non-major-dependencies
     - Keep Renovate's existing dependency review and required checks.
   * - #1738 / #1498
     - agent/issue-1498
     - Preserve retention inventory review; request human assignment before resuming.
   * - #1732 / #1391
     - agent/issue-1391
     - Preserve performance review and reconcile with the active claim owner.
   * - #1681
     - release-please--branches--develop
     - Preserve release planning and its human decision under #1577; no release
       action is authorized by this transition.

All five open PRs target develop, have no assignees, and are not Drafts:

.. list-table:: Per-PR transition plan
   :header-rows: 1
   :widths: 16 40 44

   * - PR / issue
     - Existing head
     - Owner action
   * - #1774 / #1474
     - agent/issue-1474
     - Preserve SSRF design review; human reviewer still required. No retarget.
   * - #1772
     - renovate/frontend-non-major-dependencies
     - Preserve Renovate checks and normal human review. No retarget.
   * - #1738 / #1498
     - agent/issue-1498
     - Preserve retention inventory review; human reviewer still required. No retarget.
   * - #1732 / #1391
     - agent/issue-1391
     - Reconcile with the active claim owner before assignment; preserve review.
   * - #1681
     - release-please--branches--develop
     - Preserve the existing release planning review and #1577 controls.

These heads and their reviews remain intact. Only a person may agree a change
of base or branch cleanup after checking unique commits against develop again.
No temporary epic-target exception has been approved by this document.

The open-issue assignment search returned no assigned issues. This is planning
metadata only; it does not cancel external work. ``scripts/wip ls`` found foreign
claim #1391, client ``canvas-42a37bd494fd``, branch ``tmp-claim-origin``. Its owner
must finish/reconcile it under #1753; no claim was removed or agent interrupted.
This task also registered its own #1592 claim as ``PC-Jonas:mrmap`` under the
pre-cutover instructions; finish that lifecycle without creating a second lock.
Board #917 is historical coordination evidence, not the future merge gate.

Reproduce the read-only audit
=============================

Use an authorized host GitHub login; do not copy tokens into evidence::

   gh repo view --json defaultBranchRef
   gh api repos/mrmap-community/mrmap/rulesets
   gh api repos/mrmap-community/mrmap/rules/branches/develop
   gh api repos/mrmap-community/mrmap/rules/branches/master
   gh api repos/mrmap-community/mrmap/rulesets/26961802
   gh api repos/mrmap-community/mrmap/rulesets/26682013
   gh api --paginate repos/mrmap-community/mrmap/branches?per_page=100
   gh api repos/mrmap-community/mrmap/compare/develop...epic/epic-integration
   gh pr list --state open --limit 100 --json number,headRefName,baseRefName,isDraft,assignees,reviewDecision
   gh issue list --state open --label Epic --limit 200 --json number,title,assignees
   gh issue list --state open --search 'assignee:*' --limit 200 --json number,assignees
   gh api --paginate repos/mrmap-community/mrmap/collaborators?per_page=100
   gh api repos/mrmap-community/mrmap/teams
   gh api repos/mrmap-community/mrmap/actions/permissions/workflow
   scripts/wip ls

Inspect every returned ruleset's conditions, required contexts and bypass actors.
If a listing reaches a CLI limit, paginate before declaring the inventory complete.
Also inspect the existing Project #3 UI and installed app permissions with its
owner: repository collaborator rights do not establish every app installation's
authority, and built-in project workflow settings were not audited through REST.

Isolated demonstration and operator acceptance
==============================================

**Pending, not demonstrated.** A maintainer must name an isolated test repository
or explicitly authorize disposable resources and provide a separate human
reviewer/merger. Do not fabricate a passing demonstration from mocked tests or
merge a production PR as an experiment. Before live setting changes:

1. In that repository, set default develop and reproduce review/check protection
   using a minimal existing test check; use distinct author and human reviewer.
   Record the settings, identities and lack of author/bot bypass. Test permanent
   branch restrictions and an incorrect master source without changing MrMap.
2. Create a test issue and dependency, assign one worker explicitly, show Blocked
   manually, clear the dependency with owner agreement, then create its linked
   branch from develop and a Draft PR containing ``Closes #N``. Record URLs.
3. Show Draft, missing approval and a failing/missing check prevent merge. An
   operator can use the native merge UI/rules evaluation as evidence; do not
   bypass a rule to make the example succeed.
4. Fix the check, mark ready, have the independent human approve and merge into
   default develop. Record green checks, review, merge commit and natively closed
   issue. Show the project status and assignee/blocker manual trade-offs.
5. Record the URLs/results on #1592. Only then confirm any live Projects/access
   changes, with a before/after inventory and an operator rollback plan. Revert
   settings to the recorded prior values if the demonstration or cutover fails;
   do not re-enable mandatory epic targeting as a rollback.

Maintainer sign-off remains required for the canonical workflow, this inventory,
temporary exceptions (if any), sandbox evidence, and an explicit cutover date and
operator. Merge the urgent retirement before 15 December, then confirm the live
context no longer executes epic enforcement. #1593 may remove the compatibility
context after a fresh required-check/consumer audit; #1753 may retire claims only
after owner reconciliation. No unattended release or live-agent interruption is
part of acceptance. An unanswered decision keeps #1592 open.

Project inspection limitation
==============================

Reading Project #3 fields failed because the current host token lacks
``read:project``. No token scopes were expanded. The native configuration on the
canonical workflow page is a proposal, not a claim about installed fields or
workflows. The project owner must inspect those in the UI before cutover.

Sandbox preparation and validation evidence
============================================

The user explicitly authorized ``mrmap-community/workflow-sandbox`` on
2026-11-25, with synthetic files only, ``jokiefer`` as independent human reviewer
and merger, and deletion only after separate explicit confirmation. The public
repository was created with default ``develop``. Bootstrap files are a synthetic
``greeting.txt`` and a minimal GitHub Actions shell check; no MrMap code or
configuration was copied.

Sandbox ruleset **28088403** requires a PR, one approval, resolved review threads
and ``synthetic-check`` from GitHub Actions; it bans deletion/force pushes and
has no bypass actors. `Initial synthetic CI passed
<https://github.com/mrmap-community/workflow-sandbox/actions/runs/45645962644>`_.
This proves setup and execution, not yet the required PR/review/merge demonstration.
The user then configured bot authentication. The test issue #1 is assigned to
mrmap-agent-bot, its linked branch is ``fix/issue-1-greeting``, and Draft PR #2
was opened by mrmap-agent-bot. The issue recorded a manual blocked reason.
No review/merge has been performed by the agent. Live MrMap settings are unchanged.

Local validation: ``test_epic_branch.py`` passed 104/104;
``test_epic_rollout.py`` passed 99/99; ``test_docs_build.py`` passed.
Reverting each auto-mode change makes its deadline/override regressions fail;
restoring the former workflow makes the retired-enforcement regression fail.
The full ``scripts/check_repo_tooling.sh </dev/null`` run passed 39/40 suites.
The remaining ``test_xml_parse_guard.py`` failure scans the pre-existing ignored
``backend/.venv/lib/python3.14/site-packages/lxml/html/__init__.py`` and flags
third-party text serialization. No virtualenv or unrelated guard was changed.
A restricted first run also could not create local fixture sockets; the full
run with local socket access resolved those environment failures. No application
Compose stack was created. Full Sphinx HTML validation was not run; targeted
offline portal validation passed.

`Sandbox PR #2 <https://github.com/mrmap-community/workflow-sandbox/pull/2>`_
was created as a Draft by mrmap-agent-bot from the native linked branch.
`The deliberately failing required check
<https://github.com/mrmap-community/workflow-sandbox/actions/runs/45646305831>`_
left it BLOCKED with REVIEW_REQUIRED. The bot restored the valid greeting,
added only a synthetic note, removed the manual blocked label while retaining
assignment, and marked the PR ready. Independent human review/merge and native
issue closing are pending; jokiefer received the PR URL. This evidence does not
claim the merge/closing acceptance criterion has passed yet.

The full tooling run passed 39 of 40 suites. The unrelated XML parse guard scans
the local untracked ``backend/.venv`` and reports lxml's own text serialization;
no application XML code changed here. Socket-based fixture tests require running
the suite outside the restricted execution sandbox. Full Sphinx was not run
because no host Sphinx environment is available; the targeted portal structural
suite passed. No application Compose stack was started.
