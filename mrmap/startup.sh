#!/bin/bash
#
# Start all needed application services of MrMap.
cd /opt/mrmap

# start gunicorn as wsgi service
./startup_gunicorn.sh &

# start uvicorn as asgi service
./startup_uvicorn &

# todo
#  start celery worker

# endless loop to keep docker container running endless
while true; do sleep 30; done;