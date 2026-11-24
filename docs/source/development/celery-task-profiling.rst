.. _celery-task-profiling:

=========================================================
Root-cause profiling of a slow Celery task (opt-in)
=========================================================

.. sidebar:: Issue #1389 · epic #1387 · **phase V2**

    Part of epic #1387 (task performance), deferred to **V2** by that epic:
    the profiler answers "why is this task slow", which the V1 issues of the
    epic deliberately do not ask. The lifecycle numbers it reads belong to
    :ref:`celery-capacity-telemetry` (#1330), the shape of the queues it runs
    on to :ref:`celery-queues`, and the read-only endpoint in front of the
    attempt rows to :ref:`capacity-snapshot` (#1326). The guards that keep a
    task from *becoming* slow are on
    :ref:`celery-task-sql-regression` (#1395).

The V1 telemetry of #1330 answers **how long** an attempt waited and occupied
a worker. When a task shows up as slow there, that answer is not enough: the
same ``active_seconds`` is a missing index, a catalogue which stopped
answering, and a spin over a large document, and each of those has a different
fix. This page documents the opt-in profiler that separates the three -
``backend/system/task_profiling.py`` - what it costs when it is switched on,
and what a report actually looks like.

**It is off by default and stays off.** Nothing in a normal deployment
measures anything: the mode needs the switch *and* a named task *and* the
sample. The whole point of that gating is that the answer below is bounded,
so an operator can leave it on for one task while chasing one incident.

What one switch turns on
========================

Six environment variables reach the settings of the same name
(``backend/MrMap/settings.py``); every read happens per signal, so a worker
picks up a change after its next task without a rebuild:

``MRMAP_TASK_PROFILING``
    ``on``/``1``/``true`` turns the mode on at all. Unset is off, and off
    means the receivers return at their first check.
``MRMAP_TASK_PROFILING_TASKS``
    comma-separated task names - the **allowlist**. An empty allowlist
    profiles nothing even with the mode on, which is what makes "switch it on"
    safe as a first step.
``MRMAP_TASK_PROFILING_SAMPLE_RATE``
    probability of profiling an attempt of an allowlisted task, default
    ``0.05``. The decision is made *from the task uuid*, not from a random
    draw: every process that sees the same uuid reaches the same verdict, so a
    producer which logs and a worker which profiles agree on which attempts
    have a report.
``MRMAP_TASK_PROFILING_BUFFER_LIMIT``
    how many reports one process holds before it starts dropping them
    (default 200). A drop is counted, never blocking and never raised.
``MRMAP_TASK_PROFILING_MEMORY_MIB``
    how far an attempt must push the process's high water mark before an
    unaccounted run is called ``memory_bound`` rather than
    ``cpu_or_unaccounted`` (default ``128``). An absolute figure rather than a
    share of the attempt: a peak is worth naming because of how close it comes
    to the container's ceiling, not because of how long the attempt ran. ``0``
    switches the reading off, which leaves ``cpu_or_unaccounted`` the only
    answer for a slow attempt whose SQL and HTTP totals explain nothing.
``MRMAP_TASK_PROFILING_MEMORY_SAMPLE_SECONDS``
    the seam duration from which the closing memory read is worth paying for
    (default ``0.5``). The ``smaps_rollup`` behind the private-dirty figure is
    a read over every mapping of the process, so a task of ten thousand fast
    queries must not pay it per query, while the statement or request which
    held the cursor for seconds is exactly where a peak is expected to appear.
    The read which opens an attempt's span is unconditional, since that is what
    the movement is measured from.

Four more numbers tune the reading rather than the collection. They are read
from the settings through the same ``getattr`` seam, each with the default in
brackets, so a deployment overrides them in the settings file when it needs to
and nobody has to name them otherwise: ``TASK_PROFILING_SLOW_SECONDS`` (the
budget an attempt must exceed to be called slow at all, 30 s),
``TASK_PROFILING_SHAPE_THRESHOLD`` (which share of an attempt's active time
makes one category the diagnosis, 0.5), ``TASK_PROFILING_SLOW_SQL_SECONDS``
(the per-statement threshold above which a statement is reported by its
redacted signature, 0.5 s) and ``TASK_PROFILING_MAX_SLOW_STATEMENTS`` (how
many such signatures one attempt keeps, 10).

Turn it on for one task, read one report
========================================

::

    # 1. the deployment-wide switch, plus the one task to investigate
    MRMAP_TASK_PROFILING=on
    MRMAP_TASK_PROFILING_TASKS=registry.tasks.harvest_csw_records
    MRMAP_TASK_PROFILING_SAMPLE_RATE=1.0   # during the incident only

    # 2. let the worker restart with it (the receivers read at every signal,
    #    but the wrapper on the DB connections attaches on creation)
    docker compose ... restart celery-worker

    # 3. read what the process buffered - in the worker, not in a shell:
    #    the reports are process-local until something drains them
    python manage.py shell -c "from system.task_profiling import \
        drain_reports, lifecycle_map; from system.models import \
        CeleryTaskAttempt; \
        print(drain_reports(lifecycle=lifecycle_map( \
            CeleryTaskAttempt.objects.filter( \
                task_name='registry.tasks.harvest_csw_records') \
            .values('task_id', 'attempt_no', 'active_seconds', \
                    'wait_seconds'))))"

``drain_reports()`` answers the buffered reports and removes them, which is
what keeps the buffer bounded across a long-lived worker; without the
``lifecycle`` argument a short attempt honestly reads ``fast``, because
nothing in the profiler knows whether the message waited. The rows handed in
are #1330's, joined by ``(task_id, attempt_no)`` - the same key both buffers
use, so no second identity scheme exists to keep in sync.

The read side is deliberately not an HTTP endpoint: a report is process-local
state of a worker, and a web worker cannot serve another process's buffer. An
endpoint over the persisted attempt rows stays #1326's contract, which this
change does not touch.

What a report says
===================

The committed sample is
:download:`evidence/task-profiling-sample-output.json
<evidence/task-profiling-sample-output.json>` - four attempts produced by the
shipped code path, one per diagnosis, at the default thresholds. Its four
``shape`` values are the four readings #1389 names; the fifth the code answers
today arrived with #1620 and is documented after them:

``sql_bound``
    the ``build_webmapservice`` attempt ran 61.6 s of which 61.0 s was SQL, and
    one statement of 44.2 s is named by its redacted signature::

        SELECT "reg_layer"."id" FROM "reg_layer" WHERE "reg_layer"."name" = %s

    That is the answer a fix can act on: one statement, one placeholder, no
    values. ``slow_sql_seconds`` says how much of the SQL total the reported
    statements account for, so the gap to ``sql_seconds`` stays visible instead
    of pretending the sample is complete.
``http_bound``
    the ``harvest_csw_records`` attempt spent 58.0 s of 59.5 s in nine external
    calls, four of them answered as errors. Nothing in the database can fix
    this one, which is the point of keeping the category apart.
``queue_wait``
    the ``update_wfs_capabilities`` attempt ran 0.6 s while its
    ``wait_seconds`` was 412.0. **This was never a slow task - it was a message
    which waited**, and the shape is decided from #1330's wait rather than from
    anything measured here, exactly so that the two cannot be conflated. The
    fix belongs to the queue, not to the code.
``fast`` with ``partial: ["retry"]``
    the ``monitor_probe`` attempt was short and asked for a retry. The retry is
    recorded on its attempt, so a chain of quick retries which together occupy a
    worker for ten minutes reads as what it is instead of vanishing.

The other values answer the honest edges: ``cpu_or_unaccounted`` for a
slow attempt whose SQL and HTTP totals do not explain it - *named*, never
renamed into a fake CPU total - ``mixed`` for a slow attempt no category
dominates, and ``null`` for an attempt never measured against an active time,
which stays unknown.

``memory_bound`` (#1620)
    the fifth reading of an unaccounted slow attempt: it consulted only after
    neither SQL nor HTTP dominated, and only once the attempt pushed the
    process's high water mark by ``MRMAP_TASK_PROFILING_MEMORY_MIB`` (128 MiB
    by default). Without it the only answer a memory-hungry task can get is
    ``cpu_or_unaccounted``, which sends the reader looking at CPU when the cost
    is the objects the attempt held. The committed sample predates it and
    therefore shows four shapes, not five - whoever refreshes that sample must
    add a ``memory_bound`` attempt *and* the six ``memory_*`` keys below, or
    the sample will contradict this section.

Alongside the shape, a profiled attempt carries what it did to the memory of
its worker, read off procfs:

``memory_peak_rise_mib``
    how far the attempt pushed the process's high water mark - the number a
    peak measurement is really about, since a prefork worker's peak is only
    ever reached during some attempt's work;
``memory_retained_mib``
    how much resident memory the attempt did *not* give back - the growth in
    RSS between its first and its last sample, which is what a retained object
    looks like from outside, and the retained-object half of #1620;
``memory_peak_mib`` / ``memory_private_dirty_mib``
    the absolute peak and the private dirty set at the last sample;
``memory_limit_mib`` / ``memory_of_limit``
    the container's ceiling and how far the peak reached into it, because a
    ceiling is what turns a peak into a risk of an OOM kill. The ceiling is
    read per signal and never cached: a prefork worker lives across
    ``docker update --memory``, which is exactly what an operator reaches for
    during the incident a report is read in, and a cached ceiling would keep
    judging every later peak against a limit which no longer exists.

The absolute values belong to the process, not to the attempt - a prefork
worker is reused and already holds whatever earlier attempts left behind - so
everything attributable is the *movement* inside the attempt's span. Each key
is present only when the reading behind it answered: a procfs without
``smaps_rollup`` costs ``memory_private_dirty_mib``, an unlimited container
costs ``memory_limit_mib`` and ``memory_of_limit``, and with no procfs at all -
or an attempt never sampled - the keys are simply absent. An absent reading is
never reported as ``null`` or as a zero: a reader must not be able to mistake
"the platform could not answer" for "the attempt measured zero", which in an
OOM investigation is the difference between a lead and a dead end.

Chains and retries correlate through ``root_id``/``parent_id``/``queue``, which
celery already carries: every report of one chain shares its ``root_id``, so a
chord whose 40 children are individually fast and collectively slow is one
group by that key rather than 40 unrelated rows.

Redaction is a hard rule
========================

``redact_sql()`` keeps structure and drops values: double-quoted identifiers
and the ``%s`` placeholders of Django stay - they are what identifies the
statement - while single-quoted literals and bare numbers become ``?``. The
``params`` argument is **never read** by the profiler at all, so the values
cannot leak through a code path the reader has to trust. The signature is
length-bounded like the slow request dumps of #1353 for the same reason: a
statement signature is diagnostic context, not a document.

That rule is why no ``EXPLAIN (ANALYZE BUFFERS)`` is issued anywhere in this
code. #1389 permits running it only as a *controlled analysis of a confirmed
statement*, which means a person runs it against a database they chose, after
the signature above has identified the statement. Automating it here would run
an instrumented copy of a production statement, and that is not this tool's
call to make.

What it costs, measured
=======================

The budget the acceptance criteria ask for is a number under **representative
high fan-out**, not an estimate (#1387: no always-on overhead). Measured on
2026-11-21 inside the ``django-tests`` container of this checkout's stack - the
prebuilt backend image, its own PostGIS, one process - against ``SELECT 1``
through a real cursor and the real ``task_prerun``/``task_postrun`` receivers,
best of three arms per side.

The representative shape is the fan-out the registry actually produces:
**1000 attempts of one task, all children of one ``root_id``, 3 queries each** -
the shape of a harvest or a service build whose children are individually small,
which is also the shape that stresses the bounded buffer, since 1000 attempts
arrive against a limit of 200.

.. list-table:: 1000-attempt fan-out, instrumented vs. off
   :header-rows: 1
   :widths: 22 20 20 18 20

   - - arm
     - wall clock
     - per attempt
     - delta
     - what the profiler did
   - - off (mode unset)
     - 0.461 s
     - 0.461 ms
     - —
     - nothing
   - - on, ``sample = 1.0``
     - 0.545 s
     - 0.545 ms
     - **+84 µs**
     - 200 profiled, 800 dropped
   - - on, ``sample = 0.05`` (default)
     - 0.479 s
     - 0.479 ms
     - **+18 µs**
     - 42 profiled, 0 dropped

So the budget an operator can rely on is: **well under a tenth of a
millisecond per attempt at full sampling on a burst a hundred times larger than
a default buffer, and under twenty microseconds at the shipped rate** - on
attempts whose own cost is a fraction of a millisecond, which is the worst
relative case. A real registry task runs seconds, so this is far below what the
same attempt's SQL already costs, and nothing here scales with task *duration*:
the profiler samples attempts, so a task which runs an hour is measured on one
attempt like a task which runs a second.

Two readings matter more than the arithmetic:

- the full-sampling arm **profiled 200 attempts and counted 800 drops** - that is
  the buffer doing its job under fan-out. The cost stayed bounded while the
  volume grew a hundredfold, and ``profiling_stats()`` reports the 800 rather
  than leaving them silently missing, which is how an operator learns the sample
  was thinner than intended instead of reading a thin sample as the truth.
- at the shipped default rate the same burst cost 42 profiles and **zero drops**:
  5% of 1000 attempts is 50, which sits inside a limit of 200 with room for the
  two other allowlisted tasks of the same worker. The default rate is what keeps
  a burst of fan-out inside the buffer, so a burst needs no extra tuning; the
  1.0 arm is the deliberate incident setting where drops are expected.

The three bounds those numbers rest on:

- an attempt which is not sampled costs one identity check on the uuid plus the
  allowlist membership test; the SQL wrapper still times statements for
  allowlisted tasks, which is what makes an unsampled attempt of an allowlisted
  task cheap but not free - so the allowlist, not the rate, is the main lever;
- slow statements are kept to ``TASK_PROFILING_MAX_SLOW_STATEMENTS`` per attempt
  and reports to ``TASK_PROFILING_BUFFER_LIMIT`` per process, so memory cannot
  grow with how long the mode stays on or how wide the fan-out is;
- the profiler **writes no database rows** - asserted by a test which counts
  queries across a whole profiled attempt - so enabling it cannot add load to
  the database which is already the suspect. Reports leave the process only when
  something drains them; if nothing does, they are dropped and counted.

A smaller arm, worth naming because it is the only one which resolves a
per-attempt constant: 200 attempts × 1 query measured +22 µs with the profiler
on, while the arms of 8 and 100 queries measured −15 µs and −42 µs, i.e. inside
the noise of the measurement. The single-query arm charges the two fixed signal
calls to one statement, so it is the honest figure for the seam's fixed cost and
the sign of the longer arms is what noise looks like at this resolution.

Fail-open is the last bound: every seam catches its own exception and logs at
debug, including the HTTP wrapper, which calls through to the real
``Session.send`` before recording anything. A profiler that breaks a task is
worse than no profiler, and this one is written so that the worst it can do is
cost you the profile.

Where it must not go
====================

Per epic #1387, no always-on profiling: this mode is not a metrics pipeline and
nothing here ships reports to VictoriaLogs. The permanent answers of the epic
stay the cheap counters of #1330 plus the guards of #1395, which hold whether
or not anyone is investigating. The profiler's own counters
(``profiling_stats()``) exist so that an operator can see a full buffer instead
of wondering whether a report is missing, and the mode is switched back off when
the incident is closed.
