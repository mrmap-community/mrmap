#!/bin/bash

ENDPOINT=https://mrmap-nginx/api/schema/
COUNTER=0
MAX_TRIES=20

echo "Waiting for endpoint $ENDPOINT"
until [ "$COUNTER" -eq $MAX_TRIES ] ; do
    if [[ `curl --insecure --silent --head --fail $ENDPOINT` ]]; then
        echo
        echo 'Running tests..'
        exec "$@"
        exit 0        
    fi
    printf '.'
    sleep 5
    ((COUNTER++))
done
if [ "$COUNTER" -eq $MAX_TRIES ]; then
    echo Endpoint "$ENDPOINT" did not become ready in time. Aborting.
    exit 1
fi
