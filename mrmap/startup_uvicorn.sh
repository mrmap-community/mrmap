#!/bin/bash
cd /opt/mrmap
if [ "$DJANGO_DEBUG" == "1" ]
then
  uvicorn --host 0.0.0.0 --port 8002 --workers 2 --reload --log-level debug --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
else
  uvicorn --host 0.0.0.0 --port 8002 --workers 4 --log-level error --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
fi