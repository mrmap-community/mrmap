#!/usr/bin/env python3
"""Content-addressed invalidation for the documentation pipeline (#1598, #1606).

ADR-0001 section 5 replaces the manifest with a dependency graph, and the whole
mechanism is two sentences long: every generated file records the digests it was
computed from, and invalidation is a set difference. This module is those two
sentences, plus the honesty rules that keep them from rotting.

A sidecar is one JSON file per generated output, named ``<output>.manifest.json``
and stored beside the output's copy in the run workspace::

    manifests/generated/en/integrator/webmapservice.rst.manifest.json
      {"engine": "author", "output": "generated/en/.../webmapservice.rst",
       "inputs": [{"kind": "evidence", "digest": "sha256:..."}], ...}

Three rules make the graph usable rather than decorative:

* **Nothing decides staleness by timestamp.** A sidecar is stale when one of its
  input digests no longer equals the digest of the input it names. A rebuild after
  a ``git checkout`` that changes nothing regenerates nothing.
* **An output with no producer is deleted.** The set difference runs both ways: a
  page whose subject has left the software goes, because keeping it "just in case"
  is how documentation describes a feature that no longer exists. ADR-0001 calls an
  orphan an error, not a warning, so the run reports the removal rather than
  performing it silently - deleting generated content is a decision a reviewer
  reads in ``report.json``.
* **Digests are computed from content the pipeline can still obtain.** A sidecar
  that cites a digest nothing can recompute is a permanent cache hit, so
  :meth:`SidecarStore.plan` refuses a sidecar whose input kind it does not know how
  to recompute, and counts it as stale.

#1606 put incremental reuse out of scope unless a measured bottleneck justifies it,
and that is respected here: this graph is used for correctness - what must be
regenerated, what must be removed - and the pipeline's default path is a complete
clean build. The one place a digest buys time is the translation memory, which is a
cache of accepted sentences rather than an incremental engine.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402

MANIFEST_DIR = "manifests"
SIDECAR_SUFFIX = ".manifest.json"

#: The input kinds the store knows how to recompute, and how. A kind outside this
#: map is a bug, not a cache hit: an input nobody can re-resolve would pin a page
#: to a state that no longer exists, which is the failure mode of every hand-kept
#: manifest this contract replaced.
RESOLVERS = ("source", "facts", "evidence", "model", "locale", "generator", "tool")


def digest_of(kind: str, value: str) -> str:
    """The canonical digest an input of ``kind`` carries.

    Every input digest is a ``sha256:...`` - including the inputs that are not file
    content, such as the model id or the locale. Letting a sidecar store a bare
    label would make the schema's digest shape a lie for half the kinds and would
    let a model named ``sha256:000...0`` impersonate a content digest.
    """
    if kind not in RESOLVERS:
        raise contract.ContractError(
            f"unknown input kind {kind!r}; the store can recompute "
            f"{', '.join(RESOLVERS)}")
    text = str(value)
    return text if text.startswith("sha256:") else contract.sha256_text(text)


class SidecarStore:
    """The invalidation graph of the generated tree.

    ``current`` maps an input kind to the digest that kind has *now* - the
    extractor's per-surface facts digest, the evidence store digest, the model id,
    the generator version. The store compares, and decides.
    """

    def __init__(self, workspace, current: dict[str, dict[str, str]] | None = None):
        self.workspace = workspace
        self.current = {kind: dict(values)
                        for kind, values in (current or {}).items()}
        self._written: dict[str, dict] = {}
        self.removed: list[str] = []

    # ------------------------------------------------------------------- write ---
    def write(self, record: dict) -> str:
        contract.require_valid("manifest", record)
        rel = f"{MANIFEST_DIR}/{record['output']}{SIDECAR_SUFFIX}"
        self.workspace.write_json(rel, record, base=self.workspace.work,
                                  kind="manifest")
        self._written[record["output"]] = record
        return rel

    def read(self, output: str) -> dict | None:
        rel = f"{MANIFEST_DIR}/{output}{SIDECAR_SUFFIX}"
        try:
            text = self.workspace.read_owned_text(rel)
        except (workspace_lib.GuardError, OSError):
            return self._written.get(output)
        try:
            record = json.loads(text)
        except ValueError:
            return None
        contract.require_valid("manifest", record)
        return record

    def all_outputs(self) -> list[str]:
        outputs = set(self._written)
        base = self.workspace.work / MANIFEST_DIR
        if base.is_dir():
            for path in base.rglob(f"*{SIDECAR_SUFFIX}"):
                outputs.add(path.relative_to(base).as_posix()
                            [:-len(SIDECAR_SUFFIX)])
        return sorted(outputs)

    def set_current(self, kind: str, name: str, digest: str) -> None:
        if kind not in RESOLVERS:
            raise contract.ContractError(
                f"unknown input kind {kind!r}; the store can recompute "
                f"{', '.join(RESOLVERS)}")
        self.current.setdefault(kind, {})[name] = digest

    # ------------------------------------------------------------------- plan ---
    def plan(self) -> tuple[list[str], list[str]]:
        """``(stale, orphans)`` for the outputs this run knows about.

        ``stale`` is every output whose sidecar names an input whose digest moved,
        or names an input the store cannot recompute. ``orphans`` is every output
        with no producer in this run's plan - a subject that left the software, or
        a page a generator stopped claiming - which is exactly ADR-0001's "an output
        with no producer" gate, and the mechanism behind #1606's requirement that a
        removed feature's topic not survive.
        """
        stale: list[str] = []
        orphans: list[str] = []
        for output in self.all_outputs():
            record = self.read(output)
            if record is None:
                stale.append(output)          # no sidecar: nothing to prove freshness
                continue
            if _is_stale(record, self.current):
                stale.append(output)
        planned = set(self._written)
        for output in self.all_outputs():
            if output not in planned:
                orphans.append(output)
        self.removed = orphans
        return stale, orphans

    def as_dict(self) -> dict:
        return {"outputs": len(self.all_outputs()),
                "written": len(self._written),
                "input_kinds": {kind: len(values)
                                for kind, values in sorted(self.current.items())}}


def _is_stale(record: dict, current: dict[str, dict[str, str]]) -> bool:
    """Whether any input of ``record`` moved, or cannot be re-resolved at all.

    An unresolvable kind counts as stale on purpose. A sidecar citing an input the
    store cannot recompute could never be proven fresh again, and treating that as
    "fresh" is how a cache pins a page to a state that no longer exists - the
    failure mode of the hand-kept manifest this contract replaced.
    """
    for input_ in record["inputs"]:
        if input_["kind"] not in RESOLVERS:
            return True
        if input_["digest"] not in current.get(input_["kind"], {}).values():
            return True
    return False


def plan_from_records(records, produced: list[str],
                      current: dict[str, dict[str, str]]):
    """Pure planning over sidecar records, for suites that need no filesystem.

    Returns ``(stale, orphans, unknown_kinds)``: which outputs must be regenerated,
    which have no producer among ``produced`` (the outputs this run's generators
    claim), and which cite an input kind the store cannot re-resolve. Keeping the
    decision in a function over data rather than a workspace is what lets the
    contract tests cover the interesting cases without building a tree for each.
    """
    stale: list[str] = []
    unknown: list[str] = []
    for record in records:
        output = record["output"]
        for input_ in record["inputs"]:
            if input_["kind"] not in RESOLVERS:
                unknown.append(f"{output}: {input_['kind']}")
        if _is_stale(record, current):
            stale.append(output)
    claimed = set(produced)
    orphans = sorted(record["output"] for record in records
                     if record["output"] not in claimed)
    return sorted(set(stale)), orphans, sorted(set(unknown))


def sidecar_path(output: str) -> str:
    return f"{MANIFEST_DIR}/{output}{SIDECAR_SUFFIX}"


def main(argv=None) -> int:  # pragma: no cover - the CLI is scripts/docs.py
    import argparse
    parser = argparse.ArgumentParser(prog="docs_manifests.py")
    parser.add_argument("--root", default=".")
    parser.add_argument("--workdir", default=".mrmap-docs-work")
    parser.add_argument("--plan", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=Path(args.workdir).resolve())
    workspace.allow_writes_under(workspace.work, workspace.publish,
                                 workspace.generated)
    store = SidecarStore(workspace)
    if args.plan:
        stale, orphans = store.plan()
        print(json.dumps({"stale": stale, "orphans": orphans,
                          "summary": store.as_dict()}, indent=2, sort_keys=True))
        return contract.EXIT_OK
    print(json.dumps(store.as_dict(), indent=2, sort_keys=True))
    return contract.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
