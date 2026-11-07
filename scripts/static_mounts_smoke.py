#!/usr/bin/env python3
"""static_mounts_smoke: does the stack mount anything over the static roots the frontend image carries?

Host-side check carried by this repository; run it as `python3
scripts/static_mounts_smoke.py` from the repository root. Standard library only,
plus the local `docker` CLI: this reads the configuration `docker compose up`
would run, it starts nothing. Exit 0 when no mount touches an image-owned static
root, 1 when one does, 2 when the harness itself could not run.

Why the mount layout is checked, and nowhere else
-------------------------------------------------
The frontend image carries its served content under two static roots:
`/var/www/mrmap/frontend` (the built SPA) and `/var/www/mrmap/backend` (the
backend's collectstatic output), and `docker/nginx/mrmap.conf` serves both from
the image. A named volume over either path shows that volume to nginx instead,
and Docker fills a named volume from the image only while the volume is still
empty: every rebuild after the first day then produces a new image the browser
never sees. Nothing notices from the outside - HTTP stays 200,
`/api/system/info` stays fine, the container reports the new image - which is
what made the failure expensive.

Issue #922 removed the two seed volumes `frontend-static` and `backend-static`
from `docker-compose.yml`; issue #1027 reported the very same failure from a
checkout that still carried them and asked that the chosen shape - the image
owns the static roots - not regress unnoticed again. No other suite can see
this: Django's tests and Behave run behind nginx, the frontend's own tests
never meet compose, and CI builds no image to inspect. The sibling check
`scripts/nginx_routing_smoke.py` asks which side of `mrmap.conf` a URL lands
on; this asks what is underneath it.

What it checks
--------------
`docker compose -f ... config --no-interpolate --format json`, once for the
production file and once per compose file layered over it (every
`docker-compose.*.yml` sitting in the checkout, so a worktree-local isolation
file is judged with the committed files). `--no-interpolate` keeps `.env` out
of the picture: the mount layout is literal text, so the check needs no
configured deployment. Each mount of each service is then asked whether its
target is one of the static roots or shares a path chain with one - a mount
above a root shadows it just as the exact path does, a mount below one shadows
part of it - and every answer is named with service, type and source. The one
bind mount the `frontend` service carries today (`docker/nginx/mrmap.conf` into
`/etc/nginx/conf.d/`) passes: it does not touch `/var/www/mrmap`.

When to touch this file
-----------------------
A mount under or above `/var/www/mrmap`, on any service, needs a reason first:
either the path stops being image-owned content (then adjust STATIC_ROOTS and
say why it no longer travels in the image), or the mount must go. An empty run
here is what lets `docker compose build frontend && docker compose up -d
frontend` mean "the browser gets the bundle that was just built" (#1027).
"""

import json
import subprocess  # nosec B404 - the point of this script is to call the docker CLI
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "docker-compose.yml"

# The static roots docker/nginx/nginx.Dockerfile fills and mrmap.conf serves.
# A mount that equals one of these, is an ancestor of one, or sits inside one,
# shows something else to nginx than the image the container runs from.
STATIC_ROOTS = ("/var/www/mrmap/frontend", "/var/www/mrmap/backend")


class HarnessError(Exception):
    """The check could not be run at all - a missing docker, a compose file it
    refuses. Kept apart from a found mount, which is a real answer to the
    question the check asks."""


def compose_config(files):
    """The normalized configuration of these compose files, without touching
    .env or a registry: --no-interpolate leaves every ${...} literal and config
    still expands the volumes to long syntax, which is what this reads."""
    command = ["docker", "compose"]
    for file in files:
        command += ["-f", file]
    command += ["config", "--no-interpolate", "--format", "json"]
    try:
        process = subprocess.run(command, capture_output=True, text=True,
                                 cwd=ROOT)  # nosec B603 - fixed argv, fixed cwd
    except FileNotFoundError:
        raise HarnessError("the docker CLI is not on PATH")
    if process.returncode != 0:
        raise HarnessError(
            f"docker {' '.join(command[1:])} exited {process.returncode}: "
            f"{process.stderr.strip() or process.stdout.strip()}")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError:
        raise HarnessError(
            f"docker compose config of {' + '.join(files)} printed no parsable JSON")


def shadowing(config):
    """Every mount that shares a path chain with a static root, as (service,
    type, source, target, root) - an empty list is the pass."""
    hits = []
    for service in sorted(config.get("services", {})):
        for mount in (config["services"][service].get("volumes") or []):
            if not isinstance(mount, dict) or "target" not in mount:
                raise HarnessError(
                    f"unexpected volume entry for service {service}: {mount!r}")
            target = mount["target"].rstrip("/") or "/"
            for root in STATIC_ROOTS:
                if (target == root or target.startswith(root + "/")
                        or root.startswith(target + "/")):
                    hits.append((service, mount.get("type", "?"),
                                 mount.get("source", "?"), target, root))
                    break
    return hits


def compose_files():
    """The base file plus every compose file in the checkout layered over it.

    Deliberately by glob, not by a list: a worktree-local overlay (the
    docker-compose.ao.yml an orchestrator generates, or a developer's own) is
    part of the layout this checkout would really run, and it is exactly the
    kind of file that could reintroduce a static mount without anyone looking
    at the committed files again."""
    if not (ROOT / BASE).is_file():
        raise HarnessError(f"{BASE} not found - run this from a mrmap checkout")
    overlays = sorted(path.name for path in ROOT.glob("docker-compose.*.yml"))
    return [[BASE], *[[BASE, overlay] for overlay in overlays]]


def main():
    failures = 0
    try:
        for combo in compose_files():
            label = " + ".join(combo)
            hits = shadowing(compose_config(combo))
            for service, mount_type, source, target, root in hits:
                failures += 1
                print(f"FAIL  {label}\n"
                      f"      service {service} mounts {mount_type} "
                      f"{source} at {target}, which shadows the image-owned "
                      f"static root {root}\n"
                      f"      nginx would serve that mount instead of the "
                      f"image's content - the #922 volume that #1027 was "
                      f"reported against has exactly this shape")
            if not hits:
                print(f"OK    {label}: no mount touches "
                      f"{' or '.join(STATIC_ROOTS)}")
    except HarnessError as error:
        print(f"harness: {error}", file=sys.stderr)
        return 2

    if failures:
        print(f"{failures} mount(s) shadow the static roots of the frontend "
              f"image")
        return 1
    print("the frontend image owns its static roots")
    return 0


if __name__ == "__main__":
    sys.exit(main())
