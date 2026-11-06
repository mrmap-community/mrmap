"""The worker start-up check which names the queues it cannot reach (#1040).

The stock worker starts without ``-Q`` and consumes every queue the app
declares, so ``MrMap.celery.check_consumed_queues`` must stay silent there.
A deployment which narrows the worker with ``-Q`` must hear, at worker
start, which declared queue it just stranded and which tasks are bound to
it - work published to a queue without a consumer waits unread and the job
behind it stalls in silence.
"""

from django.test import SimpleTestCase

from MrMap import celery_queues
from MrMap.celery import (app, check_consumed_queues, queues_without_consumer,
                          tasks_routed_to)

# registering the harvest tasks of the real app, the way importing an app's
# tasks module registers them; the check must name the tasks it finds
from registry.tasks import harvest  # noqa: F401


class QueuesWithoutConsumerTests(SimpleTestCase):
    """``queues_without_consumer`` reads what a worker consumes off the app.

    Runs against the real MrMap app and the real ``CELERY_TASK_QUEUES``,
    because the point of the check is that the two sides of one process -
    the declared queues and the consumed ones - are compared against each
    other. ``-Q`` is applied by ``amqp.queues.select``, which is what these
    tests do; the untouched state of the attribute is the stock worker.
    """

    def setUp(self):
        self.queues = app.amqp.queues
        # None is celery's "consume everything declared" state
        self.addCleanup(setattr, self.queues, "_consume_from", None)

    def consume_all_but(self, *missing):
        self.queues.select([
            queue.name for queue in app.conf.task_queues
            if queue.name not in missing])

    def test_worker_without_queues_option_consumes_everything(self):
        self.assertEqual(queues_without_consumer(), [])

    def test_explicit_queues_option_of_everything_is_not_missing_anything(self):
        # the stock docker-compose command of a deployment that restates
        # every queue of its release is complete and must stay silent
        self.queues.select([q.name for q in app.conf.task_queues])
        self.assertEqual(queues_without_consumer(), [])

    def test_dropped_queue_is_reported_by_name(self):
        # the drift of #1040: an override pinned to the queue list from
        # before the release which added harvest-import
        self.consume_all_but(celery_queues.HARVEST_IMPORT)
        self.assertEqual(queues_without_consumer(),
                         [celery_queues.HARVEST_IMPORT])


class TasksRoutedToTests(SimpleTestCase):
    def test_import_backlog_names_the_import_tasks(self):
        self.assertIn(
            "registry.tasks.harvest.call_md_metadata_file_to_db",
            tasks_routed_to(celery_queues.HARVEST_IMPORT))
        self.assertIn(
            "registry.tasks.harvest.call_md_metadata_files_to_db",
            tasks_routed_to(celery_queues.HARVEST_IMPORT))

    def test_default_queue_covers_the_tasks_without_a_queue_of_their_own(self):
        # tasks published without a queue= land on the default queue, so a
        # worker without it strands all of them and must be told so
        self.assertTrue(
            any("without a queue of its own" in entry
                for entry in tasks_routed_to(celery_queues.DEFAULT)))


class CheckConsumedQueuesTests(SimpleTestCase):
    def setUp(self):
        self.queues = app.amqp.queues
        self.addCleanup(setattr, self.queues, "_consume_from", None)

    def test_stays_silent_when_every_declared_queue_is_consumed(self):
        with self.assertNoLogs("celery", level="ERROR"):
            check_consumed_queues(sender="celery@test")

    def test_error_names_the_stranded_queue_and_its_tasks(self):
        self.queues.select([
            queue.name for queue in app.conf.task_queues
            if queue.name != celery_queues.HARVEST_IMPORT])
        with self.assertLogs("celery", level="ERROR") as logs:
            check_consumed_queues(sender="celery@test")
        message = "\n".join(logs.output)
        self.assertIn(celery_queues.HARVEST_IMPORT, message)
        self.assertIn("registry.tasks.harvest.call_md_metadata_file_to_db",
                      message)
        self.assertIn("celery@test", message)

    def test_error_says_so_for_a_queue_no_task_routes_to(self):
        # the update and monitoring queues are declared with no task
        # declaring them today; the line must read as that, not as empty
        self.queues.select([
            queue.name for queue in app.conf.task_queues
            if queue.name != celery_queues.MONITORING])
        with self.assertLogs("celery", level="ERROR") as logs:
            check_consumed_queues(sender="celery@test")
        self.assertIn(
            "%s' carries: (nothing routes to it yet)" % celery_queues.MONITORING,
            "\n".join(logs.output))
