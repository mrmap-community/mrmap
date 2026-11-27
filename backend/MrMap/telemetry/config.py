"""The knobs of the optional OpenTelemetry integration (#1779, epic #1775).

Every value is read from the deployment environment while the settings load, so a
process can answer "which mode am I in" without importing the SDK, without a
socket and without Django's app registry. That matters for the acceptance rule of
ADR-0003: ``off`` must not *cost* anything, and a knob which is only decided after
the SDK exists cannot enforce it.

The modes are the three of the epic:

``off``
    The shipped default. Nothing of this package runs: no instrumentor patches a
    library, no provider exists, no exporter thread starts, no DNS lookup for a
    collector address happens. The application, its console logging and its
    domain lifecycle work exactly as before.
``standard``
    Upstream Django/WSGI/ASGI, Celery and requests instrumentation with the
    allowlist of :mod:`MrMap.telemetry.policy`, parent-based head sampling, and
    unsampled metric aggregation. **No SQL statement, no SQL bind, no URL query
    and no request or task payload** ever enters a span or a metric.
``diagnostic``
    Standard plus the opt-in extras: outbound client spans for the OGC fetches
    and (only when explicitly asked for) psycopg statement spans. Always
    time-bounded by :data:`MrMap.settings.OTEL_DEBUG_MAX_MINUTES`, always without
    SQL binds, and always allowlisted like standard.

``MRMAP_OTEL_MODE`` is the switch; an unknown spelling answers ``off`` and says so
once at initialization rather than silently instrumenting.
"""

import os

MODE_OFF = "off"
MODE_STANDARD = "standard"
MODE_DIAGNOSTIC = "diagnostic"
MODES = (MODE_OFF, MODE_STANDARD, MODE_DIAGNOSTIC)

#: the spellings which mean "turn it on", same vocabulary as the other
#: deployment switches of this project (MRMAP_CAPACITY_TELEMETRY et al.)
_ON = ("on", "1", "true", "yes")


def _mode_from_env(environ) -> str:
    """The requested mode, with the fail-safe default of ``off``."""
    raw = (environ.get("MRMAP_OTEL_MODE") or "").strip().lower()
    return raw if raw in MODES else MODE_OFF


def _float_from_env(environ, name, default, minimum=0.0, maximum=1.0):
    """A float knob clamped into its documented range, default on garbage.

    A sample ratio of ``"1e9"`` or a negative timeout is not a crash and not a
    silent 100 % sampling either: the value is clamped and the operator reads
    the reading in the log line of :func:`MrMap.telemetry.lifecycle.describe`.
    """
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _int_from_env(environ, name, default, minimum=1):
    raw = (environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else minimum


def _host_list_from_env(environ, name) -> tuple:
    """A ","/";" separated list of bare hostnames, lowercased and deduplicated."""
    entries = []
    for entry in (environ.get(name) or "").replace(",", ";").split(";"):
        host = entry.strip().lower().rstrip(".")
        if host and host not in entries:
            entries.append(host)
    return tuple(entries)


def _flag_from_env(environ, name, default: bool) -> bool:
    raw = (environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in _ON


def resolve(environ=None) -> dict:
    """Every knob of one process, as plain values.

    A function and not module-level constants, so a test can decide a mode for
    one process without reloading the settings, and so
    :func:`MrMap.telemetry.lifecycle.initialize_for_process` can log exactly what
    a process decided at boot.
    """
    environ = os.environ if environ is None else environ
    mode = _mode_from_env(environ)
    diagnostic = mode == MODE_DIAGNOSTIC
    # the outbound HTTP client spans answer the mode unless the operator
    # overrides the answer; standard keeps them off, because a client span
    # against a third party endpoint is the one span this deployment cannot
    # fully control the attributes of
    client_enabled = _flag_from_env(
        environ, "MRMAP_OTEL_HTTP_CLIENT_ENABLED", diagnostic)
    return {
        "mode": mode,
        "enabled": mode != MODE_OFF,
        "diagnostic": diagnostic,
        # service identity of the resource; never a container name, never a
        # host name, never anything the caller can influence
        "service_name": (environ.get("MRMAP_OTEL_SERVICE_NAME")
                         or "mrmap").strip() or "mrmap",
        "service_version": (environ.get("MRMAP_OTEL_SERVICE_VERSION")
                            or "").strip(),
        "deployment_environment": (
            environ.get("MRMAP_OTEL_DEPLOYMENT_ENVIRONMENT") or "").strip(),
        # signal-specific complete URLs (different paths, different ports);
        # empty means: no exporter for that signal, aggregation only
        "traces_endpoint": (environ.get("MRMAP_OTEL_TRACES_ENDPOINT")
                            or "").strip(),
        "metrics_endpoint": (environ.get("MRMAP_OTEL_METRICS_ENDPOINT")
                             or "").strip(),
        # parent-based head sampling: a trusted sampled parent is honoured, a
        # public root is sampled by this ratio (ADR-0003's 1 % starting point)
        "trace_ratio": _float_from_env(
            environ, "MRMAP_OTEL_TRACES_SAMPLE_RATIO", 0.01, 0.0, 1.0),
        "export_timeout_seconds": _float_from_env(
            environ, "MRMAP_OTEL_EXPORTER_TIMEOUT_SECONDS", 1.0, 0.05, 60.0),
        "export_attempts": _int_from_env(
            environ, "MRMAP_OTEL_MAX_EXPORT_ATTEMPTS", 2, 1),
        # bounded batch pipeline: no SimpleSpanProcessor, no force_flush on a
        # request or task path, ever
        "span_max_queue": _int_from_env(
            environ, "MRMAP_OTEL_SPAN_MAX_QUEUE", 512, 16),
        "span_max_export_batch": _int_from_env(
            environ, "MRMAP_OTEL_SPAN_MAX_EXPORT_BATCH", 128, 1),
        "span_schedule_delay_seconds": _float_from_env(
            environ, "MRMAP_OTEL_SPAN_SCHEDULE_DELAY_SECONDS", 5.0,
            0.1, 300.0, ),
        "metric_interval_seconds": _float_from_env(
            environ, "MRMAP_OTEL_METRIC_INTERVAL_SECONDS", 30.0, 1.0, 3600.0),
        "metric_timeout_seconds": _float_from_env(
            environ, "MRMAP_OTEL_METRIC_TIMEOUT_SECONDS", 10.0, 0.1, 300.0),
        "shutdown_drain_seconds": _float_from_env(
            environ, "MRMAP_OTEL_SHUTDOWN_DRAIN_SECONDS", 3.0, 0.05, 60.0),
        # trust boundaries (MrMap.telemetry.propagation)
        "trusted_hosts": _host_list_from_env(environ, "MRMAP_OTEL_TRUSTED_HOSTS"),
        "trusted_source_hosts": _host_list_from_env(
            environ, "MRMAP_OTEL_TRUSTED_SOURCE_HOSTS"),
        # the internal broker is a trusted propagation boundary by default: a
        # MrMap producer stamps the context and a MrMap worker reads it back.
        # A deployment which shares its broker with a foreign producer sets
        # this off, and every task then starts its own root.
        "broker_trusted": _flag_from_env(
            environ, "MRMAP_OTEL_BROKER_TRUSTED", True),
        # instrumentation switches; SQL and Redis are off by default in every
        # mode and have to be asked for by name (ADR-0003)
        "http_client_enabled": client_enabled,
        "sql_enabled": _flag_from_env(environ, "MRMAP_OTEL_SQL_ENABLED", False),
        "redis_enabled": _flag_from_env(
            environ, "MRMAP_OTEL_REDIS_ENABLED", False),
        # bounded debug: the diagnostic extras stop by themselves after this
        # many minutes, so a forgotten "diagnostic" cannot run a deployment hot
        "debug_max_minutes": _float_from_env(
            environ, "MRMAP_OTEL_DEBUG_MAX_MINUTES", 15.0, 0.0, 24 * 60.0),
        # cardinality budgets (MrMap.telemetry.policy); the view limit leaves
        # room for the SDK's own single overflow series, which is what makes
        # the total of OTEL_MAX_ATTRIBUTE_SETS points per instrument hold
        "max_attribute_sets": _int_from_env(
            environ, "MRMAP_OTEL_MAX_ATTRIBUTE_SETS", 2000, 10),
        "max_task_classes": _int_from_env(
            environ, "MRMAP_OTEL_MAX_TASK_CLASSES", 200, 1),
        "max_routes": _int_from_env(environ, "MRMAP_OTEL_MAX_ROUTES", 500, 1),
        "max_queues": _int_from_env(environ, "MRMAP_OTEL_MAX_QUEUES", 16, 1),
        # the allowlist of registered first-party task names; empty means every
        # name maps to "other", which is the fail-safe reading of the contract
        "task_classes": _host_list_from_env(
            environ, "MRMAP_OTEL_TASK_CLASSES"),
        "worker_processes": _int_from_env(
            environ, "CELERY_WORKER_CONCURRENCY", 4, 1),
    }


def describe(values: dict) -> str:
    """One line naming what one process decided, for its boot log."""
    if not values["enabled"]:
        return "opentelemetry mode off: no instrumentor, no provider, no exporter"
    return (
        "opentelemetry mode %s (service %s, trace ratio %s, traces %s, "
        "metrics %s, http client %s, sql %s, redis %s, trusted hosts %d)" % (
            values["mode"], values["service_name"], values["trace_ratio"],
            values["traces_endpoint"] or "(off)",
            values["metrics_endpoint"] or "(off)",
            "on" if values["http_client_enabled"] else "off",
            "on" if values["sql_enabled"] else "off",
            "on" if values["redis_enabled"] else "off",
            len(values["trusted_hosts"])))
