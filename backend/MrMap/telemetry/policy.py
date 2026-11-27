"""What may leave a MrMap process, and where the bound is applied (#1779).

ADR-0003's privacy section is the contract, and it is unusually specific about the
*where*: an allowlist which runs at export time over data the SDK already
aggregated is not the contract, because the forbidden dimension already cost
memory and already entered a series. So the two enforcement points are the ones
the SDK actually offers:

*   **metrics** - :func:`views`. Every instrument this project exports goes
    through a :class:`~opentelemetry.sdk.metrics.view.View` which *projects* the
    attribute set down to the allowlist and caps the cardinality. Projection
    happens before aggregation, so a forbidden value never becomes a series. A
    second group of views drops upstream instruments whose contract this project
    does not want at all (the Celery instrumentor's ``flower.*`` histogram, the
    pre-HTTP-semconv duplicates).
*   **spans** - :class:`SanitizingSpanExporter` wraps the OTLP exporter and is the
    last seam before bytes leave the process: it replaces the attribute mapping
    with the allowlisted one, truncates values, caps events/links/attributes and
    drops everything whose name is not listed. :class:`StripOnStartSpanProcessor`
    does the same for the attributes a span is *created* with, so a forbidden
    value is not even carried in the export queue.

Deny-by-name is not sufficient and is not what is implemented: a name that is not
on the allowlist of its kind is dropped, whatever it is. The denylist of
:data:`NEVER_EXPORT_KEYS` exists only as a loud double-check for the attributes
upstream instrumentation is known to produce (URLs, message ids, peer addresses,
SQL, user agents) - a test asserts that everything the stock instrumentations set
in a request/task round trip either survives on an allowlist or is in this set.
"""

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.metrics.view import (DropAggregation,
                                            ExplicitBucketHistogramAggregation,
                                            View)
from opentelemetry.sdk.trace import Event, ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Link

#: the explicit histogram boundaries of ADR-0003, in seconds. ``0.4`` is in the
#: list because the legacy slow-request detector of #888/#1782 answered "slower
#: than 400 ms", and the count above it is computed as ``count - le=0.4`` - which
#: excludes exactly 0.4 s, the same reading the legacy threshold had.
HTTP_DURATION_BOUNDARIES = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.4, 0.5, 0.75,
    1, 2.5, 5, 7.5, 10,
)

#: task boundaries extend to the longest work this deployment runs on purpose
#: (#1396's harvests); checked against the measured workload shapes of #1396.
TASK_DURATION_BOUNDARIES = HTTP_DURATION_BOUNDARIES + (
    30, 60, 120, 300, 600, 1800, 3600, 14400,
)

#: the queue-wait boundaries; a wait longer than an hour is a starvation
#: incident, not a percentile, so the tail is coarse on purpose.
QUEUE_WAIT_BOUNDARIES = (
    0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300, 900, 3600, 14400,
)

# --------------------------------------------------------------- allowlists ---

#: identity fields of the resource, allowed on every signal
RESOURCE_KEYS = frozenset({
    "service.name",
    "service.version",
    "deployment.environment.name",
    "service.instance.id",
    "telemetry.sdk.name",
    "telemetry.sdk.version",
    "telemetry.sdk.language",
})

#: every span kind may carry these
_SPAN_COMMON_KEYS = frozenset({
    "error.type",
    "exception.type",
})

#: what a server span may say: the route *template* of a registered URL, the
#: method, the scheme, the status. Never a path, never a query, never a host.
SPAN_SERVER_KEYS = _SPAN_COMMON_KEYS | frozenset({
    "http.request.method",
    "url.scheme",
    "http.route",
    "http.response.status_code",
    "network.protocol.version",
    "http.server_name",
})

#: what a client span may say. ``url.full``, ``server.address``,
#: ``network.peer.address`` and the port are deliberately absent: an OGC hostname
#: of a third party is a business identifier of that third party, and a URL
#: carries a path and a query (#1474's fetch policy is what makes such a URL
#: somebody else's input).
SPAN_CLIENT_KEYS = _SPAN_COMMON_KEYS | frozenset({
    "http.request.method",
    "url.scheme",
    "http.response.status_code",
    "network.protocol.version",
    "mrmap.remote.kind",
})

#: the method of the operation a span describes, which even the strictest kind
#: may state: "GET" of a request and "apply_async" of a publish are both facts
#: about the call, and neither names anything
_SPAN_METHOD_KEYS = frozenset({"http.request.method", "rpc.method"})

#: what a worker/producer span may say about a task. No task uuid, no root id,
#: no parent id, no worker name, no payload size, no retry/revocation reason
#: text, no message id.
SPAN_MESSAGING_KEYS = _SPAN_COMMON_KEYS | _SPAN_METHOD_KEYS | frozenset({
    "celery.action",
    "mrmap.task.class",
    "mrmap.queue",
    "mrmap.task.outcome",
    "messaging.system",
    "messaging.operation",
    "messaging.destination.name",
})

#: what a database span may say, and only while the operator asked for SQL
#: spans at all: the system and the operation name. A statement is never
#: exported - not raw, not "sanitized", not as a signature - because #888 is the
#: precedent of what an interpolated statement turns into.
SPAN_DB_KEYS = _SPAN_COMMON_KEYS | frozenset({
    "db.system",
    "db.operation.name",
    "db.operation",
})

#: what a cache span may say while the operator asked for them.
SPAN_CACHE_KEYS = _SPAN_COMMON_KEYS | frozenset({
    "db.system",
    "db.operation.name",
    "db.operation",
})

#: the span kinds whose attributes are judged by which allowlist
_SPAN_KEYS_BY_KIND = {
    "SERVER": SPAN_SERVER_KEYS,
    "CLIENT": SPAN_CLIENT_KEYS,
    "CONSUMER": SPAN_MESSAGING_KEYS,
    "PRODUCER": SPAN_MESSAGING_KEYS,
    # an internal span is an implementation detail of this process, so it is
    # judged by the strictest list rather than by the server one
    "INTERNAL": SPAN_MESSAGING_KEYS,
}

#: the attributes the stock instrumentations of the pinned release are known to
#: produce and which must never reach an export. Not the mechanism (the
#: allowlists above are), but the list a reviewer can check a new upstream
#: release against: adding an attribute upstream is caught by
#: ``tests/django/system/test_observability_telemetry.py`` naming it here.
NEVER_EXPORT_KEYS = frozenset({
    # urls, hosts and paths
    "url.full", "url.path", "url.query", "url.scheme.deny", "http.url",
    "http.target", "http.host", "http.server_name.deny", "http.scheme",
    "net.host.name", "net.host.port", "net.peer.name", "net.peer.port",
    "net.sock.peer.addr", "net.sock.peer.port", "server.address",
    "server.port", "network.peer.address", "network.peer.port",
    "client.address", "client.port", "http.client_ip", "http.flavor",
    # identities and correlation ids which are not operator-safe labels
    "messaging.message.id", "messaging.destination.subscription.name",
    "celery.task_id", "task_id", "root_id", "parent_id",
    "messaging.celery.task.id", "mrmap.task.id",
    # payloads and bodies
    "messaging.message.payload_size_bytes",
    "messaging.message.envelope.size", "http.request_content_length",
    "http.response_content_length", "http.request.body", "http.response.body",
    # free-form text an attacker or a third party writes
    "exception.message", "exception.stacktrace", "exc.message",
    "celery.retry.reason", "celery.revoked.reason",
    "celery.terminated.signal", "celery.task_name",
    "user_agent.original", "user_agent.synthetic_type",
    "http.request.header.authorization", "http.request.header.cookie",
    # sql / redis detail
    "db.statement", "db.sql.table", "db.query.text", "db.statement.parameters",
    "db.statement_parameter", "redis.database_index",
})

#: instruments whose metric stream this project replaces with its own
#: ``mrmap.*`` contract; the Celery instrumentor of the pinned release publishes
#: ``flower.task.runtime.seconds`` (unit seconds, attributes task + worker),
#: which carries a raw task name and a worker name as dimensions.
DROP_INSTRUMENTS = (
    "flower.task.runtime.seconds",
    "flower.tasks.success",
    "flower.tasks.failure",
    # pre-HTTP-semconv names: OTEL_SEMCONV_STABILITY_OPT_IN=http makes upstream
    # report only the new names; these views are the belt so a stale default in
    # one process cannot start a second, unbounded pipeline beside the first.
    "http.server.duration",
    "http.server.request.duration.old",
    "http.client.duration",
)

#: the metric attributes of each instrument we own or forward
HTTP_SERVER_METRIC_KEYS = frozenset({
    "http.request.method", "url.scheme", "http.route",
    "http.response.status_code", "error.type",
})
HTTP_CLIENT_METRIC_KEYS = frozenset({
    "http.request.method", "http.response.status_code", "error.type",
})
TASK_METRIC_KEYS = frozenset({
    "mrmap.task.class", "mrmap.queue", "mrmap.task.outcome",
})
TASK_WAIT_METRIC_KEYS = frozenset({"mrmap.task.class", "mrmap.queue"})
OBSERVATION_METRIC_KEYS = frozenset({
    "mrmap.task.class", "mrmap.queue", "mrmap.observation.quality",
})
DROPPED_METRIC_KEYS = frozenset({"mrmap.signal", "mrmap.drop.reason"})


def allowed_span_attributes(kind, attributes, sql_enabled=False,
                            redis_enabled=False):
    """The allowlisted subset of one span's attributes.

    Unknown names are dropped rather than passed through, so a new upstream
    attribute is a *missing* attribute after an upgrade and not a leak.
    """
    # the enum's name, not its str(): str(SpanKind.SERVER) is "SpanKind.SERVER"
    base = _SPAN_KEYS_BY_KIND.get(getattr(kind, "name", None),
                                  SPAN_MESSAGING_KEYS)
    allowed = set(base)
    if sql_enabled:
        allowed |= SPAN_DB_KEYS
    if redis_enabled:
        allowed |= SPAN_CACHE_KEYS
    safe = {}
    for key, value in (attributes or {}).items():
        if key in NEVER_EXPORT_KEYS or key not in allowed:
            continue
        safe[key] = _bounded_value(value)
    return safe


def allowed_resource_attributes(attributes):
    """The resource of one process: our own identity, nothing a detector found."""
    return {
        key: _bounded_value(value)
        for key, value in (attributes or {}).items()
        if key in RESOURCE_KEYS and key not in NEVER_EXPORT_KEYS
    }


def _bounded_value(value):
    """Scalars only, strings at most :data:`MAX_VALUE_LENGTH` characters.

    A sequence keeps its length bound; a mapping is dropped, because the only
    mappings the SDK accepts in practice are of no interest here and a nested
    value is a value this module has not read.
    """
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_VALUE_LENGTH else (
            value[:MAX_VALUE_LENGTH])
    if isinstance(value, (list, tuple)):
        bounded = [_bounded_value(item) for item in value[:MAX_SEQUENCE_ITEMS]]
        return [item for item in bounded if isinstance(
            item, (str, int, float, bool))]
    return None


#: ADR-0003's provisional span bounds
MAX_VALUE_LENGTH = 128
MAX_SPAN_ATTRIBUTES = 32
MAX_SPAN_EVENTS = 8
MAX_SPAN_LINKS = 8
MAX_SEQUENCE_ITEMS = 8


def views(values):
    """The metric views of one instrumented process.

    Two jobs, in this order: drop the upstream streams this project does not
    want, and project every stream it does want down to the allowlisted
    attributes with an explicit histogram and a cardinality cap. The cap leaves
    one slot for the SDK's own ``otel.metric.overflow`` series, which is why
    ``aggregation_cardinality_limit`` is ``budget - 1``: the contract is
    *budget* total series per instrument, overflow included.
    """
    limit = max(1, int(values["max_attribute_sets"]) - 1)
    return [
        View(instrument_name=name, aggregation=DropAggregation())
        for name in DROP_INSTRUMENTS
    ] + [
        View(
            instrument_name="http.server.request.duration",
            attribute_keys=set(HTTP_SERVER_METRIC_KEYS),
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=list(HTTP_DURATION_BOUNDARIES)),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="http.client.request.duration",
            attribute_keys=set(HTTP_CLIENT_METRIC_KEYS),
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=list(HTTP_DURATION_BOUNDARIES)),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="mrmap.task.attempt.duration",
            attribute_keys=set(TASK_METRIC_KEYS),
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=list(TASK_DURATION_BOUNDARIES)),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="mrmap.task.queue.wait",
            attribute_keys=set(TASK_WAIT_METRIC_KEYS),
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=list(QUEUE_WAIT_BOUNDARIES)),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="mrmap.task.attempts",
            attribute_keys=set(TASK_METRIC_KEYS),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="mrmap.task.observations",
            attribute_keys=set(OBSERVATION_METRIC_KEYS),
            aggregation_cardinality_limit=limit,
        ),
        View(
            instrument_name="mrmap.telemetry.dropped",
            attribute_keys=set(DROPPED_METRIC_KEYS),
            aggregation_cardinality_limit=limit,
        ),
    ]


class SanitizingSpanExporter(SpanExporter):
    """The last seam before a span leaves the process.

    The exporter of the SDK serializes whatever a processor handed it, so this
    wrapper - not a hook that *adds* fields - is what enforces the contract. It
    never raises: a sanitizing bug must cost telemetry, not the request.
    """

    def __init__(self, exporter, values, dropped=None):
        self._exporter = exporter
        self._values = values
        self._dropped = dropped

    def export(self, spans):
        try:
            safe = [self._sanitize(span) for span in spans or ()]
        except Exception:  # pragma: no cover - defensive, never break the app
            self._count_drop("traces", "export_error")
            return SpanExportResult.FAILURE
        safe = [span for span in safe if span is not None]
        if not safe:
            return SpanExportResult.SUCCESS
        try:
            return self._exporter.export(safe)
        except Exception:  # pragma: no cover - exporter already swallows, belt
            self._count_drop("traces", "export_error")
            return SpanExportResult.FAILURE

    def _sanitize(self, span):
        context = span.context
        if context is None:
            self._count_drop("traces", "dropped")
            return None
        attributes = allowed_span_attributes(
            span.kind, dict(span.attributes or {}),
            sql_enabled=self._values["sql_enabled"],
            redis_enabled=self._values["redis_enabled"])
        if len(attributes) > MAX_SPAN_ATTRIBUTES:
            attributes = dict(list(attributes.items())[:MAX_SPAN_ATTRIBUTES])
        events = []
        for event in (span.events or ())[:MAX_SPAN_EVENTS]:
            event_attributes = {
                key: _bounded_value(value)
                for key, value in dict(event.attributes or {}).items()
                if key not in NEVER_EXPORT_KEYS
                and (key.startswith("exception.")
                     and key not in ("exception.message",
                                     "exception.stacktrace")
                     or key in _SPAN_COMMON_KEYS)
            }
            events.append(Event(name=event.name[:MAX_VALUE_LENGTH],
                                attributes=event_attributes,
                                timestamp=event.timestamp))
        links = []
        for link in (span.links or ())[:MAX_SPAN_LINKS]:
            link_attributes = {
                key: _bounded_value(value)
                for key, value in dict(link.attributes or {}).items()
                if key not in NEVER_EXPORT_KEYS
            }
            links.append(Link(context=link.context,
                              attributes=link_attributes))
        # the SDK's own readable span, rebuilt rather than mutated: the object a
        # processor received belongs to the SDK, and the exporter must never see
        # a span this module half-edited when sanitizing went wrong. The resource
        # goes through the same allowlist, because a span carries it out of the
        # process as part of the same request (ADR-0003: "including resources")
        return ReadableSpan(
            name=span.name[:MAX_VALUE_LENGTH],
            context=context,
            parent=span.parent,
            resource=Resource(
                attributes=allowed_resource_attributes(
                    dict(span.resource.attributes or {}))
                if span.resource is not None else None),
            attributes=attributes,
            events=events,
            links=links,
            kind=span.kind,
            status=span.status,
            start_time=span.start_time,
            end_time=span.end_time,
            instrumentation_scope=span.instrumentation_scope,
        )

    def _count_drop(self, signal, reason):
        if self._dropped is not None:
            self._dropped(signal, reason)

    def force_flush(self, timeout_millis=None):
        # never called from a request or task path; only from a process teardown
        try:
            return self._exporter.force_flush(timeout_millis)
        except Exception:
            return False

    def shutdown(self, timeout_millis=None):
        try:
            return self._exporter.shutdown(timeout_millis)
        except Exception:
            return False


class StripOnStartSpanProcessor(SpanProcessor):
    """Drop forbidden attributes while the span is still empty of them.

    The export-time filter is the guarantee; this processor is the reason a
    forbidden URL or task uuid does not sit in the export queue of a worker for
    five seconds in the meantime. It rewrites the span's own bounded attribute
    mapping in place - the SDK reads the same object at export time, so the two
    layers cannot disagree.
    """

    def __init__(self, values):
        self._values = values

    def on_start(self, span, parent_context=None):
        try:
            raw = getattr(span, "_attributes", None)
            if not raw:
                return
            safe = allowed_span_attributes(
                span.kind, dict(raw),
                sql_enabled=self._values["sql_enabled"],
                redis_enabled=self._values["redis_enabled"])
            for key in [key for key in raw if key not in safe]:
                del raw[key]
        except Exception:  # pragma: no cover
            # never break the traced work: a span which cannot be stripped is
            # still a span, and the export-time filter is the guarantee
            return

    def on_end(self, span):
        return None

    def shutdown(self):
        return None

    def force_flush(self, timeout_millis=None):
        # nothing is buffered here; the batch processor owns the queue
        return True
