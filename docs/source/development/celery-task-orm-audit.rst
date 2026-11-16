.. _celery-task-orm-audit:

=====================
Celery task ORM audit
=====================

This page is the static, exhaustive audit of #1388: the matrix of every
first-party Celery task, every ORM/query access path it reaches (including the
transitive ones through model methods, ``save()`` overrides, signal receivers
and helpers), and the owning QuerySet/Manager method each nontrivial path
should live behind under the :ref:`queryset-manager-conventions` established
by #1397. It is the input consumed
by #1392 (harvesting, import, registration), #1393 (monitoring, update) and
#1394 (housekeeping, alerts, security, conformity, notify, system), and the
checklist #1395 asserts with query-count tests.

Scope rules honored here (from #1388): the audit is **static** — source
inspection and call-graph tracing only. No runtime telemetry, no production
worker sampling, no live profiling and no dashboards were added; the existing
#1330/#1326 instrumentation is untouched. Where a claim needs measuring before
it is trusted, this page says so and hands the measurement to #1395
(test-time ``CaptureQueriesContext`` over 0/1/10/100+ fixtures), not to V2.

How to re-derive the inventory
##############################

The three sources which enumerate every task and every schedule of the
deployment:

- every ``@shared_task`` under ``backend/registry/tasks/``,
  ``backend/notify/tasks.py`` and ``backend/system/tasks.py``
  (``extras/``, ``accounts/``, ``csw/`` and ``mapbender_compatibility/``
  define none — ``extras/tasks.py`` only carries the ``SingletonTask`` base
  and the history-attribution receivers);
- the beat rows created at migrate: ``registry/apps.py``
  (``check_for_files_to_import``, ``refresh_service_alerts``,
  ``watch_import_backlogs``, ``delete_expired_probe_response_artifacts``,
  ``sweep_ended_harvest_temp_files``), ``notify/apps.py``
  (``delete_expired_background_processes``,
  ``delete_expired_operational_incidents``, ``watch_operational_incidents``),
  ``system/apps.py`` (``delete_old_slow_request_dumps``,
  ``bound_task_attempt_samples``, ``refresh_capacity_snapshot``);
- the per-resource beat models: ``WebMapServiceMonitoringSetting`` /
  ``WebFeatureServiceMonitoringSetting`` / ``CatalogueServiceMonitoringSetting``
  (one ``PeriodicTask`` row per setting, ``task`` set from ``MONITORING_TASK``
  at ``registry/models/monitoring.py:98/110/122``), the three update settings
  (``registry/models/update.py:105`` and siblings) and ``PeriodicHarvestingJob``
  (``registry/models/harvest.py:1956``, ``task`` set to
  ``registry.tasks.harvest.create_harvesting_job`` at line 1970). Each of these
  rows *is* the schedule of its setting, created and kept current by the
  setting's own save path.

The dynamic, non-beat registrations are the ``worker_ready`` hooks
(``recover_harvests_after_restart`` at ``registry/tasks/harvest.py:641``,
``recover_registration_references_after_restart`` at
``registry/tasks/service.py:804``), the ``task_prerun`` / ``task_postrun`` /
``task_retry`` receivers (``MrMap/celery.py``, ``extras/tasks.py``,
``notify/tasks.py``, ``system/capacity_telemetry.py``) and the
``transaction.on_commit`` publishes inside model saves
(``MonitoringRun.save``, ``ServiceUpdateJob.save`` and the
``TemporaryMdMetadataFile.save`` seams below).

Task inventory
##############

Every first-party task, where it is defined, which queue carries it, which
``Task`` base it runs on and what publishes it. ``db-routines`` is the bounded
housekeeping queue of #970; ``harvest-import`` is the one queue allowed to
flood (#970 again).

.. list-table::
   :header-rows: 1
   :widths: 30 18 12 14 26

   * - Task
     - Module
     - Queue
     - Base
     - Triggered by
   * - ``run_probe_check``
     - ``registry/tasks/monitoring.py:17``
     - default
     - —
     - chord member of ``run_{wms,wfs,csw}_monitoring``
   * - ``finish_run``
     - ``registry/tasks/monitoring.py:45``
     - default
     - —
     - chord body of the same chain
   * - ``run_wms_monitoring`` / ``run_wfs_monitoring`` / ``run_csw_monitoring``
     - ``registry/tasks/monitoring.py:84/106/128``
     - default
     - —
     - ``MonitoringRun.save`` → ``dispatch_run`` on commit
       (``registry/models/monitoring.py:278/312/347``); also the settings'
       review flow
   * - ``create_wms_monitoring_run`` / ``create_wfs_monitoring_run`` /
       ``create_csw_monitoring_run``
     - ``registry/tasks/monitoring.py:96/118/140``
     - default
     - —
     - beat: the monitoring setting rows (``PeriodicTask`` subclasses)
   * - ``delete_expired_probe_response_artifacts``
     - ``registry/tasks/monitoring.py:150``
     - db-routines
     - SingletonTask
     - beat row (``registry/apps.py``)
   * - ``create_wms_update_job`` / ``create_wfs_update_job`` /
       ``create_csw_update_job``
     - ``registry/tasks/update.py:12/61/89``
     - default
     - —
     - beat: the update setting rows (``PeriodicTask`` subclasses)
   * - ``run_wms_update`` / ``run_wfs_update`` / ``run_csw_update``
     - ``registry/tasks/update.py:39/74/102``
     - default
     - BackgroundProcessBased
     - ``ServiceUpdateJob.save`` on add (``registry/models/update.py:863``
       and siblings), ``LayerMapping.save`` on review edits
       (``registry/models/update.py:1174``), ``resume()``
   * - ``collect_update_metadata``
     - ``registry/tasks/update.py:121``
     - default
     - BackgroundProcessBased
     - ``finish_after_metadata_step`` / ``redrive_metadata_step``
       (#1274, ``registry/models/update.py:420/444``)
   * - ``recover_harvesting_jobs``
     - ``registry/tasks/harvest.py:647``
     - default
     - HarvestingTask
     - ``worker_ready`` (``registry/tasks/harvest.py:641``)
   * - ``watch_import_backlogs``
     - ``registry/tasks/harvest.py:906``
     - db-routines
     - SingletonTask
     - beat row (``registry/apps.py``)
   * - ``cleanup_harvesting_job_temp_files_task``
     - ``registry/tasks/harvest.py:1313``
     - db-routines
     - — (bound, self-continuing)
     - terminal transitions (``schedule_cleanup_of_harvest_temp_files``,
       line 1483), the sweep, worker-start dispatch, its own continuations
   * - ``sweep_ended_harvest_temp_files``
     - ``registry/tasks/harvest.py:1446``
     - db-routines
     - SingletonTask
     - beat row (``registry/apps.py``); also dispatches the registration
       reference recovery
   * - ``create_harvesting_job``
     - ``registry/tasks/harvest.py:1506``
     - default
     - HarvestingTask
     - API "harvest now" and the ``PeriodicHarvestingJob`` beat rows
   * - ``call_fetch_total_records``
     - ``registry/tasks/harvest.py:1555``
     - default
     - HarvestingTask
     - ``create_harvesting_job``, recovery
   * - ``call_fetch_records``
     - ``registry/tasks/harvest.py:1594``
     - download
     - HarvestingTask
     - chord member built by ``handle_total_records_defined``
       (``registry/models/harvest.py:555``)
   * - ``call_chord_md_metadata_file_to_db``
     - ``registry/tasks/harvest.py:1621``
     - db-routines
     - HarvestingTask
     - chord callback of the download chord; ``publish_import_chord``
   * - ``call_md_metadata_file_to_db``
     - ``registry/tasks/harvest.py:1811``
     - harvest-import
     - MetadataFileImportTask
     - single-row seam: ``TemporaryMdMetadataFile.save`` job branch
       (``registry/models/harvest.py:1614``)
   * - ``call_md_metadata_files_to_db``
     - ``registry/tasks/harvest.py:1824``
     - harvest-import
     - MetadataFileImportTask
     - chunk members built by ``call_chord_md_metadata_file_to_db`` (#859)
   * - ``finish_harvesting_job``
     - ``registry/tasks/harvest.py:1531``
     - db-routines
     - HarvestingTask
     - chord body of the import chord
   * - ``check_for_files_to_import``
     - ``registry/tasks/harvest.py:1856``
     - db-routines
     - SingletonTask
     - beat row (``registry/apps.py``)
   * - ``build_ogc_service``
     - ``registry/tasks/service.py:74``
     - default
     - BackgroundProcessBased
     - registration API
   * - ``collect_reference``
     - ``registry/tasks/service.py:405``
     - download
     - BackgroundProcessBased
     - chord members of the sealed plan (#1263); the single-row seam of
       ``TemporaryMdMetadataFile.save``; the recovery's re-drives
   * - ``finish_metadata_collection``
     - ``registry/tasks/service.py:724``
     - db-routines
     - BackgroundProcessBased
     - chord body; the recovery's closer for decided plans
   * - ``recover_registration_reference_work``
     - ``registry/tasks/service.py:813``
     - db-routines
     - SingletonTask
     - ``worker_ready`` (``registry/tasks/service.py:804``) and the hourly
       harvest sweep (``registry/tasks/harvest.py:1473``)
   * - ``refresh_service_alerts``
     - ``registry/tasks/alerts.py:35``
     - db-routines
     - SingletonTask
     - beat row (``registry/apps.py``) and every invalidation published by
       ``notify/utils.py:127``
   * - ``run_conformity_check``
     - ``registry/tasks/conformity.py:25``
     - default
     - —
     - no first-party caller found on develop (see the conformity section)
   * - ``run_conformity_check_etf`` / ``run_conformity_check_internal``
     - ``registry/tasks/conformity.py:44/88``
     - default
     - —
     - ``run_conformity_check`` (only)
   * - ``async_analyze_log``
     - ``registry/tasks/security.py:5``
     - default
     - —
     - ``HttpResponseLog.save`` on add, on commit
       (``registry/models/security.py``, response-log save)
   * - ``finish_background_process``
     - ``notify/tasks.py:307``
     - db-routines
     - BackgroundProcessBased
     - chord body of planned collections (#1259)
   * - ``delete_expired_background_processes``
     - ``notify/tasks.py:329``
     - db-routines
     - SingletonTask
     - beat row (``notify/apps.py``)
   * - ``delete_expired_operational_incidents``
     - ``notify/tasks.py:352``
     - db-routines
     - SingletonTask
     - beat row (``notify/apps.py``)
   * - ``watch_operational_incidents``
     - ``notify/tasks.py:371``
     - db-routines
     - SingletonTask
     - beat row (``notify/apps.py``)
   * - ``delete_old_slow_request_dumps``
     - ``system/tasks.py:97``
     - db-routines
     - SingletonTask
     - beat row (``system/apps.py``)
   * - ``bound_task_attempt_samples``
     - ``system/tasks.py:121``
     - db-routines
     - SingletonTask
     - beat row (``system/apps.py``)
   * - ``refresh_capacity_snapshot``
     - ``system/tasks.py:204``
     - db-routines
     - SingletonTask
     - beat row (``system/apps.py``)

Query paths every task pays
###########################

These hit per task *run*, not per task kind. They are listed once; the
per-family matrices below do not repeat them.

.. list-table::
   :header-rows: 1
   :widths: 25 45 30

   * - Seam
     - SQL shape
     - Verdict
   * - ``MrMap/celery.py`` ``task_prerun`` / ``task_postrun``
     - ``close_old_connections()`` and ``connections.close_all()`` — no
       statements, but every task starts on a fresh connection (this is why
       the singleton lock needs its own session, ``extras/tasks.py:76``)
     - keep as is
   * - ``extras/tasks.py:20`` ``set_current_user`` (``task_prerun``)
     - one ``User`` SELECT for every delivery whose kwargs carry an
       ``http_request`` with a ``user_pk``; feeds the history attribution of
       ``simple_history``
     - one bounded SELECT; needed for history provenance — do not "optimize"
       it away in #1392; a fix candidate is to carry it in the same kwargs
       read, not to add more
   * - ``extras/tasks.py:142`` ``SingletonTask.__call__``
     - one dedicated non-pooled connection per fire plus
       ``SELECT pg_try_advisory_lock(hashtext(%s))`` and the matching unlock;
       a denied fire runs no body
     - keep — the session-scoped lock is the fix of #837; two statements
       against a self-managed session is the floor, not a defect
   * - ``notify/tasks.py:25`` ``get_background_process`` (``task_prerun``) +
       ``BackgroundProcessBased`` (``notify/tasks.py:99``)
     - for ``BackgroundProcessBased`` tasks whose kwargs name a
       ``background_process_pk``: one process read/report at the start of the
       run and further reports around success/failure; process-less deliveries
       pay nothing
     - keep — the reports are the feature (#1203); the read is bounded per
       start
   * - ``notify/tasks.py:34`` ``report_process_retry`` (``task_retry``)
     - one ``report_retry`` UPDATE (plus a log INSERT when the reason is new)
       per retry of a process-backed task
     - bounded per retry — keep
   * - ``system/capacity_telemetry.py`` (the #1330 collector)
     - worker-local buffering; one ``bulk_create`` of ``CeleryTaskAttempt``
       rows per coalesced flush (#1330 design)
     - unchanged per the V1 scope rule — #1330/#1326 instrumentation stays
       exactly as it is
   * - ``notify/utils.py:127`` ``invalidate_service_alerts``
     - publishes ``refresh_service_alerts`` on commit plus a websocket
       message; no SQL itself (it deliberately never runs the refresh inline,
       which would rewrite the table inside the caller's transaction)
     - keep; its cost belongs to the alert refresh, audited below

Family: monitoring (scoping for #1393)
#######################################

``create_{wms,wfs,csw}_monitoring_run``
    Beat reads the setting by name (1 SELECT, ``name`` unique), inserts the
    run (``MonitoringRun.save`` → ``build_process``: ContentType SELECT
    cached + one ``BackgroundProcess`` INSERT) and dispatches the run task on
    commit. **Already optimal**; the trivial ``get(name=...)`` needs no
    manager method (#1397 rule 6).

``run_wms_monitoring`` / ``run_wfs_monitoring`` / ``run_csw_monitoring``
    ``monitoring.py:84/106/128``. One run SELECT (``select_related("setting")``),
    then two list() reads — one per probe relation of the setting (two *model*
    relations per kind, so two queries is the inherent floor, not an N+1).
    ``start_run`` reports the total steps (1 process UPDATE) and publishes the
    chain. **Already optimal.** The inline ``select_related("setting")`` is a
    reuse candidate for ``for_monitoring_task()`` (#1397's own example) but
    adds no relations today — #1393 may introduce the name without changing
    the plan.

``run_probe_check``
    The one genuine over-reading hot path of the family, reached once per
    probe per run. Paths, in evaluation order:

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - probe + run fetch (``registry/tasks/monitoring.py:30-31``)
     - two separate ``objects.get(pk=...)`` SELECTs, no ``select_related``
       anywhere
     - the body then dereferences ``self.setting.service.client``
       (``registry/models/monitoring.py:748``) which pays two *more* lazy
       SELECTs (setting, service) plus the service's auth read for the client
   * - probe back-pointer write (``registry/models/monitoring.py:741-746``)
     - ``ProbeResult`` INSERT, then ``self.save()`` — a full UPDATE of the
       *probe* row per check, storing the result pointer on the shared probe
       configuration
     - the probe row is configuration shared by every run of the setting; a
       per-check write on it is a lock/row-write on configuration and
       concurrently overwritten by every parallel probe of one run. Move the
       pointer to the result side or delete it (the result already names its
       run); at minimum ``update_fields``
   * - ``GetMapProbe.build_request`` (``registry/models/monitoring.py:871-878``)
     - ``self.layers.with_inherited_attributes_cte()`` (one heavy query: three
       ancestor CTEs) and then a second ``self.layers.all()`` for the
       identifiers
     - the M2M is evaluated **twice per GetMap probe** — the heavy scoped CTE
       query once and the plain list again; read once, reuse the rows
   * - result write and response artifact (``finally`` +
       ``store_response_artifact``)
     - one ``result.save()`` plus the artifact FileField write when the body
       is kept
     - fine
   * - ``run.report_process(step_done=True)``
     - one capped ``_apply`` UPDATE (``notify/managers.py:120/364``)
     - fine

**Classification: optimize** (#1393). Fix: a
``Probe.for_probe_execution()`` on the shared probe QuerySet (1-row plan:
``select_related("setting__service__auth")``) replacing the inline get; one
``self.layers`` read cached inside ``build_request``. Do **not** prefetch the
probe's ``layers`` M2M into the fetch — the rows are only needed inside
``build_request`` and the CTE-scoped read is already the narrow plan.

``finish_run``
    run SELECT, ``run.save()`` (full row UPDATE — only ``date_done`` changed;
    an ``update_fields`` candidate), process UPDATE, alert invalidation
    publish. **Already optimal** (the ``update_fields`` is a one-line note,
    not its own change).

``delete_expired_probe_response_artifacts``
    (``registry/models/monitoring.py:1060``) One SELECT per probe-result model
    (6 models, ``PROBE_RESULT_MODELS`` at line 1045), then **one UPDATE per
    expired row** (``save(update_fields=["response_body"])`` in a loop) plus
    one storage delete per row. **Classification: optimize** (#1394). A purge
    touching 100 k rows pays 100 k UPDATEs. Fix: read
    ``values_list("pk", "response_body")`` in bounded pages, delete the
    storage names, then ``bulk_update``/``update(response_body=None)`` in
    batches after commit-safe ordering (file first or row first is decided by
    the same reasoning as #1208/#1237: rows are the durable index, the sweep
    tolerates leftovers). Propose the method as ``for_cleanup_batch()`` on a
    shared manager of the result models (#1397's example name).

Family: update jobs (scoping for #1393)
#######################################

``create_{wms,wfs,csw}_update_job``
    Beat SELECTs the setting by name, ``get_or_create``s the unfinished job
    under the one-unfinished-job-per-service constraint
    (``registry/models/update.py:265``), the job's ``save`` builds its process
    and dispatches the runner on commit. **Already optimal.**

``run_wms_update`` / ``run_wfs_update`` / ``run_csw_update``
    Job fetch (1 SELECT) into ``job.update()``
    (``registry/models/update.py:810/1016/1128``). The no-change path is small:
    a status save, the stored-document comparison (storage IO, no SQL), the
    ``finish`` save and the metadata-step publish. The update path is the
    widest read in the update family:

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - ``old_service`` / ``new_service`` cached properties
       (``registry/models/update.py:706-712``, 944-950, 1116-1122)
     - ``prefetch_whole_service()`` on both services
       (``registry/managers/service.py``) — the **view-oriented** plan:
       contacts, operation urls, keywords and per layer/featuretype the
       keywords, reference systems, remote metadata, publishable metadata
       relations, time extents and styles with a sibling-index window
     - the update reads identifiers, mptt positions and the **configured
       scalar/M2M fields** of ``update_config``; the view's whole breadth is
       paid per candidate element per run. #1397 says exactly this:
       favor narrow task-specific plans over ``prefetch_whole_*``. A
       ``for_update_diff()`` plan built from ``update_config`` (only the
       relations the config names) is the scoped change; keep
       ``prefetch_whole_service`` for the API. Cardinality: one service +
       its elements; on a WMS with thousands of layers this is the dominant
       read. Risk: config-dependent behavior — #1395 must cover at least two
       distinct update configs
   * - ``update_field`` over M2M/reverse fields
       (``registry/models/update.py:476-501``)
     - per configured M2M/reverse field: old ids
       (``target.all().values_list``), the source set (cache-hit if the
       whole-service prefetch loaded it — a narrow plan makes these explicit
       reads), then ``set``/``add`` writes
     - bounded by the config's field count; a narrow plan must prefetch the
       configured M2M per element (bounded) instead of falling back to
       per-element lazy reads
   * - ``update_layers`` / ``update_featuretypes``
       (``registry/models/update.py:740/979``)
     - confirmed-mapping exists/values queries, mappings
       ``select_related("new_layer","old_layer")`` (fine), per-layer field
       comparison in python (fine), ``bulk_update_with_history`` and
       ``bulk_history_create`` (fine, batch 500), ``Collector``-based
       ``delete_with_reason`` (cascade reads), monitoring-settings reassign
       UPDATE, candidate DELETE (its own cascade reads), mapping DELETE
     - mostly already optimal; the cascade reads of the two deletes are the
       price of the audit trail — record, do not chase
   * - per-save mirrors
     - every job ``save()`` pays ``report_process`` +
       ``set_action_required`` (2 capped UPDATEs,
       ``registry/models/update.py:319-351``) plus the alert invalidation
       publish
     - bounded per save; the save count itself (status transitions) is small
   * - ``update_config`` cached_property (``registry/models/update.py:567+``)
     - one SELECT for the config row, cached on the job
     - fine

**Classification: optimize** (``run_wms_update``, ``run_wfs_update``) —
one scoped change: the config-driven ``for_update_diff()`` service plan.
``run_csw_update`` reads no mappings/layers at all (only
``prefetch_whole_service`` of a CSW: contacts, operation urls, keywords) —
same fix, smaller payoff, same PR is acceptable. Everything else in the
family is **already optimal**.

``collect_update_metadata`` (``registry/tasks/update.py:121``)
    Base process read, then ``update_job_for_process``
    (``registry/models/update.py:578``): a bounded loop over the three
    concrete job models, one indexed SELECT each until one answers (≤3
    SELECTs; the owning kind is found first in the common case). Then the
    registration machinery below (``advertised_references``: 2 SELECTs;
    ``plan_registration_references``: process SELECT FOR UPDATE + work-row
    ``bulk_create`` + process UPDATE). **Already optimal** — the ≤3-SELECT job
    resolution is a reasonable price for the process→job seam (#1274); an
    ContentType-keyed lookup would be the alternative if #1393 measures the
    loop as hot.

Family: harvesting (scoping for #1392)
#######################################

The download side:

``create_harvesting_job`` (``registry/tasks/harvest.py:1506``)
    Service SELECT FOR UPDATE, task-id dedup SELECT
    (``HarvestingJobTaskId``, #892), ``get_or_create`` of the job (its save
    builds the process), creation-id registration, publish on commit.
    **Already optimal** — every read is a lock or a dedup guard.

``call_fetch_total_records`` (``registry/tasks/harvest.py:1555``)
    Job SELECT FOR UPDATE, then ``fetch_total_records``
    (``registry/models/harvest.py:781``) dereferences ``self.service``
    (1 lazy SELECT + the auth read for the client) and the CSW network calls;
    ``handle_total_records_defined`` (line 555) registers the chord ids (bulk
    INSERT), reports the process (UPDATE), logs the plan (INSERT) and publishes
    the download chord. One ``job.save()`` per fire. **Classification:
    optimize (small)**: the locked read can carry
    ``select_related("service__auth")`` so the client build costs no extra
    SELECT; low priority.

``call_fetch_records`` (``registry/tasks/harvest.py:1594``)
    Job SELECT ``select_related("service","service__auth")`` — the narrow
    plan is *already* right here (this is the pattern #1397 wants; reuse it in
    ``for_harvest_task()`` candidates rather than re-inventing). Per answered
    page, ``_store_page`` (``registry/models/harvest.py:1067``):

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - duplicate-page guard ``get_stored_page_count``
     - one count SELECT per page filtering
       ``TemporaryMdMetadataFile`` by job **and** ``requested_url``
     - the available indexes (``registry/models/harvest.py:1381-1393``) are
       ``["job_id","-id"]``, ``["job_id","has_import_error"]`` and the partial
       registration index — the count matches on ``job_id`` and then filters
       ``requested_url`` against every row of the job. On the 411 k-record
       backlog of #892/#1237 this reads O(job backlog) per *page* —
       **index candidate** ``["job_id","requested_url"]`` (schema change,
       belongs with a migration in #1392; run
       ``scripts/migration_graph_smoke.py`` before pushing)
   * - page storage
     - per-record storage write + one ``bulk_create`` batch per page,
       ``ignore_conflicts`` — deliberately *no* ``save()`` scheduling here;
       the import fan-out is built later by the chord builder
     - fine
   * - job lock per page (SELECT FOR UPDATE)
     - one per page, the race guard of #688
     - keep

``call_chord_md_metadata_file_to_db`` (``registry/tasks/harvest.py:1621``)
    Job SELECT FOR UPDATE; backlog ids via the
    ``["job_id","has_import_error"]`` index ✓; ``_http_request()`` fallback
    (history ``change_log`` SELECT + user SELECT) only when a recovery message
    carries no request snapshot; task-id registration bulk INSERT; job save
    (UPDATE + history); ``reconcile_import_progress`` (process row SELECT +
    flagged count over the same index + capped raises) or ``report_process``.
    **Already optimal** — the index work of #886/#1263 already covers this
    path; do not add prefetches here.

The import side (the highest-volume path in the deployment):

``call_md_metadata_files_to_db`` chunk (``registry/tasks/harvest.py:1824``, members) and ``call_md_metadata_file_to_db`` (line 1811, single-row seam)
    Per chunk: one progress-process resolution SELECT only when the kwargs
    predate #958. Per record, inside ``import_md_metadata_file`` (line 1745):

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - row fetch
     - ``select_for_update(of=("self",))`` +
       ``select_related('job','job__service','job__service__auth')``
     - already the right narrow plan; centralize it as
       ``TemporaryMdMetadataFile.for_harvest_import()`` (the #1397 example
       name) so the lock stays an explicit call-site operation (rule 3)
       behind a chainable QuerySet method
   * - stored document read (``md_metadata_file_to_db``,
       ``registry/models/harvest.py:1716``)
     - one storage read per row (the record's own document)
     - fine
   * - ``get_record_by_id_request`` per record (line 1749)
     - per imported record: builds the client, **reads and parses the
       catalogue's stored capabilities document from storage** and computes
       the origin url for the record's identifier
     - already reduced from three document reads per record to one by #1044;
       the remaining cost is one document read+parse *per record* while the
       document is identical for the whole run. Cache the parsed document
       (or the client) per chunk/task process — keep the #1044 semantics:
       a missing document still raises ``CapabilitiesBackupMissing`` for the
       run, not a per-record workaround
   * - ``PersistenceHandler.persist_all`` per record *file* (line 1770)
     - the whole mapping/persistence machinery per file, including the
       ``get_or_create``-mode writes of the shared lookup tables (keywords,
       reference systems, contacts, time extents — ordered,
       ``ignore_conflicts`` per #817)
     - per-record commit is *required* (a failing record flags itself and
       must not fail the chunk, #895) — do not batch records into one
       transaction. The reducible cost is the per-file lookup-table round
       trips: candidates are per-chunk lookup caches (read-mostly tables;
       conflicts stay safe) — measure first, this is #1395 fixture work
       (10/100+ records per chunk)
   * - ``update_relations`` (line 1863)
     - ``harvested_through.add(service)`` M2M (existing-ids SELECT +
       INSERT-when-new) + one ``HarvestedMetadataRelation`` write per record
     - bounded per record; the through add could ride the relation write,
       low priority
   * - per-warning logs (line 1823-1849)
     - one ``HarvestingLog`` INSERT + one storage file per mapper warning of
       every record, plus one for an insufficient-quality record
     - on warning-heavy catalogues this multiplies rows and files per record;
       keep the audit trail but consider coalescing identical warnings per
       chunk (decision for #1392, evidence needed)
   * - row exit
     - row ``delete()`` + storage delete on commit (success) or one
       ``UPDATE`` flagging ``has_import_error`` (failure, #895)
     - fine
   * - progress bookkeeping (#958)
     - worker-local coalescing; one capped process UPDATE per 200 steps or
       30 s (``credit_import_progress``/``flush_import_progress``,
       ``registry/tasks/harvest.py:233/266``)
     - already optimal — the durable-progress pattern to *not* re-invent
       elsewhere

``finish_harvesting_job`` (``registry/tasks/harvest.py:1531``)
    Job SELECT FOR UPDATE, flush of the worker's unreported steps, backlog
    ``exists()`` over the ``["job_id","has_import_error"]`` index ✓, then
    ``complete_harvest`` (``registry/querys/harvest_history.py``): the
    snapshot-completeness, removal-diff and duration aggregates plus the
    terminal job save (which schedules the temp-file cleanup, #1237).
    **Already optimal** at the task level; the aggregates of
    ``harvest_history`` are the natural query-count fixture of #1395, and any
    index for them (relations by state per job) should come from measurement,
    not from this static pass — classification: **already optimal**, with the
    aggregates listed under "measure, don't assume".

The housekeeping side of the family:

``watch_import_backlogs`` (``registry/tasks/harvest.py:906``)
    One values-list SELECT of open jobs in the import phase per fire
    (indexed on ``done_at``), then per job the *broker* inspection (network,
    not SQL) and the existing log/resume paths. **Already optimal** — bounded
    by the number of open harvests, and the broker side is intentionally not
    a DB problem (#1038).

``recover_harvesting_jobs`` (``registry/tasks/harvest.py:647``)
    ``iterator()`` over open jobs, per-job branch reads (registered ids,
    phase), broker asks, log writes; ends with
    ``dispatch_cleanup_of_ended_harvest_backlogs``. Runs once per worker
    start. **Already optimal.**

``cleanup_harvesting_job_temp_files_task`` (``registry/tasks/harvest.py:1313``, via ``cleanup_harvesting_job_temp_files`` line 1133)
    Bounded rows-per-run page: paged row SELECTs by job (``["job_id","-id"]``
    ✓), batched row DELETE, per-file storage deletes after each batch commit,
    the job-directory sweep over storage, bounded self-continuation (#1237,
    #1295 retention window). **Already optimal by design** — the bound is the
    feature; do not "batch away" the per-file deletes, the ordering rows→files
    is the leak guard named in the module comment.

``sweep_ended_harvest_temp_files`` / ``dispatch_cleanup_of_ended_harvest_backlogs`` (``registry/tasks/harvest.py:1446/1372``)
    Three bounded values-list
    SELECTs (terminal jobs still holding rows; open ids among the storage
    directories; not-due ids inside the retention window) plus one storage
    ``listdir``. **Already optimal.**

``check_for_files_to_import`` (``registry/tasks/harvest.py:1856``)
    Walks the drop directory and ``bulk_create_with_task_scheduling``s rows
    (per-row on-commit publish of the single-row import seam,
    ``registry/models/harvest.py:1614``). **Not enough evidence** — the
    drop-directory path sees at most one batch of files per 5-minute fire in
    practice; leave it to #1395 to capture whether the per-row scheduling
    shape deserves the chunk path instead.

Family: registration metadata collection (scoping for #1392)
############################################################

``build_ogc_service`` (``registry/tasks/service.py:74``)
    One auth SELECT (when given), one HTTP fetch, mapper +
    ``PersistenceHandler.persist_all`` (the bulk write path,
    ``registry/mappers/persistence/handler.py``), ``refresh_from_db``,
    ``advertised_references`` (2 SELECTs over the ``RemoteMetadata``
    subclasses, lines 263-300), ``plan_registration_references`` (process
    SELECT FOR UPDATE + one ``bulk_create`` + the sealed-plan UPDATE, lines
    303-398) and the chord publish. **Already optimal** — the reads are
    bounded, the writes are the bulk machinery.

``collect_reference`` (``registry/tasks/service.py:405``)
    One row SELECT; ``claim_for_processing``
    (``registry/models/harvest.py:1459``): process SELECT FOR UPDATE → row
    SELECT FOR UPDATE → lease UPDATE (the deliberate process→row lock order
    of #1263 — tests of #1395 should assert this order, not just the count);
    fetch (network); storage write; the finalize transaction re-locks
    process+row and runs ``import_registration_reference`` (the per-reference
    mapper/persist write path, same handler as above), deletes the row on
    success and moves the counters through ``record_reference_outcome`` (one
    capped UPDATE). Failure paths: ``release_claim`` or one decided-failure
    UPDATE (``_decide_reference_failure``, line 630/658). **Already optimal**
    for V1: every read is a lock, a permit or the document itself. The
    per-reference ``import_registration_reference`` persist shares the
    lookup-table round-trip shape of the harvesting import and inherits the
    same #1395 measurement; no inline query chain here is misplaced.

``finish_metadata_collection`` (``registry/tasks/service.py:724``)
    Process SELECT FOR UPDATE + one leased-rows ``exists()`` over the partial
    ``["background_process_id","state"]`` index ✓ + (update case)
    ``update_job_for_process`` (≤3 indexed SELECTs) + the job's
    ``metadata_step_completed`` save or the process completion UPDATE.
    **Already optimal.**

``finish_background_process`` (``notify/tasks.py:307``)
    ``process_info()`` SELECT (the annotated read, ``notify/managers.py:46``)
    + completion report. **Already optimal.**

``recover_registration_reference_work`` (``registry/tasks/service.py:813``)
    One SELECT of sealed-and-open processes, then per process one eligible-row
    slice (indexed ✓) and one outstanding ``exists()``, publishes re-drives
    and closers; ends with ``sweep_registration_orphan_files`` (storage
    listings + one values-list of names per process prefix). **Already
    optimal** — it is a per-process N+1 over a set bounded by the number of
    concurrently open collections (normally single digits); a single
    windowed-CTE query would be premature unless #1395 shows the process
    count growing.

Family: the alert refresh (scoping for #1394)
##############################################

``refresh_service_alerts`` (``registry/tasks/alerts.py:35`` →
``registry/querys/alerts.py:547``)

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - ``service_alert_rows()`` (line 797)
     - per service kind one SELECT of the real services annotated with the
       full derivation (``alert_annotations``, line 247: Exists/subquery
       chains over the newest run/job per service, backed by the composite
       ``["service","-date_created"]`` indexes added with #1030)
     - already the database-side design #1030 asked for; bounded
       annotation-count, one statement per kind — keep
   * - ``schedule_alert_rows()`` (line 498)
     - one SELECT of the enabled settings per kind + the duration estimates
       (``harvest_durations`` aggregates, median windows) + python crontab
       math
     - bounded by the number of schedules; the durations aggregate is the
       measurement target for #1395 (it grows with run history — the
       windowing of #693 caps it)
   * - ``missing_capabilities_rows()`` (line 644)
     - one SELECT of every real service naming an ``xml_backup_file`` per
       kind, then **one ``storage.exists()`` per service**
     - the dominant cost of the refresh, run every beat interval *and* on
       every invalidation: a deployment with thousands of services pays
       thousands of storage probes per fire. The database cannot answer
       whether the media holds a file, but the *storage can answer for a
       prefix*: list the per-kind prefixes once and diff against the named
       files, or bound the check to a slower cadence than the alert refresh.
       This is the one scoped storage-vs-SQL change #1394 should take from
       this audit
   * - the write
     - ``ServiceAlert.objects.all().delete()`` + ``bulk_create(rows)`` in one
       transaction (line 576)
     - keep the full-replace semantics (a reader sees one full refresh or the
       previous one — #1030); add ``batch_size`` to the ``bulk_create`` so a
       deployment-wide alert set does not become one monster statement, and
       let #1395 assert the row-stability (an open alert keeps its identity)

Family: conformity checks (scoping for #1394)
##############################################

``run_conformity_check`` (``registry/tasks/conformity.py:25``)
    Run SELECT (1) + ``run.config`` FK deref (1) + a sub-task publish. Two
    bounded SELECTs — but two findings belong to #1394:

- ``return self.job.pk`` and the ``self.task`` / ``self.task.save()`` writes in
  the two workers (lines 44-124) are a seam of the *retired* DB task-result
  store: django-celery-results was removed with #1178/#1180 and the result
  backend is Redis now (:ref:`celery-result-backend`). Whatever ``self.task``/
  ``self.job`` resolve to on today's Celery (request attributes, not rows),
  the status/progress/phase writes were SQL statements in the old backend and
  are dead weight or errors on the new one. Verify at test time and retire.
- no first-party caller of ``async_run_conformity_check`` exists on develop
  (no view, serializer, model hook or ``send_task`` names it). The tasks are
  registered and reachable by name only. **Not enough evidence** for an
  optimization verdict of any kind — #1394 should first establish whether the
  family is still wired, and only then touch its SQL.

``run_conformity_check_etf`` / ``run_conformity_check_internal``
    (lines 44/88) Run SELECT + concrete-config SELECT (1 each); the checkers
    (``registry/helper/plugins/etf.py``, ``internal.py``) save the run row per
    polling/progress step and the internal plugin reads the record's stored XML
    backup. Bounded and dominated by the external ETF polling, not by SQL.
    ``ConformityCheckRunManager.has_running_check``
    (``registry/managers/conformity.py``) answers ``.count() != 0`` where
    ``.exists()`` suffices — one-line manager fix, in place, no new method.

Family: security log analysis (scoping for #1394)
##################################################

``async_analyze_log`` (``registry/tasks/security.py:5``)
    One response-log SELECT by pk, the analyzed-log model resolved through the
    reverse OneToOne metadata (no SQL), the analysis reads the stored response
    body from storage (image pixel count,
    ``registry/models/security.py``), and at most one analyzed-row INSERT.
    **Already optimal** as an ORM plan. The volume observation is
    architectural, not SQL: one task fires per *logged proxied response*
    (``HttpResponseLog.save`` on commit, #1153) — a busy secured service makes
    this the most frequent task in the deployment, but V1 does not change the
    architecture; record it for whoever eventually owns the sampling story.

Family: notify housekeeping (scoping for #1394)
###############################################

``delete_expired_background_processes`` (``notify/tasks.py:329``)
    ``purge_expired_background_processes`` (``notify/models.py:467``):
    terminal-and-expired processes collected, their ``extented_description`` /
    log file names collected before the rows go (``registration_work_file_names``
    for the #1263 processes), row deletes, then the storage deletes after
    commit — the rows→files order of #1208. **Already optimal**; keep the
    order, do not reorder for fewer round trips.

``delete_expired_operational_incidents`` (``notify/tasks.py:352``)
    One windowed SELECT + delete over resolved incidents only (#1319; active
    incidents are never touched). **Already optimal.**

``watch_operational_incidents`` → ``watch_operational_work``
    (``notify/incident_watchdog.py:327``) By design ("bounded in every
    dimension", #1320): one broker inspection per fire, one windowed SELECT
    sliced by ``OPERATIONAL_WATCH_MAX_VERDICTS`` for expired retry windows
    (line 230), one ``exists()`` for the consumer verdict (line 306), and the
    stale-verdict sweep iterating **the watchdog's own active incidents**
    (small, line 180) with one process read each. **Already optimal** — the
    per-incident process read is a bounded N+1 over the watchdog's verdicts,
    not over deployment state; #1395 should assert the bound holds
    (query count ≤ verdicts + constant), not chase it.

Family: system housekeeping (scoping for #1394)
################################################

``delete_old_slow_request_dumps`` (``system/tasks.py:97``)
    Pure storage sweep (#888) — zero SQL. **Already optimal.**

``bound_task_attempt_samples`` (``system/tasks.py:121``)
    Three sweeps over ``CeleryTaskAttempt`` (#1330): a paged abandon loop
    (SELECT page 500 + ``bulk_update`` — fine), the retention DELETE
    (``recorded_at__lt``) and the hard-cap (``count()`` + oldest-ids slice +
    delete).

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - Access path
     - Current shape
     - Finding
   * - retention delete + cap ``count()``
     - filtered by ``recorded_at`` and ordered by ``recorded_at``; the table's
       indexes (``system/models.py:134-141``) are ``started_at`` and
       ``(queue, started_at)`` — **no index on ``recorded_at``**
     - **index candidate** ``("recorded_at",)`` on ``CeleryTaskAttempt``
       (schema change, small; with it both sweeps become index reads against
       the capped 200 k table). ``for_retention()`` as a named method is
       optional — the filter is used once
   * - abandon page loop
     - ``filter(outcome="", started_at__lt=...)`` — the
       ``started_at``/``(queue,started_at)`` indexes cover it
     - fine

``refresh_capacity_snapshot`` (``system/tasks.py:204``)
    ``system/capacity_snapshot.refresh()`` (line 751): a cache read and
    fingerprint check per fire; only a stale snapshot rebuilds, under a build
    lock, from the indexed attempt table (windowed aggregates), one walk of
    the enabled ``PeriodicTask`` rows with budgets
    (``system/capacity_demand.py``) and one broker inspection
    (``system/capacity_measures`` / the snapshot's own
    ``_inspect_broadcast``). **Already optimal** — the cache + budget design
    of #1326/#1325/#1328 is exactly the pattern the audit wants elsewhere;
    do not add work to this fire, only note that the demand walk's fingerprint
    SELECT of the schedule rows is the query #1395 may assert stays constant
    per fire when nothing changed.

Classification summary
######################

Every task, one verdict (#1388 acceptance: optimize / already optimal / not
enough evidence).

.. list-table::
   :header-rows: 1
   :widths: 42 18 40

   * - Task(s)
     - Class
     - Reason (matrix above)
   * - ``create_*_monitoring_run`` (3)
     - already optimal
     - trivial indexed beat reads (#1397 rule 6: no wrapper)
   * - ``run_{wms,wfs,csw}_monitoring`` (3)
     - already optimal
     - two probe relations are two inherent list reads
   * - ``run_probe_check``
     - **optimize**
     - lazy ``setting.service`` chain; layers CTE + layers read twice; probe
       row written per check
   * - ``finish_run``
     - already optimal
     - note: ``update_fields`` on the terminal save
   * - ``delete_expired_probe_response_artifacts``
     - **optimize**
     - per-row UPDATE loop over six result models; bulk it
   * - ``create_*_update_job`` (3)
     - already optimal
     - get_or_create under the one-open-job constraint
   * - ``run_wms_update`` / ``run_wfs_update`` / ``run_csw_update``
     - **optimize**
     - ``prefetch_whole_service`` (view plan, ×2) where a config-driven
       narrow ``for_update_diff()`` suffices; rest already optimal
   * - ``collect_update_metadata``
     - already optimal
     - ≤3 indexed job-resolution SELECTs + sealed-plan machinery
   * - ``create_harvesting_job``
     - already optimal
     - locks and dedup only
   * - ``call_fetch_total_records``
     - optimize (small)
     - locked read can ``select_related("service__auth")``
   * - ``call_fetch_records`` (+ ``_store_page``)
     - **optimize**
     - missing ``["job_id","requested_url"]`` index for the per-page
       duplicate guard on a growing backlog
   * - ``call_chord_md_metadata_file_to_db``
     - already optimal
     - indexes of #886/#1263 already cover it
   * - ``import_md_metadata_file`` behind
       ``call_md_metadata_file(s)_to_db``
     - **optimize**
     - per-record capabilities-document read (#1044's single read stays);
       per-file lookup-table round trips; per-warning log writes — all
       measure-first
   * - ``finish_harvesting_job``
     - already optimal
     - index-backed exists; aggregates go to #1395 measurement
   * - ``watch_import_backlogs`` / ``recover_harvesting_jobs``
     - already optimal
     - bounded by open jobs; the broker ask is not SQL
   * - ``cleanup_harvesting_job_temp_files_task`` /
       ``sweep_ended_harvest_temp_files``
     - already optimal
     - the bound *is* the design (#1237)
   * - ``check_for_files_to_import``
     - not enough evidence
     - low-volume legacy drop-dir path; capture before judging
   * - ``build_ogc_service``
     - already optimal
     - bounded reads; bulk writes dominate
   * - ``collect_reference`` / ``finish_metadata_collection`` /
       ``finish_background_process`` / ``recover_registration_reference_work``
     - already optimal
     - locks/permits/indexed slices; the per-process N+1 is bounded by open
       collections
   * - ``refresh_service_alerts``
     - **optimize**
     - per-service ``storage.exists()`` per fire; ``bulk_create`` batch size;
       annotation side already optimal
   * - ``run_conformity_check`` + ``_etf`` + ``_internal``
     - not enough evidence
     - no first-party dispatcher on develop; retired task-result seam writes;
       establish liveness first, plus the ``has_running_check`` exists fix
   * - ``async_analyze_log``
     - already optimal
     - 1 SELECT + ≤1 INSERT; volume is architecture (per logged response)
   * - ``delete_expired_background_processes`` /
       ``delete_expired_operational_incidents``
     - already optimal
     - windowed collects, rows→files order of #1208
   * - ``watch_operational_incidents``
     - already optimal
     - bounded by #1320's own limits
   * - ``delete_old_slow_request_dumps``
     - already optimal
     - zero SQL
   * - ``bound_task_attempt_samples``
     - **optimize**
     - ``recorded_at`` index candidate; loop shape already fine
   * - ``refresh_capacity_snapshot``
     - already optimal
     - cache + budgets + indexed attempt windows (#1326)

Proposed QuerySet/Manager methods (#1397 conventions)
#####################################################

Only where a shared plan demonstrably exists (#1397 rule 6). Each row names
the owner file, the consumers, the bounded plan and the cardinality —
implement each inside its domain issue (#1392/#1393/#1394), never in a central
rewrite PR.

.. list-table::
   :header-rows: 1
   :widths: 22 20 20 24 14

   * - Method
     - Owner (existing manager chain)
     - Consumers
     - Plan / relations
     - Cardinality
   * - ``Probe.for_probe_execution()``
     - new QuerySet on the shared ``Probe`` base
       (``registry/managers/`` — same pattern as
       ``MonitoringRunQuerySet``), concrete per probe model
     - ``run_probe_check``
     - ``select_related("setting__service__auth")``; **no** layers M2M
       (read once inside ``build_request`` instead)
     - 1 row
   * - ``TemporaryMdMetadataFile.for_harvest_import()``
     - ``TemporaryMdMetadataFileManager``
       (``registry/managers/havesting.py:514``)
     - ``import_md_metadata_file`` (both chunk and single importers)
     - ``select_related("job","job__service","job__service__auth")``
       chainable; ``select_for_update(of=("self",))`` stays an explicit,
       named call-site operation (#1397 rule 3)
     - 1 row (locked)
   * - ``for_update_diff()`` on the three service QuerySets
     - ``registry/managers/service.py`` (next to
       ``prefetch_whole_service``, which stays for the API)
     - ``ServiceUpdateJob.old_service`` / ``new_service`` cached properties
     - built from the job's ``update_config``: contacts + operation urls +
       only the element M2M/reverse relations the config names, per-element
       bounded prefetches; never styles/time-extents/remote-metadata unless
       configured
     - 1 service + its elements
   * - ``ProbeResult.for_cleanup_batch()`` (name per #1397's example)
     - shared manager of the six ``PROBE_RESULT_MODELS``
       (``registry/models/monitoring.py:1045``)
     - ``delete_expired_probe_response_artifacts``
     - windowed ``values_list("pk","response_body")`` in pages feeding
       batched ``update``; replaces the per-row ``save`` loop
     - pages of ≤ N (setting)
   * - ``CeleryTaskAttempt.for_retention()``
     - the model's default manager (``system/models.py:57``)
     - ``bound_task_attempt_samples``
     - windowed id values-lists; pairs with the new
       ``recorded_at`` index (migration)
     - pages of ≤ N
   * - ``MonitoringRun.for_monitoring_task()`` (optional naming)
     - ``MonitoringRunManager`` (``registry/managers/monitoring.py``)
     - ``run_{wms,wfs,csw}_monitoring``
     - today exactly ``select_related("setting")`` — adopt the name only if
       the read grows; do not add relations without demonstrated use
     - 1 row
   * - ``HarvestingJob.for_task_recovery()``
     - *not proposed*: ``HarvestingJobManager`` already carries
       ``with_run_progress``/``with_process_info`` and the recovery reads are
       trivial values-lists — preserve the ``DefaultHistoryManager`` +
       ``CTEManager`` composition as-is
     - —
     - —
     - —

Explicit *no-method* decisions (direct one-off lookups are sufficient, #1397
rule 6): every beat ``get(name=...)`` of the settings, the by-pk fetches of
``finish_run``/``run_probe_check``-style tasks (after the FK chain fix above),
``create_harvesting_job``'s dedup reads, the alert refresh's model loops, the
conformity by-pk fetches, ``async_analyze_log``'s ``get_model().get(pk=...)``,
the three-SELECT job resolution of ``update_job_for_process``, and every
``BackgroundProcess.objects.report``-style write (already centralized in
``notify/managers.py``).

Scoping for the follow-up issues
################################

#1392 — harvesting, import, registration
    In expected-payoff order:

- capabilities-document cache per chunk in the import path
  (``md_metadata_file_to_db`` line 1749) — one storage read + parse per
  *chunk* instead of per record; preserve the #1044 error contract.
- ``TemporaryMdMetadataFile.for_harvest_import()`` centralization (mechanical,
  after the measurement).
- ``["job_id","requested_url"]`` index for the per-page duplicate guard
  (``_store_page`` / ``get_stored_page_count``) — migration; run
  ``scripts/migration_graph_smoke.py`` before pushing.
- per-file lookup-table round trips in ``PersistenceHandler`` during the
  import (measure at 10/100+ chunk fixtures first; per-record commit stays).
- per-warning ``job.log`` coalescing (only if a warning-heavy fixture shows
  multiplication).
- decide ``check_for_files_to_import``'s single-row scheduling vs the chunk
  path from a capture.

#1393 — monitoring, update
    - layers double-read + lazy FK chain + per-check probe write in
      ``run_probe_check`` / ``Probe.run_checks`` / ``GetMapProbe.build_request``
      (the three fixes are one scoped change);
      introduce ``Probe.for_probe_execution()`` with it.
    - ``for_update_diff()`` replacing ``prefetch_whole_service`` in the update
      jobs' candidate reads; config-dependent, so at least two configs in the
      fixtures.
    - ``finish_run`` / ``finish`` ``update_fields`` saves (one-liners riding
      the first PR).

#1394 — housekeeping, alerts, security, conformity, notify, system
    - ``missing_capabilities_rows``: replace per-service ``storage.exists()``
      with per-prefix listings (or a slower dedicated cadence); add
      ``batch_size`` to the alert ``bulk_create``.
    - probe-artifact purge: paged read + batched ``update`` behind
      ``for_cleanup_batch()``.
    - ``CeleryTaskAttempt``: add the ``recorded_at`` index; optional
      ``for_retention()``.
    - conformity: establish whether the tasks are wired at all; retire the
      ``self.task``/``self.job`` task-result seam; ``has_running_check``
      ``count`` → ``exists``.

Coverage checklist for #1395
############################

Assertions the family tests should carry (test-time
``CaptureQueriesContext``; fixture shapes 0/1/10/100+ where volume matters;
EXPLAIN only where an index candidate above is implemented):

- ``run_probe_check`` (WMS + WFS + CSW probe per kind): after #1393, exactly
  one layers read per GetMap probe; no probe-row UPDATE per check (or exactly
  one, ``update_fields``-scoped); the probe fetch carries
  ``setting__service`` in the same statement.
- ``refresh_service_alerts``: annotation SELECT count constant in the number
  of services (per kind); storage probes bounded by prefixes after the #1394
  change (capture the current linear shape as the red baseline); an open
  alert keeps its identity across refreshes.
- import chunk of 100 records: exactly 1 locked SELECT per row; per-chunk
  capabilities-document reads ≤ 1 after the cache; flagged-row path pays 1
  UPDATE and the chunk continues; progress UPDATEs coalesced (#958) —
  ≤ 2 per chunk at default settings.
- ``_store_page`` page of 100 records: 2 SELECTs + 1 batched INSERT; with the
  index, the duplicate-guard EXPLAIN names it.
- ``delete_expired_probe_response_artifacts`` with 100 expired rows across
  the six result models: UPDATE count constant after the bulk fix; rows keep
  every column except ``response_body``.
- ``bound_task_attempt_samples``: constant statements per page of 500; the
  retention delete's plan uses ``recorded_at`` after the index.
- ``watch_import_backlogs`` / ``watch_operational_incidents``: query count
  constant for 1 vs 10 open jobs/processes with the broker inspection
  mocked; the watchdog's count stays ≤ ``OPERATIONAL_WATCH_MAX_VERDICTS`` +
  constant.
- ``collect_reference``: claim→decide path statement order asserts the
  process→row lock order of #1263 (both the success and the
  decided-failure path); a lost-permit delivery pays the re-lock SELECTs and
  writes nothing.
- update job (two distinct ``update_config`` fixtures): after #1393, no
  styles/time-extents/remote-metadata SELECT for a config which does not name
  them; the review-required and resume paths keep their behavior.
- singleton fire: exactly the two advisory-lock statements plus the body.
- every new ``for_*()`` method: lazy and chainable (``.filter``/``.get``/
  ``.using`` still work), preserves default-manager filters and the existing
  manager composition (CTE/history/tree managers), and composes with
  ``.iterator()``/``.values()``; the harvesting case additionally proves the
  **do-not-prefetch-the-backlog** bound (no plan pulls
  ``TemporaryMdMetadataFile`` rows for a job during the import fan-out).
- ``call_chord_md_metadata_file_to_db`` and ``finish_harvesting_job``: keep
  the current query counts as the green baseline (already optimal — guard
  against regressions).

Historical fixes this audit already accounts for (do not repeat them)
#####################################################################

The current code already embodies these query fixes; none of the proposals
above re-invents them:

- #859 chunked import tasks; #886 the ``["job_id","has_import_error"]``
  index; #891/#970/#972 recovery without re-chording and the queue split;
  #892 per-task-id rows instead of the job-row array; #895 retryable-vs-record
  import errors; #817 conflict-safe lookup writes; #858/#919 the quality flag
  riding the one write; #958 coalesced durable progress; #1030 materialized
  alerts + composite newest-job indexes; #1038/#1320 the bounded watchdog;
  #1044 one capabilities-document read per record (this audit asks to widen
  the cache to the chunk, never back to three reads); #1045 log file paths;
  #1153 the abstract-model task argument; #1178/#1180 Redis result backend —
  no SQL remains on the task-result path, which is why the conformity
  result-row writes are dead weight; #1201 defined persistence failures;
  #1207/#1208 the process-state contract and bounded history; #1237/#1295
  the bounded temp-file cleanup and its retention window; #1259 sealed-plan
  counters; #1263/#1265 work rows, leases and authorized retries; #1274 the
  update's metadata step; #1319 incident dedup; #1325/#1326/#1328/#1330 the
  capacity estimator, snapshot and attempt telemetry; #1038/#1179 the broker
  inspection seam.
