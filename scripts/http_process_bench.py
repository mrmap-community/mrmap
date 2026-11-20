#!/usr/bin/env python3
"""http_process_bench - workload generator for the web tier's process shapes.

Host-side benchmark tool carried by this repository (issue #1617, epic
#1612); run it as `python3 scripts/http_process_bench.py ...` from the
repository root. It exists so the comparison #1617 has to answer - what do
the gunicorn shapes of the deployed backend actually cost and deliver under
work - is reproducible instead of re-invented per measurement. It is a tool
of the checkout, not part of the deployed application, and it is stdlib
only: it runs wherever `python3` runs, beside `scripts/stack_memory_profile`
which supplies the RAM half of the same reading.

What one `load` phase answers, for one arm (one process shape of the web
tier) and one workload:

  - an HTTP workload: N requests spread over C keep-alive client threads
    over a set of weighted endpoints, with the per-request latency of every
    request, its status, the aggregate p50/p95/p99 and requests per second;
  - optionally, a cheap peer asked every interval through the whole phase
    (#1032's reading: an endpoint which does no work of its own must not
    pay for what its neighbours do; it walks the middleware chain and
    answers 404 on an idle server);
  - optionally, K long-lived authenticated websockets held open over the
    HTTP load phase: RFC6455 handshakes against the ASGI server's
    /ws/default/ with the knox token of `--credentials` in the query
    (notify.auth's documented token branch), an auto-pong reader per
    connection, and the answer to whether they all STAYED open - #1617's
    "no stuck websockets" acceptance is a measured closed_early count, not
    an assertion;
  - `wait-ready` times the boot: the seconds from the first probe until the
    server answers anything (a startup regression is visible right there);
  - `token` prints a knox token so a runbook can reuse it for other probes.

Every run appends ONE JSON line per phase to `--out`; `report` renders the
arm-per-row comparison table of a JSONL. Percentiles are nearest-rank over
the recorded latencies - with the few hundred samples a phase carries, the
simpler definition is honest and the offline suite pins it.

The tool measures the server it is pointed at and knows nothing about the
shape behind it; the arm label (`--arm prod-4x4`, `--arm low-memory-1x2`,
...) is what `report` groups by, and
`docs/source/development/http-process-profiles.rst` says how each arm was
started. Keep the data state behind the arms in `--notes` the way #1613's
baseline page does: the same endpoints answer different numbers on an empty
and a filled database, and an unlabelled arm is not reproducible.

Usage:
  python3 scripts/http_process_bench.py load  --arm LABEL --out runs.jsonl \
      [--base-url http://127.0.0.1:18001] [--ws-base-url http://127.0.0.1:18002] \
      --endpoint /api/keywords --endpoint /api/services:2 ... \
      [--requests N] [--concurrency C] [--timeout S] \
      [--peer-endpoint PATH] [--peer-interval S] \
      [--ws-count K --credentials user:pass] [--ws-hold S] [--ws-origin URL] \
      [--phase NAME] [--notes TEXT]
  python3 scripts/http_process_bench.py wait-ready --arm LABEL --out runs.jsonl \
      [--base-url ...] [--ready-path /api/auth/session] [--timeout S]
  python3 scripts/http_process_bench.py token --base-url ... --credentials user:pass
  python3 scripts/http_process_bench.py report --in runs.jsonl [--kind load]

Like the sampler's, its safety promise is scope: it only ever makes HTTP and
websocket requests to the addresses it is given, writes only `--out`, and
starts no container, restarts no service and reads no cgroup.
"""

import argparse
import base64
import hashlib
import http.client
import json
import os
import socket
import struct
import sys
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, urlparse

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

# seconds the websocket reader waits for a frame before deciding "nothing
# arrived, still open"; comfortably above uvicorn's 20 s ws_ping default so an
# idle held connection shows up as open, never as a phantom close
WS_READ_TIMEOUT_S = 30.0


def percentile(values, q):
    """Nearest-rank percentile (the ceil(q*n)-th of the sorted values)."""
    if not values:
        return None
    ordered = sorted(values)
    rank = int(-(-q * len(ordered) // 1))
    return ordered[min(rank - 1, len(ordered) - 1)]


def latency_stats(samples):
    """The numbers one group of latencies answers, in milliseconds."""
    if not samples:
        return None
    return {
        "n": len(samples),
        "p50_ms": round(percentile(samples, 0.50) * 1000, 1),
        "p95_ms": round(percentile(samples, 0.95) * 1000, 1),
        "p99_ms": round(percentile(samples, 0.99) * 1000, 1),
        "max_ms": round(max(samples) * 1000, 1),
    }


def parse_endpoint(spec):
    """`/api/keywords` or `/api/keywords*2` -> (path, weight)."""
    path, sep, weight = spec.rpartition("*")
    if not sep:
        return spec, 1
    try:
        return path, max(int(weight), 1)
    except ValueError:
        return spec, 1


def build_plan(specs, total):
    """Deterministic request plan: the weighted endpoint list cycled round
    robin up to `total` requests (default: one round), so two arms with the
    same arguments ask the same sequence of requests."""
    plan = []
    for spec in specs:
        path, weight = parse_endpoint(spec)
        plan.extend([path] * weight)
    if not plan:
        raise SystemExit("at least one --endpoint is required")
    if total and total > 0:
        reps = total // len(plan) + 1
        plan = (plan * reps)[:total]
    return plan


# --------------------------------------------------------------- token / login


def obtain_token(base_url, credentials, timeout=15):
    """POSTs the Basic credentials to /api/auth/login (#835) and returns the
    knox token the answer names."""
    url = _base(base_url)
    conn = _http_conn(url, timeout)
    try:
        auth = base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        conn.request("POST", "/api/auth/login", body=b"{}", headers={
            "Authorization": "Basic " + auth,
            "Content-Type": "application/json",
        })
        resp = conn.getresponse()
        payload = resp.read().decode("utf-8", "replace")
        if resp.status != 200:
            raise SystemExit("login refused with %s: %s"
                             % (resp.status, payload[:200]))
        return json.loads(payload)["token"]
    finally:
        conn.close()


def _http_conn(parsed, timeout):
    if parsed.scheme == "https":
        return http.client.HTTPSConnection(parsed.hostname,
                                           parsed.port or 443,
                                           timeout=timeout)
    if parsed.scheme != "http":
        raise SystemExit("unsupported scheme %r" % parsed.scheme)
    return http.client.HTTPConnection(parsed.hostname, parsed.port or 80,
                                      timeout=timeout)


def _base(url):
    parts = urlparse(url)
    if not parts.hostname:
        raise SystemExit("a url with a host is required, got %r" % url)
    return parts


# ------------------------------------------------------------------ websockets


def ws_accept_key(key):
    digest = hashlib.sha1((key + WS_GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(payload, opcode, mask_key=None):
    """One FIN frame; client-to-server frames must be masked (RFC 6455 5.3).
    mask_key None means "server frame" (the codec is shared with the test)."""
    head = bytearray()
    head.append(0x80 | opcode)
    length = len(payload)
    if length < 126:
        head.append(length)
    elif length < 65536:
        head.append(126)
        head.extend(struct.pack(">H", length))
    else:
        head.append(127)
        head.extend(struct.pack(">Q", length))
    if mask_key is None:
        return bytes(head) + payload
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    head[1] |= 0x80
    return bytes(head) + mask_key + masked


def read_frame(sock_reader, allow_masked=False):
    """Reads one frame -> (opcode, payload). Server frames must not be
    masked; a masked one is a protocol error and raises, unless the caller
    says it is reading a CLIENT frame (allow_masked - the loopback test
    server reads the benchmark's own frames this way). Data frames are read
    complete - continuation across frames is not implemented, which is fine
    for the pings, pongs and small JSON messages of this measurement."""
    head = _read_exactly(sock_reader, 2)
    b0, b1 = head[0], head[1]
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    if masked and not allow_masked:
        raise ConnectionError("server sent a masked frame")
    length = b1 & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exactly(sock_reader, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exactly(sock_reader, 8))[0]
    mask_key = _read_exactly(sock_reader, 4) if masked else None
    payload = _read_exactly(sock_reader, length) if length else b""
    if mask_key is not None:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload


def _read_exactly(sock_reader, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock_reader.read(n - len(buf))
        if not chunk:
            raise ConnectionError("connection closed mid-frame")
        buf.extend(chunk)
    return bytes(buf)


class HeldSocket:
    """One long-lived websocket kept open by the benchmark.

    The reader thread answers protocol-level pings (uvicorn's ws_ping default
    would otherwise close the connection and the phase would measure its own
    client instead of the server), records a peer-initiated close as
    closed-by-peer - the measured shape of a dropped/stuck websocket - and
    never mistakes the silence of an idle connection for either.
    """

    PING, PONG, CLOSE = 0x9, 0xA, 0x8
    TEXT, BINARY = 0x1, 0x2

    def __init__(self, index, host, port, path, origin, timeout=15):
        self.index = index
        self.host, self.port, self.path = host, port, path
        self.origin = origin
        self.timeout = timeout
        self.sock = None
        self.reader = None
        self.handshake_s = None
        self.state = "init"  # open | closed-by-peer | closed | error
        self.detail = ""
        self.frames = 0
        self.pings = 0
        self._stop = threading.Event()
        self._thread = None

    def open(self):
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        started = time.monotonic()
        self.sock = socket.create_connection((self.host, self.port),
                                             self.timeout)
        self.sock.settimeout(self.timeout)
        self.reader = self.sock.makefile("rb")
        request = "\r\n".join([
            "GET %s HTTP/1.1" % self.path,
            "Host: %s:%s" % (self.host, self.port),
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Key: %s" % key,
            "Sec-WebSocket-Version: 13",
            "Origin: %s" % self.origin,
            "", "",
        ])
        self.sock.sendall(request.encode("ascii"))
        status_line = self.reader.readline().decode("ascii", "replace")
        headers = {}
        while True:
            line = self.reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            name, _, value = line.decode("ascii", "replace").partition(":")
            headers[name.strip().lower()] = value.strip()
        if " 101 " not in status_line:
            self.state = "error"
            self.detail = status_line.strip()[:120]
            self.close_socket()
            return self
        if headers.get("sec-websocket-accept") != ws_accept_key(key):
            self.state = "error"
            self.detail = "bad Sec-WebSocket-Accept"
            self.close_socket()
            return self
        self.handshake_s = time.monotonic() - started
        self.state = "open"
        self.sock.settimeout(WS_READ_TIMEOUT_S)
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()
        return self

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                opcode, payload = read_frame(self.reader)
            except socket.timeout:
                continue  # idle silence is not a close
            except (ConnectionError, OSError) as exc:
                if not self._stop.is_set() and self.state == "open":
                    self.state = "closed-by-peer"
                    self.detail = str(exc)[:120]
                return
            if opcode == self.PING:
                self.pings += 1
                self._send(payload, self.PONG)
            elif opcode == self.CLOSE:
                if self.state == "open":
                    self.state = "closed-by-peer"
                    self.detail = "close frame from server"
                self._send(payload[:2], self.CLOSE)
                return
            elif opcode in (self.TEXT, self.BINARY):
                self.frames += 1

    def _send(self, payload, opcode):
        try:
            self.sock.sendall(encode_frame(payload, opcode, os.urandom(4)))
        except OSError:
            pass

    def close(self):
        """Asks for an orderly close; a connection the server had already
        dropped keeps its closed-by-peer state, which is the point."""
        if self.state == "open":
            self._send(struct.pack(">H", 1000), self.CLOSE)
            self.state = "closed"
        self._stop.set()
        self.close_socket()
        if self._thread:
            self._thread.join(timeout=3)

    def close_socket(self):
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass

    def summary(self):
        return {
            "handshake_ms": (round(self.handshake_s * 1000, 1)
                             if self.handshake_s is not None else None),
            "state": self.state,
            "detail": self.detail,
            "pings": self.pings,
            "frames": self.frames,
        }


def open_websockets(ws_base, token, count, origin=""):
    parsed = _base(ws_base)
    origin = origin or ws_base.rstrip("/")
    path = "/ws/default/"
    if token:
        path += "?" + urlencode({"token": token})
    return [HeldSocket(index, parsed.hostname, parsed.port or 80, path,
                       origin).open()
            for index in range(count)]


# ---------------------------------------------------------------- HTTP workload


class HttpWorker(threading.Thread):
    """One keep-alive client of the load phase. Requests are taken from a
    shared, lock-guarded counter over the deterministic request plan."""

    def __init__(self, parsed, plan, counter, lock, timeout, results):
        super().__init__(daemon=True)
        self.parsed, self.plan = parsed, plan
        self.counter, self.lock = counter, lock
        self.timeout, self.results = timeout, results

    def run(self):
        conn = None
        while True:
            with self.lock:
                index = self.counter[0]
                if index >= len(self.plan):
                    return
                self.counter[0] = index + 1
            path = self.plan[index]
            started = time.monotonic()
            try:
                if conn is None:
                    conn = _http_conn(self.parsed, self.timeout)
                conn.request("GET", path, headers={
                    "Connection": "keep-alive", "Accept": "*/*"})
                resp = conn.getresponse()
                resp.read()
                self.results.append((path, resp.status,
                                     time.monotonic() - started))
            except Exception as exc:  # a refused/broken keep-alive is a miss
                self.results.append(("#error", 0, repr(exc)[:80]))
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None


class PeerProber(threading.Thread):
    """#1032's cheap peer: one unrouted request every interval, through the
    whole phase. It measures whether an idle-cheap endpoint pays for the
    work its neighbours do."""

    def __init__(self, parsed, path, interval, stop, timeout, results):
        super().__init__(daemon=True)
        self.parsed, self.path, self.interval = parsed, path, interval
        self.stop, self.timeout, self.results = stop, timeout, results

    def run(self):
        conn = None
        while not self.stop.is_set():
            started = time.monotonic()
            try:
                if conn is None:
                    conn = _http_conn(self.parsed, self.timeout)
                conn.request("GET", self.path,
                             headers={"Connection": "keep-alive"})
                resp = conn.getresponse()
                resp.read()
                self.results.append((self.path, resp.status,
                                     time.monotonic() - started))
            except Exception:
                self.results.append((self.path, 0, 0.0))
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
            self.stop.wait(self.interval)


def summarize(results, elapsed):
    """The aggregate numbers of one workload's (path, status, latency) list;
    #error rows carry a message where a latency would sit and are counted,
    never timed."""
    answered = [r for r in results if r[0] != "#error"]
    errors = len(results) - len(answered)
    latencies = [r[2] for r in answered]
    ok = [r for r in answered if r[1] < 400]
    status_hist = {}
    by_endpoint = {}
    for path, status, _lat in answered:
        key = str(status)
        status_hist[key] = status_hist.get(key, 0) + 1
        by_endpoint.setdefault(path, []).append((status, _lat))
    stats = latency_stats(latencies)
    if not stats:
        return {"overall": None, "status_hist": {}, "by_endpoint": {}}
    stats["rps"] = round(len(answered) / elapsed, 2) if elapsed else None
    stats["ok"] = len(ok)
    stats["errors"] = errors + len(answered) - len(ok)
    endpoints = {}
    for path, rows in by_endpoint.items():
        st = latency_stats([lat for _status, lat in rows])
        st["status"] = {}
        for status, _lat in rows:
            key = str(status)
            st["status"][key] = st["status"].get(key, 0) + 1
        endpoints[path] = st
    return {"overall": stats, "status_hist": status_hist,
            "by_endpoint": endpoints}


# ------------------------------------------------------------------ subcommands


def cmd_load(args):
    parsed = _base(args.base_url)
    plan = build_plan(args.endpoint, args.requests)
    token = args.token
    if not token and args.credentials and (args.ws_count
                                           or args.print_token):
        token = obtain_token(args.base_url, args.credentials)

    ws_sockets = []
    if args.ws_count:
        if not token:
            raise SystemExit("--ws-count needs --token or --credentials")
        ws_sockets = open_websockets(args.ws_base_url or args.base_url,
                                     token, args.ws_count, args.ws_origin)

    results = []
    peer_results = []
    stop_peer = threading.Event()
    counter = [0]
    lock = threading.Lock()
    started = time.monotonic()
    if args.peer_endpoint:
        PeerProber(parsed, args.peer_endpoint, args.peer_interval,
                   stop_peer, args.timeout, peer_results).start()
    workers = [HttpWorker(parsed, plan, counter, lock, args.timeout, results)
               for _ in range(args.concurrency)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    elapsed = time.monotonic() - started

    # the websockets stay open at least --ws-hold seconds overall: a phase
    # whose HTTP load finished early keeps them up until the hold is over,
    # because "long-lived" is measured in wall time, not in request counts
    hold_left = max(args.ws_hold - elapsed, 0)
    if hold_left and ws_sockets:
        time.sleep(hold_left)
    total_s = time.monotonic() - started
    if args.peer_endpoint:
        stop_peer.set()

    still_open = sum(1 for s in ws_sockets if s.state == "open")
    closed_early = [s for s in ws_sockets if s.state != "open"]
    for sock in ws_sockets:
        sock.close()

    record = {
        "kind": "load",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arm": args.arm, "phase": args.phase, "notes": args.notes,
        "base_url": args.base_url,
        "endpoints": args.endpoint, "requests": len(plan),
        "concurrency": args.concurrency,
        "elapsed_s": round(elapsed, 3), "total_s": round(total_s, 3),
        "http": summarize(results, elapsed),
        "peer": (summarize(peer_results, total_s)
                 if args.peer_endpoint else None),
        "ws": None if not ws_sockets else {
            "count": len(ws_sockets),
            "open_at_end": still_open,
            "closed_early": len(closed_early),
            "closed_detail": [s.summary() for s in closed_early][:5],
            "handshake": latency_stats(
                [s.handshake_s for s in ws_sockets
                 if s.handshake_s is not None]),
        },
    }
    _append_record(args.out, record)
    overall = record["http"]["overall"] or {}
    print("arm=%s phase=%s ok=%s err=%s rps=%s p95=%sms ws=%s/%s" % (
        args.arm, args.phase, overall.get("ok"), overall.get("errors"),
        overall.get("rps"), overall.get("p95_ms"), still_open,
        len(ws_sockets)))
    return 0


def cmd_wait_ready(args):
    parsed = _base(args.base_url)
    started = time.monotonic()
    status = None
    while time.monotonic() - started < args.timeout:
        try:
            conn = _http_conn(parsed, 5)
            conn.request("GET", args.ready_path, headers={
                "Connection": "close"})
            resp = conn.getresponse()
            resp.read()
            status = resp.status
            conn.close()
            break
        except Exception:
            time.sleep(args.interval)
    elapsed = time.monotonic() - started
    _append_record(args.out, {
        "kind": "boot",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "arm": args.arm, "phase": args.phase, "notes": args.notes,
        "base_url": args.base_url, "ready_path": args.ready_path,
        "first_response_s": round(elapsed, 2),
        "ready_status": status,
    })
    print("arm=%s boot=%ss status=%s" % (args.arm, round(elapsed, 2), status))
    return 0 if status else 1


def cmd_report(args):
    kind = args.kind or None
    rows = []
    with open(args.infile, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if kind is None or record.get("kind") == kind:
                rows.append(record)
    print("%-22s %-10s %6s %5s %7s %8s %8s %8s %8s %6s" % (
        "arm", "phase", "ok", "err", "rps", "p50", "p95", "p99",
        "peer95", "ws"))
    for row in rows:
        if row.get("kind") != "load":
            continue
        overall = (row.get("http") or {}).get("overall") or {}
        peer = ((row.get("peer") or {}).get("overall") or {})
        ws = row.get("ws")
        ws_cell = ("%s/%s" % (ws["open_at_end"], ws["count"]) if ws else "-")
        print("%-22s %-10s %6s %5s %7s %8s %8s %8s %8s %6s" % (
            row.get("arm", "?"), row.get("phase", "?"),
            overall.get("ok", "-"), overall.get("errors", "-"),
            overall.get("rps", "-"), overall.get("p50_ms", "-"),
            overall.get("p95_ms", "-"), overall.get("p99_ms", "-"),
            peer.get("p95_ms", "-"), ws_cell))
    print("%-22s %-10s %10s %8s" % ("arm", "phase", "boot_s", "status"))
    for row in rows:
        if row.get("kind") != "boot":
            continue
        print("%-22s %-10s %10s %8s" % (
            row.get("arm", "?"), row.get("phase", "?"),
            row.get("first_response_s", "-"), row.get("ready_status", "-")))
    return 0


def _append_record(path, record):
    if not path:
        print(json.dumps(record, indent=2))
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def build_parser():
    parser = argparse.ArgumentParser(prog="http_process_bench")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--arm", required=True,
                        help="label of the process shape under test")
    common.add_argument("--phase", default="load",
                        help="name of this workload phase")
    common.add_argument("--notes", default="",
                        help="what the arms share (data state, host, image)")
    common.add_argument("--out", default="",
                        help="JSONL to append this record to")
    common.add_argument("--base-url", default="http://127.0.0.1:18001")
    sub = parser.add_subparsers(dest="command", required=True)

    load = sub.add_parser("load", parents=[common], help="run one workload")
    load.add_argument("--endpoint", action="append", required=True,
                      help="path, repeatable; PATH*WEIGHT to weight it")
    load.add_argument("--requests", type=int, default=0,
                      help="requests overall (default: one round of the "
                           "weighted endpoint plan)")
    load.add_argument("--concurrency", type=int, default=4)
    load.add_argument("--timeout", type=float, default=30.0)
    load.add_argument("--peer-endpoint", default="",
                      help="cheap peer asked every --peer-interval seconds")
    load.add_argument("--peer-interval", type=float, default=1.0)
    load.add_argument("--ws-base-url", default="",
                      help="ASGI server of /ws (default: --base-url)")
    load.add_argument("--ws-count", type=int, default=0)
    load.add_argument("--ws-hold", type=float, default=30.0,
                      help="minimum seconds the websockets stay open")
    load.add_argument("--ws-origin", default="",
                      help="Origin header of the handshake "
                           "(AllowedHostsOriginValidator checks it)")
    load.add_argument("--token", default="",
                      help="knox token for the websockets")
    load.add_argument("--credentials", default="",
                      help="user:pass for /api/auth/login (token fetch)")
    load.add_argument("--print-token", action="store_true",
                      help="print the fetched knox token (runbook seam)")

    ready = sub.add_parser("wait-ready", parents=[common],
                           help="time the boot until the first HTTP answer")
    ready.add_argument("--ready-path", default="/api/auth/session")
    ready.add_argument("--timeout", type=float, default=180.0)
    ready.add_argument("--interval", type=float, default=0.5)

    token = sub.add_parser("token", help="print a knox token")
    token.add_argument("--base-url", required=True)
    token.add_argument("--credentials", required=True)

    report = sub.add_parser("report", help="render the arms of a JSONL")
    report.add_argument("--in", dest="infile", required=True)
    report.add_argument("--kind", choices=["load", "boot", ""], default="")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == "load":
        return cmd_load(args)
    if args.command == "wait-ready":
        return cmd_wait_ready(args)
    if args.command == "token":
        print(obtain_token(args.base_url, args.credentials))
        return 0
    if args.command == "report":
        return cmd_report(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
