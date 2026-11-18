"""The worker configuration the deployment actually runs with (#1454).

Three numbers of the celery fleet were never set, and every one of them
costs the project work it does not want:

* ``worker_prefetch_multiplier`` unset kept celery's four, so a worker of
  the ``acks_late`` fleet reserved four messages per slot and every roll or
  restart requeued the up to three per slot it had never started - side
  effects of harvest, registration and update running a second time;
* no ``task_time_limit``/``soft_time_limit`` anywhere meant the CPU-bound
  parse, import and mapping recursion could pin a slot forever (the
  comment of registry/settings.py on the registration request timeouts
  knew);
* the ETF conformity check waits on an external validator for as long as
  that validator likes, so it must keep a budget of its own above the
  global one - and below the abandon grace of the #1330 samples.

The tests read the configuration off the real app the way the worker does:
``app.conf`` answers what ``MrMap/settings.py`` configured under the
CELERY namespace, and ``Task.bind(app)`` - which celery performs on the
first use of every task - answers which limits an individual task executes
with, the same values the worker's request reads into its prefork
``soft_timeout``/``timeout``. An artificial slow task stands in for the
runaway attempt the limits are meant to cut: without an override of its own
it must inherit the global bounds, a declared override must survive
binding. For the ETF task both are asserted, because that task is exactly
the deliberate long wait the global limit must not kill.

Enforcing a limit (SIGKILL of a pool slot, SoftTimeLimitExceeded inside a
running body) is the prefork pool's own machinery and celery tests it; what
MrMap owns, and what these tests pin, is that the numbers are set and that
they resolve onto the tasks in the precedence celery applies.
"""

from django.conf import settings
from django.test import SimpleTestCase

from MrMap.celery import app
from registry.settings import (CONFORMITY_ETF_TASK_HARD_TIME_LIMIT_SECONDS,
                               CONFORMITY_ETF_TASK_SOFT_TIME_LIMIT_SECONDS,
                               HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS)

# registers the conformity tasks of the real app, the way importing an
# app's tasks module registers them; the ETF task carries the only
# per-task time budget of the fleet
from registry.tasks import conformity  # noqa: F401


class PrefetchTests(SimpleTestCase):
    """One un-acked message per slot, the acks_late fleet's price (#1454)."""

    def test_prefetch_multiplier_is_one_on_the_app(self):
        self.assertEqual(app.conf.worker_prefetch_multiplier, 1)

    def test_prefetch_multiplier_is_not_env_drifted(self):
        # the setting is a constant of the release, not a deployer knob:
        # a fleet which sets it back to celery's default re-introduces the
        # requeued side effects on every roll
        self.assertEqual(settings.CELERY_WORKER_PREFETCH_MULTIPLIER, 1)


class GlobalTimeLimitTests(SimpleTestCase):
    """The global soft/hard bounds exist and are ordered."""

    def test_global_limits_are_set_on_the_app(self):
        self.assertEqual(app.conf.task_soft_time_limit,
                         settings.CELERY_TASK_SOFT_TIME_LIMIT)
        self.assertEqual(app.conf.task_time_limit,
                         settings.CELERY_TASK_TIME_LIMIT)

    def test_a_healthy_harvest_request_always_fits_under_the_soft_limit(self):
        # the soft limit is built from the 900 s ceiling of one harvesting
        # GetRecords (HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS) times several;
        # a request which is merely slow must not be cut by the deployment
        self.assertGreaterEqual(
            app.conf.task_soft_time_limit,
            3 * HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS)

    def test_hard_limit_leaves_the_soft_handler_room(self):
        self.assertGreater(
            app.conf.task_time_limit, app.conf.task_soft_time_limit)


class TaskTimeLimitResolutionTests(SimpleTestCase):
    """Which limits one task executes with (#1454).

    ``Task.bind`` is celery's lazy resolution: every task option still
    ``None`` picks up its ``from_config`` setting, a declared option stays
    as declared. The worker's request builds its pool call from exactly
    these task attributes, so this is the seam where the global bounds
    reach a task which declares nothing.
    """

    def register(self, name, **options):
        def slow():  # the artificial slow task: runs until a limit ends it
            return 'still running'

        task = app.task(name=name, shared=False, **options)(slow)
        self.addCleanup(app.tasks.pop, name, None)
        task.bind(app)  # what celery performs on the task's first use
        return task

    def test_slow_task_without_override_inherits_the_global_bounds(self):
        task = self.register('tests.slow-without-override')
        self.assertEqual(task.time_limit, settings.CELERY_TASK_TIME_LIMIT)
        self.assertEqual(task.soft_time_limit,
                         settings.CELERY_TASK_SOFT_TIME_LIMIT)

    def test_declared_soft_limit_survives_binding(self):
        task = self.register('tests.slow-with-soft-override',
                             soft_time_limit=42)
        self.assertEqual(task.soft_time_limit, 42)
        self.assertEqual(task.time_limit, settings.CELERY_TASK_TIME_LIMIT)


class EtfConformityTimeBudgetTests(SimpleTestCase):
    """The external ETF check keeps its own budget above the global one."""

    def setUp(self):
        self.task = conformity.run_conformity_check_etf
        self.task.bind(app)  # idempotent; proves the override is not conf-drifted

    def test_etf_task_declares_the_per_task_budget(self):
        self.assertEqual(self.task.soft_time_limit,
                         CONFORMITY_ETF_TASK_SOFT_TIME_LIMIT_SECONDS)
        self.assertEqual(self.task.time_limit,
                         CONFORMITY_ETF_TASK_HARD_TIME_LIMIT_SECONDS)

    def test_budget_is_ordered_and_above_the_global_soft_limit(self):
        self.assertGreater(self.task.soft_time_limit,
                           settings.CELERY_TASK_SOFT_TIME_LIMIT)
        self.assertGreater(self.task.time_limit, self.task.soft_time_limit)

    def test_budget_stays_under_the_abandon_grace_of_the_samples(self):
        # an attempt held past CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS is
        # declared abandoned by the sweep of #1330; a still-waiting ETF
        # attempt must never be one
        self.assertLess(
            self.task.time_limit,
            settings.CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS * 3600)
