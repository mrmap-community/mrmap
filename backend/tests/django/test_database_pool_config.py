"""The pool bounds of the HTTP tier resolve from one place (#1621).

``MrMap/settings.py`` used to answer the pool of every non-celery process
from three places which disagreed: a module constant
``MAX_BACKEND_RESERVED_CONNECTIONS = 10`` no code read, an environment
variable of the same name read with a default of 20, and a ``min_size`` of 4
which no knob could reach at all. #1615 has the rule for that shape of
bug: a number a deployment sets and the process then reads differently is
worse than no knob, because it is the number an operator trusts.

Now one resolver owns the pair. The mode is ``MRMAP_LOW_MEMORY`` - the same
variable ``backend/.bash_scripts/process_defaults.sh`` uses for the process
shape, and the same reason: every HTTP worker process carries its own pool,
so the shape and the per-process reservation are one decision and must not
drift apart. Explicit bounds win over the mode, and nonsense (not a number,
below 1, min over max) raises while the settings load instead of being
decoded differently somewhere else.

The shipped numbers themselves - 4 reserved and 20 open per process, 1 and 4
in the low-memory mode - are measurements, not preferences; they are in
``docs/source/development/db-pool-memory.rst``. These tests pin that the
defaults are preserved and that the resolver, not a second copy of a
constant, is what the running settings carry. That celery keeps no pool at
all (an unfinished transaction on a pooled connection was the original
comment's reason) is verified in a fresh interpreter, because
``is_celery_process`` reads ``sys.argv`` at import time and the test process
is exactly not such a process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

import MrMap
from MrMap.settings import (_DB_POOL_MAX_SIZE, _DB_POOL_MIN_SIZE,
                            _db_pool_bounds_from_env)

POOL_ENV_NAMES = ("MIN_BACKEND_RESERVED_CONNECTIONS",
                  "MAX_BACKEND_RESERVED_CONNECTIONS", "MRMAP_LOW_MEMORY")

# the directory whose importability makes ``MrMap`` a package - the working
# directory of a fresh interpreter which has to load the settings
PROJECT_ROOT = str(Path(MrMap.__file__).parent.parent)


def clean_environ(**overrides):
    """A copy of the process environment without the pool knobs of #1621."""
    env = {k: v for k, v in os.environ.items() if k not in POOL_ENV_NAMES}
    env.update({k: v for k, v in overrides.items() if v is not None})
    return env


class PoolBoundsResolverTests(SimpleTestCase):
    """The arithmetic of one source of truth, spelled on a dict."""

    def test_shipped_defaults_are_preserved(self):
        # "production defaults preserved unless evidence warrants change"
        # of #1621 - the pair the release ships is still (4, 20)
        self.assertEqual(_db_pool_bounds_from_env({}), (4, 20))

    def test_low_memory_mode_shrinks_both_bounds(self):
        for spelling in ("1", "true", "TRUE", "Yes", " on "):
            with self.subTest(spelling=spelling):
                self.assertEqual(
                    _db_pool_bounds_from_env({"MRMAP_LOW_MEMORY": spelling}),
                    (1, 4))

    def test_low_memory_spellings_match_the_process_defaults(self):
        # process_defaults.sh accepts 1|true|yes|on and nothing else; a mode
        # which the shell reads on and Python reads off is #1615 again
        for off in ("", "  ", "0", "false", "2"):
            with self.subTest(off=off):
                self.assertEqual(
                    _db_pool_bounds_from_env({"MRMAP_LOW_MEMORY": off}),
                    (4, 20))

    def test_explicit_bounds_win_over_the_mode(self):
        self.assertEqual(_db_pool_bounds_from_env({
            "MRMAP_LOW_MEMORY": "1",
            "MIN_BACKEND_RESERVED_CONNECTIONS": "3",
        }), (3, 4))
        self.assertEqual(_db_pool_bounds_from_env({
            "MAX_BACKEND_RESERVED_CONNECTIONS": "30",
        }), (4, 30))
        self.assertEqual(_db_pool_bounds_from_env({
            "MRMAP_LOW_MEMORY": "on",
            "MIN_BACKEND_RESERVED_CONNECTIONS": " 2 ",
            "MAX_BACKEND_RESERVED_CONNECTIONS": "8",
        }), (2, 8))

    def test_empty_explicit_value_counts_as_unset(self):
        # the compose passthrough of an unset variable lands here as ""
        self.assertEqual(_db_pool_bounds_from_env({
            "MRMAP_LOW_MEMORY": "",
            "MIN_BACKEND_RESERVED_CONNECTIONS": "",
            "MAX_BACKEND_RESERVED_CONNECTIONS": "",
        }), (4, 20))

    def test_equal_bounds_are_allowed(self):
        self.assertEqual(_db_pool_bounds_from_env({
            "MIN_BACKEND_RESERVED_CONNECTIONS": "5",
            "MAX_BACKEND_RESERVED_CONNECTIONS": "5",
        }), (5, 5))

    def test_nonsense_raises_while_the_settings_load(self):
        cases = (
            ({"MAX_BACKEND_RESERVED_CONNECTIONS": "many"}, "not an integer"),
            ({"MAX_BACKEND_RESERVED_CONNECTIONS": "0"}, "below 1"),
            ({"MIN_BACKEND_RESERVED_CONNECTIONS": "-3"}, "below 1"),
            ({"MIN_BACKEND_RESERVED_CONNECTIONS": "9",
              "MAX_BACKEND_RESERVED_CONNECTIONS": "4"}, "exceeds"),
        )
        for env, expected in cases:
            with self.subTest(env=env):
                with self.assertRaises(ValueError) as caught:
                    _db_pool_bounds_from_env(env)
                self.assertIn(expected, str(caught.exception))


class ShippedSettingsTests(SimpleTestCase):
    """What the running deployment's settings actually carry."""

    def setUp(self):
        dirty = [name for name in POOL_ENV_NAMES if os.environ.get(name)]
        if dirty:
            self.skipTest(f"set in this environment: {', '.join(dirty)}")
        # is_celery_process() reads sys.argv, and a command line which
        # enumerates a module named like *celery*_config reads as a worker
        # to it - #1615's other face. In such a process the settings really
        # carry no pool, so these shipped-shape assertions do not apply;
        # FreshInterpreterTests pin the celery branch with real argvs.
        from MrMap.celery import is_celery_process
        if is_celery_process():
            self.skipTest(f"argv reads as a celery process: {sys.argv}")

    def test_default_shape_of_a_non_celery_process(self):
        pool = settings.DATABASES["default"]["OPTIONS"]["pool"]
        self.assertEqual(pool["min_size"], 4)
        self.assertEqual(pool["max_size"], 20)
        self.assertEqual(pool["timeout"], 30)

    def test_the_settings_carry_the_resolver_answer_not_a_copy(self):
        pool = settings.DATABASES["default"]["OPTIONS"]["pool"]
        self.assertEqual(pool["min_size"], _DB_POOL_MIN_SIZE)
        self.assertEqual(pool["max_size"], _DB_POOL_MAX_SIZE)


class FreshInterpreterTests(SimpleTestCase):
    """The import-time branches, read by a process which really is them.

    ``is_celery_process`` inspects ``sys.argv``, so only a fresh interpreter
    can say what a worker or Beat imports as ``DATABASES["default"]``.
    """

    def import_settings_options(self, argv, **pool_env):
        env = clean_environ(DJANGO_SETTINGS_MODULE="MrMap.settings",
                            **pool_env)
        code = (
            "import json, sys;"
            "sys.argv = %(argv)r;"
            "import MrMap.settings as s;"
            "print(json.dumps(s.DATABASES['default'].get('OPTIONS')))"
            % {"argv": argv})
        proc = subprocess.run(
            [sys.executable, "-c", code], cwd=PROJECT_ROOT, env=env,
            capture_output=True, text=True, timeout=180)
        self.assertEqual(0, proc.returncode,
                         f"settings import failed:\n{proc.stderr}")
        line = [line for line in proc.stdout.splitlines()
                if line.startswith("{")][-1]
        return json.loads(line)

    def test_worker_process_imports_no_pool(self):
        self.assertEqual(
            self.import_settings_options(["celery", "worker", "-l", "INFO"]),
            {})

    def test_worker_stays_unpooled_in_the_low_memory_mode(self):
        # the mode must not reach the celery branch - an unfinished
        # transaction on a pooled connection is why that branch exists
        self.assertEqual(
            self.import_settings_options(
                ["celery", "worker", "-l", "INFO"], MRMAP_LOW_MEMORY="1"),
            {})

    def test_beat_keeps_its_application_name(self):
        self.assertEqual(
            self.import_settings_options(["celery", "beat"]),
            {"application_name":
             settings.SYSTEM_STATUS_BEAT_APPLICATION_NAME})

    def test_low_memory_mode_reaches_a_fresh_http_settings_import(self):
        # the resolver is not only arithmetic on a dict: a container which
        # boots with MRMAP_LOW_MEMORY=1 imports the shrunk pool
        self.assertEqual(
            self.import_settings_options(
                ["manage.py", "runserver"], MRMAP_LOW_MEMORY="1"),
            {"pool": {"min_size": 1, "max_size": 4, "timeout": 30}})
