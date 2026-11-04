# Metadata identity, relationships and integer enums

Decision record for #982 (epic #669 design gate). It decides the identity, relationship,
precedence, schema-shape and enum conventions which #670 and #983 implement. It changes no
code, no model and no migration; every statement below about existing behavior describes
current `master`.

## Identity inventory (what exists today)

All metadata-bearing models share `registry.models.metadata.AbstractMetadata`:

- `id` — UUID PK, generated per row; it is a transport key, not a domain identity.
- `file_identifier` — parsed `gmd:fileIdentifier` (mappers/configs
  `dataset.py`, `service.py`, `application.py`), `db_index`, `editable=False`, defaults to a
  fresh uuid4 for records MrMap authors itself. A `UniqueConstraint`
  `%(app_label)s_%(class)s_unique_file_identifier` from `AbstractMetadata.Meta` is active on
  the tables whose Meta merges `AbstractMetadata.Meta.constraints`: `DatasetMetadataRecord`,
  `ServiceMetadataRecord`, `ApplicationMetadataRecord`, `Layer`, `FeatureType`. The three
  service tables (WMS/WFS/CSW) merge only `AbstractMetadata.Meta.indexes`, so a service's
  file identifier is indexed but **not** unique in its table — service identity is the PK
  (D3), and uniqueness of a generated service document's fileIdentifier is not a storage
  invariant.
  The field's help text already states the dual role of a layer/feature type file identifier:
  it is the uuid of the described element, used to identify the ISO document MrMap generates
  for it.
- `date_stamp` — remote date stamp for harvested records; the harvest update guard.
- `origin` (`MetadataOriginEnum`, PositiveSmallInt, nullable) and `origin_url` — provenance
  of the row; both are filled on every harvest write for all three record types since #976
  (`PersistenceHandler.defaults_of` + `_write_values_of`, `mappers/persistence/custom.py`).
- `is_customized` — set by editor writes, never by harvest (`save(mark_customized=False)`,
  #858); the only remaining marker of local edits.
- `code` / `code_space` — split out of the citation identifier
  (`CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code`) by `_split_code`;
  `resource_identifier` is the persisted `GeneratedField` `code_space || code` (string
  concatenation without separator). A conditional unique constraint keeps
  `(file_identifier, code, code_space)` unique except for broken records with empty
  code/code_space.

Concrete record tables additionally carry `harvested_through` (M2M to `CatalogueService`,
added by `TemporaryMdMetadataFile.update_relations` on every harvest write, accumulating all
catalogues which ever delivered the record), a persisted `search_vector`
(`GeneratedField` + GIN index, `expressions/search.py`) and a `keywords_list` array — the
`SearchableDatasetMetadataRecord`/`SearchableServiceMetadataRecord` materialized views were
dropped by migration `0023_drop_the_searchable_projections_of_a_record.py` (#855, epic
#851); the CSW and MapBender searches read the record tables directly. `ApplicationMetadataRecord`
exists as model, manager, mapping config and harvest target but has no registry API resource,
serializer or viewset yet — it is answered only through the CSW and MapBender search endpoints.

`MetadataRelation` couples **registered** objects: five typed FKs to resources
(`layer`, `feature_type`, `csw`, `wms`, `wfs`), two typed FKs to records
(`dataset_metadata`, `service_metadata`), `is_internal` and `origin`, guarded by the
`one_related_object_selected` check constraint over the combinations enumerated in
`registry/models/metadata_query.py` and by unique constraints holding
`service_metadata` at one per resource. Rows are created only by capabilities import
(`origin=CAPABILITIES`, `is_internal=False`, "imported evidence") or by editors
(`origin=EDITOR`, `is_internal=True`, publishable). The `self_pointing_layers`,
`self_pointing_feature_types` (dataset records) and `self_pointing_wms/wfs/csw` (service
records) relations are `ManyToManyField`s with `through=MetadataRelation,
editable=False` — derived traversal views over those rows, in both directions.

`HarvestedMetadataRelation` records per harvesting job which record was collected with
which `collecting_state` (NEW/UPDATED/EXISTING/REMOVED/DUPLICATED); a unique constraint per
job and record allows the three "atomic" states only once and admits unlimited DUPLICATED
rows, which `HarvestingJob.add_harvested_metadata_relation` writes when the atomic insert
loses against the constraint, and which `md_metadata_file_to_db` then reports as an import
error.

## Where fileIdentifier is already equated with something

The consistency check demanded by the issue — these are the existing equations, each with
the scope in which it is trusted:

| Place | Equation |
| --- | --- |
| `custom.py get_or_create_metadatarecord` / `_record_of` | harvest upsert key: one row per (record type, file_identifier), newer `date_stamp` wins |
| `csw/views.py get_record_by_id`, `csw/queryables.py` (`identifier` queryable), `csw/elementsets.py` (`dc:identifier`) | the CSW endpoint's record identifier **is** `file_identifier` |
| `md_metadata_file_to_db` provenance defaults | `origin_url` is built as `get_record_by_id_request(id=file_identifier)` — fileIdentifier is treated as this catalogue's request identifier |
| `RemoteMetadata.create_metadata_instance` | created record looked back up by file_identifier after persistence |
| `mapbender_compatibility` remote search | `"id"` and `"datasetId"` are the parsed `file_identifier` (its `local_search` answers `"id": record.pk` instead — an existing drift, not fixed here) |
| `registry/helper/preview.py registered_previews` | a CSW's advertised record is matched to registry records by `file_identifier` **scoped to records harvested through this very CSW** (`harvesting_job__service=service`) |
| `AbstractMetadata.file_identifier` help text | registered element: `PK(Layer/FeatureType)` = fileIdentifier of the document MrMap generates for it |

`docs/live-service-previews.md` documents the last row's user-facing rule. The one place
which may compare a foreign identifier to `file_identifier` today is therefore a preview
lookup fenced by harvest provenance — that fence is promoted to a rule in D4.

## Relationship and provenance inventory

- Reference kinds in harvested ISO service records (`srv:operatesOn` `@uuidref`/`@xlink:href`,
  `srv:coupledResource/srv:SV_CoupledResource` identifier, access links in
  `gmd:onLine`/`connectPoint`) are **not persisted** — no dataset/service config maps them
  (#669 findings, confirmed on master); #670 extracts them.
- `origin_url` provenance: since #976 every harvested row of every record type carries
  `origin` and `origin_url`. On an update the whole value set (including `origin`/
  `origin_url`) is copied onto the fetched row, so the provenance columns answer **the last
  document which wrote**, while `harvested_through` accumulates **all** catalogues and
  `HarvestedMetadataRelation` keeps the per-job history. The original document survives in
  `xml_backup_file` on media storage. Consequences for precedence are decided in D7.
- `MetadataRelation.publication_url` publishes the **dataset record's `origin_url`** as the
  coupled metadata reference of a service element; a curated relation without a resolvable
  `origin_url` is reported as blocked and left out (#858 coupling policy,
  `querys/metadata.py`).
- Permissions: record and service viewsets are guarded by
  `extras.permissions.DjangoObjectPermissionsOrAnonReadOnly` (guardian; anonymous read-only,
  record viewsets full `ModelViewSet`). `RecordPermissionsSerializerMixin` answers
  `can_edit`/`can_delete` per object via `ObjectPermissionChecker`. Object-level grants are
  bootstrapped only for `SECURED_MODELS` (the services); record ownership waits for the role
  work (#727). Audit: `simple_history` `change_log` with `history_user` and `_change_reason`
  (harvest writes name their reason; `keywords_list`/`search_vector` are excluded fields);
  the API answers `created_at/by` and `last_modified_at/by` from history.
- GenericFK precedent: guardian object permissions were moved **off** the generic
  `content_type`/object-id columns onto dedicated direct-FK tables per model
  (`registry/models/guardian.py`, migrations 0030/0031). New coupling tables must use typed
  FKs the same way, not `GenericForeignKey`.

## Integer enum conventions

`extras/enums.py` defines `SmartIntegerChoices` (`IntegerChoices` + metaclass allowing
label-based lookup, returning `None` instead of raising). Current users:
`MetadataOriginEnum`, `MetadataRelationPublicationEnum` (derived, never persisted),
`DatasetFormatEnum`, `TimeExtentKind` (registry/enums/metadata.py); `MetadataCharsetChoices`,
`UpdateFrequencyChoices`, `CategoryChoices`, `LanguageChoices` (enums/iso.py);
`OGCServiceVersionEnum`, `OGCOperationEnum`, `HttpMethodEnum`, `SecureableWMS/WFSOperationEnum`
(enums/service.py); `UpdateJobStatusEnum` (enums/update.py); `ProcessStatusEnum`
(notify/enums.py). Persisted choice columns are uniformly
`PositiveSmallIntegerField(choices=…)` (`origin`, `charset`, `format`,
`update_frequency_code`, `collecting_state`, `phase`, `version`, `level`, `kind`, …).

Known deviations (documented, not changed by #982): `CollectingStatenEnum`,
`HarvestingPhaseEnum`, `LogLevelEnum`, `LogKindEnum` use plain `IntegerChoices`;
`CategoryOriginEnum`, `OGCServiceEnum`, `AuthTypeEnum` are `TextChoices` (the first carries a
TODO to convert); `UpdateModeEnum` is a `StrEnum` used for dispatch, not for persistence.
Finite classifications which must exist as **rows** (ISO codeLists, securable operations) use
the `ChoiceModel` pattern: a table whose `PositiveSmallIntegerField` primary key **is** the
enum value (`IsoCategory`, `Language`, `WebMapServiceOperation`, …).

## Decisions

**D1 — Dataset identity.** The identity of a dataset is the ISO `fileIdentifier` of its
metadata record, per record type table (`DatasetMetadataRecord` unique index). The database
PK, title, citation code/code_space, layer/feature type name and endpoint URL are never
substitutes. The PK remains the JSON:API transport key. Records MrMap authors keep the
uuid4-default fileIdentifier; a parsed value is never rewritten.

**D2 — Preserve the original.** `file_identifier` is stored exactly as parsed (max 1000
chars, no case folding, no URL-semantic normalization). Normalization happens only in
comparison rules that name their steps (D4), never in the stored identity.

**D3 — Four identity classes, no cross-class equality.** (a) *document* identity: fileIdentifier
of an ISO record; (b) *service* identity: the registered `WebMapService`/`WebFeatureService`/
`CatalogueService` row (PK), versus a *merely advertised* endpoint which is a URL plus
protocol hint and has no identity until registered; (c) *registered resource* identity: the
`Layer`/`FeatureType` row (PK) with a name (`ServiceElement.identifier`) unique per owning
service; (d) *representation*: the WMS layer and the WFS feature type of the same dataset are
distinct resources whose only shared identity is evidence pointing at the same dataset record
(#986 groups them; nothing equates them). A dataset is usable without any registered service
(epic direction); a conflation of dataset identity with a layer or feature type is rejected.

**D4 — Reference resolution rules (when may which be compared?).**

| Reference kind | Identifies | May be compared against | Only under |
| --- | --- | --- | --- |
| `srv:operatesOn/@uuidref` | dataset metadata record | `DatasetMetadataRecord.file_identifier` | scoped to the catalogue provenance of the source record (`harvested_through`/`HarvestingJob.service`), mirroring `registered_previews`; a uuidref from one catalogue is never matched to a record it never delivered |
| `srv:operatesOn/@xlink:href` | a metadata *document* at a URL | `origin_url` of a record, byte-compare after trim + default-port/scheme lowercase (URL syntax only) | scoped as above; a hostname or path prefix is never a match |
| `srv:coupledResource` identifier | the *resource*, per `SV_CoupledResource` | `code` + `code_space` (`resource_identifier`) of a dataset record | only when both sides carry non-empty code and code_space; never against a fileIdentifier |
| WMS `LayerName` / WFS feature type name | a representation of one service | `ServiceElement.identifier` | within a single registered service (where it is unique); never across services |
| `gmd:onLine`/`connectPoint` linkage | an advertised endpoint | registered service URLs (candidate discovery, #671) | as candidate evidence only; a URL never becomes a service or a layer by comparison alone |

A reference to an absent target stays **unresolved** (visible, queryable); silent merging is
prohibited. A second distinct document claiming one fileIdentifier is **ambiguous**: both
provenances stay visible and the coupling is not auto-resolved. Today the per-table unique
index plus the `date_stamp` guard makes such collisions merge into one row whose provenance
answers only the last writer, with DUPLICATED flagging only *within-job* redelivery; closing
that gap for cross-catalogue collisions is a persistence task for #983 with explicit states,
not a redefinition of identity here.

**D5 — Relationship taxonomy.** A *declared* relationship is directional, source-owned and
persisted with the identity of its source document, its reference kind (D4) and provenance;
the original external value is kept beside the resolved target. A *derived* relationship is
computed traversal and is never persisted as fact — `self_pointing_*` (through
`MetadataRelation`) is the existing instance of that; new bidirectional APIs (#671/#984) read
declared rows in both directions. Discovery never creates `MetadataRelation` rows without
evidence (epic acceptance criterion). The existing MetadataRelation publication policy
(imported evidence / curated publication / local only) stays as is.

**D6 — Identity of coupling rows.** `MetadataRelation` remains the join of *registered*
objects (evidence-backed only). ISO-declared references to documents/endpoints get their own
persisted, typed, directional rows (D8) instead of growing more nullable columns onto
MetadataRelation; its FK-column-per-type shape is the precedent for "typed FKs, check
constraint over the allowed combinations" that new tables copy.

**D7 — Precedence (ownership of values).**

1. *User-confirmed internal links* (`is_internal=True`, `origin=EDITOR`) — owned by the
   curator; a re-harvest never deletes, flips or duplicates them.
2. *Locally edited ISO* (`is_customized=True`) — visible marker; column-level overwrite of
   customized record content by later harvest is the current behavior and stays until a
   per-field conflict decision is made; it does **not** extend to relationship rows, which
   are provenance-keyed (3.).
3. *Capabilities-derived evidence* (`origin=CAPABILITIES`) — owned by the document that
   declares it: a re-harvest/re-update may replace or remove only rows whose provenance is
   the document it is processing (same source kind and source document identity); it may
   never touch another source's rows.
4. *Harvested XML facts* — the stored `xml_backup_file` is immutable source truth; every
   derived row must be rebuildable from stored documents without reharvesting.
For provenance columns the existing split stands and is the convention for new tables:
`origin`/`origin_url` answer the **last document which wrote** the row; the complete set of
provenances is always the per-job history plus `harvested_through`. Consumers needing "all
sources of a record" must read those, not the columns (and consumers needing a printable
reference read `origin_url`, per the publication policy).

**D8 — Minimal schema for #983 (sketch; unblocks migration numbering).** Additive only; the
next free registry migration number is **0034** (current head: `0033_application_metadata_records_are_maintained_like_the_others.py`).

- table **metadata reference** (one row per source-document-declared reference): typed FK
  `source_record` to one of the three record tables (FK per kind + CHECK, or one table per
  kind if the check constraint becomes unwieldy), `target_file_identifier` (original value),
  `target_href` (original value), `target_code`/`target_code_space` (original values),
  `reference_kind` (PositiveSmallInt + SmartIntegerChoices: OPERATES_ON_UUIDREF,
  OPERATES_ON_HREF, COUPLED_RESOURCE_IDENTIFIER, ACCESS_ONLINE, METADATA_LINK),
  `protocol` and `operation` hints (PositiveSmallInt + SmartIntegerChoices, original strings
  beside them), `resolution_state` (PositiveSmallInt + SmartIntegerChoices: UNRESOLVED,
  RESOLVED, AMBIGUOUS, STALE), resolved typed FKs `dataset_target`/`service_target`/
  `element_target`/`endpoint_target` (nullable, CHECK: state RESOLVED ⇒ exactly one set),
  provenance `origin` + `source_harvesting_job` FK + `origin_url`-style source document URL,
  `is_internal`-equivalent ownership flag.
- table **advertised endpoint**: original `url` (preserved byte-for-byte), normalized `url`
  column for lookups, protocol/version/operation hints as enums with original strings, typed
  FK `advertised_by_service`/`mentioned_in_record`, plus the same resolution state; a
  resolved endpoint FK to a registered service exists **only** after an actual registration —
  discovery never registers.
- uniqueness: (source record FK, kind, original target value) — a document declares a target
  once; reverse lookup indexes: `(target_file_identifier)`, `(normalized url)`, and
  `(service, resolution_state)`; per-D4 scoping lookups run through the existing
  `HarvestedMetadataRelation`/`harvested_through` indexes, no full catalogue scan per save.
- deletion semantics: source record delete → CASCADE (the declaration dies with its
  document); target (dataset/service/element) delete → SET_NULL of resolved FKs and state
  back to UNRESOLVED, never CASCADE (the declaration survives a missing target — "remains
  unresolved"); harvesting job delete → CASCADE its derived rows (matches
  `HarvestedMetadataRelation`); catalogue delete leaves records (M2M rows only, as today).
- the migration is `CreateModel` + indexes/constraints plus a repeatable backfill **data**
  operation/management command reading stored `xml_backup_file`s (#983 owns it); no existing
  column changes; `search_vector`/`keywords_list` are untouched — making references
  searchable would be a separate decision.

**D9 — Enum conventions.** All new persisted finite classifications (reference kind, protocol,
operation, origin refinement, resolution state) are `SmallIntegerField`/
`PositiveSmallIntegerField` columns with `extras.enums.SmartIntegerChoices` members, values
stable once assigned (numbers are permanent addresses in the rows). External codeList/protocol
strings are stored in a separate original-value column and never round-tripped through the
enum number. Row-backed classifications follow the `ChoiceModel` pattern. Converting the
plain-`IntegerChoices` harvest enums listed above to `SmartIntegerChoices` is out of scope of
#982 and #983 (it changes no storage, only lookup ergonomics; housekeeping candidate).

**D10 — Ambiguity and duplicates.** Duplicate delivery inside one harvesting job keeps the
existing DUPLICATED collecting-state treatment. Same fileIdentifier + same (code, code_space)
= same document, newest `date_stamp` wins (existing rule). Same fileIdentifier from different
catalogues = ambiguous identity: the persisted reference rows carry the provenance of each
declaration and answer AMBIGUOUS until a curator or a verified (code, code_space) match
resolves one; nothing merges them silently and nothing picks "the newest" across catalogues.

**D11 — Permissions and audit for the new rows.** Read visibility of a persisted
reference/endpoint row follows the view permission of its source record (a curator who may
read the record may see what it declares); write access follows the record's change
permission; resolving to a target requires no permission the source reader did not have, but
*answering* the resolved target to an API consumer goes through the target's own view
permission (same pattern as the alert records in `docs/architecture.md`). Backfill runs are
system writes with a `change_reason`, history-tracked like harvest writes.

**D12 — Reverse queries.** The service→dataset direction (which datasets declare/are coupled
to this service) and the catalogue→unresolved direction must be single indexed lookups per
D8; #671's "indexed reverse service-to-dataset coupling" decision is hereby recorded as: index
`(target …, resolution_state)` on the reference table, not a new materialized view (the
projection removal of #851/#855 must not be re-litigated).

## Test obligations handed to the children

#983 implements and explicitly tests: fileIdentifier identity and collision rules (D1, D4,
D10), reference-kind matching per the D4 table, both import orders, collision visibility,
backfill from stored XML; #671 tests the reverse-lookup index decision of D12; the enum
convention of D9 is checked by review of #670/#983 models against the SmartIntegerChoices
requirement. No conflation of dataset identity with a WMS layer or WFS feature type (epic
acceptance criterion) is asserted by D3.
