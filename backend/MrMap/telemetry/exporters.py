"""The exporter seams of the OTLP/HTTP path (#1779).

Three promises, all of them about the boundary between the application and the
collector:

*   **never on the hot path.** Everything here is called from the SDK's own batch
    thread, never from a request or a task. ``force_flush`` exists for the process
    teardown, and nothing in this package calls it on a request or task path.
*   **bounded.** One HTTP call per attempt, a bounded number of attempts, one
    timeout per attempt, and the batch processor's fixed queue in front of it. A
    refused, slow, DNS-dead or full collector costs telemetry and is *counted*,
    never propagated into the application: no exception leaves these classes, and
    no disk spool is written.
*   **not self-instrumenting.** The OTLP exporter of the pinned release speaks
    with ``requests``, and the requests instrumentor patches ``Session.send``
    globally. So every exporter call runs inside upstream's own suppression
    context: an exporter span beside the export it performs is the recursion
    ADR-0003 forbids, and a deployment whose collector is down would otherwise
    feed its own failure loop back into the queue that is already full.

The retry loop deliberately knows nothing about the status code it is retrying:
the SDK's exporter collapses the answer to a result enum, and re-deriving the HTTP
code from a private client attribute to save one request is not worth coupling to
it. The bound - attempts and timeout - is the contract, and the drop counter is
what makes losing them visible.
"""

import math
from contextlib import ExitStack

from opentelemetry.exporter.otlp.proto.http.metric_exporter import \
    OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import \
    OTLPSpanExporter
from opentelemetry.instrumentation.utils import (suppress_http_instrumentation,
                                                 suppress_instrumentation)
from opentelemetry.sdk.metrics import (Counter, Histogram, ObservableCounter,
                                       ObservableGauge,
                                       ObservableUpDownCounter,
                                       UpDownCounter)
from opentelemetry.sdk.metrics.export import (AggregationTemporality,
                                              MetricExporter,
                                              MetricExportResult,
                                              PeriodicExportingMetricReader)
from opentelemetry.sdk.trace.export import SpanExportResult

#: Every instrument of the contract, exported cumulative: a restart continues a
#: series instead of resetting it, which is what the per-writer identity of the
#: resource exists to keep honest (ADR-0003). Upstream wants a mapping per
#: instrument class and not one value, and the classes it matches are the SDK's -
#: the API classes of ``opentelemetry.metrics`` are rejected by the reader.
CUMULATIVE_TEMPORALITY = {
    instrument: AggregationTemporality.CUMULATIVE
    for instrument in (Counter, UpDownCounter, Histogram, ObservableCounter,
                       ObservableUpDownCounter, ObservableGauge)
}


class _Quiet:
    """Suppress self-instrumentation for the duration of one exporter call.

    Both upstream suppression keys are set together: ``suppress_instrumentation``
    is the general key, ``suppress_http_instrumentation`` the one the requests
    instrumentor reads before it creates a client span.
    """

    def __enter__(self):
        self._stack = ExitStack()
        self._stack.enter_context(suppress_instrumentation())
        self._stack.enter_context(suppress_http_instrumentation())
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stack.close()
        return False


def _call_with_timeout(proxy, name, timeout_millis):
    """Call an exporter's teardown hook with or without a timeout, as it accepts.

    The pinned release is inconsistent here - the metric exporter takes
    ``timeout_millis`` on both hooks, the span exporter on neither - and a
    teardown which raised would turn a dead collector into a worker which cannot
    exit. Passing the bound when the hook accepts it is what keeps the drain
    bounded; dropping it when the hook does not is what keeps the call valid.
    """
    hook = getattr(proxy, name)
    try:
        return hook(timeout_millis)
    except TypeError:
        return hook()


class BoundedOTLPSpanExporter(OTLPSpanExporter):
    """OTLP/HTTP span exporter with the timeout, retry and suppression bounds."""

    def __init__(self, values, endpoint=None, dropped=None):
        self._values = values
        self._dropped = dropped
        self._attempts = max(1, int(values.get("export_attempts", 1)))
        super().__init__(
            endpoint=endpoint or None,
            timeout=float(values.get("export_timeout_seconds", 1.0)))

    def export(self, spans):
        if not spans:
            # nothing to send, nothing asked of the network: an empty batch must
            # not cost a connection attempt, a timeout or a DNS lookup
            return SpanExportResult.SUCCESS
        count = len(spans)
        with _Quiet():
            result = super().export(spans)
            for _attempt in range(self._attempts - 1):
                if result is SpanExportResult.SUCCESS:
                    break
                result = super().export(spans)
        if result is not SpanExportResult.SUCCESS:
            # the batch is lost, and the loss is a number an operator can see
            self._count("traces", "export_error", count)
        return result

    # **kwargs because the SDK calls these two with its own keyword spellings
    # (the periodic reader passes ``timeout=`` to shutdown and
    # ``timeout_millis=`` to force_flush) and a dropped batch must never be
    # raised out of a teardown. The span exporter of the pinned release takes no
    # timeout on shutdown at all, so the bound of the teardown lives in the batch
    # processor's own constructor rather than being argued into this one.
    def force_flush(self, timeout_millis=None, **kwargs):
        with _Quiet():
            return _call_with_timeout(super(), "force_flush",
                                      timeout_millis or self._drain_millis())

    def shutdown(self, timeout_millis=None, **kwargs):
        with _Quiet():
            return _call_with_timeout(super(), "shutdown",
                                      timeout_millis or self._drain_millis())

    def _drain_millis(self):
        return int(float(self._values.get("shutdown_drain_seconds", 3.0))
                   * 1000)

    def _count(self, signal, reason, count=1):
        if self._dropped is not None:
            self._dropped(signal, reason, count)


class BoundedOTLPMetricExporter(OTLPMetricExporter):
    """The metric twin: cumulative, because every writer is one process.

    ``CUMULATIVE`` is what lets a restart continue a series instead of resetting
    it, and it is the temporality the VictoriaMetrics OTLP ingestion of #1778 is
    configured for.
    """

    def __init__(self, values, endpoint=None, dropped=None):
        self._values = values
        self._dropped = dropped
        self._attempts = max(1, int(values.get("export_attempts", 1)))
        super().__init__(
            endpoint=endpoint or None,
            preferred_temporality=dict(CUMULATIVE_TEMPORALITY),
            timeout=float(values.get("metric_timeout_seconds", 10.0)))

    def export(self, metrics_data, timeout_millis=None, **kwargs):
        if not metrics_data or not getattr(metrics_data, "resource_metrics", None):
            return MetricExportResult.SUCCESS
        with _Quiet():
            result = super().export(metrics_data,
                                    timeout_millis=timeout_millis, **kwargs)
            for _attempt in range(self._attempts - 1):
                if result is MetricExportResult.SUCCESS:
                    break
                result = super().export(metrics_data,
                                        timeout_millis=timeout_millis,
                                        **kwargs)
        if result is not MetricExportResult.SUCCESS:
            self._count("metrics", "export_error")
        return result

    def force_flush(self, timeout_millis=None, **kwargs):
        with _Quiet():
            return super().force_flush(timeout_millis or self._drain_millis())

    def shutdown(self, timeout_millis=None, **kwargs):
        with _Quiet():
            return super().shutdown(timeout_millis or self._drain_millis())

    def _drain_millis(self):
        return int(float(self._values.get("shutdown_drain_seconds", 3.0))
                   * 1000)

    def _count(self, signal, reason, count=1):
        if self._dropped is not None:
            self._dropped(signal, reason, count)


class QuietMetricReader(PeriodicExportingMetricReader):
    """The reader of a process which named no metric endpoint.

    Built from the SDK's own periodic reader with its documented "never collect
    periodically" interval, rather than from a private reader class: the whole
    point of this package is that the aggregation which bounds cardinality is the
    SDK's, and reimplementing a reader would put a second implementation of that
    between MrMap and the pinned release. Nothing is ever exported, so nothing
    can block, and no thread of this process exists to be forked away from.
    """

    def __init__(self):
        super().__init__(NullMetricExporter(),
                         export_interval_millis=math.inf)


class NullMetricExporter(MetricExporter):
    """The reader's sink when the deployment named no metric endpoint.

    Aggregation still happens - that is where the cardinality bound lives - and
    the drop counters stay observable, but no bytes are produced and no collector
    is required. Deliberately not the SDK's console exporter: telemetry which is
    switched off must not print.

    A subclass of the SDK's exporter rather than a duck type, because
    ``PeriodicExportingMetricReader`` reads ``_preferred_temporality`` and
    ``_preferred_aggregation`` off the instance it is handed: the cumulative
    contract of the whole package is stated here too, for the no-endpoint case
    which states it nowhere else.
    """

    def __init__(self):
        super().__init__(preferred_temporality=dict(CUMULATIVE_TEMPORALITY),
                         preferred_aggregation={})

    def export(self, metrics_data, timeout_millis=None, **kwargs):
        return MetricExportResult.SUCCESS

    def force_flush(self, timeout_millis=None, **kwargs):
        return True

    def shutdown(self, timeout_millis=None, **kwargs):
        return None
