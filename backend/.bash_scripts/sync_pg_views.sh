#!/bin/sh


# Konfiguration
DB_NAME="deine_datenbank"
DB_USER="dein_benutzer"
DB_HOST="localhost"
TABLE_NAME="deine_tabelle"

# Passwort durchreichen
export PGPASSWORD="$SQL_PASSWORD"

SCHEMA="public"
MV1="registry_searchabledatasetmetadatarecord"
MV2="registry_searchableservicemetadatarecord"

function matview_exists() {
    local mv_name=$1
    psql -U "$SQL_USER" -h "$SQL_HOST" -p "$SQL_PORT" -d "$SQL_DATABASE" -tAc \
    "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = '$SCHEMA' AND matviewname = '$mv_name');"
}


EXISTS1=$(matview_exists "$MV1")
EXISTS2=$(matview_exists "$MV2")

if [ "$EXISTS1" != "t" ] || [ "$EXISTS2" != "t" ]; then
  echo "Mindestens eine der Materialized Views ($TABLE1 oder $TABLE2) existiert NICHT. Starte python manage.py sync_pgviews --force."

  python manage.py sync_pgviews --force
  # Falls du den Exit-Code prüfen möchtest:
    if [ $? -eq 0 ]; then
        echo "Befehl erfolgreich ausgeführt."
    else
        echo "Fehler beim Ausführen des Befehls!" >&2
        exit 1
    fi
else
  echo "Materialized views $MV1 and $MV2 allready initialized."
fi



exec "$@"