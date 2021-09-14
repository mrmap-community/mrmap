#!/bin/bash

if [ "$MRMAP_PRODUCTION" = "False" ]; 
then 
    pip install debugpy
else
    pip uninstall debugpy
fi

# wait for database
if [[ "$DATABASE" = "postgres" ]]
then
    while ! nc -z $SQL_HOST $SQL_PORT; do
      echo "Waiting for postgres host..."
      sleep 0.1
    done
    echo "PostgreSQL host is up.. starting application services"
fi

# run mrmap setup command. It will handle everthing we need to pre setup the system.
python manage.py setup


# startup all services
if [[ "$START_GUNICORN" != "False" ]];
then
    if [[ "$DJANGO_DEBUG" == "1" ]];
    then
        gunicorn -b 0.0.0.0:8001 --workers=2 --reload --log-level=debug --timeout=0 MrMap.wsgi:application &
    else
        gunicorn -b 0.0.0.0:8001 --workers=4 --log-level=error MrMap.wsgi:application &
    fi
fi

if [[ "$START_UVICORN" != "False" ]];
then
    if [[ "$DJANGO_DEBUG" == "1" ]];
    then
        uvicorn --host 0.0.0.0 --port 8002 --workers 2 --reload --log-level 'debug' --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
    else
        uvicorn --host 0.0.0.0 --port 8002 --workers 4 --log-level 'error' --proxy-headers --forwarded-allow-ips='*' MrMap.asgi:application &
    fi
fi



# wait for redis host
if [[ "$STARTUP_CELERY_WORKERS" != "False" ]];
then
    while ! nc -z $REDIS_HOST $REDIS_PORT; do
      echo "Waiting for redis host..."
      sleep 0.1
    done
    echo "Redis host is up.. starting celery workers"

    if [[ "$START_DEFAULT_WORKER" != "False" ]];
    then
        celery -A MrMap worker -E -l DEBUG -n default -Q default --detach
        echo "default worker started"
    fi

    if [[ "$START_HARVEST_WORKER" != "False" ]];
    then
        celery -A MrMap worker -E -l DEBUG -n harvest -Q harvest --detach
        echo "harvest worker started"
    fi

    if [[ "$START_DOWNLOAD_WORKER" != "False" ]];
    then
        celery -A MrMap worker -E -l DEBUG -n download -Q download_described_elements,download_iso_metadata --detach
        echo "download worker started"
    fi

fi

exec "$@"