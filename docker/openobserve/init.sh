#!/bin/bash
EMAIL="root@example.com"
PASSWORD="Complexpass#123"
ORG="default"

# Warten, bis OpenObserve bereit ist
until curl -s -u "$EMAIL:$PASSWORD" http://openobserve:5080/api/$ORG/health | grep "OK"; do
  echo "Warte auf OpenObserve..."
  sleep 2
done

# Pipelines importieren
curl -s -u "$EMAIL:$PASSWORD" \
  -X POST http://openobserve:5080/api/$ORG/pipelines \
  -H "Content-Type: application/json" \
  -d @pipelines.json

# Data Sources importieren
curl -s -u "$EMAIL:$PASSWORD" \
  -X POST http://openobserve:5080/api/$ORG/functions \
  -H "Content-Type: application/json" \
  -d @functions.json