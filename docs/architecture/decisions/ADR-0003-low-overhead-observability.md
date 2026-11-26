# ADR-0003: Low-overhead technical observability

**Status:** Proposed

**Date:** 2026-11-26

**Issue:** [#1776](https://github.com/mrmap-community/mrmap/issues/1776),
epic [#1775](https://github.com/mrmap-community/mrmap/issues/1775)

**Source baseline:** `bc3e516b6cefdd6ec13de3945a6615e89d69a64d` (`develop`)

## Context

MrMap currently combines SQL-bearing HTTP dumps, buffered task-attempt rows,
opt-in root-cause profiles, log-based task metrics, Docker health observations
and permission-filtered operational incidents. These answer different questions.
The inventory (`docs/source/development/observability-inventory.md`,
{ref}`observability-inventory` in the portal) records their
producers, consumers, settings, schedules, storage, tests and rollback boundaries.
It includes the merged #1389/#1390/#1391/#1396 work; the parent #1387 remaining
open does not mean that work is absent.

The maintainer's standard-first direction on #1775 authorizes evaluating upstream
instrumentation and the existing Victoria/Grafana ecosystem. It does not authorize
dropping reliable job evidence, widening permissions, changing retention, or
claiming measured overhead from a protocol experiment. This ADR proposes the
contract for the child implementations; acceptance still requires human review.

## Decision

### Reuse and versions

Use explicit upstream Python SDK initialization and Django, Celery and requests
instrumentation. Compose three optional single-node stores with the existing
Grafana UI. Send OTLP/HTTP protobuf directly to each signal's endpoint. Keep
console logging usable independently. No Collector, new alert evaluator,
application time-series table, frontend tracing or agent runtime is required.

Freeze this evaluation set, rather than referring to `latest`:

| Component | Evaluation pin | Evidence / compatibility limit |
| --- | --- | --- |
| OTel API, SDK, OTLP protobuf/HTTP exporter | `1.45.2` | [Published metadata](https://pypi.org/pypi/opentelemetry-sdk/1.45.2/json); API and semantic-conventions requirements match the release train. |
| OTel Django, Celery, requests, WSGI/ASGI, instrumentation base, semantic conventions and HTTP utilities | `0.66b2` | [Upstream release](https://github.com/open-telemetry/opentelemetry-python-contrib/releases/tag/v0.66b2). Instrumentation remains beta; pin and regression-test it. This package version is not a semantic-convention schema version. |
| VictoriaMetrics single-node | `victoriametrics/victoria-metrics:v1.157.0` | [Release](https://github.com/VictoriaMetrics/VictoriaMetrics/releases/tag/v1.157.0); cumulative OTLP explicit histograms selected. |
| VictoriaTraces single-node | `victoriametrics/victoria-traces:v0.13.0` | [Release](https://github.com/VictoriaMetrics/VictoriaTraces/releases/tag/v0.13.0); pre-1.0 storage/query compatibility needs upgrade/restore tests. |
| VictoriaLogs | existing `victoriametrics/victoria-logs:v1.54.0` | Keep the shipped version; its OTLP logs endpoint is documented by [upstream](https://docs.victoriametrics.com/victorialogs/data-ingestion/opentelemetry/). |
| Grafana | existing `grafana/grafana:13.3.2` | Keep shipped image. Existing `victoriametrics-logs-datasource` is **unpinned** in `GF_PLUGINS_PREINSTALL`; #1778 must freeze a tested plugin version and image digests, including the traces datasource, before claiming reproducibility. |
| Application compatibility targets | Python `3.15.2-alpine3.24`, Django `6.0.10`, Celery `5.7.0`, requests `2.34.2`, psycopg `3.3.9`, Redis client `8.2.0` | From Dockerfile and requirements at the baseline. Metadata admits Django >=2.0, Celery >=4,<6, requests ~=2.0; this is dependency compatibility, not demonstrated runtime compatibility. |

OTel metadata requires Python >=3.10 and advertises classifiers through 3.14.
The disposable probe runs on the available host Python 3.14.4. **Python 3.15.2
integration is unverified**, not declared incompatible solely from classifiers.
Do not downgrade MrMap or loosen its pins to make the evaluation pass.
#1779 must resolve and exercise the complete dependency set on the actual image.
Optional psycopg/Redis instrumentation is deferred until a privacy-safe, pinned
diagnostic configuration is demonstrated; neither is enabled in standard mode.

OTel and the Victoria components use Apache-2.0; Grafana OSS uses AGPL-3.0.
Verify the selected image/plugin license manifests and advisories in #1778/#1779;
this records license families, not a security or legal certification. These are
maintained upstream projects; no additional mandatory service is justified.
Runtime/dependency changes belong to those issues, not this documentation PR.

| Alternative | Evaluation | Choice / remaining integration |
| --- | --- | --- |
| Existing MrMap diagnostics | Reliable per-attempt and domain evidence, but SQL dumps and parallel technical exporters cost disk/DB work. | Retain authority and migrate only the technical portions with parity. |
| Native Django/PostgreSQL, procfs/cgroups, Celery Inspect/Events and Docker health | Good development/query plans, memory and liveness sources; cannot alone provide correlated sampled traces and unsampled HTTP histograms. | Reuse; do not build replacements for those facilities. |
| Direct SDK OTLP/HTTP | Native ingestion for all three stores, no protocol translation or additional process. | Selected; small application-local lifecycle/privacy adapters and domain metrics remain necessary. |
| OTel Collector | Useful for independently evidenced fan-out, protocol translation or centralized policy. Adds memory, configuration, another failure boundary and upgrade surface. It cannot redact data before it leaves the application. | No demonstrated need. Reconsider in a successor decision only after direct-path measurements identify a requirement. No tail sampling by default. |
| Prometheus scrape exporter / extra agent | Introduces a per-process/multiprocess scrape integration alongside the chosen OTLP path. | No demonstrated benefit for this scope. Do not run two metric pipelines. |

### Endpoints and storage

Use **signal-specific complete URLs**, since these are different paths and ports:

| Signal | Internal endpoint | Initial retention proposal |
| --- | --- | --- |
| Metrics | `http://victoria-metrics:8428/opentelemetry/v1/metrics` | 90 days |
| Traces | `http://victoria-traces:10428/insert/opentelemetry/v1/traces` | 7 days |
| Logs, after #1785 | `http://victoria-logs:9428/insert/opentelemetry/v1/logs` | Existing 14 days; changes require policy review |

The native [metrics ingestion contract](https://docs.victoriametrics.com/victoriametrics/integrations/opentelemetry/)
and [traces ingestion contract](https://docs.victoriametrics.com/victoriatraces/data-ingestion/opentelemetry/)
support this topology. Set `OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=CUMULATIVE`.
Use explicit histogram boundaries, not exponential histograms, for the 0.4 s
cutoff. Configure Prometheus naming explicitly with
`-opentelemetry.usePrometheusNaming`; freeze the actual ingested names and queries
in the #1778 probe. Disable promotion of arbitrary resource attributes and promote
only the resource allowlist below. Give each process an internal writer identity
to distinguish cumulative streams; it is not a user-controlled metric dimension.
Demonstrate that simultaneous processes and restarts do not overwrite or double
count each other's cumulative series before fleet aggregation is accepted.

Store data on separate named volumes, with no host-published ingestion/query
ports in the reference stack. Grafana authentication grants operator access;
it does not implement MrMap object permissions. An external OTLP endpoint is an
operator option with TLS, isolated credentials, validated destination and finite
timeouts. No credentials enter telemetry or public client configuration. No
assumption of vendor/cloud accounts. Retention bounds time, not bytes: #1778
must set measured memory/disk ceilings and document disk-full behavior.

### Signal contract

Names below are **OTel instrument names**, not guessed Victoria query names.
Use stable HTTP semantics (`OTEL_SEMCONV_STABILITY_OPT_IN=http`, no duplicate old
HTTP metrics). The
[HTTP metric specification](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/)
supplies the duration name/unit; the `mrmap.*` names describe domain-specific
distinctions upstream Celery timing does not promise.

| Instrument | Type / unit | Allowed point attributes | Meaning and missing data |
| --- | --- | --- | --- |
| `http.server.request.duration` | Histogram / `s` | `http.request.method`, `url.scheme`, `http.route`, `http.response.status_code`, bounded `error.type` | All observed requests, independent of trace sampling; count/sum, p50/p95/p99 and >0.4 s count. Zero only within an observed window. |
| `http.client.request.duration` | Histogram / `s` | `http.request.method`, `http.response.status_code`, bounded `error.type`, `mrmap.remote.kind` | Remote waiting, with kind `wms`, `wfs`, `csw`, `other`; no endpoint labels. Diagnostic mode initially. |
| `mrmap.task.attempt.duration` | Histogram / `s` | `mrmap.task.class`, `mrmap.queue`, `mrmap.task.outcome` | Worker occupancy including blocking HTTP, one terminal attempt; retries are distinct attempts. Not job elapsed or CPU. |
| `mrmap.task.queue.wait` | Histogram / `s` | `mrmap.task.class`, `mrmap.queue` | Published-to-start time only where a valid trusted publish stamp exists. No value for absent/negative stamps. |
| `mrmap.task.attempts` | Counter / `{attempt}` | `mrmap.task.class`, `mrmap.queue`, `mrmap.task.outcome` | Unsampled terminal observations; cannot prove delivery/execution exactly once after worker death/redelivery. |
| `mrmap.task.observations` | Counter / `{observation}` | `mrmap.task.class`, `mrmap.queue`, `mrmap.observation.quality` | Bounded quality: `stamped`, `unstamped`, `invalid_stamp`, `dropped`; coverage denominator separate from successful timings. |
| `mrmap.telemetry.dropped` | Counter / `{item}` | `mrmap.signal`, `mrmap.drop.reason` | `traces/metrics/logs` and `queue_full/export_error/cardinality`; observable locally even if export is unavailable. SDK-native diagnostics first; adapters only for gaps. |

The HTTP duration view uses explicit boundaries in seconds:
`0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.4, 0.5, 0.75, 1, 2.5, 5, 7.5, 10`.
The implicit final bucket is +Inf. Compute slow count from total count minus the
cumulative `le="0.4"` bucket, aggregated over the same observed interval/writers;
this excludes exactly 0.4 s. Histogram quantiles are approximations. Task
boundaries extend to `30, 60, 120, 300, 600, 1800, 3600, 14400` s and must be
checked against #1396 workloads. Do not subtract independent percentiles to
infer queue wait or CPU time. The [SDK view contract](https://opentelemetry.io/docs/specs/otel/metrics/sdk/)
supports projecting attributes and controlling aggregation; test support in the
pinned Python implementation rather than relying on specification alone.

The inspected Celery `0.66b2` instrumentor emits
`flower.task.runtime.seconds` (unit `seconds`, attributes `task`, `worker`), not
the `mrmap.*` contract above; it also attaches message IDs and retry reasons to
spans. Disable that default metric stream with a drop view when introducing the
domain adapter, remove the forbidden dimensions before aggregation, and test
unsampled recording explicitly. Merely enabling the instrumentor does not meet
the metric or privacy contract. Its [tagged source](https://github.com/open-telemetry/opentelemetry-python-contrib/blob/v0.66b2/instrumentation/opentelemetry-instrumentation-celery/src/opentelemetry/instrumentation/celery/__init__.py)
is part of the compatibility evidence.

There is no standard-mode active-task gauge whose zero claims no work exists.
Active confirmation remains bounded worker Inspect plus the existing per-attempt
and job evidence. Optional process memory/CPU metrics describe a process, not the
peak of an individual task. No per-attempt UUID, worker name, resource ID,
periodic schedule name or trace ID is a metric dimension.

### Privacy, cardinality and propagation

Allowlist before serialization/export, including resources, span names/events,
status descriptions, links and log bodies. Header redaction alone is insufficient.
Stock instrumentation can produce URL, exception, messaging and database details;
an end hook that merely adds safe fields does not remove those defaults. #1779
must demonstrate public SDK/processor/view seams that enforce this policy, or
leave the relevant instrumentation disabled and report the blocker.

* Resource attributes: configured `service.name` (`mrmap-http`, `mrmap-worker`,
  `mrmap-beat`), `service.version`, bounded `deployment.environment.name`, SDK
  identity, and an internal `service.instance.id` only for writer separation.
  Do not use automatic host/cloud/container/resource detectors. Deployments and
  release churn must be included in the stored-series budget.
* HTTP methods: the nine standard methods or `_OTHER`. Routes: registered Django
  templates, with fixed `unmatched` and `unresolved` values; never substitute
  `request.path` on a resolver miss. Status: integer 100..599 or absent if no
  response. Scheme: `http` or `https`. Errors: a finite reviewed category such as `timeout`, `connection`,
  `server`, `other`; no free-form exception message/class supplied by plugins.
* Tasks: registered first-party names mapped to a reviewed class allowlist;
  unknown names become `other`. Queues: declared queues or `other`. Outcomes:
  `success`, `failure`, `retry`, `revoked`, `unknown`. Do not attach arguments,
  kwargs, results, payload sizes that identify a resource, or dynamic task names.
* Deny SQL text and binds (including sanitized statement signatures in exports),
  full URLs, hostnames of OGC services, paths/query strings, request/response
  bodies, cookies/auth headers, API keys, account/IP/user-agent identifiers,
  raw stack traces, task/root/parent UUIDs and job/resource IDs. Trace/span IDs
  are protocol correlation fields and may appear in sanitized operator logs;
  they are never authorization tokens, application resource links or labels.
* Privacy applies to log messages too. Replacing the formatter with an OTLP
  logging handler does not sanitize existing f-strings or exception text.
  Resource-scoped records remain under existing API permissions; do not export
  their raw details into global operator stores.

Provisional limits: at most 200 task classes, 16 queues (validate against the
actual registry), 500 route templates and 2,000 attribute sets per instrument,
reader and process. A finite cross-product is not automatically small: 500 routes
times methods/statuses can exceed the instrument budget. Apply an SDK cardinality
limit: `View(aggregation_cardinality_limit=1999)` in the inspected `1.45.2`
implementation leaves room for its additional single `otel.metric.overflow`
series, for 2,000 total points. Overflow degrades dimensional coverage; include
the overflow point in fleet totals. The synthetic probe verifies this limit-plus-one
behavior with a smaller cap. Never treat overflow as a regular route/task class.
Views remove forbidden dimensions **before aggregation**, not at export time
after they already consumed memory. At most 32 span attributes, values <=128
characters, 8 sanitized events/links and 8 KiB per sanitized log record.
These caps and queue counts are hypotheses for #1780, not measured memory bounds.

Accept W3C `traceparent`/`tracestate` only across an explicitly trusted internal
ingress/broker boundary. Public nginx/backend ingress ignores caller context and
starts a local root so attackers cannot force parent sampling. Do not ingest
or inject baggage. A proxy merely present in front of Django is not trusted
unless it strips untrusted headers and its identity is enforced.
An upstream trusted sampled parent may be honored; public traffic uses the
local 1% head-sampling decision. Trust policy precedes sampling.

Propagate only between trusted MrMap producers/workers through the internal
broker. Outgoing arbitrary OGC traffic receives no `traceparent`, `tracestate`
or `baggage`, including retries, redirects and caller-supplied PreparedRequest
headers. A host allowlist applied only to the initial URL is insufficient:
strip at each actual send/redirect boundary. Use upstream suppression/context
controls and the existing outbound request seams; do not replace the HTTP
transport. Record a local sanitized client span if safe suppression of injection
can be demonstrated independently. Otherwise disable requests instrumentation
for that destination. Exporter traffic and Docker/telemetry queries are excluded
from HTTP instrumentation to prevent recursion. Capture tests must inspect the
actual redirected request headers and decoded OTLP bodies.

### Process lifecycle and failure contract

Disabled means no instrumentor patching, providers, exporter threads, DNS lookups,
required telemetry services or telemetry-specific SQL/file/network work. Retained
domain lifecycle/watchdog and console logging still work. Legacy diagnostics have
their own switches; this new mode must not implicitly turn them off.

Initialize once per process after fork: Gunicorn worker `post_fork`/application
startup, including preload on/off; ASGI serving processes; Celery
`worker_process_init` for prefork children and explicit producer initialization
in web/Beat processes. Do not start SDK background threads in `AppConfig.ready`
in a prefork parent. Avoid both explicit wrapping and `opentelemetry-instrument`
on the same service. Upstream
[Celery guidance](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/celery/celery.html)
requires child initialization; the [fork examples](https://opentelemetry-python.readthedocs.io/en/latest/examples/fork-process-model/README.html)
motivate exercising the selected release rather than assuming fork safety.
Task instrumentation must not change the existing connection lifecycle receivers.

Production starting hypothesis: parent-based trace sampling 1%; independent,
unsampled metric aggregation; batch span/log queues <=512 items, batches <=128,
5 s scheduling delay, export timeout 1 s including bounded retries; metric
reader every 30 s with bounded collection/export time. Per-worker cumulative
streams reset on restart and are distinguished by writer identity. No
`SimpleSpanProcessor` or `force_flush` on request/task paths. Metric callbacks
may read cheap process-local state, not run database/broker/remote probes.

Exporter refusal, timeout, DNS/TLS failure, full queue or dead store never changes
HTTP status, task outcome/retry, acknowledgement or job state. Drop technical
telemetry after bounded retries; no disk spool or fallback telemetry DB writes.
No recursive logging of exporter errors; use bounded/rate-limited local diagnostics
and observable drop/last-success state. Store unavailability makes coverage
unknown. Never evaluate absent-series as a healthy zero or resolve a domain
incident because the exporter stopped. Shutdown attempts one bounded drain in
process teardown; hard kills may lose buffered data. SDK processors/readers and
exporters must share one ownership/shutdown path and not be recreated per request.

Debug mode remains explicit, task/route-allowlisted and bounded in sample rate,
volume and duration (initial maximum 15 minutes), with documented restart/revert
to standard or disabled mode. Never permit SQL binds or raw bodies in debug mode.
Use native development `assertNumQueries`, `QuerySet.explain` and PostgreSQL
EXPLAIN for SQL diagnosis. No automatic tail sampling or per-outlier full dump.

## Validation

The inventory's probe/evidence section distinguishes source inspection, published
metadata and an SDK-to-local-receiver experiment from real store/application
compatibility. The experiment is deliberately insufficient to retire anything.
The following are implementation gates, with no threshold weakening on failure:

1. #1778: pinned image digests/plugins; actual direct export **and query** against
   all selected stores; cumulative two-process/restart behavior, histogram names,
   0.4 bucket, Grafana datasource queries, retention and backup/restore/disk-full.
   A protobuf receiver returning 200 is not store verification.
2. #1779: full dependency resolution and HTTP/Celery smoke on Python 3.15.2;
   prefork/preload/ASGI/worker recycling, no double instrumentation, actual payload
   redaction and redirect/header trust tests; disabled mode starts no SDK work.
3. #1777/#1780: matched repeated post-#1387 workloads, warmup and jitter/confidence,
   legacy disabled/shipped, OTel disabled/standard/debug and shadow-overlap modes.
   Mean HTTP <=+2%, p95 <=+5%, harvest wall time <=+3%, throughput loss <=3%, CPU
   <=+5% relative, incremental private/PSS <30 MiB per instrumented process.
   Record cgroup ancestors/peak and total stack/disk limits separately; these
   per-process budgets do not approve a total stack budget. Reuse #1396 evidence.
4. #1780: failure injection (offline/slow/rejecting backend, full queues, worker
   kill/restart, disk-full) proves bounded resources, no application-path exporter
   I/O/telemetry writes, and truthful missing-data behavior. Privacy failures stop
   rollout even if performance is green.
5. #1781/#1782: compare slow-request coverage with the exact legacy semantics in
   the inventory; retain access refusal and existing dump retention through the
   historical-data drain. #1783/#1786/#1787/#1788 must pass the task/capacity
   differences matrix before retiring their respective consumers.

## Consequences

HTTP aggregates can cover all observed requests even when most traces are not
kept. Sampled traces cannot promise individual evidence for every slow request,
failure, attempt, memory peak or long-running task. If the product needs that
promise, a separately reviewed bounded sanitized metadata event is required;
the old SQL capture is not the fallback. Export failures can lose signals.

The standard libraries remove technical pipeline work only after validation.
Some custom code deliberately remains for MrMap resource authorization,
authoritative lifecycle, schedule/capacity semantics, sanitized domain metrics
and process integration. The inventory classifies these as partial replacement
or retain; there is no target lines-of-code deletion or automatic table removal.

## Implementation

This issue changes documentation and synthetic evidence only. The proposed
contract is reviewed through this PR; it is not an `agent: approved` label,
production cutover or a grant to merge. #1777/#1778/#1779 can implement their
own safe slices against develop after the #1776 review. No generic engine or
mandatory external dependency is introduced here.

Rollout: collect baseline; deploy optional stores; enable bounded sanitized
instrumentation; measure overlap; switch one consumer at a time; stop legacy
writers only after parity; retain old data/protected routes/cleanup for their
retention window. Remove schema only in a later generated, reviewed reversible
migration after backup and all readers are migrated. Keep alert ownership unique
through cutover (shadow evaluation must not notify twice).

Rollback: disable OTel and restart affected processes, restore the previous
dashboard/datasource and legacy settings/schedules recorded by the operator;
preserve volumes and historical rows/files. Existing domain functionality must
run with all optional stores absent. Do not automatically enable SQL-bearing
legacy capture during rollback: restoring that mode is a conscious operator
choice with its existing privacy/access policy. No live deployment, data or
schedule is modified by this ADR.
