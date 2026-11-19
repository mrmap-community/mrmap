.. _update-refresh-policy:

============================================
What a service update may skip and must redo
============================================

Epic `#1408 <https://github.com/mrmap-community/mrmap/issues/1408>`_ phase C
(`#1413 <https://github.com/mrmap-community/mrmap/issues/1413>`_) asks which
downstream work an update run may skip when the service did not change, and
which it must repeat. This page is the answer; the deterministic tests behind
its rows are
``backend/tests/django/registry/models/tests_update_refresh_policy.py``, and
the collection rows which the update walks through (#1274) are answered by
``backend/tests/django/registry/tasks/tests_metadata_collection.py`` and
``tests_collect_reference.py``.

The one distinction the whole table rests on: **the capabilities hash proves
the capabilities, nothing else.** ``document_equals``
(:meth:`~registry.models.document.DocumentModelMixin.document_equals`) hashes
the stored capabilities document against the freshly fetched one. Equal bytes
prove the *capabilities* did not move; they say nothing about the ISO
documents the capabilities point at, which live on somebody else's server and
can be republished at any moment under the very same URL. A run which decides
"nothing to do" on capabilities equality and skips the advertised references
would serve stale records as current - what the epic forbids.

The decision table
==================

Every row is one run of one service. The capabilities document is always
fetched: without it there is nothing to decide against. What the row decides
is the work *behind* that request.

.. list-table::
   :header-rows: 1
   :widths: 22 30 26 22

   * - Situation
     - Skipped
     - Still done
     - Why
   * - Capabilities byte-identical to the stored document
     - candidate staging: no parse (``OGCServiceXmlMapper.from_xml``), no
       persistence of a candidate service, no element comparison, no
       mappings, no element writes, no history rows
     - the metadata step of the run (#1274) collects the references the
       service advertises, exactly as a changed run would; the job decides
       ``NO_UPDATE_NEEDED`` and is only ``done`` once that step closed
       (``still_works``, #1263 counters)
     - capabilities equality decides the *service mapping*, not the ISO
       documents behind the advertised links; skipping the step would
       present stale records as current
   * - Capabilities changed, advertised metadata URLs unchanged
     - (nothing: this is the full apply path)
     - elements are compared and written as configured; the advertised
       reference rows of the adopted document describe the published
       elements; every advertised link is re-fetched and re-coupled
     - the URLs are the same but their answers may not be: revalidation per
       run is the policy until a safe validator (ETag/Last-Modified
       revalidation) is specified - see "Open" below
   * - Capabilities changed, advertised URL changed
     - (nothing)
     - the rows the candidate carried move onto the published service and
       elements; rows the adopted document does not advertise anymore are
       taken back with this update; the step collects the new list, not the
       registration's stale one
     - "the service advertises these links" must mean what the adopted
       document advertises; records found through a dropped link stay
       registered, and #1261's supersede bookkeeping answers their relations
       when a link resolves to a different record
   * - Same URL, republished ISO bytes
     - row writes for a record which did not change:
       ``get_or_create_metadatarecord`` updates the stored record only when
       the parsed ``date_stamp`` is newer
     - the fetch, the parse, the record identity decision by file
       identifier, and the supersede bookkeeping (#1261) which takes back a
       relation coupling the element to another record instance
     - identity is the file identifier, freshness is the ``date_stamp``;
       both need the document in hand, so the fetch is never skipped
   * - Element removed by the new document
     - the element's reference rows: they describe the element and go with
       it through the ``describes`` cascade - together with the rows of the
       mapped pairs in the update's own single take-back statement
     - the element deletion with history, the metadata step over the
       references which remain
     - a reference of a removed element describes nothing publishable; its
       record and relations follow the bookkeeping of #1261, never a silent
       delete
   * - A fetched remote document fails
     - (nothing is skipped retroactively)
     - #1263 decides the work row: bounded retry for a transport failure,
       a decided ``error_kind`` on the last attempt, counters which keep the
       background process honest; the update's own decided status stands -
       a failed reference never turns into a false ``COMPLETED``, and never
       into a re-run of the service mapping either
     - the service mapping and the metadata step are separate decisions;
       only the reference which failed is re-delivered (#1265)

What the storage shows after an update
======================================

An update which adopted a document leaves the service *stored* as that
document. :meth:`~registry.models.update.ServiceUpdateJob.adopt_stored_document`
writes the raw answer the run compared against into the service's
``xml_backup_file``, under the file name it already had. Three readers depend
on it and only make sense with it:

* ``document_equals`` - the comparison quoted above, i.e. the first row of
  the table;
* the stored capabilities read of #1044, which answers the published service
  network-free out of exactly this file;
* the integrity check ``check_xml_backups`` of #1150.

Before this, only the registration (and the persistence handler of a
harvest) wrote the file, so after the first real change the stored document
showed the state of the registration forever. Every later cycle of a settled
service proved "changed" again: it re-fetched, re-parsed and re-persisted a
whole candidate, deleted it and collected the registration-time references -
forever. That is the unnecessary downstream work #1413 asked for, and the
first test cycle of ``tests_update_refresh_policy`` measures it: a run of the
adopted document costs **one request and zero parses** and decides
``NO_UPDATE_NEEDED``, where it previously cost a full candidate each time.

``document_equals`` hashes raw bytes, which is why adoption stores the raw
fetched answer and not the candidate's own backup: the persistence handler
stores the mapper's serialized edition of the document, and hashing that
against the next raw answer would never prove equal. A resumed review job has
no fetched answer in hand and adopts the candidate's backup; that document is
still what the adoption published, and one converging cycle later the
comparison answers unchanged.

Reference rows of the published service
=======================================

The rows are the durable answer to "which ISO documents does this service
advertise" - the collection step reads exactly them (:func:`
``registry.tasks.service.advertised_references``). During an update they are
written by the mapper onto the *candidate* elements, and the candidate dies
with the adoption. ``ServiceUpdateJob._republish_references`` moves them
before that: the service-level rows of the candidate come onto the published
service, the element rows come onto the published elements of their mapped
pairs, the published elements' rows which the adopted document does not
advertise anymore go, and elements the new document drops lose their rows
with the element itself. The whole move is a constant number of statements -
``tests_task_sql_update`` guards the apply phase against per-pair growth, and
the second sanctioned delete on that fingerprint is this take-back beside the
candidate deletion's own cascade.

Deterministic counts
====================

The savings are pinned, not observed:

* request counts ride on the ``Session.send`` side_effect - a side_effect
  which runs out *is* a request the flow should not make; the settled-cycle
  tests assert exactly one call, the capabilities read;
* parse counts patch ``OGCServiceXmlMapper.from_xml`` - the one door every
  candidate document goes through - and assert it stays untouched;
* candidate staging is asserted by the absence of an
  ``update_candidate_of`` row, element writes and history stay implicitly
  pinned by the job deciding ``NO_UPDATE_NEEDED`` without a mapping phase.

Open
====

* HTTP revalidation (ETag / Last-Modified) of the advertised ISO documents
  would turn "always re-fetch per run" into "conditional GET per run" and
  the first row's request count into the only remaining network cost. It
  needs a normative answer about honouring upstream validators for
  third-party catalogues before it may be built; until then this page's
  second row stands.
* The CSW update path (:class:`~registry.models.update.CatalogueServiceUpdateJob`)
  keeps its own copy of this defect: ``update_metadata`` copies configured
  service fields from the candidate and never refreshes the stored document
  or the advertised reference rows either. It is untouched here because the
  issue names WMS/WFS; the finding is reported with the pull request.
