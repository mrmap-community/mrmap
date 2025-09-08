#!/bin/sh

# Pass through password
export PGPASSWORD="$SQL_PASSWORD"

SCHEMA="public"

# Space-separated list of materialized views
MVS="registry_searchabledatasetmetadatarecord \
     registry_searchableservicemetadatarecord \
     registry_materializedharvestingstatsperday"

# Function: check existence
matview_exists() {
    mv_name=$1
    psql -U "$SQL_USER" -h "$SQL_HOST" -p "$SQL_PORT" -d "$SQL_DATABASE" -tAc \
    "SELECT EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = '$SCHEMA' AND matviewname = '$mv_name');"
}

# Flag: missing views
MISSING=false

for mv in $MVS; do
    EXISTS=$(matview_exists "$mv")
    if [ "$EXISTS" != "t" ]; then
        echo "Materialized view $mv does NOT exist."
        MISSING=true
    else
        echo "Materialized view $mv already exists."
    fi
done

if [ "$MISSING" = true ]; then
    echo "At least one materialized view is missing. Running python manage.py sync_pgviews --force."
    python manage.py sync_pgviews --force

    if [ $? -eq 0 ]; then
        echo "Command executed successfully."
    else
        echo "Error while executing command!" >&2
        exit 1
    fi
else
    echo "All materialized views already exist."
fi

# Pass execution to the given command
exec "$@"
