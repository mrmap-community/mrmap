#!/usr/bin/env python3
"""observability_bench - the matched measurement protocol of the legacy baseline.

Host-side tool of the checkout (issue #1777, epic #1775, ADR-0003), like
``scripts/stack_memory_profile`` and ``scripts/http_process_bench.py`` which it
drives: it adds no new kind of measurement, it runs the ones which already
exist in the order which makes them comparable. Stdlib only, and it imports
nothing from ``backend/``, so it runs on a host which has none of the
application's dependencies installed.

What the issue owes #1780 before any OTel arm may be measured is a pair of
matched readings of the same work (ADR-0003: "matched repeated post-#1387
workloads, warmup and jitter/confidence")::

    diagnostics-off reference      vs.      shipped legacy detector/profiler

The two arms differ ONLY in the opt-in knobs of the technical observability
which shipped first, so their difference IS the overhead answer; everything
else - compose project shape, seeded workload, warmup, repetitions, sampler -
is identical, because both come from the same protocol block of the same file.
The arms and the cells are data (``--arms-file``, default
``docs/source/development/evidence/observability-1777-arms.json``), so a run is
named by that file plus its digest rather than by remembered shell history, and
a reviewer can read exactly what "shipped legacy" meant.

Two kinds of cell, because the shipped tooling of the work differs:

``celery``
    ``scripts/task_perf_runner.sh`` of #1396/#1395 over one task family:
    active and end-to-end p50/p95/p99, throughput, outcomes, SQL statement
    counts and the per-arm detectors of #1395. The arm's ``celery_env`` entries
    carry the knobs of the profiler of #1389, the performance recorder of
    #1391, the exporter of #1392 and the capacity telemetry of #1401 into the
    container which does the work, and they are archived verbatim next to the
    records so a reader can see what the arm turned on.
``http``
    ``scripts/http_process_bench.py`` ``wait-ready`` + ``warmup`` + ``load``
    against the web tier of a production-shape stack: latency p50/p95/p99,
    requests per second, the cheap peer of #1032, and - for a cell with
    ``websocket_count`` - held authenticated websockets beside the load. The
    reference arm additionally boots the web tier with
    ``--legacy-off-settings-module``, which drops
    ``system.logging.middleware.LogSlowRequestsMiddleware`` out of the
    middleware chain: that middleware is the legacy HTTP detector, and no knob
    turns its per-request SQL capture off, so a "diagnostics off" reading of
    the web tier has to say so in its own definition.

A third column belongs to every cell rather than being a cell of its own: the
size and file count of the directories the observability chain writes
(slow-request dumps, security proxy logs, harvest dumps) are inventoried inside
the container before and after the phase, and the delta is the "storage" of the
issue.

Every phase is bracketed by ``scripts/stack_memory_profile sample`` of the
compose project, which supplies the CPU (``cpu.stat`` deltas), the cgroup
current/p50/peak and committed peak, and PSS of the sampled processes - the
``PSS / private / cgroup peak`` of the issue, read from the kernel's own
accounting instead of from a re-implementation of it.

Query counts per request are deliberately NOT measured for HTTP: no existing
tool counts them for a WSGI request, and putting a counting middleware in front
of the baseline would instrument the very build #1780 is meant to compare
against. The Celery records carry their statement counts already (#1395). The
limitation is stated on the baseline page rather than engineered away.

Usage::

    scripts/observability_bench.py plan     [--arm A] [--cell C] [--profile ...]
    scripts/observability_bench.py run      --arm A [--cell C]
                                            [--profile production|dev]
                                            [--repeats N] [--seed N]
                                            [--out DIR] [--artifacts DIR]
                                            [--stack-tree DIR] [--no-sample]
                                            [--legacy-off-settings-module M]
    scripts/observability_bench.py report   --in DIR
    scripts/observability_bench.py baseline --in DIR [--budget-file F]
    scripts/observability_bench.py verify   --in DIR
    scripts/observability_bench.py cleanup  --project P

The safety promise is the one AGENTS.md states: the run owns its compose
project and refuses to touch containers it did not create, it writes only under
``--out`` and ``--artifacts``, and it removes what it created inside the
checkout at the end of a run - no untracked build output survives it.
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ARMS_FILE = os.path.join(
    "docs", "source", "development", "evidence", "observability-1777-arms.json")
DEFAULT_BUDGET_FILE = os.path.join(
    "docs", "source", "development", "evidence", "observability-1777-budgets.json")

# the disposable credentials of the CI jobs (quality-assurance.yml,
# task-performance.yml): compose interpolates every service of the stack, so
# these also cover the services a run never starts. No deployment secret.
REQUIRED_ENV = (
    "COMPOSE_PROJECT_NAME", "EXTERNAL_BASE_URL", "EXTERNAL_PORT",
    "EXTERNAL_SCHEME", "DB_USER", "DB_PASSWORD", "DJANGO_ADMIN_USER",
    "DJANGO_ADMIN_PASSWORD", "DJANGO_SECRET_KEY", "REDIS_PASSWORD",
    "GRAFANA_ADMIN_USER", "GRAFANA_ADMIN_PASSWORD", "PGADMIN_USER",
    "PGADMIN_PASSWORD")

RUN_SCHEMA = "mrmap.observability-bench.v1"
BASELINE_SCHEMA = "mrmap.observability-baseline.v1"
PROJECT_PREFIX = "mrmap-"

#: the environment variables of the legacy technical observability which an arm
#: may name; ``verify`` refuses an arm which enables a knob outside its own
#: definition, so this list is what "shipped legacy" is allowed to mean.
LEGACY_TASK_KNOBS = (
    "MRMAP_TASK_PROFILING", "MRMAP_TASK_PROFILING_TASKS",
    "MRMAP_TASK_PROFILING_SAMPLE_RATE", "MRMAP_TASK_PROFILING_MEMORY_MIB",
    "MRMAP_TASK_PROFILING_MEMORY_SAMPLE_SECONDS",
    "MRMAP_TASK_PERFORMANCE", "MRMAP_TASK_PERFORMANCE_EXPORT",
    "MRMAP_TASK_PERFORMANCE_EXPORT_WINDOW_MINUTES",
    "MRMAP_TASK_PERFORMANCE_EXPORT_MAX_BUCKETS",
    "MRMAP_TASK_PERFORMANCE_POLICIES",
    "MRMAP_CAPACITY_TELEMETRY", "MRMAP_CAPACITY_TELEMETRY_COLLECT_ANY_PROCESS")


class BenchError(Exception):
    """A refusal which names the input at fault."""


def say(message):
    print("observability_bench: %s" % message, flush=True)


# ---------------------------------------------------------------------------
# the arms file
# ---------------------------------------------------------------------------
def load_json(path, what):
    try:
        with open(path) as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise BenchError("no %s at %s" % (what, path))
    except ValueError as error:
        raise BenchError("%s %s is not JSON (%s)" % (what, path, error))


def digest_of(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_arms(path):
    """Read and check the protocol file.

    Checked at read time rather than at use time: an arms file with a typo in a
    cell kind would otherwise fail halfway through a long measurement, after
    the expensive part of the run.
    """
    data = load_json(path, "arms file")
    for key in ("protocol", "arms", "cells"):
        if key not in data:
            raise BenchError("arms file %s carries no %r" % (path, key))
    protocol = data["protocol"]
    for key in ("compose_project", "repeats", "requests", "concurrency",
                "warmup_requests", "seed", "idle_sample_seconds", "peer_endpoint",
                "compose_files"):
        if key not in protocol:
            raise BenchError("arms file %s: protocol carries no %r" % (path, key))
    for profile in ("production", "dev"):
        if not protocol["compose_files"].get(profile):
            raise BenchError("arms file %s: protocol names no %s compose files"
                             % (path, profile))
    names = [arm.get("name") for arm in data["arms"]]
    if len(set(names)) != len(names) or None in names:
        raise BenchError("arms file %s names an arm twice or has an unnamed one"
                         % path)
    cells = [cell.get("name") for cell in data["cells"]]
    if len(set(cells)) != len(cells) or None in cells:
        raise BenchError("arms file %s names a cell twice or has an unnamed one"
                         % path)
    for arm in data["arms"]:
        unknown = sorted(set(arm.get("celery_env") or {}) - set(LEGACY_TASK_KNOBS))
        if unknown:
            raise BenchError("arms file %s: arm %r names %s, which is not one of"
                             " the shipped legacy task knobs; an arm may only turn"
                             " on what actually shipped (see LEGACY_TASK_KNOBS)"
                             % (path, arm.get("name"), ", ".join(unknown)))
    for cell in data["cells"]:
        if cell.get("kind") not in ("celery", "http"):
            raise BenchError("arms file %s: cell %r has kind %r, wants celery or"
                             " http" % (path, cell.get("name"), cell.get("kind")))
        if cell["kind"] == "celery":
            for key in ("family", "out_dir"):
                if not cell.get(key):
                    raise BenchError("arms file %s: celery cell %r names no %s"
                                     % (path, cell["name"], key))
        if cell["kind"] == "http":
            for key in ("base_url", "endpoints", "services"):
                if not cell.get(key):
                    raise BenchError("arms file %s: http cell %r names no %s"
                                     % (path, cell["name"], key))
    return data


def select_cells(data, only_cell=None, only_kind=None):
    cells = [cell for cell in data["cells"]
             if (not only_cell or cell["name"] == only_cell)
             and (not only_kind or cell["kind"] == only_kind)]
    if not cells:
        raise BenchError("no cell selected from the arms file%s%s"
                         % (" --cell %s" % only_cell if only_cell else "",
                            " --kind %s" % only_kind if only_kind else ""))
    return cells


def arm_of(data, name):
    for arm in data["arms"]:
        if arm.get("name") == name:
            return arm
    raise BenchError("no arm %r in the arms file (known: %s)"
                     % (name, ", ".join(sorted(str(arm.get("name"))
                                               for arm in data["arms"]))))


# ---------------------------------------------------------------------------
# environment, ownership, the stack
# ---------------------------------------------------------------------------
def read_env_file(path):
    """The ``KEY=VALUE`` pairs of a compose ``.env``, without executing it."""
    values = {}
    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return values


def prepare_environment(stack_tree, project):
    """Guarantee every variable compose interpolates, or refuse.

    Values already in the environment win - that is how a run overrides one
    knob - otherwise the deployment file of the stack tree fills the gaps, the
    way ``docker compose`` itself would. Nothing is invented: a name which is
    in neither is a refusal, because an empty credential builds a stack which
    cannot boot, and the run would read that as a measurement problem.

    ``COMPOSE_PROJECT_NAME`` is the one name which is *set* rather than
    defaulted: the stack tree carries its own deployment file for the
    developer's stack, and a helper the run calls - the workload runner of
    the measured tree composes without -p - would otherwise bring up and
    measure that other stack, whose containers are not the arm.
    """
    file_values = {}
    env_file = os.path.join(stack_tree, ".env")
    if os.path.isfile(env_file):
        file_values = read_env_file(env_file)
    missing = [name for name in REQUIRED_ENV
               if not os.environ.get(name) and name not in file_values]
    if missing:
        raise BenchError("compose needs %s and neither the environment nor %s"
                         " carries them" % (", ".join(missing), env_file))
    for name in REQUIRED_ENV:
        os.environ.setdefault(name, file_values.get(name, ""))
    os.environ["COMPOSE_PROJECT_NAME"] = project


def run(command, check=True, cwd=None, env=None, timeout=3600):
    try:
        completed = subprocess.run([str(part) for part in command], cwd=cwd,
                                   env=env, timeout=timeout, capture_output=True,
                                   text=True)
    except (OSError, subprocess.SubprocessError) as error:
        if check:
            raise BenchError("%s failed (%s)" % (" ".join(map(str, command)), error))
        return None
    if check and completed.returncode != 0:
        raise BenchError("%s exited %s\n%s"
                         % (" ".join(map(str, command)), completed.returncode,
                            (completed.stderr or completed.stdout)[-2000:]))
    return completed


def cell_base(args, cell):
    """The address an http cell is loaded against.

    ``--host-port`` moves both the published port and the address the load
    goes to, so the two cannot disagree - a run which published on a free
    pair but kept loading 8001 would measure whatever else owns it.
    """
    if args.host_port:
        return "http://127.0.0.1:%d" % args.host_port
    return args.base_url or cell["base_url"]


def listening(url):
    """What answers on the host port of ``url``: None, or a short description.

    The load of an http cell goes to a host port, and only one publisher can
    hold one: if a foreign server answers there, the run measures *that*
    server and calls it an arm. Asking costs one request, and a wrong
    measurement costs a whole baseline, so an occupied address is a refusal.
    """
    try:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=3) as response:
            return "HTTP %s%s" % (response.status,
                                  response.headers.get("Server", ""))
    except urllib.error.HTTPError as error:
        # a 4xx or 5xx still proves a server answers - it just does not like
        # this path, which is the normal case for an unauthenticated probe
        return "HTTP %s%s" % (error.code, error.headers.get("Server", "")
                              if error.headers else "")
    except (urllib.error.URLError, OSError):
        return None


def owned_or_die(project):
    """Refuse a project whose containers this run did not create (AGENTS.md)."""
    listed = run(["docker", "ps", "-aq", "--filter",
                  "label=com.docker.compose.project=%s" % project], check=False)
    if listed is None or listed.returncode != 0:
        raise BenchError("cannot ask docker about project %s (%s)"
                         % (project, (listed.stderr or "").strip() if listed
                            else "docker is not usable here"))
    if listed.stdout.split():
        raise BenchError(
            "compose project %s already has %d container(s); this run owns its"
            " project and refuses to measure someone else's stack. Choose another"
            " COMPOSE_PROJECT_NAME, or run: scripts/observability_bench.py cleanup"
            " --project %s" % (project, len(listed.stdout.split()), project))


class Stack:
    """The compose project of one run: bring it up, ask it, take it away."""

    def __init__(self, tree, project, files, arm, legacy_off_module="",
                 host_port=None):
        self.tree = tree
        self.project = project
        self.files = list(files)
        self.arm = arm
        self.legacy_off_module = legacy_off_module
        self.host_port = host_port
        self.override = None
        self._token = None

    def websocket_token(self, bench, base, log_write, protocol, cell_name):
        """One knox token for the whole run, fetched on the first need.

        knox caps the live tokens of one user at five (#1450), so an arm which
        logged in per phase exhausted them and the load died on the cap before
        it measured anything - the reading has to reuse a token the way the
        #1617 runbook says.
        """
        if self._token is not None:
            return self._token
        result = run([sys.executable, bench, "token", "--base-url", base,
                      "--credentials", protocol["websocket_credentials"]],
                     cwd=REPO, check=False, timeout=120)
        if result is None or result.returncode != 0:
            log_write((result.stderr if result else "token unavailable") or "")
            raise BenchError("the websockets of %s need a knox token and the"
                             " login of %s failed"
                             % (cell_name, protocol["websocket_credentials"]))
        self._token = result.stdout.strip().splitlines()[-1].strip()
        return self._token

    def write_override(self, directory):
        """The arm's environment as a generated compose file, never committed.

        An arm which edited the shipped stack would be an arm nobody else can
        reproduce; keeping the difference in one generated file also means
        ``docker compose config`` of the run shows exactly what the arm changed.
        """
        services = {}
        for service, values in (self.arm.get("services") or {}).items():
            if values:
                services[service] = dict(values)
        # docker-compose.dev.yml pins container_name: backend-dev, so a second
        # stack on one host silently reuses the first stack's container and the
        # run measures an arm it did not start. The shipped
        # docker-compose.prebuilt.yml resets that name; this does the same.
        backend = {"container_name": "%s-backend" % self.project}
        if self.host_port:
            # the shipped dev file publishes 0.0.0.0:8001 and the edge routes
            # /ws to 8002, and a host port can only be held by one publisher -
            # so a run pointed at a free pair publishes its own web tier there
            # instead of failing to come up beside whatever else owns 8001
            backend["ports"] = ["0.0.0.0:%d:8001" % self.host_port,
                                "0.0.0.0:%d:8002" % (self.host_port + 1)]
        environment = {}
        if self.legacy_off_module:
            # under environment, not as a bare service key: compose validates a
            # service against its schema, and a container variable belongs in
            # the environment map - which an override merges into what the
            # shipped file already passes rather than replacing it
            environment["DJANGO_SETTINGS_MODULE"] = self.legacy_off_module
        if self.arm.get("backend_command"):
            backend["command"] = self.arm["backend_command"]
        if environment:
            backend["environment"] = environment
        if backend:
            services["backend"] = dict(services.get("backend", {}), **backend)
        lines = ["# generated by scripts/observability_bench.py - the service",
                 "# overrides of arm %r. The arms file is the input and this file"
                 % self.arm["name"],
                 "# is derived from it, which is what makes the run reproducible.",
                 "services:"]
        if not services:
            lines.append("  {}")
        for service in sorted(services):
            lines.append("  %s:" % service)
            for key, value in sorted(services[service].items()):
                if isinstance(value, dict):
                    # environment merges: an override which named the whole map
                    # would drop every variable the shipped file passes
                    lines.append("    %s:" % key)
                    lines.extend("      %s: %s" % (name, json.dumps(str(item)))
                                 for name, item in sorted(value.items()))
                elif isinstance(value, list):
                    lines.append("    %s:" % key)
                    lines.extend("      - %s" % json.dumps(item) for item in value)
                else:
                    lines.append("    %s: %s" % (key, json.dumps(str(value))))
        os.makedirs(directory, exist_ok=True)
        path = os.path.join(directory, "override-%s.yml" % self.arm["name"])
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")
        self.override = path
        return path

    def check_project(self):
        """Ask compose which project the run's own files resolve to.

        ``-p`` makes the intent explicit, but a docker CLI which does not pass
        the environment through (a sudo wrapper, for one) and a stack tree
        whose ``.env`` names the developer's project both make compose answer
        with someone else's project, and the run would then measure and remove
        that stack. One ``config`` call is cheap next to the measurement.
        """
        command = ["docker", "compose"]
        for path in self.files + ([self.override] if self.override else []):
            command += ["-f", path]
        completed = run(command + ["-p", self.project, "config", "--format",
                                   "json"], check=False, cwd=self.tree,
                        timeout=180)
        if completed is None or completed.returncode != 0:
            raise BenchError("compose will not resolve the files of this run (%s)"
                             % ((completed.stderr if completed else "docker"
                                 " unavailable") or "")[:400])
        try:
            resolved = json.loads(completed.stdout).get("name")
        except ValueError:
            raise BenchError("compose did not answer the project question in JSON")
        if resolved != self.project:
            raise BenchError("compose resolves the project to %r, not the %r this"
                             " run owns: the deployment file of %s names another"
                             " stack, and the run would measure and remove that"
                             " one instead" % (resolved, self.project, self.tree))

    def compose(self, *args, check=True, timeout=1800):
        command = ["docker", "compose"]
        for path in self.files + ([self.override] if self.override else []):
            command += ["-f", path]
        command += ["-p", self.project] + [str(arg) for arg in args]
        return run(command, check=check, cwd=self.tree, timeout=timeout)

    def up(self, services):
        self.compose("up", "-d", *services)

    def stop(self, services):
        self.compose("stop", *services, check=False)

    def down(self):
        self.compose("down", "--remove-orphans", check=False)

    def inventory(self, service, paths):
        """Kilobytes and file counts below ``paths``, asked inside ``service``.

        The storage column of the report. Measured in the container which owns
        the volumes, because counting a bind mount from the host would count a
        different directory than the one the application writes into.
        """
        script = ";".join(
            'printf "%%s\\t%%s\\t%%s\\n" "%s" '
            '"$(du -sk %s 2>/dev/null | cut -f1)" '
            '"$(find %s -type f 2>/dev/null | wc -l)"' % (path, path, path)
            for path in paths)
        result = self.compose("exec", "-T", service, "sh", "-c", script, check=False)
        if result is None or result.returncode != 0:
            return {"available": False,
                    "stderr": (result.stderr if result else "docker unavailable")}
        rows = {}
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                rows[parts[0]] = {"kilobytes": _int(parts[1]) or 0,
                                  "files": _int(parts[2]) or 0}
        return {"available": True, "paths": rows}


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _belongs_to(name, arm_name):
    return name.startswith(tuple(
        "%s-%s" % (prefix, arm_name) for prefix in
        ("taskperf", "http", "memory", "storage", "celery-env", "log", "override")))


# ---------------------------------------------------------------------------
# the sampler
# ---------------------------------------------------------------------------
def sample(project, out, phase, tree, during=None, duration=None):
    """One phase of scripts/stack_memory_profile, before/around/beside the work."""
    command = [sys.executable, os.path.join(REPO, "scripts", "stack_memory_profile"),
               "sample", "--project", project, "--phase", phase,
               "--proc-interval", "5", "--pss", "--out", out]
    if during:
        command += ["--during", during]
    else:
        command += ["--duration", str(duration)]
    result = run(command, check=False, cwd=tree, timeout=3000)
    if result is None or result.returncode != 0:
        say("  sampler %s: %s"
            % (phase, ((result.stderr.strip() if result else "") or "unavailable")))
        return False
    return True


# ---------------------------------------------------------------------------
# plan
# ---------------------------------------------------------------------------
def plan_lines(data, arm, cell, profile):
    """The exact command sequence of one cell.

    What ``plan`` prints is what ``run`` executes, so the plan can never become
    a second, weaker definition of the run.
    """
    protocol = data["protocol"]
    project = protocol["compose_project"]
    files = " ".join("-f %s" % path for path in protocol["compose_files"][profile])
    lines = []
    if cell["kind"] == "celery":
        knobs = " ".join("%s=%s" % pair
                         for pair in sorted((arm.get("celery_env") or {}).items()))
        lines.append("%s MRMAP_TASK_PERF_REPEATS=%s MRMAP_TASK_PERF_SEED=%s"
                     " COMPOSE_PROJECT_NAME=%s scripts/task_perf_runner.sh --family"
                     " %s --repeats %s --seed %s --mode warn --out %s"
                     % (knobs or "<no arm knobs>", protocol["repeats"],
                        protocol["seed"], project, cell["family"],
                        protocol["repeats"], protocol["seed"], cell["out_dir"]))
        lines.append("python3 scripts/task_perf_bench.py load --arm %s --family"
                     " %s --repeats %s --seed %s --fixture <fixture.json> --out"
                     " <out>/taskperf-%s-%s.jsonl"
                     % (arm["name"], cell["name"], protocol["repeats"],
                        protocol["seed"], arm["name"], cell["name"]))
    else:
        endpoints = " ".join("--endpoint %s" % endpoint for endpoint
                             in cell["endpoints"])
        lines.append("docker compose %s -p %s up -d %s"
                     % (files, project, " ".join(cell["services"])))
        lines.append("python3 scripts/http_process_bench.py wait-ready --arm %s"
                     " --base-url %s --out <out>/http-%s-%s.jsonl"
                     % (arm["name"], cell["base_url"], arm["name"], cell["name"]))
        lines.append("python3 scripts/http_process_bench.py load --arm %s --phase"
                     " warmup --base-url %s %s --requests %s --concurrency %s"
                     " --out <out>/http-%s-%s.jsonl"
                     % (arm["name"], cell["base_url"], endpoints,
                        protocol["warmup_requests"], protocol["concurrency"],
                        arm["name"], cell["name"]))
        load = ("python3 scripts/http_process_bench.py load --arm %s --phase load"
                " --base-url %s %s --requests %s --concurrency %s --peer-endpoint"
                " %s"
                % (arm["name"], cell["base_url"], endpoints,
                   protocol["requests"] * protocol["repeats"],
                   protocol["concurrency"], protocol["peer_endpoint"]))
        if cell.get("websocket_count"):
            load += (" --ws-base-url %s --ws-count %s --ws-hold %s --token <one"
                     " reused knox token from: python3 scripts/http_process_bench.py"
                     " token --base-url %s --credentials %s>"
                     % (cell.get("ws_base_url", cell["base_url"]),
                        cell["websocket_count"],
                        cell.get("websocket_hold_seconds", 30),
                        cell["base_url"], protocol["websocket_credentials"]))
        lines.append(load + " --out <out>/http-%s-%s.jsonl"
                     % (arm["name"], cell["name"]))
        if cell.get("media_paths"):
            lines.append("docker compose %s -p %s exec %s sh -c 'du -sk <path>;"
                         " find <path> -type f | wc -l'   # before and after, per"
                         " media path"
                         % (files, project, cell.get("media_service", "backend")))
    lines.append("python3 scripts/stack_memory_profile sample --project %s --phase"
                 " <phase> --pss --out <out>/memory-*.jsonl" % project)
    return lines


def cmd_plan(args, data):
    for cell in select_cells(data, args.cell, args.kind):
        subject = arm_of(data, args.arm) if args.arm else data["arms"][0]
        print("%s / %s (%s)" % (subject["name"], cell["name"], cell["kind"]))
        for line in plan_lines(data, subject, cell, args.profile):
            print("    " + line)
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------
def cmd_run(args, data):
    arm = arm_of(data, args.arm)
    cells = select_cells(data, args.cell, args.kind)
    # refused before docker is asked anything: an arm which enables something
    # that has not shipped is not a measurement of this stack
    unknown = sorted(set(arm.get("celery_env") or {}) - set(LEGACY_TASK_KNOBS))
    if unknown:
        raise BenchError("arm %r names %s, which is not one of the shipped legacy"
                         " task knobs; an arm may only turn on what actually"
                         " shipped (see LEGACY_TASK_KNOBS)"
                         % (arm["name"], ", ".join(unknown)))
    protocol = data["protocol"]
    # an explicitly empty name is a caller which means to choose one and chose
    # nothing, so it is refused rather than quietly replaced by the default:
    # the difference matters because the name is what `down` later removes.
    raw_project = os.environ.get("COMPOSE_PROJECT_NAME")
    if raw_project is not None and not raw_project.strip():
        raise BenchError("COMPOSE_PROJECT_NAME is set but empty; the run must own"
                         " what it measures and what it removes, so name the"
                         " project (expected %s*)" % PROJECT_PREFIX)
    project = raw_project or protocol["compose_project"]
    if not project.startswith(PROJECT_PREFIX):
        raise BenchError("COMPOSE_PROJECT_NAME=%s is not a project name this tool"
                         " creates (expected %s*): the run must own what it"
                         " measures and what it removes" % (project, PROJECT_PREFIX))
    if args.profile not in ("production", "dev"):
        raise BenchError("--profile wants production or dev, got %r" % args.profile)
    if arm.get("requires_sampler") and not args.sample:
        raise BenchError("--no-sample with arm %r cannot answer the storage"
                         " question: the dumps and the profile rows are the effect"
                         " being measured" % arm["name"])
    # an arm which boots without the legacy detector names its own settings
    # module, so a protocol run is reproducible without a command-line flag;
    # the flag overrides it for whoever wants to see what the removal is worth.
    args.legacy_off_settings_module = (
        args.legacy_off_settings_module
        or arm.get("legacy_off_settings_module") or "")
    if arm.get("needs_legacy_off_module") and not args.legacy_off_settings_module:
        raise BenchError("arm %r boots the web tier without the legacy slow-request"
                         " middleware, which needs --legacy-off-settings-module"
                         " <importable module name> (or"
                         " legacy_off_settings_module in the arm definition)"
                         % arm["name"])
    stack_tree = os.path.abspath(args.stack_tree)
    if not os.path.isdir(os.path.join(stack_tree, "backend")):
        raise BenchError("--stack-tree %s is not a checkout (no backend/); a run"
                         " measures the source of the tree it is given" % stack_tree)

    prepare_environment(stack_tree, project)
    # --compose-file overrides the profile list for a caller who must run the
    # protocol against a prebuilt image instead of a locally built stack; the
    # files come from the arms file otherwise, so a plain run names them.
    files = list(args.compose_file or protocol["compose_files"][args.profile])
    for required in files:
        if not os.path.isfile(os.path.join(stack_tree, required)):
            raise BenchError("the %s profile needs %s in %s"
                             % (args.profile, required, stack_tree))
    # after ownership: whose stack it is matters more than who holds the port,
    # an http cell loads a host port, and only one publisher can hold one: a
    # foreign backend already answering there would be what gets measured
    for cell in cells:
        if cell["kind"] != "http":
            continue
        base = cell_base(args, cell)
        occupant = listening(base)
        if occupant:
            raise BenchError("something already answers on %s (%s), the address"
                             " of cell %s; the run would measure that server"
                             " and not this arm. Stop the stack which publishes"
                             " the port, or give the run a free pair with"
                             " --host-port" % (base, occupant, cell["name"]))
    owned_or_die(project)
    stack = Stack(stack_tree, project, files, arm,
                  args.legacy_off_settings_module, args.host_port)

    out = os.path.abspath(args.out)
    # only this arm's own files are cleared, so an earlier arm's readings stay
    # where they are: a protocol is a long run, and resuming one arm beats
    # restarting all of them.
    if os.path.isdir(out):
        for name in os.listdir(out):
            if _belongs_to(name, arm["name"]):
                os.remove(os.path.join(out, name))
    else:
        os.makedirs(out, exist_ok=True)
    stack.write_override(out)
    # before anything is started or removed: the run may only touch what it owns
    stack.check_project()

    say("arm=%s profile=%s project=%s" % (arm["name"], args.profile, project))
    say("stack tree=%s  out=%s" % (stack_tree, out))
    say("cells: %s" % ", ".join(cell["name"] for cell in cells))
    started = time.time()
    failures = []
    try:
        for cell in cells:
            say("cell %s (%s)" % (cell["name"], cell["kind"]))
            try:
                if cell["kind"] == "celery":
                    run_celery_cell(args, arm, cell, stack, out, protocol)
                else:
                    run_http_cell(args, arm, cell, stack, out, protocol)
            except BenchError as error:
                failures.append("%s: %s" % (cell["name"], error))
                say("  cell %s failed: %s" % (cell["name"], error))
    finally:
        stack.down()
        for name in list(os.listdir(out)):
            if name.startswith("override-") or name.endswith(".mem"):
                os.remove(os.path.join(out, name))
    write_manifest(args, data, arm, cells, project, stack_tree, started, failures)
    if args.artifacts:
        copy_artifacts(out, args.artifacts, arm["name"])
    if failures:
        say("%d of %d cell(s) failed; the artifacts above cover the rest"
            % (len(failures), len(cells)))
        return 1
    return 0


def run_celery_cell(args, arm, cell, stack, out, protocol):
    repeats = args.repeats or protocol["repeats"]
    seed = args.seed or protocol["seed"]
    host_dir = cell["out_dir"]
    # the runner composes from the tree whose source is measured and bind
    # mounts its backend/ into the workload container, so the run directory of
    # the work lives in that tree and not beside the tool
    checkout = os.path.join(stack.tree, host_dir)
    if os.path.isdir(checkout):
        shutil.rmtree(checkout)
    os.makedirs(checkout, exist_ok=True)
    os.chmod(checkout, 0o777)

    knobs = dict(arm.get("celery_env") or {})
    env = dict(os.environ)
    env["COMPOSE_PROJECT_NAME"] = stack.project
    env["MRMAP_TASK_PERF_REPEATS"] = str(repeats)
    env["MRMAP_TASK_PERF_SEED"] = str(seed)
    env["MRMAP_TASK_PERF_QUEUE_CONFIG"] = arm["name"]
    for key, value in knobs.items():
        env[key] = str(value)
    # the record has to be able to say what the arm enabled; the bench suite only
    # echoes what it was given, so the knobs are archived verbatim next to it
    with open(os.path.join(out, "celery-env-%s-%s.json" % (arm["name"], cell["name"])),
              "w") as handle:
        json.dump({"arm": arm["name"], "cell": cell["name"], "family": cell["family"],
                   "env": {key: env.get(key) for key in sorted(knobs)}},
                  handle, indent=1, sort_keys=True)

    if args.sample:
        sample(stack.project,
               os.path.join(out, "memory-%s-idle-%s.jsonl" % (arm["name"],
                                                              cell["name"])),
               "idle-%s" % cell["name"], stack.tree,
               duration=protocol["idle_sample_seconds"])

    log = os.path.join(out, "log-%s-%s.runner.log" % (arm["name"], cell["name"]))
    # the runner of the measured tree, run from that tree: it composes relative
    # to its own directory and bind mounts ./backend of that checkout into the
    # workload container, so measuring a different revision means pointing
    # --stack-tree at it, and a runner of the tool's own checkout would measure
    # the tool instead of the source
    runner = os.path.join(stack.tree, "scripts", "task_perf_runner.sh")
    if not os.path.isfile(runner):
        raise BenchError("--stack-tree %s carries no scripts/task_perf_runner.sh"
                         "; the celery cells run the workload with it" % stack.tree)
    completed = run([runner, "--family", cell["family"], "--repeats", str(repeats),
                     "--seed", str(seed), "--mode", "warn", "--out", host_dir],
                    cwd=stack.tree, env=env, check=False, timeout=6000)
    with open(log, "w") as handle:
        if completed:
            handle.write(completed.stdout or "")
            handle.write("\n--- stderr ---\n")
            handle.write(completed.stderr or "")
    code = completed.returncode if completed else "unavailable"
    say("  task_perf_runner exited %s (family=%s, %d arm knob(s))"
        % (code, cell["family"], len(knobs)))

    loaded = 0
    names = sorted(os.listdir(checkout)) if os.path.isdir(checkout) else []
    for name in names:
        if not name.endswith(".json") or name.startswith("gate.") \
                or name.startswith("detect-"):
            continue
        load = run([sys.executable, os.path.join(REPO, "scripts", "task_perf_bench.py"),
                    "load", "--arm", arm["name"], "--family", cell["family"],
                    "--repeats", str(repeats), "--seed", str(seed),
                    "--fixture", os.path.join(checkout, name),
                    "--out", os.path.join(
                        out, "taskperf-%s-%s.jsonl" % (arm["name"], cell["name"]))],
                   cwd=REPO, check=False)
        if load is not None and load.returncode == 0:
            loaded += 1
        else:
            say("  load refused %s: %s"
                % (name, (load.stderr.strip() if load else "unavailable")))
    say("  %d workload record(s) from %s" % (loaded, host_dir))
    for name in ("summary.txt", "report.txt", "gate.json"):
        source = os.path.join(checkout, name)
        if os.path.isfile(source):
            stem, extension = name.split(".", 1)
            shutil.copyfile(source, os.path.join(
                out, "%s-%s-%s.%s" % (stem, arm["name"], cell["name"], extension)))
    shutil.rmtree(checkout, ignore_errors=True)
    if completed is None or completed.returncode != 0:
        raise BenchError("task_perf_runner exited %s (see %s)" % (code, log))


def run_http_cell(args, arm, cell, stack, out, protocol):
    repeats = args.repeats or protocol["repeats"]
    # the protocol's figures are the baseline's; an override is for a smoke run
    # or a scaling study and says so in the manifest, so a reviewer never has to
    # guess whether a cheap number came from the protocol
    requests = (args.requests or protocol["requests"]) * repeats
    concurrency = args.concurrency or protocol["concurrency"]
    out_path = os.path.join(out, "http-%s-%s.jsonl" % (arm["name"], cell["name"]))
    log = os.path.join(out, "log-%s-%s.http.log" % (arm["name"], cell["name"]))

    def log_write(text):
        with open(log, "a") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")

    stack.up(cell["services"])
    if args.sample:
        sample(stack.project,
               os.path.join(out, "memory-%s-boot-%s.jsonl" % (arm["name"],
                                                              cell["name"])),
               "boot-%s" % cell["name"], stack.tree,
               duration=protocol["idle_sample_seconds"])

    base = cell_base(args, cell)
    bench = os.path.join(REPO, "scripts", "http_process_bench.py")
    result = run([sys.executable, bench, "wait-ready", "--arm", arm["name"],
                  "--base-url", base, "--out", out_path], cwd=REPO, check=False,
                 timeout=900)
    if result is None or result.returncode != 0:
        log_write((result.stderr if result else "wait-ready unavailable") or "")
        raise BenchError("the web tier of %s never answered on %s"
                         % (cell["name"], base))

    endpoints = []
    for endpoint in cell["endpoints"]:
        endpoints += ["--endpoint", endpoint]
    common = ["--base-url", base, "--concurrency", str(concurrency)]
    run([sys.executable, bench, "load", "--arm", arm["name"], "--phase", "warmup",
         "--requests", str(args.warmup or protocol["warmup_requests"])]
        + endpoints + common + ["--out", out_path], cwd=REPO, check=False)

    media = cell.get("media_paths")
    before = stack.inventory(cell["media_service"], media) if media else None
    load = [sys.executable, bench, "load", "--arm", arm["name"], "--phase", "load",
            "--requests", str(requests), "--peer-endpoint",
            protocol["peer_endpoint"]] + endpoints + common
    if cell.get("websocket_count"):
        load += ["--ws-base-url", args.ws_base_url or cell.get("ws_base_url", base),
                 "--ws-count", str(cell["websocket_count"]),
                 "--ws-hold", str(cell.get("websocket_hold_seconds", 30)),
                 "--token", stack.websocket_token(bench, base, log_write,
                                                  protocol, cell["name"])]
    mem_path = os.path.join(out, "memory-%s-load-%s.jsonl"
                            % (arm["name"], cell["name"]))
    if args.sample:
        # --during keeps load and sample one phase: a peak which happened while
        # nobody was sampling is not evidence of anything
        sample(stack.project, mem_path, "load-%s" % cell["name"], stack.tree,
               during=" ".join(str(part) for part in load))
    else:
        result = run(load, cwd=REPO, check=False, timeout=3000)
        if result is not None and result.stderr:
            log_write(result.stderr)
    after = stack.inventory(cell["media_service"], media) if media else None
    with open(os.path.join(out, "storage-%s-%s.json" % (arm["name"], cell["name"])),
              "w") as handle:
        json.dump({"arm": arm["name"], "cell": cell["name"],
                   "service": cell.get("media_service"), "before": before,
                   "after": after, "delta": storage_delta(before, after)},
                  handle, indent=1, sort_keys=True)
    stack.stop(cell["services"])


def storage_delta(before, after):
    if not before or not after or not (before.get("available")
                                       and after.get("available")):
        return None
    first = before.get("paths") or {}
    second = after.get("paths") or {}
    return {path: {
        "kilobytes": (second.get(path, {}).get("kilobytes") or 0)
        - (first.get(path, {}).get("kilobytes") or 0),
        "files": (second.get(path, {}).get("files") or 0)
        - (first.get(path, {}).get("files") or 0)}
        for path in sorted(set(first) | set(second))}


def write_manifest(args, data, arm, cells, project, stack_tree, started, failures):
    def git(*command):
        try:
            return subprocess.run(["git", *command], cwd=stack_tree, timeout=20,
                                  capture_output=True, text=True).stdout.strip()
        except Exception:
            return ""

    manifest = {
        "schema": RUN_SCHEMA,
        "kind": "run",
        "arm": arm["name"],
        "profile": args.profile,
        "project": project,
        "stack_tree": stack_tree,
        "arms_file": os.path.relpath(os.path.abspath(args.arms_file), REPO),
        "arms_file_sha256": digest_of(os.path.abspath(args.arms_file)),
        "revision": git("rev-parse", "HEAD"),
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "cells": [cell["name"] for cell in cells],
        "repeats": args.repeats or data["protocol"]["repeats"],
        "seed": args.seed or data["protocol"]["seed"],
        "sampled": bool(args.sample),
        "protocol_overrides": {key: value for key, value in (
            ("requests", getattr(args, "requests", None)),
            ("warmup_requests", getattr(args, "warmup", None)),
            ("concurrency", getattr(args, "concurrency", None)),
            ("repeats", args.repeats)) if value},
        "legacy_off_settings_module": args.legacy_off_settings_module or None,
        "protocol": data["protocol"],
        "arm_definition": arm,
        "duration_seconds": round(time.time() - started, 1),
        "failed_cells": failures,
        "host": {"machine": os.uname().sysname, "release": os.uname().release,
                 "cores": os.cpu_count()},
    }
    path = os.path.join(args.out, "run-%s.json" % arm["name"])
    with open(path, "w") as handle:
        json.dump(manifest, handle, indent=1, sort_keys=True)
        handle.write("\n")
    say("manifest %s (revision %s%s)"
        % (path, (manifest["revision"] or "?")[:10],
           ", working tree dirty" if manifest["dirty"] else ""))


def copy_artifacts(out, target, arm_name):
    if not os.path.isdir(target):
        os.makedirs(target, exist_ok=True)
    published = 0
    for name in sorted(os.listdir(out)):
        if not _belongs_to(name, arm_name):
            continue
        if os.path.getsize(os.path.join(out, name)) == 0:
            say("  %s is empty; not published" % name)
            continue
        shutil.copyfile(os.path.join(out, name), os.path.join(target, name))
        published += 1
    say("artifacts: %d file(s) in %s" % (published, target))


# ---------------------------------------------------------------------------
# the reading side: offline, no docker, no application imports
# ---------------------------------------------------------------------------
def read_jsonl(path):
    records = []
    if not os.path.isfile(path):
        return records
    with open(path) as handle:
        for number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except ValueError as error:
                say("%s:%d is not JSON (%s)" % (path, number, error))
    return records


#: one phase record of scripts/stack_memory_profile carries the stack sums; a
#: sampler written before the per-process reads existed carries none of the
#: process rows, which the reader must not read as "no process used memory".
SAMPLE_MARKER = "stack_sum_current_peak"


def cell_records(directory, arm_name):
    """The measurements of one arm, keyed by cell, from its run directory.

    The names are matched by PREFIX, never by a pattern with a wildcard arm: an
    arm name and a cell name may both contain dashes, so "which part is the arm"
    is only decidable against the arm this reader was asked about. A regex with
    a greedy arm reads ``http-legacy-shipped-service-list-ws.jsonl`` as cell
    ``ws``, and the cell silently disappears from the baseline.
    """
    rows = {}
    for kind in ("taskperf", "http"):
        prefix = "%s-%s-" % (kind, arm_name)
        for name in sorted(os.listdir(directory)):
            if not (name.startswith(prefix) and name.endswith(".jsonl")):
                continue
            records = read_jsonl(os.path.join(directory, name))
            if records:
                rows.setdefault(name[len(prefix):-len(".jsonl")], {})[kind] = records
    prefix = "memory-%s-" % arm_name
    for name in sorted(os.listdir(directory)):
        if not (name.startswith(prefix) and name.endswith(".jsonl")):
            continue
        # the writer names the phase "<kind>-<cell>" (load-, idle-, boot-), so
        # the phase is the part before the first dash of what is left
        remainder = name[len(prefix):-len(".jsonl")]
        phase, _, cell = remainder.partition("-")
        if not cell:
            continue
        records = read_jsonl(os.path.join(directory, name))
        if records:
            rows.setdefault(cell, {}).setdefault("memory", {})[phase] = records
    return rows


def memory_summary(records):
    """The stack-wide reading of one phase, over the containers it sampled."""
    peaks = []
    committed = []
    cpu = 0
    oom = 0
    pss = None
    samples = 0
    containers = set()
    for record in records:
        if SAMPLE_MARKER not in record:
            continue
        samples += record.get("samples") or 0
        if record.get(SAMPLE_MARKER) is not None:
            peaks.append(record[SAMPLE_MARKER])
        if record.get("stack_sum_committed_peak") is not None:
            committed.append(record["stack_sum_committed_peak"])
        for name, row in (record.get("containers") or {}).items():
            containers.add(name)
            cpu += row.get("cpu_usage_usec_delta") or 0
            oom += row.get("oom_kill_delta") or 0
            for process in (row.get("procs") or {}).values():
                peak = process.get("pss_peak")
                if peak is not None:
                    pss = peak if pss is None else max(pss, peak)
    if not peaks:
        return None
    return {"samples": samples,
            "stack_current_peak_bytes": max(peaks),
            "stack_committed_peak_bytes": max(committed) if committed else None,
            "process_pss_peak_bytes": pss,
            "cpu_usage_usec": cpu,
            "oom_kill": oom,
            "containers": len(containers)}


def injected(record):
    """The fault-injection name of a task_perf_bench record, or None.

    ``task_perf_bench.py`` uses *arm* for something else than this protocol
    does: it injects a fault (``sql-n-plus-one``, ``slow-body``,
    ``duplicate-remote-call``) into the workload to check a detector sees it
    (#1778), and names it in ``quality.injection``. Those records are evidence
    for #1778 and never for a baseline - averaging a deliberately degraded run
    into the cost of a profiler compares a fault against an instrument and
    reports the difference as instrumentation.
    """
    injection = (record.get("quality") or {}).get("injection") or {}
    installed = injection.get("installed")
    if installed:
        return ",".join(sorted(installed))
    if injection.get("arm") and injection["arm"] != "baseline":
        return injection["arm"]
    return None


def celery_summary(records):
    """One row per family/scale, from the runtime records of one arm.

    Only the un-injected workload is aggregated, and the row carries the count
    of what was left out so a reader sees the exclusion instead of trusting it.
    """
    groups = {}
    excluded = {}
    for record in records:
        key = "%s/%s" % (record.get("family"), record.get("scale"))
        if injected(record):
            # counted against its own family and scale, so a reader can see
            # which row lost records rather than trusting a file-wide total
            excluded[key] = excluded.get(key, 0) + 1
            continue
        durations = record.get("durations") or {}
        active = durations.get("active") or {}
        end = durations.get("end_to_end") or {}
        group = groups.setdefault(key, {"active": [], "end": [], "outcomes": {},
                                        "sql": [], "evidence": set(),
                                        "repeats": set()})
        group["active"] += [float(value) for value in (active.get("samples") or [])]
        group["end"] += [float(value) for value in (end.get("samples") or [])]
        for outcome, row in (record.get("outcomes") or {}).items():
            count = row.get("count") if isinstance(row, dict) else row
            group["outcomes"][outcome] = group["outcomes"].get(outcome, 0) + (count or 0)
        statements = ((record.get("sql") or {}).get("statements") or {})
        if statements.get("value") is not None:
            group["sql"].append(statements["value"])
        if active.get("evidence"):
            group["evidence"].add(active["evidence"])
        group["repeats"].add(record.get("repeat"))
    rows = {}
    for key, group in sorted(groups.items()):
        active = sorted(group["active"])
        rows[key] = {"samples": len(active),
                     "repeats": len(group["repeats"]),
                     "active_p50": _percentile(active, 0.5),
                     "active_p95": _percentile(active, 0.95),
                     "active_p99": _percentile(active, 0.99),
                     "active_mean": _mean(active),
                     "active_cv": _cv(active),
                     "end_to_end_p95": _percentile(sorted(group["end"]), 0.95),
                     "sql_statements_max": max(group["sql"]) if group["sql"] else None,
                     "outcomes": group["outcomes"],
                     "injected_records_excluded": excluded.get(key, 0),
                     "evidence": sorted(group["evidence"])}
    return rows


def http_summary(records):
    """One row per phase, from the load records of one arm."""
    rows = {}
    for record in records:
        if record.get("kind") == "boot":
            rows.setdefault("boot", {})["ready_seconds"] = record.get("seconds")
            continue
        if record.get("kind") != "load":
            continue
        overall = ((record.get("http") or {}).get("overall")) or {}
        peer = ((record.get("peer") or {}).get("overall")) or {}
        websocket = record.get("ws") or {}
        rows[record.get("phase") or "load"] = {
            "requests": record.get("requests"),
            "answered": overall.get("n"),
            "rps": overall.get("rps"),
            "errors": overall.get("errors"),
            "p50_ms": overall.get("p50_ms"),
            "p95_ms": overall.get("p95_ms"),
            "p99_ms": overall.get("p99_ms"),
            "peer_p95_ms": peer.get("p95_ms"),
            "websocket_open": websocket.get("open_at_end"),
            "websocket_closed_early": websocket.get("closed_early"),
        }
    return rows


def _percentile(values, quantile):
    if not values:
        return None
    index = min(len(values) - 1, max(0, math.ceil(quantile * len(values)) - 1))
    return values[index]


def _mean(values):
    return round(sum(values) / len(values), 6) if values else None


def _cv(values):
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if not mean:
        return None
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return round(math.sqrt(variance) / mean, 4)


def _on(value):
    return str(value).strip().lower() not in ("", "0", "off", "false", "no", "none")


def build_summaries(directory):
    """Every arm of one run directory, with the tables of each of its cells."""
    summaries = {}
    for name in sorted(os.listdir(directory)):
        match = re.match(r"^run-(?P<arm>.+)\.json$", name)
        if not match:
            continue
        arm = match.group("arm")
        manifest = load_json(os.path.join(directory, name), "run manifest")
        entries = {}
        for cell, kinds in sorted(cell_records(directory, arm).items()):
            entry = {}
            if "taskperf" in kinds:
                entry["runtime"] = celery_summary(kinds["taskperf"])
            if "http" in kinds:
                entry["http"] = http_summary(kinds["http"])
            if "memory" in kinds:
                entry["memory"] = {phase: row for phase, row in
                                   ((phase, memory_summary(rows))
                                    for phase, rows in sorted(kinds["memory"].items()))
                                   if row}
            storage = os.path.join(directory, "storage-%s-%s.json" % (arm, cell))
            if os.path.isfile(storage):
                payload = load_json(storage, "storage inventory")
                entry["storage"] = payload.get("delta")
                entry["storage_measured"] = bool((payload.get("before") or {})
                                                 .get("available"))
            environment = os.path.join(directory,
                                       "celery-env-%s-%s.json" % (arm, cell))
            if os.path.isfile(environment):
                entry["observability_env"] = load_json(
                    environment, "celery environment").get("env")
            entries[cell] = entry
        summaries[arm] = {"manifest": manifest, "cells": entries}
    return summaries


def cmd_report(args, data):
    summaries = build_summaries(args.out)
    if not summaries:
        raise BenchError("report: %s holds no run-<arm>.json manifest; run the"
                         " protocol first, or point --in at its output directory"
                         % args.out)
    for arm, summary in summaries.items():
        manifest = summary["manifest"]
        print()
        print("arm %s  [%s%s]  revision %s%s  %ss"
              % (arm, manifest.get("profile"),
                 "" if manifest.get("sampled", True) else ", unsampled",
                 (manifest.get("revision") or "?")[:10],
                 " (dirty)" if manifest.get("dirty") else "",
                 manifest.get("duration_seconds")))
        if manifest.get("failed_cells"):
            print("  failed cells: %s" % "; ".join(manifest["failed_cells"]))
        for cell, entry in summary["cells"].items():
            print("  cell %s" % cell)
            if entry.get("observability_env") is not None:
                enabled = {key: value for key, value in
                           entry["observability_env"].items() if _on(value)}
                print("    observability: %s"
                      % (", ".join("%s=%s" % pair for pair in sorted(enabled.items()))
                         or "nothing enabled (diagnostics off)"))
            for label, row in sorted((entry.get("runtime") or {}).items()):
                print("    runtime   %-30s n=%-4s p50=%-10s p95=%-10s p99=%-10s"
                      " cv=%-7s sql<=%-5s %s"
                      % (label, row["samples"], row["active_p50"], row["active_p95"],
                         row["active_p99"], row["active_cv"],
                         row["sql_statements_max"],
                         ",".join("%s=%s" % pair
                                  for pair in sorted(row["outcomes"].items()))))
                if row["evidence"]:
                    print("    %-39s evidence=%s" % ("", ",".join(row["evidence"])))
            for phase, row in sorted((entry.get("http") or {}).items()):
                print("    http      %-30s n=%-5s rps=%-7s p50=%-7s p95=%-7s p99=%-7s"
                      " errors=%-4s peer_p95=%-7s ws=%s"
                      % (phase,
                         row["answered"] if row["answered"] is not None
                         else row["requests"], row["rps"], row["p50_ms"],
                         row["p95_ms"], row["p99_ms"], row["errors"],
                         row["peer_p95_ms"],
                         "-" if row["websocket_open"] is None
                         else "%s open, %s closed early"
                         % (row["websocket_open"], row["websocket_closed_early"])))
            for phase, row in sorted((entry.get("memory") or {}).items()):
                print("    memory    %-30s samples=%-4s stack_peak=%-12s"
                      " committed=%-12s pss=%-12s cpu_usec=%-11s oom=%s"
                      % (phase, row["samples"], row["stack_current_peak_bytes"],
                         row["stack_committed_peak_bytes"],
                         row["process_pss_peak_bytes"], row["cpu_usage_usec"],
                         row["oom_kill"]))
            if entry.get("storage"):
                for path, row in sorted(entry["storage"].items()):
                    print("    storage   %-30s +%s KiB, +%s file(s)"
                          % (path, row["kilobytes"], row["files"]))
            elif entry.get("storage_measured") is False:
                print("    storage   %-30s not measurable in this container" % "(--)")
    print()
    return 0


def cmd_baseline(args, data):
    """The paired baseline artifact: cells, ratios, variability, budget verdicts."""
    summaries = build_summaries(args.out)
    if not summaries:
        raise BenchError("baseline: %s holds no run-<arm>.json manifest" % args.out)
    budgets = load_json(args.budget_file, "budget file")
    reference = budgets.get("reference_arm")
    if reference not in summaries:
        raise BenchError("baseline: the budget file names reference arm %r, which"
                         " has no run in %s (arms present: %s)"
                         % (reference, args.out, ", ".join(sorted(summaries))))
    payload = {
        "schema": BASELINE_SCHEMA,
        "issue": 1777,
        "measured_from": os.path.abspath(args.out),
        "arms_file": os.path.relpath(os.path.abspath(args.arms_file), REPO),
        "arms_file_sha256": digest_of(os.path.abspath(args.arms_file)),
        "reference_arm": reference,
        "arms": {arm: {key: summary["manifest"].get(key) for key in
                       ("revision", "branch", "dirty", "profile", "sampled",
                        "repeats", "seed", "host", "duration_seconds")}
                 for arm, summary in sorted(summaries.items())},
        "cells": {},
        "budgets": budgets.get("budgets", []),
        "verdicts": [],
    }
    for cell in sorted({name for summary in summaries.values()
                        for name in summary["cells"]}):
        payload["cells"][cell] = {arm: summaries[arm]["cells"].get(cell, {})
                                  for arm in sorted(summaries)}
    payload["verdicts"] = judge(payload, summaries)
    target = args.out_file or os.path.join(args.out, "baseline.json")
    with open(target, "w") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    counts = {}
    for verdict in payload["verdicts"]:
        counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1
        say("  %-6s %-52s %s"
            % (verdict["verdict"],
               "%s/%s/%s" % (verdict["arm"], verdict["cell"], verdict["metric"]),
               verdict["detail"]))
    say("baseline %s: %d budget check(s) %s"
        % (target, len(payload["verdicts"]),
           ", ".join("%s=%d" % pair for pair in sorted(counts.items())) or "none"))
    return 0


def judge(payload, summaries):
    """Compare every other arm against the reference arm of the same cell.

    A budget is a ceiling on a *ratio* against the reference, never an absolute
    wall-clock figure: absolute numbers are a property of the host, and a CI
    gate on those is the flaky timing gate the issue forbids. A missing side is
    a ``skip`` rather than a pass - a budget nobody measured has not been met.
    """
    reference = payload["reference_arm"]
    measured = {arm for arms in payload["cells"].values() for arm in arms}
    verdicts = []
    for budget in payload["budgets"]:
        cell = budget["cell"]
        metric = budget["metric"]
        named = budget.get("arm")
        # the candidates are the arms the baseline actually carries, not the
        # arguments of the caller: a budget must be judged against what was
        # measured, and a budget naming a cell no arm ran is judged as missing
        candidates = [named] if named else sorted(measured - {reference})
        if not candidates:
            verdicts.append({"verdict": "skip", "arm": "(none)", "cell": cell,
                             "metric": metric, "reference": None, "value": None,
                             "detail": "no arm besides the reference ran this cell"})
            continue
        for candidate in candidates:
            base = _metric_value(payload, reference, cell, metric)
            after = _metric_value(payload, candidate, cell, metric)
            if base in (None, 0) or after is None:
                verdicts.append({"verdict": "skip", "arm": candidate, "cell": cell,
                                 "metric": metric, "reference": base,
                                 "value": after,
                                 "detail": "reference=%s candidate=%s - one side was"
                                           " never measured" % (base, after)})
                continue
            ratio = round(after / base, 4)
            limit = budget.get("max_ratio")
            verdict = "pass" if limit is None or ratio <= limit else "fail"
            verdicts.append({"verdict": verdict, "arm": candidate, "cell": cell,
                             "metric": metric, "reference": base, "value": after,
                             "ratio": ratio, "max_ratio": limit,
                             "detail": "%s over %s = x%s (limit x%s)"
                                       % (_short(candidate, cell, metric),
                                          _short(reference, cell, metric), ratio,
                                          limit)})
    return verdicts


def _short(arm, cell, metric):
    return "%s/%s.%s" % (arm, cell, metric)


def _metric_value(payload, arm, cell, metric):
    """Walk a dotted metric path through one arm's cell entry.

    A metric names a row of one of the tables the report prints, e.g.
    ``runtime.harvesting.import_chunk/typical.active_p95`` or
    ``memory.load-service-list.stack_committed_peak_bytes``. An absent row
    answers None, which the caller reads as "not measured".
    """
    return _walk((payload["cells"].get(cell) or {}).get(arm) or {},
                 metric.split("."))


def _walk(node, parts):
    """Resolve a dotted path whose ROW key may itself contain dots.

    ``runtime.harvesting.import_chunk/typical.active_p95`` names the row
    ``harvesting.import_chunk/typical`` of the runtime table, and the row key
    carries the dots of the family name - so a level is matched against the
    longest join of the remaining parts which the table actually has, longest
    first, rather than one part at a time.
    """
    if not parts:
        return node if isinstance(node, (int, float)) or node is None else None
    if not isinstance(node, dict):
        return None
    for take in range(len(parts), 0, -1):
        key = ".".join(parts[:take])
        if key in node:
            found = _walk(node[key], parts[take:])
            if found is not None:
                return found
    return None


def cmd_verify(args, data):
    """Offline checks of a run directory: the evidence of a run, without docker.

    Refuses a run whose manifest does not match the arms file it claims, whose
    arm enabled a knob its definition does not name, whose table is empty, and
    any budget which was exceeded. This is what lets the committed baseline be
    trusted without starting a stack.
    """
    summaries = build_summaries(args.out)
    problems = []
    if not summaries:
        problems.append("no run-<arm>.json manifest in %s" % args.out)
    expected = digest_of(os.path.abspath(args.arms_file))
    defined = {arm["name"]: arm for arm in data["arms"]}
    for arm, summary in summaries.items():
        manifest = summary["manifest"]
        if manifest.get("arms_file_sha256") != expected:
            problems.append("arm %s was measured with a different arms file (%s"
                            " != %s): its numbers do not describe the protocol"
                            " this file defines"
                            % (arm, str(manifest.get("arms_file_sha256"))[:12],
                               expected[:12]))
        if arm not in defined:
            problems.append("arm %s is not defined in the arms file" % arm)
            continue
        if manifest.get("arm_definition") != defined[arm]:
            problems.append("arm %s: the manifest carries an arm definition which"
                            " is not the one in the arms file" % arm)
        if not manifest.get("revision"):
            problems.append("arm %s: no git revision in the manifest, so the"
                            " measurement cannot be attributed to a checkout" % arm)
        if manifest.get("dirty"):
            say("note: arm %s was measured on a dirty working tree" % arm)
        enabled = set(defined[arm].get("celery_env") or {})
        unknown = sorted(enabled - set(LEGACY_TASK_KNOBS))
        if unknown:
            problems.append("arm %s names %s, which is not a shipped legacy task"
                            " knob" % (arm, ", ".join(unknown)))
        for cell, entry in summary["cells"].items():
            observed = {key for key, value in (entry.get("observability_env")
                                               or {}).items() if _on(value)}
            extra = observed - enabled
            if extra:
                problems.append("arm %s/%s enabled %s, which its definition does"
                                " not name - the arm is not the one it claims"
                                % (arm, cell, ", ".join(sorted(extra))))
            if not entry:
                problems.append("arm %s/%s: the manifest names the cell but no"
                                " artifact backs it" % (arm, cell))
            for table in ("runtime", "http"):
                if table in entry and not entry[table]:
                    problems.append("arm %s/%s: the %s table is empty"
                                    % (arm, cell, table))
    target = os.path.join(args.out, "baseline.json")
    if os.path.isfile(target):
        payload = load_json(target, "baseline")
        if payload.get("arms_file_sha256") != expected:
            problems.append("baseline.json was generated from a different arms file")
        for verdict in payload.get("verdicts", []):
            if verdict["verdict"] == "fail":
                problems.append("budget %s/%s/%s exceeded: %s"
                                % (verdict["arm"], verdict["cell"],
                                   verdict["metric"], verdict["detail"]))
    for problem in problems:
        say("verify: %s" % problem)
    if problems:
        say("%d problem(s)" % len(problems))
        return 1
    say("verified %d arm(s) from %s" % (len(summaries), args.out))
    return 0


def cmd_cleanup(args, data):
    project = args.project
    if not project.startswith(PROJECT_PREFIX):
        raise BenchError("--project %s does not look like a project this tool"
                         " creates (expected %s*): only a project this tool created"
                         " may be removed by it" % (project, PROJECT_PREFIX))
    command = ["docker", "compose"]
    for path in args.compose_file or [
            data["protocol"]["compose_files"]["production"][0]]:
        command += ["-f", path]
    run(command + ["-p", project, "down", "--remove-orphans"],
        cwd=os.path.abspath(args.stack_tree), check=False)
    say("removed the stack of %s" % project)
    return 0


# ---------------------------------------------------------------------------
def parser():
    tool = argparse.ArgumentParser(
        description="the matched observability benchmark protocol of #1777")
    tool.add_argument("--arms-file",
                      default=os.path.join(REPO, DEFAULT_ARMS_FILE))
    sub = tool.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="print the exact command sequence of a cell")
    plan.add_argument("--arm")
    plan.add_argument("--cell")
    plan.add_argument("--kind", choices=["celery", "http"])
    plan.add_argument("--profile", default="production")

    runner = sub.add_parser("run", help="measure one arm of the protocol")
    runner.add_argument("--arm", required=True)
    runner.add_argument("--cell")
    runner.add_argument("--kind", choices=["celery", "http"])
    runner.add_argument("--profile", default="production")
    runner.add_argument("--repeats", type=int)
    runner.add_argument("--requests", type=int,
                        help="requests per repeat of an http cell; the protocol"
                             " figure of the arms file is the baseline, anything"
                             " else is recorded as an override in the manifest")
    runner.add_argument("--warmup", type=int,
                        help="warmup requests of an http cell")
    runner.add_argument("--concurrency", type=int,
                        help="request concurrency of an http cell")
    runner.add_argument("--seed", type=int)
    runner.add_argument("--out", default=os.path.join(REPO, "backend",
                                                      "observability-bench"))
    runner.add_argument("--artifacts", default="")
    runner.add_argument("--stack-tree", default=REPO)
    runner.add_argument("--compose-file", action="append",
                        help="override the compose file list of the profile"
                             " (repeatable); the arms file names them otherwise")
    runner.add_argument("--base-url", default="")
    runner.add_argument("--ws-base-url", default="")
    runner.add_argument("--host-port", type=int,
                        help="publish the web tier of an http cell on this host"
                             " port and the next one (for /ws) instead of the"
                             " 8001/8002 of the shipped files, and load it"
                             " there; needed whenever another stack holds 8001")
    runner.add_argument("--legacy-off-settings-module", default="")
    runner.add_argument("--no-sample", dest="sample", action="store_false")
    runner.set_defaults(sample=True)

    report = sub.add_parser("report", help="print the readings of a run directory")
    report.add_argument("--in", dest="out", required=True)

    baseline = sub.add_parser("baseline", help="the paired baseline artifact")
    baseline.add_argument("--in", dest="out", required=True)
    baseline.add_argument("--budget-file",
                          default=os.path.join(REPO, DEFAULT_BUDGET_FILE))
    baseline.add_argument("--out-file", default="")

    verify = sub.add_parser("verify", help="offline checks of a run directory")
    verify.add_argument("--in", dest="out", required=True)

    cleanup = sub.add_parser("cleanup", help="remove a stack this tool created")
    cleanup.add_argument("--project", required=True)
    cleanup.add_argument("--stack-tree", default=REPO)
    cleanup.add_argument("--compose-file", action="append")
    return tool


def main(argv=None):
    args = parser().parse_args(argv)
    data = load_arms(args.arms_file)
    handlers = {"plan": cmd_plan, "run": cmd_run, "report": cmd_report,
                "baseline": cmd_baseline, "verify": cmd_verify,
                "cleanup": cmd_cleanup}
    try:
        return handlers[args.cmd](args, data)
    except BenchError as error:
        print("observability_bench: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
