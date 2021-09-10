#!/bin/bash
#
# Start all needed application services of MrMap.
cd /opt/mrmap

# start gunicorn as wsgi service
if [ "$DJANGO_DEBUG" == "1" ]
then
  gunicorn -b 0.0.0.0:8001 --workers=2 --reload --log-level='debug' MrMap.wsgi:application &
else
  gunicorn -b 0.0.0.0:8001 --workers=4 --log-level='error' MrMap.wsgi:application &
fi

status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start gunicorn: $status"
  exit $status
else
  echo "gunicorn successfully started."
fi

# start uvicorn as asgi service
if [ "$DJANGO_DEBUG" == "1" ]
then
  uvicorn --host 0.0.0.0 --port 8002 --workers 2 --reload --log-level debug --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
else
  uvicorn --host 0.0.0.0 --port 8002 --workers 4 --log-level error --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
fi

status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start uvicorn: $status"
  exit $status
else
  echo "uvicorn successfully started."
fi


# todo
#  start celery worker

# endless loop to keep docker container running endless
while true; do sleep 30; done;