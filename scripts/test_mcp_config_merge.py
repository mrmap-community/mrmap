#!/usr/bin/env python3
"""Offline checks for the local OpenCode config merge (#1637).

Run from the repository root:  python3 scripts/test_mcp_config_merge.py
Needs nothing but the standard library: no docker, no network, no gh, no
database, no OpenCode. Exit 0 = every check passed, 1 = a check failed, 2 = the
harness itself could not run.

Why these checks exist
----------------------
``scripts/mcp-setup.sh`` answered its last step with a heredoc which wrote
``.opencode/opencode.json`` from scratch. That file is the local layer of the
host's OpenCode configuration, so a run of the setup script cost the machine
its own choices - model and provider selection, the context and output limits
of a locally served model, compaction, permissions, and the MCP servers someone
switched off on purpose. Writing that file from scratch was therefore the bug,
and the check which matters here is the one which fails on it: the config which
was there before must still be there afterwards, apart from the one server
entry the script is being run for.

How the checks stay off the machine
-----------------------------------
* Every merge runs with a temp directory as its working directory and a path
  inside it as its target. The checkout's own ``opencode.json`` and
  ``.opencode/`` are never arguments to anything run here.
* The checks which run the real ``scripts/mcp-setup.sh`` do so against a throw
  away repository in a temp directory with ``HOME`` pointed into the same temp
  tree, so neither the venv step (``$HOME/.venvs``) nor the token file step can
  reach the host. ``git``, ``docker``, ``openssl`` and ``gh`` are stubbed by
  shell scripts earlier on ``PATH``: no repository is read, no container is
  started, no database is touched, no credential is asked of a keyring and no
  auth status is checked against the network.
* Every password, DSN and token in this file is synthetic and committed on
  purpose (#1637 asks for exactly that). One check asserts that those literals
  never come back out of the merger's stdout or stderr, so the no-secrets-in-
  logs rule is tested and not just promised. No shell tracing is used anywhere:
  the real credentials are never in this script's environment to begin with.
"""

import copy
import json
import os
import shlex
import shutil
import stat
import subprocess  # nosec B404 - running the script under test is the point
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MERGER = ROOT / "scripts" / "mcp_config_merge.py"
SETUP = ROOT / "scripts" / "mcp-setup.sh"

# Synthetic, deliberately recognisable: one check greps for these literals in
# everything the merger prints.
RO_PW = "aabbccddeeff00112233445566778899"
OLD_PW = "OLD-pw-never-written"
DSN = f"postgresql://mcp_readonly:{RO_PW}@127.0.0.1:15999/mrmapdb"
SECRETS = (RO_PW, OLD_PW, DSN)
PIN = "@yawlabs/postgres-mcp@0.13.13"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


# The local config of a host, in the shape #1637 reported: the keys are taken
# from the issue's wording. The merger does not know any of them - that is the
# point - so these checks assert they come back unchanged without claiming
# anything about OpenCode's schema.
HOST_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "$comment": "hand written on this machine, not the setup script's to own",
    "model": "local/qwen3.8-flash",
    "provider": {
        "local": {
            "options": {
                "baseURL": "http://127.0.0.1:8080/v1",
                "limit": {"context": 32768, "output": 8192},
            }
        }
    },
    "compaction": {"auto": True, "prune": False},
    "permission": {"edit": "ask", "bash": {"*": "ask", "git push *": "deny"}},
    "a_key_opencode_does_not_know_yet": {"nested": [1, 2, {"deep": "value"}]},
    "mcp": {
        "timeout": {"startup": 90000},
        "servers": {
            "django-docs": {"type": "remote",
                            "url": "https://gitmcp.io/django/django/6.0.8/mcp"},
            # switched off on this host, and it must stay switched off
            "github": {"type": "local", "disabled": True,
                       "command": ["docker", "run", "-i", "--rm",
                                   "ghcr.io/github/github-mcp-server"]},
            # the entry the script is allowed to rewrite, with an old DSN
            "postgres": {"type": "local",
                         "command": ["npx", "-y", PIN],
                         "environment": {"DATABASE_URL": (
                             f"postgresql://mcp_readonly:{OLD_PW}"
                             "@127.0.0.1:15432/mrmap")}},
        },
    },
}


def without_postgres(document):
    """A deep copy with only the postgres entry dropped out of it."""
    kept = copy.deepcopy(document)
    kept.get("mcp", {}).get("servers", {}).pop("postgres", None)
    return kept


def run_merger(cwd, dsn=DSN, file="opencode.json", server="postgres",
               package=PIN, note=""):
    """One merger run against a path inside ``cwd``; returns the process."""
    argv = [sys.executable, str(MERGER), "--file", file,
            "--server", server, "--package", package]
    if note:
        argv += ["--note", note]
    process = subprocess.run(  # nosec B603 - fixed argv, temp cwd, no shell
        argv, input=dsn, capture_output=True, text=True, cwd=str(cwd),
        timeout=60)
    return process


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mode_of(path):
    return stat.S_IMODE(Path(path).stat().st_mode)


def temp_tree():
    """A temp dir with a scripts/ copy of the merger, ready to work in.

    The copy of ``mcp_config_merge.py`` is what lets the real
    ``scripts/mcp-setup.sh`` run against a throw-away repository: it reaches the
    merger over the same relative path it uses in a real checkout.
    """
    tree = Path(tempfile.mkdtemp(prefix="mrmap-mcp-merge-"))
    (tree / "scripts").mkdir()
    shutil.copyfile(MERGER, tree / "scripts" / "mcp_config_merge.py")
    return tree


# ----------------------------------------------------------- merger behaviour

def merger_checks():
    with tempfile.TemporaryDirectory(prefix="mrmap-merge-") as raw:
        tmp = Path(raw)

        # -- creates what a clean checkout does not have
        proc = run_merger(tmp, note="LOCAL override for this checkout")
        target = tmp / "opencode.json"
        created_ok = proc.returncode == 0 and target.is_file()
        check("creates the local override when there is none", created_ok,
              proc.stderr.strip())
        if created_ok:
            doc = read_json(target)
            check("  with the schema and the note of a fresh file",
                  doc.get("$schema") == "https://opencode.ai/config.json"
                  and doc.get("$comment") == "LOCAL override for this checkout")
            check("  with the postgres entry the setup script needs",
                  doc["mcp"]["servers"]["postgres"] == {
                      "type": "local", "command": ["npx", "-y", PIN],
                      "environment": {"DATABASE_URL": DSN}})
            check("  written as mode 0600 (it carries a DSN)",
                  mode_of(target) == 0o600, f"mode {oct(mode_of(target))}")

        # -- preserves everything the script was not asked about
        host_file = tmp / "host.json"
        host_file.write_text(json.dumps(HOST_CONFIG, indent=2) + "\n",
                             encoding="utf-8")
        os.chmod(host_file, 0o644)
        proc = run_merger(tmp, file="host.json")
        preserved_ok = proc.returncode == 0
        check("updates an existing local config", preserved_ok, proc.stderr.strip())
        if preserved_ok:
            after = read_json(host_file)
            check("  keeps every setting which is not postgres identical",
                  without_postgres(after) == without_postgres(HOST_CONFIG),
                  "a top-level setting or another server entry changed")
            check("  keeps a server the host disabled, disabled",
                  after["mcp"]["servers"]["github"].get("disabled") is True)
            check("  keeps the mcp settings beside the servers",
                  after["mcp"].get("timeout") == {"startup": 90000})
            check("  keeps the host's own $comment and $schema",
                  after.get("$comment") == HOST_CONFIG["$comment"]
                  and "$schema" in after)
            check("  replaces the postgres entry with the intended one",
                  after["mcp"]["servers"]["postgres"] == {
                      "type": "local", "command": ["npx", "-y", PIN],
                      "environment": {"DATABASE_URL": DSN}})
            check("  tightens a mode which is too loose for a DSN",
                  mode_of(host_file) == 0o600, f"mode {oct(mode_of(host_file))}")

            # -- repeated setup runs are idempotent about unrelated settings
            before_bytes = host_file.read_bytes()
            again = run_merger(tmp, file="host.json")
            check("  a second run changes no byte of the file",
                  again.returncode == 0 and host_file.read_bytes() == before_bytes,
                  again.stderr.strip())
            check("  and still leaves the unrelated settings alone",
                  without_postgres(read_json(host_file))
                  == without_postgres(HOST_CONFIG))

        # -- the file it cannot preserve stays as it is
        cases = [
            ("broken JSON", '{"mcp": {"servers": '),
            ("a trailing comma (JSON5, not JSON)",
             '{"mcp": {"servers": {"a": {"type": "local"},},}}'),
            ("a // comment (JSONC, not JSON)",
             '{\n  // host note\n  "mcp": {"servers": {}}\n}'),
            ("a JSON array at the top level", '["mcp"]'),
            ("an mcp section which is not an object", '{"mcp": []}'),
            ("an mcp.servers which is not an object", '{"mcp": {"servers": []}}'),
        ]
        for label, content in cases:
            bad = tmp / "bad.json"
            bad.write_text(content, encoding="utf-8")
            os.chmod(bad, 0o640)
            proc = run_merger(tmp, file="bad.json")
            untouched = (bad.read_text(encoding="utf-8") == content
                         and mode_of(bad) == 0o640)
            check(f"refuses {label} and leaves the file alone",
                  proc.returncode == 2 and untouched,
                  f"exit {proc.returncode}, content "
                  f"{'unchanged' if untouched else 'CHANGED'}")
            check("  and names the file rather than its content in the error",
                  "bad.json" in proc.stderr
                  and not any(secret in proc.stderr for secret in SECRETS),
                  proc.stderr.strip())

        # -- a path which is not a plain file
        blocked = tmp / "blocked"
        blocked.mkdir()
        proc = run_merger(tmp, file="blocked")
        check("refuses a directory in the file's place",
              proc.returncode == 2 and blocked.is_dir(), proc.stderr.strip())

        outside = tmp / "outside.json"
        outside.write_text(json.dumps({"keep": "me"}, indent=2), encoding="utf-8")
        link = tmp / "link.json"
        link.symlink_to(outside)
        proc = run_merger(tmp, file="link.json")
        check("refuses a symlink and leaves both it and its target alone",
              proc.returncode == 2 and link.is_symlink()
              and read_json(outside) == {"keep": "me"}, proc.stderr.strip())

        # -- nothing to preserve, and nothing to write into
        empty = tmp / "empty.json"
        empty.write_text("\n", encoding="utf-8")
        proc = run_merger(tmp, file="empty.json")
        check("treats an empty file as nothing to preserve",
              proc.returncode == 0
              and read_json(empty)["mcp"]["servers"]["postgres"]
              ["environment"]["DATABASE_URL"] == DSN
              and mode_of(empty) == 0o600, proc.stderr.strip())

        proc = run_merger(tmp, file="no/such/dir/opencode.json")
        check("refuses a missing directory without creating one",
              proc.returncode == 3 and not (tmp / "no").exists(),
              proc.stderr.strip())

        # -- the DSN itself is checked before anything is written
        keep = tmp / "keep.json"
        keep.write_text(json.dumps(HOST_CONFIG, indent=2), encoding="utf-8")
        keep_bytes = keep.read_bytes()
        proc = run_merger(tmp, dsn="", file="keep.json")
        check("refuses an empty DSN and touches nothing",
              proc.returncode == 3 and keep.read_bytes() == keep_bytes,
              proc.stderr.strip())
        proc = run_merger(tmp, dsn=f"{DSN}\n{DSN}", file="keep.json")
        check("refuses a DSN which is not one line and touches nothing",
              proc.returncode == 3 and keep.read_bytes() == keep_bytes,
              proc.stderr.strip())

        # -- no credential in anything printed
        ok_proc = run_merger(tmp, file="keep.json")
        quiet = all(
            not any(secret in proc.stdout + proc.stderr for secret in SECRETS)
            for proc in (ok_proc, run_merger(tmp, dsn="", file="keep.json")))
        check("keeps the DSN out of its own stdout and stderr", quiet)


# --------------------------------------------------- the setup script itself

STUBS = {
    # The script only asks git for the repository root; the temp tree is not a
    # repository and needs none of the rest of it.
    "git": "#!/bin/sh\n"
           'for arg in "$@"; do case "$arg" in --show-toplevel) '
           "printf '%s\\n' \"$MRMAP_TEST_REPO\"; exit 0;; esac; done\n"
           "exit 0\n",
    # Stands in for the whole container side: it answers the postgis probe the
    # way the script expects and records the calls, and starts nothing.
    "docker": "#!/bin/sh\n"
              'printf \'%s\\n\' "$*" >> "$MRMAP_TEST_DOCKER_LOG"\n'
              'if [ "$1" = "ps" ]; then printf \'%s\\n\' '
              '"$MRMAP_TEST_PG_CONTAINER"; fi\n'
              "exit 0\n",
    # The read-only password: synthetic, fixed, so a re-run sees the same DSN.
    "openssl": "#!/bin/sh\n" "printf '%s\\n' 'aabbccddeeff00112233445566778899'\n",
    # Never reached: the real gh would ask the network for an auth status.
    "gh": "#!/bin/sh\nexit 1\n",
}


def setup_sandbox():
    """A throw-away checkout, an isolated HOME and stubbed external commands.

    Returns (repo, home, stub_dir, docker_log, cleanup). The real checkout, its
    ``.env``, its venv and the host's OpenCode config are not part of it.
    """
    base = Path(tempfile.mkdtemp(prefix="mrmap-mcp-setup-"))
    repo = base / "checkout"
    home = base / "home"
    stubs = base / "stubs"
    docker_log = base / "docker.log"
    docker_log.touch()
    repo.mkdir()
    home.mkdir()
    stubs.mkdir()
    (home / ".venvs" / "orm-lens" / "bin").mkdir(parents=True)
    # present, so the venv step short-circuits instead of installing anything
    venv_marker = home / ".venvs" / "orm-lens" / "bin" / "orm-lens-mcp"
    venv_marker.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(venv_marker, 0o755)
    stub_files = dict(STUBS)
    stub_files["python3"] = (
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n")
    for name, body in stub_files.items():
        stub = stubs / name
        stub.write_text(body, encoding="utf-8")
        os.chmod(stub, 0o755)
    # the merger, reachable under the path the script uses from its repo root
    (repo / "scripts").mkdir()
    shutil.copyfile(MERGER, repo / "scripts" / "mcp_config_merge.py")
    # the committed base config and the slot's .env, secret-free and synthetic.
    # DB_NAME only: that is the key both the current parser and the #1434 one
    # read, so this fixture does not pin which of them landed.
    (repo / "opencode.json").write_text(
        json.dumps({"$schema": "https://opencode.ai/config.json",
                    "mcp": {"servers": {"postgres": {"type": "local",
                                                     "disabled": True}}}},
                   indent=2) + "\n", encoding="utf-8")
    (repo / ".gitignore").write_text("/.env\n", encoding="utf-8")
    (repo / ".env").write_text(
        "COMPOSE_PROJECT_NAME=mrmap-agent-test-1637\n"
        "DB_USER=mrmap\nDB_NAME=mrmapdb\n", encoding="utf-8")
    return repo, home, stubs, docker_log, base


def run_setup(repo, home, stubs, docker_log, no_db=False):
    env = {
        "HOME": str(home),
        "PATH": f"{stubs}{os.pathsep}{os.environ.get('PATH', '')}",
        "MRMAP_TEST_REPO": str(repo),
        "MRMAP_TEST_DOCKER_LOG": str(docker_log),
        "MRMAP_TEST_PG_CONTAINER": "mrmap-agent-test-1637-postgis-1",
        "MRMAP_MCP_PORT": "15999",
    }
    if no_db:
        env["MRMAP_MCP_NO_DB"] = "1"
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("no bash on this runner")
    process = subprocess.run(  # nosec B603 - fixed argv, sandboxed env
        [bash, str(SETUP)], capture_output=True, text=True, cwd=str(repo),
        env=env, timeout=120)
    return process


def script_checks():
    base = None
    try:
        repo, home, stubs, docker_log, base = setup_sandbox()
        override = repo / ".opencode" / "opencode.json"
        base_config = repo / "opencode.json"
        base_bytes = base_config.read_bytes()

        # 1. clean checkout: the override is created, and the ignore rule too
        proc = run_setup(repo, home, stubs, docker_log)
        check("the script creates the override on a clean checkout",
              proc.returncode == 0 and override.is_file(),
              f"exit {proc.returncode}: {proc.stderr.strip()}")
        if override.is_file():
            doc = read_json(override)
            check("  with the DSN of this slot's forwarder",
                  doc["mcp"]["servers"]["postgres"]["environment"]
                  ["DATABASE_URL"] == DSN, json.dumps(
                      doc["mcp"]["servers"].get("postgres", {})))
            check("  as mode 0600", mode_of(override) == 0o600,
                  f"mode {oct(mode_of(override))}")
        ignore = (repo / ".gitignore").read_text(encoding="utf-8")
        check("  and the ignore rule, added once",
              ignore.count("/.opencode/") == 1, ignore)
        check("  the tracked base config is never written",
              base_config.read_bytes() == base_bytes)
        check("  and its output carries no credential",
              not any(secret in proc.stdout + proc.stderr
                      for secret in SECRETS),
              proc.stdout[-200:])

        # 2. the host's own config: the regression #1637 is about
        override.write_text(json.dumps(HOST_CONFIG, indent=2) + "\n",
                            encoding="utf-8")
        os.chmod(override, 0o644)
        proc = run_setup(repo, home, stubs, docker_log)
        ok = proc.returncode == 0
        check("the script keeps a host's local config across a re-run", ok,
              f"exit {proc.returncode}: {proc.stderr.strip()}")
        if ok:
            after = read_json(override)
            check("  model, provider limits, compaction, permissions and "
                  "unknown keys survive",
                  without_postgres(after) == without_postgres(HOST_CONFIG))
            check("  a server disabled on this host is still disabled",
                  after["mcp"]["servers"]["github"].get("disabled") is True)
            check("  only the postgres entry was updated",
                  after["mcp"]["servers"]["postgres"]["environment"]
                  ["DATABASE_URL"] == DSN)
            check("  and the file ends up 0600", mode_of(override) == 0o600)
        again_bytes = override.read_bytes()
        proc = run_setup(repo, home, stubs, docker_log)
        check("  a third run changes no byte at all",
              proc.returncode == 0 and override.read_bytes() == again_bytes,
              proc.stderr.strip())
        ignore = (repo / ".gitignore").read_text(encoding="utf-8")
        check("  without duplicating the ignore rule",
              ignore.count("/.opencode/") == 1, ignore)

        # 3. a config it cannot read is refused, not replaced
        broken = ('{\n  "model": "local/qwen3.8-flash",\n'
                  '  "mcp": {"servers": {"postgres": {"type": "local"}}\n}\n')
        override.write_text(broken, encoding="utf-8")
        os.chmod(override, 0o644)
        proc = run_setup(repo, home, stubs, docker_log)
        check("the script refuses a broken local config and fails",
              proc.returncode != 0
              and override.read_text(encoding="utf-8") == broken,
              f"exit {proc.returncode}")
        check("  and says so without repeating a credential",
              "opencode.json" in proc.stderr + proc.stdout
              and not any(secret in proc.stdout + proc.stderr
                          for secret in SECRETS),
              (proc.stderr or proc.stdout).strip())

        # 4. no-db mode: no provisioning, and the override untouched
        host_only = json.dumps(HOST_CONFIG, indent=2) + "\n"
        override.write_text(host_only, encoding="utf-8")
        docker_log.write_text("", encoding="utf-8")
        proc = run_setup(repo, home, stubs, docker_log, no_db=True)
        check("MRMAP_MCP_NO_DB=1 leaves the existing override untouched",
              proc.returncode == 0
              and override.read_text(encoding="utf-8") == host_only,
              f"exit {proc.returncode}: {proc.stderr.strip()}")
        check("  and provisions no container in that mode",
              docker_log.read_text(encoding="utf-8").strip() == "",
              docker_log.read_text(encoding="utf-8"))

        # 5. the script delegates: the heredoc which generated the file is gone
        script = SETUP.read_text(encoding="utf-8")
        check("the script no longer generates the JSON itself",
              "cat > .opencode/opencode.json" not in script
              and "mcp_config_merge.py" in script)
        check("and hands the DSN over stdin, never as an argument",
              "| python3 scripts/mcp_config_merge.py" in script)
    except (RuntimeError, OSError, subprocess.SubprocessError) as error:
        check("the setup script sandbox could run", False, str(error))
    finally:
        if base is not None:
            shutil.rmtree(base, ignore_errors=True)


def main():
    merger_checks()
    script_checks()

    width = max((len(name) for name, _, _ in RESULTS), default=0)
    failed = [(name, detail) for name, ok, detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name:<{width}}"
        if not ok and detail:
            line += f"   <- {detail}"
        print(line)
    if failed:
        print(f"FAILED ({len(failed)} of {len(RESULTS)} checks)",
              file=sys.stderr)
        return 1
    print(f"OK ({len(RESULTS)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
