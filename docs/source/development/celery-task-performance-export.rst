.. _celery-task-performance-export:

============================================
Celery task-performance series and dashboard
============================================

:ref:`celery-capacity-telemetry` measures one execution at a time. Issue #1391
publishes the same measurement as a **series**: once per export window, the
deployment writes one small structured record per ``(task class, queue)`` and
one fleet record, and the Grafana of the stack reads them back. The difference
to a per-attempt log line is the point - a window of a busy deployment is
thousands of attempts and a handful of records, so the series is cheap enough
to always run and small enough to aggregate over a week.

This document is the contract between the exporter and the dashboard. Both
sides read it; when one changes what it emits or what it selects on, it
changes this page in the same pull request.

Off by default
==============

Nothing is published until the deployment says so::

    MRMAP_TASK_PERFORMANCE_EXPORT=on
    MRMAP_TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES=5

``MRMAP_TASK_PERFORMANCE_EXPORT`` is the only mode which also removes its own
beat row (:func:`system.apps.create_task_performance_export_task`) while it is
off, so a deployment which never installed the dashboard pays nothing for the
idea. The knobs of the exporter are in ``MrMap/settings.py`` next to each
other; the cadence **is** ``MRMAP_TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES``:
the beat row is scheduled from the same value, so one knob moves the window
and the fire which produces it. A window always continues where the previous
one ended, so a late fire widens the next window instead of shifting or
double counting it.

The record shape
================

One fire of ``system.tasks.publish_task_performance`` writes:

``fleet``
    exactly one record, the whole deployment for the window;
``class_bucket``
    one record per ``(task_class, queue)`` seen in the window, heaviest first,
    up to ``MRMAP_TASK_PERFORMANCE_EXPORT_MAX_BUCKETS`` of them;
``class_sample``
    up to ``MRMAP_TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS`` finished
    attempts of the heaviest ``MRMAP_TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES``
    classes - the rows an operator clicks into, not a series;
``coverage``
    exactly one record, the crash residue the attempt table is holding *right
    now*;
``class_coverage``
    the same read per task class which is holding residue.

The last two are a gauge read at every fire, not a partition of the window, and
they exist because the window cannot answer the coverage question: see
*Coverage is a state, not a window* below.

Every record of the windowed series - ``fleet``, ``class_bucket`` and
``class_sample`` - carries the same window - ``window_start`` (exclusive),
``window_end`` (inclusive), ``window_seconds`` - and ``source``, which is the
source class of #1330 the numbers came from. The coverage records carry
``measured_at`` instead: the moment the standing read ran, because they are
not a slice of anything. The fields beside them are the contract; an
unmeasured value is **absent**, never ``0``, because the semantics of the
source layer survive into the series.

``fleet`` - exactly one per window, the whole deployment:

``executions``
    attempts of the window
``slot_seconds``
    sum of measured worker occupancy - the occupancy of #1330
``succeeded`` / ``failed`` / ``retried`` / ``revoked``
    outcomes of the window
``uncertain_open``
    open rows this window flushed - a crash shows up here only if the row was
    *written* in the window
``uncertain_abandoned``
    of those, the ones the sweep had already flagged
``active_p50`` / ``active_p95`` / ``active_p99`` / ``active_max``
    wall time of a single run
``wait_p50`` / ``wait_p95`` / ``wait_max`` / ``wait_samples``
    broker wait, and how many runs had one measured
``wait_coverage``
    share of attempts with a measured wait
``buckets``
    how many (class, queue) records this window has
``truncated``
    "true" when the (class, queue) cap was reached

``class_bucket`` - one per ``(task_class, queue)`` seen in the window,
heaviest first, up to ``MRMAP_TASK_PERFORMANCE_EXPORT_MAX_BUCKETS`` of them:
``task_class``, ``queue`` and every measure of the fleet record except
``wait_coverage``, ``buckets`` and ``truncated``. The class is the module of
the task name under the bounded class rule of #1326, so the cardinality of
the series is the (class, queue) pairs of the deployment - never a per-task
series, which is what a task uuid would become.

``class_sample`` - up to ``MRMAP_TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS``
newest measured attempts of the heaviest
``MRMAP_TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES`` classes: ``task_class``,
``task_name``, ``queue``, ``worker``, ``periodic_name``, ``root_id``,
``task_id``, ``attempt_no``, ``outcome``, ``active_seconds``, ``wait_seconds``,
``started_at``, ``finished_at``. These are the rows an operator clicks into,
not a series.

``coverage`` - exactly one per fire, the standing state of the attempt table:

``open_running``
    open attempts without a terminal row, young enough to still be running -
    an expected state
``open_abandoned``
    open attempts without a terminal row which are past
    ``CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS`` - the crash residue, the
    number a coverage panel must move
``open_total``
    both together
``grace_seconds``
    the grace the partition was made at, so a reader can tell what "past the
    grace" meant at read time
``measured_at``
    when the read ran, not a window edge

``class_coverage`` - one per task class which is holding open attempts, with
``task_class`` and the same count fields.

Coverage is a state, not a window
---------------------------------

The coverage question of #1391 - "can this dashboard see what ran, or is a
worker quietly dying?" - is a question about the *state of the attempt table*,
and the windowed ``uncertain_open`` / ``uncertain_abandoned`` of the series
cannot answer it. The collector writes a crashed attempt's open row when the
task *started*; the sweep of ``system.tasks`` adds the ``abandoned`` quality
only once the row is ``CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS`` (~48 h) old.
An exporter window is minutes wide and attributes rows by when they were
written, so by the time the flag exists the row has left every window the
exporter will ever publish: a deployment whose workers died mid-task publishes
``uncertain_open=0 uncertain_abandoned=0`` beside a panel which presents
itself as exactly that read.

So the coverage records do not go through the window at all.
:func:`system.capacity_measures.uncertain_coverage` reads the table as it
stands - open attempts of the look-back whose identity has no terminal row -
and partitions them at the abandon grace: an attempt young enough that its
worker may still be running is ``open_running``, one past the grace is
``open_abandoned``. Partitioning is what makes the two distinguishable at all;
collapsing them would present a healthy multi-day task as crashed workers, or
hide crashed workers among the running ones. The read counts the age as well
as the flag, so it does not wait for the next sweep to notice what the age
already says.

Because these are gauge reads, a panel reads them from the newest fire and
never aggregates them over the interval: ``sum()`` of an "is it still open?"
count over the fires of an hour counts one residue once per fire, and
``max()`` answers "how bad was the worst fire" - a deployment which recovered
from its crash would keep showing it. The exporter publishes the read at every
fire, including a fire which had no window to publish, so the newest record is
as current as the beat cadence; a coverage record older than the cadence means
the beat row is not firing at all.

A record carries no argument, no URL and no payload; ``task_class``,
``task_name``, ``queue``, ``worker``, ``periodic_name``, ``outcome`` and
``source`` are the only free text, and none of them is user input.

On the wire
===========

The record leaves the process as an RFC 5424 syslog message
(:class:`system.logging.formatter.RFC5424Formatter`, #1033) whose message is
the marker, the event and the whole payload as ``key=value`` pairs::

    <174>1 2026-11-23T09:00:02+00:00 worker mrmap 12 - - Celery task
    performance class_bucket event=class_bucket
    task_class=registry.tasks.harvest queue=default executions=12
    slot_seconds=6.5 periodic_name="harvest hourly"

The payload travels twice on the ``LogRecord`` - as ``structured_data`` under
the id ``metaSDID@taskperf`` and as that tail - and only the tail reaches the
log store. A record which suppresses its dump (this one, to keep a scheduled
exporter from writing a file per window below the media root) leaves the
structured data area of the line as ``-``, and VictoriaLogs - the store of the
compose stack, provisioned as the Grafana datasource ``victorialogs`` -
stores the message and nothing else of the line. The tail is therefore the
wire contract of the record: the only thing a panel can select, group or
``sum()`` by, the thing the tests pin and the thing a reviewer's query has to
match. The structured data stays because it is the record's own shape, is what
a handler which does not speak syslog renders, and would be indexed natively
by an RFC 5424 aware store.

Quoting is meaningful in the tail: an unquoted value is a number to the store,
a quoted one is text, so the seconds and count fields are unquoted on purpose
and only a value which needs it is quoted.

The dashboard
=============

``docker/grafana/provisioning/dashboards/jsons/mrmap_celery_task_performance.json``
provisions alongside ``mrmap_slow_requests.json`` into the MrMap folder and
selects on the tail. Every panel carries its query in ``targets[].expr`` with
``editorMode: "code"``, so the queries in the file are the ones the panels run
and a reviewer or an operator can copy one straight into Explore.

``Fleet occupancy`` / ``Windows emitted``
    the ``slot_seconds`` of the ``fleet`` record over the interval, beside the
    ``window_seconds`` the same records published. Read together they are the
    honest version of the first panel: a gap in occupancy which is also a gap
    in windows is a beat fire which did not happen, not a quiet deployment.
``Task class occupancy``
    the panel the issue is named for - ``sum(slot_seconds)`` per ``task_class``
    per window, with the interval ranking beside it. This is "who occupies the
    workers", which no per-attempt line of a busy deployment answers.
``Failed, retried and revoked attempts``
    the outcomes of the ``fleet`` record per window. A retry burns the worker
    slot again, so this is the plot to read beside an occupancy which suddenly
    grew; an absent line is an unmeasured count of #1330, not a zero.
``Queue wait beside wall time``
    ``wait_p95`` and ``active_p95`` of the fleet record on one plot and
    deliberately never added together - a task is slow either because it waited
    for a worker or because it ran long, and those have different fixes. Read
    it with ``wait_coverage``: a p95 of the wait is only meaningful for the
    share of attempts where a publish timestamp made one measurable.
``Slow classes``
    ``active_p95`` per class: the classes whose runs are long, and the row an
    operator clicks.
``Attempts still open, by class``
    the ``class_coverage`` records as a table - ``open_running`` and
    ``open_abandoned`` per class. A class which keeps a row here for days is
    either genuinely long-running (``open_running``) or has crashed workers
    (``open_abandoned``); the two are shown apart because they are different
    incidents, and the table is the drill-down entry for both. The listing is
    newest-first and capped at 200 rows, the default
    ``MRMAP_TASK_PERFORMANCE_EXPORT_MAX_BUCKETS`` - one fire cannot publish
    more ``class_coverage`` records than that cap, so the table is complete
    for a default deployment; a deployment which raised the knob beyond 200
    sees the newest 200 classes only, and the absent classes carry no marker
    of their own, which is why the cap of the panel is pinned against the
    setting by the dashboard test.
``Queues``
    executions and occupancy per ``queue``, so a saturated queue is visible
    without a broker export.
``Periodic tasks behind the samples``
    sampled attempts per ``periodic_name``; a beat row which stopped firing
    shows as its absence, which is the question of epic #1324.
``Drill-down samples of the heaviest classes``
    the ``class_sample`` records as a table, and the only place
    ``task_id`` appears: the path from "this class is slow" to "this attempt,
    this queue, this time".
``Coverage of the deployment``
    ``open_running``, ``open_abandoned`` and ``open_total`` of the ``coverage``
    record - the crash residue the attempt table is holding right now, read
    from the newest fire because it is a gauge and not a window total: an
    aggregate over the interval, ``max()`` included, would answer "how bad was
    the worst fire" and keep showing a crash the deployment recovered from. A
    dashboard which cannot see its own coverage presents a gap as performance,
    and #1330 made an unmeasured value explicit for a reason. Read this row
    before trusting any number beside it: a deployment whose workers died
    mid-task publishes no executions and still shows residue here, which is
    exactly the state the windowed counters of the series cannot express.

A panel selects one event type of the series like this (the query of the
fleet occupancy panel)::

    "Celery task performance" "event=fleet"
      | extract `slot_seconds=<slot_seconds> `
      | stats by (_time:5m) sum(slot_seconds) as slot_seconds

Three parts of it are the contract rather than taste, and each was found by
running the panel against the store:

* the marker filter comes first, so no other log of the deployment can reach
  a panel;
* the event is selected as a ``key=value`` pair, which is why the exporter
  writes ``event=`` into the tail and not only the bare word - a panel of
  ``event=class_bucket`` must not match a record of a name which merely
  begins the same way;
* the pattern of ``extract`` ends in a space, because its placeholder is
  greedy and would otherwise swallow the rest of the line; the exporter's
  trailing ``sd=<structured data id>`` is what guarantees the space after the
  last field of every record.

Operator drill-down
===================

The sequence the dashboard exists for, from the operator's side:

1. **Open the dashboard.** If the first row is empty, check the mode and the
   beat row before believing anything else::

       docker compose exec django python manage.py shell -c \
         "from django_celery_beat.models import PeriodicTask; \
          print(PeriodicTask.objects.filter(name='publish celery task performance').values('name','crontab'))"

   and ``docker compose logs celery_beat | grep -i task.performance``.
2. **Read the coverage row first.** ``open_abandoned`` above zero means the
   attempt table is holding attempts whose worker never reported an end: the
   numbers beside it describe what could be measured, not what ran. Then read
   the window itself - a window whose ``wait_samples`` is small against
   ``executions`` tells you the wait numbers beside it describe what was
   measured, not what ran; ``truncated=true`` on the fleet record says the
   (class, queue) cap was hit and the heaviest buckets are what is missing.
   All of it is reported rather than hidden - see the "why is a number missing"
   table below. A class which sits in ``open_running`` for days is a different
   incident from one in ``open_abandoned``: the first is a long task, the
   second is a dead worker, and the beat log line of the exporter names both
   without Grafana.
3. **Click the slow row.** ``Slow classes`` ranks classes by ``active_p95``;
   ``Attempts still open, by class`` lists the newest coverage record of each
   class, open runs and crash residue apart. Pick the class from the row.
4. **Open the samples table** for that class. Each row is one attempt with its
   ``task_id``, queue, outcome, wall and wait seconds, and whether it came
   from a beat row. The samples are capped on purpose (the heaviest classes,
   the heaviest runs): the table is a pointer into the attempt table, not a
   substitute for it.
5. **From a sample, go to the attempt.** ``task_id`` is the value the
   ``CeleryTaskAttempt`` of #1330 is keyed by::

       docker compose exec django python manage.py shell -c \
         "from system.models import CeleryTaskAttempt; \
          print(CeleryTaskAttempt.objects.filter(task_id='<task_id>').values())"

   and the reconciliation of #1330 answers whether that attempt is still
   running.
6. **From the fleet row, decide.** ``slot_seconds`` of the fleet divided by the
   window is what fraction of the worker pool was busy; compared against the
   topology of :ref:`celery-capacity-telemetry` it answers "do I need another
   worker" without a broker export.

Why a number is missing
=======================

``resumed_from`` on every record says where the window came from. It is the
first field to read when the series looks wrong.

``first_window``
    there was no cursor, so the window looked back over
    ``MRMAP_TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES``. One record per
    deployment with this value after a restart or a cache flush is expected
    and costs nothing; **every** record with it means the cursor is not
    surviving the cadence, and the windows of the deployment overlap.
``cursor``
    normal: the window continued where the last published one ended, which
    is what makes the windows of a deployment a partition of its time.
``first_window`` for two fires in a row
    the cursor did not survive the cadence. The exporter stores it with a
    timeout of its own (twice the window, never below 15 minutes) precisely
    because the deployment's cache would not: a ``CACHES["default"]`` without
    a ``TIMEOUT`` drops a key after 300 seconds, which is the default cadence,
    and a cursor which expires between two fires makes every fire republish
    its look-back. Two adjacent windows which overlap are the panel to check
    it against: sum ``executions`` over both and compare with one
    ``capacity_measures`` query over the same span.

A window which could not be read is not in the series and not in any record
either: the exporter names the failing read in the beat log of the
``publish_task_performance`` row and advances the cursor over it, so one bad
read costs its window and never the next one. A repeat of the same text there
is a bug to file against #1391 with the window and the text.

A gap between two records therefore means either no attempt ran in that window
(the series publishes what ran, so an idle deployment publishes only its fleet
record), or no fire happened at all (beat, see step 1), or the read of that
window failed (the beat log of the fire which covers the gap says so). It is
never a measurement dropped silently.

Testing the contract
====================

``backend/tests/django/system/test_task_performance_export.py`` pins both sides of
this page: the fields of each event, that unmeasured values stay out of a
record, that a record carries no argument, URL or payload, and that the
numbers of a record are the numbers of the bounded ``capacity_measures``
query it was read from. The coverage records are pinned against a row seeded
the way a crashed worker actually leaves it - open, with ``started_at``
*and* ``recorded_at`` hours old - because that is the state a window can
never reach, and a suite which seeds the flag onto a fresh row proves
nothing about it. ``tests.django.system.test_capacity_measures`` pins the
standing read itself: that residue past the grace is reported whether or not
the sweep has flagged it, that a task still inside the grace is not reported
as residue, and that the read costs one or two queries. The dashboard file is itself tested
(``backend/tests/django/system/test_task_performance_dashboard.py``): every
panel has a datasource and a query, every query selects the marker, every
field name and numeric role in it is part of the contract above, and the
provisioning of the datasource it selects on exists. Run both with the rest
of the system tests::

    python manage.py test tests.django.system.test_task_performance_export \
                          tests.django.system.test_task_performance_dashboard

See also: :ref:`celery-capacity-telemetry`, :ref:`celery-queues`,
:ref:`background-jobs`, and the detection side of the same epic at
:ref:`celery-task-performance`.
