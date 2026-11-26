#!/usr/bin/env python3
"""docs_gate: the validation and fail-closed decision gate of the portal (#1607).

Run from the repository root as ``python3 scripts/docs_gate.py <subcommand>``.
Standard library only - no container, no network, no database, no model
credentials - so the same command answers on a bare checkout, in CI and on a
release runner. Exit ``0`` the candidate is accepted, ``1`` the gate decides
against it, ``2`` the gate could not run (a missing file, an unreadable report):
"could not run" is never reported as a pass, which is the convention every other
gate of this repository follows (`scripts/release_gates.py`).

Why a gate and not more checking
--------------------------------
#1597 delivered the build, its strictness (``-W --keep-going``) and its offline
structural suite; #1606 delivered clean rebuilds and automatic topic discovery.
What was missing is the thing that turns those into a decision: one command that
says whether the documentation of *this* candidate may be published, and - just
as important - what to keep when it may not. ADR-0001 section 11 is exact about
the meaning of failure: **no new publication, never a downgraded one**. A failed
run leaves the previous verified documentation standing, blocks the candidate,
and records the reason. That behaviour is only trustworthy if it is one
implemented rule rather than a convention a workflow happens to honour, so it is
implemented here once.

Standard tools do the validation, not this file
-----------------------------------------------
The issue's anti-goal is a standalone validation and repair engine, and this file
honours it. Everything answerable by a standard tool is answered by that tool and
only *collected* here:

  structure, warnings, missing assets, diagrams   ``sphinx-build -b html -W --keep-going``
  cross-link health                                ``sphinx-build -b linkcheck``
  build identity                                   ``provenance.json`` of ``docs/source/_ext/mrmap_docs.py``
  structural facts of the corpus                   ``scripts/test_docs_build.py``
  topic discovery and coverage                     the generators and the source tree itself
  artifact shape                                   ``scripts/docs_gate_schemas.json``

What is genuinely MrMap-specific, and therefore the whole of this file, is the
five checks no upstream tool can answer: the evidence records (ADR-0001 section
4), the coverage floors against the committed floor file (section 2), redaction
of secret material from artifacts (section 7), EN/DE parity (section 10) and
source/version identity bound to the candidate (section 6). Plus the decision
itself, and the bounded retry bookkeeping of section 8.

Repair is a rerun, not an engine
-------------------------------
There is no repair loop here, no agent, no scheduler. When a stage fails the gate
reruns **that stage** and only within the budget its determinism allows -
deterministic stages zero, the browser-shaped stage one, the model-shaped stage
two (ADR-0001 section 8) - records every attempt with its reason, and if the
stage is still red the candidate is refused and the last verified publication is
retained. A deterministic stage that needed a second attempt is itself a failure:
deterministic code either works or is a bug, and retrying a bug hides it.

Subcommands
-----------
evidence   Validate the evidence store: schema, blob digests against the real
           file content, ``executed`` records with a zero exit code and a
           recorded output digest, model-written prose citing only facts it was
           given, no secret material. ``--write`` regenerates the store of the
           portal's own generated pages; drift is a finding.
coverage   Discover every surface denominator from source (ADR-0001 section 2)
           and compare what the corpus covers against the committed floors.
           Floors move upward only, so a generator that silently loses a section
           cannot pass.
gate       Run the stages of a target, apply the retry policy, decide the
           publication action and write the machine-readable report.

Targets
-------
``pr``        The targeted generator checks only - suite, evidence, coverage. No
              build, no browser, no model, no network: this is what an ordinary
              pull request owes and it runs in well under a second.
``release``   The whole contract: the ordinary stages above plus the strict
              build, linkcheck, diagram rendering, build identity and EN/DE
              parity. Wired into the release path by #1609; runnable today.

Examples
--------
  python3 scripts/docs_gate.py evidence --check-generated
  python3 scripts/docs_gate.py coverage --report docs-coverage.json
  python3 scripts/docs_gate.py gate --target pr --report docs-gate.json
  python3 scripts/docs_gate.py gate --target release \\
      --sphinx /tmp/docsenv/bin/python --report docs-gate.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA_FILE = ROOT / "scripts" / "docs_gate_schemas.json"
BASELINE_FILE = ROOT / "scripts" / "docs_coverage_floors.json"
EVIDENCE_DIR = ROOT / "docs" / "evidence"
GENERATED_PAGES = ("design", "release_notes")
GENERATOR = ROOT / "scripts" / "gen_docs_design.py"
PORTAL_SOURCE = ROOT / "docs" / "source"
SUITE = ROOT / "scripts" / "test_docs_build.py"

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

#: ADR-0001 section 8. An attempt budget is a number with a named consequence,
#: and the consequence is decided here rather than by whoever runs the job: a
#: stage may not retry itself past its bound, and a deterministic stage that
#: needed a second attempt is a finding, not a pass.
ATTEMPT_BUDGETS = {"deterministic": 1, "browser": 2, "model": 3}

#: The stages of each target, with how they may retry. ``required`` stages of a
#: target must come back green; ``optional`` ones are reported as skipped when
#: their tool is not present, which is an answer rather than a silence.
STAGES = {
    "pr": [
        {"name": "suite", "kind": "deterministic", "required": True},
        {"name": "evidence", "kind": "deterministic", "required": True},
        {"name": "coverage", "kind": "deterministic", "required": True},
    ],
    "release": [
        {"name": "suite", "kind": "deterministic", "required": True},
        {"name": "evidence", "kind": "deterministic", "required": True},
        {"name": "coverage", "kind": "deterministic", "required": True},
        {"name": "build", "kind": "deterministic", "required": True},
        {"name": "links", "kind": "browser", "required": False},
        {"name": "diagrams", "kind": "deterministic", "required": False},
        {"name": "identity", "kind": "deterministic", "required": True},
        {"name": "provider", "kind": "model", "required": False},
    ],
}

#: What a reader of the portal may never receive: secret material of any kind,
#: whether a build logged it, a generator quoted it or a fixture carried it.
#: These are the shapes worth refusing, not a blocklist of vendor formats.
SECRET_PATTERNS = [
    ("aws-access-key-id", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("gcp-api-key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    ("slack-token", r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b"),
    ("github-token", r"\bgh[pousr]_[0-9A-Za-z]{36,}\b"),
    ("openai-style-key", r"\bsk-[A-Za-z0-9_\-]{20,}\b"),
    ("private-key-block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("jwt", r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"),
    # The host is part of the match on purpose: the placeholder exemption below
    # reads it, and a match that stopped at the `@` could not tell a documented
    # local example from a production connection string.
    ("credentials-in-url",
     r"[A-Za-z][A-Za-z0-9+.-]*://[^\s/\"'`]+:[^\s/\"'`]+@[^\s/\"'`]+"),
    # An environment-style or JSON assignment of anything named like a
    # credential. The name is matched inside longer identifiers -
    # `DJANGO_SECRET_KEY`, `AWS_SECRET_ACCESS_KEY` - because those are the names
    # a leaked environment dump actually carries, and both `"k": "v"` and `k=v`
    # are matched because an artifact is JSON while a captured log line is shell.
    ("secret-assignment",
     r"(?i)[\"']?[A-Z0-9_\-]*(password|passwd|secret|token|api[-_ ]?key"
     r"|access[-_ ]?key|access[-_ ]?token)[A-Z0-9_\-]*[\"']?\s*[:=]\s*"
     r"[\"'][^\"'\s][^\"]{5,}[\"']"),
    ("database-url-with-credentials",
     r"(?i)\b(?:postgres(?:ql)?|mysql|redis|amqp)(?:us)?://"
     r"[^\s/\"'`]*:[^\s/\"'`]+@[^\s/\"'`]+"),
]

#: A placeholder is what documentation *should* carry where a value is unknown.
#: Anything matching one of these shapes in a credential position is not secret
#: material, and refusing it would train people to delete the check.
PLACEHOLDER_RE = re.compile(
    r"^(?:<[^>]+>|\$\{[^}]+\}|\{\{[^}]+\}\}|\*{3,}|"
    r"(?:x{3,}|X{3,}|example|changeme|placeholder|redacted|dummy|sample|your)"
    r"[\w.-]*)$", re.IGNORECASE)
NON_SECRET_HOSTS = ("127.0.0.1", "localhost", "0.0.0.0")

#: Keywords this validator implements. Anything else in the schema file is a
#: **cannot-run**, not a silent skip: a schema that quietly ignores `oneOf` is a
#: gate that quietly accepts what `oneOf` refused, which is the failure mode this
#: whole file exists to prevent.
SUPPORTED_KEYWORDS = {
    "$schema", "$id", "title", "description", "$defs", "$ref", "type", "enum",
    "const", "required", "properties", "additionalProperties", "patternProperties",
    "items", "minItems", "maxItems", "minLength", "maxLength", "minimum",
    "maximum", "pattern", "allOf", "anyOf", "oneOf", "if", "then", "else",
    "minProperties",
}


class CannotRun(Exception):
    """The gate could not answer. Exit 2, never a pass."""


# --------------------------------------------------------------- json schema ---
def _types_ok(value, wanted) -> bool:
    kinds = wanted if isinstance(wanted, list) else [wanted]
    for kind in kinds:
        if kind == "object" and isinstance(value, dict):
            return True
        if kind == "array" and isinstance(value, list):
            return True
        if kind == "string" and isinstance(value, str):
            return True
        if kind == "integer" and isinstance(value, int) and not isinstance(value, bool):
            return True
        if kind == "number" and isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        if kind == "boolean" and isinstance(value, bool):
            return True
        if kind == "null" and value is None:
            return True
    return False


def check_keywords(node, where="") -> None:
    """Refuse a schema this validator would only partially honour."""
    if not isinstance(node, dict):
        return
    unsupported = sorted(k for k in node if k not in SUPPORTED_KEYWORDS)
    if unsupported:
        raise CannotRun(
            f"schema at {where or '#'} uses keywords this validator does not "
            f"implement: {', '.join(unsupported)} - a keyword that is silently "
            "ignored is a rule that is silently not enforced")
    for key, child in node.items():
        if key in {"$defs", "properties", "patternProperties"} \
                and isinstance(child, dict):
            for name, sub in child.items():
                check_keywords(sub, f"{where}/{key}/{name}")
        elif key in {"items", "if", "then", "else", "additionalProperties"} \
                and isinstance(child, dict):
            # `additionalProperties` is itself a schema, not a map of them - the
            # distinction matters, or the walk mistakes `floor` for a keyword.
            check_keywords(child, f"{where}/{key}")
        elif isinstance(child, list):
            for index, sub in enumerate(child):
                check_keywords(sub, f"{where}/{key}/{index}")


def resolve_ref(ref: str, root_schema: dict) -> dict:
    if not ref.startswith("#/"):
        raise CannotRun(f"only local $ref is supported, got {ref!r}")
    node = root_schema
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise CannotRun(f"$ref {ref!r} does not resolve")
        node = node[part]
    return node


def validate(instance, schema, root_schema=None, where="#") -> list[str]:
    """Every violation of ``schema`` by ``instance``, as ``path: message``.

    The subset is the one ``scripts/docs_gate_schemas.json`` uses; anything
    outside it is refused by :func:`check_keywords` before validation starts,
    so there is no keyword that is "not implemented yet".
    """
    root_schema = root_schema if root_schema is not None else schema
    problems: list[str] = []
    if "$ref" in schema:
        return validate(instance, resolve_ref(schema["$ref"], root_schema),
                        root_schema, where)

    if "type" in schema and not _types_ok(instance, schema["type"]):
        return [f"{where}: expected type {schema['type']}, got "
                f"{type(instance).__name__}"]
    if "const" in schema and instance != schema["const"]:
        return [f"{where}: must be {schema['const']!r}, got {instance!r}"]
    if "enum" in schema and instance not in schema["enum"]:
        return [f"{where}: must be one of {schema['enum']}, got {instance!r}"]

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                problems.append(f"{where}: {key!r} is required")
        properties = schema.get("properties", {})
        for name, value in instance.items():
            if name in properties:
                problems += validate(value, properties[name], root_schema,
                                     f"{where}/{name}")
            elif isinstance(schema.get("additionalProperties"), dict):
                problems += validate(value, schema["additionalProperties"],
                                     root_schema, f"{where}/{name}")
            elif schema.get("additionalProperties") is False:
                problems.append(f"{where}: {name!r} is not allowed here")
        for pattern, sub in schema.get("patternProperties", {}).items():
            rx = re.compile(pattern)
            for name, value in instance.items():
                if rx.search(name):
                    problems += validate(value, sub, root_schema,
                                         f"{where}/{name}")
        if "minProperties" in schema and len(instance) < schema["minProperties"]:
            problems.append(f"{where}: needs at least {schema['minProperties']} "
                            f"properties, has {len(instance)}")
    elif isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for index, value in enumerate(instance):
                problems += validate(value, items, root_schema,
                                     f"{where}/{index}")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            problems.append(f"{where}: needs at least {schema['minItems']} "
                            f"items, has {len(instance)}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            problems.append(f"{where}: allows at most {schema['maxItems']} "
                            f"items, has {len(instance)}")
    elif isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            problems.append(f"{where}: needs at least {schema['minLength']} "
                            f"characters")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            problems.append(f"{where}: {instance!r} does not match "
                            f"{schema['pattern']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            problems.append(f"{where}: {instance} is below the minimum of "
                            f"{schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            problems.append(f"{where}: {instance} is above the maximum of "
                            f"{schema['maximum']}")
    if isinstance(instance, str) and "maxLength" in schema \
            and len(instance) > schema["maxLength"]:
        problems.append(f"{where}: longer than maxLength "
                        f"{schema['maxLength']}")

    for key in ("allOf", "anyOf", "oneOf"):
        if key not in schema:
            continue
        found = []
        for index, sub in enumerate(schema[key]):
            found.append(validate(instance, sub, root_schema,
                                  f"{where}({key}[{index}])"))
        if key == "allOf":
            problems += [p for branch in found for p in branch]
        elif key == "anyOf" and not any(not branch for branch in found):
            problems.append(f"{where}: matches none of the {len(found)} "
                            f"branches of anyOf")
        elif key == "oneOf" and sum(1 for branch in found if not branch) != 1:
            problems.append(f"{where}: matches "
                            f"{sum(1 for branch in found if not branch)} of the "
                            f"{len(found)} branches of oneOf, needs exactly one")

    # if/then/else only fires when `if` passes *cleanly*, which is what makes it
    # usable for "this kind requires that field" without leaking the if's own
    # complaints into the verdict.
    if "if" in schema:
        if not validate(instance, schema["if"], root_schema, f"{where}(if)"):
            if "then" in schema:
                problems += validate(instance, schema["then"], root_schema,
                                     f"{where}(then)")
        elif "else" in schema:
            problems += validate(instance, schema["else"], root_schema,
                                 f"{where}(else)")
    return problems


def load_schema() -> dict:
    if not SCHEMA_FILE.is_file():
        raise CannotRun(f"{SCHEMA_FILE} is missing")
    try:
        schema = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CannotRun(f"{SCHEMA_FILE} is not valid JSON: {error}")
    check_keywords(schema)
    return schema


def validate_named(instance, name: str, root_schema=None) -> list[str]:
    """Validate against ``#/$defs/<name>``, refusing a missing definition."""
    schema = root_schema if root_schema is not None else load_schema()
    defs = schema.get("$defs", {})
    if name not in defs:
        raise CannotRun(f"the schema file has no $defs/{name}")
    return validate(instance, defs[name], schema, f"#/$defs/{name}")


# -------------------------------------------------------------------- helpers ---
def blob_digest(path: Path) -> str:
    """The git blob id of a file, computed the way git computes it.

    ADR-0001 section 4 names a blob rather than a line count on purpose: a line
    number rots the moment an unrelated edit lands above it, while a blob says
    "verified against exactly this content". The id is git's own - `git
    hash-object <path>` answers the same value - so an evidence record can be
    checked by a reader with git alone, and recomputing it with hashlib here
    needs no git, no index and no network.
    """
    content = path.read_bytes()
    header = f"blob {len(content)}\0".encode("ascii")
    return "sha1:" + hashlib.sha1(header + content).hexdigest()  # noqa: S304


def write_json_report(path: Path, document: dict) -> None:
    """Write one artifact the gate hands to CI, creating its directory.

    A gate that crashes on its own output path has neither published nor refused
    anything, which is the one reading section 11 never allows: a caller pointing
    ``--report`` somewhere that does not exist yet has made a caller error, not a
    verdict, and that must not swallow the decision.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def read_json(path: str | Path, what: str):
    file = Path(path)
    if not file.is_file():
        raise CannotRun(f"{what} {path} does not exist")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CannotRun(f"{what} {path} is not valid JSON: {error}")


def canonical_version() -> str | None:
    """The application version of the checkout, from the one canonical file."""
    try:
        return (ROOT / "VERSION").read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def redaction_findings(text: str, where: str) -> list[str]:
    """Every secret-shaped string in ``text``, minus the placeholders.

    ADOPT-0001 section 7 requires artifacts to carry no environment values, no
    request headers and no connection strings. The primary control is that the
    documentation worker holds no real credentials at all; this is the net under
    it, and it deliberately reports the *shape* of a secret rather than a list of
    known ones.
    """
    findings = []
    for line_number, line in enumerate(text.splitlines(), 1):
        for name, pattern in SECRET_PATTERNS:
            for match in re.finditer(pattern, line):
                secret = match.group(0)
                if _looks_like_placeholder(secret):
                    continue
                findings.append(f"{where}:{line_number}: {name}: "
                                f"{_mask(secret)}")
    return findings


def _looks_like_placeholder(secret: str) -> bool:
    """Whether a credential-shaped string is a documented placeholder.

    Documentation legitimately shows `DATABASE_URL=postgres://user:<PW>@host/db`
    and `DJANGO_SECRET_KEY=changeme`. What must not pass is a value that could
    actually authenticate, so the exemption reads the whole shape: a local host
    is never a production credential, and a password written as a placeholder is
    not one either. An *empty* user is not an exemption - `redis://:pw@prod`
    carries a real password and no user - which is why only the password and the
    host are consulted.
    """
    if "://" in secret:
        _, _, rest = secret.partition("://")
        authority = rest.split("/")[0]
        if "@" not in authority:
            return True
        host = authority.rsplit("@", 1)[1]
        host = re.sub(r":\d+$", "", host)
        if any(host == name or host.startswith(name + ".")
               for name in NON_SECRET_HOSTS):
            return True
        userinfo = authority.rsplit("@", 1)[0]
        _, _, password = userinfo.rpartition(":")
        return _is_placeholder_value(password)
    for separator in ("=", ":"):
        if separator in secret:
            _, _, value = secret.partition(separator)
            return _is_placeholder_value(value)
    return False


def _is_placeholder_value(value: str) -> bool:
    value = value.strip().strip("\"'").strip()
    if not value:
        return False
    if PLACEHOLDER_RE.match(value):
        return True
    # A value made only of mask characters is a redaction, not a secret.
    return bool(re.fullmatch(r"[*xX#.\-<>]+", value))


def _mask(secret: str) -> str:
    """Show enough of a finding to locate it, never the whole value."""
    secret = secret.strip()
    if len(secret) <= 12:
        return secret[:3] + "…"
    return f"{secret[:6]}…{secret[-3:]}"


def sphinx_argv(executable: str, *arguments: str) -> list[str]:
    """The command line for one Sphinx builder, whichever form was configured.

    ``--sphinx`` names either ``sphinx-build`` itself or the interpreter of the
    pinned environment - the second is what CI and the docs image carry, and
    ``python -m sphinx`` is how the build is documented everywhere else in this
    repository, so the gate asks for the same thing a contributor types.
    """
    head = [executable]
    if Path(executable).name.startswith("python"):
        head += ["-m", "sphinx"]
    return head + list(arguments)


def run_command(argv, cwd=None, env=None) -> tuple[int, str]:
    """Run one ordinary stage command; return its exit code and combined output."""
    try:
        process = subprocess.run(argv, cwd=cwd or str(ROOT), env=env,
                                 capture_output=True, text=True, timeout=3600)
    except FileNotFoundError:
        return 127, f"command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timed out"
    return process.returncode, (process.stdout or "") + (process.stderr or "")


# ------------------------------------------------------------------ discovery ---
def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _corpus_text() -> str:
    """Everything a reader of the portal is shown, plus the release notes.

    The numerator of every coverage surface is measured over this text: a topic
    counts as covered when the corpus actually names it, which is a question a
    machine can answer and an editor cannot be trusted to keep current.
    """
    parts = []
    for pattern in ("**/*.rst", "**/*.md"):
        for path in sorted((ROOT / "docs").rglob(pattern)):
            if {"build", "_build", "locale", "_static"} & set(path.parts):
                continue
            parts.append(_read(path))
    parts.append(_read(ROOT / "CHANGELOG.md"))
    return "\n".join(parts)


def _corpus_index() -> tuple[frozenset, str]:
    """Word tokens of the corpus, plus the corpus itself for hyphenated names.

    ``measure_coverage`` asks this for every discovered topic. Searching each
    name as its own regex over a corpus of more than a megabyte cost fifteen
    seconds per gate run, which is fifteen seconds nobody pays twice: tokens
    decide the ordinary identifier in one pass, and only the few names carrying
    punctuation - a compose service like ``celery-worker``, a Behave feature
    like ``featuretypes-per-service`` - still need a substring search. The
    semantics match the word-boundary match they replaced, because `\b` treats
    a hyphen as a boundary anyway and `_` as part of the word already.
    """
    text = _corpus_text()
    return frozenset(re.findall(r"\w+", text)), text


def _is_documented(item: str, tokens: frozenset, corpus: str) -> bool:
    if re.fullmatch(r"\w+", item):
        return item in tokens
    return item in corpus


def discover_surface(name: str) -> list[str]:
    """The denominator of one surface, discovered from source and never curated.

    ADR-0001 section 2: a curated list is hand-maintained documentation wearing a
    different hat, so every list below is read out of the software that defines
    it. A surface whose source file is missing is a cannot-run rather than an
    empty list - an empty denominator passes every floor.

    Each branch reads the file(s) that *define* the surface: the component
    registry, the models, the settings module, the management commands, the task
    modules, the two compose files, the Behave features. Tests drive a branch by
    pointing :data:`SURFACE_SOURCES` somewhere else, so a rule can be shown red
    over a planted file without editing this function.
    """
    if name == "resources":
        source = ROOT / "frontend" / "src" / "components" / "Resource" / "Definition.tsx"
        if not source.is_file():
            raise CannotRun(f"{source} is missing; the resource surface has no denominator")
        return sorted(set(re.findall(r'name:\s*"([A-Za-z0-9_]+)"', _read(source))))
    if name == "models":
        models = set()
        files = (sorted((ROOT / "backend").glob("*/models.py"))
                 + sorted((ROOT / "backend").glob("*/models/*.py")))
        if not files:
            raise CannotRun("no models.py under backend/; the model surface has no denominator")
        for path in files:
            models |= set(re.findall(
                r"^class\s+(\w+)\s*\([^)]*models\.Model[^)]*\)", _read(path), re.M))
        return sorted(models)
    if name == "settings":
        sources = SURFACE_SOURCES.get(name) or [ROOT / "backend" / "MrMap" / "settings.py"]
        settings = set()
        for source in sources:
            if not source.is_file():
                raise CannotRun(f"{source} is missing; the settings surface has "
                                "no denominator")
            settings |= set(re.findall(r"^([A-Z][A-Z0-9_]*)\s*=", _read(source),
                                       re.M))
        return sorted(settings)
    if name == "commands":
        return sorted({path.stem for path in (ROOT / "backend").glob("*/management/commands/*.py")
                       if path.name != "__init__.py"})
    if name == "tasks":
        tasks = set()
        for path in sorted((ROOT / "backend").glob("*/tasks/*.py")):
            text = _read(path)
            tasks |= set(re.findall(
                r"@(?:shared_task|app\.task|celery_app\.task)[^\n]*\n(?:\s*@[^\n]*\n)*"
                r"def\s+(\w+)", text))
        return sorted(tasks)
    if name in ("compose", "compose-dev"):
        filename = "docker-compose.yml" if name == "compose" else "docker-compose.dev.yml"
        source = ROOT / filename
        if not source.is_file():
            raise CannotRun(f"{source} is missing; the deployment surface has no denominator")
        text = _read(source)
        block = text.split("\nservices:", 1)[1] if "\nservices:" in text else ""
        stop = re.search(r"^\S", block, re.M)
        if stop:
            block = block[:stop.start()]
        return sorted(set(re.findall(r"^  ([a-z][\w-]*):\s*$", block, re.M)))
    if name == "behave":
        return sorted({path.stem for path in
                       (ROOT / "backend" / "tests" / "behave" / "features").rglob("*.feature")})
    raise CannotRun(f"unknown surface {name!r}")


#: Where a surface's denominator comes from, when it is a set of files rather
#: than a location the branch already knows. Empty in normal operation; the
#: suite uses it to drive one branch over a planted file.
SURFACE_SOURCES: dict[str, list[Path]] = {}

#: The surfaces of ADR-0001 section 2. ``owner`` names the issue that can raise
#: the floor, so an unraisable floor is visible as a gap rather than a pass.
SURFACES = {
    "resources": {"adr": "V-1", "owner": "#1603"},
    "models": {"adr": "V-2", "owner": "#1599"},
    "settings": {"adr": "V-4", "owner": "#1600"},
    "commands": {"adr": "V-5", "owner": "#1600"},
    "tasks": {"adr": "V-6", "owner": "#1600"},
    "compose": {"adr": "V-7", "owner": "#1600"},
    "compose-dev": {"adr": "V-7", "owner": "#1600"},
    "behave": {"adr": "V-8", "owner": "#1602"},
}


def measure_coverage(contract: dict) -> dict:
    """Measure every surface against its committed contract, and name the holes.

    Two rules, both from ADR-0001 section 2, and each catching a failure the
    other misses. The **floor** stops a generator from quietly losing a section:
    it was raised when the section was gained, so a run that drops it is red.
    The **gap list** stops new software from arriving undocumented: a topic that
    is not in the corpus and is not a declared gap is a finding, which is the
    only way a coverage floor that "passes" means something rather than merely
    being comfortable. ``policy: floor`` waives only the second rule, for the one
    surface the ADR reports as unsupported rather than enforced (V-8).
    """
    tokens, corpus = _corpus_index()
    report = {}
    for name, meta in SURFACES.items():
        entry = contract.get(name)
        if entry is None:
            # A surface with no contract entry could not regress, which is
            # exactly the situation section 2 refuses to allow. Checked before
            # discovery: the contract, not the tree, is what the gate answers to.
            raise CannotRun(
                f"surface {name!r} has no entry in the coverage contract; add it "
                "in a pull request that names the surface, or the gate cannot "
                "decide anything about it")
        discovered = discover_surface(name)
        floor = int(entry["floor"])
        policy = entry["policy"]
        declared = set(entry["gaps"])
        missing = [item for item in discovered
                   if not _is_documented(item, tokens, corpus)]
        covered = len(discovered) - len(missing)
        new_gaps = sorted(set(missing) - declared)
        closed = sorted(declared - set(missing))
        status = "pass"
        if covered < floor:
            status = "fail"
        elif new_gaps and policy != "floor":
            status = "fail"
        report[name] = {
            "surface": f"{name} ({meta['adr']}, raisable by {meta['owner']})",
            "covered": covered,
            "discovered": len(discovered),
            "floor": floor,
            "status": status,
            # The lists are bounded so one report stays a readable artifact and
            # not a 4 000-entry dump; the counts are what the decision reads,
            # and `new_gaps` - the list that can turn a run red - is never cut.
            "missing": missing[:40],
            "missing_count": len(missing),
            "new_gaps": new_gaps,
            "closed_gaps": closed[:40],
        }
    return report


def write_coverage_contract(path: Path) -> dict:
    """Re-measure the whole coverage contract from the software.

    The committed file is a measurement, not a list of topics a person curates -
    which is what keeps it from becoming the hand-maintained manifest the epic
    forbids, and what makes "regenerate and diff" the review of a coverage
    change. Existing `floor` and `raised_by` values are preserved where they are
    still reachable, so raising a floor stays a deliberate act.
    """
    previous = {}
    if path.is_file():
        try:
            previous = (read_json(path, "the coverage contract") or {}).get(
                "surfaces", {})
        except CannotRun:
            previous = {}
    tokens, corpus = _corpus_index()
    surfaces = {}
    for name, meta in SURFACES.items():
        discovered = discover_surface(name)
        gaps = sorted(i for i in discovered
                      if not _is_documented(i, tokens, corpus))
        old = previous.get(name) or {}
        measured = len(discovered) - len(gaps)
        floor = max(measured, int(old.get("floor", 0) or 0))
        surfaces[name] = {
            "floor": floor,
            "gaps": gaps,
            "policy": old.get("policy", "floor" if name == "behave"
                              else "floor+growth"),
            "raised_by": old.get("raised_by", "#1607"),
            "reason": old.get(
                "reason",
                f"measured by scripts/docs_gate.py coverage; {meta['adr']} of "
                f"ADR-0001, raisable by {meta['owner']}"),
        }
    document = {"schema": "mrmap.docs.coverage-baseline.v1",
                "note": BASELINE_NOTE, "surfaces": surfaces}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return surfaces


BASELINE_NOTE = (
    "The coverage contract of ADR-0001 section 2, measured by `python3 "
    "scripts/docs_gate.py coverage --write-baseline`. Every value is a "
    "measurement of the software and of the corpus, never a curated topic list. "
    "Two rules follow, and the gate enforces both: `floor` only ever moves "
    "upward, so a generator that silently loses a section cannot clear the floor "
    "raised when the section was gained; and every topic that is not documented "
    "today is named in `gaps`, so new software that arrives undocumented is a red "
    "gate rather than a quiet hole. Lowering a floor is a maintainer decision, "
    "never a generator convenience. `policy: floor` waives the gap rule for the "
    "one surface the ADR reports as unsupported rather than enforced - V-8 does "
    "that for Behave features until #1602 ships browser scenarios.")


# ------------------------------------------------------------------- evidence ---
def evidence_files(directory: Path) -> list[Path]:
    return sorted(list(directory.rglob("*.evidence.json"))
                  + list(directory.rglob("*.evidence.jsonl")))


def load_records(path: Path) -> list[tuple[int, dict]]:
    """The records of one evidence file, line-numbered for readable findings."""
    text = _read(path)
    if path.suffix == ".jsonl" or all(
            line.strip() for line in text.splitlines() if line.strip()) \
            and text.lstrip().startswith("{") and "\n{" in text:
        records = []
        for number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                records.append((number, json.loads(line)))
            except json.JSONDecodeError as error:
                raise CannotRun(f"{path}:{number} is not valid JSON: {error}")
        return records
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise CannotRun(f"{path} is not valid JSON: {error}")
    if isinstance(parsed, dict) and isinstance(parsed.get("records"), list):
        return [(0, record) for record in parsed["records"]]
    if isinstance(parsed, list):
        return [(0, record) for record in parsed]
    return [(0, parsed)]


def check_evidence(directory: Path, schema: dict,
                   corpus_pages: list[Path] | None = None) -> list[str]:
    """Every rule of ADR-0001 section 4 that a machine can decide.

    The schema decides the shape; the rules below decide whether the record
    *means* what it says, which no schema can. Each one earned its place against
    a way a generated page could look evidenced and not be.
    """
    findings: list[str] = []
    records = []
    for path in evidence_files(directory):
        for number, record in load_records(path):
            # Display path only; a store outside the checkout is legal to check.
            where = str(path.relative_to(ROOT)
                        if path.is_relative_to(ROOT) else path) \
                + (f":{number}" if number else "")
            for problem in validate_named(record, "evidence", schema):
                findings.append(f"{where}: {problem}")
            findings += redaction_findings(json.dumps(record), where)
            records.append((where, record, path))

    seen_ids: dict[str, str] = {}
    for where, record, path in records:
        if not isinstance(record, dict):
            continue
        identifier = record.get("id")
        if identifier in seen_ids:
            findings.append(f"{where}: evidence id {identifier} is also used by "
                            f"{seen_ids[identifier]} - one claim, one record")
        seen_ids.setdefault(identifier, where)

        # V-14: an `executed` record is a claim that something ran. It has to
        # carry the command, its zero exit code and the digest of what it
        # printed, or it is an assertion with no evidence behind it.
        if record.get("kind") == "executed":
            assertion = record.get("assertion") or {}
            if assertion.get("exit_code") != 0:
                findings.append(f"{where}: executed evidence exited "
                                f"{assertion.get('exit_code')!r}; a claim proven "
                                "by a failed command is not proven")
            if not re.fullmatch(r"sha256:[0-9a-f]{64}",
                                str(assertion.get("stdout_sha256") or "")):
                findings.append(f"{where}: executed evidence must record the "
                                "sha256 of what the command printed")

        # A `human` record is the grandfathered pre-epic corpus. It must say so
        # and name where it came from, or it is a model claim wearing a human
        # name - which is the one forgery worth refusing outright.
        if record.get("kind") == "human":
            reviewed = record.get("reviewed") or {}
            if not (reviewed.get("legacy") or reviewed.get("by")):
                findings.append(f"{where}: human evidence must name its reviewer "
                                "or be marked legacy, per ADR-0001 section 4")

        # Model-written prose may only cite facts it was actually given. This is
        # the mechanical form of "no invented features", and it is the reason an
        # `inferred` claim is publishable without a human in the loop.
        if record.get("kind") == "inferred":
            facts = set(record.get("facts") or [])
            cited = record.get("cited_fact_ids")
            if not isinstance(cited, list):
                findings.append(f"{where}: inferred prose must list the fact ids "
                                "it cites")
            else:
                unknown = sorted(set(cited) - facts)
                if unknown:
                    findings.append(
                        f"{where}: inferred prose cites facts that are not in "
                        f"its own facts[]: {', '.join(unknown[:8])} - a response "
                        "citing an unknown fact is discarded in full")
            if not record.get("produced_by", {}).get("model"):
                findings.append(f"{where}: inferred prose must name the model "
                                "that wrote it")

        # A source span is only as good as the content it was taken from: the
        # blob must be the blob of that path *in this tree*, or the record
        # describes a file that no longer exists.
        for source in record.get("sources") or []:
            if not isinstance(source, dict):
                continue
            target = ROOT / source.get("path", "")
            if not target.is_file():
                findings.append(f"{where}: source {source.get('path')!r} is not "
                                "in the tree the gate is validating")
            elif blob_digest(target) != source.get("blob"):
                findings.append(
                    f"{where}: source {source.get('path')!r} has blob "
                    f"{blob_digest(target)} but the record claims "
                    f"{source.get('blob')} - the evidence is stale, regenerate it")

    # V-13: a generated page with no evidence record is an empty space a reader
    # cannot distinguish from a complete one.
    if corpus_pages is not None:
        evidenced = {record.get("page") for _w, record, _p in records
                     if isinstance(record, dict)}
        for page in corpus_pages:
            relative = str(page.relative_to(PORTAL_SOURCE))
            if relative not in evidenced and not (
                    str(page.relative_to(ROOT)) in evidenced):
                findings.append(f"{relative}: generated page has no evidence "
                                "record (V-13)")
    return findings


def generated_pages() -> list[Path]:
    return sorted(path for name in GENERATED_PAGES
                  for path in (PORTAL_SOURCE / name).rglob("*") if path.is_file())


def write_evidence(directory: Path) -> list[Path]:
    """Regenerate the evidence store of the portal's own generated pages.

    These pages are written by ``scripts/gen_docs_design.py`` from notes outside
    the portal tree, so "the committed page still matches its note" is a claim
    with an owner and a source - the two things an evidence record exists to
    name. Deterministic: the same tree always writes the same bytes.
    """
    generator_digest = blob_digest(GENERATOR)
    records = []
    for page in generated_pages():
        text = _read(page)
        match = re.search(r"``docs/([^`]+)``", text)
        note = ROOT / "docs" / match.group(1) if match else None
        sources = [{"path": str(GENERATOR.relative_to(ROOT)), "blob": generator_digest}]
        if note is not None and note.is_file():
            sources.insert(0, {"path": str(note.relative_to(ROOT)),
                               "blob": blob_digest(note)})
        claim = (f"{page.relative_to(PORTAL_SOURCE)} is rendered by "
                 f"scripts/gen_docs_design.py from "
                 f"{sources[0]['path']}")
        record = {
            "schema": "mrmap.docs.evidence.v1",
            "id": "sha256:" + hashlib.sha256(
                (claim + "\0".join(s["blob"] for s in sources)).encode()).hexdigest(),
            "claim": claim,
            "kind": "extracted",
            "page": str(page.relative_to(PORTAL_SOURCE)),
            "locale": "en",
            "sources": sources,
            "produced_by": {"engine": "generator",
                            "generator": "scripts/gen_docs_design.py",
                            "model": None},
            "reviewed": None,
        }
        records.append(record)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "generated.evidence.jsonl"
    body = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    if not target.is_file() or target.read_text(encoding="utf-8") != body:
        target.write_text(body, encoding="utf-8")
    return [target]


# --------------------------------------------------------------------- stages ---
def stage(name: str, *, kind: str, status: str, attempts: int,
          log: list[dict] | None = None, findings: list[str] | None = None,
          retry_reason: str | None = None, note: str = "") -> dict:
    return {
        "name": name,
        "deterministic": kind == "deterministic",
        "status": status,
        "attempts": attempts,
        "max_attempts": ATTEMPT_BUDGETS[kind],
        "retry_reason": retry_reason,
        "attempt_log": log or [],
        "findings": [{"code": finding["code"] if isinstance(finding, dict)
                      else finding[0],
                      "detail": finding["detail"] if isinstance(finding, dict)
                      else finding[1]}
                     for finding in (findings or [])],
        **({"note": note} if note else {}),
    }


def run_stage(spec: dict, action, retryable: bool = False) -> dict:
    """Run one ordinary stage, rerunning it at most within its own budget.

    ``action`` returns ``(ok, findings, log_entry)``. The budget is the whole
    policy: a deterministic stage gets exactly one attempt because its budget is
    1, and retrying deterministic code would only hide a bug for longer. A
    browser-shaped stage gets a second attempt and a model-shaped stage a third,
    because those two can genuinely fail for a reason that clears on its own.
    """
    kind = spec["kind"]
    budget = ATTEMPT_BUDGETS[kind]
    log: list[dict] = []

    def attempt(number: int) -> tuple[bool, list, dict]:
        ok, findings, entry = action()
        entry["attempt"] = number
        return ok, findings, entry

    ok, findings, entry = attempt(1)
    attempts = 1
    log.append(entry)
    retry_reason = None
    while not ok and attempts < budget and retryable:
        retry_reason = f"stage {spec['name']} failed its first attempt: " \
                       f"{entry.get('reason', 'unknown')}"
        ok, findings, entry = attempt(attempts + 1)
        attempts += 1
        log.append(entry)
    # `attempts` cannot exceed the budget: the loop above is the only place it
    # grows, and its condition is the bound. So a stage can never report more
    # attempts than its kind allows, and there is no lying-to-the-report path to
    # guard against here.
    return stage(spec["name"], kind=kind,
                 status="pass" if ok else "fail", attempts=attempts,
                 log=log, findings=findings, retry_reason=retry_reason)


def command_action(argv, cwd=None, env=None, code="stage-failed"):
    """An action that runs one external command; the command is its own verdict."""
    def action():
        exit_code, output = run_command(argv, cwd=cwd, env=env)
        entry = {"attempt": 0, "reason": f"exit {exit_code}",
                 "exit_code": exit_code}
        lines = [line for line in output.splitlines() if line.strip()]
        if exit_code != 0:
            tail = " | ".join(lines[-8:]) or f"exit {exit_code}"
            return False, [(code, tail[:500])], entry
        return True, [], entry
    return action


# ------------------------------------------------------------------ decisions ---
def decide(report: dict, keep: dict | None) -> dict:
    """Refuse the candidate or accept it, and name what a failure retains.

    ADOPT-0001 section 11 in one function: red means *no new publication*, and
    the previous verified documentation is named in the same artifact that says
    so, so nothing downstream has to remember the rule.
    """
    red = [s for s in report["stages"] if s["status"] in ("fail", "cannot-run")]
    coverage_red = [name for name, row in (report.get("coverage") or {}).items()
                    if row.get("status") == "fail"]
    if red or coverage_red:
        reasons = [f"stage {s['name']} is {s['status']}" for s in red]
        reasons += [f"coverage of {name} is {row['covered']}, below its floor "
                    f"of {row['floor']}" for name, row in
                    (report.get("coverage") or {}).items()
                    if row.get("status") == "fail"]
        return {"action": "retain-previous", "keep": keep,
                "reason": "; ".join(reasons)}
    return {"action": "allow", "keep": keep,
            "reason": "every required stage of the target is green"}


def last_verified(path: str | None) -> dict | None:
    """The identity of the last verified publication, from its own report."""
    if not path:
        return None
    report = read_json(path, "the report of the last verified publication")
    candidate = report.get("candidate") or {}
    return {"version": candidate.get("version"),
            "documented_commit": candidate.get("documented_commit"),
            "source_digest": candidate.get("source_digest")}


# ------------------------------------------------------------------ subcommands ---
def cmd_evidence(args) -> int:
    schema = load_schema()
    directory = Path(args.dir)
    if args.write:
        written = write_evidence(directory)
        for path in written:
            print(f"wrote {path.relative_to(ROOT)}")
        return EXIT_OK
    findings = check_evidence(directory, schema,
                              generated_pages() if args.check_generated else None)
    if args.check_logs:
        for path in sorted(Path(args.check_logs).rglob("*")):
            if path.is_file() and path.suffix in {".log", ".txt", ".json"}:
                findings += redaction_findings(_read(path),
                                               str(path.relative_to(ROOT))
                                               if path.is_relative_to(ROOT) else str(path))
    total = len(evidence_files(directory))
    for finding in findings:
        print(f"evidence: FAIL - {finding}")
    if findings:
        return EXIT_FAIL
    print(f"evidence: ok - {total} file(s), all records schema-valid, "
          "blobs current, nothing unredacted")
    return EXIT_OK


def cmd_coverage(args) -> int:
    if args.write_baseline:
        write_coverage_contract(Path(args.baseline))
        print(f"re-measured the coverage contract of {BASELINE_FILE.name} "
              "from the software; review the diff")
        return EXIT_OK
    contract = _load_contract(Path(args.baseline))
    report = measure_coverage(contract)
    for name, row in report.items():
        mark = "ok  " if row["status"] == "pass" else "FAIL"
        policy = "" if contract[name]["policy"] == "floor+growth" \
            else "  (growth reported, not enforced)"
        print(f"  {mark}  {name:14s} {row['covered']:4d}/{row['discovered']:<4d} "
              f"floor {row['floor']}, {row['missing_count']} gap(s)"
              f"{policy}")
        if row["status"] != "pass":
            if row["new_gaps"]:
                print(f"        undocumented and undeclared: "
                      f"{', '.join(row['new_gaps'][:12])}")
            if row["covered"] < row["floor"]:
                print(f"        below the floor by "
                      f"{row['floor'] - row['covered']}")
        if row["closed_gaps"]:
            print(f"        now documented (raise the floor): "
                  f"{', '.join(row['closed_gaps'][:8])}")
    if args.report:
        write_json_report(Path(args.report), {
            "schema": "mrmap.docs.coverage.v1",
            "candidate": _candidate_identity(),
            "surfaces": report})
        print(f"wrote {args.report}")
    red = [name for name, row in report.items() if row["status"] != "pass"]
    if red:
        for name in red:
            row = report[name]
            if row["covered"] < row["floor"]:
                print(f"coverage: FAIL - {name} covers {row['covered']}, below "
                      f"its floor of {row['floor']}: documentation was lost")
            else:
                print(f"coverage: FAIL - {name} added "
                      f"{len(row['new_gaps'])} topic(s) that no page names and "
                      f"no gap declares: {', '.join(row['new_gaps'][:6])}")
        return EXIT_FAIL
    print(f"coverage: ok - {len(report)} surface(s) at or above their floors, "
          "no undeclared gap")
    return EXIT_OK


def _load_contract(path: Path | None = None) -> dict:
    """The committed coverage contract, or a cannot-run.

    A missing or malformed contract is never treated as an empty one: with no
    floors to clear, every surface would pass, which is the exact reading a
    broken file must not be allowed to have.
    """
    path = path or BASELINE_FILE
    schema = load_schema()
    if not path.is_file():
        raise CannotRun(f"{path} is missing; coverage cannot be decided without "
                        "its contract")
    contract = read_json(path, "the coverage contract")
    problems = validate_named(contract, "coverage_baseline", schema)
    if problems:
        raise CannotRun(f"{path.name} is not valid: " + "; ".join(problems[:6]))
    return contract["surfaces"]


def _candidate_identity() -> dict:
    from importlib import util  # local: the shared module lives under docs/
    module_path = PORTAL_SOURCE / "_ext" / "mrmap_digests.py"
    if not module_path.is_file():
        raise CannotRun(f"{module_path} is missing; the source identity cannot "
                        "be computed")
    spec = util.spec_from_file_location("mrmap_digests", module_path)
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {
        "version": canonical_version(),
        "documented_commit": os.environ.get("GITHUB_SHA") or _git_head(),
        "source_digest": module.source_digest(PORTAL_SOURCE),
    }


def _git_head() -> str | None:
    try:
        process = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                                 capture_output=True, text=True, timeout=10)
    except OSError:
        return None
    value = process.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _identity_findings(build_dir: Path, candidate: dict, expect_sha: str | None,
                       expect_version: str | None) -> list[tuple[str, str]]:
    """V-13 and section 6: the artifact must say what it was built from."""
    findings: list[tuple[str, str]] = []
    provenance = build_dir / "provenance.json"
    if not provenance.is_file():
        return [("provenance-missing",
                 "the build wrote no provenance.json, so the artifact cannot "
                 "name the revision it documents")]
    data = read_json(provenance, "provenance.json")
    if data.get("schema") != "mrmap.docs.provenance.v1":
        findings.append(("provenance-schema",
                         f"provenance.json schema is {data.get('schema')!r}"))
    documented = data.get("documented_commit")
    if not re.fullmatch(r"[0-9a-f]{40}", str(documented or "")):
        findings.append(("provenance-commit",
                         f"documented_commit is {documented!r}; a build that "
                         "cannot name its revision is not attributable"))
    elif expect_sha and documented != expect_sha:
        findings.append(("provenance-commit-mismatch",
                         f"the build documents {documented} but the candidate is "
                         f"{expect_sha} - documentation of one revision cannot be "
                         "published as another"))
    if expect_version and data.get("version") != expect_version:
        findings.append(("provenance-version-mismatch",
                         f"the build documents version {data.get('version')!r} "
                         f"but the candidate is {expect_version!r}"))
    if data.get("source_digest") != candidate["source_digest"]:
        findings.append(("provenance-digest-mismatch",
                         "the documented source digest differs from the one "
                         "computed from this tree: the artifact was not built "
                         "from the sources being gated"))
    if not data.get("toolchain", {}).get("sphinx"):
        findings.append(("provenance-toolchain",
                         "provenance.json names no Sphinx version, so the build "
                         "is not reproducible"))
    return findings


def _locale_findings(build_dir: Path, required: list[str]) -> list[tuple[str, str]]:
    """V-12: a per-locale floor, so an English-only run cannot pass on the aggregate."""
    if not required:
        return []
    findings: list[tuple[str, str]] = []
    for locale in required:
        tree = build_dir / locale
        if not tree.is_dir() or not any(tree.rglob("*.html")):
            findings.append(("locale-missing",
                             f"locale {locale!r} produced no pages; per-locale "
                             "coverage is measured per locale, not on the "
                             "aggregate"))
    return findings


def cmd_gate(args) -> int:
    if args.target not in STAGES:
        raise CannotRun(f"unknown target {args.target!r}")
    target = args.target
    schema = load_schema()
    build_dir = Path(args.build_dir)
    candidate = (read_json(args.candidate, "--candidate")
                 if args.candidate else _candidate_identity())
    problems = validate_named(candidate, "candidate", schema)
    if problems:
        raise CannotRun("the candidate identity is not usable: "
                        + "; ".join(problems[:6]))
    contract = _load_contract(Path(args.baseline))
    stages: list[dict] = []
    coverage: dict = {}
    provider_available = bool(args.provider_cmd
                              or os.environ.get("MRMAP_DOCS_PROVIDER_CMD"))
    narrative_needed = (args.require_narrative
                        or _narrative_needed(Path(args.evidence_dir)))

    for spec in STAGES[target]:
        if not spec["required"] and not _asked(spec["name"], args):
            # An optional stage that was not asked for is reported as skipped
            # with its reason, never as a pass it did not earn.
            stages.append(stage(spec["name"], kind=spec["kind"],
                                status="skipped", attempts=0,
                                note=f"optional stage of target {target}; "
                                     "not requested"))
            continue
        if spec["name"] == "suite":
            stages.append(run_stage(
                spec, command_action([sys.executable, str(SUITE)],
                                     code="suite-failed")))
        elif spec["name"] == "evidence":
            def evidence_action():
                findings = check_evidence(Path(args.evidence_dir), schema,
                                          generated_pages())
                entry = {"attempt": 0, "reason": "checked", "exit_code": None}
                return not findings, [("evidence", f) for f in findings[:20]], entry
            stages.append(run_stage(spec, evidence_action))
        elif spec["name"] == "coverage":
            def coverage_action():
                nonlocal coverage
                coverage = measure_coverage(contract)
                red = [f"{name}: {row['covered']} of floor {row['floor']}"
                       for name, row in coverage.items()
                       if row["status"] != "pass"]
                entry = {"attempt": 0, "reason": "measured", "exit_code": None}
                return not red, [("coverage", r) for r in red], entry
            stages.append(run_stage(spec, coverage_action))
        elif spec["name"] == "identity":
            built = next((s for s in stages if s["name"] == "build"), None)
            if built is not None and built["status"] != "pass":
                # Comparing provenance of an artifact this run refused would let
                # the previous, still-green build of the same tree pass identity
                # on stale bytes. No build, no artifact, no claim.
                stages.append(stage(spec["name"], kind=spec["kind"],
                                    status="cannot-run", attempts=0,
                                    findings=[("build-red",
                                               "the strict build is red, so the "
                                               "artifact beside it is not "
                                               "evidence of anything")],
                                    note="skipped because the build failed"))
                continue

            def identity_action():
                findings = _identity_findings(Path(args.build_dir), candidate,
                                              args.expect_sha,
                                              args.expect_version)
                findings += _locale_findings(Path(args.build_dir), args.require_locale)
                entry = {"attempt": 0, "reason": "compared", "exit_code": None}
                return not findings, findings, entry
            stages.append(run_stage(spec, identity_action))
        elif spec["name"] == "build":
            if not args.sphinx:
                # A required stage that cannot run is a cannot-run, which decides
                # the candidate red: a release target without the strict build is
                # a release gate that gates nothing.
                stages.append(stage(
                    spec["name"], kind=spec["kind"],
                    status="cannot-run" if spec["required"] else "skipped",
                    attempts=0,
                    findings=[("no-sphinx",
                               "--sphinx is required for the release target: the "
                               "strict build is the gate")]
                    if spec["required"] else None))
                continue
            doctrees = build_dir.parent / "doctrees"
            argv = sphinx_argv(args.sphinx, "-b", "html", "-E", "-W",
                               "--keep-going", "-d", str(doctrees),
                               str(PORTAL_SOURCE), str(build_dir))
            stages.append(run_stage(spec, command_action(argv, code="build-warnings")))
        elif spec["name"] == "links":
            if not args.sphinx or not args.check_links:
                stages.append(stage(spec["name"], kind=spec["kind"],
                                    status="skipped", attempts=0,
                                    note="linkcheck needs network; the external-"
                                         "link policy of conf.py governs it"))
                continue
            argv = sphinx_argv(args.sphinx, "-b", "linkcheck", "-E",
                               "--keep-going",
                               "-d", str(build_dir.parent / "doctrees"),
                               str(PORTAL_SOURCE),
                               str(build_dir.parent / "linkcheck"))
            stages.append(run_stage(spec, command_action(argv, code="linkcheck"),
                                    retryable=True))
        elif spec["name"] == "diagrams":
            cli = args.mmdc or _which("mmdc")
            if not cli:
                stages.append(stage(spec["name"], kind=spec["kind"],
                                    status="skipped", attempts=0,
                                    note="no Mermaid CLI on this runner; the "
                                         "static renderer needs none"))
                continue
            stages.append(run_stage(spec, _diagram_action(cli, Path(args.build_dir))))
        elif spec["name"] == "provider":
            if not narrative_needed:
                stages.append(stage(spec["name"], kind=spec["kind"],
                                    status="skipped", attempts=0,
                                    note="no model-written claim in this "
                                         "candidate; nothing to ask a provider"))
                continue
            if not provider_available:
                stages.append(stage(spec["name"], kind=spec["kind"],
                                    status="cannot-run", attempts=0,
                                    findings=[(
                                        "provider-unavailable",
                                        "the candidate carries model-written claims"
                                        " and no provider is configured; ADR-0001"
                                        " section 11 fails closed rather than"
                                        " publishing unevidenced prose")]))
                continue
            stages.append(run_stage(
                spec, command_action(shlex_split(args.provider_cmd
                                                 or os.environ["MRMAP_DOCS_PROVIDER_CMD"]),
                                     code="provider-refused"),
                retryable=True))

    report = {
        "schema": "mrmap.docs.gate.v1",
        "target": target,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": args.actor or os.environ.get("GITHUB_ACTOR") or "unknown",
        "candidate": candidate,
        "stages": stages,
        "coverage": coverage,
        "ok": not ([s for s in stages if s["status"] in ("fail", "cannot-run")]
                   or [n for n, r in coverage.items() if r["status"] != "pass"]),
    }
    report["publication"] = decide(report, last_verified(args.keep_report))
    problems = validate_named(report, "report", schema)
    if problems:
        raise CannotRun("the gate wrote an invalid report: "
                        + "; ".join(problems[:6]))

    for entry in report["stages"]:
        mark = {"pass": "ok  ", "fail": "FAIL", "skipped": "--  ",
                "unsupported": "--  ", "cannot-run": "FAIL"}[entry["status"]]
        extra = f" ({entry['note']})" if entry.get("note") else ""
        print(f"  {mark}  {entry['name']:12s} {entry['attempts']}"
              f"/{entry['max_attempts']} attempt(s){extra}")
        if entry["status"] == "fail" or entry["status"] == "cannot-run":
            for finding in entry["findings"][:12]:
                # Long enough to survive to the actionable tail of the longest
                # finding: a message cut at the point where it says what to do
                # is a message that sends someone to read the source.
                print(f"          {finding['code']}: {finding['detail'][:500]}")
            if entry.get("retry_reason"):
                print(f"          retried: {entry['retry_reason'][:160]}")
    for name, row in coverage.items():
        if row["status"] != "pass":
            print(f"  FAIL  coverage {name}: {row['covered']} of floor "
                  f"{row['floor']}")
    print(f"publication: {report['publication']['action']} - "
          f"{report['publication']['reason']}")
    if report["publication"]["keep"]:
        keep = report["publication"]["keep"]
        print(f"retaining: version {keep['version']} at "
              f"{str(keep['documented_commit'])[:12]}")
    else:
        print("retaining: no previous verified publication is recorded")
    if args.report:
        write_json_report(Path(args.report), report)
        print(f"wrote {args.report}")
    return EXIT_OK if report["ok"] else EXIT_FAIL


def _asked(name: str, args) -> bool:
    """Whether an optional stage was asked for at all.

    The provider is always asked for on the release target: whether it is
    skipped (the candidate carries no model-written claim), cannot-run (it does
    and no provider is configured) or run is a decision with three different
    answers that only the stage itself can make.
    """
    return {"identity": bool(args.build_dir),
            "build": bool(args.sphinx),
            "links": bool(args.check_links),
            # Always asked for, because only the stage can tell the two absent
            # cases apart: a runner with no renderer (a skip with a reason) and
            # a renderer that was named and is not there (a failure). A filter
            # here would answer "not requested" to both, and a check nobody can
            # tell apart from an opt-out is a check that quietly stopped running.
            "diagrams": True,
            "provider": True}[name]


def provider_configured() -> bool:
    return bool(os.environ.get("MRMAP_DOCS_PROVIDER_CMD"))


def _narrative_needed(directory: Path | None = None) -> bool:
    """Whether this candidate carries prose a model wrote.

    Only then does a missing provider matter: today the portal carries no
    model-written claim, so the stage is skipped out loud rather than gating a
    dependency the corpus does not have - and the moment an ``inferred`` record
    lands, the same command fails closed on an unavailable provider. Read from
    the store under test, so pointing ``--evidence-dir`` somewhere else cannot
    hide a model-written claim from the stage that has to answer for it.
    """
    for path in evidence_files(directory or EVIDENCE_DIR):
        for _number, record in load_records(path):
            if isinstance(record, dict) and record.get("kind") == "inferred":
                return True
    return False


def shlex_split(command: str) -> list[str]:
    import shlex
    return shlex.split(command)


def _which(name: str) -> str | None:
    import shutil
    return shutil.which(name) or os.environ.get("MMDC")


def _diagram_action(cli: str, build_dir: Path):
    """Render every mermaid block of the corpus with the Mermaid CLI.

    The portal renders diagrams as their own source offline by design, so the
    only thing a renderer adds is the proof that the source *parses*: a diagram
    nobody can render is a diagram no reader can read.
    """
    sources = []
    for page in sorted((ROOT / "docs").rglob("*")):
        if page.suffix not in {".md", ".rst"} or not page.is_file():
            continue
        text = _read(page)
        for block in re.findall(r"```mermaid\n(.*?)```", text, re.S) + \
                re.findall(r"\.\.\s+mermaid::\n((?:[ \t]*\n|[ \t]+\S.*\n)*)", text):
            if block.strip():
                sources.append((page, block))

    def action():
        findings = []
        with tempfile.TemporaryDirectory() as tmp:
            for index, (page, block) in enumerate(sources):
                source = Path(tmp) / f"{index}.mmd"
                target = Path(tmp) / f"{index}.svg"
                source.write_text(block, encoding="utf-8")
                code, output = run_command([cli, "-i", str(source),
                                            "-o", str(target)], cwd=tmp)
                if code != 0 or not target.is_file():
                    findings.append(("mermaid",
                                     f"{page.relative_to(ROOT)} block {index}: "
                                     f"{output.strip()[:200] or 'no SVG'}"))
                    break
        entry = {"attempt": 0, "reason": f"{len(sources)} block(s) rendered",
                 "exit_code": 0 if not findings else 1}
        return not findings, findings, entry
    return action


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_gate", description=__doc__.splitlines()[0],
        epilog="exit 0 the candidate is accepted, 1 the gate decides against it, "
               "2 the gate could not run")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("evidence", help="validate the evidence store")
    p.add_argument("--dir", default=str(EVIDENCE_DIR))
    p.add_argument("--check-generated", action="store_true",
                   help="require one evidence record per generated page")
    p.add_argument("--check-logs", default=None,
                   help="redaction-scan every file under this directory too")
    p.add_argument("--write", action="store_true",
                   help="regenerate the evidence store of the generated pages")
    p.set_defaults(func=cmd_evidence)

    p = sub.add_parser("coverage", help="measure every surface against its "
                                        "committed contract")
    p.add_argument("--report", default=None)
    p.add_argument("--baseline", default=str(BASELINE_FILE))
    p.add_argument("--write-baseline", action="store_true",
                   help="re-measure the contract from the software and write it "
                        "back; review the diff, it is a coverage decision")
    p.set_defaults(func=cmd_coverage)

    p = sub.add_parser("gate", help="run the stages and decide publication")
    p.add_argument("--target", choices=sorted(STAGES), default="pr")
    p.add_argument("--report", default=None)
    p.add_argument("--evidence-dir", default=str(EVIDENCE_DIR))
    p.add_argument("--baseline", default=str(BASELINE_FILE),
                   help="the coverage contract to measure against")
    p.add_argument("--build-dir", default="docs/build/html")
    p.add_argument("--sphinx", default=os.environ.get("MRMAP_DOCS_PYTHON"),
                   help="python of the pinned docs environment, e.g. "
                        "/tmp/docsenv/bin/python")
    p.add_argument("--check-links", action="store_true",
                   help="run linkcheck as a stage (needs network)")
    p.add_argument("--mmdc", default=None, help="path of the Mermaid CLI")
    p.add_argument("--provider-cmd", default=None,
                   help="command that answers the DocumentAgent interface")
    p.add_argument("--require-narrative", action="store_true",
                   help="treat the narrative stage as required even with no "
                        "inferred claim in the store")
    p.add_argument("--require-locale", action="append", default=[],
                   choices=["en", "de"])
    p.add_argument("--expect-sha", default=None)
    p.add_argument("--expect-version", default=None)
    p.add_argument("--candidate", default=None,
                   help="JSON with version, documented_commit, source_digest")
    p.add_argument("--keep-report", default=None,
                   help="report of the last verified publication to retain")
    p.add_argument("--actor", default=None)
    p.set_defaults(func=cmd_gate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except CannotRun as error:
        print(f"docs_gate: cannot run: {error}", file=sys.stderr)
        return EXIT_CANNOT


if __name__ == "__main__":
    sys.exit(main())
