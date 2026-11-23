.. _celery-task-performance:

==========================================
Celery task-performance series and dashboard
==========================================

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
    classes - the rows an operator clicks into, not a series.

Every record of one fire carries the same window - ``window_start``
(exclusive), ``window_end`` (inclusive), ``window_seconds`` - and ``source``,
which is the source class of #1330 the numbers came from. The fields beside
them are the contract; an unmeasured value is **absent**, never ``0``,
because the semantics of the source layer survive into the series.

``fleet`` - exactly one per window, the whole deployment:

    ``executions``          attempts of the window
    ``slot_seconds``        sum of measured worker occupancy - the occupancy of #1330
    ``succeeded`` / ``failed`` / ``retried`` / ``revoked``
                            outcomes of the window
    ``uncertain_open``      attempts with no end yet - running for hours
    ``uncertain_abandoned`` attempts left without a terminal signal
    ``active_p50`` / ``active_p95`` / ``active_p99`` / ``active_max``
                            wall time of a single run
    ``wait_p50`` / ``wait_p95`` / ``wait_max`` / ``wait_samples``
                            broker wait, and how many runs had one measured
    ``wait_coverage``       share of attempts with a measured wait
    ``buckets``             how many (class, queue) records this window has
    ``truncated``           "true" when the (class, queue) cap was reached

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
``Slow classes`` / ``Classes with attempts still running``
    ``active_p95`` and ``uncertain_open`` per class. These two are the
    drill-down entry: they name the classes whose runs are long and the
    classes with attempts which never ended, and the row an operator clicks.
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
``Coverage of the interval``
    ``uncertain_open`` and ``uncertain_abandoned`` of the fleet records. A
    dashboard which cannot see its own coverage presents a gap as performance,
    and #1330 made an unmeasured value explicit for a reason.

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
2. **Read the coverage row first.** A window whose ``wait_samples`` is small
   against ``executions`` tells you the wait numbers beside it describe what
   was measured, not what ran; ``truncated=true`` on the fleet record says the
   (class, queue) cap was hit and the heaviest buckets are what is missing.
   Both are reported rather than hidden - see the "why is a number missing"
   table below.
3. **Click the slow row.** ``Slow classes`` ranks classes by ``active_p95`` and
   ``Classes with attempts still running`` by ``uncertain_open``. Pick the
   class from the row.
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

``backend/tests/django/system/test_task_performance.py`` pins both sides of
this page: the fields of each event, that unmeasured values stay out of a
record, that a record carries no argument, URL or payload, and that the
numbers of a record are the numbers of the bounded ``capacity_measures``
query it was read from. The dashboard file is itself tested
(``backend/tests/django/system/test_task_performance_dashboard.py``): every
panel has a datasource and a query, every query selects the marker, every
field name and numeric role in it is part of the contract above, and the
provisioning of the datasource it selects on exists. Run both with the rest
of the system tests::

    python manage.py test tests.django.system.test_task_performance \
                          tests.django.system.test_task_performance_dashboard

See also: :ref:`celery-capacity-telemetry`, :ref:`celery-queues`,
:ref:`background-jobs`.
