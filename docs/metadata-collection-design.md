# Registering an OGC service and collecting its linked metadata — audit and design

> Research and design document, **no implementation**. Everything below was read out of
> `origin/master` at `d2a9dc0` (2026-11-11); file and line references are given for every statement.
> `master` has since moved to `af93eaf`; every cited line was re-checked there and still reads the same,
> because the only change to the files in question adds keyword triggers below line 1275.
> The mockups in [`images/metadata-collection/`](images/metadata-collection/README.md) are HTML renderings
> of the real components — no running deployment was involved, see the README.
>
> Status: **findings and proposals**. Items marked **verified** were read in the source; items marked
> **suspicion** need a run to confirm; items marked **proposal** are decisions nobody has taken yet.

## 1. What this covers

The registration of a WMS or WFS runs asynchronously and, when the option
`collect_metadata_records` is on, fetches every metadata document that the GetCapabilities
document references and turns it into a metadata record. Three questions came up repeatedly:

1. What does a user actually learn about that collection — while it runs, and after it ended?
2. When a metadata document fails, where is that visible, and for how long?
3. How does an operator see which metadata belongs to which layer, feature type or service?

## 2. The lifecycle as it is implemented

```mermaid
sequenceDiagram
    participant U as Browser
    participant API as POST /api/registry/wms<br/>extras/viewsets.py:202
    participant DB as BackgroundProcess
    participant B as build_ogc_service<br/>registry/tasks/service.py:26
    participant F as fetch_remote_metadata_xml<br/>registry/tasks/service.py:199
    participant FC as finish_background_process<br/>notify/tasks.py:219

    U->>API: create_WebMapService (collect_metadata_records=true)
    API->>DB: create process REGISTERING, status pending<br/>registry/views/service.py:344
    API->>B: apply_async(task_id=uuid) (task id stored first)<br/>extras/viewsets.py:217-220
    API-->>U: 202 + the serialized process + Content-Location
    Note over U: the client shows a "created" snackbar and refetches the list<br/>components/Dialog/useDialogMutationSuccess.ts:18-27<br/>the process in the answer is dropped
    B->>B: GetCapabilities, map, persist service + layers<br/>+ RemoteMetadata rows (one transaction)
    B->>DB: phase='collecting metadata records...', total_steps=N<br/>registry/tasks/service.py:177-181
    B->>F: chord(header=N tasks)(body)
    F->>F: fetch remote_content -> create_metadata_instance<br/>-> add_metadata_relation
    Note over F: success returns at :236 before step_done at :272
    F-->>DB: done_steps + 1 — only on the failure paths
    FC->>DB: update_background_process(completed=True)<br/>notify/tasks.py:224-231
    Note over DB: done_steps=total_steps, phase='completed',<br/>status=COMPLETED — also when every reference failed
```

**verified** — the relevant facts of that picture:

| Fact | Where |
| --- | --- |
| The create endpoint answers 202 with the process, not with the service | `extras/viewsets.py:200-254` |
| The task is published after the process row is committed, with a pre-assigned task id | `extras/viewsets.py:217-220` |
| `collect_metadata_records` defaults to `True` for WMS and WFS, is forced to `False` for CSW | `registry/serializers/service.py:615-618`, `:820`, `registry/views/service.py:1011` |
| The collection is a Celery **chord**: one `fetch_remote_metadata_xml` per `RemoteMetadata` row, body `finish_background_process` | `registry/tasks/service.py:170-183` |
| `total_steps` is set once, to the number of references; the build task's own phases only write `phase` text | `registry/tasks/service.py:177-181`, `notify/tasks.py:124-126` |
| A run in which **every** reference failed still ends `completed` | `notify/tasks.py:224-231`; asserted by `tests/django/notify/test_registration_polling.py:370-410` |
| Failures are stored only as free-text `BackgroundProcessLog` rows of type `WARNING` | `registry/tasks/service.py:245-270` |
| `RemoteMetadata` stores `link`, `remote_content`, `describes` — nothing else | `registry/models/metadata.py:492-513`, `:576-623` |
| `link` is not unique and there is no dedup between registrations | `registry/models/metadata.py:502-504` (a `TODO` says so) |
| The relation to the described object is created only for what the collection produced | `registry/models/metadata.py:571`, `:1217-1246` |
| Harvesting keeps its own bookkeeping (`HarvestedMetadataRelation` with `collecting_state`, phases, logs) — registration does not | `registry/models/harvest.py`, `registry/enums/harvesting.py` |
| No test calls `fetch_remote_metadata_xml` at all | `grep -rn fetch_remote_metadata tests/` → only a comment in `tests/django/notify/test_measurement.py:130` |

## 3. Defects found

| # | Defect | Evidence | Effect today | Class |
| --- | --- | --- | --- | --- |
| A | `case "LayerRemoteMetadata"` appears twice in `fetch_remote_metadata_xml`; the second one — whose body loads `FeatureTypeRemoteMetadata` — can never match | `registry/tasks/service.py:216` and `:222` | Every **WFS feature-type** metadata reference falls into `case _`, returns `None` at `:228-229` with **no log line, no step, no record**. The service ends `completed`. Untested (§2, last row) | **verified bug** |
| B | The success path returns inside the `try`; the only `update_background_process(step_done=True)` sits after the whole `try/except` | `registry/tasks/service.py:236-244` vs `:272-274` | While a healthy collection runs, `done_steps` stays 0 → the Job Center shows 0 % until the last task jumps it to completed. Only failures make the bar move | **verified bug** |
| C | `finish_background_process` completes unconditionally; `update_background_process(completed=True)` forces `done_steps=total_steps` and `status=COMPLETED` | `notify/tasks.py:163-170`, `:224-231` | "Completed" does not mean "everything was collected". The difference is only readable as `WARNING` log lines, which #1208's retention purges | **verified design gap** |
| D | `UnknownMetadataKind` is imported and caught, but never raised anywhere | `registry/tasks/service.py:9`, `:252`; no `raise UnknownMetadataKind` in `registry/` | A document of an unsupported kind lands in the generic `except Exception` instead — same visible effect, dead branch | **verified dead code** |
| E | Both failure branches of the fetch task end without re-raising, so `autoretry_for` never applies to a single document: urllib3's `MaxRetryError` (after three internal retries with `backoff_factor=0.1`) and every other exception - including `NoContent` for a non-200 answer - become a warning | `registry/tasks/service.py:245-270`, `notify/tasks.py:98-103`, `registry/models/metadata.py:517-539`, `registry/exceptions/service.py:11` | A document which is unreachable for a moment is given up for the whole registration, and nothing offers a second attempt | **verified** |
| F | `fetch_remote_content` sends the request **without a timeout**, while the capabilities request of the same flow passes `timeout=15` | `registry/models/metadata.py:530` vs `registry/tasks/service.py:63-65` | One slow or hung metadata endpoint occupies a worker of the `download` queue indefinitely; the `Retry` adapter only covers connection errors, not a silent server | **verified** |
| G | The per-step increment is unbounded (`F("done_steps") + 1`) while a task may be delivered more than once | `notify/tasks.py:157-160` (contrast the capping in `notify/managers.py:144-153`, which this path does not use) | `done_steps` can exceed `total_steps` → `progress` above 100 % | **suspicion** (needs a duplicate-delivery run) |
| H | The answer for `metadata_record=None` still builds a payload: `"id": "None"` and a `"self"` link of the string `"None"` | `registry/tasks/service.py:236-244` | A collection that parsed a document but found no `file_identifier` produces a record reference which is a stringified `None` | **verified** |
| I | A FeatureType never shows its records: `ElementInspection` renders the metadata section for layers only, and `metadataIds` is hardcoded to `[]` for feature types | `Generic/ServiceShow/ElementInspection.tsx:110-113`, `:260-263` | The relation rows exist (`MetadataRelation.feature_type` is filled) but nothing reads them for a WFS element | **verified gap** |
| J | `remove_metadata_relation` is never called from anywhere | `registry/models/metadata.py:1250-1270` (definition), no callers in `grep` | Relations survive a re-registration. Whether they *stack* is not settled by reading: `add_metadata_relation` is a `select_for_update().get_or_create()` over the filled columns plus `is_internal` (`:1241-1245`), so the same record and element cannot produce a second row — a duplicate needs a second record instance for the same identifier, which depends on #982's identity rules | **verified** (the duplicate consequence is a **suspicion** until measured) |
| K | The German label of the create option reads "Metadaten wiederherstellen" ("restore metadata") | `backend/locale/de/LC_MESSAGES/django.po:3129-3130` for `registry/serializers/service.py:617` | The option is named after a different action in the German UI | **verified** |

A–C together are the reason the collection is described as "silent": a WFS operator loses the metadata of
every feature type, and the only clue is that the progress bar never moved.

## 4. Relations: what is stored, what is visible

**verified** — `MetadataRelation` is seven explicit foreign keys plus two provenance fields
(`registry/models/metadata.py:916-1084`): `layer`, `feature_type`, `csw`, `wms`, `wfs`, `dataset_metadata`,
`service_metadata`, with `origin` (`MetadataOriginEnum`: Capabilities, Upload, File System Import, Editor,
Catalogue) and `is_internal`. There is no generic foreign key and no relation "type" — the type is which
column is filled.

Consequences which the UI inherits:

* **verified** — the graph and the tables of the record's *Relations* tab group strictly by those columns
  (`Generic/RecordShow/RecordRelations.tsx:40-51`, `:257-263`). A `ServiceMetadataRecord` that describes a
  dataset (filled via `wms`/`wfs`) is therefore invisible on the dataset record, because the dataset branch
  only asks for `layer`, `featureType` and `csw`.
* **verified** — nothing in the model distinguishes "this record describes that element" from "this record
  refers to that element" (`add_metadata_relation` is called only from `RemoteMetadata.create_metadata_instance`
  with `related_object=self.describes`, `registry/models/metadata.py:571`, `:1217-1246`). So the ISO
  "applies to" direction cannot be shown, and cannot be created by a user through this model.
* **verified** — the record's origin URL and a `MetadataRelation` are the only link back to the `RemoteMetadata`
  row; the link is not unique, and the mapping is by matching `origin=CAPABILITIES` + `origin_url == link`
  (`registry/models/metadata.py:549-554`). Nothing stores "this record came from that reference".
* **verified** — the CSW harvesting path never creates `MetadataRelation` rows at all; a harvested dataset
  record has no element relations (`registry/tasks/harvest.py` — no call of `add_metadata_relation`).
* **verified** — the display is capped at `perPage: 100` and 100 nodes, with the real total only behind an
  info alert (`RecordRelations.tsx:169`, `:133-134`, `:204-207`).

## 5. What an operator cannot find out today

| Question | Answer today |
| --- | --- |
| Is a registration still collecting? | Only "running" vs "completed"; the bar sits at 0 % (defect B) |
| How many references were expected? | `total_steps`, but only after the fan-out; nothing before |
| Which reference produced which record? | Nothing stored; derivable heuristically by `origin_url` matching |
| Which references failed, and why? | Free-text `WARNING` log lines that embed a numeric id, purged by the retention of #1208 |
| Which references were never even attempted (defect A)? | Nothing at all — no log, no state |
| Which metadata describes this feature type? | Not shown (defect I); only the layer branch shows its records |
| Which service-level record describes this dataset record? | Not shown (grouping in the graph/tables, §4) |
| Is a relation from a previous registration still live? | Nothing removes relations (defect J) |

## 6. Proposal: reuse the harvesting bookkeeping instead of inventing a second one

Harvesting already solved the same problem and its shape is documented, translated, tested and rendered.
Registration should adopt it rather than add a parallel mechanism.

| Need | Existing pattern to copy | Where it lives today |
| --- | --- | --- |
| one row per expected item, with a state | `HarvestedMetadataRelation` + `collecting_state` | `registry/models/harvest.py`, `registry/enums/harvesting.py` |
| phases a run goes through | `HarvestingJob.phase` + `HarvestingPhaseStepper` | `registry/tasks/harvest.py`, `frontend/src/components/Resource/HarvestingJob/` |
| counters which must not be re-aggregated per poll | stored counters, not annotations (measured in #1037: annotations on a live run cost 5.85 s cold / 12.2 s worst) | `docs/architecture.md:100-172` |
| run summary screen | `HarvestingRunSummary` + `harvestRun.collectingStates` vocabulary (rendered by `HarvestingRunMissingRecords.tsx:111`) | `frontend/src/components/Resource/HarvestingJob/`, `frontend/src/i18n/en.ts:459-469` |
| a run card on the object's own page | `HarvestingActivityCard` | `frontend/src/components/Resource/CatalogueService/Show/` |
| normalized progress and states for the browser | `OperationStateEnum`, `revision`, `error_summary` | `notify/enums.py`, `notify/managers.py` (#1207) |
| live updates without polling storms | topic websocket + bounded poll fallback | `notify/consumers.py`, Job Center (#1203/#1205/#1206) |

Concretely, as a proposal for a follow-up implementation (each step is independently shippable):

1. **Fix the two bugs first.** `case "LayerRemoteMetadata"` (A) and the position of `step_done` (B) are two
   one-line changes plus a test that calls `fetch_remote_metadata_xml` with each of the four reference kinds.
   This alone turns a silent total loss for WFS into a visible, correct run.
2. **Give a collecting run a truthful end state.** Either a distinct terminal state for "ended with findings"
   (which `OperationStateEnum` does not have yet — needs a decision, see §8), or a stored per-process summary
   (`references_total / stored / failed / skipped`) that the serializer exposes. The chord body stays as it is.
3. **Persist the outcome per reference**, in the `RemoteMetadata` subclass rows (or one table for all kinds,
   as `HarvestedMetadataRelation` does): the reference keeps `link` + `describes` and gains
   `collecting_state`, `collected_at`, `error_kind`, `error_detail`, and a nullable FK to the created record.
   That answers §5 rows 3-5 without heuristic matching, and makes a per-reference retry possible.
   **Never** derive a counter per request — store it (see the #1037 measurement above).
4. **Deduplicate references** by making `link` unique per described object (the `TODO` in
   `registry/models/metadata.py:502-504` already asks for it), so re-registration updates instead of stacking.
5. **Close the relation gap**: let `ElementInspection` use the same data for both element kinds (the branch at
   `:110-113` is the only thing that differs), and show *which* element a record describes rather than only
   "related". Adding the "applies to" direction needs a model decision (§8) — until then the graph should say
   what it does *not* know instead of drawing one undirected "related" edge.
6. **Make the 100-relation cap a facet, not a ceiling**: the tables already filter per group, so a count per
   group plus a link "show all of this group" removes the only place where a user sees a truncated set.

## 7. Mockups

Two current screens (what exists, with the two gaps marked inside the image) and five proposals. All are
rendered from the components themselves; the proposed parts are dashed and tagged.
See [`images/metadata-collection/README.md`](images/metadata-collection/README.md).

| Image | Shows |
| --- | --- |
| `current-registration-jobcenter.png` | after registering a WMS the service page says nothing about the collection; the Job Center row is the only trace, at 0 % during the run and "Completed" after failures |
| `current-featuretype-inspection.png` | a WFS feature type has no metadata section at all, although its relation rows exist |
| `proposed-create-dialog-collect-metadata.png` | the option with wording that states what is collected, what happens on failure, and where to look |
| `proposed-registration-collection-card.png` | one card per registration on the service overview: phases, progress, per-outcome counters |
| `proposed-collection-outcome.png` | the per-reference table on the process screen, with the skipped references of defect A visible |
| `proposed-featuretype-metadata-relations.png` | the element inspection with the metadata section for a feature type, showing which record describes what |
| `proposed-dataset-relationship-graph.png` | the relations graph grouped by what a relation actually means, including the directions it cannot express today |

## 8. Decisions this needs from a human

1. **Terminal state.** Should a collection that ended with findings stay `completed` plus a summary, or get a
   distinguishable state? The vocabulary for that state exists: `action_required` is a derived
   `OperationStateEnum` value (#1207) driven by the stored flag `BackgroundProcess.action_required`, set
   through `BackgroundProcess.objects.set_action_required()` — harvesting (`registry/models/harvest.py:668`)
   and an update waiting for its review (`registry/models/update.py:334`) already use it, registration
   does not. The obstacle is the derivation order: `OperationStateEnum.derive()` answers `completed`
   before it looks at the flag (`notify/enums.py:80-90`), so a run cannot be both finished and awaiting
   attention unless the stored status stays non-terminal (which parks it in the drawer's *Waiting* tab,
   whose filter is `status: pending` — `JobCenter/counts.ts:12-17`) or the shared derivation changes.
2. **Where the per-reference outcome lives.** New columns on the four `RemoteMetadata` subclasses, or one
   table per registration run (the `HarvestedMetadataRelation` shape). The first is cheaper, the second keeps
   history across re-registrations.
3. **Retry semantics.** A per-reference "collect now" action needs an endpoint that starts work for one
   reference; today nothing but abort exists (`JobCenterDrawer.tsx:94-103`: no api restarts a decided
   process, `:205` is the only action).
4. **The "applies to" direction.** Add a relation kind (and what ISO element it mirrors), or state in the UI
   that MrMap's relations always mean "describes"?
5. **Backfill.** Existing services have `RemoteMetadata` rows without outcome, and duplicate rows from every
   update. Migrate, or accept and let the next registration rewrite them?
6. **Naming.** The German label of the option (defect K) and the vocabulary of the outcomes
   (reuse `harvestRun.collectingStates` or a registration-specific set?).

These six are asked as the numbered decision request on the epic — answering them is a design decision,
not implementation approval.

## 9. Where this went

The findings are published as **[epic #1256](https://github.com/mrmap-community/mrmap/issues/1256)**,
`slug: metadata-collection`, with twelve children (#1257–#1268) whose sub-issue and blocking relations
are registered on GitHub itself. The two one-line bugs are #1257 and #1258; the transport bounds are
#1260; the bookkeeping clean-up is #1261; everything that reports the outcome reads from #1263. Nothing
in this document was implemented, and no `agent: approved` was applied.

