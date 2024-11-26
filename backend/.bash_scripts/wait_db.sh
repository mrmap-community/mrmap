#!/bin/sh

# wait for database
echo "checking database host is reachable..."
while ! nc -z $SQL_HOST $SQL_PORT; do
  sleep 0.1
  echo "Waiting for database host..."
done
echo "database host is up... continue"

exec "$@"