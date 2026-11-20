#!/usr/bin/env python3
"""Offline checks that Redis runtime memory stays bounded (#1618).

One Redis instance is the broker of the celery fleet, the result backend of its
chords and the Django cache. Without ``maxmemory`` the process grows until the
kernel OOM-kills it and the broker dies with it; with an ``allkeys-*`` policy
Redis instead evicts the broker's own queue keys to make room and loses queued
tasks without an error. Both failures were open as of #1618, and nothing
checked either: CI does not look at the compose files (its QA container binds
only ``./backend``), and the validator retired by #1529 took the last
container-pinned guard with it.

What this pins, without starting a container:

  policy    ``docker/redis/redis.conf`` names ``volatile-lru`` and is not empty
            — the empty file was the bug this issue was opened for
  compose   the ``redis`` service of ``docker-compose.yml`` passes
            ``--maxmemory`` from ``${REDIS_MAXMEMORY:-...}`` and mounts that
            file at the path its command loads it from, read-only
  neutral   no other committed compose file restates a redis command without a
            bound or reads the variable without a default
  resolve   every committed compose combination still resolves and the
            effective command of the service keeps the bound and the mount
            (skipped out loud where docker is not reachable)
  naming    ``REDIS_MAXMEMORY`` is read by the compose file only, never by
            ``settings.py``, so there is one owner of the number

Run: ``python3 scripts/test_redis_memory_bounds.py``. Stdlib only; the
resolution needs the docker CLI, and ``DOCKER``/``DOCKER_COMPOSE`` may name the
wrapper of a sandboxed host (``DOCKER='sudo docker'``). Required compose
variables are passed by this suite, so it needs no ``.env``.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPOSE_BASE = REPO / "docker-compose.yml"
REDIS_CONF = REPO / "docker" / "redis" / "redis.conf"
SETTINGS = REPO / "backend" / "MrMap" / "settings.py"

# Where the image expects a config file and where redis-server reads CLI args.
CONF_TARGET = "/usr/local/etc/redis/redis.conf"

# Combinations which are committed and expected to resolve.
# docker-compose.vscode.yml is not listed: it did not resolve before #1618
# either ("invalid reference format"), it is not on a documented run path, and
# its removal belongs to the vscode cleanup — a permanent red here would bury
# the redis verdict under a failure which names a different issue.
# Only combinations which are documented: the prebuilt files are layered on top
# of docker-compose.dev.yml (AGENTS.md), and alone they reset a build section
# which the base file needs, so they are not a runnable configuration.
COMPOSE_COMBINATIONS = [
    ["docker-compose.yml"],
    ["docker-compose.yml", "docker-compose.lightweight.yml"],
    ["docker-compose.yml", "docker-compose.dev.yml"],
    ["docker-compose.yml", "docker-compose.dev.yml", "docker-compose.lightweight.yml"],
    ["docker-compose.yml", "docker-compose.dev.yml", "docker-compose.prebuilt.yml"],
    ["docker-compose.yml", "docker-compose.dev.yml",
     "docker-compose.prebuilt-frontend.yml"],
    [
        "docker-compose.yml",
        "docker-compose.dev.yml",
        "docker-compose.prebuilt.yml",
        "docker-compose.prebuilt-frontend.yml",
        "docker-compose.lightweight.yml",
    ],
]

# Values for the variables the compose files mark required, so a resolution
# does not depend on a developer's .env.
STAND_IN_ENV = {
    "DB_USER": "mrmap",
    "DB_PASSWORD": "mrmap",
    "POSTGRES_DB": "mrmap",
    "DJANGO_SECRET_KEY": "not-a-secret-a-check-only-value",
    "DJANGO_ADMIN_USER": "mrmap",
    "DJANGO_ADMIN_PASSWORD": "mrmap",
    "EXTERNAL_BASE_URL": "http://localhost:8000",
    "COMPOSE_PROJECT_NAME": "mrmap-redis-bounds",
    # Referenced by the prebuilt overrides; a tag-shaped value, never pulled.
    "MRMAP_BACKEND_DEV_IMAGE": "ghcr.io/mrmap-community/mrmap-backend-dev:000000000000",
    "MRMAP_FRONTEND_DEV_IMAGE": "ghcr.io/mrmap-community/mrmap-frontend-dev:000000000000",
    "MRMAP_FRONTEND_IMAGE_FP": "000000000000",
    "MRMAP_BACKEND_DEV_FP": "000000000000",
}

# Directives this project is willing to ship for a shared broker+cache instance.
# A new one is a deliberate decision, so an unlisted directive fails until it is
# either justified here or removed.
ALLOWED_DIRECTIVES = {
    "maxmemory-policy",
    "maxmemory",
    "maxmemory-samples",
    "maxmemory-eviction-tenacity",
    "save",
    "appendonly",
    "appendfsync",
}

# Policies which may evict a key without an expiry, i.e. which may drop a
# celery queue list. Never acceptable on this instance.
UNSAFE_POLICIES = ("allkeys-lru", "allkeys-lfu", "allkeys-random", "noeviction")


class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def ok(self, name: str, detail: str = "") -> None:
        self.passed += 1
        print(f"PASS  {name}" + (f": {detail}" if detail else ""))

    def fail(self, name: str, detail: str) -> None:
        self.failed += 1
        print(f"FAIL  {name}: {detail}")

    def skip(self, name: str, detail: str) -> None:
        self.skipped += 1
        print(f"SKIP  {name}: {detail}")


def service_body(text: str, service: str) -> str:
    """The text block of one top-level service, scanned without a YAML parser."""
    out: list[str] = []
    inside = False
    opener = re.compile(rf"^  {re.escape(service)}:\s*(#.*)?$")
    for line in text.splitlines():
        if not inside and opener.match(line):
            inside = True
            out.append(line)
            continue
        if inside:
            if re.match(r"^  [^ #\s][^:]*:", line):  # next service, 2-space key
                break
            out.append(line)
    return "\n".join(out)


def check_config_file(checks: Checks) -> None:
    if not REDIS_CONF.is_file():
        checks.fail("redis-conf-present", f"{REDIS_CONF.relative_to(REPO)} is missing")
        return
    checks.ok("redis-conf-present")
    text = REDIS_CONF.read_text(encoding="utf-8")

    directives = [line.strip() for line in text.splitlines()
                  if line.strip() and not line.strip().startswith("#")]
    if not directives:
        checks.fail("redis-config-not-empty",
                    "the config ships no directive: an empty file leaves the "
                    "image default noeviction and Redis grows until it is killed")
    else:
        checks.ok("redis-config-not-empty", f"{len(directives)} directive(s)")

    policy = re.search(r"^\s*maxmemory-policy\s+(\S+)", text, re.M)
    if policy and policy.group(1) == "volatile-lru":
        checks.ok("redis-eviction-policy", "volatile-lru")
    elif policy:
        checks.fail("redis-eviction-policy",
                    f"policy is {policy.group(1)}; volatile-lru is required "
                    f"(unsafe here: {', '.join(UNSAFE_POLICIES)})")
    else:
        checks.fail("redis-eviction-policy", "no maxmemory-policy in the config file")

    unlisted = [d.split()[0] for d in directives if d.split()[0] not in ALLOWED_DIRECTIVES]
    if unlisted:
        checks.fail("redis-config-directives",
                    f"unlisted directive(s) {', '.join(unlisted)}: each must be "
                    "justified in ALLOWED_DIRECTIVES or removed")
    else:
        checks.ok("redis-config-directives", ", ".join(d.split()[0] for d in directives))


def check_base_compose(checks: Checks) -> None:
    text = COMPOSE_BASE.read_text(encoding="utf-8")
    body = service_body(text, "redis")
    if not body:
        checks.fail("redis-service-found", "no redis service in docker-compose.yml")
        return
    checks.ok("redis-service-found")

    line = re.search(r"^\s*command:\s*(.*)$", body, re.M)
    command = line.group(1) if line else ""
    if "--maxmemory" not in command:
        checks.fail("redis-maxmemory-arg",
                    f"the redis command passes no --maxmemory: {command.strip()!r}")
    else:
        checks.ok("redis-maxmemory-arg")

    if re.search(r"\$\{REDIS_MAXMEMORY:-[^\}]+\}", command):
        checks.ok("redis-maxmemory-defaulted", "REDIS_MAXMEMORY has a default")
    elif "REDIS_MAXMEMORY" in command:
        checks.fail("redis-maxmemory-defaulted",
                    "REDIS_MAXMEMORY is read without a :- default: a deployment "
                    "without the variable yields an empty argument and an "
                    "unbounded Redis")
    else:
        checks.fail("redis-maxmemory-defaulted", "command never reads REDIS_MAXMEMORY")

    # An unquoted substitution splits into several arguments and redis-server
    # aborts with "Unknown argument"; inside the sh -c string of a YAML list the
    # quote arrives here already escaped for the shell.
    after_flag = command.split("--maxmemory", 1)[1].lstrip() if "--maxmemory" in command else ""
    quoted = (r'\"${REDIS_MAXMEMORY', '"${REDIS_MAXMEMORY', "'${REDIS_MAXMEMORY")
    if after_flag.startswith(quoted):
        checks.ok("redis-maxmemory-quoted")
    else:
        checks.fail("redis-maxmemory-quoted",
                    "--maxmemory must receive its value as one quoted argument: "
                    f"{command.strip()!r}")

    if CONF_TARGET not in body:
        checks.fail("redis-conf-mounted",
                    f"redis service neither mounts nor loads anything at {CONF_TARGET}")
        return
    checks.ok("redis-conf-mounted", CONF_TARGET)

    # The `target:` line of the mount, not the command line which names the
    # same path: read_only belongs to the mount entry next to it.
    lines = body.splitlines()
    target_at = next(i for i, line in enumerate(lines)
                     if line.strip().startswith("target:") and CONF_TARGET in line)
    window = "\n".join(lines[target_at:target_at + 4])
    if "read_only" not in window:
        checks.fail("redis-conf-read-only",
                    "the redis.conf mount is writable: a container could rewrite "
                    "the eviction policy it is bounded by")
    else:
        checks.ok("redis-conf-read-only")


def check_other_compose_files(checks: Checks) -> None:
    offenders = []
    for path in sorted(COMPOSE_BASE.parent.glob("docker-compose*.yml")):
        if path == COMPOSE_BASE:
            continue
        body = service_body(path.read_text(encoding="utf-8"), "redis")
        if not body:
            continue
        if re.search(r"^\s*command:", body, re.M) and "--maxmemory" not in body:
            offenders.append(f"{path.name} restates the redis command without a bound")
        if "REDIS_MAXMEMORY" in body and not re.search(r"REDIS_MAXMEMORY:-", body):
            offenders.append(f"{path.name} reads REDIS_MAXMEMORY without a default")
        if re.search(r"^\s*mem_limit|^\s*deploy:", body, re.M) and "--maxmemory" not in body:
            offenders.append(f"{path.name} caps the container without bounding maxmemory")
    if offenders:
        for offender in offenders:
            checks.fail("other-compose-files-neutral", offender)
    else:
        checks.ok("other-compose-files-neutral")


def check_settings(checks: Checks) -> None:
    if not SETTINGS.is_file():
        checks.skip("settings-single-owner", "backend/MrMap/settings.py not found")
        return
    settings_text = SETTINGS.read_text(encoding="utf-8")
    if re.search(r"(os\.environ|getenv)[^\n]*REDIS_MAXMEMORY"
                 r"|REDIS_MAXMEMORY[^\n]*(os\.environ|getenv)", settings_text):
        checks.fail("settings-single-owner",
                    "settings.py reads REDIS_MAXMEMORY, so two places would know "
                    "a bound the redis service may override elsewhere")
    else:
        checks.ok("settings-single-owner")


def docker_prefix() -> list[str]:
    wrapper = os.environ.get("DOCKER_COMPOSE")
    if wrapper:
        return shlex.split(wrapper)
    docker = os.environ.get("DOCKER", "docker")
    return shlex.split(docker)


def run_or_missing(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    """A missing executable answers like a failing one, not like a traceback."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=180, **kwargs)
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(argv, 127, "", str(error))


def check_resolution(checks: Checks) -> None:
    prefix = docker_prefix()
    cli = prefix + ["compose"]
    probe = run_or_missing(prefix + ["version"])
    if probe.returncode != 0:
        checks.skip("compose-resolution",
                    f"no reachable docker daemon for {' '.join(prefix)} "
                    "(set DOCKER='sudo docker' on a sandboxed host)")
        return

    # A temp --env-file, not the process environment: sudo's default policy is
    # env_reset, so variables exported for `sudo docker` are dropped before
    # compose sees them and every required variable then fails interpolation.
    env_file = tempfile.NamedTemporaryFile("w", suffix=".env", delete=False,
                                           encoding="utf-8")
    for combination in COMPOSE_COMBINATIONS:
        label = "+".join(Path(name).stem.replace("docker-compose", "").strip(".") or "base"
                         for name in combination)
        missing = [n for n in combination if not (REPO / n).is_file()]
        if missing:
            checks.skip(f"resolution[{label}]", f"missing {missing}")
            continue
        # Required variables are discovered per combination rather than
        # enumerated: a compose file which starts to require another one should
        # not make this suite red, since a stand-in value is all a redis check
        # needs in order to reach the resolution.
        required = set()
        for name in combination:
            required.update(re.findall(
                r"\$\{([A-Za-z_][A-Za-z0-9_]*):\?",
                (REPO / name).read_text(encoding="utf-8")))
        def stand_in(name: str) -> str:
            # A port-typed variable has to be a number or compose fails with
            # "invalid hostPort" before the redis service is ever inspected.
            if name.endswith("_PORT"):
                return "16379"
            return "smoke-test-value"

        values = {**STAND_IN_ENV, **{name: stand_in(name) for name in required
                                    if name not in STAND_IN_ENV}}
        with open(env_file.name, "w", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"{key}={value}\n")

        argv = cli + ["--env-file", env_file.name,
                      "-p", STAND_IN_ENV["COMPOSE_PROJECT_NAME"]]
        for name in combination:
            argv += ["-f", name]
        argv += ["config", "--format", "json"]
        proc = run_or_missing(argv, cwd=str(REPO))
        if proc.returncode != 0:
            tail = proc.stderr.strip().splitlines()
            checks.fail(f"resolution[{label}]", (tail[-1] if tail else "compose config failed"))
            continue
        try:
            resolved = json.loads(proc.stdout)
        except json.JSONDecodeError:
            checks.fail(f"resolution[{label}]", "compose config printed no JSON")
            continue
        redis = resolved.get("services", {}).get("redis")
        if not redis:
            checks.skip(f"resolution[{label}]", "combination answers no redis service")
            continue

        # Compose answers a list for the sh -c form, where the flag sits inside
        # one shell string. Splitting each element into shell tokens gives one
        # view for both spellings, which is what the container actually runs.
        command = redis.get("command")
        elements = command if isinstance(command, list) else [str(command or "")]
        tokens: list[str] = []
        for element in elements:
            try:
                tokens.extend(shlex.split(element))
            except ValueError:
                tokens.append(element)
        text = " ".join(tokens)
        hits = [i for i, token in enumerate(tokens) if token == "--maxmemory"]
        if not hits:
            checks.fail(f"resolution-bound[{label}]",
                        f"effective command lost the bound: {text!r}")
        elif len(hits) > 1:
            checks.fail(f"resolution-bound[{label}]", "--maxmemory given twice")
        else:
            value = tokens[hits[0] + 1] if hits[0] + 1 < len(tokens) else ""
            if re.fullmatch(r"\d+[bkBKmMGg]?[bB]?", value):
                checks.ok(f"resolution-bound[{label}]", value)
            else:
                checks.fail(f"resolution-bound[{label}]",
                            f"--maxmemory value {value!r} is not a byte spec; "
                            "an empty one leaves Redis unbounded")
        if CONF_TARGET not in text:
            checks.fail(f"resolution-policy-loaded[{label}]",
                        f"the effective command does not load {CONF_TARGET}, "
                        "so the eviction policy of the config file is never read")
        else:
            checks.ok(f"resolution-policy-loaded[{label}]")

        volumes = json.dumps(redis.get("volumes", []))
        if CONF_TARGET not in volumes:
            checks.fail(f"resolution-mount[{label}]",
                        f"{CONF_TARGET} no longer mounted, the policy is not read")
            continue
        mount_entries = [v for v in (redis.get("volumes") or [])
                         if isinstance(v, dict) and CONF_TARGET in str(v.get("target", ""))]
        if mount_entries and not all(m.get("read_only") for m in mount_entries):
            checks.fail(f"resolution-mount[{label}]", "effective redis.conf mount is writable")
        else:
            checks.ok(f"resolution-mount[{label}]")
    os.unlink(env_file.name)


def main() -> int:
    checks = Checks()
    if not COMPOSE_BASE.is_file():
        print(f"FAIL  setup: {COMPOSE_BASE} not found", file=sys.stderr)
        return 2
    check_config_file(checks)
    check_base_compose(checks)
    check_other_compose_files(checks)
    check_settings(checks)
    check_resolution(checks)
    print()
    print(f"redis memory bounds: {checks.passed} passed, {checks.failed} failed, "
          f"{checks.skipped} skipped")
    return 1 if checks.failed else 0


if __name__ == "__main__":
    sys.exit(main())
