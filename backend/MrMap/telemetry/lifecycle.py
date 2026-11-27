"""Initialize the SDK exactly once per process, and after the fork (#1779).

The lifecycle is the acceptance criterion of this issue, because every other
promise of OpenTelemetry is worthless if the initialization is wrong: a provider
created before ``fork()`` leaves every Gunicorn and Celery child holding a copy of
an exporter thread that does not run in it, and a provider created per request
leaves one batch thread per request. So the rules here are few and enforced:

*   **one ownership path.** Providers, processors, readers and exporters are
    created together here and shut down together by :func:`shutdown`. Nothing else
    in the project constructs them, and nothing recreates them per request.
*   **after the fork.** :func:`initialize_for_process` records the pid it ran in.
    Called again from a different pid - a Gunicorn worker, a Celery prefork child,
    a uvicorn worker - it drops what the parent created and builds fresh objects
    with fresh threads instead of inheriting them: the threads of the parent's
    batch processors do not exist in this process anymore, so they are neither
    reused nor asked to flush. A deployment running with ``GUNICORN_PRELOAD`` on
    is therefore as correct as one running without it.
*   **``off`` means nothing happens.** The function returns at once when the mode
    is off: no instrumentor import or patch, no provider, no thread, no DNS
    lookup, no telemetry service required. Console logging and the domain
    lifecycle are untouched.
*   **never fatal.** A broken configuration costs the deployment its telemetry and
    logs one line; it must never stop a worker from serving or a task from
    running. Initialization and :func:`shutdown` are the only places allowed to
    block, and the shutdown drain is bounded - no request or task path ever
    touches an exporter.

The domain metrics live on the meter provider rather than on spans, which is what
makes them independent of the trace sampler: an attempt whose span was never
sampled is still counted and still in its histogram.
"""

import os
import threading
import uuid
from logging import getLogger

from MrMap.telemetry import config

logger = getLogger("MrMap.telemetry")

#: what this process decided at its last initialization, and the pid it decided
#: it in. The pid is the whole of the fork detection: a child which does not find
#: its own pid here initializes its own SDK.
_state = {
    "pid": None,
    "values": None,
    "provider": None,
    "meter_provider": None,
    "reader": None,
    "roles": set(),
    "failed": None,
}
_lock = threading.Lock()

#: the roles a process may declare at initialization; they decide which
#: instrumentors make sense there and appear in the boot log
ROLE_HTTP = "http"
ROLE_WS = "websocket"
ROLE_WORKER = "worker"
ROLE_BEAT = "beat"
ROLE_OTHER = "other"


def is_enabled() -> bool:
    """Whether this process should run telemetry at all (never raises)."""
    try:
        return bool(config.resolve().get("enabled"))
    except Exception:
        # a knob this broken is not worth an outage: off is the answer, and it is
        # the same answer a deployment without the dependency gets
        logger.warning("opentelemetry: cannot read the configuration; staying "
                       "off (#1779).", exc_info=True)
        return False


def initialized():
    """The values of the current initialization, or ``None`` before it ran."""
    return _state["values"]


def current_pid():
    """The pid the current providers belong to."""
    return _state["pid"]


def roles():
    """Which roles asked for telemetry in this process (for the tests)."""
    return set(_state["roles"])


def failure():
    """Why initialization gave up in this process, or ``None``."""
    return _state["failed"]


def describe() -> str:
    """The one line this process logged (or would log) at initialization."""
    return config.describe(_state["values"] or config.resolve())


def initialize_for_process(role=ROLE_OTHER):
    """Build the SDK of this process, once.

    Idempotent per process: a second call from the same pid returns what is
    already there, and a call from a child of a forked parent replaces what it
    inherited. Returns ``None`` when the mode is off - the caller's cue to connect
    and patch nothing at all.
    """
    values = config.resolve()
    if not values.get("enabled"):
        return None
    pid = os.getpid()
    with _lock:
        if _state["failed"] is not None and _state["pid"] == pid:
            # this process already tried and the SDK refused; saying it once at
            # boot beats saying it on every request
            return None
        if _state["pid"] == pid and _state["values"] is not None:
            _state["roles"].add(role)
            return _state["values"]
        if _state["pid"] is not None and _state["pid"] != pid:
            _abandon_inherited()
        try:
            _build(values, role, pid)
        except Exception as error:  # pragma: no cover - depends on the SDK
            # telemetry is optional; the application is not. One line, and the
            # process continues without it.
            _reset_state()
            _state["pid"] = pid
            _state["failed"] = str(error)
            logger.warning("opentelemetry: initialization failed (%s); this "
                           "process runs without telemetry (#1779).", error,
                           exc_info=True)
            return None
        return values


def _build(values, role, pid):
    """Create the resource, providers, processors, readers and instrumentors."""
    # set before the SDK reads the environment: cumulative metrics, so a restart
    # continues a series instead of resetting it, and the stable HTTP semantic
    # conventions, so one process cannot run the old and the new pipeline side by
    # side (which would be the duplicate metric stream of the ADR)
    os.environ.setdefault("OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE",
                          "CUMULATIVE")
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")
    # and never through the auto-instrumentation of a parent process: this module
    # owns the lifecycle, and both paths on one service is the double
    # instrumentation ADR-0003 rules out
    os.environ["OTEL_PYTHON_DJANGO_INSTRUMENT"] = "False"

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.trace import SpanLimits, TracerProvider
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

    from MrMap.telemetry import celery_metrics, exporters, metrics, policy

    resource = _resource(values)
    provider = TracerProvider(
        sampler=ParentBasedTraceIdRatio(float(values["trace_ratio"])),
        resource=resource,
        span_limits=SpanLimits(
            max_attributes=policy.MAX_SPAN_ATTRIBUTES,
            max_span_attributes=policy.MAX_SPAN_ATTRIBUTES,
            max_event_attributes=policy.MAX_SPAN_ATTRIBUTES,
            max_link_attributes=policy.MAX_SPAN_ATTRIBUTES,
            max_events=policy.MAX_SPAN_EVENTS,
            max_links=policy.MAX_SPAN_LINKS,
            max_attribute_length=policy.MAX_VALUE_LENGTH,
        ),
    )
    dropped = _dropped_counter()

    if values["traces_endpoint"]:
        # no endpoint, no span pipeline: no batch thread, no queue of 512 spans
        # nobody reads, no DNS lookup for a collector that is not there. The
        # provider stays, because the span context is what links a publish to
        # its execution inside this process.
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        provider.add_span_processor(policy.StripOnStartSpanProcessor(values))
        provider.add_span_processor(BatchSpanProcessor(
            policy.SanitizingSpanExporter(
                exporters.BoundedOTLPSpanExporter(
                    values,
                    endpoint=values["traces_endpoint"],
                    dropped=dropped),
                values, dropped=dropped),
            max_queue_size=int(values["span_max_queue"]),
            max_export_batch_size=int(values["span_max_export_batch"]),
            schedule_delay_millis=float(
                values["span_schedule_delay_seconds"]) * 1000.0,
            export_timeout_millis=float(
                values["export_timeout_seconds"]) * 1000.0,
        ))

    reader = _metric_reader(values, exporters, dropped)
    meter_provider = MeterProvider(
        resource=resource, views=policy.views(values), metric_readers=[reader])
    # the instruments of the domain contract are created from this meter and not
    # from a span: that is what makes a task's duration and count independent of
    # whether its trace was ever sampled
    metrics.attach(meter_provider.get_meter(
        "mrmap", schema_url="https://opentelemetry.io/schemas/1.34.0"))

    _adopt_globals(provider, meter_provider, values)

    _state["pid"] = pid
    _state["values"] = values
    _state["provider"] = provider
    _state["meter_provider"] = meter_provider
    _state["reader"] = reader
    _state["roles"] = {role}
    _state["failed"] = None

    from MrMap.telemetry import instrumentation
    instrumentation.instrument(values, provider, meter_provider, role)
    if role == ROLE_WORKER:
        # the receivers of the domain task metrics belong to a process which
        # executes tasks; a process which merely publishes observes no execution
        celery_metrics.connect()
    logger.info("%s (pid %s, role %s)", config.describe(values), pid, role)


def _adopt_globals(provider, meter_provider, values):
    """Point the SDK's process-wide accessors at what this process created.

    ``set_tracer_provider`` and ``set_meter_provider`` of the API are write-once:
    the second call only logs "Overriding of current TracerProvider is not
    allowed". In a preloaded Gunicorn or a prefork Celery deployment the lifecycle
    legitimately runs twice - once in the master, once in the child - and a child
    which left the global accessors on the master's provider would hand every span
    of every request to a batch processor whose thread does not exist in it. So
    the "once" gate of the pinned release is reset here and only here, which keeps
    it a single line of reasoning about one ownership path instead of a
    distribution-wide override.

    Everything upstream reads - the global provider, the meter provider and the
    text map - is set together, because the propagator is what enforces the trust
    rules and a provider without it would be an unfiltered pipeline.
    """
    from opentelemetry import propagate, trace
    from opentelemetry import metrics as metrics_api

    _release_once(trace, "_TRACER_PROVIDER_SET_ONCE", "_TRACER_PROVIDER")
    from opentelemetry.metrics import _internal as metrics_internal
    _release_once(metrics_internal, "_METER_PROVIDER_SET_ONCE", "_METER_PROVIDER")
    trace.set_tracer_provider(provider)
    metrics_api.set_meter_provider(meter_provider)
    propagate.set_global_textmap(_propagator(values))


def _release_once(module, once_name, provider_name):
    """Re-arm one of the SDK's write-once global setters.

    Belt and braces by design: if a future release renames the module attributes,
    the process keeps the provider it was given by the caller and loses only the
    global accessor - it never loses the telemetry of its own requests, which is
    what ``_state`` holds.
    """
    once = getattr(module, once_name, None)
    if not hasattr(once, "_done") or not hasattr(module, provider_name):
        # a renamed internal of a new release: keep the provider of the caller and
        # lose only the global accessor, which is the lesser failure
        return
    once._done = False
    setattr(module, provider_name, None)


def _resource(values):
    """The resource of this process, written by hand.

    ``Resource.create`` runs the SDK's detectors, which read the host, the
    container and the cloud metadata of the machine - dimensions ADR-0003 does not
    allow, and each of them costs a lookup at boot. So the attributes are the ones
    the contract lists, plus an instance id which only separates two cumulative
    writers.
    """
    from opentelemetry.sdk.resources import Resource

    attributes = {
        "service.name": values["service_name"],
        "telemetry.sdk.name": "opentelemetry",
        # a cumulative stream needs one identity per writer, or two processes of
        # the same service overwrite each other's series. Internal plumbing, not
        # a user-facing dimension - and deliberately not a container name.
        "service.instance.id": "%s-%s" % (os.getpid(), uuid.uuid4().hex[:8]),
    }
    if values["service_version"]:
        attributes["service.version"] = values["service_version"][:128]
    if values["deployment_environment"]:
        attributes["deployment.environment.name"] = (
            values["deployment_environment"][:128])
    return Resource(attributes=attributes)


def _metric_reader(values, exporters, dropped):
    """The periodic reader of one process, with its bounded export time.

    A deployment which named no metric endpoint still gets a reader, because the
    reader is what bounds collection time; its exporter is the null one, which
    produces no bytes and requires no service.
    """
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    endpoint = values["metrics_endpoint"]
    if not endpoint:
        # no endpoint, no timer and no thread: ``math.inf`` is the SDK's own
        # spelling for "never collect periodically", and it is what keeps a
        # deployment which named no collector from paying a wake-up per process
        # for data it has nowhere to send. The reader and the aggregation stay,
        # because the cardinality bound is applied while recording.
        return exporters.QuietMetricReader()
    return PeriodicExportingMetricReader(
        exporters.BoundedOTLPMetricExporter(
            values, endpoint=endpoint, dropped=dropped),
        export_interval_millis=float(
            values["metric_interval_seconds"]) * 1000.0,
        export_timeout_millis=float(values["metric_timeout_seconds"]) * 1000.0)


def _propagator(values):
    """The one text map of this process - never the stock one."""
    from MrMap.telemetry.propagation import MrMapPropagator

    return MrMapPropagator(values)


def _dropped_counter():
    """The function the exporters and the sanitizer call when telemetry is lost.

    It is a closure over the metric instrument rather than a direct import inside
    those classes, so the privacy layer keeps no dependency on the metric
    lifecycle and cannot fail because of it.
    """
    from MrMap.telemetry import metrics

    def count(signal, reason, amount=1):
        try:
            for _ in range(max(1, int(amount))):
                metrics.count_dropped(signal, reason)
        except Exception:
            # the counter of lost telemetry must itself never be the failure
            return

    return count


def _reset_state():
    _state["provider"] = None
    _state["meter_provider"] = None
    _state["reader"] = None
    _state["values"] = None
    _state["roles"] = set()


def _abandon_inherited():
    """Forget what the parent process created; this child owns nothing now.

    No ``shutdown()`` on the inherited objects on purpose: their batch threads do
    not exist in this process after a fork, and asking a thread which is not
    running to flush is how a worker hangs at boot.
    """
    from MrMap.telemetry import metrics

    _reset_state()
    _state["pid"] = None
    _state["failed"] = None
    metrics.detach()


def _drain(target, drain_millis):
    """Shut one provider down within the bounded drain, whatever it answers.

    Every failure is swallowed on purpose: a collector which is down, a provider
    of a release which takes no timeout and a provider already shut down are all
    the same outcome - buffered telemetry is lost, which the drop counters of the
    collector exist to make visible. Nothing here may raise, because the caller is
    process teardown and a hanging or failing worker exit is not an acceptable
    price for an observability feature.
    """
    if target is None:
        return
    try:
        target.shutdown(timeout_millis=drain_millis)
    except TypeError:  # pragma: no cover - the tracer provider takes none
        try:
            target.shutdown()
        except Exception:
            pass
    except Exception:
        # a dead collector at teardown is normal; it costs telemetry only
        pass


def _run_quietly(action):
    """One teardown step whose failure may not stop the steps behind it."""
    try:
        action()
    except Exception:
        pass


def shutdown(reason="shutdown"):
    """One bounded drain, then let go. Called from process teardown only.

    Never from a request or a task path - a flush there is the blocking exporter
    I/O the performance budget forbids. An unfinished drain loses buffered
    telemetry, which is what the drop counters exist for; it never changes a
    response, a retry or a job state. Returns whether anything was shut down.
    """
    with _lock:
        provider = _state["provider"]
        meter_provider = _state["meter_provider"]
        values = _state["values"]
        _reset_state()
        _state["pid"] = None
        _state["failed"] = None
    if provider is None and meter_provider is None:
        return False
    drain_millis = int(float((values or {}).get(
        "shutdown_drain_seconds", 3.0)) * 1000)
    from MrMap.telemetry import celery_metrics, instrumentation
    # close the open observations *before* the receivers go away, so a graceful
    # restart of a worker is not a hole in the task histogram
    _run_quietly(celery_metrics.flush_on_process_shutdown)
    _run_quietly(celery_metrics.disconnect)
    _run_quietly(instrumentation.uninstrument)
    _drain(provider, drain_millis)
    _drain(meter_provider, drain_millis)
    logger.debug("opentelemetry: process telemetry shut down (%s).", reason)
    return True
