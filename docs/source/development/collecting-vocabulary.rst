.. _collecting-vocabulary:

=======================
Vocabulary of collecting
=======================

Registering an OGC service can collect the metadata documents the service
points at. That path shares its words with the harvesting of a catalogue:
where the two mean the same thing, they say the same thing — in German and in
English. Epic #1256 decided this as D6, option A; issue #1267 executed it.
This page is the word list written down once; the screens and the issues
(#1263, #1264, #1265, #1266, #1274) reference it instead of naming the words
again.

The one rule: a concept has one word, in both languages, across the
registration dialog, the job center and the record pages. „Wiederherstellen"
is not one of these words — it names the different action of discarding the
user's changes and restoring the harvested content
(`registry/serializers/service.py`, description of the restore of an XML
backup).

The option
==========

The checkbox on the WMS and the WFS create dialog, ``collect_metadata_records``
(`registry/serializers/service.py`, both create serializers carry the same two
msgid — the WFS option is not a second string):

.. list-table::
   :header-rows: 1
   :widths: 30 70 70

   * - Where
     - English
     - German
   * - the option (msgid ``collect metadata records``)
     - collect metadata records
     - Metadaten erfassen

The run
=======

The registration run is named by ``backgroundActivity.jobCenter.processTypes``
(`frontend/src/i18n`): en *Registration*, de *Registrierung* — unchanged, it
was already right.

The phases
==========

The ``phase`` of a ``BackgroundProcess`` (`notify/models.py`) reaches the
browser as a **key**, never as a baked-in sentence. The registration path
writes these keys (`registry/views/service.py`, `registry/tasks/service.py`;
the task base of `notify/tasks.py` ends a process with ``completed``); the
screens of the background process look the value up under
``backgroundActivity.phases`` (`frontend/src/i18n`) and answer any value that
is not a key raw:

.. list-table::
   :header-rows: 1
   :widths: 34 33 33

   * - Key
     - English
     - German
   * - ``background_process_created``
     - Background process created
     - Hintergrundprozess angelegt
   * - ``download_capabilities``
     - Download capabilities document
     - Capabilities-Dokument abrufen
   * - ``parse_capabilities``
     - Parse capabilities document
     - Capabilities-Dokument auswerten
   * - ``persist_service``
     - Persist service
     - Dienst speichern
   * - ``collect_metadata_records``
     - Collect metadata records
     - Metadaten erfassen
   * - ``completed``
     - Completed
     - Abgeschlossen

This is deliberately said explicitly, not left to chance: what is *not* a key
stays as it is. The error a registration task reports into the phase is a
diagnostic, not a phase, and stays free text (`registry/tasks/service.py`
answers ``str(e)``, `notify/tasks.py` answers
``f"An error occurred: {exc}"``); the phases harvested, updated and monitored
processes write, and the lines of the process log, belong to their own paths
and reach the browser untranslated, as before. The ``meta`` progress payloads
of ``update_state`` are no-ops suppressed by the task base and reach nobody.

The outcomes
============

One table for both collecting paths: ``harvestRun.collectingStates``
(`frontend/src/i18n`, rendered by `HarvestingRunMissingRecords.tsx` for
harvesting's
``CollectingStatenEnum`` and to be rendered by the collection screens of
#1263–#1266). Where registration and harvesting mean the same outcome, they
render the same key. The two last rows are the genuinely new, registration-only
outcomes — their reason: only the registration's collection knows a reference
the remote refused (``failed``) and one its run did not attempt (``skipped``);
harvesting's own states cover neither (#1264, #1265).

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - Key
     - English
     - German
   * - ``new``
     - New
     - Neu
   * - ``updated``
     - Updated
     - Aktualisiert
   * - ``existing``
     - Already there
     - Vorhanden
   * - ``duplicated``
     - Duplicated
     - Dupliziert
   * - ``removed``
     - Gone
     - Entfernt
   * - ``failed``
     - Failed
     - Fehlgeschlagen
   * - ``skipped``
     - Skipped
     - Übersprungen

The reference and the record
============================

The two nouns the collection screens of #1263–#1266 speak about, fixed here so
those issues do not each pick one:

* **reference** (de *Metadatenreferenz*) — one declared metadata location of
  the service, a row of ``RemoteMetadata`` (`registry/models/metadata.py`);
  the unit a phase or an outcome of the collection is about.
* **record** (de *Metadatensatz*) — the stored metadata document a reference
  produced, a row of one of the ``MetadataRecord`` kinds; harvesting already
  calls the same thing *Record* / *Eintrag* on its run screen.

No screen shows the word *reference* yet; when #1263–#1266 show it, they use
these words and no others.
