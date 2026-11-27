"""Which upstream instrumentors a MrMap process installs (#1779).

Standard-first is the rule of the epic, so the HTTP and Celery pipelines *are*
the upstream instrumentations of the pinned release: this module decides which of
them a process installs, hands them the providers this process owns, and adds the
two things upstream cannot provide for MrMap - the destination trust decision on
every outbound send, and the removal of the attributes upstream sets by default.

| role | installed | why |
| --- | --- | --- |
| ``http`` | Django, requests guard | the WSGI tier answers every MrMap view (#1032) |
| ``websocket`` | requests guard only | the ASGI process answers ``/ws``; a channels consumer is not an HTTP request and has no upstream instrumentation to reuse |
| ``worker`` | Celery, requests guard | the task spans and the ``mrmap.*`` task metrics |
| ``beat`` | Celery (producer side), requests guard | beat publishes, so its spans are the root of a scheduled run |
| anything else | nothing | a management command is not a long-lived server |

The requests *guard* is not the requests *instrumentor*: the guard is the seam
which enforces "nothing leaving towards a third party carries a trace header",
and it is installed even when the client spans of the diagnostic mode are off,
because the trust rule applies in every mode. The instrumentor itself is installed
only in the diagnostic mode, and only for the destinations the operator trusted.

SQL and Redis instrumentation is off by default in every mode, as ADR-0003
requires. Its knobs exist so that an operator can ask for it, and asking without
the pinned optional package installed says so once instead of silently doing
nothing.
"""

from logging import getLogger
from urllib.parse import urlsplit

from MrMap.telemetry import propagation

logger = getLogger("MrMap.telemetry")

#: what is installed in this process, for the boot log and for the tests
_installed = set()

#: the ``Session.send`` wrapper of the requests guard, so uninstrument() can put
#: the original back
_wrapped_send = None


def installed():
    """The names of the instrumentations this process patched."""
    return set(_installed)


def instrument(values, tracer_provider, meter_provider, role):
    """Install what this role needs, once per process."""
    from MrMap.telemetry import lifecycle

    if role in (lifecycle.ROLE_HTTP,):
        _instrument_django(tracer_provider, meter_provider)
    if role in (lifecycle.ROLE_WORKER, lifecycle.ROLE_BEAT):
        _instrument_celery(tracer_provider, meter_provider)
    # the guard first: it must be the outermost wrapper of Session.send, so it
    # decides trust and strips caller headers before any inject() runs
    _install_requests_guard()
    if values.get("http_client_enabled"):
        _instrument_requests(tracer_provider, meter_provider)
    _instrument_optional(values, tracer_provider, meter_provider)
    return _installed


def uninstrument():
    """Undo what :func:`instrument` patched (the shutdown path)."""
    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    for name, instrumentor in (("django", DjangoInstrumentor()),
                               ("celery", CeleryInstrumentor()),
                               ("requests", RequestsInstrumentor())):
        if name in _installed and instrumentor.is_instrumented_by_opentelemetry:
            try:
                instrumentor.uninstrument()
            except Exception:  # pragma: no cover - defensive
                logger.debug("opentelemetry: could not uninstrument %s.", name,
                             exc_info=True)
    _uninstall_requests_guard()
    _installed.clear()


# ------------------------------------------------------------------ server ---

def _instrument_django(tracer_provider, meter_provider):
    """Patch Django's request handler.

    ``excluded_urls`` keeps the telemetry's own endpoints and the health probes
    out of the pipeline: a probe which produces a span produces the export which
    the probe is measuring, which is the recursion the contract forbids. The
    middleware of the instrumentor is inserted by upstream at position 0 of
    ``settings.MIDDLEWARE``, ahead of everything MrMap lists - the correct place
    for a server span, and the reason MrMap's own middleware list does not name
    it.
    """
    from opentelemetry.instrumentation.django import DjangoInstrumentor

    if "django" in _installed:
        return
    DjangoInstrumentor().instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        excluded_urls=EXCLUDED_URLS,
    )
    _installed.add("django")


#: the URLs which never produce a server span: the liveness/readiness probes of
#: the stack and the telemetry endpoints themselves
EXCLUDED_URLS = (
    r"^/api/system/status/current",
    r"^/api/system/info",
    r"^/healthz",
    r"^/v1/traces",
    r"^/v1/metrics",
)


def _instrument_celery(tracer_provider, meter_provider):
    """Patch Celery's task execution and publishing.

    Upstream's own guidance is that the instrumentor must run in the process which
    executes the task, which is why the lifecycle calls it from
    ``worker_process_init`` and not from the worker's parent. Its
    ``flower.task.runtime.seconds`` histogram is dropped by a view of
    :mod:`MrMap.telemetry.policy`, and the ``celery.task_name`` /
    ``messaging.message.id`` attributes it sets never survive the sanitizer.
    """
    from opentelemetry.instrumentation.celery import CeleryInstrumentor

    if "celery" in _installed:
        return
    CeleryInstrumentor().instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    _installed.add("celery")


# ----------------------------------------------------------------- outbound ---

def _install_requests_guard():
    """Wrap ``Session.send`` so no hop decides trust by itself.

    A redirect re-enters ``Session.send`` with the new URL, so deciding per send
    is what makes the rule hold across a 302 to a host nobody trusted. The caller
    headers are stripped before anything can inject, which covers the case of a
    ``PreparedRequest`` somebody built with a ``traceparent`` of its own.

    The wrapper is installed only while telemetry is enabled; an uninstrumented
    deployment pays nothing, because nothing leaving its processes carries a
    trace header to begin with.
    """
    global _wrapped_send
    if _wrapped_send is not None:
        return
    from requests import Session

    original = Session.send
    _wrapped_send = original

    def guarded_send(self, request, **kwargs):
        try:
            decision = _destination_is_trusted(getattr(request, "url", None))
            # strip first, then decide: a caller-supplied parent must not
            # survive a hop we chose to leave untraced either
            propagation.strip_context_headers(getattr(request, "headers", None))
        except Exception:
            decision = False
        token = propagation.mark_untrusted_destination(not decision)
        try:
            return original(self, request, **kwargs)
        finally:
            propagation.reset_untrusted_destination(token)

    Session.send = guarded_send
    _installed.add("requests-guard")


def _uninstall_requests_guard():
    global _wrapped_send
    if _wrapped_send is None:
        return
    from requests import Session

    Session.send = _wrapped_send
    _wrapped_send = None


def _destination_is_trusted(url) -> bool:
    """Whether the operator named this destination for trace propagation.

    The host of the URL that is *actually being sent* is the only thing asked -
    never a host allowlist applied to an initial URL, which a redirect would
    defeat.
    """
    from django.conf import settings

    trusted = getattr(settings, "OTEL_TRUSTED_HOSTS", ()) or ()
    if not trusted:
        return False
    try:
        host = urlsplit(str(url)).hostname
    except (ValueError, AttributeError):
        return False
    return propagation._is_trusted(host, trusted)


def _instrument_requests(tracer_provider, meter_provider):
    """Install the upstream client instrumentation (diagnostic mode only).

    Upstream creates the client span and calls ``inject()``; the propagator of
    this process answers that call with nothing for a destination the guard did
    not trust, so the span stays local. ``url.full``, the peer address and the
    user agent upstream also sets are removed by the sanitizer.
    """
    from opentelemetry.instrumentation.requests import RequestsInstrumentor

    if "requests" in _installed:
        return
    RequestsInstrumentor().instrument(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )
    _installed.add("requests")


# ------------------------------------------------------------------ extras ---

#: the deferred diagnostic instrumentations of ADR-0003: knob -> (package,
#: instrumentor import path). Not installed by this project's requirements, so
#: asking for one is an operator decision with a dependency attached to it.
OPTIONAL = {
    "sql_enabled": ("opentelemetry-instrumentation-psycopg",
                    "opentelemetry.instrumentation.psycopg",
                    "PsycopgInstrumentor"),
    "redis_enabled": ("opentelemetry-instrumentation-redis",
                      "opentelemetry.instrumentation.redis",
                      "RedisInstrumentor"),
}


def _instrument_optional(values, tracer_provider, meter_provider):
    """Install the opt-in SQL/Redis instrumentation, if it was asked for.

    Off by default in every mode, and never silently: an operator who turned a
    knob on and did not install the pinned package hears about it once. The
    statement text of a database span is removed by the sanitizer in every mode,
    so even the diagnostic extras answer "which statement class", never "with
    which parameters".
    """
    import importlib

    for knob, (package, module_name, class_name) in OPTIONAL.items():
        if not values.get(knob):
            continue
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            logger.warning(
                "opentelemetry: %s is on but %s is not installed; this "
                "process runs without it (#1779).", knob, package)
            continue
        try:
            getattr(module, class_name)().instrument(
                tracer_provider=tracer_provider,
                meter_provider=meter_provider,
            )
            _installed.add(knob)
        except Exception:
            logger.warning("opentelemetry: %s could not be installed (%s).",
                           knob, class_name, exc_info=True)
