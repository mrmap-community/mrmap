.. _task-memory-shapes:

=======================================================
Task memory shapes in harvesting, monitoring and update
=======================================================

Issue #1620, part of :ref:`runtime-memory-baselines` / epic #1612, on the rule
#1613 states for this area and with the measurement convention #1615 requires:
a worker's memory claim is only real if a number bounds it and a measurement
backs it.

What the issue pointed at
=========================

Three worker paths were named as candidates for an unbounded working set -
one page, one backlog, one document set at a time - and each was measured
before anything was changed. Two of the three were real and are fixed here;
the third did not survive its measurement and is documented as a negative
result, because a claim nobody measured is the same claim #1613 retired for
the pool bounds. The instrument these numbers were taken with is the memory
half of :doc:`celery-task-profiling`.

Monitoring - the probe's answer is decoded once
===============================================

``Probe.check_does_not_contain`` read ``response.text`` once per needle.
``requests`` decodes the body on every read of ``text`` (no cache; only
``content`` is the stored bytes), so a probe with five needles decoded the
whole capped answer five times per monitored service - and an ETF check,
which fans out per test step, repeats it per step. A successful check is
the common case, so this ran on every scheduled monitor.

The check now reads the text once through ``_response_text`` and searches
that. The same helper is the one place that knows why the response's own
``text`` must not be kept on the instance: the instance lives on through the
whole check sequence, and the answer is capped only for XML, so an image
answer would otherwise be held by the probe and survive into the failure
trail as well.

What it cost, and what it costs now (measured): a 5 859 676 byte answer -
over the XML cap, so this is the worst legal answer - and five needles.
Per arm: peak traced bytes and the number of full decodes of the body.

.. list-table:: ``check_does_not_contain``, 5 needles over a 5.9 MB answer
   :header-rows: 1

   * - arm
     - peak traced
     - full decodes of the body
     - wall clock
   * - before (one ``response.text`` per needle)
     - 5 860 053 B
     - 5
     - 37.5 ms
   * - after (one decode, ``_response_text``)
     - 5 860 053 B
     - 1
     - 27.0 ms

Honest reading: the *peak* does not move - the check still needs the decoded
body exactly once, and that is the floor. What is gone is the four
superfluous decodes: the allocation churn behind them and about a quarter of
the wall clock. The improvement is per monitored service per check run and
per ETF step, so on a stack monitoring many services this is the worker's
baseline churn, not an outlier path. If a future audit needs a peak
reduction here, the change is the decoder's (search bytes for ASCII
needles), not the check's, and it would have to be measured again.

Update - the reference planning reads keys, not documents
=========================================================

An update's metadata step collects the references which advertise a service
and its elements, and the adoption moves those rows onto the published
service. Both read ``remote_content`` - the stored capabilities document -
although neither writes it and neither reads it. The cost is not one
document: one document is advertised by *every* element, so the read pays
the document once per row, and a WMS with thousands of layers has thousands
of copies of the same text.

``advertised_references`` (``registry/tasks/service.py``) and the move in
``ServiceUpdateJob._republish_references`` (``registry/models/update.py``)
now read those rows with ``defer("remote_content")``. The read is scoped
(only the service's own rows), the deferred column is not in the SELECT, and
the shipped answer of the planning - element and url - is complete. The
bulk update behind the move writes only ``describes_id``, so the text it
never reads is also never written.

Measured, both arms in one process over the same rows, 3 repetitions, best
of each set; the document is a 44 000 byte capabilities document, the size
of a real one for a mid-sized service. The planning read covers 2 000
element references plus the 1 000 service rows, the move 1 000 elements over
the same document.

.. list-table:: the reference read of an update - CPython heap
   :header-rows: 1

   * - path
     - shape
     - peak traced
   * - ``advertised_references``
     - before: full model instances
     - 89 177 985 B
   * - ``advertised_references``
     - after: ``defer("remote_content")``
     - 1 105 771 B
   * - ``_republish_references`` move
     - before: full model instances
     - 46 980 351 B
   * - ``_republish_references`` move
     - after: ``defer("remote_content")``
     - 395 148 B

``advertised_references``: 80x. The move: 119x. Both are the *worker's* heap
during the step, so the numbers are what a worker holding one such update
could not give back until the step ended.

The same two arms measured at the kernel, in **separate processes** - RSS is
a per-process high-water mark, so an arm which has once touched its bytes
cannot share a process with the other arm. The process reads its own
``/proc/self/status`` (``RssAnon``, ``VmHWM``) and ``/proc/self/smaps_rollup``
(``Pss``, ``Private_Dirty``) before and after the call, plus the wall clock.
``RssFile`` moves 0 kB in every arm, so the growth below is anonymous memory,
and ``Pss`` tracks ``RssAnon`` exactly because nothing here is shared.

.. list-table:: the reference read of an update - anonymous RSS, PSS, throughput
   :header-rows: 1

   * - path / arm
     - ``RssAnon`` delta
     - ``Pss`` delta
     - ``VmHWM`` delta
     - wall clock
   * - planning, before
     - +84 kB
     - +84 kB
     - **+99 288 kB**
     - 0.706 s
   * - planning, after
     - 0 kB
     - 0 kB
     - **0 kB**
     - 0.042 s
   * - move, before
     - +68 kB
     - +68 kB
     - **+5 444 kB**
     - 0.470 s
   * - move, after
     - 0 kB
     - 0 kB
     - **0 kB**
     - 0.036 s

The ``RssAnon`` *delta at the end of the call* is small in every arm because
CPython frees the instances the moment the list goes out of scope and glibc
keeps the arena; the number which decides an OOM is ``VmHWM``, the high-water
mark the worker could not give back while the step ran - and that is 99 MB
and 5 MB before, and **unchanged from the baseline** after. Throughput
follows the same line: the planning read is 17x and the move 13x faster,
because the text is no longer fetched from PostgreSQL, decoded into Python
``str`` and re-materialised once per row.

The reduction is proportional to ``references x document``: for a service
whose advertised document is larger, or which has more elements, the
before-number is larger in the same proportion and the after-number barely
moves - that is the point of the defer, the working set is now the keys, not
the documents.

Harvesting - the import fan-out builds its chord from a cursor
===============================================================

``call_chord_md_metadata_file_to_db`` read the ids of the whole pending
backlog into a Python list before chunking it into the chord. The list is
the whole backlog's worth of Python int objects plus the list's own
pointers, held by the building worker while it *also* holds the group
object it is building - and a backlog is exactly as large as the harvest
that just downloaded it, which is the size the harvest's own page bounds
never constrained.

The read is now ``.values_list('pk', flat=True).iterator()``: django's
chunked fetch opens a named server-side cursor (verified against
``pg_cursors`` on the stack below), so the ids are consumed as far as the
chunker needs them and the building worker holds one fetch and one chunk
(50 ids) plus the group. The query is unchanged and still covered by
``harvest_tmp_md_file_import_pending_idx`` - the same partial index the
chunker's own ``id > watermark`` filter uses (the cursor needs no order
change for that, the index scan answers it either way). Because an
iterator has no ``len()``, the build counts the ids of the chunks it
creates, which is the same total the process name and the reconciliation
of #958 compare against.

Measured at the size the fix is for. The build is measured around
``iter_md_metadata_file_chunks``; peaks are traced bytes, and the wall
clock is the build's own loop.

.. list-table:: the chord build over a 100 000 row backlog
   :header-rows: 1

   * - arm
     - peak traced
     - wall clock
   * - before: ``list(values_list)``
     - 9 929 033 B
     - 0.067 s
   * - after: ``values_list(...).iterator()``
     - 272 186 B
     - 0.083 s

The peak is 36x smaller and no longer scales with the backlog - 272 kB is
the fetch size of the cursor and one chunk, so a backlog ten times as large
costs the same here where the list cost ten times as much. The build gets
~16 ms slower per 100 000 rows (0.067 -> 0.083 s) because the server-side
cursor fetches in batches instead of one result set: that is the price of
the bounded peak, and 16 ms per 100 000 records is not what the import
chord is timed by - each of its tasks opens its own transaction and reads
its own 50 files.

The same arm at 2 000 rows (the size a normal harvest actually has) leaves
67 kB against 57 kB: the cursor is never *worse* by a meaningful amount,
which is why no size threshold guards the change.

At the kernel, in separate processes and the same before/after-call reading
as the update section, the list's cost is visible as anonymous memory the
building worker grows and keeps: ``RssAnon`` and ``Pss`` move **+3 440 kB**
for the 100 000-id list and **+16 kB** for the cursor, ``RssFile`` 0 kB in
both. ``VmHWM`` reads 0 delta in both arms here - the setUp which created the
backlog rows had already touched that much arena earlier in the same process,
which is exactly why ``tracemalloc`` (above) is the primary instrument for
this path and the RSS reading is reported as its corroboration: the bytes are
the list's, and the cursor does not allocate them at all.

Harvesting - the page store keeps its shape (negative result)
=============================================================

The same issue asked whether the page store needs chunking. It does not, and
the measurement is the reason it was not changed.

``HarvestingJob._store_page`` builds a list of one
``TemporaryMdMetadataFile`` per record of a page and writes it with one
``bulk_create``. That list looks unbounded - a page is up to
``MAX_STEP_SIZE`` records - but the bytes of a record are never in it:
``md_metadata_file.save(..., save=False)`` spools the serialised record to
storage immediately and keeps only the file's *name* on the instance. What
the list holds is one thin instance per record, and the whole page is
written once.

Measured before/after with a page of 200 records at 50 kB each (10.3 MB
document) - the shipped whole-page list against the batched-write candidate,
both arms the same process, best of 3 repetitions - and with a page of 500
records at ~5 kB each (2.4 MB document):

.. list-table:: ``HarvestingJob._store_page``, peak traced
   :header-rows: 1

   * - page shape
     - whole-page list (shipped)
     - batched bulk write (candidate, not shipped)
   * - 200 records x 50 kB
     - 323 406 B
     - 352 647 B
   * - 500 records x ~5 kB
     - 523 122 B
     - 423 872 B

The candidate moves the peak by less than the run-to-run noise, in both
directions - which is the finding: batching adds a generator frame and the
batch bookkeeping while removing nothing, because the retained set it was
supposed to shrink was never there. A change with no measured improvement
and a visible cost in statements (one INSERT per batch instead of one per
page) is the change #1613's rule refuses, so the store is left exactly as it
was and the question is closed here: the page store is bounded by the page,
and its working set is the page's *instances*, not its bytes. The page's
bytes are bounded where they always were - ``MRMAP_CSW_MAX_RECORDS`` over
the response, and the storage spool.

How the numbers were produced
=============================

One disposable stack, the *deployed* shape, job-owned project
``mrmap-agent-1620-run1``; the container ``rev1620-tests`` from the
prebuilt dev image ``ghcr.io/mrmap-community/mrmap-backend-dev:a6db4c98151b``
(Python 3.15.2, Django 6.0.10, psycopg 3.3.9), its ``/opt/mrmap`` replaced by
this branch's ``backend/`` before each run - so the code measured is the code
shipped. PostgreSQL is the stack's own postgis service; the database is the
empty migrate-only floor of the Compose entrypoint (#1613's convention), with
the rows each arm needs created inside the measured test's own transaction.
Host: kernel 6.12.107+deb13-amd64, docker 29.10.0 - one host generation, to
be re-measured rather than extrapolated.

The harness is a Django ``TestCase`` per path that runs the old shape and
the new shape over the same rows in the same process and prints the numbers;
it is not in the repository, and every arm is reproducible from the tables
above:

* *peak traced* - ``tracemalloc`` around the call, with
  ``clear_traces()`` before each repetition and the best of 3 repetitions
  taken, which is what removes the noise a cold psycopg connection adds to
  the first repetition. This is the CPython heap of the measured worker,
  which is the right unit for "the worker cannot give this back"; it is
  not RSS, and it does not include the database's own memory.
* *full decodes* - a counter on the response's ``text`` property of a
  response of the shape ``requests`` answers with (decode per read), so the
  number is the library's behaviour, not the harness's.
* *wall clock* - ``perf_counter`` around the same call, after one warm
  repetition.
* *the RSS/PSS arms* - a separate ``manage.py test`` process per arm
  (``BENCH_ARM`` selects it), reading ``/proc/self/status`` and
  ``/proc/self/smaps_rollup`` around the call. One process per arm is not a
  stylistic choice: ``VmHWM`` and ``ru_maxrss`` are per-process high-water
  marks, so an arm which already touched its bytes in a shared process reads
  the *other* arm's peak. ``RssFile`` is reported alongside ``RssAnon`` so
  the reader can see the growth is anonymous, not page cache.
* the reference arms use 44 000 byte documents (a real mid-sized
  capabilities document), 2 000 reference rows for the planning read and
  1 000 elements for the move; the backlog arm uses 100 000
  ``TemporaryMdMetadataFile`` rows, and the probe arm a 5 859 676 byte
  answer - over the cap, so the worst answer a check may legally see.

What this does not claim
========================

* no stack-wide peak moved: these are per-worker heaps inside one worker at
  a time, and the stack's idle floor is #1614's and #1618's page, not this
  one. The epic's V2 question - how many workers a host can admit with
  these numbers - is still #1612's.
* the before-arms are *shapes*, reconstructed from the code as it was, not
  runs of an old revision: the old arm of the deferred read builds full
  model instances, the old arm of the build materialises the list. That is
  what the code did, and it is why the two arms of each table are
  comparable; it is not a git bisect.
* ``advertised_references`` and the move are measured over one service's
  rows. The deferral is per row, so a service with a bigger document or
  more elements scales the before-number up and leaves the after-number
  where it is - the tables above are one point on that line, not its
  ceiling.
* the ETF fan-out (#1620 mentions ETF checks as a consumer of the probe
  checks) is counted through the per-step arithmetic in the probe section;
  a full ETF run was not measured here, and its per-step overhead is
  #1623's subject.
* the probe's peak reduction would need the check to search bytes; that is
  a deliberate non-change, documented above rather than shipped unmeasured.
