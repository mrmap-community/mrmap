#!/bin/bash
cd /opt/mrmap || exit
if [ "$DJANGO_DEBUG" == "1" ]
then
  gunicorn -b 0.0.0.0:8001 --workers=2 --reload --log-level='debug' --timeout=0 MrMap.wsgi:application
else
  gunicorn -b 0.0.0.0:8001 --workers=4 --log-level='error' MrMap.wsgi:application
fi