#!/bin/bash
#
# Start all needed application services of MrMap.
cd /opt/mrmap

# start gunicorn as wsgi service
if [ "$DJANGO_DEBUG" == "1" ]
then
  gunicorn -b 0.0.0.0:8001 --workers=2 --reload --log-level='debug' --timeout=0 MrMap.wsgi:application &
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




# todo
#  start celery worker

# endless loop to keep docker container running endless
while true; do sleep 30; done;