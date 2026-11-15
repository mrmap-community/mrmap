#!/usr/bin/env python3
"""Local Git hook checks; reuse the project's lint settings and test containers.

The index (commit) or pushed tree (push) is exported into a temporary directory.
Checks never lint unrelated working edits or regenerate the user's catalogs.
No application dependencies are imported on the host.
"""

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid


def run(args, *, cwd, env=None, capture=False):
    return subprocess.run(
        [str(arg) for arg in args], cwd=cwd, env=env, check=True,
        # The pre-push hook's stdin is Git's ref-update protocol. A child
        # (especially Compose) must never consume updates intended for us.
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE if capture else None,
    ).stdout


def git(root, *args, env=None):
    return run(["git", *args], cwd=root, env=env, capture=True)


def sonar_configuration(root, required=False):
    configured = git(root, "config", "--bool", "--default", "false", "--get",
                     "mrmap.sonarPrePush").decode().strip() == "true"
    token = os.environ.get("SONAR_TOKEN", "").strip()
    if not (required or configured or token):
        return None
    if not token:
        raise RuntimeError("SONAR_TOKEN is required; inject it through the agent launcher")
    scanner = shutil.which("sonar-scanner")
    if not scanner:
        raise RuntimeError("provision SonarScanner CLI on the agent's PATH before pushing")
    if git(root, "rev-parse", "--is-shallow-repository").decode().strip() == "true":
        raise RuntimeError("Sonar needs full Git history; run git fetch --unshallow")
    # Public identifiers of the existing SonarCloud project; CI can override
    # the same properties with its repository variables.
    return {
        "scanner": scanner,
        "organization": os.environ.get("SONAR_ORGANIZATION") or "mrmap-community",
        "project": os.environ.get("SONAR_PROJECT_KEY") or "mrmap-community_mrmap",
        "target": os.environ.get("SONAR_TARGET_BRANCH") or "master",
    }


def scan_sonar(snapshot, configuration, revision, remote_ref):
    if not (snapshot / "sonar-project.properties").is_file():
        raise RuntimeError("the pushed tree must contain sonar-project.properties")
    environment = os.environ.copy()
    # Git's exported local environment describes the original checkout. Use
    # the exported commit's own Git metadata and no inherited CI/PR context.
    for name in git(snapshot, "rev-parse", "--local-env-vars").decode().splitlines():
        environment.pop(name, None)
    for name in list(environment):
        if name.startswith("GITHUB_"):
            environment.pop(name)
    for name in ("SONAR_SCANNER_JSON_PARAMS", "SONARQUBE_SCANNER_PARAMS"):
        environment.pop(name, None)
    environment["SONAR_HOST_URL"] = "https://sonarcloud.io"
    branch = f"pre-push/{remote_ref.removeprefix('refs/heads/')}"
    print(f"git checks: Sonar static analysis on {branch} (coverage remains in CI)", flush=True)
    run([
        configuration["scanner"],
        "-Dsonar.host.url=https://sonarcloud.io",
        f"-Dsonar.organization={configuration['organization']}",
        f"-Dsonar.projectKey={configuration['project']}",
        f"-Dsonar.branch.name={branch}",
        f"-Dsonar.branch.target={configuration['target']}",
        f"-Dsonar.scm.revision={revision}",
        "-Dsonar.qualitygate.wait=true",
        "-Dsonar.qualitygate.timeout=300",
        # This separate preview branch checks static rules and duplication.
        # A pre-push run has no full-suite coverage reports; never publish its
        # coverage result over the real branch/PR analysis produced by CI.
        "-Dsonar.coverage.exclusions=**",
        "-Dsonar.python.coverage.reportPaths=",
        "-Dsonar.javascript.lcov.reportPaths=",
    ], cwd=snapshot, env=environment)


def install_hooks(root, uninstall=False, sonar=False):
    """Install tiny executable wrappers without changing tracked file modes.

    Git's hooks directory is shared by linked worktrees. Refuse to replace a
    custom hook or redirect an existing hooksPath setting.
    """
    configured = git(root, "config", "--default", "", "--get", "core.hooksPath").decode().strip()
    if configured:
        raise RuntimeError(f"core.hooksPath is already {configured}; integrate the hooks manually")
    directory = Path(git(root, "rev-parse", "--path-format=absolute", "--git-path", "hooks").decode().strip())
    marker = b"#!/bin/sh\n# MrMap managed hook; checks live in scripts/git_checks.py.\n"
    targets = [directory / name for name in ("pre-commit", "pre-push")]
    for target in targets:
        if target.is_symlink() or (target.exists() and not target.read_bytes().startswith(marker)):
            raise RuntimeError(f"custom hook at {target}; integrate the hooks manually")
    if sonar:
        sonar_configuration(root, required=True)
    if uninstall:
        for target in targets:
            target.unlink(missing_ok=True)
        git(root, "config", "mrmap.sonarPrePush", "false")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        for target in targets:
            shutil.copyfile(root / ".githooks" / target.name, target)
            target.chmod(0o755)
        if sonar:
            git(root, "config", "mrmap.sonarPrePush", "true")
    print(f"git checks: {'removed' if uninstall else 'installed'} hooks in {directory}")


def changed_paths(root, *revisions):
    return [os.fsdecode(path) for path in git(
        root, "diff", "--name-only", "--no-renames", "-z", *revisions,
        "--",
    ).split(b"\0") if path]


def push_trees(root, lines, remote="origin"):
    """Git supplies one update per line, including deletions and new refs.

    For a new ref, compare with the fetched remote default branch's merge
    base; without a known baseline check the entire tip. Never fetch implicitly
    or assume that the working HEAD is the ref being pushed.
    """
    for line in lines:
        _local_ref, local_oid, remote_ref, remote_oid = line.split()
        if set(local_oid) == {"0"}:
            continue
        tree = git(root, "rev-parse", "--verify", f"{local_oid}^{{commit}}")
        tree = tree.decode().strip()
        if set(remote_oid) == {"0"}:
            baseline = git(root, "for-each-ref", "--format=%(symref)",
                           f"refs/remotes/{remote}/HEAD").decode().strip()
            if not baseline:
                baseline = git(root, "for-each-ref", "--format=%(refname)",
                               f"refs/remotes/{remote}/master").decode().strip()
            try:
                base = git(root, "merge-base", local_oid, baseline).decode().strip() if baseline else None
            except subprocess.CalledProcessError:
                base = None
            paths = changed_paths(root, base, local_oid) if base else [
                os.fsdecode(path) for path in git(
                    root, "ls-tree", "-r", "--name-only", "-z", tree,
                ).split(b"\0") if path]
        else:
            paths = changed_paths(root, remote_oid, local_oid)
        yield tree, paths, remote_ref


def selection(paths, stage):
    backend = [p for p in paths if p.startswith("backend/")
               and not p.endswith((".md", ".rst"))]
    frontend = [p for p in paths if p.startswith("frontend/")
                and not p.endswith((".md", ".rst"))]
    if stage == "push":
        return bool(backend), bool(frontend)
    python = [p[len("backend/"):] for p in backend if p.endswith(".py")
              and not p.startswith("backend/tests/")]
    javascript = [p[len("frontend/"):] for p in frontend
                  if p.startswith("frontend/src/")
                  and p.endswith((".js", ".jsx", ".ts", ".tsx"))]
    # Config/dependency changes can affect files that were not edited.
    if any(p == "backend/setup.cfg" or p.startswith("backend/.requirements/")
           for p in backend):
        python = ["."]
    if any(p in {"frontend/eslint.config.mjs", "frontend/package.json",
                 "frontend/package-lock.json"} for p in frontend):
        javascript = ["src"]
    return python, javascript


def export_tree(root, destination, tree, history=False):
    env = os.environ.copy()
    if history:
        for name in git(root, "rev-parse", "--local-env-vars").decode().splitlines():
            env.pop(name, None)
        run(["git", "clone", "--shared", "--no-checkout", "--quiet", "--",
             root, destination], cwd=root, env=env)
        git(destination, "checkout", "--detach", "--quiet", tree, env=env)
        return
    if tree is not None:
        # A private index makes this work for refs other than HEAD, without
        # checking out a branch or touching the live index.
        env["GIT_INDEX_FILE"] = str(destination.parent / "snapshot.index")
        git(root, "read-tree", tree, env=env)
    git(root, "checkout-index", "--all", f"--prefix={destination}/", env=env)


class Containers:
    """One disposable Compose project per check; dependency images stay cached."""

    def __init__(self, root, snapshot):
        self.root = root
        self.snapshot = snapshot
        self.project = f"mrmap-agent-hooks-{uuid.uuid4().hex[:12]}"
        self.env = os.environ.copy()
        self.env["COMPOSE_PROJECT_NAME"] = self.project
        # Do not inherit the developer's stack or additional compose layers.
        self.env.pop("COMPOSE_FILE", None)
        self.env.pop("COMPOSE_REMOVE_ORPHANS", None)
        self.files = ["docker-compose.yml", "docker-compose.dev.yml"]
        self.started = False

    def prepare(self, backend, frontend):
        run([sys.executable, self.root / "scripts/agent_capacity"], cwd=self.root)
        for relative in (".env", "docker/backend/.mrmap.env"):
            source = self.root / relative
            if not source.is_file():
                raise RuntimeError(f"configure {source} before running Docker checks")
            shutil.copy2(source, self.snapshot / relative)
        for image, needed in (("backend", backend), ("frontend", frontend)):
            if not needed:
                continue
            fp = run([
                sys.executable, self.root / "scripts/dev_image_id.py",
                "--repo-root", self.snapshot, "--resolve", "--image", image,
            ], cwd=self.snapshot, capture=True).decode().strip()
            if image == "backend":
                self.env["MRMAP_BACKEND_DEV_FP"] = fp
                self.files.append("docker-compose.prebuilt.yml")
            else:
                self.env["MRMAP_FRONTEND_IMAGE_FP"] = fp
                self.env["MRMAP_FRONTEND_DEV_IMAGE"] = (
                    f"ghcr.io/mrmap-community/mrmap-frontend-dev:{fp}")
                self.files.append("docker-compose.prebuilt-frontend.yml")
        override = self.snapshot / "hooks.override.yml"
        override.write_text(
            "services:\n  frontend-tests:\n"
            f"    container_name: {self.project}-frontend-tests\n")
        self.files.append(str(override))

    def compose(self, *args, capture=False):
        command = ["docker", "compose", "-p", self.project]
        for filename in self.files:
            command.extend(["-f", filename])
        return run([*command, *args], cwd=self.snapshot, env=self.env,
                   capture=capture)

    def check(self, stage, backend, frontend):
        self.prepare(bool(backend), bool(frontend))
        # Cleanup is armed before Compose can create any project resources.
        self.started = True
        if backend:
            # Match CI: generated Python/catalog files must remain removable
            # by the host user when the temporary source tree is discarded.
            user = f"{os.getuid()}:{os.getgid()}"
            if stage == "commit":
                self.compose("run", "--rm", "--no-deps", "-T",
                             "--user", user,
                             "--entrypoint", "flake8", "pre-commit-check",
                             "--jobs=1", "--config=/opt/mrmap/setup.cfg", "--", *backend)
            else:
                self.compose("up", "-d", "postgis", "redis")
                self.compose("run", "--rm", "--no-deps", "-T",
                             "--user", user, "pre-commit-check")
        if frontend:
            command = (["npx", "--no-install", "eslint", "--max-warnings", "0",
                        "--", *frontend] if stage == "commit" else
                       ["/bin/sh", "-c", "npm run lint && npm run type-check && "
                        "npm run test -- --run src/i18n"])
            self.compose("run", "--rm", "--no-deps", "-T", "frontend-tests", *command)

    def close(self):
        if not self.started:
            return
        # Ownership is the exact generated project label, never a name prefix.
        owned = run([
            "docker", "ps", "-a", "--filter",
            f"label=com.docker.compose.project={self.project}",
            "--format", "{{.Names}}",
        ], cwd=self.snapshot, capture=True).decode().strip()
        if owned:
            print(f"git checks: cleaning {self.project}: {owned}", flush=True)
        self.compose("down", "--volumes")
        for resource in ("container", "network", "volume"):
            command = (["docker", "ps", "-aq"] if resource == "container" else
                       ["docker", resource, "ls", "-q"])
            leftovers = run([
                *command, "--filter", f"label=com.docker.compose.project={self.project}",
            ], cwd=self.snapshot, capture=True).decode().strip()
            if leftovers:
                raise RuntimeError(f"{self.project} left {resource} resources: {leftovers}")


def check_tree(root, stage, tree, paths, remote_ref=""):
    backend, frontend = selection(paths, stage)
    sonar = None
    if (stage == "push" and remote_ref.startswith("refs/heads/")
            and (backend or frontend or "sonar-project.properties" in paths)):
        # Check credentials before starting the heavier Docker checks.
        sonar = sonar_configuration(root)
    if not backend and not frontend and not sonar:
        return
    with tempfile.TemporaryDirectory(prefix="mrmap-git-checks-") as tmp:
        snapshot = Path(tmp) / "source"
        snapshot.mkdir()
        export_tree(root, snapshot, tree, history=bool(sonar))
        if stage == "commit":
            # Deletions affect push checks but must not be passed to a linter.
            backend = [p for p in backend if (snapshot / "backend" / p).exists()]
            frontend = [p for p in frontend if (snapshot / "frontend" / p).exists()]
            executable = root / ".venv/bin/flake8"
            flake8 = str(executable) if executable.is_file() else shutil.which("flake8")
            if backend and flake8:
                print("git checks: linting staged Python", flush=True)
                run([flake8, "--jobs=1", "--config=setup.cfg", "--", *backend],
                    cwd=snapshot / "backend")
                backend = []
        if backend or frontend:
            containers = Containers(root, snapshot)
            try:
                containers.check(stage, backend, frontend)
            finally:
                containers.close()
        if sonar:
            scan_sonar(snapshot, sonar, tree, remote_ref)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("install", "uninstall", "commit", "push"))
    parser.add_argument("--sonar", action="store_true",
                        help="with install: require SonarScanner and SONAR_TOKEN on code pushes")
    parser.add_argument("remote", nargs="?", help="remote name supplied by Git")
    parser.add_argument("url", nargs="?", help="remote URL supplied by Git")
    args = parser.parse_args()
    if args.sonar and args.stage != "install":
        parser.error("--sonar is only supported with install")
    root = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").decode().strip())
    if args.stage in {"install", "uninstall"}:
        install_hooks(root, uninstall=args.stage == "uninstall", sonar=args.sonar)
        return
    if args.stage == "commit":
        check_tree(root, args.stage, None, changed_paths(root, "--cached"))
    else:
        for tree, paths, remote_ref in push_trees(root, sys.stdin, args.remote or "origin"):
            check_tree(root, args.stage, tree, paths, remote_ref)


if __name__ == "__main__":
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except KeyboardInterrupt:
        print("git checks: interrupted", file=sys.stderr)
        sys.exit(130)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"git checks: {error}\nFix the check or its prerequisites and retry.",
              file=sys.stderr)
        sys.exit(1)
