(observability-inventory)=

# Observability inventory and migration boundaries

This is the read-only #1776 inventory for
[epic #1775](https://github.com/mrmap-community/mrmap/issues/1775), inspected on
2026-11-26 at develop `bc3e516b6cefdd6ec13de3945a6615e89d69a64d`.
[ADR-0003](../design/decisions/ADR-0003-low-overhead-observability.md) proposes the
replacement contract. No application, dependency, Compose, schedule, database or
retention change is made here. Counts/sizes/load in a running deployment are
**unmeasured**, never zero.

The baseline contains the task profiler (#1389), slow-task detection (#1390),
dashboard/exporter (#1391, merge `9bd7cbb3e`) and benchmark work (#1396, merge
`e2c76a15e`). The live #1387 parent was still open with 11/11 completed children.
Rebase the Celery evidence on develop again before any replacement; do not infer
pending source work from unchecked historical parent-body boxes. At inspection,
no #1776 PR/assignee/conflicting branch was linked. The user assigned this task;
the retired claim board/tool is not part of this work.

## Reading the matrix

Paths below are repository-relative. **Retire** means a candidate after its child
issue's validation/cutover, **Partial** means some semantics cannot be supplied by
standard telemetry, **Retain** means not a retirement target. Each row identifies
the source symbol/family, consumers, risk/unknown semantics and migration/rollback.
Test keys refer to the verification register below. These are proposals, not
permission to delete data. The owner named is the owning app/issue, not an assignee.

### HTTP and all formatter dump producers

| ID / disposition / owner | Producer and stored signal | Consumers / privacy and missing-data semantics | Migration and rollback / tests |
| --- | --- | --- | --- |
| H1 Retire, system / #1782 | `backend/system/logging/middleware.py:LogSlowRequestsMiddleware` wraps default-connection SQL, captures params and wall time; warning after slow returned response. | `ROOT_LOGGER` → RFC5424 formatter → media dump and slow-request dashboard; includes full absolute URI/query and interpolated SQL. No warning does not prove healthy (exceptions, clock changes, non-default DB, streaming work excluded). | Replace HTTP count/histogram first (#1781), compare coverage, then remove middleware; a high threshold does **not** disable SQL collection. Roll back code/settings deliberately, respecting privacy. T1. |
| H2 Partial, system / #1782/#1785 | `backend/system/logging/formatter.py:RFC5424Formatter.format/_write_dump`, `PYTHON_META_SDID`, `SLOW_REQUEST_DUMP_SUBDIR`; `util.py:quote_parameter/interpolate_sql/format_structured_data/escape_sd_value`. | Any record with `exc_info` adds a raw traceback and can write a dump even without H1. Plain code-position-only records do not write; `suppress_dump=True` overrides dumping. Disk errors return no pointer. Short syslog line carries a `/media/logs/<uuid>.json` pointer, **not** all structured fields. | Migrate every row H3–H5 before retiring generic dump output; sanitized structured console/OTLP logs replace the file mechanism. Retain console/fallback and old-file access refusals. Restore prior formatter only as an explicit rollback. T1/T2. |
| H3 Retire dump only, extras / #1785 | `backend/extras/serializers.py:ObjectPermissionCheckerSerializer.get_perm_checker` warns with `metaSDID@django.view_name` for missing prebuilt checker. | Operator diagnosis of slow permission fallback; application permission decisions do not depend on log/dump. | Keep a bounded safe warning/counter, stop file output; retain permission code and tests. Rollback previous logging configuration. T2. |
| H4 Partial, registry / #1785 | `backend/registry/models/service.py:_report_capabilities_backup_missing/_clear_capabilities_backup_missing`; `metaSDIS@django` (existing spelling). | Logs once per service/process until successful read; includes resource ID and missing filesystem path, with recovery advice. Missing backup still raises; no remote fallback (#1044). Dump is operator evidence. | Keep authoritative stored-document failure/recovery behavior; replace dump with safe code/type in global logs; resource detail stays protected locally. Never export interpolated service strings/paths. Rollback logging only. T2/T9. |
| H5 Partial, system / #1786 | `backend/system/task_performance_export.py:_log`: `metaSDID@taskperf`, `suppress_dump=True`, bounded logfmt message payload. | Task dashboard consumes the **message** fields in VictoriaLogs, since formatter sends only a dump pointer for other structured records. Removing formatter alone cannot migrate this contract. | Migrate exporter and dashboard together after window/coverage parity. Keep previous JSON provisioning and exporter cursor/settings for rollback; no dump is needed for this producer today. T4. |
| H6 Retain through drain, system / #1782 and #1497 | `backend/system/tasks.py:slow_request_dumps_dir/_dumps_by_age/delete_dumps/delete_old_slow_request_dumps`; `system/apps.py:create_slow_request_dump_cleanup_task`. | All H1–H4 dumps under `MEDIA_ROOT/logs/*.json`, not security-proxy or monitoring files. Age default 14d, cap default 0 (unbounded), either positive bound deletes oldest eligible files; zero disables that bound. | Stop writers before removing schedule; retain sweep for the configured historical window, or separately approved export/deletion. Preserve operator-custom cadence/caps. Rollback resumes same data/settings, never reconstructs erased dumps. T2. |
| H7 Retain, system/MrMap/nginx / #1782 | `backend/system/views.py:MEDIA_PRIVATE_SUBPATHS/MEDIA_PRIVATE_URL_PATTERN/PrivateMediaNotFoundView/ProtectedServeView/_is_private_media`; `backend/MrMap/urls.py`; `docker/nginx/mrmap.conf` guarded prefixes. | `/media/logs/` returns 404 (including backend routes and resolved symlink/dot paths); filesystem operators are the dump readers. Other private prefixes: `ext_auth_keys`, `security_proxy/logs`, `temporary_md_metadata_file`. | Keep refusal even after writer removal while old files/backups may exist. Do not turn pointers into public links. Rollback cannot broaden access. T2/T8. |

`rg -n 'structured_data|suppress_dump' backend --glob '*.py'` identifies the
explicit structured producers above plus formatter and tests. Any first-party
or third-party logger emitting `exc_info` is an additional **generic exception**
dump producer through H2. Operator filesystem investigation is the known dump
reader; no application JSON API/frontend viewer reads those files. Unknown
external filesystem consumers require an operator check before deletion, not
invented compatibility access or indefinite new dumping.

### Task, capacity, status and infrastructure

| ID / disposition / owner | Producer / storage / entry symbol | Consumers and limits | Migration and rollback / tests |
| --- | --- | --- | --- |
| C1 Partial, system / #1786/#1788 | `backend/system/capacity_telemetry.py`: `stamp_publish_time`, `note_worker_process`, `begin_attempt`, terminal receivers, `flush_attempts`, shutdown; `system/apps.py:SystemConfig.ready`. Inserts bounded batches, publish header `mrmap-published-at`. | C2/C3/C5/C6; enabled by default but worker-only, fail-open bounded process buffer can drop records. Open and terminal twins distinguish retry number; terminal duplicate insert suppressed. Stamp absence makes wait unknown. Root/task/parent IDs and worker/schedule identity are stored locally. | Standard metrics can replace technical aggregates only. Retain authoritative per-attempt needs until all consumers pass parity; sampler spans cannot replace them. Restart restores old collector settings; retain table and buffer-loss semantics. T3. |
| C2 Partial, system / #1788 | `backend/system/models.py:CeleryTaskAttempt`, `AttemptOutcome`, `AttemptQuality`, `TERMINAL_OUTCOMES`; SQL table `system_celerytaskattempt`. | Per-attempt durations, queue wait, open/crashed/abandoned quality; **not** domain workflow elapsed. C3–C6 and bounded drilldown. | No drop in #1776. Later removal needs consumers/backup/retention and generated migration; retain read-only history through rollback window. Restore schema/data from verified backup if a later destructive cutover is approved. T3/T4/T5. |
| C3 Partial, system / #1788 | `backend/system/capacity_measures.py:attempt_measures/grouped_measures/recent_samples/window_buckets/drilldown_samples/uncertain_coverage/task_class_of`. SQL percentiles, slot seconds, stamped-wait coverage. | Capacity cost and #1390/#1391; started-at windows differ from recorded-at export windows. Minimum samples, caps/truncation, abandoned/open and insufficient stamps are explicit uncertainty. | Histograms/unsampled counters may replace aggregates; preserve window/denominator/coverage contracts and exact-vs-approximate quantile disclosure. Keep old functions/table for rollback. T3/T4/T5. |
| C4 Partial, system / #1783/#1612 | `backend/system/task_profiling.py`: `_begin_profile/_end_profile`, `_SqlTimingWrapper`, `_wrap_session_send`, `_Profile`, `profile_report/drain_reports/lifecycle_map`. | Opt-in task allowlist, deterministic task-ID sample, bounded process buffer; slow/abnormal profiles log redacted SQL shapes, SQL/HTTP counts/times and unaccounted time. Actual code wraps `RequestsSession.send` even though introductory prose calls it a signal. | Native spans can replace SQL/HTTP timing only after no-SQL/privacy gates. Keep memory/cgroup and unaccounted semantics until parity. Restore explicit profiling settings at restart; profile buffers are not durable history. T6. |
| C5 Partial, system / #1787 and notify / #1104 | `backend/system/task_performance.py:evaluate_task_performance`, `judge_completed_slow/judge_regression/judge_queue_wait/judge_long_running/evaluate_coverage`, `process_of_attempt/scope_verdict/publish_verdicts/resolve_verdicts`. | `taskperf_completed_slow_*`, `taskperf_regression_*`, `taskperf_long_running`, `taskperf_queue_wait_*`, `taskperf_coverage_*` incidents; bounded worker Inspect confirms active tasks. Resource join is permission-sensitive. No worker answer is unknown, not proof an attempt ended. | Generic technical rules/routing move to Grafana; retain reliable resource lifecycle/active-confirmation/coverage adapters until #1787 parity. Shadow rules do not double publish/resolve. Restore old detector task/settings and unique rule ownership. T5/T7. |
| C6 Partial, system / #1786 | `backend/system/task_performance_export.py:export_task_performance/_next_window`, cache `mrmap-task-performance-window-cursor`; events `fleet`, `class_bucket`, `class_sample`, `coverage`, `class_coverage`. | `docker/grafana/provisioning/dashboards/jsons/mrmap_celery_task_performance.json`; five-minute, recorded-at nonoverlapping windows, late writes/resumed cursor, open/crashed coverage even when no window elapsed. Bounded samples include task IDs in operator log messages. | Replace technical exporter with unsampled SDK metrics and safe selected traces; exclude IDs from new exports. Retain drilldown authority, truncation and no-window coverage. Roll back exporter/cursor/dashboard together without double-counting overlap. T4. |
| C7 Retain domain, partial measured-cost replacement, system/registry / #1788/#1324 | `backend/system/capacity_snapshot.py:build_capacity_snapshot/observe_message_backlog/observe_queue_depths/refresh/get_capacity_snapshot`, `capacity_topology.py:observe_topology/task_routes`, `capacity_demand.py:periodic_demand/schedule_fingerprint/walk_crontab`; `backend/registry/querys/capacity.py`. | Admin API `/api/system/capacity`, `CapacitySnapshotSerializer`; cached materialization and build lock, native worker pools, queue subscriptions/depth, reserved/scheduled/in-flight work, projected periodic dispatch/cost and rho. Redis LLEN alone is not backlog; shared pools counted once. Cold/stale/limited/failed observation is unknown; rho is a periodic-only lower bound when comparable. | Standard measured cost input may change after parity; schedule evaluation, eligibility, ownership and reliable workload evidence stay in their apps. No external worker-admission engine. Preserve cache schema/API and prior cost source for rollback. T3/T8. |
| C8 Retain until equivalence, system / #1784 | `backend/system/status.py:get_status_snapshot/container_observation/component_observation`; `system/views.py:SystemStatusView/SystemView`; `/api/system/status/current`, `/api/system/info`. | Admin-only JSON:API `SystemStatus`/`System`, serializers; Docker GET-only proxy, exact project/service labels, excludes one-offs, 2s budget. `frontend/src/context/SystemStatusContext.tsx`, `components/Layout/SystemStatusIndicator.tsx`, `components/Resource/System/SystemStatus.tsx`; no usable observation → unknown/stale after 45s. | Metrics do not prove current service readiness. Keep API/UI permissions and freshness semantics; replacement needs equivalent readiness/liveness/offline behavior. Restore proxy/status path if a later reviewed simplification fails. T8. |
| C9 Retain, system/runtime / #1784 | `backend/system/worker_healthcheck.py:ping/main`; `backend/system/scheduler.py:HealthcheckScheduler`; Docker healthchecks in `docker-compose.yml`, `docker/docker-api/haproxy.cfg`. | Directed local-worker ping, independent Beat loop heartbeat `/var/mrmap/run/beat-heartbeat` (<30s), PostGIS `pg_isready`, Redis PING. Docker status consumed by C8. Proxy allows only GET container list/exact inspect, no mutations. | Do not replace a local worker pong/Beat successful loop with sampled activity. Preserve destination matching, protected heartbeat directory and sanitized error output. Optional change requires failure/recovery parity, restore prior healthcheck on rollback. T8. |
| I1 Partial, runtime / #1785 | `backend/MrMap/settings.py:LOGGING/ROOT_LOGGER`, `system/logging/fallback.py:syslog_reachable/warn_without_syslog`; `MrMap/celery.py:config_loggers`. All application/Django/Celery logger and exception call sites. | Console always; optional RFC5424 UDP handler attached on startup DNS reachability, not end-to-end sink health. A later silent UDP drop is possible. `LOG_DIR`, `LOG_FILE_MAX_SIZE`, `LOG_FILE_BACKUP_COUNT` exist but no rotating-file handler is wired in `LOGGING`. | Sanitized correlated logging replaces formatter/syslog only after content review; preserve fallback and bounded local diagnostics. Restart with prior handler config to roll back, avoiding duplicate propagation. T1/T2/T4. |
| I2 Retain transport, sanitize separately, runtime / #1785 | `docker-compose.yml` postgis/frontend syslog driver → host `127.0.0.1:5514/udp` → VictoriaLogs `:9428`; nginx stdout/stderr. `docker/nginx/mrmap.conf:mrmap_frontend_error` and `docker/nginx/error-beacon.js`. | PostgreSQL/nginx/container diagnostics, bounded client error reports and edge errors absent from Django metrics. Raw access URI, DB statements and browser report text can expose secrets; this ADR does not certify those streams safe. | Keep edge/container visibility, review content and transport separately from application OTLP. Do not ingest raw streams into the new allowlist by default. Roll back driver/config together. T8. |
| I3 Retain optional stores/UI, runtime / #1778 | `docker-compose.yml:victoria-logs/grafana`, `docker/grafana/provisioning/datasources/vl.yml` (`victorialogs`), dashboard provider `dashboards/mrmap.yml`, `mrmap_slow_requests.json`. | `vlogs-data` volume, 14d logs; Grafana `/grafana/` proxy/auth. Slow dashboard: slow count/minute, count/hostname, level volume, DB-side slow statements, raw dump-pointer lines. Count is unsampled log reception, not lossless request accounting. No provisioned alert rules/contact points currently; provisioning covers dashboards/datasource. | Add optional metrics/traces stores and tested datasources; replace panels individually (#1781), preserve DB/container/error panels. Native Grafana alert rules/contact points belong to future implementation. Backup volumes/provisioning; restore same-version volume/config on rollback, not blind downgrade. T4/T8. |
| I4 Retain, runtime / #1778/#1612 | `docker-compose.lightweight.yml`, prebuilt overrides, `scripts/compose_profiles_smoke.py`. | Lightweight profiles put logs/Grafana behind `observability`, pgAdmin/Flower behind `admin`, checks behind `testing`; logs dependency optional. PostGIS/frontend use rotated `json-file` 10m ×2 instead of syslog; backend console fallback warns. Full mode keeps syslog startup ordering. | New stores/SDK remain optional in both lite/full. With observability absent domain work still starts; do not restore fixed ports/names in agent stacks. Restore prior Compose layers/config to roll back. T8. |
| I5 Retain development evidence, scripts/tests / #1777/#1396/#1612 | `scripts/task_perf_bench.py`, `task_perf_runner.sh`, `task_perf_baseline.json`, `stack_memory_profile`; `backend/tests/django/system/_task_runtime_bench_support.py`, `test_task_runtime_bench.py`. | Offline benchmark reporting, exact run ownership and independent cgroup/process memory, query-count/runtime regression evidence. Not a deployed telemetry store, scheduler or worker admission service. Historical baseline is not today's performance. | Reuse measurements for #1777, with new matched arms/metadata; never relabel old measurements. No runtime replacement or benchmark duplication. T6/T10. |

### Domain records and protected consumers

| ID / disposition / owner | Evidence and consumers | Migration/rollback boundary / tests |
| --- | --- | --- |
| D1 Retain, notify / #1104 | `backend/notify/models.py:BackgroundProcess/BackgroundProcessLog/OperationalIncident`; `incident_reporting.py`, `incident_watchdog.py`, `tasks.py:BackgroundProcessBased/watch_operational_incidents`; query managers `visible_for_user`, permissions, serializers/views/filters/URLs, Channels consumers/routing/signals. Retry/failure/recovery and independent watchdog evidence; typed resource FKs, deduplication, safe bounded incident details. | Sampled spans and Grafana rules do not replace source job state or per-resource authorization. Preserve list/detail/count/filter symmetry, system incidents admin-only, active/resolved lifecycle and per-resource joins. Frontend `Resource/OperationalIncident/{IncidentCenter,Context}`, `Resource/BackgroundProcess/{JobCenter,BackgroundProcessLogs,BackgroundJobBridge}`, `incidentContract.ts`, translations are consumers. No schema/API change here. T7. |
| D2 Retain, registry | `registry/models/{harvest,monitoring,update,alerts,security}.py`, tasks `{harvest,monitoring,update,alerts,security}.py`, querys/serializers/views/filters of those families; `HarvestingJob.log`/`HarvestingLog`, monitoring runs/probe checks/artifacts, update/recovery state, `ServiceAlert`, proxy `HttpRequestLog` bodies, simple-history. Frontend HarvestingLog, monitoring response inspector, ServiceAlert and job screens. | These are geospatial monitoring/audit/business history, not technical OTel storage. Generic technical alert routing may move, while OGC checks, domain rules, recovery, protected files and row permissions stay. `ServiceAlert` is a materialized domain projection, not an invitation to add another generic evaluator. T7/T9. |
| D3 Retain ownership, #1497 | Existing cleanup includes dump H6, attempt C2, notify completed-process/incident cleanup and `registry.tasks.monitoring.delete_expired_probe_response_artifacts`; temporary harvest files and Redis result expiry have separate lifecycles. PR [#1738](https://github.com/mrmap-community/mrmap/pull/1738) is a draft inventory, **not merged source at this baseline**. | Native Victoria retention owns technical signal windows after cutover; #1497 retains domain/protected history. No new central technical retention engine. Preserve active jobs/incidents, minima/holds, current zero-age semantics and operator schedules; no destructive migration in this issue. T2/T3/T7/T9. |

## Exact legacy 400 ms behavior

`LogSlowRequestsMiddleware.get_duration_ms` is
`int((timezone.now() - start).total_seconds() * 1000)`. The threshold is captured
when the middleware is constructed from `LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS`
(environment `MRMAP_SLOW_REQUEST_THRESHOLD_MS`, default 400). `_response` returns
when that integer is **<=400**. Thus 400.999 ms is not logged; 401 ms is logged.
It uses a wall clock, not a monotonic duration; collection starts at this
middleware's position in the chain and ends when `get_response` returns.

It records every statement/params on Django's default `connection` in that
synchronous context, even for fast requests. It interpolates statements only
for slow responses. A slow request **with zero SQL** still warns; it has request
metadata without `metaSDID@queries`. A raised exception bypasses `_response`;
other loggers may still create an exception dump. Streaming iteration and work
after the returned response, other DB aliases/threads, nginx/static and rejected
edge requests are outside this interval. Failed/rolled-back SQL executions are
still collected by the execute wrapper's `finally`.

The proposed monotonic standard HTTP histogram counts **>0.4 s** independently
of trace sampling. That corrects the legacy integer truncation and may observe
a different middleware/streaming/exception boundary. #1781/#1782 must explicitly
report these differences and compare the common interval on 399, 400, 400.999,
401 ms, zero-SQL, exception, streaming and edge-only cases. Do not call panel
counts identical or silently introduce another permanent legacy-duration metric.
No promise of retaining every individual slow request follows from that count.

## Settings and persisted lifecycle register

`backend/MrMap/settings.py` remains authoritative. This groups **all declared
settings in the candidate families**, including in-code defaults read by the
profiler. Values here describe the baseline, not new environment options.

| Family | Settings / defaults and lifecycle |
| --- | --- |
| HTTP/dumps/logging | `LOG_LONG_RUNNING_REQUEST_THRESHOLD_MS` 400; `SLOW_REQUEST_DUMP_RETENTION_DAYS` 14; `SLOW_REQUEST_DUMP_MAX_FILES` 0; `SYSLOG_HOST/PORT` (`MRMAP_SYSLOG_HOST/PORT`) `victoria-logs:5514`; `ROOT_LOGGER_NAME/ROOT_LOGGER`, `LOGGING`, `LOG_DIR` (`MRMAP_LOG_DIR`), `LOG_FILE_MAX_SIZE` 20 MiB, `LOG_FILE_BACKUP_COUNT` 5. Console handler always, syslog conditional at startup. |
| Attempt collection | `CAPACITY_TELEMETRY_ENABLED` (`MRMAP_CAPACITY_TELEMETRY`) on; `COLLECT_ANY_PROCESS` false, `BUFFER_LIMIT` 1000, `FLUSH_THRESHOLD` 100, `FLUSH_SECONDS` 30, `RETRY_COOLDOWN_SECONDS` 60, `RETENTION_DAYS` 14, `MAX_ATTEMPTS` 200000, `ABANDON_GRACE_HOURS` 48 (all `CAPACITY_TELEMETRY_` prefix). |
| Profiling | `TASK_PROFILING_ENABLED` (`MRMAP_TASK_PROFILING`) off, `TASKS` empty, `SAMPLE_RATE` .05, `BUFFER_LIMIT` 200, `MEMORY_MIB` 128, `MEMORY_SAMPLE_SECONDS` .5 (`TASK_PROFILING_` prefix; environment exists for tasks/rate/memory knobs). Module-only defaults: `SLOW_SQL_SECONDS` .5, `MAX_SLOW_STATEMENTS` 10, `SLOW_SECONDS` 30, `SHAPE_THRESHOLD` .5. |
| Performance exporter | `TASK_PERFORMANCE_EXPORT_ENABLED` (`MRMAP_TASK_PERFORMANCE_EXPORT`) off; `WINDOW_MINUTES` 5, `MAX_BUCKETS` 200, `DRILLDOWN_CLASSES` 3, `SAMPLES_PER_CLASS` 5, `FIRST_WINDOW_MINUTES` 60 (all `TASK_PERFORMANCE_EXPORT_` prefix). Named environment values; cache cursor expires per exporter policy. |
| Detector | `TASK_PERFORMANCE_ENABLED` off (`MRMAP_TASK_PERFORMANCE`), `INTERVAL_MINUTES` 15, `WINDOW_HOURS` 24, `MIN_SAMPLES` 5, `DEFAULT_BUDGET_SECONDS` 600, `DEFAULT_LONG_SECONDS` 1800, `LONG_MIN_ACTIVE_SECONDS` 60, `LONG_GRACE_SECONDS` 300, `REGRESSION_FACTOR` 2, `SPIKE_SHARE` .10, `REGRESSION_MIN_BASELINE_SECONDS` 1, `MAX_CLASSES` 200, `MAX_VERDICTS_PER_FIRE` 25, `COVERAGE_MIN_STAMPED` .5, `ABANDON_STALE_HOURS` 6, `STALE_AFTER_HOURS` 72, `POLICY` {}, `POLICIES` env JSON (all `TASK_PERFORMANCE_`). No broad detector expansion. |
| Capacity projection | `CAPACITY_TOPOLOGY_CACHE_SECONDS` 60, `TIMEOUT_SECONDS` 1; `CAPACITY_SNAPSHOT_TTL_SECONDS` 900, `HORIZON_DAYS` 7, `MAX_HORIZON_DAYS` 31, `BUILD_LOCK_SECONDS` 300, `MIN_REBUILD_SECONDS` 60, `BUCKET_SECONDS` 3600, `MAX_BUCKETS` 744, `MAX_SCHEDULES` 100000, `MAX_OCCURRENCES` 2000000, `MAX_OCCURRENCES_PER_SETTING` 20000; `CAPACITY_FINGERPRINT_CACHE_SECONDS` 30; `CAPACITY_COST_LOOKBACK_DAYS` 7, `MIN_SAMPLES` 3, `GROUP_LIMIT` 5000; `CAPACITY_RHO_ADVISORY_THRESHOLD` .7. Short names inherit the nearest full prefix. |
| Domain/status/runtime | `SYSTEM_STATUS_DOCKER_URL/PROJECT`; `BACKGROUND_PROCESS_RETENTION_DAYS` 90, `OPERATIONAL_INCIDENT_RETENTION_DAYS` 90, `MONITORING_PROBE_RESPONSE_MAX_SIZE` 5 MiB, `MONITORING_PROBE_RESPONSE_RETENTION_DAYS` 30; `CELERY_RESULT_EXPIRES` 86400s, worker recycling/revocation, HTTP process/DB-pool knobs remain under existing runbooks. Module defaults in `notify/apps.py` / `incident_watchdog.py`: `OPERATIONAL_WATCH_INTERVAL_MINUTES` 5, `RETRY_GRACE_MINUTES` 15, `RETRY_LOOKBACK_HOURS` 24, `MAX_VERDICTS` 25 (all `OPERATIONAL_WATCH_`). These are retained families, not new technical observability settings. |

| Persisted surface | Existing creation/retention and future migration constraint |
| --- | --- |
| `system_celerytaskattempt` | `backend/system/migrations/0002_celery_attempt_samples.py`; `0003_text_columns_reject_null.py`, `0004_alter_celerytaskattempt_parent_id_and_more.py`, `0005_celerytaskattempt_attempt_recorded_idx.py` refine data/columns/retention index. Keep history; never edit these generated artifacts for retirement. `0001_removes_the_scheduled_refresh_of_the_statistics_views.py` already retires an unrelated old task and must not be undone. |
| Beat rows, `django_celery_beat_*` | `system/apps.py` post-migrate: dump cleanup :05 hourly; attempt bounding :50 hourly; capacity refresh :13,:28,:43,:58 (comment says twice hourly but code is four); performance detector interval default 15m, row remains while disabled; exporter cadence default :02 every 5m, row only created while enabled and its own named row deleted on migrate while disabled. Operator-renamed rows are not inferred disposable. |
| Notify rows and schedules | `notify/migrations/0001_initial.py` process/log foundation, `0010_operationalincident.py` typed incidents and later constraint/data migrations retained. `notify/apps.py` process cleanup :30, resolved-incident cleanup :40 hourly; independent incident watch interval. Do not remove all PeriodicTask rows sharing a crontab. |
| Domain monitoring/history/proxy/alerts | Registry `0001_initial.py`, `0013_catalogueservicemonitoringrun_and_more.py`, `0037_store_the_rows_of_the_alerts.py` and subsequent migrations establish domain data; retained in full. Probe-body cleanup :20 hourly (`registry/apps.py`). Domain migration/retention changes belong to their owners. |
| Files/cache/volumes | `MEDIA_ROOT/logs`, protected domain media and `BackgroundProcessLog.extented_description` are different stores; no broad `MEDIA_ROOT` sweep. Attempt/profile buffers and snapshot/export cursors are not durable job truth. Victoria `vlogs-data`, Docker `json-file`, Beat heartbeat and Celery statedb each have distinct lifecycle/backup policies. No automatic volume/disk deletion or reinterpretation of historical data. |

## Coverage differences that block automatic retirement

| Required answer | Existing evidence | What OTel/Victoria can and cannot replace |
| --- | --- | --- |
| #1390 completed outlier | Terminal attempts, class budgets and bounded exact exceedance/coverage. | Unsampled histograms/counters give aggregate exceedances; selected spans give examples. They do not identify every finished outlier or exactly deduplicate redelivery. Keep per-attempt facts if that guarantee is required. |
| Regression versus isolated spike | Current/baseline windows, minimum samples, p50/p95, per-attempt slot cost and spike-share policy. | Native rules can compare histogram windows, with approximate quantiles, sufficient counts and coverage checks. Sparse/changed population or missing exporter is unknown; do not translate one p95 threshold into the same verdict. |
| Currently active long-running task | Open attempt plus answering owner worker's active IDs, grace, absent/stale confirmation handling and resolution evidence. | A span normally exports after it ends; a last gauge value or absent terminal span does not confirm active work. Retain independent bounded Inspect/lifecycle/watchdog path. |
| Queue wait versus workflow elapsed | Trusted publish stamp/start, coverage; root/job tables separately own end-to-end time. | Upstream task-body duration does not supply those two durations. Independent wait histogram plus coverage may replace aggregates; job elapsed remains domain-owned. |
| Capacity inputs | Registered queues, unique shared pools/slots, subscription topology, ready/reserved/scheduled/unacked counts, schedule horizon/dispatch/cost, bounds and confidence. | Standard duration metrics can supply measured cost after parity. They do not produce the authoritative schedule projection, shared-pool accounting, admission policy or complete queue state. Keep #1324/#1326 semantics. |
| Task memory peaks / #1612 | Profiler `VmHWM` change, start/end RSS retained growth, private dirty, sampled near-limit ratio and current cgroup ceiling; benchmark procfs/cgroup evidence. | Process gauges sample current memory. They miss transient task peaks, cannot attribute lifetime HWM to each attempt, and do not equal PSS/private dirty. Keep opt-in attribution/native evidence until matched-workload parity, with unavailable fields absent/unknown. |
| Offline/disabled/failed collection | Domain records independent of technical stores; bounded telemetry loss/quality/coverage. | Sampled or dropped traces cannot prove success or absence of jobs. Show disabled, unavailable, insufficient, stale, truncated and measured-zero distinctly. Missing metrics must never auto-resolve protected incidents. |

## Verification register

These are **existing** tests/commands to retain or adapt in their owning change;
they were inspected, not executed as application suites by this docs-only audit.
Paths beginning `test_` below are under `backend/tests/django/system/` unless
qualified. No database/Docker workload was started.

| Key | Existing regression surface |
| --- | --- |
| T1 | `test_logging.py`, `test_formatter.py`; zero-query warnings, threshold/metadata, SQL interpolation/types, formatter exceptions and suppression. |
| T2 | `test_slow_request_dumps.py`, `test_syslog_fallback.py`, `backend/tests/django/test_media_serving.py`; age/count, schedules, disk failure, local fallback, GET/HEAD and private/symlink/dot path refusals. |
| T3 | `test_capacity_telemetry.py`, `test_capacity_measures.py`, `test_capacity_topology.py`, `test_capacity_demand.py`, `test_capacity_snapshot.py`, `test_remove_refresh_task_migration.py`; lifecycle, dedup, windows, limits, unknowns, materialization and retired task. |
| T4 | `test_task_performance_export.py`, `test_task_performance_dashboard.py`; message encoding, samples/caps/cursor/fresh coverage and every dashboard query/field contract. |
| T5 | `test_task_performance.py`; completed/regression/spike/active/queue/coverage/resolution/incident scope and policy parsing. |
| T6 | `test_task_profiling.py`, `test_task_runtime_bench.py`, `_task_runtime_bench_support.py`, `test_task_sql_guards.py`; opt-in, failure handling, memory/SQL/HTTP semantics and static query guard. |
| T7 | `backend/tests/django/notify/test_incidents.py`, `test_incidents_api.py`, `test_incident_publishers.py`, `test_incident_watchdog.py`, cancellation/BackgroundProcess tests; Behave `tests/behave/features/json:api/notify/operationalincident/list_operationalincidents.feature`; frontend `Resource/OperationalIncident/{IncidentCenter,Context}/*.spec*`, `Resource/BackgroundProcess/**/*.spec*`. Preserve unauthorized list/detail/count/filter behavior. |
| T8 | `test_status.py`, `test_worker_healthcheck.py`, `test_system_endpoints_permissions.py`; Behave `tests/behave/features/json:api/system/system_endpoints_admin_only.feature`; frontend `Resource/System/SystemStatus.spec.tsx`; `scripts/test_compose_profiles_smoke.py`, `scripts/static_mounts_smoke.py`, `scripts/nginx_routing_smoke.py`, healthcheck/memory evidence runbooks. |
| T9 | Existing registry tasks/tests for harvesting import recovery/watchdog, monitoring/probe artifacts, service update/history, alerts, proxy/auth/private media; `registry/tasks/tests_harvest_import_watchdog.py` is an explicit lifecycle boundary. Retain these suites in the owning implementation; no OTel assertion replaces them. |
| T10 | `scripts/test_task_perf_bench.py`, `test_stack_memory_profile.py`; #1396 benchmark and `task-memory-shapes`, `runtime-memory-baselines`, `celery-healthcheck-overhead`, `http-process-profiles`, `db-pool-memory` runbooks. |

CI sources: `.github/workflows/quality-assurance.yml`, `docs.yml`, `script-tests.yml`.
Use the nearest AGENTS.md for actual area checks and isolated Compose ownership.
Do not start another stack without operator/external-environment admission.

## Reproducing this audit and protocol probe

Read-only source discovery from the repository root:

```bash
git rev-parse origin/develop
git log origin/develop --oneline --grep='#1389\|#1390\|#1391\|#1396'
rg -n 'structured_data|suppress_dump|exc_info' backend --glob '*.py'
rg -n 'capacity_telemetry|capacity_measures|task_profiling|task_performance' backend frontend/src docker scripts docs
rg -n 'CAPACITY_|TASK_PROFILING_|TASK_PERFORMANCE_|SLOW_REQUEST_|SYSLOG|LOGGING|SYSTEM_STATUS_' backend/MrMap/settings.py
rg -n 'create_.*task|post_migrate' backend/system/apps.py backend/notify/apps.py backend/registry/apps.py
rg -n 'image:|logging:|healthcheck:|profiles:|retention' docker-compose*.yml
rg --files backend/system/migrations backend/tests/django/system docker/grafana/provisioning
```

The [synthetic probe](evidence/observability-1776-probe.py) has no MrMap imports,
real credentials, application payloads or live service targets. It runs only an
ephemeral loopback protobuf capture receiver. It demonstrates cumulative explicit
histograms with a 0.4 boundary, metric recording with trace sampling off, bounded
batched trace export and exporter refusal without changing the synthetic work.
It also verifies the SDK's two ordinary series plus one overflow behavior. It
tests the SDK/view, **not instrumentation redaction or actual Victoria storage**.
The [recorded result](evidence/observability-1776-results.json) states the interpreter,
versions, observations and remaining blockers. Reproduce in a disposable venv:

```bash
set -eu
MRMAP_OBS_PROBE_DIR=$(mktemp -d /tmp/mrmap-1776-probe.XXXXXX)
trap 'rm -rf -- "$MRMAP_OBS_PROBE_DIR"' EXIT
python3 -m venv "$MRMAP_OBS_PROBE_DIR/venv"
"$MRMAP_OBS_PROBE_DIR/venv/bin/pip" install \
  opentelemetry-sdk==1.45.2 \
  opentelemetry-exporter-otlp-proto-http==1.45.2
OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=CUMULATIVE \
  NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
  "$MRMAP_OBS_PROBE_DIR/venv/bin/python" \
  docs/source/development/evidence/observability-1776-probe.py
```

For reproducible deployed dependencies, #1779 must freeze/hash the entire
transitive closure on the target image; this two-pin SDK probe is not a production
lockfile. Published metadata can be checked without a deployment:
`https://pypi.org/pypi/<package>/<pinned-version>/json` (`requires_python`,
`requires_dist`, classifiers, wheel hashes). The probe environment also installed
Django/Celery/requests **instrumentation packages** `0.66b2` for source/metadata
inspection; no Django/Celery application or database was installed or exercised.

Remaining verification blockers are explicit: target Python 3.15.2/app smoke,
actual Victoria ingestion/query/datasource and plugin pinning, fork/restart and
multi-process cumulative streams, redaction/propagation on real instrumentation,
and admitted matched performance/outage workloads. No disposable Docker stack
was admitted or started in this audit. These belong to #1777–#1780 and block
cutover, not completion of the documentation-only inventory with recorded limits.

Before each retirement, update its row with the repaired develop SHA, actual
consumer tests, operator settings/schedule snapshot, historical retention/backup
decision, rollout owner and rollback evidence. Preserve #1104 resource visibility
and #1497 data protection; native observability retention is not domain deletion
authority.
