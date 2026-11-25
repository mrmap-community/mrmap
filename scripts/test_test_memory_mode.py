#!/usr/bin/env python3
"""Config-only checks of the opt-in test mode (#1619); starts no containers.

The shell probe executes the shipped Django command with a recording Python
stub, so a failed test/report cannot become a successful job. The existing
coverage-parallel probe separately exercises real multiprocessing coverage.
"""
import itertools
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODE = "docker-compose.test-low-memory.yml"
BASE = ["docker-compose.yml", "docker-compose.dev.yml"]


def config(files):
    command = ["docker", "compose", "--env-file", "/dev/null"]
    for name in files:
        command.extend(["-f", name])
    command.extend(["config", "--no-interpolate", "--no-env-resolution",
                    "--format", "json"])
    env = dict(os.environ)
    for key in ("COMPOSE_FILE", "COMPOSE_PROFILES"):
        env.pop(key, None)
    result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                            capture_output=True, check=True)
    return json.loads(result.stdout)["services"]


def environment(service):
    values = service.get("environment", {})
    if isinstance(values, list):
        return dict(item.split("=", 1) for item in values)
    # With --no-interpolate a map can retain YAML scalars; a merged list has
    # already become the strings Docker puts in the container environment.
    return {key: str(value).lower() if isinstance(value, bool) else str(value)
            for key, value in values.items()}


@unittest.skipUnless(shutil.which("docker"), "Docker CLI missing: Compose checks unavailable")
class TestMemoryMode(unittest.TestCase):
    def test_mode_only_adds_worker_limits_across_layers(self):
        for backend, frontend, light in itertools.product((False, True), repeat=3):
            files = BASE.copy()
            if backend:
                files.append("docker-compose.prebuilt.yml")
            if frontend:
                files.append("docker-compose.prebuilt-frontend.yml")
            if light:
                files.append("docker-compose.lightweight.yml")
            with self.subTest(files=files):
                normal = config(files)
                low = config([*files, MODE])
                self.assertEqual(set(normal), set(low))
                for name in normal:
                    before, after = normal[name].copy(), low[name].copy()
                    if name in ("django-tests", "frontend-tests"):
                        before_env = environment(before)
                        after_env = environment(after)
                        self.assertNotIn("MRMAP_TEST_WORKERS", before_env)
                        self.assertEqual(after_env.pop("MRMAP_TEST_WORKERS"), "1")
                        self.assertEqual(before_env, after_env)
                        before.pop("environment", None)
                        after.pop("environment", None)
                    self.assertEqual(before, after, name)

    def test_django_command_workers_coverage_and_failure_status(self):
        command = config(BASE)["django-tests"]["command"]
        # --no-interpolate deliberately preserves Compose's dollar escaping.
        # Undo that one escape before giving the command to the container shell.
        if isinstance(command, str):
            command = shlex.split(command.replace("$$", "$"))
        else:
            command = [part.replace("$$", "$") for part in command]
        with tempfile.TemporaryDirectory(prefix="mrmap-1619-") as tmp:
            stub = Path(tmp) / "python"
            stub.write_text("""#!/usr/bin/env python3
import json, os, sys
with open(os.environ['PROBE_LOG'], 'a') as log:
    log.write(json.dumps([sys.argv[1:], os.getenv('COVERAGE_FILE')]) + '\\n')
sys.exit(int(os.environ.get('FAIL_RUN' if sys.argv[3] == 'run' else 'FAIL_XML', '0')))
""")
            stub.chmod(0o755)
            for workers, fail_run, fail_xml in itertools.product(
                    (None, "1", "2", "4"), (0, 13), (0, 17)):
                with self.subTest(workers=workers, fail_run=fail_run, fail_xml=fail_xml):
                    log = Path(tmp) / "calls.jsonl"
                    log.unlink(missing_ok=True)
                    env = dict(os.environ, PATH=tmp + os.pathsep + os.environ["PATH"],
                               PROBE_LOG=str(log), FAIL_RUN=str(fail_run), FAIL_XML=str(fail_xml))
                    env.pop("MRMAP_TEST_WORKERS", None)
                    env.pop("COVERAGE_FILE", None)
                    if workers is not None:
                        env["MRMAP_TEST_WORKERS"] = workers
                    result = subprocess.run(command, env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, fail_run or fail_xml, result.stderr)
                    calls = [json.loads(line) for line in log.read_text().splitlines()]
                    self.assertEqual(len(calls), 1 if fail_run else 2)
                    argv, coverage_file = calls[0]
                    self.assertEqual(coverage_file, ".coverage.unit")
                    self.assertIn("--parallel=" + (workers or "4"), argv)
                    self.assertEqual(argv, [
                        "-m", "coverage", "run", "--data-file=.coverage.unit",
                        "./manage.py", "test", "-v", "3", "/opt/mrmap/tests/",
                        "--noinput", "--parallel=" + (workers or "4")])
                    if not fail_run:
                        self.assertEqual(calls[1][0], [
                            "-m", "coverage", "xml", "--data-file=.coverage.unit",
                            "-o", "unit-tests-coverage-report.xml"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
