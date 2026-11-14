# Metadata identity, relationships and integer enums

Decision record for #982 (epic #669 design gate). It decides the identity, relationship,
precedence, schema-shape and enum conventions which #670 and #983 implement. It changes no
code, no model and no migration; every statement below about existing behavior describes
current `master`. The review rounds on #991 and the maintainer clarification on #992
(2026-11) superseded an earlier draft which equated dataset identity with the ISO
`fileIdentifier`; D1–D4 and the schema sketch carry that correction. The same correction
propagates to #992 (its D01) and to the dependent designs.

## Identity inventory (what exists today)

All metadata-bearing models share `registry.models.metadata.AbstractMetadata`:

- `id` — UUID PK, generated per row; it is the JSON:API transport identity, not a domain
  identity.
- `file_identifier` — parsed `gmd:fileIdentifier` (mappers/configs `dataset.py`, `service.py`,
  `application.py`), `db_index`, `editable=False`, defaults to a fresh uuid4 for records MrMap
  authors itself. It identifies the **metadata document**, not the described dataset: several
  distinct documents (different fileIdentifier) may describe the same dataset, and a document
  version keeps its fileIdentifier while its `date_stamp` advances. A `UniqueConstraint`
  `%(app_label)s_%(class)s_unique_file_identifier` from `AbstractMetadata.Meta` is active on
  the tables whose Meta merges `AbstractMetadata.Meta.constraints`: `DatasetMetadataRecord`,
  `ServiceMetadataRecord`, `ApplicationMetadataRecord`, `Layer`, `FeatureType` — a
  **document-level** constraint: one row per document identifier per record type. The three
  service tables (WMS/WFS/CSW) merge only `AbstractMetadata.Meta.indexes`, so a service's
  file identifier is indexed but **not** unique in its table — service identity is the PK
  (D3), and uniqueness of a generated service document's fileIdentifier is not a storage
  invariant. The field's help text already states the dual role of a layer/feature type file
  identifier: it is the uuid of the described element, used to identify the ISO document
  MrMap generates for it.
- `date_stamp` — remote date stamp for harvested records; the harvest update guard, and the
  version ordering of one document identifier (D10).
- `origin` (`MetadataOriginEnum`, PositiveSmallInt, nullable) and `origin_url` — provenance
  of the row; both are filled on every harvest write for all three record types since #976
  (`PersistenceHandler.defaults_of` + `_write_values_of`, `mappers/persistence/custom.py`).
- `is_customized` — set by editor writes, never by harvest (`save(mark_customized=False)`,
  #858); the only remaining marker of local edits.
- `code` / `code_space` — the split citation identifier, i.e. the ISO **resource identifier**:
  `.../gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code/gco:CharacterString`
  parsed by `string_to_code` / `string_to_code_space` (`mappers/parsers/value.py _split_code`)
  in all three record configs. The parser is heuristic on URL-shaped values: an http(s)
  value with a `/` in its path yields the last segment as `code` and the remainder as
  `code_space`; an http(s) value with a `#` splits on the fragment; anything else is the whole
  string as `code` with an empty `code_space`. A conditional unique constraint keeps
  `(file_identifier, code, code_space)` unique except for broken records with empty
  code/code_space. `resource_identifier` is a persisted `GeneratedField` of
  `code_space || code` — a display/transport convenience only, never an identity key (D2).

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

## Which identifier is already equated with what

The consistency check demanded by the issue — these are the existing equations, each with
the scope in which it is trusted. Read through D1: the first block is **document**-identity
usage (fileIdentifier answering "which XML document?"), which is legitimate; the legacy
rows which answer "which dataset?" with a fileIdentifier are compatibility surfaces, not
identity rules:

| Place | Equation | Class |
| --- | --- | --- |
| `custom.py get_or_create_metadatarecord` / `_record_of` | harvest upsert key: one row per (record type, file_identifier), newer `date_stamp` wins | document merge/versioning |
| `csw/views.py get_record_by_id`, `csw/queryables.py` (`identifier` queryable), `csw/elementsets.py` (`dc:identifier`) | the CSW endpoint's record identifier **is** `file_identifier` | document identifier (CSW `csw:Identifier` identifies the record document) |
| `harvest.py` provenance / `models/harvest.py` | `origin_url` is built via `get_record_by_id_request(id=file_identifier)` — fileIdentifier is treated as this catalogue's request identifier | document address |
| `RemoteMetadata.create_metadata_instance` | created record looked back up by file_identifier after persistence | document lookup |
| `registry/helper/preview.py registered_previews` | a CSW's advertised record is matched to registry records by `file_identifier` **scoped to records harvested through this very CSW** (`harvesting_job__service=service`) | document lookup, fenced |
| `AbstractMetadata.file_identifier` help text | registered element: `PK(Layer/FeatureType)` = fileIdentifier of the document MrMap generates for it | generated-document convention |
| `mapbender_compatibility` remote search | `"id"` and `"datasetId"` are the parsed `file_identifier` (its `local_search` answers `"id": record.pk` instead — an existing drift, not fixed here) | legacy dataset-level surface on a document identifier |

`docs/live-service-previews.md` documents the preview row's user-facing rule. The one place
which may compare a foreign identifier to `file_identifier` today is therefore a preview
lookup fenced by harvest provenance — that fence is promoted to a rule in D4. Wherever a
**dataset** is addressed in new code, the key is the `(code, code_space)` pair (D1), not the
file_identifier; the MapBender remote surface stays byte-compatible as legacy and is not a
pattern to copy.

## Relationship and provenance inventory

- Reference kinds in harvested ISO service records are **extracted but not persisted**: the
  #981 extraction API (persistence-independent `XmlMapper.mapped_values()`) maps them as
  `_values` specs in `mappers/configs/iso_access.py` — `OPERATES_ON` (`@uuidref` and
  `@xlink:href` kept apart as two evidence strands), `COUPLED_RESOURCES` (identifier,
  operation name, scoped name), `ONLINE_LINKS` and `DISTRIBUTOR_ONLINE_LINKS` (the
  `gmd:distributionInfo` `gmd:onLine`/`gmd:CI_OnlineResource` links with linkage, protocol,
  application profile, name, description, function) and `SERVICE_OPERATIONS` (operation
  name, DCP, `srv:connectPoint` linkage). The mapped document carries them as ordered lists
  of plain dicts with the original external values; no model stores them yet. #670 defines
  their resolution, #983 persists them (D8).
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
  (`registry/models/guardian.py`, migrations 0030/0031, completed for the remaining models
  by 0044/0045). New coupling tables must use typed FKs the same way, not
  `GenericForeignKey`.

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

**D1 — Dataset identity.** The identity of a dataset is the ISO **resource identifier**: the
citation identifier of its dataset description
(`.../gmd:citation/gmd:CI_Citation/gmd:identifier/gmd:MD_Identifier/gmd:code`, inventory
above) as the pair `(code, code_space)`. The ISO `fileIdentifier` identifies the **metadata
document**, not the dataset: distinct documents with the same resource identifier describe
one dataset and must be preserved with their own provenance and version information; they
are never silently merged into each other and never merged into the dataset's registered
representations. The database PK remains the internal JSON:API resource identity; the title,
the layer/feature type name and endpoint URLs are never substitutes; Layer and FeatureType
keep their own service-scoped identities (D3). Records MrMap authors keep the uuid4-default
fileIdentifier; a parsed value is never rewritten. The resource identifier is stored exactly
as parsed into `code`/`code_space`; documents whose citation carries no identifier are
broken-but-preserved records (empty code/code_space, excluded from the unique constraint),
visible for curation, never identity-addressable.

**D2 — Preserve the original; compare as a pair.** `file_identifier`, `code` and
`code_space` are stored exactly as parsed (max 1000 chars, no case folding, no URL-semantic
normalization). Identity comparisons use the **(code, code_space) pair**, never a derived
concatenation: the persisted `resource_identifier` column (`code_space || code` without a
separator) is collision-prone (e.g. `("a/b", "c")` vs `("a", "/b")`) and serves display and
transport only. Normalization happens only in comparison rules that name their steps (D4),
never in the stored identity.

**D3 — Identity classes, no cross-class equality.** (a) *document* identity: fileIdentifier
of an ISO record, per-table unique index (document-level, see inventory); (b) *dataset*
identity: the `(code, code_space)` pair of a dataset description (D1); (c) *service*
identity: the registered `WebMapService`/`WebFeatureService`/`CatalogueService` row (PK),
versus a *merely advertised* endpoint which is a URL plus protocol hint and has no identity
until registered; (d) *registered resource* identity: the `Layer`/`FeatureType` row (PK)
with a name (`ServiceElement.identifier`) unique per owning service; (e) *representation*:
the WMS layer and the WFS feature type of the same dataset are distinct resources whose only
shared identity is evidence pointing at the same dataset (D1 identity, resolved per D4; #986
groups them; nothing equates them). **Metadata alone is not evidence of an
operationally accessible map representation.** A dataset without a verified registered
representation is not a **managed operational MrMap registry resource**; its metadata
remains discoverable, editable and publishable through CSW. **OWS Context is not
registry-only:** a user may include a standards-compliant external public offering
without registering its service, and may include authorized private offerings
subject to content-inherited permissions. The OWS Context conceptual model and
GeoJSON encoding (OGC 12-080r2 / 14-055r2) permit diverse service and content
offerings (not only WMS/WFS), including their operations, inline/by-reference
content and extensions. Valid external offerings can be represented, imported,
persisted and exported even if their operation has no implemented viewer renderer;
only supported, safe and authorized operations can actually be executed/rendered.
An external context offering does **not** become a registered service or a verified
ISO dataset/MetadataRelation association by being included in a context.
A conflation of dataset identity with a layer or feature type, or with a
metadata document, is rejected. (Maintainer decision #1314, 2026-11-13.)

**D4 — Reference resolution rules (when may which be compared?).** The #981 extraction
carries every original value below; which of them may be *compared*, and against what, is
this table:

| Reference kind (extraction spec) | Identifies | May be compared against | Only under |
| --- | --- | --- | --- |
| `srv:operatesOn/@uuidref` (`OPERATES_ON`) | a metadata *document* by uuid | nothing **automatically** | persisted as a declared document reference with its provenance; not used for automatic dataset resolution (a uuidref names a document, and documents are not datasets); visible for curation only |
| `srv:operatesOn/@xlink:href` (`OPERATES_ON`) | a metadata *document* at a URL | the dataset behind the referenced document, via its parsed `(code, code_space)` **not** a URL-string comparison: the href is not directly equal to any stored field. Resolution of the **dataset** takes the resource identifier — where the href itself carries it in citation-identifier shape it goes through the same `_split_code` rule, else the target document is taken (an already-harvested one whose `origin_url` is that href, else a documented fetch + parse) and **its** identifier yields `(code, code_space)`; scoped to the catalogue provenance of the source record (`harvested_through`/`HarvestingJob.service`), mirroring `registered_previews` |
| `srv:coupledResource/srv:SV_CoupledResource` identifier (`COUPLED_RESOURCES`) | an operation-resource binding | nothing | kept as declared evidence with the original identifier and scoped name only; `SV_CoupledResource` is not a valid specific profile in the relevant metadata profile, so it never resolves a dataset automatically |
| WMS `LayerName` / WFS feature type name | a representation of one service | `ServiceElement.identifier` | within a single registered service (where it is unique); never across services |
| distribution `gmd:onLine` linkage — `gmd:distributionInfo/gmd:MD_Distribution/gmd:transferOptions/gmd:MD_DigitalTransferOptions/gmd:onLine/gmd:CI_OnlineResource/gmd:linkage/gmd:URL` (`ONLINE_LINKS`, incl. the `gco:CharacterString` encoding #981 accepts) | an advertised endpoint | registered service URLs (candidate discovery, #671) | as candidate evidence only; a URL never becomes a service or a layer by comparison alone; `srv:connectPoint` (`SERVICE_OPERATIONS`) is the same candidate evidence on operation level |

A reference to an absent target stays **unresolved** (visible, queryable); silent merging is
prohibited. Distinct documents describing one dataset (same `(code, code_space)`, different
fileIdentifier) are **expected**, not a collision: both stay visible with their own
provenance. The collision case is *one fileIdentifier claimed by distinct documents* (two
catalogues delivering different documents under one identifier): that is ambiguous
**document** identity — both provenances stay visible, nothing merges them and nothing picks
"the newest" across catalogues. Today the per-table document-unique index plus the
`date_stamp` guard makes such a case merge into one row whose provenance answers only the
last writer, with DUPLICATED flagging only *within-job* redelivery; preserving the distinct
documents is a persistence task for #983 with explicit states, not a redefinition of
identity here.

**D5 — Relationship taxonomy.** A *declared* relationship is directional, source-owned and
persisted with the identity of its source document, its reference kind (D4) and provenance;
the original external value is kept beside the resolved target. A *derived* relationship is
computed traversal and is never persisted as fact — `self_pointing_*` (through
`MetadataRelation`) is the existing instance of that; new bidirectional APIs (#671/#984) read
declared rows in both directions. Discovery never creates `MetadataRelation` rows without
evidence (epic acceptance criterion). The existing MetadataRelation publication policy
(imported evidence / curated publication / local only) stays as is. Only the established
relationship kinds are reused — service metadata → dataset metadata (including harvested
`operatesOn` couplings), registered WMS Layer / WFS FeatureType → dataset metadata, and
WMS/WFS/CSW → their service metadata — plus relationships actually discovered by harvesting;
consumers such as MapContext membership (#992) sit **beside** this graph and are not
expressed as generic ISO dataset associations.

**D6 — Identity of coupling rows.** `MetadataRelation` remains the join of *registered*
objects (evidence-backed only). ISO-declared references to documents/endpoints get their own
persisted, typed, directional rows (D8) instead of growing more nullable columns onto
MetadataRelation; its FK-column-per-type shape is the precedent for "typed FKs, check
constraint over the allowed combinations" that new tables copy. The #981 `_values` lists are
the input of that persistence; nothing about the extraction order or storage is decided here.

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
next free registry migration number is **0047** (current head:
`0046_explicit_keyword_through_models.py`; 0043 was skipped historically).

- table **metadata reference** (one row per source-document-declared reference): typed FK
  `source_record` to one of the three record tables (FK per kind + CHECK, or one table per
  kind if the check constraint becomes unwieldy), `target_uuidref` (original value),
  `target_href` (original value), `target_code`/`target_code_space` (resolved dataset target
  **and** the original values they were parsed from), `reference_kind` (PositiveSmallInt +
  SmartIntegerChoices: OPERATES_ON_UUIDREF, OPERATES_ON_HREF, COUPLED_RESOURCE,
  ACCESS_ONLINE, SERVICE_OPERATION — mirroring the #981 extraction specs), `protocol` and
  `operation` hints (PositiveSmallInt + SmartIntegerChoices, original strings beside them),
  `resolution_state` (PositiveSmallInt + SmartIntegerChoices: UNRESOLVED, RESOLVED,
  AMBIGUOUS, STALE), resolved typed FKs `dataset_target`/`service_target`/
  `element_target`/`endpoint_target` (nullable, CHECK: state RESOLVED ⇒ exactly one set; a
  `dataset_target` is only ever set through the `(code, code_space)` route of D4),
  provenance `origin` + `source_harvesting_job` FK + `origin_url`-style source document URL,
  `is_internal`-equivalent ownership flag.
- table **advertised endpoint**: original `url` (preserved byte-for-byte), normalized `url`
  column for lookups, protocol/version/operation hints as enums with original strings, typed
  FK `advertised_by_service`/`mentioned_in_record`, plus the same resolution state; a
  resolved endpoint FK to a registered service exists **only** after an actual registration —
  discovery never registers.
- uniqueness: (source record FK, kind, original target value) — a document declares a target
  once; reverse lookup indexes: `(target_code, target_code_space)`, `(normalized url)`, and
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

**D10 — Ambiguity and duplicates, on the two identity axes.**
*Document axis*: duplicate delivery inside one harvesting job keeps the existing DUPLICATED
collecting-state treatment. Same fileIdentifier + same `(code, code_space)` = same document
redelivered, newest `date_stamp` wins (existing rule). Same fileIdentifier from different
catalogues with differing content = ambiguous document identity: the persisted reference rows
carry the provenance of each declaration and answer AMBIGUOUS until a curator resolves one —
nothing merges them silently. Same fileIdentifier with a changed `(code, code_space)` = a
document version that re-points at another dataset: the document row follows `date_stamp`
(existing rule) and derived reference rows re-resolve, keeping the previous resolution in
history. *Dataset axis*: multiple documents with one `(code, code_space)` are normal
operation — they describe the same resource in different versions, and every document stays
a distinct row with its own provenance and `date_stamp`; a dataset is the union of its
descriptions, and "which document is newest" is never asked across document identities.

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
`(target_code, target_code_space, resolution_state)` and `(normalized url, resolution_state)`
on the reference/endpoint tables, not a new materialized view (the projection removal of
#851/#855 must not be re-litigated).

## Test obligations handed to the children

#983 implements and explicitly tests: resource-identifier `(code, code_space)` dataset
identity and the document-vs-dataset collision rules (D1, D2, D4, D10), reference-kind
matching per the D4 table including the href fetch/parse obligation, both import orders,
collision visibility, backfill from stored XML; #671 tests the reverse-lookup index decision
of D12; the enum convention of D9 is checked by review of #670/#983 models against the
SmartIntegerChoices requirement. No conflation of dataset identity with a WMS layer or WFS
feature type (epic acceptance criterion) is asserted by D3, and D3's usability rule (metadata alone is not an operational representation;
registered resources are managed, while supported and secure external OWS Context
items need no registration) is asserted at the API/viewer boundary and in
MapContext import/export tests (#1280/#1284).
