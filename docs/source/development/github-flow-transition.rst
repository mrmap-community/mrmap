.. _github-flow-transition:

======================
GitHub Flow transition
======================

The #1592 cutover was approved and merged in PR #1790 on 2026-11-25 at
15:39:41 UTC (16:39:41 Europe/Berlin). Its original audit and sandbox evidence
remain below as historical measurements. The canonical workflow is
:doc:`github-flow`. The following retirement patch is prepared for review under
#1593; its removal takes effect only when a person merges it into develop.

Agent-independent handoff under #1753
=====================================

The maintainer explicitly authorized full retirement of the repository capacity
script and its tests on 2026-11-25, without a compatibility tool or replacement
script. Resource management, concurrency and workspace isolation belong to the
operator/external execution environment. Unknown external consumers do not keep
that script alive indefinitely. This patch changes source and documentation;
it does not stop workers, change host limits, revoke credentials or delete work.

Known consumers and transition before removal
---------------------------------------------

* ``scripts/git_checks.py`` called the capacity script before optional Docker
  checks. Remove that call and its obsolete test fixture/assertion while retaining
  stack isolation, cleanup and failure propagation. The visible checkout has no
  executable pre-commit/pre-push hook. External hook users must put admission and
  concurrency controls in their executor before starting further Docker checks
  on the new revision. Do not update a running job's checkout or limits.
* ``scripts/low_memory_deployment.json`` and its documentation consistency suite
  pointed at the script as admission authority. Update them to name the operator/
  external execution environment; keep all application memory modes, measurements
  and Compose ceilings unchanged. Historical thresholds are measurements, not
  current repository admission rules.
* Root/backend instructions, four optional skills, the low-memory runbook,
  Compose/test-memory guides and CI/tooling comments invoked or described the
  script. Replace active commands with the external ownership boundary. The
  historical capacity report remains evidence, explicitly retired.
* The earlier AO integrations and nightly runners described in the historical
  capacity report are external consumers, not services installed by this
  repository. AO is retired. Their owners must remove the old command from any
  remaining launcher configuration at a job boundary and configure ordinary
  process/container limits and concurrency externally first. This session cannot
  inspect or certify the remote hosts or their installed limits. No running
  protection is disabled here; source retirement is not a remote-host migration.

Before adopting this revision, an executor owner checks effective host/container
limits, memory/disk headroom and concurrent jobs, records the selected limits and
single-worker policy in that environment, and changes any launcher/hook command
at a safe job boundary. If that handoff is not ready, finish the running job on
its existing checkout; do not start new jobs on the new revision. No new MrMap
script performs or supervises this work.

Explicit temporary legacy exception
------------------------------------

.. note::
   **Resolved 2026-11-25 (#1794).** The maintainer confirmed the #1391
   implementation as finished and PR #1732 as merged (merge commit ``9bd7cbb3e``);
   the temporary exception documented below is no longer required. Its five reserved
   files (``scripts/wip``, ``scripts/next_eligible.py`` and their three test suites)
   were removed under #1794, the legacy claim was reconciled by a follow-up comment
   on #1391, the stale ``status: wip`` labels on #1391, #1592 and #1753 were dropped,
   and Agent Work Board #917 was closed. Everything below records the cutover-time
   state and stays as historical evidence.

The maintainer confirmed that the owner of #1391 has **not** completed the
assignment handoff. Preserve PR #1732, branch ``agent/issue-1391``, its worktrees
``/srv/openhands/projects/mrmap-agent`` and
``/home/openhands/projects/mrmap-canvas-1391``, and claim
`7163745678 <https://github.com/mrmap-community/mrmap/issues/1391#issuecomment-7163745678>`_
(client ``canvas-42a37bd494fd``, branch marker ``tmp-claim-origin``). Do not
interrupt the worker, edit its claim or force a migration. Existing work may
finish using its legacy workflow; new work follows :doc:`github-flow`.

Accordingly ``scripts/wip``, ``scripts/next_eligible.py`` and their three suites
remained solely for that exception until #1794 removed them on 2026-11-25. They were never prerequisites or merge gates
for new work. Retirement condition: #1391's owner confirms the handoff/finish,
reconciles its claim, and confirms no remaining legacy consumer; then a reviewed
cleanup removes those five files. Maintainer sign-off on #1753/#1588 remains
explicit; this exception must not be described as completed claim retirement.
Board #917, heartbeat comments and WIP/approval/pause labels are preserved as
history and existing human decisions. No label, board, claim or PR is cleaned
up automatically. The decision-request tool is made independent of the claim
module while continuing to ignore historical machine comments as answers.

Remote branch and external-service inventory
---------------------------------------------

The live branch audit at develop ``1de96ed08`` found **two** ``ao/*`` branches
and **one** ``epic/*`` branch, rather than the historical 153 AO branches.
:download:`Per-branch SHAs, ancestry and patch-equivalence evidence
<evidence/github-native-legacy-branches.csv>` records the current snapshot:

* ``ao/mrmap-1445/issue-1445-admin-only-system-api``: six commits ahead, 308
  behind. Of the non-merge patches, three are patch-equivalent and one is unique.
  Preserve for owner review; ancestry alone cannot declare it superseded.
* ``ao/mrmap-1848/issue-1530-etf-retirement``: three commits ahead, 308 behind,
  all three non-merge patches unique. Preserve the rescued work and request an
  owner comparison before proposing any cleanup.
* ``epic/epic-integration``: zero ahead, 90 behind; merged by ancestry. Preserve
  it until a person separately authorizes deletion after rechecking.

The open PRs remain #1774, #1772, #1738, #1732 and #1681, all based on develop;
none uses those three legacy heads. The only live claim found is #1391; board
#917 also reports a stale WIP label on closed #1592. Both remained untouched at
cutover time; both were reconciled on 2026-11-25 under #1794 (claim answered by a
follow-up comment, labels dropped, #917 closed with a pointer to this workflow).
Remote AO/OpenHands services, external launchers and credentials are outside
this checkout's visibility; their state is **unknown**, not certified stopped.
The maintainer's instruction that AO is retired supersedes old AO operating
instructions. Re-read branch heads, open PRs and owner decisions before any
manual cleanup. Do not delete branches, revoke credentials or interrupt agents
without separate explicit authorization.

Reproduce the branch evidence with ordinary Git: ``git ls-remote --heads origin
'refs/heads/ao/*' 'refs/heads/epic/*'``, fetch those heads, then use ``git rev-list
--left-right --count <develop-sha>...<branch-sha>`` and ``git cherry
<develop-sha> <branch-sha>``. Patch equivalence does not authorize deletion.

Tool retirement under #1593
===========================

Rechecked against ``origin/develop`` at ``631c2ca7a`` on 2026-11-25:

* Effective rules for develop and master still require the same seven QA/Sonar
  contexts listed below; neither requires **Validate PR target** or the project
  sync job. No ruleset/check setting needs removal before deleting those jobs.
  Recheck before merge if an administrator changes the rules in the meantime.
* The same five open PRs below target develop; none uses an epic head/base.
  The only epic branch, ``epic/epic-integration``, has zero commits ahead of
  develop. It is left intact. No branch depends on the removed resolver,
  manifest or dry-run engine in the observed inventory.
* All tracked consumers of the retired tools are their workflows/tests and the
  historical documents below. Active contributor/agent references are reconciled.
  Unknown external installations are not migrated or interrupted; old evidence
  can be read with ``git show 631c2ca7a:<path>``. No helper replaces these tools.
* **Retained coverage:** QA, CodeQL, script-tests and PR classification keep
  ``epic/**`` PR triggers as protection for existing arrangements. This does not
  require an epic branch for new work. An operator may review coverage removal
  only after confirming no legacy PR/owner still needs it; no coverage is removed
  in #1593. All QA/security/release workflows and the small master source-policy
  workflow remain byte-identical to the base revision.
* The live workflow inventory reported CodeQL as ``disabled_manually``. This is
  a pre-existing operator setting, not a source change or a claim that security
  analysis passed. The operator should review that setting separately; this
  patch neither enables nor disables workflows through the API.

The retired surface contains 11 files and 6,583 physical lines before this
change, zero files/lines afterward. No replacement tooling or dependency is added:

.. list-table:: Retired files (physical lines)
   :header-rows: 1
   :widths: 70 15 15

   * - Path
     - Before
     - After
   * - ``scripts/epic_branch.py``
     - 1598
     - 0
   * - ``scripts/test_epic_branch.py``
     - 949
     - 0
   * - ``scripts/epic_rollout.py``
     - 891
     - 0
   * - ``scripts/epic_rollout.json``
     - 42
     - 0
   * - ``scripts/test_epic_rollout.py``
     - 783
     - 0
   * - ``scripts/epic_integration_dryrun.py``
     - 1057
     - 0
   * - ``scripts/test_epic_integration_dryrun.py``
     - 935
     - 0
   * - ``scripts/sync_project_overview.py``
     - 199
     - 0
   * - ``scripts/test_sync_project_overview.py``
     - 46
     - 0
   * - ``.github/workflows/pr-target-policy.yml``
     - 33
     - 0
   * - ``.github/workflows/project-overview-sync.yml``
     - 50
     - 0

The suite runner discovers ``scripts/test_*.py`` automatically, so its invocation
and the script-tests workflow need no replacement list. Removing these four
suites leaves 36 suites. Historical ADRs, scenario JSON and recorded results stay
as evidence, with explicit notices that their commands no longer run on develop.

Native Projects handoff
------------------------

The removed sync imported issues and derived **Development Phase** and **Agent
Status**. Its native/manual replacement is documented in :doc:`github-flow`:
use Parent issue, Sub-issue progress, Status, Assignees and Labels; manually add
items and maintain blocked/review states where built-in workflows are insufficient.
There is no readiness or approval inference, no custom status authority and no
new script, token or synchronization service.

Project #3 inspection still fails for lack of ``read:project`` scope. Its live
fields/views/workflows are therefore **unverified**, not claimed configured.
An owner can follow the UI handoff without granting the agent more access:

1. Preserve all project items, views, old custom fields and their values. Inspect
   the native fields/views and use the mapping on the canonical workflow page.
2. After this PR merges, confirm old queued/running project-sync jobs have
   finished before relying on manual Status updates. The audit saw queued run
   `45647950421 <https://github.com/mrmap-community/mrmap/actions/runs/45647950421>`_.
   That run subsequently completed successfully. Recheck at merge because issue
   events can enqueue more runs until the workflow is removed. Deleting the
   workflow does not cancel existing runs. No run is cancelled here.
3. Add/update items manually, or use available native auto-add and Done workflows;
   do not enable Status-to-issue-close behavior. This meets daily planning needs
   without reproducing the derived fields. A project setting change needs the
   owner's confirmation; no settings are changed by this patch.
4. Keep ``MRMAP_PROJECTS_TOKEN`` and any shared credentials. Removing this
   consumer grants no permission to delete secrets, revoke access, delete fields
   or clean up project data. Any later cleanup needs its own consumer inventory.

Claims/eligibility and host-resource guards remain owned by #1753 until their
owners reconcile active work. No foreign claim or live agent is changed.

Validation
-----------

The retained master-policy shell step was executed directly with three synthetic
event environments: same-repository develop succeeds; same-repository task branch
and fork develop both fail. The workflow is unchanged. The native issue-to-develop
review/check/merge/closing demonstration remains the completed #1592 sandbox
record below; #1593 does not reuse or delete that sandbox. Targeted portal
structural validation passes. ``scripts/check_repo_tooling.sh </dev/null``
passed 35 of the remaining 36 suites. The unchanged XML parse guard also scans
the local untracked ``backend/.venv`` and flags lxml's own text serialization,
the same workspace-only failure recorded under #1592. Running that unchanged
XML suite against a temporary clean local clone of this commit passed all 38
checks; the temporary clone was removed afterward. Validator retirement
passes with 93 checks (Docker skips are reported by that suite). No application,
schema or migration changed and no Compose stack was started.

Historical #1592 audit and transition plan
==========================================

Snapshot: 2026-11-25, against ``origin/develop`` at ``e2c76a15e``.
Live settings and in-flight work were read only. The measurements below do not
supersede the retirement audit above or authorize changes to live settings.

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

The open-issue assignment search returned no assigned issues. This is planning
metadata only; it does not cancel external work. ``scripts/wip ls`` found foreign
claim #1391, client ``canvas-42a37bd494fd``, branch ``tmp-claim-origin``. Its owner
must finish/reconcile it under #1753; no claim was removed or agent interrupted.
This task also registered its own #1592 claim as ``PC-Jonas:mrmap`` under the
pre-cutover instructions; that own claim was released when PR #1790 became ready
for review. The foreign claim remains untouched.
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

Inspect every returned ruleset's conditions, required contexts and bypass actors.
If a listing reaches a CLI limit, paginate before declaring the inventory complete.
The claim listing of the cutover audit ran through the then-current
``scripts/wip ls``, retired with its tool under #1794; the claim it found is
recorded above and needs no re-run.
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

PR #1790 completed the #1592 cutover before 15 December. The #1593 retirement
audit above rechecks the required contexts and consumers before removing the
compatibility workflow. Remaining project/access settings stay operator-owned;
#1753 may retire claims only after owner reconciliation. No unattended release
or live-agent interruption is authorized by either change.

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
Compose stack was created. Full Sphinx was unavailable on the host; targeted
offline portal validation passed and the strict CI build passed as linked below.

`Sandbox PR #2 <https://github.com/mrmap-community/workflow-sandbox/pull/2>`_
was created as a Draft by mrmap-agent-bot from the native linked branch.
`The deliberately failing required check
<https://github.com/mrmap-community/workflow-sandbox/actions/runs/45646305831>`_
left it BLOCKED with REVIEW_REQUIRED. The bot restored the valid greeting,
added only a synthetic note, removed the manual blocked label while retaining
assignment, and marked the PR ready. Independent human approval by jokiefer
was recorded at 15:34:49 UTC.
jokiefer then merged the PR at 15:36:16 UTC (16:36:16 Europe/Berlin), merge commit
``72481bb9b749bb0db706db6fa4beb09ce8421d90``. GitHub reports linked
`issue #1 <https://github.com/mrmap-community/workflow-sandbox/issues/1>`_ closed
at 15:36:18 UTC. The default-branch native issue-closing demonstration passed.
No agent approved or merged the PR; no sandbox protection bypass was configured.

The main PR's `strict portal build passed in GitHub Actions
<https://github.com/mrmap-community/mrmap/actions/runs/45646651293>`_, including
the Sphinx build that was unavailable on the host. The compatibility target
context also passed without invoking epic enforcement.

The main PR's `complete repository-tooling suite passed in GitHub Actions
<https://github.com/mrmap-community/mrmap/actions/runs/45646650928>`_. This isolates
the one local XML-guard failure to the development workspace's untracked virtualenv.
