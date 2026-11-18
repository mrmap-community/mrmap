.. _metadata-transform-inventory:

Metadata transform inventory: what importing one ISO document costs
====================================================================

Epic #1408 / phase-C review #1415 walked the parse -> map -> persist -> couple
stages of an imported ISO 19139 record -
``MDMetadataXmlMapper.from_xml``, ``XmlMapper.xml_to_django``,
``PersistenceHandler.persist_all``, ``get_or_create_metadatarecord``,
``md_metadata_file_to_db`` and ``couple_document`` - and asked which XML
mapping, transform, serialization and reference-coupling work is semantically
identical and repeated. This page is the inventory its acceptance asks for;
the deterministic half lives in
``backend/tests/django/registry/mappers/tests_transform_counts.py``, which
counts the transformations at the seams the code performs them at.

This page covers the non-ORM work only. Confirmed database-side findings are
filed against the task-SQL epic's ORM issue #1392, not implemented here; the
harvesting bulk-write answers of #817 (lookup upserts in key order with
``ignore_conflicts``) and the bounded import chunks of #859 stand untouched.

Where one document goes in
---------------------------

Three store paths hand documents to the same import code, and all three store
*one standalone ``MD_Metadata`` document per file*:

* a CSW page answer: ``HarvestingJob._store_page`` cuts every ``MD_Metadata``
  out of the ``GetRecordsResponse`` and stores it as its own file;
* a filesystem import: ``_store_dropped_md_metadata`` stores each parsed
  ``MD_Metadata`` the same way;
* a registration reference: ``collect_reference`` stores the advertised
  document as downloaded (#1410 shares the *fetch* of one url between the
  references advertising it; each reference still owns its copy).

So the imported file normally *is* the record's document - the one shape fact
that makes the first reduction below safe.

Transformations per single-document import (after #1415)
---------------------------------------------------------

===================  ============================================================
Stage                Work per imported file
===================  ============================================================
parse                one ``etree.fromstring`` of the stored document
detach copy          none for the root-node document; one serialize + one
                     reparse per node that must be cut out of a wrapper
hierarchyLevel       one traversal, by ``from_xml``; the bucket check of a
                     catalogue run reads the answer carried on the mapper
map                  one ``xml_to_django`` traversal; persistence and the
                     #981 extraction read its result, no second pass
backup serialization none when no record is written; one
                     ``serialize_document`` when a record is created or
                     updated (shared by all written records of the run)
cache                the parsed instances are released with the import
                     instead of being held until the TTL of the global cache
===================  ============================================================

What #1415 reduced
--------------------

* **The detach copy is skipped for the document root.** ``from_xml`` used to
  serialize and reparse *every* ``MD_Metadata`` node so that each mapper
  holds a standalone document; for the root node of a standalone document the
  copy is structurally identical, and that is the shape of every stored
  harvest file and every downloaded advertised document. The copy still runs
  for a node below a wrapper and per node of a multi-record document - the
  deterministic counts of the paths, the backup and the per-node mapper
  semantics are unchanged.
* **The backup is serialized only when a record is written.**
  ``get_or_create_metadatarecord`` used to run ``serialize_document`` (and
  decode it) once per handler call *before* knowing whether the catalogue's
  answer changed anything; the unchanged path - re-harvesting a record
  nobody edited, or the ninth reference coupling to an already-imported
  document - paid a whole-document serialization for a backup nobody wrote.
  A written record still gets exactly one backup, and several written records
  of one document share the one serialization.
* **The bucket check reads the mapping's detection.** The post-filter of the
  application bucket (#827) ran its own ``hierarchyLevel`` traversal right
  after ``from_xml`` had run the identical traversal to select the mapping
  config. ``from_xml`` now carries the detected level on the mapper (never a
  forced ``hierarchy_level``: a caller's interpretation does not travel as
  the document's own answer) and the check reuses it.
* **An import releases what it mapped.** The parsed instances live in the
  process-global ``GlobalXmlCache`` under the fresh uuid of their mapper and
  are read by nothing outside the import that stored them - the TTL (#1028)
  only bounds the retention, it does not need it. ``md_metadata_file_to_db``
  and ``couple_document`` release their mappers' entries when the import is
  through, whatever its outcome; a crashed attempt's entries still expire
  with the TTL.

What was reviewed and deliberately not changed
-----------------------------------------------

* **Two keyword-quality evaluations per import** (#919): the first runs on
  the *parsed* instance so a created record rides its indicators out in the
  one write #858 established; the second answers whether the *stored* row
  differs, which is the only write trigger on the unchanged path. Different
  objects, different answers - not duplicated work.
* **One ``PersistenceHandler`` per mapped instance in ``md_metadata_file_to_db``.**
  Each ``persist_all`` re-reads the whole mapper cache, so a config producing
  a second top-level instance would persist everything twice. Every ISO
  config names exactly one record spec, so today one handler runs per file;
  the count test pins that one read and one persist belong to one file. If a
  future config adds a second top-level spec, the handler-per-instance loop
  is the first thing to revisit.
* **The mapping count of repeated shared references** (#1410's shape): N
  elements advertising one url are N deliveries, and each maps its own copy.
  Mapping across deliveries would need a cross-run cache, which must not
  grow here; the per-delivery mapping is also what keeps each delivery's
  import-error ledger, provenance and per-element coupling whole. The cadence
  test pins: parses = deliveries, backup serializations = record writes.
* **``_persist_get_or_create`` and the chunked import** (#817, #859): the
  bulk lookup upserts in key order and the bounded chunks stay exactly as
  they are; nothing here reintroduces a per-row insert loop.

Confirmed SQL findings (for #1392, not implemented here)
---------------------------------------------------------

* ``get_or_create_metadatarecord`` calls ``build_final_key_map`` twice - once
  for the persisted rows, once for the parsed instances - which is two
  ``SELECT`` s of the same rows through the same OR-chain filter; the
  injection of the ``_parsed``/``_custom_state`` attributes out of the parsed
  instances is a pure in-memory mapping.
* ``build_final_key_map`` asks the database with one ``Q`` per instance OR-ed
  together; the per-table key shape could become a bounded bulk plan.
* The ORM side of the shared-reference cadence: every coupling re-runs the
  lookup-table upserts, re-``set``s the record's M2M relations and runs the
  superseded-relation bookkeeping even when the record row is not written.

Each is a database-side question of the task-SQL epic; the review comments
linking them are on #1392.
