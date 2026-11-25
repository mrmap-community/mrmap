---
name: MrMap GitHub Workflow
description: "Doing MrMap development work on GitHub — claiming an issue, branch/worktree setup, the native GitHub Flow contribution loop, commits, pushes, pull-request readiness, definition of done, asking humans for decisions, the wip claim board, labels/epics, or respecting human-only actions (approve/merge/resolve)."
---

# MrMap GitHub Workflow

Task skill for the contribution loop around the code. The authorities are root `AGENTS.md`
("Git conventions", "Assigning work and legacy claims", "Asking for human decisions"), `CONTRIBUTING.md`,
`docs/source/development/definition_of_done.rst` and `docs/source/development/decision-requests.rst`.
This skill sequences them; it does not restate every rule — read the named files.

## Activation

Load when the task involves: starting work on an issue, branch/worktree creation, `scripts/wip`
or `scripts/decisions`, preparing/pushing a pull request, issue labels/epic relations, or deciding
whether an action needs a human.

## Non-negotiables (sources named)

- Follow `docs/source/development/github-flow.rst`: explicit assignment by a human or
  external coordinator, one worker, verify blockers and conflicting work, link a branch,
  open a Draft PR. Native assignees/dependencies are planning signals, not atomic locks.
  No new claim, heartbeat or eligibility checker is required. Preserve foreign legacy
  claims until their owners reconcile them; #1753 owns retirement of the old board.
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


- Always explicitly specify `--base develop`, including for native epic sub-issues.
  Epics are parent issues only. Existing arrangements need an owner-approved temporary
  exception recorded in `docs/source/development/github-flow-transition.rst`.
  The epic branch contract and its dated rollout are superseded by #1592; retained
  diagnostics are not prerequisites. Retargeting and branch cleanup remain human acts.
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
- Sleep/wait loops around CI or docker (root `AGENTS.md` "Running shell commands").
- Mixing unrelated formatting/refactoring, changelog entries, or labels into a PR
  (`CONTRIBUTING.md`, root `AGENTS.md`).
- Automatically retargeting existing PRs, deleting branches, removing foreign claims or
  interrupting active workers during the transition.
- Inventing conventions for missing pieces (e.g. inventing a "ready for review" label): check
  `gh label list` / templates, ask via `scripts/decisions` or `scripts/wip ask`.

## Verification of this skill's own steps

- `scripts/wip ls` reflects your claim after claiming; `scripts/wip answers` after a human reply.
- Offline checks for the tooling itself: `python3 scripts/test_wip_board_sync.py`,
  `python3 scripts/test_decisions.py`, `python3 scripts/test_epic_rollout.py` (no `gh`, no
  network; CI runs them via `scripts/check_repo_tooling.sh`).
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
