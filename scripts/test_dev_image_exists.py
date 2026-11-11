#!/usr/bin/env python3
"""Offline tests for `dev_image_id.py --exists` (issue #1077).

Run from the repository root:  python3 scripts/test_dev_image_exists.py
Needs no docker, no gh and no network: the registry is a stdlib HTTP server on
127.0.0.1 that answers by scenario, one scenario per tag name, chosen by the
test before each ask. Only the three opt-in live cases (MRMAP_TEST_LIVE=1) talk
to ghcr.io.

What these checks hold onto is the one thing the probe can get expensively
wrong: the difference between "the tag is not there" (exit 3, go build it) and
"I could not look" (exit 4, ask again). ghcr answers BOTH with 404 and the code
MANIFEST_UNKNOWN, so the scenarios are arranged around that. `accept-quirk`
reproduces the measured registry behaviour that turns a PUBLISHED tag into a 404
for a wildcard or a docker media type, so it must still exit 0;
`answer-changed` is the same 404 from a registry that no longer answers this
request shape at all, and must never exit 3.

Exit code 0 = all ran checks passed.
"""

import importlib.util
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
REPO = "ghcr.io/mrmap-community/mrmap-backend-dev"
REPO_PATH = "mrmap-community/mrmap-backend-dev"

_spec = importlib.util.spec_from_file_location("dev_image_id", SCRIPTS / "dev_image_id.py")
dev_image_id = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev_image_id)

RESULTS = []
REQUESTS = []                     # one dict per registry request, appended by the handler
CURRENT = {"tag": "published"}    # the scenario the token half answers for

MANIFEST = json.dumps({
    "schemaVersion": 2,
    "mediaType": "application/vnd.oci.image.manifest.v1+json",
    "config": {"mediaType": "application/vnd.oci.image.config.v1+json",
               "digest": "sha256:cafe", "size": 900},
    "layers": [{"digest": "sha256:f00d", "size": 1}],
}).encode()
UNKNOWN = b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown"}]}\n'
WRONG_TYPE = (b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"OCI manifest found, '
              b'but Accept header does not support OCI manifests"}]}\n')

# The rule measured against ghcr.io on 2026-11-05 for both mrmap dev packages:
# the tags are OCI manifests and are served only to a header naming that type.
# */*, an empty header and the docker distribution types answer 404 with the
# WRONG_TYPE body; a list that contains the type answers 200.
OCI_TYPE = "application/vnd.oci.image.manifest.v1+json"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def serves_oci_manifest(accept):
    """ghcr's measured Accept rule, as the `accept-quirk` scenario applies it."""
    return any(part.strip() == OCI_TYPE for part in (accept or "").split(","))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):        # silence the per-request print
        pass

    def _send(self, status, body=b"", content_type="application/json", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/token"):
            query = parse_qs(urlparse(self.path).query)
            REQUESTS.append({"kind": "token", "path": self.path,
                             "scope": (query.get("scope") or [""])[0],
                             "service": (query.get("service") or [""])[0],
                             "accept": self.headers.get("Accept"),
                             "authorization": self.headers.get("Authorization")})
            tag = CURRENT["tag"]
            if tag == "token-denied":
                return self._send(401, UNKNOWN)
            if tag == "no-token":
                return self._send(200, b'{"token": ""}')
            if tag == "token-is-html":
                return self._send(200, b"<html>login first</html>")
            return self._send(200, json.dumps({"token": "anonymous-pull-token"}).encode())

        if self.path.startswith("/v2/") and "/manifests/" in self.path:
            tag = self.path.rsplit("/manifests/", 1)[1]
            REQUESTS.append({"kind": "manifest", "path": self.path,
                             "accept": self.headers.get("Accept"),
                             "authorization": self.headers.get("Authorization")})
            if tag == "answer-changed":
                # a registry that stopped answering this request shape: 404,
                # MANIFEST_UNKNOWN, and only the message says why
                return self._send(404, WRONG_TYPE)
            if tag == "manifest-denied":
                return self._send(403, UNKNOWN)
            if tag == "server-error":
                return self._send(500, b"internal error")
            if tag == "rate-limited":
                return self._send(429, b"too many requests")
            if tag == "body-is-html":
                return self._send(200, b"<html>a proxy said no</html>", "text/html")
            if tag == "truncated-body":
                self.send_response(200)
                self.send_header("Content-Length", "5000")
                self.end_headers()
                self.wfile.write(MANIFEST[:12])
                self.close_connection = True
                return None
            if tag == "not-http":
                self.connection.sendall(b"warming up, please wait\r\n\r\n")
                self.close_connection = True
                return None
            if tag == "slow":
                time.sleep(3)
                return self._send(200, MANIFEST, extra={"Docker-Content-Digest": "sha256:cafe"})
            if tag == "accept-quirk":
                if not serves_oci_manifest(self.headers.get("Accept")):
                    return self._send(404, WRONG_TYPE)
                return self._send(200, MANIFEST, extra={"Docker-Content-Digest": "sha256:cafe"})
            if tag == "published":
                return self._send(200, MANIFEST, extra={"Docker-Content-Digest": "sha256:cafe"})
            return self._send(404, UNKNOWN)

        return self._send(404, UNKNOWN)


class _Server(ThreadingHTTPServer):
    """A registry stub that keeps a handler's own failure to itself.

    The slow scenario's write lands after the client has given up, and the
    resulting traceback would be printed into the middle of the test's own
    report by the default handle_error - noise that reads like a failure.
    """

    def handle_error(self, request, client_address):
        pass


class Registry:
    """A registry answering by tag name, so a scenario is one flag on the call."""

    def __init__(self):
        self.server = _Server(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return f"http://127.0.0.1:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


BIN = None
SIDE_EFFECTS = None


def fake_host_bin():
    """A PATH entry whose docker and gh record any call: the probe must never reach them."""
    global BIN, SIDE_EFFECTS
    BIN = tempfile.mkdtemp(prefix="mrmap-exists-no-docker-")
    SIDE_EFFECTS = Path(BIN) / "host-tools-were-called"
    for name, mark in (("docker", "docker"), ("gh", "gh")):
        script = Path(BIN) / name
        script.write_text(f"#!/bin/sh\nprintf {mark} >> {SIDE_EFFECTS}\nexit 0\n")
        script.chmod(0o755)


def probe_argv(*extra, base=None, timeout=None):
    argv = [sys.executable, str(SCRIPTS / "dev_image_id.py"), "--exists",
            "--image", "backend", "--repo", REPO]
    if base:
        argv += ["--registry-base", base]
    if timeout is not None:
        argv += ["--timeout", str(timeout)]
    return argv + list(extra)


def host_env(env_extra=None):
    env = dict(os.environ)
    env.pop(dev_image_id.MUTABLE_OPT_OUT_ENV, None)
    env["PATH"] = f"{BIN}{os.pathsep}{env.get('PATH', '')}"
    if env_extra:
        env.update(env_extra)
    return env


def ask(base, *extra, env_extra=None, timeout=None):
    """One probe run against the stub; returns (rc, stdout, stderr)."""
    proc = subprocess.run(probe_argv(*extra, base=base, timeout=timeout),
                          capture_output=True, text=True, timeout=120,
                          cwd=ROOT, env=host_env(env_extra))
    return proc.returncode, proc.stdout, proc.stderr


def scenario(base, tag, expect_rc, name, want_in_stderr=(), want_not_in_stderr=(),
             timeout=None, env_extra=None):
    """One ask, its exit code, and what the answer had to say (and must not)."""
    REQUESTS.clear()
    CURRENT["tag"] = tag
    rc, out, err = ask(base, "--fp", tag, timeout=timeout, env_extra=env_extra)
    check(f"{name}: exit {expect_rc}", rc == expect_rc, f"rc={rc} stderr={err[-260:]}")
    check(f"{name}: stdout is exactly the asked tag", out.strip() == tag, repr(out))
    for want in want_in_stderr:
        check(f"{name}: says {want!r}", want in err, err[-260:])
    for avoid in want_not_in_stderr:
        check(f"{name}: does NOT say {avoid!r}", avoid not in err, err[-260:])
    return rc, out, err


def last(kind):
    return next((r for r in REQUESTS if r["kind"] == kind), None)


def probe_checks(base):
    # ---- the two answers that are statements about the tag ------------------
    scenario(base, "published", 0, "published tag",
             want_in_stderr=("is published", "sha256:cafe", "existence only"),
             want_not_in_stderr=("is not published",))
    manifest, token = last("manifest"), last("token")
    check("a published ask is exactly two requests",
          len(REQUESTS) == 2 and token and manifest, str(REQUESTS))
    check("the token grant is anonymous",
          token is not None and token["authorization"] is None, str(token))
    check("the token scope asks for pull on this repository only",
          token is not None and token["scope"] == f"repository:{REPO_PATH}:pull", str(token))
    check("the token grant names this registry as its service",
          token is not None and token["service"] == "127.0.0.1", str(token))
    check("the manifest request names exactly one media type",
          manifest is not None and manifest["accept"] == OCI_TYPE, str(manifest))
    check("the manifest request carries the token as Bearer",
          manifest is not None and (manifest["authorization"] or "").startswith("Bearer "),
          str(manifest))
    check("the manifest request addresses the tag under the repository path",
          manifest is not None
          and manifest["path"] == f"/v2/{REPO_PATH}/manifests/published", str(manifest))

    scenario(base, "absent", 3, "a tag that was never published",
             want_in_stderr=("is not published", "never published"),
             want_not_in_stderr=("is published as manifest",))

    # ---- the Accept quirk: a published tag disappears for a wildcard, so the
    #      probe sends the one type the registry serves it under
    scenario(base, "accept-quirk", 0, "the registry's own Accept rule",
             want_in_stderr=("is published",))
    check("the ask that survives the quirk still names the OCI manifest type",
          (last("manifest") or {}).get("accept") == OCI_TYPE, str(last("manifest")))

    # ---- everything else is "could not look", exit 4 and never exit 3 -------
    scenario(base, "answer-changed", 4, "a 404 that does not say 'manifest unknown'",
             want_in_stderr=("NOT read as",),
             want_not_in_stderr=("is not published",))
    scenario(base, "token-denied", 4, "an anonymous token grant that is refused",
             want_in_stderr=("cannot look", "private"),
             want_not_in_stderr=("is not published",))
    scenario(base, "manifest-denied", 4, "a manifest read that is refused",
             want_in_stderr=("refuses an anonymous read", "refused is not absent"),
             want_not_in_stderr=("is not published",))
    scenario(base, "server-error", 4, "a registry that answers 500",
             want_in_stderr=("could not look",))
    scenario(base, "rate-limited", 4, "a registry that answers 429",
             want_in_stderr=("could not look",))
    scenario(base, "body-is-html", 4, "a 200 whose body is not a manifest",
             want_in_stderr=("not a manifest",), want_not_in_stderr=("is not published",))
    scenario(base, "truncated-body", 4, "a response shorter than its Content-Length",
             want_in_stderr=("not a manifest",), want_not_in_stderr=("is not published",
                                                                     "is published as manifest"))
    scenario(base, "not-http", 4, "a response that is not HTTP at all",
             want_in_stderr=("could not look",), want_not_in_stderr=("is not published",))
    scenario(base, "no-token", 4, "a token grant that carries no token",
             want_in_stderr=("cannot look", "carried no token"))
    scenario(base, "token-is-html", 4, "a token grant that is not JSON",
             want_in_stderr=("cannot look",))
    scenario(base, "slow", 4, "a registry that answers too late",
             want_in_stderr=("could not look",), timeout=0.5)

    check("the probe never calls docker or gh",
          SIDE_EFFECTS is not None and not SIDE_EFFECTS.exists(),
          SIDE_EFFECTS.read_text() if SIDE_EFFECTS and SIDE_EFFECTS.exists() else "")


def other_checks(base):
    # no listener behind the port: unreachable, and still not "not published"
    idle = socket.socket()
    idle.bind(("127.0.0.1", 0))
    idle.listen(1)
    port = idle.getsockname()[1]
    idle.close()
    REQUESTS.clear()
    CURRENT["tag"] = "published"
    rc, _out, err = ask(f"http://127.0.0.1:{port}", "--fp", "published")
    check("a registry that is not there exits 4", rc == 4, f"rc={rc} {err[-200:]}")
    check("and says it could not look, not that the tag is gone",
          "cannot look" in err and "is not published" not in err, err[-220:])

    # the human opt-out makes --resolve exit 0 without looking at anything; it
    # must not touch a question about one exact tag (the CI gate strips it for
    # exactly that reason, and --exists is the cheaper question of the same kind)
    rc, _out, err = ask(base, "--fp", "absent",
                        env_extra={dev_image_id.MUTABLE_OPT_OUT_ENV: "1"})
    check("the mutable-image opt-out does not turn --exists into a yes",
          rc == 3 and "OPT-OUT" not in err, f"rc={rc} {err[-200:]}")

    # an unusable tag is refused before any request goes out
    for bad in ("with space", "x" * 200, "-leading-dash", "semi;colon"):
        REQUESTS.clear()
        proc = subprocess.run(probe_argv("--fp", bad, base=base), capture_output=True,
                              text=True, timeout=60, cwd=ROOT)
        check(f"--fp {bad[:14]!r} is refused before the registry is asked",
              proc.returncode != 0 and not REQUESTS,
              f"rc={proc.returncode} requests={len(REQUESTS)}")

    # asking about this checkout's own fingerprint is the default, and what the
    # probe prints is what it asked about
    fp = dev_image_id.fingerprint(ROOT, "backend")
    rc, out, err = ask(base)
    check("with no --fp the checkout's fingerprint is the tag",
          rc == 3 and out.strip() == fp, f"rc={rc} stdout={out!r} {err[-160:]}")

    # --exists must not need docker even where --resolve would
    proc = subprocess.run(probe_argv("--fp", "published", base=base), capture_output=True,
                          text=True, timeout=120, cwd=ROOT,
                          env=host_env({"PATH": str(BIN)}))
    check("--exists runs on a PATH that has neither docker nor coreutils",
          proc.returncode == 0, f"rc={proc.returncode} {proc.stderr[-200:]}")


def live_checks():
    """The same statements against the real registry (opt-in, read-only)."""
    for image in ("backend", "frontend"):
        started = time.monotonic()
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "dev_image_id.py"), "--exists", "--image", image],
            capture_output=True, text=True, timeout=120, cwd=ROOT)
        took = time.monotonic() - started
        check(f"live: ghcr.io serves the {image} fingerprint, exit 0",
              proc.returncode == 0, f"rc={proc.returncode} {proc.stderr[-200:]}")
        check(f"live: the {image} ask costs far less than a pull", took < 10, f"{took:.2f}s")
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "dev_image_id.py"), "--exists", "--image", "backend",
         "--fp", "000000000000"], capture_output=True, text=True, timeout=120, cwd=ROOT)
    check("live: a fingerprint that was never published exits 3",
          proc.returncode == 3 and "is not published" in proc.stderr,
          f"rc={proc.returncode} {proc.stderr[-200:]}")


def main():
    print(f"dev_image_id --exists tests against a local stub registry, on {ROOT}")
    fake_host_bin()
    registry = Registry()
    try:
        probe_checks(registry.base)
        other_checks(registry.base)
        if os.environ.get("MRMAP_TEST_LIVE") == "1":
            live_checks()
        else:
            print("SKIP  the three live ghcr.io cases (set MRMAP_TEST_LIVE=1)")
    finally:
        registry.close()

    width = max(len(name) for name, _, _ in RESULTS)
    failed = [(name, detail) for name, ok, detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name:<{width}}"
        if not ok and detail:
            line += f"   <- {detail}"
        print(line)
    if failed:
        print(f"FAILED ({len(failed)} of {len(RESULTS)} checks)", file=sys.stderr)
        return 1
    print(f"OK ({len(RESULTS)} checks; skips marked above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
