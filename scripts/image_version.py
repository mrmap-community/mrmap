#!/usr/bin/env python3
"""image_version: identity, tags and deployment coherence for the app images.

Run from the repository root as `python3 scripts/image_version.py <action>`.
Standard library only, no docker (except `--verify-image`), no network, no gh.
Exit 0 = ok, 1 = a policy or coherence rule was violated, 2 = usage error,
3 = the tool could not run here (missing file, no docker CLI, ...).

Why this tool exists
--------------------
#1582 turns the first-party application images (backend, frontend) from
"build: sections with no image reference" (release-versioning-baseline.rst,
measured) into versioned artifacts. Every artifact needs one provable
identity, and the identity must not be re-invented per build path:

  * the version is the canonical application version - the root ``VERSION``
    file (#1579), read through ``scripts/canonical_version.py``;
  * the revision is the exact source commit the image was built from;
  * the source is this repository's canonical URL.

Those three become the OCI labels ``org.opencontainers.image.version``,
``.revision`` and ``.source`` baked into the images, and they decide the
tags. One script computes them so the CI workflow, the deploy manifests and
a human at a console all ask the same question the same way.

Tag policy (acceptance criteria of #1582)
-----------------------------------------
channel    when                          tags emitted
stable     VERSION has no prerelease     ``<version>`` (immutable) only
           and the caller says stable
prerelease VERSION carries a prerelease  the full prerelease version
           (``0.2.0-rc.1``)                 ``dev-<revision>`` (traceability)
dev        any VERSION                   ``dev-<revision>`` only

A dev or prerelease build can never emit a stable-shaped tag: guard_tags
accepts exactly the tag set derive_tags derives from the same identity, so
"dev/RC overwriting a stable alias" is refused at the tool, not discovered
at the registry. Rolling aliases (``latest`` and friends) are an approval
question, not a technical one: APPROVED_ROLLING_ALIASES is the approved
set and it is deliberately EMPTY until a maintainer decides otherwise.
Only the stable channel may use an approved alias at all.

Immutable digests, one build
----------------------------
A candidate is built once and pushed once; anything that happens to it
afterwards (a stable tag, an RC promotion) re-points a NAME at the already
pushed digest - ``docker buildx imagetools create -t <repo>:<tag>
<repo>@sha256:...`` - never rebuilds. The digests of a build are printed
into the CI step summary. Who may run that retag, and when, is the
protected promotion of #1584; this file only provides the mechanics and
the guard.

Actions
-------
  --print                       print the canonical version
  --tags                        print the bare tags for --channel (one per line)
  --guard                       verify --tags equals the derived tag set
  --build-args                  docker build args (MRMAP_VERSION,...) as one
                                compact k=v,... line; docker/build-push-action
                                wants newline-separated, pipe through
                                `tr ',' '\n'` (app-images.yml does)
  --labels                      the OCI label set as KEY=VALUE lines
  --manifest                    the deployment manifest (JSON) for --channel
  --check-deploy                coherence/pinning/secrets checks over deploy/
  --verify-image REF            docker inspect REF's labels against the identity
  --digest REF                  print the registry digest a tag resolves to
                                (buildx imagetools; the identity promotion
                                retags, docs/versioned-images.rst)
  --self-check                  offline self-test of every rule above

Common flags: --channel dev|prerelease|stable (required where it matters),
--revision <40-hex> (CI passes the exact commit; without it the tool asks
git), --image backend|frontend|all, --env FILE (extra deployment env).

A missing or invalid VERSION fails every action: the same rule
canonical_version.py states for the application build (#1579) - a build
that cannot name its version must fail.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import canonical_version  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# The first-party APPLICATION images (#1582). The dependency images
# mrmap-backend-dev / mrmap-frontend-dev published by dev-images.yml are NOT
# application artifacts: they keep their dependency-fingerprint tags from the
# epic #959 contract, and nothing here touches them.
APP_IMAGES = {
    "backend": "ghcr.io/mrmap-community/mrmap-backend",
    "frontend": "ghcr.io/mrmap-community/mrmap-frontend",
}

# The canonical origin. Hardcoded on purpose: the source label of a published
# artifact must not depend on which remote URL a build machine happens to
# have configured.
SOURCE_URL = "https://github.com/mrmap-community/mrmap"

IMAGE_TITLE = {
    "backend": "MrMap backend",
    "frontend": "MrMap frontend",
}
IMAGE_DESCRIPTION = {
    "backend": "The MrMap spatial data infrastructure registry (Django backend, "
               "Celery worker and beat entrypoints share this image).",
    "frontend": "The MrMap single page application served by nginx, with the "
                "backend's collected static files baked in.",
}

# The repository's LICENSE file is MIT.
LICENSE = "MIT"

# Rolling aliases a deployment may ever see on the application images. A
# rolling alias is a maintainer decision ("only approved rolling aliases" of
# #1582), not something a build script may invent: extending this set is a
# human reviewing a pull request, and until then NO channel ever emits an
# alias, only the exact tags derive_tags computes.
APPROVED_ROLLING_ALIASES = frozenset()

CHANNELS = ("dev", "prerelease", "stable")

# A full commit hash - the only shape an artifact revision accepts. Short
# hashes are ambiguous across forks and rewritten histories; an artifact
# names the commit it was built from exactly.
HEX40 = re.compile(r"^[0-9a-f]{40}$")

# strict SemVer without prerelease/build metadata: what a STABLE tag looks
# like. Anything matching a version shape that is NOT this (or this plus a
# prerelease equal to VERSION) is not a stable-shaped tag, and a stable-shaped
# tag may only come from the stable channel.
STABLE_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

PRERELEASE_MARK = "-"

BASE_COMPOSE = "docker-compose.yml"
DEPLOY_DIR = "deploy"
DEPLOY_COMPOSE = "deploy/docker-compose.images.yml"
DEPLOY_ENV_EXAMPLE = "deploy/images.env.example"

# An env value in the committed example: a stable version, optionally pinned
# by digest. A dev artifact (dev-<sha>) is deployable by setting MRMAP_IMAGE_TAG
# by hand; the committed EXAMPLE shows the stable shape.
# What a deployment may name as its artifact: the canonical SemVer (#1579)
# with an optional @sha256:... digest suffix, or a dev-<exact-commit> build.
# Spliced from canonical_version.SEMVER_PATTERN - one semver grammar in this
# repository, never a hand-copied second opinion of it.
_SEMVER_BARE = canonical_version.SEMVER_PATTERN.pattern
if _SEMVER_BARE.startswith("^"):
    _SEMVER_BARE = _SEMVER_BARE[1:]
if _SEMVER_BARE.endswith("$"):
    _SEMVER_BARE = _SEMVER_BARE[:-1]
PINNED_TAG = re.compile(
    rf"^(?:dev-[0-9a-f]{{40}}|{_SEMVER_BARE}(?:@sha256:[0-9a-f]{{64}})?)$")
DIGEST_VALUE = re.compile(r"^sha256:[0-9a-f]{64}$")

# Names that must never carry a literal value in a committed deployment file
# (the "no secrets" acceptance criterion): the value is always a ${VAR}
# interpolation resolved from the operator's .env.
SECRETISH = re.compile(r"(SECRET|PASSWORD|TOKEN|PRIVATE_KEY|API_KEY|ACCESS_KEY)",
                       re.IGNORECASE)
INTERPOLATION = re.compile(r"\$\{[^}]*\}")

EXIT_OK, EXIT_POLICY, EXIT_USAGE, EXIT_CANNOT = 0, 1, 2, 3


class IdentityError(Exception):
    """The requested identity is missing, inconsistent, or violates policy."""


def read_version(root=REPO):
    """The canonical application version, or IdentityError (never a guess)."""
    try:
        return canonical_version.read_version(root)
    except canonical_version.VersionError as error:
        raise IdentityError(str(error)) from None


def has_prerelease(version):
    """Whether a canonical version carries a SemVer prerelease section."""
    core = version.split("+", 1)[0]
    return PRERELEASE_MARK in core


def git_revision(root=REPO):
    """The exact commit of this checkout via git; IdentityError when absent."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise IdentityError("git is not available and no --revision was given")
    if proc.returncode != 0:
        raise IdentityError(
            f"`git rev-parse HEAD` failed in {root}: {proc.stderr.strip()}")
    revision = proc.stdout.strip()
    if not HEX40.match(revision):
        raise IdentityError(f"`git rev-parse HEAD` answered {revision!r}")
    return revision


def worktree_dirty(root=REPO):
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain"],
        capture_output=True, text=True, timeout=30)
    return bool(proc.stdout.strip())


def resolve_revision(root=REPO, override=None, channel="dev"):
    """The exact source commit an artifact may claim, and a warning string.

    CI passes --revision (the checked-out commit); a local build may ask git.
    An artifact on the prerelease or stable channel must be built from a
    COMMITTED tree: a dirty worktree would bake unreviewed bytes under a
    published name, so it is refused. The dev channel only warns - a dev
    artifact is named by its revision, and what it is stays its own
    business.
    """
    if override:
        if not HEX40.match(override):
            raise IdentityError(
                f"--revision must be a full 40-hex commit hash, got {override!r}")
        return override, ""
    revision = git_revision(root)
    if channel in ("prerelease", "stable"):
        if worktree_dirty(root):
            raise IdentityError(
                f"channel {channel} requires a clean worktree: HEAD {revision} "
                "has uncommitted changes, so an artifact built here would "
                "claim a commit that does not describe its bytes")
    elif worktree_dirty(root):
        return revision, ("warning: worktree is dirty; the artifact is named "
                          f"after commit {revision} but carries uncommitted bytes")
    return revision, ""


def derive_tags(version, revision, channel,
                rolling=APPROVED_ROLLING_ALIASES):
    """The exact, complete tag set a channel may publish for an identity.

    This is the tag POLICY of #1582, in one function so the workflow, the
    guard and a human all read the same rules.
    """
    canonical_version.SEMVER_PATTERN.match(version) or _bad_version(version)
    if not HEX40.match(revision):
        raise IdentityError(f"revision {revision!r} is not a 40-hex commit hash")
    if channel == "stable":
        if has_prerelease(version):
            raise IdentityError(
                f"channel stable refuses the prerelease version {version}: a "
                "stable tag names only a released version (VERSION is the "
                "single source, #1579)")
        tags = {version}
        if rolling:
            if not STABLE_VERSION.match(version):
                raise IdentityError("internal: rolling on a non-stable version")
            tags |= set(rolling)
        return tags
    if channel == "prerelease":
        if not has_prerelease(version):
            raise IdentityError(
                f"channel prerelease needs a prerelease VERSION (e.g. "
                f"0.2.0-rc.1); VERSION reads {version}, so there is nothing "
                "to prerelease")
        # The full prerelease version string is immutable by SemVer itself:
        # rc.2 is a different version, so publishing never moves rc.1. The
        # BARE 0.2.0 form is what an RC must never touch - it is absent here.
        return {version, f"dev-{revision}"}
    if channel == "dev":
        # "SHA-tagged dev builds": a dev build owns exactly one name, its
        # commit. Versions belong to releases, not to every merge.
        return {f"dev-{revision}"}
    raise IdentityError(f"unknown channel {channel!r}, expected one of "
                        + ", ".join(CHANNELS))


def _bad_version(version):
    raise IdentityError(
        f"{version!r} is not a strict SemVer 2.0.0 version; the canonical "
        "VERSION file is the only source and it is validated by "
        "scripts/canonical_version.py")


def guard_tags(version, revision, channel, tags,
               rolling=APPROVED_ROLLING_ALIASES):
    """Refuse any tag a caller is not entitled to publish. Returns the set.

    The guard is exact-equality against derive_tags: an EXTRA tag is refused
    (that is the stable alias someone appended), a MISSING tag is refused
    (a partial push would leave an alias behind an unknown digest), and a
    channel mismatch was already refused by derive_tags. The workflow runs
    this before any push step, and a push step without it cannot exist in
    .github/workflows/app-images.yml (scripts/test_image_version.py pins
    that wiring).
    """
    allowed = derive_tags(version, revision, channel, rolling)
    asked = set(tags)
    extra = sorted(asked - allowed)
    missing = sorted(allowed - asked)
    if extra:
        named = ", ".join(extra)
        stable_offenders = [t for t in extra if STABLE_VERSION.match(t)]
        hint = ""
        if stable_offenders:
            hint = (f" (stable-shaped tag(s) {', '.join(stable_offenders)} "
                    "cannot come from the "
                    f"{channel} identity - a stable alias is published only "
                    "from channel stable, and only by the protected "
                    "promotion of #1584)")
        elif any(t in APPROVED_ROLLING_ALIASES or t in
                 ("latest", "main", "edge", "stable") for t in extra):
            hint = " (rolling aliases are the approved set in " \
                "scripts/image_version.py, which no build may extend)"
        raise IdentityError(
            f"guard: tags not derivable from {channel} version {version} "
            f"revision {revision}: {named}{hint}")
    if missing:
        raise IdentityError(
            f"guard: the {channel} identity {version}@{revision[:12]} also "
            f"requires tag(s) {', '.join(missing)}; a partial push would "
            "leave a name pointing at an unknown digest")
    return asked


def label_set(version, revision, channel, image, source=SOURCE_URL):
    """The OCI labels one application image carries (#1582 acceptance)."""
    if image not in APP_IMAGES:
        raise IdentityError(f"unknown app image {image!r}")
    return {
        "org.opencontainers.image.title": IMAGE_TITLE[image],
        "org.opencontainers.image.description": IMAGE_DESCRIPTION[image],
        "org.opencontainers.image.licenses": LICENSE,
        "org.opencontainers.image.version": version,
        "org.opencontainers.image.revision": revision,
        "org.opencontainers.image.source": source,
        "io.github.mrmap.channel": channel,
    }


def build_args(version, revision, channel, source=SOURCE_URL):
    """The docker build args the versioned identity requires.

    docker/backend/alpine.Dockerfile (production-image stage) and
    docker/nginx/nginx.Dockerfile declare these ARGs and LABEL them; the
    production stage of the backend also REFUSES an empty or malformed set.
    """
    return ",".join([
        f"MRMAP_VERSION={version}",
        f"MRMAP_REVISION={revision}",
        f"MRMAP_SOURCE={source}",
        f"MRMAP_CHANNEL={channel}",
    ])


def third_party_pins(root=REPO):
    """Every ``image:`` reference the base compose pulls, as written.

    Third-party images stay independently pinned exactly as they are today
    (release-versioning-baseline.rst: every one already carries an exact
    version); --check-deploy only verifies they STAY exact.
    """
    text = (root / BASE_COMPOSE).read_text(encoding="utf-8")
    pins = {}
    for match in re.finditer(
            r"^\s+image:\s*(\S+)\s*(?:#.*)?$", text, re.MULTILINE):
        ref = match.group(1)
        pins[ref] = ref
    return sorted(pins)


def _ref_is_pinned(ref):
    """A reference is pinned when it names an exact tag (never :latest).

    A ref without any tag (``busybox``) is implicitly ``:latest``; an
    ``image@sha256:...`` digest is pinned; ``host:5000/repo`` must not be
    mistaken for a tag on the last path segment.
    """
    if "@sha256:" in ref:
        return True
    last = ref.rsplit("/", 1)[-1]
    if ":" not in last:
        return False
    return last.rsplit(":", 1)[-1] != "latest"


def manifest(root=REPO, version=None, revision=None, channel="dev"):
    """The deployment manifest: one coherent, fully named image set.

    JSON on stdout; the shape is versioned (format field) so a later
    extension cannot silently collide. Every mrmap service of the reference
    deployment maps to ONE tag of its image - the coherence rule an operator
    needs is that the set moved together, and one tag variable in
    deploy/docker-compose.images.yml makes that structural.
    """
    if version is None:
        version = read_version(root)
    tags = sorted(derive_tags(version, revision, channel))
    return {
        "format": "mrmap-deployment-manifest/1",
        "version": version,
        "revision": revision,
        "channel": channel,
        "source": SOURCE_URL,
        "images": {
            "mrmap-backend": {
                "repository": APP_IMAGES["backend"],
                "services": ["backend", "celery-worker", "celery-beat"],
                "tags": tags,
            },
            "mrmap-frontend": {
                "repository": APP_IMAGES["frontend"],
                "services": ["frontend"],
                "tags": tags,
            },
        },
        "third_party": {ref: ref for ref in third_party_pins(root)},
    }


# ---------------------------------------------------------------------------
# deployment coherence (--check-deploy)
# ---------------------------------------------------------------------------

def _service_blocks(text):
    """Split a compose file into {service: block} on two-space service keys."""
    blocks = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if match:
            current = match.group(1)
            blocks[current] = []
        elif current is not None and not re.match(r"^[a-zA-Z]", line):
            blocks[current].append(line)
        elif re.match(r"^[a-zA-Z]", line):
            current = None
    return {name: "\n".join(body) for name, body in blocks.items()}


def check_env_file(path, require_pinned=True):
    """Rules for one deployment env file. Returns a list of problems."""
    problems = []
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return [f"{path} does not exist"]
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        where = f"{path}:{number}"
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", stripped)
        if not match:
            problems.append(f"{where}: not a KEY=VALUE line")
            continue
        key, value = match.groups()
        if SECRETISH.search(key) and value and not INTERPOLATION.search(value):
            problems.append(
                f"{where}: {key} carries a literal secret in a deployment "
                "file; secrets are ${VAR} interpolation from the operator's "
                ".env only")
        if key == "MRMAP_IMAGE_TAG" and require_pinned:
            if value in ("", "latest", "main", "edge", "dev"):
                problems.append(
                    f"{where}: MRMAP_IMAGE_TAG={value!r} is a moving target; "
                    "an artifact deployment names an exact version (or a "
                    "dev-<commit> artifact)")
            elif not PINNED_TAG.match(value):
                problems.append(
                    f"{where}: MRMAP_IMAGE_TAG={value!r} is not an exact "
                    "version, an exact version @sha256:... digest, or "
                    "dev-<40-hex-commit>")
        if key.endswith("_IMAGE_DIGEST") and value:
            if not DIGEST_VALUE.match(value):
                problems.append(
                    f"{where}: {key} must be sha256:<64 hex>, not {value!r}")
    return problems


def check_deploy(root=REPO, extra_env=None):
    """Every deployment coherence rule of #1582, offline.

    What an operator can get wrong with an image-based deployment, this
    refuses: two mrmap services on different versions, an overlay that
    silently keeps a ``build:`` section (compose would rebuild over the
    pinned artifact), a bind mount of the checkout over the baked code (the
    #922/#1027 stale-shadow failure, this time at /opt/mrmap), a floating
    tag, a third-party image that stopped being exact, a literal secret.
    """
    problems = []
    compose_path = root / DEPLOY_COMPOSE
    if not compose_path.is_file():
        return [f"{DEPLOY_COMPOSE} is missing"]
    text = compose_path.read_text(encoding="utf-8")
    blocks = _service_blocks(text)

    # (repository, must the build: section be reset?) - the backend trio is
    # pull-only, the frontend deliberately keeps its build: section because
    # the SPA bundle bakes the DEPLOYMENT's API address (#922/#1027); its
    # pinned image still names the coherent set. See the file's header.
    want = {
        "backend": (APP_IMAGES["backend"], True),
        "celery-worker": (APP_IMAGES["backend"], True),
        "celery-beat": (APP_IMAGES["backend"], True),
        "frontend": (APP_IMAGES["frontend"], False),
    }
    for service, (repo, reset_required) in want.items():
        block = blocks.get(service)
        if block is None:
            problems.append(
                f"{DEPLOY_COMPOSE}: service {service} is missing - a "
                "deployment overlay must pin every mrmap service")
            continue
        if reset_required and not re.search(
                r"^\s+build:\s*!reset\b", block, re.MULTILINE):
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: build: must be reset "
                "(`build: !reset null`) - leaving it lets compose silently "
                "rebuild over the pinned artifact")
        image_match = re.search(r"^\s+image:\s*(\S+)", block, re.MULTILINE)
        if not image_match:
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: no image: reference")
            continue
        ref = image_match.group(1)
        if not ref.startswith(repo + ":"):
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: image {ref!r} does not point "
                f"at the application repository {repo}")
        if "${MRMAP_IMAGE_TAG:?" not in ref:
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: the tag must be "
                "${MRMAP_IMAGE_TAG:?...} - fail fast, never default")

    # The baked artifacts must not be shadowed by the checkout they were
    # built from (the #922/#1027 stale-statics lesson, this time at
    # /opt/mrmap and /etc/nginx). A volumes property, checked for every
    # service - independent of whether its image: reference is sane.
    for service, block in sorted(blocks.items()):
        if "./backend" in block:
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: a ./backend bind mount would "
                "shadow the code baked into the artifact (#922 lesson)")
        if "mrmap.conf" in block:
            problems.append(
                f"{DEPLOY_COMPOSE}: {service}: the nginx config is baked "
                "into the frontend artifact; do not bind-mount it over")

    # One tag variable for the whole mrmap set (the coherence rule).
    tag_vars = set(re.findall(r"\$\{(MRMAP_[A-Z_]*)", text))
    allowed_vars = {"MRMAP_IMAGE_TAG", "MRMAP_BACKEND_IMAGE_DIGEST",
                    "MRMAP_FRONTEND_IMAGE_DIGEST"}
    stray = tag_vars - allowed_vars
    if stray:
        problems.append(
            f"{DEPLOY_COMPOSE}: unexpected variable(s) {sorted(stray)}; the "
            "mrmap image set shares exactly one tag variable MRMAP_IMAGE_TAG")

    # The committed example names an exact artifact and carries no secrets.
    env_example = root / DEPLOY_ENV_EXAMPLE
    if not env_example.is_file():
        problems.append(f"{DEPLOY_ENV_EXAMPLE} is missing")
    else:
        problems += check_env_file(env_example)

    # No secrets anywhere in the deployment surface (committed files only).
    for path in sorted((root / DEPLOY_DIR).iterdir()):
        if path.is_file() and path != env_example:
            problems += check_env_file(path) if path.suffix == ".example" \
                else _literal_secrets(path)

    # Third-party images stay independently pinned, exactly as they are.
    for ref in third_party_pins(root):
        if "${" in ref:
            problems.append(
                f"{BASE_COMPOSE}: image {ref!r} interpolates; third-party "
                "images are pinned in the file, independently of the mrmap "
                "artifact set")
        elif not _ref_is_pinned(ref):
            problems.append(
                f"{BASE_COMPOSE}: image {ref!r} is not pinned to an exact "
                "version")

    # The overlay must not add any third-party image beyond the base file's
    # set (its job is the four mrmap services only).
    for service, block in _service_blocks(text).items():
        for match in re.finditer(r"^\s+image:\s*(\S+)", block, re.MULTILINE):
            if not match.group(1).startswith(
                    (APP_IMAGES["backend"], APP_IMAGES["frontend"])):
                problems.append(
                    f"{DEPLOY_COMPOSE}: {service} pulls {match.group(1)!r}; "
                    "third-party images belong to the base compose file")

    if extra_env:
        problems += check_env_file(extra_env)
    return problems


def _literal_secrets(path):
    problems = []
    for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        match = re.match(
            r"^[^#]*?\b([A-Za-z_][A-Za-z0-9_]*(?:SECRET|PASSWORD|TOKEN|"
            r"PRIVATE_KEY|API_KEY|ACCESS_KEY)[A-Za-z0-9_]*)\s*[:=]\s*"
            r"[\"']?([^\"'\s#][^#]*?)[\"']?\s*(?:#.*)?$",
            line, re.IGNORECASE)
        if match and not INTERPOLATION.search(match.group(2)):
            problems.append(
                f"{path}:{number}: {match.group(1)} has a literal value "
                "instead of a ${VAR} interpolation")
    return problems


# ---------------------------------------------------------------------------
# artifact verification (--verify-image, --live registry checks)
# ---------------------------------------------------------------------------

def docker_inspect_labels(ref):
    """The Config.Labels of a local image, or IdentityError."""
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", "--format", "{{json .Config.Labels}}",
             ref],
            capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise IdentityError("the docker CLI is not available on this host")
    if proc.returncode != 0:
        raise IdentityError(
            f"`docker image inspect {ref}` failed: {proc.stderr.strip()}")
    raw = proc.stdout.strip()
    if raw in ("", "null", "<no value>"):
        raise IdentityError(f"image {ref} carries no labels at all")
    return json.loads(raw)


def compare_labels(labels, version, revision, channel,
                   require_labels=("version", "revision", "source")):
    """The pure mismatch rules: labels vs identity. Returns the problems."""
    prefix = "org.opencontainers.image."
    expected = {}
    for key in require_labels:
        expected[prefix + key] = {"version": version, "revision": revision,
                                  "source": SOURCE_URL}[key]
    expected["io.github.mrmap.channel"] = channel
    problems = []
    for key, value in sorted(expected.items()):
        got = labels.get(key)
        if got != value:
            problems.append(
                f"label {key} = {got!r}, identity says {value!r}")
    return problems


def verify_image(ref, version, revision, channel,
                 require_labels=("version", "revision", "source")):
    """Compare an image's OCI labels with the identity it should carry.

    This is the mismatched-versions test of #1582: build a mismatch (a
    wrong --build-arg), run this against it, and it fails by naming the
    exact label. An EMPTY label value fails too - a published artifact
    must name itself, and "makes no claim" is not a claim.
    """
    labels = docker_inspect_labels(ref)
    return [f"{ref}: {problem}" for problem in compare_labels(
        labels, version, revision, channel, require_labels)]


def _parse_digest(inspect_output):
    """The Digest line of `docker buildx imagetools inspect` output."""
    match = re.search(r"^Digest:\s*(sha256:[0-9a-f]{64})\s*$",
                      inspect_output, re.MULTILINE)
    return match.group(1) if match else None


def registry_digest(ref):
    """The digest a registry serves for ref, via buildx imagetools (needs
    docker; used by the isolated-registry proof and the CI summary). A tag
    resolves to its manifest digest - the identity promotion retags."""
    try:
        proc = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", ref],
            capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise IdentityError("the docker CLI is not available on this host")
    if proc.returncode != 0:
        raise IdentityError(
            f"`docker buildx imagetools inspect {ref}` failed: "
            f"{proc.stderr.strip()}")
    digest = _parse_digest(proc.stdout)
    if not digest:
        raise IdentityError(
            f"`docker buildx imagetools inspect {ref}` answered no Digest "
            "line; refusing to guess one")
    return digest


# ---------------------------------------------------------------------------
# self-check (offline; the live repo wiring is scripts/test_image_version.py)
# ---------------------------------------------------------------------------

def self_check():
    """Exercise every rule against fixtures - no git, no docker, no network."""
    results = []

    def check(name, ok, detail=""):
        results.append((name, bool(ok), detail))

    sha = "0123456789abcdef0123456789abcdef01234567"

    # derive_tags: the policy table, exactly
    check("stable tags the version only",
          derive_tags("1.2.3", sha, "stable") == {"1.2.3"})
    check("prerelease tags the prerelease version and the sha",
          derive_tags("0.2.0-rc.1", sha, "prerelease")
          == {"0.2.0-rc.1", f"dev-{sha}"})
    check("dev tags the sha only",
          derive_tags("0.1.0", sha, "dev") == {f"dev-{sha}"})
    check("dev on a prerelease VERSION still only tags the sha",
          derive_tags("0.2.0-rc.1", sha, "dev") == {f"dev-{sha}"})
    for channel, extra in (("dev", {"1.2.3"}), ("dev", {"latest"}),
                           ("prerelease", {"0.2.0"}),
                           ("stable", {f"dev-{sha}"}),
                           ("stable", {"0.2.0-rc.1", "0.2.0"})):
        version = {"dev": "0.1.0", "prerelease": "0.2.0-rc.1",
                   "stable": "0.1.0"}[channel]
        asked = derive_tags(version, sha, channel) | extra
        try:
            guard_tags(version, sha, channel, asked)
            ok, detail = False, "guard accepted it"
        except IdentityError:
            ok, detail = True, ""
        check(f"guard refuses channel {channel} tag(s) {sorted(extra)}", ok,
              detail)
    check("guard accepts the exact derived set",
          guard_tags("0.2.0-rc.1", sha, "prerelease",
                     derive_tags("0.2.0-rc.1", sha, "prerelease"))
          == derive_tags("0.2.0-rc.1", sha, "prerelease"))
    check("guard refuses a PARTIAL set (leaves a name behind an old digest)",
          not _guard_passes("1.2.3", sha, "stable", set()))
    check("stable channel refuses a prerelease VERSION",
          not _derive_passes("0.2.0-rc.1", sha, "stable"))
    check("prerelease channel refuses a plain VERSION",
          not _derive_passes("0.2.0", sha, "prerelease"))
    check("rolling aliases are unapproved and a stable build emits none",
          APPROVED_ROLLING_ALIASES == frozenset()
          and "latest" not in derive_tags("1.2.3", sha, "stable"))
    check("an approved rolling alias only joins the stable set",
          derive_tags("1.2.3", sha, "stable", rolling=frozenset({"latest"}))
          == {"1.2.3", "latest"})
    check("guard refuses the alias on a dev identity",
          not _guard_passes("1.2.3", sha, "dev", {f"dev-{sha}", "latest"}))
    check("revision must be a full commit hash",
          not _derive_passes("1.2.3", "dead", "dev"))
    check("version must be strict SemVer",
          not _derive_passes("1.2", sha, "stable"))

    # labels and build args are the same three values everywhere
    labels = label_set("1.2.3", sha, "stable", "backend")
    check("labels carry version, revision, source",
          labels["org.opencontainers.image.version"] == "1.2.3"
          and labels["org.opencontainers.image.revision"] == sha
          and labels["org.opencontainers.image.source"] == SOURCE_URL)
    check("labels carry the channel", labels["io.github.mrmap.channel"]
          == "stable")
    args = build_args("1.2.3", sha, "stable")
    check("build args name version+revision+source+channel",
          all(part in args for part in
              ("MRMAP_VERSION=1.2.3", f"MRMAP_REVISION={sha}",
               "MRMAP_SOURCE=", "MRMAP_CHANNEL=stable")))

    # deployment env rules
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "deploy").mkdir()
        good = root / "deploy" / "images.env.example"
        good.write_text(
            "MRMAP_IMAGE_TAG=1.2.3\n"
            "# MRMAP_BACKEND_IMAGE_DIGEST=sha256:" + "ab" * 32 + "\n")
        check("env example: exact version passes",
              check_env_file(good) == [])
        good.write_text("MRMAP_IMAGE_TAG=1.2.3@sha256:" + "ab" * 32 + "\n")
        check("env example: digest-pinned version passes",
              check_env_file(good) == [])
        good.write_text("MRMAP_IMAGE_TAG=dev-" + sha + "\n")
        check("env example: a dev artifact is nameable",
              check_env_file(good) == [])
        good.write_text("MRMAP_IMAGE_TAG=latest\n")
        check("env example: latest is refused",
              len(check_env_file(good)) == 1)
        good.write_text("MRMAP_IMAGE_TAG=1.2\n")
        check("env example: a partial version is refused",
              len(check_env_file(good)) == 1)
        good.write_text("MRMAP_IMAGE_TAG=1.2.3\n"
                        "DJANGO_SECRET_KEY=nonsense\n")
        check("env example: a literal secret is refused",
              any("DJANGO_SECRET_KEY" in p for p in check_env_file(good)))
        good.write_text("MRMAP_IMAGE_TAG=1.2.3\n"
                        "MRMAP_BACKEND_IMAGE_DIGEST=sha256:dead\n")
        check("env example: a malformed digest is refused",
              any("DIGEST" in p for p in check_env_file(good)))

        # a mismatched overlay: two services on two versions
        bad_compose = root / "deploy" / "docker-compose.images.yml"
        bad_compose.write_text(
            "services:\n"
            "  backend:\n"
            "    image: ghcr.io/mrmap-community/mrmap-backend:"
            "${MRMAP_IMAGE_TAG:?}\n"
            "    build: !reset null\n"
            "  frontend:\n"
            "    image: ghcr.io/mrmap-community/mrmap-frontend:latest\n"
            "    build: !reset null\n")
        (root / "docker-compose.yml").write_text("services: {}\n")
        problems = check_deploy(root)
        check("overlay: a floating artifact tag is refused",
              any("latest" in p or "fail fast" in p for p in problems),
              "; ".join(problems))

    check("ref pinning: exact tag and digest pass, latest and bare refs fail",
          _ref_is_pinned("a/b:1.2.3")
          and _ref_is_pinned("a/b@sha256:" + "ab" * 32)
          and not _ref_is_pinned("a/b:latest")
          and not _ref_is_pinned("a/b"))
    check("ref registry-host-with-port is not mistaken for a tag",
          not _ref_is_pinned("registry:5000/x")
          and _ref_is_pinned("registry:5000/x:1.0"))
    check("digest parsing reads the Digest line and nothing else",
          _parse_digest("MediaType: application/vnd.oci.image.manifest...\n"
                        "Digest: sha256:" + "ab" * 32 + "\nImages:\n")
          == "sha256:" + "ab" * 32
          and _parse_digest("Digest: sha512:zz\n") is None)

    # label comparison: the mismatched-versions rules, offline
    good = {"org.opencontainers.image.version": "1.2.3",
            "org.opencontainers.image.revision": sha,
            "org.opencontainers.image.source": SOURCE_URL,
            "io.github.mrmap.channel": "dev"}
    check("label comparison passes the exact identity",
          compare_labels(good, "1.2.3", sha, "dev") == [])
    mismatch = dict(good, **{"org.opencontainers.image.version": "1.2.4"})
    check("label comparison names the mismatched version",
          any("version" in p for p in compare_labels(
              mismatch, "1.2.3", sha, "dev")))
    empty = dict(good, **{"org.opencontainers.image.revision": ""})
    check("label comparison refuses an empty claim",
          any("revision" in p for p in compare_labels(empty, "1.2.3", sha, "dev")))
    missing = dict(good)
    del missing["org.opencontainers.image.source"]
    check("label comparison refuses a missing label",
          any("source" in p for p in compare_labels(
              missing, "1.2.3", sha, "dev")))

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
              + (f"  ({detail})" if detail and not ok else ""))
    print(f"image_version self-check: {len(results) - len(failed)} of "
          f"{len(results)} checks passed")
    return 0 if not failed else 1


def _guard_passes(version, revision, channel, tags):
    try:
        guard_tags(version, revision, channel, tags)
        return True
    except IdentityError:
        return False


def _derive_passes(version, revision, channel, rolling=APPROVED_ROLLING_ALIASES):
    try:
        derive_tags(version, revision, channel, rolling)
        return True
    except IdentityError:
        return False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0], allow_abbrev=False)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--print", action="store_true", dest="print_version",
                        help="print the canonical version")
    action.add_argument("--tags", action="store_true",
                        help="print the bare tags of the identity")
    action.add_argument("--guard", action="store_true",
                        help="refuse unless --tag set equals the derived set")
    action.add_argument("--build-args", action="store_true",
                        help="print the docker build args of the identity")
    action.add_argument("--labels", action="store_true",
                        help="print the OCI labels of one image")
    action.add_argument("--manifest", action="store_true",
                        help="print the deployment manifest JSON")
    action.add_argument("--check-deploy", action="store_true",
                        help="run the deployment coherence checks")
    action.add_argument("--verify-image", metavar="REF",
                        help="compare a local image's labels with the identity")
    action.add_argument("--digest", metavar="REF",
                        help="print the registry digest this ref resolves to")
    action.add_argument("--self-check", action="store_true",
                        help="offline self-test")
    parser.add_argument("--channel", choices=CHANNELS, default="dev")
    parser.add_argument("--revision", default=None,
                        help="the exact source commit (CI: the checked-out "
                             "sha); default: git rev-parse HEAD")
    parser.add_argument("--image", choices=sorted(APP_IMAGES) + ["all"],
                        default="all")
    parser.add_argument("--tag", action="append", default=None,
                        dest="tags_asked",
                        help="a tag the caller intends to publish (repeatable,"
                             " for --guard)")
    parser.add_argument("--env", default=None,
                        help="extra deployment env file to check")
    parser.add_argument("--root", default=str(REPO))
    args = parser.parse_args(argv)
    root = Path(args.root)

    if args.self_check:
        return self_check()
    if args.print_version:
        try:
            print(read_version(root))
        except IdentityError as error:
            print(f"image_version: {error}", file=sys.stderr)
            return EXIT_POLICY
        return EXIT_OK

    if args.check_deploy:
        try:
            problems = check_deploy(root, extra_env=args.env)
        except IdentityError as error:
            print(f"image_version: {error}", file=sys.stderr)
            return EXIT_POLICY
        for problem in problems:
            print(f"image_version: {problem}", file=sys.stderr)
        if problems:
            return EXIT_POLICY
        print("image_version: deployment surface is coherent")
        return EXIT_OK

    if args.digest:
        try:
            print(registry_digest(args.digest))
        except IdentityError as error:
            print(f"image_version: {error}", file=sys.stderr)
            return EXIT_CANNOT
        return EXIT_OK

    # Everything below needs the identity itself.
    try:
        version = read_version(root)
        revision, warning = resolve_revision(root, args.revision, args.channel)
        if warning:
            print(f"image_version: {warning}", file=sys.stderr)
    except IdentityError as error:
        print(f"image_version: {error}", file=sys.stderr)
        return EXIT_POLICY

    try:
        if args.tags:
            for tag in sorted(derive_tags(version, revision, args.channel)):
                print(tag)
            return EXIT_OK
        if args.guard:
            if args.tags_asked is None:
                print("image_version: --guard needs at least one --tag",
                      file=sys.stderr)
                return EXIT_USAGE
            guard_tags(version, revision, args.channel, args.tags_asked)
            print(f"image_version: guard passes for {args.channel} "
                  f"{version} @{revision[:12]}")
            return EXIT_OK
        if args.build_args:
            print(build_args(version, revision, args.channel))
            return EXIT_OK
        if args.labels:
            images = sorted(APP_IMAGES) if args.image == "all" else [args.image]
            for image in images:
                for key, value in sorted(
                        label_set(version, revision, args.channel, image).items()):
                    print(f"{key}={value}")
            return EXIT_OK
        if args.manifest:
            print(json.dumps(
                manifest(root, version, revision, args.channel), indent=2,
                sort_keys=True))
            return EXIT_OK
        if args.verify_image:
            problems = verify_image(args.verify_image, version, revision,
                                    args.channel)
            for problem in problems:
                print(f"image_version: {problem}", file=sys.stderr)
            if problems:
                return EXIT_POLICY
            print(f"image_version: {args.verify_image} carries the "
                  f"{args.channel} identity {version} @{revision[:12]}")
            return EXIT_OK
    except IdentityError as error:
        print(f"image_version: {error}", file=sys.stderr)
        return EXIT_POLICY
    except FileNotFoundError as error:
        print(f"image_version: {error}", file=sys.stderr)
        return EXIT_CANNOT
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
