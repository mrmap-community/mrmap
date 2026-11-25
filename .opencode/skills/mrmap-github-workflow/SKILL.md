---
name: MrMap GitHub Workflow
description: "Doing MrMap development work on GitHub — claiming an issue, branch/worktree setup, the epic branch base rule (scripts/epic_rollout.py), commits, pushes, pull-request readiness, definition of done, asking humans for decisions, the wip claim board, labels/epics, or respecting human-only actions (approve/merge/resolve)."
---

# MrMap GitHub Workflow

Task skill for the contribution loop around the code. The authorities are root `AGENTS.md`
("Git conventions", "Claiming work", "Asking for human decisions"), `CONTRIBUTING.md`,
`docs/source/development/definition_of_done.rst` and `docs/source/development/decision-requests.rst`.
This skill sequences them; it does not restate every rule — read the named files.

## Activation

Load when the task involves: starting work on an issue, branch/worktree creation, `scripts/wip`
or `scripts/decisions`, preparing/pushing a pull request, issue labels/epic relations, or deciding
whether an action needs a human.

## Non-negotiables (sources named)

- Work on an issue starts with `scripts/wip claim` **before the first file edit** (idempotent);
  re-run after every `git push`; `scripts/wip wait "<need>"` when blocked on a human;
  `scripts/wip ask` to hand a question to the issue; `scripts/wip answers` to read replies;
  `scripts/wip done` when the PR is ready or work is abandoned; `scripts/wip ls` before picking up
  or merging (no merge over a live claim). `gh` unauthenticated → say so once and continue
  (root `AGENTS.md`).
- Branches: `<type>/<short-topic>`; worktrees `git worktree add <dir> -b <type>/issue-<N>-<topic>
  origin/develop` after `git fetch origin`; **no merging `origin/develop` into a branch** before the
  PR (the merge queue tests integration); never force-push/rebase a branch open for review;
  commit messages are short lowercase summaries ("fixes …") (root `AGENTS.md`).
- A pull request relates to an accepted issue or it is closed (`CONTRIBUTING.md`). Issues are
  labelled at creation (`gh issue create --labels 'type: …'`); epic children carry the epic slug
  prefix and the native sub-issue link (root `AGENTS.md`).
- The **PR title** carries the change class and CI checks it: `<type>[(<scope>)][!]: <summary>`
  with a type from `python3 scripts/pr_classify types`; a component name is a scope
  (`fix(mcp-setup): …`, not `mcp-setup: …`), and `!` goes on the title whenever anything breaks
  a consumer — a merge keeps only the title, so `BREAKING CHANGE:` in a commit message or the PR
  body is lost at the merge. `python3 scripts/pr_classify title "<title>"` answers it locally
  (`docs/source/development/commit-classification.rst`).
- Human-only acts: `agent: approved`, PR review, merge, resolving human threads, branch
  protection/CI changes, access grants, committing secrets. Ask via `scripts/wip ask`; do not
  attempt them (root `AGENTS.md`).
- Design questions (normative standards readings, scope, migration risk) go through
  `scripts/decisions` — never answered silently; an answered decision grants neither approval nor
  merge (root `AGENTS.md`, `docs/source/development/decision-requests.rst`).
- Orchestration is external (Agent Orchestrator); this repository runs no scheduler/daemon/CI
  watcher — do not reintroduce one (root `AGENTS.md`).


- Always explicitly specify the PR base: `develop`, or — for a child of an open epic that
  declares a `slug:` first body line — `epic/<slug>` of its own epic and nothing else. An epic
  branch is cut by a **person** from the tip of `origin/develop` and never created, deleted,
  retargeted or pushed to directly by an agent; the epic's single integration PR (`epic/<slug>`
  → `develop`) is human-approved and human-merged (`AGENTS.md` "Git conventions",
  `docs/source/development/epic-integration-contract.rst`). Before starting work on an epic
  child, or before opening any PR whose base is not `develop`, run
  `python3 scripts/epic_rollout.py --epic <epic number>` (or without `--epic` for every open
  epic at once): it prints the decision row, the lawful base and the actor owed every
  outstanding step. `scripts/epic_rollout.json` is the reviewed rollout
  policy (dates, bootstrap exemption, time-limited legacy exceptions); an epic exempt from the
  contract targets `develop` only while that file says so with a reason and an expiry.
- Only the same repository's `develop` branch may target
  `master`. Never delete, force-push or directly push to either permanent branch.
- Use merge commits when synchronizing permanent branches.

## The pre-PR readiness loop (definition_of_done.rst + backend/AGENTS.md)

1. `python3 scripts/agent_capacity` (or `--need suite`) before starting a Compose stack; own
   project name + override per root `AGENTS.md`.
2. Targeted tests first, then the checks the change's area requires
   (`backend/AGENTS.md`, `frontend/AGENTS.md`; skills `mrmap-testing` + the area skill).
3. Migrations added → `pre-commit-check` drift/translation gates **and**
   `python3 scripts/migration_graph_smoke.py` before pushing.
4. `scripts/` touched → `scripts/check_repo_tooling.sh`.
5. Frontend route starting with a proxied prefix → `python3 scripts/nginx_routing_smoke.py`;
   compose mounts under `/var/www/mrmap` → `python3 scripts/static_mounts_smoke.py`.
6. Report every command run and its result, plus what could not run (root `AGENTS.md`).

## MCP dependencies

None — the loop runs on `git` and `gh` (authenticated host account) and the offline
`scripts/test_*.py` suites. `gh` usage here stays read/write within the issue/PR flow the claim
board defines; creating issues/PRs is a separate human-approved context. **Optional:** the
`sonarqube` MCP (remote, `api.sonarcloud.io`; a person must place a SonarQube Cloud user
token in `~/.config/opencode/sonar-token` once per host — see
`docs/development/mcp-servers.md`) gives the findings SonarCloud posts on your PR — read
them through it instead of scraping the check output, and fix them where reported (root
`AGENTS.md`, SonarCloud).

## Anti-patterns

- Hand-editing machine-managed artifacts: claim comments (`<!-- agent-claim … -->`),
  `status: wip`, the Agent Work Board issue (#917), decision markers.
- Working without a claim because "the change is small" — claiming never blocks work, skipping it
  races another client.
- Sleep/wait loops around CI or docker (root `AGENTS.md` "Running shell commands").
- Mixing unrelated formatting/refactoring, changelog entries, or labels into a PR
  (`CONTRIBUTING.md`, root `AGENTS.md`).
- Basing an epic child PR on `develop`, or opening one into another epic's branch or a
  sibling child branch (R2/R5 of the contract); creating, deleting or force-pushing an
  `epic/*` branch, or retargeting a PR to "fix" its base — those are person-owned acts
  (`epic_rollout.py` names the actor).
- Starting work on an epic child without reading its row: `python3 scripts/epic_rollout.py
  --epic <N>` says the lawful base, and `scripts/epic_rollout.json` says whether the epic is
  exempt — an exemption that is not in that file is not an exemption.
- Inventing conventions for missing pieces (e.g. inventing a "ready for review" label): check
  `gh label list` / templates, ask via `scripts/decisions` or `scripts/wip ask`.

## Verification of this skill's own steps

- `scripts/wip ls` reflects your claim after claiming; `scripts/wip answers` after a human reply.
- Offline checks for the tooling itself: `python3 scripts/test_wip_board_sync.py`,
  `python3 scripts/test_decisions.py`, `python3 scripts/test_epic_rollout.py` (no `gh`, no
  network; CI runs them via `scripts/check_repo_tooling.sh`).
- Before an epic child's PR: `python3 scripts/epic_rollout.py --epic <epic number>` names the
  row, the base and the actor; the same tool's readiness findings are what says the rollout is
  on, and `--json` is the shape for a machine to read.
- Before hand-back: `git status` clean of unintended files, zero leftover containers/networks/
  volumes of the job's project (names reported per root `AGENTS.md`).

## Security constraints

- `gh` token and `MRMAP_*` credentials stay on the host: never echo, store in files committed to
  the repo, or paste into issue text.
- Push only your own branches; never rewrite shared refs; never change `.github/workflows/*` or
  branch protection as collateral.

## Explicit exceptions

- Meta work in a research checkout (documentation of the agent setup itself, like the files under
  `.opencode/skills/`) is not an issue-claimed code change: no claim is possible without an
  `issue-<N>` branch; note the situation once and proceed locally — do **not** invent an issue,
  branch or PR for it.
- A stale foreign claim may be taken over with `scripts/wip claim --force` only after the holder
  was confirmed gone (root `AGENTS.md`).
