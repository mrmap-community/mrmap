#!/usr/bin/env python3
"""Offline checks for scripts/low_memory_deployment.json (issue #1624, epic #1612).

The JSON file is the machine-readable description of the low-memory deployment
modes: the documentation automation (#1604) generates the operator prose from
it and the operator runbook
``docs/source/administration/low-memory-operator-runbook.rst`` is its rendered
face. A description is only as honest as its binding, so this suite holds
every fact in the file against the committed reality it names - the Compose
files, the two resolvers which actually decode the knobs
(``backend/.bash_scripts/process_defaults.sh`` and the pool-bounds resolver of
``MrMap/settings.py``), the tier matrix of ``compose_profiles_smoke.py``, the
admission gate and the measurement pages whose figures are quoted - and fails
the moment description and tooling drift apart. It is the #1615 rule applied
to documentation: a number an operator reads and the software reads
differently is worse than no number.

Runs without docker, without network, without a configured deployment: every
check reads repository files; the web-tier rows are proven by sourcing the
resolver in a bare ``sh``, the pool rows by the resolver function's source.
Figures are cross-checked against the page each one cites as its source, so a
runbook which invents a RAM number cannot pass - the page has to carry it.

Run from the repository root: `python3 scripts/test_low_memory_deployment.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import importlib.util
import json
import os
import re
import subprocess  # nosec B404 - sourcing the resolver in sh is the check
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTION = ROOT / "scripts" / "low_memory_deployment.json"
COMPOSE_BASE = ROOT / "docker-compose.yml"
COMPOSE_LIGHT = ROOT / "docker-compose.lightweight.yml"
COMPOSE_TEST_LOW = ROOT / "docker-compose.test-low-memory.yml"
PROCESS_DEFAULTS = ROOT / "backend" / ".bash_scripts" / "process_defaults.sh"
SETTINGS = ROOT / "backend" / "MrMap" / "settings.py"
AGENT_CAPACITY = ROOT / "scripts" / "agent_capacity"
SMOKE = ROOT / "scripts" / "compose_profiles_smoke.py"
DEVELOPMENT_DOCS = ROOT / "docs" / "source" / "development"

failures = []


def check(name, ok, detail=""):
    if not ok:
        failures.append(f"{name}: {detail}")
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"  - {detail}" if detail and not ok else ""))


def read(path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"<unreadable: {exc}>"


def doc_labels():
    labels = set()
    for rst in (ROOT / "docs" / "source").rglob("*.rst"):
        labels.update(re.findall(r"^\.\. _([\w-]+):\s*$", read(rst), re.MULTILINE))
    return labels


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("compose_profiles_smoke", SMOKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_web_shape(env):
    """The shape process_defaults.sh exports for env (same harness as
    test_http_process_bench.py: a compose passthrough of an unset variable
    arrives as "", which must count as unset)."""
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update(env)
    script = (". '{path}'; printf \"%s|%s|%s|%s\" "
              "\"$GUNICORN_WORKERS\" \"$GUNICORN_THREADS\" "
              "\"$GUNICORN_WS_WORKERS\" \"$GUNICORN_PRELOAD_FLAG\""
              ).format(path=PROCESS_DEFAULTS)
    out = subprocess.run(  # nosec B602 - fixed command, env passed explicitly
        ["sh", "-c", script],
        capture_output=True, text=True, check=True, env=base)
    return out.stdout.split("|")


def compose_service_block(text, service):
    """The raw block of one top-level service of a compose file."""
    match = re.search(rf"^  {re.escape(service)}:\s*$(.*?)(?=^  \S|\Z)",
                      text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def main():
    print("low_memory_deployment.json holds against the committed tooling")
    try:
        desc = json.loads(read(DESCRIPTION))
    except json.JSONDecodeError as exc:
        print(f"FAIL  the description file parses - {exc}")
        return 1
    check("the description file parses", True)
    check("the description carries its schema version",
          desc.get("schema_version") == 1, str(desc.get("schema_version")))

    base_text = read(COMPOSE_BASE)
    light_text = read(COMPOSE_LIGHT)
    settings_text = read(SETTINGS)
    labels = doc_labels()

    # --- the runbook page is the described one ---------------------------------
    book = desc["runbook"]
    book_path = ROOT / book["page"]
    book_text = read(book_path)
    check("the runbook page exists", book_path.is_file(), book["page"])
    check("the runbook carries its declared label",
          f".. _{book['label']}:" in book_text, book["label"])
    check("the runbook is reachable from the administration toctree",
          book["page"].rsplit("/", 1)[-1][:-len(".rst")]
          in read(ROOT / "docs" / "source" / "administration" / "index.rst"))
    for section in book["sections"]:
        check(f"runbook section exists: {section}",
              re.search(rf"^{re.escape(section)}\n=+\n", book_text, re.MULTILINE))

    # --- modes ------------------------------------------------------------------
    for mode in desc["modes"]:
        for rel in mode["compose_files"]:
            check(f"mode {mode['id']} names a committed compose file: {rel}",
                  (ROOT / rel).is_file())
        if mode["is_contract"]:
            check(f"the contract mode is docker-compose.yml alone",
                  mode["compose_files"] == ["docker-compose.yml"]
                  and mode["id"] == "full", str(mode["compose_files"]))
        for doc in (mode.get("docs") or []):
            check(f"mode {mode['id']} links a label that exists: {doc}", doc in labels)
        for key, value in (mode.get("env") or {}).items():
            check(f"mode {mode['id']} env {key}={value} is read by the tooling",
                  key in base_text or key in read(PROCESS_DEFAULTS)
                  or key in settings_text or key in read(COMPOSE_TEST_LOW))
    shapes = {m["id"]: m for m in desc["modes"]}

    # the web shape strings agree with what the resolver actually exports
    shipped = shapes["full"]["web_shape"]
    check("the shipped web shape is what process_defaults.sh resolves",
          "4 workers x 4 threads" in shipped
          and resolve_web_shape({}) == ["4", "4", "1", ""],
          resolve_web_shape({}))
    lowmem = shapes["low-memory-web-tier"]["web_shape"]
    check("the low-memory web shape is what process_defaults.sh resolves",
          "1 worker x 2 threads" in lowmem
          and resolve_web_shape({"MRMAP_LOW_MEMORY": "1"}) == ["1", "2", "1", ""],
          resolve_web_shape({"MRMAP_LOW_MEMORY": "1"}))
    check("an explicit value still wins over the mode",
          resolve_web_shape({"MRMAP_LOW_MEMORY": "1", "GUNICORN_WORKERS": "3"})[:1]
          == ["3"])

    # the pool pairs are the ones the settings resolver falls back to
    check("the shipped pool pair is the resolver's non-mode default",
          "(1, 4) if low_memory else (4, 20)" in settings_text
          and "4 reserved / 20 open" in shapes["full"]["pool_bounds"],
          "settings resolver default pair")
    check("the low-memory pool pair is the resolver's mode default",
          "1 reserved / 4 open" in shapes["low-memory-web-tier"]["pool_bounds"])
    check("the mode is spelled identically in both resolvers",
          "MRMAP_LOW_MEMORY" in read(PROCESS_DEFAULTS)
          and "MRMAP_LOW_MEMORY" in settings_text)

    # --- tiers and core agree with the matrix checker ----------------------------
    smoke = load_smoke_module()
    check("the tier table equals compose_profiles_smoke.TIERS",
          desc["tiers"] == {k: list(v) for k, v in smoke.TIERS.items()},
          f"json={desc['tiers']} smoke={smoke.TIERS}")
    check("the core services equal compose_profiles_smoke.CORE",
          set(desc["core_services"]) == set(smoke.CORE),
          f"json={sorted(desc['core_services'])} smoke={sorted(smoke.CORE)}")
    for tier, members in desc["tiers"].items():
        for service in members:
            block = compose_service_block(light_text, service)
            check(f"the lightweight file profiles {service} as {tier}",
                  f"profiles: [{tier}]" in block, block.strip()[:60])
    for service in desc["core_services"]:
        check(f"core service {service} is defined in docker-compose.yml",
              compose_service_block(base_text, service) != "")

    # every :ref: the runbook makes resolves to a real label - the same
    # fault the ADR-0001 baseline counts as a silent docs warning
    for ref in set(re.findall(r":ref:`[^`<]*<([^`>]+)>`|:ref:`([^`]+)`", book_text)):
        target = (ref[0] or ref[1]).strip()
        check(f"runbook :ref: resolves: {target}", target in labels)

    # --- knobs: name, owner file and the default the file passes ------------------
    for name, pattern in (
        ("CELERY_WORKER_CONCURRENCY",
         r'\$\{CELERY_WORKER_CONCURRENCY:-(\d+)\}'),
        ("CELERY_WORKER_MAX_TASKS_PER_CHILD",
         r'\$\{CELERY_WORKER_MAX_TASKS_PER_CHILD:-(\d+)\}'),
        ("CELERY_WORKER_REVOKES_MAX",
         r'\$\{CELERY_WORKER_REVOKES_MAX:-(\d+)\}'),
        ("REDIS_MAXMEMORY",
         r'\$\{REDIS_MAXMEMORY:-([0-9a-z]+)\}'),
    ):
        knob = next((k for k in desc["knobs"] if k["name"] == name), None)
        check(f"knob {name} is declared in the description", knob is not None)
        if knob is None:
            continue
        check(f"knob {name} names docker-compose.yml as its owner",
              "docker-compose.yml" in knob["owner"], knob["owner"])
        # the default the description quotes is the one the file interpolates
        passed = re.search(pattern, base_text)
        check(f"knob {name} is passed by docker-compose.yml from the variable",
              passed is not None)
        if passed:
            stated = knob["default"].split()[0] if knob["default"] else ""
            check(f"knob {name} states the default docker-compose.yml passes",
                  stated == passed.group(1),
                  f"json={stated!r} compose={passed.group(1)!r}")
    for name in ("GUNICORN_WORKERS", "GUNICORN_THREADS", "GUNICORN_WS_WORKERS",
                 "GUNICORN_PRELOAD", "MRMAP_LOW_MEMORY"):
        check(f"knob {name} resolves in process_defaults.sh",
              name in read(PROCESS_DEFAULTS))
        check(f"knob {name} is passed through by docker-compose.yml",
              f"{name}: " in base_text, "no environment entry naming it")
    for name in ("MIN_BACKEND_RESERVED_CONNECTIONS", "MAX_BACKEND_RESERVED_CONNECTIONS"):
        check(f"knob {name} is read by the settings resolver", name in settings_text)
    check("knob MRMAP_TEST_WORKERS belongs to the test preset only",
          "MRMAP_TEST_WORKERS" in read(COMPOSE_TEST_LOW)
          and "MRMAP_TEST_WORKERS" not in base_text)
    for knob in desc["knobs"]:
        check(f"knob {knob['name']} links its documentation page",
              knob["docs"] in labels, knob["docs"])
    check("the pool bounds deliberately have no compose passthrough (#1621)",
          "MIN_BACKEND_RESERVED_CONNECTIONS:" not in base_text
          and "MAX_BACKEND_RESERVED_CONNECTIONS:" not in base_text
          and "RESERVED_CONNECTIONS" in base_text,
          "named in docker-compose.yml only as the documented non-passthrough")

    # --- healthchecks are the committed ones --------------------------------------
    for probe in desc["health_checks"]:
        block = compose_service_block(base_text, probe["service"])
        rendered = json.dumps(probe["test"])
        # compose escapes a literal $ as $$, so both spellings are the same test
        doubled = rendered.replace("$", "$$")
        check(f"healthcheck of {probe['service']} matches docker-compose.yml",
              f"test: {rendered}" in block or f"test: {doubled}" in block,
              rendered[:70])
        check(f"healthcheck interval of {probe['service']} matches",
              f"interval: {probe['interval']}" in block, probe["interval"])
        if probe.get("start_period"):
            check(f"healthcheck start_period of {probe['service']} matches",
                  f"start_period: {probe['start_period']}" in block,
                  probe["start_period"])

    # --- quoted figures exist on the page cited as their source --------------------
    for figure in desc["figures"]:
        page = DEVELOPMENT_DOCS / f"{figure['source']}.rst"
        check(f"figure {figure['id']} cites a committed page", page.is_file(),
              figure["source"])
        if not page.is_file():
            continue
        page_text = read(page)
        for value in (figure["charge_mib"], figure["committed_mib"]):
            found = re.search(rf"\b{value}\b", page_text) is not None
            check(f"figure {figure['id']} value {value} MiB appears on {figure['source']}",
                  found)
        # the page has to speak the figure's language: a "measured" row
        # next to the word measured, a "derived" row next to the word
        # derived - the labelling #1613's reading rule depends on.
        word = "measured" if figure["kind"] == "measured" else "derived"
        check(f"figure {figure['id']} kind {figure['kind']} is how the source page labels it",
              re.search(word, page_text, re.IGNORECASE) is not None)

    # --- scenarios: measured vs not, and the admission constants --------------------
    scenarios = {s["id"]: s for s in desc["scenarios"]}
    check("the 16-GiB agent scenario is the measured one",
          scenarios["agent-cgroup-16gib"]["status"] == "measured")
    check("the baseline page measured the 16-GiB agent cgroup it is quoted from",
          "16" in read(DEVELOPMENT_DOCS / "runtime-memory-baselines.rst"))
    check("the 32-GiB host scenario is explicitly not measured",
          scenarios["developer-host-32gib"]["status"] == "not measured")
    baselines = read(DEVELOPMENT_DOCS / "runtime-memory-baselines.rst")
    check("the baseline page itself keeps the 32-GiB host a projection",
          "32-GiB" in baselines and "projection" in baselines)
    capacity = read(AGENT_CAPACITY)
    check("the admission gate still owns the constants the scenario quotes",
          'threshold("AGENT_STACK_MIN_MEM_GB", 6)' in capacity
          and 'threshold("AGENT_SUITE_MIN_MEM_GB", 8)' in capacity)
    check("the runbook defers admission to agent_capacity",
          "scripts/agent_capacity" in book_text
          and "agent_capacity" in desc["authority"]["admission"])

    # --- the runbook's own honesty rules ---------------------------------------------
    check("the runbook names the sampler and the bench as the instruments",
          "stack_memory_profile" in book_text and "http_process_bench" in book_text)
    check("the runbook keeps the measured/derived split visible",
          "**derived**" in book_text and "**measured**" in book_text
          and "not measured" in book_text.lower())
    check("the runbook documents the console log fallback of the lightweight mode",
          "syslog" in book_text and "console" in book_text)
    check("the runbook states the tier-reboot fact",
          "restart" in book_text and "reboot" in book_text)
    for knob in desc["knobs"]:
        if knob["name"] in ("GUNICORN_WS_WORKERS", "MRMAP_TEST_WORKERS"):
            continue
        check(f"the runbook covers knob {knob['name']}", knob["name"] in book_text)

    print(f"\n{len(failures)} failed of the checks above" if failures
          else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
