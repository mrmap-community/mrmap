#!/bin/sh
source /opt/venv/bin/activate

# Two servers, because the two kinds of request this container answers want
# opposite things of their worker class (#1032).
#
# Every view of MrMap is sync. Under an ASGI worker the view therefore runs on
# threads off the event loop while that same loop keeps the sockets of the
# worker - one GIL for the two of them - and the measured cost is paid twice: the
# view itself is slower, and its neighbours wait for the loop. Measured on this
# application behind a 4-core quota, 4 workers, a burst of 8 `/api/schema` builds
# (~2.4 s of building each) and ten cheap unrouted requests beside them: the
# uvicorn worker class used 1.8 - 2.2 of the 4 cores, one build alone took 2.9 s
# and a cheap neighbour which answers in 5 ms on an idle server waited 181 - 233
# ms. The same application under `gthread` took 2.7 - 3.4 cores, 2.4 - 2.5 s per
# build and 41 - 95 ms for that neighbour. Which of the four processes burned
# that work is the other half of the reading: 18.4 / 10.5 / 7.7 / 4.5 CPU seconds
# per worker under the uvicorn class of the same burst, 10.2 / 8.8 / 8.5 / 8.2
# under gthread.
#
# `--threads` is the queueing depth of a worker and not a promise of cores: CPU
# bound views parallelize per *process*, because the interpreter serves one of
# them at a time, and a request which arrives at a worker whose threads are all
# taken waits behind the ones already in it. Both sides of that are measured at
# 4 workers and the same burst: 1 thread per worker gave the most cores (3.8) and
# a cheap peer at 4.1 s, 8 threads gave 2.1 - 3.4 cores and a peer at 45 - 95 ms.
# 4 is the shipped middle, and GUNICORN_WORKERS is the knob for cores. The whole
# reading is in docs/source/development/environment.rst.

# The websockets go first, in the background, so that the HTTP server below can
# stay PID 1 and own the exit of the container the way it did before.
/opt/mrmap/.bash_scripts/startup_ws.sh &
WS_PID=$!

# Fail the boot rather than run a container whose /ws is quietly dead: gunicorn
# restarts the workers of a master, but nothing restarts a master which exited at
# startup, and PID 1 is the other server.
attempt=1
while ! python -c "import socket; socket.create_connection(('127.0.0.1', 8002), 2).close()" 2>/dev/null; do
    if ! kill -0 $WS_PID 2>/dev/null; then
        printf 'websocket server exited before it listened on 8002 - giving up\n'
        exit 1
    fi
    if [ "$attempt" -ge 60 ]; then
        printf 'websocket server never listened on 8002 - giving up\n'
        exit 1
    fi
    printf 'waiting for the websocket server (probe %s/60)\n' "$attempt"
    attempt=$((attempt + 1))
    sleep 1
done

exec gunicorn -b 0.0.0.0:8001 -k gthread \
    --workers=${GUNICORN_WORKERS:-4} --threads=${GUNICORN_THREADS:-4} \
    --log-level=info --timeout=0 MrMap.wsgi:application
