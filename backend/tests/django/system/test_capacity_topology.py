"""The worker/queue topology verdict of #1330, fail-closed by design.

#1326 may only multiply slots it saw. These tests hand
``observe_topology`` canned ``inspect`` answers and assert the accounting
rules of epic #1324: one worker consuming many queues is ONE pool with
routing metadata, an unconsumed queue is visible as unhealthy, a worker that
answers without a concurrency number keeps its slots unknown, and a fleet
that cannot be reached answers ``available: False`` instead of a silently
empty worker list.
"""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import caches
from django.test import SimpleTestCase, override_settings

from MrMap import celery_queues
from MrMap.celery import app as real_app
from system import capacity_topology

LOC_MEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "topology-tests",
    },
}


class FakeInspector:
    """The reply shape of ``app.control.inspect().stats()/active_queues()``."""

    def __init__(self, stats=None, queues=None, stats_error=None,
                 queues_error=None):
        self.stats_reply = stats
        self.queues_reply = queues
        self.stats_error = stats_error
        self.queues_error = queues_error
        self.stats_calls = 0
        self.queues_calls = 0

    def stats(self):
        self.stats_calls += 1
        if self.stats_error:
            raise self.stats_error
        return self.stats_reply

    def active_queues(self):
        self.queues_calls += 1
        if self.queues_error:
            raise self.queues_error
        return self.queues_reply


class TopologyTestsMixin:
    """Runs ``observe_topology`` against a fake control console.

    Tasks and conf stay the real app's - the routes and declared queues of
    the deployment are exactly what the verdict must read off the settings.
    """

    def observe(self, stats=None, queues=None, stats_error=None,
                queues_error=None, force=False):
        inspector = FakeInspector(stats, queues, stats_error, queues_error)
        fake_app = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: inspector),
            tasks=real_app.tasks,
            conf=real_app.conf,
        )
        with patch.object(capacity_topology, "app", fake_app):
            return capacity_topology.observe_topology(force=force)


@override_settings(CACHES=LOC_MEM, CAPACITY_TOPOLOGY_CACHE_SECONDS=60)
class ObserveTopologyTests(TopologyTestsMixin, SimpleTestCase):

    def setUp(self):
        # the locmem instance of this override, not the project's redis
        self.cache = caches["default"]
        self.cache.clear()

    def one_worker_three_queues(self):
        return {
            "celery@box": {
                "pool": {"max-concurrency": 4},
                "hostname": "celery@box",
                "processed": 12,
            },
        }, {
            "celery@box": [
                {"name": celery_queues.MONITORING},
                {"name": celery_queues.UPDATE},
                {"name": celery_queues.DEFAULT},
            ],
        }

    def test_shared_worker_is_one_pool_not_one_per_queue(self):
        stats, queues = self.one_worker_three_queues()
        verdict = self.observe(stats=stats, queues=queues)

        self.assertTrue(verdict["available"])
        self.assertEqual(list(verdict["workers"]), ["celery@box"])
        pool = verdict["workers"]["celery@box"]
        self.assertEqual(pool["slots"], 4)
        self.assertEqual(
            pool["queues"],
            sorted([celery_queues.MONITORING, celery_queues.UPDATE,
                    celery_queues.DEFAULT]))
        # the consumed queues all name the SAME pool - #1326 must not
        # multiply these slots per queue
        self.assertEqual(
            verdict["consumed_by"][celery_queues.MONITORING], ["celery@box"])
        self.assertEqual(
            verdict["consumed_by"][celery_queues.UPDATE], ["celery@box"])

    def test_unconsumed_declared_queue_is_visible_as_unhealthy(self):
        stats, queues = self.one_worker_three_queues()
        # the harvest-import queue is declared but nobody reads it - the
        # starvation shape of #970/#1040
        verdict = self.observe(stats=stats, queues=queues)
        self.assertIn(celery_queues.HARVEST_IMPORT,
                      verdict["zero_consumer_queues"])
        self.assertEqual(
            verdict["consumed_by"][celery_queues.HARVEST_IMPORT], [])
        # and every declared queue the fleet really covers is not listed
        self.assertNotIn(celery_queues.MONITORING,
                         verdict["zero_consumer_queues"])
        for name in verdict["declared_queues"]:
            self.assertIn(name, verdict["consumed_by"])

    def test_two_workers_keep_their_own_pools(self):
        stats = {
            "celery@a": {"pool": {"max-concurrency": 2}},
            "celery@b": {"pool": {"max-concurrency": 8}},
        }
        queues = {
            "celery@a": [{"name": celery_queues.MONITORING}],
            "celery@b": [{"name": celery_queues.MONITORING},
                         {"name": celery_queues.UPDATE}],
        }
        verdict = self.observe(stats=stats, queues=queues)
        self.assertEqual(
            verdict["consumed_by"][celery_queues.MONITORING],
            ["celery@a", "celery@b"])
        self.assertEqual(
            verdict["consumed_by"][celery_queues.UPDATE], ["celery@b"])
        # disjoint pools stay disjoint: 2 + 8, never a collapsed 8 or 10
        self.assertEqual(verdict["workers"]["celery@a"]["slots"], 2)
        self.assertEqual(verdict["workers"]["celery@b"]["slots"], 8)

    def test_unreported_concurrency_stays_unknown(self):
        # the threads pool answers stats without max-concurrency; slots are
        # then unknown - not the configured value, not a guess
        stats = {"celery@box": {"clock": "..."}}
        verdict = self.observe(stats=stats, queues={})
        self.assertIsNone(verdict["workers"]["celery@box"]["slots"])

    def test_worker_without_active_queues_answer_has_unknown_routing(self):
        stats = {"celery@box": {"pool": {"max-concurrency": 4}}}
        verdict = self.observe(stats=stats, queues={})
        self.assertIsNone(verdict["workers"]["celery@box"]["queues"])
        self.assertEqual(
            verdict["unknown_routing_workers"], ["celery@box"])
        # unknown routing contributes to NO queue's consumers, so every
        # declared queue reads as unconsumed rather than pretending coverage
        self.assertEqual(
            set(verdict["zero_consumer_queues"]),
            set(verdict["declared_queues"]))

    def test_silent_fleet_is_unknown_not_zero_workers(self):
        verdict = self.observe(stats={})
        self.assertFalse(verdict["available"])
        self.assertIn("reason", verdict)
        # and the same for a broken control console (forced: the first
        # unavailable verdict must not be the one read here)
        verdict = self.observe(stats_error=OSError("broker down"),
                               force=True)
        self.assertFalse(verdict["available"])

    def test_routes_come_from_the_task_declarations(self):
        stats = {"celery@box": {"pool": {"max-concurrency": 1}}}
        verdict = self.observe(stats=stats, queues={})
        routes = verdict["task_routes"]
        # the import backlog tasks declare queue= at the task (#970)
        self.assertEqual(
            routes["registry.tasks.harvest.call_md_metadata_file_to_db"],
            celery_queues.HARVEST_IMPORT)
        # an unrouted task is published to the default queue
        unrouted = [
            name for name, task in real_app.tasks.items()
            if getattr(task, "queue", None) is None]
        for name in unrouted[:5]:
            self.assertEqual(routes[name], real_app.conf.task_default_queue)

    def test_the_broker_round_trip_is_shared_by_the_cache(self):
        stats = {"celery@box": {"pool": {"max-concurrency": 1}}}
        inspector = FakeInspector(stats, {})
        fake_app = SimpleNamespace(
            control=SimpleNamespace(inspect=lambda timeout: inspector),
            tasks=real_app.tasks, conf=real_app.conf)
        with patch.object(capacity_topology, "app", fake_app):
            first = capacity_topology.observe_topology()
            second = capacity_topology.observe_topology()
            self.assertEqual(first["observed_at"], second["observed_at"])
            self.assertEqual(inspector.stats_calls, 1)
            self.assertEqual(inspector.queues_calls, 1)
            # force re-observes (an invalidation on a topology change)
            capacity_topology.observe_topology(force=True)
            self.assertEqual(inspector.stats_calls, 2)
