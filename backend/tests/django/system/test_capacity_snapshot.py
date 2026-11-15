"""The deployment capacity snapshot of #1326: materialized, bounded, fail-closed.

These tests hand the builder canned observations - the topology verdict of
#1330, broker queue depths, the active/reserved backlog - and assert the
accounting rules the issue exists for, because a reader cannot tell a made-up
number from a measured one:

*   **one worker is one pool of slots**: a worker consuming two queues is
    four slots for the fleet, never eight, and its slots are only multiplied
    into a per-queue answer when that assignment is verifiable;
*   **a queue without a consumer is degraded, not infinitely fast**;
*   **``rho`` only when comparable**, and then always as a ``periodic_only``
    lower bound; **queue depth is an integer count**, never seconds;
*   everything unobserved stays ``null`` with its reason, a stale snapshot is
    *served as stale* rather than quietly re-labelled fresh, and the reader
    path is a cache read: no schedule walk, no broker round trip, no
    attempt-table query.
"""

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework.test import APIClient
from system.capacity_demand import FINGERPRINT_CACHE_KEY
from system.models import CeleryTaskAttempt

from system import capacity_snapshot
from system.capacity_snapshot import BUILD_LOCK_KEY, DATETIME_KEYS

UTC = ZoneInfo("UTC")
AT = datetime(2026, 6, 10, 7, 17, 13, tzinfo=UTC)
BEFORE = AT - timedelta(days=2)
HORIZON_SECONDS = 7 * 86400

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "capacity-snapshot-tests",
    },
}


def fleet(workers, zero_consumer_queues=()):
    """A topology verdict in #1330's shape, from ``{node: (slots, queues)}``."""
    entries = {node: {"slots": slots, "queues": queues}
               for node, (slots, queues) in workers.items()}
    consumed_by = {}
    for node, entry in entries.items():
        for queue in entry["queues"] or []:
            consumed_by.setdefault(queue, []).append(node)
    for queue in zero_consumer_queues:
        consumed_by.setdefault(queue, [])
    return {
        "available": True,
        "observed_at": timezone.now(),
        "workers": entries,
        "consumed_by": consumed_by,
        "zero_consumer_queues": list(zero_consumer_queues),
        "unknown_routing_workers": [
            node for node, entry in entries.items()
            if entry["queues"] is None],
        "declared_queues": sorted({
            queue for entry in entries.values()
            for queue in (entry["queues"] or [])}),
        "task_routes": {},
    }


UNREACHABLE = {
    "available": False,
    "reason": "no worker answered the inspect broadcast",
    "observed_at": AT,
}


def depths(lengths):
    return {
        "available": True,
        "observed_at": timezone.now(),
        "queues": {name: {"depth": depth, "reason": None}
                   for name, depth in lengths.items()},
        "delivery_backlog": {"unacked": 0, "unacked_index": 0},
    }


NO_BACKLOG = {
    "available": True, "observed_at": AT, "workers": {},
    "totals": {"active": 0, "reserved": 0},
}


@contextmanager
def observed(topology, queue_depths=None, messages=None):
    """The build's three console/broker reads, handed canned answers.

    The topology of ``system.capacity_topology`` is patched at its own seam
    (a verdict is an input to a build); the snapshot's two own reads are
    patched here so a test says which half of the picture it is about.
    """
    with patch.object(capacity_snapshot.capacity_topology, "observe_topology",
                      return_value=topology), \
            patch.object(capacity_snapshot, "observe_queue_depths",
                         return_value=queue_depths if queue_depths is not None
                         else depths({})), \
            patch.object(capacity_snapshot, "observe_message_backlog",
                         return_value=messages if messages is not None
                         else NO_BACKLOG):
        yield


class SeededDeployment(TestCase):
    """A deployment with one hourly schedule and its measured samples."""

    def setUp(self):
        cache.clear()
        PeriodicTask.objects.filter(enabled=True).update(enabled=False)

    def hourly(self, name, task, queue, active=60.0, measured=True):
        """An hourly schedule, its dispatches measured at ``active`` seconds."""
        schedule = CrontabSchedule.objects.create(
            minute="0", hour="*", timezone=UTC)
        row = PeriodicTask.objects.create(
            name=name, task=task, queue=queue, crontab=schedule,
            last_run_at=BEFORE)
        if measured:
            for index in range(3):
                started = AT - timedelta(hours=1, minutes=index)
                CeleryTaskAttempt.objects.create(
                    task_id=f"{name}-{index}", task_name=task, queue=queue,
                    worker="celery@a", periodic_name=name, started_at=started,
                    finished_at=started + timedelta(seconds=active),
                    active_seconds=active, outcome="success", quality=[])
        return row


@override_settings(CACHES=LOC_MEM)
class SnapshotBuildTests(SeededDeployment):
    """The arithmetic of one build, against canned observations."""

    def build(self, topology, queue_depths=None, messages=None, at=AT,
              horizon_days=7):
        with observed(topology, queue_depths, messages):
            return capacity_snapshot.build_capacity_snapshot(
                at=at, horizon_days=horizon_days)

    def test_one_worker_is_one_pool_whatever_it_consumes(self):
        """The acceptance example of the issue: four slots, never eight."""
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        self.hourly("updates", "registry.tasks.update.run_service_update",
                    "update")
        snapshot = self.build(
            fleet({"celery@a": (4, ["monitoring", "update"])}))

        self.assertEqual(snapshot["fleet"]["unique_worker_slots"], 4)
        self.assertEqual(snapshot["fleet"]["workers_observed"], 1)
        # 168 dispatches on each queue, 60 measured seconds each, over four
        # slots for the whole horizon
        self.assertEqual(
            snapshot["rho"]["value"],
            round(2 * 168 * 60 / (4 * HORIZON_SECONDS), 4))
        self.assertEqual(snapshot["rho"]["basis"], "periodic_only")
        self.assertIn("lower bound", snapshot["rho"]["statement"])

        # ... and the shared pool is NOT multiplied into either queue's own
        # answer: both queues carry real demand, so no verifiable assignment
        # exists and each stays null instead of both claiming the four slots
        monitoring = snapshot["queues"]["monitoring"]
        self.assertEqual(monitoring["consumers"], ["celery@a"])
        self.assertFalse(monitoring["exclusive_workers"])
        self.assertTrue(monitoring["eligible_workers_complete"])
        self.assertIsNone(monitoring["eligible_slots"])
        self.assertIsNone(monitoring["rho"])

    def test_disjoint_workers_add_up_and_their_queues_answer_rho(self):
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        self.hourly("updates", "registry.tasks.update.run_service_update",
                    "update")
        snapshot = self.build(fleet({
            "celery@monitor": (4, ["monitoring"]),
            "celery@update": (4, ["update"]),
        }))
        self.assertEqual(snapshot["fleet"]["unique_worker_slots"], 8)
        monitoring = snapshot["queues"]["monitoring"]
        self.assertTrue(monitoring["exclusive_workers"])
        self.assertEqual(monitoring["eligible_slots"], 4)
        self.assertEqual(monitoring["eligible_slot_seconds"],
                         4 * HORIZON_SECONDS)
        self.assertEqual(monitoring["rho"],
                         round(168 * 60 / (4 * HORIZON_SECONDS), 4))

    def test_a_worker_without_concurrency_keeps_the_fleet_answer_null(self):
        """The denominator would be made up, so no ratio is answered at all."""
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        snapshot = self.build(fleet({"celery@a": (None, ["monitoring"])}))
        self.assertIsNone(snapshot["fleet"]["unique_worker_slots"])
        self.assertEqual(snapshot["fleet"]["workers_with_unknown_slots"], 1)
        self.assertIsNone(snapshot["rho"]["value"])
        self.assertIn("conc", snapshot["rho"]["reason"])
        self.assertIn("worker_slots_unknown", snapshot["gaps"])

    def test_a_queue_without_a_consumer_is_degraded_not_infinitely_fast(self):
        """#970/#1040's starvation shape: accepted and never executed."""
        self.hourly("orphan", "registry.tasks.update.run_service_update",
                    "update")
        snapshot = self.build(fleet({"celery@a": (4, ["monitoring"])},
                                    zero_consumer_queues=["update"]))
        entry = snapshot["queues"]["update"]
        self.assertEqual(entry["status"], "degraded")
        self.assertTrue(entry["zero_consumers"])
        self.assertIsNone(entry["rho"])
        self.assertIsNone(entry["drain_estimate"])
        self.assertEqual(entry["drain_reason"][0],
                         "degraded: no consumer, wait is unbounded")
        self.assertIn("zero_consumer_queue", snapshot["gaps"])
        self.assertEqual(snapshot["confidence"], "degraded")

    def test_an_unobservable_fleet_answers_unknown_and_not_zero(self):
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        snapshot = self.build(UNREACHABLE)
        self.assertEqual(snapshot["confidence"], "unknown")
        self.assertIn("topology_unavailable", snapshot["gaps"])
        self.assertIsNone(snapshot["fleet"]["unique_worker_slots"])
        self.assertIsNone(snapshot["rho"]["value"])
        monitoring = snapshot["queues"]["monitoring"]
        self.assertIsNone(monitoring["consumers"])
        self.assertIsNone(monitoring["zero_consumers"])
        self.assertEqual(monitoring["status"], "unknown")
        # the demand side is still answered: what the schedules promise does
        # not depend on reaching the fleet
        self.assertEqual(monitoring["periodic_occurrences"], 168)

    def test_uncosted_occurrences_keep_rho_null_with_their_coverage(self):
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring", measured=False)
        snapshot = self.build(fleet({"celery@a": (4, ["monitoring"])}))
        self.assertIsNone(snapshot["rho"]["value"])
        self.assertIn("periodic_cost_not_measured", snapshot["gaps"])
        entry = snapshot["queues"]["monitoring"]
        # the count is per schedule row, not per occurrence: this one
        # hourly row is entirely uncosted over the whole horizon
        self.assertEqual(entry["periodic_cost_sources"]["unknown"], 1)
        self.assertIsNone(entry["periodic_demand_worker_seconds"])
        self.assertEqual(entry["periodic_demand_coverage"], 0.0)

    def test_queue_depth_is_an_integer_count_from_the_broker(self):
        snapshot = self.build(
            fleet({"celery@a": (4, ["monitoring"])}),
            queue_depths=depths({"monitoring": 17, "update": 0}))
        monitoring = snapshot["queues"]["monitoring"]
        self.assertEqual(monitoring["queue_depth"], 17)
        self.assertIsNone(monitoring["queue_depth_reason"])
        # a queue the broker did not answer for is unknown, not empty
        self.assertIsNone(snapshot["queues"]["default"]["queue_depth"])
        self.assertIn("queue_depth_unobserved", snapshot["gaps"])
        # and the drain range stays null because the arrival rate of the
        # non-periodic work is what nobody observes
        self.assertIsNone(monitoring["drain_estimate"])
        self.assertIn("nonperiodic_arrival_rate_unobserved",
                      monitoring["drain_reason"])

    def test_the_whole_snapshot_survives_a_json_round_trip(self):
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        snapshot = self.build(fleet({"celery@a": (4, ["monitoring"])}))
        body = {key: value for key, value in snapshot.items()
                if key not in DATETIME_KEYS}
        json.loads(json.dumps(body))
        # nested moments arrive as text; only the three top level ones stay
        # datetimes, for the serializer's DateTimeFields
        self.assertIsInstance(snapshot["demand"]["horizon"]["start"], str)
        self.assertIsInstance(snapshot["snapshot_at"], datetime)

    def test_refresh_answers_unchanged_while_the_snapshot_is_current(self):
        """Beat's cadence is cheap when nothing moved: one fingerprint read."""
        with observed(fleet({"celery@a": (4, ["monitoring"])})), \
                patch.object(capacity_snapshot, "build_capacity_snapshot",
                             wraps=capacity_snapshot.build_capacity_snapshot) as build:
            first = capacity_snapshot.refresh()
            second = capacity_snapshot.refresh()
        self.assertTrue(first["refreshed"])
        self.assertFalse(second["refreshed"])
        self.assertEqual(second["reason"], "snapshot is current")
        build.assert_called_once()


@override_settings(CACHES=LOC_MEM)
class SnapshotServingTests(SeededDeployment):
    """The reader path: a cache read, one bounded rebuild, honest staleness."""

    def setUp(self):
        super().setUp()
        self.row = self.hourly("probes",
                               "registry.tasks.monitoring.run_probe_check",
                               "monitoring")

    def read(self):
        with observed(fleet({"celery@a": (4, ["monitoring"])}),
                      queue_depths=depths({"monitoring": 0})):
            return capacity_snapshot.get_capacity_snapshot()

    def age_the_snapshot(self, seconds):
        """The cached answer as it looks ``seconds`` after its build."""
        stored = cache.get(capacity_snapshot.SNAPSHOT_CACHE_KEY)
        cache.set(capacity_snapshot.SNAPSHOT_CACHE_KEY,
                  dict(stored, built_at=stored["built_at"]
                       - timedelta(seconds=seconds)),
                  timeout=3600)

    def test_a_warm_read_costs_no_queries_and_no_observations(self):
        """The promise of the issue: no schedule walk on a request path."""
        first = self.read()
        self.assertFalse(first["stale"])
        with patch.object(capacity_snapshot,
                          "build_capacity_snapshot") as build, \
                patch.object(capacity_snapshot, "observe_queue_depths") as llen, \
                patch.object(capacity_snapshot,
                             "observe_message_backlog") as inspect, \
                CaptureQueriesContext(connection) as queries:
            second = self.read()
        build.assert_not_called()
        llen.assert_not_called()
        inspect.assert_not_called()
        self.assertEqual(len(queries), 0)
        self.assertEqual(second["queues"]["monitoring"]["queue_depth"], 0)

    def test_a_stale_snapshot_is_served_as_stale_while_another_build_runs(self):
        self.read()
        self.age_the_snapshot(2 * 3600)
        cache.set(BUILD_LOCK_KEY, True, 300)
        with patch.object(capacity_snapshot, "build_capacity_snapshot") as build:
            answer = self.read()
        build.assert_not_called()
        self.assertTrue(answer["stale"])

    def test_the_horizon_aging_by_less_than_a_rebuild_is_worth_stays_stale(self):
        """Same definitions, seconds of age: beat's refresh fixes it, not a
        second walk for a reader that happened to arrive a moment earlier."""
        with override_settings(CAPACITY_SNAPSHOT_TTL_SECONDS=1,
                               CAPACITY_SNAPSHOT_MIN_REBUILD_SECONDS=600):
            self.read()
            self.age_the_snapshot(5)
            with patch.object(capacity_snapshot,
                              "build_capacity_snapshot") as build:
                answer = self.read()
            build.assert_not_called()
            self.assertTrue(answer["stale"])

    def test_a_changed_schedule_definition_rebuilds_and_bookkeeping_does_not(self):
        builds = {"count": 0}
        real = capacity_snapshot.build_capacity_snapshot

        def counting(*args, **kwargs):
            builds["count"] += 1
            return real(*args, **kwargs)

        with observed(fleet({"celery@a": (4, ["monitoring"])}),
                      queue_depths=depths({"monitoring": 0})), \
                patch.object(capacity_snapshot, "build_capacity_snapshot",
                             side_effect=counting):
            self.read()
            self.assertEqual(builds["count"], 1)

            # beat's per-dispatch bookkeeping save is not a schedule change
            self.row.last_run_at = timezone.now()
            self.row.total_run_count = 7
            self.row.save()
            answer = self.read()
            self.assertEqual(builds["count"], 1)
            self.assertFalse(answer["stale"])

            # the definition is - as soon as the fingerprint interval passed
            self.row.crontab.minute = "*/15"
            self.row.crontab.save()
            cache.delete(FINGERPRINT_CACHE_KEY)
            answer = self.read()
            self.assertEqual(builds["count"], 2)
            self.assertFalse(answer["stale"])

    def test_a_failed_rebuild_serves_the_stale_answer(self):
        self.read()
        self.age_the_snapshot(2 * 3600)
        with patch.object(capacity_snapshot, "build_capacity_snapshot",
                          side_effect=RuntimeError("the walk blew up")):
            answer = self.read()
        self.assertTrue(answer["stale"])
        self.assertIsNotNone(answer["queues"])

    def test_a_failed_first_build_answers_a_verdict_without_counts(self):
        with patch.object(capacity_snapshot, "build_capacity_snapshot",
                          side_effect=RuntimeError("no broker, no schedules")):
            answer = self.read()
        self.assertFalse(answer["available"])
        self.assertEqual(answer["confidence"], "unknown")
        # a stated nothing carries no counts either: nothing to read a
        # partially observed deployment out of
        for section in ("queues", "rho", "demand", "pools", "fleet"):
            self.assertNotIn(section, answer)

    def test_a_missing_snapshot_while_one_is_building_answers_a_verdict(self):
        cache.set(BUILD_LOCK_KEY, True, 300)
        answer = self.read()
        self.assertFalse(answer["available"])
        self.assertIn("being built", answer["reason"])


@override_settings(CACHES=LOC_MEM, ROOT_URLCONF="system.urls")
class CapacityEndpointTests(SeededDeployment):
    """Admin only, read only, and a refusal that never pays for a snapshot."""

    def setUp(self):
        super().setUp()
        self.hourly("probes", "registry.tasks.monitoring.run_probe_check",
                    "monitoring")
        self.admin = get_user_model().objects.create_user(
            username="capacity-admin", password="x", is_staff=True)

    def client_for(self, user=None):
        client = APIClient()
        if user is not None:
            client.force_authenticate(user=user)
        return client

    def observed_read(self, user):
        # the build reads "now" from django.utils.timezone and looks costs up
        # in the window before it; the samples were created around AT, so the
        # request's clock is pinned there or the lookback misses them and rho
        # is legitimately null
        with observed(fleet({"celery@a": (4, ["monitoring"])}),
                      queue_depths=depths({"monitoring": 3})), \
                patch.object(capacity_snapshot.timezone, "now",
                             return_value=AT):
            return self.client_for(user).get(
                "/capacity", HTTP_ACCEPT="application/vnd.api+json")

    def test_the_endpoint_is_admin_only(self):
        self.assertIn(self.client_for().get("/capacity").status_code,
                      (401, 403))
        reader = get_user_model().objects.create_user(username="reader")
        self.assertEqual(
            self.client_for(reader).get("/capacity").status_code, 403)

    def test_a_refusal_never_pays_for_or_leaks_a_snapshot(self):
        """403 comes before any observation runs."""
        reader = get_user_model().objects.create_user(username="reader")
        with patch.object(capacity_snapshot, "build_capacity_snapshot") as build:
            response = self.client_for(reader).get("/capacity")
        self.assertEqual(response.status_code, 403)
        build.assert_not_called()

    def test_the_snapshot_answers_as_the_admin_resource(self):
        response = self.observed_read(self.admin)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual((data["type"], data["id"]),
                         ("CapacitySnapshot", "deployment"))
        attributes = data["attributes"]
        # JSON:API formats the attribute names; the sections are JSON values
        # and keep the keys the build answered them with, which is what the
        # reading guide documents
        self.assertIn("snapshotAt", attributes)
        self.assertTrue(attributes["available"])
        self.assertEqual(attributes["fleet"]["unique_worker_slots"], 4)
        self.assertEqual(attributes["queues"]["monitoring"]["queue_depth"], 3)
        self.assertEqual(attributes["rho"]["basis"], "periodic_only")

    def test_the_fail_closed_verdict_is_a_200_and_not_a_serialization_error(self):
        """An answer of "unknown" carries no sections at all."""
        with patch.object(capacity_snapshot, "build_capacity_snapshot",
                          side_effect=RuntimeError("nothing observable")):
            response = self.client_for(self.admin).get(
                "/capacity", HTTP_ACCEPT="application/vnd.api+json")
        self.assertEqual(response.status_code, 200)
        attributes = response.json()["data"]["attributes"]
        self.assertFalse(attributes["available"])
        self.assertEqual(attributes["confidence"], "unknown")
        self.assertNotIn("queues", attributes)

    def test_the_resource_is_read_only(self):
        client = self.client_for(self.admin)
        self.assertEqual(client.post("/capacity", {}).status_code, 405)
        self.assertEqual(client.delete("/capacity").status_code, 405)


@override_settings(CACHES=LOC_MEM)
class BrokerObservationTests(TestCase):
    """The two broker reads: integer depths, and the backlog in hand."""

    def setUp(self):
        cache.clear()

    def fake_app(self, client=None, error=None):
        if error is not None:
            def connection_for_read():
                raise error
            return SimpleNamespace(connection_for_read=connection_for_read)

        connection = SimpleNamespace(
            default_channel=SimpleNamespace(client=client))

        def connection_for_read():
            @contextmanager
            def opener():
                yield connection
            return opener()
        return SimpleNamespace(connection_for_read=connection_for_read)

    def test_depths_are_read_as_counts_with_the_delivery_backlog(self):
        redis = Mock()
        redis.llen.side_effect = lambda key: {
            "monitoring": 5, "update": 0, "unacked": 2}[key]
        redis.zcard.return_value = 2
        with patch.object(capacity_snapshot, "app", self.fake_app(client=redis)):
            answer = capacity_snapshot.observe_queue_depths(
                ["monitoring", "update"])
        self.assertTrue(answer["available"])
        self.assertEqual(answer["queues"]["monitoring"]["depth"], 5)
        self.assertEqual(answer["queues"]["update"]["depth"], 0)
        self.assertEqual(answer["delivery_backlog"]["unacked"], 2)
        self.assertEqual(answer["delivery_backlog"]["unacked_index"], 2)

    def test_an_unreadable_queue_stays_null_with_its_reason(self):
        redis = Mock()

        def llen(key):
            if key == "monitoring":
                raise RuntimeError("WRONGTYPE")
            return 0
        redis.llen.side_effect = llen
        redis.zcard.return_value = 0
        with patch.object(capacity_snapshot, "app", self.fake_app(client=redis)):
            answer = capacity_snapshot.observe_queue_depths(["monitoring"])
        self.assertIsNone(answer["queues"]["monitoring"]["depth"])
        self.assertIn("unreadable", answer["queues"]["monitoring"]["reason"])

    def test_a_broker_that_answers_no_lengths_is_not_a_queue_of_zero(self):
        with patch.object(capacity_snapshot, "app", self.fake_app(client=None)):
            answer = capacity_snapshot.observe_queue_depths(["monitoring"])
        self.assertFalse(answer["available"])
        self.assertIsNotNone(answer["reason"])
        self.assertIsNone(answer["queues"]["monitoring"]["depth"])

    def test_an_unreachable_broker_fails_the_whole_section_closed(self):
        with patch.object(capacity_snapshot, "app",
                          self.fake_app(error=ConnectionError("no redis"))):
            answer = capacity_snapshot.observe_queue_depths(["monitoring"])
        self.assertFalse(answer["available"])
        self.assertIn("no redis", answer["reason"])

    def test_active_and_reserved_are_counted_per_worker(self):
        inspector = Mock()
        inspector.active.return_value = {"celery@a": [{"id": 1}, {"id": 2}]}
        inspector.reserved.return_value = {"celery@a": [{"id": 3}]}
        fake = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: inspector))
        with patch.object(capacity_snapshot, "app", fake):
            answer = capacity_snapshot.observe_message_backlog(force=True)
        self.assertTrue(answer["available"])
        self.assertEqual(answer["totals"], {"active": 2, "reserved": 1})
        self.assertEqual(answer["workers"]["celery@a"],
                         {"active": 2, "reserved": 1})

    def test_a_fleet_that_does_not_answer_the_broadcast_is_unobserved(self):
        inspector = Mock()
        inspector.active.side_effect = ConnectionError("no console")
        inspector.reserved.return_value = None
        fake = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: inspector))
        with patch.object(capacity_snapshot, "app", fake):
            answer = capacity_snapshot.observe_message_backlog(force=True)
        self.assertFalse(answer["available"])

    def test_a_partial_answer_names_the_half_that_is_missing(self):
        inspector = Mock()
        inspector.active.return_value = {"celery@a": [{"id": 1}]}
        inspector.reserved.return_value = None
        fake = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: inspector))
        with patch.object(capacity_snapshot, "app", fake):
            answer = capacity_snapshot.observe_message_backlog(force=True)
        self.assertTrue(answer["available"])
        self.assertEqual(answer["partial"], ["reserved"])
        self.assertEqual(answer["totals"]["active"], 1)
        self.assertIsNone(answer["totals"]["reserved"])
