#!/usr/bin/env python3
"""nginx_routing_smoke: does the frontend's nginx answer a URL, or proxy it?

Host-side check carried by this repository; run it as `python3
scripts/nginx_routing_smoke.py` from the repository root. Standard library only,
plus the local `docker` CLI. No credentials and no registry are needed: the one
image it runs is the nginx base image of `docker/nginx/nginx.Dockerfile`, so it
is normally cached already. Exit 0 when every URL lands where it belongs, 1 when
one does not, 2 when the harness itself could not run.

Nothing runs it on its own yet: `.github/workflows/` is a person's file, so the
`nginx-routing` job of `quality-assurance.yml` which would run it on every change
is proposed on #1036 for a person to add. Until then it is the check to run before
touching `docker/nginx/mrmap.conf`.

Why routing is checked in nginx, and nowhere else
-------------------------------------------------
`docker/nginx/mrmap.conf` is the only unit that decides whether a URL is answered
by the SPA or proxied to Django, and that decision is invisible to every suite
this repository has: Django's tests and Behave run *behind* nginx, the frontend's
own tests run *in front of* it, and the `frontend-tests` container does not even
mount the file. A wrong decision has no traceback either - the browser simply
gets a page that is not the application.

Issue #1036 is that failure. Its location read `^/(api|csw|ws|django-admin|
mrmap-proxy|media/)`, which matches any path that merely *starts* with one of the
words, so `/csw-client` - a registered frontend route whose name happens to begin
with "csw" - went to Django and came back as Django's own 404. The page could not
be reloaded, bookmarked or shared, and no suite noticed, because the path works
fine as long as nobody enters it in the address bar.

How it works
------------
One disposable network and two containers on it:

  * the *edge*: this checkout's `docker/nginx/mrmap.conf`, mounted at the path
    `docker-compose.yml` mounts it at, on the nginx base image of the frontend
    image. Its SPA root holds a stub `index.html` and the real `error-beacon.js`
    - what is under test is which `location` answers, not what the built app
    renders, so nothing has to be compiled.
  * the *backend*: the same image with a three line server that answers 200 with
    `backend-stub <uri>` for every path, on the name and port the conf resolves
    (`backend:8001`). A proxied URL is then proven by that echo - including the
    path it was forwarded with - rather than inferred from a 502 that merely says
    nothing was listening.

One GET per row of CASES below, read from the published loopback port. The
shell's body and the stub's echo are compared literally, so a URL that moves from
one side of the conf to the other fails here with both bodies side by side.

When to add a row
-----------------
The SPA rows are the hand-written routes of
`frontend/src/components/MrMapFrontend.tsx`; react-admin derives more of them
from the schema and any one of those may one day start with a proxied prefix. A
new frontend route whose name begins with one of them - the shape of #1036 -
belongs in this table, because that is precisely the case nginx gets wrong
without anyone noticing.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONF = ROOT / "docker" / "nginx" / "mrmap.conf"
BEACON = ROOT / "docker" / "nginx" / "error-beacon.js"
FRONTEND_DOCKERFILE = ROOT / "docker" / "nginx" / "nginx.Dockerfile"

# The app shell, as far as this harness is concerned: whichever location serves
# this file served the SPA fallback.
SPA_BODY = "<html><body>mrmap-nginx-smoke-spa-shell</body></html>\n"

# Answers the conf's proxy target. `$uri` is the decoded path without the query
# string, so a case states its expectation as the path it requested.
STUB_BACKEND_CONF = """
server {
    listen 8001;
    location / {
        default_type text/plain;
        return 200 "backend-stub $uri\\n";
    }
}
"""

SPA = "spa"
BACKEND = "backend"
DENY = "deny"

# (kind, path, argument) - SPA: the shell answers; BACKEND: the upstream echoes
# the requested path back, without its query string; DENY: this status answers
# and it is not the shell.
CASES = [
    # Application routes belong to the SPA. /csw-client is #1036 itself: it
    # starts with the proxied word "csw" and must still not be proxied.
    (SPA, "/"),
    (SPA, "/csw-client"),
    (SPA, "/csw-client/"),
    (SPA, "/service-explorer"),
    (SPA, "/viewer"),
    (SPA, "/search"),
    (SPA, "/definitely-not-a-route"),

    # The backend mounts, each with the separator that keeps them apart from the
    # routes above. /csw is the mount without one of its own (the CSW endpoint is
    # registered exactly at "csw" in backend/MrMap/urls.py), so both its exact
    # form and its subtree are proxied while /csw-client stays with the SPA.
    (BACKEND, "/api/schema"),
    (BACKEND, "/api/registry/resources"),
    (BACKEND, "/api/auth/login"),
    (BACKEND, "/csw"),
    (BACKEND, "/csw/"),
    # The way a client actually calls the CSW endpoint. The query string is not
    # part of a location match, and the upstream is asked for the path alone.
    (BACKEND, "/csw?service=CSW&request=GetRecords"),
    (BACKEND, "/ws/default/"),
    (BACKEND, "/django-admin/login/"),
    (BACKEND, "/mrmap-proxy/ows/1"),
    (BACKEND, "/media/some-upload"),

    # Answered by nginx itself, before both of the two above.
    (DENY, "/api/system/error", 204),   # the error beacon of #942, exact match
    (DENY, "/media/logs/a-dump.sql", 404),   # slow request dumps, #888
    (DENY, "/assets/does-not-exist.js", 404),  # hashed bundles, #942

    # The answer of today, not the wanted one: the nested asset rule of
    # `location /` is judged at a deeper level than the proxy regex above, so it
    # intercepts every proxied URL whose last segment ends in .png, .json, .js or
    # another asset extension, before that regex is consulted at all. Measured
    # identically on the conf this change replaces, so nothing here causes or
    # cures it - #1110 is about it, and this row moves to BACKEND with that fix.
    (DENY, "/media/some-upload.png", 404),
]

READINESS_TIMEOUT_S = 25.0


class HarnessError(Exception):
    """The check could not be run at all - a missing docker, a container that
    never came up. Kept apart from a routing failure, which is a real answer to
    the question the check asks."""


def docker(*args, check=True):
    """Run the docker CLI and return its stdout, or raise with its stderr."""
    try:
        process = subprocess.run(["docker", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise HarnessError("the docker CLI is not on PATH")
    if check and process.returncode != 0:
        raise HarnessError(
            f"docker {' '.join(args)} exited {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}"
        )
    return process.stdout.strip()


def nginx_image():
    """The nginx tag the frontend image is built on, so this checks the nginx
    which actually serves the app instead of whatever is newest on the host."""
    tags = re.findall(r"(?m)^FROM\s+(nginx:\S+)",
                      FRONTEND_DOCKERFILE.read_text())
    if not tags:
        raise HarnessError(
            f"no nginx base image found in {FRONTEND_DOCKERFILE}")
    return tags[-1]


def labels():
    """Track what this run started, so the orchestrator can find it (#1036
    harnesses are disposable and must never outlive their session)."""
    out = ["--label", "ao.tool=nginx-routing-smoke"]
    session = os.environ.get("AO_SESSION_ID")
    if session:
        out = [*out, "--label", f"ao.session={session}"]
    return out


def readable(*paths):
    """Hand the bind mounted tree to the container. A temp dir is 0700 for its
    owner, and inside the container it is the nginx worker - not the root owned
    master - which opens the files, so everything here has to be world readable."""
    for path in paths:
        os.chmod(path, 0o755 if path.is_dir() else 0o644)


def fetch(base, path):
    """GET one path and report (status, body), errors included."""
    try:
        with urllib.request.urlopen(base + path, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except OSError as error:
        raise HarnessError(f"request for {base + path} failed: {error}")


def wait_until_serving(edge, port):
    """Wait for nginx to bind its published port, then hand out the base URL.

    Bounded, and it fails with the container's own log: a conf nginx refuses is
    the most likely reason to sit here, and that reason is only in the log."""
    deadline = time.monotonic() + READINESS_TIMEOUT_S
    while True:
        if docker("inspect", "-f", "{{.State.Running}}", edge) != "true":
            raise HarnessError(
                f"{edge} exited; docker logs:\n{docker('logs', edge, check=False)}")
        try:
            body = fetch(f"http://127.0.0.1:{port}", "/")
            if body[0] == 200:
                return f"http://127.0.0.1:{port}"
        except HarnessError:
            pass  # nothing listening yet
        if time.monotonic() >= deadline:
            raise HarnessError(
                f"{edge} did not serve within {READINESS_TIMEOUT_S:.0f}s; "
                f"docker logs:\n{docker('logs', edge, check=False)}")
        time.sleep(0.1)


def judge(kind, path, argument, status, body):
    """Compare one answer with what its kind owes, and say what was seen."""
    if kind == SPA:
        return (status, body) == (200, SPA_BODY), "the SPA shell"
    if kind == BACKEND:
        # The stub echoes the path it was asked for, without the query string.
        wanted = f"backend-stub {path.split('?')[0]}\n"
        return (status, body) == (200, wanted), f"proxied as {wanted.strip()}"
    return status == argument and body != SPA_BODY, f"status {argument}, not the shell"


def main():
    if not CONF.is_file():
        raise HarnessError(f"{CONF} not found - run this from a mrmap checkout")

    image = nginx_image()
    token = uuid.uuid4().hex[:8]
    network = f"mrmap-nginx-smoke-{token}"
    backend = f"{network}-backend"
    edge = f"{network}-edge"
    workspace = Path(tempfile.mkdtemp(prefix=f"mrmap-nginx-smoke-{token}-"))

    try:
        # The SPA root the conf points at, with a stub shell and the real beacon.
        spa_root = workspace / "frontend"
        spa_root.mkdir()
        (spa_root / "index.html").write_text(SPA_BODY)
        shutil.copy(BEACON, spa_root / "error-beacon.js")
        stub_conf = workspace / "backend-stub.conf"
        stub_conf.write_text(STUB_BACKEND_CONF)
        readable(workspace, spa_root, spa_root / "index.html",
                 spa_root / "error-beacon.js", stub_conf)

        docker("network", "create", network)
        # The name the conf resolves is "backend" (set $upstream_backend), so the
        # alias is what makes the stub reachable under it.
        docker("run", "-d", "--name", backend, "--network", network,
               "--network-alias", "backend", *labels(), "-v",
               f"{stub_conf}:/etc/nginx/conf.d/default.conf:ro", image)
        docker("run", "-d", "--name", edge, "--network", network,
               "-p", "127.0.0.1::80", *labels(),
               "-v", f"{CONF}:/etc/nginx/conf.d/default.conf:ro",
               "-v", f"{spa_root}:/var/www/mrmap/frontend:ro", image)

        published = docker("port", edge, "80/tcp")
        if not published:
            raise HarnessError(f"{edge} published no port")
        base = wait_until_serving(edge, published.splitlines()[0].rsplit(":", 1)[1])
        print(f"nginx routing smoke on {base} ({image})")

        failures = 0
        for case in CASES:
            kind, path = case[0], case[1]
            argument = case[2] if len(case) > 2 else None
            status, body = fetch(base, path)
            ok, expected = judge(kind, path, argument, status, body)
            failures += ok is False
            print(f"  {'ok  ' if ok else 'FAIL'} {path:<38} expected "
                  f"{expected:<45} got {status} "
                  f"{'' if ok else repr(body[:80])}")

        if failures:
            print(f"{failures} of {len(CASES)} URLs routed wrong")
            return 1
        print(f"all {len(CASES)} URLs routed correctly")
        return 0
    finally:
        # What is still there after the removal is a leftover worth naming; the
        # removal of a container docker already forgot is not.
        for name in (edge, backend):
            docker("rm", "-f", name, check=False)
            if subprocess.run(["docker", "inspect", name],
                              capture_output=True).returncode == 0:
                print(f"leftover container: {name}")
        docker("network", "rm", network, check=False)
        if subprocess.run(["docker", "network", "inspect", network],
                          capture_output=True).returncode == 0:
            print(f"leftover network: {network}")
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HarnessError as error:
        print(f"nginx_routing_smoke: cannot run: {error}", file=sys.stderr)
        sys.exit(2)
