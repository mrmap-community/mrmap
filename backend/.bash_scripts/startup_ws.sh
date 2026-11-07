#!/bin/sh
# The websocket server of this container, on a port of its own.
#
# Kept apart from startup.sh because the development stack needs it too: its
# `backend` service replaces startup.sh with `manage.py runserver`, and nginx
# sends /ws to this port whether the HTTP side is gunicorn or runserver (see
# docker/nginx/mrmap.conf, #1032).
#
# Websockets are the one part of MrMap which has to be served as ASGI: they are
# long lived, idle and I/O bound, so one event loop carries the open
# connections of a whole deployment, and uvicorn workers - the worker class of
# the ASGI handler - are the right fit for exactly that shape of work. HTTP
# deliberately is not: see startup.sh.
source /opt/venv/bin/activate

exec gunicorn -b 0.0.0.0:8002 -k uvicorn.workers.UvicornWorker \
    --workers=${GUNICORN_WS_WORKERS:-1} --log-level=info --timeout=0 \
    MrMap.asgi:application
