#!/bin/bash

# start gunicorn as wsgi service
gunicorn MrMap.wsgi:application -b 0.0.0.0:8001 --workers 4 &

# start uvicorn as asgi service
uvicorn --host 0.0.0.0 --port 8002 --workers 4  MrMap.asgi:application

# todo
#  start celery worker