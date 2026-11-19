#!/usr/bin/env python3
"""Set one MCP server entry of a local OpenCode config, keep everything else.

Run from the repository root (``scripts/mcp-setup.sh`` does it):

    printf '%s' "$DSN" | python3 scripts/mcp_config_merge.py \
        --file .opencode/opencode.json --server postgres \
        --package @yawlabs/postgres-mcp@0.13.13 --note "LOCAL overrides ..."

Why this exists (#1637)
-----------------------
``scripts/mcp-setup.sh`` used to answer its last step with a heredoc which wrote
``.opencode/opencode.json`` from scratch. That file is the *local* layer: hosts
keep their own choices there - model and provider selection, the context and
output limits of a locally served model, compaction settings, permissions, and
MCP servers they switched off on purpose. The rewrite discarded all of it, and
OpenCode's hot reload picked the consequence up immediately: servers which were
disabled ran again and a context limit of 32K read as the provider default
(about 256K) again. A step whose only job is to hand one dev-only DSN to one
server entry must not be a reason to lose the rest of a machine's configuration.

So the writing is here, and it is deliberately narrow:

* Only ``mcp.servers.<server>`` is replaced, with the entry the setup script
  needs. A same-named server entry replaces the base entry wholesale in
  OpenCode, so replacing it wholesale is what enables the server; every other
  key of the file, known to OpenCode or not, is carried over as it was read.
* The config is *validated before it is touched*. A file this cannot preserve -
  broken JSON, a JSONC comment or a trailing comma, a top level which is not an
  object, an ``mcp`` or ``mcp.servers`` which is not an object - is refused with
  exit 2 and left byte for byte as it is. Refusing is the honest answer: any
  other action would be the destructive rewrite under a better name.
* The replacement is atomic (a temp file in the same directory, then
  ``os.replace``), so an interrupted run cannot leave a half-written config
  behind, and the result is mode 0600 because the file carries a DSN.
* The DSN arrives on **stdin** and is never echoed. It stays out of ``ps``, out
  of the log of whoever runs the script, and out of every message this writes,
  including the refusal messages.

Formatting is the one thing which is not preserved: a rewritten file is
serialised as 2-space-indented JSON. Values survive unchanged in meaning; byte
identity of a hand-formatted file is not promised and no config consumer reads
bytes.

Exit codes: 0 wrote (or rewrote the same bytes), 2 refused - the file was not
touched, 3 the call itself is wrong (bad arguments, no DSN on stdin).
"""

import argparse
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

# The entry shape the setup script needs: an npx stdio server whose database
# credential is the DSN on stdin. Pinned package comes from --package, so the
# pin stays where it was before: in scripts/mcp-setup.sh.
SERVER_TYPE = "local"
SCHEMA_URL = "https://opencode.ai/config.json"

REFUSED = 2
USAGE = 3


class Refused(Exception):
    """The existing config cannot be preserved; the file must stay as it is."""


def _json_type_name(value):
    """Name a JSON type the way the message reads, not ``list`` for an array."""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, bool):
        return "boolean"
    if value is None:
        return "null"
    return "number"


def read_existing(path):
    """Parse the file to update.

    Returns the parsed document, or ``None`` when there is nothing to preserve
    (no file, or an empty one - an empty file is what an interrupted rewrite of
    the old script left behind, and it holds no settings to lose). Everything
    else which is not a config this function can write back is ``Refused``.

    No message here ever carries file content: the config may hold a DSN, so a
    parse error is reported by position only (``json`` reports it that way) and
    the type complaints name a type, never a value.
    """
    try:
        # lstat, not stat: a symlink is refused rather than silently detached
        # from the file it points at, because replacing the link would leave a
        # stale DSN behind at its target. A dangling link holds nothing to read,
        # and it is refused for the same reason: it is not the plain file this
        # writes back.
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return None
    except OSError as error:
        raise Refused(f"cannot be inspected ({error.strerror})")
    if not stat.S_ISREG(mode):
        raise Refused("is not a regular file - a symlink or a directory in its "
                      "place is not a local override this can write back")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise Refused("is not UTF-8 text")
    except OSError as error:
        raise Refused(f"cannot be read ({error.strerror})")
    if not text.strip():
        return None
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        # json's own message is position-only ("Expecting ',' delimiter: line 5
        # column 3 (char 61)"), which is what makes it safe to repeat: a config
        # with a DSN in it must not be quoted back to the terminal.
        raise Refused(
            "is not valid JSON "
            f"({error.msg} at line {error.lineno} column {error.colno}). "
            "Comments and trailing commas are not JSON: OpenCode reads "
            "`.jsonc`/`.json5` files as such, this file is parsed strictly")
    if not isinstance(document, dict):
        raise Refused(
            f"holds a JSON {_json_type_name(document)} at its top level; an "
            "OpenCode config is a JSON object")
    mcp = document.get("mcp")
    if mcp is not None and not isinstance(mcp, dict):
        raise Refused(
            "has a `mcp` section which is a JSON "
            f"{_json_type_name(mcp)}, not an object")
    if isinstance(mcp, dict):
        servers = mcp.get("servers")
        if servers is not None and not isinstance(servers, dict):
            raise Refused(
                "has `mcp.servers` which is a JSON "
                f"{_json_type_name(servers)}, not an object")
    return document


def merge(document, server, entry, note):
    """Return ``document`` with ``mcp.servers.<server>`` set to ``entry``.

    The entry is replaced wholesale - that is how OpenCode itself treats a
    same-named server against the committed base, and it is what re-enables a
    server the setup script is being run for. Nothing else is read or written.
    """
    if document is None:
        document = {"$schema": SCHEMA_URL}
        if note:
            document["$comment"] = note
        document["mcp"] = {"servers": {server: entry}}
        return document
    mcp = document.setdefault("mcp", {})
    servers = mcp.setdefault("servers", {})
    servers[server] = entry
    return document


def write_atomic(path, document):
    """Write ``document`` as 0600 JSON by replacing the file in one step.

    The temp file sits in the same directory so ``os.replace`` is atomic on the
    same filesystem; it is created with mode 0600 rather than umask-default,
    because the moment the DSN is on disk it is readable material.
    """
    payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w", encoding="utf-8") as handle_file:
            handle_file.write(payload)
            handle_file.flush()
            os.fsync(handle_file.fileno())
        os.replace(tmp_name, str(path))
    except OSError:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    # os.replace carried the temp file's mode over; say it again so the promise
    # holds even for a filesystem which ignored fchmod.
    os.chmod(str(path), 0o600)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Replace one mcp.servers entry of a local OpenCode config "
                    "and keep every other setting of it.")
    parser.add_argument("--file", required=True,
                        help="the local override to update (created when missing)")
    parser.add_argument("--server", default="postgres",
                        help="the key under mcp.servers to replace")
    parser.add_argument("--package", required=True,
                        help="pinned npm package for the npx command line")
    parser.add_argument("--note", default="",
                        help="$comment to write when the file is created")
    args = parser.parse_args(argv)

    dsn = sys.stdin.read().strip()
    if not dsn:
        print("mcp_config_merge: no DSN on stdin - nothing to write, "
              f"{args.file} untouched", file=sys.stderr)
        return USAGE
    if "\n" in dsn or "\r" in dsn:
        # Say nothing about the value itself: a stray newline inside a DSN is a
        # caller bug, and the fix is in the caller, not in this output.
        print("mcp_config_merge: the DSN on stdin is more than one line - "
              f"nothing to write, {args.file} untouched", file=sys.stderr)
        return USAGE

    path = Path(args.file)
    if not path.parent.is_dir():
        print(f"mcp_config_merge: no directory {path.parent} - create it first",
              file=sys.stderr)
        return USAGE

    entry = {
        "type": SERVER_TYPE,
        "command": ["npx", "-y", args.package],
        "environment": {"DATABASE_URL": dsn},
    }

    try:
        existing = read_existing(path)
    except Refused as error:
        print(f"mcp_config_merge: refusing to touch {path}: it {error}.\n"
              f"                  {path} was left exactly as it is. Fix it, or "
              "move it aside and re-run scripts/mcp-setup.sh to get a fresh "
              "local override.", file=sys.stderr)
        return REFUSED
    except OSError as error:
        print(f"mcp_config_merge: cannot work on {path}: {error}",
              file=sys.stderr)
        return USAGE

    created = existing is None
    document = merge(existing, args.server, entry, args.note)
    try:
        write_atomic(path, document)
    except OSError as error:
        print(f"mcp_config_merge: cannot write {path}: {error}", file=sys.stderr)
        return USAGE
    verb = "created" if created else "updated"
    entry = f"mcp.servers.{args.server}"
    detail = (f"{entry} with the dev-only DSN" if created
              else f"{entry} only, the rest of the file is carried over")
    print(f"mcp_config_merge: {verb} {path} (mode 600, {detail})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
