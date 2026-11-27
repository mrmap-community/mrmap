.. _github-flow:

===========
GitHub Flow
===========

One small, independently safe issue and pull request targets ``develop``, the
repository's default branch. Epics group native sub-issues; they impose no
branch, stack or readiness-check requirement. This workflow supersedes the
mandatory epic branch contract under #1592. Existing work follows the reviewed
:doc:`github-flow-transition` until its owner agrees a transition.

The contribution loop
=====================

1. A human or external coordinator explicitly assigns one worker. Check native
   issue dependencies, assignees, linked branches/PRs and open Draft PRs before
   starting. Keep the single-worker model; if ownership conflicts,
   ask the owners on the issue. Assignees and dependencies are planning signals,
   not atomic locks or automatic merge gates. Approval and pause labels remain
   human-owned during transition.
2. Fetch current ``origin/develop`` and create a short task branch. Use the
   issue's Development sidebar, **Create a branch**, or ordinary Git/GitHub CLI.
   For example, ``gh issue develop N --base develop --name fix/issue-N-topic
   --checkout`` creates a linked branch; use ``git switch -c`` when working
   locally and link the PR through its description. No agent service or custom
   eligibility/claim helper is a prerequisite.
3. Open a Draft PR early with an explicit ``--base develop`` and a body containing
   ``Closes #N``. Describe the problem, resulting behavior and validation. Use
   the change-class title required by :doc:`commit-classification`. Each change
   must be independently safe; split unfinished work at safe boundaries rather
   than making an epic branch or a new feature-flag framework mandatory.
4. Run the area's documented checks, including tests, migrations and translations
   where applicable. Keep Compose projects and disposable data isolated as
   documented in the repository instructions. For docs changes, run targeted
   documentation validation; #1589 owns release-event full documentation builds.
   This transition changes neither documentation triggers nor release tooling.
5. When ready, mark the PR ready for review. A person reviews and merges after
   required checks, Sonar and human review requirements are satisfied. A person
   resolves threads they raised. Agents never approve or merge their own work,
   bypass protection, force-push review branches or push permanent branches.
6. Merging the linked PR into default ``develop`` closes the issue natively when
   auto-closing is enabled. Confirm the issue closed; update project status
   manually if needed. A merge into a temporary legacy epic branch does not
   provide that default-branch closing behavior.

When blocked, record the dependency and reason on the issue, keep the PR a
Draft, and manually set project Status to Blocked. Resume only after the owner
confirms the blocker is cleared and the work is still assigned to this worker.
Silence is not permission. No watcher, scheduler or new status authority is needed.

Permanent branches and releases
================================

Keep all existing review, security, CI, Sonar, migration and release controls.
Only same-repository ``develop`` may target ``master`` under the existing small
``branch-policy.yml`` workflow. Permanent-branch synchronization uses merge
commits. Never directly push, delete, rename or force-push ``develop`` or
``master``. Release decisions and promotion remain human-owned; this workflow
does not alter :doc:`release-promotion` or authorize a production release.

Native Projects configuration
==============================

The project owner can configure the existing organization Project #3 in its UI,
preserving items and views. This is a proposed configuration, not an applied
settings change. Show **Parent issue**, **Sub-issue progress**, **Status**,
**Assignees** and **Labels**. Use native parent links for hierarchy; keep legacy
custom fields and their values as historical; field deletion requires separate
owner approval. The sync code/workflow is removed by #1593.

* **Work board**: group by Status (Todo, In progress, Blocked, In review, Done);
  show Assignees and Labels. Assignment and blocker status are manual.
* **Epic progress**: table grouped by Parent issue with Sub-issue progress;
  no derived branch or custom readiness field.
* **Review**: view of pull requests, displaying Status and Assignees; maintain
  In review manually after leaving Draft, without inferring approval.

Enable only useful built-in workflows: item added → Todo and issue closed/PR
merged → Done. Check the installed UI's available workflow choices first. Do
not enable a Status change that closes issues, and do not mark work complete
because its PR merely closed without merge. Review linked issue and PR items
separately. Native workflows do not encode every dependency/assignment state;
manual updates are the accepted trade-off. No new project script or token is
needed. After #1593 merges, confirm any already queued/running sync runs have
finished before starting manual updates. Keep the old fields and values for
history. Maintain Status in the UI: Backlog → Todo, In Progress → In progress,
Review → In review, Blocked → Blocked, Done → Done. Do not bulk-copy stale
Development Phase values. Replace the derived Agent Status column with the
existing human-owned Labels column; a label remains a planning signal.

Add an issue or PR through the project UI when assigning it, unless a native
auto-add workflow already covers it. Inspect existing project views, then add
or adapt views without deleting them. If built-in workflows are unavailable,
manual item addition and Status updates are sufficient for this contribution
loop. Keep shared Projects credentials; retiring this consumer does not
authorize deleting a secret or revoking a token another consumer might use.

GitHub references
==================

* `Creating a linked issue branch <https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-a-branch-for-an-issue>`_
  and `gh issue develop <https://cli.github.com/manual/gh_issue_develop>`_.
* `Linking PRs and default-branch issue closing <https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue>`_
  and `auto-closing settings <https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/managing-auto-closing-issues>`_.
* `Native hierarchy fields <https://docs.github.com/en/issues/planning-and-tracking-with-projects/understanding-fields/about-parent-issue-and-sub-issue-progress-fields>`_
  and `built-in project workflows <https://docs.github.com/en/issues/planning-and-tracking-with-projects/automating-your-project/using-the-built-in-automations>`_.
