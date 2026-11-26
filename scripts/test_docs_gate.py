#!/usr/bin/env python3
"""Offline checks for scripts/docs_gate (issue #1607, epic #1589).

The gate decides whether documentation gets published, so the question this
suite answers is not "does it run" but "does it refuse". Every rule is woken up
RED at least once with the finding it names, and the SAME scenario is then run
GREEN with the missing digest, exit code, model name or locale added - the
standard of ``scripts/test_release_gates.py``, applied to documentation. A gate
nobody has seen refuse something is a gate that publishes whatever it is given.

Nothing here needs Sphinx, a browser, a model, network access or the
application: cases are records and provenance documents written into a temporary
directory, and the gate is called through the same :func:`docs_gate.main` entry
point CI calls, so the CLI contract - 0 accepted, 1 refused, 2 could not run -
is what gets asserted rather than an internal return value.

Run from the repository root: ``python3 scripts/test_docs_gate.py``.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GATE = HERE / "docs_gate.py"
SCHEMAS = HERE / "docs_gate_schemas.json"
BASELINE = HERE / "docs_coverage_floors.json"
EVIDENCE_STORE = ROOT / "docs" / "evidence"
EXT_DIR = ROOT / "docs" / "source" / "_ext"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
          + (f"  - {detail}" if detail and not ok else ""))


def load_gate():
    spec = importlib.util.spec_from_file_location("docs_gate", GATE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["docs_gate"] = module
    spec.loader.exec_module(module)
    return module


G = load_gate()


def run_gate(*argv) -> tuple[int, str]:
    """Call the gate the way CI calls it and return (exit code, output)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = G.main(list(argv))
    return code, out.getvalue() + err.getvalue()


def gate_report(*argv) -> tuple[int, dict, str]:
    """Run the gate with ``--report`` into a throw-away file and parse it.

    A case that reads the report rather than the printed table asserts on what
    CI actually consumes: stdout is for the operator, the report is the
    artifact, and a check on a sliced printout can go green or red for reasons
    that have nothing to do with the decision.
    """
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        code, output = run_gate(*argv, "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    return code, document, output


def stage_of(document: dict, name: str) -> dict:
    return next(s for s in document["stages"] if s["name"] == name)


def blob_of(text: str) -> str:
    """git's blob id for these bytes, computed the way git computes it."""
    body = text.encode("utf-8")
    return "sha1:" + hashlib.sha1(
        f"blob {len(body)}\0".encode("ascii") + body).hexdigest()


def write_store(directory: Path, records: list[dict]) -> Path:
    """Write `records` as one store file. Only for the plain `evidence` command,
    which checks the store it is given and nothing else."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "case.evidence.jsonl"
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n"
                            for r in records), encoding="utf-8")
    return path


def store_with_gate_records(directory: Path, extra: list[dict]) -> Path:
    """The committed store plus `extra`, in a directory of its own.

    The gate's evidence stage insists every generated page carries a record, and
    that insistence is not a switch the tests may flip: so a gate case copies the
    real store and adds what it wants refused. Everything the real store already
    proves stays proven, and the only thing that can turn the run red is the
    record being tested.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for source in sorted(EVIDENCE_STORE.glob("*.evidence.jsonl")):
        shutil.copy(source, directory / source.name)
    write_store(directory, extra)
    return directory


def record(**overrides) -> dict:
    """A minimal valid `extracted` record, overridable field by field.

    The defaults name a real file of the real tree with its real digest, so the
    baseline case satisfies the blob rule and only the field under test decides.
    """
    source = "docs/architecture.md"
    base = {
        "schema": "mrmap.docs.evidence.v1",
        "id": "sha256:" + hashlib.sha256(source.encode()).hexdigest(),
        "claim": "the architecture note describes the platform",
        "kind": "extracted",
        "page": "design/case.md",
        "sources": [{"path": source,
                     "blob": blob_of((ROOT / source).read_text(encoding="utf-8"))}],
        "produced_by": {"engine": "extractor", "model": None},
        "reviewed": None,
    }
    base.update(overrides)
    if "id" not in overrides:
        base["id"] = "sha256:" + hashlib.sha256(
            (str(base["claim"]) + json.dumps(base["sources"], sort_keys=True))
            .encode()).hexdigest()
    return base


def write_contract(tmp: Path, mutate) -> Path:
    """A copy of the committed contract with one deliberate change in it."""
    document = json.loads(BASELINE.read_text(encoding="utf-8"))
    mutate(document)
    path = tmp / "contract.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# ------------------------------------------------------------------------ schema ---
def test_the_schema_file_is_the_one_the_gate_honours() -> None:
    document = json.loads(SCHEMAS.read_text(encoding="utf-8"))
    try:
        G.check_keywords(document)
        check("the schema uses only keywords the validator implements", True)
    except G.CannotRun as error:
        check("the schema uses only keywords the validator implements", False,
              str(error))
    check("the schema declares every artifact the gate emits",
          {"evidence", "report", "candidate", "coverage_baseline", "stage"}
          <= set(document.get("$defs", {})),
          str(sorted(document.get("$defs", {}))))

    # A keyword the validator does not implement has to be a cannot-run. A
    # validator that quietly ignored `dependentRequired` would accept what that
    # keyword refuses, and nothing downstream would ever learn.
    tampered = json.loads(json.dumps(document))
    tampered["$defs"]["evidence"]["dependentRequired"] = {"claim": ["page"]}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "schemas.json"
        path.write_text(json.dumps(tampered), encoding="utf-8")
        original = G.SCHEMA_FILE
        try:
            G.SCHEMA_FILE = path
            code, output = run_gate("evidence", "--dir", str(EVIDENCE_STORE))
        finally:
            G.SCHEMA_FILE = original
    check("an unimplemented schema keyword cannot run rather than pass",
          code == 2 and "does not implement" in output,
          f"exit {code}: {output.strip()[:180]}")


def test_the_schema_refuses_a_malformed_record() -> None:
    problems = G.validate_named(
        {"schema": "mrmap.docs.evidence.v1", "kind": "telepathic"}, "evidence")
    check("a record with an unknown kind and missing fields is refused",
          any("kind" in p for p in problems)
          and any("claim" in p for p in problems)
          and any("sources" in p for p in problems),
          str(problems[:4]))


# ----------------------------------------------------------------------- evidence ---
def test_a_valid_record_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record()])
        code, output = run_gate("evidence", "--dir", tmp)
    check("a well-formed evidence record is accepted", code == 0,
          output.strip()[:200])


def test_missing_evidence_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, output = run_gate("evidence", "--dir", tmp, "--check-generated")
    check("generated pages with no evidence store at all are refused",
          code == 1 and "no evidence record" in output,
          f"exit {code}: {output.strip()[:180]}")


def test_a_generated_page_without_a_record_is_refused() -> None:
    pages = G.generated_pages()
    if len(pages) < 2:
        check("there are generated pages to test", False, str(pages))
        return
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [
            record(page=str(p.relative_to(G.PORTAL_SOURCE))) for p in pages[1:]])
        code, output = run_gate("evidence", "--dir", tmp, "--check-generated")
    missing = str(pages[0].relative_to(G.PORTAL_SOURCE))
    check("one generated page without a record is refused (V-13)",
          code == 1 and missing in output, f"exit {code}: {output[:200]}")


def test_stale_evidence_is_refused() -> None:
    """A digest that no longer matches its file is evidence about a dead tree."""
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(sources=[{
            "path": "docs/architecture.md", "blob": "sha1:" + "0" * 40}])])
        code, output = run_gate("evidence", "--dir", tmp)
    check("evidence whose source digest no longer matches is stale, not valid",
          code == 1 and "stale" in output, f"exit {code}: {output[:200]}")

    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(sources=[{
            "path": "docs/does-not-exist.md", "blob": "sha1:" + "0" * 40}])])
        code, output = run_gate("evidence", "--dir", tmp)
    check("evidence about a file that is not in the tree is refused",
          code == 1 and "not in the tree" in output,
          f"exit {code}: {output[:200]}")


def test_executed_evidence_must_have_actually_run() -> None:
    """V-14: `executed` claims something ran, so it has to show its work."""
    assertion = {"command": "true", "exit_code": 0,
                 "stdout_sha256": "sha256:" + "a" * 64}
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="executed", assertion=assertion)])
        code, output = run_gate("evidence", "--dir", tmp)
    check("executed evidence with command, zero exit and output digest passes",
          code == 0, output[:160])

    cases = {
        "a command that exited non-zero": (
            {**assertion, "exit_code": 1}, "not proven"),
        "an exit code that is not an integer": (
            {**assertion, "exit_code": "0"}, "type"),
        "no recorded output digest": (
            {k: v for k, v in assertion.items() if k != "stdout_sha256"},
            "sha256"),
        "an output digest of the wrong shape": (
            {**assertion, "stdout_sha256": "sha256:abc"}, "does not match"),
    }
    for name, (broken, expected) in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            write_store(Path(tmp), [record(kind="executed", assertion=broken)])
            code, output = run_gate("evidence", "--dir", tmp)
        check(f"executed evidence with {name} is refused",
              code == 1 and expected in output,
              f"exit {code}: {output.strip()[:180]}")

    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="executed")])
        code, output = run_gate("evidence", "--dir", tmp)
    check("executed evidence with no assertion at all is refused",
          code == 1 and "assertion" in output, f"exit {code}: {output[:180]}")


def test_inferred_evidence_must_cite_facts_it_was_given() -> None:
    facts = ["harvesting runs nightly", "the UI shows a job per service"]
    modelled = {"engine": "author", "model": "some-model-1"}
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="inferred", facts=facts,
                                       cited_fact_ids=[facts[0]],
                                       produced_by=modelled)])
        code, output = run_gate("evidence", "--dir", tmp)
    check("inferred prose citing only given facts and naming its model passes",
          code == 0, output[:160])

    for name, overrides, expected in (
        ("that cites a fact nobody gave it",
         {"facts": facts, "cited_fact_ids": ["made-up-feature"],
          "produced_by": modelled}, "not in its own facts[]"),
        ("that names no model",
         {"facts": facts, "cited_fact_ids": [facts[0]],
          "produced_by": {"engine": "author", "model": None}},
         "name the model"),
        ("that omits its citations",
         {"facts": facts, "produced_by": modelled}, "fact ids"),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            write_store(Path(tmp), [record(kind="inferred", **overrides)])
            code, output = run_gate("evidence", "--dir", tmp)
        check(f"inferred prose {name} is refused",
              code == 1 and expected in output,
              f"exit {code}: {output.strip()[:180]}")


def test_human_evidence_must_say_who_reviewed_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="human",
                                       reviewed={"by": "maintainer"})])
        code, _ = run_gate("evidence", "--dir", tmp)
    check("human evidence naming its reviewer passes", code == 0)

    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="human", reviewed=None)])
        code, output = run_gate("evidence", "--dir", tmp)
    check("human evidence with no reviewer and no legacy mark is refused",
          code == 1 and "reviewer" in output, f"exit {code}: {output[:180]}")

    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [record(kind="human",
                                       reviewed={"legacy": True})])
        code, _ = run_gate("evidence", "--dir", tmp)
    check("the grandfathered corpus is allowed when it says so", code == 0)


def test_duplicate_evidence_ids_are_refused() -> None:
    one = record(claim="first claim")
    two = record(claim="second claim", id=one["id"])
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [one, two])
        code, output = run_gate("evidence", "--dir", tmp)
    check("two records claiming one id are refused",
          code == 1 and "one claim, one record" in output,
          f"exit {code}: {output[:180]}")


def test_a_malformed_evidence_file_cannot_run() -> None:
    """Truncated JSON is a broken tool, not a documentation failure."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "broken.evidence.jsonl").write_text(
            '{"schema": "mrmap.docs.evidence.v1",\n', encoding="utf-8")
        code, output = run_gate("evidence", "--dir", tmp)
    check("an unparseable evidence file exits 2 rather than passing",
          code == 2 and "cannot run" in output, f"exit {code}: {output[:180]}")


def test_the_committed_evidence_store_is_valid() -> None:
    """The store CI gates has to be valid today, or the gate is decoration."""
    code, output = run_gate("evidence", "--dir", str(EVIDENCE_STORE),
                            "--check-generated")
    check("the committed evidence store passes its own rules", code == 0,
          output.strip()[:240])


# ----------------------------------------------------------------------- redaction ---
PLACEHOLDERS = [
    'DATABASE_URL=postgresql://mcp_readonly:<RO_PW>@127.0.0.1:15432/mrmap',
    'DATABASE_URL=postgres://mrmap:${DB_PASSWORD}@db:5432/mrmap',
    'DJANGO_SECRET_KEY=changeme',
    'export SECRET_KEY=example-value-not-a-real-one',
    'redis://:mypassword@localhost:6379',
    'postgres://user:pass@127.0.0.1:5432/db',
    '"api_key": "<YOUR_KEY>"',
    '"token": "xxxxxxxxxxxx"',
    'amqp://guest:guest@0.0.0.0:5672',
    'celery://user:changeme@broker.internal:5672/0',
    'redis://:placeholder-value@redis.internal:6379/0',
]
SECRETS = [
    'postgresql://mrmap:Rea1PasswordValue@db.internal:5432/mrmap',
    'postgres://mrmap:Rea1PasswordValue@db.internal/mrmap',
    'mysql://app:S3cretPassword@mysql.prod:3306/app',
    'export DJANGO_SECRET_KEY="abc123def456ghi789"',
    '"DJANGO_SECRET_KEY": "abc123def456ghi789"',
    'aws_secret_access_key = "wJalrXUtnFEMI7MDENGbPxRfiC"',
    '"AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI7MDENGbPxRfiC"',
    '"access_token": "ghp_' + "a" * 36 + '"',
    "-----BEGIN RSA PRIVATE KEY-----",
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_" + "a" * 36,
    "AIzaSyabcdefghijklmnopqrstuvwxyz1234567",
    "xoxb-1234567890abcdefghijklmnop",
    "sk-" + "A" * 30,
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
     ".eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"),
]


def test_redaction_finds_real_secrets() -> None:
    missed = [secret for secret in SECRETS
              if not G.redaction_findings(secret, "case")]
    check("every secret shape the gate claims to refuse is refused",
          not missed, ", ".join(s[:44] for s in missed))


def test_redaction_allows_documented_placeholders() -> None:
    """A check that cries wolf gets disabled; documentation is full of these."""
    fired = [text for text in PLACEHOLDERS
             if G.redaction_findings(text, "case")]
    check("documented placeholders and local URLs are not reported as secrets",
          not fired, ", ".join(t[:44] for t in fired))


def test_a_secret_in_evidence_is_refused() -> None:
    leaked = record(claim="the connection string is postgresql://mrmap:"
                          "Rea1PasswordValue@db.internal:5432/mrmap")
    with tempfile.TemporaryDirectory() as tmp:
        write_store(Path(tmp), [leaked])
        code, output = run_gate("evidence", "--dir", tmp)
    check("evidence carrying a credential is refused",
          code == 1 and "database-url-with-credentials" in output,
          f"exit {code}: {output[:200]}")


def test_the_finding_does_not_echo_the_secret() -> None:
    """The report is an artifact people read; it must not repeat what leaked."""
    findings = G.redaction_findings(
        'export DJANGO_SECRET_KEY="abc123def456ghi789"', "case")
    check("a redaction finding masks the value it found",
          bool(findings)
          and not any("abc123def456ghi789" in f for f in findings),
          str(findings))


def test_unredacted_build_logs_are_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        logs = Path(tmp) / "logs"
        logs.mkdir()
        (logs / "build.log").write_text(
            "loading settings\nDATABASE_URL=postgres://mrmap:"
            "Rea1PasswordValue@db.internal:5432/mrmap\n", encoding="utf-8")
        store = Path(tmp) / "evidence"
        write_store(store, [record()])
        code, output = run_gate("evidence", "--dir", str(store),
                                "--check-logs", str(logs))
    check("a build log that carried a credential fails the gate",
          code == 1 and "build.log" in output, f"exit {code}: {output[:200]}")


def test_the_committed_documentation_is_clean() -> None:
    findings: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*")):
        if path.is_file() and path.suffix in {".rst", ".md", ".json", ".jsonl"}:
            findings += G.redaction_findings(
                path.read_text(encoding="utf-8", errors="replace"), str(path))
    check("the committed documentation carries nothing unredacted",
          not findings, "; ".join(findings[:3]))


# ------------------------------------------------------------------------ coverage ---
def test_the_coverage_contract_is_a_measurement() -> None:
    """The committed contract must still be exactly what the software yields.

    A hand-lowered floor or a quietly deleted gap turns a surface into a rubber
    stamp; regenerating and comparing is what keeps it a measurement rather than
    a curated list.
    """
    committed = json.loads(BASELINE.read_text(encoding="utf-8"))
    problems = G.validate_named(committed, "coverage_baseline")
    check("the committed coverage contract is schema-valid", not problems,
          str(problems[:4]))
    check("the contract covers every discovered surface",
          set(committed["surfaces"]) == set(G.SURFACES),
          str(set(G.SURFACES) ^ set(committed["surfaces"])))

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "contract.json"
        target.write_text(json.dumps(committed), encoding="utf-8")
        G.write_coverage_contract(target)
        regenerated = json.loads(target.read_text(encoding="utf-8"))
    drift = [name for name in
             set(committed["surfaces"]) | set(regenerated["surfaces"])
             if committed["surfaces"].get(name) != regenerated["surfaces"].get(name)]
    check("regenerating the contract from the software changes nothing",
          not drift, f"drift in {drift}")


def test_coverage_reports_without_failing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "coverage.json"
        code, output = run_gate("coverage", "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    check("coverage of the committed corpus is green", code == 0,
          output.strip()[-200:])
    check("the coverage report names every discovered surface",
          set(document["surfaces"]) == set(G.SURFACES),
          str(set(G.SURFACES) ^ set(document["surfaces"])))
    check("every surface reports its floor, its gaps and its verdict",
          all({"floor", "missing", "new_gaps", "status"} <= set(row)
              for row in document["surfaces"].values()))


def test_losing_documentation_breaks_the_floor() -> None:
    """A generator that silently drops a section must not be able to pass."""
    tokens, corpus = G._corpus_index()
    items = G.discover_surface("commands")
    documented = [i for i in items if G._is_documented(i, tokens, corpus)]
    if not documented:
        check("the commands surface is documented enough to test a floor",
              False, str(items))
        return

    # At the measured value the floor passes; one short of it is red. That is
    # the whole ratchet, and it is the rule that makes a generator safe to run
    # unattended.
    for offset, expected in ((0, 0), (1, 1)):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_contract(
                Path(tmp),
                lambda d, o=offset: d["surfaces"]["commands"].__setitem__(
                    "floor", len(documented) + o))
            code, output = run_gate("coverage", "--baseline", str(path))
        check(f"a floor of {len(documented) + offset} against "
              f"{len(documented)} documented exits {expected}",
              code == expected and (expected == 0 or "commands" in output),
              f"exit {code}: {output.strip()[-160:]}")


def test_new_undocumented_software_is_a_finding() -> None:
    """The half of coverage a floor alone cannot express.

    A setting that no page names and no gap declares arrives every time somebody
    adds a setting without a docs note, so it has to refuse the run. The floor is
    zeroed in both cases so the verdict comes from the gap rule alone.
    """
    planted = "PROBED_SETTING_WITHOUT_A_PAGE"
    original = dict(G.SURFACE_SOURCES)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "settings_probe.py"
            source.write_text(f"{planted} = 'value'\n", encoding="utf-8")
            G.SURFACE_SOURCES["settings"] = [source]

            code, output = run_gate(
                "coverage", "--baseline", str(write_contract(
                    Path(tmp), lambda d: d["surfaces"]["settings"].update(
                        {"floor": 0, "gaps": []}))))
            check("a new setting nobody documented is a red coverage run",
                  code == 1 and planted in output
                  and "undocumented and undeclared" in output,
                  f"exit {code}: {output[:220]}")

            # Declaring it as a known gap is the honest move, and the gate
            # accepts that while still showing the topic as work outstanding.
            code, output = run_gate(
                "coverage", "--baseline", str(write_contract(
                    Path(tmp), lambda d: d["surfaces"]["settings"].update(
                        {"floor": 0, "gaps": [planted]}))))
            check("the same setting declared as a known gap is accepted",
                  code == 0, output.strip()[-200:])
    finally:
        G.SURFACE_SOURCES.clear()
        G.SURFACE_SOURCES.update(original)


def test_a_broken_or_absent_contract_cannot_run() -> None:
    """No floors means every surface passes; a broken file must never mean that."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "contract.json"
        path.write_text('{"schema": "mrmap.docs.coverage-baseline.v1",'
                        ' "surfaces": {}}', encoding="utf-8")
        code, output = run_gate("coverage", "--baseline", str(path))
    check("an empty contract is refused rather than read as no requirements",
          code == 2, f"exit {code}: {output[:180]}")

    with tempfile.TemporaryDirectory() as tmp:
        code, output = run_gate("coverage",
                                "--baseline", str(Path(tmp) / "absent.json"))
    check("a missing contract is a cannot-run rather than a pass",
          code == 2 and "cannot run" in output, f"exit {code}: {output[:180]}")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "contract.json"
        path.write_text('{"surfaces": {"tasks": {"floor": "lots"}}}',
                        encoding="utf-8")
        code, output = run_gate("coverage", "--baseline", str(path))
    check("a contract that is not schema-valid is a cannot-run",
          code == 2 and "not valid" in output, f"exit {code}: {output[:180]}")


def test_a_surface_without_a_contract_entry_cannot_run() -> None:
    """A surface nobody wrote a floor for is a surface nobody can regress."""
    original = dict(G.SURFACES)
    try:
        G.SURFACES.clear()
        G.SURFACES["invented-surface"] = {"adr": "ADR-0001 section 2",
                                          "owner": "Docs Guild"}
        code, output = run_gate("coverage")
    finally:
        G.SURFACES.clear()
        G.SURFACES.update(original)
    check("a surface with no contract entry cannot run",
          code == 2 and "no entry" in output, f"exit {code}: {output[:180]}")


def test_a_surface_with_no_denominator_cannot_run() -> None:
    """An empty denominator passes every floor, so a missing source is fatal."""
    original = dict(G.SURFACE_SOURCES)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            G.SURFACE_SOURCES["settings"] = [Path(tmp) / "absent.py"]
            code, output = run_gate("coverage")
        check("a surface whose defining file is gone cannot run",
              code == 2 and "no denominator" in output,
              f"exit {code}: {output[:180]}")
    finally:
        G.SURFACE_SOURCES.clear()
        G.SURFACE_SOURCES.update(original)


# ------------------------------------------------------------------------ identity ---
def write_provenance(build_dir: Path, candidate: dict, **overrides) -> None:
    data = {
        "schema": "mrmap.docs.provenance.v1",
        "builder": "html",
        "version": candidate["version"],
        "release": candidate["version"],
        "documented_commit": candidate["documented_commit"],
        "source_digest": candidate["source_digest"],
        "toolchain": {"sphinx": "8.1.3"},
        "pages": 1,
    }
    data.update(overrides)
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "provenance.json").write_text(json.dumps(data),
                                               encoding="utf-8")


def test_build_identity_binds_the_artifact_to_a_revision() -> None:
    candidate = G._candidate_identity()
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp) / "html"
        write_provenance(build, candidate)
        findings = G._identity_findings(build, candidate, None, None)
    check("an artifact whose provenance matches the tree is attributable",
          not findings, str(findings[:3]))

    cases = {
        "no provenance at all": ("absent", "provenance"),
        "a provenance of another schema": (
            {"schema": "mrmap.docs.provenance.v0"}, "schema"),
        "no documented commit": ({"documented_commit": None}, "revision"),
        "a truncated commit": ({"documented_commit": "abc123"}, "revision"),
        "another source digest": ({"source_digest": "sha256:" + "b" * 64},
                                  "not built from"),
        "no toolchain version": ({"toolchain": {}}, "reproducible"),
    }
    for label, (overrides, expected) in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            build = Path(tmp) / "html"
            if overrides == "absent":
                build.mkdir()
            else:
                write_provenance(build, candidate, **overrides)
            findings = G._identity_findings(build, candidate, None, None)
        check(f"an artifact with {label} is refused",
              any(expected in detail for _code, detail in findings),
              str(findings[:2]))

    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp) / "html"
        write_provenance(build, candidate)
        findings = G._identity_findings(build, candidate, "0" * 40, None)
    check("documentation of one revision cannot be published as another",
          any("cannot be published as another" in d for _c, d in findings),
          str(findings[:2]))

    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp) / "html"
        write_provenance(build, candidate, version="9.9.9")
        findings = G._identity_findings(build, candidate, None,
                                        candidate["version"])
    check("an artifact claiming another version is refused",
          any("version" in d for _c, d in findings), str(findings[:2]))


def test_the_per_locale_floor_is_measured_per_locale() -> None:
    """V-12: an English-only run must not pass on the aggregate."""
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp) / "html"
        for locale in ("en", "de"):
            (build / locale).mkdir(parents=True)
            (build / locale / "index.html").write_text("<html></html>",
                                                       encoding="utf-8")
        check("both locales producing pages is parity",
              not G._locale_findings(build, ["en", "de"]))
        (build / "de" / "index.html").unlink()
        findings = G._locale_findings(build, ["en", "de"])
        check("a locale that produced no pages is refused",
              any("'de'" in detail for _c, detail in findings),
              str(findings[:2]))
        check("a corpus that promised no locale is held to none",
              not G._locale_findings(build, []))


# -------------------------------------------------------------------------- retries ---
def _failing(calls: dict, clears_at: int = 0):
    def action():
        calls["n"] += 1
        if clears_at and calls["n"] >= clears_at:
            return True, [], {"attempt": 0}
        return False, [("transient", "flaky")], {"attempt": 0}
    return action


def test_the_retry_policy_is_the_adr_budget() -> None:
    check("the retry budgets are the ones ADR-0001 section 8 names",
          G.ATTEMPT_BUDGETS == {"deterministic": 1, "browser": 2, "model": 3},
          str(G.ATTEMPT_BUDGETS))

    for kind, budget in (("deterministic", 1), ("browser", 2), ("model", 3)):
        calls = {"n": 0}
        entry = G.run_stage({"name": f"{kind}-stage", "kind": kind},
                            _failing(calls), retryable=True)
        check(f"a failing {kind} stage exhausts exactly its budget of {budget}",
              calls["n"] == budget and entry["status"] == "fail"
              and entry["attempts"] == budget
              and entry["max_attempts"] == budget,
              f"{calls['n']} attempts, {entry['status']}, "
              f"budget {entry['max_attempts']}")
        check(f"a {kind} stage records why it retried, if it may",
              bool(entry["retry_reason"]) == (budget > 1),
              str(entry["retry_reason"]))


def test_a_stage_that_recovers_within_its_budget_passes() -> None:
    calls = {"n": 0}
    entry = G.run_stage({"name": "links", "kind": "browser"},
                        _failing(calls, clears_at=2), retryable=True)
    check("a transient browser failure that clears on the retry passes",
          entry["status"] == "pass" and entry["attempts"] == 2,
          str(entry["attempts"]))
    check("a recovered retry is still visible in the report",
          bool(entry["retry_reason"]), str(entry["retry_reason"]))

    calls = {"n": 0}
    entry = G.run_stage({"name": "provider", "kind": "model"},
                        _failing(calls, clears_at=3), retryable=True)
    check("a model stage that clears on its last permitted attempt passes",
          entry["status"] == "pass" and entry["attempts"] == 3,
          str(entry["attempts"]))


def test_a_stage_that_passes_never_runs_twice() -> None:
    calls = {"n": 0}

    def action():
        calls["n"] += 1
        return True, [], {"attempt": 0}

    entry = G.run_stage({"name": "browser-stage", "kind": "browser"}, action,
                        retryable=True)
    check("a passing stage is not retried",
          calls["n"] == 1 and entry["status"] == "pass"
          and entry["attempts"] == 1, str(entry))


def test_a_finding_keeps_its_reason_whatever_shape_it_arrives_in() -> None:
    """`stage` is the single funnel from a finding to the report.

    Every stage writes tuples; one site wrote a dict, and because the funnel
    unpacked positionally the operator read the words "code: detail" instead of
    the reason the stage gave. Both shapes now normalize to the same artifact,
    which is only safe because this check exists.
    """
    entry = G.stage("x", kind="model", status="cannot-run", attempts=0,
                    findings=[("a", "tuple reason"),
                              {"code": "b", "detail": "dict reason"}])
    check("a finding is reported by code and reason, from either shape",
          [(f["code"], f["detail"]) for f in entry["findings"]]
          == [("a", "tuple reason"), ("b", "dict reason")],
          str(entry["findings"]))


def test_attempt_numbers_in_the_log_are_1_based_and_distinct() -> None:
    calls = {"n": 0}
    entry = G.run_stage({"name": "links", "kind": "browser"},
                        _failing(calls), retryable=True)
    check("the attempt log numbers its attempts 1..n",
          [a["attempt"] for a in entry["attempt_log"]]
          == list(range(1, entry["attempts"] + 1)),
          str(entry["attempt_log"]))


# --------------------------------------------------------------------- the whole gate ---
def test_the_pull_request_target_runs_the_targeted_checks_only() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        code, output = run_gate("gate", "--target", "pr",
                                "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    check("the targeted generator checks of an ordinary pull request are green",
          code == 0, output.strip()[-200:])
    check("the pull request target runs suite, evidence and coverage only",
          [s["name"] for s in document["stages"]]
          == ["suite", "evidence", "coverage"],
          str([s["name"] for s in document["stages"]]))
    check("the pull request target allows publication",
          document["publication"]["action"] == "allow",
          str(document["publication"]))
    check("no stage of the pull request target exceeded its budget",
          all(s["attempts"] <= s["max_attempts"] for s in document["stages"]),
          str([(s["name"], s["attempts"], s["max_attempts"])
               for s in document["stages"]]))


def test_the_release_target_is_green_end_to_end() -> None:
    """The real strict build, when the pinned docs environment is available."""
    sphinx = os.environ.get("MRMAP_DOCS_PYTHON")
    if not sphinx or not Path(sphinx).is_file():
        check("release target end to end (set MRMAP_DOCS_PYTHON to run)", True)
        return
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        code, output = run_gate(
            "gate", "--target", "release", "--sphinx", sphinx,
            "--build-dir", str(Path(tmp) / "build" / "html"),
            "--report", str(report))
    check("the release target is green end to end", code == 0,
          output.strip()[-260:])


def test_a_required_stage_that_cannot_run_refuses_the_candidate() -> None:
    """The release target without the strict build gates nothing, so it fails."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        code, output = run_gate("gate", "--target", "release",
                                "--sphinx", "", "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    build = next(s for s in document["stages"] if s["name"] == "build")
    check("a release run without --sphinx is a cannot-run on the build stage",
          code == 1 and build["status"] == "cannot-run",
          f"exit {code}, build {build['status']}")
    check("the red candidate is refused and retention decided",
          document["publication"]["action"] == "retain-previous"
          and "build" in document["publication"]["reason"],
          str(document["publication"]))
    check("the report declares itself not ok", document["ok"] is False,
          str(document["ok"]))
    check("a cannot-run is printed as a failure, not as a skip",
          "FAIL  build" in output, output[-240:])


def test_identity_of_a_red_build_is_not_credited() -> None:
    """Otherwise the previous green build of the tree passes on stale bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        build = Path(tmp) / "build" / "html"
        write_provenance(build, G._candidate_identity())
        report = Path(tmp) / "gate.json"
        code, output = run_gate("gate", "--target", "release",
                                "--sphinx", "", "--build-dir", str(build),
                                "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    identity = next(s for s in document["stages"] if s["name"] == "identity")
    check("identity does not run against a build this run refused",
          code == 1 and identity["status"] == "cannot-run"
          and identity["attempts"] == 0
          and any(f["code"] == "build-red" for f in identity["findings"]),
          f"exit {code}: identity {identity['status']}")
    check("the skipped identity says why rather than being silent",
          bool(identity.get("note")), str(identity))


def test_the_gate_refuses_a_candidate_whose_evidence_is_invalid() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = store_with_gate_records(
            Path(tmp) / "evidence",
            [record(sources=[{"path": "docs/architecture.md",
                              "blob": "sha1:" + "0" * 40}])])
        code, document, output = gate_report("gate", "--target", "pr",
                                             "--evidence-dir", str(store))
    evidence = stage_of(document, "evidence")
    check("an ordinary pull request with stale evidence is refused",
          code == 1 and evidence["status"] == "fail"
          and any("stale" in f["detail"] for f in evidence["findings"]),
          f"exit {code}: {evidence['findings'][:1]}")


def test_the_gate_refuses_a_candidate_that_loses_documentation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = write_contract(
            Path(tmp),
            lambda d: d["surfaces"]["tasks"].__setitem__("floor", 10_000))
        code, document, output = gate_report("gate", "--target", "pr",
                                             "--baseline", str(path))
    check("a candidate below a coverage floor is refused",
          code == 1
          and document["coverage"]["tasks"]["status"] == "fail"
          and document["publication"]["action"] == "retain-previous"
          and "tasks" in document["publication"]["reason"],
          f"exit {code}: {document['coverage']['tasks']}")


def test_the_report_validates_against_its_own_schema() -> None:
    """The gate validates what it writes; a report it cannot describe is useless."""
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        run_gate("gate", "--target", "release", "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    problems = G.validate_named(document, "report")
    check("the release report validates against the committed schema",
          not problems, str(problems[:5]))
    check("every skipped stage states why it was skipped",
          all(s["status"] not in ("skipped", "cannot-run")
              or s.get("findings") or s.get("note")
              for s in document["stages"]),
          str([s["name"] for s in document["stages"]
               if s["status"] in ("skipped", "cannot-run")
               and not s.get("note") and not s.get("findings")]))


def test_the_gate_refuses_to_write_an_invalid_report() -> None:
    """A gate that cannot describe its own verdict must not publish one."""
    original = G.validate_named

    def broken(instance, name, root_schema=None):
        if name == "report":
            return ["#/stages/0: 'status' is required"]
        return original(instance, name, root_schema)

    G.validate_named = broken
    try:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = run_gate("gate", "--target", "pr",
                                    "--report", str(Path(tmp) / "g.json"))
    finally:
        G.validate_named = original
    check("a report the schema refuses is a cannot-run, never a publication",
          code == 2 and "invalid report" in output,
          f"exit {code}: {output[:180]}")


def test_retaining_the_last_good_publication_is_named_in_the_failure() -> None:
    """Section 11 in one artifact: red says no, and says what stands."""
    previous = {"candidate": {"version": "0.1.0",
                              "documented_commit": "a" * 40,
                              "source_digest": "sha256:" + "c" * 64}}
    with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp) / "last-good.json"
            keep.write_text(json.dumps(previous), encoding="utf-8")
            report = Path(tmp) / "gate.json"
            path = write_contract(
                Path(tmp),
                lambda d: d["surfaces"]["tasks"].__setitem__("floor", 10_000))
            code, output = run_gate("gate", "--target", "pr",
                                    "--report", str(report),
                                    "--baseline", str(path),
                                    "--keep-report", str(keep))
            document = json.loads(report.read_text(encoding="utf-8"))
    retained = document["publication"]["keep"]
    check("a red run names the last verified publication it retains",
          code == 1 and document["publication"]["action"] == "retain-previous"
          and retained["documented_commit"] == "a" * 40
          and retained["version"] == "0.1.0",
          str(document["publication"]))
    check("the retained publication is printed for the operator",
          "retaining: version 0.1.0" in output, output[-200:])


def test_the_verdict_survives_an_output_path_that_does_not_exist_yet() -> None:
    """A gate that dies on its own output path has neither published nor refused.

    Section 11 has exactly two allowed outcomes, and "traceback" is neither, so
    the report is written into a directory the caller never created rather than
    the run ending in a stack trace.
    """
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "nested" / "deeper" / "gate.json"
        code, output = run_gate("gate", "--target", "pr", "--report", str(report))
        written = (json.loads(report.read_text(encoding="utf-8"))
                   if report.is_file() else None)
    check("a report path whose directories are missing still gets a verdict",
          code == 0 and written is not None and written["ok"] is True
          and "Traceback" not in output,
          f"exit {code}, wrote={written is not None}: {output[-160:]}")


def test_a_green_run_retains_nothing_because_it_needs_to() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "gate.json"
        run_gate("gate", "--target", "pr", "--report", str(report))
        document = json.loads(report.read_text(encoding="utf-8"))
    check("a green run allows publication",
          document["publication"]["action"] == "allow",
          str(document["publication"]))


def test_an_unreadable_keep_report_cannot_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        keep = Path(tmp) / "broken.json"
        keep.write_text("{not json", encoding="utf-8")
        code, output = run_gate("gate", "--target", "pr",
                                "--keep-report", str(keep))
    check("a corrupt last-good report is a cannot-run, not a silent retention",
          code == 2 and "cannot run" in output, f"exit {code}: {output[:180]}")


def test_there_is_no_target_that_publishes_to_production() -> None:
    # Out of process on purpose: argparse rejects an unknown --target with
    # sys.exit, and in-process that is a SystemExit interrupting the suite
    # rather than the exit code being checked.
    refused = subprocess.run([sys.executable, str(GATE), "gate",
                              "--target", "production"],
                             capture_output=True, text=True, cwd=ROOT)
    combined = refused.stdout + refused.stderr
    check("there is no target an operator can invent to publish anyway",
          refused.returncode == 2 and "invalid choice" in combined,
          f"exit {refused.returncode}: {combined[:160]}")
    check("the only targets are the pull request and the release contract",
          set(G.STAGES) == {"pr", "release"}, str(sorted(G.STAGES)))
    check("neither target is named for publishing to production",
          not [name for name in G.STAGES
               if "prod" in name or "publish" in name], str(sorted(G.STAGES)))


def test_an_unusable_candidate_identity_cannot_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "candidate.json"
        candidate.write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")
        code, output = run_gate("gate", "--target", "pr",
                                "--candidate", str(candidate))
    check("a candidate that cannot name its sources cannot be gated",
          code == 2 and "identity" in output, f"exit {code}: {output[:180]}")


# ------------------------------------------------------------------------- provider ---
def _store_with_inferred_claim(directory: Path) -> Path:
    """The real store plus one model-written claim: enough for the provider
    stage to have something to demand, without un-evidencing any page."""
    facts = ["the platform publishes a machine-readable capability list"]
    return store_with_gate_records(directory, [record(
        kind="inferred", claim="the platform publishes a capability list",
        page="design/narrative-case.md",
        facts=facts, cited_fact_ids=[facts[0]],
        produced_by={"engine": "author", "model": "some-model-1"})])


def test_an_unavailable_provider_fails_closed_only_when_it_matters() -> None:
    """No model, no claim, no dependency - but a claim without a model is fatal."""
    with tempfile.TemporaryDirectory() as tmp:
        store = store_with_gate_records(Path(tmp) / "evidence", [])
        code, document, output = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--evidence-dir", str(store))
    provider = stage_of(document, "provider")
    check("with no model-written claim the provider stage is skipped out loud",
          code == 1 and provider["status"] == "skipped"
          and "nothing to ask a provider" in provider.get("note", "")
          and provider["attempts"] == 0,
          f"exit {code}: {provider}")

    with tempfile.TemporaryDirectory() as tmp:
        store = _store_with_inferred_claim(Path(tmp) / "evidence")
        code, document, output = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--evidence-dir", str(store))
    provider = stage_of(document, "provider")
    check("model-written claims with no provider configured fail closed",
          code == 1 and provider["status"] == "cannot-run"
          and any(f["code"] == "provider-unavailable"
                  for f in provider["findings"]),
          f"exit {code}: {provider}")
    check("an unevidenced model claim is never a publish, and says so",
          document["publication"]["action"] == "retain-previous"
          and "provider" in document["publication"]["reason"],
          str(document["publication"]))


def test_the_narrative_stage_can_be_demanded_without_a_claim() -> None:
    """The operator can insist on the narrative check even before the corpus
    carries a model-written claim; a missing provider is then the failure it
    names rather than a stage that quietly skipped itself."""
    with tempfile.TemporaryDirectory() as tmp:
        store = store_with_gate_records(Path(tmp) / "evidence", [])
        code, document, output = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--evidence-dir", str(store), "--require-narrative")
    provider = stage_of(document, "provider")
    check("--require-narrative makes a missing provider fatal even with no"
          " inferred claim",
          code == 1 and provider["status"] == "cannot-run"
          and any(f["code"] == "provider-unavailable"
                  for f in provider["findings"]),
          f"exit {code}: {provider}")


def test_a_provider_is_one_stage_of_the_existing_policy() -> None:
    """An existing runner drives it: no model, no network, no agent loop."""
    with tempfile.TemporaryDirectory() as tmp:
        store = _store_with_inferred_claim(Path(tmp) / "evidence")
        answering = Path(tmp) / "answers.sh"
        answering.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        answering.chmod(0o755)
        code_ok, document_ok, _out = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--evidence-dir", str(store), "--provider-cmd", str(answering))

        refusing = Path(tmp) / "declines.sh"
        refusing.write_text("#!/bin/sh\necho 'provider declined' >&2\n"
                            "exit 3\n", encoding="utf-8")
        refusing.chmod(0o755)
        code, document, output = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--evidence-dir", str(store), "--provider-cmd", str(refusing))

    answered = stage_of(document_ok, "provider")
    check("a provider that answers runs once, inside its budget of three",
          answered["status"] == "pass" and answered["attempts"] == 1
          and answered["max_attempts"] == 3
          and answered["deterministic"] is False,
          str(answered))

    declined = stage_of(document, "provider")
    check("a provider that refuses is a red stage, not a warning",
          code == 1 and declined["status"] == "fail"
          and any(f["code"] == "provider-refused"
                  for f in declined["findings"]),
          str(declined))
    check("the refusing provider used its full budget and no more",
          declined["attempts"] == 3 == declined["max_attempts"]
          and len(declined["attempt_log"]) == 3,
          str(declined["attempts"]))
    check("a refusing provider stops the publication",
          document["publication"]["action"] == "retain-previous",
          str(document["publication"]))


def test_diagrams_are_rendered_by_the_existing_mermaid_cli() -> None:
    """The portal renders diagrams statically, so a renderer adds one fact.

    It proves the source parses: a diagram nobody can render is a diagram no
    reader can read, and no static build will ever notice. The CLI is an
    existing tool driven as a stage, not a new dependency of the gate - and
    without it the stage reports that it was absent rather than passing.
    """
    with tempfile.TemporaryDirectory() as tmp:
        working = Path(tmp)
        good = working / "mmdc-ok"
        good.write_text('#!/bin/sh\n'
                        'while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift 2;;'
                        ' *) shift;; esac; done\n'
                        'echo "<svg/>" > "$out"\n', encoding="utf-8")
        good.chmod(0o755)
        code, document, output = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--mmdc", str(good))
        broken = working / "mmdc-broken"
        broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        broken.chmod(0o755)
        code_bad, document_bad, _out = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--mmdc", str(broken))
        named_but_absent = working / "no-such-cli"
        _code_missing, document_missing, _out = gate_report(
            "gate", "--target", "release", "--sphinx", "",
            "--mmdc", str(named_but_absent))
        original_which = G._which
        try:
            G._which = lambda name: None
            _code_absent, document_absent, _out = gate_report(
                "gate", "--target", "release", "--sphinx", "")
        finally:
            G._which = original_which

    diagrams = stage_of(document, "diagrams")
    check("the corpus of diagrams renders with the Mermaid CLI",
          diagrams["status"] == "pass" and diagrams["attempts"] == 1
          and diagrams["max_attempts"] == 1,
          str(diagrams["findings"][:2]))

    refused = stage_of(document_bad, "diagrams")
    check("a diagram the renderer cannot parse is a red stage",
          code_bad == 1 and refused["status"] == "fail"
          and any(f["code"] == "mermaid" for f in refused["findings"]),
          str(refused["findings"][:2]))
    check("a diagram failure stops the publication",
          document_bad["publication"]["action"] == "retain-previous",
          str(document_bad["publication"]))

    named = stage_of(document_missing, "diagrams")
    check("a renderer named on the command line that is not there is a failure",
          named["status"] == "fail"
          and any(f["code"] == "mermaid" and "command not found" in f["detail"]
                  for f in named["findings"]),
          str(named["findings"][:1]))

    absent = stage_of(document_absent, "diagrams")
    check("a runner without the Mermaid CLI says so instead of passing",
          absent["status"] == "skipped" and absent["attempts"] == 0
          and "no Mermaid CLI" in absent.get("note", ""),
          str(absent))


def test_linkcheck_is_opt_in_and_never_silent() -> None:
    """The external-link policy of conf.py governs linkcheck; the gate runs it
    only when asked, and says which of the two happened."""
    with tempfile.TemporaryDirectory() as tmp:
        _code, document, _out = gate_report("gate", "--target", "release",
                                            "--sphinx", "")
    links = stage_of(document, "links")
    check("linkcheck is skipped out loud, with a reason, when not requested",
          links["status"] == "skipped" and links["attempts"] == 0
          and bool(links.get("note")),
          str(links))
    check("a browser-shaped stage has the two-attempt budget",
          links["max_attempts"] == 2 and links["deterministic"] is False,
          str(links))


def test_the_gate_ships_no_agent_loop_and_no_new_framework() -> None:
    """The issue forbids a standalone engine, a second framework or a scheduler."""
    tree = GATE.read_text(encoding="utf-8")
    modules = {line.split()[1].split(".")[0]
               for line in tree.splitlines()
               if (line.startswith("import ") or line.startswith("from "))
               and not line.lstrip().startswith("#")}
    check("the gate imports nothing outside the standard library",
          modules <= {"argparse", "hashlib", "json", "os", "re", "subprocess",
                      "sys", "tempfile", "datetime", "pathlib", "importlib",
                      "__future__"},
          str(sorted(modules)))
    check("no agent framework, browser or model SDK is imported",
          not modules & {"openai", "anthropic", "langchain", "autogen",
                         "playwright", "requests", "httpx"},
          str(sorted(modules)))


def test_the_gate_is_wired_into_the_existing_ci() -> None:
    """Existing CI, no job of its own: the docs workflow must call the gate."""
    workflow = ROOT / ".github" / "workflows" / "docs.yml"
    if not workflow.is_file():
        check("the docs workflow exists", False, str(workflow))
        return
    text = workflow.read_text(encoding="utf-8")
    check("the pull request job runs the targeted generator checks",
          "docs_gate.py gate --target pr" in text, "no gate invocation")
    check("the gate report is published for review",
          "docs-gate.json" in text, "no gate artifact")
    check("the gate is handed no credentials",
          "secrets." not in text.split("jobs:", 1)[1], "workflow passes a secret")
    check("the offline structural suite still runs", "test_docs_build.py" in text)


def test_the_shared_identity_module_has_the_rules_it_claims() -> None:
    """The build and the gate must compute one identity, or the check is void."""
    digests = EXT_DIR / "mrmap_digests.py"
    if not digests.is_file():
        check("the shared digest module exists", False, str(digests))
        return
    spec = importlib.util.spec_from_file_location("mrmap_digests", digests)
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    check("the portal extension imports the digest instead of rewriting it",
          "from mrmap_digests import source_digest"
          in (EXT_DIR / "mrmap_docs.py").read_text(encoding="utf-8"))
    check("the gate asks that same module for the candidate identity",
          "mrmap_digests" in GATE.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as first, \
            tempfile.TemporaryDirectory() as second:
        for root in (Path(first), Path(second)):
            (root / "a.rst").write_text("content of a.rst\n", encoding="utf-8")
            (root / "b.rst").write_text("content of b.rst\n", encoding="utf-8")
        forward = shared.source_digest(Path(first))
        other_order = shared.source_digest(Path(second))
    check("the digest is ordered by path, not by directory order",
          forward == other_order, f"{forward[:18]} != {other_order[:18]}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.rst").write_text("content of a.rst\n", encoding="utf-8")
        (root / "b.rst").write_text("content of b.rst\n", encoding="utf-8")
        check("a file outside the documented suffixes is not in the identity",
              shared.source_digest(root) == forward)
        (root / "notes.md").write_text("markdown counts\n", encoding="utf-8")
        check("a markdown page counts towards the identity",
              shared.source_digest(root) != forward)
        (root / "notes.md").unlink()
        (root / "a.py").write_text("code counts too\n", encoding="utf-8")
        check("the documented source code counts towards the identity",
              shared.source_digest(root) != forward)
        (root / "a.py").unlink()
        (root / "b.rst").write_text("content of a.rst\n", encoding="utf-8")
        (root / "a.rst").write_text("content of b.rst\n", encoding="utf-8")
        check("swapping the bytes between two paths changes the identity",
              shared.source_digest(root) != forward)


def test_the_blob_digest_is_what_git_computes() -> None:
    """Evidence stays checkable with git alone only if the id is git's own."""
    expected = subprocess.run(["git", "hash-object", str(SCHEMAS)],
                              capture_output=True, text=True, cwd=ROOT)
    if expected.returncode != 0:
        check("the blob digest equals git's (skipped: git unavailable)", True)
        return
    check("the evidence blob digest is git's own blob id",
          G.blob_digest(SCHEMAS) == "sha1:" + expected.stdout.strip(),
          f"{G.blob_digest(SCHEMAS)} vs {expected.stdout.strip()}")


def main() -> int:
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            print(f"\n{name[5:]}")
            function()
    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(failed)} failed of {len(RESULTS)} checks" if failed
          else f"\nall {len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
