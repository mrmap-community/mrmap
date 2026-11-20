# The process shape of the web tier (#1617, epic #1612).
#
# Sourced by startup.sh and startup_ws.sh, and executed by
# scripts/test_http_process_bench.py in a bare `sh` - so this file must stay
# pure environment arithmetic: no venv, no python, no absolute paths. The two
# servers read the resolved values it exports; keeping the resolution here and
# not in the compose file gives one source of truth for the shape a container
# boots with, whether it was started by compose, by `docker run` or by a test.
#
# Inputs (all optional; empty counts as unset, so the compose passthrough of
# an unset variable lands on the defaults below):
#   GUNICORN_WORKERS, GUNICORN_THREADS, GUNICORN_WS_WORKERS - explicit values
#       always win over the profile defaults.
#   MRMAP_LOW_MEMORY  - a deployment that trades web-tier throughput for its
#       memory reservation: one HTTP worker with a shallow thread queue
#       instead of four with a deep one. Every worker process carries its own
#       copy of the imports and its own database pool (settings' min_size),
#       so the worker count is the multiplier of the HTTP tier's reservation;
#       the threads are its maximum of concurrently open requests.
#   GUNICORN_PRELOAD  - import the application once in the gunicorn master and
#       let the HTTP workers fork it, so the pages of the imports are shared
#       copy-on-write. Off by default: the fork-safety audit and the measured
#       trade are in docs/source/development/http-process-profiles.rst. The
#       websocket server is deliberately not preloaded - it runs one worker
#       anyway (there is nothing to share) and the acceptance of #1617 names
#       stuck websockets as the failure mode to avoid.
#
# Outputs: GUNICORN_WORKERS, GUNICORN_THREADS, GUNICORN_WS_WORKERS (exported,
# always a number), and GUNICORN_PRELOAD_FLAG ("" or "--preload").

mrm_process_is_on() {
    case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
        1|true|yes|on) return 0 ;;
        *) return 1 ;;
    esac
}

if mrm_process_is_on "${MRMAP_LOW_MEMORY:-}"; then
    _mrm_default_workers=1
    _mrm_default_threads=2
else
    # the shipped production shape: the reading behind 4/4 is in
    # docs/source/development/environment.rst (#1032); selecting the mode
    # never reduces this default (#1617's acceptance)
    _mrm_default_workers=4
    _mrm_default_threads=4
fi

export GUNICORN_WORKERS="${GUNICORN_WORKERS:-$_mrm_default_workers}"
export GUNICORN_THREADS="${GUNICORN_THREADS:-$_mrm_default_threads}"
# open websockets are idle and I/O bound; one event loop carries a deployment
export GUNICORN_WS_WORKERS="${GUNICORN_WS_WORKERS:-1}"

GUNICORN_PRELOAD_FLAG=""
if mrm_process_is_on "${GUNICORN_PRELOAD:-}"; then
    GUNICORN_PRELOAD_FLAG="--preload"
fi
export GUNICORN_PRELOAD_FLAG

unset _mrm_default_workers _mrm_default_threads
