#!/usr/bin/env python3
"""The deterministic half of the documentation pipeline (#1598, epic #1589).

ADR-0001 section 1 draws the line this module sits on: **what the source states**
is extracted by code, and nothing here writes prose, calls a model, or makes a
judgement. Given the same tree the output is byte-identical, which is what makes
the facts usable as a cache key, as a coverage denominator, and as the only thing
a model is allowed to write about.

One function per surface, one surface per ADR-0001 section 2 row:

``resources``  every ``name:`` of ``frontend/src/components/Resource/Definition.tsx``
``models``     every ``models.Model`` subclass of ``backend/*/models*.py``
``relations``  every ``ForeignKey`` / ``OneToOneField`` / ``ManyToManyField``
``settings``   every module-level uppercase assignment of ``backend/MrMap/settings.py``
``commands``   every ``backend/*/management/commands/*.py``
``tasks``      every task decorator under ``backend/*/tasks/``
``services``   every service key of each committed compose file
``features``   every ``.feature`` file of the Behave suite

Parsing is text-level on purpose. ``ast`` would be better for Python, but the
extractor must run on a machine where the application is not importable and the
file may not even be valid for this interpreter - and the ADR's own baseline was
measured with these exact regexes, so reproducing them is the contract. Where a
regex is knowingly approximate the fact carries a warning rather than a claim, and
the gate counts what it could not read instead of pretending it read nothing.

Every fact carries its sources: the relative path, the line span, and the digest
of the file as it stood. That is what lets a later reader verify a page against
the revision it was generated from, and what makes "the model invented a field"
detectable: no citation, no sentence.

Run ``python3 scripts/docs_extract.py --surface models --json`` from the repository
root for one surface, or ``--surface all`` for the register the pipeline consumes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402

DEFINITION_TSX = "frontend/src/components/Resource/Definition.tsx"
SETTINGS_PY = "backend/MrMap/settings.py"
BEHAVE_FEATURES = "backend/tests/behave/features"

#: Compose files the repository commits. Discovered rather than curated where the
#: name pattern holds; this tuple names the pattern's expected shape so a suite can
#: fail when a new variant appears and nobody added it to the denominator.
COMPOSE_GLOB = "docker-compose*.yml"

RESOURCE_NAME_RE = re.compile(r'\bname\s*:\s*"([A-Za-z0-9_]+)"')
MENU_GROUP_RE = re.compile(r'\bgroup\s*:\s*"([^"]+)"')
MODEL_CLASS_RE = re.compile(
    r"^class\s+(\w+)\s*\(([^)]*models\.Model[^)]*)\)", re.MULTILINE)
RELATION_RE = re.compile(
    r"\b(?:models\.)?(ForeignKey|OneToManyField|OneToOneField|ManyToManyField)"
    r"\s*\(\s*(?:['\"]([^'\"]+)['\"]|\w+)")
SETTING_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")
TASK_DECORATOR_RE = re.compile(
    r"^[ \t]*@(?:shared_task|app\.task|celery_app\.task|celery\.task)\b.*$",
    re.MULTILINE)
TASK_DEF_RE = re.compile(r"^\s*def\s+(\w+)\s*\(", re.MULTILINE)
FEATURE_NAME_RE = re.compile(r"^\s*Feature\s*:\s*(.+?)\s*$", re.MULTILINE)
HELP_TEXT_RE = re.compile(r"\bhelp\s*=\s*_?\s*[\"'](?P<text>.*?)[\"']", re.DOTALL)

#: Files whose name says "this is not a model module", matched on the stem. The
#: registry split left migrations and test helpers beside real models; counting
#: them would inflate a denominator, which the ADR forbids in both directions.
SKIP_MODEL_STEMS = ("tests", "test", "admin", "apps", "signals", "serializers",
                    "views", "urls", "factories")


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _span_of(text: str, needle: str, hint: int = 0) -> tuple[int, int]:
    """The 1-based inclusive line span of ``needle`` in ``text``, nearest ``hint``."""
    lines = _lines(text)
    best, best_distance = (1, 1), None
    for index, line in enumerate(lines):
        if needle and needle in line:
            distance = abs(index - hint)
            if best_distance is None or distance < best_distance:
                best, best_distance = (index + 1, index + 1), distance
    return best


def _fact(workspace, *, surface: str, kind: str, name: str, rel: str,
          span: tuple[int, int], fields=(), extra=None, **known) -> dict:
    """One fact, with its sources computed from the file's actual bytes.

    The span is stored exclusive-end, the way a reader quotes a range: ``[41, 97)``
    for lines 41 through 96. A reader who wants the text asks for the file, takes
    the lines and compares the blob - which is the only verification that does not
    trust this module's own arithmetic.
    """
    data = workspace.read_bytes(rel)
    fact = {"kind": kind, "name": name, "surface": surface,
            "sources": [contract.source_ref(rel, span, data)]}
    if fields:
        fact["fields"] = list(fields)
    for key in ("app", "value", "default", "help"):
        if known.get(key) is not None:
            fact[key] = known[key]
    merged = {k: v for k, v in (extra or {}).items() if v is not None}
    if merged:
        fact["extra"] = merged
    return fact


# ------------------------------------------------------------------- surfaces ---
def extract_resources(workspace) -> tuple[list[dict], list[str]]:
    """Every registered frontend resource, from the one file that registers them.

    ``Definition.tsx`` is the denominator ADR-0001 section 2 names, and the reason
    it is the denominator: the menu, the routes and the API client all hang off
    this list, so a resource that exists in the product is in it. Counting names
    anywhere else would measure the docs' imagination.
    """
    warnings: list[str] = []
    if not workspace.exists(DEFINITION_TSX):
        return [], [f"{DEFINITION_TSX} not found: the resources surface has no "
                    "denominator and coverage cannot be measured"]
    text = workspace.read_text(DEFINITION_TSX)
    facts = []
    for match in RESOURCE_NAME_RE.finditer(text):
        name = match.group(1)
        line = text[:match.start()].count("\n")
        start, end = _span_of(text, f'name: "{name}"', line)
        scope = text[max(0, match.start() - 600):match.start() + 600]
        groups = MENU_GROUP_RE.findall(scope)
        fields = [name]
        if groups:
            fields.append(f"group:{groups[-1]}")
        facts.append(_fact(workspace, surface="resources", kind="resource",
                           name=name, rel=DEFINITION_TSX, span=(start, end),
                           fields=fields))
    if not facts:
        warnings.append(f"no resource names found in {DEFINITION_TSX}: either the "
                        "file changed shape or the extractor is out of date - "
                        "a zero denominator is never a pass")
    return facts, warnings


def _model_files(workspace) -> list[str]:
    """The model modules, in both shapes the repository uses.

    ``backend/<app>/models.py`` and ``backend/<app>/models/<surface>.py`` are both
    model modules - the registry split moved the registry's models into a package
    and left the others as single files - so membership is decided by the file's
    name *or* its directory. Deciding on the name alone silently loses the largest
    model surface in the repository, which is precisely the kind of false-zero
    denominator ADR-0001 section 2 forbids.
    """
    found = []
    for rel in workspace.walk("backend", suffixes=(".py",)):
        parts = Path(rel).parts[:-1]
        if "migrations" in parts or "tests" in parts:
            continue
        stem = Path(rel).stem
        if stem in SKIP_MODEL_STEMS:
            continue
        if stem == "models" or stem.startswith("models_") or "models" in parts:
            found.append(rel)
    return found


def extract_models(workspace) -> tuple[list[dict], list[str]]:
    """Every ``models.Model`` subclass, per app.

    The ADR counts 55 at its anchor by walking ``models.py`` and ``models/*.py``;
    this walks the same set, skipping migrations and test helpers, so the
    denominator is comparable with the committed baseline rather than merely
    plausible.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in _model_files(workspace):
        text = workspace.read_text(rel)
        app = Path(rel).parts[1] if len(Path(rel).parts) > 2 else None
        for match in MODEL_CLASS_RE.finditer(text):
            name, bases = match.group(1), match.group(2)
            start, end = _span_of(text, f"class {name}(",
                                  text[:match.start()].count("\n"))
            fields = sorted(set(re.findall(r"\b(\w+)\s*=\s*models\.\w+",
                                           text[match.end():match.end() + 4000])))
            facts.append(_fact(workspace, surface="models", kind="model", name=name,
                               rel=rel, span=(start, end), app=app,
                               fields=fields, extra={"bases": bases.strip()}))
    if not facts:
        warnings.append("no Django models found under backend/: the models and "
                        "relations surfaces would report a false zero")
    return facts, warnings


def extract_relations(workspace) -> tuple[list[dict], list[str]]:
    """Every FK/O2O/M2M, attributed to the model whose body declares it.

    The target is recorded as written (``"registry.Catalogue"`` or a variable)
    because resolving a string target needs the import graph, and a resolved
    target the extractor guessed is worse than a raw one the reader can check.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in _model_files(workspace):
        text = workspace.read_text(rel)
        app = Path(rel).parts[1] if len(Path(rel).parts) > 2 else None
        owners = [(match.group(1), text[:match.start()].count("\n"))
                  for match in MODEL_CLASS_RE.finditer(text)]
        for match in RELATION_RE.finditer(text):
            kind, target = match.group(1), match.group(2)
            line = text[:match.start()].count("\n")
            owner = next((name for name, start in reversed(owners) if start <= line),
                         None)
            if owner is None:
                warnings.append(f"{rel}:{line + 1}: relation outside any model "
                                "class body; counted, owner unknown")
                owner = "unknown"
            start, end = _span_of(text, match.group(0).split("(")[0], line)
            field = re.search(r"^\s*(\w+)\s*=", text.splitlines()[line]
                              if line < len(text.splitlines()) else "")
            name = f"{owner}.{field.group(1) if field else f'relation{line + 1}'}"
            facts.append(_fact(workspace, surface="relations", kind=kind.lower(),
                               name=name, rel=rel, span=(start, end), app=app,
                               fields=[kind] + ([f"target:{target}"] if target else []),
                               extra={"owner": owner, "target": target}))
    return facts, warnings


def extract_settings(workspace) -> tuple[list[dict], list[str]]:
    """Every module-level uppercase assignment of the project settings module.

    Distinct names, not assignment lines: the ADR's denominator is 158 names from
    164 lines, and a surface that counts a setting twice when it is assigned twice
    measures the file's style rather than the software's configuration.
    """
    warnings: list[str] = []
    if not workspace.exists(SETTINGS_PY):
        return [], [f"{SETTINGS_PY} not found: the settings surface has no "
                    "denominator"]
    text = workspace.read_text(SETTINGS_PY)
    lines = _lines(text)
    seen: dict[str, dict] = {}
    for index, line in enumerate(lines):
        if line[:1].isspace():
            continue                       # nested assignments are not settings
        match = SETTING_RE.match(line)
        if not match:
            continue
        name, raw = match.group(1), match.group(2).strip()
        if name in seen:
            continue
        seen[name] = _fact(workspace, surface="settings", kind="setting", name=name,
                           rel=SETTINGS_PY, span=(index + 1, index + 1),
                           value=raw[:200] or None,
                           help=_comment_above(lines, index))
    return list(seen.values()), warnings


def _comment_above(lines: list[str], index: int) -> str | None:
    """The contiguous comment block above an assignment, if any.

    This is the only place the extractor reads prose, and it reads it verbatim:
    the comment the developer wrote is a fact about the setting, and quoting it is
    not authoring. Where the model later explains a setting in its own words, that
    text is ``inferred`` and carries a citation back to this fact.
    """
    collected: list[str] = []
    cursor = index - 1
    while cursor >= 0:
        stripped = lines[cursor].strip()
        if stripped.startswith("#"):
            collected.append(stripped.lstrip("# ").strip())
            cursor -= 1
        elif not stripped and collected:
            cursor -= 1
        else:
            break
    text = " ".join(reversed(collected)).strip()
    return text[:1000] or None


#: How much of a command's own help a fact carries. The coverage contract asks the
#: operations reference to name the command "with its help text", which is the
#: summary a reader scans for - not the module's whole documentation, which stays
#: reachable at the span the evidence record cites.
HELP_TEXT_CHARS = 700


def _first_paragraph(text: str) -> str:
    """The leading paragraph of a docstring, on one line and within the cap."""
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return ""
    paragraph = collapsed.split("\n\n")[0]
    if len(paragraph) > HELP_TEXT_CHARS:
        paragraph = paragraph[:HELP_TEXT_CHARS].rsplit(" ", 1)[0] + " ..."
    return paragraph


def extract_commands(workspace) -> tuple[list[dict], list[str]]:
    """Every management command, with the help text Django would show.

    ``help`` is taken from the module docstring or the ``help =`` attribute, which
    is the developer's own sentence about what the command does - a fact with a
    line span behind it, not a model's summary of one.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in workspace.walk("backend", suffixes=(".py",)):
        parts = Path(rel).parts
        if "management" not in parts or "commands" not in parts:
            continue
        if Path(rel).stem == "__init__":
            continue
        text = workspace.read_text(rel)
        name = Path(rel).stem
        app = parts[parts.index("management") - 1] if "management" in parts else None
        doc = re.match(r'\s*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', text, re.DOTALL)
        help_match = HELP_TEXT_RE.search(text)
        help_text = None
        span = (1, min(len(_lines(text)), 10))
        if doc and doc.group(1).strip():
            help_text = _first_paragraph(doc.group(1))
        elif help_match:
            help_text = _first_paragraph(help_match.group("text"))
            span = _span_of(text, "help", text[:help_match.start()].count("\n"))
        else:
            warnings.append(f"{rel}: management command with no help text; the "
                            "operations reference can name it but not explain it")
        facts.append(_fact(workspace, surface="commands", kind="command", name=name,
                           rel=rel, span=span, app=app, help=help_text))
    return facts, warnings


def extract_tasks(workspace) -> tuple[list[dict], list[str]]:
    """Every Celery task definition, by decorator.

    One fact per decorated function. The ADR counts 35 with a line-counting grep,
    which counts decorator lines; counting the definitions instead is the same
    number while the tree holds one task per decorator, and it refuses to inflate
    when a task carries two decorators.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in workspace.walk("backend", suffixes=(".py",)):
        parts = Path(rel).parts
        if "tasks" not in parts or Path(rel).stem == "__init__":
            continue
        text = workspace.read_text(rel)
        app = parts[parts.index("tasks") - 1] if "tasks" in parts else None
        for match in TASK_DECORATOR_RE.finditer(text):
            decorator_line = text[:match.start()].count("\n")
            tail = text[match.end():]
            definition = TASK_DEF_RE.search(tail)
            if not definition:
                warnings.append(f"{rel}:{decorator_line + 1}: task decorator with no "
                                "following def; counted as a warning, not a fact")
                continue
            name = definition.group(1)
            start, end = _span_of(text, f"def {name}(",
                                  decorator_line + definition.group(0).count("\n"))
            facts.append(_fact(workspace, surface="tasks", kind="task", name=name,
                               rel=rel, span=(start, end), app=app,
                               extra={"decorator": match.group(0).strip()}))
    return facts, warnings


def _compose_files(workspace) -> list[str]:
    return [rel for rel in workspace.walk("", suffixes=(".yml", ".yaml"))
            if "/" not in rel and Path(rel).name.startswith("docker-compose")]


def extract_services(workspace) -> tuple[list[dict], list[str]]:
    """Every service key of every committed compose file.

    Parsed with PyYAML when it is importable and with a column-aware scanner when
    it is not: the pipeline runs on a bare runner where PyYAML is not installed,
    and a surface that silently disappears because a dependency is missing is the
    failure mode ADR-0001 section 11 exists to prevent. The two readers are held
    to each other by the suite.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in _compose_files(workspace):
        text = workspace.read_text(rel)
        services, detail = _compose_services(text)
        if detail:
            warnings.append(f"{rel}: {detail}")
        for name, line in services:
            start, end = _span_of(text, f"{name}:", line)
            facts.append(_fact(workspace, surface="services", kind="service",
                               name=name, rel=rel, span=(start, end),
                               extra={"compose_file": rel}))
    if not facts:
        warnings.append("no compose services found: the deployment reference has no "
                        "denominator")
    return facts, warnings


def _compose_services(text: str) -> tuple[list[tuple[str, int]], str | None]:
    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None
    if yaml is not None:
        try:
            document = yaml.safe_load(text) or {}
        except Exception as exc:                      # noqa: BLE001 - reported
            return [], f"PyYAML could not parse it ({type(exc).__name__}); " \
                       "falling back to the scanner"
        services = document.get("services") or {}
        if not isinstance(services, dict):
            return [], "the services key is not a mapping"
        # The line of each key is still needed for the span, so the scanner runs
        # for positions while PyYAML decides membership.
        positions = {name: line for name, line in _scan_service_keys(text)}
        return ([(name, positions.get(name, 0)) for name in services], None)
    return _scan_service_keys(text), "PyYAML is not installed: service keys were " \
                                     "found by indentation, not by YAML parsing"


def _scan_service_keys(text: str) -> list[tuple[str, int]]:
    """Service names, found the way a reader finds them: two spaces under ``services:``."""
    found: list[tuple[str, int]] = []
    inside = False
    for index, line in enumerate(_lines(text), start=1):
        stripped = line.rstrip()
        if not stripped or stripped.lstrip().startswith("#"):
            continue
        if not line[:1].isspace():
            inside = stripped.strip() == "services:"
            continue
        if inside and re.match(r"^  [A-Za-z0-9_.\-]+:\s*(?:#.*)?$", line):
            found.append((line.strip().rstrip(":"), index))
        elif inside and not line.startswith("    "):
            inside = False
    return found


def extract_features(workspace) -> tuple[list[dict], list[str]]:
    """Every Behave feature file: the denominator of the user-workflows surface.

    V-8 of the ADR reports these as unsupported until #1602 has scenarios, which is
    exactly what the facts are for: the count is real, the coverage is zero, and a
    stub names the missing evidence instead of a paragraph implying it exists.
    """
    facts: list[dict] = []
    warnings: list[str] = []
    for rel in workspace.walk(BEHAVE_FEATURES, suffixes=(".feature",)):
        text = workspace.read_text(rel)
        match = FEATURE_NAME_RE.search(text)
        name = match.group(1) if match else Path(rel).stem
        span = _span_of(text, name, text[:match.start()].count("\n")) if match \
            else (1, min(len(_lines(text)), 5))
        facts.append(_fact(workspace, surface="features", kind="feature",
                           name=f"{Path(rel).parent.name}/{Path(rel).stem}",
                           rel=rel, span=span, fields=[f"path:{rel}"],
                           extra={"feature_title": name}))
    return facts, warnings


EXTRACTORS = {
    "resources": extract_resources,
    "models": extract_models,
    "relations": extract_relations,
    "settings": extract_settings,
    "commands": extract_commands,
    "tasks": extract_tasks,
    "services": extract_services,
    "features": extract_features,
}


def _disambiguate(facts: list[dict], warnings: list[str]) -> list[dict]:
    """Make every ``(kind, name)`` in a surface unique, keeping names readable.

    Two facts with one name are two claims about the same thing, and the evidence
    store is keyed by claim: a duplicate would either be refused or overwrite the
    other. Composition legitimately produces duplicates here - two apps each with a
    ``load`` command, the same service key in two compose files - so the name
    carries the discriminator a reader needs anyway (``registry/load``, not an
    ambiguous ``load``). Only the colliding facts are widened, so the common case
    stays exactly as the developer named it.
    """
    seen: dict[tuple[str, str], int] = {}
    for fact in facts:
        key = (fact["kind"], fact["name"])
        seen[key] = seen.get(key, 0) + 1
    used: set[str] = set()
    for fact in facts:
        key = (fact["kind"], fact["name"])
        if seen[key] == 1 and fact["name"] not in used:
            used.add(fact["name"])
            continue
        path = fact["sources"][0]["path"]
        widened = f"{path}/{fact['name']}"
        if widened in used:
            widened = f"{widened}-{fact['sources'][0]['span'][0]}"
        if widened in used:
            warnings.append(f"{fact['surface']}: {widened} could not be made "
                            "unique; the duplicate is reported, not silently kept")
        used.add(widened)
        fact["name"] = widened
    return facts


def extract_surface(workspace, surface: str) -> dict:
    """One surface as a validated ``mrmap.docs.facts.v1`` document."""
    if surface not in EXTRACTORS:
        raise KeyError(f"unknown surface {surface!r}; "
                       f"the extractor knows {', '.join(EXTRACTORS)}")
    facts, warnings = EXTRACTORS[surface](workspace)
    facts = _disambiguate(facts, warnings)
    return contract.facts_document(surface, facts, warnings)


def extract_all(workspace, surfaces: tuple[str, ...] = contract.SURFACES) -> dict:
    """Every surface, keyed by name. The input digest of the whole author stage."""
    return {surface: extract_surface(workspace, surface) for surface in surfaces}


def facts_digest(document: dict) -> str:
    """The digest of one surface's facts: the chokepoint of ADR-0001 section 5.

    One digest per surface means a change to one serializer invalidates one page
    and the paragraphs that cite it - not the whole portal.
    """
    return contract.sha256_obj(document)


def fact_refs(document: dict, evidence_ids) -> list[dict]:
    """Turn facts into the citation objects the author is allowed to reference.

    ``evidence_ids`` cycles positionally rather than by content hash on purpose:
    the evidence records are built from the same facts in the same order, so the
    pairing is stable, and a suite can prove that the record a citation names is
    the one whose sources equal the fact's sources.
    """
    ids = list(evidence_ids)
    if not ids:
        return []
    refs = []
    for index, fact in enumerate(document["facts"]):
        refs.append(contract.fact_ref(
            surface=fact["surface"], kind=fact["kind"], name=fact["name"],
            fields=fact.get("fields", ()),
            evidence_id=ids[index % len(ids)],
            value=fact.get("value"), default=fact.get("default"),
            help_text=fact.get("help")))
    return refs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_extract.py",
        description="Extract the deterministic facts of one documentation surface.")
    parser.add_argument("--surface", default="all",
                        choices=["all", *contract.SURFACES])
    parser.add_argument("--root", default=".", help="tree under documentation")
    parser.add_argument("--json", action="store_true",
                        help="print the facts document instead of a summary")
    parser.add_argument("--out", help="write the document here, inside --root")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work")
    try:
        if args.surface == "all":
            payload: object = extract_all(workspace)
        else:
            payload = extract_surface(workspace, args.surface)
    except workspace_lib.GuardError as exc:
        print(f"extract refused: {exc}", file=sys.stderr)
        return contract.EXIT_CANNOT
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        workspace.write_text(args.out, text, kind="facts")
        print(f"wrote {args.out}")
    if args.json or not args.out:
        print(text, end="")
    if args.surface != "all":
        warnings = payload.get("warnings") or []          # type: ignore[union-attr]
        for warning in warnings:
            print(f"warning: {workspace_lib.scrub_text(warning)}", file=sys.stderr)
    return contract.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
