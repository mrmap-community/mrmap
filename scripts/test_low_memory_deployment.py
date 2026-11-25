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
import shlex
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


def list_table_rows(text, key_column, columns):
    """Rows of the unique reST ``list-table`` keyed by ``key_column`` and
    carrying ``columns``, parsed one cell per ``* -``/``- `` line with
    continuation lines appended to the cell they belong to.

    Figures bind to a ROW and a COLUMN, not to a page: a budget table carries
    a dozen configurations, and a number that merely appears somewhere on the
    page says nothing about which configuration was quoted - the exact slip
    class this page exists to prevent.
    """
    key = key_column.strip()
    wanted = [c.strip() for c in columns]
    tables = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not lines[i].lstrip().startswith(".. list-table"):
            i += 1
            continue
        j, rows, cell = i + 1, [], None
        while j < len(lines):
            line = lines[j]
            if line.startswith("   :") or not line.strip():
                j += 1
                continue
            first = re.match(r"^   \* - (.*)$", line)
            rest = re.match(r"^     -(?: (.*))?$", line)
            if first:
                cell = [first.group(1).strip()]
                rows.append(cell)
            elif cell is not None and rest:
                cell.append((rest.group(1) or "").strip())
            elif cell is not None and line.startswith("       ") and line.strip():
                cell[-1] += " " + line.strip()
            else:
                break
            j += 1
        if rows and rows[0][0].strip() == key and all(c in rows[0] for c in wanted):
            tables.append(rows)
        i = j
    if len(tables) != 1:
        return None, f"{len(tables)} tables keyed {key!r} with columns {wanted}"
    return tables[0], None


def table_cell(text, key_column, columns, row_label, column):
    """The cell of ``row_label`` under ``column`` of that table."""
    rows, err = list_table_rows(text, key_column, columns)
    if rows is None:
        return None, err
    header, body = rows[0], rows[1:]
    index = header.index(column.strip())
    for cells in body:
        if cells[0].strip() == row_label.strip():
            if len(cells) <= index:
                return None, f"row {row_label!r} has no cell {index}"
            return cells[index], None
    return None, f"no row {row_label!r} (have {[c[0] for c in body][:8]})"


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

    # --- quoted figures sit in the ROW of the configuration quoted ------------------
    # A number merely appearing on a page is not evidence. The first draft of
    # this runbook paired the core-only CHARGE (1558 M) with the
    # observability-on COMMITTED (1379 M) - two rows of the same table - and a
    # "does the value appear on the page" check cannot see that. Every figure
    # therefore binds to page + key column + row label + column label, and the
    # cell itself has to carry the value.
    for figure in desc["figures"]:
        page = DEVELOPMENT_DOCS / f"{figure['source']}.rst"
        check(f"figure {figure['id']} cites a committed page", page.is_file(),
              figure["source"])
        if not page.is_file():
            continue
        page_text = read(page)
        for column, value in zip(figure["columns"],
                                 (figure["charge_mib"], figure["committed_mib"])):
            cell, err = table_cell(page_text, figure["key_column"],
                                   figure["columns"], figure["row"], column)
            check(f"figure {figure['id']}: {figure['source']} row {figure['row']!r} "
                  f"column {column!r} reads {value} MiB",
                  cell is not None
                  and re.search(rf"\*?{value}\*?\s*M\b", cell) is not None,
                  err or cell)
        # and the labelling the figure claims has to be the labelling the
        # SOURCE gives this row. The basis column of compose-profiles says
        # "derived: ..."; where a row carries no word of its own, the page's
        # framing is the claim - but a row that says "derived" may never be
        # quoted as measured, nor the other way round.
        word = "measured" if figure["kind"] == "measured" else "derived"
        rows, err = list_table_rows(page_text, figure["key_column"],
                                    figure["columns"])
        row_cells = next((c for c in (rows or [])[1:]
                          if c[0].strip() == figure["row"].strip()), None)
        if row_cells is None:
            check(f"figure {figure['id']} kind {figure['kind']} is how the source "
                  f"page labels {figure['row']!r}", False, err)
        else:
            row_text = " ".join(row_cells).lower()
            if "derived" in row_text or "measured" in row_text:
                ok, detail = word in row_text, row_text[:90]
            else:
                ok = word == "measured" and "measured" in page_text.lower()
                detail = "row carries no label of its own; page framing"
            check(f"figure {figure['id']} kind {figure['kind']} is how the source "
                  f"page labels {figure['row']!r}", ok, detail)

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

    # --- operator commands do what the page promises --------------------------------
    # Three commands an operator copies out of this page were reviewed and were
    # wrong as pasted; each check below pins the property that makes it work.

    # (1) the core-only floor must pair the core-only charge with the core-only
    # committed. 1379 M is committed of a DIFFERENT row (lightweight +
    # observability) and may only appear where that row is named - the exact
    # row-mixing slip the first draft carried, invisible to a page-level check.
    core = next(f for f in desc["figures"] if f["id"] == "lightweight-core-warm-idle")
    obs = next(f for f in desc["figures"]
               if f["id"] == "lightweight-plus-observability-warm-idle")
    pair = f'{core["charge_mib"]} M charge / {core["committed_mib"]} M committed'
    check(f"the runbook quotes the core-only floor as one row ({pair})",
          pair in book_text)
    # 1379 M belongs to the observability-on row, so every mention of it in the
    # runbook has to name that tier within the same sentence-ish window.
    obs_windows = [book_text[max(0, m.start() - 200):m.end() + 60]
                   for m in re.finditer(rf"\b{obs['committed_mib']} M\b", book_text)]
    check(f"every mention of {obs['committed_mib']} M names the observability-on row",
          all("observability" in w.lower() for w in obs_windows),
          [w.replace("\n", " ")[:90] for w in obs_windows
           if "observability" not in w.lower()])

    # (2) psql runs inside the container. The postgis image has no role matching
    # the exec user, so names have to come from the CONTAINER's environment:
    # single quotes plus $POSTGRES_USER/$POSTGRES_DB, and no host-side $DB_USER
    # that Compose's .env never exports into the operator's shell.
    psql_block = book_text[book_text.find("pg_stat_activity") - 600:
                           book_text.find("pg_stat_activity")]
    check("the pg_stat_activity reading names its user inside the container",
          "psql" in psql_block and "$POSTGRES_USER" in psql_block
          and "$POSTGRES_DB" in psql_block
          and "'" in psql_block)
    check("the pg_stat_activity reading does not expand .env variables on the host",
          "$DB_USER" not in psql_block and "${POSTGRES_DB" not in psql_block)

    # (3) the bench invocation is complete: --endpoint is required=True, so an
    # elided line exits 2. Parse the pasted line with the tool's own parser.
    bench = importlib.util.spec_from_file_location(
        "http_process_bench", ROOT / "scripts" / "http_process_bench.py")
    bench_module = importlib.util.module_from_spec(bench)
    bench.loader.exec_module(bench_module)
    start = book_text.find("http_process_bench.py load")
    lines, i = [], start
    while i < len(book_text):
        line = book_text[i:].split("\n", 1)[0].strip().lstrip("#").strip()
        lines.append(line)
        if not line.endswith("\\"):
            break
        i += book_text[i:].index("\n") + 1
    command = " ".join(l.rstrip("\\").strip() for l in lines)
    command = command.split("http_process_bench.py", 1)[1].strip()
    try:
        parsed = bench_module.build_parser().parse_args(shlex.split(command))
        ok, detail = parsed.command == "load" and bool(parsed.endpoint), ""
    except SystemExit as exc:
        ok, detail = False, f"argparse exited {exc.code}"
    check("the bench load invocation of the runbook parses as written", ok, detail)

    # (4) the one destructive command names its project. `down` re-reads .env on
    # every call, so an inherited COMPOSE_PROJECT_NAME can tear down somebody
    # else's stack - the hazard AGENTS.md requires a -p for.
    book_lines = book_text.splitlines()
    removal = []
    for index, line in enumerate(book_lines):
        stripped = line.strip()
        if not stripped.startswith("docker compose") or stripped.startswith("#"):
            continue
        # join backslash continuations so the whole command is one unit
        cursor = index
        while stripped.endswith("\\") and cursor + 1 < len(book_lines):
            cursor += 1
            stripped = stripped[:-1].strip() + " " + book_lines[cursor].strip()
        if re.search(r"\bdown\b", stripped):
            removal.append(stripped)
    check("the down command pins the project and the files it operates on",
          len(removal) == 1 and '-p "$COMPOSE_PROJECT_NAME"' in removal[0]
          and " -f " in removal[0], removal)
    check("the runbook looks at the project before removing it",
          "com.docker.compose.project" in book_text)
    check("the repo rule the down command follows is the one it cites",
          "AGENTS.md" in book_text and "COMPOSE_PROJECT_NAME" in read(ROOT / "AGENTS.md"))

    print(f"\n{len(failures)} failed of the checks above" if failures
          else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
