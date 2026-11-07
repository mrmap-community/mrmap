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
    image. Its SPA root holds a stub `index.html` and the real `error-beacon.js`,
    and its collectstatic root one stub file - what is under test is which
    `location` answers, not what the built app renders, so nothing has to be
    compiled.
  * the *backend*: the same image with a three line server that answers 200 with
    `backend-stub <uri>` for every path, on the name and port the conf resolves
    (`backend`, port 8001). A proxied URL is then proven by that echo - including
    the path it was forwarded with - rather than inferred from a 502 that merely
    says nothing was listening.

Everything this harness invents is *staged into* the containers rather than bind
mounted, so the host tree it draws from stays private: it is the nginx worker, not
the root owned master, which opens those files, and a bind mount therefore only
works when the host copy is readable by everybody.

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

A new backend mount belongs here as well, and with one asset-shaped url of its
own: #1110 is the other class of failure this table exists for, where a url of a
mount is answered by a rule which nginx judges at a *deeper* level than the
mount's own location, so the mount never sees the request. Nothing but the edge
can show that - behind it django answers the url happily.
"""

import os
import re
import subprocess
import sys
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
SPA_ROOT = "/var/www/mrmap/frontend"

# The collectstatic root the conf aliases at /backend/static/. One file of it is
# staged, so a row can ask for a url that location really owns.
BACKEND_STATIC_ROOT = "/var/www/mrmap/backend"
BACKEND_STATIC_PATH = "/backend/static/admin/css/base.css"
BACKEND_STATIC_ON_DISK = f"{BACKEND_STATIC_ROOT}/admin/css/base.css"
BACKEND_STATIC_BODY = "collectstatic-stub\n"

# The beacon the image copies into its SPA root, read here as the body its own
# exact location owes.
BEACON_BODY = BEACON.read_text()

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

# A word only this conf defines, to prove the edge really loaded the file under
# test instead of still serving the image's own default.
CONF_MARKER = "mrmap_frontend_error"

SPA = "spa"
BACKEND = "backend"
DENY = "deny"
FILE = "file"

# (kind, path, argument) - SPA: the shell answers; BACKEND: the upstream echoes
# the requested path back, without its query string; DENY: this status answers
# and it is not the shell; FILE: this body is served from a root of nginx itself.
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

    # The same urls with an asset extension on the last segment - the shape
    # #1110 is about. While the asset rule of #942 sat nested inside `location /`
    # it was judged at that deeper level, before the proxy regex below was
    # consulted at all, and answered every one of them with nginx's own 404. The
    # two media names are the ones a deployment really answers: a stored
    # preview_image (registry/models/mapcontext.py names it
    # preview_images/<pk>/<filename>) and the body of one security proxy log row,
    # which an operator opens through the link of that row. They are the two 200
    # cases of backend/tests/django/test_media_serving.py, and that suite runs
    # behind this nginx with django's own test client - which is why it never
    # noticed what the edge in front of it answered.
    (BACKEND, "/media/preview_images/42/logo.png"),
    (BACKEND, "/media/security_proxy/logs/requests/"
              "1b4d0e0a-2c3d-4e5f-8a9b-000000000000.json"),
    # The other mounts carry the same shape, and none of them is about media:
    # whatever a mount answers, an asset extension on the last segment belongs
    # to that mount and not to the asset rule.
    (BACKEND, "/api/x.js"),
    (BACKEND, "/csw/x.png"),
    (BACKEND, "/ws/x.js"),
    (BACKEND, "/django-admin/x.css"),
    (BACKEND, "/mrmap-proxy/x.map"),

    # Answered by nginx itself, before both of the two above.
    (DENY, "/api/system/error", 204),   # the error beacon of #942, exact match
    (DENY, "/media/logs/a-dump.sql", 404),   # slow request dumps, #888
    (DENY, "/assets/does-not-exist.js", 404),  # hashed bundles, #942

    # A missing file with an asset extension below the SPA root stays a real 404
    # and never the app shell: what the asset rule of #942 was written for, and
    # what the fix of #1110 must not undo by moving that rule up a level.
    (DENY, "/missing-image.png", 404),

    # The files of nginx's own two roots, asked for through the location which
    # owns them. Both names carry an asset extension, so both would answer 404 if
    # a location of this server ever let the asset rule judge the url instead of
    # its own file: the beacon through its exact location (#942), the collectstatic
    # file through the alias of /backend/static/.
    (FILE, "/error-beacon.js", BEACON_BODY),
    (FILE, BACKEND_STATIC_PATH, BACKEND_STATIC_BODY),

    # The asset-shaped urls of the three tool proxies stay with their own proxy.
    # This harness runs no grafana, no pgadmin and no flower, so the 502 of the
    # proxy which could not resolve its upstream is the proof that *that* location
    # judged the url: with the asset rule of #942 in reach of these urls, the answer
    # would be its 404 instead. That reach is what the `^~` of those locations takes
    # away, and it is what #942 avoided by nesting its rule; #1110 moves the rule to
    # the server level, where a plain prefix would not survive it.
    (DENY, "/grafana/public/build/grafana.dark.json", 502),
    (DENY, "/pgadmin/static/grappelli/styles/screen.css", 502),
    (DENY, "/flower/static/imgs/favicon.png", 502),
]

READINESS_TIMEOUT_S = 25.0


class HarnessError(Exception):
    """The check could not be run at all - a missing docker, a container that
    never came up. Kept apart from a routing failure, which is a real answer to
    the question the check asks."""


def docker(*args, check=True, stdin=None):
    """Run the docker CLI and return its stdout, or raise with its stderr."""
    try:
        process = subprocess.run(["docker", *args], capture_output=True,
                                 text=True, input=stdin)
    except FileNotFoundError:
        raise HarnessError("the docker CLI is not on PATH")
    if check and process.returncode != 0:
        raise HarnessError(
            f"docker {' '.join(args)} exited {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}"
        )
    return process.stdout.strip()


def stage(container, path, content=None, source=None):
    """Put one file into a running container.

    Never a bind mount: the nginx *worker* - not the root owned master - is the
    one which opens these, so a mounted file is only readable when the host copy
    is readable by everybody. Written into the container it stays private to this
    run's own filesystem, which is disposable anyway.
    """
    docker("exec", container, "mkdir", "-p", str(Path(path).parent))
    if content is not None:
        docker("exec", "-i", container, "sh", "-c", f"cat > {path}", stdin=content)
    else:
        docker("cp", str(source), f"{container}:{path}")


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
    """Track what this run started, so the orchestrator can find it: this
    harness is disposable and must never outlive the session running it."""
    out = ["--label", "ao.tool=nginx-routing-smoke"]
    session = os.environ.get("AO_SESSION_ID")
    if session:
        out = [*out, "--label", f"ao.session={session}"]
    return out


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
    """Wait for nginx to serve the staged shell, then hand out the base URL.

    Bounded, and it fails with the container's own log: a conf nginx refuses is
    the most likely reason to sit here, and that reason is only in the log."""
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + READINESS_TIMEOUT_S
    while True:
        if docker("inspect", "-f", "{{.State.Running}}", edge) != "true":
            raise HarnessError(
                f"{edge} exited; docker logs:\n{docker('logs', edge, check=False)}")
        try:
            if fetch(base, "/")[0] == 200:
                return base
        except HarnessError:
            pass  # nothing listening yet
        if time.monotonic() >= deadline:
            raise HarnessError(
                f"{edge} did not serve within {READINESS_TIMEOUT_S:.0f}s; "
                f"docker logs:\n{docker('logs', edge, check=False)}")
        time.sleep(0.1)


def wait_until_proxied(base, backend):
    """Wait until the reload of the stub upstream is in effect.

    `nginx -s reload` returns once the signal is sent, so the first proxied row
    could otherwise still meet the image's default server, which does not listen
    on 8001 at all, and be reported as a routing failure."""
    deadline = time.monotonic() + READINESS_TIMEOUT_S
    while True:
        status, body = fetch(base, "/api/readiness-probe")
        if status == 200 and body.startswith("backend-stub"):
            return
        if time.monotonic() >= deadline:
            raise HarnessError(
                f"{backend} never answered as the upstream (last answer {status} "
                f"{body[:60]!r}); docker logs:\n"
                f"{docker('logs', backend, check=False)}")
        time.sleep(0.1)


def judge(kind, path, argument, status, body):
    """Compare one answer with what its kind owes, and say what was seen."""
    if kind == SPA:
        return (status, body) == (200, SPA_BODY), "the SPA shell"
    if kind == BACKEND:
        # The stub echoes the path it was asked for, without the query string.
        wanted = f"backend-stub {path.split('?')[0]}\n"
        return (status, body) == (200, wanted), f"proxied as {wanted.strip()}"
    if kind == FILE:
        return ((status, body) == (200, argument),
                "the file of this url, not the shell")
    return status == argument and body != SPA_BODY, f"status {argument}, not the shell"


def main():
    if not CONF.is_file():
        raise HarnessError(f"{CONF} not found - run this from a mrmap checkout")

    image = nginx_image()
    token = uuid.uuid4().hex[:8]
    network = f"mrmap-nginx-smoke-{token}"
    backend = f"{network}-backend"
    edge = f"{network}-edge"

    try:
        docker("network", "create", network)
        # The name the conf resolves is "backend" (set $upstream_backend), so the
        # alias is what makes the stub reachable under it.
        docker("run", "-d", "--name", backend, "--network", network,
               "--network-alias", "backend", *labels(), image)
        docker("run", "-d", "--name", edge, "--network", network,
               "-p", "127.0.0.1::80", *labels(),
               "-v", f"{CONF}:/etc/nginx/conf.d/default.conf:ro", image)

        # The SPA root of the edge: a stub shell and the real beacon, so the
        # beacon's exact location is judged with its file present, as in the image.
        stage(edge, f"{SPA_ROOT}/index.html", content=SPA_BODY)
        stage(edge, f"{SPA_ROOT}/error-beacon.js", source=BEACON)
        # And one file of the collectstatic root, so the alias of
        # /backend/static/ has something of its own to answer with.
        stage(edge, BACKEND_STATIC_ON_DISK, content=BACKEND_STATIC_BODY)
        # The edge started with the conf under test; prove it kept it rather than
        # answering these rows from the image's own default server.
        if CONF_MARKER not in docker("exec", edge, "nginx", "-T"):
            raise HarnessError(
                f"{edge} is not running {CONF}; nginx -T says otherwise")

        # The stub upstream: its own conf, then a reload to hand it over.
        stage(backend, "/etc/nginx/conf.d/default.conf", content=STUB_BACKEND_CONF)
        docker("exec", backend, "nginx", "-t")
        docker("exec", backend, "nginx", "-s", "reload")

        published = docker("port", edge, "80/tcp")
        if not published:
            raise HarnessError(f"{edge} published no port")
        base = wait_until_serving(edge, published.splitlines()[0].rsplit(":", 1)[1])
        wait_until_proxied(base, backend)
        print(f"nginx routing smoke on {base} ({image})")

        failures = 0
        for case in CASES:
            kind, path = case[0], case[1]
            argument = case[2] if len(case) > 2 else None
            status, body = fetch(base, path)
            ok, expected = judge(kind, path, argument, status, body)
            if not ok:
                failures += 1
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


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HarnessError as error:
        print(f"nginx_routing_smoke: cannot run: {error}", file=sys.stderr)
        sys.exit(2)
