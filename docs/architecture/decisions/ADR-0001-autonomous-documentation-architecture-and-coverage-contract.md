# ADR-0001: Autonomous documentation architecture and coverage contract

- **Status:** Proposed
- **Date:** 2026-11-21
- **Issue:** #1596 (epic #1589)
- **Measurement anchor:** `664ceeef2` on `develop`. Every number in this record
  was produced by the commands in Appendix A at that commit and is reproducible.
  Re-checked at `a72f40552`: the surface denominators are unchanged except
  `.rst` files (58 to 59), words (107 833 to 109 935) and settings (158 to 162
  unique names), all of which move simply because `develop` grew a page and four
  settings since the anchor. The warning profile is identical at both.

## Context

MrMap documents itself by hand. `docs/source` holds 58 reStructuredText files,
14 images and roughly 107 800 words, written over five years. Two further sets of
Markdown sit outside the built corpus and are invisible in the portal: 8 design
notes totalling 1 633 lines under `docs/`, and 2 files totalling 690 lines
*inside* `docs/source` itself (`administration/authentication.md`,
`administration/permissions.md`) which Sphinx cannot read at all, because
`conf.py` loads only `sphinx.ext.autodoc`, `sphinx_rtd_theme` and
`sphinx_multiversion` and no Markdown parser.
Publishing runs `docs/publish_docs.sh`, a 2021 script that force-pushes the
build onto the `gh-pages` branch.

Epic #1589 wants documentation that no human authors or maintains: derived from
source and from running instances, complete for every audience, in English and
German, versioned per release, and published only as part of a release. This
record is the architecture and the coverage contract that the rest of the epic
is built against. It decides the shape of the system and the rules that make
"autonomous" defensible rather than a slogan.

Three constraints make this a design problem and not a tooling exercise.

First, the facts must come from the software. A documentation agent that reads a
Python file and writes prose about it has produced a second, unauditable
description of the code that will drift exactly as fast as the code. The only
defensible division of labour is deterministic extraction for anything the
source already states, and generated prose only for narrative that connects
verified facts.

Second, the epic forbids the usual escape hatches. No manifest that a human
maintains, because a manifest is hand-maintained documentation wearing a
different hat. No full documentation build on ordinary pull requests, because
that puts a multi-minute browser-and-model job in the way of every change.
Those two rules remove both of the ways this is normally kept honest, so the
contract has to supply a replacement for each.

Third, an agent that can write documentation can also invent it. The failure
mode to design against is not a crashed build, it is a confident paragraph
about a feature that does not exist, published under the project's name.

### What is actually there today

Measured at the anchor commit, all by the commands in Appendix A.

| Thing | Value | How it was measured |
| --- | --- | --- |
| Sphinx sources | 58 `.rst` files, 67 labelled sections, 107 833 words | walk of `docs/source` |
| Images in docs | 14 files | walk of `docs/source` |
| Markdown outside the build | 8 files / 1 633 lines in `docs/*.md`, plus 2 files / 690 lines under `docs/source` | walk of `docs/`; `conf.py` registers no Markdown parser |
| Registered frontend resources | 72 | `name:` entries of `frontend/src/components/Resource/Definition.tsx` |
| Resources named anywhere in docs | 47 (65 %) | identifier search over `docs/**` |
| Resources with no mention at all | 25 | complement of the above |
| Django model classes | 55 | `models.py` of each app |
| Model relations (FK/O2O/M2M) | 178 | same walk |
| Documentable settings | 158 | uppercase assignments in `MrMap/settings.py` |
| Management commands | 9 | `*/management/commands/*.py` |
| Celery task definitions | 35 | task decorators in `*/tasks/` |
| Compose services | 11 base / 12 dev | service keys of each compose file |
| Behave feature files | 97 | walk of `tests/behave/features/` |
| `automodule`/`autoclass` directives | 5, in 4 files | grep over `docs/source` |
| Cold HTML build | 8 s wall clock, 61 HTML pages, exit 0 | compatible Sphinx in a container, stubbed `conf.py` imports |
| Sphinx warnings on that build | 22 | counted from the build log |

The 25 unmentioned resources are not an accident of taste, they are a
representative sample of what hand-keeping misses: every historical resource
(`HistoricalWebMapService`, `HistoricalDatasetMetadataRecord`,
`HistoricalServiceMetadataRecord`), every update setting
(`WebMapServiceUpdateSetting`, `WebFeatureServiceUpdateSetting`,
`CatalogueServiceUpdateSetting`), the operation URL records, `MetadataContact`,
`TimeExtent`, `Licence`, `ReferenceSystem` and the monitoring probe records.
These are precisely the resources the API answers and an administrator has to
reason about.

### The build does not currently build

This is the most important line in the baseline and it is easy to miss because
nothing runs it. `backend/.requirements/docs.txt` pins `Sphinx==4.5.0` together
with `sphinxcontrib-applehelp==2.0.0`, `sphinxcontrib-devhelp==2.0.0`,
`sphinxcontrib-htmlhelp==2.1.0`, `sphinxcontrib-qthelp==2.0.0` and
`sphinxcontrib-serializinghtml==2.0.0`. Those five packages all require Sphinx
5.0 or newer. With the committed pins, a build aborts immediately:

```
Sphinx version error:
The sphinxcontrib.applehelp extension used by this project needs at least
Sphinx v5.0; it therefore cannot be built with this version.
```

Pinned to the compatible versions instead, the same tree builds in 8 seconds and
answers 61 HTML pages with 22 warnings. So the documentation pipeline is not
"slow" or "thin", it is **red and nobody sees it**, because per the epic and per
current CI no job builds the docs on an ordinary change. That is the strongest
possible argument for the coverage gate in this record, and the strongest
argument that the gate must be run by something other than a human noticing.

What the log shows, besides the pin conflict:

- 5 of the 22 warnings are `autodoc: failed to import module` for
  `registry.models.service`, `registry.models.security`,
  `registry.managers.service`, `registry.proxy.wms_proxy` and
  `registry.proxy.wfs_proxy`. Those files are the API-reference layer of the
  docs, they reference the modules that were reorganised during the registry
  split, and they have been failing silently.
- `docs/source/development/collecting-vocabulary.rst` is cited by name from
  `background-operations.rst` but sits in no toctree, so Sphinx reports it as a
  document that isn't included in any toctree. It is written and unreachable.
- The remaining warnings are plain markup faults that any docs CI job would
  have caught years ago: `Title underline too short` in
  `vscode-configuration.rst`, `Title overline too short` in five pages that use an
  overlined section title, `Pygments lexer name 'env' is not known` in two code
  blocks, an unterminated inline literal in
  `metadata-transform-inventory.rst`, and a block quote ending without a blank
  line in `compose-profiles.rst`. Sphinx counts 22 in total because it reports a
  doctree fault once per pass.
- The gap the log *cannot* show is `docs/source/administration/`: two Markdown
  files totalling 690 lines sit inside the source tree, are matched by no
  `source_suffix` and parsed by nothing, so the authentication and permissions
  guidance exists in the repository and is absent from the portal without a
  single warning. This is the exact failure mode section 11 exists to make
  visible, and it is why an input with no consumer must be a gate failure
  (section 5) rather than a silence.

Neither is fixed here. This record is a contract; #1597 owns the build.

## Decision

### 1. Two engines, one output, with a hard line between them

Documentation generation is split at the line between **what the source states**
and **what it means**.

- The **extractor** is deterministic code. It parses the repository and a
  running instance and emits structured facts: resources, fields, filters,
  permissions, settings, management commands, Celery tasks, compose services,
  model relations, OpenAPI operations. No model, no prose, no judgement.
  Given the same input tree it emits byte-identical output.
- The **author** is a language model. It receives verified facts plus existing
  verified prose and writes narrative: tutorials, the reasoning behind a
  setting, the order in which an administrator should do things. It may not
  introduce an identifier that the extractor did not emit.

Everything downstream of that line is rendering. Sphinx renders the same
reStructuredText tree whether each sentence came from a human or the author,
which is what makes the epic an increment rather than a rewrite.

**A fact that cannot be extracted is not a fact.** It is either a claim the
author must cite evidence for, or it is not published.

### 2. The coverage contract replaces the manifest

The epic forbids a hand-maintained manifest. This is what stands in its place.

**Coverage is a measured relation between two sets that the code already
defines.** The denominator is never curated: it is the set of entities the
software actually exposes, discovered from source. For each surface the
denominator is named in the gate's configuration, never in a list of topics.

| Surface | Denominator (discovered, not curated) | Numerator (a unit counts as covered when…) |
| --- | --- | --- |
| API resources | every `name:` in `Resource/Definition.tsx`, ∪ every JSON:API `resource_type` in the OpenAPI schema | a page states the resource purpose **and** the generator finds that page's field list identical to the schema's |
| Model relations | every `ForeignKey`, `OneToOneField`, `ManyToManyField` in `backend/*/models*` | rendered in the generated ERD of its app |
| Settings | every module-level uppercase assignment in `MrMap/settings.py` | named in the configuration reference with its default and its effect |
| Management commands | every `*/management/commands/*.py` | named in the operations reference with its help text and one example |
| Celery tasks | every task decorator in the app's `tasks/` | named in the background-operations reference |
| Compose services | every service key of each committed compose file | named in the deployment reference |
| User workflows | every Behave feature file under `tests/behave/features/` | a Playwright scenario asserts the steps of that feature |
| Frontend screens | every route reachable from `Definition.tsx` menu options | has at least one generated screenshot with a passing assertion |

**Coverage is a floor, not a target.** The gate is `coverage >= the committed
baseline`, and the baseline may only move upward, in a pull request that also
names the surface it improved. That rule is what makes "autonomous" safe: a
generator that silently loses a section cannot pass, because the floor it must
clear was raised when the section was gained. A drop is a release blocker.

**Coverage is enforced where a surface can change, not everywhere.** The gate
runs on the release path (section 5) and as a *targeted* check in the pull
request that changes the discovered set, identified by the extractor's own diff.
Adding a resource to `Definition.tsx` makes the target surface grow, so the
check runs. Editing a view body does not, so it does not. This is targeted, not
full, documentation CI and stays inside the epic's no-routine-latency rule.

### 3. Audience taxonomy is derived from the software's own roles

Audiences are not invented for the docs; they are the roles MrMap already
enforces, so the set cannot drift from the product.

| Audience | Derived from | Primary content |
| --- | --- | --- |
| **Cataloguer** | the editor permissions of the registry and metadata aggregates | how to register, edit, harvest and share a service or record |
| **Administrator** | superuser-only endpoints, management commands, settings, monitoring | install, configure, operate, diagnose, upgrade |
| **Integrator** | public API, `/csw`, OWS endpoints, security proxy | API reference, OGC interfaces, proxy and auth configuration |
| **Developer** | source layout, tests, `AGENTS.md`, task SQL guards | architecture, contributor guide, generated UML/ERD |
| **Operator** | compose files, release lifecycle, promotion scripts | deployment topologies, release operation, runbooks |

Two rules follow. An audience has no section if the software has no role to
anchor it — a section is created by the discovery step finding evidence for it,
not by an editor deciding to write one. And every section declares its audience
in a generated marker, so a reader can filter the portal by role, and so the
coverage table above has a stable per-audience denominator. The existing
`docs/source` tree already groups along these lines
(`introduction`, `installation`, `system_architecture`, `usage`,
`administration`, `development`, `models`, `managers`, `modules`), so the
taxonomy maps onto the portal rather than replacing it.

### 4. Evidence is the unit of trust

Every generated statement carries machine-readable provenance, and prose
without provenance is not rendered. Evidence is a JSON object emitted beside the
page, not embedded in prose.

```json
{
  "schema": "mrmap.docs.evidence.v1",
  "id": "sha256:…",
  "claim": "registry.models.service.WebMapService",
  "kind": "extracted",
  "sources": [
    {"path": "backend/registry/models/service.py",
     "span": [41, 96], "blob": "sha256:…"}
  ],
  "assertion": {
    "command": "python3 scripts/docs_extract.py --surface models --json",
    "exit_code": 0, "stdout_sha256": "…", "at": "664ceeef2"
  },
  "produced_by": {"engine": "extractor", "generator": "mrmap-docs/1.0.0",
                   "model": null},
  "reviewed": null
}
```

Fields that carry weight:

- `kind` ∈ `extracted` | `executed` | `inferred` | `human`. `extracted` proves a
  statement against a file span; `executed` proves it against a command that ran
  and exited 0, with the recorded output digest; `inferred` marks prose the
  author wrote over extracted facts — always rendered, never as a factual
  claim; `human` marks the pre-epic corpus, grandfathered with
  `reviewed.legacy: true` and a link to the commit that wrote it.
- `sources[].blob` is a git blob SHA, not a line count. A line number rots the
  moment an unrelated edit lands above it; a blob SHA says "verified against
  exactly this content", which is the only assertion worth keeping.
- `assertion` is what makes a screenshot, a command, or an API example
  trustworthy: the exact command, its exit code, and the digest of what it
  printed. A tutorial step without an `executed` record is labelled
  `unverified` in the portal and excluded from the coverage numerator.
- `model` is `null` for `extracted` and `executed`. It is set only for
  `inferred`. This is how a reader and a reviewer can see which sentences a
  model wrote.
- `reviewed` names the person and pull request that accepted an `inferred` claim
  as durable. Nothing requires review to publish; review is what promotes a
  claim so later runs preserve it verbatim instead of rewriting it.

The evidence store is committed on the release branch, not on `develop`. It is
part of the release artifact set (section 6), which satisfies both the
no-manifest rule and the immutability rule from the epic.

### 5. Source-to-output invalidation is a content-addressed graph, not a manifest

A manifest is a hand-written mapping from source to page. A dependency graph is
computed, and recomputing it costs nothing.

Every generated file records, in a sidecar, the digests it was computed from:

```
generated/docs/api/resources/webmapservice.rst.manifest.json
  { "engine": "…", "inputs": [
      {"kind": "schema",   "digest": "sha256:…"},   # the OpenAPI document
      {"kind": "source",   "digest": "sha256:…"},   # Definition.tsx blob
      {"kind": "evidence", "digest": "sha256:…"} ],
    "outputs": ["api/resources/webmapservice.html"] }
```

Invalidation is then a set difference. Recompute the input digests for a
candidate tree; any sidecar whose inputs changed is regenerated; any page whose
sidecar no longer has a producer is deleted, because its subject was removed
from the software. Nothing decides staleness by timestamp, and nothing is kept
merely because it was there before.

The graph is layered so that an edit invalidates as little as possible:

```
source tree ─┬─► facts (extractor, per surface)         ─┐
             ├─► structural diagrams (deterministic)     ├─► rendered rst ─► HTML
running stack┤                                           │
             └─► executed evidence (demo + Playwright) ──┴─► narrative (author)
```

Facts are the chokepoint: one digest per surface. A one-line change to a
serializer invalidates one surface digest, one page, and the narrative
paragraphs that cite it. A change to a Dockerfile invalidates the deployment
reference and nothing else. Measured cost of the full render at the anchor
commit is **8 s** for 61 pages, so the expensive edges are exclusively the
browser and the model, which is exactly where the budgets of section 8 belong.

**Orphans are an error, not a warning.** `collecting-vocabulary.rst` is in no
toctree today; the gate treats an output with no producer and an input with no
consumer as a failure, which is how the current gap and every future one gets
caught by a machine.

### 6. Release candidate identity is the #1577 promotion identity, unchanged

The docs must be attributable to one exact revision, and there is already one
authority for that: the release promotion path of #1577
(`.github/workflows/release-promotion.yml` as reconciled by #1798,
`scripts/release_gates.py`, the `release-stable` environment). Documentation
does not mint its own identity.

A documentation run is parameterised by the same tuple #1577 already produces:

| Field | Source | Pinned by this record |
| --- | --- | --- |
| `version` | root `VERSION`, projected by the release tooling | yes — the same value as the release |
| `candidate_sha` | the merge commit of the reviewed release pull request, as `verify` reports it | yes — the documented revision of a develop preview |
| `release_sha` | the master commit the tag points at | yes — for stable publication |
| `artifact_digests` | CI uploads of the tests/Sonar/dependency jobs | consumed, not recomputed |
| `docs_manifest` | `sha256` over (version, tree, dependency lockfiles, locales, generator version, model id, evidence store digest) | yes |

`docs_manifest` is the reuse key. The #1577 promotion attestation gains one
field naming it; a candidate may reuse a documentation artifact only when that
digest matches, so a locale edit, a `package-lock.json` change or a generator
bump all force regeneration, and a rerun of an identical candidate costs
nothing. This is the compatibility with #1577 the epic asks for: **the docs gate
is one more attested artifact in an existing attestation, and one more
promotion gate in an existing gate list** — not a parallel release process.

Because #1577 has not yet shipped its callable contract, this record fixes the
interface and leaves the wiring to #1609. Until then no gate here blocks a
release, which is the negative-case dry run the epic's definition of done names.

### 7. Artifact and cache schema

Two stores with different lifetimes, both content-addressed.

```
docs-artifact/v1/<docs_manifest>/
  portal/            rendered HTML, the publishable tree
  evidence/          the evidence store of section 4
  facts/             extractor output per surface
  manifests/         invalidation sidecars
  diagrams/          ERD, UML, dependency graphs (source + SVG/PNG)
  screenshots/       Playwright PNGs + their executed evidence
  i18n/              per-locale generated rst and the translation memory
  provenance.json    version, candidate_sha, release_sha, generator, model,
                     timings, cost, gate report
  report.json        coverage table vs baseline, warnings, failures
```

Rules that make this usable as a cache and as a legal record:

- `portal/` is **immutable once published**, keyed by `<docs_manifest>`. Nothing
  overwrites a published path. This is what allows retention of history and is
  the property the force-push model of the retired `publish_docs.sh` could not
  offer (see section 12 for who provides it now).
- `report.json` is the artifact the gate reads. A build that "succeeded" but
  whose report shows a coverage regression is a failed build.
- Model output is cached under `sha256(prompt, model_id, model_parameters,
  input_facts_digest)` and reused only on an exact match. A cache miss caused by
  a model swap regenerates rather than mixing two models' prose within one page.
- Intermediates are retained as CI artifacts for the project's retention window;
  only the release artifact set is retained permanently, which is what makes
  "reproducible" a claim rather than a hope.
- Logs written into `provenance.json` are **redacted**: no environment values,
  no request headers, no connection strings. The stack used for evidence holds
  development credentials only (section 11), so the redaction is defence in
  depth, not the primary control.

### 8. Bounded cost, concurrency, retries, and the model interface

Every bound is a number with an owner and a named consequence when exceeded.
An unbounded autonomous system is not autonomous, it is unattended.

| Bound | Value | On breach |
| --- | --- | --- |
| Wall clock per release candidate | 30 min extraction + render, 60 min browser + narrative | run fails closed, prior publication stands |
| Model tokens per release candidate | hard cap from config, sized for a full regeneration | generation stops at the boundary, partial output is discarded, never published |
| Model requests per claim | 3 | claim fails, `inferred` text is dropped, `extracted` text survives |
| Browser scenarios | one worker, scenario timeout 90 s | scenario fails, its workflow is reported uncovered |
| Concurrency | extraction 4-way (per surface), render 1, browser 1 (determinism requires it) | not tunable per run |
| Retries | extractor 0, render 0, model 2 with backoff, browser 1 | each retry is logged with its reason; a silent retry is a defect |
| Isolated worker | CPU- and memory-capped container, no network except the model endpoint and the local stack | refusing to run uncapped is a gate failure |

Extraction and render get **zero** retries deliberately: they are deterministic,
so a failure is a bug and retrying it hides it. Only the two non-deterministic
edges retry, and only within their own budgets.

### 9. Provider-agnostic agent interface

The author talks to one narrow interface. Nothing else in the system knows a
model exists.

```
DocumentAgent
  generate(request) -> response
    request:  {claim_id, kind, audience, locale, facts[], evidence_refs[],
               prior_prose?, style_profile, budget}
    response: {text, cited_fact_ids[], model_id, usage, refusal_reason?}
```

Four rules make the interface load-bearing rather than cosmetic:

- The adapter must report `model_id` and `usage`. An adapter that cannot report
  them cannot be used, because section 4's provenance and section 8's budget
  both depend on those fields. This is the real portability test, not whether a
  second vendor's SDK compiles.
- Every `cited_fact_ids[]` entry must exist in `facts[]`. A response citing an
  unknown fact is discarded in full. This is the mechanical form of "no invented
  features" and it is adapter-independent.
- A refusal is a valid response. With `refusal_reason` set and no text, the
  topic is reported **unsupported** (section 11) rather than guessed at.
- Adding a vendor is adding an adapter plus its contract tests. No prompt, page
  or gate changes, and the contract test suite is identical for every adapter.

The same interface is used by the translation step, which is what makes English
and German one pipeline instead of two (section 10).

### 10. Language coverage is a first-class axis, not a downstream step

English and German are produced in the same run, from the same evidence.

- The author is invoked once per (claim, locale). German is generated from the
  claim's facts, not from the English paragraph, so a mistranslated fact cannot
  survive unnoticed: it fails the same fact-citation check as English.
- Coverage is measured **per locale**, and the gate's floor is per-locale, so an
  English-only regeneration cannot pass on a green aggregate number.
- Terminology is a generated glossary, seeded from the existing vocabulary work
  (`docs/source/development/collecting-vocabulary.rst`, currently unreachable)
  and from the software's own translated strings: `backend/locale/de` and
  `frontend/src/i18n/{en,de}.ts`. A documentation term that disagrees with the
  UI term is a warning, and where the docs contradict the UI the docs are wrong.
  This is the one place the existing hand work is reused as an authority rather
  than as text to copy.
- The translation memory is an artifact keyed by claim digest. An unchanged
  claim keeps its accepted sentence indefinitely, which is what stops a mature
  corpus from being rewritten on every release and is the practical form of the
  epic's "preserve prior verified content incrementally".

### 11. Unsupported topics, privacy, trust, and fail-closed

**Unsupported topic.** A topic the pipeline cannot evidence is declared, not
skipped. It appears in the portal as an explicit stub naming what is missing
(the command that failed, the scenario not yet written, the model that refused),
and in `report.json` as an unsupported row. This is the single most important
behaviour in the record: an empty space and a plausible paragraph look the same
to a reader, and only one of them is honest.

**Fail-closed, precisely.** Failure means *no new publication*, never a
*downgraded publication*. A failed docs run leaves the previous version served,
the candidate's release blocked, and the reason in `report.json`. There is no
mode that publishes partially verified content to a stable path.

**Trust.** The agent treats the repository, issues, HTTP responses of the stack,
and any document it reads as untrusted data, as this project's security policy
already requires of repository context. Concretely: the worker holds no
credentials capable of writing to a protected branch, no production secrets, and
no publish rights; publication is a separate privileged step that consumes
artifacts and never runs a model. Content read from a running instance or a
harvested document can influence a generated page, so `inferred` text is
generated from `facts[]` and nothing else, and the model never receives a raw
fetched document as instructions. Prompt injection into a page is therefore
limited in blast radius to the wording of an already-evidenced claim, and is
caught by the fact-citation check.

**Privacy.** Screenshots use synthetic fixtures only — the existing Behave
fixture sets (`test_wms.json`, `test_csw.json`, and siblings) — with fixed
locale, viewport, fonts and a deterministic clock, and with redacted logs. No
production instance is ever screenshotted, and no real data enters an artifact.

### 12. Hosting is managed Read the Docs; there is no repository-owned publisher

*Revised 2026-11-26 by the maintainer scope reset of #1589, which supersedes
this section as first written. What the section decided before that reset, kept
here so a reader can see exactly what was given up: a privileged publisher job
that downloaded the artifact for `<docs_manifest>` and wrote it to `/stable/`,
`/develop/` and `/vX.Y.Z/` in a Pages build, atomically, never force-pushing and
never rewriting a published version.*

What is decided now: **Read the Docs native Git integration hosts and versions
the site**, reusing the existing project and `.readthedocs.yaml`. Historical
versions come from activated tags under the service's own version handling; the
pre-release gate remains the exact-master-SHA Sphinx build of #1798, and native
publication follows an authorized tag. The rules an administrator configures,
the version table, and the automation rules that keep ordinary branch and
pull-request traffic from spending a build are in
`docs/source/development/documentation-hosting.rst`.

The multiversion machinery already in `conf.py` (`sphinx_multiversion`, with the
tag selection described by `scripts/release_lifecycle.json`) stays, because the
docs image at `docker/docs/entrypoint.sh` is a separate consumer that calls
`sphinx-multiversion` directly and needs it. That is one selection read by two
consumers, not two publishers.

**A repository-owned publisher, artifact archive or Pages workflow is out of
scope and must not be reintroduced without prior explicit maintainer approval
and a demonstrated upstream gap** (#1589, 2026-11-26). If the service
provably cannot serve the minimum needs, the fallback is the *official* GitHub
Actions artifact-upload and Pages-deploy actions for the latest stable only —
never a custom archive layout, and never a dual publisher.

`docs/publish_docs.sh` is deleted with #1608. It was a 2021 script that
`git push --force`d a freshly built tree onto `gh-pages`; under the contract
above it has no role to keep, because the version identity, the retention and
the build queue are all the service's.

Historical content is preserved by construction: the pre-epic corpus enters as
`kind: human` evidence, the existing `docs/source` tree keeps its paths and
therefore its anchors and labels (`_documenting_metadata` and the section labels
the root toctree lists), and the coverage floor only ever grows. No page is
deleted because a generator dislikes it — a page is deleted only when the
invalidation graph proves its subject is gone from the software. Prefix-level
URL moves of the previously published site are answered by **native redirects**
in the service, not by a publisher keeping old paths alive.

### 13. No production publish from this record

This record ships no publish job, no Pages write, no model call, and no gate
wired to a release. It ships the contract and the measurements that make it
checkable. #1610 performs the end-to-end negative-case dry run; activation
happens in an approved integration pull request.

## Validation

The record is validated by re-running its own baseline. Each row is a
machine-checkable assertion, not a review judgement. `scripts/docs_coverage.py`
(#1597) implements them; the Appendix A commands are the reference behaviour it
must reproduce until it exists.

| ID | Assertion | Enforcement |
| --- | --- | --- |
| V-1 | Every registered frontend resource appears in a page whose field list equals the schema's. Baseline: 47/72 (65 %). Floor = last accepted value. | gate, release + surface-change PR |
| V-2 | Every `models.Model` subclass is in its app's ERD. Baseline: 55 classes. | gate |
| V-3 | Every relation (FK/O2O/M2M) is rendered in the ERD of its app. Baseline: 178 relations. | gate |
| V-4 | Every uppercase setting in `MrMap/settings.py` is documented. Baseline: 158 settings. | gate |
| V-5 | Every management command is documented. Baseline: 9. | gate |
| V-6 | Every Celery task definition is documented. Baseline: 35. | gate |
| V-7 | Every compose service of every committed compose file is documented. Baseline: 11 base / 12 dev. | gate |
| V-8 | Every Behave feature file maps to at least one browser scenario. Baseline: 97 features, 0 scenarios. | report as unsupported until #1602 |
| V-9 | Zero Sphinx `autodoc: failed to import module` warnings. Baseline: **5 (red)**. | gate, red until #1597 |
| V-10 | Zero orphan pages: no `.rst` outside a toctree, no output without a producer. Baseline: **1 (red)** — `development/collecting-vocabulary.rst`. | gate, red until #1597 |
| V-11 | `sphinx-build -b html -W` succeeds on the committed `docs.txt`. Baseline: **fails in 1 s (red)** on the Sphinx 4.5.0 / `sphinxcontrib-*` 2.x conflict. | gate, red until #1597 |
| V-12 | Per-locale coverage of DE equals EN for every generated surface. Baseline: no generated DE. | gate from #1603 |
| V-13 | Every rendered page resolves to an evidence record; zero pages without provenance. | gate |
| V-14 | Every `executed` evidence record has `exit_code: 0` and a reproducible `stdout_sha256`. | gate |
| V-15 | The model adapter contract test suite passes unchanged against every configured adapter. | CI on generator changes |
| V-16 | Full render of the pre-epic tree stays under the 30 min budget. Baseline: **8 s, 61 pages, 22 warnings**. | gate |
| V-17 | `report.json` of a failed run leaves the previously published version byte-identical (negative-case dry run). | #1610 |
| V-18 | Zero files under `docs/source` that no builder can consume. Baseline: **2 (red)** — the two Markdown files in `administration/`. | gate, red until #1597 |

Four of these are **red at the anchor commit** (V-9, V-10, V-11, V-18). That is
intentional and is the deliverable's sharpest result: the contract is written
tight enough that the current pipeline fails it, which is the only way an
autonomous system improves rather than merely re-renders.

## Consequences

**Enables.** Coverage becomes a number that moves, so regressions are detectable
without a reader noticing an omission. The invalidation graph makes an 8-second
render the only deterministic cost, concentrating all budget and all risk in the
two non-deterministic edges where the budgets of section 8 apply. Because Sphinx
consumes generated reStructuredText, the existing tree, its labels and its URLs
survive untouched, and #1597 can land without a migration of prose. The #1577
interface means the release process gains a gate rather than a fork.

**Costs.** Four things are now mandatory that a weaker contract would have
skipped: the evidence store must be written before any autonomous prose is
trustworthy, so #1598 cannot start from the epic's prose requirements alone.
Every coverage floor added by this record is a permanent obligation on later
generators, and V-1 through V-8 are large denominators — 178 relations, 158
settings — that must be met by extraction rather than by lowering the metric.
Retiring the manifest idea means the invalidation graph must be correct in its
first version, because there is no hand-written fallback to consult when it is
not. And the two red gates mean #1597 carries a documentation-build repair in
addition to its own scope.

**Deliberate trade-offs.** V-8 is reported-unsupported rather than enforced,
because browser scenarios are #1602's work and an enforced floor nobody can
raise is a lie. Model output is not review-gated before publication, because the
epic forbids a human authoring obligation; the compensation is fact-citation
mechanics plus per-locale coverage floors, and the accepted residual risk is
mis-worded prose over correct facts, which is why `reviewed` promotes rather than
permits. `inferred` text is published without review at all.

## Implementation

| Record | Owns |
| --- | --- |
| #1597 | Sphinx portal, `docs.txt` repair (V-11), autodoc repair (V-9), toctree repair (V-10), the render layer |
| #1595 | generator repository layout and `scripts/docs_*.py` entry points |
| #1598 | agent runtime, the `DocumentAgent` adapter and its contract tests (V-15), budgets (section 8) |
| #1599, #1600 | structural extraction (V-2, V-3) and reference extraction (V-4 … V-7) |
| #1601, #1602 | deterministic demo stack, Playwright evidence (V-8, V-14) |
| #1603, #1604, #1605 | audience sections, per-locale generation (V-12), behavioural evidence |
| #1606, #1607 | invalidation graph (section 5), coverage gate and bounded repair (V-1 … V-16) |
| #1608, #1609 | managed Read the Docs hosting and its configuration, replacing the retired `publish_docs.sh`; #1577 wiring |
| #1610 | end-to-end validation including the negative-case dry run (V-17) |

## Appendix A — Reproducing the baseline

Run from the repository root at the anchor commit. No container is needed except
where stated; nothing here writes to the repository.

```bash
# Sphinx corpus
find docs/source -name '*.rst' | wc -l                       # 58
find docs/source -type f \( -name '*.png' -o -name '*.svg' -o -name '*.jpg' \) | wc -l   # 14
find docs/source -name '*.rst' -exec cat {} + | wc -w         # 107833
find docs/source -name '*.md' | wc -l                        # 2  (built by nothing)
grep -rhE '^\.\. _[A-Za-z0-9_-]+:' docs/source --include='*.rst' | wc -l   # 67 labels
grep -rn 'automodule\|autoclass' docs/source | wc -l          # 5
# orphan probe (see V-10): the reliable check is the build log, not a text scan
#   python -m sphinx -b html -E docs/source /tmp/out 2>&1 \
#     | grep "isn't included in any toctree"      # collecting-vocabulary.rst

# Surface denominators (the coverage table's numerators/denominators)
grep -oE 'name: *"[A-Za-z0-9_]+"' frontend/src/components/Resource/Definition.tsx \
  | wc -l                                                     # 72
# resources not named anywhere in docs (25) — identifier match over all doc text
python3 - <<'PY'
import re, glob
names = re.findall(r'name:\s*"([A-Za-z0-9_]+)"',
                   open("frontend/src/components/Resource/Definition.tsx").read())
docs = "".join(open(p, encoding="utf-8", errors="replace").read()
               for p in glob.glob("docs/**/*.rst", recursive=True)
                    + glob.glob("docs/**/*.md", recursive=True))
missing = [n for n in names if not re.search(rf'\b{n}\b', docs)]
print(len(names), len(missing)); print(missing)
PY
python3 - <<'PY'                                                    # models & relations
import re, glob
files = glob.glob("backend/*/models.py") + glob.glob("backend/*/models/*.py")
cls = rel = 0
for p in files:
    t = open(p, encoding="utf-8", errors="replace").read()
    cls += len(re.findall(r'^class\s+\w+\s*\([^)]*models\.Model[^)]*\)', t, flags=re.M))
    rel += len(re.findall(r'\b(?:models\.)?(?:ForeignKey|OneToOneField|ManyToManyField)\s*\(', t))
print(cls, rel)                                                     # 55 178
PY
python3 -c "
import re;s=open('backend/MrMap/settings.py').read()
print(len(set(re.findall(r'^([A-Z][A-Z0-9_]*)\\s*=',s,re.M))))"     # 158 settings
# (164 assignment lines, 158 distinct names; the denominator is distinct names)
find backend -path '*/management/commands/*.py' ! -name '__init__.py' | wc -l   # 9
grep -rEc '@shared_task|@app\.task|@celery_app\.task' backend/*/tasks/*.py \
  | awk -F: '{s+=$2} END {print s}'                                # 35
python3 -c "import yaml;print(len(yaml.safe_load(open('docker-compose.yml'))['services']))"      # 11
python3 -c "import yaml;print(len(yaml.safe_load(open('docker-compose.dev.yml'))['services']))"  # 12
find backend/tests/behave/features -name '*.feature' | wc -l       # 97
```

The build measurement needs GDAL and the docs toolchain, so it runs in a
container. Two runs, which together are V-11 and V-9/V-16:

```bash
# V-11 — committed pins: fails in ~1 s with the sphinxcontrib-applehelp version error
tar -C docs/source -cf - . | docker run -i --rm <docs-image> /bin/sh -c '
  mkdir -p /src /tmp/stub/MrMap /tmp/logs && tar xf - -C /src
  printf "def setup():\n    pass\n" > /tmp/stub/django.py
  printf "VERSION = \"0.1.0\"\n" > /tmp/stub/MrMap/__init__.py
  printf "LOG_DIR = \"/tmp/logs\"\n" > /tmp/stub/MrMap/settings.py
  cd /src && PYTHONPATH=/tmp/stub python -m sphinx -b html -E . /tmp/out'
# V-9, V-16 — Sphinx >= 5 pins: rc=0, ~8 s, 61 HTML files, 22 warnings, of which
# 5 are "autodoc: failed to import module" for
# registry.models.service, registry.models.security, registry.managers.service,
# registry.proxy.wms_proxy, registry.proxy.wfs_proxy
```

The `django.py` stub satisfies `conf.py`'s `import django` without a database,
and the `MrMap` stub supplies the two values `conf.py` reads (`VERSION`,
`LOG_DIR`). That is the minimum environment a docs build needs, and the fact that
a stub is needed at all is input to #1597: the build should not require the
application to be importable in order to render prose.

The 22 warnings are a stable set, not a flaky one: 5 autodoc import failures, 1
orphan page, and 16 markup faults counted over the passes of one build. The
anchor commit and current `develop` report the same 22 with the same
composition.
