#!/usr/bin/env python3
"""Offline checks for scripts/http_process_bench (issue #1617).

Runs without docker (the compose check falls back to reading the compose
file when the CLI is absent), without network beyond loopback and without
`gh`: the statistics, the deterministic request plan, the RFC 6455 codec,
the live websocket client against a tiny loopback server, the process-shape
resolver of backend/.bash_scripts/process_defaults.sh and the compose
passthrough of the web tier knobs are all exercised here.

Run from the repository root:
`python3 scripts/test_http_process_bench.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import socket
import struct
import subprocess  # nosec B404 - the checks call the docker CLI and `sh`
import sys
import threading
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
BENCH = SCRIPTS / "http_process_bench.py"
PROCESS_DEFAULTS = ROOT / "backend" / ".bash_scripts" / "process_defaults.sh"

_loader = importlib.machinery.SourceFileLoader("http_process_bench",
                                               str(BENCH))
_spec = importlib.util.spec_from_loader("http_process_bench", _loader)
B = importlib.util.module_from_spec(_spec)
_loader.exec_module(B)

RESULTS = []
SKIPS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def skip(name, reason):
    SKIPS.append((name, reason))


# ------------------------------------------------------------------ stats


def test_stats():
    vals = [float(v) for v in range(1, 101)]
    check("percentile p50 of 1..100", B.percentile(vals, 0.50) == 50)
    check("percentile p95 of 1..100", B.percentile(vals, 0.95) == 95)
    check("percentile p99 of 1..100", B.percentile(vals, 0.99) == 99)
    check("percentile of one sample", B.percentile([2.5], 0.99) == 2.5)
    check("percentile of none", B.percentile([], 0.5) is None)
    # nearest rank: q*n rounds up, so 4 of the sorted 7 samples
    check("percentile ceil rank",
          B.percentile([float(v) for v in range(1, 8)], 0.5) == 4.0)
    stats = B.latency_stats([0.1, 0.2, 0.3])
    check("latency_stats ms", stats and stats["p50_ms"] == 200.0
          and stats["max_ms"] == 300.0 and stats["n"] == 3)
    check("latency_stats empty", B.latency_stats([]) is None)


def test_plan():
    plan = B.build_plan(["/a*2", "/b"], 7)
    check("plan cycles round robin",
          plan == ["/a", "/a", "/b", "/a", "/a", "/b", "/a"])
    check("plan one round",
          B.build_plan(["/a*2", "/b"], 0) == ["/a", "/a", "/b"])
    check("endpoint weight parses", B.parse_endpoint("/x*3") == ("/x", 3))
    check("endpoint without weight", B.parse_endpoint("/x") == ("/x", 1))
    check("endpoint odd weight falls back",
          B.parse_endpoint("/x*y") == ("/x*y", 1))
    try:
        B.build_plan([], 10)
        check("empty plan refused", False)
    except SystemExit:
        check("empty plan refused", True)


def test_summarize():
    results = [
        ("/a", 200, 0.10), ("/a", 200, 0.20), ("/b", 404, 0.30),
        ("/b", 500, 0.40), ("#error", 0, "Connection refused"),
    ]
    s = B.summarize(results, 2.0)
    overall = s["overall"]
    check("summarize counts every answer", overall["n"] == 4)
    check("summarize ok only below 400", overall["ok"] == 2)
    check("summarize errors incl. 4xx/5xx and transport",
          overall["errors"] == 3)
    check("summarize rps", overall["rps"] == 2.0)
    check("summarize per endpoint",
          s["by_endpoint"]["/a"]["n"] == 2
          and s["by_endpoint"]["/b"]["status"]["500"] == 1)
    check("summarize empty workload",
          B.summarize([], 1.0)["overall"] is None)


# ------------------------------------------------------------- ws codec


def test_codec():
    for opcode, payload in [(0x1, b"x"), (0x1, b"y" * 200),
                            (0x8, struct.pack(">H", 1000))]:
        raw = B.encode_frame(payload, opcode, mask_key=None)
        got = B.read_frame(io.BytesIO(raw))
        check("frame roundtrip len %d" % len(payload),
              got == (opcode, payload))
    # masked client frame -> the reader must refuse it
    masked = B.encode_frame(b"hi", 0x1, mask_key=b"\x01\x02\x03\x04")
    try:
        B.read_frame(io.BytesIO(masked))
        check("masked server frame refused", False)
    except ConnectionError:
        check("masked server frame refused", True)
    check("client frame is masked", bool(masked[1] & 0x80))
    opcode, unmasked = B.read_frame(io.BytesIO(masked), allow_masked=True)
    check("mask round-trips", unmasked == b"hi" and opcode == 0x1)
    big = b"z" * 300
    check("16-bit length used", B.encode_frame(big, 0x2, None)[1] == 126)
    huge = b"w" * 70000
    check("64-bit length used", B.encode_frame(huge, 0x2, None)[1] == 127)
    check("accept key matches the RFC example",
          B.ws_accept_key("dGhlIHNhbXBsZSBub25jZQ==")
          == "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")


# ------------------------------------------------ ws client vs loopback server


class MiniWsServer(threading.Thread):
    """A one-connection RFC 6455 server for exactly the behaviours the held
    client relies on: 101 with the computed accept key, answering a ping with
    its pong, noticing a client close, refusing a handshake."""

    def __init__(self, mode):
        super().__init__(daemon=True)
        self.mode = mode  # ping-then-close | refuse | hold
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.saw_pong = None
        self.saw_client_close = None
        self.key = None

    def run(self):
        try:
            conn, _addr = self.sock.accept()
        except OSError:
            return
        self.sock.close()
        reader = conn.makefile("rb")
        key = ""
        while True:
            line = reader.readline().decode("ascii", "replace")
            if line in ("\r\n", "\n", ""):
                break
            name, _, value = line.partition(":")
            if name.strip().lower() == "sec-websocket-key":
                key = value.strip()
        if self.mode == "refuse":
            conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            conn.close()
            return
        accept = B.ws_accept_key(key)
        conn.sendall((
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode("ascii"))
        if self.mode == "ping-then-close":
            conn.sendall(B.encode_frame(b"hb", 0x9, mask_key=None))
            try:
                opcode, payload = B.read_frame(reader, allow_masked=True)
                self.saw_pong = (opcode == 0xA and payload == b"hb")
            except (ConnectionError, OSError):
                self.saw_pong = False
            conn.sendall(B.encode_frame(struct.pack(">H", 1000), 0x8, None))
        elif self.mode == "hold":
            time.sleep(1.0)
            # read until the client closes; note its close frame
            try:
                opcode, _payload = B.read_frame(reader, allow_masked=True)
                self.saw_client_close = opcode == 0x8
            except (ConnectionError, OSError):
                self.saw_client_close = False
        time.sleep(0.2)
        conn.close()


def test_held_socket():
    server = MiniWsServer("ping-then-close")
    server.start()
    held = B.HeldSocket(0, "127.0.0.1", server.port, "/ws/default/?token=t",
                        "http://127.0.0.1").open()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and held.state == "open":
        time.sleep(0.05)
    check("peer close detected", held.state == "closed-by-peer",
          held.detail)
    check("ping answered with pong", server.saw_pong is True)
    check("handshake timed", held.handshake_s is not None
          and held.handshake_s < 2)
    held.close()

    server = MiniWsServer("refuse")
    server.start()
    refused = B.HeldSocket(0, "127.0.0.1", server.port, "/ws/default/",
                           "http://127.0.0.1").open()
    check("refused handshake is an error state",
          refused.state == "error" and "403" in refused.detail)

    server = MiniWsServer("hold")
    server.start()
    held = B.HeldSocket(0, "127.0.0.1", server.port, "/ws/default/",
                        "http://127.0.0.1").open()
    time.sleep(0.3)
    check("idle connection stays open", held.state == "open", held.detail)
    held.close()
    check("orderly client close", held.state == "closed")
    server.join(timeout=4)
    check("server saw the client close frame",
          server.saw_client_close is True)


# --------------------------------------------------------- profile resolver


def resolve(env):
    """Sources process_defaults.sh in a bare `sh` with the given environment
    and returns the values it exports (a compose environment that is unset
    arrives as an empty string, so "" must count as unset)."""
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update(env)
    script = (". '{path}'; printf \"%s|%s|%s|%s\" "
              "\"$GUNICORN_WORKERS\" \"$GUNICORN_THREADS\" "
              "\"$GUNICORN_WS_WORKERS\" \"$GUNICORN_PRELOAD_FLAG\""
              ).format(path=PROCESS_DEFAULTS)
    out = subprocess.run(  # nosec B602 - fixed command, env passed explicitly
        ["sh", "-c", script],
        capture_output=True, text=True, check=True, env=base)
    return out.stdout.split("|")


def test_process_defaults():
    check("default is the shipped production shape",
          resolve({}) == ["4", "4", "1", ""], resolve({}))
    check("empty compose passthrough counts as unset",
          resolve({"GUNICORN_WORKERS": "", "GUNICORN_THREADS": "",
                   "GUNICORN_WS_WORKERS": "", "GUNICORN_PRELOAD": "",
                   "MRMAP_LOW_MEMORY": ""}) == ["4", "4", "1", ""])
    check("low memory mode trades throughput",
          resolve({"MRMAP_LOW_MEMORY": "1"}) == ["1", "2", "1", ""],
          resolve({"MRMAP_LOW_MEMORY": "1"}))
    check("low memory switch is case-insensitive",
          resolve({"MRMAP_LOW_MEMORY": "TRUE"})[:2] == ["1", "2"])
    check("off words keep the production shape",
          resolve({"MRMAP_LOW_MEMORY": "false"}) == ["4", "4", "1", ""])
    check("explicit overrides win over the profile",
          resolve({"MRMAP_LOW_MEMORY": "1", "GUNICORN_WORKERS": "3",
                   "GUNICORN_THREADS": "8"}) == ["3", "8", "1", ""])
    check("preload is off by default",
          resolve({})[3] == "")
    check("preload opt-in yields the flag",
          resolve({"GUNICORN_PRELOAD": "on"})[3] == "--preload")
    check("resolver leaves no scratch exports",
          subprocess.run(  # nosec B603 - fixed argv
              ["sh", "-c", '. "%s"; [ -z "${_mrm_default_workers+set}" ] '
                           "|| exit 1" % PROCESS_DEFAULTS]).returncode == 0)


def test_startup_scripts_wiring():
    startup = (ROOT / "backend" / ".bash_scripts" / "startup.sh"
               ).read_text(encoding="utf-8")
    startup_ws = (ROOT / "backend" / ".bash_scripts" / "startup_ws.sh"
                  ).read_text(encoding="utf-8")
    check("http server sources the resolver",
          "source /opt/mrmap/.bash_scripts/process_defaults.sh" in startup)
    check("http server uses the resolved numbers",
          '--workers="$GUNICORN_WORKERS"' in startup
          and '--threads="$GUNICORN_THREADS"' in startup)
    check("preload flag reaches only the http server",
          "$GUNICORN_PRELOAD_FLAG" in startup
          and "GUNICORN_PRELOAD_FLAG" not in startup_ws)
    check("ws server sources the resolver",
          "source /opt/mrmap/.bash_scripts/process_defaults.sh"
          in startup_ws)
    check("ws server keeps the separate ASGI split (#1032)",
          "-k uvicorn.workers.UvicornWorker" in startup_ws
          and "0.0.0.0:8002" in startup_ws
          and "MrMap.asgi:application" in startup_ws)


# ---------------------------------------------------------- compose knobs


def _compose_backend_env():
    """The resolved env of the backend service, or None when this host has
    no docker CLI (the fallback check then reads the compose file as text)."""
    try:
        out = subprocess.run(  # nosec B603 - fixed argv
            ["docker", "compose", "-f", "docker-compose.yml",
             "config", "--no-interpolate", "--format", "json"],
            capture_output=True, text=True, timeout=120, cwd=ROOT)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    document = json.loads(out.stdout)
    env = document["services"]["backend"].get("environment") or {}
    if isinstance(env, list):
        env = dict(item.split("=", 1) for item in env)
    return env


def test_compose_passthrough():
    knobs = ["GUNICORN_WORKERS", "GUNICORN_THREADS", "GUNICORN_WS_WORKERS",
             "MRMAP_LOW_MEMORY", "GUNICORN_PRELOAD"]
    env = _compose_backend_env()
    if env is None:
        skip("compose backend env (docker compose config)",
             "docker CLI unavailable")
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for knob in knobs:
            check("compose passes %s through (%s)" % (knob, "text check"),
                  ("%s: ${%s:-}" % (knob, knob)) in text)
        return
    missing = [k for k in knobs if k not in env]
    check("compose passes every web tier knob through", not missing,
          "missing %s" % missing)
    pinned = [k for k in knobs if env.get(k) not in (None,
                                                     "${%s:-}" % k)]
    check("no knob is pinned to a default here (defaults live in the "
          "resolver)", not pinned, "pinned: %s" % pinned)
    check("no debug toolbar exposure: DJANGO_DEBUG is not set on the "
          "production backend", "DJANGO_DEBUG" not in env,
          str(env.get("DJANGO_DEBUG")))


# ------------------------------------------------------------------ report


def test_report_roundtrip():
    import tempfile
    record_load = {
        "kind": "load", "arm": "prod-4x4", "phase": "api-load",
        "http": {"overall": {"n": 3, "ok": 3, "errors": 0, "rps": 1.5,
                              "p50_ms": 10.0, "p95_ms": 30.0,
                              "p99_ms": 30.0, "max_ms": 30.0},
                 "status_hist": {"200": 3}, "by_endpoint": {}},
        "peer": {"overall": {"n": 2, "p50_ms": 5.0, "p95_ms": 6.0,
                             "p99_ms": 6.0, "max_ms": 6.0},
                 "status_hist": {}, "by_endpoint": {}},
        "ws": {"count": 2, "open_at_end": 2, "closed_early": 0,
               "closed_detail": [], "handshake": None},
    }
    record_boot = {"kind": "boot", "arm": "prod-4x4", "phase": "boot",
                   "first_response_s": 12.5, "ready_status": 200}
    parser = B.build_parser()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "runs.jsonl"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(record_load) + "\n")
            handle.write(json.dumps(record_boot) + "\n")
        args = parser.parse_args(["report", "--in", str(path)])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            rc = B.cmd_report(args)
        text = buffer.getvalue()
        check("report renders the load arm",
              rc == 0 and "prod-4x4" in text and "1.5" in text
              and "2/2" in text)
        check("report renders the boot arm", "12.5" in text)
        args = parser.parse_args(["report", "--in", str(path),
                                  "--kind", "boot"])
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            B.cmd_report(args)
        check("report --kind filters", "1.5" not in buffer.getvalue()
              and "12.5" in buffer.getvalue())


def main():
    test_stats()
    test_plan()
    test_summarize()
    test_codec()
    test_held_socket()
    test_process_defaults()
    test_startup_scripts_wiring()
    test_compose_passthrough()
    test_report_roundtrip()

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        if not ok:
            print("FAIL %s%s" % (name, (" - " + detail) if detail else ""))
    for name, reason in SKIPS:
        print("SKIP %s - %s" % (name, reason))
    print("%d checks, %d failed, %d skipped"
          % (len(RESULTS), len(failed), len(SKIPS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
