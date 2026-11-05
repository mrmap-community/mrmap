"""Host-side OpenCode agent supervisor for MrMap (epic #1052).

A small, standard-library-only orchestrator that starts OpenCode workers for
GitHub issues a human has approved. It is deliberately not a framework: one
process, the repository's own ``scripts/wip`` claims and
``scripts/agent_capacity`` admission, and the ``AGENTS.md`` hierarchy of the
checkout a worker runs in - no Celery, no Kubernetes, no new agent library.

What it never does (enforced by there being no code path for it, not only by a
configuration switch): approve a pull request, resolve a human review thread,
merge, enqueue into the merge queue, or bypass a branch protection rule.

Modules in this branch (#1058, the authorization gate)
-------------------------------------------------------
``gh``          GitHub reads, always through the host's ``gh``
``config``      protected host configuration, fail-closed
``approvals``   the trusted-human approval gate: who may authorize an issue
``cli``         the operator's command line

The scheduler, worktree runner, CI and review supervision and the systemd
service are the follow-up issues of this epic (#1059 to #1063).
"""

VERSION = "0.1.0"
