"""Host-side OpenCode agent supervisor for MrMap (epic #1052).

A small, standard-library-only orchestrator that starts OpenCode workers for
GitHub issues a human has approved. It is deliberately not a framework: one
process, the repository's own ``scripts/wip`` claims and
``scripts/agent_capacity`` admission, and the ``AGENTS.md`` hierarchy of the
checkout a worker runs in - no Celery, no Kubernetes, no new agent library.

What it never does (enforced by there being no code path for it, not only by a
configuration switch): approve a pull request, resolve a human review thread,
merge, enqueue into the merge queue, rerun a workflow, or bypass a branch
protection rule.

Modules
-------
``gh``          GitHub reads, always through the host's ``gh``, plus the two
                label writes of the approval contract
``config``      protected host configuration, fail-closed
``approvals``   the trusted-human approval gate: who may authorize an issue
``claims``      the ``scripts/wip`` board, read and written through wip itself
``capacity``    the ``scripts/agent_capacity`` verdict, read as a contract
``scheduler``   one tick: which eligible issue starts next, under a lease
``runner``      start, stop and reconcile one worker in its own worktree,
                process group and Compose project
``store``       the supervisor's own SQLite state: leases, verdicts, events and
                the pull requests under CI watch
``ci_monitor``  follow the checks of the pull requests those workers opened,
                repair what names a test, report everything else (#1061)
``cli``         the operator's command line

Review feedback (#1062) and the daemon that ties these commands to a timer
(#1063) are the remaining issues of this epic.
"""

VERSION = "0.1.0"
