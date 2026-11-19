"""Exercise the real frontend bootstrap with stubbed Node/npm, offline.

Run with ``python3 scripts/test_frontend_bootstrap.py``. No containers,
dependency downloads or host Node installation are needed.
"""

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DEV_COMMAND = ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


class FrontendBootstrapTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="frontend bootstrap-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.app = self.root / "frontend"
        self.deps = self.root / "image-deps"
        self.modules = self.app / "node_modules"
        self.app.mkdir()
        for name in ("package.json", "package-lock.json"):
            (self.app / name).write_text("{}\n")
        self.log = self.root / "npm.jsonl"
        binary = self.root / "bin"
        binary.mkdir()
        self.env = {
            **os.environ,
            "PATH": f"{binary}:{os.defpath}",
            "NPM_LOG": str(self.log),
            "FAKE_NODE_VERSION": "v26.0.0",
            "FAKE_NPM_VERSION": "11.0.0",
            "MRMAP_FRONTEND_IMAGE_FP": "",
        }
        (binary / "node").write_text(
            '#!/bin/sh\nprintf "%s\\n" "$FAKE_NODE_VERSION"\n')
        (binary / "npm").write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            "args = sys.argv[1:]\n"
            "if args == ['-v']:\n"
            "    print(os.environ['FAKE_NPM_VERSION'])\n"
            "    sys.exit(0)\n"
            "with open(os.environ['NPM_LOG'], 'a') as log:\n"
            "    log.write(json.dumps(args) + '\\n')\n"
            "if args[0] == 'ci':\n"
            "    if os.environ.get('NPM_CI_FAIL'):\n"
            "        sys.exit(23)\n"
            "    vite = pathlib.Path('node_modules/.bin/vite')\n"
            "    vite.parent.mkdir(parents=True, exist_ok=True)\n"
            "    vite.write_text('installed')\n"
            "elif args[:2] == ['run', 'dev']:\n"
            "    if not pathlib.Path('node_modules/.bin/vite').exists():\n"
            "        sys.exit('vite: not found')\n")
        for path in binary.iterdir():
            path.chmod(0o755)
        # Relocate only the container paths; run the shipped shell logic.
        source = (ROOT / "docker/frontend/tests-entrypoint.sh").read_text()
        source = source.replace("APP_DIR=/opt/mrmap/frontend",
                                f"APP_DIR={shlex.quote(str(self.app))}")
        source = source.replace("DEPS_DIR=/opt/frontend-deps",
                                f"DEPS_DIR={shlex.quote(str(self.deps))}")
        self.script = self.root / "bootstrap.sh"
        self.script.write_text(source)

    def run_bootstrap(self, **environment):
        return subprocess.run(
            ["sh", str(self.script), *DEV_COMMAND], cwd=self.app,
            env={**self.env, **environment}, capture_output=True, text=True,
            timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def install_count(self):
        return sum(call[0] == "ci" for call in self.calls())

    def prebuilt(self, fingerprint=None):
        modules = self.deps / "node_modules/.bin"
        modules.mkdir(parents=True)
        (modules / "vite").write_text("prebuilt")
        data = b"".join((self.app / name).read_bytes()
                        for name in ("package.json", "package-lock.json"))
        data += b"v26.0.0\n11.0.0\n"
        marker = fingerprint or hashlib.sha256(data).hexdigest()[:12]
        (self.deps / ".mrmap-deps-fp").write_text(marker + "\n")

    def test_plain_node_installs_before_dev_and_reuses_warm_volume(self):
        self.assert_success(self.run_bootstrap())
        self.assertEqual(self.calls(), [
            ["ci", "--no-audit", "--no-fund"], DEV_COMMAND[1:]])
        self.assert_success(self.run_bootstrap())
        self.assertEqual(self.install_count(), 1)

    def test_manifest_and_lockfile_changes_reinstall(self):
        self.assert_success(self.run_bootstrap())
        for count, name in enumerate(("package.json", "package-lock.json"), 2):
            with self.subTest(name=name):
                (self.app / name).write_text('{"changed": true}\n')
                self.assert_success(self.run_bootstrap())
                self.assertEqual(self.install_count(), count)

    def test_node_and_npm_changes_reinstall(self):
        self.assert_success(self.run_bootstrap())
        self.assert_success(self.run_bootstrap(FAKE_NODE_VERSION="v26.1.0"))
        self.assert_success(self.run_bootstrap(
            FAKE_NODE_VERSION="v26.1.0", FAKE_NPM_VERSION="11.1.0"))
        self.assertEqual(self.install_count(), 3)

    def test_matching_prebuilt_image_seeds_without_installing(self):
        self.prebuilt()
        self.assert_success(self.run_bootstrap())
        self.assert_success(self.run_bootstrap())
        self.assertEqual(self.install_count(), 0)
        self.assertEqual((self.modules / ".bin/vite").read_text(), "prebuilt")
        self.assertEqual(self.calls(), [DEV_COMMAND[1:], DEV_COMMAND[1:]])

    def test_stale_prebuilt_image_installs_instead_of_seeding(self):
        self.prebuilt("stale")
        self.assert_success(self.run_bootstrap())
        self.assertEqual(self.install_count(), 1)
        self.assertEqual((self.modules / ".bin/vite").read_text(), "installed")

    def test_canonical_image_change_reseeds(self):
        self.prebuilt()
        self.assert_success(self.run_bootstrap(MRMAP_FRONTEND_IMAGE_FP="first"))
        stale = self.modules / "stale-file"
        stale.touch()
        self.assert_success(self.run_bootstrap(MRMAP_FRONTEND_IMAGE_FP="second"))
        self.assertFalse(stale.exists())
        self.assertTrue((self.modules / ".mrmap-deps-fp").read_text().startswith("second "))
        self.assertEqual(self.install_count(), 0)

    def test_failed_install_stops_before_dev_and_is_retried(self):
        result = self.run_bootstrap(NPM_CI_FAIL="1")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertFalse((self.modules / ".mrmap-deps-fp").exists())
        self.assertEqual(self.calls(), [["ci", "--no-audit", "--no-fund"]])
        self.assert_success(self.run_bootstrap())
        self.assertEqual(self.install_count(), 2)


if __name__ == "__main__":
    unittest.main()
