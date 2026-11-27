#!/usr/bin/env python3
"""compose_profiles_smoke: does the Compose profile matrix still say what #1614 designed it to say?

Host-side check carried by this repository; run it as
`python3 scripts/compose_profiles_smoke.py` from the repository root.
Standard library only, plus the local `docker` CLI: this reads the
configuration each supported combination would run, it starts nothing. Exit 0
when the matrix holds, 1 when a combination contradicts it, 2 when the harness
itself could not run (no docker, an unreadable compose file).

Why the matrix is checked, and nowhere else
-------------------------------------------
`docker-compose.lightweight.yml` (#1614) moves the observability, admin and
testing tier out of the default deployment by way of Compose profiles, and the
combination that is supposed to work is not one file but a stack of them: the
production file, the development file, the prebuilt-image file, the worktree
overlay an orchestrator generates, and now this one - in an order which
matters, each merged over the previous. Three of the properties that make that
usable are invisible from any single file:

  * a dependency on a service the profile switched off is a hard configuration
    error ("service backend depends on undefined service victoria-logs"), so
    the one edge the core tier keeps into the observability tier has to carry
    `required: false` in the lightweight mode and must NOT carry it in the full
    one, where the wait is what makes the application's syslog handler attach;
  * the base file ships a `logging: driver: syslog` block aimed at the host
    loopback port of the log store; with the store switched off that sink is
    gone and the container's output disappears without any error, so the
    lightweight mode has to answer where its container logs go;
  * profiles gate what `up` creates, they never remove anything, so the tier
    which "is not part of" a stack is only truly absent while nothing created
    it - which is why the tiers are also named in the switch documentation.

Nothing else can see this either. Django's tests and Behave run inside
`docker compose run` of a single service, the frontend's tests never meet
compose, and the CI jobs name their services explicitly - so a matrix that
drifted (a new service nobody classified, a tier service left unprofiled, the
`required: false` of the lightweight mode leaking into the base file) first
shows up as a stack that does not start, on somebody's host. The sibling
`scripts/static_mounts_smoke.py` asks what is mounted in the stack,
`scripts/nginx_routing_smoke.py` which side of the edge a URL lands on; this
asks which services a given invocation actually runs.

What it checks
--------------
For every supported combination it runs
`docker compose -f ... config --no-interpolate --format json` with
`COMPOSE_PROFILES` pinned to that combination's profiles and `COMPOSE_FILE`
removed from the environment, so neither a developer's `.env` nor their shell
can flip the answer. `--no-interpolate` keeps `.env` out of the picture the
same way static_mounts_smoke.py does, which is also what lets the check run on
a CI runner without a configured deployment. Note that with that flag Compose
lists every service in `config --services` regardless of its profile, so the
active set is computed here from each service's `profiles` list rather than
asked of the CLI. Then, per combination:

  * the active set is exactly the set the documentation of the combination
    names - no tier service in the lightweight default, the whole fleet in the
    full one;
  * every service of the checkout is classified in the matrix below - an
    unclassified new service fails, which is the gate that keeps the table
    honest as the fleet grows;
  * no active service depends on an inactive one unless that edge is optional;
  * no active service ships its container log to the loopback syslog sink of an
    inactive log store, and the full mode still does ship it;
  * the always-on core keeps `restart: unless-stopped` everywhere, so no mode
    quietly makes a deployment non-persistent across a host reboot;
  * no active service lacks both an image and a build - the shape a service
    reference into a combination that does not define it produces;
  * the observers of the observability and admin tier carry the memory
    ceiling of #1622 in every lightweight combination, each inside its
    documented band, and carry none of them in the full mode - which keeps the
    uncapped contract of `docker-compose.yml` and fails a ceiling which drifted
    so far down that a healthy container of the #1613 measurement would be
    OOM-killed by it.

The same checks run offline against synthetic configurations in
`scripts/test_compose_profiles_smoke.py`, which CI does run
(`scripts/check_repo_tooling.sh`); this file is what an agent or an operator
runs against the real files before starting a stack.
"""

import json
import os
import re
import subprocess  # nosec B404 - the point of this script is to call the docker CLI
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "docker-compose.yml"
DEV = "docker-compose.dev.yml"
PREBUILT = "docker-compose.prebuilt.yml"
LITE = "docker-compose.lightweight.yml"
LOG_STORE = "victoria-logs"

# The matrix of #1614: which service belongs to which tier. Services with no
# tier are part of the core - they run in every combination. A service in the
# checkout which is in none of these lists and is not core fails the check:
# the table below is only worth anything while it stays complete.
TIERS = {
    # the log store, the two OpenTelemetry stores of #1778 and their UI
    "observability": ("victoria-logs", "victoria-metrics", "victoria-traces",
                      "grafana"),
    # operator UIs over data the application itself serves
    "admin": ("pgadmin", "flower"),
    # one-off check containers, defined by docker-compose.dev.yml
    "testing": ("pre-commit-check", "behave", "django-tests", "frontend-tests"),
}
TIER_SERVICES = frozenset(name for members in TIERS.values() for name in members)

# The memory ceilings of #1622 - and, since #1778, of the two OpenTelemetry
# stores - and the band each has to stay inside. Only the observers of the two
# optional tier are capped, and only in the
# lightweight overlay: the full deployment keeps its uncapped contract, so the
# upper half of every band is what a ceiling must not exceed there either (an
# uncapped service is answered by `None`, which is out of no band). The lower
# bound is the shipping default - below it a healthy container of the #1613
# measurement starts getting OOM-killed, which is a loud degradation of the
# observability this tier exists to provide.
CEILINGS = {
    "victoria-logs": ("256m", "512m"),
    # the two stores of #1778: no #1613 baseline exists for them, so the band
    # is the starting budget of ADR-0003 - wide enough that a store inside its
    # retention window is never killed for a normal query, narrow enough that a
    # leak or an oversized deployment is an OOM kill and a loud restart rather
    # than an unbounded charge on the host. #1780 re-measures both.
    "victoria-metrics": ("512m", "1g"),
    "victoria-traces": ("512m", "1g"),
    "grafana": ("1g", "2g"),
    "pgadmin": ("512m", "1g"),
    "flower": ("256m", "512m"),
}
MEMORY_SUFFIXES = {"": 1, "b": 1, "k": 1024, "kb": 1024, "m": 1024 ** 2,
                   "mb": 1024 ** 2, "g": 1024 ** 3, "gb": 1024 ** 3}

# The services a deployment must come back with after a host reboot on its own
# (#901). The one-off check containers are deliberately not in this list: a
# `docker compose run` container never inherits a restart policy anyway.
ALWAYS_ON = ("postgis", "redis", "docker-api", "backend", "celery-worker",
             "celery-beat", "frontend")

# The core tier of the production file: the application, its data, its broker
# and the socket proxy the status UI reads container health through.
CORE = frozenset(ALWAYS_ON)

# Every combination this repository supports, with the profiles it activates
# and the services it then runs. `defines` names the files a combination needs
# to be asked about at all: the testing tier belongs to docker-compose.dev.yml,
# so the combinations which do not layer that file do not get to activate it -
# activating it there is the one combination #1614 documents as not existing.
COMBINATIONS = (
    {
        "name": "full deployment (the documented contract)",
        "files": (BASE,),
        "profiles": (),
        "expect": frozenset(CORE) | TIER_SERVICES - frozenset(TIERS["testing"]),
    },
    {
        "name": "full development stack",
        "files": (BASE, DEV),
        "profiles": (),
        # what develop ran before #1614: everything, including the one-off
        # check containers, which `up -d` used to boot as services
        "expect": "all",
    },
    {
        "name": "lightweight core",
        "files": (BASE, LITE),
        "profiles": (),
        "expect": CORE,
    },
    {
        "name": "lightweight core + observability",
        "files": (BASE, LITE),
        "profiles": ("observability",),
        "expect": CORE | frozenset(TIERS["observability"]),
    },
    {
        "name": "lightweight core + admin",
        "files": (BASE, LITE),
        "profiles": ("admin",),
        "expect": CORE | frozenset(TIERS["admin"]),
    },
    {
        "name": "lightweight development stack",
        "files": (BASE, DEV, LITE),
        "profiles": (),
        # mapserver is not a tier: it is a runtime dependency of the
        # development stack and the exact dependency of the suites which assert
        # OGC responses, started by name where it is needed
        "expect": CORE | {"mapserver"},
    },
    {
        "name": "lightweight agent stack (prebuilt images)",
        "files": (BASE, DEV, PREBUILT, LITE),
        "profiles": (),
        "expect": CORE | {"mapserver"},
    },
    {
        "name": "lightweight development stack, testing tier on",
        "files": (BASE, DEV, LITE),
        "profiles": ("testing",),
        "expect": CORE | {"mapserver"} | frozenset(TIERS["testing"]),
    },
    {
        "name": "lightweight development stack, every tier on",
        "files": (BASE, DEV, LITE),
        "profiles": ("observability", "admin", "testing"),
        "expect": "all",
    },
)


class HarnessError(Exception):
    """The check could not be run at all - a missing docker, a compose file it
    refuses to read. Kept apart from a matrix violation, which is a real answer
    to the question the check asks."""


def compose_config(files, profiles, cwd=ROOT):
    """The resolved model of these compose files with these profiles active.

    The environment is pinned, not inherited: COMPOSE_PROFILES of a developer's
    `.env` would activate profiles the combination under test never asked for,
    and COMPOSE_FILE would replace the very file list being examined.
    """
    environment = dict(os.environ)
    environment.pop("COMPOSE_FILE", None)
    environment["COMPOSE_PROFILES"] = ",".join(profiles)
    command = ["docker", "compose"]
    for profile in profiles:
        command += ["--profile", profile]
    for file in files:
        command += ["-f", file]
    command += ["config", "--no-interpolate", "--format", "json"]
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 cwd=cwd, env=environment)  # nosec B603
    except FileNotFoundError:
        raise HarnessError("the docker CLI is not on PATH")
    if process.returncode != 0:
        raise HarnessError(
            f"docker {' '.join(command[1:])} exited {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        raise HarnessError(
            f"docker compose config of {' + '.join(files)} printed no parsable JSON")


def active_services(config, profiles=()):
    """The services this configuration runs: one with no profile always, one
    with a profile only when that profile is active."""
    active = set(profiles)
    return {
        name for name, service in config.get("services", {}).items()
        if not service.get("profiles")
        or active.intersection(service["profiles"])
    }


def unclassified(config):
    """Services which are neither in a tier nor in the core."""
    return sorted(
        name for name in config.get("services", {})
        if name not in TIER_SERVICES and name not in CORE | {"mapserver"})


def dangling_dependencies(config, profiles=()):
    """Edges from a service which runs to a service which does not, where the
    edge still demands it."""
    running = active_services(config, profiles)
    found = []
    for name in sorted(running):
        depends = (config["services"][name].get("depends_on") or {})
        if isinstance(depends, list):  # the short syntax: every edge required
            depends = {target: {} for target in depends}
        for target, edge in sorted(depends.items()):
            if target not in running and (edge or {}).get("required", True):
                found.append((name, target))
    return found


def blind_syslog(config, profiles=()):
    """Services shipping their container log to the loopback syslog sink while
    the log store which listens there does not run."""
    running = active_services(config, profiles)
    found = []
    for name in sorted(running):
        logging = config["services"][name].get("logging") or {}
        if logging.get("driver") != "syslog":
            continue
        address = (logging.get("options") or {}).get("syslog-address", "")
        if LOG_STORE not in running:
            found.append((name, address))
    return found


def nonpersistent(config, profiles=()):
    """Always-on core services which lost the restart policy of #901."""
    running = active_services(config, profiles)
    return sorted(
        name for name in ALWAYS_ON
        if name in running
        and config["services"][name].get("restart") != "unless-stopped")


def homeless(config, profiles=()):
    """Active services with neither an image nor a build: the shape of a
    reference into a combination which does not define them."""
    return sorted(
        name for name in active_services(config, profiles)
        if not config["services"][name].get("image")
        and not config["services"][name].get("build"))


def memory_bytes(value):
    """Bytes of a docker memory value - `1g`, `512m`, `256mb`, a plain byte
    count, or the un-interpolated `${VAR:-1g}` of `config --no-interpolate`.
    None for anything this check cannot read, which is never a pass: a ceiling
    nobody can parse is not a ceiling an operator can rely on."""
    if value is None:
        return None
    text = str(value).strip()
    default = re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*:-(.+)}", text)
    if default:
        text = default.group(1)
    number = re.fullmatch(r"(\d+)\s*([a-zA-Z]*)", text)
    if not number:
        return None
    factor = MEMORY_SUFFIXES.get(number.group(2).lower())
    if factor is None:
        return None
    return int(number.group(1)) * factor


def stray_ceilings(config, profiles=()):
    """Ceilings on a service which is not one of the observers of #1622 / #1778.

    Those observers are the only services this repository bounds anywhere;
    a `mem_limit` on anything else - the core in particular - is an unrelated
    cap nobody decided, and the same failure in both modes.
    """
    capped = {
        name for name in active_services(config, profiles)
        if config["services"][name].get("mem_limit") is not None}
    return sorted(capped - frozenset(CEILINGS))


def ceiling_problems(config, profiles=(), capped=True):
    """Ceilings of #1622 which contradict the mode they are resolved in.

    With `capped`, every active observer must carry a readable ceiling inside
    its band; without it - the full deployment of `docker-compose.yml` - every
    observer must carry none at all, because the uncapped full mode is the
    contract of that file and a `mem_limit` leaking into it is the silent
    OOM-restart of an operator UI on a loaded production host.
    """
    found = []
    running = active_services(config, profiles)
    for name in sorted(CEILINGS):
        if name not in running:
            continue
        declared = config["services"][name].get("mem_limit")
        if not capped:
            if declared is not None:
                found.append((name, declared, None, "capped in the full mode"))
            continue
        if declared is None:
            found.append((name, None, None, "uncapped"))
            continue
        size = memory_bytes(declared)
        low, high = (memory_bytes(value) for value in CEILINGS[name])
        if size is None:
            found.append((name, declared, None, "unreadable"))
        elif not low <= size <= high:
            found.append((name, declared, CEILINGS[name], "out of band"))
    return found


def check_combination(combo, config):
    """Every assertion about one resolved combination, as failure strings."""
    profiles = combo["profiles"]
    running = active_services(config, profiles)
    expected = combo["expect"]
    failures = []

    if expected == "all":
        expected = set(config.get("services", {}))
    if running != expected:
        missing = ", ".join(sorted(expected - running)) or "-"
        extra = ", ".join(sorted(running - expected)) or "-"
        failures.append(
            f"runs {len(running)} service(s), not the {len(expected)} the "
            f"combination documents (missing: {missing}; unexpected: {extra})")

    for name in unclassified(config):
        failures.append(f"service {name} is in no tier and not core")

    for name, target in dangling_dependencies(config, profiles):
        failures.append(
            f"service {name} depends on {target}, which no profile activates; "
            f"the edge needs `required: false` in this mode")

    for name, address in blind_syslog(config, profiles):
        failures.append(
            f"service {name} ships its container log to {address or 'syslog'} "
            f"while {LOG_STORE} is inactive; the sink is gone and the output "
            f"is lost without an error")

    for name in nonpersistent(config, profiles):
        failures.append(
            f"always-on service {name} no longer declares "
            f"`restart: unless-stopped`")

    for name in homeless(config, profiles):
        failures.append(f"active service {name} has neither image nor build")

    for name in stray_ceilings(config, profiles):
        failures.append(
            f"active service {name} carries a mem_limit which belongs to no "
            f"tier of #1622; only {', '.join(sorted(CEILINGS))} are bounded "
            f"anywhere in this repository")

    for name, declared, band, why in ceiling_problems(
            config, profiles, capped=LITE in combo["files"]):
        if why == "uncapped":
            failures.append(
                f"active service {name} runs without a memory ceiling in the "
                f"lightweight mode; #1622 bounds every service of the "
                f"observability and admin tier")
        elif why == "capped in the full mode":
            failures.append(
                f"service {name} carries `mem_limit: {declared}` in the full "
                f"mode; the full deployment of {BASE} stays uncapped - the "
                f"ceiling belongs to {LITE}")
        elif why == "unreadable":
            failures.append(
                f"the mem_limit of {name} is {declared!r}, which is no docker "
                f"memory value this check can verify")
        else:
            failures.append(
                f"the mem_limit of {name} is {declared!r}, outside the "
                f"documented band {band[0]}..{band[1]}")

    # The two halves of the seam #1614 exists for: the full deployment keeps
    # waiting for the log store, the lightweight mode may start without it.
    edge = ((config["services"].get("backend") or {}).get("depends_on")
            or {}).get(LOG_STORE) or {}
    if LITE not in combo["files"] and not edge.get("required", True):
        failures.append(
            f"the full mode must keep `depends_on: {LOG_STORE}` required - "
            f"the wait is what attaches the application's syslog handler")
    if LITE in combo["files"] and LOG_STORE not in running \
            and edge.get("required", True):
        failures.append(
            f"the lightweight mode must carry `required: false` on its "
            f"`depends_on: {LOG_STORE}` edge, or `up` cannot start the core")
    return failures


def main():
    if not (ROOT / BASE).is_file():
        print(f"harness: {BASE} not found - run this from a mrmap checkout",
              file=sys.stderr)
        return 2
    if not (ROOT / LITE).is_file():
        print(f"harness: {LITE} is missing; #1614 introduced it", file=sys.stderr)
        return 2

    failures = 0
    for combo in COMBINATIONS:
        label = combo["name"]
        for file in combo["files"]:
            if not (ROOT / file).is_file():
                print(f"SKIP  {label}: {file} is not in this checkout")
                break
        else:
            try:
                config = compose_config(combo["files"], combo["profiles"])
            except HarnessError as error:
                print(f"harness: {label}: {error}", file=sys.stderr)
                return 2
            problems = check_combination(combo, config)
            for problem in problems:
                failures += 1
                print(f"FAIL  {label}\n      {problem}")
            if not problems:
                print(f"OK    {label}: runs "
                      f"{' '.join(sorted(active_services(config, combo['profiles'])))}")

    if failures:
        print(f"{failures} profile matrix violation(s)")
        return 1
    print(f"{len(COMBINATIONS)} supported combination(s) agree with the matrix "
          f"of #1614")
    return 0


if __name__ == "__main__":
    sys.exit(main())
