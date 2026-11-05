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
``store``       the supervisor's own SQLite state: leases, verdicts, events, the
                pull requests under CI watch and the review ledger
``ci_monitor``  follow the checks of the pull requests those workers opened,
                repair what names a test, report everything else (#1061)
``reviews``     read the human review feedback on those pull requests, answer what
                a trusted reviewer asked for, hand reserved acts to a human and
                never settle a thread the human raised (#1062)
``daemon``      the loop on a timer: one daemon per state directory, per-stage
                containment, a pause that survives a restart, and a log that
                redacts anything credential-shaped before it is written (#1063)
``metrics``     the operational numbers, each read from its real source or
                reported as unknown - never as zero (#1063)
``cli``         the operator's command line: the gate's answers, the loop and its
                controls, one issue started or stopped by hand, the metrics and
                the readiness check

The seven offline checks are ``scripts/test_agent_supervisor_approvals.py``,
``..._scheduler.py``, ``..._capacity.py``, ``..._runner.py``, ``..._ci.py``,
``..._reviews.py`` and ``..._daemon.py``; none of them needs ``gh``, the network,
a container or a model, and none of them can write to a repository.
"""

VERSION = "0.1.0"
