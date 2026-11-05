#!/usr/bin/env python3
"""dev_image_id: dependency fingerprints and prebuilt-image resolution for mrmap.

Host-side tool carried by this repository; run it as `python3
scripts/dev_image_id.py` from the repository root. It has two halves:

  * fingerprinting (standard library only, entirely local, no network): reads
    the checkout and prints the first 12 hex digits of the sha256 over a
    canonical, sorted manifest of the inputs an image's layers depend on (the
    integration contract of epic #959, see issue #960). This is the single
    source of truth for the immutable image tag `ghcr.io/mrmap-community/
    mrmap-<image>-dev:<fp>`; CI calls this script instead of re-implementing
    the manifest (see .github/workflows/dev-images.yml).
  * resolution (`--resolve`, additionally uses the local `docker` CLI): find
    the image whose tag matches the fingerprint - reuse it when present
    locally, otherwise pull it from the registry, and on a registry miss fail
    loudly with actionable fallbacks (or build locally when `--build` is
    given). A missing image is NEVER silently replaced by a mutable tag; the
    only opt-out is the explicit env var MRMAP_ALLOW_MUTABLE_DEV_IMAGE=1,
    intended for humans, never for agent tooling.
  * existence (`--exists`, no docker and no credential): ask the registry over
    plain HTTPS whether one tag is there, and answer in one of three ways.
    Deliberately a separate command and not a cheaper mode of `--resolve`,
    because the two prove different things - see "What each probe proves".

What each probe proves
  `--exists` sends an anonymous pull token request plus ONE manifest request
  and proves that the registry serves a manifest under this exact name. It
  proves nothing about the bytes: nothing is downloaded, so it cannot notice a
  truncated layer, a tag pointed at foreign content, or an image that will not
  run on this host. `--resolve` proves the stronger statement - published AND
  pulled intact - and pays for it: measured 2026-11-05, 38 s and 308 MB of
  compressed layers for the backend fp tag, against 0.3 s and about 1.5 kB for
  `--exists` on the same tag.

  So only `--resolve` may justify "we do not need to build this" in a context
  where the bytes will never be pulled (an image the run throws away is still
  an image whose buildx output has to be valid, and CI's gate is exactly that
  context: `scripts/dev_image_gate.py` keeps calling `--resolve`). Where a
  manifest-only answer is enough: an agent's pre-flight, which decides between
  `--resolve` and `--build` without waiting on a pull, and a human asking "did
  the publish for my fingerprint land?". `docs/source/development/
  prebuilt-images.rst` carries the same table with the gate's decision.

Images and their manifest inputs
  backend  (docker/backend/alpine.Dockerfile, shared by backend, django-tests,
           behave and pre-commit-check): the Dockerfile, every file under
           backend/.requirements/, the build args the image is built with and
           the FROM base references the Dockerfile pins.
  frontend (docker/frontend/tests.Dockerfile, dependency image for
           frontend-tests): the Dockerfile, its bootstrap entrypoint
           script (both are baked into the image, so a changed entrypoint
           must not resolve to a stale tag), frontend/package.json,
           frontend/package-lock.json and the FROM base references. The build
           arg MRMAP_IMAGE_FP is deliberately NOT a manifest input: it carries
           a copy of the fingerprint INTO the image (stamp below), and hashing
           it would be self-referential.
Source-code-only changes are in no manifest, so they never change a
fingerprint; dependency, Dockerfile, entrypoint or build-arg changes always do.

Frontend fingerprint sync contract (#962, with #963)
  The image tag fp (this script, host) and the dependency marker the image
  bakes at build time (docker/frontend/tests.Dockerfile and
  docker/frontend/tests-entrypoint.sh, inside the container) serve different
  checks and are deliberately two different values with a defined agreement:

  - tag fp  = sha256 over the manifest above. Covers EVERYTHING the build
    reads, so it changes whenever the marker can change, plus whenever the
    Dockerfile/entrypoint logic itself changes.
  - marker fp (deps marker, `--deps-marker --image frontend`) = first 12 hex
    of sha256 over the raw bytes the container hashes:
    `package.json || package-lock.json || node -v || npm -v` - exactly the
    formula baked into /opt/frontend-deps/.mrmap-deps-fp at build time and
    recomputed by the entrypoint against the bind-mounted lockfiles.
    `--node-version`/`--npm-version` supply the two version lines from the
    host (get them from the FROM-pinned base image, e.g. `docker run --rm
    --entrypoint node node:26-alpine -v`); each is used with exactly one
    trailing newline, matching the shell pipeline.

  The compose layer passes the host-resolved tag fp into the container as
  MRMAP_FRONTEND_IMAGE_FP, so the entrypoint's volume marker stores the
  CANONICAL value next to the deps marker it verifies locally; the tag
  itself is stamped into the image at build time
  (/opt/frontend-deps/.mrmap-image-fp via build arg MRMAP_IMAGE_FP) so
  `--resolve` can verify a local hit's content, not just its name.

Usage
  python3 scripts/dev_image_id.py [--image backend]
                  print the fingerprint of the (backend) dev/test image
  python3 scripts/dev_image_id.py --image frontend
                  print the fingerprint of the frontend dependency image
  python3 scripts/dev_image_id.py [--image IMAGE] --print-build-args
                  print the docker build args the fingerprint assumes, so the
                  CI workflow and agent tooling cannot drift from them
  python3 scripts/dev_image_id.py --image frontend --deps-marker \
      --node-version v26.13.0 --npm-version 11.20.0
                  print the in-container dependency marker for these inputs
  python3 scripts/dev_image_id.py --resolve [--image IMAGE] [--build]
                  ensure an image for the current fingerprint exists locally:
                  local hit -> (verify) -> done; else pull; on a registry miss
                  fail with exit code 3 and actionable fallbacks, or build
                  locally under the same immutable tag when --build is given.
                  The fingerprint goes to stdout (capture it for the compose
                  variables); every diagnostic goes to stderr.
  python3 scripts/dev_image_id.py --exists [--image IMAGE] [--fp TAG]
                  ask the registry whether this tag is published, over plain
                  HTTPS: anonymous token plus one manifest request, no docker,
                  no credential, nothing downloaded. Existence only - see "What
                  each probe proves" above. The asked tag goes to stdout, every
                  diagnostic to stderr, like --resolve.
  python3 scripts/dev_image_id.py --self-check
                  verify determinism and input sensitivity of both images'
                  fingerprints, the marker formula, and the resolver's failure
                  classification on a throwaway tree and canned data - no
                  docker, no network.

Resolver exit codes
  0  image available locally (hit, pulled, built with --build, or opt-out)
  2  usage error (argparse)
  3  no such tag in the registry and no local image: build locally (see the
     printed command / --build) or wait for CI to publish this fingerprint
  4  transient registry/docker failure (network, dns, timeouts, 5xx) or an
     unclassified pull error: the tag may exist; retry, nothing was changed
     locally
  5  platform mismatch: the image exists but cannot run on this host/daemon
  6  --build: the local fallback build failed
  7  the local tag exists but its stamped fingerprint differs: the tag was
     pointed at foreign content - do not use it; rebuild with --build

  --exists answers within the same codes, and only these three:
  0  the registry serves a manifest under this name (existence, nothing more)
  3  the registry says this name is not there ("manifest unknown")
  4  could not look: no answer, a timeout, a 5xx, a refused anonymous read, or
     a 404 that does not say "manifest unknown" - a registry that changed its
     answer shape is not evidence that the tag is gone
"""

import argparse
import hashlib
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# Single source of truth for the build args of the published backend dev/test
# image: docker-compose.dev.yml passes the same value to the shared
# Dockerfile. CI reads them through --print-build-args instead of repeating
# them, so the args the fingerprint covers are the args the image is built by.
BACKEND_DEV_BUILD_ARGS = {"MRMAP_PRODUCTION": "False"}

# The frontend dependency image takes no build args: docker/frontend/
# tests.Dockerfile installs exactly what the lockfile pins. The stamp arg
# MRMAP_IMAGE_FP records the fingerprint and is deliberately not hashed
# (see the module docstring). Kept as a dict so both images print through the
# same code path.
FRONTEND_DEV_BUILD_ARGS = {}

BACKEND_DOCKERFILE = "docker/backend/alpine.Dockerfile"
BACKEND_REQUIREMENTS_DIR = "backend/.requirements"

FRONTEND_DOCKERFILE = "docker/frontend/tests.Dockerfile"
FRONTEND_ENTRYPOINT = "docker/frontend/tests-entrypoint.sh"
FRONTEND_PACKAGE_JSON = "frontend/package.json"
FRONTEND_PACKAGE_LOCK = "frontend/package-lock.json"

# Paths INSIDE the frontend image: the baked deps marker (#963) and the
# canonical fingerprint stamp this script's --resolve verifies.
FRONTEND_IMAGE_DEPS_FP = "/opt/frontend-deps/.mrmap-deps-fp"
FRONTEND_IMAGE_STAMP = "/opt/frontend-deps/.mrmap-image-fp"

# Versioned manifest format tag, so a later extension of this script (the
# frontend image of #962/#963 adds its own inputs under its own image name)
# can change the layout without silently colliding with backend fingerprints.
MANIFEST_FORMAT = "mrmap-dev-image-manifest/1"

IMAGES = ("backend", "frontend")

# Registry coordinates per the epic #959 integration contract (issue #960).
REGISTRY_REPO = {
    "backend": "ghcr.io/mrmap-community/mrmap-backend-dev",
    "frontend": "ghcr.io/mrmap-community/mrmap-frontend-dev",
}

# Explicit, loud human opt-out from immutable tags (see docstring). Agent
# tooling must never set it.
MUTABLE_OPT_OUT_ENV = "MRMAP_ALLOW_MUTABLE_DEV_IMAGE"
MUTABLE_TAG = "main"

# The media type the published dev-image tags are actually stored as, measured
# 2026-11-05 against ghcr.io for both packages: an OCI *manifest* (single
# architecture, not an index). This is not a negotiation to widen - ghcr answers
# 404 MANIFEST_UNKNOWN, "OCI manifest found, but Accept header does not support
# OCI manifests", for every header that does not name this type, including
# */*, an empty header and the docker distribution types. A second type beside
# it is harmless, a wildcard beside it is not, so exactly one type is sent.
MANIFEST_MEDIA_TYPE = "application/vnd.oci.image.manifest.v1+json"

# The registry's own origin, for the two API endpoints below. REGISTRY_REPO
# above carries full references; the API needs host and repository path apart.
# Overridable for the offline test (see --registry-base), which points both
# endpoints at a local stub instead of the network.
REGISTRY_BASE = "https://ghcr.io"
USER_AGENT = "mrmap-dev-image-id"

# Both requests of the probe are small JSON reads. A registry that does not
# answer within this is "could not look", which is exit 4 and a retry - never a
# statement about the tag - so the cap is what keeps a pre-flight cheap.
REGISTRY_TIMEOUT_S = 20

# A manifest is a few kB of JSON; the cap keeps a confused or hostile endpoint
# from turning a pre-flight into a download.
MAX_RESPONSE_BYTES = 65536

EXIT_OK = 0
EXIT_MISS = 3
EXIT_TRANSIENT = 4
EXIT_PLATFORM = 5
EXIT_BUILD_FAILED = 6
EXIT_STAMP_MISMATCH = 7

DOCKER_PULL_TIMEOUT_S = 900
DOCKER_INSPECT_TIMEOUT_S = 30
DOCKER_RUN_TIMEOUT_S = 120


def _require(path, root):
    if not path.is_file():
        raise SystemExit(
            f"dev_image_id: {path.relative_to(root)} not found - run this "
            "script from a complete repository checkout"
        )
    return path


def _from_references(dockerfile):
    """Base image references of the FROM lines, as the Dockerfile pins them."""
    refs = set()
    for raw in dockerfile.read_text(encoding="utf-8").splitlines():
        tokens = raw.split("#", 1)[0].split()
        if not tokens or tokens[0].upper() != "FROM":
            continue
        for token in tokens[1:]:
            if token.startswith("--"):  # --platform=... and friends
                continue
            if token.upper() == "AS":  # the stage name is not a reference
                break
            refs.add(token)
            break
    return refs


def backend_manifest(root):
    """The canonical sorted manifest of the backend dev-image dependency inputs."""
    dockerfile = _require(root / BACKEND_DOCKERFILE, root)
    requirements_dir = root / BACKEND_REQUIREMENTS_DIR
    if not requirements_dir.is_dir():
        raise SystemExit(
            f"dev_image_id: {requirements_dir.relative_to(root)} not found - "
            "run this script from a complete repository checkout"
        )

    lines = [MANIFEST_FORMAT, "image=backend"]
    dependency_files = [dockerfile] + sorted(
        f for f in requirements_dir.iterdir() if f.is_file()
    )
    build_args = BACKEND_DEV_BUILD_ARGS
    for dependency_file in dependency_files:
        digest = hashlib.sha256(dependency_file.read_bytes()).hexdigest()
        lines.append(f"file {dependency_file.relative_to(root)} sha256={digest}")
    for name, value in build_args.items():
        lines.append(f"build-arg {name}={value}")
    for ref in _from_references(dockerfile):
        lines.append(f"from {ref}")
    return "\n".join(sorted(lines)) + "\n"


def frontend_manifest(root):
    """The canonical sorted manifest of the frontend dependency-image inputs.

    Everything docker/frontend/tests.Dockerfile reads at build time: the
    lockfiles it installs from, the Dockerfile and the bootstrap entrypoint
    it bakes in, and the FROM references that pin node/npm. package.json
    belongs in because npm ci resolves the tree from package.json + lock.
    """
    dockerfile = _require(root / FRONTEND_DOCKERFILE, root)
    lines = [MANIFEST_FORMAT, "image=frontend"]
    dependency_files = [
        root / name
        for name in (
            FRONTEND_DOCKERFILE,
            FRONTEND_ENTRYPOINT,
            FRONTEND_PACKAGE_JSON,
            FRONTEND_PACKAGE_LOCK,
        )
    ]
    for dependency_file in dependency_files:
        _require(dependency_file, root)
        digest = hashlib.sha256(dependency_file.read_bytes()).hexdigest()
        lines.append(f"file {dependency_file.relative_to(root)} sha256={digest}")
    for name, value in FRONTEND_DEV_BUILD_ARGS.items():
        lines.append(f"build-arg {name}={value}")
    for ref in _from_references(dockerfile):
        lines.append(f"from {ref}")
    return "\n".join(sorted(lines)) + "\n"


def manifest(root, image="backend"):
    if image == "backend":
        return backend_manifest(root)
    if image == "frontend":
        return frontend_manifest(root)
    raise SystemExit(f"dev_image_id: unknown image {image!r} (expected one of {', '.join(IMAGES)})")


def fingerprint(root, image="backend"):
    """The 12-hex dependency fingerprint of the given image."""
    return hashlib.sha256(manifest(root, image).encode("utf-8")).hexdigest()[:12]


def deps_marker(root, node_version, npm_version):
    """The in-container dependency marker for the checkout's lockfiles.

    Byte-for-byte the formula of docker/frontend/tests.Dockerfile and
    tests-entrypoint.sh: sha256 over package.json, package-lock.json,
    `node -v` and `npm -v`, each version line with exactly one trailing
    newline. Returns the 12-hex marker, or None when a version pin is
    missing (the host usually has no node/npm; --node-version/--npm-version
    pass the values of the FROM-pinned base image).
    """
    if node_version is None or npm_version is None:
        return None
    blob = _require(root / FRONTEND_PACKAGE_JSON, root).read_bytes()
    blob += _require(root / FRONTEND_PACKAGE_LOCK, root).read_bytes()
    for version in (node_version, npm_version):
        blob += version.rstrip("\n").encode("utf-8") + b"\n"
    return hashlib.sha256(blob).hexdigest()[:12]


def print_build_args(image="backend"):
    build_args = BACKEND_DEV_BUILD_ARGS if image == "backend" else FRONTEND_DEV_BUILD_ARGS
    return ",".join(f"{name}={value}" for name, value in sorted(build_args.items()))


# --------------------------------------------------------------------------
# resolver (--resolve): local docker CLI, no SDK, nothing else
# --------------------------------------------------------------------------


def docker_cli(*args, timeout=DOCKER_INSPECT_TIMEOUT_S):
    """Run the docker CLI; returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        raise SystemExit("dev_image_id: the docker CLI is not available on this host")
    except subprocess.TimeoutExpired:
        return 124, "", f"docker {' '.join(args)} timed out after {timeout}s"


def image_inspect(ref):
    rc, out, _ = docker_cli("image", "inspect", ref)
    if rc != 0:
        return None
    try:
        return json.loads(out)[0]
    except (ValueError, KeyError, IndexError):
        return None


def host_platform():
    rc, out, _ = docker_cli("version", "--format", "{{.Server.Os}}/{{.Server.Arch}}")
    value = out.strip()
    return value if rc == 0 and "/" in value else None


def classify_pull_failure(stderr):
    """Map docker pull output onto the contract's failure classes.

    "miss"      - the registry answered and this tag is not there: build
                  locally or wait for CI.
    "platform"  - the tag exists but not for this OS/architecture.
    "transient" - the registry or the network could not be reached properly;
                  the tag may well exist.
    "unknown"   - anything else; the raw docker output is shown to the user.
    """
    text = stderr.lower()
    miss_markers = (
        "manifest unknown",
        "not found",
        "pull access denied",
        "name unknown",
        "errors: denied",
        "error from registry: denied",
        "requested access to the resource is denied",
        "denied",
        "no such manifest",
        "repository name not known",
    )
    platform_markers = (
        "no match for platform in manifest",
        "manifest with match for platform",
        "image operating system",
    )
    transient_markers = (
        "timeout",
        "timed out",
        "connection refused",
        "connection reset",
        "connection closed",
        "i/o timeout",
        "no such host",
        "temporary failure",
        "tls handshake",
        "unexpected eof",
        "eof",
        "500 internal",
        "502",
        "503",
        "504",
        "toomanyrequests",
        "too many requests",
        "rate limit",
        "server misbehaving",
        "cannot connect",
        "could not find a compatible",  # docker hub transient name resolution
        "dial tcp",
        "network is unreachable",
        "i/o error",
        "http response to https client",
    )
    for marker in platform_markers:
        if marker in text:
            return "platform"
    for marker in miss_markers:
        if marker in text:
            return "miss"
    for marker in transient_markers:
        if marker in text:
            return "transient"
    return "unknown"


def local_build_command(root, image, ref, fp):
    """The sanctioned local fallback build: same Dockerfile, same build args
    the fingerprint covers, same immutable tag CI would publish (#959
    fallback rule). Kept in one place so docs, --build and the tests agree."""
    if image == "backend":
        build_arg_flags = []
        for name, value in sorted(BACKEND_DEV_BUILD_ARGS.items()):
            build_arg_flags += ["--build-arg", f"{name}={value}"]
        return [
            "docker", "build",
            "-f", str(root / BACKEND_DOCKERFILE),
            *build_arg_flags,
            "-t", ref,
            str(root / "backend"),
        ]
    return [
        "docker", "build",
        "-f", str(root / FRONTEND_DOCKERFILE),
        "--build-arg", f"MRMAP_IMAGE_FP={fp}",
        "-t", ref,
        str(root),
    ]


def read_frontend_stamp(ref):
    """The fingerprint stamped into the image at build time, or None.

    None means "unverifiable": old image without the stamp file, or an image
    that cannot be started here. Not a failure by itself - the immutable tag
    name remains the primary guarantee - but a MISMATCH is a hard failure.
    """
    rc, out, _ = docker_cli(
        "run", "--rm", "--entrypoint", "cat", ref, FRONTEND_IMAGE_STAMP,
        timeout=DOCKER_RUN_TIMEOUT_S,
    )
    value = out.strip()
    return value if rc == 0 and value else None


def _note(message):
    print(f"dev_image_id: {message}", file=sys.stderr)


def resolve(root, image, build=False, dry_run=False, repo=None):
    """Ensure a locally usable image with the immutable fingerprint tag.

    Prints the fingerprint on stdout (the compose wiring captures it); all
    diagnostics go to stderr. Returns the process exit code.
    """
    fp = fingerprint(root, image)
    repo = repo or REGISTRY_REPO[image]
    ref = f"{repo}:{fp}"

    if os.environ.get(MUTABLE_OPT_OUT_ENV) == "1":
        _note("=" * 72)
        _note(f"OPT-OUT ACTIVE via {MUTABLE_OPT_OUT_ENV}=1: NOT pinning the "
              f"immutable tag {ref}. The stack may run on a MUTABLE, possibly "
              f"STALE image ({repo}:{MUTABLE_TAG}). This is a human "
              "convenience escape hatch; agent tooling must not set it.")
        _note("=" * 72)
        _note(f"compose wiring under the opt-out: "
              f"export MRMAP_FRONTEND_DEV_IMAGE={repo}:{MUTABLE_TAG}")
        print(fp)
        return EXIT_OK

    if dry_run:
        _note(f"would resolve {image} dependency image: {ref} "
              f"(local hit, else pull, else {'local fallback build' if build else 'loud exit'})")
        print(fp)
        return EXIT_OK

    inspected = image_inspect(ref)
    if inspected is not None:
        problems = []
        host = host_platform()
        if host and inspected.get("Architecture") not in (None, "unknown"):
            image_os_arch = f"{inspected.get('Os', 'linux')}/{inspected['Architecture']}"
            if image_os_arch != host:
                problems.append(
                    f"platform mismatch: local {ref} is {image_os_arch}, "
                    f"this docker daemon serves {host}"
                )
        if image == "frontend":
            stamp = read_frontend_stamp(ref)
            if stamp is None:
                _note(f"warning: {ref} carries no content stamp "
                      f"({FRONTEND_IMAGE_STAMP} unreadable) - trusting the "
                      "immutable tag name; rebuild once to make hits verifiable")
            elif stamp != fp:
                problems.append(
                    f"the local tag {ref} is stamped {stamp!r}, not {fp!r} - "
                    "it was pointed at foreign content"
                )
        if problems:
            for problem in problems:
                _note(f"ERROR: {problem}")
            _note("refusing to run against an image that cannot match this "
                  "checkout's dependencies. Rebuild under the tag with "
                  "--build, or retag/remove the foreign image deliberately.")
            print(fp)
            return EXIT_PLATFORM if any("platform" in p for p in problems) else EXIT_STAMP_MISMATCH
        _note(f"local hit: {ref} is present and matches this checkout's "
              "dependency fingerprint; no registry access needed")
        _compose_wiring(image, fp, ref)
        print(fp)
        return EXIT_OK

    _note(f"{ref} not present locally; pulling (pull_policy-equivalent)")
    rc, _, err = docker_cli("pull", ref, timeout=DOCKER_PULL_TIMEOUT_S)
    if rc == 0:
        _note(f"pulled {ref}")
        _compose_wiring(image, fp, ref)
        print(fp)
        return EXIT_OK

    kind = classify_pull_failure(err)
    if not build:
        _report_miss(kind, image, fp, ref, err, root)
        print(fp)
        return {"miss": EXIT_MISS, "transient": EXIT_TRANSIENT,
                "platform": EXIT_PLATFORM, "unknown": EXIT_TRANSIENT}[kind]

    if kind == "platform":
        _note("ERROR: the registry refused this tag for a platform reason; a "
              "local build is exactly the right fallback, continuing")
    _note(f"registry miss/failure ({kind}); running the sanctioned local "
          f"fallback build under the SAME immutable tag")
    command = local_build_command(root, image, fp=fp, ref=ref)
    _note("+ " + " ".join(command))
    proc = subprocess.run(command)
    if proc.returncode != 0:
        _note("ERROR: the local fallback build failed; nothing was tagged")
        print(fp)
        return EXIT_BUILD_FAILED
    _note(f"built {ref} locally - this is the ONLY sanctioned case in which "
          "local content carries the contract name (epic #959 fallback rule)")
    _compose_wiring(image, fp, ref)
    print(fp)
    return EXIT_OK


def _compose_wiring(image, fp, ref):
    if image == "backend":
        _note(f"compose wiring: export MRMAP_BACKEND_DEV_FP={fp}  "
              "(docker-compose.prebuilt.yml)")
    else:
        _note(f"compose wiring: export MRMAP_FRONTEND_DEV_IMAGE={ref}  "
              f"MRMAP_FRONTEND_IMAGE_FP={fp}  "
              "(docker-compose.prebuilt-frontend.yml)")


def _report_miss(kind, image, fp, ref, err, root):
    line = "=" * 72
    if kind == "miss":
        _note(line)
        _note(f"NO IMAGE FOR THIS CHECKOUT: {ref} is not in the registry and "
              "not present locally. This fingerprint has not been published "
              "(yet). Nothing was run - tests against a mismatching "
              "dependency set would be meaningless.")
        _note(line)
        _note("deterministic fallbacks, pick one:")
        _note(f"  1. build locally under the contract tag: rerun with --build "
              f"(equivalent to: {' '.join(local_build_command(root, image, ref, fp))})")
        _note("  2. let CI publish this fingerprint: .github/workflows/dev-images.yml "
              "publishes on every push to master and on `gh workflow run dev-images.yml "
              "--ref master`; check `gh run list --workflow dev-images.yml` for the run "
              f"that carries fp {fp}, then rerun this resolver")
        _note("  3. (humans only) the mutable convenience tag exists for "
              f"exploration: {repo_hint(image)}:{MUTABLE_TAG} may be stale - the "
              f"frontend image's own fingerprint check keeps it honest; agent "
              f"tooling must instead set {MUTABLE_OPT_OUT_ENV}=1 explicitly to "
              "make the opt-out visible")
    elif kind == "platform":
        _note(f"ERROR: {ref} exists but not for this host's platform "
              "(see the docker output below). Build locally with --build.")
    elif kind == "transient":
        _note(f"TRANSIENT failure while resolving {ref}: the registry or the "
              "docker daemon could not be reached properly. The tag may exist. "
              "Nothing was changed locally; retry, or use --build to build "
              "locally instead of waiting.")
    else:
        _note(f"docker pull {ref} failed with an unclassified error; raw "
              "docker output follows, then the fallbacks of the miss case:")
    for raw in (err.strip().splitlines() or ["(no output)"]):
        _note(f"  docker| {raw}")


def repo_hint(image):
    return REGISTRY_REPO[image]


# --------------------------------------------------------------------------
# existence probe (--exists): anonymous HTTPS, no docker, nothing downloaded
# --------------------------------------------------------------------------


def repository_path(repo, base=REGISTRY_BASE):
    """The registry's repository path of an image reference.

    REGISTRY_REPO holds full references ("ghcr.io/mrmap-community/..."), while
    the token scope and the /v2/ API address a repository by its path alone.
    A reference naming a different host than the request is stripped the same
    way, which is what lets the offline test reuse the --repo hook.
    """
    path = repo
    origin = urlsplit(base).netloc
    if path.startswith(f"{origin}/"):
        return path[len(origin) + 1:]
    first, slash, rest = path.partition("/")
    if slash and "." in first:
        return rest
    return path


def registry_endpoints(repo, tag, base=REGISTRY_BASE):
    """(token grant, manifest url) for one repository path and tag.

    The scope asks for exactly what the probe needs - `pull` on this one
    repository - because an anonymous token that asked for more would be a
    broader credential than the question deserves.
    """
    base = base.rstrip("/")
    origin = urlsplit(base)
    service = origin.hostname or ""
    scope = urllib.parse.quote(f"repository:{repository_path(repo, base)}:pull", safe=":")
    token_url = f"{base}/token?service={urllib.parse.quote(service, safe='')}&scope={scope}"
    manifest_url = f"{base}/v2/{repository_path(repo, base)}/manifests/{urllib.parse.quote(tag, safe='')}"
    return token_url, manifest_url


def http_get(url, headers=None, timeout=REGISTRY_TIMEOUT_S):
    """One bounded GET: (status, headers, body) or (None, None, why not).

    Every transport failure - refused, unresolvable, timed out, a response that
    is not HTTP at all - comes back in the third shape. The probe's contract
    has exactly one answer for "the registry did not tell us" and it is not
    "the tag does not exist", so collapsing them here is the point.
    """
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers or {}), response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:      # a real answer, including 4xx/5xx
        try:
            body = exc.read(MAX_RESPONSE_BYTES)
        except Exception:                      # noqa: BLE001 - the status still stands
            body = b""
        return exc.code, dict(exc.headers or {}), body
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def classify_manifest_answer(status, body, detail=""):
    """What one manifest answer says about a tag: (kind, what it says).

    Kinds: "published", "absent", "ambiguous", "denied", "transient",
    "malformed", "unreachable". Only the first two are statements about the
    tag; the rest are "could not look" and exit 4.

    The distinction between "absent" and "ambiguous" is the whole subtlety of
    this probe: ghcr answers BOTH with 404 and the code MANIFEST_UNKNOWN. One
    of them means the tag is not there, the other means the request did not ask
    in a language the registry answers ("... but Accept header does not support
    OCI manifests"). Reading the second as "not published" would tell an agent
    to build an image that already exists, and would tell CI the same thing.
    """
    if status is None:
        return "unreachable", detail or "the registry did not answer"
    text = (body or b"").decode("utf-8", "replace").strip()
    reasons = []
    try:
        payload = json.loads(text) if text else None
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        for entry in payload.get("errors") or []:
            if isinstance(entry, dict):
                reasons.append(" ".join(str(part) for part in (entry.get("code"), entry.get("message"))
                                        if part).strip())
    registry_said = "; ".join(reasons) or (text[:160] or "no body")

    if status == 200:
        if isinstance(payload, dict) and payload.get("schemaVersion") is not None:
            return "published", registry_said
        return "malformed", ("the registry answered 200 with something that is not a manifest "
                             "(or not all of it): " + repr(text[:120]))
    if status in (401, 403):
        return "denied", registry_said
    if status == 404:
        lowered = registry_said.lower()
        names_the_header = "accept header" in lowered or (
            "accept" in lowered and "does not support" in lowered)
        if names_the_header:
            return "ambiguous", registry_said
        if any(word in lowered for word in ("manifest unknown", "name unknown", "not found")):
            return "absent", registry_said
        return "ambiguous", registry_said
    if status in (408, 429) or status >= 500:
        return "transient", f"HTTP {status}: {registry_said}"
    return "ambiguous", f"HTTP {status}: {registry_said}"


def anonymous_pull_token(token_url, timeout=REGISTRY_TIMEOUT_S):
    """(token, None) or (None, why not). Public packages answer this anonymously.

    A refusal here is deliberately not read as "the package does not exist": a
    private package refuses an anonymous grant for a tag it publishes, so the
    only honest answer is that this probe cannot see it and `docker` - which
    has the host's credential - can.
    """
    status, _headers, payload = http_get(
        token_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=timeout)
    if status is None:
        return None, payload.decode("utf-8", "replace") if isinstance(payload, bytes) else str(payload)
    if status not in (200, 201):
        return None, f"HTTP {status} for the anonymous token grant: " \
                     f"{payload[:200].decode('utf-8', 'replace')}"
    try:
        token = json.loads(payload.decode("utf-8", "replace")).get("token")
    except ValueError:
        return None, f"the token grant answered something that is not JSON: {payload[:120]!r}"
    if not token:
        return None, f"the token grant carried no token: {payload[:120]!r}"
    return token, None


def exists(root, image, tag=None, repo=None, base=REGISTRY_BASE, timeout=REGISTRY_TIMEOUT_S):
    """Answer "is this tag published?" and nothing else; returns the exit code.

    Two anonymous GETs, no docker, no credential, nothing downloaded. The asked
    tag goes to stdout, every diagnostic to stderr, as with --resolve.

    Existence is all it can prove, and the wording below says so on purpose:
    the caller that wants "we do not need to build this" needs --resolve.
    """
    asked = tag or fingerprint(root, image)
    repo = repo or REGISTRY_REPO[image]
    ref = f"{repo}:{asked}"
    token_url, manifest_url = registry_endpoints(repo, asked, base)

    token, problem = anonymous_pull_token(token_url, timeout=timeout)
    if token is None:
        _note(f"EXISTS: cannot look at {ref} - {problem}")
        _note("this says nothing about whether the tag exists: a private package refuses "
              "an anonymous read exactly like a missing one. If the package is private, ask "
              "with docker (it uses this host's credential) or make it public; if the "
              "registry is merely unreachable, retry.")
        print(asked)
        return EXIT_TRANSIENT

    status, headers, body = http_get(
        manifest_url,
        headers={"User-Agent": USER_AGENT, "Accept": MANIFEST_MEDIA_TYPE,
                 "Authorization": f"Bearer {token}"},
        timeout=timeout)
    kind, said = classify_manifest_answer(
        status, body, detail="" if status is not None else str(body))

    if kind == "published":
        digest = headers.get("Docker-Content-Digest") or headers.get("docker-content-digest")
        _note(f"EXISTS: {ref} is published" + (f" as manifest {digest}" if digest else ""))
        _note("existence only: no layer was downloaded, so this does not say the content "
              "arrives intact or runs here. Use --resolve when the image is really wanted.")
        print(asked)
        return EXIT_OK
    if kind == "absent":
        _note(f"EXISTS: {ref} is not published ({said})")
        _note("never published is not the same as unimportant: the publish of this "
              "fingerprint may simply not have run yet. See the --resolve miss message "
              "for the sanctioned fallbacks.")
        print(asked)
        return EXIT_MISS
    if kind == "denied":
        _note(f"EXISTS: the registry refuses an anonymous read of {ref} ({said})")
        _note("refused is not absent. A private package answers like this for a tag it "
              "publishes; ask with docker, which has this host's credential.")
        print(asked)
        return EXIT_TRANSIENT
    if kind == "ambiguous":
        _note(f"EXISTS: the registry answered 404 for {ref} but not with \"manifest unknown\" ({said})")
        _note("that is a difference we cannot resolve from here, so this is NOT read as "
              "'not published': the request may not be in a language this registry answers "
              "(ghcr needs the OCI manifest media type, see MANIFEST_MEDIA_TYPE), or the "
              "package may have become a multi-arch index. --resolve asks with docker and "
              "is not fooled by either; report the answer shape upstream.")
        print(asked)
        return EXIT_TRANSIENT
    if kind == "malformed":
        _note(f"EXISTS: {said}")
        _note("an answer this tool cannot read is not an answer about the tag; retry or use --resolve.")
    else:
        _note(f"EXISTS: could not look at {ref} - {said}")
        _note("the registry or the network did not answer properly. Nothing was learned about "
              "the tag; retry, or use --resolve to let docker try with this host's credential.")
    print(asked)
    return EXIT_TRANSIENT


# --------------------------------------------------------------------------
# self-check (--self-check): offline property tests
# --------------------------------------------------------------------------


def self_check(root):
    """Verify the contract properties on a throwaway copy, never on the checkout.

    A minimal dependency tree is assembled in a temp directory: the real
    Dockerfile and requirements files plus one dummy application source file.
    """
    results = []
    with tempfile.TemporaryDirectory(prefix="mrmap-dev-image-id-") as tmp:
        work = Path(tmp)
        (work / BACKEND_DOCKERFILE).parent.mkdir(parents=True)
        shutil.copyfile(root / BACKEND_DOCKERFILE, work / BACKEND_DOCKERFILE)
        requirements = work / BACKEND_REQUIREMENTS_DIR
        requirements.mkdir(parents=True)
        for dependency_file in sorted((root / BACKEND_REQUIREMENTS_DIR).iterdir()):
            if dependency_file.is_file():
                shutil.copyfile(dependency_file, requirements / dependency_file.name)
        frontend_dir = work / "frontend"
        frontend_dir.mkdir(parents=True)
        for name in (FRONTEND_PACKAGE_JSON, FRONTEND_PACKAGE_LOCK):
            shutil.copyfile(root / name, work / name)
        (work / FRONTEND_DOCKERFILE).parent.mkdir(parents=True, exist_ok=True)
        for name in (FRONTEND_DOCKERFILE, FRONTEND_ENTRYPOINT):
            shutil.copyfile(root / name, work / name)
        source = work / "backend" / "MrMap" / "settings.py"
        source.parent.mkdir(parents=True)
        source.write_text("# original source content\n")
        fe_source = work / "frontend" / "src" / "App.tsx"
        fe_source.parent.mkdir(parents=True)
        fe_source.write_text("// original frontend source\n")

        fp = fingerprint(work, "backend")
        results.append(("backend fingerprint is 12 lowercase hex digits",
                        re.fullmatch(r"[0-9a-f]{12}", fp) is not None))
        results.append(("backend deterministic across repeated runs",
                        fingerprint(work, "backend") == fp))

        (requirements / "selfcheck.txt").write_text("pinned-dep==1.2.3\n")
        results.append(("added requirements .txt changes the backend fingerprint",
                        fingerprint(work, "backend") != fp))
        (requirements / "selfcheck.txt").unlink()

        base = requirements / "base.txt"
        base_backup = base.read_text()
        base.write_text(base_backup + "\n# touched by self-check\n")
        results.append(("touched requirements .txt changes the backend fingerprint",
                        fingerprint(work, "backend") != fp))
        base.write_text(base_backup)

        dockerfile_backup = (work / BACKEND_DOCKERFILE).read_text()
        (work / BACKEND_DOCKERFILE).write_text(
            dockerfile_backup.replace("FROM ", "FROM ", 1) + "\n# touched\n")
        results.append(("touched backend Dockerfile changes the fingerprint",
                        fingerprint(work, "backend") != fp))
        (work / BACKEND_DOCKERFILE).write_text(dockerfile_backup)

        df_text = (work / BACKEND_DOCKERFILE).read_text()
        (work / BACKEND_DOCKERFILE).write_text(
            df_text.replace("python:3.15.2-alpine3.24", "python:3.14.0-alpine3.22")
            + "\n# touched\n")
        results.append(("changed FROM pin changes the backend fingerprint",
                        fingerprint(work, "backend") != fp))
        (work / BACKEND_DOCKERFILE).write_text(dockerfile_backup)

        source.write_text("# changed application source only\n")
        results.append(("source-file change keeps the backend fingerprint",
                        fingerprint(work, "backend") == fp))

        # -- frontend image contract ----------------------------------------
        ffp = fingerprint(work, "frontend")
        results.append(("frontend fingerprint is 12 lowercase hex digits",
                        re.fullmatch(r"[0-9a-f]{12}", ffp) is not None))
        results.append(("frontend deterministic across repeated runs",
                        fingerprint(work, "frontend") == ffp))

        lock = work / FRONTEND_PACKAGE_LOCK
        lock_backup = lock.read_bytes()
        lock.write_bytes(lock_backup + b"\n")
        results.append(("lockfile change changes the frontend fingerprint",
                        fingerprint(work, "frontend") != ffp))
        lock.write_bytes(lock_backup)

        pkg = work / FRONTEND_PACKAGE_JSON
        pkg_backup = pkg.read_bytes()
        pkg.write_bytes(pkg_backup.replace(b'"name"', b'"namex"', 1))
        results.append(("package.json change changes the frontend fingerprint",
                        fingerprint(work, "frontend") != ffp))
        pkg.write_bytes(pkg_backup)

        fe_df = work / FRONTEND_DOCKERFILE
        fe_df_backup = fe_df.read_text()
        fe_df.write_text(fe_df_backup + "\n# touched\n")
        results.append(("Dockerfile change changes the frontend fingerprint",
                        fingerprint(work, "frontend") != ffp))
        fe_df.write_text(fe_df_backup)

        ep = work / FRONTEND_ENTRYPOINT
        ep_backup = ep.read_text()
        ep.write_text(ep_backup + "\n# touched\n")
        results.append(("entrypoint change changes the frontend fingerprint",
                        fingerprint(work, "frontend") != ffp))
        ep.write_text(ep_backup)

        fe_df.write_text(fe_df_backup.replace("node:26-alpine", "node:25-alpine"))
        results.append(("FROM/node version pin change changes the frontend fingerprint",
                        fingerprint(work, "frontend") != ffp))
        fe_df.write_text(fe_df_backup)

        fe_source.write_text("// changed frontend source only\n")
        results.append(("frontend source-file change keeps the frontend fingerprint",
                        fingerprint(work, "frontend") == ffp))

        results.append(("frontend fingerprint does not move with backend files",
                        fingerprint(work, "frontend") == ffp))
        backend_inputs = [work / BACKEND_DOCKERFILE] + sorted(requirements.iterdir())
        fp_before = fingerprint(work, "backend")
        (requirements / "another.txt").write_text("x==1\n")
        results.append(("backend and frontend manifests stay independent",
                        fingerprint(work, "backend") != fp_before
                        and fingerprint(work, "frontend") == ffp))
        (requirements / "another.txt").unlink()
        for dep in backend_inputs:
            dep.touch()
        results.append(("backend fp still stable after isolation test",
                        fingerprint(work, "backend") == fp_before))

        # -- deps marker formula (sync contract with #963) ------------------
        marker_a = deps_marker(work, "v26.13.0", "11.20.0")
        marker_b = deps_marker(work, "v26.13.0", "11.20.0")
        marker_new = deps_marker(work, "v26.99.0", "11.20.0")
        results.append(("deps marker is 12 lowercase hex digits",
                        marker_a is not None
                        and re.fullmatch(r"[0-9a-f]{12}", marker_a) is not None))
        results.append(("deps marker deterministic", marker_a == marker_b))
        results.append(("node version pin changes the deps marker", marker_new != marker_a))
        lock.write_bytes(lock_backup + b" ")
        results.append(("lockfile change changes the deps marker",
                        deps_marker(work, "v26.13.0", "11.20.0") != marker_a))
        lock.write_bytes(lock_backup)
        fe_df.write_text(fe_df_backup + "\n# touched by self-check\n")
        results.append(("deps marker insensitive to Dockerfile-only changes",
                        deps_marker(work, "v26.13.0", "11.20.0") == marker_a))
        fe_df.write_text(fe_df_backup)

        # -- concurrency: read-only means nothing to corrupt -----------------
        before = sorted((p.relative_to(work).as_posix(), p.stat().st_mtime_ns)
                        for p in work.rglob("*") if p.is_file())
        outputs = {}
        errors = []

        def worker(index):
            try:
                outputs[index] = (fingerprint(work, "backend"),
                                  fingerprint(work, "frontend"))
            except BaseException as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        results.append(("8 concurrent fingerprint runs raise no error", not errors))
        results.append(("8 concurrent fingerprint runs agree exactly",
                        len(set(outputs.values())) == 1 and len(outputs) == 8))
        after = sorted((p.relative_to(work).as_posix(), p.stat().st_mtime_ns)
                       for p in work.rglob("*") if p.is_file())
        results.append(("concurrent fingerprinting writes nothing", before == after))

    # -- resolver failure classification (canned docker output) ------------
    cases = [
        ("Error response from daemon: pull access denied for ghcr.io/x/y, "
         "repository does not exist or may require 'docker login': denied: "
         "requested access to the resource is denied", "miss"),
        ("failed to resolve reference ghcr.io/x/y: error: "
         "manifest unknown", "miss"),
        ("failed to copy: httpReadSeeker: readObject: "
         "net/http: TLS handshake timeout", "transient"),
        ("dial tcp: lookup ghcr.io on 127.0.0.53:53: no such host", "transient"),
        ("toomanyrequests: you have exceeded your unauthenticated "
         "image pull limit", "transient"),
        ("failed to resolve source metadata: no match for platform in "
         "manifest: (linux, arm64)", "platform"),
        ("something entirely unexpected happened", "unknown"),
    ]
    results.append(("resolver classifies every canned docker failure correctly",
                    all(classify_pull_failure(text) == want for text, want in cases)))

    # -- existence probe: canned registry answers (the request itself is the
    #    test file's job, over a stub) --------------------------------------
    def answer(body, status=200):
        raw = body.encode("utf-8") if isinstance(body, str) else body
        return classify_manifest_answer(status, raw)[0]

    ghcr_manifest = json.dumps({
        "schemaVersion": 2,
        "mediaType": MANIFEST_MEDIA_TYPE,
        "config": {"digest": "sha256:aaa"},
    }).encode()
    unknown = b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"manifest unknown"}]}\n'
    wrong_language = (b'{"errors":[{"code":"MANIFEST_UNKNOWN","message":"OCI manifest '
                      b'found, but Accept header does not support OCI manifests"}]}')
    results.append(("canned manifest 200 is published",
                    classify_manifest_answer(200, ghcr_manifest)[0] == "published"))
    results.append(("canned 404 'manifest unknown' is absent",
                    classify_manifest_answer(404, unknown)[0] == "absent"))
    # The two 404s above look the same by status and code alone; only the
    # message tells them apart, and mixing them up is the expensive direction.
    results.append(("canned 404 about the Accept header is NOT absent",
                    classify_manifest_answer(404, wrong_language)[0] == "ambiguous"))
    results.append(("canned 404 with no recognised wording is NOT absent",
                    classify_manifest_answer(404, b"gateway said no")[0] == "ambiguous"))
    results.append(("canned 200 that is not a manifest is malformed",
                    answer("<html>502 bad gateway</html>", 200) == "malformed"))
    results.append(("canned 401 and 403 are denied, never absent",
                    classify_manifest_answer(401, unknown)[0] == "denied"
                    and classify_manifest_answer(403, unknown)[0] == "denied"))
    results.append(("canned 500, 429 and 408 are transient",
                    answer(b"boom", 500) == "transient" and answer(b"", 429) == "transient"
                    and answer(b"", 408) == "transient"))
    results.append(("a transport failure is unreachable, not absent",
                    classify_manifest_answer(None, b"", "Connection refused")[0] == "unreachable"))
    results.append(("the probe sends exactly one media type, not a wildcard",
                    MANIFEST_MEDIA_TYPE == "application/vnd.oci.image.manifest.v1+json"))
    token_url, manifest_url = registry_endpoints(
        "ghcr.io/mrmap-community/mrmap-backend-dev", "9aaf0524cd23")
    token_parts = urllib.parse.parse_qs(urllib.parse.urlparse(token_url).query)
    results.append(("the token grant asks for pull on this repository only",
                    urllib.parse.urlparse(token_url).path == "/token"
                    and token_parts.get("service") == ["ghcr.io"]
                    and token_parts.get("scope")
                    == ["repository:mrmap-community/mrmap-backend-dev:pull"],
                    token_url))
    results.append(("the manifest request addresses the tag under /v2/",
                    manifest_url == "https://ghcr.io/v2/mrmap-community/mrmap-backend-dev"
                    "/manifests/9aaf0524cd23", manifest_url))
    stub_token, stub_manifest = registry_endpoints(
        "ghcr.io/mrmap-community/mrmap-backend-dev", "ab", base="http://127.0.0.1:9")
    stub_scope = urllib.parse.parse_qs(urllib.parse.urlparse(stub_token).query).get("scope")
    results.append(("a --repo override keeps the reference's host out of the API path",
                    stub_manifest == "http://127.0.0.1:9/v2/mrmap-community/mrmap-backend-dev"
                    "/manifests/ab"
                    and stub_scope == ["repository:mrmap-community/mrmap-backend-dev:pull"],
                    stub_manifest))

    width = max(len(entry[0]) for entry in results)
    failed = [entry[0] for entry in results if not entry[1]]
    for entry in results:
        # an entry is (name, ok) or (name, ok, detail); the detail is printed for
        # a failure only, where the raw value read is the useful half of it.
        line = f"{'PASS' if entry[1] else 'FAIL'}  {entry[0]:<{width}}"
        if not entry[1] and len(entry) > 2:
            line += f"   <- {entry[2]}"
        print(line)
    if failed:
        print(f"self-check FAILED ({len(failed)} of {len(results)} checks)", file=sys.stderr)
        return 1
    print(f"self-check OK ({len(results)} checks) on a copy of {root}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="fingerprint and resolve the mrmap dev images (epic #959)"
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="checkout to read (defaults to the repository holding this script)")
    parser.add_argument("--image", choices=IMAGES, default="backend",
                        help="which dev image the command refers to (default: backend)")
    parser.add_argument("--print-build-args", action="store_true",
                        help="print the docker build args the fingerprint "
                        "assumes instead of the fingerprint")
    parser.add_argument("--deps-marker", action="store_true",
                        help="print the in-container dependency marker "
                        "(frontend image contract with #963) instead of the "
                        "image fingerprint; needs --node-version and --npm-version")
    parser.add_argument("--node-version", default=None,
                        help="`node -v` output of the FROM-pinned base image, for --deps-marker")
    parser.add_argument("--npm-version", default=None,
                        help="`npm -v` output of the FROM-pinned base image, for --deps-marker")
    parser.add_argument("--resolve", action="store_true",
                        help="ensure the fp-tagged image is locally available: "
                        "hit/pull, loud miss, --build for the local fallback")
    parser.add_argument("--exists", action="store_true",
                        help="ask the registry whether this tag is published: "
                        "anonymous token plus one manifest request, no docker, "
                        "nothing downloaded (existence only)")
    parser.add_argument("--fp", default=None, metavar="TAG",
                        help="with --exists: ask about this tag instead of this "
                             "checkout's fingerprint (any tag works, e.g. main)")
    parser.add_argument("--timeout", type=float, default=REGISTRY_TIMEOUT_S,
                        help=argparse.SUPPRESS)  # test hook: cap on both registry reads
    parser.add_argument("--registry-base", default=REGISTRY_BASE,
                        help=argparse.SUPPRESS)  # test hook: registry origin for --exists
    parser.add_argument("--build", action="store_true",
                        help="with --resolve: build locally under the "
                        "immutable tag when the pull misses (sanctioned fallback)")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --resolve: print the plan and the fp, touch nothing")
    parser.add_argument("--repo", default=None,
                        help=argparse.SUPPRESS)  # resolver test hook: registry repo override
    parser.add_argument("--self-check", action="store_true",
                        help="verify fingerprint determinism and input "
                        "sensitivity on a throwaway tree")
    args = parser.parse_args(argv)

    root = args.repo_root.resolve()
    if args.self_check:
        return self_check(root)
    if args.exists:
        if args.fp and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}", args.fp):
            raise SystemExit(f"dev_image_id: --exists cannot ask about {args.fp!r}: "
                             "a registry tag is 128 characters of [A-Za-z0-9._-], "
                             "starting alphanumeric or _")
        return exists(root, args.image, tag=args.fp, repo=args.repo,
                      base=args.registry_base, timeout=args.timeout)
    if args.resolve:
        return resolve(root, args.image, build=args.build, dry_run=args.dry_run,
                       repo=args.repo)
    if args.print_build_args:
        print(print_build_args(args.image))
        return 0
    if args.deps_marker:
        if args.image != "frontend":
            raise SystemExit("dev_image_id: --deps-marker is the frontend "
                             "image's in-container contract (--image frontend)")
        marker = deps_marker(root, args.node_version, args.npm_version)
        if marker is None:
            raise SystemExit("dev_image_id: --deps-marker needs --node-version "
                             "and --npm-version (from the FROM-pinned base image)")
        print(marker)
        return 0
    print(fingerprint(root, args.image))
    return 0


if __name__ == "__main__":
    sys.exit(main())
