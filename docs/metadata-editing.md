# Metadata editing in MrMap — the implemented design

This is the current documentation of how a metadata record is authored in MrMap:
the write path and what it guarantees, how authoring profiles are created, when
and how validation runs, what a save does to the served document, and what v1
deliberately does not do. It was written against the merged foundation of the
epic **metadata-editor** ([#1239](https://github.com/mrmap-community/mrmap/issues/1239)):
the API, write mapper, validation and publish (#1240–#1244) and the full-screen
editor (#1245) are implemented and described here as built; the remaining
stories (#1246–#1249) build on exactly these contracts and are marked where
they are still in delivery.

The research and gap analysis behind these decisions — the GeoNetwork study,
the evidence grading and the mockups — remains in
[metadata-editor-design.md](metadata-editor-design.md); the open questions it
listed were answered in the [review of PR #1238](https://github.com/mrmap-community/mrmap/pull/1238),
and this document states what became of them.

One cross-cutting rule from that review shapes everything below and is not
repeated at every bullet: **every endpoint follows the json:api default CRUD
behaviour — there is no bespoke action endpoint anywhere in this design**
([r4537341050](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537341050)).
That decision is why there is no `/validate` call, no `/publish` call and why
raw XML is an attribute (or will be — §1.4), not an endpoint.

## 1. The write path and its guarantees

### 1.1 What a write is

A metadata record is authored through the ordinary json:api resources:

- `/api/registry/dataset-metadata/`, `/api/registry/service-metadata/`,
  `/api/registry/application-metadata/` and their nested routes;
- POST creates a record, PUT/PATCH edit one — permissions are the existing
  guardian object permissions (`canEdit`, `canDelete`), no new role concept;
- whether a deployment opens writes at all is the activation gate
  `MRMAP_METADATA_EDITOR_WRITES_ENABLED` (on by default since #1244); reads
  always answer, and no permission a user could hold bypasses the gate.

The editor never ships hand-written XML for the mapped fields. A write PATCHes
**model fields**, and the backend regenerates the affected elements of the
stored ISO document (`xml_backup_file`) through the write mapper
(`MDMetadataXmlMapper.write_mapped_values`, #1242). That document is what the
CSW serves, so one save moves the row, the stored document and the CSW answer
together.

Two refusals keep the row and the document from ever drifting apart
(`RecordWriteSerializerMixin`, #1241, fail-closed posture of #1244):

* a payload naming a field the model pins `editable=False`
  (`file_identifier`, `date_stamp`, `origin`, `is_broken`, …) is answered with a
  400 naming every offending member — not the silent drop a `read_only` DRF
  field performs; the refused set is derived from the model, it is not a second
  list to maintain;
* a payload naming a field the configs **read** from the document but the write
  mapper can not **write** back (the citation
  identifier) is refused with a 400 naming the member. Bounding geometry and
  time extents joined the writable set with #1246: their configs answer a
  ``_reverse_parser`` which serializes the geometry as
  ``gmd:EX_GeographicBoundingBox``/``gmd:EX_BoundingPolygon`` and each time row
  as a ``gml:TimePeriod`` fragment. The set comes from the
  configs themselves (`publish.non_roundtrippable_fields`), and accepting such
  a write would commit into the row while the served document silently kept its
  old value.

### 1.2 What survives an edit, what regenerates

The write mapper is the inverse of the read mapper and works on the stored
document in place (`write_mapped_values`):

* **Everything the configs do not map keeps its bytes.** This is the guarantee
  for profile-specific content the form never renders — asserted against this
  repository's own namespace-prefixed GDI-DE fixtures, the lesson GeoNetwork
  teaches by contrast (its converter regenerates a touched section wholesale and
  loses unknown content inside it).
* A mapped element that exists gets its text or attribute replaced; a missing
  one is created at the position the element order table names — the same
  positions a harvested document carries them in.
* A value the document already carries is left alone (compared both as
  serialized text and through the field's `_parser`), so writing back freshly
  extracted values changes the document not even in a date's representation.
  A read-write-read round trip is byte-stable.
* A field missing from the payload, a value of `None` and an empty list all
  mean **not written** — removing mapped content must become an explicit act
  (a later issue), never a side effect of a partial PATCH.
* Multi-valued fields pair values with document matches by position; surplus
  values create new rows at the config's `_reverse._row`, surplus matches are
  removed only while the field carries values at all.
* A field whose config names no `_reverse_parser` is skipped with a warning —
  never guessed at. Such fields are refused as writes already at validation
  time (§1.1), so a warning is a config-development signal, not curator-facing
  behaviour.

### 1.3 One ISO interpretation layer

The mapper configs in `registry/mappers/configs/` are the only ISO mapping
(#981/#982). The editor does not get a second mapping: the ISO 19139 element
path of every **writable** mapped field rides the OpenAPI schema as an
`x-iso-path` extension, injected by a drf-spectacular postprocessing hook
(`registry/schema.py`) that re-reads those very configs. The path the editor
displays and the path the write mapper writes can therefore never disagree, and
`tests/django/registry/tests_metadata_profile.py` re-walks the configs and
asserts the served paths against them. Fields pinned read-only appear with
`readOnly: true` and carry no path.

### 1.4 Raw XML is a writable attribute, not an endpoint

The stored document is readable today (the record's XML download); it is not
writable yet. The design decision — from the same review that killed the
standalone validate endpoint — is that when the XML source view ships
([#1247](https://github.com/mrmap-community/mrmap/issues/1247)), raw XML becomes
a **writable json:api attribute of the record resource**, going through the same
validation and publish path as a mapped-field PATCH (§5 of the research
document as revised by [r4537341050](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537341050)).
There is no custom XML-write endpoint and none will be added: a resource
endpoint that needed a bespoke verb would be the first violation of the rule
this design was built under.

## 2. Authoring profiles: the model, seeded by migration

Profiles are **data**, not code ([decision 2, r4537433349](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537433349)).
`registry.models.metadata.MetadataProfile` is a Django model with:

| field | content |
| --- | --- |
| `name` | machine name, unique — e.g. `iso19139-generic` |
| `label` | display name the editor header renders |
| `sections` | JSON list: the ordered sections of the editor's section rail; each section names the fields it groups and, per field, the requirement `mandatory` / `recommended` / `optional` |
| `rules` | JSON list: the structural rules validated on save (§3) |

The model and the v1 profile are seeded by migration `0049_the_profile_of_metadata_is_data`
under the fixed UUID `0180721f-bf34-4281-b367-648a74dd8ff9`, and migration
`0052_the_generic_profile_names_its_rules` fills its ISO 19139 rule set
(§3.4). Migration `0050` gives every record table (and its history mirror) a
`profile` relationship; existing rows answer `iso19139-generic`. The column is
deliberately nullable with no default — creation paths (mapper persistence and
api POST) look the seeded row up via `MetadataProfile.generic()` instead of
naming it in a column default.

The seeded generic sections are `identification`, `extent`, `distribution` and
`quality`; their mandatory markers follow the unconditional mandatory elements of
the ISO 19139 schema (title, abstract, keyword, contact, language,
characterSet). Read-only fields have no entry in a section — the editor takes
them from the schema's `readOnly` marker, so there is one source per fact.

**Adding a GDI-DE or INSPIRE profile is a row, not a release.** It arrives as
data — a data migration (like 0049/0052) or, once profile administration
exists, an api write — carrying its own `sections` and its own `rules` with its
own rule families (§3.5). No frontend change, no code branch.

What deliberately does **not** live on the profile: the ISO element paths of the
mapped fields. They stay in the mapper configs and reach the client from there
as `x-iso-path` (§1.3); a second copy on the profile row would drift.

**Rule transport to the client** was decided after the review — asked as Q1 on
[#1243](https://github.com/mrmap-community/mrmap/issues/1243) and answered option
C, hybrid
([audit](https://github.com/mrmap-community/mrmap/issues/1243#issuecomment-6804023599)):
attribute-level constraints keep riding the OpenAPI schema (the SPA already
maps `maxLength`/`pattern`/`required`/`format` to react-admin validators),
while ISO structural rules travel on the profile resource, fetched with the
record (`include=profile`, optionally `fields[profile]=rules`). The profile
resource at `/api/registry/metadata-profiles/` is ordinary json:api CRUD;
writing profiles is an operator task today.

## 3. The validation contract

### 3.1 Where validation runs

There is **no standalone validate endpoint** ([r4537341050](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537341050)).
The profile's structural rules are evaluated **as part of the normal PUT/PATCH
write** (`RecordWriteSerializerMixin.validate`), before DRF stores anything.
Editor, batch edit (#1249) and a future CSW `Transaction` handler therefore get
the same verdict through one enforcement path. The frontend pre-validates from
the same rule objects it fetched (§2) to answer faster — how much of the
verdict the client can honestly know is §3.2; the server's verdict on the write
is authoritative.

### 3.2 What the rules run over

Rules are evaluated over the **resulting document** — the record's stored
document with the row's values and the payload's values written through the
publish seam in memory (`publish.build_resulting_document`, #1244) — never over
a disconnected representation. What validation evaluates is literally what the
publish would persist, so a payload can not pass validation and then produce a
violating document. Only the server can build that document — it needs the
write mapper — so the client's pre-validation (§2, built for #1245 as
`MetadataEditor/rules.ts`) honestly checks what it knows: the presence of each
rule's `field` in the values a save would send, merged with the server's verdict
by rule id. The server's answer on the write stays authoritative.

Two fail-closed postures belong to this contract (#1241, kept by #1243):

* a rule set this version can not assess (wrong shape, unknown severity, a
  field the overlay can not place) **refuses the write on every verb** — an
  unevaluated rule set must never answer a payload as validated;
* a document the seam can not build (the record can not be located in its own
  document, the write mapper refuses the combination) refuses the write for the
  same reason.

A record that serves no document yet — a POST whose first document this very
save publishes at commit — has nothing for the document rules to govern at
validation time; it joins the rule regime with its next write.

### 3.3 Findings are json:api error objects

A rule is a dict carried on the profile row (`registry/mappers/rules.py`
defines the shape):

```json
{
  "id":       "iso19139-title",
  "family":   "iso19139",
  "severity": "error",
  "field":    "title",
  "assert":   "count(//*[local-name()='MD_Metadata']/*[local-name()='identificationInfo']//*[local-name()='title'][normalize-space()]) > 0",
  "message":  "The identification section must carry a title (gmd:citation/gmd:title)."
}
```

Every `assert` is a boolean XPath 1.0 written in the prefix-independent
`local-name()` form: a document may bind the ISO namespaces to any prefixes,
and the expression must evaluate over any of them. The form stays
browser-portable — DOM XPath has no access to a document's prefix table either
— even though the shipped editor pre-validates field presence rather than
running the XPath itself (§3.2).

An `error` finding blocks the save; a `warning` never does. A refused save
answers one **json:api error object per finding** (`rules.findings_to_errors`):

* `source.pointer` — `/data/attributes/<camelCaseField>` or `/data` — is the
  member the editor jumps to (the merged findings rail does exactly this);
* `rule` cites the rule id, so the client can match its own copy of the rule;
* `severity` grades the finding;
* `meta.family` plus `meta.severityCounts` (string counts) carry the per-family
  grouping for consumers that group — the GeoNetwork lesson that families, not
  raw engine text, are what a curator reads; the shipped v1 rail orders errors
  before warnings and shows each finding's own message, never engine output.

**No rule-engine text ever surfaces to the client.** A rule whose XPath call
itself breaks is answered with severity `error` and a detail naming the rule
id; the traceback goes to the server log (acceptance criterion of #1243 —
GeoNetwork shows its curators raw XSLT failures, this must not).

### 3.4 The v1 rule set

The generic profile ships the ISO 19139 presence family (seeded by migration
0052): `title`, `abstract`, `keyword`, `metadata-contact`, `language` and
`charset` must be present in the resulting document, and every named
`CI_ResponsibleParty` must carry at least one of organisation, individual or
position name (the ISO 19115 constraint) — all severity `error`. A missing
`dateStamp` grades as a `warning`, because the field is read-only for the
curator and a blocker would lock the record out of every save.

### 3.5 How later rule families register

GDI-DE and INSPIRE rules join **as data with their own `family` strings**, not
as code branches: the evaluator, the error-object shape and the client's rail
grouping are already family-agnostic (`meta.family`/`meta.severityCounts`).
Adding a family is adding rule dicts to a profile (§2); v1 ships ISO 19139 only
([decision 3, r4537437616](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537437616)),
and nothing in the written contract has to change when a later family joins.

## 4. The save/publish lifecycle

### 4.1 Atomic publishing only in v1

A successful, validated save **is** the publish
([decision 1, r4537429688](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537429688)).
`create` and `update` wrap the row save and the publish seam
(`registry/mappers/publish.py`) in one transaction (DRF opens none itself):

* the fields, the validation verdict and the regenerated `xml_backup_file`
  commit together or not at all; after the commit the CSW serves exactly what
  was saved;
* a **refused write changes nothing**: on rollback the row keeps pointing at
  the old document (a file written before the rollback stays as unreferenced
  garbage of the media storage — it is never served);
* there is no draft document, no editorial state column, no second publish
  step — the document is built *from the row*, so served and stored can only
  disagree while a transaction is still running.

POST publishes the record's first document the same way: a created record
without one would fail the CSW page it appears in, so the seam generates a
minimal skeleton document of the record's kind and fills it like any other
document. The seed is **not a template** — template administration is a decided
v2 epic (§5).

The values the document is written from come from the **row**, not the payload:
model-maintained fields (the bumped `date_stamp`, the server-assigned
`file_identifier`) travel with it, and a record whose row and document had
drifted apart is healed towards the row.

### 4.2 `is_customized` and `date_stamp` keep protecting against harvest

The harvest overwrite gate of `get_or_create_metadatarecord` replaces a stored
record only when the freshly parsed document carries a **newer `date_stamp`**
than the row. An editor-style save sets `is_customized=True`
(`AbstractMetadata.save`) and bumps `date_stamp = now()`
(`MetadataRecord.save`, #1241) — so after any edit, a re-harvest of the
catalogue's older document cannot overwrite curated content. That bump is
exactly what "the harvest overwrite gate is untouched" means for an api write:
the same side effect an ORM save already had. Harvesting's own writes pass
`mark_customized=False` (#858) and keep both flag and stamp at the parsed
document's values. A created record arrives with the gate's stamp a parsed
record would carry: `date_stamp` gets its creation default, and the first
editor update bumps it.

### 4.3 Concurrency

Last-write-wins ([decision 6, r4537458987](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537458987)):
no editing lock is taken, no revision token is answered; the last committed
publish is the document. Editing locks are out of scope for v1 (§5).

## 5. Out of scope for v1 — each with the deciding review comment

| out of scope for v1 | what v1 does instead | deciding comment |
| --- | --- | --- |
| **Draft/publish split and per-section conflict resolution** — no draft state, no harvest-during-edit conflict UI (mockup `proposed-12` is a v2 candidate) | atomic publishing: the validated save is the publish (§4.1) | [r4537429688](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537429688) |
| **Editing locks** — no lock is taken, no token answered | last-write-wins (§4.3); the harvest gate (§4.2) keeps protecting curated content | [r4537458987](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537458987) |
| **GDI-DE / INSPIRE rule sets** — no GDI-DE or INSPIRE conformance verdict in v1 | ISO 19139 rules only (§3.4); families register as data later (§3.5) | [r4537437616](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537437616) |
| **Template administration** — no template catalogue, no template editing | creating a record starts blank from the profile (§4.1); templates are a separate v2 epic | [r4537453636](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537453636) |
| **Background batch execution** — no Celery batch jobs, no job UI | batch editing (#1249) is a synchronous frontend-side bulk action over a selection, react-admin functionality only, per-record PATCH | [r4537448116](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537448116) |

Two further rejections from the same review are structural rather than scope
items, and are already baked in: a **standalone validate endpoint**
([r4537341050](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537341050))
and **fully new React components** in the editor
([r4537359916](https://github.com/mrmap-community/mrmap/pull/1238#discussion_r4537359916)
— React Admin components, extended only where needed, which is how the editor
of §6 is composed). Multi-step
approval workflows and ISO 19115-3 authoring are out per the epic's acceptance
criteria.

## 6. Where the contracts are pinned

| contract | implementation | tests |
| --- | --- | --- |
| profile resource, record→profile link, `x-iso-path`, readOnly markers (#1240) | `registry/models/metadata.py`, `registry/serializers/metadata.py`, `registry/schema.py`, migrations 0049–0051 | `tests/django/registry/tests_metadata_profile.py` |
| record CRUD, refused members, write-back semantics (#1241, #1242) | `registry/serializers/metadata.py` (`RecordWriteSerializerMixin`), `registry/mappers/xml_mapper.py` | `tests_metadata_record_writes.py`, `mappers/tests_write_mapper.py` |
| rules on save, json:api error objects (#1243) | `registry/mappers/rules.py`, migration 0052 | `tests_record_validation_on_save.py` |
| atomic publish, harvest gate (#1244) | `registry/mappers/publish.py`, `MetadataRecord.save` | `tests_metadata_record_publish.py` |
| full-screen editor: route not dialog, section rail, Simple/Advanced, findings rail, pre-validation (#1245) | `frontend/src/components/Resource/Generic/MetadataEditor/` | `MetadataEditor.spec.tsx`, `rules.spec.ts`, `sections.spec.ts` |

The full-screen editor (#1245) consumes these contracts without adding new
ones, and the stories still in delivery — widgets (#1246), XML source view
(#1247), blank creation (#1248), batch editing (#1249) — are expected to do the
same: anything they need beyond what is documented here would be a design
change, not an implementation detail.
