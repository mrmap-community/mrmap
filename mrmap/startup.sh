#!/bin/bash
#
# Start all needed application services of MrMap.
cd /opt/mrmap || exit

# start gunicorn as wsgi service
./startup_gunicorn.sh &

# start uvicorn as asgi service
./startup_uvicorn.sh &

#  start celery worker
#celery -A MrMap worker -E -l DEBUG -n default -Q default
#celery -A MrMap worker -E -l DEBUG -n harvest -Q harvest
#celery -A MrMap worker -E -l DEBUG -n download2 -Q download_described_elements
#celery -A MrMap worker -E -l DEBUG -n download1 -Q download_iso_metadata

# endless loop to keep docker container running endless
while true; do sleep 30; done;