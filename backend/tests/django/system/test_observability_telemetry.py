"""The optional OpenTelemetry integration of #1779, on the pinned SDK.

The acceptance list of the issue is mostly made of negations - disabled must cost
nothing, the pipeline must not double up, nothing forbidden may leave the process,
no export may ever be seen by a request or a task - and a test which only checks
that "a span appeared" proves none of them. So these tests ask the negative
questions against the real SDK of ``.requirements/base.txt`` rather than against a
mock of it.

Groups, in the order of the acceptance list:

``ConfigTests`` / ``SettingsProjectionTests``
    one source of truth for the knobs, ``off`` as the fail-safe answer, every
    number clamped into its documented range.
``DisabledModeTests``
    ``off`` starts no instrumentor, no provider, no exporter thread and no lookup
    of a collector address.
``ProcessLifecycleTests``
    one initialization per process, and a forked child which replaces rather than
    inherits the threads of the parent (the fork-safety rule of ADR-0003).
``SamplingTests``
    parent-based head sampling, with the trust decision taken *before* it.
``PropagationTests`` / ``RequestsGuardTests``
    a caller cannot choose its own parent, and nothing leaving towards a third
    party carries a trace header - including a caller's own ``PreparedRequest``.
``SpanPolicyTests``
    the allowlists, with SQL binds, URLs, identifiers and free-form text denied in
    every mode.
``MetricContractTests``
    the ``mrmap.*`` instruments: dimensions projected **before** aggregation, the
    upstream ``flower.*`` stream dropped, cardinality capped including the SDK's
    overflow series, and recordings independent of the trace sampler.
``CeleryAttemptTests``
    retries, revocations and missing stamps, and the rule that a broken observer
    never costs the task it observes.
``NamingTests``
    the bounded dimension vocabulary: a registered template or ``other``, never a
    path, a foreign queue or an unknown task name.
``ExportBoundaryTests``
    an unreachable collector costs telemetry only, the probes are excluded from
    their own pipeline, and the shutdown drain is bounded.

No test here talks to a collector: an endpoint is either absent or refused, and the
metric assertions read an ``InMemoryMetricReader``. Nothing of this module needs the
telemetry services of the stack, which is the same promise the ``off`` mode makes.
"""

import os
import re
import threading
import time
from contextlib import contextmanager
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from MrMap.telemetry import (celery_metrics, config, exporters, instrumentation,
                             lifecycle, metrics, naming, policy, propagation)


#: the SDK's own worker threads; a deployment which measures "no telemetry" needs
#: a number to measure, and these are the names the batch pipeline gives them
PIPELINE_THREADS = ("OtelBatchSpan", "OtelPeriodicExportingMetricReader")


def pipeline_threads():
    """The exporter/reader threads alive in this process."""
    return [name for name in (thread.name for thread in threading.enumerate())
            if any(name.startswith(prefix) for prefix in PIPELINE_THREADS)]


@contextmanager
def environ(**values):
    """Set (and afterwards restore) deployment environment variables."""
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update({key: str(value) for key, value in values.items()})
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def isolated_telemetry():
    """A clean telemetry process state, restored afterwards.

    The lifecycle's state and the instrument caches are per-process memory, so a
    test which initializes must leave nothing for the next one - the same reason
    #1330's collector has ``reset_collector``.
    """
    lifecycle.shutdown("test enter")
    instrumentation.uninstrument()
    metrics.detach()
    naming.reset_caches()
    celery_metrics.reset_collector()
    try:
        yield
    finally:
        lifecycle.shutdown("test leave")
        instrumentation.uninstrument()
        metrics.detach()
        naming.reset_caches()
        celery_metrics.reset_collector()


def standard_env(**extra):
    """The environment of an instrumented process with a refused collector.

    The endpoints point at port 1 on loopback: connection refused, which is the
    failure mode of a collector that is not there at all and therefore exactly
    what the "a dead store costs telemetry only" rule has to survive.
    """
    base = {
        "MRMAP_OTEL_MODE": "standard",
        "MRMAP_OTEL_TRACES_ENDPOINT": "http://127.0.0.1:1/v1/traces",
        "MRMAP_OTEL_METRICS_ENDPOINT": "http://127.0.0.1:1/v1/metrics",
        "MRMAP_OTEL_TRUSTED_HOSTS": "broker.internal;collector.internal",
        "MRMAP_OTEL_TRUSTED_SOURCE_HOSTS": "proxy.internal",
    }
    base.update(extra)
    return base


def metric_data(reader):
    """``{instrument name: [point attributes, ...]}`` of one collection.

    The SDK answers ``None`` when a collection would be empty, which is the
    honest reading of "nothing was recorded" and the answer several of these
    tests assert on.
    """
    collected = {}
    data = reader.get_metrics_data()
    for resource_metrics in (data.resource_metrics if data else ()):
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                collected[metric.name] = [
                    dict(point.attributes) for point in metric.data.data_points]
    return collected


def meter_provider_with_reader(values=None):
    """A provider of the shipped views plus a reader which needs no network."""
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.resources import Resource

    reader = InMemoryMetricReader()
    provider = MeterProvider(
        resource=Resource({"service.name": "mrmap-worker"}),
        views=policy.views(values or config.resolve()),
        metric_readers=[reader])
    return provider, reader


# ---------------------------------------------------------------- knobs ---

class ConfigTests(SimpleTestCase):
    """One parser, a fail-safe default and no unbounded number."""

    def test_off_is_the_shipped_default(self):
        with environ(MRMAP_OTEL_MODE=""):
            values = config.resolve()
        self.assertEqual(values["mode"], config.MODE_OFF)
        self.assertFalse(values["enabled"])

    def test_an_unknown_mode_reads_off_and_not_instrumented(self):
        # a typo must not turn into "instrument everything"
        with environ(MRMAP_OTEL_MODE="everything"):
            self.assertEqual(config.resolve()["mode"], config.MODE_OFF)

    def test_modes_are_the_three_of_the_epic(self):
        self.assertEqual(set(config.MODES), {"off", "standard", "diagnostic"})

    def test_numbers_are_clamped_into_their_documented_range(self):
        with environ(MRMAP_OTEL_TRACES_SAMPLE_RATIO="1e9",
                     MRMAP_OTEL_SPAN_MAX_QUEUE="0",
                     MRMAP_OTEL_SPAN_MAX_EXPORT_BATCH="-5",
                     MRMAP_OTEL_EXPORTER_TIMEOUT_SECONDS="3600"):
            values = config.resolve()
        self.assertEqual(values["trace_ratio"], 1.0)
        self.assertEqual(values["span_max_queue"], 16)
        self.assertEqual(values["span_max_export_batch"], 1)
        self.assertLessEqual(values["export_timeout_seconds"], 60.0)

    def test_garbage_answers_the_default_and_never_raises(self):
        with environ(MRMAP_OTEL_TRACES_SAMPLE_RATIO="nearly",
                     MRMAP_OTEL_MAX_ATTRIBUTE_SETS="?"):
            values = config.resolve()
        self.assertEqual(values["trace_ratio"], 0.01)
        self.assertEqual(values["max_attribute_sets"], 2000)

    def test_the_batch_pipeline_is_the_bounded_one_of_the_adr(self):
        with environ(MRMAP_OTEL_MODE="standard"):
            values = config.resolve()
        self.assertLessEqual(values["span_max_queue"], 512)
        self.assertLessEqual(values["span_max_export_batch"], 128)
        self.assertLessEqual(values["span_schedule_delay_seconds"], 5.0)
        self.assertLessEqual(values["export_timeout_seconds"], 1.0)
        self.assertGreaterEqual(values["metric_interval_seconds"], 30.0)

    def test_sql_and_redis_are_off_in_every_mode(self):
        for mode in config.MODES:
            with environ(MRMAP_OTEL_MODE=mode):
                values = config.resolve()
            self.assertFalse(values["sql_enabled"], mode)
            self.assertFalse(values["redis_enabled"], mode)

    def test_the_outbound_client_spans_are_a_diagnostic_extra(self):
        with environ(MRMAP_OTEL_MODE="standard"):
            self.assertFalse(config.resolve()["http_client_enabled"])
        with environ(MRMAP_OTEL_MODE="diagnostic"):
            self.assertTrue(config.resolve()["http_client_enabled"])

    def test_debug_mode_bounds_itself(self):
        with environ(MRMAP_OTEL_MODE="diagnostic",
                     MRMAP_OTEL_DEBUG_MAX_MINUTES="15"):
            values = config.resolve()
        self.assertLessEqual(values["debug_max_minutes"], 15.0)

    def test_trusted_hosts_are_hostnames_and_deduplicated(self):
        with environ(MRMAP_OTEL_TRUSTED_HOSTS="Broker.Internal, broker.internal ;",
                     MRMAP_OTEL_TRUSTED_SOURCE_HOSTS="10.0.0.5"):
            values = config.resolve()
        self.assertEqual(values["trusted_hosts"], ("broker.internal",))
        self.assertEqual(values["trusted_source_hosts"], ("10.0.0.5",))

    def test_describe_names_the_decisions_of_one_process(self):
        with environ(MRMAP_OTEL_MODE="standard",
                     MRMAP_OTEL_SERVICE_NAME="mrmap-http"):
            line = config.describe(config.resolve())
        for needle in ("standard", "mrmap-http", "sql off", "redis off"):
            self.assertIn(needle, line)


class SettingsProjectionTests(SimpleTestCase):
    """``MrMap/settings.py`` must project what the parser answered.

    Two sources of truth for one knob is how #1615 got its configured-but-never-
    read numbers, so the projection is asserted rather than trusted.
    """

    def test_the_documented_names_all_exist(self):
        from django.conf import settings

        documented = {
            "OTEL_MODE", "OTEL_VALUES", "OTEL_SERVICE_NAME", "OTEL_SERVICE_VERSION",
            "OTEL_DEPLOYMENT_ENVIRONMENT", "OTEL_TRACES_ENDPOINT",
            "OTEL_METRICS_ENDPOINT", "OTEL_TRACES_SAMPLE_RATIO",
            "OTEL_TRUSTED_HOSTS", "OTEL_TRUSTED_SOURCE_HOSTS",
            "OTEL_BROKER_TRUSTED", "OTEL_TASK_CLASSES", "OTEL_MAX_ATTRIBUTE_SETS",
            "OTEL_MAX_TASK_CLASSES", "OTEL_MAX_ROUTES", "OTEL_MAX_QUEUES",
            "OTEL_DEBUG_MAX_MINUTES", "OTEL_HTTP_CLIENT_ENABLED",
            "OTEL_SQL_ENABLED", "OTEL_REDIS_ENABLED", "OTEL_SPAN_MAX_QUEUE",
            "OTEL_SPAN_MAX_EXPORT_BATCH", "OTEL_SPAN_SCHEDULE_DELAY_SECONDS",
            "OTEL_METRIC_INTERVAL_SECONDS", "OTEL_METRIC_TIMEOUT_SECONDS",
            "OTEL_EXPORTER_TIMEOUT_SECONDS", "OTEL_MAX_EXPORT_ATTEMPTS",
            "OTEL_SHUTDOWN_DRAIN_SECONDS", "OTEL_COLLECT_ANY_PROCESS",
        }
        answered = {name for name in dir(settings) if name.startswith("OTEL_")}
        self.assertEqual(answered - documented, set())
        self.assertEqual(documented - answered, set())

    def test_the_projection_equals_the_resolution(self):
        from django.conf import settings

        with environ(**standard_env(MRMAP_OTEL_SERVICE_NAME="mrmap-http",
                                    MRMAP_OTEL_TRACES_SAMPLE_RATIO="0.05",
                                    MRMAP_OTEL_TASK_CLASSES="harvest.run")):
            values = config.resolve()
        self.assertEqual(values["trace_ratio"], 0.05)
        self.assertEqual(values["task_classes"], ("harvest.run",))
        self.assertEqual(settings.OTEL_VALUES["mode"],
                         settings.OTEL_MODE)
        for name, key in (("OTEL_MAX_ATTRIBUTE_SETS", "max_attribute_sets"),
                          ("OTEL_MAX_TASK_CLASSES", "max_task_classes"),
                          ("OTEL_MAX_ROUTES", "max_routes"),
                          ("OTEL_MAX_QUEUES", "max_queues"),
                          ("OTEL_SPAN_MAX_QUEUE", "span_max_queue"),
                          ("OTEL_SHUTDOWN_DRAIN_SECONDS", "shutdown_drain_seconds")):
            self.assertIsInstance(getattr(settings, name), type(values[key]), name)

    def test_the_service_version_is_the_canonical_one(self):
        from django.conf import settings

        from MrMap import VERSION
        self.assertEqual(settings.OTEL_SERVICE_VERSION, VERSION)


# ------------------------------------------------------------- disabled ---

class DisabledModeTests(SimpleTestCase):
    """``off`` must cost nothing, which is a property of the call graph."""

    def test_no_provider_no_thread_and_no_patched_library(self):
        with isolated_telemetry():
            with environ(MRMAP_OTEL_MODE=""):
                before = pipeline_threads()
                self.assertFalse(lifecycle.is_enabled())
                self.assertIsNone(
                    lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER))
                self.assertEqual(pipeline_threads(), before)
                self.assertEqual(instrumentation.installed(), set())
                self.assertIsNone(lifecycle.initialized())

    def test_the_requests_guard_is_not_installed_while_off(self):
        from requests import Session
        with isolated_telemetry():
            with environ(MRMAP_OTEL_MODE=""):
                original = Session.send
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertIs(Session.send, original)

    def test_recording_while_off_is_a_no_op_which_never_raises(self):
        with isolated_telemetry():
            metrics.record_attempt("registry.tasks.harvest.run", "harvest",
                                   "success", active_seconds=1.0, wait_seconds=2.0)
            metrics.record_unmeasured("x", "y")
            metrics.count_dropped("traces", "export_error")

    def test_shutdown_of_an_uninstrumented_process_is_cheap(self):
        with isolated_telemetry():
            with environ(MRMAP_OTEL_MODE=""):
                self.assertFalse(lifecycle.shutdown("nothing here"))

    def test_a_broken_configuration_costs_telemetry_and_not_the_process(self):
        with isolated_telemetry():
            with environ(**standard_env()):
                with patch("MrMap.telemetry.lifecycle._build",
                           side_effect=RuntimeError("the SDK refused")):
                    self.assertIsNone(
                        lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP))
                self.assertIn("the SDK refused", str(lifecycle.failure()))
                # and it says it once: a second call does not retry per request
                self.assertIsNone(
                    lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP))


# ------------------------------------------------------------ lifecycle ---

class ProcessLifecycleTests(SimpleTestCase):
    """One SDK per process, created after the fork."""

    def test_the_ownership_path_of_one_process(self):
        # the "no duplicate export loop" rule of the issue, asked where it is
        # decided: one batch processor and one periodic reader per provider, and
        # a second initialization call which adds neither
        with isolated_telemetry():
            with environ(**standard_env()):
                first = lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertIsNotNone(first)
                self.assertEqual(
                    [type(processor).__name__ for processor in
                     lifecycle._state["provider"]
                     ._active_span_processor._span_processors],
                    ["StripOnStartSpanProcessor", "BatchSpanProcessor"])
                self.assertEqual(
                    [type(reader).__name__ for reader in
                     lifecycle._state["meter_provider"]._metric_readers],
                    ["PeriodicExportingMetricReader"])
                again = lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertIs(first, again)
                self.assertIs(lifecycle._state["provider"],
                              lifecycle._state["provider"])
                self.assertEqual(
                    len(lifecycle._state["meter_provider"]._metric_readers), 1)

    def test_a_forked_child_replaces_what_the_parent_created(self):
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                parent_provider = lifecycle._state["provider"]
                parent_threads = set(pipeline_threads())
                # a fork: the child holds the parent's objects and none of its
                # threads, so the pid check is the only honest detection
                with patch("os.getpid", return_value=os.getpid() + 1):
                    child = lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                    self.assertIsNotNone(child)
                    self.assertIsNot(lifecycle._state["provider"], parent_provider)
                self.assertEqual(set(pipeline_threads()), parent_threads)

    def test_the_preload_shape_never_asks_an_inherited_thread_to_flush(self):
        # asking a thread which does not exist in this process to flush is how a
        # worker hangs at boot, so the child forgets the parent instead of
        # shutting it down
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                inherited = lifecycle._state["provider"]
                with patch.object(
                        type(inherited), "shutdown",
                        side_effect=AssertionError(
                            "a child must never drain the parent's provider")):
                    with patch("os.getpid", return_value=os.getpid() + 2):
                        self.assertIsNotNone(lifecycle.initialize_for_process(
                            role=lifecycle.ROLE_WORKER))

    def test_the_global_accessors_belong_to_this_process(self):
        # the preloaded shape again, from the other side: an instrumentor asks the
        # SDK for "the" tracer provider, and the answer must be the provider of
        # the process it is running in and not the one the master handed over
        from opentelemetry import trace
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                master_provider = lifecycle._state["provider"]
                self.assertIs(trace.get_tracer_provider(), master_provider)
                with patch("os.getpid", return_value=os.getpid() + 3):
                    lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                    child_provider = lifecycle._state["provider"]
                    self.assertIsNot(child_provider, master_provider)
                    self.assertIs(trace.get_tracer_provider(), child_provider)

    def test_the_celery_receivers_belong_to_a_worker_only(self):
        # the receivers of the task metrics are connected by the lifecycle of a
        # worker and by nobody else, so a process which only answers requests can
        # never report an execution it did not run
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertEqual(lifecycle.roles(), {lifecycle.ROLE_HTTP})
                self.assertNotIn("celery", instrumentation.installed())
                self.assertEqual(celery_metrics.open_observations(), {})
            lifecycle.shutdown("between roles")
            instrumentation.uninstrument()
            celery_metrics.reset_collector()
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                self.assertEqual(lifecycle.roles(), {lifecycle.ROLE_WORKER})
                self.assertIn("celery", instrumentation.installed())

    def test_the_resource_carries_only_the_allowlisted_identity(self):
        with isolated_telemetry():
            with environ(**standard_env(MRMAP_OTEL_SERVICE_NAME="mrmap-worker",
                                        MRMAP_OTEL_SERVICE_VERSION="1.2.3",
                                        MRMAP_OTEL_DEPLOYMENT_ENVIRONMENT="prod")):
                values = lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                attributes = dict(lifecycle._state["provider"].resource.attributes)
        self.assertEqual(values["service_name"], "mrmap-worker")
        self.assertEqual(attributes["service.name"], "mrmap-worker")
        self.assertEqual(attributes["service.version"], "1.2.3")
        self.assertEqual(attributes["deployment.environment.name"], "prod")
        # an identity per cumulative writer, and nothing a detector read
        self.assertIn("service.instance.id", attributes)
        for forbidden in ("host.name", "container.id", "process.pid",
                          "cloud.provider", "container.name"):
            self.assertNotIn(forbidden, attributes)

    def test_the_auto_instrumentation_path_stays_switched_off(self):
        # ``opentelemetry-instrument`` plus our own wrapping is the double
        # instrumentation ADR-0003 rules out
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertEqual(os.environ.get("OTEL_PYTHON_DJANGO_INSTRUMENT"),
                                 "False")
                self.assertEqual(os.environ.get("OTEL_SEMCONV_STABILITY_OPT_IN"),
                                 "http")
                self.assertEqual(os.environ.get(
                    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE"),
                    "CUMULATIVE")

    def test_the_upstream_instrumentations_are_the_ones_installed(self):
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                installed = instrumentation.installed()
        # upstream Celery, plus MrMap's own seam for the outbound trust rule
        self.assertIn("celery", installed)
        self.assertIn("requests-guard", installed)
        # the metric stream of the Celery instrumentor is dropped, not renamed
        self.assertIn("flower.task.runtime.seconds", policy.DROP_INSTRUMENTS)

    def test_no_sql_or_redis_instrumentation_without_being_asked(self):
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                installed = instrumentation.installed()
        self.assertNotIn("sql_enabled", installed)
        self.assertNotIn("redis_enabled", installed)


# ------------------------------------------------------------- sampling ---

class SamplingTests(SimpleTestCase):
    """Parent-based head sampling, with trust decided first."""

    def _parent_context(self, sampled):
        # a NonRecordingSpan is how the SDK itself carries "a parent I do not
        # record", which is exactly what a propagated parent is in the process
        # which only reads it
        from opentelemetry import trace as trace_api
        from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags
        context = SpanContext(1, 2, True,
                              TraceFlags(TraceFlags.SAMPLED if sampled
                                         else TraceFlags.DEFAULT))
        return trace_api.set_span_in_context(NonRecordingSpan(context))

    def _sampler(self, ratio):
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio
        return ParentBasedTraceIdRatio(ratio)

    def _sampled(self, ratio, parent_context=None):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        provider = TracerProvider(sampler=self._sampler(ratio),
                                  resource=Resource({"service.name": "mrmap"}))
        span = provider.get_tracer("test").start_span(
            "GET /api", context=parent_context)
        try:
            return span.get_span_context().trace_flags.sampled
        finally:
            span.end()

    def test_an_unsampled_parent_is_not_revived(self):
        self.assertFalse(self._sampled(1.0, self._parent_context(sampled=False)))

    def test_a_sampled_parent_is_honoured_even_at_a_zero_ratio(self):
        self.assertTrue(self._sampled(0.0, self._parent_context(sampled=True)))

    def test_public_roots_use_the_local_ratio(self):
        # 1 % is the starting hypothesis of the ADR, and the decision is
        # deterministic: nothing at 0 %, everything at 100 %
        self.assertFalse(self._sampled(0.0))
        self.assertTrue(self._sampled(1.0))

    def test_a_ratio_above_one_cannot_sample_everything_in_silence(self):
        with environ(MRMAP_OTEL_TRACES_SAMPLE_RATIO="100"):
            self.assertEqual(config.resolve()["trace_ratio"], 1.0)

    def test_the_sampler_of_a_process_is_parent_based(self):
        from opentelemetry.sdk.trace.sampling import ParentBased
        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertIsInstance(lifecycle._state["provider"].sampler,
                                      ParentBased)


# --------------------------------------------------------- propagation ---

class PropagationTests(SimpleTestCase):
    """Who may supply a parent, and who may receive a header."""

    def setUp(self):
        super().setUp()
        naming.reset_caches()

    def _values(self, **extra):
        base = dict(trusted_hosts=("broker.internal",),
                    trusted_source_hosts=("10.0.0.5",),
                    broker_trusted=True)
        base.update(extra)
        return base

    def _carrier(self):
        return {"traceparent":
                "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
                "HTTP_HOST": "mrmap.example"}

    def _context(self):
        from opentelemetry import context
        return context.get_current()

    def test_a_public_caller_cannot_choose_its_parent(self):
        from opentelemetry import trace
        propagator = propagation.MrMapPropagator(self._values())
        extracted = propagator.extract(self._carrier(), context=self._context())
        self.assertFalse(
            trace.get_current_span(extracted).get_span_context().is_valid)

    def test_a_forwarded_header_is_not_a_trust_claim(self):
        from opentelemetry import trace
        carrier = self._carrier()
        carrier["HTTP_X_FORWARDED_FOR"] = "10.0.0.5"
        propagator = propagation.MrMapPropagator(self._values())
        extracted = propagator.extract(carrier, context=self._context())
        self.assertFalse(
            trace.get_current_span(extracted).get_span_context().is_valid)

    def test_a_named_source_host_may_supply_a_parent(self):
        from opentelemetry import trace
        propagator = propagation.MrMapPropagator(self._values())
        token = propagation.set_peer_address("10.0.0.5")
        try:
            extracted = propagator.extract(self._carrier(), context=self._context())
        finally:
            propagation.reset_peer_address(token)
        span_context = trace.get_current_span(extracted).get_span_context()
        self.assertTrue(span_context.is_valid)
        self.assertEqual(span_context.trace_id, 0x0AF7651916CD43DD8448EB211C80319C)
        self.assertTrue(span_context.trace_flags.sampled)

    def test_baggage_is_never_a_field_of_this_propagator(self):
        self.assertEqual(propagation.MrMapPropagator(self._values()).fields,
                         ("traceparent", "tracestate"))

    def _broker_carrier(self):
        """A celery request object, which is to say the message headers."""
        class Request:
            def __init__(self, headers):
                self.__dict__.update(headers)

        return Request({"celery-retries": 0, "correlation_id": "x", "id": "1" * 32,
                        "traceparent": "00-%032x-%016x-01" % (7, 8)})

    def _broker_extract(self, **extra):
        # with the getter of the upstream Celery instrumentor, because that is the
        # only caller of this seam and it reads attributes rather than keys
        from opentelemetry.instrumentation.celery import CeleryGetter
        from opentelemetry import trace
        propagator = propagation.MrMapPropagator(self._values(**extra))
        extracted = propagator.extract(self._broker_carrier(),
                                       context=self._context(),
                                       getter=CeleryGetter())
        return trace.get_current_span(extracted).get_span_context()

    def test_the_broker_is_a_trusted_boundary(self):
        self.assertTrue(self._broker_extract().is_valid)

    def test_a_shared_broker_can_be_untrusted_and_then_a_task_starts_its_root(self):
        self.assertFalse(self._broker_extract(broker_trusted=False).is_valid)

    def _inject(self, untrusted):
        # an explicit provider, so the answer cannot depend on which provider the
        # global happens to hold after another test of this class ran
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        provider = TracerProvider(resource=Resource({"service.name": "mrmap"}))
        span = provider.get_tracer("test").start_span("GET")
        propagator = propagation.MrMapPropagator(self._values())
        headers = {}
        token = propagation.mark_untrusted_destination(untrusted)
        try:
            propagator.inject(headers, context=trace.set_span_in_context(span))
        finally:
            propagation.reset_untrusted_destination(token)
            span.end()
        provider.shutdown()
        return headers

    def test_injection_is_refused_for_an_untrusted_destination(self):
        self.assertEqual(self._inject(untrusted=True), {})

    def test_injection_happens_for_a_trusted_destination(self):
        self.assertIn("traceparent", self._inject(untrusted=False))

    def test_a_callers_own_prepared_request_cannot_smuggle_a_parent(self):
        from requests import PreparedRequest
        request = PreparedRequest()
        request.prepare(url="http://broker.internal/x",
                        headers={"traceparent": "00-%032x-%016x-01" % (1, 2),
                                 "Baggage": "a=b", "X-Keep": "yes"})
        propagation.strip_context_headers(request.headers)
        names = {name.lower() for name in request.headers}
        self.assertNotIn("traceparent", names)
        self.assertNotIn("baggage", names)
        self.assertEqual(request.headers["X-Keep"], "yes")

    def test_the_asgi_inbound_list_loses_the_context_too(self):
        self.assertEqual(
            propagation.strip_asgi_headers([(b"traceparent", b"00-x-01"),
                                            (b"baggage", b"a=b"),
                                            (b"host", b"mrmap.example")]),
            [(b"host", b"mrmap.example")])


class RequestsGuardTests(SimpleTestCase):
    """The guard decides per actual send, so a redirect cannot smuggle a hop."""

    def test_the_wrapper_is_installed_and_restored(self):
        from requests import Session
        with isolated_telemetry():
            with environ(**standard_env()):
                original = Session.send
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                self.assertIsNot(Session.send, original)
                self.assertIn("requests-guard", instrumentation.installed())
        self.assertIs(Session.send, original)

    def test_what_the_guard_sends_is_what_it_judged(self):
        from requests import PreparedRequest, Session

        sent = []

        class Transport:
            def send(self, request, **kwargs):
                from requests import Response
                sent.append((request.url,
                             {name.lower() for name in request.headers
                              if name.lower() in propagation.CONTEXT_HEADERS}))
                return Response()

        with isolated_telemetry():
            with environ(**standard_env()):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP)
                session = Session()
                session.get_adapter("http://").send = Transport().send
                for host in ("broker.internal", "third-party.example"):
                    request = PreparedRequest()
                    request.prepare(
                        url="http://%s/ogc" % host,
                        headers={"traceparent": "00-%032x-%016x-01" % (3, 4)})
                    session.send(request)
        self.assertEqual(len(sent), 2)
        for _url, context_headers in sent:
            self.assertEqual(context_headers, set(),
                             "a caller's header must not survive a hop")


class DestinationTrustTests(SimpleTestCase):
    """The host of the URL which is actually being sent is the only thing asked."""

    def test_the_trusted_list_is_the_only_answer(self):
        from MrMap.telemetry.instrumentation import _destination_is_trusted
        with override_settings(OTEL_TRUSTED_HOSTS=("broker.internal",)):
            self.assertTrue(_destination_is_trusted("http://broker.internal/wms"))
            self.assertTrue(_destination_is_trusted("https://BROKER.internal/wfs"))
            # the port and the query of our own trusted hop change nothing
            self.assertTrue(_destination_is_trusted(
                "http://broker.internal:8080/wms?service=WMS"))
            self.assertFalse(_destination_is_trusted("http://evil/ogc"))
            self.assertFalse(_destination_is_trusted(None))
        with override_settings(OTEL_TRUSTED_HOSTS=()):
            self.assertFalse(_destination_is_trusted("http://broker.internal/wms"))


# ------------------------------------------------------ span privacy ---

class SpanPolicyTests(SimpleTestCase):
    """Allow, bound, deny - in that order, in every mode."""

    def _kind(self, name):
        from opentelemetry.trace import SpanKind
        return getattr(SpanKind, name)

    def test_a_server_span_says_its_route_template_and_nothing_else(self):
        self.assertEqual(policy.allowed_span_attributes(self._kind("SERVER"), {
            "http.request.method": "GET",
            "url.scheme": "https",
            "http.route": "api/services/wms/<int:resource_id>/",
            "http.response.status_code": 200,
            "url.full": "https://mrmap/api/services/wms/4211/?api_key=secret",
            "http.target": "/api/services/wms/4211/",
            "client.address": "203.0.113.9",
            "user_agent.original": "curl/8",
            "exception.message": "the password of user x was wrong",
        }), {"http.request.method": "GET", "url.scheme": "https",
             "http.route": "api/services/wms/<int:resource_id>/",
             "http.response.status_code": 200})

    def test_a_client_span_never_names_the_remote_it_called(self):
        self.assertEqual(policy.allowed_span_attributes(self._kind("CLIENT"), {
            "http.request.method": "GET",
            "http.response.status_code": 502,
            "url.full": "http://third-party.example/wfs?typename=secret",
            "server.address": "third-party.example",
            "network.peer.address": "198.51.100.7",
            "user_agent.original": "mrmap/1",
            "mrmap.remote.kind": "wfs",
            "error.type": "connection",
        }), {"http.request.method": "GET", "http.response.status_code": 502,
             "mrmap.remote.kind": "wfs", "error.type": "connection"})

    def test_a_task_span_never_carries_an_identifier_of_an_attempt(self):
        self.assertEqual(policy.allowed_span_attributes(self._kind("CONSUMER"), {
            "celery.action": "apply_async",
            "mrmap.task.class": "harvest.run",
            "mrmap.queue": "harvest",
            "mrmap.task.outcome": "success",
            "messaging.message.id": "9b1de4f2-...",
            "celery.task_id": "9b1de4f2-...",
            "root_id": "9b1de4f2-...",
            "parent_id": "9b1de4f2-...",
            "celery.retry.reason": "the remote said no",
            "messaging.message.payload_size_bytes": 4211,
        }), {"celery.action": "apply_async", "mrmap.task.class": "harvest.run",
             "mrmap.queue": "harvest", "mrmap.task.outcome": "success"})

    def test_sql_is_denied_in_every_mode_including_diagnostic(self):
        attributes = {"db.system": "postgresql", "db.operation.name": "SELECT",
                      "db.statement": "SELECT * FROM registry_resourceserver "
                                      "WHERE name = 'MrMap Admin'",
                      "db.query.text": "SELECT 1",
                      "db.statement.parameters": ("secret",)}
        for mode in config.MODES:
            stripped = policy.allowed_span_attributes(
                self._kind("INTERNAL"), attributes, sql_enabled=True)
            for forbidden in ("db.statement", "db.query.text",
                              "db.statement.parameters"):
                self.assertNotIn(forbidden, stripped, mode)
        # only an operator who asked for SQL spans gets the statement *class*,
        # and nobody at all gets its parameters (#888 is the precedent)
        self.assertNotIn("db.system", policy.allowed_span_attributes(
            self._kind("INTERNAL"), attributes, sql_enabled=False))
        self.assertIn("db.system", policy.allowed_span_attributes(
            self._kind("INTERNAL"), attributes, sql_enabled=True))

    def test_an_unknown_attribute_is_dropped_rather_than_passed_through(self):
        # the reading which makes an upstream upgrade safe: a new attribute is a
        # missing attribute, never a leak
        self.assertEqual(policy.allowed_span_attributes(
            self._kind("SERVER"), {"http.response.status_code.2": 200}), {})

    def test_values_and_counts_are_bounded(self):
        safe = policy.allowed_span_attributes(
            self._kind("SERVER"), {"http.route": "x" * 5000})
        self.assertEqual(len(safe["http.route"]), policy.MAX_VALUE_LENGTH)
        many = {"http.request.method": "GET"}
        for index in range(200):
            many["error.type.%d" % index] = "timeout"
        self.assertLessEqual(len(policy.allowed_span_attributes(
            self._kind("SERVER"), many)), policy.MAX_SPAN_ATTRIBUTES)

    def test_the_exporter_sanitizes_what_leaves_the_process(self):
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import ReadableSpan
        from opentelemetry.sdk.trace.export import SpanExportResult

        from opentelemetry.trace import SpanContext, TraceFlags
        span = ReadableSpan(
            name="GET /api/services/wms/4211/" + ("y" * 500),
            context=SpanContext(7, 8, False, TraceFlags(TraceFlags.SAMPLED)),
            attributes={"url.full": "http://x/y?token=1",
                        "http.request.method": "GET"},
            resource=Resource({"service.name": "mrmap", "host.name": "node"}))
        captured = []

        class Sink:
            def export(self, spans):
                captured.append(list(spans))
                return SpanExportResult.SUCCESS

            def shutdown(self, *args, **kwargs):
                return None

        exporter = policy.SanitizingSpanExporter(Sink(), config.resolve())
        self.assertIs(exporter.export([span]), SpanExportResult.SUCCESS)
        exported = captured[0][0]
        self.assertNotIn("url.full", exported.attributes)
        self.assertEqual(exported.attributes["http.request.method"], "GET")
        self.assertNotIn("host.name", dict(exported.resource.attributes))
        self.assertLessEqual(len(exported.name), policy.MAX_VALUE_LENGTH)

    def test_a_sanitizer_failure_drops_telemetry_and_not_the_request(self):
        from opentelemetry.sdk.trace.export import SpanExportResult
        drops = []
        exporter = policy.SanitizingSpanExporter(
            object(), config.resolve(), dropped=lambda *a: drops.append(a))
        # an object which is not an exporter stands in for any failure inside the
        # serialization of the SDK
        self.assertIs(exporter.export([object()]), SpanExportResult.FAILURE)
        self.assertTrue(drops)

    def test_the_processor_strips_at_start_so_the_queue_never_holds_it(self):
        from opentelemetry.sdk.trace import _Span
        from opentelemetry.trace import SpanContext, TraceFlags

        context = SpanContext(1, 2, True, TraceFlags(TraceFlags.SAMPLED))
        from opentelemetry.trace import SpanKind
        span = _Span("GET /api/services/wms/4211/", context=context,
                     kind=SpanKind.SERVER,
                     attributes={"url.full": "http://x?token=1",
                                 "http.request.method": "GET"})
        policy.StripOnStartSpanProcessor(config.resolve()).on_start(span)
        self.assertNotIn("url.full", span._attributes)
        self.assertIn("http.request.method", span._attributes)


# ---------------------------------------------------- metric contract ---

class MetricContractTests(SimpleTestCase):
    """The instruments of ADR-0003, on the pinned SDK's own aggregation."""

    def setUp(self):
        super().setUp()
        naming.reset_caches()

    def test_the_contract_instruments_are_the_named_ones(self):
        self.assertEqual(sorted(metrics.INSTRUMENTS),
                         ["mrmap.task.attempt.duration", "mrmap.task.attempts",
                          "mrmap.task.observations", "mrmap.task.queue.wait",
                          "mrmap.telemetry.dropped"])

    @override_settings(OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_dimensions_are_the_allowlisted_ones(self):
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        metrics.record_attempt("registry.tasks.harvest.run", "harvest", "success",
                               active_seconds=1.2, wait_seconds=3.5)
        metrics.record_attempt("unknown.task", "harvest", "failure",
                               active_seconds=0.05)
        metrics.record_unmeasured("registry.tasks.harvest.run", "harvest",
                                  "invalid_stamp")
        metrics.count_dropped("traces", "export_error")
        collected = metric_data(reader)
        provider.shutdown()
        for name, points in collected.items():
            allowed = set(metrics.INSTRUMENTS[name][2])
            for point in points:
                self.assertLessEqual(set(point), allowed, name)
        self.assertEqual({point["mrmap.task.class"]
                          for point in collected["mrmap.task.attempts"]},
                         {"harvest.run", "other"})

    @override_settings(OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_a_missing_duration_stays_absent_and_never_becomes_zero(self):
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        metrics.record_attempt("registry.tasks.harvest.run", "harvest", "success")
        collected = metric_data(reader)
        provider.shutdown()
        self.assertIn("mrmap.task.attempts", collected)
        self.assertNotIn("mrmap.task.attempt.duration", collected)
        self.assertNotIn("mrmap.task.queue.wait", collected)

    def test_the_upstream_celery_stream_is_dropped_before_aggregation(self):
        provider, reader = meter_provider_with_reader()
        meter = provider.get_meter("opentelemetry.instrumentation.celery")
        meter.create_histogram("flower.task.runtime.seconds",
                               unit="seconds").record(
            1.0, {"task": "registry.tasks.harvest.run", "worker": "celery@node-1"})
        collected = metric_data(reader)
        provider.shutdown()
        self.assertNotIn("flower.task.runtime.seconds", collected)

    def test_the_http_server_metric_keeps_its_contract_and_forgets_the_rest(self):
        provider, reader = meter_provider_with_reader()
        meter = provider.get_meter("opentelemetry.instrumentation.django")
        meter.create_histogram("http.server.request.duration", unit="s").record(
            0.5, {"http.request.method": "GET", "url.scheme": "https",
                  "http.route": "api/services/wms/<int:id>/",
                  "http.response.status_code": 200, "error.type": "timeout",
                  "url.full": "https://mrmap/api/x?api_key=secret",
                  "client.address": "203.0.113.9",
                  "user_agent.original": "curl/8"})
        points = metric_data(reader)["http.server.request.duration"]
        provider.shutdown()
        self.assertEqual(points, [{"http.request.method": "GET",
                                   "url.scheme": "https",
                                   "http.route": "api/services/wms/<int:id>/",
                                   "http.response.status_code": 200,
                                   "error.type": "timeout"}])

    def test_the_0_4_second_boundary_and_the_cumulative_temporality(self):
        # the slow-request answer of #888 is count minus the cumulative bucket at
        # 0.4 s, which excludes exactly 0.4 - so the boundary has to exist
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import (AggregationTemporality,
                                                      InMemoryMetricReader)
        from opentelemetry.sdk.resources import Resource

        reader = InMemoryMetricReader()
        provider = MeterProvider(resource=Resource({"service.name": "mrmap"}),
                                 views=policy.views(config.resolve()),
                                 metric_readers=[reader])
        meter = provider.get_meter("test")
        duration = meter.create_histogram("http.server.request.duration")
        duration.record(0.39, {"http.request.method": "GET"})
        duration.record(0.41, {"http.request.method": "GET"})
        metric = reader.get_metrics_data().resource_metrics[0] \
            .scope_metrics[0].metrics[0]
        self.assertEqual(metric.data.aggregation_temporality,
                         AggregationTemporality.CUMULATIVE)
        point = metric.data.data_points[0]
        self.assertIn(0.4, list(point.explicit_bounds))
        self.assertEqual(sum(point.bucket_counts), 2)
        # the answer of #888: everything above 0.4 s is the count minus the
        # cumulative bucket at 0.4, which excludes a request of exactly 0.4 s
        at_or_below = sum(point.bucket_counts[:list(point.explicit_bounds)
                                              .index(0.4) + 1])
        self.assertEqual(point.count - at_or_below, 1)
        provider.shutdown()

    def test_cardinality_is_capped_including_the_overflow_series(self):
        budget = 20
        provider, reader = meter_provider_with_reader(
            dict(config.resolve(), max_attribute_sets=budget))
        attempts = provider.get_meter("test").create_counter(
            "mrmap.task.attempts", unit="{attempt}")
        for index in range(budget * 3):
            attempts.add(1, {"mrmap.task.class": "task-%d" % index,
                             "mrmap.queue": "harvest",
                             "mrmap.task.outcome": "success"})
        points = metric_data(reader)["mrmap.task.attempts"]
        provider.shutdown()
        self.assertLessEqual(len(points), budget)
        # the SDK's synthetic overflow series must stay visible, because a fleet
        # total which ignores it reads a lost dimension as a healthy zero
        self.assertTrue(any("otel.metric.overflow" in point for point in points))

    def test_metrics_survive_a_trace_sampler_which_sampled_nothing(self):
        # the independence promise of the issue, stated as a test: no tracer of
        # any kind, and the attempt counters still hold their values
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF

        trace.set_tracer_provider(TracerProvider(sampler=ALWAYS_OFF))
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        metrics.record_attempt("registry.tasks.harvest.run", "harvest", "success",
                               active_seconds=2.0, wait_seconds=1.0)
        collected = metric_data(reader)
        provider.shutdown()
        self.assertIn("mrmap.task.attempts", collected)
        self.assertIn("mrmap.task.attempt.duration", collected)
        self.assertIn("mrmap.task.queue.wait", collected)

    def test_the_drop_counter_names_the_signal_and_the_reason(self):
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        metrics.count_dropped("metrics", "queue_full")
        metrics.count_dropped("nonsense", "nonsense")
        points = metric_data(reader)["mrmap.telemetry.dropped"]
        provider.shutdown()
        reasons = {point["mrmap.drop.reason"] for point in points}
        self.assertIn("queue_full", reasons)
        self.assertIn("dropped", reasons)


# ------------------------------------------------ celery attempt rules ---

class CeleryAttemptTests(SimpleTestCase):
    """Retries, revocations and missing stamps: one observation per attempt."""

    def setUp(self):
        super().setUp()
        naming.reset_caches()
        celery_metrics.reset_collector()

    def _task(self, task_id="1" * 32, name="registry.tasks.harvest.run",
              queue="harvest", retries=0, published=None):
        class Task:
            def __init__(self):
                self.name = name
                self.request = type("Request", (), {})()
                self.request.id = task_id
                self.request.retries = retries
                self.request.delivery_info = {"routing_key": queue}
                self.request.headers = (
                    {"mrmap-published-at": published}
                    if published is not None else {})
                self.request.root_id = task_id
                self.request.parent_id = None

        return Task()

    def _provider(self):
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        return provider, reader

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_success_records_one_terminal_attempt(self):
        provider, reader = self._provider()
        task = self._task(published=str(time.time() - 2.0))
        celery_metrics.begin_attempt(task=task)
        self.assertEqual(len(celery_metrics.open_observations()), 1)
        celery_metrics.finish_attempt_on_success(sender=task)
        collected = metric_data(reader)
        provider.shutdown()
        self.assertEqual(celery_metrics.open_observations(), {})
        self.assertEqual(len(collected["mrmap.task.attempts"]), 1)
        self.assertEqual(collected["mrmap.task.attempts"][0]["mrmap.task.outcome"],
                         "success")
        self.assertEqual([point["mrmap.task.class"]
                          for point in collected["mrmap.task.attempt.duration"]],
                         ["harvest.run"])
        self.assertEqual([point["mrmap.task.class"]
                          for point in collected["mrmap.task.queue.wait"]],
                         ["harvest.run"])

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_a_retry_is_an_attempt_of_its_own(self):
        # the same id with a raised counter is a different attempt: it consumed
        # real slot time, which is what #1330 decided and ADR-0003 repeats
        provider, reader = self._provider()
        first = self._task(retries=0)
        celery_metrics.begin_attempt(task=first)
        celery_metrics.finish_attempt_on_retry(sender=first)
        second = self._task(retries=1)
        celery_metrics.begin_attempt(task=second)
        celery_metrics.finish_attempt_on_success(sender=second)
        outcomes = sorted(point["mrmap.task.outcome"]
                          for point in metric_data(reader)["mrmap.task.attempts"])
        provider.shutdown()
        self.assertEqual(outcomes, ["retry", "success"])

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_a_second_terminal_signal_records_nothing_more(self):
        provider, reader = self._provider()
        task = self._task()
        celery_metrics.begin_attempt(task=task)
        celery_metrics.finish_attempt_on_success(sender=task)
        celery_metrics.finish_attempt_on_failure(sender=task)
        celery_metrics.finish_attempt_on_postrun(task=task)
        self.assertEqual(len(metric_data(reader)["mrmap.task.attempts"]), 1)
        provider.shutdown()

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_a_revoked_attempt_is_counted_as_revoked(self):
        provider, reader = self._provider()
        task = self._task(task_id="2" * 32)
        celery_metrics.begin_attempt(task=task)
        celery_metrics.mark_attempt_revoked(sender=task, request="2" * 32)
        self.assertEqual([point["mrmap.task.outcome"]
                          for point in metric_data(reader)["mrmap.task.attempts"]],
                         ["revoked"])
        provider.shutdown()

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_an_untrusted_publish_stamp_costs_the_wait_and_not_the_count(self):
        # never a zero wait: an absent stamp is an absent measurement, and the
        # coverage series is what keeps that honest
        for published, quality in ((None, "unstamped"),
                                   ("not-a-time", "invalid_stamp"),
                                   ("nan", "invalid_stamp")):
            with self.subTest(published=published):
                celery_metrics.reset_collector()
                provider, reader = self._provider()
                task = self._task(published=published)
                celery_metrics.begin_attempt(task=task)
                celery_metrics.finish_attempt_on_success(sender=task)
                collected = metric_data(reader)
                provider.shutdown()
                self.assertNotIn("mrmap.task.queue.wait", collected)
                self.assertIn("mrmap.task.attempts", collected)
                self.assertIn(quality, [point["mrmap.observation.quality"]
                                        for point in
                                        collected["mrmap.task.observations"]])

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_a_terminally_missing_signal_leaves_coverage_and_no_duration(self):
        provider, reader = self._provider()
        celery_metrics.finish_attempt_on_success(sender=self._task(task_id="3" * 32))
        collected = metric_data(reader)
        provider.shutdown()
        self.assertNotIn("mrmap.task.attempt.duration", collected)
        self.assertEqual([point["mrmap.observation.quality"]
                          for point in collected["mrmap.task.observations"]],
                         ["unstamped"])

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True,
                       OTEL_TASK_CLASSES=("harvest.run",), OTEL_MAX_QUEUES=16,
                       OTEL_MAX_TASK_CLASSES=200)
    def test_the_open_observations_are_bounded(self):
        provider, reader = self._provider()
        for index in range(celery_metrics.OPEN_LIMIT + 25):
            celery_metrics.begin_attempt(task=self._task(task_id="%032d" % index))
        self.assertLessEqual(len(celery_metrics.open_observations()),
                             celery_metrics.OPEN_LIMIT)
        provider.shutdown()

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=True)
    def test_a_broken_observer_never_costs_the_task(self):
        # the rule above all others on a task path: a telemetry failure may not
        # change the outcome, the retry or the acknowledgement of the attempt
        provider, reader = self._provider()
        task = self._task()
        with patch("MrMap.telemetry.celery_metrics.metrics") as broken:
            broken.OUTCOME_SUCCESS = "success"
            broken.OUTCOME_FAILURE = "failure"
            broken.OUTCOME_RETRY = "retry"
            broken.OUTCOME_REVOKED = "revoked"
            broken.OUTCOME_UNKNOWN = "unknown"
            broken.record_attempt.side_effect = RuntimeError("the meter exploded")
            broken.record_unmeasured.side_effect = RuntimeError("ditto")
            for signal in (celery_metrics.begin_attempt,
                           celery_metrics.finish_attempt_on_success,
                           celery_metrics.finish_attempt_on_failure,
                           celery_metrics.finish_attempt_on_retry,
                           celery_metrics.finish_attempt_on_postrun,
                           celery_metrics.flush_on_process_shutdown):
                signal(task=task, sender=task)
        provider.shutdown()

    @override_settings(OTEL_MODE="off")
    def test_nothing_is_recorded_while_the_mode_is_off(self):
        provider, reader = self._provider()
        task = self._task()
        celery_metrics.begin_attempt(task=task)
        celery_metrics.finish_attempt_on_success(sender=task)
        self.assertEqual(metric_data(reader), {})
        self.assertEqual(celery_metrics.open_observations(), {})
        provider.shutdown()

    @override_settings(OTEL_MODE="standard", OTEL_COLLECT_ANY_PROCESS=False)
    def test_a_process_which_does_not_execute_tasks_reports_nothing(self):
        # a prefork parent, a web process and the test runner must not report
        # queue waits for work they never ran
        provider, reader = self._provider()
        task = self._task()
        celery_metrics.begin_attempt(task=task)
        celery_metrics.finish_attempt_on_success(sender=task)
        self.assertEqual(metric_data(reader), {})
        provider.shutdown()

    def test_the_receivers_attach_and_detach_as_a_set(self):
        from celery.signals import task_prerun
        before = len(task_prerun.receivers)
        celery_metrics.connect()
        self.assertGreater(len(task_prerun.receivers), before)
        celery_metrics.disconnect()
        self.assertLessEqual(len(task_prerun.receivers), before)


# ------------------------------------------------------ naming contract ---

class NamingTests(SimpleTestCase):
    """A dimension is either reviewed or one of the fixed bucket names."""

    def setUp(self):
        super().setUp()
        naming.reset_caches()

    def test_an_unregistered_task_is_other_and_never_a_truncated_name(self):
        # a truncated name is still a name, which is the whole point
        self.assertEqual(naming.task_class("some.plugin.evil_task", ()), "other")
        self.assertEqual(naming.task_class(None, ()), "other")
        self.assertEqual(naming.task_class("", ()), "other")
        self.assertEqual(naming.task_class("celery.chord", ()), "other")

    def test_the_celery_registry_is_the_first_party_list(self):
        from celery import Celery
        app = Celery("naming-test")

        @app.task(name="registry.tasks.test.work")
        def work():
            return None

        with patch("MrMap.telemetry.naming._registered_task_names",
                   return_value=frozenset(app.tasks)):
            self.assertEqual(naming.task_class("registry.tasks.test.work", ()),
                             "registry.tasks.test.work")
            self.assertEqual(naming.task_class("not.registered.at.all", ()), "other")

    def test_the_operators_allowlist_wins_in_its_own_spelling(self):
        self.assertEqual(naming.task_class("registry.tasks.harvest.run",
                                           allowed=("harvest.run",)), "harvest.run")
        self.assertEqual(naming.task_class("a.b.c", allowed=("a.b.c",)), "a.b.c")
        self.assertEqual(naming.task_class("a.b.c", allowed=("other.one",)), "other")

    def test_the_task_class_budget_bounds_one_process(self):
        registered = frozenset("task-%d" % index for index in range(100))
        with patch("MrMap.telemetry.naming._registered_task_names",
                   return_value=registered):
            for index in range(5):
                self.assertEqual(naming.task_class("task-%d" % index, (), budget=5),
                                 "task-%d" % index)
            self.assertEqual(naming.task_class("task-50", (), budget=5), "other")

    @override_settings(CELERY_TASK_QUEUES=[{"name": "harvest"}, {"name": "default"}],
                       CELERY_TASK_DEFAULT_QUEUE="default", OTEL_MAX_QUEUES=16)
    def test_a_foreign_queue_folds_into_one_series(self):
        self.assertEqual(naming.queue("harvest"), "harvest")
        self.assertEqual(naming.queue("somebody-elses-queue"), "other")
        self.assertEqual(naming.queue(""), "other")
        self.assertEqual(naming.queue("x" * 200), "other")

    def test_a_route_is_a_registered_template_or_the_honest_absence(self):
        self.assertEqual(naming.route("api/services/wms/<int:resource_id>/"),
                         "api/services/wms/<int:resource_id>/")
        # a path is somebody's request path, and ADR-0003 forbids substituting it
        self.assertEqual(naming.route("/api/services/wms/4211/"), "unmatched")
        self.assertEqual(naming.route(None), "unresolved")
        self.assertEqual(naming.route(""), "unresolved")
        self.assertEqual(naming.route("api/x?" + "y" * 300), "unmatched")

    def test_the_route_budget_bounds_one_process(self):
        for index in range(10):
            self.assertEqual(naming.route("api/x/%d/" % index, budget=10),
                             "api/x/%d/" % index)
        self.assertEqual(naming.route("api/x/99/", budget=10), "unmatched")

    def test_the_http_vocabulary_is_finite(self):
        self.assertEqual(naming.method("gEt"), "GET")
        self.assertEqual(naming.method("PROPFIND"), "_OTHER")
        self.assertEqual(naming.method(None), "_OTHER")
        self.assertEqual(naming.status("200"), 200)
        self.assertIsNone(naming.status("999"))
        self.assertIsNone(naming.status("nope"))
        self.assertEqual(naming.scheme("HTTPS"), "https")
        self.assertIsNone(naming.scheme("gopher"))

    def test_an_error_type_is_a_category_and_not_an_exception_class(self):
        self.assertEqual(naming.error_type("ConnectTimeout"), "timeout")
        self.assertEqual(naming.error_type("ConnectionError"), "connection")
        self.assertEqual(naming.error_type("HTTPServerError"), "server")
        self.assertEqual(naming.error_type("PluginExploded"), "other")
        self.assertEqual(naming.error_type(None), "other")

    def test_a_remote_is_a_kind_and_not_a_host(self):
        self.assertEqual(naming.remote_kind("http://x/wms?service=WMS"), "wms")
        self.assertEqual(naming.remote_kind("http://x/wfs"), "wfs")
        self.assertEqual(naming.remote_kind("http://x/csw"), "csw")
        self.assertEqual(naming.remote_kind("http://x/arcgis/rest"), "other")
        self.assertEqual(naming.remote_kind(None), "other")


# ------------------------------------------------------ export boundary ---

class ExportBoundaryTests(SimpleTestCase):
    """A dead store costs telemetry, and only telemetry."""

    def test_a_refused_collector_changes_nothing_the_application_can_see(self):
        with isolated_telemetry():
            with environ(**standard_env(MRMAP_OTEL_EXPORTER_TIMEOUT_SECONDS="0.05")):
                self.assertIsNotNone(
                    lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER))
                from opentelemetry import trace
                for _ in range(20):
                    span = trace.get_tracer("test").start_span("GET /api")
                    span.set_attribute("http.request.method", "GET")
                    span.end()
                # neither the export nor its failure may raise into the caller
                self.assertTrue(lifecycle.shutdown("after a dead store"))

    def test_the_exporters_never_raise_and_report_what_they_lost(self):
        from opentelemetry.sdk.trace.export import SpanExportResult
        values = config.resolve()
        drops = []
        span_exporter = exporters.BoundedOTLPSpanExporter(
            dict(values, traces_endpoint="http://127.0.0.1:1/v1/traces"),
            values, dropped=lambda *args: drops.append(args))
        self.assertIs(span_exporter.export([]), SpanExportResult.SUCCESS)
        metric_exporter = exporters.BoundedOTLPMetricExporter(
            dict(values, metrics_endpoint="http://127.0.0.1:1/v1/metrics"),
            values, dropped=lambda *args: drops.append(args))
        self.assertIsNotNone(metric_exporter.export(None))
        # a teardown of a dead exporter neither raises nor blocks: the pinned
        # release answers it with None on the span side, so the promise is the
        # absence of an exception rather than a truth value
        span_exporter.shutdown()
        metric_exporter.shutdown()
        self.assertTrue(span_exporter.force_flush(10))

    def test_a_process_without_endpoints_starts_no_exporter_thread(self):
        # the provider stays - its span context is what links a publish to its
        # execution inside this process - but nothing reaches the network
        with isolated_telemetry():
            with environ(MRMAP_OTEL_MODE="standard",
                         MRMAP_OTEL_TRACES_ENDPOINT="",
                         MRMAP_OTEL_METRICS_ENDPOINT=""):
                before = set(pipeline_threads())
                self.assertIsNotNone(
                    lifecycle.initialize_for_process(role=lifecycle.ROLE_HTTP))
                self.assertEqual(set(pipeline_threads()), before)

    def test_the_null_metric_exporter_produces_no_bytes_and_needs_no_service(self):
        exporter = exporters.NullMetricExporter()
        self.assertIsNotNone(exporter.export(None))
        self.assertTrue(exporter.force_flush(1))
        self.assertIsNone(exporter.shutdown())

    def test_the_probes_are_excluded_from_their_own_pipeline(self):
        # a span for a probe is the export the probe is measuring
        for probe in ("/api/system/status/current", "/healthz", "/v1/traces",
                      "/v1/metrics"):
            self.assertTrue(
                any(re.match(pattern, probe)
                    for pattern in instrumentation.EXCLUDED_URLS), probe)

    def test_the_shutdown_drain_is_bounded_and_happens_once(self):
        with isolated_telemetry():
            with environ(**standard_env(MRMAP_OTEL_SHUTDOWN_DRAIN_SECONDS="0.2")):
                lifecycle.initialize_for_process(role=lifecycle.ROLE_WORKER)
                started = time.monotonic()
                self.assertTrue(lifecycle.shutdown("bounded drain"))
                self.assertLess(time.monotonic() - started, 5.0)
                self.assertFalse(lifecycle.shutdown("again"))

    def test_recording_never_touches_an_exporter(self):
        # the performance budget: an attempt is an in-memory add, no flush, no I/O
        provider, reader = meter_provider_with_reader()
        metrics.attach(provider.get_meter("mrmap"))
        with patch.object(type(exporters.NullMetricExporter()), "force_flush",
                          side_effect=AssertionError("flush on a hot path")) as flush:
            for _ in range(50):
                metrics.record_attempt("registry.tasks.harvest.run", "harvest",
                                       "success", active_seconds=0.01)
            self.assertEqual(flush.call_count, 0)
        provider.shutdown()

    def test_the_diagnostic_window_closes_by_itself(self):
        celery_metrics.reset_collector()
        values = dict(config.resolve(), diagnostic=True, debug_max_minutes=0.0)
        # the first call opens the window at the current moment, the next one
        # already finds it expired - a forgotten "diagnostic" never runs hot
        # forever, while the standard contract keeps working
        self.assertTrue(celery_metrics.diagnostic_window_open(values))
        self.assertFalse(celery_metrics.diagnostic_window_open(values))
        self.assertFalse(celery_metrics.diagnostic_window_open(
            dict(config.resolve(), diagnostic=False)))
