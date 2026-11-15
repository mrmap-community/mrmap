"""Offline hook regressions: real Git trees, fake check executables, no Docker."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("git_checks", ROOT / "scripts/git_checks.py")
hooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hooks)
ZERO = "0" * 40


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="mrmap-hook-tests-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo with spaces"
        self.root.mkdir()
        self.git("init", "-q", "--initial-branch=master")
        self.git("config", "user.email", "hooks@example.com")
        self.git("config", "user.name", "Hook tests")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", "initial\n")
        self.commit()

    def git(self, *args):
        env = os.environ.copy()
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
            env.pop(name, None)
        return subprocess.check_output(["git", *args], cwd=self.root, env=env).decode().strip()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def update(self, local, remote=ZERO, ref="refs/heads/topic"):
        return f"{ref} {local} {ref} {remote}\n"

    def templates(self):
        for name in ("pre-commit", "pre-push"):
            destination = self.root / ".githooks" / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(ROOT / ".githooks" / name, destination)

    def test_installer_is_idempotent_and_preserves_tracked_modes(self):
        self.templates()
        self.commit()
        hooks.install_hooks(self.root)
        hooks.install_hooks(self.root)
        for name in ("pre-commit", "pre-push"):
            self.assertTrue(os.access(self.root / ".git/hooks" / name, os.X_OK))
            self.assertEqual((self.root / ".githooks" / name).stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.git("status", "--porcelain"), "")
        hooks.install_hooks(self.root, uninstall=True)
        self.assertFalse((self.root / ".git/hooks/pre-commit").exists())
        self.assertFalse((self.root / ".git/hooks/pre-push").exists())

    def test_installer_preserves_custom_hooks_without_partial_install(self):
        self.templates()
        custom = self.write(".git/hooks/pre-push", "#!/bin/sh\necho custom\n")
        with self.assertRaisesRegex(RuntimeError, "custom hook"):
            hooks.install_hooks(self.root)
        self.assertEqual(custom.read_text(), "#!/bin/sh\necho custom\n")
        self.assertFalse((self.root / ".git/hooks/pre-commit").exists())

    def test_installer_preserves_custom_hooks_path(self):
        self.templates()
        self.git("config", "core.hooksPath", ".custom-hooks")
        with self.assertRaisesRegex(RuntimeError, "core.hooksPath"):
            hooks.install_hooks(self.root)
        self.assertEqual(self.git("config", "--get", "core.hooksPath"), ".custom-hooks")

    def test_documentation_skips_snapshot_and_containers(self):
        with patch.object(hooks, "export_tree") as export, patch.object(hooks, "Containers") as docker:
            hooks.check_tree(self.root, "commit", None, ["docs/example.rst"])
            hooks.check_tree(self.root, "push", "HEAD", ["backend/AGENTS.md"])
            export.assert_not_called()
            docker.assert_not_called()

    def test_staged_content_and_config_ignore_working_edits(self):
        self.write("backend/setup.cfg", "[flake8]\nignore = E501\n")
        self.write("backend/a file.py", "staged\n")
        self.git("add", "backend")
        self.write("backend/a file.py", "unstaged\n")
        self.write("backend/setup.cfg", "unstaged config\n")
        index_before = self.git("ls-files", "--stage")
        observed = []
        original_run = hooks.run

        def lint(args, **kwargs):
            if str(args[0]) == "/fake/flake8":
                observed.append(((kwargs["cwd"] / "a file.py").read_text(),
                                 (kwargs["cwd"] / "setup.cfg").read_text()))
                return b""
            return original_run(args, **kwargs)

        with patch.object(hooks.shutil, "which", return_value="/fake/flake8"), patch.object(hooks, "run", side_effect=lint):
            hooks.check_tree(self.root, "commit", None, hooks.changed_paths(self.root, "--cached"))
        self.assertEqual(observed, [("staged\n", "[flake8]\nignore = E501\n")])
        self.assertEqual((self.root / "backend/a file.py").read_text(), "unstaged\n")
        self.assertEqual(self.git("ls-files", "--stage"), index_before)

    def test_lint_failure_blocks_commit_and_preserves_index(self):
        self.write("backend/setup.cfg", "[flake8]\n")
        self.write("backend/module.py", "bad staged code\n")
        self.git("add", "backend")
        executable = self.write(".venv/bin/flake8", "#!/bin/sh\nexit 1\n")
        executable.chmod(0o755)
        self.templates()
        destination = self.root / "scripts/git_checks.py"
        destination.parent.mkdir()
        shutil.copy2(ROOT / "scripts/git_checks.py", destination)
        hooks.install_hooks(self.root)
        before = self.git("rev-parse", "HEAD")
        index_before = self.git("ls-files", "--stage")
        result = subprocess.run(["git", "commit", "-qm", "must fail"], cwd=self.root,
                                capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git("ls-files", "--stage"), index_before)

    def test_failed_backend_check_blocks_real_push_and_cleans_stack(self):
        remote = Path(self.tmp.name) / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "origin", "HEAD:master")
        self.write("backend/module.py", "changed\n")
        self.write("docker/backend/README.md", "fixture\n")
        self.commit()
        self.templates()
        destination = self.root / "scripts/git_checks.py"
        destination.parent.mkdir()
        shutil.copy2(ROOT / "scripts/git_checks.py", destination)
        self.write("scripts/agent_capacity", "raise SystemExit(0)\n")
        self.write("scripts/dev_image_id.py", "print('0123456789ab')\n")
        self.write(".env", "COMPOSE_PROJECT_NAME=developer-stack\n")
        self.write("docker/backend/.mrmap.env", "fixture\n")
        log = self.root / "docker-commands.log"
        docker = self.write("bin/docker", f"#!{sys.executable}\n" +
                            "import sys\n" +
                            f"with open({str(log)!r}, 'a') as log:\n" +
                            "    log.write(' '.join(sys.argv[1:]) + '\\n')\n" +
                            "raise SystemExit(1 if 'run' in sys.argv else 0)\n")
        docker.chmod(0o755)
        hooks.install_hooks(self.root)
        env = {**os.environ, "PATH": f"{docker.parent}:{os.environ['PATH']}"}
        result = subprocess.run(["git", "push", "origin", "HEAD:topic"],
                                cwd=self.root, env=env, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/topic"), "")
        self.assertIn("pre-commit-check", log.read_text())
        self.assertIn("down --volumes", log.read_text())
        self.assertNotIn("developer-stack", log.read_text())

    def test_push_uses_each_pushed_tip_and_not_working_head(self):
        base = self.git("rev-parse", "HEAD")
        self.write("backend/a.py", "pushed\n")
        pushed = self.commit()
        self.write("backend/a.py", "working head\n")
        self.commit()
        updates = [self.update(pushed, base), self.update(ZERO, pushed)]
        trees = list(hooks.push_trees(self.root, updates))
        self.assertEqual(len(trees), 1)
        tree, paths = trees[0]
        self.assertEqual(paths, ["backend/a.py"])
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "snapshot"
            snapshot.mkdir()
            hooks.export_tree(self.root, snapshot, tree)
            self.assertEqual((snapshot / "backend/a.py").read_text(), "pushed\n")
        self.assertEqual((self.root / "backend/a.py").read_text(), "working head\n")

    def test_new_documentation_branch_uses_remote_baseline(self):
        self.write("backend/a.py", "existing code\n")
        base = self.commit()
        self.git("update-ref", "refs/remotes/origin/master", base)
        self.write("docs/topic.rst", "new docs\n")
        head = self.commit()
        _tree, paths = next(hooks.push_trees(self.root, [self.update(head)]))
        self.assertEqual(paths, ["docs/topic.rst"])
        self.assertEqual(hooks.selection(paths, "push"), (False, False))

    def test_unknown_remote_baseline_checks_entire_tree(self):
        self.write("frontend/src/a.ts", "export {};\n")
        head = self.commit()
        _tree, paths = next(hooks.push_trees(self.root, [self.update(head)]))
        self.assertIn("frontend/src/a.ts", paths)

    def test_missing_remote_object_fails_instead_of_skipping(self):
        head = self.git("rev-parse", "HEAD")
        with self.assertRaises(subprocess.CalledProcessError):
            list(hooks.push_trees(self.root, [self.update(head, "1" * 40)]))

    def test_deletions_and_renames_trigger_push_validation(self):
        self.write("backend/a.py", "old\n")
        base = self.commit()
        self.git("mv", "backend/a.py", "README.py")
        head = self.commit()
        _tree, paths = next(hooks.push_trees(self.root, [self.update(head, base)]))
        self.assertEqual(hooks.selection(paths, "push"), (True, False))
        with patch.object(hooks, "Containers") as docker:
            hooks.check_tree(self.root, "commit", head, paths)
            docker.assert_not_called()

    def test_selection_rechecks_config_but_not_backend_test_lint(self):
        self.assertEqual(hooks.selection(["backend/setup.cfg"], "commit"), (["."], []))
        self.assertEqual(hooks.selection(["frontend/package-lock.json"], "commit"), ([], ["src"]))
        self.assertEqual(hooks.selection(["backend/tests/test_example.py"], "commit"), ([], []))
        self.assertEqual(hooks.selection(["frontend/src/a file.ts"], "commit"), ([], ["src/a file.ts"]))

    def test_snapshots_work_in_linked_worktrees(self):
        worktree = Path(self.tmp.name) / "linked"
        self.git("worktree", "add", "-qb", "linked", str(worktree))
        (worktree / "README.md").write_text("linked index\n")
        subprocess.run(["git", "add", "README.md"], cwd=worktree, check=True)
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = Path(tmp) / "snapshot"
            snapshot.mkdir()
            hooks.export_tree(worktree, snapshot, None)
            self.assertEqual((snapshot / "README.md").read_text(), "linked index\n")
        self.assertEqual((self.root / "README.md").read_text(), "initial\n")

    def test_container_failure_always_attempts_cleanup(self):
        self.write("frontend/src/a.ts", "export {};\n")
        head = self.commit()
        with patch.object(hooks, "Containers") as docker:
            docker.return_value.check.side_effect = RuntimeError("check failed")
            with self.assertRaisesRegex(RuntimeError, "check failed"):
                hooks.check_tree(self.root, "push", head, ["frontend/src/a.ts"])
            docker.return_value.close.assert_called_once()

    def test_container_commands_use_isolated_stack_and_existing_checks(self):
        self.write(".env", "COMPOSE_PROJECT_NAME=developer-stack\n")
        self.write("docker/backend/.mrmap.env", "fixture\n")
        for stage, backend, frontend in (("commit", ["a file.py"], ["src/a.ts"]),
                                         ("push", True, True)):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as tmp:
                snapshot = Path(tmp)
                (snapshot / "docker/backend").mkdir(parents=True)

                def fake_run(args, **kwargs):
                    if "--resolve" in args:
                        return b"0123456789ab\n"
                    return b""

                with patch.dict(os.environ, {"COMPOSE_FILE": "/foreign/compose.yml"}), patch.object(hooks, "run", side_effect=fake_run) as command:
                    containers = hooks.Containers(self.root, snapshot)
                    containers.check(stage, backend, frontend)
                    containers.close()
                commands = [call.args[0] for call in command.call_args_list]
                self.assertIn(str(self.root / "scripts/agent_capacity"), [str(x) for x in commands[0]])
                compose = [args for args in commands if args[:2] == ["docker", "compose"]]
                self.assertTrue(all(args[2:4] == ["-p", containers.project] for args in compose))
                checks = [args for args in compose if "run" in args]
                self.assertTrue(all("--rm" in args and "--no-deps" in args and "--build" not in args for args in checks))
                if stage == "commit":
                    self.assertFalse(any("up" in args for args in compose))
                    self.assertIn("a file.py", checks[0])
                    self.assertIn("src/a.ts", checks[1])
                else:
                    self.assertTrue(any(args[-4:] == ["up", "-d", "postgis", "redis"] for args in compose))
                    self.assertEqual(checks[0][-1], "pre-commit-check")
                    self.assertEqual(checks[1][-1], "npm run lint && npm run type-check")
                self.assertEqual(containers.env["COMPOSE_PROJECT_NAME"], containers.project)
                self.assertNotIn("COMPOSE_FILE", containers.env)

    def test_cleanup_scopes_every_operation_and_detects_leftovers(self):
        containers = hooks.Containers(self.root, self.root)
        containers.started = True
        with patch.object(hooks, "run", return_value=b"") as command:
            containers.close()
        for call in command.call_args_list:
            args = call.args[0]
            self.assertTrue(containers.project in args or
                            f"label=com.docker.compose.project={containers.project}" in args)
            self.assertNotIn("--remove-orphans", args)
        with patch.object(hooks, "run", side_effect=[b"", b"", b"leftover"]):
            with self.assertRaisesRegex(RuntimeError, "leftover"):
                containers.close()


if __name__ == "__main__":
    unittest.main()
