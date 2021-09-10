#!/bin/bash
cd /opt/mrmap

# start gunicorn as wsgi service
gunicorn MrMap.wsgi:application &
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start gunicorn: $status"
  exit $status
else
  echo "gunicorn successfully started."
fi

# start uvicorn as asgi service
uvicorn --host 0.0.0.0 --port 8002 --workers 4 --log-level debug --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
status=$?
if [ $status -ne 0 ]; then
  echo "Failed to start uvicorn: $status"
  exit $status
else
  echo "uvicorn successfully started."
fi


# todo
#  start celery worker

# Naive check runs checks once a minute to see if either of the processes exited.
# This illustrates part of the heavy lifting you need to do if you want to run
# more than one service in a container. The container exits with an error
# if it detects that either of the processes has exited.
# Otherwise it loops forever, waking up every 60 seconds

while sleep 60; do
  ps aux |grep gunicorn |grep -q -v grep
  PROCESS_1_STATUS=$?
  ps aux |grep uvicorn |grep -q -v grep
  PROCESS_2_STATUS=$?
  # If the greps above find anything, they exit with 0 status
  # If they are not both 0, then something is wrong
  if [ $PROCESS_1_STATUS -ne 0 -o $PROCESS_2_STATUS -ne 0 ]; then
    echo "One of the processes has already exited."
    exit 1
  fi
done