#!/bin/sh

SQL_HOST="${SQL_HOST:-localhost}"
SQL_PORT="${SQL_PORT:-5432}"
SQL_USER="${SQL_USER:-postgres}"
SQL_DATABASE="${SQL_DATABASE:-mrmap}"
# Bounded wait: the probe runs every $WAIT_DB_DELAY seconds, at most
# $WAIT_DB_ATTEMPTS times (default: 120 x 5 s = 10 minutes, which also covers
# a WAL replay on a large instance).
WAIT_DB_ATTEMPTS="${WAIT_DB_ATTEMPTS:-120}"
WAIT_DB_DELAY="${WAIT_DB_DELAY:-5}"

# "Database is up" must mean "accepting queries", not "port open" (#901).
# After an unclean shutdown - a host reboot is the normal case - Postgres
# replays its WAL first: the postmaster already listens on the port but
# refuses every connection with
#   FATAL: the database system is not yet accepting connections
# so the previous "nc -z" TCP probe passed *during* the recovery, the log
# claimed success and manage.py migrate died with an unretried
# OperationalError. pg_isready exits 0 only in the accepting state; while the
# server is starting up or recovering it exits non-zero ("rejecting
# connections" / "no response"), which keeps this loop waiting.
echo "checking database host is reachable and accepting connections..."
attempt=0
while true; do
  probe_output=$(pg_isready -h "$SQL_HOST" -p "$SQL_PORT" -U "$SQL_USER" -d "$SQL_DATABASE" 2>&1)
  probe_status=$?
  if [ "$probe_status" -eq 0 ]; then
    break
  fi
  attempt=$((attempt + 1))
  if [ "$attempt" -ge "$WAIT_DB_ATTEMPTS" ]; then
    echo "ERROR: database $SQL_HOST:$SQL_PORT did not start accepting connections after $attempt probes of the last: $probe_output" >&2
    exit 1
  fi
  echo "database not yet accepting connections (probe $attempt/$WAIT_DB_ATTEMPTS): $probe_output"
  sleep "$WAIT_DB_DELAY"
done
echo "database is accepting connections... continue"

exec "$@"
