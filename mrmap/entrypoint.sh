#!/bin/bash

# wait for database
if [[ "$DATABASE" = "postgres" ]]
then
    echo "Waiting for postgres..."

    while ! nc -z $SQL_HOST $SQL_PORT; do
      sleep 0.1
    done

    echo "PostgreSQL host is up"
fi

python manage.py setup

if [[ "$START_UVICORN" == "true" && "$MRMAP_DEVELOPMENT" == "true" ]];
then
    ./startup_uvicorn.sh &
fi

if [[ "$START_GUNICORN" == "true" && "$MRMAP_DEVELOPMENT" == "true" ]];
then
    ./startup_gunicorn.sh &
fi

exec "$@"
