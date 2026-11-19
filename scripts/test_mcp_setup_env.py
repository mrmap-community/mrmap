"""Offline checks that scripts/mcp-setup.sh reads a slot's .env without
evaluating it (#1434).

WHY THIS EXISTS

The script provisioned the per-host MCP wiring by sourcing the slot's .env
(``set -a; . ./.env``). That file is written for django-environ, whose documented
list separator is ";" (``backend/MrMap/settings.py`` ``_split_host_list``), and
bash reads an unquoted ";" as a *command separator*. Every slot which set
``DJANGO_ALLOWED_HOST_DEFAULTS`` the documented way therefore died right there -
and any other value carrying a shell metacharacter was executed, not read. The
script also required ``DB_NAME``, a key no slot has ever had: docker-compose.yml
names the database ``POSTGRES_DB`` (defaulted to ``mrmap``).

WHAT THIS RUNS

The real script, in a throwaway git repository, with a stub ``docker`` on PATH
which answers exactly the four calls it makes and records them. So the checks
cover the shipped control flow rather than an extracted copy of it. Step 4 runs
the real ``scripts/mcp_config_merge.py`` (#1637), copied into the throwaway tree
as the merge suite does it, which follows the resolved database name all the way
into the DSN of the local config.

WHAT NEEDS TO BE PRESENT

Only ``bash`` and ``git``. No docker, no network, no Compose stack, no node: the
orm-lens step is short-circuited by a pre-existing venv stub under a temporary
HOME, and node/gh are stubbed to the answers the script accepts.

Usage: python3 scripts/test_mcp_setup_env.py
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mcp-setup.sh"
MERGER = ROOT / "scripts" / "mcp_config_merge.py"

DOCKER_STUB = """#!/bin/sh
# Stub docker for scripts/test_mcp_setup_env.py. Answers the calls
# scripts/mcp-setup.sh makes and records each one in $DOCKER_LOG; the container's
# own environment is simulated by FAKE_C_<KEY> variables in this environment.
printf 'docker %s\\n' "$*" >> "$DOCKER_LOG"
case "$1" in
  ps)  printf '%s\\n' "$FAKE_PG_CONTAINER"; exit 0 ;;
  rm)  exit 0 ;;
  run) printf 'cafebabe\\n'; exit 0 ;;
esac
[ "$1" = exec ] || { printf 'stub docker: unhandled: %s\\n' "$*" >&2; exit 1; }
shift
while [ $# -gt 0 ]; do
  case "$1" in
    -i) shift ;;
    -e) shift 2 ;;
    *) break ;;
  esac
done
shift  # the container name
case "$1" in
  printenv) printenv "FAKE_C_$2" || exit 3 ;;
  psql) printf '%s\\n' "$*" >> "$PSQL_LOG"; exec cat >> "$SQL_LOG" ;;
  *) printf 'stub docker: unhandled exec: %s\\n' "$*" >&2; exit 1 ;;
esac
"""

NODE_STUB = """#!/bin/sh
# Stub node: version answers only, so the version probe of the script is decided
# by the test instead of by whatever the runner happens to have installed.
case "$1" in
  -p) printf '22\\n' ;;
  --version) printf 'v22.0.0\\n' ;;
esac
exit 0
"""

GH_STUB = """#!/bin/sh
# Stub gh: unauthenticated, which is the answer that costs the script nothing.
exit 1
"""


@unittest.skipUnless(shutil.which("bash"), "no bash on this host")
@unittest.skipUnless(shutil.which("git"), "no git on this host")
class SlotEnvReadingTests(unittest.TestCase):
    """The four steps must run for a slot configured the documented way."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "slot"
        self.home = Path(self._tmp.name) / "home"
        self.stub = Path(self._tmp.name) / "bin"
        for path in (self.root, self.home, self.stub):
            path.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        # The committed base config and the merger of step 4: both are tracked
        # files a real slot has, and the script reaches the merger by that path.
        (self.root / "opencode.json").write_text(
            '{\n  "$schema": "https://opencode.ai/config.json",\n'
            '  "mcp": {\n    "servers": {}\n  }\n}\n')
        (self.root / "scripts").mkdir()
        shutil.copyfile(MERGER, self.root / "scripts" / "mcp_config_merge.py")
        for name, body in (("docker", DOCKER_STUB), ("node", NODE_STUB), ("gh", GH_STUB)):
            tool = self.stub / name
            tool.write_text(body)
            tool.chmod(0o755)
        # Step 1 is not what these checks are about: an existing venv makes it a
        # note instead of a pip install.
        venv_bin = self.home / ".venvs" / "orm-lens" / "bin"
        venv_bin.mkdir(parents=True)
        orm_lens = venv_bin / "orm-lens-mcp"
        orm_lens.write_text("#!/bin/sh\nexit 0\n")
        orm_lens.chmod(0o755)
        # The read-only password the script reads instead of generating one.
        (self.home / ".mrmap_mcp_ro_pw").write_text("ropw-fixed\n")
        self.docker_log = Path(self._tmp.name) / "docker.log"
        self.psql_log = Path(self._tmp.name) / "psql.log"
        self.sql_log = Path(self._tmp.name) / "sql.log"

    def run_setup(self, env_lines, container_env=None, project="slot7", port="15999"):
        """Run the real script in the throwaway slot; returns the CompletedProcess.

        ``env_lines`` is the slot's .env content (None leaves the slot without a
        .env at all), ``container_env`` the POSTGRES_* variables the stub answers
        for the postgis container.
        """
        if env_lines is not None:
            (self.root / ".env").write_text(env_lines)
        env = {
            "PATH": f"{self.stub}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "DOCKER_LOG": str(self.docker_log),
            "PSQL_LOG": str(self.psql_log),
            "SQL_LOG": str(self.sql_log),
            "FAKE_PG_CONTAINER": f"{project}-postgis-1",
            "MRMAP_MCP_PORT": port,
        }
        for key, value in (container_env or {}).items():
            env[f"FAKE_C_{key}"] = value
        return subprocess.run(
            ["bash", str(SCRIPT)], cwd=self.root, env=env,
            capture_output=True, text=True)

    def logs(self):
        def read(path):
            return path.read_text() if path.exists() else ""
        return read(self.docker_log), read(self.psql_log), read(self.sql_log)

    def override(self):
        return self.root / ".opencode" / "opencode.json"

    def test_documented_semicolon_host_list_still_provisions_everything(self):
        """The reproduction of #1434: the documented value must not kill the run."""
        result = self.run_setup(
            "COMPOSE_PROJECT_NAME=slot7\n"
            "DB_USER=mrmap\n"
            "POSTGRES_DB=mrmap_slot7\n"
            "# documented as a ';' (and ',') separated list: settings.py\n"
            "DJANGO_ALLOWED_HOST_DEFAULTS=localhost;127.0.0.1;[::1];mrmap-appserver;"
            "172.17.0.1;testserver;10.99.12.3\n"
            "DJANGO_ALLOWED_HOSTS=demo.mrmap.de;mrmap.internal\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        docker_log, psql_log, _ = self.logs()
        # Step 2 asked the right container as the right role of the right database.
        self.assertIn("docker exec -i -e RO_PW=ropw-fixed slot7-postgis-1 psql "
                      "-v ON_ERROR_STOP=1 -v ro_pw=ropw-fixed "
                      "-U mrmap -d mrmap_slot7", docker_log)
        self.assertIn("-U mrmap -d mrmap_slot7", psql_log)
        # Step 3 bridged this slot's network, not the one of a sourced default.
        self.assertIn("docker run -d --name mrmap-mcp-dbproxy "
                      "--network slot7_mrmap-internal -p 127.0.0.1:15999:5432", docker_log)
        # Step 4 wrote the override, with the resolved database in the DSN.
        self.assertTrue(self.override().exists(), result.stdout + result.stderr)
        self.assertIn("postgresql://mcp_readonly:ropw-fixed@127.0.0.1:15999/mrmap_slot7",
                      self.override().read_text())
        self.assertEqual(self.override().stat().st_mode & 0o777, 0o600)

    def test_the_connect_grant_follows_the_connected_database(self):
        """The SQL must not assume the slot's database is called mrmap."""
        self.run_setup("COMPOSE_PROJECT_NAME=slot7\nDB_USER=mrmap\nPOSTGRES_DB=mrmap_slot7\n",
                       container_env={"POSTGRES_USER": "mrmap", "POSTGRES_DB": "mrmap"})
        _, _, sql = self.logs()
        self.assertIn("GRANT pg_read_all_data TO mcp_readonly;", sql)
        self.assertIn("current_database()", sql)
        self.assertNotIn("ON DATABASE mrmap ", sql)

    def test_values_of_the_file_are_never_executed(self):
        """Whatever a value carries, reading it must not run it."""
        marker = self._tmp.name + "/executed"
        substitution = self._tmp.name + "/executed-substitution"
        command = self._tmp.name + "/executed-backtick"
        result = self.run_setup(
            "COMPOSE_PROJECT_NAME=slot7\n"
            "DB_USER=mrmap\n"
            "POSTGRES_DB=mrmap_slot7\n"
            f"DJANGO_ALLOWED_HOSTS=localhost;touch {marker}\n"
            f"EXTERNAL_BASE_URL=http://example.invalid/$(touch {substitution})\n"
            f"MRMAP_BASE_URL=http://example.invalid/`touch {command}`\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in (marker, substitution, command):
            self.assertFalse(Path(path).exists(), f"{path} was executed by reading .env")
        docker_log, _, _ = self.logs()
        self.assertIn("-U mrmap -d mrmap_slot7", docker_log)

    def test_keys_the_slot_does_not_come_from_the_container(self):
        """A slot .env is not required to carry the database keys at all."""
        result = self.run_setup(
            "COMPOSE_PROJECT_NAME=slot7\nDJANGO_SECRET_KEY=not-a-real-secret\n",
            container_env={"POSTGRES_USER": "slot_user", "POSTGRES_DB": "slot_db"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        docker_log, psql_log, _ = self.logs()
        self.assertIn("-U slot_user -d slot_db", psql_log)
        self.assertIn("docker exec slot7-postgis-1 printenv POSTGRES_USER", docker_log)
        self.assertIn("docker exec slot7-postgis-1 printenv POSTGRES_DB", docker_log)
        self.assertIn("@127.0.0.1:15999/slot_db", self.override().read_text())

    def test_the_slot_answers_and_the_container_is_not_asked(self):
        """What the .env declares wins, and is not second-guessed by the container."""
        result = self.run_setup(
            "COMPOSE_PROJECT_NAME=slot7\nDB_USER=slot_user\nPOSTGRES_DB=slot_db\n",
            container_env={"POSTGRES_USER": "other", "POSTGRES_DB": "other"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        docker_log, psql_log, _ = self.logs()
        self.assertIn("-U slot_user -d slot_db", psql_log)
        self.assertNotIn("printenv", docker_log)

    def test_the_name_the_previous_version_required_is_still_honoured(self):
        """DB_NAME named no key of a slot, but slots configured for the old script
        do carry it; reading it first keeps those slots on their own database."""
        result = self.run_setup(
            "COMPOSE_PROJECT_NAME=slot7\nDB_USER=mrmap\nDB_NAME=legacy_db\n",
            container_env={"POSTGRES_DB": "mrmap"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        _, psql_log, _ = self.logs()
        self.assertIn("-d legacy_db", psql_log)

    def test_quoted_export_prefixed_and_crlf_values_arrive_clean(self):
        """The value is the text after "=", not a shell word."""
        for label, body in (
                ("quoted", "COMPOSE_PROJECT_NAME=slot7\n"
                           'export DB_USER="slot_user"\n'
                           "POSTGRES_DB='slot_db'\n"),
                ("crlf", "COMPOSE_PROJECT_NAME=slot7\r\n"
                         "DB_USER=slot_user\r\n"
                         "POSTGRES_DB=slot_db\r\n")):
            with self.subTest(label):
                result = self.run_setup(body, container_env={"POSTGRES_USER": "other"})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                _, psql_log, _ = self.logs()
                self.assertIn("-U slot_user -d slot_db", psql_log)

    def test_a_missing_role_names_the_key_that_is_missing(self):
        """Nothing answers for the role: fail, and name DB_USER, not another key."""
        result = self.run_setup("COMPOSE_PROJECT_NAME=slot7\nDJANGO_SECRET_KEY=x\n")
        self.assertEqual(result.returncode, 1)
        self.assertIn("DB_USER", result.stderr)
        self.assertNotIn("DB_NAME", result.stderr)
        self.assertFalse(self.override().exists())

    def test_a_slot_without_env_still_says_configure_it(self):
        result = self.run_setup(None)
        self.assertEqual(result.returncode, 1)
        self.assertIn(".env missing", result.stderr)


if __name__ == "__main__":
    unittest.main()
