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

exec "$@"