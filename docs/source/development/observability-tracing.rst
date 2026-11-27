.. _observability-tracing:

========================
Request and task tracing
========================

Issue #1779 adds the optional OpenTelemetry integration of the epic (#1775): upstream
Django/WSGI/ASGI, Celery and requests instrumentation with MrMap's own lifecycle, privacy
and trust rules around it. The binding contract is
``docs/architecture/decisions/ADR-0003-low-overhead-observability.md``; this page is the
operator-facing version of the same rules — what to set, what a process does with it, and
what an answer from the store means.

Nothing here is required to run MrMap. The integration is **off** by default and an
uninstrumented deployment is a fully supported deployment.

Off means off
=============

``MRMAP_OTEL_MODE`` is the switch, and its shipped value is empty, which reads ``off``.
While the mode is off, the process:

* imports nothing of the SDK and patches no library — the lifecycle returns before the
  first OpenTelemetry import, so ``requests``, Django and Celery are the libraries the
  deployment installed;
* creates no provider, no exporter thread and no queue;
* performs no DNS lookup for a collector address, so a stack without the telemetry
  services of #1778 boots and stays healthy;
* connects no Celery receiver, which is the difference between "a hot path checks a flag"
  and "there is no hot path".

An unknown mode spelling — a typo, a mode a newer release removed — also reads ``off`` and
says so once at boot. The fail-safe answer of every knob in this package is the cheap one.

The three modes
===============

``standard``
  The contract of ADR-0003: server spans and HTTP duration histograms from the upstream
  instrumentations, Celery task spans, and the ``mrmap.*`` task metrics — all filtered
  through the allowlist, sampled parent-based, aggregated independently of the sampler.
``diagnostic``
  Standard plus the extras an operator asks for: outbound client spans for the OGC fetches
  and, if the pinned extra is installed and the knob is on, psycopg and Redis spans. A
  forgotten ``diagnostic`` deployment stops paying for the extras by itself after
  ``MRMAP_OTEL_DEBUG_MAX_MINUTES`` (15 by default); the standard contract keeps working.
``off``
  Nothing above, at no cost.

Every knob, with its default
============================

Read once while the settings load, so a process can answer "which mode am I in" without
the SDK, without a socket and without Django's app registry.

.. list-table::
   :header-rows: 1
   :widths: 32 14 54

   * - Variable
     - Default
     - Meaning
   * - ``MRMAP_OTEL_MODE``
     - ``off``
     - ``off``, ``standard`` or ``diagnostic``; anything else is ``off``.
   * - ``MRMAP_OTEL_SERVICE_NAME``
     - ``mrmap``
     - ``service.name`` of the resource. Name the tier (``mrmap-http``,
       ``mrmap-worker``) when one collector serves several.
   * - ``MRMAP_OTEL_SERVICE_VERSION``
     - the ``VERSION`` file
     - ``service.version``; the canonical version of #1579 unless overridden.
   * - ``MRMAP_OTEL_DEPLOYMENT_ENVIRONMENT``
     - empty
     - ``deployment.environment.name``, the only environment label exported.
   * - ``MRMAP_OTEL_TRACES_ENDPOINT``
     - empty
     - Complete OTLP/HTTP URL of the trace store, e.g.
       ``http://victoria-traces:10428/insert/opentelemetry/v1/traces``. Empty means no
       span pipeline at all: no batch thread, no queue, no lookup of a collector.
   * - ``MRMAP_OTEL_METRICS_ENDPOINT``
     - empty
     - Complete OTLP/HTTP URL of the metric store, e.g.
       ``http://victoria-metrics:8428/opentelemetry/v1/metrics``. Empty keeps the
       aggregation (that is where the cardinality bound lives) and exports nothing.
   * - ``MRMAP_OTEL_TRACES_SAMPLE_RATIO``
     - ``0.01``
     - Head ratio for a root span this process created. A propagated parent from a trusted
       source decides for its own trace instead.
   * - ``MRMAP_OTEL_TRUSTED_HOSTS``
     - empty
     - Destinations MrMap may **send** trace context to. Empty means nothing leaving
       towards a third party carries a ``traceparent``.
   * - ``MRMAP_OTEL_TRUSTED_SOURCE_HOSTS``
     - empty
     - Peer addresses MrMap may **accept** a parent from, e.g. the address of the reverse
       proxy. Empty means every caller gets a local root.
   * - ``MRMAP_OTEL_BROKER_TRUSTED``
     - ``1``
     - Whether the Redis broker is the internal boundary ADR-0003 names. Set ``0`` when
       the vhost is shared with a foreign producer.
   * - ``MRMAP_OTEL_TASK_CLASSES``
     - empty
     - Extra task names allowed as the ``mrmap.task.class`` dimension, beside the tasks
       this app registers.
   * - ``MRMAP_OTEL_MAX_TASK_CLASSES`` / ``_MAX_ROUTES`` / ``_MAX_QUEUES``
     - ``200`` / ``500`` / ``16``
     - Cardinality budgets of the three naming dimensions; beyond a budget a new value
       folds into ``other`` / ``unmatched``.
   * - ``MRMAP_OTEL_MAX_ATTRIBUTE_SETS``
     - ``2000``
     - Per-instrument attribute-set budget of the metric views, the SDK's overflow series
       included.
   * - ``MRMAP_OTEL_SPAN_MAX_QUEUE`` / ``_SPAN_MAX_EXPORT_BATCH``
     - ``512`` / ``128``
     - The batch processor's bounds; a full queue drops and is counted.
   * - ``MRMAP_OTEL_SPAN_SCHEDULE_DELAY_SECONDS``
     - ``5.0``
     - How often the batch thread may wake.
   * - ``MRMAP_OTEL_METRIC_INTERVAL_SECONDS`` / ``_METRIC_TIMEOUT_SECONDS``
     - ``30.0`` / ``10.0``
     - The periodic reader's cadence and its collection bound.
   * - ``MRMAP_OTEL_EXPORTER_TIMEOUT_SECONDS``
     - ``1.0``
     - One HTTP attempt of an OTLP export. Never a request or a task waits on this; the
       batch thread does.
   * - ``MRMAP_OTEL_MAX_EXPORT_ATTEMPTS``
     - ``2``
     - Attempts per export, including the first. A lost batch is telemetry lost, counted
       by ``mrmap.telemetry.dropped``, never an error for the application.
   * - ``MRMAP_OTEL_SHUTDOWN_DRAIN_SECONDS``
     - ``3.0``
     - The bound of the one drain a process performs at exit.
   * - ``MRMAP_OTEL_HTTP_CLIENT_ENABLED``
     - mode
     - Outbound client spans; off in ``standard``, on in ``diagnostic``.
   * - ``MRMAP_OTEL_SQL_ENABLED`` / ``MRMAP_OTEL_REDIS_ENABLED``
     - ``0``
     - Opt-in database/cache spans. Off in every mode including ``diagnostic``, and
       asking for one without its pinned package logs one line instead of pretending.
       Statement text and binds are never exported, whatever this is set to.
   * - ``MRMAP_OTEL_DEBUG_MAX_MINUTES``
     - ``15``
     - How long the ``diagnostic`` extras stay on in one process.
   * - ``MRMAP_OTEL_COLLECT_ANY_PROCESS``
     - ``0``
     - Report task metrics from any process, not only from a Celery worker child. A
       development switch; it exists because an unlabelled number is worse than none.

The SDK's own variables (``OTEL_*``) keep working: the lifecycle sets
``OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE=CUMULATIVE`` and
``OTEL_SEMCONV_STABILITY_OPT_IN=http`` as defaults, and forces
``OTEL_PYTHON_DJANGO_INSTRUMENT=False`` — see "one instrumentation path" below.

Which process instruments what
==============================

.. list-table::
   :header-rows: 1
   :widths: 22 30 48

   * - Process
     - Instrumentation
     - Where the lifecycle is called
   * - Gunicorn HTTP worker
     - upstream Django, requests guard
     - ``MrMap/wsgi.py`` and the ``post_fork`` hook of ``backend/gunicorn.conf.py``, which
       Gunicorn loads from the image's working directory without either start-up script
       naming it.
   * - uvicorn websocket worker
     - upstream ASGI middleware, requests guard
     - ``MrMap/asgi.py``, once per worker; the ASGI server is never preloaded (#1617).
   * - Celery worker child
     - upstream Celery, requests guard, the ``mrmap.*`` receivers
     - ``worker_process_init`` in ``MrMap/celery.py`` — never the prefork parent.
   * - Celery beat
     - upstream Celery (producer side)
     - ``beat_init`` in ``MrMap/celery.py``, so a scheduled run has a root span.
   * - management command
     - nothing
     - a command is not a long-lived server; initializing one would mean a batch thread
       per invocation.

One instrumentation path
========================

The upstream auto-instrumentation of the same libraries is switched off
(``OTEL_PYTHON_DJANGO_INSTRUMENT=False``) because the two paths on one service is the
duplicate the ADR rules out: one request would produce two server spans and two duration
histograms, and the second would be outside the allowlist. Run ``gunicorn MrMap.wsgi:application``,
not ``opentelemetry-instrument gunicorn``.

The Django instrumentor inserts its middleware at position 0 of ``MIDDLEWARE`` itself,
which is the correct place for a server span and the reason MrMap's own middleware list
does not name it.

Privacy, and where the bound is applied
=======================================

An allowlist applied at export time over data the SDK already aggregated is not the
contract, because the forbidden dimension already cost memory and already became a series.
The two enforcement points are the ones the SDK offers:

*   **metrics** — a :class:`~opentelemetry.sdk.metrics.view.View` per instrument projects
    the attribute set down to the allowlist *before* aggregation and caps the number of
    series. The Celery instrumentor's ``flower.task.runtime.seconds`` histogram, whose
    dimensions are a raw task name and a worker name, is dropped by a view rather than
    renamed; :mod:`MrMap.telemetry.metrics` answers the same question with the reviewed
    dimensions.
*   **spans** — a processor strips the attributes a span is *created* with, and the
    exporter wrapping the OTLP exporter replaces the attribute mapping with the
    allowlisted one, truncates values and caps events, links and attributes. Attributes
    not on the allowlist of their kind are dropped rather than passed through, so a new
    upstream attribute is a missing attribute after an upgrade and not a leak.

Never exported, in every mode: a URL, a path, a query string, a hostname or an IP address
of a peer or a client, a user agent, any identifier of a task attempt, a message payload
or its size, a retry or revocation reason, an exception message or stack trace, a SQL
statement or its binds, and ``baggage``. The resource carries the service identity and
nothing a detector read about the host.

Sampling is parent-based: a trusted sampled parent decides for its trace, an untrusted
caller cannot choose its own parent, and a root this process created is sampled by
``MRMAP_OTEL_TRACES_SAMPLE_RATIO``. A metric never depends on that decision — the
``mrmap.*`` instruments live on the meter provider, so an attempt whose span was dropped
is still counted and still in its histogram.

Reading the store
=================

The instrument names are the ADR's, and the answers come with the caveats it attaches:

``http.server.request.duration``
    ``count``/``sum``, p50/p95/p99, and the slow-request answer of #888 as ``count`` minus
    the cumulative ``le="0.4"`` bucket — which excludes a request of exactly 0.4 s, the
    same reading the legacy threshold had. Quantiles from explicit buckets are
    approximations.
``mrmap.task.attempt.duration``
    Worker occupancy of one terminal attempt, retries as distinct attempts. Not job
    elapsed time and not CPU time.
``mrmap.task.queue.wait``
    Published-to-start, only where the trusted publish stamp of #1330 exists. An absent or
    unreadable stamp produces no value — a zero wait would be a measurement, and there was
    none.
``mrmap.task.attempts`` / ``mrmap.task.observations``
    The unsampled count per outcome, and the coverage denominator (``stamped``,
    ``unstamped``, ``invalid_stamp``, ``dropped``) which keeps an empty histogram from
    reading as "no slow tasks".
``mrmap.telemetry.dropped``
    Telemetry this process could not keep, by signal and reason. This is the number to
    read before trusting any other: a collector which is down makes a store look healthy
    and empty otherwise.

Query names depend on the VictoriaMetrics naming configuration of #1778
(``-opentelemetry.usePrometheusNaming``); the names above are the OTel instrument names.

Troubleshooting
===============

``the boot log has no opentelemetry line``
    The mode is off, which is the default. ``MRMAP_OTEL_MODE`` must be spelled exactly.
``"opentelemetry: initialization failed"``
    One line at boot and the process runs without telemetry — observability is not a
    runtime dependency (#1775). The reason follows the colon; it is almost always an
    endpoint URL which the OTLP exporter rejects.
``spans arrive with no route``
    ``http.route`` is a registered URL template or the honest absence: ``unresolved`` when
    the resolver did not match, ``unmatched`` for anything that looks like a request path.
    A path is never a substitute, and a route the URLconf does not name is a cardinality
    incident waiting to happen.
``a task dimension says "other"``
    The name is neither a task this app registers nor on ``MRMAP_OTEL_TASK_CLASSES``, or
    the budget of that dimension is exhausted. A truncated name would still be a name, so
    folding into ``other`` is the answer by design.
``metrics stop during a collector outage``
    Expected, and bounded: the batch queue fills, its contents are dropped and counted by
    ``mrmap.telemetry.dropped``, and requests and tasks never wait for the exporter.

Tests
=====

``backend/tests/django/system/test_observability_telemetry.py`` runs against the pinned SDK
of ``.requirements/base.txt`` — not against a mock of it — and asserts the negations the
acceptance list is made of: no provider, thread or patched library while off; one
initialization and one export loop per process; a forked child which replaces what it
inherited instead of asking a nonexistent thread to flush; parent-based sampling; a caller
which cannot choose its parent or smuggle a header into an outbound hop; the allowlists
with SQL binds, URLs and identifiers denied in every mode; dimensions projected before
aggregation; recordings independent of the sampler; and a dead collector which costs
telemetry only. It needs no telemetry service and no database.
