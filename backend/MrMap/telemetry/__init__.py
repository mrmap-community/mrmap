"""The optional OpenTelemetry integration of MrMap (#1779, epic #1775).

Three questions decide everything in this package, and each has its own module:

*   **is the mode on at all** - :mod:`MrMap.telemetry.config`. ``off`` (the
    shipped default) must cost nothing: no instrumentor is patched, no provider
    is created, no exporter thread starts, no DNS lookup happens and no
    telemetry service is required to boot the application.
*   **what may leave the process** - :mod:`MrMap.telemetry.policy`. The allowlist
    is applied *before* aggregation (metric views) and *before* export (span
    processor), never as an export-time filter over data already collected.
*   **who may talk to the pipeline** - :mod:`MrMap.telemetry.propagation`.
    Public ingress never supplies a trace parent, and nothing leaving towards a
    third-party OGC endpoint carries a trace header.

The lifecycle - initialize exactly once per process, after the fork, and shut the
SDK's own threads down again - is :mod:`MrMap.telemetry.lifecycle`. It is the
module the Gunicorn, ASGI and Celery entry points call; it refuses to run twice in
one process and does nothing at all while the mode is ``off``.

ADR-0003 (``docs/architecture/decisions/``) is the contract this implements;
``docs/source/development/observability-tracing.rst`` is the operator-facing
version of the same rules.
"""

from MrMap.telemetry.lifecycle import (initialized, initialize_for_process,
                                       is_enabled, shutdown)

__all__ = ["initialized", "initialize_for_process", "is_enabled", "shutdown"]
