#!/usr/bin/env bash
#
# mcp-setup.sh - provision the per-host side of the MrMap MCP setup.
#
# The committed opencode.json holds all secret-free MCP servers. This script
# prepares what cannot live in git (per machine/checkout):
#
#   1. orm-lens into an isolated venv  (~/.venvs/orm-lens)
#   2. the read-only postgres role     (mcp_readonly, pg_read_all_data, 30s cap)
#   3. a loopback-only TCP forwarder   (127.0.0.1:15432 -> this slot's postgis)
#   4. the local override              (.opencode/opencode.json, mode 600,
#                                       git-ignored) enabling `postgres` with
#                                       the dev-only DSN. Step 4 MERGES that one
#                                       entry into whatever the file already
#                                       holds - it is the host's own config
#                                       (model, limits, permissions, servers it
#                                       switched off), not this script's to
#                                       rewrite; see scripts/mcp_config_merge.py
#
# Safe to re-run. Run from the repository root of the checkout you want to
# wire up. Removes nothing except its own previous forwarder container.
# Before the numbered steps it checks the host prerequisites the committed
# config cannot carry: node >= 18, an authenticated gh CLI and the SonarQube
# token file.
#
# Options (environment):
#   MRMAP_MCP_NO_DB=1   skip steps 2-4 (e.g. host without the dev stack)
#   MRMAP_MCP_PORT=NNN  host port for the forwarder (default 15432)
#
set -euo pipefail

PORT="${MRMAP_MCP_PORT:-15432}"
VENV="$HOME/.venvs/orm-lens"
ORMLENS_PIN="orm-lens[mcp]==1.18.0"
PG_MCP_PIN="@yawlabs/postgres-mcp@0.13.13"
PWFILE="$HOME/.mrmap_mcp_ro_pw"
ERR() { printf '\033[31mmcp-setup:\033[0m %s\n' "$*" >&2; }
NOTE() { printf '\033[36mmcp-setup:\033[0m %s\n' "$*"; }

root="$(git rev-parse --show-toplevel 2>/dev/null)" || { ERR "run inside the mrmap repo"; exit 1; }
cd "$root"
[ -f opencode.json ] || ERR "no opencode.json in repo root - is this the mrmap repo?"

# ---------------------------------------------------------------- node check
if command -v node >/dev/null 2>&1; then
  major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$major" -ge 18 ] || ERR "node >= 18 required for npx MCP servers (found $(node --version))"
else
  NOTE "no node on PATH - playwright/postgres MCP servers will not start on this host"
fi

# ------------------------------------------------------------ sonar token
# The committed opencode.json authenticates the hosted SonarQube MCP server with a
# SonarQube Cloud USER token read from this per-host file (OAuth is not available
# for OpenCode: Sonar only admits CIMD clients from its own allowlist). The script
# checks and tightens the file, it never writes token material.
SONAR_TOKEN_FILE="$HOME/.config/opencode/sonar-token"
if [ ! -s "$SONAR_TOKEN_FILE" ]; then
  NOTE "no $SONAR_TOKEN_FILE - hosted sonarqube MCP server cannot connect. Create a SonarQube Cloud USER token (user icon -> My Account -> Security -> Generate New Token), then: umask 077 && printf '%s' '<token>' > $SONAR_TOKEN_FILE"
else
  [ "$(tail -c1 "$SONAR_TOKEN_FILE")" ] \
    || ERR "$SONAR_TOKEN_FILE ends with a newline - the Authorization header would carry it. Rewrite it without: umask 077 && printf '%s' '<token>' > $SONAR_TOKEN_FILE"
  chmod 600 "$SONAR_TOKEN_FILE"
  NOTE "sonar token file present ($SONAR_TOKEN_FILE) - hosted sonarqube MCP server will connect"
fi

# ----------------------------------------------------------------- gh check
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  NOTE "gh CLI authenticated - github MCP server (Docker) will work on this host"
else
  NOTE "gh CLI missing or unauthenticated - github MCP server will not start (fix: install gh, then 'gh auth login')"
fi

# ---------------------------------------------------------------- 1. orm-lens
if [ ! -x "$VENV/bin/orm-lens-mcp" ]; then
  NOTE "installing orm-lens into $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q "$ORMLENS_PIN"
else
  NOTE "orm-lens venv already present (pinned: $ORMLENS_PIN)"
fi

if [ "${MRMAP_MCP_NO_DB:-0}" = "1" ]; then
  NOTE "MRMAP_MCP_NO_DB=1 - skipping DB role, forwarder and local override"
  exit 0
fi

# ------------------------------------------------------------- read slot keys
# The slot's .env is written for django-environ, not for a shell: the separator a
# host list is documented with is ";" (settings.py _split_host_list), and bash
# reads an unquoted ";" inside a value as a command separator. Sourcing the file
# therefore died on every slot which set DJANGO_ALLOWED_HOST_DEFAULTS the way the
# settings document it, and would have run whatever else a value carried (#1434).
# The keys needed below are read by name instead, and the file is never evaluated.
[ -f .env ] || { ERR ".env missing - run 'mrp init' / configure the slot first"; exit 1; }

# env_key <key>: the value of exactly that key in ./.env, or empty when the slot
# does not declare it. First line carrying the key wins; a trailing CR and one
# pair of surrounding quotes are removed; nothing is expanded or executed.
env_key() {
  local line value
  line="$(grep -m1 -E "^[[:space:]]*(export[[:space:]]+)?$1=" ./.env || true)"
  [ -n "$line" ] || return 0
  value="${line#*=}"
  value="${value%$'\r'}"
  case "$value" in
    '"'*'"') value="${value#\"}"; value="${value%\"}" ;;
    "'"*"'") value="${value#\'}"; value="${value%\'}" ;;
  esac
  printf '%s' "$value"
}

project="$(env_key COMPOSE_PROJECT_NAME)"; project="${project:-mrmap}"
pg_container="${project}-postgis-1"
network="${project}_mrmap-internal"

docker ps --format '{{.Names}}' | grep -qx "$pg_container" \
  || { ERR "container $pg_container not running - start it (mrp up postgis / mrp deps)"; exit 1; }

# container_key <key>: the same key answered by the container's own environment,
# which is what its database was actually created with.
container_key() {
  docker exec "$pg_container" printenv "$1" 2>/dev/null || true
}

# The role and the database to reach: where the slot's .env does not name them,
# the postgis container answers for itself. A slot has never had a DB_NAME key -
# docker-compose.yml names them DB_USER and POSTGRES_DB, the latter defaulted to
# mrmap - and a deployment may keep the user in the backend's env file only.
# DB_NAME is still read, behind POSTGRES_DB, for the slots which were configured
# for the version of this script that required it.
dbuser="$(env_key DB_USER)"; dbuser="${dbuser:-$(container_key POSTGRES_USER)}"
[ -n "$dbuser" ] \
  || { ERR "no DB_USER in $PWD/.env and no POSTGRES_USER in $pg_container - configure the slot"; exit 1; }
dbname="$(env_key POSTGRES_DB)"; dbname="${dbname:-$(env_key DB_NAME)}"
dbname="${dbname:-$(container_key POSTGRES_DB)}"; dbname="${dbname:-mrmap}"
NOTE "slot '$project': role '$dbuser', database '$dbname'"

# ------------------------------------------------------- 2. read-only role
if [ -f "$PWFILE" ]; then
  ro_pw="$(cat "$PWFILE")"
else
  ro_pw="$(openssl rand -hex 16)"; (umask 077; echo "$ro_pw" > "$PWFILE")
  NOTE "generated read-only password in $PWFILE"
fi
docker exec -i -e RO_PW="$ro_pw" "$pg_container" \
  psql -v ON_ERROR_STOP=1 -v ro_pw="$ro_pw" -U "$dbuser" -d "$dbname" <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='mcp_readonly') THEN
    CREATE ROLE mcp_readonly LOGIN;
  END IF;
END $$;
ALTER ROLE mcp_readonly PASSWORD :'ro_pw';
ALTER ROLE mcp_readonly SET statement_timeout = '30s';
ALTER ROLE mcp_readonly SET idle_in_transaction_session_timeout = '30s';
GRANT pg_read_all_data TO mcp_readonly;
-- Connect right on the database this slot's forwarder serves, whatever it is
-- called: psql is connected to exactly that one, so current_database() names it
-- and %I quotes it, instead of assuming the slot's database is called mrmap.
DO $$ BEGIN
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO mcp_readonly', current_database());
END $$;
SQL
NOTE "role mcp_readonly ready (read-only, 30s statement_timeout)"

# ------------------------------------------------- 3. loopback forwarder
docker rm -f mrmap-mcp-dbproxy >/dev/null 2>&1 || true
docker run -d --name mrmap-mcp-dbproxy --network "$network" \
  -p "127.0.0.1:${PORT}:5432" --restart unless-stopped --read-only --memory 64m \
  node:26-alpine node -e '
const net=require("net");
const srv=net.createServer(c=>{const up=net.connect(5432,"postgis");
  c.pipe(up); up.pipe(c);
  c.on("error",()=>up.destroy()); up.on("error",()=>c.destroy());});
srv.listen(5432,"0.0.0.0");' >/dev/null
NOTE "forwarder up: 127.0.0.1:${PORT} -> ${pg_container}:5432 (docker rm -f mrmap-mcp-dbproxy to stop)"

# ------------------------------------------------ 4. local override file
# keep the ignore entry (the committed .gitignore uses "/.opencode/"; only add
# a variant that is actually missing, never a duplicate)
grep -qE '^/?\.opencode/' .gitignore \
  || printf '\n# local per-host OpenCode MCP overrides (dev-only DSN) - never commit\n/.opencode/\n' >> .gitignore
mkdir -p .opencode; chmod 700 .opencode
# The DSN is handed to the merger on stdin: it stays out of argv (world-readable
# in ps), out of every message the merger prints and out of this script's output.
# The merger replaces `mcp.servers.postgres` only and carries the rest of the
# file over, so the host's own choices - model and provider, context and output
# limits, compaction, permissions, servers switched off on purpose - survive a
# re-run (#1637). A config it cannot preserve is refused and left byte for byte
# as it is, which fails this step instead of quietly costing the host its config.
if ! printf '%s' "postgresql://mcp_readonly:${ro_pw}@127.0.0.1:${PORT}/${dbname}" \
  | python3 scripts/mcp_config_merge.py \
      --file .opencode/opencode.json \
      --server postgres \
      --package "$PG_MCP_PIN" \
      --note "LOCAL overrides generated by scripts/mcp-setup.sh on $(hostname) for $(pwd). Contains a DEV-ONLY read-only DSN. Git-ignored. Re-running scripts/mcp-setup.sh updates the postgres entry and keeps everything else."; then
  ERR "could not update .opencode/opencode.json - the file was left untouched. Fix it, or move it aside and re-run this script for a fresh override."
  exit 2
fi
NOTE ".opencode/opencode.json carries the postgres override (enabled); the rest of the local config was left as found"

cat <<'DONE'

Done. OpenCode picks this up without a restart (hot reload; /reload to force).
- /mcps shows: docs servers, orm-lens, playwright, postgres
- stop the DB forwarder any time: docker rm -f mrmap-mcp-dbproxy
- docs: docs/development/mcp-servers.md
DONE
