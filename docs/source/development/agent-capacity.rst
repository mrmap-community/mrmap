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
   look at the same metrics by hand. The ceiling over all of it is the
   operator's: :ref:`development-agent-capacity-ceiling` says what raising it
   changes, what it costs and which numbers have to be read for a claim about
   it to hold (#1054).

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
       ``mrmap-agent-`` or ``mrmap-ao-``
     - how many disposable test stacks are already up - both prefixes agent
       stacks actually carry in the field: the repository naming convention
       and the Agent Orchestrator worktree name this host's wrapper pins
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

Three classes of job
====================

The gate decides about one *prospective* job at a time, and the job matters:

.. code-block:: console

   $ scripts/agent_capacity                  # a heavy Compose test stack
   $ scripts/agent_capacity --need suite     # a stack running the FULL suite
   $ scripts/agent_capacity --need process   # another agent worker, no stack
   $ scripts/agent_capacity --need none      # report only, no class need
   $ scripts/agent_capacity --json           # the same verdict for a program
   $ scripts/agent_capacity --wait 900       # queue for a refusal to clear

A stack needs the memory of postgis, redis, mapserver and a one-off test
container at once; an agent process needs a runtime and a context. ``stack`` is
the default, because most checks ``AGENTS.md`` documents are stack checks - but
it is sized from a *targeted* run. #1055 measured what the full backend suite
costs in the same stack shape: ``--parallel=4`` runs the 1312 tests in 225 s
and put the container's memory cgroup at 12.1 GiB, where a targeted module
never comes close. A caller that means to run the whole suite asks
``--need suite`` so the gate compares against ``AGENT_SUITE_MIN_MEM_GB``
instead of the lighter number, and a second heavy job is refused *by the memory
rule* while the suite is charging - which is the arithmetic of the section
"Why #1054's acceptance is out of reach at 16 GiB" below, turned into an
admission decision instead of an OOM.

"Prospective" is the part that was wrong before: the reported counts are the
jobs **already running**, and the job being asked about is added before the
comparison. So ``stacks 2 (max 3)`` fits and ``stacks 3 (max 3)`` refuses. The
old check compared the current count alone, which let a fourth stack start
beside three.

Admission never kills. There is no code path that signals another job - the
gate's only response to pressure is to refuse the newcomer, and the verdict
flips back on its own as soon as the charge or the pressure drops. ``--wait N``
uses that: it turns one refusal into a bounded queue, re-reading the metrics
for up to N seconds and exiting 0 the moment a verdict says ``fits``. A job
that can afford to be late then does not have to poll the gate from its own
loop, and waiting is still admission control - a running job is never
displaced for the newcomer. Progress lines go to stderr, so ``--json`` stdout
stays exactly one object.

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
     - effective GiB one heavy Compose stack needs, sized from a targeted run
   * - ``AGENT_SUITE_MIN_MEM_GB``
     - 8
     - effective GiB a ``--need suite`` stack needs: the same stack running
       the full unit suite, which #1055 measured well above a targeted run
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
     - most running agent stacks (``mrmap-agent-*``, ``mrmap-ao-*``), counted
       prospectively
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
daemon out of the agent container, is an operator decision and
:ref:`development-agent-capacity-ceiling` below is the runbook for it (#1054).

.. _development-agent-capacity-ceiling:

Raising the ceiling: an operator runbook
========================================

Everything above sizes a job to the ceiling it is born under; nothing above
raises that ceiling, and nothing in this repository can. The 16 GiB the
measurements kept hitting is applied by the deployment *around* the agent
container - a compose file, a systemd unit or slice, a runtime flag, an
orchestrator - and that lives on the host. #1054 is exact about who acts: an
agent may read these numbers, report them and recommend a value, while applying
a change is a host action and therefore a human one. An agent that concludes it
needs more room is the precise thing the gate exists to refuse, because that
room would come out of the jobs already running.

Why one ceiling covers the session and its stacks
-------------------------------------------------

An OpenCode session starts the dockerd that runs its disposable test stacks, and
that daemon is a child of the session's container. The containers it creates are
therefore nested cgroups under the same limit - the gate's ``docker 2.1G of it``
is that subtree, ``/sys/fs/cgroup/docker/`` inside the agent container. That
accounting is not an obstacle the gate works around: it is the reason the
measurement can be trusted, since a test stack can never be handed memory the
container does not have.

The number that decides every admission on this host is the one the verdict line
is built on::

    effective = min(MemAvailable, headroom of the binding cgroup level) - reserve

*headroom* is ``memory.max`` minus the unreclaimable charge, taken at the
tightest level between this process and the root. On the measured baseline
(limit 16.0G, committed 2.4G, host 63.3G) that is 13.6 - 2 = 11.6 GiB: the room
a 6 GiB stack is admitted into, and the same line reads a smaller number the
moment that stack is charged. ``MemAvailable`` decides nothing here - at 63.3
GiB it claims more than four times the room that exists.

Where the limit is set - read-only checks
-----------------------------------------

The first job is finding out *which* level applies the limit, because the gate
takes the smallest headroom over the whole chain: an operator who raises the
container while a parent slice stays at 16 GiB has changed nothing, and the
verdict will keep naming 16 GiB. Read the ceiling from both sides - inside the
container is what the gate sees, outside is where it can be changed.

.. code-block:: console

    # inside the agent container - what the gate reads
    $ scripts/agent_capacity --json | python3 -m json.tool | grep mem_cgroup
    $ cat /sys/fs/cgroup/memory.max /sys/fs/cgroup/memory.peak
    $ cat /sys/fs/cgroup/memory.events      # cumulative: max, oom, oom_kill
    $ cat /proc/self/cgroup                 # which level this process sits in

    # on the host - who applies the limit, and who else shares it
    $ docker inspect -f '{{.Name}} memory={{.HostConfig.Memory}}' <agent-container>
    $ docker inspect -f 'cgroup-parent={{.HostConfig.CgroupParent}}' <agent-container>
    $ systemctl show -p MemoryMax -p MemoryHigh <unit-or-slice>
    $ cat /sys/fs/cgroup/<parent-of-the-container>/memory.max

``memory=0`` from ``docker inspect`` means "not capped by the daemon" and points
at the unit, the slice or the orchestrator instead; a non-zero value is bytes and
is the number to change, wherever the deployment that sets it lives -
``deploy.resources.limits.memory`` in a compose file, ``MemoryMax`` in a unit
drop-in, the orchestrator's resource limit, ``docker run --memory``. Check the
parent chain for the same reason the gate walks it.

None of these is a reason to edit a running host from a job. They are the
operator's inventory: which value, which file or unit owns it, and what to roll
back to.

Option A - raise the agent container's own limit
------------------------------------------------

What it does: the session and everything its dockerd starts keep sharing one
number and that number gets bigger - #1054 names 24 to 32 GiB. The accounting
stays as it is, so the gate keeps measuring the truth without being retargeted,
and the change is one value in one deployment file.

What it costs: the container's blast radius grows with it. Everything the agent's
daemon can start is bounded by the same ceiling as the session, so a runaway
stack takes the OpenCode server down with it - which is what the eleven OOM kills
of 2026-11-05 were. A larger ceiling makes that less frequent, not impossible.
The gate is what keeps it infrequent, and ``AGENT_MAX_STACKS`` is the
repository-side half of that; see the note on un-muted rules below.

Option B - move the docker daemon out of the agent's cgroup
-----------------------------------------------------------

What it does: the stacks stop being charged to the session. Two shapes reach
that - the *host* daemon, whose socket is mounted into the agent container, or a
separate daemon in its own container with its own ceiling that the agent reaches
over a socket the operator exports.

What it costs, and this is the larger half of the decision:

- **Measurement.** The gate sizes a job against the cgroup the *gate* runs in.
  Once the stacks are charged elsewhere, the ``docker ... of it`` detail leaves
  the verdict and a ``--need stack`` decision is made on a ceiling that no
  longer carries the stack: it reads free and admits work that OOMs where the
  gate cannot see it. ``AGENT_CGROUP_ROOT`` relocates the mount the tool reads,
  not the process's place in the hierarchy, so it does not fix this. The
  decision has to be taken where the stacks will be charged - a second
  measurement point watching the daemon's cgroup through the same four files, or
  the gate running in that cgroup.
- **Comparability.** ``memory.peak`` and the ``memory.events`` counters then
  describe a cgroup that no longer holds the stacks, so before and after such a
  switch are two different quantities. After one, read both cgroups and name
  which is which.
- **Privilege.** A docker socket is root over everything that daemon can reach:
  whoever holds it can start a container with the host's filesystem mounted
  writable. Mounting the *host* daemon's socket ends the isolation the
  parallel-agent rules are built on in a single line of configuration - the
  "never ``down`` a project you did not create" rule, the no-global-prune rule,
  the exact-name cleanup checks all stop being enforceable and become policy,
  because one job's ``docker ps`` now addresses every other job's stacks. That
  is why the host socket is not the cheap option it looks like. The shape that
  keeps the memory win without that jump is one daemon per agent, in its own
  cgroup, with its own project namespace and its own ceiling: the isolation the
  compose-project rules already assume, moved one level down.

.. list-table:: What each option leaves the gate to measure
   :header-rows: 1
   :widths: 26 34 40

   * - Question
     - Option A: bigger container
     - Option B: daemon outside
   * - Ceiling that carries a test stack
     - the agent container's, raised
     - the daemon's own, somewhere else
   * - What ``agent_capacity`` sees from inside the session
     - still the whole truth
     - the session only; the stacks are invisible to it
   * - Extra reading the operator takes on
     - none
     - the daemon's cgroup, same four files
   * - Privilege change
     - none
     - a socket into another daemon - per agent, never the host's
   * - Rollback
     - the recorded value, one file
     - the daemon wiring and the socket

Could Option B run without an operator? Measured on the agent host
-------------------------------------------------------------------

The 2026-11-05 operator decision left one open half: an agent, without admin
rights, evaluate whether Option B is implementable under its own permissions.
The answer is measured, not argued, and it is no - in a way that is worth
writing down because it is a property of the cgroup layout, not of missing
tooling:

- The socket the agent holds addresses a rootful dockerd running *inside* the
  agent container itself: ``docker info`` names the daemon after the container,
  its process is a child of the container's PID namespace, and its cgroup
  ``/sys/fs/cgroup/docker`` is a **child** of the 16 GiB root (``memory.max``
  inside it reads ``max``, which means "bounded by the parent's charge", not
  "unbounded"). The stacks were always billed there - the verdict's
  ``docker 2.1G of it`` is this same fact.
- Rootless docker cannot be substituted: there is no user systemd session (PID
  1 is the container's startup script and ``systemctl --user`` fails), and
  ``newuidmap``/``newgidmap`` are absent, so the uid remapping cannot even
  start although the ``subuid`` ranges exist. Installing the pieces needs root
  inside the container, which is not an agent operation.
- No host daemon socket is mounted in, which is exactly why the nested daemon
  above is the only one addressable - and why the privilege cost of Option B
  is not even on the table from here.
- The container has its own cgroup namespace (``/proc/self/cgroup`` reads
  ``0::/init.scope`` and the ceiling appears as the mounted root's
  ``memory.max``). *Every* daemon an agent can start here - rootful, rootless,
  systemd-scoped - is born as a descendant of that root, and a cgroup child
  can never use memory its parent's ceiling does not carry. Relocating the
  daemon means leaving the container, which is the host action the runbook is
  about. A rootless daemon inside would share the ceiling verbatim and must
  not be presented as isolation.
- Self-raising the ceiling is equally out of an unprivileged agent's reach:
  the namespace root's ``memory.max`` is root-owned mode ``0644``, and writing
  the same value back as the agent user is an ``EPERM`` (measured - the probe
  cannot change anything, which is the point of probing with the unchanged
  value). Whether root *inside* the container could lift the limit depends on
  the hidden host-side parent and is moot besides: the operator decision of
  2026-11-05 pins the 16 GiB and container root is not an agent permission.

So Option B is not a feature an agent failed to build; under agent permissions
no daemon placement escapes the ceiling. The repository-side answer is the one
in this document: keep the stacks inside the session's accounting - the only
place the gate can measure them truthfully - and let the gate's numbers decide
how many jobs the ceiling carries.

Why #1054's acceptance is out of reach at 16 GiB
------------------------------------------------

The acceptance is that OpenCode survives two to three concurrent heavy jobs. On
this host that cannot be demonstrated today, and it is worth writing down why -
it is arithmetic, not willingness.

#1055 measured the full backend suite (1312 tests, all green) in exactly such a
throwaway stack and recorded the container cgroup's peak per arm (PR #1073): one
process takes 654.9 s of suite time and peaks at 12.48 GiB, ``--parallel=2``
peaks at 11.34 GiB, and the ``--parallel=4`` arm it adopted runs the suite in
225.4 s at 12.09 GiB. So *one* representative heavy job reaches for ~12.5 GiB of
a 16 GiB ceiling that already holds ~2.4 GiB of unreclaimable session baseline: a
second concurrent full suite is left with about 1 GiB of nominal room, less than
the 2 GiB reserve the gate keeps back. That is the 2026-11-05 diagnosis in one
sentence. Running the acceptance here would not test a fix, it would reproduce
the OOM.

Sizing from those peaks, with the measured 2.4 GiB baseline and the 2 GiB reserve
the gate always keeps out of reach:

.. list-table::
   :header-rows: 1
   :widths: 16 22 62

   * - Ceiling
     - Headroom / effective at idle
     - Carries
   * - 16 GiB (today)
     - 13.6 / 11.6 GiB
     - one full-suite stack. Its measured peak leaves the ceiling in sight, and
       under the container settings above a second heavy job is refused by
       ``stacks`` before memory is even argued about.
   * - 24 GiB
     - 21.6 / 19.6 GiB
     - one full suite plus targeted checks. Two full suites at their measured
       peaks (2 x 12.48 = 25.0 GiB) do not fit.
   * - 32 GiB
     - 29.6 / 27.6 GiB
     - two full-suite peaks plus the baseline (27.4 of 32 GiB) with room for a
       targeted third - the ceiling that can carry "two to three heavy jobs"
       as #1054 words it.

Two caveats, both about how these numbers are counted. A peak is a
``memory.peak``-style total and includes page cache, so it is the conservative
bound; the unreclaimable charge *during* a suite run has never been recorded, and
it is what the gate sizes the next job against - step 5 of the protocol below is
where to read it. And the parallel arms peaked *below* the serial one, so two
overlapping suites are not simply twice 12.48: their phases do not align. Treat
the sum of peaks as an upper bound, not a forecast.

Raising the ceiling also un-mutes a second rule. At 32 GiB the memory rule alone
admits four 6 GiB stacks, so ``AGENT_MAX_STACKS`` becomes the limit that binds -
and with the container configuration of the section above leaving it at ``1``, a
bigger ceiling buys no throughput at all. Both halves belong to the change and
both show up in the verdict line.

Validation protocol - the numbers that have to be read
------------------------------------------------------

This is what makes a sentence like "24 GiB is enough" mean something. It is a
human's checklist; an agent can produce the from-inside readings and the verdict
lines and nothing else.

1. **Before, from both sides.** Inside: ``scripts/agent_capacity --json`` - keep
   ``mem_cgroup_path``, ``mem_cgroup_limit_gb``, ``mem_cgroup_committed_gb``,
   ``mem_cgroup_headroom_gb``, ``mem_cgroup_peak_gb``, ``mem_cgroup_used_pct``
   and ``oom_events``. Outside: ``.HostConfig.Memory``, the unit's
   ``MemoryMax``, the parent levels' ``memory.max``. Put them in the change
   note: they are the rollback values, and without a before-value no
   after-number can be read as a difference.
2. **Change one thing** - the level the verdict *names*. Keep the old value.
3. **Re-read the ceiling with nothing running.** The verdict must name the new
   limit at the path that binds, e.g. ``[cgroup / limit 32.0G ...]``. If it
   still says ``16.0G``, the edited level was not the binding one and every
   later step measures an unchanged host.
4. **Load it the way production does.** One heavy job is the full suite with
   ``--parallel=4``, the command #1055 measured; then the concurrent set the
   acceptance names. Ask before each start: ``scripts/agent_capacity --json``
   counts the prospective job, so every verdict line is that job's admission
   record. Keep them.
5. **Read the charge while it runs** - the data point that does not exist yet.
   Inside, mid-suite:
   ``grep -E '^(anon|kernel |slab_unreclaimable)' /sys/fs/cgroup/memory.stat``.
   Outside, per stack: ``docker stats --no-stream``. The unreclaimable sum is
   what the gate will size the next job against; the peak says how close the
   ceiling came.
6. **Decide from deltas, not absolutes.** Pass: ``oom_kill`` did not move during
   the run, the OpenCode session was still the same process afterwards,
   ``mem_cgroup_used_pct`` stayed below ``AGENT_MEM_NEAR_CEILING_PCT`` (90),
   ``memory.pressure`` stayed below ``AGENT_MAX_MEM_PRESSURE`` (10), and the
   verdict for one further job of the accepted class still said ``fits``.
   Any new ``oom_kill``, or a dead session: restore the recorded value and
   confirm with step 3 that the old limit is back.
7. **Record the measured configuration**, not the intended one: the ceiling, the
   committed charge during a full suite, the peak, and which rule binds
   afterwards - ``mem`` or ``stacks``. #1054 asks for the recommended measured
   value; a ceiling nobody watched under load is a guess with a number in it.

``memory.peak`` and the ``memory.events`` counters are cumulative over the
lifetime of the cgroup, not since the change, so report the difference from
step 1 - and a recreated container starts at zero, which makes its absolute peak
incomparable with the old container's.

If the ceiling is not raised
----------------------------

Then nothing in the repository needs to change, and today's behaviour is the
intended state rather than a defect: the gate refuses the newcomer that does not
fit (exit ``1``, reason ``mem``, ``ceiling``, ``pressure`` or ``stacks``), leaves
every running job alone, and flips back on its own as soon as the charge or the
pressure drops. It does not throttle, pause, renice or kill, and it does not
pretend to share - under a 16 GiB ceiling the honest configuration is one heavy
stack at a time. Throughput suffers and the OpenCode server stops dying. That
trade is a human's to reverse, and this runbook is what makes reversing it an
informed decision: the acceptance of #1054 stays open until someone applies the
change on the host and reads the protocol above back.

Who asks the gate
=================

Nothing in this repository starts an agent any more: development orchestration is done
by Agent Orchestrator, an external tool whose worker sessions run against a checkout
like any human's. The in-repository supervisor of epic #1052 which first called this
gate is retired and removed with it (#1102). Whoever asks - AO, a nightly runner or a
person at a shell - asks the same gate rather than re-implementing a policy:
``scripts/agent_capacity --json`` for a decision that can be branched on (``fits`` and
``reasons``, plus the metrics it reports to its operators), and
``--stacks``/``--processes`` to pass the counts a caller already tracks in its own
state, so the number that decides is the number of jobs it actually has.
``evaluate()`` is importable for a caller that would rather not fork. Import it with
``importlib`` - the file has no ``.py`` suffix, like ``scripts/wip``.
