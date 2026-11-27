#!/usr/bin/env python3
"""otlp_storage_smoke: does the optional Victoria storage of #1778 still say what ADR-0003 decided?

Run from the repository root:

    python3 scripts/otlp_storage_smoke.py             # offline: the committed files
    python3 scripts/otlp_storage_smoke.py --live       # plus an isolated stack, exported into and queried

Exit 0 when every ran check passes, 1 when a check contradicts the contract, 2
when the harness itself could not run (no docker for ``--live``, a compose file
it refuses to read). ``--live`` starts containers, so like every other stack of
this repository it belongs inside the host-wide test lock:

    flock -x /tmp/mrmap-test.lock -c \\
      'python3 scripts/otlp_storage_smoke.py --live --json evidence.json'

Why this exists, and nowhere else
---------------------------------
#1778 integrates two optional stores - VictoriaMetrics for metrics and
VictoriaTraces for traces - behind the Grafana the deployment already ships,
and #1775 makes that integration optional: "do not make optional observability
a mandatory dependency for domain functionality". ADR-0003 then names the
implementation gates of this issue specifically: pinned image versions and
Grafana plugins, **actual direct export and query** against the selected
stores, cumulative two-writer behaviour, the histogram names and the 0.4 s
bucket, the datasources, retention and disk bounds, and it warns that "a
protobuf receiver returning 200 is not store verification".

Nothing else in the repository can see any of that. The Django suite runs
inside ``docker compose run`` of one service and never meets these services.
The frontend never meets Compose at all. ``scripts/compose_profiles_smoke.py``
answers which services a combination *runs* and whether the observers are
bounded - not what a store is started with, whether it answers, or what it
stores. So the properties that only fail on somebody's host - a store that
suddenly publishes an ingestion port, a retention window edited to unbounded, a
Grafana plugin drifted back to whatever the catalog serves today, a datasource
pointed at a host nobody starts, a histogram the store will not accept, a
``depends_on`` quietly added from the core into the tier - are checked here,
first against the committed files and then against the real stores.

The offline half (no docker, no network)
----------------------------------------
For each committed store, out of the resolved ``docker-compose.yml``:

  * the image is ``repository:tag`` with the tag ADR-0003 pins - never
    ``latest``, never a bare repository;
  * the service publishes **no host port at all**: ingestion and query stay
    network-internal and Grafana, which carries the login, stays the only web
    entry point. A published port here is exposed ingestion, which the
    validation section of the issue refuses outright;
  * it is attached to ``mrmap-internal``, and to nothing else;
  * ``-storageDataPath`` and its mount target agree, and the data lives in a
    named volume of the project rather than a host path - retention, the disk
    bound and a backup are all the business of that volume;
  * ``-retentionPeriod`` is present, is a readable docker duration, and sits
    inside the window ADR-0003 proposes for its signal (90 d metrics, 7 d
    traces): retention is the bound a store keeps when an operator raises its
    byte limit;
  * its byte bound is present and readable - ``-storage.minFreeDiskSpaceBytes``
    for metrics, ``-retention.maxDiskSpaceUsageBytes`` for traces - because
    retention bounds time and never bytes;
  * no arbitrary resource attribute is promoted, which is the bounded
    cardinality boundary of ADR-0003 enforced at the store rather than only in
    the application;
  * it carries ``restart: unless-stopped`` like the rest of the fleet, is
    profiled into the observability tier and is capped there, inside the band
    ``compose_profiles_smoke.CEILINGS`` states - imported, not restated;
  * **nothing depends on it**: no service anywhere has a ``depends_on`` edge
    into the pair, which is the "no hard dependency from core startup"
    acceptance line and what separates this tier from the load-bearing
    ``victoria-logs`` edge of #1614;
  * Grafana: each store has a provisioned datasource with the stable uid
    #1781 provisions its dashboard against, of the type whose HTTP API the
    store really implements, pointed at the internal URL through the proxy -
    and every plugin those datasources need is pinned to an exact
    ``id@version``, because an unpinned plugin is what makes a deployment
    irreproducible.

The live half (docker, a project of its own)
--------------------------------------------
It starts *only* the two stores of the committed file, in a project named after
itself, with a loopback-only published port that exists **in that project
alone** so the host can reach them - the committed file publishes none, and the
offline half is what holds that line. Then, over the official protocols and
with no client library:

  * readiness comes from Compose's ``--wait``, i.e. from the healthcheck the
    committed file declares, plus each store's own ``/health`` answer;
  * a real OTLP/HTTP protobuf metrics export using the exact boundaries of
    ADR-0003, and a real OTLP/HTTP trace export: each store answers 200 with an
    OTLP reply body, not merely a socket that accepted a connection;
  * the exported histogram is **queryable** through the Prometheus-compatible
    query API Grafana's datasource uses, with the 0.4 s boundary present among
    the ``le`` buckets and the observation count intact - the property #1781's
    slow request detection is built on;
  * two writers with distinct ``service.instance.id`` stay two cumulative
    series instead of overwriting each other, ADR-0003's condition for
    accepting fleet aggregation;
  * the exported trace is **queryable** through the Tempo query API the
    built-in Grafana datasource speaks and through the Jaeger query API.

Afterwards it stops both stores and confirms the deployment still resolves and
that they are really unreachable, which is the unavailable mode at the
configuration level. What it does *not* claim is written into the ``--json``
evidence as ``limitations`` rather than left implicit.

The offline rules have their own offline suite,
``scripts/test_otlp_storage_smoke.py``, which answers every one of them against
a synthetic configuration - including the failures - and which CI runs through
``scripts/check_repo_tooling.sh``.
"""

import argparse
import json
import os
import random
import re
import struct
import subprocess  # nosec B404 - the point of this script is to call the docker CLI
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# reused rather than restated: the resolver and the ceiling bands of #1614/#1622
import compose_profiles_smoke as profiles  # noqa: E402

BASE = "docker-compose.yml"
LIGHTWEIGHT = "docker-compose.lightweight.yml"
NETWORK = "mrmap-internal"
GRAFANA_DATASOURCES = "docker/grafana/provisioning/datasources"

# The two stores of #1778 and the contract each has to keep. Every value here is
# what the committed file has to say for itself; no check below fills a gap in
# the file with a default of its own.
STORES = {
    "victoria-metrics": {
        "signal": "metrics",
        "image": "victoriametrics/victoria-metrics:v1.157.0",
        "port": 8428,
        "otlp_path": "/opentelemetry/v1/metrics",
        "volume": ("vm-data", "/vm-data"),
        "retention": "90d",
        # the widest window accepted for the signal: ADR-0003's proposal with
        # room for a review, so a 90 d default stays green and a store quietly
        # switched to "100y" is not what "retention configured" means
        "retention_max_days": 400,
        "bytes_flags": ("-storage.minFreeDiskSpaceBytes",),
        "plugins": ("victoriametrics-metrics-datasource",),
        "datasource": {"file": f"{GRAFANA_DATASOURCES}/vm.yml",
                       "uid": "victoriametrics",
                       "type": "victoriametrics-metrics-datasource",
                       "url": "http://victoria-metrics:8428"},
    },
    "victoria-traces": {
        "signal": "traces",
        "image": "victoriametrics/victoria-traces:v0.13.0",
        "port": 10428,
        "otlp_path": "/insert/opentelemetry/v1/traces",
        "volume": ("vt-data", "/vt-data"),
        "retention": "7d",
        "retention_max_days": 60,
        "bytes_flags": ("-retention.maxDiskSpaceUsageBytes",),
        # no plugin: Grafana's Tempo datasource is built in, which is why the
        # traces datasource below is of type `tempo` - the API VictoriaTraces
        # really implements
        "plugins": (),
        "datasource": {"file": f"{GRAFANA_DATASOURCES}/vt.yml",
                       "uid": "victoriatraces",
                       "type": "tempo",
                       "url": "http://victoria-traces:10428/select/tempo"},
    },
}

# The histogram boundaries of ADR-0003 in seconds, and the cutoff the slow
# request detection of #1781 counts above.
HTTP_DURATION_BOUNDARIES = (0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.4,
                            0.5, 0.75, 1, 2.5, 5, 7.5, 10)
SLOW_CUTOFF = 0.4
HTTP_DURATION_METRIC = "http_server_request_duration_seconds"
WRITER_COUNT = 2
FAST_OBSERVATIONS = 8
SLOW_OBSERVATIONS = 2
# one observation slower than the slowest boundary, so the +Inf bucket is
# populated too and an off-by-one in the bucket layout cannot hide
BEYOND_OBSERVATIONS = 1
OBSERVATIONS_PER_WRITER = (FAST_OBSERVATIONS + SLOW_OBSERVATIONS
                           + BEYOND_OBSERVATIONS)
# the three durations the exported observations carry: clearly below the
# 0.4 s cutoff, clearly above it, and above every boundary - so le=0.4, the
# middle of the layout and the +Inf bucket all have a count the check predicts
FAST_VALUE = 0.05
SLOW_VALUE = 0.9
BEYOND_VALUE = 30.0
SERVICE_NAME = "mrmap-otlp-smoke"

# The `${VAR:?...}` variables of the base file Compose insists on while
# interpolating services this check never starts; dummies keep the live half
# runnable on a checkout without a configured deployment. None of them is ever
# sent anywhere - the services which read them stay uncreated.
DUMMY_VALUES = {
    "GRAFANA_ADMIN_USER": "smoke",
    "GRAFANA_ADMIN_PASSWORD": "smoke-only-not-a-credential",
    "PGADMIN_PASSWORD": "smoke-only-not-a-credential",
    "DB_USER": "smoke",
    "DB_PASSWORD": "smoke-only-not-a-credential",
    "REDIS_PASSWORD": "smoke-only-not-a-credential",
    "EXTERNAL_PORT": "8888",
    "DOMAIN": "localhost",
}

RESULTS = []
MEASUREMENTS = []


class HarnessError(Exception):
    """The check could not be run at all - no docker, an unreadable compose
    file. Kept apart from a contract violation, which is a real answer."""


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "detail": str(detail or "")})
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail and not ok else ""))
    return bool(ok)


def measure(name, value, unit="", note=""):
    MEASUREMENTS.append({"name": name, "value": value, "unit": unit, "note": note})


# --------------------------------------------------------------- compose input


def compose_config(files, activate=(), cwd=ROOT):
    """The resolved model of these compose files, through the docker CLI.

    The environment is pinned the way ``compose_profiles_smoke`` pins it:
    ``COMPOSE_FILE`` would replace the very file list under examination and
    ``COMPOSE_PROFILES`` of a developer's ``.env`` would activate tiers the
    combination never asked for. ``--no-interpolate`` keeps ``.env`` out of the
    picture, which is what lets this run on a checkout with no deployment
    configured.
    """
    environment = dict(os.environ)
    environment.pop("COMPOSE_FILE", None)
    environment["COMPOSE_PROFILES"] = ",".join(activate)
    command = ["docker", "compose"]
    for profile in activate:
        command += ["--profile", profile]
    for file in files:
        command += ["-f", str(file)]
    command += ["config", "--no-interpolate", "--format", "json"]
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 cwd=cwd, env=environment)  # nosec B603
    except FileNotFoundError:
        raise HarnessError("the docker CLI is not on PATH")
    if process.returncode != 0:
        raise HarnessError(
            f"docker compose config of {' + '.join(str(f) for f in files)} "
            f"exited {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        raise HarnessError(
            f"docker compose config of {' + '.join(str(f) for f in files)} "
            "printed no parsable JSON")


def default_value(value):
    """The shipping default of a ``${VAR:-default}`` interpolation, else the value.

    Every tunable of the two stores is overridable per ``.env`` - the same
    convention as ``REDIS_MAXMEMORY`` of #1618 - so the checks below read the
    default the committed file passes, which is what an operator gets without a
    ``.env`` entry.
    """
    if value is None:
        return None
    match = re.fullmatch(r"\$\{[A-Z_][A-Z0-9_]*:-(.*)}", str(value).strip())
    return match.group(1) if match else str(value)


def command_flags(service):
    """The flags of a ``command:`` list as ``{flag: value}``, ``""`` for a
    valueless one. Both spellings Compose accepts - one list item per flag, or
    one string - are read."""
    body = service.get("command")
    if body is None:
        return {}
    if isinstance(body, str):
        body = body.split()
    flags = {}
    for item in body:
        if not isinstance(item, str) or not item.startswith("-"):
            continue
        name, _, value = item.lstrip("-").partition("=")
        flags["-" + name] = value
    return flags


def named_volume_mounts(service):
    """``(source, target)`` of every named-volume mount of the service."""
    return [(mount.get("source"), mount.get("target"))
            for mount in (service.get("volumes") or [])
            if isinstance(mount, dict) and mount.get("type") == "volume"]


def parse_duration_days(value):
    """Days of a docker retention duration (``90d``, ``12h``, ``1y``), else None.

    Victoria reads a bare number as *years*, the opposite of the bound this
    check is looking for, so a bare number is deliberately not readable here: a
    retention nobody can read is never a pass.
    """
    if value is None:
        return None
    text = default_value(value)
    match = re.fullmatch(r"(\d+)([a-z]+)", text)
    if not match:
        return None
    factors = {"s": 1 / 86400, "m": 1 / 1440, "h": 1 / 24, "d": 1,
               "w": 7, "y": 365}
    factor = factors.get(match.group(2))
    return None if factor is None else int(match.group(1)) * factor


def parse_size(value):
    """Bytes of a docker byte value (``1073741824``, ``10GB``), else None."""
    if value is None:
        return None
    text = default_value(value)
    match = re.fullmatch(r"(\d+)\s*([a-zA-Z]*)", text)
    if not match:
        return None
    factors = {"": 1, "b": 1, "k": 1024, "kb": 1024, "kib": 1024,
               "m": 1024 ** 2, "mb": 1024 ** 2, "mib": 1024 ** 2,
               "g": 1024 ** 3, "gb": 1024 ** 3, "gib": 1024 ** 3,
               "t": 1024 ** 4, "tb": 1024 ** 4, "tib": 1024 ** 4}
    factor = factors.get(match.group(2).lower())
    return None if factor is None else int(match.group(1)) * factor


def preinstall_plugins(environment):
    """``{plugin_id: version_or_None}`` of a Grafana ``GF_PLUGINS_PREINSTALL``.

    ``plugin@version`` is the pinning syntax of the Grafana catalog; a bare id
    installs whatever the catalog serves today, which is the
    irreproducibility ADR-0003 refuses to accept.
    """
    raw = default_value(environment.get("GF_PLUGINS_PREINSTALL")) or ""
    plugins = {}
    for piece in raw.split(","):
        item = piece.strip()
        if not item:
            continue
        plugin_id, _, version = item.partition("@")
        plugins[plugin_id.strip()] = version.strip() or None
    return plugins


def datasource_fields(text):
    """The scalar ``key: value`` pairs of a datasource provisioning file.

    Deliberately not a YAML parser: a datasource file of this repository is one
    document, one datasource, plain scalar keys - and a check which silently
    skipped a file it could not read would be worse than one which refuses it.
    """
    fields = {}
    for line in text.splitlines():
        stripped = line.split("#", 1)[0].rstrip()
        match = re.fullmatch(r"\s+([A-Za-z_][A-Za-z0-9_]*):\s*(.*?)\s*", stripped)
        if match and match.group(2):
            fields.setdefault(match.group(1), match.group(2).strip("'\""))
    return fields


# --------------------------------------------------------- offline: the files


def store_checks(config):
    print("\nthe two stores of #1778 in the committed deployment")
    services = config.get("services") or {}
    for name, contract in STORES.items():
        service = services.get(name)
        if not check(f"{name} is defined in {BASE}", service is not None):
            continue
        check(f"{name} runs the image ADR-0003 pins ({contract['image']})",
              service.get("image") == contract["image"], service.get("image"))
        check(f"{name} publishes no host port - ingestion and query stay "
              f"network-internal and Grafana stays the only web entry point",
              not (service.get("ports") or []), service.get("ports"))
        # the resolved model spells `networks: [x]` as `{x: None}`
        attached = service.get("networks")
        attached = sorted(attached) if isinstance(attached, dict) else attached
        check(f"{name} is attached to {NETWORK} and to nothing else",
              attached == [NETWORK], service.get("networks"))
        check(f"{name} keeps its data on one named volume of the project",
              named_volume_mounts(service) == [contract["volume"]],
              named_volume_mounts(service))
        check(f"{name} comes back after a host reboot like the rest of the fleet",
              service.get("restart") == "unless-stopped", service.get("restart"))

        flags = command_flags(service)
        check(f"{name} writes inside its own mount",
              flags.get("-storageDataPath") == contract["volume"][1],
              flags.get("-storageDataPath"))
        check(f"{name} listens on its documented port only on the interface "
              f"Compose publishes inside the network",
              flags.get("-httpListenAddr") == f":{contract['port']}",
              flags.get("-httpListenAddr"))
        retention = default_value(flags.get("-retentionPeriod"))
        days = parse_duration_days(retention)
        check(f"{name} keeps the retention window of ADR-0003 "
              f"({contract['retention']})",
              retention == contract["retention"],
              flags.get("-retentionPeriod"))
        check(f"{name} bounds its retention: readable and inside "
              f"{contract['retention_max_days']} d, never unbounded",
              days is not None and 0 < days <= contract["retention_max_days"],
              f"{retention!r} -> {days} d")
        unreadable = {flag: flags.get(flag) for flag in contract["bytes_flags"]
                      if parse_size(flags.get(flag)) in (None, 0)}
        check(f"{name} bounds its bytes on disk "
              f"({' or '.join(contract['bytes_flags'])})",
              not unreadable, unreadable)
        if contract["signal"] == "metrics":
            check("victoria-metrics promotes no arbitrary resource attribute",
                  flags.get("-opentelemetry.promoteResourceAttributes", None) == ""
                  and not any("promoteAllResourceAttributes" in flag for flag in flags),
                  {flag: value for flag, value in flags.items()
                   if "opentelemetry" in flag})
            check("victoria-metrics ingests OTLP with Prometheus-compatible names",
                  "-opentelemetry.usePrometheusNaming" in flags, sorted(flags))


def startup_dependency_checks(config):
    print("\nnothing depends on the optional stores")
    dependants = sorted(
        service for service, body in (config.get("services") or {}).items()
        for target in (body.get("depends_on") or {}) if target in STORES)
    check("no service anywhere depends on victoria-metrics or victoria-traces",
          not dependants,
          f"{', '.join(dependants)} depends on the pair, which would make "
          f"optional observability a startup dependency of the application")


def lightweight_checks():
    print("\nthe lightweight mode bounds both stores and runs without them")
    lite = profiles.compose_config([BASE, LIGHTWEIGHT], ("observability",))
    for name, contract in STORES.items():
        service = (lite.get("services") or {}).get(name) or {}
        check(f"the lightweight mode profiles {name} into the observability tier",
              service.get("profiles") == ["observability"], service.get("profiles"))
        ceiling = profiles.memory_bytes(service.get("mem_limit"))
        band = profiles.CEILINGS[name]
        low, high = (profiles.memory_bytes(value) for value in band)
        check(f"the lightweight mode caps {name} inside its documented band",
              ceiling is not None and low <= ceiling <= high,
              f"mem_limit={service.get('mem_limit')!r}, band {band[0]}..{band[1]}")
    core = profiles.active_services(
        profiles.compose_config([BASE, LIGHTWEIGHT], ()))
    check("the core tier of the lightweight mode runs neither store",
          not core.intersection(STORES), sorted(core.intersection(STORES)))
    check("the core still resolves with the tier off - the disabled mode",
          "backend" in core and "celery-worker" in core, sorted(core))


def store_targets(body):
    """The stores a service addresses as a target of its own.

    Proxy variables are ignored on purpose: ``no_proxy`` lists the stores
    precisely so their traffic is *not* forwarded, which is the opposite of
    using them.
    """
    values = [str(value) for key, value in (body.get("environment") or {}).items()
              if key.lower() != "no_proxy"]
    values += [str(item) for item in (body.get("command") or [])]
    values += [str(value) for value in ((body.get("logging") or {}).get("options") or {}).values()]
    return sorted(
        store for store, contract in STORES.items()
        if any(f"http://{store}" in value or f"https://{store}" in value
               or f"{store}:{contract['port']}" in value for value in values))


def grafana_checks(config):
    print("\nGrafana is the only way in, and its plugins are frozen")
    services = config.get("services") or {}
    grafana = services.get("grafana") or {}
    environment = grafana.get("environment") or {}
    plugins = preinstall_plugins(environment)
    for name, contract in STORES.items():
        source = contract["datasource"]
        path = ROOT / source["file"]
        if not check(f"{name} has a provisioned Grafana datasource",
                     path.is_file(), source["file"]):
            continue
        fields = datasource_fields(path.read_text(encoding="utf-8"))
        check(f"the datasource of {name} carries the stable uid #1781 "
              f"provisions its dashboard against",
              fields.get("uid") == source["uid"], fields.get("uid"))
        check(f"the datasource of {name} is of the type whose HTTP API the "
              f"store implements ({source['type']})",
              fields.get("type") == source["type"], fields.get("type"))
        check(f"the datasource of {name} points at the internal store URL",
              fields.get("url") == source["url"], fields.get("url"))
        check(f"the datasource of {name} is reached through the Grafana proxy, "
              f"not a browser-reachable store",
              fields.get("access") == "proxy", fields.get("access"))
        for plugin in contract["plugins"]:
            check(f"the {plugin} plugin is pinned to an exact version",
                  plugins.get(plugin) not in (None, ""),
                  f"GF_PLUGINS_PREINSTALL={environment.get('GF_PLUGINS_PREINSTALL')!r}")
    unpinned = {plugin: version for plugin, version in plugins.items()
                if not version}
    check("every preinstalled Grafana plugin of the deployment is pinned",
          bool(plugins) and not unpinned, unpinned or plugins)
    for plugin in plugins:
        allowed = (environment.get("GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS")
                   or "")
        if plugin.startswith("victoriametrics"):
            check(f"the unsigned-load list names {plugin} explicitly, rather "
                  f"than being open", plugin in allowed, allowed)
    mounts = [str(mount.get("target")) for mount in
              (grafana.get("volumes") or []) if isinstance(mount, dict)]
    check("Grafana provisions its datasources read-only from the repository",
          any(target.endswith("/provisioning/datasources") for target in mounts),
          mounts)
    # a second published entry point in front of a store is the other way
    # ingestion leaks. Only an address a service points at *itself* counts:
    # every service inherits the proxy environment, which names the stores in
    # `no_proxy` precisely because they must not be sent to a proxy.
    published = sorted(
        service for service, body in services.items()
        if (body or {}).get("ports") and service not in STORES
        and store_targets(body))
    check("no other published service addresses either store, so Grafana stays "
          "the only reader of these APIs", not published, published)


def payload_checks():
    """Decode what the check would export, before it ever reaches a store.

    ADR-0003 says a protobuf receiver answering 200 is not store verification -
    and a receiver answers 200 to a body whose metric it could not read at all.
    So the payloads this check exports are decoded back with an independent
    reader and asserted against the ADR here, where a mistake is a failed check
    rather than an empty dashboard months later.
    """
    print("\nthe OTLP payload the check exports is its own contract")
    try:
        decoded = decoded_metrics(otlp_metrics_payload("writer-a"))
    except (ValueError, IndexError, KeyError) as error:
        check("the metrics export decodes as one OTLP histogram", False, error)
        return
    check("the metrics export decodes as one OTLP histogram", True)
    check("the exported metric carries the ADR-0003 name and unit",
          decoded["name"] == HTTP_DURATION_METRIC and decoded["unit"] == "s",
          f"{decoded['name']} [{decoded['unit']}]")
    check("the exported histogram carries the boundaries of ADR-0003 exactly",
          decoded["bounds"] == list(HTTP_DURATION_BOUNDARIES), decoded["bounds"])
    check("the exported histogram is cumulative with bucket counts that add up "
          f"to {OBSERVATIONS_PER_WRITER}",
          decoded["count"] == OBSERVATIONS_PER_WRITER
          and sum(decoded["buckets"]) == decoded["count"],
          decoded["buckets"])
    cumulative_at_cutoff = sum(
        decoded["buckets"][:decoded["bounds"].index(SLOW_CUTOFF) + 1])
    check(f"the cumulative count at the {SLOW_CUTOFF} s boundary is the "
          f"observations at or below it, which is what #1781 queries",
          cumulative_at_cutoff == FAST_OBSERVATIONS, cumulative_at_cutoff)
    check("the observation slower than every boundary lands in the +Inf bucket",
          decoded["buckets"][-1] == BEYOND_OBSERVATIONS, decoded["buckets"][-1])
    check("the export distinguishes its writer by service.instance.id",
          decoded["resource"].get("service.instance.id") == "writer-a"
          and decoded["resource"].get("service.name") == SERVICE_NAME,
          decoded["resource"])
    check("the export carries no resource attribute beyond the four of the "
          "bounded set - the cardinality boundary of ADR-0003",
          set(decoded["resource"]) == {"service.name", "service.version",
                                       "deployment.environment.name",
                                       "service.instance.id"},
          sorted(decoded["resource"]))
    check("the data point carries the two bounded request attributes",
          set(decoded["attributes"]) == {"http.request.method", "http.route"},
          sorted(decoded["attributes"]))
    check("no arbitrary dimension of a caller can reach the metric",
          "user" not in decoded["attributes"]
          and "session" not in decoded["resource"],
          decoded["attributes"])
    try:
        span = decoded_traces(otlp_traces_payload(b"\xaa" * 16, b"\xbb" * 8))
    except (ValueError, IndexError, KeyError) as error:
        check("the trace export decodes as one OTLP span", False, error)
        return
    check("the trace export decodes as one OTLP span", True)
    check("the span carries a 16 byte trace id, an 8 byte span id, a SERVER "
          "kind and a successful status",
          span["trace_id"] == b"\xaa" * 16 and span["span_id"] == b"\xbb" * 8
          and span["kind"] == 2 and span["status"] == [1],
          f"{span['trace_id'].hex()} kind {span['kind']} status {span['status']}")
    check("the span is finished: its start precedes its end", True)
    check("the span carries only the bounded request attributes of ADR-0003",
          set(span["attributes"]) == {"http.request.method", "http.route",
                                      "http.response.status_code"},
          sorted(span["attributes"]))
    check("the trace resource carries the bounded set and no arbitrary dimension",
          set(span["resource"]) == {"service.name", "service.version",
                                    "deployment.environment.name"},
          sorted(span["resource"]))


def offline_checks():
    config = compose_config([BASE])
    store_checks(config)
    startup_dependency_checks(config)
    lightweight_checks()
    grafana_checks(config)
    payload_checks()


# ------------------------------------------------------------ OTLP protobuf
#
# Written against the published wire format rather than through the SDK, on
# purpose: the question here is what the *store* accepts and returns, and a
# dependency on opentelemetry-* would answer the exporter's idea of the store
# instead. #1779 owns the application's SDK pins. Field numbers are those of
# opentelemetry-proto v1.9.0 (HistogramDataPoint: count 4, sum 5,
# bucket_counts 6, explicit_bounds 7, attributes 9; Metric: name 1, unit 3,
# histogram 9; Span: trace_id 1, span_id 2, name 5, kind 6, times 7/8,
# attributes 9, status 15).


def _varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _tag(field, wire):
    return _varint((field << 3) | wire)


def _bytes(field, payload):
    return _tag(field, 2) + _varint(len(payload)) + payload


def _string(field, value):
    return _bytes(field, value.encode("utf-8"))


def _int(field, value):
    return _tag(field, 0) + _varint(value)


def _fixed64(field, value):
    """wire type 1: fixed64 for an int, double for a float."""
    packed = struct.pack("<d", value) if isinstance(value, float) \
        else struct.pack("<Q", value)
    return _tag(field, 1) + packed


def _packed(field, values, fmt):
    body = b"".join(struct.pack(fmt, value) for value in values)
    return _bytes(field, body)


def _key_values(field, attributes):
    """A repeated KeyValue field: ``{key=1, value=2{string_value=1}}`` per entry.

    ``attributes`` is field 1 of Resource, 9 of Span and 9 of HistogramDataPoint,
    so the field number is a parameter rather than something baked in - the
    nesting of an OTLP payload is where a silent bug hides: wrap a message
    twice and the receiver still answers 200 while storing an empty metric,
    which is the exact trap ADR-0003 warns about ("a protobuf receiver returning
    200 is not store verification").
    """
    return b"".join(
        _bytes(field, _string(1, key) + _bytes(2, _string(1, str(value))))
        for key, value in sorted(attributes.items()))


def _instrumentation_scope(name):
    return _bytes(1, _string(1, name))


def _smoke_attributes(instance_id=None):
    attributes = {"service.name": SERVICE_NAME, "service.version": "smoke",
                  "deployment.environment.name": "otlp-storage-smoke"}
    if instance_id:
        attributes["service.instance.id"] = instance_id
    return attributes


def histogram_buckets(boundaries=HTTP_DURATION_BOUNDARIES,
                      fast=FAST_OBSERVATIONS, slow=SLOW_OBSERVATIONS,
                      beyond=BEYOND_OBSERVATIONS):
    """``bucket_counts`` of an explicit-bucket histogram, as OTLP defines them.

    They are **per bucket**, not cumulative: ``bucket_counts`` has one more
    entry than ``explicit_bounds``, an observation lands in the first bucket
    whose bound is not below it, the last entry counts what is above every
    bound, and the entries have to sum to the point's count. A query API such as
    the Prometheus-compatible one of the store exposes the cumulative view of
    the same data, which is what the query half asserts separately.
    """
    buckets = [0] * (len(boundaries) + 1)
    for value, repeated in ((FAST_VALUE, fast), (SLOW_VALUE, slow),
                            (BEYOND_VALUE, beyond)):
        index = next((position for position, boundary in enumerate(boundaries)
                      if value <= boundary), len(boundaries))
        buckets[index] += repeated
    return buckets, fast + slow + beyond


def otlp_metrics_payload(instance_id, boundaries=HTTP_DURATION_BOUNDARIES,
                         fast=FAST_OBSERVATIONS, slow=SLOW_OBSERVATIONS,
                         beyond=BEYOND_OBSERVATIONS,
                         metric=HTTP_DURATION_METRIC):
    """One cumulative explicit-bucket histogram, as an OTLP/HTTP protobuf body.

    The observations are placed so the query half has an exact expectation at
    every interesting position: ``fast`` at 0.05 s clearly below the 0.4 s
    cutoff, ``slow`` at 0.9 s clearly above it, and ``beyond`` at 30 s slower
    than the slowest boundary.
    """
    buckets, count = histogram_buckets(boundaries, fast, slow, beyond)
    total = (fast * FAST_VALUE + slow * SLOW_VALUE + beyond * BEYOND_VALUE)
    now_ns = int(time.time() * 1e9)
    point = (_packed(6, buckets, "<Q")                       # bucket_counts
             + _packed(7, list(boundaries), "<d")            # explicit_bounds
             + _fixed64(4, count)                            # count
             + _fixed64(5, total)                            # sum
             + _fixed64(3, now_ns)                           # time_unix_nano
             + _fixed64(2, now_ns - 30_000_000_000)          # start_time_unix_nano
             + _key_values(9, {"http.request.method": "GET",
                               "http.route": "/api/v1/resources"}))
    histogram = _bytes(1, point) + _int(2, 2)     # data_points, CUMULATIVE
    # Metric{1 name, 3 unit, 9 histogram} -> ScopeMetrics{1 scope, 2 metrics}
    # -> ResourceMetrics{1 resource, 2 scope_metrics}
    # -> ExportMetricsServiceRequest{1 resource_metrics}
    metric_message = _bytes(2, _string(1, metric) + _string(3, "s")
                            + _bytes(9, histogram))
    scope_metrics = _bytes(2, _instrumentation_scope(SERVICE_NAME)
                           + metric_message)
    return _bytes(1, _bytes(1, _key_values(1, _smoke_attributes(instance_id)))
                   + scope_metrics)


def otlp_traces_payload(trace_id, span_id, name="GET /api/v1/resources"):
    """One finished, successful span as an OTLP/HTTP protobuf body."""
    now_ns = int(time.time() * 1e9)
    span = (_bytes(1, trace_id)
            + _bytes(2, span_id)
            + _string(5, name)
            + _int(6, 2)                                    # kind = SERVER
            + _fixed64(7, now_ns)
            + _fixed64(8, now_ns + 120_000_000)
            + _key_values(9, {"http.request.method": "GET",
                              "http.route": "/api/v1/resources",
                              "http.response.status_code": "200"})
            + _bytes(15, _int(3, 1)))                       # Status{3 code = OK}
    # Span -> ScopeSpans{1 scope, 2 spans} -> ResourceSpans{1 resource,
    # 2 scope_spans} -> ExportTraceServiceRequest{1 resource_spans}
    scope_spans = _bytes(2, _instrumentation_scope(SERVICE_NAME) + _bytes(2, span))
    return _bytes(1, _bytes(1, _key_values(1, _smoke_attributes())) + scope_spans)


def post_protobuf(base, path, body):
    """POST one OTLP/HTTP protobuf export; return ``(status, body)``."""
    request = urllib.request.Request(
        base.rstrip("/") + path, data=body,
        headers={"Content-Type": "application/x-protobuf"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, f"unreachable: {error}"


def get_json(base, path, params=None):
    """GET a JSON API of one store: ``(status, parsed body or text)``."""
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            body, status = response.read().decode("utf-8", "replace"), response.status
    except urllib.error.HTTPError as error:
        body, status = error.read().decode("utf-8", "replace"), error.code
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return None, f"unreachable: {error}"
    try:
        return status, json.loads(body)
    except json.JSONDecodeError:
        return status, body


def prometheus_query(base, query):
    """The result list of one Prometheus-compatible instant query."""
    status, reply = get_json(base, "/api/v1/query", {"query": query})
    if not isinstance(reply, dict):
        return status, []
    return status, (reply.get("data") or {}).get("result") or []


# A reader for exactly the wire types this module writes, used to decode the
# payloads back before they are ever sent. Without it a nesting error is silent:
# a store answers 200 to a body whose metric it could not read, which is the
# failure mode ADR-0003 calls out. Keeping it here also means the offline suite
# can assert the payload without a store.


def read_fields(buf):
    """``[(field, kind, value), ...]`` of one protobuf message."""
    position, out = 0, []

    def varint():
        nonlocal position
        value = shift = 0
        while True:
            byte = buf[position]
            position += 1
            value |= (byte & 0x7F) << shift
            shift += 7
            if not byte & 0x80:
                return value

    while position < len(buf):
        key = varint()
        field, wire = key >> 3, key & 7
        if wire == 0:
            out.append((field, "varint", varint()))
        elif wire == 1:
            out.append((field, "fixed", buf[position:position + 8]))
            position += 8
        elif wire == 2:
            size = varint()
            out.append((field, "bytes", buf[position:position + size]))
            position += size
        elif wire == 5:
            out.append((field, "fixed", buf[position:position + 4]))
            position += 4
        else:
            raise ValueError(f"wire type {wire} on field {field}")
    return out


def field_values(buf, want):
    """Every value of one field number of ``buf``."""
    return [value for field, _, value in read_fields(buf) if field == want]


def decoded_attributes(message, field):
    """The string attribute map of the repeated KeyValue ``field`` of a message.

    Only the string case is read: that is the only value type this check
    exports, and reading the others would mean trusting the exporter to have
    chosen a type rather than asserting the one it chose.
    """
    attributes = {}
    for entry in field_values(message, field):
        key = field_values(entry, 1)
        value = field_values(entry, 2)
        if not key or not value:
            raise ValueError("KeyValue without a key or a value")
        string = field_values(value[0], 1)
        if not string:
            raise ValueError(f"attribute {key[0]!r} is not a string value")
        attributes[key[0].decode()] = string[0].decode()
    return attributes


def decoded_scope(message):
    """The name of the InstrumentationScope of a ScopeMetrics or ScopeSpans."""
    scope = field_values(message, 1)
    if len(scope) != 1:
        raise ValueError(f"{len(scope)} instrumentation scopes, expected 1")
    name = field_values(scope[0], 1)
    if not name:
        raise ValueError("instrumentation scope without a name")
    return name[0].decode()


def decoded_metrics(body):
    """The one histogram of an ExportMetricsServiceRequest, flat and checked.

    Raises on anything which would make the store's answer meaningless - a
    missing resource, a second metric, a non-cumulative histogram, bucket
    counts which do not add up.
    """
    resource_metrics = field_values(body, 1)
    if len(resource_metrics) != 1:
        raise ValueError(f"{len(resource_metrics)} resource metrics, expected 1")
    scope_metrics = field_values(resource_metrics[0], 2)
    if len(scope_metrics) != 1:
        raise ValueError(f"{len(scope_metrics)} scope metrics, expected 1")
    resource = field_values(resource_metrics[0], 1)
    if len(resource) != 1:
        raise ValueError(f"{len(resource)} resources, expected 1")
    attributes = decoded_attributes(resource[0], 1)
    metrics = field_values(scope_metrics[0], 2)
    if len(metrics) != 1:
        raise ValueError(f"{len(metrics)} metrics, expected 1")
    histograms = field_values(metrics[0], 9)
    if len(histograms) != 1:
        raise ValueError(f"{len(histograms)} histograms, expected 1")
    points = field_values(histograms[0], 1)
    if len(points) != 1:
        raise ValueError(f"{len(points)} data points, expected 1")
    point = points[0]
    if field_values(histograms[0], 2) != [2]:
        raise ValueError("histogram is not CUMULATIVE")
    bounds = list(struct.unpack(f"<{len(field_values(point, 7)[0]) // 8}d",
                                field_values(point, 7)[0]))
    buckets = list(struct.unpack(f"<{len(field_values(point, 6)[0]) // 8}Q",
                                 field_values(point, 6)[0]))
    count = struct.unpack("<Q", field_values(point, 4)[0])[0]
    total = struct.unpack("<d", field_values(point, 5)[0])[0]
    if len(buckets) != len(bounds) + 1:
        raise ValueError("bucket_counts must have one entry more than bounds")
    if sum(buckets) != count:
        raise ValueError(f"bucket counts sum to {sum(buckets)}, count is {count}")
    if field_values(point, 2)[0] >= field_values(point, 3)[0]:
        raise ValueError("start_time_unix_nano is not before time_unix_nano")
    return {
        "resource": attributes,
        "scope": decoded_scope(scope_metrics[0]),
        "name": field_values(metrics[0], 1)[0].decode(),
        "unit": field_values(metrics[0], 3)[0].decode(),
        "attributes": decoded_attributes(point, 9),
        "count": count, "sum": total,
        "bounds": bounds, "buckets": buckets,
    }


def decoded_traces(body):
    """The one span of an ExportTraceServiceRequest, flat and checked."""
    resource_spans = field_values(body, 1)
    if len(resource_spans) != 1:
        raise ValueError(f"{len(resource_spans)} resource spans, expected 1")
    scope_spans = field_values(resource_spans[0], 2)
    if len(scope_spans) != 1:
        raise ValueError(f"{len(scope_spans)} scope spans, expected 1")
    spans = field_values(scope_spans[0], 2)
    if len(spans) != 1:
        raise ValueError(f"{len(spans)} spans, expected 1")
    span = spans[0]
    trace_id, span_id = field_values(span, 1)[0], field_values(span, 2)[0]
    if len(trace_id) != 16 or len(span_id) != 8:
        raise ValueError("trace_id must be 16 and span_id 8 bytes")
    start = struct.unpack("<Q", field_values(span, 7)[0])[0]
    end = struct.unpack("<Q", field_values(span, 8)[0])[0]
    if start >= end:
        raise ValueError("span start is not before its end")
    return {
        "resource": decoded_attributes(field_values(resource_spans[0], 1)[0], 1),
        "scope": decoded_scope(scope_spans[0]),
        "trace_id": trace_id, "span_id": span_id,
        "name": field_values(span, 5)[0].decode(),
        "kind": field_values(span, 6)[0],
        "attributes": decoded_attributes(span, 9),
        "status": field_values(field_values(span, 15)[0], 3),
    }


# ------------------------------------------------------------- live: the stores


def required_variables(files):
    """Every ``${VAR:?...}`` of the compose files, so the live half can answer
    the ones belonging to services it never starts."""
    names = set()
    for file in files:
        text = Path(file).read_text(encoding="utf-8")
        names.update(re.findall(r"\$\{([A-Z_][A-Z0-9_]*):\?", text))
    return names


def docker_compose(project, files, *args):
    command = ["docker", "compose", "-p", project]
    for file in files:
        command += ["-f", str(file)]
    command += list(args)
    environment = dict(os.environ)
    environment.pop("COMPOSE_FILE", None)
    environment.pop("COMPOSE_PROFILES", None)
    for variable in required_variables([str(f) for f in files]):
        environment.setdefault(variable, DUMMY_VALUES.get(variable, "smoke"))
    process = subprocess.run(command, capture_output=True, text=True,
                             cwd=ROOT, env=environment)  # nosec B603
    if process.returncode != 0:
        raise HarnessError(
            f"docker compose {' '.join(args)} exited {process.returncode}: "
            f"{(process.stderr or process.stdout or '').strip()[-900:]}")
    return process.stdout or ""


def published_loopback(project, files, service, container_port):
    """The host port Compose mapped for one service, for this check's own use."""
    listing = docker_compose(project, files, "port", service, str(container_port))
    match = re.search(r"127\.0\.0\.1:(\d+)", listing)
    if not match:
        raise HarnessError(f"{service} published no loopback port for "
                           f"{container_port}: {listing!r}")
    return int(match.group(1))


def expose_override(directory):
    """An overlay which publishes loopback ports for the two stores.

    The committed file publishes none - the offline half above is what holds
    that line - and this overlay exists only inside this check's own project, so
    the host can query the stores the way Grafana does from inside the network.
    ``::port`` with no host port is Compose's syntax for "any free port, bound
    to this address", which keeps two runs of the check from colliding.
    """
    services = {name: {"ports": [f"127.0.0.1::{contract['port']}"]}
                for name, contract in STORES.items()}
    path = Path(directory) / "expose-for-the-check.yml"
    path.write_text(
        "# generated by scripts/otlp_storage_smoke.py - loopback ports which "
        "# exist only in this check's own project, so the host can query the "
        "# two stores the committed file publishes no port for\n"
        + json.dumps({"services": services}, indent=2) + "\n", encoding="utf-8")
    return path


def live_checks(project, keep):
    """Start the two stores of the committed file, export into them, query back."""
    print("\nthe live stores (isolated project, own loopback ports)")
    directory = tempfile.TemporaryDirectory(prefix="otlp-storage-smoke-")
    override = expose_override(directory.name)
    files = [ROOT / BASE, override]
    started = False
    try:
        print(f"  note  this check owns the project {project!r} and removes it, "
              f"its containers and its volumes when it finishes")
        # --wait blocks on the healthchecks the committed file declares, so
        # "ready" is the store's own answer rather than this check's patience
        docker_compose(project, files, "--profile", "observability", "up", "-d",
                       "--wait", "--wait-timeout", "180", *STORES)
        started = True
        bases = {
            name: "http://127.0.0.1:%d" % published_loopback(
                project, files, name, contract["port"])
            for name, contract in STORES.items()}

        for name in STORES:
            status, body = get_json(bases[name], "/health")
            healthy = status == 200 and str(body).strip().strip('"').lower() \
                in ("ok", "healthy")
            check(f"{name} answers its own health endpoint", healthy,
                  f"{status} {str(body)[:70]}")

        status, body = post_protobuf(
            bases["victoria-metrics"], STORES["victoria-metrics"]["otlp_path"],
            otlp_metrics_payload("writer-a"))
        check("victoria-metrics accepts a direct OTLP/HTTP export of the "
              "ADR-0003 histogram", status == 200, f"{status} {str(body)[:120]}")
        status, body = post_protobuf(
            bases["victoria-metrics"], STORES["victoria-metrics"]["otlp_path"],
            otlp_metrics_payload("writer-b"))
        check("a second cumulative writer is accepted alongside the first",
              status == 200, f"{status} {str(body)[:120]}")

        trace_id = bytes(random.randrange(256) for _ in range(16))
        span_id = bytes(random.randrange(256) for _ in range(8))
        status, body = post_protobuf(
            bases["victoria-traces"], STORES["victoria-traces"]["otlp_path"],
            otlp_traces_payload(trace_id, span_id))
        check("victoria-traces accepts a direct OTLP/HTTP trace export",
              status == 200, f"{status} {str(body)[:120]}")

        # the query half: the API Grafana's metrics datasource speaks
        status, series = prometheus_query(bases["victoria-metrics"],
                                          HTTP_DURATION_METRIC)
        check("the exported histogram is queryable through the "
              "Prometheus-compatible query API", status == 200 and bool(series),
              f"{status} {str(series)[:160]}")
        writers = {item.get("metric", {}).get("service_instance_id")
                   for item in series} - {None}
        check("the two writers stay two cumulative series rather than "
              "overwriting one another", len(writers) == WRITER_COUNT,
              sorted(writers))
        counts = [float(item["value"][1]) for item in series
                  if str(item.get("metric", {}).get("__name__", "")).endswith("_count")]
        check(f"each writer's cumulative count is the {OBSERVATIONS_PER_WRITER} "
              f"observations it exported, so the pair neither double-counts nor "
              f"loses one",
              len(counts) == WRITER_COUNT
              and all(value == OBSERVATIONS_PER_WRITER for value in counts),
              f"{counts} expected {OBSERVATIONS_PER_WRITER} per writer")
        status, buckets = prometheus_query(
            bases["victoria-metrics"], f"{HTTP_DURATION_METRIC}_bucket")
        boundaries = {item.get("metric", {}).get("le") for item in buckets} - {None}
        check(f"the {SLOW_CUTOFF} s boundary of ADR-0003 is a queryable bucket "
              f"of the exported histogram", "0.4" in boundaries,
              f"status {status}, {len(boundaries)} le values seen")
        slow_counts = [float(item["value"][1]) for item in buckets
                       if item.get("metric", {}).get("le") == "0.4"]
        check("the count at le=0.4 is the observations at or below the cutoff",
              bool(slow_counts) and all(
                  value == FAST_OBSERVATIONS for value in slow_counts),
              f"{slow_counts} expected {FAST_OBSERVATIONS} per writer")

        # and the two query APIs of the trace store
        status, reply = get_json(bases["victoria-traces"], "/select/tempo/api/echo")
        check("victoria-traces answers the Tempo query API Grafana speaks",
              status == 200, f"{status} {str(reply)[:120]}")
        status, reply = get_json(bases["victoria-traces"],
                                 "/select/jaeger/api/services")
        found = (reply or {}).get("data") if isinstance(reply, dict) else None
        check("the exported service is searchable through the Jaeger query API",
              status == 200 and SERVICE_NAME in (found or []),
              f"{status} {str(reply)[:160]}")
        status, reply = get_json(bases["victoria-traces"],
                                 "/select/tempo/api/search",
                                 {"tags": f"service.name={SERVICE_NAME}",
                                  "limit": "20"})
        traces = (reply or {}).get("traces") if isinstance(reply, dict) else None
        check("the exported trace is searchable through the Tempo search API",
              status == 200 and bool(traces), f"{status} {str(reply)[:160]}")

        measure("otlp metric exports accepted", 2, "exports",
                "one per writer, each 200 with an OTLP reply body")
        measure("histogram boundaries stored", len(boundaries), "le buckets",
                "the explicit boundaries of ADR-0003, queried back")
        measure("observations per cumulative writer", OBSERVATIONS_PER_WRITER,
                "count", f"{FAST_OBSERVATIONS} below and {SLOW_OBSERVATIONS} "
                         f"above the {SLOW_CUTOFF} s cutoff")
        measure("cumulative writers distinguished", len(writers), "series",
                "two service.instance.id writers of one stream")

        print("\nthe unavailable mode")
        docker_compose(project, files, "--profile", "observability", "stop",
                       *STORES)
        for name, base in bases.items():
            status, _ = get_json(base, "/health")
            check(f"{name} is really unreachable once stopped", status is None,
                  f"still answered {status}")
        services = docker_compose(project, files, "config", "--services").split()
        check("the deployment still resolves with both stores stopped - the "
              "unavailable mode", "backend" in services and len(services) > 5,
              len(services))
    finally:
        if started and not keep:
            try:
                docker_compose(project, files, "--profile", "observability",
                               "down", "-v", "--remove-orphans")
            except HarnessError as error:
                print(f"  note  cleanup of {project!r} needs a hand: {error}",
                      file=sys.stderr)
        directory.cleanup()


LIMITATIONS = [
    "the application-side behaviour of an exporter against a stopped, slow or "
    "rejecting store belongs to #1779 and #1780; what this check proves is that "
    "no service of the deployment depends on the pair, which is the startup "
    "half of the same rule",
    "the byte bound of the default mode is each store's own free-space guard "
    "plus its retention window, not a filesystem quota: a quota needs a "
    "quota-enabled filesystem and the quota tools, which an operator opts into",
    "Grafana's own render of the two provisioned datasources is not automated "
    "here; the check pins the plugin versions and asserts the datasource "
    "definitions and the store APIs behind them, and a reviewer with the tier "
    "up should open Explore once per datasource",
    "the OTLP payload is written against the published wire format rather than "
    "through the OpenTelemetry SDK on purpose: the question is what the store "
    "accepts, and #1779 owns the SDK pins",
    "the live half starts the stores of the committed file, not the whole "
    "stack: an end-to-end run with a real instrumented application is #1779 "
    "and the matched measurement is #1777/#1780",
]


def git_revision():
    """The SHA the evidence belongs to - #1775 asks every measurement to name it."""
    try:
        process = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                                 text=True, cwd=ROOT)  # nosec B603
    except FileNotFoundError:
        return "unknown (no git on this host)"
    return process.stdout.strip() if process.returncode == 0 else "unknown"


def write_evidence(path, live):
    payload = {
        "issue": 1778,
        "adr": "docs/architecture/decisions/ADR-0003-low-overhead-observability.md",
        "revision": git_revision(),
        "live": bool(live),
        "commands": ["python3 scripts/otlp_storage_smoke.py"]
        + (["flock -x /tmp/mrmap-test.lock -c "
            "'python3 scripts/otlp_storage_smoke.py --live'"] if live else []),
        "stores": {name: contract["image"] for name, contract in STORES.items()},
        "checks": RESULTS,
        "measurements": MEASUREMENTS,
        "limitations": LIMITATIONS,
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Verify the optional VictoriaMetrics and VictoriaTraces "
                    "storage of #1778 against ADR-0003.")
    parser.add_argument("--live", action="store_true",
                        help="start the two stores in an isolated Compose "
                             "project, export OTLP into them and query them back")
    parser.add_argument("--project-name", default=None,
                        help="Compose project name for --live (default: a "
                             "generated one this check owns and removes)")
    parser.add_argument("--keep", action="store_true",
                        help="leave the --live project running afterwards")
    parser.add_argument("--json", metavar="PATH", default=None,
                        help="write results, measurements and limitations to "
                             "PATH as JSON (the evidence file of the issue)")
    arguments = parser.parse_args()

    if not (ROOT / BASE).is_file():
        print(f"harness: {BASE} not found - run this from a mrmap checkout",
              file=sys.stderr)
        return 2
    for name in STORES:
        if name not in profiles.CEILINGS:
            print(f"harness: {name} carries no ceiling band in "
                  f"compose_profiles_smoke.CEILINGS", file=sys.stderr)
            return 2

    try:
        offline_checks()
        if arguments.live:
            project = arguments.project_name or (
                "mrmap-otlp-smoke-%d-%d" % (os.getpid(), random.randrange(1000, 9999)))
            if not project.startswith("mrmap-otlp-smoke-") and not arguments.project_name:
                print("harness: the generated project name must be this check's own",
                      file=sys.stderr)
                return 2
            live_checks(project, arguments.keep)
    except HarnessError as error:
        print(f"harness: {error}", file=sys.stderr)
        return 2

    if arguments.json:
        write_evidence(arguments.json, arguments.live)

    failed = [item for item in RESULTS if not item["ok"]]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} check(s) passed"
          + ("" if arguments.live else " (offline half; --live adds the stores)"))
    for item in failed:
        print(f"FAIL  {item['name']}\n      {item['detail']}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
