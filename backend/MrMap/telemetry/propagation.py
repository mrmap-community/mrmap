"""Who may talk to the trace context of a MrMap process (#1779).

Two rules from ADR-0003, both of which the *stock* propagator would break:

1.  **A caller must not be able to choose the parent - and therefore the
    sampling decision - of a MrMap span.** W3C ``traceparent`` is honored only
    from a boundary the operator named as trusted
    (``MRMAP_OTEL_TRUSTED_SOURCE_HOSTS``); every other caller - the public nginx
    ingress, a scraped health check, whoever reaches the port directly - gets a
    local root and the deployment's own head-sampling decision. A proxy sitting in
    front of Django does not make anything trusted: it is trusted only if the
    operator says its address is, which is the same reading as Django's
    ``SECURE_PROXY_SSL_HEADER``.
2.  **Nothing leaving towards a third party carries a trace header.** The
    instrumentations of the pinned release call ``inject()`` on the outgoing
    request headers before the send; MrMap's propagator answers that call with
    nothing unless the destination host is on ``MRMAP_OTEL_TRUSTED_HOSTS``. The
    decision is taken per actual send - a redirect re-enters the instrumented
    ``Session.send``, so a 302 to an untrusted host is decided again - and the
    outbound headers are stripped of any ``traceparent``/``tracestate``/``baggage``
    a caller put into its own ``PreparedRequest`` before the decision is applied.

``baggage`` is never extracted and never injected: it is an arbitrary
caller-controlled dimension channel, and MrMap has no use for one.

The trust decisions of the current call live in context variables rather than in
arguments, because the seams which call ``inject``/``extract`` are upstream's and
their signatures are not ours to extend.
"""

from contextvars import ContextVar

from opentelemetry.propagators.textmap import TextMapPropagator, default_getter
from opentelemetry.trace.propagation.tracecontext import \
    TraceContextTextMapPropagator

TRACEPARENT = "traceparent"
TRACESTATE = "tracestate"
BAGGAGE = "baggage"

#: the header names this module ever touches, lowercased - one list for the
#: stripping and for the tests
CONTEXT_HEADERS = (TRACEPARENT, TRACESTATE, BAGGAGE)

#: set while an outbound request to a destination the operator did not trust is
#: instrumented; the propagator then injects nothing
untrusted_destination: ContextVar = ContextVar(
    "mrmap_otel_untrusted_destination", default=False)

#: set by the ASGI entry point with the peer address of the connection, because
#: the ASGI carrier (``scope["headers"]``) carries no address of its own
peer_address: ContextVar = ContextVar("mrmap_otel_peer_address", default=None)


def _is_trusted(host, trusted_hosts) -> bool:
    """Whether one hostname is on the operator's list (exact, case-insensitive)."""
    if not host or not trusted_hosts:
        return False
    return host.strip().lower().rstrip(".") in trusted_hosts


class MrMapPropagator(TextMapPropagator):
    """W3C context, gated by the two rules above.

    Composed rather than re-implemented: the W3C propagator of the SDK does the
    parsing, this class decides whether it is asked at all. Baggage is left out
    of the composition on purpose.
    """

    def __init__(self, values=None):
        self._w3c = TraceContextTextMapPropagator()
        self._values = values or {}

    # -- read side ----------------------------------------------------------

    @property
    def fields(self):
        # only what may ever be read; the stock list would advertise baggage too
        return (TRACEPARENT, TRACESTATE)

    def extract(self, carrier=None, context=None, getter=None):
        getter = default_getter if getter is None else getter
        if not self._ingress_is_trusted(carrier, getter):
            # no parent and no remote sampling decision: the caller gets what
            # the local sampler decides
            return context
        return self._w3c.extract(carrier=carrier, context=context,
                                 getter=getter)

    def _ingress_is_trusted(self, carrier, getter) -> bool:
        if _is_broker_carrier(carrier):
            # the internal broker is the second trusted boundary ADR-0003
            # names: a MrMap producer stamps the context, a MrMap worker reads
            # it back. A deployment which shares its broker with a foreign
            # producer turns this off and every task starts its own root.
            return bool(self._values.get("broker_trusted", True))
        trusted = self._values.get("trusted_source_hosts") or ()
        if not trusted:
            return False
        return _is_trusted(_carrier_peer(carrier, getter), trusted)

    # -- write side ---------------------------------------------------------

    def inject(self, carrier, context=None, setter=None, value_setter=None):
        # setter/value_setter belong to the TextMapPropagator signature and are
        # unused here: the W3C propagator writes plain string headers, and
        # MrMap writes none at all for an untrusted destination.
        if untrusted_destination.get():
            return None
        return self._w3c.inject(carrier=carrier, context=context)

    def __repr__(self):
        return "MrMapPropagator(trusted_source_hosts=%d)" % len(
            self._values.get("trusted_source_hosts") or ())


def _is_broker_carrier(carrier) -> bool:
    """Whether this carrier is a Celery message the internal broker delivered.

    The Celery instrumentor extracts from the task's request object, whose
    attributes are the message headers (``celery-retries`` and friends). That is
    the shape of a broker hop - no network peer of its own, and written by a
    producer of this deployment rather than by a client.
    """
    if carrier is None or not hasattr(carrier, "__dict__"):
        return False
    for name in ("celery-retries", "correlation_id", "id"):
        if getattr(carrier, name, None) is not None:
            return True
    return False


def _carrier_peer(carrier, getter):
    """The address of whoever filled this carrier, or ``None``.

    Three carrier shapes reach a propagator in this project: the WSGI
    environment (or Django's ``request.META``, same content), the ASGI header
    list of the websocket/ASGI stack, and the Celery message carrier. Only the
    first names a network peer by itself; for the others the entry point had to
    record the peer while the connection was still in hand.
    """
    if carrier is None:
        return None
    if isinstance(carrier, dict):
        remote = carrier.get("REMOTE_ADDR")
        if remote:
            return str(remote).strip()
        # The forwarded headers are deliberately NOT read: they are
        # caller-supplied unless the proxy is trusted, and a header an attacker
        # writes cannot decide its own trust.
        return peer_address.get()
    keys = getattr(getter, "keys", None)
    if keys is not None:
        try:
            # the celery getter answers no keys at all, which is also the
            # honest answer here: a broker message names no network peer
            if not keys(carrier):
                return None
        except Exception:
            return None
    return peer_address.get()


def mark_untrusted_destination(untrusted: bool):
    """Remember, for the current outbound call, whether it may carry context."""
    return untrusted_destination.set(bool(untrusted))


def reset_untrusted_destination(token) -> None:
    untrusted_destination.reset(token)


def set_peer_address(address):
    """Record the peer of the current inbound call; returns a reset token."""
    return peer_address.set(address)


def reset_peer_address(token) -> None:
    peer_address.reset(token)


def strip_context_headers(headers) -> None:
    """Remove every trace-context header a caller may have written itself.

    ``headers`` is anything mapping-like which supports ``del`` (the
    ``CaseInsensitiveDict`` of a ``PreparedRequest``, a plain dict). Called
    before the decision to inject, so a caller cannot smuggle a parent into an
    otherwise clean outbound hop. The ASGI list of inbound tuples is inbound and
    handled by :func:`strip_asgi_headers`.
    """
    if headers is None:
        return
    for name in list(headers):
        if isinstance(name, str) and name.lower() in CONTEXT_HEADERS:
            try:
                del headers[name]
            except Exception:
                continue


def strip_asgi_headers(headers):
    """The inbound ASGI headers without any trace context (a new list)."""
    kept = []
    for name, value in (headers or ()):
        try:
            key = name.decode("latin-1") if isinstance(name, bytes) else str(name)
        except Exception:
            kept.append((name, value))
            continue
        if key.lower() in CONTEXT_HEADERS:
            continue
        kept.append((name, value))
    return kept
