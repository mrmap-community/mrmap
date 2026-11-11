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
import re
import subprocess
import sys
import tempfile
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


#: the file name pattern of ``tempfile.mkstemp`` and its friends: "tmp" plus
#: eight random characters; a ``.py`` file of this name belongs to a test
#: which is running right now, never to the application
TRANSIENT_ARTIFACT = re.compile(r"tmp[a-z0-9_]{8}\.py\Z")


def read_application_source(path):
    """The text of a file the scans below discovered, or None when a
    transient artifact of a parallel test vanished between listing and read.

    A ``test_api_renderers`` deployment probe which the other worker
    unlinks while this scan is between its listing and its read is the race
    the FileNotFoundError of the #1270 CI run reported; only a name matching
    TRANSIENT_ARTIFACT is forgiven over it. A source file of the application
    which is not there to be read is a real problem and raises.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if TRANSIENT_ARTIFACT.fullmatch(path.name):
            return None
        raise


def _dotted(path, root=BACKEND_DIR):
    """The import name of a source file inside the backend, e.g.
    ``registry.tasks.alerts`` for ``registry/tasks/alerts.py``."""
    parts = list(path.relative_to(root).parts)
    parts[-1] = parts[-1][:-len(".py")]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _task_files(root=BACKEND_DIR):
    """Every source module the worker's autodiscover can arrive at: the
    ``tasks.py`` of an app and the modules of a ``tasks/`` package."""
    files = list(root.glob("*/tasks.py"))
    for package in root.glob("*/tasks"):
        files.extend(entry for entry in package.rglob("*.py")
                     if "__pycache__" not in entry.parts)
    return sorted(files)


def _source_files(root=BACKEND_DIR):
    """Every application source file, the tests and the migrations aside.

    A file lying directly in the backend root is not among them: it belongs
    to no application package, which no start-up import of the worker can
    arrive at — the only one there is ``manage.py``, the launcher. This is
    also what keeps the scan away from the deployment probes which
    ``test_api_renderers`` writes into the backend root with
    ``mkstemp(suffix=".py", dir=BACKEND_DIR)``: those exist for the seconds
    of their subprocess and are unlinked when it answers, and reading one of
    them raced with the removal — the FileNotFoundError which broke this
    module's own check under ``--parallel`` in the #1270 CI run.
    """
    return sorted(
        path for path in root.rglob("*.py")
        if path.parent != root
        and not {"tests", "migrations", "__pycache__"} & set(path.parts))


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
def task_definitions(root=BACKEND_DIR):
    """The tasks the sources define, keyed by defining module and function,
    valued by the name the task has on the queue."""
    definitions = {}
    for path in _task_files(root):
        module = _dotted(path, root)
        text = read_application_source(path)
        if text is None:
            continue
        tree = ast.parse(text, filename=str(path))
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
def published_references(root=BACKEND_DIR):
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
    definitions = task_definitions(root)
    task_modules = {module for module, _ in definitions}
    published, scheduled = set(), set()
    for path in _source_files(root):
        text = read_application_source(path)
        if text is None:
            continue
        tree = ast.parse(text, filename=str(path))
        module = _dotted(path, root)
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


class SourceDiscoveryTests(SimpleTestCase):
    """The scans read the application, not whatever lies next to it.

    ``test_api_renderers`` runs its deployment probe from a script file —
    the interpreter puts the script's own directory on the import path, so
    the probe has to lie in the backend root — and removes it once the
    probe has answered. Under ``--parallel`` that file therefore lives for
    the seconds of a Django start-up inside a directory the scan of this
    module walks; it used to be enumerated as an application source, and
    its read raced with the unlink of the other worker: the
    FileNotFoundError of the #1270 CI run. Both halves of the answer are
    kept below — the backend root is no application directory, and a file
    which vanished between listing and read is forgiven only when its name
    says "tempfile of a test which is running right now".
    """

    def test_the_backend_root_itself_is_not_an_application_directory(self):
        files = _source_files()
        # manage.py is the only .py lying directly in the backend root; it
        # belongs to no app and publishes no task
        self.assertNotIn(BACKEND_DIR / "manage.py", files)
        # application sources are still read: a view which imports a task
        # the worker reaches only through it, and the shared DRF layer
        self.assertIn(BACKEND_DIR / "registry" / "views" / "service.py", files)
        self.assertIn(BACKEND_DIR / "extras" / "viewsets.py", files)

    def test_a_probe_script_in_the_backend_root_changes_nothing(self):
        # the shape of the probe of test_api_renderers to the letter: a
        # .py which mkstemp places in the backend root and which is gone
        # when its subprocess has answered. It carries a publication the
        # scan would report if the root were still scanned.
        published, scheduled = published_references()
        descriptor, script_path = tempfile.mkstemp(
            suffix=".py", dir=str(BACKEND_DIR), text=True)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(
                    "from celery import Celery\n"
                    "\n"
                    "app = Celery()\n"
                    "\n"
                    "app.send_task('probe.must.not.be.scanned')\n")
            self.assertNotIn(Path(script_path), _source_files())
            # a recomputation with the litter in place answers exactly what
            # the scan answered without it — and still finds the real
            # publications, so nothing was lost with the root
            with_litter = published_references(BACKEND_DIR)
            self.assertEqual(with_litter, (published, scheduled))
            self.assertIn(ALERT_REFRESH_TASK, with_litter[0])
        finally:
            os.unlink(script_path)

    def test_a_transient_artifact_which_vanished_while_reading_is_skipped(self):
        # the listing held the file, the read finds nothing: the window the
        # FileNotFoundError of #1270 fell into, replayed on the name the
        # race really produced
        vanished = BACKEND_DIR / "registry" / "tmp0gq1s5bf.py"
        self.assertFalse(vanished.exists())
        self.assertIsNone(read_application_source(vanished))

    def test_a_missing_application_source_is_not_forgiven(self):
        # a name which says application must still answer the missing file
        with self.assertRaises(FileNotFoundError):
            read_application_source(
                BACKEND_DIR / "registry" / "no_such_task_module.py")


class ScanOfAFakeBackendTests(SimpleTestCase):
    """What the scans answer for a small tree of known contents.

    A hand-built backend of a few files answers which references the scans
    find, what their transient artifacts do on the way and what must still
    fail. Everything lies below a temporary directory, so these tests stay
    valid whatever the real applications grow to.
    """

    TASKS_SOURCE = (
        "from celery import shared_task\n"
        "\n"
        "\n"
        "@shared_task\n"
        "def work():\n"
        "    pass\n"
        "\n"
        "\n"
        "@shared_task(name='renamed.work')\n"
        "def named_work():\n"
        "    pass\n")

    VIEWS_SOURCE = (
        "from celery import Celery\n"
        "\n"
        "from app.tasks import work\n"
        "\n"
        "app = Celery()\n"
        "\n"
        "\n"
        "def publish():\n"
        "    work.delay()\n"
        "    work.apply_async()\n"
        "    app.send_task('renamed.work')\n"
        "    app.send_task('app.tasks.never_registered')\n")

    SEEDER_SOURCE = (
        "def seed(sender, **kwargs):\n"
        "    PeriodicTask.objects.create(name='work', task='renamed.work')\n"
        "    PeriodicTask.objects.get_or_create(\n"
        "        name='late',\n"
        "        defaults={'name': 'late', 'task': 'app.tasks.never_registered'})\n")

    @classmethod
    def _fake_backend(cls, root):
        """An app with tasks, publications and seeds, plus the transient
        artifacts of a parallel test run: one probe script which stays in
        the root and must not be read at all — its content would not even
        parse — and one artifact which vanished between listing and read —
        a dangling symlink is the listing with nothing behind it."""
        (root / "app").mkdir()
        (root / "app" / "__init__.py").write_text("", encoding="utf-8")
        (root / "app" / "tasks.py").write_text(cls.TASKS_SOURCE, encoding="utf-8")
        (root / "app" / "views.py").write_text(cls.VIEWS_SOURCE, encoding="utf-8")
        (root / "app" / "seeder.py").write_text(cls.SEEDER_SOURCE, encoding="utf-8")
        staying = root / "tmpaaaaaaaa.py"
        staying.write_text("def (():\n", encoding="utf-8")
        os.symlink(str(root / "gone-with-the-test.py"),
                   str(root / "app" / "tmpbbbbbbbb.py"))
        return root

    def test_the_references_of_the_fake_backend_are_found_despite_the_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._fake_backend(Path(directory))
            published, scheduled = published_references(root)
            self.assertEqual(
                published,
                {"app.tasks.work", "renamed.work", "app.tasks.never_registered"})
            self.assertEqual(
                scheduled, {"renamed.work", "app.tasks.never_registered"})
            # the guard of the registration checks is intact: the name no
            # task module defines is in the published set, so the
            # difference against a worker's registration still reports it
            self.assertIn("app.tasks.never_registered", published)

    def test_a_vanished_file_of_a_real_name_is_not_forgiven(self):
        # the same dangling listing, but under a name which says
        # application: here the FileNotFoundError is the report, not noise
        with tempfile.TemporaryDirectory() as directory:
            root = self._fake_backend(Path(directory))
            os.symlink(str(root / "gone-with-the-test.py"),
                       str(root / "app" / "vanished_module.py"))
            with self.assertRaises(FileNotFoundError):
                published_references(root)
