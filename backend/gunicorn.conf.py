"""The Gunicorn hooks of the optional OpenTelemetry integration (#1779).

Gunicorn loads a file of this name from its working directory automatically, and
the working directory of the application image is ``/opt/mrmap``
(``docker/backend/alpine.Dockerfile``) - so the two servers of
``.bash_scripts/startup.sh`` and ``startup_ws.sh`` get these hooks without either
script naming the file, and a third way of starting gunicorn gets them too.

One hook matters: :func:`post_fork`. It is the point where a worker process exists
and has not served a request yet, which is the only correct place to create the
SDK of that worker - a provider created in the master would hand every child a
copy of an exporter thread that does not exist in it. With ``GUNICORN_PRELOAD`` on
the master imported the application first, and the pid check of
:func:`MrMap.telemetry.lifecycle.initialize_for_process` is what makes the child
replace rather than inherit. With preload off the master created nothing and the
same call simply creates it here.

The hook never raises: a deployment whose telemetry is broken serves its requests
without telemetry, because observability is not allowed to be a runtime dependency
(epic #1775).
"""

import atexit

from MrMap.telemetry import lifecycle


def _role_of(cfg):
    """Which of the two servers of the container this worker belongs to.

    ``startup.sh`` runs ``gthread`` for HTTP and ``startup_ws.sh`` runs the uvicorn
    worker class for the websockets (#1032); the roles decide which instrumentors
    are installed, and a websocket worker is not an HTTP request pipeline.
    """
    worker_class = str(getattr(cfg, "worker_class", "") or "").lower()
    if "uvicorn" in worker_class or "asgi" in worker_class:
        return lifecycle.ROLE_WS
    return lifecycle.ROLE_HTTP


def post_fork(server, worker):
    """Create the telemetry of this worker, once, after the fork."""
    if not lifecycle.is_enabled():
        # off means off: no provider, no thread, no atexit hook, no DNS lookup
        return
    try:
        values = lifecycle.initialize_for_process(role=_role_of(worker.cfg))
    except Exception:  # pragma: no cover - lifecycle already guards itself
        server.log.warning("opentelemetry: worker telemetry unavailable; "
                           "serving without it (#1779).")
        return
    if values is None:
        return
    # one bounded drain when this worker exits; a hard kill loses the buffer,
    # which the drop counters of the collector exist to make visible
    atexit.register(lifecycle.shutdown, "gunicorn worker exit")
    server.log.info("opentelemetry: %s", lifecycle.describe())
