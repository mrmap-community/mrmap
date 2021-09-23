#!/bin/bash

# wait for database
echo "checking database host is reachable..."
while ! nc -z $SQL_HOST $SQL_PORT; do
  echo "Waiting for database host..."
  sleep 0.1
  echo "..."
done
echo "database host is up... continue"

exec "$@"