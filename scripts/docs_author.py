#!/usr/bin/env python3
"""The author stage: the only place in the pipeline that produces prose (#1598).

ADR-0001 section 1 gives this stage one job - write the narrative that connects
verified facts - and takes away every way it could do that badly. The code below is
those constraints, in the order a request travels through them:

1. **Facts are the entire input.** A claim is built from extracted facts plus their
   evidence digests. Nothing else enters a prompt: not a file's content, not a
   fetched document, not a page's text. Whatever a hostile README says, it reaches
   a model as a digest at most.
2. **The response is gated, not trusted.** Every citation must name a fact the
   request carried, the prose may not name an identifier no fact carries, and text
   without a citation is not prose - it is nothing. A failed gate discards the
   response in full, never in part: a paragraph with one un-evidenced sentence is
   still a paragraph with one un-evidenced sentence.
3. **Budgets bind the stage.** A per-run token cap, a per-claim request cap and a
   wall-clock cap, each with the consequence the ADR names. When the cap is reached
   the stage stops generating and the partial output is discarded rather than
   published - "we ran out of budget" is a report, "we published half" is a
   defect.
4. **Retries are bounded and logged.** Two retries of a failing claim, with the
   reason of each attempt recorded. A deterministic stage gets zero retries by
   contract, so this is the only place in the pipeline a retry exists at all.
5. **A refusal is an outcome.** ``insufficient_evidence`` and friends become an
   *unsupported topic* row naming what is missing, which is the behaviour ADR-0001
   calls the most important in the record: a stub and a confident paragraph look
   the same to a reader.
6. **German is generated from the facts**, not from the English paragraph, so a
   mistranslated fact fails the same citation check an English one does; and an
   unchanged claim keeps its previously accepted sentence through the translation
   memory instead of being rewritten every release.

Two more rules are enforced here rather than in the provider layer because they are
about publishing, not about calling: ``inferred`` text is published only with its
evidence record and its citation list, and a claim whose evidence has not been
produced is not generated over at all.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS)) if str(SCRIPTS) not in sys.path else None

import docs_contract as contract  # noqa: E402
import docs_providers as providers  # noqa: E402
import docs_workspace as workspace_lib  # noqa: E402

#: The generated marker ADR-0001 section 3 requires on every section, so a reader
#: can filter the portal by role and the coverage table has a per-audience
#: denominator. Kept as a comment so it is invisible to a reader and obvious to a
#: machine - the alternative, a visible line, gets copied and drifts.
AUDIENCE_MARKER = ".. mrmap-audience: {audience} locale={locale} claims={claims}"
PROVENANCE_MARKER = ".. mrmap-evidence: run={run_id} pages={pages}"

STYLE_PROFILES = {
    "developer": providers.DEFAULT_STYLE_PROFILE,
    "administrator": {**providers.DEFAULT_STYLE_PROFILE,
                      "voice": "imperative for steps, indicative for explanations",
                      "must_name_only_cited_facts": True},
    "operator": {**providers.DEFAULT_STYLE_PROFILE,
                 "voice": "imperative for runbook steps"},
    "integrator": {**providers.DEFAULT_STYLE_PROFILE,
                   "voice": "indicative; name endpoints and operations exactly"},
    "cataloguer": {**providers.DEFAULT_STYLE_PROFILE,
                   "voice": "indicative; name the screen the user is on"},
}


class BudgetExceeded(RuntimeError):
    """A budget bound was reached. Never a pass, never a partial publication."""

    def __init__(self, budget: str, value, limit):
        super().__init__(f"{budget} reached {value} of {limit}: "
                         f"{contract.BUDGETS[budget]['on_breach']}")
        self.budget = budget
        self.value = value
        self.limit = limit


class CostLedger:
    """The token and request ledger of one run, with the caps that stop it.

    Raised on the call that would breach a cap, not after it: the difference is
    whether the over-budget text exists anywhere. On breach the caller discards the
    claim and the run fails closed, so the tokens that were already spent are the
    only cost and the partial output is not published.
    """

    def __init__(self, overrides: dict | None = None):
        self.overrides = dict(overrides or {})
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.requests = 0
        self.retries = 0
        self.started = time.monotonic()
        self.by_claim: dict[str, int] = {}
        self.stopped: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def remaining_tokens(self) -> int:
        return self.limit("model_tokens_total") - self.total_tokens

    def limit(self, name: str):
        return contract.budget(name, self.overrides)

    def authorize(self, claim_id: str) -> None:
        """Ask to make one more request for ``claim_id``."""
        if self.stopped:
            raise BudgetExceeded(self.stopped, self.total_tokens,
                                 self.limit(self.stopped))
        spent = self.by_claim.get(claim_id, 0)
        if spent >= self.limit("model_requests_per_claim"):
            raise BudgetExceeded("model_requests_per_claim", spent,
                                 self.limit("model_requests_per_claim"))
        elapsed = time.monotonic() - self.started
        if elapsed >= self.limit("wall_clock_narrative_s"):
            raise BudgetExceeded("wall_clock_narrative_s", round(elapsed, 1),
                                 self.limit("wall_clock_narrative_s"))
        self.by_claim[claim_id] = spent + 1
        self.requests += 1

    def record(self, usage: dict) -> None:
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        if self.total_tokens > self.limit("model_tokens_total"):
            self.stopped = "model_tokens_total"

    def as_dict(self, *, reproducible: bool = False) -> dict:
        """The ledger as recorded output.

        ``reproducible`` drops the one field a second run cannot reproduce - the
        wall clock the generator itself spent - so the field can appear in the
        transcript without making the release artifact unreproducible.
        """
        record = {"requests": self.requests, "retries": self.retries,
                  "prompt_tokens": self.prompt_tokens,
                  "completion_tokens": self.completion_tokens,
                  "total_tokens": self.total_tokens,
                  "token_limit": self.limit("model_tokens_total"),
                  "requests_per_claim_limit": self.limit("model_requests_per_claim"),
                  "wall_clock_limit_s": self.limit("wall_clock_narrative_s"),
                  "stopped_at": self.stopped}
        if not reproducible:
            record["elapsed_s"] = round(time.monotonic() - self.started, 3)
        return record


class TranslationMemory:
    """Accepted sentences keyed by (claim digest, locale).

    The practical form of "preserve prior verified content incrementally": a claim
    whose facts are unchanged keeps its sentence across releases, so a mature corpus
    is not rewritten by every build and a model swap regenerates rather than mixes
    two models' prose on one page.
    """

    def __init__(self, entries: dict | None = None):
        self.entries = dict(entries or {})
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(claim_id: str, locale: str, facts, model_id: str) -> str:
        return contract.sha256_obj({"claim_id": claim_id, "locale": locale,
                                    "facts": facts, "model_id": model_id})

    def get(self, key: str) -> dict | None:
        found = self.entries.get(key)
        if found:
            self.hits += 1
        else:
            self.misses += 1
        return found

    def put(self, key: str, entry: dict) -> None:
        self.entries[key] = entry

    def as_dict(self) -> dict:
        return {"entries": self.entries, "hits": self.hits, "misses": self.misses}

    def save(self, workspace) -> None:
        workspace.write_json("i18n/translation_memory.json", self.as_dict(),
                             kind="i18n")


def page_body(*, claim_id: str, audience: str, locale: str, title: str,
              text: str, citations, facts, run_id: str, unsupported=None) -> str:
    """The reStructuredText body of one generated page.

    The evidence and audience markers sit at the top as comments, the prose follows,
    and the citations are rendered as a visible list - so a reader can see which
    sentences a model wrote and which facts stand under them. Where a claim cannot
    be evidenced, the page says so by naming what is missing: the stub is the
    deliverable, not a placeholder for one.
    """
    lines = [AUDIENCE_MARKER.format(audience=audience, locale=locale, claims=1),
             PROVENANCE_MARKER.format(run_id=run_id, pages=1),
             "", title, "=" * len(title), ""]
    if unsupported:
        lines += [".. warning:: Topic not yet documented", "",
                  f"   {unsupported}", ""]
    if text:
        lines += [text.strip(), ""]
    if citations:
        lines += ["Evidence", "-" * len("Evidence"), ""]
        by_id = {fact["id"]: fact for fact in facts}
        for citation in citations:
            fact = by_id.get(citation)
            if fact is None:
                continue
            source = fact.get("evidence_id", "unknown")
            lines.append(f"* ``{fact['name']}`` ({fact['surface']}/{fact['kind']})"
                         f" - evidence ``{source}``")
        lines.append("")
    return "\n".join(lines)


class AuthorStage:
    """Generate narrative and translation over extracted facts."""

    def __init__(self, workspace, *, adapter, ledger=None, memory=None,
                 budget_overrides=None, log=None):
        self.workspace = workspace
        self.adapter = adapter
        self.ledger = ledger or CostLedger(budget_overrides)
        self.memory = memory or TranslationMemory()
        self.log = log or (lambda *a: None)
        self.outcomes: list[dict] = []
        self.unsupported: list[dict] = []

    # ------------------------------------------------------------------ claims ---
    def claim(self, *, claim_id: str, title: str, audience: str, locale: str,
              facts, evidence_ids, kind: str = "narrative") -> dict:
        """Write one claim. Returns an outcome row; never raises for a bad model.

        The three terminal states are the only ones the report can carry:
        ``generated`` (text plus citations plus an evidence record),
        ``unsupported`` (a refusal or an exhausted budget, with the reason named),
        and ``failed`` (the provider was unreachable at all). The distinction
        between the last two matters: a model that declines one topic is information,
        a model that is down fails the run closed.
        """
        if not facts:
            row = self._unsupported(claim_id, audience, locale,
                                    "no extracted facts: nothing may be claimed "
                                    "about this topic")
            return row
        request = providers.build_request(
            claim_id=claim_id, kind=kind, audience=audience, locale=locale,
            facts=facts, evidence_refs=list(evidence_ids),
            style_profile=STYLE_PROFILES.get(audience,
                                             providers.DEFAULT_STYLE_PROFILE),
            budget={"max_tokens": self.ledger.remaining_tokens(),
                    "max_requests_per_claim":
                        self.ledger.limit("model_requests_per_claim")})
        key = TranslationMemory.key(claim_id, locale, request["facts"],
                                   self.adapter.model_id)
        cached = self.memory.get(key)
        if cached:
            row = {"claim_id": claim_id, "title": title, "audience": audience,
                   "locale": locale,
                   "status": "cached", "text": cached["text"],
                   "citations": cached["citations"], "attempts": 0,
                   "model_id": cached["model_id"], "usage": {"prompt_tokens": 0,
                                                             "completion_tokens": 0}}
            self.outcomes.append(row)
            return row

        attempts = 0
        last_detail = ""
        max_attempts = self.ledger.limit("retries_model") + 1
        while attempts < max_attempts:
            attempts += 1
            try:
                self.ledger.authorize(claim_id)
            except BudgetExceeded as exc:
                self.ledger.stopped = self.ledger.stopped or exc.budget
                row = self._unsupported(claim_id, audience, locale,
                                        f"budget exhausted before this claim could "
                                        f"be generated: {exc}")
                row["attempts"] = attempts - 1
                row["status"] = "unsupported"
                return row
            try:
                response = self.adapter.generate(request)
            except providers.ProviderError as exc:
                last_detail = str(exc)
                if attempts < max_attempts:
                    self.ledger.retries += 1
                    self.log("retry", claim_id, f"attempt {attempts} failed: "
                                                f"{last_detail}")
                    time.sleep(self.ledger.limit("retry_backoff_s"))
                    continue
                raise providers.ProviderError(last_detail) from None
            issues = providers.validate_response(response, request)
            if not issues:
                if response["refusal_reason"] is not None:
                    row = self._unsupported(
                        claim_id, audience, locale,
                        f"the model declined this topic "
                        f"({response['refusal_reason']}): the stub names it rather "
                        "than guessing")
                    row["attempts"] = attempts
                    return row
                self.ledger.record(response["usage"])
                self.memory.put(key, {"text": response["text"],
                                      "citations": response["cited_fact_ids"],
                                      "model_id": response["model_id"]})
                row = {"claim_id": claim_id, "title": title,
                       "audience": audience, "locale": locale,
                       "status": "generated", "text": response["text"],
                       "citations": response["cited_fact_ids"],
                       "attempts": attempts, "model_id": response["model_id"],
                       "usage": dict(response["usage"])}
                self.outcomes.append(row)
                return row
            # A gated response is discarded in full. Retrying a malformed answer is
            # allowed inside the per-claim cap, because a provider that truncated
            # one response usually answers the next; retrying an invented claim is
            # how a hallucination eventually gets through, so the reason is logged
            # every time and the claim still fails when the cap is reached.
            last_detail = contract.issues_text(issues)
            self.log("gate", claim_id, f"attempt {attempts} discarded: {last_detail}")
            if any("names identifiers" in issue.message
                   or "did not carry" in issue.message for issue in issues):
                row = self._unsupported(claim_id, audience, locale,
                                        f"the model's answer was discarded by the "
                                        f"fact-citation gate: {last_detail}")
                row["attempts"] = attempts
                row["status"] = "failed"
                return row
            if attempts >= max_attempts:
                break
            self.ledger.retries += 1
            time.sleep(self.ledger.limit("retry_backoff_s"))
        row = self._unsupported(claim_id, audience, locale,
                                f"every attempt was discarded by the gate: "
                                f"{last_detail}")
        row["status"] = "failed"
        # The attempt count travels with the failure: a report that says a claim was
        # discarded without saying it was tried three times reads as one bad answer,
        # and the retries are the part a reviewer audits against the retry budget.
        row["attempts"] = attempts
        return row

    def generate_audience(self, *, audience: str, claims, locales=contract.LOCALES):
        """Generate one audience's claims in every locale.

        Locales are generated from the same facts, in the same run, so per-locale
        coverage is comparable and an English-only regeneration cannot pass on a
        green aggregate (V-12).
        """
        rows = []
        for claim in claims:
            for locale in locales:
                rows.append(self.claim(
                    claim_id=claim["claim_id"], title=claim["title"],
                    audience=audience, locale=locale, facts=claim["facts"],
                    evidence_ids=claim["evidence_ids"],
                    kind="translation" if locale != "en" else "narrative"))
        return rows

    def _unsupported(self, claim_id: str, audience: str, locale: str,
                     reason: str) -> dict:
        row = {"claim_id": claim_id, "audience": audience, "locale": locale,
               "status": "unsupported", "text": "", "citations": [],
               "attempts": 0, "reason": workspace_lib.scrub_text(reason),
               "title": ""}
        self.outcomes.append(row)
        self.unsupported.append({"claim_id": claim_id, "audience": audience,
                                 "locale": locale, "reason": row["reason"]})
        return row

    # ------------------------------------------------------------------ report ---
    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for row in self.outcomes:
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        per_locale: dict[str, dict[str, int]] = {}
        for row in self.outcomes:
            bucket = per_locale.setdefault(row["locale"], {})
            bucket[row["status"]] = bucket.get(row["status"], 0) + 1
        return {"claims": len(self.outcomes), "by_status": counts,
                "per_locale": per_locale, "unsupported": len(self.unsupported),
                "cost": self.ledger.as_dict(),
                "translation_memory": {"hits": self.memory.hits,
                                       "misses": self.memory.misses}}

    def write_pages(self, *, facts_by_surface, evidence_ids_by_claim,
                    run_id: str, evidence=None) -> list[dict]:
        """Write the generated pages and their sidecars. Returns the page rows.

        ``evidence`` is the run's store, consulted so the page's citation list
        names the id of the record that stands under each fact. A page that cited
        nothing but the fact's name would tell a reader the fact was evidenced
        without letting them look it up, which is provenance as decoration.
        """
        pages = []
        for row in self.outcomes:
            if row["status"] not in ("generated", "cached", "unsupported"):
                continue
            facts = _facts_for(row["claim_id"], facts_by_surface, evidence)
            body = page_body(claim_id=row["claim_id"], audience=row["audience"],
                             locale=row["locale"],
                             title=row.get("title")
                             or row["claim_id"].replace(":", " ").replace(
                                 "_", " ").title(),
                             text=row["text"], citations=row["citations"],
                             facts=facts, run_id=run_id,
                             unsupported=row.get("reason"))
            rel = (f"generated/{row['locale']}/{row['audience']}/"
                   f"{_slug(row['claim_id'])}.rst")
            self.workspace.write_text(rel, body, base=self.workspace.work,
                                      kind="page")
            pages.append({"output": rel, "claim_id": row["claim_id"],
                          "title": row.get("title", ""),
                          "audience": row["audience"], "locale": row["locale"],
                          "status": row["status"], "reason": row.get("reason"),
                          "text": row["text"], "citations": row["citations"],
                          "inputs": [{"kind": "evidence",
                                      "digest": evidence_ids_by_claim.get(
                                          row["claim_id"],
                                          contract.sha256_text(row["claim_id"]))}],
                          "digest": contract.sha256_text(body)})
        return pages


def _slug(claim_id: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in claim_id).lower()


def _facts_for(claim_id: str, facts_by_surface: dict, evidence=None) -> list[dict]:
    """The facts a page may cite, each carrying the id of its evidence record.

    The lookup is by claim id, which is what the extractor and the evidence stage
    both build from ``(surface, kind, name)`` - so a page's citation resolves to the
    record whose sources are the very span the fact came from, without a second
    mapping somebody has to keep in sync.
    """
    surface = claim_id.split(":", 1)[0]
    document = facts_by_surface.get(surface) or {}
    refs = []
    for fact in document.get("facts", ()):
        claim = f"{fact['surface']}:{fact['kind']}:{fact['name']}"
        evidence_id = ""
        if evidence is not None:
            records = [record for record in evidence.for_claim(claim)
                       if record["kind"] == "extracted"]
            if records:
                evidence_id = records[0]["id"]
        refs.append({"id": fact.get("id") or f"{claim}",
                     "surface": fact["surface"], "kind": fact["kind"],
                     "name": fact["name"], "fields": fact.get("fields", []),
                     "evidence_id": evidence_id})
    return refs


def load_memory(path: Path) -> TranslationMemory:
    """Read a previous run's translation memory, if there is one.

    Absent or unreadable is not an error: an empty memory regenerates everything,
    which costs tokens and changes wording, never publishes a lie.
    """
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return TranslationMemory()
    entries = document.get("entries") if isinstance(document, dict) else None
    return TranslationMemory(entries if isinstance(entries, dict) else {})


def main(argv=None) -> int:  # pragma: no cover - the CLI is scripts/docs.py
    parser = __import__("argparse").ArgumentParser(prog="docs_author.py")
    parser.add_argument("--root", default=".")
    parser.add_argument("--provider", default="fake")
    parser.add_argument("--provider-argv", nargs="*")
    parser.add_argument("--model-id", default="mrmap-docs-model/fake-1")
    parser.add_argument("--surface", default="resources")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    workspace = workspace_lib.Workspace(root=root, work=root / ".mrmap-docs-work")
    workspace.allow_writes_under(workspace.work, workspace.publish,
                                 workspace.generated)
    import docs_extract as extract  # local import: extraction is the caller's input
    document = extract.extract_surface(workspace, args.surface)
    facts = [contract.fact_ref(surface=args.surface, kind=fact["kind"],
                               name=fact["name"], fields=fact.get("fields", ()),
                               evidence_id="sha256:" + "0" * 64)
             for fact in document["facts"][:3]]
    adapter = providers.build_adapter(
        args.provider, workspace=workspace,
        args={"model_id": args.model_id, "argv": args.provider_argv})
    stage = AuthorStage(workspace, adapter=adapter)
    rows = stage.generate_audience(
        audience="integrator",
        claims=[{"claim_id": f"{args.surface}:generated",
                 "title": args.surface.title(), "facts": facts,
                 "evidence_ids": [ref["evidence_id"] for ref in facts]}])
    pages = stage.write_pages(facts_by_surface={args.surface: document},
                              evidence_ids_by_claim={},
                              run_id="cli")
    print(json.dumps({"rows": rows, "pages": pages, "summary": stage.summary()},
                     indent=2, sort_keys=True))
    return contract.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
