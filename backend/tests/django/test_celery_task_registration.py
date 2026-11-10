"""Which tasks the worker really has when it starts (#1199).

A worker answers a message whose task name it never imported by discarding
it — "Received unregistered task ... The message has been ignored and
discarded" — and the publishing process learns nothing of it. A task module
which no start-up import of the worker reaches therefore swallows its work
in silence: that is how the refresh of the alert rows added by #1030 never
ran, because ``registry/tasks/__init__.py``, the package the worker's task
autodiscovery arrives at, did not import the module behind it (#1199).

The registration is read from a fresh interpreter which replays the worker's
own import — ``app.loader.import_default_modules()`` is what the worker
triggers before it consumes, and it fires the ``autodiscover_tasks()`` of
``MrMap/celery.py``, which imports the ``tasks`` module of every installed
app; for the registry that module is the manifest package
``registry/tasks/__init__.py``. The check cannot run in this test process:
by the time any test module runs, the suite itself has imported many task
modules and ``app.tasks`` of this process would answer "registered" for
nearly everything regardless of what the worker imports.

The references — the task names the code publishes and the task names the
deployments of beat are seeded with — are read from the sources with the
``ast`` module for the same reason: what matters is what a name means in the
source, not what this process happens to have imported. Dispatch through
variables (``task_function = build_ogc_service`` and the like) is beyond a
scan of the call sites and is not followed; the codebase dispatches by
importing the task from its defining module, which the scan does follow.
"""

import ast
import functools
import json
import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

# backend/ — the directory whose subdirectories are the apps, which is also
# the directory the worker starts in and the cwd the replay needs
BACKEND_DIR = Path(__file__).resolve().parents[2]

#: the refresh whose silent loss this regression guards (#1199, #1030)
ALERT_REFRESH_TASK = "registry.tasks.alerts.refresh_service_alerts"

#: marker of the JSON line the replay prints
TASKS_MARKER = "MRMAP_REGISTERED_TASKS:"

#: task modules outside the manifest which reach the worker through another
#: import; a new task module belongs in the manifest, not in this dict
IMPORTED_ELSEWHERE_AT_WORKER_START = {
    # the views import it and the worker imports the URLconf when the celery
    # django fixup runs the system checks at start-up; it cannot join the
    # manifest because it needs the finished registry.models package while
    # that package is itself the first to import the manifest (#1199 analysis)
    "registry.tasks.service": "registry/views/service.py",
    # imported at module level by registry/models/update.py, and the app
    # registry imports the models of every installed app — in the worker too
    "registry.tasks.update": "registry/models/update.py",
}

#: task modules the replayed import does not reach and which the checks below
#: therefore do not require of the replay; the codebase currently publishes
#: no task of these by name, so this only answers a future reference. The
#: real worker imports the URLconf while the celery django fixup runs the
#: system checks at start-up, and the views import ``registry.tasks.service``;
#: that module cannot join the manifest because it needs the finished
#: ``registry.models`` package while the models package is itself the first
#: to import the manifest. The replay skips those checks — they would need a
#: database and answer for the incidental URLconf import, not for the
#: manifest this file is about.
NOT_REACHED_BY_THE_REPLAY = {
    "registry.tasks.service",
    "registry.tasks.update",
}

#: replayed in a fresh interpreter: the import the worker performs for its
#: task registration, and nothing more; the script is plain text with the
#: marker of the result line substituted in
WORKER_IMPORT_TEMPLATE = """
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MrMap.settings")

import django

django.setup()

from MrMap.celery import app

# the worker's own entry into task registration: the signal fires the
# autodiscover connected by MrMap/celery.py, which imports the "tasks"
# module of every installed app
app.loader.import_default_modules()

print("__MARKER__" + json.dumps(sorted(app.tasks)))
"""

WORKER_IMPORT_SCRIPT = WORKER_IMPORT_TEMPLATE.replace(
    "__MARKER__", TASKS_MARKER)

# a worker start pays for itself once, not once per test method
_replay_cache = {}


def worker_registered_tasks():
    """The task names ``app.tasks`` holds after the worker's own import.

    Run in a fresh interpreter over the same checkout and environment as
    the test process, with the system checks off: the registration is about
    the task imports, and the checks of the fixup would reach the database.
    """
    if "tasks" not in _replay_cache:
        result = subprocess.run(
            [sys.executable, "-c", WORKER_IMPORT_SCRIPT],
            cwd=str(BACKEND_DIR),
            env=dict(os.environ, CELERY_SKIP_CHECKS="1"),
            capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise AssertionError(
                "the worker import replay failed with %d:\n%s\n%s"
                % (result.returncode, result.stdout, result.stderr))
        line = next(
            (entry for entry in result.stdout.splitlines()
             if entry.startswith(TASKS_MARKER)), None)
        if line is None:
            raise AssertionError(
                "the worker import replay printed no task list:\n%s\n%s"
                % (result.stdout, result.stderr))
        _replay_cache["tasks"] = set(json.loads(line[len(TASKS_MARKER):]))
    return _replay_cache["tasks"]


def _dotted(path):
    """The import name of a source file inside the backend, e.g.
    ``registry.tasks.alerts`` for ``registry/tasks/alerts.py``."""
    parts = list(path.relative_to(BACKEND_DIR).parts)
    parts[-1] = parts[-1][:-len(".py")]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _task_files():
    """Every source module the worker's autodiscover can arrive at: the
    ``tasks.py`` of an app and the modules of a ``tasks/`` package."""
    files = list(BACKEND_DIR.glob("*/tasks.py"))
    for package in BACKEND_DIR.glob("*/tasks"):
        files.extend(entry for entry in package.rglob("*.py")
                     if "__pycache__" not in entry.parts)
    return sorted(files)


def _source_files():
    """Every application source file, the tests and the migrations aside."""
    return sorted(
        path for path in BACKEND_DIR.rglob("*.py")
        if not {"tests", "migrations", "__pycache__"} & set(path.parts))


def _decorates_task(node):
    """The decorator call which turns a function into a celery task, or None."""
    for decorator in node.decorator_list:
        called = (decorator.func if isinstance(decorator, ast.Call)
                  else decorator)
        if ((isinstance(called, ast.Name)
             and called.id in ("task", "shared_task"))
                or (isinstance(called, ast.Attribute)
                    and called.attr in ("task", "shared_task"))):
            return decorator
    return None


def _wire_name(decorator, module, function):
    """The name the task has on the queue: the explicit ``name=`` of the
    decorator or, as celery does by default, module and function."""
    if isinstance(decorator, ast.Call):
        for keyword in decorator.keywords:
            if keyword.arg == "name":
                try:
                    name = ast.literal_eval(keyword.value)
                except ValueError:
                    raise AssertionError(
                        "%s declares a task name which does not read "
                        "statically; the scans of this module cannot follow "
                        "it" % module)
                if not isinstance(name, str):
                    raise AssertionError(
                        "%s declares a task name which is not a string; the "
                        "scans of this module cannot follow it" % module)
                return name
    return "%s.%s" % (module, function)


@functools.lru_cache(maxsize=None)
def task_definitions():
    """The tasks the sources define, keyed by defining module and function,
    valued by the name the task has on the queue."""
    definitions = {}
    for path in _task_files():
        module = _dotted(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decorator = _decorates_task(node)
                if decorator is not None:
                    definitions[(module, node.name)] = _wire_name(
                        decorator, module, node.name)
    return definitions


def _func_path(node):
    """The dotted text of a plain ``a.b.c`` callable, or None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


@functools.lru_cache(maxsize=None)
def published_references():
    """The task names the sources publish.

    Two shapes are read out of the application code: the names a call site
    resolves to — ``<name>.apply_async()``, ``<name>.delay()``,
    ``<name>.apply()`` where the name was imported from the module which
    defines the task (or names a task defined in the same file) — and the
    names given as strings: the first argument of ``send_task`` and the
    ``task`` of a ``PeriodicTask`` row which a ``post_migrate`` handler
    seeds.

    Returns ``(published, scheduled)``: the names of the first group, the
    names of the second group.
    """
    definitions = task_definitions()
    task_modules = {module for module, _ in definitions}
    published, scheduled = set(), set()
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = _dotted(path)
        # what a plain name means at a call site in this file: the task it
        # was imported from, aliased or not, plus the tasks defined here
        names = {
            alias.asname or alias.name: (node.module, alias.name)
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            if node.level == 0 and node.module in task_modules
            for alias in node.names
        }
        names.update({
            function: (defined_module, function)
            for defined_module, function in definitions
            if defined_module == module
        })
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func
            if (isinstance(called, ast.Attribute)
                    and called.attr in ("apply_async", "delay", "apply")
                    and isinstance(called.value, ast.Name)
                    and called.value.id in names):
                published.add(definitions[names[called.value.id]])
            elif called is not None and _func_path(called) is not None:
                path_text = _func_path(called)
                if (path_text.endswith(".send_task") and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    published.add(node.args[0].value)
                elif path_text.startswith("PeriodicTask.objects."):
                    scheduled.update(_scheduled_task_name(node))
    return published, scheduled


def _scheduled_task_name(call):
    """The ``task`` of a ``PeriodicTask`` creation: a keyword or an entry of
    the ``defaults`` dict, whichever shape the handler chose."""
    found = []
    for keyword in call.keywords:
        if keyword.arg == "task" and isinstance(keyword.value, ast.Constant):
            found.append(keyword.value.value)
        if keyword.arg == "defaults" and isinstance(keyword.value, ast.Dict):
            for key, value in zip(keyword.value.keys, keyword.value.values):
                if (isinstance(key, ast.Constant) and key.value == "task"
                        and isinstance(value, ast.Constant)):
                    found.append(value.value)
    return [name for name in found if isinstance(name, str)]


def _registry_task_modules():
    """The modules below ``registry/tasks/`` which define at least one task."""
    return {
        module for module, _ in task_definitions()
        if module.startswith("registry.tasks.") and module != "registry.tasks"
    }


def _manifest_imports():
    """The task modules ``registry/tasks/__init__.py`` imports."""
    tree = ast.parse(
        (BACKEND_DIR / "registry" / "tasks" / "__init__.py").read_text(
            encoding="utf-8"),
        filename=str(BACKEND_DIR / "registry" / "tasks" / "__init__.py"))
    return {
        "registry.tasks.%s" % node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.level == 1 and node.module
    }


class RegistryTasksManifestTests(SimpleTestCase):
    """Every task module of the registry is in the manifest the worker reads.

    The static guard against the next #1199: a module added under
    ``registry/tasks/`` without joining ``registry/tasks/__init__.py`` is
    never imported by the worker, and everything published to it is
    discarded. ``registry/tasks/`` has no subpackages, so the manifest's own
    imports are the registration of everything below it.
    """

    def test_the_manifest_imports_every_task_module_of_the_registry(self):
        missing = sorted(
            _registry_task_modules() - _manifest_imports()
            - set(IMPORTED_ELSEWHERE_AT_WORKER_START))
        self.assertEqual(
            missing, [],
            "these registry task modules define tasks but no start-up "
            "import of the worker reaches them; add them to "
            "registry/tasks/__init__.py, or to the exceptions there only "
            "with an import which answers it: %s" % ", ".join(missing))


class WorkerImportTests(SimpleTestCase):
    """What a worker can run after its own import — no test process imports.

    The replay registers exactly what a start-up import reaches; a name the
    sources publish but the replay does not know is a message the worker
    discards.
    """

    def test_the_replay_reads_a_useful_task_list(self):
        # a replay which silently stopped importing would make every
        # membership assertion below vacuous; this one is only worth its
        # name if a known registered task is really in the list
        registered = worker_registered_tasks()
        self.assertTrue(registered)
        self.assertIn(
            "registry.tasks.harvest.check_for_files_to_import", registered)

    def test_the_alert_refresh_of_the_attention_is_registered(self):
        self.assertIn(
            ALERT_REFRESH_TASK, worker_registered_tasks(),
            "the worker discards every message naming the refresh of the "
            "alert rows — the loss of #1199 is back")

    def test_every_task_the_code_publishes_is_registered(self):
        published, _ = published_references()
        self.assertIn(ALERT_REFRESH_TASK, published,
                      "the scan lost the call site of the alerts refresh")
        registered = worker_registered_tasks()
        missing = sorted(
            name for name in published - registered
            if name.rsplit(".", 1)[0] not in NOT_REACHED_BY_THE_REPLAY)
        self.assertEqual(
            missing, [],
            "the code publishes these tasks but a worker which starts "
            "without them discards every message of them: %s"
            % ", ".join(missing))

    def test_every_task_the_beat_rows_are_seeded_with_is_registered(self):
        _, scheduled = published_references()
        self.assertIn(ALERT_REFRESH_TASK, scheduled,
                      "the scan lost the seeded schedule of the refresh")
        registered = worker_registered_tasks()
        missing = sorted(
            name for name in scheduled - registered
            if name.rsplit(".", 1)[0] not in NOT_REACHED_BY_THE_REPLAY)
        self.assertEqual(
            missing, [],
            "beat fires these tasks but a worker without them discards "
            "every fire: %s" % ", ".join(missing))
