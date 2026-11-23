"""The exporter the task dashboard of #1391 reads its series from.

``task_performance`` turns one window of the #1330 attempt rows into a bounded
structured syslog record per (task class, queue) plus one fleet record, and
nothing else. What these tests pin down are the promises the issue makes about
that shape:

*   off by default: no records, and no beat row for a deployment which never
    installed the dashboard;
*   the windows do not overlap, so a fire which is late, doubled, or missing
    cannot double count and cannot shift what a range of the series adds up to;
*   never a record per attempt and never a query per attempt - the cost of a
    fire is fixed and small however busy its window was;
*   an unmeasured duration stays out of the record instead of becoming a zero,
    occupied seconds never contain queue waiting, and the coverage fields say
    how much could be seen at all;
*   the drill-down rows carry the measurement columns and the correlation keys
    of #1330, and nothing that would let a per-attempt row become a label of a
    time series;
*   a broken read or a log store which is down costs the window and is named in
    the summary - it never raises into the caller, because this is telemetry of
    the family of #1330's collector and #1320's publishers.

The records are collected through the logging machinery, off the root logger
the deployment actually syslogs, because the promise under test is what the
syslog line carries: a record keeps its structured data only as far as a real
handler sees it.
"""

import logging
import re
import uuid
from datetime import timedelta
from unittest.mock import patch

from django_celery_beat.models import PeriodicTask
from django.core.cache import cache
from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.locmem import LocMemCache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from system.apps import (TASK_PERFORMANCE_EXPORT_TASK_NAME,
                         create_task_performance_export_task)
from system.capacity_measures import task_class_of
from system.models import AttemptQuality, CeleryTaskAttempt
from system.task_performance import (EVENT_CLASS_BUCKET, EVENT_FLEET,
                                     EVENT_SAMPLE, TELEMETRY_SDID,
                                     WINDOW_CURSOR_KEY, _cursor_ttl,
                                     _logfmt_value,
                                     export_task_performance)

LOGGER = "MrMap.root"

#: the cadence the exporter's beat row fires at by default, which is also the
#: span of one window (MRMAP_TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES)
DEFAULT_CADENCE_MINUTES = 5

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "task-performance-tests",
    },
}

#: the locmem cache of these tests, on the backend which remembers timeouts
RECORDING_CACHES = {
    "default": {
        "BACKEND": "tests.django.system.test_task_performance"
                   "._TimeoutRecordingLocMem",
        "LOCATION": "task-performance-timeout-tests",
    },
}

ENABLED = override_settings(
    CACHES=LOC_MEM,
    TASK_PERFORMANCE_EXPORT_ENABLED=True,
    TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES=60,
    TASK_PERFORMANCE_EXPORT_MAX_BUCKETS=200,
    TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES=3,
    TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS=5)

#: the fields a record must never carry, whatever the attempt table grows
FORBIDDEN_FIELDS = ("args", "kwargs", "url", "headers", "payload", "request",
                    "body", "task_args", "task_kwargs")


def seed(task_id=None, attempt_no=0, queue="default",
         task_name="registry.tasks.harvest.harvest_metadata",
         outcome="success", active=2.0, wait=None, started_ago_seconds=0,
         quality=None, periodic_name="harvest hourly", root_id=None):
    # a real periodic name is two words, which is the shape of the
    # value on the wire: quoted in the tail, so every fire of these
    # tests also proves a value with a space survives the store

    """One attempt row, written the way the #1330 collector writes it."""
    started = timezone.now() - timedelta(seconds=started_ago_seconds)
    published = (started - timedelta(seconds=wait)
                 if wait is not None else None)
    terminal = outcome != ""
    return CeleryTaskAttempt.objects.create(
        task_id=task_id or str(uuid.uuid4()),
        attempt_no=attempt_no,
        task_name=task_name,
        queue=queue,
        worker="celery@worker-1",
        root_id=root_id or "",
        periodic_name=periodic_name,
        published_at=published,
        started_at=started,
        finished_at=started + timedelta(seconds=active or 0)
        if terminal else None,
        active_seconds=active if terminal else None,
        wait_seconds=float(wait) if wait is not None else None,
        outcome=outcome,
        quality=quality or [],
    )


class Records(list):
    """The structured records of one fire, collected off the root logger."""

    class Handler(logging.Handler):
        def __init__(self, owner):
            super().__init__()
            self.owner = owner

        def emit(self, record):
            structured = getattr(record, "structured_data", None)
            if not structured:
                return
            sdid, payload = next(iter(structured.items()))
            self.owner.append({
                "message": record.getMessage(),
                "level": record.levelno,
                "disable_python_meta": getattr(
                    record, "disable_python_meta", False),
                "suppress_dump": getattr(record, "suppress_dump", False),
                "sdid": sdid,
                "payload": payload,
            })

    @classmethod
    def collect(cls, case):
        collected = cls()
        handler = cls.Handler(collected)
        logger = logging.getLogger(LOGGER)
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        def detach():
            logger.removeHandler(handler)
            logger.setLevel(previous_level)

        case.addCleanup(detach)
        return collected

    def for_event(self, event):
        return [record for record in self if record["payload"]["event"] ==
                event]

    def payload(self, event, index=0):
        return self.for_event(event)[index]["payload"]


class ExportOffByDefaultTests(TestCase):

    def test_a_fire_without_the_mode_publishes_nothing(self):
        seed()
        # a quiet log is the point: a deployment which never installed the
        # dashboard should not pay records nobody reads, not even a note that
        # it is not writing them
        records = Records.collect(self)
        summary = export_task_performance()
        self.assertEqual(summary["published"], 0)
        self.assertIn("off", summary["reason"])
        self.assertEqual(records, [])

    def test_beat_gets_no_row_while_the_mode_is_off(self):
        create_task_performance_export_task(sender=None)
        self.assertFalse(PeriodicTask.objects.filter(
            name=TASK_PERFORMANCE_EXPORT_TASK_NAME).exists())

    @override_settings(CACHES=LOC_MEM, TASK_PERFORMANCE_EXPORT_ENABLED=True)
    def test_an_operator_who_turned_the_mode_off_loses_the_row(self):
        create_task_performance_export_task(sender=None)
        self.assertTrue(PeriodicTask.objects.filter(
            name=TASK_PERFORMANCE_EXPORT_TASK_NAME).exists())
        with override_settings(TASK_PERFORMANCE_EXPORT_ENABLED=False):
            create_task_performance_export_task(sender=None)
        self.assertFalse(PeriodicTask.objects.filter(
            name=TASK_PERFORMANCE_EXPORT_TASK_NAME).exists())


@ENABLED
class PublishedRecordsTests(TestCase):
    """The shape and the content of what one fire writes."""

    def setUp(self):
        cache.delete(WINDOW_CURSOR_KEY)
        self.records = Records.collect(self)

    def test_one_fleet_record_and_one_record_per_class_and_queue(self):
        seed(task_name="registry.tasks.harvest.harvest_metadata", active=10.0)
        seed(task_name="registry.tasks.harvest.harvest_result", active=4.0)
        seed(task_name="notify.tasks.send_mail", queue="notify", active=1.0)
        summary = export_task_performance()
        self.assertEqual(summary["buckets"], 2)
        self.assertEqual(len(self.records.for_event(EVENT_FLEET)), 1)
        self.assertEqual(
            sorted((record["payload"]["task_class"],
                    record["payload"]["queue"])
                   for record in self.records.for_event(EVENT_CLASS_BUCKET)),
            [("notify.tasks.send_mail", "notify"),
             ("registry.tasks.harvest", "default")])

    def test_the_numbers_of_a_record_are_the_numbers_of_the_query(self):
        # the acceptance criterion: what the dashboard plots is what the
        # bounded capacity_measures query answers for the same window
        seed(wait=4 * 3600, active=2.0)
        export_task_performance()
        payload = self.records.payload(EVENT_CLASS_BUCKET)
        self.assertAlmostEqual(float(payload["slot_seconds"]), 2.0)
        self.assertAlmostEqual(float(payload["wait_p95"]), 4 * 3600)
        self.assertEqual(payload["executions"], "1")
        self.assertEqual(payload["succeeded"], "1")
        self.assertEqual(payload["wait_samples"], "1")
        self.assertAlmostEqual(
            float(self.records.payload(EVENT_FLEET)["slot_seconds"]), 2.0)

    def test_unmeasured_values_stay_out_of_the_record(self):
        seed(wait=None)
        export_task_performance()
        payload = self.records.payload(EVENT_CLASS_BUCKET)
        for field in ("wait_p50", "wait_p95", "wait_max"):
            self.assertNotIn(field, payload,
                             "%s must be absent, not zero" % field)
        self.assertIn("active_p95", payload)

    def test_records_carry_their_window_and_the_fleet_its_coverage(self):
        seed()
        export_task_performance()
        payload = self.records.payload(EVENT_CLASS_BUCKET)
        start = timezone.datetime.fromisoformat(payload["window_start"])
        end = timezone.datetime.fromisoformat(payload["window_end"])
        self.assertAlmostEqual(
            float(payload["window_seconds"]),
            (end - start).total_seconds())
        self.assertAlmostEqual(
            float(self.records.payload(EVENT_FLEET)["wait_coverage"]), 0.0)

    def test_records_suppress_the_dump_and_the_code_position(self):
        # a scheduled exporter must not leave one json file per window below
        # the media root for numbers the syslog line already carries (#1033)
        seed()
        export_task_performance()
        self.assertTrue(self.records)
        for record in self.records:
            self.assertTrue(record["suppress_dump"])
            self.assertTrue(record["disable_python_meta"])
            self.assertEqual(record["sdid"], TELEMETRY_SDID)

    def test_no_record_carries_an_argument_a_url_or_a_payload(self):
        seed(periodic_name="harvest hourly", root_id="root-1")
        export_task_performance()
        self.assertTrue(self.records)
        for record in self.records:
            for field in FORBIDDEN_FIELDS:
                self.assertNotIn(field, record["payload"])

    def test_drilldown_samples_are_rows_to_read_not_a_series(self):
        for index in range(4):
            seed(task_name="registry.tasks.harvest.task%d" % index,
                 periodic_name="harvest hourly", root_id="root-%d" % index,
                 started_ago_seconds=index)
        with override_settings(
                TASK_PERFORMANCE_EXPORT_ENABLED=True, CACHES=LOC_MEM,
                TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS=2,
                TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES=3,
                TASK_PERFORMANCE_EXPORT_MAX_BUCKETS=200,
                TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES=60):
            summary = export_task_performance()
        samples = self.records.for_event(EVENT_SAMPLE)
        self.assertEqual(len(samples), 2)
        self.assertEqual(summary["drilldown_classes"],
                         ["registry.tasks.harvest"])
        payload = samples[0]["payload"]
        self.assertEqual(payload["task_class"], "registry.tasks.harvest")
        self.assertEqual(payload["periodic_name"], "harvest hourly")
        self.assertIn(payload["root_id"],
                      {"root-0", "root-1", "root-2", "root-3"})
        self.assertIn("task_id", payload)

    def test_a_fire_which_could_not_read_its_window_costs_that_window(self):
        seed()
        with patch("system.task_performance.window_buckets",
                   side_effect=RuntimeError("db is gone")):
            summary = export_task_performance()
        self.assertEqual(summary["published"], 0)
        self.assertEqual(summary["reason"], "db is gone")

    def test_a_broken_drilldown_read_keeps_the_series(self):
        seed()
        with patch("system.task_performance.drilldown_samples",
                   side_effect=RuntimeError("no samples")):
            summary = export_task_performance()
        self.assertGreaterEqual(summary["published"], 2)
        self.assertEqual(self.records.for_event(EVENT_SAMPLE), [])
        self.assertEqual(len(self.records.for_event(EVENT_FLEET)), 1)


@ENABLED
class WindowCursorTests(TestCase):
    """The windows of a deployment are non-overlapping by construction."""

    def setUp(self):
        cache.clear()
        self.records = Records.collect(self)

    def test_the_first_fire_looks_back_over_the_configured_span(self):
        seed(started_ago_seconds=3600)
        summary = export_task_performance()
        self.assertEqual(summary["resumed_from"], "first_window")
        self.assertAlmostEqual(_window_minutes(summary), 60, places=1)

    def test_the_next_fire_continues_where_the_last_window_ended(self):
        export_task_performance()
        first = self.records.payload(EVENT_FLEET)
        cache.set(WINDOW_CURSOR_KEY, first["window_end"])
        export_task_performance()
        second = self.records.payload(EVENT_FLEET, index=1)
        self.assertEqual(second["window_start"], first["window_end"])

    def test_a_fire_without_an_elapsed_window_says_so(self):
        # a doubled fire or a clock which went backwards leaves the cursor
        # ahead of now; there is no window to cover and nothing is published
        cache.set(WINDOW_CURSOR_KEY,
                  (timezone.now() + timedelta(minutes=5)).isoformat())
        summary = export_task_performance()
        self.assertEqual(summary["published"], 0)
        self.assertIn("no window", summary["reason"])

    def test_an_unreadable_cursor_starts_a_new_window_instead_of_guessing(self):
        cache.set(WINDOW_CURSOR_KEY, "not a moment")
        with self.assertLogs(LOGGER, level="WARNING") as logs:
            summary = export_task_performance()
        self.assertEqual(summary["resumed_from"], "first_window")
        self.assertTrue([line for line in logs.output
                         if "could not be read" in line])

    def test_the_windows_of_a_busy_period_add_up_to_what_it_measured(self):
        # a doubled, late or missing fire must not double count: what the
        # published windows add up to is what the attempts were. The two fires
        # are a minute apart, which is how a beat cadence actually arrives.
        with patch.object(timezone, "now",
                          return_value=timezone.now() - timedelta(minutes=1)):
            seed(active=2.0, started_ago_seconds=30)
            export_task_performance()
        seed(active=3.0, started_ago_seconds=5)
        export_task_performance()
        fleets = [record["payload"]
                  for record in self.records.for_event(EVENT_FLEET)]
        self.assertEqual(len(fleets), 2)
        self.assertEqual(
            sum(float(fleet["executions"]) for fleet in fleets), 2)
        self.assertAlmostEqual(
            sum(float(fleet["slot_seconds"]) for fleet in fleets), 5.0)
        self.assertEqual(fleets[1]["window_start"], fleets[0]["window_end"])


@ENABLED
class BoundedCostTests(TestCase):
    """The acceptance criterion: cost independent of the window's volume."""

    def setUp(self):
        cache.clear()
        self.records = Records.collect(self)

    def test_a_busy_window_costs_the_same_records_as_a_quiet_one(self):
        for index in range(200):
            seed(task_name="registry.tasks.harvest.task%d" % (index % 2),
                 queue="q%d" % (index % 3), active=1.0,
                 started_ago_seconds=index % 60)
        with CaptureQueriesContext(connection) as queries:
            summary = export_task_performance()
        # the grouped bucket read, the two uncertain reads, the fleet
        # aggregate, the drill-down read and the cursor's cache round trips -
        # a fixed count, never one per attempt
        self.assertLessEqual(len(queries), 10)
        # 1 fleet + the (class x queue) buckets + the samples of one class
        self.assertLessEqual(summary["published"], 15)
        self.assertEqual(summary["executions"], 200)

    def test_the_bucket_cap_keeps_the_cardinality_bounded(self):
        for index in range(5):
            seed(task_name="registry.tasks.harvest%d.task" % index,
                 queue="q%d" % index, active=float(5 - index))
        with override_settings(
                CACHES=LOC_MEM, TASK_PERFORMANCE_EXPORT_ENABLED=True,
                TASK_PERFORMANCE_EXPORT_MAX_BUCKETS=2,
                TASK_PERFORMANCE_EXPORT_DRILLDOWN_CLASSES=3,
                TASK_PERFORMANCE_EXPORT_SAMPLES_PER_CLASS=5,
                TASK_PERFORMANCE_EXPORT_FIRST_WINDOW_MINUTES=60):
            summary = export_task_performance()
        self.assertEqual(summary["buckets"], 2)
        self.assertTrue(summary["truncated"])
        self.assertIn("partial", summary.get("note", ""))
        # the fleet row still answers the whole window
        self.assertEqual(summary["executions"], 5)

    def test_the_uncertain_observations_ride_along_as_counts(self):
        seed(outcome="", active=None, started_ago_seconds=10,
             quality=[AttemptQuality.ABANDONED.value])
        export_task_performance()
        payload = self.records.payload(EVENT_FLEET)
        self.assertEqual(payload["uncertain_open"], "1")
        self.assertEqual(payload["uncertain_abandoned"], "1")

    def test_the_published_class_is_the_class_of_the_policy(self):
        seed(task_name="notify.tasks.send_mail")
        export_task_performance()
        published = {record["payload"]["task_class"] for record
                     in self.records.for_event(EVENT_CLASS_BUCKET)}
        self.assertEqual(published,
                         {task_class_of("notify.tasks.send_mail")})


@ENABLED
class MessageTailTests(TestCase):
    """The ``key=value`` tail is what the log store keeps and the panels parse.

    A record which suppresses its dump reaches VictoriaLogs as its message
    only: the structured data area of the syslog line is ``-`` for it, so the
    tail of the message is the wire contract of #1391 rather than a readable
    convenience. What the shipped Grafana dashboard does with it is select a
    record by ``key=value`` pairs and pull the values out with ``extract``
    placeholders, and the two properties below are what makes that work; both
    were found by running the panels against the store, not by reading about
    it. The assertions parse the formatted line the way the store does.
    """

    def setUp(self):
        cache.clear()
        self.records = Records.collect(self)

    def test_a_message_is_marker_event_fields_and_the_structured_data_id(self):
        seed(periodic_name="harvest hourly")
        export_task_performance()
        for record in self.records:
            message = record["message"]
            event = record["payload"]["event"]
            self.assertTrue(message.startswith(
                "Celery task performance %s event=%s " % (event, event)),
                "the event is a key=value pair so a panel of one event type "
                "cannot match another whose name begins the same way: %r"
                % message[:80])
            self.assertTrue(message.endswith(" sd=%s" % TELEMETRY_SDID),
                            "the UDP syslog handler appends a NUL to every "
                            "datagram and the store's placeholder is greedy, "
                            "so a field of its own has to end the message: %r"
                            % message[-60:])

    def test_every_field_of_a_record_reads_back_the_way_the_store_reads_it(
            self):
        # a field the shipped store cannot hand back is a field no panel can
        # group by or sum, which shows up as an empty panel rather than an
        # error - so the parse below is the store's own rule, applied to every
        # field of every record of one fire
        seed(periodic_name="harvest hourly", root_id="root-1", wait=0.5)
        export_task_performance()
        self.assertTrue(self.records)
        for record in self.records:
            fields = _store_fields(record["message"])
            self.assertEqual(
                set(fields), set(record["payload"]) | {"sd"},
                "the tail of the %s record does not carry exactly the fields "
                "of the record: %s" % (record["payload"]["event"],
                                       sorted(set(fields)
                                              ^ set(record["payload"])))
            )
            for key, value in record["payload"].items():
                self.assertEqual(
                    fields[key], value,
                    "the store would read %s of the %s record as %r, not %r"
                    % (key, record["payload"]["event"], fields[key], value))

    def test_a_number_stays_bare_and_a_name_with_a_space_is_quoted(self):
        # the store keeps an unquoted value numeric, which is what lets a
        # panel sum() the seconds of #1391, so quoting is only ever the answer
        # for a value which would otherwise be read as two tokens - and a
        # periodic name is exactly that, because a PeriodicTask is named in
        # words
        seed(periodic_name="harvest hourly")
        export_task_performance()
        fleet = self.records.payload(EVENT_FLEET)
        fleet_message = self.records.for_event(EVENT_FLEET)[0]["message"]
        self.assertIn(" slot_seconds=%s " % fleet["slot_seconds"],
                      fleet_message,
                      "a quoted number is text to the store and cannot be "
                      "summed")
        self.assertIn(" truncated=%s " % fleet["truncated"], fleet_message)
        sample_message = self.records.for_event(EVENT_SAMPLE)[0]["message"]
        self.assertIn(' periodic_name="harvest hourly" ', sample_message,
                      "a value with a space reaches the store as two tokens "
                      "unless it is quoted")

    def test_the_quoting_rule_of_the_tail(self):
        # the shapes a builder does not currently produce, stated on the rule
        # itself so the wire contract does not depend on what the attempt
        # table happens to contain today
        self.assertEqual(_logfmt_value(""), '""',
                         "nothing at all is not a value the store could tell "
                         "apart from a missing field")
        self.assertEqual(_logfmt_value(2.5), "2.5")
        self.assertEqual(_logfmt_value(True), "true")
        self.assertEqual(_logfmt_value("a b"), '"a b"')
        self.assertEqual(_logfmt_value('a"b'), '"a\\"b"')
        self.assertEqual(_logfmt_value("a\\b"), '"a\\\\b"')


#: one ``key=`` of a message tail, as the store's ``extract`` sees it
_KEY = re.compile(r"([a-z0-9_]+)=")


def _store_fields(message):
    """The ``key=value`` tail of a message, read the way the store reads it.

    ``extract `key=<value> ```` hands the placeholder the text up to the next
    space which is not inside double quotes and strips those quotes; this is
    that rule. Escapes are out of its scope on purpose - no value of this
    record can contain a quote in practice, and the escaping of one is tested
    against the writer of it instead.
    """
    # past "Celery task performance" and the event word which follows it
    tail = message.split(" ", 3)[3]
    # the event is written twice by design: once as the word after the marker,
    # so the log line is human-readable, and once as a field - the word is
    # skipped, the field is what the store reads
    tail = tail[tail.find(" "):].lstrip()
    fields = {}
    position = 0
    while position < len(tail):
        key = _KEY.match(tail, position)
        if key is None:
            break
        end = key.end()
        quoted = False
        while end < len(tail) and (tail[end] != " " or quoted):
            if tail[end] == '"':
                quoted = not quoted
            end += 1
        fields[key.group(1)] = tail[key.end():end].strip('"')
        position = end + 1
    return fields


@ENABLED
class CursorLifetimeTests(TestCase):
    """The cursor has to outlive the cadence it is read on.

    The window of a fire continues where the last one ended, which is what
    keeps a doubled, late or missed fire from double counting - and that only
    holds while the cursor is still there when the next fire looks for it. A
    cache configured without a ``TIMEOUT`` drops a key after 300 seconds (the
    Django default and the value django-redis ships), which is exactly the
    default cadence, so a cursor written without an explicit timeout expires
    just as the next fire reads it and every fire republishes its whole
    look-back. The recording backend below is how a test sees the timeout the
    exporter handed the cache; the cache itself is Django's own.
    """

    def setUp(self):
        cache.clear()
        self.records = Records.collect(self)

    def test_a_fire_stores_the_cursor_longer_than_its_cadence(self):
        seed(active=2.0, started_ago_seconds=30)
        _TimeoutRecordingLocMem.timeouts = {}
        with override_settings(CACHES=RECORDING_CACHES):
            export_task_performance()
            stored = _TimeoutRecordingLocMem.timeouts.get(WINDOW_CURSOR_KEY)
        self.assertIsNotNone(
            stored, "the exporter left the cursor to the cache default, "
                    "which on the shipped setup is the cadence itself")
        self.assertGreater(
            stored, DEFAULT_CADENCE_MINUTES * 60,
            "the cursor would expire before the next fire looks for it")

    def test_the_cursor_ttl_outlives_every_cadence_the_knob_allows(self):
        # the cadence is a setting and system/apps.py schedules the beat row
        # from the same value, so the ttl has to scale with it rather than be
        # a constant which a longer cadence silently outruns
        for minutes in (1, 5, 7, 60, 120):
            with self.settings(TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES=minutes):
                self.assertGreater(
                    _cursor_ttl(), minutes * 60,
                    "a %s minute cadence would outrun the cursor ttl"
                    % minutes)


class _TimeoutRecordingLocMem(LocMemCache):
    """LocMemCache which remembers the timeout a key was stored with."""

    timeouts = {}

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None,
            **kwargs):
        answer = super().set(key, value, timeout=timeout, version=version,
                             **kwargs)
        self.timeouts[key] = timeout
        return answer


def _window_minutes(summary):
    start = timezone.datetime.fromisoformat(summary["window_start"])
    end = timezone.datetime.fromisoformat(summary["window_end"])
    return (end - start).total_seconds() / 60
