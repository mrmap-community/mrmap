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
#                                       the dev-only DSN
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

# ------------------------------------------------------------ read .env slot
[ -f .env ] || { ERR ".env missing - run 'mrp init' / configure the slot first"; exit 1; }
# Read specific keys via grep to avoid issues with ; in values (issue #1434)
project="${COMPOSE_PROJECT_NAME:-mrmap}"
dbuser="$(grep -m1 '^DB_USER=' .env | cut -d= -f2)"
# Backend uses SQL_DATABASE env var, but .env slot uses DB_NAME for backwards compat
if grep -q '^SQL_DATABASE=' .env; then
  dbname="$(grep -m1 '^SQL_DATABASE=' .env | cut -d= -f2)"
elif grep -q '^DB_NAME=' .env; then
  dbname="$(grep -m1 '^DB_NAME=' .env | cut -d= -f2)"
else
  dbname="mrmap"
fi
pg_container="${project}-postgis-1"
network="${project}_mrmap-internal"

docker ps --format '{{.Names}}' | grep -qx "$pg_container" \
  || { ERR "container $pg_container not running - start it (mrp up postgis / mrp deps)"; exit 1; }

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
GRANT CONNECT ON DATABASE mrmap TO mcp_readonly;
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
cat > .opencode/opencode.json <<JSON
{
  "\$schema": "https://opencode.ai/config.json",
  "\$comment": "LOCAL overrides generated by scripts/mcp-setup.sh on $(hostname) for $(pwd). Contains a DEV-ONLY read-only DSN. Git-ignored. Re-run the script to regenerate.",
  "mcp": {
    "servers": {
      "postgres": {
        "type": "local",
        "command": ["npx", "-y", "@yawlabs/postgres-mcp@0.13.13"],
        "environment": {
          "DATABASE_URL": "postgresql://mcp_readonly:${ro_pw}@127.0.0.1:${PORT}/${dbname}"
        }
      }
    }
  }
}
JSON
chmod 600 .opencode/opencode.json
NOTE "wrote .opencode/opencode.json (postgres override, enabled)"

cat <<'DONE'

Done. OpenCode picks this up without a restart (hot reload; /reload to force).
- /mcps shows: docs servers, orm-lens, playwright, postgres
- stop the DB forwarder any time: docker rm -f mrmap-mcp-dbproxy
- docs: docs/development/mcp-servers.md
DONE
