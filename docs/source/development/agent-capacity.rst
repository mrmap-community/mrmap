.. _development-agent-capacity:


==========================
Agent Capacity And Cgroups
==========================

.. sidebar:: Issue #1053 (epic #1051)

   The gate is ``scripts/agent_capacity``; its offline checks are
   ``scripts/test_agent_capacity.py`` (no docker, no network, no real cgroup
   needed). The copy-paste rule for agents stays in ``AGENTS.md`` under "Check
   host capacity before starting another stack"; this page is the background:
   which number the gate actually reads, what each threshold means, and how to
   look at the same metrics by hand.

Several agents share one machine, and since 2026-11-05 they share it inside a
container: the OpenCode session and the dockerd it starts for its test stacks
live in one cgroup whose ``memory.max`` is 16 GiB, while the machine behind it
has ~96 GiB. An agent that asks ``/proc/meminfo`` for room sees a healthy
machine and starts a stack the cgroup cannot carry. The day that was measured,
the cgroup had 153 OOM events and 11 OOM kills - and the process it killed was
the OpenCode server itself, because the test stack it was asked to protect was
never the largest thing in sight.

``scripts/agent_capacity`` is the gate that decides before the damage: one
verdict line, exit ``0`` when the job still fits, ``1`` when it does not.

What the gate measures
======================

.. list-table::
   :header-rows: 1

   * - Metric
     - Read from
     - What it answers
   * - load per core
     - ``/proc/loadavg`` divided by ``os.cpu_count()``
     - is the machine already busy for fifteen minutes
   * - host memory
     - ``MemAvailable`` in ``/proc/meminfo``
     - how much the *machine* has free - the misleading half inside a container
   * - cgroup headroom
     - ``memory.max`` minus the unreclaimable charge of ``memory.stat``, for
       this cgroup **and every parent**
     - how much *this job's* ceiling has free
   * - effective memory
     - the smaller of host memory and cgroup headroom, minus a reserve
     - the number the admission decision is made on
   * - memory pressure
     - ``some avg10`` of ``memory.pressure`` (PSI)
     - is the cgroup already reclaiming itself to pieces
   * - charge share
     - unreclaimable charge as a percentage of ``memory.max``
     - is the cgroup at its ceiling
   * - stacks
     - ``docker ps`` labels ``com.docker.compose.project`` starting with
       ``mrmap-agent-``
     - how many disposable test stacks are already up
   * - processes
     - ``/proc/<pid>/cmdline`` of the agent executable (``opencode`` by default)
     - how many workers are already running
   * - disk
     - free bytes on ``/``
     - is there room for another database cluster and build cache

Two decisions are baked into the memory metric and worth stating:

- **Page cache is not charged.** ``memory.current`` of the agent container is
  ~8.4 GiB while only ~2.4 GiB of it is anonymous or kernel memory; the rest is
  file cache a new allocation evicts. Charging a new job against
  ``memory.current`` would refuse work the cgroup serves happily. The gate uses
  the unreclaimable charge (``anon`` + ``slab_unreclaimable`` + the larger of
  ``kernel`` and its itemised parts) and reports both numbers, so an operator
  can see the difference.
- **The binding level is the smallest headroom, not the leaf.** A container can
  be ``max`` inside and still be confined by the slice its runtime runs in, so
  the gate walks from ``/proc/self/cgroup`` up to the root and takes the
  tightest level. That level is named in the verdict (``cgroup / limit 16.0G``).

Nested docker is accounted for rather than trusted: containers started by an
in-container dockerd are children of the same cgroup (the gate reports them as
``docker 2.1G of it``), so their memory is already inside the headroom being
measured and a test stack can never be handed memory the container does not
have. Swap is deliberately not counted - a stack that has reached swap misses
its own timeouts.

Two classes of job
==================

The gate decides about one *prospective* job at a time, and the job matters:

.. code-block:: console

   $ scripts/agent_capacity                  # a heavy Compose test stack
   $ scripts/agent_capacity --need process   # another agent worker, no stack
   $ scripts/agent_capacity --need none      # report only, no class need
   $ scripts/agent_capacity --json           # the same verdict for a program

A stack needs the memory of postgis, redis, mapserver and a one-off test
container at once; an agent process needs a runtime and a context. ``stack`` is
the default, because every check ``AGENTS.md`` documents is a stack check.

"Prospective" is the part that was wrong before: the reported counts are the
jobs **already running**, and the job being asked about is added before the
comparison. So ``stacks 2 (max 3)`` fits and ``stacks 3 (max 3)`` refuses. The
old check compared the current count alone, which let a fourth stack start
beside three.

Admission never kills. There is no code path that signals another job - the
gate's only response to pressure is to refuse the newcomer, and the verdict
flips back on its own as soon as the charge or the pressure drops.

Thresholds
==========

Every threshold is an environment override, so a job can tighten the gate
without editing the file:

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``AGENT_MAX_LOAD_PER_CORE``
     - 1.5
     - most 15-minute load average per core
   * - ``AGENT_STACK_MIN_MEM_GB``
     - 6
     - effective GiB one heavy Compose stack needs
   * - ``AGENT_PROCESS_MIN_MEM_GB``
     - 2
     - effective GiB one agent process needs
   * - ``AGENT_MIN_MEM_GB``
     - 16
     - floor for a stack when no memory limit of this cgroup is visible, i.e.
       the plain host case (kept from the first version of the gate)
   * - ``AGENT_MEM_RESERVE_GB``
     - 2
     - GiB kept out of reach of every admission, always
   * - ``AGENT_MEM_NEAR_CEILING_PCT``
     - 90
     - refuse new stacks at or above this percentage of ``memory.max`` charged
       to unreclaimable memory
   * - ``AGENT_MAX_MEM_PRESSURE``
     - 10
     - most memory PSI ``some avg10`` percent for a new stack
   * - ``AGENT_MIN_DISK_GB``
     - 100
     - least free GiB on ``/``
   * - ``AGENT_MAX_STACKS``
     - 3
     - most running ``mrmap-agent-*`` stacks, counted prospectively
   * - ``AGENT_MAX_PROCESSES``
     - 6
     - most running agent processes, counted prospectively
   * - ``AGENT_PROCESS_MATCH``
     - ``opencode``
     - process name the agent-process counter looks for
   * - ``AGENT_CGROUP_ROOT``
     - ``/sys/fs/cgroup``
     - cgroup mount to read (the seam the offline tests fabricate into)
   * - ``AGENT_PROC_ROOT``
     - ``/proc``
     - proc mount to read (the other test seam)

A metric that cannot be read is printed as ``n/a`` and never makes the host look
busy: the gate blocks only on what it can actually see over budget. The one
exception is a cgroup that *is* readable and *is* capped - that is the case it
exists for.

Measured on the 16 GiB agent container
======================================

The same host, before and after. The container had already OOM-killed the
OpenCode server eleven times.

.. list-table::
   :header-rows: 1

   * - Version
     - Command
     - Verdict
   * - before (#1053)
     - ``agent_capacity``
     - ``mem 63.3G (min 16) ... stacks 0 (max 3) -> fits`` - host memory, and a
       fourth stack would have fitted too
   * - after
     - ``agent_capacity``
     - ``mem 11.6G effective of 13.6G cgroup / 63.3G host (need 6, reserve 2)
       ... [cgroup / limit 16.0G committed 2.4G current 8.4G; docker 2.1G of it;
       peak 16.0G; oom 153/11 kill] -> fits``
   * - after
     - ``agent_capacity --stacks 3``
     - ``... stacks 3+1 (max 3) ... -> BUSY: stacks`` (exit 1)
   * - after
     - ``agent_capacity --need process``
     - ``... mem 11.6G effective ... (need 2 ...) ... processes 3 (max 6) ... -> fits``

The first line is the change that matters: a job is now admitted against 13.6
GiB of real headroom instead of 63.3 GiB of machine memory, and the 6 GiB a
stack needs is checked against it. With this baseline one further stack fits, a
second one is refused by the memory rule, and a third by the stack rule.
``memory.peak 16.0G`` next to ``oom 153/11 kill`` is the reason not to argue
with the cgroup.

Looking at the same numbers by hand
===================================

.. code-block:: console

   # the ceiling of this container and what it holds
   $ cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.peak
   # what of that charge cannot be reclaimed (anon, kernel, unreclaimable slab)
   $ grep -E '^(anon|file|kernel |kernel_stack|pagetables|slab_reclaimable|slab_unreclaimable)' \
       /sys/fs/cgroup/memory.stat
   # has it OOMed, and how often
   $ cat /sys/fs/cgroup/memory.events
   # is it reclaiming right now (some avg10 is the number the gate reads)
   $ cat /sys/fs/cgroup/memory.pressure
   # which cgroup is this process actually in
   $ cat /proc/self/cgroup
   # what an in-container dockerd currently holds
   $ cat /sys/fs/cgroup/docker/memory.current

A ceiling of ``max`` simply means "not capped here" - on a plain host that is
normal and the gate falls back to ``MemAvailable``.

Configuring a constrained agent container
=========================================

The defaults describe an unrestricted developer host. Inside a 16 GiB agent
container, tighten the gate to what the container can actually carry - the
numbers below are the defaults, restated for a container so they can be copied
into a service environment:

.. code-block:: ini

   AGENT_STACK_MIN_MEM_GB=6
   AGENT_PROCESS_MIN_MEM_GB=2
   AGENT_MEM_RESERVE_GB=2
   AGENT_MAX_STACKS=1
   AGENT_MAX_PROCESSES=4

``AGENT_MAX_STACKS=1`` is honest at a 16 GiB ceiling with an ~8 GiB idle
baseline: two concurrent test stacks are what the OOM diagnosis killed. The
ceiling itself is not a repository setting - raising it, or moving the docker
daemon out of the agent container, is the operator runbook of #1054.

OpenCode supervisor integration
===============================

The supervisor of epic #1052 calls the same gate rather than re-implementing a
policy: ``scripts/agent_capacity --json`` for a decision it can branch on
(``fits`` and ``reasons``, plus the metrics it reports to its own operators), and
``--stacks``/``--processes`` to pass the counts it already tracks in its own
state, so the number that decides is the number of jobs the supervisor actually
has. ``evaluate()`` is importable for a caller that would rather not fork.
Import it with ``importlib`` - the file has no ``.py`` suffix, like
``scripts/wip``.
