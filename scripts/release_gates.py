#!/usr/bin/env python3
"""release_gates: the compatibility and upgrade gates a release candidate must pass.

Host-side tool carried by this repository; run it as `python3
scripts/release_gates.py <subcommand>` from the repository root (issue #1583,
epic #1577). Standard library only, plus the local `git` CLI where a gate reads
history: no container, no network, no database, no `gh`. Exit 0 when the gate
passes, 1 when it decides against the candidate, 2 when the gate could not run
(a missing file, an unresolvable ref) - "could not run" is never reported as a
pass.

Why these gates exist as host checks
-----------------------------------
#1578 measured that the repository has ZERO tags and ZERO releases: there is no
previously supported stable release to compare a candidate against, and Q1/Q2/
Q5/Q6 of its decision register are Pending. A compatibility gate that demanded
a released baseline would therefore be dead code today - and dead code is
precisely what lets the first real release skip it. So every gate here runs
TODAY in one of two modes and the mode itself is reviewed content:

  released       a supported stable release exists; the contract baseline
                 manifest names its version, its source tag and a committed
                 snapshot of its OpenAPI document, and `api` diffs against it.
  pre-baseline   no stable release exists (measured: 0 tags); there is nothing
                 to diff a public contract against. What is NOT skipped is the
                 evidence a breaking change still owes while major is 0: the
                 reviewed classification of #1580, a "**Breaking:**" line in
                 the changelog, migration notes, and the ledger entries below.
                 The manifest must carry `reviewed_0_x: true` and say which
                 pending questions stand in for a policy - if the manifest
                 ever claims pre-baseline without that declaration, the gate
                 refuses (exit 2), because then nobody decided the fallback.

The diff itself reuses nothing invented here: the version bump policy reads the
same classified history `scripts/pr_classify` produces (#1580 - one classifier,
one answer), the migration-graph check shells out to
`scripts/migration_graph_smoke.py` (#1157 - one graph reader), and the version
identity comes from `scripts/canonical_version.py` (#1579). Duplicate
suites were the issue's anti-goal.

Subcommands
-----------
api       Diff the candidate OpenAPI/JSON:API document against the committed
          contract baseline. Breaking findings are: removed operation, changed
          operationId, removed parameter, newly required parameter or request
          body, removed response status code, removed property, newly required
          property, changed property type, narrowed enum. Every breaking
          finding must be covered by an entry of the reviewed exceptions
          ledger naming the issue that reviewed it (`refs`), and an exception
          that matches no finding is itself a failure (reviewed exceptions do
          not accumulate). Additive changes are reported, never failed. A
          candidate whose `info.version` differs from the canonical version of
          the checkout is refused: that means a stale file is being gated.
          Categories a schema diff cannot see at all (authentication semantics,
          the meaning of a kept status code, error bodies, pagination,
          JSON:API side effects, the proxied OGC surface) are listed in every
          report as behavioral blindspots - the release notes, not the diff,
          carry their acknowledgment.

version   Decide what the candidate's version must be from the classified
          change classes of the range (`pr_classify history --json`): breaking
          requires a MAJOR bump, or a MINOR bump while major is 0 and the
          baseline manifest carries the reviewed `breaking_below_1_0: "minor"`
          reading of Q2; a feature requires MINOR; a fix requires PATCH. Versions are
           compared by SemVer precedence, not by splitting on dots: build
           metadata never moves a version ahead (section 10), and a prerelease
           sorts BELOW the release it precedes (section 11), so an rc candidate
           must carry the version it will become (`0.2.0-rc.1`, the convention
           of `image_release.py`) and not the baseline's own - while the
           baseline itself must be a STABLE release, because the rc of 0.2.0
           already carries the movement that 0.2.0 releases. A version the
           regex cannot read is a cannot-run (exit 2), never a traceback
           masquerading as a decision (exit 1). While
          no baseline version exists the required bump is reported as advisory
          (nothing to bump FROM - Q1/Q4 pending), but a range containing
          breaking entries still requires a "**Breaking:**" line in the
          UNRELEASED changelog section. Independently of the mode: every NEW
          migration of the range and every NEW required deployment setting
          (a `${VAR:?}` interpolation of the Compose files, an
          `os.environ[...]` subscript of the settings - both fail a deployment
          that does not set them) must be named under the "### Migration
          notes" subsection of the UNRELEASED section. Notes for what a change
          demands of an operator are not optional documentation; they are what
          the issue calls "migration notes".

upgrade   The migration and upgrade surface, statically: (1) the graph gate of
          `migration_graph_smoke.py` runs unchanged - one leaf per app; (2) the
          staged #1180 constraints hold: the named intermediate-release nodes
          (notify/0001..0006) still exist on disk because the graph parents on
          their names even though their bodies are empty, and nothing of
          backend/ depends on a retired app again (`django_celery_results`);
          (3) NO FAKE MIGRATIONS: a migration ADDED by the range must carry
          operations - an empty `operations` list or a RunPython whose both
          sides are a noop is a node that lies about changing the schema -
          unless the file itself carries the reviewed marker
          `# release-gates: empty-operations -- refs #<issue>` (the #1180
          nodes predate this gate and are not in any checked range; the marker
          is only for additions, so a human had to say yes); (4) DESTRUCTIVE
          CHANGES NEED APPROVAL: RemoveField, DeleteModel, RenameField,
          RemoveIndex and a RunSQL containing DROP in a new migration must
          each appear in the exceptions ledger with `refs` - the PR that adds
          them is where a human reviews that entry. The gate also prints the
          oldest supported upgrade baseline of #1180 answer 3 (a deployment
          whose `django_migrations` records `notify.0006_...`) as the directive
          the CI upgrade run must start from. A fresh-install and an
          upgrade-from-baseline run against PostgreSQL stay with the existing
          QA containers - this gate decides what such a run may assume, it
          does not duplicate the suites.

promote   Aggregate the evidence a production promotion needs and attest the
          candidate: it takes the evidence file a promotion workflow writes
          (tests, Sonar, dependency/vulnerability review, artifacts) plus the
          JSON reports of the three gates above, and refuses to produce the
          attestation unless every required check passed FOR THIS EXACT SHA,
          both first-party images carry a `sha256:` digest, and all three
          gates are green. The output is the attestation JSON binding
          `(sha, version)` to that evidence - the callable contract #1584
          promotes on and #1585/#1586 consume. It writes no tag, publishes
          nothing, grants nothing: promotion stays a human act, and an
          attestation is a statement of evidence, not an approval.

Tested on purpose, both ways
----------------------------
`scripts/test_release_gates.py` (offline, in `scripts/check_repo_tooling.sh`)
drives every gate through its intentional failure AND its pass: an unreviewed
removed endpoint, a stale exception, a fake migration, an unapproved
RemoveField, a missing migration note, a wrong bump, evidence for the wrong
SHA - and the same inputs once reviewed/digested/correct. A gate nobody woke
up red is a decoration.
"""

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK, EXIT_FAIL, EXIT_CANNOT = 0, 1, 2

BASELINE_DEFAULT = "scripts/release_contract_baseline.json"
EXCEPTIONS_DEFAULT = "scripts/release_contract_exceptions.json"
UPGRADE_BASELINE_DEFAULT = "scripts/release_upgrade_baseline.json"

# What a schema diff cannot see. Named once, printed in every api report: the
# release notes carry their acknowledgment, the diff must not pretend.
BEHAVIORAL_BLINDSPOTS = [
    "authentication and permission semantics behind an unchanged operation",
    "the meaning of a status code that stayed in the document",
    "error and exception report body shapes",
    "pagination, filtering and ordering behaviour of a kept parameter",
    "JSON:API side effects (compound documents, sparse fieldsets, includes)",
    "the proxied OGC surface (/mrmap-proxy) which the document does not describe",
]

BREAKING_KINDS = {
    "removed-operation", "operation-id-change", "removed-parameter",
    "new-required-parameter", "new-required-request-body",
    "removed-response-status", "removed-property", "new-required-property",
    "property-type-change", "enum-narrowed",
}
DESTRUCTIVE_OPS = {"RemoveField", "DeleteModel", "RenameField", "RemoveIndex"}
MARKER_RE = re.compile(
    r"release-gates:\s*empty-operations\s*--\s*refs\s+(\S+)")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")
REQUIRED_COMPOSE_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]+):?[?]")
REQUIRED_SETTINGS_RE = re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]+)["']\s*\]""")


class GateCannotRun(Exception):
    """The gate could not answer; reported as exit 2, never as a pass."""


def semver_parse(version, what="version"):
    """(major, minor, patch, prerelease-identifiers) of a strict SemVer.

    Read from SEMVER_RE's own groups, never by splitting on '.': this project
    allows the prerelease and build-metadata suffixes on purpose (#1579 -
    `0.2.0-rc.1`, `0.2.0+9f8e7d6`, and `scripts/image_release.py` tags rc
    candidates that way), so a split yields `int("0-rc")` and raises. A
    traceback would exit 1, which this tool reserves for a decision the gate
    made AGAINST a candidate; a version the gate cannot read is not a
    decision, it is a cannot-run and exits 2.
    """
    match = SEMVER_RE.match(version or "")
    if not match:
        raise GateCannotRun(
            f"{what} {version!r} is not strict SemVer - readable is "
            "major.minor.patch with an optional -prerelease and an optional "
            "+buildmetadata")
    major, minor, patch, prerelease, _meta = match.groups()
    return (int(major), int(minor), int(patch),
            tuple(prerelease.split(".")) if prerelease else ())


def semver_precedence(version, what="version"):
    """The SemVer precedence key of a version (spec sections 10 and 11).

    Build metadata is IGNORED for precedence (section 10): `0.1.0+9f8e7d6` is
    the same release as `0.1.0` and is therefore not a bump. A version WITH a
    prerelease sorts BELOW the same version without one (section 11), which is
    what makes `1.2.3-rc.1` and `1.2.3` two versions instead of one - the
    mistake a numeric-triple comparison makes. Prerelease identifiers compare
    dot by dot: numerically when numeric, numeric always below alphanumeric,
    and a larger set of identifiers wins when all preceding ones are equal.
    """
    major, minor, patch, prerelease = semver_parse(version, what)

    def identifier(ident):
        if ident.isdigit():
            return (0, int(ident), "")
        return (1, 0, ident)

    return ((major, minor, patch), 0 if prerelease else 1,
            tuple(identifier(i) for i in prerelease))


def semver_cmp(older, newer, what_older="version", what_newer="version"):
    """<0, 0 or >0: the precedence of the first version against the second."""
    first = semver_precedence(older, what_older)
    second = semver_precedence(newer, what_newer)
    return (first > second) - (first < second)


# --------------------------------------------------------------------------
# json plumbing


def load_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise GateCannotRun(f"{what} not found: {path}")
    except (OSError, json.JSONDecodeError) as error:
        raise GateCannotRun(f"{what} cannot be read ({path}): {error}")


def run_tool(argv, cwd=None):
    """Run a repository tool as a subprocess and return (returncode, stdout,
    stderr). The tools are siblings of this one, always called by path with the
    running interpreter - never by name on a PATH that may not have them."""
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


# --------------------------------------------------------------------------
# baseline manifest and reviewed exceptions ledger


def read_baseline(root, path, document_required=True):
    """The manifest, validated. `document_required` is False for the version
    gate, which reads the manifest's version and policy but diffs no document
    - only the api gate owes the snapshot."""
    manifest = load_json(root / path, "contract baseline manifest")
    mode = manifest.get("mode")
    if mode not in ("pre-baseline", "released"):
        raise GateCannotRun(
            f"{path}: mode must be 'pre-baseline' or 'released', not {mode!r}")
    policy = manifest.get("policy") or {}
    version = manifest.get("version")
    document = manifest.get("document")
    if mode == "pre-baseline":
        # The fallback is only legitimate while somebody declared it: a
        # pre-baseline mode without the 0.x declaration is an undeclared
        # anything-goes window, which is what this gate exists to prevent.
        if not policy.get("reviewed_0_x"):
            raise GateCannotRun(
                f"{path}: mode 'pre-baseline' requires policy.reviewed_0_x: "
                "true and a policy.declared_on list naming where the 0.x "
                "reading was asked (the pending questions of #1578)")
        if not policy.get("declared_on"):
            raise GateCannotRun(
                f"{path}: policy.declared_on must name the questions/issues "
                "that carry the reviewed 0.x reading")
        if version is not None or document is not None:
            raise GateCannotRun(
                f"{path}: pre-baseline must leave version and document null "
                "(there is no released baseline to name)")
    else:
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            raise GateCannotRun(
                f"{path}: released mode needs a strict SemVer 'version'")
        if semver_parse(version, f"{path} 'version'")[3]:
            # The baseline is the previous SUPPORTED stable release, and a
            # prerelease is not one: scripts/image_release.py refuses the
            # stable aliases for a prerelease precisely because an rc promises
            # a release instead of being one. Letting an rc in here would also
            # make the bump question undecidable, since the rc of 0.2.0 already
            # carries the minor movement that 0.2.0 releases.
            raise GateCannotRun(
                f"{path}: the contract baseline must be a stable release, not "
                f"the prerelease {version} (an rc announces a release, it is "
                "not a supported one - image_release.py refuses the stable "
                "aliases for a prerelease)")
        if document_required and not document:
            raise GateCannotRun(
                f"{path}: released mode needs the committed 'document' "
                "snapshot to diff against")
    return manifest


def read_exceptions(root, path):
    data = load_json(root / path, "exceptions ledger")
    entries = data.get("exceptions")
    if not isinstance(entries, list):
        raise GateCannotRun(f"{path}: 'exceptions' must be a list")
    seen = set()
    for entry in entries:
        for field in ("id", "kind", "target", "refs"):
            if field == "refs":
                if not isinstance(entry.get("refs"), list) or not entry["refs"]:
                    raise GateCannotRun(
                        f"{path}: exception {entry.get('id')}! must name "
                        "refs - a reviewed exception without the issue that "
                        "reviewed it is prose, not approval")
            elif not entry.get(field):
                raise GateCannotRun(
                    f"{path}: every exception needs {field}")
        if entry["id"] in seen:
            raise GateCannotRun(
                f"{path}: duplicate exception id {entry['id']}")
        seen.add(entry["id"])
    return entries


def match_exception(kind, target, exceptions):
    """The covering exception for a finding, or None. Target matching is exact
    or by an explicit trailing-* prefix written in the ledger - not a regex, so
    a ledger entry cannot quietly widen itself into other findings."""
    for entry in exceptions:
        if entry["kind"] != kind:
            continue
        want = entry["target"]
        if want.endswith("*") and target.startswith(want[:-1]):
            return entry
        if want == target:
            return entry
    return None


# --------------------------------------------------------------------------
# the api gate: OpenAPI/JSON:API contract diff


def deref(node, doc, seen):
    """Follow a $ref into components. A cycle (an operation whose schema
    contains itself) is answered as opaque, not by infinite recursion."""
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    if ref in seen:
        return {"opaque": True}
    target = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(target, dict) or part not in target:
            return {"opaque": True}
        target = target[part]
    return deref(target, doc, seen | {ref})


def schema_surface(schema, doc, seen, depth=0):
    """The property surface of one schema as {pointer: (type, enum, required)}:
    required properties are marked, recursion stops at depth 6 or at an
    opaque/cyclic node. This is the surface the diff compares."""
    props = {}

    def walk(node, prefix, seen, depth):
        node = deref(node, doc, seen)
        if not isinstance(node, dict) or node.get("opaque"):
            return
        for name, sub in (node.get("properties") or {}).items():
            pointer = f"{prefix}.{name}" if prefix else name
            sub_resolved = deref(sub, doc, seen)
            ptype = sub_resolved.get("type") if isinstance(sub_resolved, dict) else None
            if ptype is None and isinstance(sub_resolved, dict) and sub_resolved.get("oneOf"):
                ptype = "oneOf"
            enum = sub_resolved.get("enum") if isinstance(sub_resolved, dict) else None
            props[pointer] = (ptype or "?", tuple(enum) if enum else None,
                              name in (node.get("required") or []))
            if depth < 6:
                walk(sub, pointer, seen, depth + 1)
    walk(schema, "", seen, depth)
    return props


def collect_operations(doc):
    """Every (path, method) of the document as its operation contract:
    parameters, request surface, and the property surface of each 2xx answer."""
    if not isinstance(doc, dict) or "paths" not in doc:
        raise GateCannotRun("the document is not an OpenAPI document "
                            "(no 'paths' member)")
    operations = {}
    for path, item in (doc.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in ("get", "put", "post", "patch", "delete", "head",
                       "options", "trace"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            params = {}
            for param in op.get("parameters") or []:
                param = deref(param, doc, set())
                if isinstance(param, dict) and param.get("name"):
                    params[(param.get("in", "?"), param["name"])] = \
                        bool(param.get("required"))
            body = None
            body_required = False
            content = ((op.get("requestBody") or {}).get("content") or {})
            for media in ("application/vnd.api+json", "application/json"):
                if media in content:
                    body = content[media].get("schema")
                    break
            if op.get("requestBody") is not None:
                body_required = bool((op["requestBody"] or {}).get("required"))
            responses = {}
            for status, response in (op.get("responses") or {}).items():
                if not status.startswith("2"):
                    continue
                response = deref(response, doc, set())
                content = (response.get("content") or {}) if isinstance(response, dict) else {}
                schema = None
                for media in ("application/vnd.api+json", "application/json"):
                    if media in content:
                        schema = content[media].get("schema")
                        break
                responses[status] = schema_surface(schema, doc, set()) \
                    if schema is not None else None
            operations[(path, method)] = {
                "operationId": op.get("operationId"),
                "params": params,
                "body_required": body_required,
                "body": (schema_surface(body, doc, set())
                         if body is not None else None),
                "responses": responses,
            }
    return operations


def _diff_surfaces(findings, op_id, label, base_surface, cand_surface):
    if base_surface is None or cand_surface is None:
        return
    for pointer, (ptype, enum, was_required) in sorted(base_surface.items()):
        if pointer not in cand_surface:
            findings.append({"kind": "removed-property", "breaking": True,
                             "target": f"{op_id} [{label}]: property '{pointer}'",
                             "detail": f"type was {ptype}"})
            continue
        ctype, cenum, is_required = cand_surface[pointer]
        if not was_required and is_required:
            findings.append({"kind": "new-required-property", "breaking": True,
                             "target": f"{op_id} [{label}]: property '{pointer}'",
                             "detail": "an optional property became required"})
        if ptype != ctype and "?" not in (ptype, ctype) and ctype != "?":
            findings.append({"kind": "property-type-change", "breaking": True,
                             "target": f"{op_id} [{label}]: property '{pointer}'",
                             "detail": f"type {ptype} -> {ctype}"})
        if enum and cenum is not None and not set(enum).issubset(set(cenum)):
            findings.append({"kind": "enum-narrowed", "breaking": True,
                             "target": f"{op_id} [{label}]: property '{pointer}'",
                             "detail": f"enum {sorted(set(enum) - set(cenum))} no longer answers"})


def cmd_api(args):
    root = Path(args.root)
    baseline = read_baseline(root, args.baseline)
    exceptions = read_exceptions(root, args.exceptions)
    candidate = load_json(args.candidate, "candidate OpenAPI document")

    # A candidate that does not name the version of the checkout it was
    # generated from is a stale file being gated - refuse it in every mode.
    info_version = (candidate.get("info") or {}).get("version")
    if not args.skip_version_check:
        version_path = root / "VERSION"
        if version_path.exists():
            canonical = version_path.read_text(encoding="utf-8").strip()
            if info_version and info_version != canonical:
                print(f"api: FAIL - the candidate document says info.version "
                      f"{info_version!r} but this checkout is {canonical!r}: "
                      "regenerate the candidate (a stale file cannot attest a "
                      "candidate)", file=sys.stderr)
                return EXIT_FAIL

    breaking, additive = [], 0
    if baseline["mode"] == "released":
        baseline_doc = load_json(root / baseline["document"],
                                 "baseline OpenAPI snapshot")
        base_ops = collect_operations(baseline_doc)
        cand_ops = collect_operations(candidate)
        findings = []
        for key, base in sorted(base_ops.items()):
            path, method = key
            op_id = f"{method.upper()} {path}"
            cand = cand_ops.get(key)
            if cand is None:
                findings.append({"kind": "removed-operation", "breaking": True,
                                 "target": op_id,
                                 "detail": "the operation is gone from the candidate"})
                continue
            if base["operationId"] and cand["operationId"] \
                    and base["operationId"] != cand["operationId"]:
                findings.append({"kind": "operation-id-change", "breaking": True,
                                 "target": op_id,
                                 "detail": f"operationId {base['operationId']} -> "
                                           f"{cand['operationId']}"})
            for (loc, name), was_required in sorted(base["params"].items()):
                if (loc, name) not in cand["params"]:
                    findings.append({"kind": "removed-parameter",
                                     "breaking": True,
                                     "target": f"{op_id}: {loc} parameter '{name}'",
                                     "detail": "the parameter is gone"})
                elif not was_required and cand["params"][(loc, name)]:
                    findings.append({"kind": "new-required-parameter",
                                     "breaking": True,
                                     "target": f"{op_id}: {loc} parameter '{name}'",
                                     "detail": "an optional parameter became required"})
            if not base["body_required"] and cand["body_required"]:
                findings.append({"kind": "new-required-request-body",
                                 "breaking": True, "target": op_id,
                                 "detail": "a request body that was optional "
                                           "is now required"})
            _diff_surfaces(findings, op_id, "request", base["body"], cand["body"])
            for status, base_surface in sorted(base["responses"].items()):
                if status not in cand["responses"]:
                    findings.append({"kind": "removed-response-status",
                                     "breaking": True,
                                     "target": f"{op_id}: status {status}",
                                     "detail": "the status code is gone"})
                    continue
                _diff_surfaces(findings, op_id, f"response {status}",
                               base_surface, cand["responses"][status])
        for key in sorted(set(cand_ops) - set(base_ops)):
            additive += 1
        covered_ids = set()
        for finding in findings:
            entry = match_exception(finding["kind"], finding["target"], exceptions)
            if entry:
                covered_ids.add(entry["id"])
                finding["covered_by"] = entry["id"]
            else:
                breaking.append(finding)
        consumed_kinds = BREAKING_KINDS
        for entry in exceptions:
            if entry["kind"] in consumed_kinds and entry["id"] not in covered_ids:
                print(f"api: FAIL - reviewed exception {entry['id']} "
                      f"({entry['kind']} {entry['target']!r}) matches no "
                      "finding: the breaking change it reviewed is gone or "
                      "renamed, and stale exceptions are how a ledger starts "
                      "covering changes nobody reviewed", file=sys.stderr)
                return EXIT_FAIL
    else:
        # Nothing to diff against until the first tag exists; the reviewed 0.x
        # declaration is what stands in, and it was validated by read_baseline.
        print("api: NOTE - contract mode is pre-baseline: this repository has "
              "no previously supported stable release to diff against "
              "(measured 0 tags, #1578). The reviewed 0.x reading declared in "
              f"{args.baseline} ({'; '.join(baseline['policy']['declared_on'])}) "
              "is in force; `version` and `upgrade` still enforce what a "
              "breaking change owes in this mode.")

    report = {
        "gate": "api", "ok": not breaking, "mode": baseline["mode"],
        "info_version": info_version,
        "breaking": breaking,
        "additive_operations": additive,
        "behavioral_blindspots": BEHAVIORAL_BLINDSPOTS,
        "behavioral_note": "a schema diff cannot see these; the release "
                           "notes, not this gate, carry their acknowledgment",
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                     encoding="utf-8")
    for finding in breaking:
        print(f"api: FAIL - unreviewed breaking change: {finding['kind']} "
              f"{finding['target']} ({finding['detail']}); name it in "
              f"{args.exceptions} with the issue that reviewed it",
              file=sys.stderr)
    if breaking:
        return EXIT_FAIL
    print(f"api: ok - mode {baseline['mode']}, "
          f"{additive} additive operation(s), no unreviewed breaking change")
    print("api: note - behavioral gaps the diff cannot see (acknowledge in "
          "the release notes):")
    for item in BEHAVIORAL_BLINDSPOTS:
        print(f"  - {item}")
    return EXIT_OK


# --------------------------------------------------------------------------
# git helpers shared by version and upgrade


def git(root, *args):
    proc = subprocess.run(("git", "-C", str(root)) + args,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise GateCannotRun(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def resolve_base(root, base):
    for ref in (base, "develop", "origin/develop"):
        proc = subprocess.run(("git", "-C", str(root), "rev-parse", "--verify",
                               f"{ref}^{{commit}}"),
                              capture_output=True, text=True)
        if proc.returncode == 0:
            return git(root, "merge-base", proc.stdout.strip(), "HEAD").strip()
    raise GateCannotRun(
        f"neither {base} nor develop resolves in {root}: this gate decides "
        "about a range and refuses to guess one")


MIGRATION_ADDED_RE = re.compile(r"backend/([^/]+)/migrations/(\d+_[^/]+)\.py$")


def new_migration_files(root, merge_base):
    out = git(root, "diff", "--name-only", "--diff-filter=A",
              f"{merge_base}..HEAD", "--", "backend")
    found = []
    for line in out.splitlines():
        match = MIGRATION_ADDED_RE.match(line)
        if match:
            found.append({"app": match.group(1), "name": match.group(2),
                          "path": line})
    return found


# --------------------------------------------------------------------------
# the required-configuration surface


def required_compose_vars(root):
    """Every ${VAR:?...} of the tracked Compose files: a deployment that does
    not set one fails at `docker compose` with 'Please configure ...' - the
    machine-detectable definition of a required deployment setting."""
    names = set()
    proc = subprocess.run(("git", "-C", str(root), "ls-files",
                           "--", "*.yml", "*.yaml"),
                          capture_output=True, text=True)
    for line in proc.stdout.splitlines():
        if "compose" not in Path(line).name:
            continue
        try:
            text = (root / line).read_text(encoding="utf-8")
        except OSError:
            continue
        names.update(REQUIRED_COMPOSE_RE.findall(text))
    return names


def required_settings_vars(root):
    names = set()
    settings_dir = root / "backend" / "MrMap"
    if not settings_dir.is_dir():
        raise GateCannotRun(f"no backend/MrMap settings directory in {root}")
    for path in sorted(settings_dir.glob("*.py")):
        names.update(REQUIRED_SETTINGS_RE.findall(
            path.read_text(encoding="utf-8")))
    return names


def new_required_config(root, merge_base):
    """Config names the range ADDED to the required surface (compose diff plus
    the settings diff). Removals are left to the changelog: a removed variable
    is invisible to a static diff exactly when its last reader was the range's
    own code, which is what the Migration notes entry is for."""
    added = set()
    out = git(root, "diff", "--unified=0", f"{merge_base}..HEAD", "--",
              "*.yml", "*.yaml", "backend/MrMap")
    current_compose = required_compose_vars(root)
    current_settings = required_settings_vars(root)
    for line in out.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:]
        added.update(REQUIRED_COMPOSE_RE.findall(body))
        added.update(REQUIRED_SETTINGS_RE.findall(body))
    return sorted(added & (current_compose | current_settings))


# --------------------------------------------------------------------------
# the changelog's migration notes


def unreleased_section(root):
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[0\.x\.x\] - UNRELEASED$", text, re.M)
    if not match:
        raise GateCannotRun("CHANGELOG.md has no '## [0.x.x] - UNRELEASED' "
                            "heading - the migration-notes gate has no place "
                            "to look and refuses to invent one")
    nxt = re.search(r"^## \[", text[match.end():], re.M)
    return text[match.end():match.end() + (nxt.start() if nxt else len(text))]


def migration_notes_section(section):
    start = section.find("### Migration notes")
    if start < 0:
        return None
    nxt = re.search(r"^### ", section[start + len("### Migration notes"):], re.M)
    return section[start:start + len("### Migration notes") +
                   (nxt.start() if nxt else len(section))]


def cmd_version(args):
    root = Path(args.root)
    baseline = read_baseline(root, args.baseline, document_required=False)
    code, out, err = run_tool(
        [sys.executable, str(root / "scripts/canonical_version.py"),
         "--print", "--root", str(root)], cwd=str(root))
    if code != 0:
        raise GateCannotRun(f"canonical_version --print failed: {err.strip()}")
    candidate_version = out.strip()

    merge_base = resolve_base(root, args.base)
    rng = f"{merge_base}..HEAD"
    count = int(git(root, "rev-list", "--count", rng).strip() or "0")
    if count:
        code, out, err = run_tool(
            [sys.executable, str(root / "scripts/pr_classify"), "history",
             "--range", rng, "--repo", str(root), "--json"], cwd=str(root))
        if code not in (0, 1):
            raise GateCannotRun(f"pr_classify history failed: {err.strip()}")
        history = json.loads(out)
        entries = history.get("entries", [])
    else:
        # An empty range is the common case on develop itself and on the
        # merge-queue squash of a branch that was just cut: nothing to
        # classify, which is an answer, not a failure.
        entries = []
    breaking = [e for e in entries if e.get("breaking")]
    features = [e for e in entries if e.get("type") == "feat"
                and not e.get("breaking")]
    fixes = [e for e in entries if e.get("type") in ("fix", "perf")
             and not e.get("breaking")]

    problems, advisories = [], []
    section = unreleased_section(root)
    notes = migration_notes_section(section)

    # what the range demands of an operator, before any version question
    migrations = new_migration_files(root, merge_base)
    configs = new_required_config(root, merge_base)
    tokens = [f"{m['app']}.{m['name']}" for m in migrations] + configs
    if tokens:
        if notes is None:
            problems.append(
                "the range adds "
                + ", ".join(tokens)
                + " but CHANGELOG.md's UNRELEASED section has no '### "
                "Migration notes' subsection - what a deployment must do is "
                "not documentation to skip")
        else:
            for token in tokens:
                short = token.split(".", 1)[-1]
                if token not in notes and short not in notes:
                    problems.append(
                        f"{token} is added by this range but is not named "
                        "under '### Migration notes' of the UNRELEASED "
                        "section")

    if breaking:
        if "**Breaking:**" not in section:
            problems.append(
                f"{len(breaking)} breaking change(s) in {rng} but the "
                "UNRELEASED section carries no '**Breaking:**' line - the "
                "classification of #1580 says breaking, the notes have to say "
                "it too")

    # the bump question, which only a released baseline can decide
    required = None
    if breaking:
        required = "major"
    elif features:
        required = "minor"
    elif fixes:
        required = "patch"
    baseline_version = baseline.get("version")
    if baseline_version is None:
        if required:
            advisories.append(
                f"the range contains a {required}-worthy change, but there "
                f"is no released baseline to bump from (mode "
                f"'{baseline['mode']}', Q1 of #1578 Pending) - the reviewed "
                "0.x reading stands in until the first tag exists")
    else:
        base_parts = semver_parse(baseline_version, "the baseline version")[:3]
        cand_parts = semver_parse(candidate_version,
                                  "the candidate version")[:3]
        order = semver_cmp(candidate_version, baseline_version,
                           "the candidate version", "the baseline version")
        moved_major = cand_parts[0] > base_parts[0]
        moved_minor = moved_major or (cand_parts[0] == base_parts[0]
                                      and cand_parts[1] > base_parts[1])
        if order < 0:
            problems.append(
                f"{candidate_version} is BEHIND the baseline "
                f"{baseline_version}: a released version never moves "
                "backwards, and a prerelease sorts below the release it "
                "precedes - an rc candidate carries the version it will "
                "become (`0.2.0-rc.1`, scripts/image_release.py), not the "
                "baseline's")
        elif order == 0 and required:
            problems.append(
                f"the range is {required}-worthy but {candidate_version} has "
                f"the same precedence as the baseline {baseline_version} "
                "(build metadata does not move a version ahead: SemVer "
                "ignores it for precedence, so a new build of the baseline "
                "version is not a bump)")
        else:
            policy = baseline.get("policy", {})
            minor_for_breaking = (policy.get("breaking_below_1_0") == "minor"
                                  and base_parts[0] == 0
                                  and cand_parts[0] == 0)
            if required == "major" and not moved_major and not minor_for_breaking:
                problems.append(
                    f"a breaking change requires a major bump (or the "
                    f"reviewed 0.x minor reading, which needs "
                    f"policy.breaking_below_1_0='minor' and major 0): "
                    f"{baseline_version} -> {candidate_version}")
            elif required == "minor" and not moved_minor:
                problems.append(
                    f"a feature requires a minor bump: {baseline_version} -> "
                    f"{candidate_version}")

    report = {
        "gate": "version", "ok": not problems,
        "mode": baseline["mode"], "candidate_version": candidate_version,
        "baseline_version": baseline_version, "required_bump": required,
        "breaking": len(breaking), "features": len(features),
        "new_migrations": [f"{m['app']}.{m['name']}" for m in migrations],
        "new_required_config": configs,
        "problems": problems, "advisories": advisories,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                     encoding="utf-8")
    for advisory in advisories:
        print(f"version: note - {advisory}")
    for problem in problems:
        print(f"version: FAIL - {problem}", file=sys.stderr)
    if problems:
        return EXIT_FAIL
    print(f"version: ok - {candidate_version}, required bump "
          f"{required or 'none'}, {len(breaking)} breaking, "
          f"{len(migrations)} new migration(s), "
          f"{len(configs)} new required setting(s)")
    return EXIT_OK


# --------------------------------------------------------------------------
# the upgrade gate


def inspect_migration(path):
    """What one migration file statically is: fake (no real operations),
    destructive (its destructive operation names), and whether it carries the
    reviewed empty-operations marker with the issue that approved it."""
    text = path.read_text(encoding="utf-8")
    marker = MARKER_RE.search(text)
    tree = ast.parse(text, filename=str(path))
    operations = None
    destructive = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                        isinstance(t, ast.Name) and t.id == "operations"
                        for t in stmt.targets) and isinstance(stmt.value, ast.List):
                    operations = stmt.value
        if isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else \
                func.id if isinstance(func, ast.Name) else None
            if name in DESTRUCTIVE_OPS:
                detail = "/".join(
                    a.value if isinstance(a, ast.Constant) and isinstance(a.value, str)
                    else "?" for a in node.args) or "?"
                destructive.append({"op": name, "detail": detail})
            elif name == "RunSQL":
                for arg in node.args:
                    for const in ast.walk(arg):
                        if isinstance(const, ast.Constant) and isinstance(const.value, str) \
                                and re.search(r"\bDROP\b", const.value, re.I):
                            destructive.append({"op": "RunSQL",
                                                "detail": const.value[:80]})
                            break
    empty = operations is None or len(operations.elts) == 0
    noop_only = False
    if not empty and all(
            isinstance(el, ast.Call) and (
                (isinstance(el.func, ast.Attribute) and el.func.attr == "RunPython"))
            for el in operations.elts):
        def is_noop(node):
            if node is None:
                return True
            if isinstance(node, ast.Constant) and node.value is None:
                return True
            if isinstance(node, ast.Attribute) and node.attr == "noop":
                return True
            if isinstance(node, ast.Name) and node.id == "noop":
                return True
            if isinstance(node, ast.Lambda) and (
                    isinstance(node.body, ast.Constant) and node.body.value is None):
                return True
            return False
        noop_only = all(
            is_noop(el.args[0] if el.args else None)
            and is_noop(el.args[1] if len(el.args) > 1 else None)
            for el in operations.elts)
    return {"empty": empty, "noop_only": noop_only,
            "destructive": destructive,
            "marker": marker.group(1) if marker else None}


def _non_docstring_strings(path):
    """Every string constant of a module that is not a docstring. Prose about
    a retired app is documentation (#1180's own migration explains the old
    dependency); only a string the CODE carries can name it again."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    doc_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                doc_ids.add(id(node.body[0].value))
    return {n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in doc_ids}


def retired_app_references(root, label):
    """Files whose CODE still names the retired application as a Django app
    (a dependency edge string, an INSTALLED_APPS entry string). The bare
    legacy TABLE names of the package's tables never match this exact label,
    and #1180's guarded raw-SQL reads of its orphaned tables stay legitimate
    evidence, not hits."""
    hits = []
    for path in (sorted((root / "backend").glob("*/migrations/*.py"))
                 + sorted((root / "backend" / "MrMap").glob("*.py"))):
        if label in _non_docstring_strings(path):
            hits.append(str(path.relative_to(root)))
    return hits


def cmd_upgrade(args):
    root = Path(args.root)
    constraints = load_json(root / args.constraints, "upgrade constraints file")
    exceptions = read_exceptions(root, args.exceptions)
    problems = []

    # 1) the graph, decided by the one tool that reads graphs (#1157)
    code, out, err = run_tool(
        [sys.executable, str(root / "scripts/migration_graph_smoke.py"),
         "--head", args.head, "--base", args.base, "--json"], cwd=str(root))
    if code == 2:
        raise GateCannotRun(f"migration_graph_smoke could not run: {err.strip()}")
    graph = json.loads(out) if code in (0, 1) and out.strip() else None
    if graph is None:
        raise GateCannotRun("migration_graph_smoke answered nothing")
    if not graph.get("ok"):
        for app in graph["apps"]:
            if not app["ok"]:
                problems.append(
                    f"migration graph: app {app['app']} has leaves "
                    + ", ".join(leaf["name"] for leaf in app["leaves"]))
        if graph.get("dangling"):
            problems.append("migration graph: dangling dependency(ies) "
                            + json.dumps(graph["dangling"]))
        if graph.get("cyclic"):
            problems.append("migration graph: the graph has a cycle")

    # 2) the staged #1180 constraints
    for node in constraints.get("protected_nodes", []):
        app, name = node.split("/", 1)
        path = root / "backend" / app / "migrations" / f"{name}.py"
        if not path.exists():
            problems.append(
                f"#1180 constraint: protected node {node} is gone ({path}); "
                "a node whose name the graph parents on cannot be deleted - "
                "see docs/source/development/celery-result-backend.rst")
    for app_label in constraints.get("retired_apps", []):
        hits = retired_app_references(root, app_label)
        if hits:
            problems.append(
                f"#1180 constraint: retired app {app_label} is named as a "
                "Django application again by:\n  " + "\n  ".join(hits))

    # 3) + 4) what the ADDED migrations of the range are
    merge_base = resolve_base(root, args.base)
    new = new_migration_files(root, merge_base)
    destructive_targets = []
    for migration in new:
        path = root / migration["path"]
        info = inspect_migration(path)
        node = f"{migration['app']}.{migration['name']}"
        if (info["empty"] or info["noop_only"]) and not info["marker"]:
            problems.append(
                f"fake migration: {node} declares "
                f"{'no operations' if info['empty'] else 'only a noop RunPython'}"
                " - a node that lies about the schema it changes. If the empty"
                " node is genuinely wanted (a #1180-style named placeholder),"
                " the file must carry '# release-gates: empty-operations --"
                " refs #<issue>' so a human approved exactly that")
        for found in info["destructive"]:
            target = f"{node}: {found['op']} {found['detail']}"
            destructive_targets.append(target)
            if not match_exception("destructive-migration", target, exceptions):
                problems.append(
                    f"destructive change without approval: {target} - name it"
                    f" in {args.exceptions} with the issue a human reviewed")

    # stale destructive exceptions are as dangerous as stale api ones
    new_nodes = {f"{m['app']}.{m['name']}" for m in new}
    for entry in exceptions:
        if entry["kind"] != "destructive-migration":
            continue
        if entry["target"].split(":", 1)[0] not in new_nodes \
                and not entry["target"].endswith("*"):
            problems.append(
                f"stale exception {entry['id']}: {entry['target']} reviews a "
                "destructive change of a migration this range does not add")

    report = {
        "gate": "upgrade", "ok": not problems,
        "graph": graph.get("ok"), "new_migrations": [
            f"{m['app']}.{m['name']}" for m in new],
        "destructive": destructive_targets,
        "oldest_supported_baseline": constraints.get(
            "oldest_supported_baseline"),
        "problems": problems,
    }
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n",
                                     encoding="utf-8")
    for problem in problems:
        print(f"upgrade: FAIL - {problem}", file=sys.stderr)
    if problems:
        return EXIT_FAIL
    print(f"upgrade: ok - graph one leaf per app, "
          f"{len(constraints.get('protected_nodes', []))} protected nodes "
          f"present, {len(new)} new migration(s) checked")
    print(f"upgrade: note - the CI upgrade run must start from the oldest "
          f"supported baseline: {constraints.get('oldest_supported_baseline')} "
          f"(marker {constraints.get('marker_migration')}); a fresh install "
          "and an upgrade from there are run by the existing QA containers")
    return EXIT_OK


# --------------------------------------------------------------------------
# the promotion gate and its attestation


REQUIRED_EVIDENCE = ("tests", "sonar", "dependencies", "artifacts")
REQUIRED_IMAGES = ("mrmap-backend", "mrmap-frontend")
REQUIRED_GATES = ("api", "version", "upgrade")


def cmd_promote(args):
    evidence = load_json(args.evidence, "promotion evidence file")
    sha = args.sha or (evidence.get("candidate") or {}).get("sha")
    version = args.version or (evidence.get("candidate") or {}).get("version")
    problems = []
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        problems.append(f"candidate sha must be 40 hex characters, "
                        f"got {sha!r}")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        problems.append(f"candidate version must be strict SemVer, "
                        f"got {version!r}")

    checks = evidence.get("checks") or {}
    digests = {}
    for name in REQUIRED_EVIDENCE:
        check = checks.get(name)
        if not isinstance(check, dict):
            problems.append(f"required evidence {name!r} is missing entirely")
            continue
        if check.get("status") != "pass":
            problems.append(f"evidence {name} did not pass "
                            f"(status {check.get('status')!r})")
        if check.get("sha") != sha:
            problems.append(
                f"evidence {name} was gathered for sha "
                f"{check.get('sha')!r}, not the candidate {sha!r} - evidence "
                "of another build cannot promote this one")
        if name == "artifacts":
            images = check.get("images") or {}
            for image in REQUIRED_IMAGES:
                entry = images.get(image)
                digest = (entry or {}).get("digest", "")
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                    problems.append(
                        f"artifact {image} must carry a sha256:<64 hex> "
                        f"digest of the candidate, got {digest!r}")
                else:
                    digests[image] = digest

    gates = {}
    for spec in args.gate or []:
        if "=" not in spec:
            raise GateCannotRun(f"--gate {spec!r} is not name=path")
        name, path = spec.split("=", 1)
        gates[name] = load_json(path, f"gate report {name}")
    for name in REQUIRED_GATES:
        report = gates.get(name)
        if report is None:
            problems.append(f"gate report {name} was not provided "
                            "(run the gate and pass its --report file)")
            continue
        if not report.get("ok"):
            problems.append(f"gate {name} is red")
        if name == "version" and version and report.get("candidate_version") \
                and report["candidate_version"] != version:
            problems.append(
                f"the version gate reports {report['candidate_version']} but "
                f"the candidate is {version}")

    if args.expect_version:
        if version != args.expect_version:
            problems.append(
                f"the candidate version {version} is not the expected "
                f"{args.expect_version}")

    if problems:
        for problem in problems:
            print(f"promote: FAIL - {problem}", file=sys.stderr)
        return EXIT_FAIL

    evidence_summary = {
        name: {key: (checks.get(name) or {}).get(key)
               for key in ("status", "url", "sha")}
        for name in REQUIRED_EVIDENCE}

    attestation = {
        "attestation": "mrmap-release-candidate/1",
        "candidate": {"sha": sha, "version": version,
                      "channel": args.channel},
        "digests": digests,
        "evidence": evidence_summary,
        "gates": {name: {"ok": report.get("ok"),
                         "mode": report.get("mode")}
                  for name, report in sorted(gates.items())},
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "generated_by": args.actor or "unknown",
        "note": "evidence binding, not an approval: promotion itself stays a "
                "human act on a permanent branch",
    }
    text = json.dumps(attestation, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"promote: attestation written to {args.output}")
    else:
        print(text, end="")
    print(f"promote: ok - attested {version} at {sha[:12]} with "
          f"{len(digests)} artifact digest(s) and "
          f"{len(gates)} green gate report(s)")
    return EXIT_OK


# --------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="release_gates", description=__doc__.splitlines()[0],
        epilog="exit 0 the gate passes, 1 the gate decides against the "
               "candidate, 2 the gate could not run")
    parser.add_argument("--root", default=".",
                        help="repository root (default: cwd)")
    sub = parser.add_subparsers(dest="gate", required=True)

    def common(p):
        p.add_argument("--baseline", default=BASELINE_DEFAULT)
        p.add_argument("--exceptions", default=EXCEPTIONS_DEFAULT)
        p.add_argument("--report", default=None,
                       help="also write the machine-readable verdict here")

    p = sub.add_parser("api", help="diff the candidate OpenAPI document "
                                   "against the reviewed contract baseline")
    common(p)
    p.add_argument("--candidate", required=True,
                   help="the generated candidate document (JSON)")
    p.add_argument("--skip-version-check", action="store_true",
                   help="do not require info.version to equal VERSION "
                        "(only for testing the gate itself)")
    p.set_defaults(func=cmd_api)

    p = sub.add_parser("version", help="decide the bump and the migration "
                                       "notes of the range")
    common(p)
    p.add_argument("--base", default="origin/develop",
                   help="the ref HEAD is merged into (default origin/develop)")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("upgrade", help="graph, #1180 constraints, fake and "
                                       "destructive migrations")
    common(p)
    p.add_argument("--constraints", default=UPGRADE_BASELINE_DEFAULT)
    p.add_argument("--head", default="HEAD")
    p.add_argument("--base", default="origin/develop")
    p.set_defaults(func=cmd_upgrade)

    p = sub.add_parser("promote", help="attest the candidate from its "
                                       "evidence and gate reports")
    p.add_argument("--evidence", required=True)
    p.add_argument("--gate", action="append", metavar="NAME=PATH",
                   help="a gate report, repeatable")
    p.add_argument("--sha", default=None)
    p.add_argument("--version", default=None)
    p.add_argument("--expect-version", default=None,
                   help="refuse a candidate that is not this version")
    p.add_argument("--channel", default="stable")
    p.add_argument("--actor", default=None)
    p.add_argument("--output", default=None)
    p.set_defaults(func=cmd_promote)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GateCannotRun as error:
        print(f"release_gates: cannot run: {error}", file=sys.stderr)
        return EXIT_CANNOT


if __name__ == "__main__":
    sys.exit(main())
