#!/usr/bin/env python3
"""docs: the provider-independent documentation pipeline of epic #1589 (#1598).

An ordinary noninteractive command line, orchestrated by ordinary GitHub Actions -
not a workflow engine, not an agent runtime, not a scheduler. Seven explicit
stages run in order over a frozen tree, and the artifact they leave is a report
plus a content-addressed bundle::

    python3 scripts/docs.py run --provider fake
    python3 scripts/docs.py run --provider command --provider-argv ./my-model-cli
    python3 scripts/docs.py contract --provider command --provider-argv ./my-model-cli
    python3 scripts/docs.py extract --surface models --json

What the pipeline guarantees, and where each guarantee lives:

* **Facts come from the tree** - ``scripts/docs_extract.py``, deterministic, no
  model. A fact that cannot be extracted is not a fact.
* **Prose is gated before it is rendered** - ``scripts/docs_author.py`` discards a
  response that cites an unknown fact or names an identifier no fact carries.
* **Every statement carries provenance** - ``scripts/docs_evidence.py``; a page
  without an evidence record is a gate failure, not a page.
* **Nothing runs but what is allowlisted** - ``scripts/docs_workspace.py`` holds the
  read/write/execute boundary, the scrubbed child environment and the budgets.
* **A provider is an adapter, and one suite judges every adapter** -
  ``scripts/docs_providers.py``; ``contract`` runs it, which is validation row V-15.
* **A failed run publishes nothing** - the publish stage writes only when the gate
  is green, and refuses a second write into a published path, so the previously
  verified publication stays byte-identical.

Exit codes follow the repository's host tools: **0** the asked-for work is done and
the gate is green, **1** the pipeline ran and refused the candidate (gate red, or a
publication that must not happen), **2** the pipeline could not run (a missing
binary, a refused path, a bad provider configuration). "Could not run" is never a
pass.

No credentials are needed for any stage of the default path, and the default path is
the one CI runs: the ``fake`` adapter is deterministic, offline and credential-free,
so "the pipeline works" is a claim a runner can check without a model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_author as author  # noqa: E402
import docs_contract as contract  # noqa: E402
import docs_evidence as evidence_lib  # noqa: E402
import docs_extract as extract  # noqa: E402
import docs_manifests as manifests  # noqa: E402
import docs_providers as providers  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402
from docs_workspace import GuardError  # noqa: E402

BASELINE_FILE = SCRIPTS / "docs_coverage_baseline.json"
PROVENANCE_SCHEMA = "mrmap.docs.provenance.v1"
#: How many facts one generated claim may carry. Bounded because the per-claim
#: request cap is per claim: a claim over 500 facts is one request that can fail
#: once and lose 500 sentences, and a chunk that small turns one model hiccup into
#: a page-sized hole.
FACTS_PER_CLAIM = 20
#: The dependency lockfiles that belong in the reuse key: a change to any of them
#: changes what the documented software *is*, so it must change the artifact's key
#: (ADR-0001 section 6). A lockfile the tree does not have is digested as absent
#: rather than skipped, so "no lockfile" is distinguishable from "another lockfile".
LOCKFILES = ("backend/requirements.txt", "frontend/package-lock.json",
             "backend/.requirements/docs.txt")


class StageError(RuntimeError):
    """A stage could not complete; the reason goes into ``report.json`` verbatim."""


# ----------------------------------------------------------------------- stage ---
class StageRecorder:
    """One row of the run's stage list, with the timing the report shows.

    A stage that never ran is recorded ``not_run`` rather than left out. A reader
    of ``report.json`` can then tell "this stage passed" from "this stage was never
    reached", which is the difference between a green run and a short one.
    """

    def __init__(self, run, name: str):
        self.run = run
        self.name = name
        self.started = run.stamp()

    def finish(self, status: str, *, detail: str = "", reason: str = "",
               checks: dict | None = None) -> dict:
        row = {"name": self.name, "status": status, "started_at": self.started,
               "finished_at": self.run.stamp(),
               "detail": workspace_lib.scrub_text(detail)[:2000] or None,
               "reason": workspace_lib.scrub_text(reason)[:500] or None,
               "checks": checks or {}}
        self.run.stages.append(row)
        self.run.log("stage", self.name, f"{status}: {row['detail'] or row['reason'] or ''}")
        return row


class Run:
    """One documentation run: its inputs, its stages, its report.

    The object is deliberately explicit about what a stage may use - the workspace
    boundary, the evidence store, the ledger, the adapter - because "the author
    cannot reach the tree" and "a failed run cannot reach the publish root" are
    properties of which object a stage holds, not of which checks it remembers to
    call.
    """

    def __init__(self, *, root: Path, workdir: Path, publish: Path,
                 surfaces: tuple[str, ...], provider_name: str,
                 provider_args: dict, locales: tuple[str, ...],
                 render: bool, verify_provider: bool, release: dict,
                 budget_overrides: dict, facts_per_claim: int,
                 allow_unknown_commit: bool, overwrite: bool,
                 now: str | None = None, python: str | None = None,
                 tool_timeout: float | None = None, verbose: bool = False):
        self.workspace = workspace_lib.Workspace(
            root=root, work=workdir, publish=publish,
            clock=workspace_lib.Clock(now), python=python or sys.executable,
            timeout_s=tool_timeout)
        self.workspace.allow_writes_under(self.workspace.work,
                                          self.workspace.publish,
                                          self.workspace.generated)
        self.surfaces = tuple(surfaces)
        self.provider_name = provider_name
        self.provider_args = dict(provider_args)
        self.locales = tuple(locales)
        self.render = render
        self.verify_provider = verify_provider
        self.release = dict(release or {})
        self.budget_overrides = dict(budget_overrides)
        self.facts_per_claim = max(1, int(facts_per_claim))
        self.allow_unknown_commit = allow_unknown_commit
        self.overwrite = overwrite
        self.verbose = verbose

        self._run_id = ""
        self.started_at = self.workspace.stamp()
        self.finished_at = self.started_at
        self.stages: list[dict] = []
        self.warnings: list[str] = []
        self.failures: list[str] = []
        self.checks: dict = {}
        self.facts: dict[str, dict] = {}
        self.pages: list[dict] = []
        self.evidence = evidence_lib.EvidenceStore(self.workspace)
        self.assertion_evidence: dict[str, str] = {}
        self.ledger = author.CostLedger(self.budget_overrides)
        self.memory = author.TranslationMemory()
        self.author: author.AuthorStage | None = None
        self.provider: providers.ProviderAdapter | None = None
        self.gate = None
        self.input_digest: str | None = None
        self.tool_env_withheld: set[str] = set()
        self.sidecars = manifests.SidecarStore(self.workspace)
        self.blocked_reason: str | None = None
        self.baseline: dict = {}
        #: ``(stale, orphans)`` as measured by discover, before this run wrote anything.
        self.plan_at_start: tuple[list[str], list[str]] = ([], [])
        #: Generated outputs this run removed because nothing produces them any more.
        self.removed: list[str] = []

    def compute_run_id(self) -> str:
        """The run id, once the input digest is known.

        Not cached before then: the id is read by stage logging before discover has
        run, and caching a placeholder at that moment would freeze the whole run's
        identity to the string "pending".
        """
        if self._run_id:
            return self._run_id
        if self.input_digest is None:
            return f"{self.started_at}-pending"
        self._run_id = f"{self.started_at}-{contract.short(self.input_digest)}"
        return self._run_id

    @property
    def run_id(self) -> str:
        return self.compute_run_id()

    @run_id.setter
    def run_id(self, value: str) -> None:
        self._run_id = value

    # ------------------------------------------------------------------- logging ---
    def log(self, kind: str, *parts) -> None:
        if self.verbose:
            print(f"[{kind}] " + " ".join(str(part) for part in parts),
                  file=sys.stderr)

    def warn(self, message: str) -> None:
        text = workspace_lib.scrub_text(message)[:2000]
        if text not in self.warnings:
            self.warnings.append(text)
            self.log("warning", text)

    def stamp(self) -> str:
        return self.workspace.stamp()

    # ------------------------------------------------------------------ identity ---
    @property
    def documented_commit(self) -> str | None:
        return self.workspace.documented_commit

    @property
    def version(self) -> str | None:
        return self.workspace.version()

    @property
    def input_prefixes(self) -> tuple[str, ...]:
        """The tree the run reads. Everything outside it is out of scope by policy."""
        return ("frontend/src/components/Resource", "backend", "docs",
                "scripts/docs_contract.py", "scripts/docs_extract.py")

    @property
    def generated_source(self) -> Path:
        return self.workspace.generated

    def audience_for(self, surface: str) -> str:
        return SURFACE_AUDIENCE.get(surface, "developer")

    @property
    def docs_manifest(self) -> str:
        """The reuse key of ADR-0001 section 6.

        A digest over everything that legitimately changes the artifact: the
        version, the tree, the dependency lockfiles, the locales, this generator's
        version, the model that answered and the evidence store. A locale edit, a
        ``package-lock.json`` bump or a model swap moves it; an identical rerun of
        an identical candidate does not, which is what makes "reuse only on an exact
        match" cheap enough to enforce.
        """
        model = self.provider.model_id if self.provider else None
        # Inputs only. The evidence digest that belongs here is the digest of the
        # extracted and executed records - the prose the run has not written yet is
        # an *output*, and folding it in made this key change while a single run was
        # still executing: the page body carries the run id, the run id carried this
        # key, and the key was therefore never the same value twice. A reuse key that
        # moves during its own run invalidates everything it is supposed to protect,
        # so #1606's clean-build comparison would never have matched.
        return contract.sha256_obj({
            "version": self.version,
            "tree": self.input_digest,
            "lockfiles": {name: self._lockfile_digest(name)
                          for name in LOCKFILES},
            "locales": list(self.locales),
            "generator": contract.TOOL_VERSION,
            "model": model,
            "evidence": self.evidence.input_digest(),
            "surfaces": list(self.surfaces),
        })

    def _lockfile_digest(self, rel: str) -> str:
        try:
            return contract.sha256_bytes(self.workspace.read_bytes(rel))
        except (GuardError, OSError):
            # A missing lockfile is recorded as absent rather than guessed at: the
            # reuse key has to distinguish "no lockfile" from "some other lockfile".
            return "sha256:" + "0" * 64

    # -------------------------------------------------------------------- stages ---
    def record(self, name: str) -> StageRecorder:
        return StageRecorder(self, name)

    def run_stages(self, stages: tuple[str, ...]) -> int:
        # A publication is a release act, and the release gate carries the adapter
        # contract suite (V-15): asking for an artifact without checking the provider
        # that wrote its prose would make the one check the epic names as mandatory
        # opt-out. Running it is cheap for the deterministic adapter and bounded for
        # a real one, so the release path turns it on rather than trusting a flag.
        if (self.release.get("candidate_sha") or self.release.get("release_sha")) \
                and not self.verify_provider:
            self.verify_provider = True
            self.warn("V-15 enabled for a release act: the contract suite runs "
                      "against the configured provider before anything is published")
        # The run id names every artifact and appears in every page, so it must be
        # reproducible: two runs against one pinned clock over one tree have to be
        # byte-identical, or the reuse key is a fiction. It is therefore the pinned
        # clock plus the input digest, and it is computed on demand rather than
        # assigned here - the digest is not known until discover has read the tree.
        try:
            self.memory = author.load_memory(
                self.workspace.work / "i18n" / "translation_memory.json")
        except contract.ContractError as exc:
            self.warn(f"translation memory ignored: {exc}")
        for name in stages:
            stage = STAGES[name]
            recorder = self.record(name)
            try:
                outcome = stage(self)
            except StageError as exc:
                self.failures.append(f"{name}: {workspace_lib.scrub_text(str(exc))}")
                recorder.finish("failed", reason=str(exc))
                self._mark_not_run(name)
                return self.finish(exit_code=contract.EXIT_FAIL)
            except providers.ProviderError as exc:
                # An unavailable model is a fail-closed event, not a degraded one:
                # the report says why, and the previous publication stands.
                self.failures.append(
                    f"{name}: provider unavailable: {workspace_lib.scrub_text(str(exc))}")
                recorder.finish("failed", reason=f"provider unavailable: {exc}")
                self._mark_not_run(name)
                return self.finish(exit_code=contract.EXIT_FAIL)
            except GuardError as exc:
                self.failures.append(f"{name}: refused by the boundary: "
                                     f"{workspace_lib.scrub_text(str(exc))}")
                recorder.finish("blocked", reason=str(exc))
                self._mark_not_run(name)
                return self.finish(exit_code=contract.EXIT_CANNOT)
            except contract.ContractError as exc:
                self.failures.append(f"{name}: contract refused: "
                                     f"{workspace_lib.scrub_text(str(exc))}")
                recorder.finish("failed", reason=str(exc))
                self._mark_not_run(name)
                return self.finish(exit_code=contract.EXIT_FAIL)
            status = outcome.get("status", "ok")
            recorder.finish(status, detail=outcome.get("detail", ""),
                            reason=outcome.get("reason", ""),
                            checks=outcome.get("checks", {}))
            if status == "blocked":
                self.blocked_reason = outcome.get("reason")
                self._mark_not_run(name)
                return self.finish(exit_code=contract.EXIT_FAIL)
        # A green run means the gate is green. Returning 0 after a red gate would
        # make the pipeline's own release gate unreadable by the caller, so the exit
        # code follows the gate rather than the absence of an exception.
        if self.gate is not None and self.gate.status == "fail":
            return self.finish(exit_code=contract.EXIT_FAIL)
        return self.finish(exit_code=contract.EXIT_OK)

    def _mark_not_run(self, after: str) -> None:
        reached = False
        for name in contract.STAGES:
            if reached:
                self.stages.append({"name": name, "status": "not_run",
                                    "started_at": self.stamp(),
                                    "finished_at": self.stamp(),
                                    "detail": None,
                                    "reason": f"the run stopped at {after}",
                                    "checks": {}})
            if name == after:
                reached = True

    # ---------------------------------------------------------------- sidecars ---
    def write_sidecar(self, output: str, record: dict) -> None:
        self.sidecars.write(record)

    def plan_invalidation(self) -> tuple[list[str], list[str]]:
        """Re-resolve the input digests and ask the graph what changed."""
        for surface, document in self.facts.items():
            self.sidecars.set_current("facts", surface,
                                      extract.facts_digest(document))
        self.sidecars.set_current("evidence", "store",
                                  self.evidence.input_digest())
        self.sidecars.set_current(
            "generator", contract.TOOL_VERSION,
            manifests.digest_of("generator", contract.TOOL_VERSION))
        self.sidecars.set_current("source", "tree",
                                  self.input_digest or contract.sha256_text(""))
        if self.provider:
            self.sidecars.set_current(
                "model", self.provider.model_id,
                manifests.digest_of("model", self.provider.model_id))
        for locale in self.locales:
            self.sidecars.set_current("locale", locale,
                                      manifests.digest_of("locale", locale))
        self.sidecars.set_current(
            "tool", "sphinx",
            manifests.digest_of("tool", "sphinx" if self.render
                                else "not-requested"))
        return self.sidecars.plan()

    # ------------------------------------------------------------------ claims ---
    def build_claims(self) -> dict[str, list[dict]]:
        """One claim per chunk of facts per surface, keyed by audience.

        Chunked rather than one-claim-per-surface so a claim that fails its budget
        costs a chunk and not a whole audience section, and so the per-claim request
        cap bounds a single page's model usage rather than a surface's.
        """
        claims: dict[str, list[dict]] = {}
        for surface, document in self.facts.items():
            audience = self.audience_for(surface)
            facts = document["facts"]
            chunks = [facts[index:index + self.facts_per_claim]
                      for index in range(0, len(facts), self.facts_per_claim)] or [[]]
            for number, chunk in enumerate(chunks, start=1):
                refs = extract.fact_refs(
                    {"facts": chunk},
                    _surface_evidence_ids(self.evidence, surface, chunk))
                claims.setdefault(audience, []).append({
                    "claim_id": f"{surface}:chunk-{number}",
                    "title": f"{surface} reference, part {number}",
                    "facts": refs,
                    "evidence_ids": [ref["evidence_id"] for ref in refs]
                    + [self.assertion_evidence.get(surface, "sha256:" + "0" * 64)],
                })
        return claims

    def apply_orphan_removal(self) -> list[str]:
        """Delete generated outputs that this run's generators do not claim.

        ADR-0001 treats an output with no producer as an error rather than a warning,
        and #1606 requires that the topic of a removed feature not survive its
        removal: a page that keeps rendering because nobody thought to delete it is
        how documentation ends up describing software that no longer exists. The
        deletion is reported rather than silent, because removing generated content
        is a decision a reviewer reads in the report.
        """
        _, orphans = self.plan_at_start
        produced = ({page["output"] for page in self.pages}
                    | {record["output"]
                       for record in self.sidecars._written.values()})
        for output in orphans:
            if output in produced:
                continue
            for path in (self.workspace.work / output,
                         self.workspace.work / manifests.sidecar_path(output)):
                try:
                    path.unlink()
                except OSError:
                    pass
            self.removed.append(output)
            self.warn(f"invalidation: removed {output}: no generator claims it")
        return self.removed

    # ----------------------------------------------------------------- coverage ---
    def measure_coverage(self) -> dict[str, dict]:
        """Covered/denominator per surface, by the definition the baseline names.

        ``covered`` counts facts whose exact name the run rendered into a page in
        the reference locale. Counting by name in the *output* rather than by
        "the generator claimed it" is the difference between a coverage number and
        a self-report: a page that dropped a fact because the model's prose about
        it was discarded does not count as covering it.
        """
        rendered = _rendered_text(self.workspace, "en")
        measured: dict[str, dict] = {}
        for surface in self.surfaces:
            document = self.facts.get(surface) or {"facts": [], "denominator": 0}
            entry = self.baseline["surfaces"][surface]
            covered = 0
            for fact in document["facts"]:
                if entry.get("match", "name") == "name" and fact["name"] in rendered:
                    covered += 1
                elif entry.get("match") == "path" and fact["sources"][0]["path"] \
                        in rendered:
                    covered += 1
            measured[surface] = {"covered": covered,
                                 "denominator": document["denominator"],
                                 "floor": entry["floor"],
                                 "report_only": bool(entry.get("report_only"))}
        return measured

    def generator_is_implemented(self, surface: str) -> bool:
        return not self.baseline["surfaces"][surface].get("external")

    # ----------------------------------------------------------------- artifacts ---
    def artifact_documents(self) -> dict[str, dict]:
        documents = {"evidence-store": self.evidence.as_document()}
        for surface, document in sorted(self.facts.items()):
            documents[f"facts/{surface}.json"] = document
        for output, record in self.sidecars._written.items():
            documents[f"manifests/{output}"] = record
        return documents

    def scan_for_secrets(self) -> list[str]:
        """Look for credential-shaped content in everything this run wrote.

        Two sweeps, because they catch different mistakes: the patterns catch a
        secret that arrived from outside (a tool's stderr echoed into an artifact),
        and the environment sweep catches the specific values this host happens to
        hold - which is the disclosure that would actually matter.
        """
        import re
        problems: list[str] = []
        import os
        values = [value for name, value in os.environ.items()
                  if workspace_lib.SECRET_NAME_RE.search(name)
                  and len(value) >= 8 and value != "0" and value != "1"]
        patterns = list(workspace_lib.SECRET_VALUE_RES)
        for rel in sorted(self.workspace.owned()):
            target = (self.workspace.work / rel)
            if not target.is_file():
                continue
            try:
                text = target.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                problems.append(f"{rel}: cannot be scanned ({exc})")
                continue
            for pattern in patterns:
                if pattern.search(text):
                    problems.append(f"{rel}: credential-shaped text matched "
                                    f"{pattern.pattern[:40]}")
                    break
            for value in values:
                if value in text:
                    problems.append(f"{rel}: carries the value of a credential "
                                    f"shaped environment variable")
                    break
        return problems

    # -------------------------------------------------------------------- report ---
    def provenance(self) -> dict:
        return {
            "schema": PROVENANCE_SCHEMA,
            "generator": contract.TOOL_VERSION,
            "run_id": self.run_id,
            "documented_commit": self.documented_commit,
            "version": self.version,
            "candidate_sha": self.release.get("candidate_sha"),
            "release_sha": self.release.get("release_sha"),
            "docs_manifest": self.docs_manifest,
            "toolchain": {"python": sys.version.split()[0],
                          "sphinx": "requested" if self.render else "not-requested",
                          "provider": self.provider_name,
                          "model": self.provider.model_id if self.provider else None},
            "source_digest": self.input_digest,
            "evidence_digest": self.evidence.digest(),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cost": self.ledger.as_dict(),
            "gate": self.gate.as_dict() if self.gate else None,
            "budgets": {name: entry["value"]
                        for name, entry in sorted(contract.BUDGETS.items())},
            "allowlisted_tools": sorted(contract.TOOL_ALLOWLIST),
            "withheld_env": sorted(self.tool_env_withheld),
        }

    def report(self) -> dict:
        rows = [{"name": row["name"], "status": row["status"],
                 "started_at": row["started_at"],
                 "finished_at": row["finished_at"],
                 "detail": row["detail"] or row["reason"] or "",
                 "reason": row["reason"] or "",
                 "checks": row["checks"]}
                for row in self.stages]
        return {
            "schema": contract.REPORT_SCHEMA,
            "run_id": self.run_id,
            "generator": contract.TOOL_VERSION,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "documented_commit": self.documented_commit,
            "version": self.version,
            "candidate_sha": self.release.get("candidate_sha"),
            "release_sha": self.release.get("release_sha"),
            "docs_manifest": self.docs_manifest,
            "provider": self.provider_name,
            "stages": rows,
            "summary": {
                "surfaces": {surface: self.facts[surface]["denominator"]
                             for surface in self.surfaces} if self.facts else {},
                "pages": len(self.pages),
                "evidence": self.evidence.counts(),
                "author": self.author.summary() if self.author else {},
                "invalidation": self.sidecars.as_dict(),
            },
            "gate": self.gate.as_dict() if self.gate else {
                "status": "skipped",
                "checks": [{"id": row["name"],
                            "status": "fail" if row["status"] in ("failed", "blocked")
                            else "skipped",
                            "detail": row["detail"]} for row in rows]},
            "warnings": self.warnings,
            "failures": self.failures,
            "cost": self.ledger.as_dict(),
            "would_publish": (self.gate is not None
                              and self.gate.status != "fail"
                              and self.blocked_reason is None),
        }

    def finish(self, exit_code: int) -> int:
        self.finished_at = self.workspace.stamp()
        try:
            report = self.report()
            # The report is the artifact the release gate reads, so it is checked
            # against its schema before it is written. A run that cannot answer with
            # a valid report has not run in any sense a gate can use, and exiting 0
            # on that would be the worst kind of green.
            contract.require_valid("report", report)
            self.workspace.write_json("report.json", report,
                                      base=self.workspace.work, kind="report")
            provenance = self.provenance()
            self.workspace.write_json("provenance.json", provenance,
                                      base=self.workspace.work, kind="provenance")
        except (GuardError, OSError, contract.ContractError) as exc:
            print(f"the run could not write its report: {exc}", file=sys.stderr)
            return contract.EXIT_CANNOT
        return exit_code


def _surface_evidence_ids(store: evidence_lib.EvidenceStore, surface: str,
                          chunk) -> list[str]:
    wanted = {f"{surface}:{fact['kind']}:{fact['name']}" for fact in chunk}
    return [record["id"] for record in store.records()
            if record["claim_id"] in wanted]


def _rendered_text(workspace, locale: str) -> str:
    base = workspace.generated / locale
    if not base.is_dir():
        return ""
    return "\n".join(path.read_text(encoding="utf-8", errors="replace")
                     for path in sorted(base.rglob("*.rst")))


# --------------------------------------------------------------------- stages ---
def stage_discover(run: Run) -> dict:
    """Enumerate the surfaces, digest the inputs, and ask the graph what is stale."""
    run.facts = {}
    for surface in run.surfaces:
        try:
            run.facts[surface] = extract.extract_surface(run.workspace, surface)
        except contract.ContractError as exc:
            raise StageError(f"surface {surface} produced facts the contract "
                             f"refuses: {exc}") from exc
        for warning in run.facts[surface].get("warnings", ()):
            run.warn(f"extract/{surface}: {warning}")
        if run.facts[surface]["denominator"] == 0:
            run.warn(f"surface {surface} discovered nothing: a zero denominator is "
                     f"usually the extractor and the tree disagreeing, not a "
                     f"software with no {surface}")
    run.input_digest = run.workspace.tree_digest(run.input_prefixes)
    # The invalidation plan is taken *here*, before any stage writes. Re-planning at
    # validate time compares sidecars against digests the run itself just moved - the
    # pages it wrote become "stale" by its own authorship, and the gate then fails a
    # run for doing its job. The plan is an input like any other: measured once,
    # reported once, and acted on below.
    run.plan_at_start = run.plan_invalidation()
    stale, orphans = run.plan_at_start
    denominators = {surface: document["denominator"]
                    for surface, document in run.facts.items()}
    return {"checks": {"denominators": denominators,
                       "input_digest": run.input_digest,
                       "stale": len(stale), "orphans": len(orphans)},
            "detail": (f"{sum(denominators.values())} fact(s) over "
                       f"{len(run.surfaces)} surface(s); {len(stale)} output(s) "
                       f"stale, {len(orphans)} with no producer")}


def stage_extract(run: Run) -> dict:
    """Write the facts documents and one ``extracted`` record per fact."""
    written = 0
    for surface, document in run.facts.items():
        rel = f"facts/{surface}.json"
        run.workspace.write_json(rel, document, base=run.workspace.work,
                                 kind="facts")
        run.write_sidecar(rel, contract.manifest_record(
            engine="extractor", output=rel,
            inputs=[{"kind": "facts",
                     "digest": extract.facts_digest(document)}],
            outputs=[f"facts/{surface}.json"],
            produced_by_=contract.produced_by("extractor"), run_id=run.run_id))
        written += 1
        for fact in document["facts"]:
            run.evidence.add_extracted(
                claim_id=f"{surface}:{fact['kind']}:{fact['name']}",
                audience=run.audience_for(surface), locale="en",
                sources=fact["sources"], run_id=run.run_id,
                generated_at=run.started_at)
    problems = run.evidence.verify_sources(run.workspace)
    if problems:
        raise StageError("the extraction's own provenance does not verify: "
                         + "; ".join(problems[:3]))
    return {"checks": {"documents": written,
                       "facts": sum(document["denominator"]
                                    for document in run.facts.values()),
                       "evidence": run.evidence.counts()},
            "detail": f"{written} facts document(s) and "
                      f"{run.evidence.counts()['records']} evidence record(s)"}


def stage_evidence(run: Run) -> dict:
    """Re-run each surface's extraction through the allowlisted tool.

    ADR-0001 section 4 makes an ``executed`` record the command, its exit code and
    the digest of what it printed. Recording the command the facts *claim* ran,
    rather than the command the code happened to call in process, is what lets a
    reviewer reproduce a fact from the artifact alone. Zero retries: extraction is
    deterministic, so a failure is a bug and retrying it hides it.
    """
    timings: dict[str, float] = {}
    for surface in run.surfaces:
        result = run.workspace.run_tool("docs-extract", {"surface": surface})
        run.tool_env_withheld.update(result.withheld_env)
        # Timing is deliberately *not* in the assertion. How long a command took is a
        # measurement of the runner, and the assertion's fields are content-addressed
        # into the record id that feeds the reuse key - an elapsed time in there makes
        # every rerun of an identical candidate a brand-new artifact, which is
        # exactly the false staleness #1606's clean-build comparison is there to
        # disprove. The number is still reported, as a stage check.
        timings[surface] = round(result.duration_s, 3)
        assertion = {
            "command": "python3 scripts/docs_extract.py --surface "
                       f"{surface} --json",
            "exit_code": result.exit_code,
            "stdout_sha256": contract.sha256_text(result.stdout),
            "stderr_sha256": contract.sha256_text(result.stderr),
            "at": run.documented_commit or run.input_digest or run.started_at}
        run.evidence.add_executed(
            claim_id=f"{surface}:assertion", audience=run.audience_for(surface),
            locale="en", assertion=assertion, run_id=run.run_id,
            generated_at=run.started_at)
        run.assertion_evidence[surface] = run.evidence.records()[-1]["id"]
        if result.exit_code != 0:
            raise StageError(
                f"the extraction command for {surface} exited {result.exit_code}"
                f"{' and timed out' if result.timed_out else ''}: "
                f"{(result.stderr or result.stdout)[-300:]}")
    problems = run.evidence.verify_assertions()
    if problems:
        raise StageError("; ".join(problems[:3]))
    return {"checks": {"executed": len(run.surfaces),
                       "withheld_env": sorted(run.tool_env_withheld),
                       "tool_durations_s": timings},
            "detail": f"{len(run.surfaces)} executed record(s); the child "
                      f"environment withheld {len(run.tool_env_withheld)} "
                      f"credential-shaped variable(s)"}


def stage_generate(run: Run) -> dict:
    """Write the narrative and the translation, over facts only."""
    run.provider = providers.build_adapter(run.provider_name,
                                           workspace=run.workspace,
                                           args=run.provider_args)
    healthy, detail = run.provider.healthcheck()
    if not healthy:
        raise StageError(f"the provider is not usable: {detail}")
    run.memory = author.load_memory(
        run.workspace.work / "i18n" / "translation_memory.json")
    stage = author.AuthorStage(run.workspace, adapter=run.provider,
                              ledger=run.ledger, memory=run.memory,
                              log=run.log)
    rows: list[dict] = []
    for audience, audience_claims in run.build_claims().items():
        rows.extend(stage.generate_audience(audience=audience,
                                            claims=audience_claims,
                                            locales=run.locales))
    run.author = stage
    pages = stage.write_pages(facts_by_surface=run.facts,
                              evidence_ids_by_claim=run.assertion_evidence,
                              run_id=run.run_id, evidence=run.evidence)
    for page in pages:
        # The page's inputs are the *store* digest, not one record id: the
        # provenance a generated output depends on is every extracted span its
        # facts cite plus the executed record behind them, which is exactly what
        # the store digests. A single record id would also make the sidecar depend
        # on a value that changes later in the same stage - the inferred record for
        # the page itself is added below - and a sidecar that is stale the moment it
        # is written invalidates the whole run on every rerun.
        inputs = [{"kind": "evidence", "digest": run.evidence.input_digest()},
                  {"kind": "generator",
                   "digest": manifests.digest_of("generator",
                                                 contract.TOOL_VERSION)},
                  {"kind": "locale",
                   "digest": manifests.digest_of("locale", page["locale"])}]
        if run.provider:
            inputs.append({"kind": "model",
                           "digest": manifests.digest_of(
                               "model", run.provider.model_id)})
        run.write_sidecar(page["output"], contract.manifest_record(
            engine="author", output=page["output"], inputs=inputs,
            outputs=[page["output"].replace(".rst", ".html")],
            produced_by_=contract.produced_by("author", run.provider.model_id,
                                              run.provider.name),
            run_id=run.run_id))
        # The prose a page carries needs its own record: kind inferred, model
        # named, text digested. Without it V-13 has nothing to resolve to.
        if page["status"] in ("generated", "cached"):
            run.evidence.add_inferred(
                claim_id=page["claim_id"], audience=page["audience"],
                locale=page["locale"], text=page["text"] if "text" in page else
                _read_page(run, page), model_id=run.provider.model_id,
                provider=run.provider.name, sources=_page_sources(
                    run.facts, page["claim_id"]), run_id=run.run_id,
                generated_at=run.started_at)
        elif page["status"] == "unsupported":
            run.evidence.add_unsupported(
                claim_id=page["claim_id"], audience=page["audience"],
                locale=page["locale"], reason=page.get("reason", ""),
                run_id=run.run_id, generated_at=run.started_at)
    run.pages = pages
    run.apply_orphan_removal()
    run.memory.save(run.workspace)
    summary = stage.summary()
    for row in rows:
        if row["status"] in ("unsupported", "failed"):
            run.warn(f"generate/{row['locale']}/{row['claim_id']}: {row['reason']}")
    counts = summary["by_status"]
    return {"checks": {"claims": len(rows), "pages": len(pages),
                       "cost": summary["cost"],
                       "translation_memory": summary["translation_memory"],
                       "per_locale": summary["per_locale"]},
            "detail": (f"{counts.get('generated', 0)} + "
                       f"{counts.get('cached', 0)} cached of {len(rows)} claim(s), "
                       f"{counts.get('unsupported', 0)} unsupported, "
                       f"{counts.get('failed', 0)} discarded by the gate; "
                       f"{summary['cost']['total_tokens']} token(s) of "
                       f"{summary['cost']['token_limit']}")}


def _read_page(run: Run, page: dict) -> str:
    try:
        return (run.workspace.work / page["output"]).read_text(encoding="utf-8")
    except OSError:
        return page["output"]


def _page_sources(facts_by_surface: dict, claim_id: str) -> list[dict]:
    surface = claim_id.split(":", 1)[0]
    document = facts_by_surface.get(surface) or {}
    sources: list[dict] = []
    for fact in document.get("facts", ()):
        sources.extend(fact["sources"])
    return sources[:50]


def stage_render(run: Run) -> dict:
    """Build the portal through the allowlisted tool, when asked to."""
    if not run.render:
        return {"status": "skipped",
                "reason": "render was not requested; the portal build is #1597's "
                          "job on ordinary changes (--render asks for it here)"}
    result = run.workspace.run_tool("sphinx", {
        "work": str(run.workspace.work / "doctrees"),
        "source": str(run.generated_source),
        "out": str(run.workspace.work / "portal")})
    run.tool_env_withheld.update(result.withheld_env)
    if result.exit_code != 0:
        raise StageError(f"the portal build exited {result.exit_code}"
                         f"{' after timing out' if result.timed_out else ''}: "
                         f"{(result.stderr or result.stdout)[-600:]}")
    pages = sorted(str(path.relative_to(run.workspace.work))
                   for path in (run.workspace.work / "portal").rglob("*.html"))
    return {"checks": {"pages": len(pages),
                       "duration_s": round(result.duration_s, 3),
                       "withheld_env": result.withheld_env},
            "detail": f"{len(pages)} HTML page(s) built in "
                      f"{result.duration_s:.1f}s"}


def stage_validate(run: Run) -> dict:
    """The gate: schemas, provenance, invalidation, redaction, budgets, coverage."""
    if not run.baseline:
        run.baseline = read_baseline()
    gate = Gate()
    for index, record in enumerate(run.evidence.records()):
        found = contract.errors(contract.validate("evidence", record))
        if found:
            gate.add(f"schema/evidence[{index}]", False, contract.issues_text(found))
    gate.add("schema/evidence store", True,
             f"{len(run.evidence.records())} record(s) validated individually")
    for name, document in run.artifact_documents().items():
        if name == "evidence-store":
            continue
        kind = "facts" if name.startswith("facts/") else "manifest"
        found = contract.errors(contract.validate(kind, document))
        gate.add(f"schema/{name}", not found, contract.issues_text(found))
    gate.add("every artifact id matches its content",
             not run.evidence.rejected, "; ".join(run.evidence.rejected[:3]))
    orphan_pages = [page["output"] for page in run.pages
                    if not page["inputs"]
                    or not any(input_["digest"].startswith("sha256:")
                               for input_ in page["inputs"])]
    gate.add("V-13 every rendered page resolves to an evidence record",
             not orphan_pages, ", ".join(orphan_pages[:5]))
    gate.add("every generated page has an inferred or unsupported evidence record",
             all(run.evidence.for_claim(page["claim_id"], page["locale"])
                 for page in run.pages),
             ", ".join(page["output"] for page in run.pages
                       if not run.evidence.for_claim(page["claim_id"],
                                                     page["locale"]))[:5])
    gate.add("V-14 every executed record exited 0 with a stdout digest",
             not run.evidence.verify_assertions(),
             "; ".join(run.evidence.verify_assertions()[:3]))
    stale_at_start, orphans_at_start = run.plan_at_start
    produced = {page["output"] for page in run.pages} | set(run.sidecars._written)
    unproduced = sorted(set(orphans_at_start) - set(run.removed) - produced)
    gate.add("V-10 no output without a producer", not unproduced,
             "still present with nothing to generate it: "
             + ", ".join(unproduced[:5]))
    unrepaired = sorted(output for output in stale_at_start if output not in produced)
    gate.add("V-10 every stale output was regenerated", not unrepaired,
             "stale at the start of the run and not written by it: "
             + ", ".join(unrepaired[:5]))
    leaked = run.scan_for_secrets()
    gate.add("no credential-shaped value reached an artifact", not leaked,
             ", ".join(leaked[:5]))
    gate.add("no credential path was read", not run.workspace.denied,
             ", ".join(f"{item} -> refused" for item in run.workspace.denied[:5]))
    if run.provider is not None and run.verify_provider:
        results = providers.adapter_contract_checks(lambda: run.provider)
        failed = [name for name, ok, _ in results if not ok]
        gate.add("V-15 the adapter passes the provider contract suite unchanged",
                 not failed, ", ".join(failed[:5]))
    else:
        gate.add("V-15 the adapter passes the provider contract suite unchanged",
                 "skipped: run `docs.py contract` or pass --verify-provider")
    coverage = run.measure_coverage()
    run.checks["coverage"] = coverage
    for surface in run.surfaces:
        row = coverage[surface]
        if row["report_only"]:
            gate.add(f"V-8 coverage of {surface} is reported, not enforced", True,
                     f"{row['covered']}/{row['denominator']} covered; the numerator "
                     f"needs evidence {row.get('owner', 'another issue')} owns")
            continue
        if row["denominator"] == 0 and run.baseline["surfaces"][surface].get(
                "requires_denominator", True):
            gate.add(f"coverage of {surface} has a denominator", False,
                     "the surface discovered nothing, so its floor cannot be "
                     "measured: a zero denominator is a red gate, not an easy pass")
            continue
        gate.add(f"coverage of {surface} >= floor {row['floor']}",
                 row["covered"] >= row["floor"],
                 f"{row['covered']}/{row['denominator']} covered, floor "
                 f"{row['floor']}")
        if row["covered"] > row["floor"]:
            run.warn(f"coverage of {surface} is {row['covered']}, above the "
                     f"committed floor {row['floor']}: raise "
                     f"scripts/docs_coverage_baseline.json in a pull request that "
                     f"names the surface - the gate never raises its own floor")
    if run.author:
        for locale in run.locales:
            rows = [row for row in run.author.outcomes if row["locale"] == locale]
            gate.add(f"locale {locale} produced claims", bool(rows),
                     "this locale produced nothing")
        per_locale = run.author.summary()["per_locale"]
        en = per_locale.get("en", {})
        de = per_locale.get("de", {})
        gate.add("V-12 DE coverage equals EN for generated surfaces",
                 de.get("generated", 0) + de.get("cached", 0)
                 >= en.get("generated", 0) + en.get("cached", 0),
                 f"en={en} de={de}")
    cost = run.ledger.as_dict()
    gate.add("the token budget held", cost["total_tokens"] <= cost["token_limit"],
             f"{cost['total_tokens']} of {cost['token_limit']}")
    gate.add("the per-claim request cap held",
             all(count <= cost["requests_per_claim_limit"]
                 for count in run.ledger.by_claim.values()),
             str(dict(list(run.ledger.by_claim.items())[:3])))
    # The wall clock is measured, not inferred from which budget stopped the ledger:
    # ``stopped_at`` names whichever bound was hit first, so reading it as "the
    # narrative wall clock" reported a per-claim or token stop as a timeout and
    # failed a run for a reason the report did not describe.
    gate.add("the narrative wall clock held",
             cost["elapsed_s"] <= cost["wall_clock_limit_s"],
             f"{cost['elapsed_s']}s of {cost['wall_clock_limit_s']}s")
    # A budget that stopped the whole ledger is a run that could not finish, whatever
    # the wall clock says. A per-claim stop is not: that is the cap doing its job on
    # one claim, whose absence the completeness check below reports.
    gate.add("no run-wide budget stopped the run",
             cost["stopped_at"] in (None, "model_requests_per_claim"),
             f"stopped at {cost['stopped_at']}")
    # Every claim the run planned must land as a page or as a named absence. This is
    # the mechanical form of "a discarded answer is never a silent gap": a claim the
    # gate discarded, or that ran out of its own budget, fails the run here rather
    # than publishing a page that quietly lost a section.
    if run.author is not None:
        rows = run.author.outcomes
        accounted = {"generated", "cached", "unsupported"}
        holes = sorted(f"{row['locale']}/{row['claim_id']} ({row['status']})"
                       for row in rows if row["status"] not in accounted)
        gate.add("every planned claim became a page or a named absence", not holes,
                 ", ".join(holes[:6]))
        missing_pages = sorted(
            f"{row['locale']}/{row['claim_id']}" for row in rows
            if row["status"] in ("generated", "cached")
            and not any(page["claim_id"] == row["claim_id"]
                        and page["locale"] == row["locale"] for page in run.pages))
        gate.add("every generated claim was written as a page", not missing_pages,
                 ", ".join(missing_pages[:6]))
    gate.add("the run names the revision it documents",
             bool(run.documented_commit) or run.allow_unknown_commit,
             "documented_commit is absent and --allow-unknown-commit was not "
             "given: an artifact that cannot say what it documents is not "
             "reviewable")
    gate.add("the run names the version it documents", bool(run.version),
             "VERSION could not be read")
    run.gate = gate
    return {"checks": {"gate": gate.status, "checks": len(gate.checks),
                       "failed": [row["id"] for row in gate.failed],
                       "skipped": [row["id"] for row in gate.skipped]},
            "detail": f"gate {gate.status}: {len(gate.failed)} failure(s) and "
                      f"{len(gate.skipped)} skipped of {len(gate.checks)} check(s)"}


def stage_publish(run: Run) -> dict:
    """Write the release bundle - or refuse, which is the half that matters.

    Two refusals, both fail-closed. The first is the important one: a run whose
    gate is not green writes nothing, so the previously published artifact stays
    byte-identical (V-17) and a reader of the artifact directory can tell that
    this candidate was refused by looking for a bundle that is not there. The
    second is immutability: a path that already carries a bundle for this
    ``docs_manifest`` is never overwritten, because an artifact that can be
    rewritten under its own name is not an artifact.
    """
    if run.gate is None or run.gate.status == "fail":
        failed = run.gate.failed if run.gate else []
        return {"status": "blocked",
                "reason": "the gate is not green, so nothing is published and the "
                          "previous artifact stands: "
                          + "; ".join(row["id"] for row in failed[:6])}
    if not run.release.get("candidate_sha") and not run.release.get("release_sha"):
        # Not a refusal. Publication is a release act, and an ordinary run over a
        # pull request candidate was never asked to publish: its deliverable is the
        # report and the artifact set. Returning ``blocked`` here would make every
        # non-release run exit non-zero, which teaches CI to ignore this stage's
        # verdict - and a stage whose verdict is ignored is not a gate.
        return {"status": "skipped",
                "reason": "publication is a release act: --candidate-sha or "
                          "--release-sha names the frozen revision this artifact "
                          "documents, and neither was given"}
    target = run.workspace.publish / run.docs_manifest
    if (target / "report.json").exists() and not run.overwrite:
        return {"status": "blocked",
                "reason": f"{target} already carries a bundle for this "
                          f"docs_manifest; a published path is immutable "
                          f"(--overwrite is for a scratch directory only)"}
    written: list[str] = []
    for relative, payload in run.artifact_documents().items():
        rel = f"{run.docs_manifest}/{_bundle_name(relative)}"
        _write_bundle(run, rel, json.dumps(payload, indent=2, sort_keys=True,
                                           ensure_ascii=False) + "\n")
        written.append(rel)
    for page in run.pages:
        try:
            body = (run.workspace.work / page["output"]).read_text(encoding="utf-8")
        except OSError as exc:
            raise StageError(f"{page['output']} cannot be read for the bundle: {exc}")
        rel = f"{run.docs_manifest}/{page['output']}"
        _write_bundle(run, rel, body)
        written.append(rel)
        sidecar = run.sidecars._written.get(page["output"])
        if sidecar:
            rel = f"{run.docs_manifest}/manifests/{page['output']}"
            _write_bundle(run, rel, json.dumps(sidecar, indent=2, sort_keys=True,
                                               ensure_ascii=False) + "\n")
            written.append(rel)
    _write_bundle(run, f"{run.docs_manifest}/report.json",
                  json.dumps(run.report(), indent=2, sort_keys=True,
                             ensure_ascii=False) + "\n")
    written.append(f"{run.docs_manifest}/report.json")
    _write_bundle(run, f"{run.docs_manifest}/provenance.json",
                  json.dumps(run.provenance(), indent=2, sort_keys=True,
                             ensure_ascii=False) + "\n")
    written.append(f"{run.docs_manifest}/provenance.json")
    return {"checks": {"artifacts": len(written),
                       "docs_manifest": run.docs_manifest,
                       "target": str(target)},
            "detail": f"{len(written)} artifact(s) written under {target}"}


def _write_bundle(run: Run, rel: str, text: str) -> None:
    target = run.workspace.claim_for_write(rel, run.workspace.publish)
    target.write_text(workspace_lib.scrub_text(text), encoding="utf-8")


def _bundle_name(relative: str) -> str:
    if relative == "evidence-store":
        return "evidence/store.json"
    return relative


class Gate:
    """One row per assertion, and a status that never counts a skip as a pass."""

    def __init__(self):
        self.checks: list[dict] = []

    def add(self, check_id: str, ok, detail: str = "") -> bool:
        if isinstance(ok, str):
            status, ok, detail = "skipped", None, ok
        else:
            status = "pass" if ok else "fail"
        self.checks.append({"id": check_id, "status": status,
                            "detail": workspace_lib.scrub_text(detail)[:2000]})
        return bool(ok)

    @property
    def failed(self) -> list[dict]:
        return [row for row in self.checks if row["status"] == "fail"]

    @property
    def skipped(self) -> list[dict]:
        return [row for row in self.checks if row["status"] == "skipped"]

    @property
    def status(self) -> str:
        if self.failed:
            return "fail"
        if self.skipped:
            return "skipped"
        return "pass"

    def as_dict(self) -> dict:
        return {"status": self.status, "checks": self.checks}


SURFACE_AUDIENCE = {
    "resources": "integrator", "models": "developer", "relations": "developer",
    "settings": "administrator", "commands": "operator", "tasks": "operator",
    "services": "operator", "features": "cataloguer",
}

STAGES = {
    "discover": stage_discover,
    "extract": stage_extract,
    "evidence": stage_evidence,
    "generate": stage_generate,
    "render": stage_render,
    "validate": stage_validate,
    "publish": stage_publish,
}


def read_baseline(path: Path = BASELINE_FILE) -> dict:
    """The committed coverage floors.

    A missing or malformed baseline is a hard stop. A gate with no floors is a gate
    that passes everything, so a pipeline whose gate can be removed by deleting one
    file has no gate - the same reasoning that makes the release tools refuse a
    missing baseline.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise StageError(f"{path.name} cannot be read: {exc}") from exc
    except ValueError as exc:
        raise StageError(f"{path.name} is not JSON: {exc}") from exc
    surfaces = document.get("surfaces")
    if not isinstance(surfaces, dict):
        raise StageError(f"{path.name} has no surfaces object")
    for surface in contract.SURFACES:
        entry = surfaces.get(surface)
        if not isinstance(entry, dict):
            raise StageError(f"{path.name} has no entry for surface {surface!r}")
        if not isinstance(entry.get("floor"), int) or entry["floor"] < 0:
            raise StageError(f"{path.name}: surface {surface!r} needs a "
                             "non-negative integer floor")
        if not entry.get("denominator"):
            raise StageError(f"{path.name}: surface {surface!r} must name the "
                             "discovered denominator it measures against")
    extra = sorted(set(surfaces) - set(contract.SURFACES))
    if extra:
        raise StageError(f"{path.name} names surfaces the contract does not know: "
                         f"{', '.join(extra)}")
    return document


# --------------------------------------------------------------------- command ---
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="docs.py", description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def common(target):
        target.add_argument("--root", default=".",
                            help="the tree under documentation (default: cwd)")
        target.add_argument("--workdir", default=None,
                            help="scratch root for artifacts (default: "
                                 "<root>/.mrmap-docs-work)")
        target.add_argument("--publish-dir", default=None,
                            help="where a release bundle may be written")
        target.add_argument("--surfaces", nargs="*", choices=list(contract.SURFACES),
                            default=list(contract.SURFACES))
        target.add_argument("--locales", nargs="*", choices=list(contract.LOCALES),
                            default=list(contract.LOCALES))
        target.add_argument("--provider", default="fake",
                            choices=sorted(providers.ADAPTERS))
        target.add_argument("--model-id", default=None)
        target.add_argument("--provider-argv", nargs="*", default=None,
                            help="argv of the command provider's binary")
        target.add_argument("--provider-url", default=None,
                            help="https endpoint of the http provider")
        target.add_argument("--provider-token-env",
                            default="MRMAP_DOCS_MODEL_TOKEN")
        target.add_argument("--script", default="prose",
                            choices=("prose", "refuse", "empty", "garbage",
                                     "uncited", "invented"),
                            help="scripted behaviour of the fake provider")
        target.add_argument("--facts-per-claim", type=int, default=FACTS_PER_CLAIM)
        target.add_argument("--budget", action="append", default=[],
                            metavar="NAME=VALUE",
                            help="tighten one contract budget (a run may lower a "
                                 "bound, never raise it)")
        target.add_argument("--tool-timeout", type=float, default=None)
        target.add_argument("--now", default=None,
                            help="pin generated_at, for a reproducible artifact")
        target.add_argument("--python", default=None,
                            help="interpreter the allowlisted tools run with")
        target.add_argument("--verbose", action="store_true")

    run_parser = sub.add_parser("run", help="run the whole pipeline")
    common(run_parser)
    run_parser.add_argument("--stages", nargs="*", choices=list(contract.STAGES),
                            default=list(contract.STAGES))
    run_parser.add_argument("--render", action="store_true",
                            help="ask the allowlisted sphinx entry to build")
    run_parser.add_argument("--verify-provider", action="store_true",
                            help="run the V-15 contract suite as a gate check")
    run_parser.add_argument("--candidate-sha", default=None)
    run_parser.add_argument("--release-sha", default=None)
    run_parser.add_argument("--allow-unknown-commit", action="store_true")
    run_parser.add_argument("--overwrite", action="store_true")
    run_parser.add_argument("--json", action="store_true",
                            help="print report.json instead of a summary")

    for name, help_text in (
            ("extract", "extract one surface's facts"),
            ("evidence", "inspect or verify an evidence store"),
            ("contract", "run the provider contract suite for one adapter (V-15)"),
            ("manifests", "report the invalidation graph of a workdir")):
        target = sub.add_parser(name, help=help_text)
        common(target)
        if name == "extract":
            target.add_argument("--surface", default="all",
                                choices=["all", *contract.SURFACES])
            target.add_argument("--json", action="store_true")
        if name == "evidence":
            target.add_argument("--store", default=None)
            target.add_argument("--verify", action="store_true")
        if name == "contract":
            target.add_argument("--json", action="store_true")
    return parser


def provider_args_from(args) -> dict:
    model = args.model_id or ("mrmap-docs-model/fake-1"
                             if args.provider == "fake"
                             else "mrmap-docs-model/configured")
    return {"model_id": model, "script": args.script, "argv": args.provider_argv,
            "url": args.provider_url, "token_env": args.provider_token_env}


def budget_overrides_from(pairs: list[str]) -> dict:
    overrides: dict = {}
    for pair in pairs:
        if "=" not in pair:
            raise StageError(f"--budget wants NAME=VALUE, got {pair!r}")
        name, _, value = pair.partition("=")
        name = name.strip()
        if name not in contract.BUDGETS:
            raise StageError(f"--budget: unknown budget {name!r}; the contract "
                             f"knows {', '.join(sorted(contract.BUDGETS))}")
        try:
            number = float(value)
        except ValueError:
            raise StageError(f"--budget: {name} wants a number, got {value!r}") \
                from None
        original = contract.BUDGETS[name]["value"]
        if isinstance(original, int) and not isinstance(original, float):
            number = int(number)
        if number < 0:
            raise StageError(f"--budget: {name} cannot be negative")
        overrides[name] = number
    return overrides


def make_run(args, command: str) -> Run:
    root = Path(args.root).resolve()
    if not root.is_dir():
        raise StageError(f"--root {root} is not a directory")
    workdir = Path(args.workdir).resolve() if args.workdir \
        else root / ".mrmap-docs-work"
    publish = Path(args.publish_dir).resolve() if args.publish_dir \
        else workdir / "publish"
    for directory in (workdir, publish):
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.is_dir():
            raise StageError(f"{directory} is not a directory")
    return Run(root=root, workdir=workdir, publish=publish,
               surfaces=tuple(args.surfaces), provider_name=args.provider,
               provider_args=provider_args_from(args),
               locales=tuple(args.locales), render=getattr(args, "render", False),
               verify_provider=getattr(args, "verify_provider", False),
               release={"candidate_sha": getattr(args, "candidate_sha", None),
                        "release_sha": getattr(args, "release_sha", None)},
               budget_overrides=budget_overrides_from(args.budget),
               facts_per_claim=args.facts_per_claim,
               allow_unknown_commit=getattr(args, "allow_unknown_commit", False),
               overwrite=getattr(args, "overwrite", False), now=args.now,
               python=args.python, tool_timeout=args.tool_timeout,
               verbose=args.verbose)


def cmd_run(args) -> int:
    run = make_run(args, "run")
    run.baseline = read_baseline()
    stages = tuple(args.stages) or contract.STAGES
    ordered = tuple(name for name in contract.STAGES if name in set(stages))
    exit_code = run.run_stages(ordered)
    report = run.report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for row in report["stages"]:
            mark = {"ok": "ok   ", "failed": "FAIL ", "skipped": "skip ",
                    "blocked": "block", "not_run": "never"}.get(row["status"], "?   ")
            print(f"{mark}  {row['name']:<10} {row['detail']}")
        gate = report["gate"]
        passed = sum(1 for c in gate["checks"] if c["status"] == "pass")
        failed = sum(1 for c in gate["checks"] if c["status"] == "fail")
        skipped = sum(1 for c in gate["checks"] if c["status"] == "skipped")
        print(f"\ngate {gate['status']}: {passed} pass, {failed} fail, "
              f"{skipped} skipped of {len(gate['checks'])} check(s)")
        for failure in report["failures"]:
            print(f"failure: {failure}")
        for warning in report["warnings"][:20]:
            print(f"warning: {warning}")
        print(f"\nrun {report['run_id']}  manifest {report['docs_manifest'][:19]}  "
              f"commit {str(report['documented_commit'])[:12]}  "
              f"version {report['version']}")
        print(f"artifacts: {run.workspace.work}")
    return exit_code


def cmd_extract(args) -> int:
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work",
                                        python=args.python,
                                        clock=workspace_lib.Clock(args.now))
    if args.surface == "all":
        payload = extract.extract_all(workspace, tuple(args.surfaces))
    else:
        payload = extract.extract_surface(workspace, args.surface)
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    return contract.EXIT_OK


def cmd_evidence(args) -> int:
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work")
    store_path = Path(args.store) if args.store \
        else workspace.work / evidence_lib.STORE_REL
    try:
        store = evidence_lib.EvidenceStore.load(store_path, workspace)
    except (OSError, ValueError, contract.ContractError) as exc:
        print(f"the evidence store at {store_path} is not readable: {exc}",
              file=sys.stderr)
        return contract.EXIT_CANNOT
    print(json.dumps(store.counts(), indent=2, sort_keys=True))
    if args.verify:
        problems = store.verify_sources(workspace) + store.verify_assertions()
        for problem in problems:
            print(f"FAIL  {problem}")
        total = len(store.ids())
        print(f"{total - len(problems)}/{total} record(s) verified")
        return contract.EXIT_FAIL if problems else contract.EXIT_OK
    return contract.EXIT_OK


def cmd_contract(args) -> int:
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work",
                                        python=args.python)
    status, results = providers.run_contract_suite(
        args.provider, workspace=workspace, args=provider_args_from(args))
    if args.json:
        print(json.dumps([{"check": name, "ok": ok, "detail": detail}
                          for name, ok, detail in results], indent=2))
    else:
        for name, ok, detail in results:
            print(f"{'PASS' if ok else 'FAIL'}  {name}"
                  + (f"  [{detail[:200]}]" if detail and not ok else ""))
        passed = sum(1 for _, ok, _ in results if ok)
        print(f"\n{passed}/{len(results)} contract checks passed for "
              f"{args.provider} ({provider_args_from(args)['model_id']})")
    return status


def cmd_manifests(args) -> int:
    run = make_run(args, "manifests")
    run.baseline = read_baseline()
    stale, orphans = run.plan_invalidation()
    print(json.dumps({"stale": stale, "orphans": orphans,
                      "graph": run.sidecars.as_dict()}, indent=2, sort_keys=True))
    return contract.EXIT_OK


COMMANDS = {"run": cmd_run, "extract": cmd_extract, "evidence": cmd_evidence,
            "contract": cmd_contract, "manifests": cmd_manifests}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except StageError as exc:
        print(f"docs: {workspace_lib.scrub_text(str(exc))}", file=sys.stderr)
        return contract.EXIT_CANNOT
    except providers.AdapterPolicyError as exc:
        print(f"docs: the provider is not usable: "
              f"{workspace_lib.scrub_text(str(exc))}", file=sys.stderr)
        return contract.EXIT_CANNOT
    except GuardError as exc:
        print(f"docs: refused by the boundary: "
              f"{workspace_lib.scrub_text(str(exc))}", file=sys.stderr)
        return contract.EXIT_CANNOT
    except contract.ContractError as exc:
        print(f"docs: the contract refused: "
              f"{workspace_lib.scrub_text(str(exc))}", file=sys.stderr)
        return contract.EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
