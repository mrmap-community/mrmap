#!/bin/bash

# wait for database
if [[ "$DATABASE" = "postgres" ]]
then
    while ! nc -z $SQL_HOST $SQL_PORT; do
      echo "Waiting for postgres host to finish mrmap setup..."
      sleep 0.1
    done
    echo "PostgreSQL host is up.. running setup..."
fi

# run mrmap setup command. It will handle everthing we need to pre setup the system.
python manage.py setup

exec "$@"