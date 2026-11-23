.. _retention-inventory:

====================================================
Persistent-data inventory and storage growth (#1498)
====================================================

``manage.py retention_inventory`` answers one question for a deployment
administrator: *what does this instance keep forever, how fast is each part of it
growing, and which of those answers are actually measurements?* It is the
read-only half of the V1 retention work (#1497); the policies which would shrink
what it reports are #1499 and the domain issues, and they are written from this
output rather than from a guess at it.

The command **never changes anything**. Every statement runs inside one
``READ ONLY``, ``REPEATABLE READ`` transaction, so a write would raise instead of
happening, and nothing in it deletes a row, removes a file, flushes a cache key or
dispatches a task. That is why the command has no ``--confirm``, no ``--dry-run``
and no ``--force``: there is no second mode to guard.

Three files, three kinds of change
==================================

* ``system/retention_datasets.py`` — the declarations: which dataset grows, who
  owns it, what holds it, which decision gates it. Reviewed as **content**; a
  change here is a statement about the domain, not about a query.
* ``system/retention_inventory.py`` — the measurements: what PostgreSQL, the media
  storage, the caches and the disk say on this run.
* ``system/management/commands/retention_inventory.py`` — the presentation: one
  command, one report.

The split is deliberate. An operator reading the report has to tell a fact about
the domain apart from a fact about their database, and the two live in different
files with different reviewers. ``DECLARATION_VERSION`` is printed in every
report, so a ticket can name the declaration set a number came from.

Running it
==========

.. code-block:: console

   # the full report, as an operator reads it
   python manage.py retention_inventory

   # the machine-readable form, for a ticket or a diff between two runs
   python manage.py retention_inventory --format json --output inventory.json

   # one dataset, one table, a shorter window
   python manage.py retention_inventory --dataset monitoring_run
   python manage.py retention_inventory --table registry_harvestingjob
   python manage.py retention_inventory --window-days 7 --horizon-days 30

   # on a host which does not mount the media volume
   python manage.py retention_inventory --no-media

   # the cluster WAL counter, when the role may read it
   python manage.py retention_inventory --wal

``--table`` and ``--dataset`` narrow the database half and **fail loudly** for an
unknown name rather than answering with an empty report: a typo that returns
nothing looks exactly like a deployment which holds nothing. ``--dataset`` of a
family declaration measures all of the family's physical tables, because MTI
spreads one row over the base table and every subclass table and one of them is
not the footprint.

The defaults are ``--window-days 30`` and ``--horizon-days 90``. The window is the
interval the growth rate is counted over and the horizon is how far that measured
rate is projected for the risk ranking; both travel with every number they
produced, so a rate in a ticket carries the interval it came from.

A dash is never a zero
======================

The report's central discipline: every value is either measured or carries a
reason. The two are rendered differently — a measured zero prints ``0``, an
unmeasured value prints ``—`` — and the reason is named in the text report and in
``reason`` in the JSON. The codes an operator will actually see:

``no_rows_in_window``
    the window held no rows: the growth rate of a quiet deployment is unknown, not zero.

``no_time_field_declared``
    the dataset declares no timestamp to grow over (reference data, or an age which is only answerable through its owner).

``row_estimate_only``
    the table was never analysed, so ``reltuples`` is unset. The window count is still measured.

``table_absent``
    the table does not exist in this schema — typically a partially migrated deployment.

``scan_budget_exhausted``
    the media walk stopped at its budget; the bytes it counted are reported alongside, so the number reads as a lower bound.

``reference_limit_exhausted``
    the reference set stopped at its limit, so no file of that prefix may be called orphaned.

``query_failed``
    a catalog read failed. For the media reference sets this also voids the orphan answer: a column which could not be read would turn every file of the prefix into a false orphan.

``references_without_file``
    a row names a file the walk did not see: the record exists and its document does not. Those bytes are counted as neither referenced nor orphaned.

``storage_without_filesystem_location``
    object storage has no walk to take.

``path_outside_storage_root``
    a stored value resolves outside the storage root. The name is reported; the file is never opened.

``not_requested``
    the report half was not asked for (``--no-media``, or ``--wal`` left out).

What a run reads
================

The whole database half runs in one transaction with a 60 s ``statement_timeout``,
so a runaway inventory cannot become an outage. Row counts are ``reltuples`` (the
planner's estimate, labelled as such), sizes are ``pg_total_relation_size`` —
heap plus every index plus TOAST, the number freed disk space compares against.

Deliberately **not** reported, and named in ``provenance.not_measured`` rather
than estimated:

* the heap/index/TOAST split — the per-relation counters of
  ``pg_statio_user_tables`` are cumulative since the last stats reset and are not
  a current byte split;
* per-table WAL — ``pg_wal_bytes()`` answers cluster-wide since startup;
* deleted space actually reclaimed — ``DELETE`` returns nothing to the operating
  system until a vacuum, rewrite or WAL checkpoint does;
* broker and result-backend bytes — a broker round trip, which is #1500's tool;
* media on object storage — a storage without a filesystem location.

The media walk uses ``os.scandir`` below each declared prefix, does not follow
symlinks, and reads no file body at all — which is what makes it safe to name a
path which points outside the storage root instead of opening it. Reference sets
are ``values_list`` over the declared FileField columns: no instance is
materialised and no relation is followed. Because the prefixes are shared (the
``xml_documents`` tree holds the backups of three record tables and the capability
documents alike), the reference set of a prefix is the union over every column
which may point into it, and a prefix nested below another is walked by its own
source so the same bytes are never counted twice.

For each dataset the report also carries the deletion graph — the ``on_delete`` of
every incoming and outgoing FK and one-to-one, read from the model metadata —
together with the table's indexes and triggers from ``pg_index`` and
``pg_trigger``. A ``Protect`` trigger is how the keyword maintenance of #1009 is
still reachable after a rollback, and a retention ``DELETE`` which trips it is a
migration failure, not a size win. ``provenance.read_plan`` holds the
``EXPLAIN (FORMAT JSON)`` of the window read: a retention predicate that needs a
``Seq Scan`` on a large table is a finding of this inventory.

Growth rates
============

Two rates are answered and never merged:

``rows_per_day``
    counted rows of the window over the window — a measurement.
``bytes_per_day``
    that rate times the current average row size, so it inherits every
    uncertainty of the row estimate and is labelled as an estimate.

The ranking key is the projection of the second one over the horizon, so the risk
order is derived from what *this* deployment holds. A dataset whose window could
not be measured keeps ``rank: null`` rather than a rank invented from its
declaration — an unranked dataset is an honest gap, while a ranked one from a
stale declaration would send an operator to the wrong table first.

A family declaration is summed over all of its tables before the rate is
computed: a dataset which measures one table of an MTI chain would report a
fraction of its own footprint.

Gated decisions
===============

Sixteen datasets are gated behind a decision #1497 has not answered: whether an
error log is audit evidence, which statuses of an update job are truly terminal,
how many complete harvest runs the removal detection needs as its baseline, which
chart coverage the harvesting history screens must keep, and what #741 requires of
the audit and privacy classes. ``gates`` in the JSON names the decision per
dataset; the text report prints them after the numbers, and the command repeats
the count on stderr when it prints a report to a terminal.

The placement is deliberate: a report of large growing tables invites the next
command to be a deletion, so the gates arrive at exactly the moment that decision
would be made. **No retention policy for a gated dataset may be enabled, nor
shipped preview-only, until its decision is answered.**

Keeping the inventory honest
============================

``undeclared_tables()`` lists every table of an inventoried app which no
declaration covers. That is what makes "the inventory is complete" a checkable
claim instead of an aspiration: an app added to ``INSTALLED_APPS`` or a model
added to an app shows up there until it is declared, which is where the epic's
rule that a new continuously growing model declares its lifecycle gets enforced.

The declarations themselves are covered by tests which resolve them against the
running schema and the loaded models: every declared model resolves (concrete or
abstract), every declared table exists in the migrated database, every declared
``FileField`` is a real file field on a concrete descendant, every dataset names at
least one table, and the ``time_field`` of a dataset physically lives in one of its
tables. A declaration which drifts from the models therefore fails the suite rather
than quietly reporting a wrong number.

Read the tests as the specification of the expected deletion and reference
behaviour: each dataset carries ``test_expectations`` (what a dry run must not
touch, what a run over one scope must leave alone, and that re-running is a
no-op) and ``writers``/``readers`` name the code which produces and consumes the
rows. Those fields are the overlap map with the existing issues — #1237 and #1295
for the harvest backlog, #1208 for background processes, #1459 for the analyzed
response logs, #1480/#1482 for history, #1484 for monitoring deletion, #741 for
audit and privacy.

.. code-block:: console

   # the focused PostgreSQL suite of this inventory
   python manage.py test tests.django.system.test_retention_inventory

Related
=======

* :ref:`capacity-snapshot` — the committed work of the fleet, the sibling question
  to what this inventory measures on disk.
* :ref:`celery-capacity-telemetry` — the attempt samples the platform's own
  growth numbers come from.
* ``backend/system/retention_datasets.py`` — the declarations themselves.
