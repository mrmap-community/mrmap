"""Synthetic SDK/protobuf experiment for #1776; no application/store imports.

Run in a disposable venv as documented in observability-inventory.md. This
receiver decodes the wire payload; it is not a Victoria compatibility test.
"""

import json
import platform
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.metadata import version

from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON


def main():
    captures = []
    failures = []
    metrics_path = "/opentelemetry/v1/metrics"
    traces_path = "/insert/opentelemetry/v1/traces"
    status = {"code": 200}

    class Receiver(BaseHTTPRequestHandler):
        def do_POST(self):
            try:
                assert self.headers.get("Content-Type") == "application/x-protobuf"
                decoder = {
                    metrics_path: ExportMetricsServiceRequest,
                    traces_path: ExportTraceServiceRequest,
                }[self.path]
                data = decoder.FromString(self.rfile.read(int(self.headers["Content-Length"])))
                captures.append((self.path, data))
                self.send_response(status["code"])
                self.end_headers()
            except Exception as error:
                failures.append(type(error).__name__)
                self.send_response(400)
                self.end_headers()

        def log_message(self, *args):
            pass

    resource = Resource({"service.name": "mrmap-http", "service.version": "probe"})
    meters = None
    providers = []
    server = HTTPServer(("127.0.0.1", 0), Receiver)
    receiver = threading.Thread(target=server.serve_forever, daemon=True)
    receiver.start()
    endpoint = "http://127.0.0.1:%s" % server.server_port
    try:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint + metrics_path, timeout=1),
            export_interval_millis=60000, export_timeout_millis=1000,
        )
        meters = MeterProvider(resource=resource, metric_readers=[reader], views=[View(
            instrument_name="http.server.request.duration",
            attribute_keys={"http.route", "http.request.method", "http.response.status_code"},
            aggregation=ExplicitBucketHistogramAggregation(boundaries=[0.4, 1.0]),
            aggregation_cardinality_limit=2,
        )])
        histogram = meters.get_meter("mrmap-1776-probe").create_histogram(
            "http.server.request.duration", unit="s")

        def tracer(sampler):
            provider = TracerProvider(resource=resource, sampler=sampler)
            provider.add_span_processor(BatchSpanProcessor(
                OTLPSpanExporter(endpoint=endpoint + traces_path, timeout=1),
                max_queue_size=8, max_export_batch_size=4,
                schedule_delay_millis=60000, export_timeout_millis=1000,
            ))
            providers.append(provider)
            return provider, provider.get_tracer("mrmap-1776-probe")

        disabled, off_tracer = tracer(ALWAYS_OFF)
        for duration in [0.399, 0.4, 0.401]:
            with off_tracer.start_as_current_span("GET route"):
                histogram.record(duration, {
                    "http.route": "/api/example/<id>", "http.request.method": "GET",
                    "http.response.status_code": 200, "forbidden.synthetic": "discard",
                })
        disabled.force_flush(timeout_millis=1000)
        reader.collect(timeout_millis=1000)
        assert not any(path == traces_path for path, _ in captures)
        message = next(data for path, data in captures if path == metrics_path)
        point = message.resource_metrics[0].scope_metrics[0].metrics[0].histogram.data_points[0]
        assert point.count == 3 and list(point.explicit_bounds) == [0.4, 1.0]
        assert list(point.bucket_counts) == [2, 1, 0]
        assert {attr.key for attr in point.attributes} == {
            "http.route", "http.request.method", "http.response.status_code"}
        # CUMULATIVE = 2 in the OTLP protobuf; default must be pinned/verified.
        assert message.resource_metrics[0].scope_metrics[0].metrics[0].histogram.aggregation_temporality == 2

        for route in ["/a", "/b", "/c"]:
            histogram.record(0.1, {"http.route": route})
        reader.collect(timeout_millis=1000)
        overflow_message = next(data for path, data in reversed(captures) if path == metrics_path)
        points = overflow_message.resource_metrics[0].scope_metrics[0].metrics[0].histogram.data_points
        assert len(points) == 3 and sum(p.count for p in points) == 6
        overflow = [p for p in points if any(a.key == "otel.metric.overflow" for a in p.attributes)]
        assert len(overflow) == 1 and overflow[0].count == 2

        enabled, on_tracer = tracer(ALWAYS_ON)
        with on_tracer.start_as_current_span("GET route"):
            pass
        assert enabled.force_flush(timeout_millis=2000)
        assert sum(len(scope.spans) for path, data in captures if path == traces_path
                   for batch in data.resource_spans for scope in batch.scope_spans) == 1

        status["code"] = 400  # permanent refusal: exporter must not fail caller
        with on_tracer.start_as_current_span("GET refused-export"):
            work_result = "completed"
        enabled.force_flush(timeout_millis=2000)
        assert work_result == "completed" and not failures
        print(json.dumps({
            "python": platform.python_version(),
            "sdk": version("opentelemetry-sdk"),
            "http_exporter": version("opentelemetry-exporter-otlp-proto-http"),
            "sampling_off_metric_count": point.count,
            "explicit_bounds_seconds": list(point.explicit_bounds),
            "bucket_counts": list(point.bucket_counts),
            "metric_forbidden_attribute_removed": True,
            "temporality": "cumulative",
            "normal_series_limit": 2,
            "total_series_with_overflow": len(points),
            "overflow_observation_count": overflow[0].count,
            "sampling_on_exported_spans_before_refusal": 1,
            "export_http_400_work_result": work_result,
            "receiver_decode_failures": failures,
            "real_store_compatibility": "not tested",
        }, sort_keys=True))
    finally:
        # Drain while the receiver is still alive, then close every thread/socket.
        for provider in providers:
            provider.shutdown()
        if meters is not None:
            meters.shutdown(timeout_millis=2000)
        server.shutdown()
        server.server_close()
        receiver.join(timeout=2)


if __name__ == "__main__":
    main()
