.. _celery-task-sql-regression:

===============================
Celery task SQL regression page
===============================

This page documents the test-time regression guards of #1395 - the executable
half of the static audit at :ref:`celery-task-orm-audit`. The audit said where
every first-party Celery task touches the database and what should be true
about it; #1395 pins those statements with assertions that run in the normal
Django test suite: how many statements a task issues, how many rows a
statement hands back, and which plan PostgreSQL picks for the statements that
ride an index.

V1 scope, honored strictly: the guards measure **statements, rows and plans at
test time**. No runtime telemetry, no durations, no percentiles, no
production instrumentation and no dashboards were added - the timing story is
V2 (#1396), and the production instrumentation of #1330/#1326 is untouched.
Everything here runs inside ``CaptureQueriesContext`` over 0/1/10/100+
fixtures; nothing measures a live worker.

Where the guards live
#####################

- ``backend/tests/django/sql_guard.py`` - the guard library (mixins and
  helpers below).
- the family modules named in the coverage matrix, laid out like every other
  backend test: below ``tests/django/`` mirroring the app layout.
- ``backend/tests/django/registry/tasks/tests_sql_guard_contract.py`` - the
  contract of the guards themselves: the acceptance of #1395 is that the
  guards are trustworthy, so an N+1 **injected into a fixture loop must make
  ``assertNoNPlusOne`` fail**, a bulk rewrite of the same work must pass it,
  and a huge unbounded prefetch must fail the row guard **even though its
  statement count is lower** - a prefetch which drains whole tables is not
  an optimization.

Running them
#############

From the repository root, on the prebuilt dependency image (see
:ref:`development-prebuilt-images` and the Docker ownership rules of
``AGENTS.md`` - one stack per job, its own project name):

.. code-block:: bash

    export MRMAP_BACKEND_DEV_FP=$(python3 scripts/dev_image_id.py --resolve --image backend --build)
    export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"
    docker compose up -d postgis redis mapserver
    docker compose run --rm --no-deps -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \
      django-tests python manage.py test \
      tests.django.registry.tasks.tests_sql_guard_contract \
      tests.django.registry.tasks.tests_task_sql_monitoring \
      tests.django.registry.tasks.tests_task_sql_update \
      tests.django.registry.tasks.tests_task_sql_harvesting \
      tests.django.registry.tests_task_sql_alert_refresh \
      tests.django.system.test_task_sql_guards \
      tests.django.notify.test_task_sql_guards \
      tests.django.test_task_sql_singleton_fire \
      --noinput --keepdb

The family modules plus the contract and the singleton seam run as one
suite in seconds once the stack is up (``--keepdb`` reuses the created test
database; drop the flag after changing models or migrations). Each module is
runnable on its own with the same command and one label.

The guard library
##################

``SqlGuardMixin`` (``tests/django/sql_guard.py``) answers the three questions
V1 asks of any task:

``capture(run)``
    The ``CaptureQueriesContext`` of a zero-argument callable, plus what it
    returned. Everything else reads this capture.

``assertQueryCountIndependent(sizes, seed, run, per_row=0, extra=0)``
    The statement count of ``run`` does not grow with the seeded rows.
    ``per_row`` is how a deliberate per-record transaction is named honestly
    - the locked per-record read of the import (#895) is one sanctioned
    statement per record; an accidental per-row read of anything else
    exceeds the allowance and fails. An absolute budget is never asserted:
    what a task costs depends on what the task base owes per save (history
    writes), so guards compare measured sizes, never a magic number.

``assertNoNPlusOne(run, sanctioned=None, exclude=None, max_repeats=1)``
    No statement fingerprint repeats more often than allowed. The
    fingerprint folds literals, ``IN`` lists of any length and multi-row
    ``VALUES`` away, so ``WHERE id = 1`` and ``WHERE id = 2`` collapse into
    the one shape which gives the game away. ``sanctioned`` maps an
    SQL-substring to the repeats it allows - an allowance that grows only
    with the rows it names. ``exclude`` names statements the whole task base
    owes per record by contract (the ``simple_history`` writes are the
    standing example) and leaves them out narrowly.

``assertRowsReadBound(run, max_rows)``
    No captured SELECT hands more rows to the task than the bound. This is
    why the wide prefetch fails although its statement count fell. The rows
    are read from the cursor after each ``execute`` (``connection
    .execute_wrapper``) - see "plan assumptions" for why not EXPLAIN ANALYZE.

``explain_select(sql)`` / ``assertPlanUsesIndex(sql, table, index=None)``
    The plan of one captured SELECT, read without executing anything (see
    below). With ``index`` given, the named index must be among the scan
    nodes of ``table``.

``statements_of`` / ``first_index_of`` / ``table_counter``
    The capture read as data: statements per verb/table, the index of the
    first match (for lock-order assertions - the process-before-row order of
    #1263 is asserted this way), the table-count shape of a whole capture.

Coverage matrix
################

Green = the guard pins the current shape as a regression baseline; **red** =
a documented baseline the guard captures AS the waste, naming the issue that
must tighten it. A red baseline failing means the fix landed and the
assertion was not tightened with it - that is the intent.

.. list-table::
   :header-rows: 1
   :widths: 22 30 33 15

   * - Family
     - Guard module
     - What is pinned (baseline color)
     - Tightened by
   * - harvesting (chord, chunk, ``_store_page``, finish, import watch)
     - ``registry/tasks/tests_task_sql_harvesting.py``
     - chord fan-out and finish: constant in backlog size, index-backed
       reads (green, "already optimal" per audit); import chunk: exactly one
       locked read per record, coalesced progress (#958/#895), flagged row
       pays one UPDATE and the chunk continues (green, allowances named);
       ``_store_page``: job lock + duplicate count + bulk batches of 50,
       redelivery writes nothing (green, #688); ``watch_import_backlogs``:
       per open job - locked read, index-backed waiting-count, baseline
       write - and nothing per backlog row (green)
     - #1392 (scoped ``for_harvest_import`` plans); duplicate-guard index
       candidate for ``requested_url`` belongs to #1397, not to these tests
   * - registration metadata collection
     - same module, ``ReferenceClaimLockOrderTest``
     - the claim path locks process before row before any lease write
       (#1263, green - asserted from the capture order); a lost-permit
       delivery pays the re-lock reads and writes nothing (green)
     - #1392
   * - monitoring (``run_probe_check``, artifact purge)
     - ``registry/tasks/tests_task_sql_monitoring.py``
     - the by-pk probe fetch carries the ``setting__service__auth`` chain in
       its single SELECT via ``Probe.for_probe_execution()`` and ``layers``
       is read exactly once per GetMap probe (green since #1393 - both were
       the documented red baselines, tightened in the PR that moved the
       plan); one result INSERT, one capped progress UPDATE, no probe-row
       write (green); artifact purge: SELECTs constant per result model
       plus one sliced read per page, and one batched write per page of 500
       expired rows - shipped with #1394 (green) - and rows keep every
       column but ``response_body`` (green)
     - #1393; the purge shipped with #1394
   * - update jobs
     - ``registry/tasks/tests_task_sql_update.py``
     - the ``old_service``/``new_service`` plan is config-driven: a narrow
       config costs the service row plus the layer rows - two reads - and a
       wide config costs exactly its two configured service relation reads
       more; no element relation ever rides the service plan (green,
       #1393); the apply phase of a WMS update over 1/10/100 confirmed
       layer pairs, and of a WFS update over mapped feature-type pairs,
       costs one statement per pair and no more - the per-pair one is the
       history-attribution by-pk service read of every deleted candidate
       element (predates #1393, named by fingerprint in the guard), and
       each configured element relation is one IN read per side on the
       mapping rows (green, #1393; two distinct ``update_config``
       fixtures per service kind drive the shape)
     - #1393
   * - alert refresh
     - ``registry/tests_task_sql_alert_refresh.py``
     - one annotation SELECT per kind, never per service (green - the
       #1030 design); the storage probes for stored capability backups are
       answered by one listing per named document prefix instead of one
       probe per flagged record, shipped with #1394 (green); an open alert
       keeps its identity across refreshes (green, #1319/#1030)
     - #1394
   * - conformity checks
     - retired with #1458 and #1530
     - the three dead tasks and their liveness guard left the codebase with
       #1458: nothing on develop ever dispatched them and their abstract
       base fetch could never answer, so no query guard had anything to
       regress; #1530 then retired the rest of the family - models,
       managers, enums, plugin helpers, fixtures and all twelve tables -
       through ``registry/migrations/0062_retire_conformity_check_family``,
       per the decision record of gate #1528
     - #1458, gate #1528, #1530
   * - security log analysis
     - not pinned
     - already optimal as an ORM plan per the audit; its volume question is
       architectural (one task per logged response) and belongs to whoever
       owns the sampling story, not to a query-count guard
     - -
   * - notify housekeeping (watchdog, retention sweeps)
     - ``notify/test_task_sql_guards.py``
     - watchdog fire: process reads constant for 1 vs 10 stalled windows,
       incident reads bounded by the sweep plus the verdicts the fire
       publishes itself (green - the #1320 bound "≤ verdicts + constant"
       asserted exactly); the write slope equals the verdict count exactly;
       a dark fire reads no process rows; healthy processes cost zero
       writes; both retention sweeps (#1208 processes, #1319 incidents)
       delete in constant statements and never touch what stands (green)
     - -
   * - system housekeeping (``bound_task_attempt_samples``)
     - ``system/test_task_sql_guards.py``
     - the abandon loop grows per PAGE of 500, not per row; the retention
       DELETE is one statement; the hard cap costs the same whatever the
       excess; no sweep writes per attempt (green); the ``recorded_at``
       index landed with #1394 (``attempt_recorded_idx``) and the retention
       delete's plan is asserted against it (green)
     - #1394 (index shipped)
   * - the singleton seam every task pays
     - ``test_task_sql_singleton_fire.py``
     - an acquired fire costs exactly ``pg_try_advisory_lock`` +
       ``pg_advisory_unlock`` on the dedicated lock session and nothing
       else; a refused fire costs one statement and runs no body; five
       fires cost ten lock statements - the seam keeps no history between
       fires (all green; this is the one shape EVERY scheduled task pays)
     - -
   * - the guards themselves
     - ``registry/tasks/tests_sql_guard_contract.py``
     - injected per-row read and per-row write loops are detected; the bulk
       rewrite of the same work passes; the sanctioned per-record allowance
       passes; a wide prefetch FAILS the row guard although its statement
       count is lower; EXPLAIN helpers refuse writes and locking reads; the
       row guard measures locked reads without EXPLAIN; statement order is
       answered from the capture
     - -

Manager-first checklist for a new or changed Celery task
#########################################################

The conventions of #1397, condensed into what a pull request adding or
changing a Celery task must answer before it is reviewable:

1. **Selection logic lives on a manager/queryset, not in the task body.**
   Reuse an existing plan from ``registry/querys/``, ``registry/managers/``
   or ``extras/managers.py``; if none fits, add a named, scoped plan
   (``for_probe_execution()``, ``for_update_diff()`` - the audit names the
   shape per family) instead of chaining ``select_related`` inside the task.
   The composition of the existing managers (CTE, history, tree) is
   preserved by extending them, never by replacing them.
2. **A scoped plan carries only what its task reads.** ``prefetch_whole_service``
   is the API's plan; a task that updates one service builds its plan from
   what its config names. Do not prefetch what the body only needs in one
   place (the audit's probe/layers note) and do not pull backlog rows during
   the import fan-out - the harvesting guard of this page proves that bound.
3. **Per-record work must be named, not averaged away.** If the design runs
   one transaction per record (#895), say so in the test: ``per_row`` on
   ``assertQueryCountIndependent``, ``sanctioned`` on ``assertNoNPlusOne``.
   A per-row statement nobody can name to a contract is a bug the guard
   found.
4. **Capture the baseline the day the task ships.** Green if the shape is
   right; if the shape is known-bad, land the red baseline anyway with the
   tightening issue named in the failure message, exactly like the ones in
   the matrix above.
5. **Assert the plan only where the index exists.** Index candidates live in
   the audit until a schema change lands them; until then assert statement
   shape, not the plan.
6. **New task, new singleton seam check.** Every scheduled task runs through
   ``SingletonTask``; if a task skips that base or acquires locks outside the
   seam, the statement-shape test of the seam does not cover it - say why.
7. **Runtime is #1396.** A guard that measures seconds does not belong here;
   it belongs to the telemetry which has the p95/p99 and the dashboard, and
   would grow the drift tables this page's singleton guard refuses entry to.

Plan assumptions, written down
###############################

What these guards assume about PostgreSQL, so a failure can be read without
guessing:

- **EXPLAIN without ANALYZE only.** ``explain_select`` wraps the captured
  text in plain ``EXPLAIN`` - the planner runs, the statement does not. The
  helper REFUSES anything that is not a bare ``SELECT`` (no ``INSERT``,
  ``UPDATE``, ``DELETE``, no ``FOR UPDATE``), because an ``EXPLAIN ANALYZE``
  or a careless replay would execute it. The contract test asserts the
  refusal.
- **Row counts come from cursors, not from EXPLAIN ANALYZE.** The first
  attempt at the row guard measured ``actual rows`` by re-running captured
  text under EXPLAIN ANALYZE; that measures a DIFFERENT statement, because
  Django's captured SQL has the bind values rendered and a sliced queryset's
  ``LIMIT`` is not part of it. The guard therefore reads ``cursor.rowcount``
  via ``connection.execute_wrapper`` around the real execution, which also
  makes locked reads measurable without executing anything twice.
- **Small test tables lie to the planner.** A ten-row table prefers a seq
  scan whatever the index; a plan assertion over such a table is a coin
  flip. ``off_seqscan()`` sets ``SET LOCAL enable_seqscan = off`` (it lives
  and dies with the test transaction) and the assertion reads "if a scan of
  this table were indexable here, would the planner take the index?".
  Where two indexes cover a prefix equally well (the backlog's
  ``(job_id, -id)`` versus #886's ``(job_id, has_import_error)``), the
  choice is statistics, not contract: the guard pins the catalog's exact
  column order and the never-a-scan property separately, instead of naming
  one index on a coin flip.
- **Captures render parameters; fingerprints fold them.** The captured SQL
  has values filled in, which is why per-row statements differ textually and
  must collapse through ``normalize_sql``/``fingerprint`` before they are
  counted. Multi-row ``VALUES`` lists are distinguished from single-row
  inserts on purpose: a bulk insert is one statement, a loop is not.
- **``--keepdb`` and test databases.** The guards create and measure over the
  kept test database; after changing models or migrations, drop the flag
  once so the database is brought up to date, else a plan assertion reads a
  stale index set.
- **Broker and storage stay mocked.** The watchdog guards patch the celery
  inspection exactly like the watchdog suite (on ``celery.app.control.Control``);
  the alert-refresh storage guard counts ``storage.exists()`` calls, because
  storage probes are not SQL and must be counted where they are paid.

Not covered here, and why
##########################

- **conformity**: #1394 established that no first-party code dispatches the
  family and that its tasks read the abstract run base, which has no table -
  a query guard would measure a dead path. The tasks retired with #1458 and
  the whole family, schema included, retired with #1530, so there is nothing
  left to guard. **security-log-analysis**: already optimal per the
  audit; a count guard would re-assert a conclusion that has nothing to
  regress.
- **Runtime behavior of any kind** - durations, backpressure, queue drain:
  #1396 owns it, and the singleton guard above is deliberately the pin which
  keeps its drift tables out of the lock seam.
