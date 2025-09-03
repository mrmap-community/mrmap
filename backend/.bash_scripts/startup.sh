#!/bin/sh
source /opt/venv/bin/activate
gunicorn -b 0.0.0.0:8001 -k uvicorn.workers.UvicornWorker --workers=$GUNICORN_WORKERS --log-level=info --timeout=0 MrMap.asgi:application