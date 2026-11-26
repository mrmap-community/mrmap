#!/usr/bin/env python3
"""The contract the documentation pipeline and its tests share (#1598, epic #1589).

Why a contract module at all: the pipeline's trust model - ADR-0001 sections 4, 5,
8, 9 and 11 - is entirely carried by the shape of the artifacts. A run is only
auditable because an evidence record says which file span and which executed
command stands behind a sentence, a page is only regenerable because a sidecar
names the digests it was computed from, and a model is only usable because its
request and response are checked before any of its text is rendered. So the
schemas, the validator and the digests are the product, and every other module
in this pipeline is a client of them.

Four things live here, all of them dependency-free:

* **The schemas** of the seven artifacts the pipeline writes or consumes, written
  in the JSON Schema subset the ``jsonschema`` library accepts and checked with
  or without it installed. ``pip install jsonschema`` makes the check independent
  of this file's implementation; without it the same documents are checked by the
  validator below, whose behaviour ``scripts/test_docs_pipeline.py`` pins against
  the schema text (a schema this validator reads wrongly fails a check, not a
  silent pass).
* **The digests.** Content-addressed, always ``sha256:<hex>``, with git blob
  SHAs computed in pure Python so an extraction run needs no subprocess and no
  repository - a blob SHA says "verified against exactly this content", which is
  what ADR-0001 section 4 requires of a source reference.
* **The builders** of evidence records, claims, invalidation sidecars and the run
  report. They validate what they return, so an unbuildable record is a bug at
  its source rather than a corrupt artifact discovered by the publication gate.
* **The budgets** of ADR-0001 section 8, as one dict with a named consequence per
  bound. A bound that no module reads is decoration, so each of these is consumed
  where it applies and asserted by the suite.

Run ``python3 scripts/docs_contract.py`` to print the schema register and the
budget table; it doubles as the self-check the suites use to prove the module
imports on a bare runner.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

#: Names the artifacts of one run carry, so a consumer can tell which contract it
#: is reading and refuse another one's output instead of guessing.
EVIDENCE_SCHEMA = "mrmap.docs.evidence.v1"
MANIFEST_SCHEMA = "mrmap.docs.manifest.v1"
FACTS_SCHEMA = "mrmap.docs.facts.v1"
PROVENANCE_SCHEMA = "mrmap.docs.provenance.v1"
REPORT_SCHEMA = "mrmap.docs.report.v1"
REQUEST_SCHEMA = "mrmap.docs.request.v1"
RESPONSE_SCHEMA = "mrmap.docs.response.v1"
PROVIDER_SCHEMA = "mrmap.docs.provider.v1"

#: Written into every artifact and into the model's own prompt, so a page always
#: says which code produced it (ADR-0001 section 4, ``produced_by.generator``).
TOOL_VERSION = "mrmap-docs/1.0.0"

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2
#: "could not run" is never a pass, so it is a distinct code, as in the release
#: tools: a missing binary or a blocked path must not read as a green run.

LOCALES = ("en", "de")
EVIDENCE_KINDS = ("extracted", "executed", "inferred", "human")
AUDIENCES = ("cataloguer", "administrator", "integrator", "developer", "operator")
STAGES = ("discover", "extract", "evidence", "generate", "render", "validate",
          "publish")
REFUSAL_REASONS = ("policy", "out_of_scope", "insufficient_evidence",
                   "unsupported_locale")
GATE_STATUSES = ("pass", "fail", "skipped")

#: The surfaces ADR-0001 section 2 names, each with the discovered denominator it
#: is measured against. This tuple is the contract the extractor implements and
#: the coverage gate reads; adding a surface means changing this line, the
#: extractor and the gate together, which is the point.
SURFACES = (
    "resources",          # every `name:` of frontend/src/components/Resource/Definition.tsx
    "models",             # every models.Model subclass
    "relations",          # every ForeignKey / OneToOneField / ManyToManyField
    "settings",           # every module-level uppercase assignment in MrMap/settings.py
    "commands",           # every */management/commands/*.py
    "tasks",              # every task decorator in the app's tasks/
    "services",           # every service key of each committed compose file
    "features",           # every Behave feature file
)

SHA_SCHEMA = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
#: A git blob SHA is SHA-1 by definition, so it carries its own prefix: an artifact
#: that said "sha256:" over a 40-hex git hash would be unreadable to anything that
#: tries to verify it against ``git hash-object``.
BLOB_SCHEMA = {"type": "string", "pattern": "^sha1:[0-9a-f]{40}$"}
#: A path inside the tree under documentation. Absolute paths and ``..`` segments
#: are refused by the schema, not only by the guard that reads them: an artifact
#: that could name ``/etc/passwd`` is rejected before anything opens it. Backslashes
#: are excluded too, so a sidecar written on Linux cannot mean ``..`` on Windows by
#: spelling it ``..\..``.
REL_PATH_SCHEMA = {
    "type": "string", "minLength": 1, "maxLength": 400,
    "pattern": r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))[A-Za-z0-9_.+:\-/ ]+$",
}
NAME_SCHEMA = {"type": "string", "minLength": 1, "maxLength": 300,
               "pattern": r"^[A-Za-z0-9_.:/\-\+]+$"}
KIND_SCHEMA = {"type": "string", "pattern": r"^[a-z][a-z0-9_]*$"}
ENGINE_SCHEMA = {"type": "string", "pattern": r"^[a-z][a-z0-9_-]*$"}
LOCALE_SCHEMA = {"enum": list(LOCALES)}
#: A model reference is a label, never a URL and never a credential. The prefix is
#: required so a provider can be identified across vendors without the artifact
#: naming an endpoint or an account.
MODEL_REF_RE = re.compile(r"^mrmap-docs-model/[A-Za-z0-9][A-Za-z0-9._\-]{0,120}$")
MODEL_REF_SCHEMA = {"type": "string", "pattern": MODEL_REF_RE.pattern}
PROVIDER_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

SOURCE_REF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["path", "span", "blob"],
    "properties": {
        "path": REL_PATH_SCHEMA,
        "absolutePath": {"const": False},
        "span": {"type": "array", "minItems": 2, "maxItems": 2,
                 "items": {"type": "integer", "minimum": 1}},
        "blob": BLOB_SCHEMA,
    },
}
ASSERTION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["command", "exit_code", "stdout_sha256", "at"],
    "properties": {
        "command": {"type": "string", "minLength": 1, "maxLength": 2000},
        "exit_code": {"type": "integer", "minimum": 0},
        "stdout_sha256": SHA_SCHEMA,
        "stderr_sha256": SHA_SCHEMA,
        "at": {"type": "string", "minLength": 4, "maxLength": 200},
        "duration_s": {"type": "number", "minimum": 0},
    },
}
PRODUCED_BY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["engine", "generator", "model"],
    "properties": {
        "engine": {"enum": ["extractor", "executor", "author", "renderer",
                            "validator", "publisher", "human"]},
        "generator": {"const": TOOL_VERSION},
        "model": {"anyOf": [{"type": "null"}, MODEL_REF_SCHEMA]},
        "provider": {"anyOf": [{"type": "null"},
                               {"type": "string", "pattern": PROVIDER_NAME_RE.pattern}]},
    },
}
USAGE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["prompt_tokens", "completion_tokens"],
    "properties": {
        "prompt_tokens": {"type": "integer", "minimum": 0},
        "completion_tokens": {"type": "integer", "minimum": 0},
    },
}

EVIDENCE_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.evidence.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "id", "claim_id", "kind", "sources", "produced_by",
                 "audience", "locale", "run_id", "generated_at"],
    "properties": {
        "schema": {"const": EVIDENCE_SCHEMA},
        "id": SHA_SCHEMA,
        "claim_id": {"type": "string", "minLength": 1, "maxLength": 300,
                     "pattern": r"^[a-z][a-z0-9_]*:"},
        "kind": {"enum": list(EVIDENCE_KINDS)},
        "audience": {"enum": list(AUDIENCES)},
        "locale": LOCALE_SCHEMA,
        "run_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "generated_at": {"type": "string", "minLength": 4, "maxLength": 200},
        "sources": {"type": "array", "items": SOURCE_REF_SCHEMA},
        "assertion": {"anyOf": [{"type": "null"}, ASSERTION_SCHEMA]},
        "produced_by": PRODUCED_BY_SCHEMA,
        "reviewed": {"anyOf": [{"type": "null"}, {"type": "object"}]},
        "text_sha256": {"anyOf": [{"type": "null"}, SHA_SCHEMA]},
        "unsupported_reason": {"anyOf": [{"type": "null"},
                                         {"type": "string", "minLength": 1,
                                          "maxLength": 2000}]},
    },
    "allOf": [
        # extracted proves a file span, executed proves a command, inferred is the
        # only kind a model wrote. A record that claims otherwise is refused rather
        # than published: this is where "no invented features" becomes mechanical.
        {"if": {"properties": {"kind": {"const": "extracted"}}},
         "then": {"if": {"properties": {"unsupported_reason": {"type": "string"}}},
                  # An unsupported topic is a record of an absence, so it may cite
                  # nothing: that is the whole point of the row.
                  "then": {},
                  "else": {"properties": {
                      "sources": {"minItems": 1},
                      "assertion": {"type": "null"},
                      "produced_by": {"properties": {"model": {"type": "null"}}}}}},
         "else": {}},
        {"if": {"properties": {"kind": {"const": "executed"}}},
         "then": {"required": ["assertion"], "properties": {
             "assertion": {"type": "object"},
             "produced_by": {"properties": {"model": {"type": "null"}}}}}},
        {"if": {"properties": {"kind": {"const": "inferred"}}},
         "then": {"required": ["text_sha256"], "properties": {
             "produced_by": {"properties": {"model": MODEL_REF_SCHEMA}}}}},
    ],
}

FACTS_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.facts.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "surface", "denominator", "facts"],
    "properties": {
        "schema": {"const": FACTS_SCHEMA},
        "surface": {"enum": list(SURFACES)},
        "denominator": {"type": "integer", "minimum": 0},
        "warnings": {"type": "array", "items": {"type": "string", "maxLength": 1000}},
        "facts": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "name", "surface", "sources"],
            "properties": {
                "kind": KIND_SCHEMA,
                "name": NAME_SCHEMA,
                "surface": {"enum": list(SURFACES)},
                "app": {"anyOf": [{"type": "null"},
                                  {"type": "string", "maxLength": 100}]},
                "sources": {"type": "array", "minItems": 1, "items": SOURCE_REF_SCHEMA},
                "fields": {"type": "array", "items": {"type": "string",
                                                      "minLength": 1,
                                                      "maxLength": 300}},
                "value": {"type": ["string", "integer", "number", "boolean", "null"]},
                "default": {"type": ["string", "integer", "number", "boolean", "null"]},
                "help": {"type": ["string", "null"], "maxLength": 4000},
                "extra": {"type": "object"},
            }}},
    },
}

MANIFEST_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.manifest.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "engine", "output", "inputs"],
    "properties": {
        "schema": {"const": MANIFEST_SCHEMA},
        "engine": ENGINE_SCHEMA,
        "output": REL_PATH_SCHEMA,
        "inputs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["kind", "digest"],
            "properties": {"kind": ENGINE_SCHEMA, "digest": SHA_SCHEMA}}},
        "outputs": {"type": "array", "items": REL_PATH_SCHEMA},
        "produced_by": PRODUCED_BY_SCHEMA,
        "run_id": {"type": "string", "maxLength": 200},
    },
}

FACT_REF_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["id", "surface", "kind", "name", "fields", "evidence_id"],
    "properties": {
        "id": {"type": "string", "minLength": 1, "maxLength": 400,
               "pattern": r"^[A-Za-z0-9_.:/\-\+]+$"},
        "surface": {"enum": list(SURFACES)},
        "kind": KIND_SCHEMA,
        "name": NAME_SCHEMA,
        "fields": {"type": "array", "items": {"type": "string", "maxLength": 300}},
        "value": {"type": ["string", "integer", "number", "boolean", "null"]},
        "default": {"type": ["string", "integer", "number", "boolean", "null"]},
        "help": {"type": ["string", "null"], "maxLength": 2000},
        "evidence_id": SHA_SCHEMA,
    },
}
#: The prompt boundary, stated as a schema: the model receives facts, evidence
#: digests and a style profile - and nothing else. No fetched document, no file
#: content, no instruction from a page. ADR-0001 section 11 makes this the limit
#: of the blast radius of a prompt-injected page, so it is enforced on the way out
#: of the pipeline, not only trusted on the way in.
REQUEST_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.request.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "claim_id", "kind", "audience", "locale", "facts",
                 "evidence_refs", "style_profile", "budget"],
    "properties": {
        "schema": {"const": REQUEST_SCHEMA},
        "claim_id": {"type": "string", "minLength": 1, "maxLength": 300},
        "kind": {"enum": ["narrative", "translation"]},
        "audience": {"enum": list(AUDIENCES)},
        "locale": LOCALE_SCHEMA,
        "facts": {"type": "array", "minItems": 1, "items": FACT_REF_SCHEMA},
        "evidence_refs": {"type": "array", "items": SHA_SCHEMA},
        "prior_prose": {"anyOf": [{"type": "null"},
                                  {"type": "string", "maxLength": 20000}]},
        "style_profile": {"type": "object"},
        "budget": {"type": "object"},
    },
}
RESPONSE_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.response.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "text", "cited_fact_ids", "model_id", "usage",
                 "refusal_reason"],
    "properties": {
        "schema": {"const": RESPONSE_SCHEMA},
        "text": {"type": "string", "maxLength": 20000},
        "cited_fact_ids": {"type": "array", "items": {"type": "string",
                                                     "maxLength": 400}},
        "model_id": MODEL_REF_SCHEMA,
        "usage": USAGE_SCHEMA,
        "refusal_reason": {"anyOf": [{"type": "null"},
                                     {"enum": list(REFUSAL_REASONS)}]},
        "provider": {"type": ["string", "null"], "maxLength": 100},
    },
    "allOf": [
        # A refusal is a valid response, but a refusal carries no text: "I cannot
        # evidence this" and a paragraph about the topic must not be mixable.
        {"if": {"properties": {"refusal_reason": {"type": "string"}}},
         "then": {"properties": {"text": {"maxLength": 0},
                                 "cited_fact_ids": {"maxItems": 0}}}},
        # ... and text is only meaningful with at least one citation, since an
        # uncited sentence is dropped by the gate anyway.
        {"if": {"properties": {"refusal_reason": {"type": "null"},
                               "text": {"minLength": 1}}},
         "then": {"properties": {"cited_fact_ids": {"minItems": 1}}}},
    ],
}

PROVIDER_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.provider.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "provider", "model_id", "reports_usage",
                 "supports_refusal", "requires_credentials", "is_networked"],
    "properties": {
        "schema": {"const": PROVIDER_SCHEMA},
        "provider": {"type": "string", "pattern": PROVIDER_NAME_RE.pattern},
        "model_id": MODEL_REF_SCHEMA,
        "reports_usage": {"type": "boolean"},
        "supports_refusal": {"type": "boolean"},
        "requires_credentials": {"type": "boolean"},
        "is_networked": {"type": "boolean"},
        "note": {"type": ["string", "null"], "maxLength": 500},
    },
}

REPORT_SCHEMA_DOC = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "mrmap.docs.report.v1",
    "type": "object", "additionalProperties": False,
    "required": ["schema", "run_id", "generator", "started_at", "finished_at",
                 "documented_commit", "version", "provider", "stages", "summary",
                 "gate", "would_publish"],
    "properties": {
        "schema": {"const": REPORT_SCHEMA},
        "run_id": {"type": "string", "minLength": 1, "maxLength": 200},
        "generator": {"const": TOOL_VERSION},
        "started_at": {"type": "string", "minLength": 4},
        "finished_at": {"type": "string", "minLength": 4},
        "documented_commit": {"type": ["string", "null"],
                              "pattern": r"^[0-9a-f]{40}$"},
        "version": {"type": ["string", "null"], "maxLength": 100},
        "candidate_sha": {"type": ["string", "null"], "pattern": r"^[0-9a-f]{40}$"},
        "release_sha": {"type": ["string", "null"], "pattern": r"^[0-9a-f]{40}$"},
        "docs_manifest": SHA_SCHEMA,
        "provider": {"type": ["string", "null"]},
        "stages": {"type": "array", "minItems": 1, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["name", "status", "started_at", "finished_at"],
            "properties": {
                "name": {"enum": list(STAGES)},
                "status": {"enum": ["ok", "failed", "skipped", "blocked",
                                    "not_run"]},
                "started_at": {"type": "string"}, "finished_at": {"type": "string"},
                "detail": {"type": ["string", "null"], "maxLength": 2000},
                "reason": {"type": ["string", "null"], "maxLength": 500},
                "checks": {"type": "object"}}}},
        "summary": {"type": "object"},
        "gate": {"type": "object", "additionalProperties": False,
                 "required": ["status", "checks"],
                 "properties": {
                     "status": {"enum": list(GATE_STATUSES)},
                     "checks": {"type": "array", "items": {
                         "type": "object", "additionalProperties": False,
                         "required": ["id", "status", "detail"],
                         "properties": {"id": {"type": "string", "maxLength": 200},
                                        "status": {"enum": list(GATE_STATUSES)},
                                        "detail": {"type": "string",
                                                   "maxLength": 2000}}}}}},
        "warnings": {"type": "array", "items": {"type": "string", "maxLength": 2000}},
        "failures": {"type": "array", "items": {"type": "string", "maxLength": 2000}},
        "cost": {"type": "object"},
        "would_publish": {"type": "boolean"},
    },
}

SCHEMAS = {
    "evidence": EVIDENCE_SCHEMA_DOC,
    "facts": FACTS_SCHEMA_DOC,
    "manifest": MANIFEST_SCHEMA_DOC,
    "request": REQUEST_SCHEMA_DOC,
    "response": RESPONSE_SCHEMA_DOC,
    "provider": PROVIDER_SCHEMA_DOC,
    "report": REPORT_SCHEMA_DOC,
}


def load_sibling(name: str):
    """Import ``scripts/<name>.py`` by path, as the release tools import each other.

    The pipeline is host tooling run from a checkout, not an installed package, so
    there is no importable distribution name to rely on. Loading by path keeps the
    modules importable individually - which is what lets a suite exercise the
    provider contract without the CLI.
    """
    module_name = f"mrmap_docs_{name}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------- digests ---
def canonical(obj) -> bytes:
    """The one JSON spelling a digest is ever taken over."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def sha256_obj(obj) -> str:
    return sha256_bytes(canonical(obj))


def blob_sha(data: bytes) -> str:
    """The git blob SHA of ``data``, without git.

    The name is a claim about the content, not about the repository: a source
    reference has to say "verified against exactly these bytes" (ADR-0001 section
    4), and a line number rots the moment anyone edits above it. Computing the
    git blob hash directly means extraction runs with no subprocess, no
    ``.git`` and no writable directory.
    """
    return "sha1:" + hashlib.sha1(
        b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def short(digest: str) -> str:
    """A digest shortened for a log line; full digests belong in artifacts."""
    return digest.split(":", 1)[-1][:12] if ":" in digest else digest[:12]


# -------------------------------------------------------------------- schemas ---
class Issue:
    """One schema finding. ``warning`` never fails a gate; everything else does."""

    __slots__ = ("path", "message", "severity")

    def __init__(self, path: str, message: str, severity: str = "error"):
        self.path = path
        self.message = message
        self.severity = severity

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{self.severity} {self.path}: {self.message}"

    def as_dict(self) -> dict:
        return {"path": self.path, "message": self.message,
                "severity": self.severity}


_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, (list, tuple)),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


class Validator:
    """A validator for the JSON Schema subset the schemas above use.

    Deliberately small: ``type``, ``enum``/``const``, ``required``,
    ``properties``, ``additionalProperties``, ``items``, ``pattern``,
    ``minLength``/``maxLength``, ``minimum``/``maximum``, ``minItems``/``maxItems``,
    ``anyOf``/``oneOf``/``allOf`` and ``if``/``then``/``else``. That is everything
    the seven documents use and nothing else, because an incomplete validator is
    only safe if it is also simple enough to read in one screen. The suite runs the
    same documents through ``jsonschema`` when it is installed, which is what
    keeps this honest rather than self-certifying.
    """

    def __init__(self, schema, path: str = "$"):
        self.schema = schema
        self.path = path
        self.issues: list[Issue] = []

    def check(self, instance) -> list[Issue]:
        self._check(instance, self.schema, self.path)
        return self.issues

    def _err(self, path: str, message: str, severity: str = "error") -> None:
        self.issues.append(Issue(path, message, severity))

    @staticmethod
    def _is_valid(instance, schema) -> bool:
        """Whether ``instance`` satisfies ``schema``, ignoring warnings.

        Unknown properties are a warning at the top level (an artifact may carry
        a field a released validator has not caught up with) but must not decide
        an ``if`` branch, or every conditional rule would silently stop applying.
        """
        sub = Validator(schema)
        return not errors(sub.check(instance))

    def _check(self, value, schema, path: str) -> None:
        if schema is True or schema == {}:
            return
        if schema is False:
            self._err(path, "no value is allowed here")
            return
        declared = schema.get("type")
        if declared is not None:
            types = declared if isinstance(declared, list) else [declared]
            if not any(_TYPES.get(t, lambda v: True)(value) for t in types):
                self._err(path, f"expected {' or '.join(types)}, "
                                f"got {type(value).__name__}")
                return
        if "const" in schema and value != schema["const"]:
            self._err(path, f"expected {schema['const']!r}, got {value!r}")
            return
        if "enum" in schema and value not in schema["enum"]:
            self._err(path, f"{value!r} is not one of {schema['enum']}")
            return
        for combinator in ("allOf",):
            for sub in schema.get(combinator, ()):  # type: ignore[arg-type]
                self._check(value, sub, path)
        for combinator in ("anyOf", "oneOf"):
            if combinator not in schema:
                continue
            matched = sum(1 for sub in schema[combinator]
                          if self._is_valid(value, sub))
            if matched == 0:
                self._err(path, f"matches none of the {combinator} branches")
                return
            if combinator == "oneOf" and matched != 1:
                self._err(path, f"matches {matched} of the oneOf branches")
                return
        if "if" in schema:
            branch = "then" if self._is_valid(value, schema["if"]) else "else"
            if branch in schema:
                self._check(value, schema[branch], path)
        if isinstance(value, dict):
            self._object(value, schema, path)
        elif isinstance(value, (list, tuple)):
            self._array(value, schema, path)
        elif isinstance(value, str):
            self._string(value, schema, path)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                self._err(path, f"{value} is below minimum {schema['minimum']}")
            if "maximum" in schema and value > schema["maximum"]:
                self._err(path, f"{value} is above maximum {schema['maximum']}")

    def _object(self, value: dict, schema: dict, path: str) -> None:
        props = schema.get("properties", {})
        for required in schema.get("required", ()):
            if required not in value:
                self._err(path, f"missing required property {required!r}")
        for key, sub in props.items():
            if key in value:
                self._check(value[key], sub, f"{path}.{key}")
        extra = sorted(set(value) - set(props))
        if not extra:
            return
        additional = schema.get("additionalProperties", None)
        if additional is False:
            for key in extra:
                self._err(f"{path}.{key}", "unknown property")
        elif isinstance(additional, dict):
            for key in extra:
                self._check(value[key], additional, f"{path}.{key}")
        else:
            for key in extra:
                self._err(f"{path}.{key}", "property is not part of the contract",
                          "warning")

    def _array(self, value, schema: dict, path: str) -> None:
        if "minItems" in schema and len(value) < schema["minItems"]:
            self._err(path, f"needs at least {schema['minItems']} item(s), has {len(value)}")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            self._err(path, f"allows at most {schema['maxItems']} item(s), has {len(value)}")
        items = schema.get("items")
        if isinstance(items, dict):
            for index, item in enumerate(value):
                self._check(item, items, f"{path}[{index}]")

    def _string(self, value: str, schema: dict, path: str) -> None:
        if "minLength" in schema and len(value) < schema["minLength"]:
            self._err(path, f"shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            self._err(path, f"longer than maxLength {schema['maxLength']}")
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, value):
            self._err(path, f"{value!r} does not match {pattern!r}")


def validate(name: str, instance) -> list[Issue]:
    """Check ``instance`` against the registered schema ``name``."""
    try:
        schema = SCHEMAS[name]
    except KeyError:
        return [Issue("$", f"no schema registered as {name!r}")]
    return Validator(schema).check(instance)


def validate_with_library(name: str, instance, jsonschema_module=None) -> list[Issue]:
    """Check with the ``jsonschema`` library, when it is installed.

    Used by the suite as the second opinion, and by a run that wants the standard
    library's own judgement rather than this file's. Returns ``None``-free: an
    absent library is reported as an issue with severity ``warning`` so a caller
    can fall back instead of pretending a check ran.
    """
    module = jsonschema_module
    if module is None:
        try:
            import jsonschema as module  # type: ignore[no-redef]
        except Exception:
            return [Issue("$", "jsonschema is not installed; the built-in "
                               "validator is the authority for this run", "warning")]
    errors = list(module.Draft202012Validator.iter_errors(
        module.Draft202012Validator(SCHEMAS[name]), instance))
    return [Issue("/".join(str(part) for part in error.absolute_path) or "$",
                  error.message) for error in errors]


def errors(issues: list[Issue]) -> list[Issue]:
    return [issue for issue in issues if issue.severity != "warning"]


def issues_text(issues: list[Issue]) -> str:
    return "; ".join(f"{issue.path}: {issue.message}" for issue in issues) or "valid"


class ContractError(ValueError):
    """A record the contract refuses. Raised at the source, never published."""


def require_valid(name: str, instance) -> None:
    found = errors(validate(name, instance))
    if found:
        raise ContractError(f"{name} is not valid: {issues_text(found)}")


# -------------------------------------------------------------------- builders ---
def source_ref(path: str, span: tuple[int, int], data: bytes) -> dict:
    """One source reference: the path, the inclusive 1-based line span, the blob.

    The span is inclusive - ``[41, 96]`` is lines 41 to 96 - which is how the ADR
    records its own example and how a reader quotes a range. ``data`` is the file
    as it stood when the fact was read, so the digest says "verified against
    exactly these bytes", the only assertion about a source a later reader can
    still check.
    """
    start, end = int(span[0]), int(span[1])
    if end < start:
        start, end = end, start
    return {"path": str(path), "span": [start, end], "blob": blob_sha(data)}


def produced_by(engine: str, model: str | None = None,
                provider: str | None = None) -> dict:
    return {"engine": engine, "generator": TOOL_VERSION, "model": model,
            "provider": provider}


def evidence_record(*, claim_id: str, kind: str, audience: str, locale: str,
                    run_id: str, generated_at: str, sources=(), assertion=None,
                    produced_by_: dict | None = None, reviewed=None,
                    text_sha256=None, unsupported_reason=None) -> dict:
    """Build and validate one evidence record.

    The id is the digest of the record without it, which makes the store
    content-addressed: the same claim, the same facts and the same run cannot
    produce two ids, and a reader can recompute the id from the file to be sure
    nothing was edited after the run.
    """
    record = {
        "schema": EVIDENCE_SCHEMA,
        "id": "sha256:" + "0" * 64,
        "claim_id": claim_id,
        "kind": kind,
        "audience": audience,
        "locale": locale,
        "run_id": run_id,
        "generated_at": generated_at,
        "sources": [dict(ref) for ref in sources],
        "assertion": assertion,
        "produced_by": produced_by_ or produced_by("extractor"),
        "reviewed": reviewed,
        "text_sha256": text_sha256,
        "unsupported_reason": unsupported_reason,
    }
    record["id"] = sha256_obj({k: v for k, v in record.items() if k != "id"})
    require_valid("evidence", record)
    return record


def fact_ref(*, surface: str, kind: str, name: str, fields=(), evidence_id: str,
             value=None, default=None, help_text=None) -> dict:
    ref = {"id": f"{surface}:{kind}:{name}", "surface": surface, "kind": kind,
           "name": name, "fields": list(fields), "evidence_id": evidence_id}
    if value is not None:
        ref["value"] = value
    if default is not None:
        ref["default"] = default
    if help_text is not None:
        ref["help"] = help_text
    return ref


def facts_document(surface: str, facts, warnings=()) -> dict:
    document = {"schema": FACTS_SCHEMA, "surface": surface,
                "denominator": len(facts), "facts": list(facts),
                "warnings": list(warnings)}
    require_valid("facts", document)
    return document


def manifest_record(*, engine: str, output: str, inputs, outputs=(),
                    produced_by_: dict | None = None, run_id: str = "") -> dict:
    record = {"schema": MANIFEST_SCHEMA, "engine": engine, "output": str(output),
              "inputs": [dict(item) for item in inputs],
              "outputs": list(outputs),
              "produced_by": produced_by_ or produced_by(engine),
              "run_id": run_id}
    require_valid("manifest", record)
    return record


def provider_info(*, provider: str, model_id: str, reports_usage: bool,
                  supports_refusal: bool, requires_credentials: bool,
                  is_networked: bool, note: str | None = None) -> dict:
    info = {"schema": PROVIDER_SCHEMA, "provider": provider, "model_id": model_id,
            "reports_usage": bool(reports_usage),
            "supports_refusal": bool(supports_refusal),
            "requires_credentials": bool(requires_credentials),
            "is_networked": bool(is_networked), "note": note}
    require_valid("provider", info)
    return info


# --------------------------------------------------------------------- budgets ---
#: ADR-0001 section 8, as data. Each entry carries the consequence that happens on
#: breach, because a bound without a named consequence is a suggestion.
BUDGETS = {
    "wall_clock_extraction_s": {"value": 1800, "on_breach":
        "the run fails closed and the prior publication stands"},
    "wall_clock_narrative_s": {"value": 3600, "on_breach":
        "the run fails closed and the prior publication stands"},
    "model_tokens_total": {"value": 400_000, "on_breach":
        "generation stops at the boundary and the partial output is discarded"},
    "model_requests_per_claim": {"value": 3, "on_breach":
        "the claim fails, its inferred text is dropped, extracted text survives"},
    "scenario_wall_clock_s": {"value": 90, "on_breach":
        "the scenario fails and its workflow is reported uncovered"},
    "tool_wall_clock_s": {"value": 120, "on_breach":
        "the tool call fails and its fact is reported unsupported"},
    "retries_extractor": {"value": 0, "on_breach":
        "not applicable: a deterministic stage that fails is a bug, and retrying "
        "it hides it"},
    "retries_render": {"value": 0, "on_breach": "not applicable, as above"},
    "retries_model": {"value": 2, "on_breach":
        "the claim fails; every retry is logged with its reason"},
    "retries_browser": {"value": 1, "on_breach": "the scenario fails"},
    "concurrency_extraction": {"value": 4, "on_breach": "not tunable per run"},
    "concurrency_render": {"value": 1, "on_breach": "not tunable per run"},
    "concurrency_browser": {"value": 1, "on_breach": "not tunable per run"},
    "retry_backoff_s": {"value": 0.25, "on_breach":
        "the scheduler sleeps longer between attempts of a failing claim"},
}

#: The only commands the pipeline may execute, each with the exact arguments it
#: may receive and what it is for. Anything else - a different binary, an
#: unexpected argument, a path outside the tree - is refused before a process is
#: spawned. ``docs`` is the portal build itself, so a stage can prove it ran
#: without any stage owning a shell.
TOOL_ALLOWLIST = {
    "sphinx": {
        "argv": ["{python}", "-m", "sphinx", "-b", "html", "-E", "-W",
                 "--keep-going", "-d", "{work}/doctrees", "{source}", "{out}"],
        "purpose": "build the portal strictly, offline",
    },
    "git-revision": {
        "argv": ["git", "rev-parse", "HEAD"],
        "purpose": "name the revision under documentation",
    },
    # The pipeline extracts facts in-process; this entry exists so the *evidence*
    # stage can re-run one surface in a child and record its exit code and output
    # digest, which is what makes an `executed` record reproducible from the
    # artifact alone. The script path is baked into the allowlist rather than
    # passed by the caller: an entry that accepted "any script" would be an
    # arbitrary-execution hole with a nicer name.
    "docs-extract": {
        "argv": ["{python}", str(SCRIPTS / "docs_extract.py"), "--surface",
                 "{surface}", "--json"],
        "purpose": "re-extract one surface and record its exit code and output "
                   "digest as executed evidence",
    },
}


def budget(name: str, overrides: dict | None = None):
    """Read one bound, with per-run overrides applied only when they tighten it.

    A caller may lower a bound, never raise it: the budgets are the contract that
    makes an autonomous run safe to leave running, and "the model was slow, so we
    raised the token cap" is exactly how an unattended job becomes an unbounded
    one.
    """
    try:
        entry = BUDGETS[name]
    except KeyError:
        raise KeyError(f"unknown budget {name!r}; the contract knows "
                       f"{', '.join(sorted(BUDGETS))}") from None
    value = entry["value"]
    override = (overrides or {}).get(name)
    if override is not None:
        value = min(value, override)
    return value


def main() -> int:
    problems = []
    for name, schema in SCHEMAS.items():
        found = errors(validate(name, {}))
        # An empty object must fail every document: each has required properties.
        if not found:
            problems.append(f"{name}: the schema accepts an empty object")
    print(f"contract {TOOL_VERSION}: {len(SCHEMAS)} schemas, "
          f"{len(BUDGETS)} budgets, {len(TOOL_ALLOWLIST)} allowlisted tools")
    if problems:
        print("\n".join(f"FAIL  {problem}" for problem in problems))
        return 1
    print("all schemas refuse an empty document")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
