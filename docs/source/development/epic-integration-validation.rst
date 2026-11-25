.. _epic-integration-validation:

=====================================================
Epic integration workflow: end-to-end validation
=====================================================

.. sidebar:: Issue #1595

   Part of epic #1588 (enforce epic-based development and integration
   workflow), issue #1595: the validation deliverable of that epic. #1590 wrote
   the contract, #1591 enforces the base rule, #1592 schedules against it,
   #1593 gates readiness, #1594 states it in the agent rules and rolls it out.
   This page is the evidence that the contract *works end to end*: the whole
   lifecycle — native epic and approved child selection, branch creation, child
   PR checks, blocker merges, readiness, the human-approved integration, and the
   standalone, external-blocker, paused, claimed, wrong-base, cancelled,
   migration-conflict and release-semantics cases — replayed in an isolated dry
   run, plus rollback and recovery, with no production effect.

   This page is a **validation record, not a tool**. The tool is
   ``scripts/epic_integration_dryrun.py``, and its offline suite is
   ``scripts/test_epic_integration_dryrun.py``.

Three kinds of statement are kept apart, as on the contract page
(:ref:`epic-integration-contract`):

* **measured** — a command was run and its result is quoted.
  `Reproducing this validation`_ gives every command.
* **validated** — the dry run observed a behaviour that matches a row of the
  decision table. Every validated line names the check id that observes it, so a
  reader can re-run the check rather than trust the sentence.
* **not validated here** — what this issue deliberately leaves to the issues that
  own the mechanism, and why the gap is stated rather than papered over.

Status of this validation
===========================

The dry run replays a scenario file; it executes **no** command. Every fact it
judges — the native parent link, the ``agent: approved`` provenance, the commit
topology, PR bases and merges, check runs, claims, workflow triggers — comes from
the scenario, and every read it *would* have asked ``git`` or ``gh`` is journalled
against a read-only allowlist. The suite asserts the refusal directly: a scenario
that needs ``git push`` or ``gh pr merge`` is refused with exit 2, which is the
property that lets this be run against a world as dangerous as this repository's
without touching it.

Exit 2 is a refusal, not a result, in both directions: a scenario with no
expectation for one of the 22 checks is refused too, because a check nobody
stated an expectation for is a check that proved nothing.

And the scenario cannot launder what it declares. The human-authority checks
read the *login*, not the scenario's label for it: an actor equal to
``agent_actor`` or shaped like one (``-bot``, ``-agent``) is an agent even when
the scenario lists it among ``humans``, and a login that is neither allow-listed
nor agent-shaped is refused rather than guessed. The ``no-direct-push``
exemptions are verified against the commit topology instead of trusted from
flags - and the rule-3 exemption asks the discriminating question: a claimed cut
must reach ``cut_from`` only past a merge commit, which is how an epic line
legitimately enters develop (through the sync or the integration merge), so a
single-parent commit pushed onto develop's tip is reported whatever its
``cut_from`` says. The CI-coverage set is *derived* from the contract - every workflow that
triggers for ``master``/``develop`` owes the epic base the same coverage - so an
empty ``required`` in a scenario opts nothing out. Three of these properties are
asserted in the suite with the exact worlds the reviews demonstrated, each
one pinned so that relaxing its guard turns the suite red.

.. _epic-integration-validation-ci-contract:

The CI contract, as validated
===============================

The contract page states the rule; this is what the dry run can actually observe
of it, which is why three of the 22 checks exist.

* A child PR into ``epic/<slug>`` must run the same required checks as one into
  ``develop``. The dry run reads the trigger list of every workflow in the
  scenario, derives the required job set of a PR's base, and refuses a child PR
  whose set is not exactly that - including the case where its base triggers
  nothing at all, because a green with no checks behind it is the failure this
  whole validation was asked to make visible.
* The epic branch is where two children's migrations collide first, so a shared
  migration slot on the epic head refuses readiness until the side develop does
  not carry renumbers - the same answer ``scripts/migration_graph_smoke.py``
  gives a merge queue.
* Documentation and release pipelines are release-only (#1589): no job whose name
  names documentation, sphinx or readthedocs may sit behind a ``pull_request``
  trigger of the everyday epic path.
* The integration PR re-runs everything against current ``develop``. That re-run
  is CI's act, not this tool's; what the tool checks is that the integration PR is
  the single PR whose head is the epic branch and whose base is ``develop``, which
  is what makes the re-run meaningful rather than decorative.

The 22 checks are the acceptance lines
========================================

``python3 scripts/epic_integration_dryrun.py --list-checks`` prints them; the
suite asserts that a run reports exactly these ids, so a check cannot go missing
between two revisions of this page.

.. list-table::
   :header-rows: 1
   :widths: 30 26 44

   * - Check id
     - Contract row / rule
     - What the dry run observes

   * - ``child-selection``
     - R1-R4
     - Every native child has exactly one legal base, and an unapproved child of
       an open epic gets none at all.
   * - ``branch-creation``
     - rule 3
     - The epic branch is the canonical ``epic/<slug>``, cut from develop at
       creation, once.
   * - ``child-starts-from-epic-head``
     - R2, R12, rule 5
     - Children start from the epic head; an open branch that moved did it by
       merging, never by rebasing.
   * - ``child-pr-checks``
     - :ref:`The CI contract, as validated <epic-integration-validation-ci-contract>`
     - A child PR carries exactly the required job set of its base; a base that
       triggers no workflow is refused rather than read as green.
   * - ``blocker-satisfied-by-ancestry``
     - rule 7
     - A dependency counts only as an ancestor of the epic head **and** of
       develop — closed on GitHub is not implemented, and merged into another
       private epic branch is not available.
   * - ``readiness``
     - R7, R8
     - Every required child merged into the epic, dependencies resolved, checks
       green, migration conflicts settled — or the named reason it is not.
   * - ``integration-pr``
     - rule 9, R6
     - Exactly one PR, head ``epic/<slug>``, base ``develop``, merged as a merge
       commit by a person.
   * - ``wrong-base``
     - R5, rule 15
     - A child PR on the wrong base is reported, and an agent that retargeted
       anything fails the run whatever the scenario hoped.
   * - ``epic-head-base``
     - R6
     - No PR with the epic branch as its head targets anything but develop.
   * - ``paused-or-claimed``
     - R13
     - Paused work gets no base, and paused work that was worked on anyway is
       reported.
   * - ``claim-carries-target``
     - rule 14
     - A claim records the integration target the scheduling decision used.
   * - ``cancellation``
     - R10, R11
     - A closed epic takes no child work and leaves no child PR open.
   * - ``migration-conflict``
     - :ref:`The CI contract, as validated <epic-integration-validation-ci-contract>`
     - Two children claiming one migration slot collide on the epic head and
       refuse readiness until the later side renumbers.
   * - ``release-semantic-history``
     - rule 10, #1577/#1580
     - One integration entry whose merge keeps the epic title, child merge
       commits still reachable, a breaking fact surviving on the title, no
       squashing of the epic.
   * - ``rollback``
     - rule 11
     - Recovery is a revert PR into develop — a history rewrite or a force-push
       is refused, not a recovery.
   * - ``recovery-after-deletion``
     - R10
     - After the integration merge the topic continues on develop; a retired
       epic branch is never recreated.
   * - ``no-docs-job``
     - #1589
     - No documentation build sits behind any ``pull_request`` trigger of the
       everyday epic path.
   * - ``epic-ci-coverage``
     - :ref:`The CI contract, as validated <epic-integration-validation-ci-contract>`
     - The workflows the contract requires do trigger for the epic base.
   * - ``no-self-approval``
     - rule 15
     - No agent applied the approval, merged, labelled or claimed the work it
       authored — an unnamed actor is refused, not guessed.
   * - ``no-direct-push``
     - rule 11, ``AGENTS.md``
     - Every commit on a permanent branch is carried by a merged PR. The three
       exemptions (pre-existing history, the rule-3 cut, the rule-12 sync of the
       integration target) are *verified against the topology*, not taken on the
       scenario's word - a commit that merely declares ``"sync": true`` without
       being a two-parent merge of develop, or ``"cut": true`` without being the
       single-parent start of an epic line that reaches ``cut_from`` only past a
       merge, is reported like any smuggled commit.
   * - ``production-untouched``
     - epic objective
     - ``master`` did not move; a scenario cannot green-wash a move by
       declaring it - only a ``promotion_waiver`` naming the #1584 runbook
       passes, and then only as a stated finding.
   * - ``no-competing-orchestrator``
     - epic objective
     - No scheduler, daemon, cron or watcher appears in the change set — AO stays
       the only orchestrator and the contract only extends its inputs.

The happy world and the failure worlds
========================================

The suite builds one world and mutates it, so every failure path is the happy
world with exactly one thing wrong. The happy world is committed as
``docs/source/development/evidence/epic-integration-dryrun-scenario.json`` and its
report as ``docs/source/development/evidence/epic-integration-dryrun-report.json``.

.. code-block:: text

   $ python3 scripts/epic_integration_dryrun.py \
       --scenario docs/source/development/evidence/epic-integration-dryrun-scenario.json
   epic integration dry run: epic-integration-happy-path (epic #1588, repo mrmap-community/mrmap)
     world: 3 branches, 4 PRs, 2 issues, 9 commits; 8 reads journalled

     PASS  child-selection
     PASS  branch-creation
     PASS  child-starts-from-epic-head
     PASS  child-pr-checks
     PASS  blocker-satisfied-by-ancestry
     PASS  readiness
     PASS  integration-pr
     PASS  wrong-base
     PASS  epic-head-base
     PASS  paused-or-claimed
     PASS  claim-carries-target
     PASS  cancellation
     PASS  migration-conflict
     PASS  release-semantic-history
     PASS  rollback
     PASS  recovery-after-deletion
     PASS  no-docs-job
     PASS  epic-ci-coverage
     PASS  no-self-approval
     PASS  no-direct-push
     PASS  production-untouched
     PASS  no-competing-orchestrator

   22/22 checks observed what the contract expects

Every world the issue names is in the suite as its own scenario, and each is
asserted to be **seen**, not merely tolerated:

.. list-table::
   :header-rows: 1
   :widths: 38 20 42

   * - World
     - Exit
     - What the run reports

   * - a child PR based on ``develop`` while the epic branch stands
     - 0 / 1
     - ``wrong-base`` sees it; the same world with the scenario *expecting* R2
       goes red on ``readiness`` instead of passing silently
   * - an unapproved child, a paused child
     - 0
     - ``child-selection`` gives it no base at all (R4, R13)
   * - work on a paused child anyway
     - 1
     - ``paused-or-claimed``
   * - an external blocker merged, but its commit never reached ``develop``
     - 0
     - ``readiness`` refuses with ``dependency-1412-not-in-develop`` (R8)
   * - a dependency merged only into another epic's private branch
     - 0
     - the same refusal — the failure mode the epic objective names
   * - a child whose PR never merged into the epic; a merged child with a
       failing check
     - 0
     - ``readiness`` names the child (R7)
   * - two children claiming migration slot ``registry/0002``
     - 0
     - ``migration-conflict`` and ``readiness`` refuse; renumbering the later side
       clears both
   * - an agent merges the integration PR / retargets a child PR
     - 1
     - ``integration-pr``, ``no-self-approval``, ``wrong-base``
   * - an approval applied by the agent's own login
     - 1
     - ``no-self-approval`` with ``approval:1591``
   * - the epic branch PR based on ``master``; two PRs out of the epic head
     - 1
     - ``integration-pr``, ``epic-head-base`` (R6)
   * - a claim without the integration target, or pointing at ``develop``
     - 1
     - ``claim-carries-target`` (rule 14)
   * - a child branch cut from develop instead of the epic head; an open branch
       that was rebased
     - 1
     - ``child-starts-from-epic-head`` (R12, rule 5)
   * - the epic cancelled with a child PR still open
     - 1
     - ``cancellation``
   * - a documentation job behind a ``pull_request`` trigger
     - 1
     - ``no-docs-job`` (#1589)
   * - recovery by rewriting history, or by force-push
     - 1
     - ``rollback``
   * - a follow-up issue cut from the retired epic branch after integration
     - 1
     - ``child-selection`` gives it ``develop`` under R1, and
       ``recovery-after-deletion`` refuses a recreated branch (R10)
   * - a commit on ``develop`` no PR carried
     - 0 / 1
     - ``no-direct-push`` passes it as a stated *finding*, and ``--fail-on-findings``
       makes it red — the reading the contract wants before enforcement turns strict
   * - ``master`` moved; a new scheduler file appears in the change set
     - 1
     - ``production-untouched``, ``no-competing-orchestrator``
   * - a scenario missing an expectation, of another schema, naming a ref it does
       not carry
     - 2
     - refused before any verdict is printed

Measured against this repository
==================================

These are the live facts the validation was written around. A dated statement
ages; a revision-pinned one does not, so each bullet names the revision it was
taken at (``origin/develop`` at ``f0fc22646`` / 2026-11-24, re-checked at this
PR's head). All commands are read-only.

* **The epic branch stands, cut from develop.** ``git ls-remote --heads
  origin`` lists ``epic/epic-integration`` at ``3f602ad45`` — which was
  ``origin/develop``'s tip at the time it was cut (``develop`` has since moved
  on; the cut's base is what rule 3 judges, not today's tip). The contract page
  measured *zero* ``epic/*`` branches at ``b07e893d1``; the namespace is now in
  use, and the cut matches rule 3 (created from the head of ``origin/develop``).
  Because the branch exists, ``select_children()`` routes approved children at
  it — this is no longer the bootstrap world of rule 16; the row that applies
  to the epic's own children once #1594's enforcement lands is R2, and while
  #1594 is unmerged nothing enforces it yet (the contract's Open questions list
  the rollout as #1594's, which checks out).
* **The native hierarchy is intact.** ``gh api repos/mrmap-community/mrmap/issues/1588/sub_issues``
  returns exactly #1590-#1595, #1590 closed and the other five open — which is
  how the contract's "the native relation is the fact" reading is verified on the
  live side, and how this automation read its own eligibility.
* **The blocker edge of this issue is native and still open.** The GraphQL
  ``blockedBy`` of #1595 names exactly #1594 with state ``OPEN`` — the issue
  that owns the rollout whose absence the next bullet measures. Rule 16's
  bootstrap reading (the epic that builds its own enforcement cannot be bound by
  it, so its children followed R3 against ``develop``) described the world at
  ``f0fc22646``, before ``epic/epic-integration`` was cut; with the branch
  standing, the contract's ordinary rows apply to the epic's children, and the
  epic's own integration PR stays its last act.
* **The rollout gap #1594 owns is still open, and this validation says so.** All
  four workflows of :ref:`The CI contract, as validated <epic-integration-validation-ci-contract>` still restrict their ``pull_request``
  trigger to ``[master, develop]`` — verified with the block below. A child PR
  into ``epic/epic-integration`` today therefore runs **no** required check, and
  the tool refuses to read such a PR as green: the committed world
  ``docs/source/development/evidence/epic-integration-pre-rollout-gap.json``
  reproduces exactly that state and exits 1 on ``child-pr-checks`` and
  ``epic-ci-coverage`` — the two checks the gap touches — while every other
  check passes. Both went red unprompted: the required set is *derived* from
  the contract ("the same checks as develop"), so a scenario cannot opt the
  epic base out of CI by naming an empty one. That is the difference between
  recording the gap and hiding it behind a green.
* **The claim board still carries no integration target.** ``grep -c epic
  scripts/wip`` is still 0, which is rule 14's gap and #1592's scope; the
  ``claim-carries-target`` check is written against the target the scheduling
  decision used, so it is ready for the claim shape #1592 introduces rather than
  invented alongside it.

Not validated here
====================

Named rather than glossed, each with the issue that owns it:

* **The enforcement itself, with one of its three now landed.** The state at
  this head, stated per tool: #1591 has **landed** — ``scripts/epic_branch.py``
  resolves an issue's epic branch and polices PR targets
  (``resolve``/``check-pr``/``check-branch``/``audit``, with the human-gated
  ``create-branch``/``retarget``), runs on every PR into ``develop`` through
  ``pr-target-policy.yml``, and is **advisory until #1594's ``STRICT_FROM``
  date** — exactly as this page predicted the rollout would work. What still
  does *not* exist is #1592's scheduling and claims (the ``epic/**`` entries
  the claim board still lacks, ``grep -c epic scripts/wip`` → 0) and #1593's
  readiness gate. This issue validates the *contract* — that its rows are
  executable and that following them produces the behaviour the epic objective
  promises — and its check ids are the assertions the remaining two tools will
  have to satisfy; #1591's landed tool is now the first of them measured
  against. The two statements are consistent: "#1591 enforces the base rule"
  names what shipped, and this bullet names what #1592/#1593 still owe.
* **A live branch pair on this repository.** The issue asks for an *isolated* dry
  run; creating ``epic/<slug>`` branches, child PRs or check runs on the real
  repository to prove a fixture works would be the production disruption the
  same sentence rules out. The topology is replayed instead, from committed
  scenario files, and the engine cannot push even if asked.
* **The CI-cost budget of :ref:`The CI contract, as validated <epic-integration-validation-ci-contract>`.** Six children costing six child
  runs plus one integration run is a statement about runners and minutes, which
  only a real epic's real runs can measure. The tool counts the required job set
  per base (``child-pr-checks`` reports it) so the number can be read from a real
  epic's checks when one runs; measuring it against a throwaway epic belongs to
  the rollout, and #1594 owns the date enforcement turns strict.
* **Branch protection and the merge queue.** Those are settings, changed by a
  person in the repository's settings, and no dry run can observe them; the
  contract leaves them as the implementing act of #1594.
* **The OpenHands integration of the epic's acceptance text** — multiple
  instance claim exclusion, agent capacity limits and restart recovery, "verify
  actual OpenHands integration where accessible". None of that is validated by
  this page, and none of it is fixture evidence either: the dry run replays a
  *claim record* (``claim-carries-target``, ``paused-or-claimed``), not the
  running orchestrator. Real claim exclusion across two agent instances, the
  capacity limiter refusing a third worktree, and a claim surviving an agent
  restart are AO-side behaviours that need the deployed instances and their
  claim backend — evidence this checkout cannot produce without the
  live-agent interruption the issue rules out. Their validation belongs to
  #1592, which owns the AO scheduling/claim integration; when it runs, the
  evidence must be labelled live, not fixture, exactly as this page labels its
  own two kinds. Until then the claim checks here stand as the *contract* side
  (#1592) of that pair, and #1592 remains the issue to ask for the live half.

Reproducing this validation
=============================

All four commands are offline, need neither ``gh`` nor the network, and write
nothing but the file ``--evidence-out`` names.

.. code-block:: text

   # the suite: every world above, and the refusals
   python3 scripts/test_epic_integration_dryrun.py          # 65/65 checks passed

   # the contract's acceptance lines, as the tool itself lists them
   python3 scripts/epic_integration_dryrun.py --list-checks

   # the happy world, and its report (regenerate the committed evidence)
   python3 scripts/epic_integration_dryrun.py \
     --scenario docs/source/development/evidence/epic-integration-dryrun-scenario.json \
     --evidence-out docs/source/development/evidence/epic-integration-dryrun-report.json

   # the pre-rollout gap: refuses to read a CI-less child PR as green (exit 1)
   python3 scripts/epic_integration_dryrun.py \
     --scenario docs/source/development/evidence/epic-integration-pre-rollout-gap.json

   # the suite re-checks both committed files above; a report that drifted from
   # its scenario fails it, which is why the two lines above need no manual re-run

   # the live facts quoted above
   git ls-remote --heads origin | sed 's#.*refs/heads/##' | grep -c '^epic/'      # 1
   git ls-remote origin refs/heads/epic/epic-integration                          # 3f602ad45
   gh api repos/mrmap-community/mrmap/issues/1588/sub_issues \
     --jq '.[] | "#\(.number) \(.state) \(.title)"'                              # #1590-#1595
   grep -n 'branches:' .github/workflows/quality-assurance.yml \
       .github/workflows/script-tests.yml .github/workflows/codeql.yml \
       .github/workflows/pr-classification.yml                                    # master, develop
   grep -c epic scripts/wip                                                       # 0
