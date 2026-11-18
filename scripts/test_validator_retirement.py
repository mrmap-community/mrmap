#!/usr/bin/env python3
"""ETF validator retirement guard (#1529, epic #1527).

Run from the repository root:  python3 scripts/test_validator_retirement.py
Needs git; wants docker and skips the checks that need it out loud when it is
absent, the way the other suites of scripts/ do. Exit 0 = every ran check
passed, 1 = a check failed, 2 = the harness itself could not run (no git).

Why this guard exists
---------------------
#1529 removed the ETF validator from the tracked infrastructure: the
``docker/inspire-validator/`` build subtree, the ``inspire-validator`` service
of ``docker-compose.dev.yml`` (host port 5557), the VS Code task that ran it,
the Sonar exclusion of the subtree and the comments that named its port. The
issue #1528 gate page (docs/source/development/etf-conformity-retirement.rst)
records the removal and the operator cleanup; the acceptance of #1529 asks
that the infrastructure change ships with a test. This is it: the retired
service must not creep back into the files a stack resolves, because a single
re-added block resurrects a Jetty image, a squid proxy and a callback surface
that nothing in the product reads anymore.

What it checks
--------------
1. The tracked infrastructure surfaces - every ``docker-compose*.yml``,
   ``.vscode/*.json``, ``sonar-project.properties``, ``.dockerignore``, every
   ``.github/workflows/*.yml`` and everything under ``docker/`` - carry no
   ``inspire-validator`` in path or content, and no compose file publishes
   port 5557. Tracked files only (``git ls-files``): a worktree-local
   orchestrator overlay is machine-generated and not the surface this guard
   governs.
2. Where docker answers, every committed Compose variant resolves at all
   (base file alone, base + each committed overlay, and the documented agent
   chain base + dev + prebuilt), the resolved services contain no name that
   reads as a validator, no build context under ``docker/inspire-validator``
   and no published port 5557, the ordinary services (backend, postgis,
   redis, celery-worker) still resolve, and the shared networks
   (``mrmap-internal``, ``docker-status``) survive - the issue's "do not
   remove shared tools or networks" seen from the other side.

``docker compose config --no-interpolate`` is what static_mounts_smoke.py
uses for the same reason: it leaves ``${...}`` literal, so no ``.env`` and no
registry fingerprint variable is needed - the surfaces are judged as the
committed text they are, on a runner that has no configured deployment.
"""

import json
import re
import subprocess  # nosec B404 - the point of this suite is to call git and docker
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

BASE_COMPOSE = "docker-compose.yml"
RETIRED_TOKEN = "inspire-validator"
RETIRED_PORT = "5557"
VALIDATOR_RE = re.compile(r"validator", re.IGNORECASE)

# Tracked surfaces whose path and content must be free of the retired name.
SWEEP_PREFIXES = ("docker/", ".github/workflows/", ".vscode/")
SWEEP_FILES = (BASE_COMPOSE, ".dockerignore", "sonar-project.properties")


class HarnessError(Exception):
    """The check could not be run at all - no git to list the tracked files.
    Kept apart from a found reference, which is a real answer."""


RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def git_stdout(*args):
    """git stdout as text, run from the repository root."""
    try:
        process = subprocess.run(  # nosec B603 - fixed argv, fixed cwd
            ["git", *args], capture_output=True, text=True, cwd=ROOT)
    except FileNotFoundError:
        raise HarnessError("the git CLI is not on PATH")
    if process.returncode != 0:
        raise HarnessError(
            f"git {' '.join(args)} exited {process.returncode}: "
            f"{process.stderr.strip()}")
    return process.stdout


def tracked_in_surface():
    """Every tracked file of the infrastructure surfaces, plus every tracked
    docker-compose*.yml (the base and the overlays sit at the root)."""
    tracked = [p for p in git_stdout("ls-files", "-z").split("\0") if p]
    hits = []
    for path in tracked:
        if (path.startswith(SWEEP_PREFIXES) or path in SWEEP_FILES
                or (path.startswith("docker-compose")
                    and path.endswith(".yml"))):
            hits.append(path)
    return tracked, hits


def compose_overlays():
    """The committed overlays in the layered order of AGENTS.md: base alone,
    base + each overlay (sorted by name, like static_mounts_smoke.py), and
    the agent chain a backend job actually runs."""
    _, sweep = tracked_in_surface()
    overlays = sorted(p for p in sweep
                      if p.startswith("docker-compose")
                      and p.endswith(".yml") and p != BASE_COMPOSE)
    combos = [[BASE_COMPOSE]]
    combos += [[BASE_COMPOSE, overlay] for overlay in overlays]
    agent_chain = [BASE_COMPOSE, "docker-compose.dev.yml",
                   "docker-compose.prebuilt.yml"]
    if all(c in overlays or c == BASE_COMPOSE for c in agent_chain):
        combos.append(agent_chain)
    return combos


def text_sweep():
    """No retired name in any tracked infrastructure path or content, no
    retired port in any tracked compose file."""
    tracked, sweep = tracked_in_surface()
    stale_paths = [p for p in tracked if RETIRED_TOKEN in p]
    check("no tracked path names the validator", not stale_paths,
          ", ".join(stale_paths[:5]))
    for path in sweep:
        try:
            content = (ROOT / path).read_text(encoding="utf-8",
                                              errors="replace")
        except OSError as error:
            check(f"surface readable: {path}", False, str(error))
            continue
        lowered = content.lower()
        hits = [line.strip() for line in content.splitlines()
                if RETIRED_TOKEN in line.lower()]
        check(f"no validator reference: {path}", not hits,
              "; ".join(hits[:3]))
        if path.startswith("docker-compose") and RETIRED_PORT in lowered:
            check(f"no port {RETIRED_PORT}: {path}", False,
                  "the retired validator host port reappears")
        elif path.startswith("docker-compose"):
            check(f"no port {RETIRED_PORT}: {path}", True)


def docker_available():
    try:
        process = subprocess.run(  # nosec B603 - fixed argv
            ["docker", "compose", "version"], capture_output=True, text=True)
    except FileNotFoundError:
        return False, "the docker CLI is not on PATH"
    if process.returncode != 0:
        return False, f"docker compose version exited {process.returncode}"
    return True, ""


def compose_config(files):
    """The resolved configuration of these compose files, literal ``${...}``
    and all - no .env, no registry. Raises HarnessError only when the docker
    call itself cannot be made."""
    command = ["docker", "compose"]
    for file in files:
        command += ["-f", file]
    command += ["config", "--no-interpolate", "--format", "json"]
    process = subprocess.run(command, capture_output=True, text=True,
                             cwd=ROOT)  # nosec B603 - fixed argv, fixed cwd
    if process.returncode != 0:
        return None, (f"exited {process.returncode}: "
                      f"{process.stderr.strip() or process.stdout.strip()}")
    try:
        return json.loads(process.stdout), ""
    except json.JSONDecodeError:
        return None, "printed no parsable JSON"


def published_ports(service):
    """Every published port of a service as a string, whatever shape the
    resolved config uses (short string or long-syntax mapping)."""
    ports = []
    for entry in (service.get("ports") or []):
        if isinstance(entry, dict):
            ports.append(str(entry.get("published", "")))
        else:
            ports.append(str(entry))
    return ports


def config_sweep():
    """The resolved compose surface: resolves at all, no validator in it,
    the ordinary services and the shared networks still in it."""
    for combo in compose_overlays():
        label = " + ".join(combo)
        config, error = compose_config(combo)
        if config is None:
            check(f"compose resolves: {label}", False, error)
            continue
        check(f"compose resolves: {label}", True)
        services = config.get("services", {})
        named = [s for s in services if VALIDATOR_RE.search(s)]
        check(f"no validator service: {label}", not named, ", ".join(named))
        built = [s for s, spec in services.items()
                 if RETIRED_TOKEN in str((spec.get("build") or {}).get("context", ""))]
        check(f"no validator build context: {label}", not built,
              ", ".join(built))
        ported = [s for s, spec in services.items()
                  if any(RETIRED_PORT in p for p in published_ports(spec))]
        check(f"no validator port {RETIRED_PORT}: {label}", not ported,
              ", ".join(ported))


def survivor_checks():
    """The part of the removal the issue forbids: shared networks gone, or
    ordinary services no longer resolving after the surgery."""
    config, error = compose_config([BASE_COMPOSE])
    if config is None:
        raise HarnessError(f"the base compose file does not resolve: {error}")
    networks = config.get("networks", {})
    for shared in ("mrmap-internal", "docker-status"):
        check(f"shared network survives: {shared}", shared in networks)
    services = config.get("services", {})
    for ordinary in ("backend", "postgis", "redis", "celery-worker"):
        check(f"ordinary service resolves: {ordinary}", ordinary in services)


def main():
    try:
        text_sweep()
        survivor_checks()
        docker_ok, reason = docker_available()
        if docker_ok:
            config_sweep()
        else:
            print(f"SKIP  the compose config sweep ({reason})")
    except HarnessError as error:
        print(f"harness: {error}", file=sys.stderr)
        return 2

    width = max((len(name) for name, _, _ in RESULTS), default=0)
    failed = [(name, detail) for name, ok, detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name:<{width}}"
        if not ok and detail:
            line += f"   <- {detail}"
        print(line)
    if failed:
        print(f"FAILED ({len(failed)} of {len(RESULTS)} checks)",
              file=sys.stderr)
        return 1
    print(f"OK ({len(RESULTS)} checks; skips marked above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
