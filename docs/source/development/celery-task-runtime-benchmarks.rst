.. _celery-task-runtime-benchmarks:

======================================
Celery task runtime benchmarks (V2)
======================================

This page is the runbook of #1396 - the runtime half of the epic #1387, and the
timing counterpart of the test-time guards at
:ref:`celery-task-sql-regression`. Where those guards count statements, rows and
plans inside a test transaction, this measures **seconds**: what one fire of a
first-party Celery task costs on a named machine, how repeatable that reading
is, and when it is allowed to say anything at all about a pull request.

V1 stayed out of this on purpose. A duration measured on a shared runner is a
reading of that runner, so the acceptance of #1396 is not "a number" but "a
number that can be defended" - which is why every figure this tooling writes
carries its sample size, its seed, its environment and an evidence label, and
why the judgement about thresholds lives in a reviewed file rather than in code.

What is measured, and what is deliberately not
##############################################

The unit of measurement is the **workload record**: one arm of one workload,
written by the bench suite as one JSON file and read by the analyzer. A workload
is named by the fields its cost depends on (family, fixture, scale, record and
chunk counts, attempts per unit, concurrency, worker count, queue and queue
configuration, mock-response condition, seed, environment) and is identified by
the digest of those fields; two arms whose digests differ are not the same
experiment and the analyzer refuses to compare them.

Each record carries these readings, and they are kept apart because conflating
them is the failure mode #1330 exists to prevent:

``active``
    Occupied worker-slot seconds - what the attempt really ran. When the run
    rides celery's trace machinery this is #1330's own ``active_seconds``, read
    from the same ``CeleryTaskAttempt`` rows the capacity endpoint of #1326
    aggregates, so a benchmark and a capacity reader cannot disagree.
``queue``
    ``started_at - published_at``, the wait a message spent on the broker. The
    eager path publishes nothing, so its queue wait is **unknown**, reported as
    ``null`` with a ``queue_wait_unmeasured`` coverage flag - never as zero.
    Only a real worker answers this, and the runbook below shows that path.
``end_to_end``
    Whole-workflow elapsed time, reported separately and never used as a task
    cost. A chord callback which waited an hour is not a task that ran an hour.
``sql``
    Statement count and time, measured with the same instrumentation the #1395
    guards use.
``http``
    Outbound OGC/remote calls counted at the client boundary.
``quality``
    Success / retry / error / abandoned / open distribution of the attempts,
    with worker loss and retention truncation named rather than smoothed over.
``pressure``
    Broker depth at the start and end of the run, and peak memory of the
    measuring process with its cgroup limit - the "did it OOM" question is
    answered for what survived, and ``null`` when the counter is unreadable.
``instrumentation``
    The overhead of the #1389 instrumentation itself, measured with it enabled
    and disabled over the same workload.
``correlation``
    Whether the #1390 slow-task record for the same ``task_id`` exists, so a
    benchmark and an operator alarm describe the same execution.

Nothing here is invented: a value that was not measured stays ``null`` and is
listed under ``missing`` coverage, and every value carries one of these evidence
labels - ``measured`` (worker signals of an actual execution),
``measured_local`` (stopwatch of the runner process), ``derived`` (computed from
measured values of the same sample set), ``projected`` (an extrapolation from a
smaller measurement) and ``inferred`` (read from a run table, not from attempt
rows). A projection is never printed as an observation.

The arms
########

Every workload runs the same four arms, because "the task is slow" is not a
finding until something names the mechanism:

``baseline``
    The task as it is. This is the arm the others are read against.
``sql-n-plus-one``
    One extra statement per unit, injected in the test - the regression the
    statement guards of #1395 forbid, reintroduced so the two readings must
    agree. If the time stays flat while the statement count climbs, the
    benchmark is measuring something other than the database.
``duplicate-remote-call``
    The same remote answer asked for twice per unit, the shape of a forgotten
    per-record capabilities read.
``slow-body``
    A CPU-bound burn inside the attempt - slowness that neither the SQL nor the
    HTTP counter can see. Its length is a multiple of what the same unit cost in
    the baseline arm of the same cell (``MRMAP_TASK_PERF_SLOW_FACTOR``, default
    2.0), bounded by ``MRMAP_TASK_PERF_SLOW_MIN`` and
    ``MRMAP_TASK_PERF_SLOW_MAX``. A fixed burn cannot work: the 50 ms which
    doubles a 20 ms probe fire is 1% of a 4-second import chunk, and the first
    real run measured exactly that - a 1.03x arm the detector was right to call
    clean and the harness was wrong to call a demonstration. Bounded on purpose:
    an arm that takes an hour to be slow proves only that the harness can be slow.

Each injection declares what it installed; an arm whose injection did not fire
is reported as untrustworthy instead of as a clean result.

Running the quick, deterministic half
#####################################

The light half is the suite plus the analyzer. It needs no worker and no broker,
runs in one test process, and is the part CI is allowed to run:

.. code-block:: bash

    # from the repository root; one stack per job, its own project name (AGENTS.md)
    scripts/task_perf_runner.sh --family harvesting.import_chunk \
        --repeats 7 --seed 20261121 --out backend/task-perf

That script owns the whole flow - compose project, database healthcheck, one
test process with ``--keepdb`` and **without** ``--parallel`` (four Django test
workers on one PostGIS measure contention, not the task), then ``load``,
``report``, ``summary``, ``detect`` and ``gate`` over what the run wrote. It
fails loudly on a missing image, a skipped suite or an empty output directory:
a report that silently contains no measurements is the flakiness this issue is
about in its worst form, a green that measured nothing.

Two of its rules are about paths and selection, because both were once wrong in
a way that only showed up as an empty artifact an hour later:

- ``--out`` has to sit under ``backend/``. The test container shares exactly one
  directory with the host - ``docker-compose.dev.yml`` bind-mounts ``./backend``
  at ``/opt/mrmap`` - so a record written anywhere else inside it is invisible
  outside, and the nightly would upload nothing. The runner is given the host
  path and derives the container path from it, so the two cannot drift apart.
  The directory belongs to one run: it is emptied of the previous run's
  artifacts before anything is written, and the files which feed ``report`` are
  read from the manifest the workload process appended to as it wrote. A rerun
  into a used ``--out`` therefore reports the cells it measured itself - not a
  family it never selected, and not the repeats of the run before it, whose
  count would have inflated the ``cv`` the stability floor reads.
- ``--family`` selects the workload, and is checked before the stack boots: the
  name has to be a first-party family which a bench class actually measures, so
  a typo and a registry family nobody timed are refused in a second instead of
  ending in a two-minute stack which skipped everything.
  ``scripts/task_perf_bench.py families`` lists both sets, and
  ``families --check NAME`` runs that same check on one name.
  The bench classes compare themselves against
  ``MRMAP_TASK_PERF_FAMILY``, which the runner passes through, and every other
  family **skips itself out loud** rather than being measured anyway: a nightly
  which asked for one family measures one family, and a report over part of a run
  is visibly partial. One workload file whose record the analyzer refuses is
  named and counted while the rest still reach ``report`` and ``detect``; the run
  ends red at the end, so a partial report can never read as a green one.

The same steps by hand, when you want to see one of them:

.. code-block:: bash

    export MRMAP_TASK_PERF_BENCH=1 MRMAP_TASK_PERF_REPEATS=7 MRMAP_TASK_PERF_SEED=20261121
    # one directory, named once: the test container writes it under /opt/mrmap,
    # which is ./backend bind-mounted, so the host reads it back as backend/task-perf
    export MRMAP_TASK_PERF_OUT=task-perf
    export MRMAP_TASK_PERF_FAMILY=harvesting.import_chunk
    docker compose run --rm --no-deps -e MRMAP_TASK_PERF_BENCH \
      -e MRMAP_TASK_PERF_REPEATS -e MRMAP_TASK_PERF_SEED -e MRMAP_TASK_PERF_OUT \
      -e MRMAP_TASK_PERF_FAMILY \
      django-tests python manage.py test \
      tests.django.system.test_task_runtime_bench --noinput --keepdb

    python3 scripts/task_perf_bench.py load --arm baseline --seed 20261121 \
      --fixture-dir backend/task-perf --out backend/task-perf/task-perf.jsonl
    python3 scripts/task_perf_bench.py report --in backend/task-perf/task-perf.jsonl
    python3 scripts/task_perf_bench.py summary --in backend/task-perf/task-perf.jsonl
    python3 scripts/task_perf_bench.py detect --in backend/task-perf/task-perf.jsonl \
        --arm sql-n-plus-one

The suite is **opt-in**: without ``MRMAP_TASK_PERF_BENCH=1`` every bench test
skips. A stopwatch in the normal ``unit-tests`` job is exactly the flakiness
this issue asks to remove, not to add.

For a real worker and a real broker - the only path that answers queue wait -
run the same workloads through celery with the eager switch off and read the
attempt rows; the record then labels its active time ``measured`` instead of
``measured_local``, which is the whole point of separating the two.

The heavy backlog arm (opt-in, dedicated runner)
################################################

The large-volume harvesting acceptance transferred from #1392 runs on a second
switch, so the repeatable half stays runnable on an ordinary machine:

.. code-block:: bash

    scripts/task_perf_runner.sh --family harvesting.import_chunk --heavy \
        --repeats 3 --out backend/task-perf-heavy

``--heavy`` drives the backlog of ``MRMAP_TASK_PERF_BACKLOG`` records (default
400000) in bounded chunks of ``MRMAP_TASK_PERF_CHUNK_SIZE`` (default 1000)
through the store-page and import-chunk tasks. The backlog is generated by the
seeding path, never eagerly materialised in one query, and the record says how
it was produced.

This arm is **not** part of any CI job, and it is not a projection: it either
ran against the backlog or the run says it did not run. Peak memory of the
measuring process and its cgroup limit are recorded with it, including whether
an OOM kill was observable - ``null`` when the counter is unreadable, never a
comforting zero. Where a figure comes from a smaller measurement rather than
from this run, its evidence label says ``projected`` and it is quoted as such.

Reading a run
#############

``report`` is the arm table (n, p50, p95, p99, cv, active vs queue vs
end-to-end, per-arm evidence). ``summary`` is the one-line-per-cell view a
reviewer actually reads: family, scale, arm, sample size, median active seconds,
coefficient of variation, the ratio over the baseline arm of the **same**
workload, and any detection. ``compare`` aligns two runs cell by cell,
distinguishing "slower" from "too noisy to say", and refuses to compare cells
whose workload digest differs.

The two claims the acceptance asks the tooling to be able to make are
``detect``-able directly, and all four arms were verified against the records of
a real run:

.. code-block:: bash

    python3 scripts/task_perf_bench.py detect --in backend/task-perf/task-perf.jsonl \
        --arm sql-n-plus-one --out backend/task-perf/detect.json

An arm is judged **one family at a time**. A run without ``--family`` holds every
family of the bench, and one slope fitted over all of them would ask how the cost
of a monitoring probe grows with the size of an import chunk - and read the
slowest family as the shape of all of them.

``sql_n_plus_one`` is decided by the slope of the **total** statement count over
the size of the workload (the 1/10/100+ record rungs of one arm), never over the
number of timed samples: one fire over a 1000-row backlog produces one timing and
a thousand statements, which is the shape the ``housekeeping`` arm actually wrote.
Slope is of the total rather than of a per-unit figure for the same reason -
dividing by a growing size makes the same linear code read as expensive at one
rung and cheap at another, and the first version of this detector called a
genuine per-row injection flat for exactly that. Super-linear growth (a tail of
the ladder clearly steeper than its head) is a verdict on its own; linear growth
is judged against what one unit legitimately pays, which the family registry
declares as its ``contract`` and ``families`` prints:

.. code-block:: text

    harvesting.import_chunk   contract={"http_calls_per_unit": 0, "statements_per_unit": 4}

``duplicate_remote_call`` compares the calls of the biggest rung against the
**same workload's baseline arm**: a call duplicated at every size is linear, so
neither a slope nor a per-unit count sees it - which is how the real
``harvesting.fan_out`` arm (1 call at 50 records, 2 at 5000) first hid. The
signature is a doubling, because a retry also makes more calls without being a
duplicate. ``slow_task_body`` is judged **per scale cell** - a second budget names
what one fire of one workload may take, and the 1000-record rung legitimately
costs more than the 1-record rung - against the budget *and* against the same cell
of the baseline arm, since the regression a pull request introduces is relative to
what the task cost before. Active time only, so waiting never becomes the finding;
``queue_wait_inflation`` reports separately.

A family which declares no contract judges only super-linear growth and says so in
the finding's ``note``, so a clean report cannot be read as an untested one. The
per-unit expectations of the CLI (``--expected-statements-per-unit``,
``--expected-http-per-unit``) override the registry either way.

Repeatability, and the thresholds it does and does not license
##############################################################

Measured on a Docker runner (the backend test image of this repository, host
with 20 cores), PostgreSQL 18.6 / PostGIS 3.6 read from the server itself, seed
20261121, the synthetic local fixtures named in the records - no production
endpoint is reachable from the suite and none is used. The figures below are
from those runs, with the repeat count each cell actually had:

.. list-table::
   :header-rows: 1

   * - workload / arm
     - n
     - median active seconds
     - cv
     - reading
   * - ``harvesting.import_chunk`` / large
     - 7
     - 4.2935
     - 0.096
     - the widest cell of the quick half; a 10 % spread on a 4 s workload needs
       more samples before a 25 % ratio means anything
   * - ``monitoring.wms`` / large
     - 2
     - 7.6182
     - 0.002
     - the mocked remote dominates the cell and is stable; 2 samples cannot
       certify it, so the cell reports ``insufficient``, not ``pass``
   * - ``monitoring.wms`` / typical
     - 2
     - 0.7149
     - 0.036
     - just outside the proposed floor at this sample size
   * - ``harvesting.fan_out`` / typical
     - 2
     - 0.0091
     - 0.052
     - millisecond work: a percent-scale verdict is not available here
   * - ``housekeeping.system`` / typical
     - 7
     - 0.0021
     - 1.038
     - a beat fire on an empty table cannot repeat to a percent; the floor is
       family-specific on purpose and time must not gate this cell
   * - ``housekeeping.system`` / typical, ``slow-body``
     - 7
     - 0.0533
     - 0.014
     - the injected arm: x25.77 over the baseline of its own workload, and the
       cv of the *injected* cell is far tighter than the baseline's - which is
       exactly why a verdict needs the baseline stable, not the anomaly

Two of these readings are the reason the gate refuses to speak without evidence
rather than picking a number, and one is the reason arms are compared only
inside a workload: an injected defect is *easier* to reproduce than the clean
task it sits in. The proposed thresholds, recorded in
``scripts/task_perf_baseline.json`` and deliberately **not** approved there:

- ``max_cv = 0.03`` - the coefficient of variation of an arm's repeat medians
  must sit inside 3 % before any verdict about that arm is made at all. A family
  whose own floor is looser says so with ``max_cv`` on its entry, because a
  family that cannot repeat to 3 % cannot be gated at 3 %.
- ``min_samples = 20`` - p95 and p99 require 20 attempts. Below that the analyzer
  reports p50 with its ``n`` and marks the cell ``insufficient``, which is a
  third state next to pass and fail.
- ``p95_ratio = 1.25`` - the proposed regression ratio over the baseline of the
  same workload. It is the value a reviewer is expected to confirm or tighten
  per family; nothing treats it as reviewed.

and the standing rule from the epic: **no mandatory performance gate exists
until a human approves one**. In CI the gate runs in ``warn`` mode, which
reports and never reddens a check. A blocking verdict needs, per family, a
baseline entry with a real ``active_p50`` / ``active_p95`` / ``slot_seconds``,
``reviewed: true``, an ``approved_by`` and ``block: true`` - set in a pull
request that shows the run it is based on. ``mode=block`` with no reviewed entry
reports ``skip`` for every cell and exits 0; it does not fabricate a pass.

Artifacts, redaction and bounds
###############################

- Records are written one per file under the run directory, named so the file
  names its own workload (``family__scale__arm__rN.json``); a rerun of the same
  workload overwrites its own file instead of accumulating readings nobody
  asked for. The JSONL is derived from them.
- ``units`` is capped (``--max-units``, default 2000 per record). When it is
  capped the record says so with ``units_truncated`` and reports the **true**
  counts of the whole sample - truncating the storage must never truncate the
  arithmetic.
- Retention truncation of the #1330 window and worker loss are labelled, and a
  retention-truncated window is refused unless it carries a note saying what was
  truncated.
- Credentials, URLs and payloads never enter a record. The environment block is
  platform, python, core count, cgroup limit, dispatch mode, cache condition and
  the database's self-reported version - read from the connection under test, so
  a record cannot drift from what it measured. ``monitored_uri`` and request
  bodies are not fields of a workload record at all; the storage paths of the
  probe artifacts of #1394 are never copied into a benchmark.
- CI uploads the run directory with ``if-no-files-found: error``, so a job that
  produced no measurements fails instead of publishing an empty artifact.
- ``.github/workflows/task-performance.yml`` is that job: a nightly on an
  otherwise idle runner, plus ``workflow_dispatch`` for a pull request that wants
  its own number. It is deliberately not a ``pull_request`` trigger - medians
  measured on a shared runner describe the neighbour, and a threshold tuned on a
  quiet machine reddens on a busy one. The gate it runs is ``warn``, always;
  blocking is a decision recorded in ``scripts/task_perf_baseline.json``, never
  here.

Instrumentation, slow-task correlation and Grafana
##################################################

``instrumentation`` measures the #1389 overhead by running the same workload
with the instrumentation off and on and reporting the difference as a ratio with
its own evidence label - the overhead of the measuring device is part of what is
being measured. ``correlation`` says whether the #1390 slow-task record of the
same ``task_id`` exists, so a benchmark and an operator alarm agree about which
executions were slow. Neither number is printed as measured unless the
underlying rows were actually read; otherwise the coverage list names what is
missing (``instrumentation_overhead_unmeasured(#1389)``,
``slow_task_correlation_unmeasured(#1390)``). The aggregates of #1391 consume
the same ``CeleryTaskAttempt`` rows, which is why the active time of an arm is
read from that table rather than from a second stopwatch.

Upgrade notes
#############

- The record schema is ``mrmap.task-perf.v1``. The analyzer refuses a record of
  another version rather than guessing at its shape; a new field is additive and
  optional, and a changed meaning is a new version - baselines are entries, not
  code, so a version bump forces the reviewed numbers to be re-stated.
- The baseline file is data and is reviewed as data. Its ``review_policy`` names
  who may approve an entry and what ``reviewed`` means.
- The CI job is optional and ``warn``-only. Removing it changes no verdict;
  enabling a blocking gate for a family is a reviewed change to one entry in one
  file.
- Heavy runs leave the backlog rows in the test database of the compose project
  they ran in. Use a project name of your own (``COMPOSE_PROJECT_NAME``), and
  drop it afterwards; nothing in the quick path touches them.
