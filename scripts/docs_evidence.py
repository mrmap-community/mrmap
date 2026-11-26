#!/usr/bin/env python3
"""The evidence store of one documentation run (#1598, epic #1589).

ADR-0001 section 4 makes evidence the unit of trust, and the rule it enforces is
short: **prose without provenance is not rendered**. This module is what that rule
needs to be executable rather than aspirational - a content-addressed store with a
digest per record, a lookup by claim and locale, and a validator that refuses a
record whose sources cannot be checked against the tree it names.

The store is written as one JSON document per run under ``evidence/`` and becomes
part of the release artifact set (section 6), not a commit to develop. It is
deliberately a file and not a database: the epic forbids a persistent store, the
gate reads it in one pass, and a reviewer must be able to read it in one screen.

Two things are verified rather than trusted:

* **The id.** Recomputed from the record's own content. An id that does not match
  its body means the file was edited after the run, and that is a gate failure
  rather than a curiosity.
* **The sources.** Every ``extracted`` source is checked against the bytes at the
  path it names: the blob must match, and the line span must lie inside the file.
  A record that cites a span past the end of its file is refused - which is the
  check that catches a fact carried over from a tree that no longer exists, the
  slow drift that hand-maintained provenance suffers from.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402

STORE_REL = "evidence/store.json"


class EvidenceStore:
    """The evidence of one run, keyed by record id.

    ``add`` validates, deduplicates by id and refuses a second record for the same
    ``(claim_id, locale, kind)`` triple. The dedup matters: two records for one
    claim is how a run ends up publishing whichever sentence a dict iteration
    happened to yield last.
    """

    def __init__(self, workspace=None):
        self.workspace = workspace
        self._records: dict[str, dict] = {}
        self._triples: dict[tuple, str] = {}
        self.rejected: list[str] = []

    # --------------------------------------------------------------------- add ---
    def add(self, record: dict) -> dict:
        contract.require_valid("evidence", record)
        recomputed = contract.sha256_obj(
            {key: value for key, value in record.items() if key != "id"})
        if recomputed != record["id"]:
            raise contract.ContractError(
                f"evidence id {contract.short(record['id'])} does not match its "
                f"content ({contract.short(recomputed)}): the record was edited "
                f"after it was built")
        triple = (record["claim_id"], record["locale"], record["kind"])
        existing = self._triples.get(triple)
        if existing and existing != record["id"]:
            self.rejected.append(
                f"{triple}: a record for this claim, locale and kind already "
                f"exists ({contract.short(existing)})")
            raise contract.ContractError(self.rejected[-1])
        self._records[record["id"]] = record
        self._triples[triple] = record["id"]
        return record

    def add_extracted(self, *, claim_id: str, audience: str, locale: str,
                      sources, run_id: str, generated_at: str) -> dict:
        return self.add(contract.evidence_record(
            claim_id=claim_id, kind="extracted", audience=audience, locale=locale,
            run_id=run_id, generated_at=generated_at, sources=sources,
            produced_by_=contract.produced_by("extractor")))

    def add_executed(self, *, claim_id: str, audience: str, locale: str,
                     assertion, run_id: str, generated_at: str,
                     sources=()) -> dict:
        return self.add(contract.evidence_record(
            claim_id=claim_id, kind="executed", audience=audience, locale=locale,
            run_id=run_id, generated_at=generated_at, sources=list(sources),
            assertion=assertion, produced_by_=contract.produced_by("executor")))

    def add_inferred(self, *, claim_id: str, audience: str, locale: str, text: str,
                     model_id: str, provider: str, sources, run_id: str,
                     generated_at: str) -> dict:
        return self.add(contract.evidence_record(
            claim_id=claim_id, kind="inferred", audience=audience, locale=locale,
            run_id=run_id, generated_at=generated_at, sources=list(sources),
            text_sha256=contract.sha256_text(text),
            produced_by_=contract.produced_by("author", model_id, provider)))

    def add_unsupported(self, *, claim_id: str, audience: str, locale: str,
                        reason: str, run_id: str, generated_at: str) -> dict:
        """A topic the pipeline could not evidence, recorded as such.

        ADR-0001 section 11: an empty space and a plausible paragraph look the same
        to a reader, so the absence is an artifact of its own. An ``unsupported``
        row is what makes "not documented" a reported state rather than a silent
        omission.
        """
        return self.add(contract.evidence_record(
            claim_id=claim_id, kind="extracted", audience=audience, locale=locale,
            run_id=run_id, generated_at=generated_at, sources=[],
            unsupported_reason=workspace_lib.scrub_text(reason)[:2000],
            produced_by_=contract.produced_by("validator")))

    # ------------------------------------------------------------------- query ---
    def records(self) -> list[dict]:
        return [self._records[key] for key in sorted(self._records)]

    def ids(self) -> list[str]:
        return sorted(self._records)

    def get(self, evidence_id: str) -> dict | None:
        return self._records.get(evidence_id)

    def for_claim(self, claim_id: str, locale: str | None = None) -> list[dict]:
        return [record for key, record in sorted(self._records.items())
                if record["claim_id"] == claim_id
                and (locale is None or record["locale"] == locale)]

    def counts(self) -> dict:
        by_kind: dict[str, int] = {}
        for record in self._records.values():
            by_kind[record["kind"]] = by_kind.get(record["kind"], 0) + 1
        unsupported = sum(1 for record in self._records.values()
                          if record["unsupported_reason"])
        return {"records": len(self._records), "by_kind": by_kind,
                "unsupported": unsupported, "rejected": len(self.rejected)}

    def digest(self, kinds: tuple[str, ...] | None = None) -> str:
        """The store's digest: an input of the reuse key, so an evidence edit
        invalidates the artifact rather than silently riding along with it.

        ``kinds`` narrows the digest. A generated page depends on the
        ``extracted`` spans and the ``executed`` assertions behind its facts - not
        on the ``inferred`` record that describes the page itself, which is written
        *after* the page. Without that distinction every page would cite a digest
        that the same stage changes a moment later, and every rerun would find the
        whole corpus stale: a sidecar that is stale the instant it is written is
        not a dependency graph, it is noise.
        """
        records = [self._digestable(record) for record in self.records()
                   if (kinds is None or record["kind"] in kinds)
                   # An ``unsupported`` row is an output of the author stage even
                   # though it is filed under ``extracted``, and it is written after
                   # the page that reports it. Counting it here would make the digest
                   # a page cites change the moment the page is written - permanently
                   # stale sidecars, and a rerun that regenerates everything.
                   and not record.get("unsupported_reason")]
        return contract.sha256_obj({"schema": "mrmap.docs.evidence-store.v1",
                                    "generator": contract.TOOL_VERSION,
                                    "kinds": list(kinds) if kinds else "all",
                                    "records": records})

    #: Timing is a measurement of the runner, not a claim about the software. Left
    #: inside a digest it makes the reuse key of an otherwise identical candidate
    #: move on every run, which turns "reuse only on an exact match" into "never
    #: reuse". The pipeline stops recording it inside an assertion; this projection
    #: is here so a store written by an older run - or by a tool that did record it -
    #: still digests the same way as the same content without it. The record id is
    #: dropped too: it is derived from the content, so carrying both double-counts
    #: and lets any content-level volatility leak into the key twice.
    VOLATILE_ASSERTION_FIELDS = ("duration_s",)

    @classmethod
    def _digestable(cls, record: dict) -> dict:
        projection = {key: value for key, value in record.items() if key != "id"}
        assertion = projection.get("assertion")
        if assertion:
            projection["assertion"] = {
                key: value for key, value in assertion.items()
                if key not in cls.VOLATILE_ASSERTION_FIELDS}
        return projection

    #: The evidence a generated output may depend on: what stood before the run
    #: wrote any prose. ``inferred`` and unsupported rows are outputs, not inputs.
    INPUT_KINDS = ("extracted", "executed")

    def input_digest(self) -> str:
        return self.digest(self.INPUT_KINDS)

    def as_document(self) -> dict:
        return {"schema": "mrmap.docs.evidence-store.v1",
                "generator": contract.TOOL_VERSION,
                "records": self.records()}

    # ------------------------------------------------------------------- write ---
    def save(self, workspace) -> str:
        document = self.as_document()
        workspace.write_json(STORE_REL, document, base=workspace.work,
                             kind="evidence")
        return STORE_REL

    @classmethod
    def load(cls, path: Path, workspace=None) -> "EvidenceStore":
        """Read a previous run's store, verifying every id on the way in.

        A corrupt store is refused rather than repaired: if the evidence of the
        last good run cannot be trusted, the run that reuses it cannot either.
        """
        store = cls(workspace)
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        for record in document.get("records", ()):
            store.add(record)
        return store

    # ------------------------------------------------------------------ verify ---
    def verify_sources(self, workspace) -> list[str]:
        """Check every source reference against the bytes it claims to come from.

        Returns the problems; empty means the store and the tree agree. This is the
        only place a source path is opened by the validator rather than written by
        the extractor, and it is the check that turns provenance from a claim into
        a fact: the blob must match the file, and the span must fit inside it.
        """
        problems: list[str] = []
        for record in self._records.values():
            for source in record["sources"]:
                rel = source["path"]
                try:
                    data = workspace.read_bytes(rel)
                except (workspace_lib.GuardError, OSError) as exc:
                    problems.append(f"{contract.short(record['id'])}: {rel} cannot "
                                    f"be read: {exc}")
                    continue
                if contract.blob_sha(data) != source["blob"]:
                    problems.append(
                        f"{contract.short(record['id'])}: {rel} has blob "
                        f"{contract.short(contract.blob_sha(data))}, the record "
                        f"claims {contract.short(source['blob'])}")
                    continue
                lines = data.count(b"\n") + 1
                start, end = source["span"]
                if start < 1 or end > lines:
                    problems.append(
                        f"{contract.short(record['id'])}: {rel} has {lines} line(s), "
                        f"the record cites {start}-{end}")
        return problems

    def verify_assertions(self) -> list[str]:
        """Check the shape of every ``executed`` assertion (V-14)."""
        problems = []
        for record in self._records.values():
            if record["kind"] != "executed":
                continue
            assertion = record["assertion"]
            if not assertion:
                problems.append(f"{contract.short(record['id'])}: executed without "
                                f"an assertion")
                continue
            if assertion["exit_code"] != 0:
                problems.append(f"{contract.short(record['id'])}: command exited "
                                f"{assertion['exit_code']}")
            if not str(assertion["stdout_sha256"]).startswith("sha256:"):
                problems.append(f"{contract.short(record['id'])}: no stdout digest")
            if not assertion["at"]:
                problems.append(f"{contract.short(record['id'])}: no revision named")
        return problems


def main(argv=None) -> int:  # pragma: no cover - exercised by the suites
    import argparse
    parser = argparse.ArgumentParser(prog="docs_evidence.py")
    parser.add_argument("--store", required=True, help="path to store.json")
    parser.add_argument("--root", default=".", help="tree to verify sources against")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(argv)
    workspace = workspace_lib.Workspace(root=Path(args.root).resolve(),
                                        work=Path(args.root).resolve()
                                        / ".mrmap-docs-work")
    try:
        store = EvidenceStore.load(Path(args.store), workspace)
    except (OSError, ValueError, contract.ContractError) as exc:
        print(f"the evidence store is not readable: {exc}", file=sys.stderr)
        return contract.EXIT_CANNOT
    print(json.dumps(store.counts(), indent=2, sort_keys=True))
    if args.verify:
        problems = store.verify_sources(workspace) + store.verify_assertions()
        for problem in problems:
            print(f"FAIL  {problem}")
        print(f"{len(store.ids()) - len(problems)}/{len(store.ids())} record(s) "
              f"verified")
        return contract.EXIT_FAIL if problems else contract.EXIT_OK
    return contract.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
