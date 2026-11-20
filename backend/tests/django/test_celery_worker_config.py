"""The worker configuration the deployment actually runs with (#1454).

Two numbers of the celery fleet were never set, and every one of them
costs the project work it does not want:

* ``worker_prefetch_multiplier`` unset kept celery's four, so a worker of
  the ``acks_late`` fleet reserved four messages per slot and every roll or
  restart requeued the up to three per slot it had never started - side
  effects of harvest, registration and update running a second time;
* no ``task_time_limit``/``soft_time_limit`` anywhere meant the CPU-bound
  parse, import and mapping recursion could pin a slot forever (the
  comment of registry/settings.py on the registration request timeouts
  knew).

The tests read the configuration off the real app the way the worker does:
``app.conf`` answers what ``MrMap/settings.py`` configured under the
CELERY namespace, and ``Task.bind(app)`` - which celery performs on the
first use of every task - answers which limits an individual task executes
with, the same values the worker's request reads into its prefork
``soft_timeout``/``timeout``. An artificial slow task stands in for the
runaway attempt the limits are meant to cut: without an override of its own
it must inherit the global bounds, a declared override must survive
binding.

#1615 found the same fleet configured twice by names celery does not read:

* ``CELERY_MAX_TASKS_PER_CHILD``: under the CELERY namespace celery 5.7 looks
  for ``max_tasks_per_child``, a key of no table of its own (measured against
  the installed package, where ``worker_max_tasks_per_child`` *is* a key), so
  ``app.conf`` answered the live name as ``None`` and the fleet never replaced
  a child while the deployment believed it recycled after 1000 tasks;
* ``CELERY_WORKER_REVOKES_MAX``: not a setting at all. celery builds the
  revocation window in ``celery/worker/state.py`` from the *environment*
  (``_int_env('CELERY_WORKER_REVOKES_MAX', 50000)``), so the 2000000 of the
  settings never applied and the window stayed at celery's 50000 - below the
  number of queued ids the abort of a big catalogue revokes
  (``registry/models/harvest.py`` names over 600000 for BKG).

So these tests ask two things of every knob: that ``app.conf`` answers it the
way the deployment set it, and that the name in ``MrMap/settings.py`` is a name
celery knows at all. A knob which is configured, printed by
``celery -A MrMap inspect conf`` and never read is worse than no knob, because
it is the number an operator trusts.

Enforcing a limit (SIGKILL of a pool slot, SoftTimeLimitExceeded inside a
running body) is the prefork pool's own machinery and celery tests it; what
MrMap owns, and what these tests pin, is that the numbers are set and that
they resolve onto the tasks in the precedence celery applies.
"""

import os

from celery.app import defaults
from django.conf import settings
from django.test import SimpleTestCase

from MrMap.celery import app
from MrMap.settings import _worker_int_from_env
from registry.settings import HARVESTING_REQUEST_TIMEOUT_MAX_SECONDS


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


class ChildRecyclingTests(SimpleTestCase):
    """A prefork child is recycled by a name celery reads (#1615)."""

    def test_the_recycling_knob_reaches_the_app(self):
        # the seam the worker reads: app.conf, not the settings module
        self.assertEqual(app.conf.worker_max_tasks_per_child,
                         settings.CELERY_WORKER_MAX_TASKS_PER_CHILD)

    def test_the_release_boots_with_the_recycling_it_asked_for(self):
        # 1000 is the number the deployment has named for years; before #1615
        # it named it into a key no reader existed for. The measurement behind
        # keeping it: one child holds 211 MB after 2400 imported documents and
        # does not grow further, and one replacement costs 0.6 s
        # (docs/source/development/celery-queues.rst)
        self.assertEqual(app.conf.worker_max_tasks_per_child, 1000)

    def test_the_memory_bound_stays_off_until_a_deployment_names_its_peak(self):
        # celery compares ru_maxrss, which a fresh child of this project
        # already fills to near 170 MB, and asks only after a completed task -
        # so a bound below the peak of the deployment's own biggest import
        # recycles after every task without bounding anything, and guards
        # nothing meanwhile
        self.assertIsNone(app.conf.worker_max_memory_per_child)

    def test_a_deployment_reads_both_knobs_like_the_slot_count(self):
        parse = _worker_int_from_env
        tasks = 'CELERY_WORKER_MAX_TASKS_PER_CHILD'
        self.assertEqual(parse(tasks, {tasks: '250'}, 1000), 250)
        self.assertIsNone(parse(tasks, {}, None))
        self.assertEqual(parse(tasks, {tasks: '  '}, 1000), 1000)
        # 0 is not the project's spelling of "never": the worker command reads
        # the same variable itself and hands 0 to the pool, which refuses it
        # ("maxtasksperchild must be a positive int or None"), so a deployment
        # which set 0 would crash-loop instead of never recycling
        with self.assertRaisesRegex(ValueError, 'below 1'):
            parse(tasks, {tasks: '0'}, 1000)
        with self.assertRaisesRegex(ValueError, 'below 1'):
            parse('CELERY_WORKER_MAX_MEMORY_PER_CHILD',
                  {'CELERY_WORKER_MAX_MEMORY_PER_CHILD': '-1'})
        # a value which is no number at all fails while the settings load, with
        # the name of the knob in the message
        with self.assertRaisesRegex(ValueError, f'{tasks}='):
            parse(tasks, {tasks: 'vier'}, 1000)


class NoInertCelerySettingTests(SimpleTestCase):
    """No setting of the project configures a key celery does not read.

    ``app.config_from_object('django.conf:settings', namespace='CELERY')``
    strips the prefix and looks the rest up in celery's own table; whatever is
    not in that table is configured, answered by ``inspect conf`` and ignored
    by the worker. That is where ``CELERY_MAX_TASKS_PER_CHILD`` spent its life
    (#1615), so the guard is the whole class of the bug and not its last
    spelling.
    """

    def test_every_celery_setting_is_a_celery_setting(self):
        configured = [name for name in dir(settings)
                      if name.startswith('CELERY_')]
        # a loop over nothing would prove nothing, and which names dir() of the
        # lazy settings object answers is exactly what could silently change
        self.assertIn('CELERY_BROKER_URL', configured)
        self.assertGreater(len(configured), 10,
                           f'only these CELERY_ names were seen: {configured}')
        inert = []
        for name in configured:
            key = name[len('CELERY_'):].lower()
            if key in defaults.DEFAULTS:
                continue
            near = sorted(k for k in defaults.DEFAULTS
                          if k.split('_')[-1] == key.split('_')[-1])
            inert.append(f'{name} (celery has no "{key}"; near names: '
                         f'{", ".join(near[:3]) or "none"})')
        self.assertEqual(
            inert, [],
            'these settings reach no worker: ' + '; '.join(sorted(inert)))


class RevokesWindowTests(SimpleTestCase):
    """The revocation window belongs to the worker's environment (#1615).

    Which makes handing it over a compose question, and a unit test can not
    ask one: the runner mounts ``backend/`` as ``/opt/mrmap`` and never sees the
    ``docker-compose.yml`` above it. So this asks the half the settings file
    owns - that celery really reads the environment, and that the project
    carries no second, inert copy of the name.
    """

    def test_celery_builds_the_window_from_the_environment(self):
        from celery.worker import state
        # the app configuration has no key for the window at all, so the
        # environment is the only way to name it - and this is the window a
        # deployment silently gets when it forgets the variable: celery's own
        # 50000, below the ids a big catalogue's abort revokes
        self.assertNotIn('worker_revokes_max', defaults.DEFAULTS)
        self.assertEqual(
            state.REVOKES_MAX,
            int(os.environ.get('CELERY_WORKER_REVOKES_MAX', 50000)))

    def test_the_project_carries_no_setting_for_it(self):
        self.assertFalse(
            hasattr(settings, 'CELERY_WORKER_REVOKES_MAX'),
            'a setting of this name configures nothing: celery reads the '
            'environment in celery/worker/state.py (#1615)')
