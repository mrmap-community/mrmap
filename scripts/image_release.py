#!/usr/bin/env python3
"""image_release: the version identity of the first-party runtime images.

Host-side tool carried by this repository; run it as `python3
scripts/image_release.py` from the repository root (issue #1582, epic #1577).
It is the single source of truth for WHAT a released MrMap image is called, WHAT
it says about itself and WHICH images a deployment of one version names - the
same role ``scripts/dev_image_id.py`` holds for the dependency images of epic
#959, for the same reason: a tag computed in two places drifts, so nothing else
may compute it.

What it does NOT do is decide what becomes a release. It reads no credential of
any deployment, and the only registry it will push to is the one named by
``--registry-base``. ``.github/workflows/candidate-images.yml`` calls it to build
and publish ONE explicitly selected candidate under isolated candidate tags and
to write the evidence file of that run (#1799); what that workflow may never do
is point a stable version tag at anything, because the tool creates a version tag
only through ``--promote``, and ``--promote`` is a human dispatch of
``.github/workflows/release-promotion.yml`` behind the ``release-stable``
environment. Q1 and Q4 of #1578 are answered policy now (first published tag
`v0.2.0`, tag shape `vMAJOR.MINOR.PATCH`, no version for a docs-only window -
ADR-0002), and an answered question publishes nothing by itself: publishing a
stable release stays a human act on a project's own package namespace. The
immutable-tag rule - and the refusal that backs it - is here either way, as is
everything else that makes publication safe: names, tags, labels, the rule that a
stable tag never moves, the manifest a deployment is pinned with.

The inventory this tool encodes (measured on develop, #1582)
------------------------------------------------------------
Two Dockerfiles build the images a production MrMap runs on, and they are named
by four ``build:`` sections of ``docker-compose.yml``:

  backend   docker/backend/alpine.Dockerfile, context ./backend
            services backend, celery-worker, celery-beat - one image, three
            containers; worker and beat differ by command only, so one release
            must never run their images from different builds.
  frontend  docker/nginx/nginx.Dockerfile, context ./
            service frontend - the SPA bundle plus the nginx that serves it.

Neither carries an ``image:`` reference in the base file, so a deployment today
is "build from a checkout" (#1578 named exactly this as the reason no version
could be deployed). The further consumers of the backend Dockerfile
(``django-tests``, ``behave``, ``pre-commit-check`` of ``docker-compose.dev.yml``)
and the two images of ``dev-images.yml`` are test tooling, tagged by dependency
fingerprint under different names (``mrmap-*-dev``). Their contract is #959's and
this tool leaves it alone on purpose: a release build must not disturb the
prebuilt dev cache every agent stack resolves through.

Third-party images (``postgis``, ``redis``, ``haproxy``, ``victoria-logs``,
``grafana``, ``pgadmin4``, ``flower``; dev-only ``mapserver``, ``node``) are
pinned to exact versions in ``docker-compose.yml`` already. A release manifest
never writes them: they are versioned by their upstream and Renovate, and a
second place to change one is a second way to be wrong. ``--check-manifest``
reads them, to refuse a manifest that overrode a pin unnoticed.

Tag policy
----------
``--kind`` is the identity of the build. The version always comes from the root
``VERSION`` file through ``scripts/canonical_version.py`` (#1579), never from a
second constant:

  stable     the version itself, e.g. ``0.2.0``. Immutable: once a registry
             serves that tag for a digest, this tool refuses to point it at any
             other digest. Build metadata is DROPPED from the tag - the
             distribution reference grammar allows ``[a-zA-Z0-9_.-]`` only, so a
             ``+9f8e7d6`` cannot be a tag - and survives in
             ``org.opencontainers.image.version``, which is where an exact build
             is identified.
  prerelease the version with its prerelease part, e.g. ``0.2.0-rc.1``. Also
             immutable, and never allowed to move a stable alias.
  dev        ``dev-<12 hex of the commit>``, the same length a dependency
             fingerprint has. Movable by design (a dev revision is not a
             product), but it can never carry an alias - which is the whole
             "dev and RC must not overwrite stable" rule in one line.
  candidate  ``candidate-<12 hex of the commit>``. The tag of the candidate
             that #1799's build workflow publishes for ONE explicitly selected,
             reviewed commit: named by its commit like a dev build, because it
             is a build of a revision and not yet a release, but kept apart from
             the ``dev-`` namespace so a candidate is never mistaken for the
             movable build of a branch, and refused every alias for the same
             reason a dev build is. Two builders of one commit get one digest
             here (SOURCE_DATE_EPOCH is the commit's own timestamp), which is
             what lets a promotion compare what it is told with what the
             registry serves.

Rolling aliases (``latest``, ``stable``, ...) are opt-in, one ``--alias`` each,
and the default is none: #1578's Q1 fixed the tag shape and approved no alias,
and a rolling alias is a product promise this repository has not made. ``--alias`` is refused for
``--kind dev``, and the stable aliases are refused for a prerelease.

Build once, promote the bytes that were tested
----------------------------------------------
``--build`` builds the candidate under its candidate tag(s) only; ``--push``
publishes those. The version tag is never written by a build: ``--promote``
creates it registry-side from the candidate's DIGEST with
``docker buildx imagetools create``, so no compiler runs a second time and the
content cannot differ from what was tested.

What "the same content" means was measured against an isolated registry rather
than assumed, because the two digests involved are NOT equal: ``buildx build``
pushes a bare ``image.manifest.v1+json`` while ``imagetools create`` copies those
same bytes into a new ``image.index.v1+json`` around them, writing a different
digest for identical content (candidate ``0e70980a…`` became index ``9fbd3110…``,
whose only child is ``0e70980a…``). Identity is therefore the SET OF CHILD
MANIFESTS, falling back to the manifest digest for a bare one - measured first,
because a promotion comparing manifest digests would report its own second run as
a conflicting release. Promotion is idempotent on that identity (``already
promoted``) and refuses when the tag already holds other content; there is no
``--force`` for that, because moving a published release tag is a human decision,
not a flag.

The deployment manifest
-----------------------
``--manifest`` writes a Compose overlay in the shape
``docker-compose.prebuilt.yml`` established for the dev images: per first-party
service an ``image:`` reference carrying tag AND digest, plus
``build: !reset null``::

    docker compose -f docker-compose.yml -f mrmap-0.2.0.yml up -d

The digests are read from the registry by default - the digest each release tag
ANSWERS, which is what an operator pulls - and can be named explicitly with
``--digest image=sha256:...``.

That overlay is the "coherent image set" of the acceptance, and
``--check-manifest`` is what keeps it coherent: it refuses a manifest that lets
a service keep building from a checkout, that mixes two versions of one
release, that names a repository this release does not build, that overrides a
third-party pin, or that carries a credential-shaped value.

``--verify`` then asks the registry, without pulling, as TWO separate references
because their answers fail differently: resolving the tag answers whether it still
points at what was released, resolving the digest and reading its
``org.opencontainers.image.version`` label answers whether these are the bytes of
that release. Asking the combined ``repo:tag@digest`` form would answer neither -
measured, a distribution resolves that reference by the digest and ignores the
tag, so a digest comparison against it compares a value with itself and always
passes. The label question is the one nothing else can answer: a promotion cannot
see that it was handed the previous release's bytes, and one hand-edited line is a
backend and its worker on two versions against one database.

The candidate evidence file
---------------------------
``--attest PATH`` writes the machine-readable answer of ``--verify`` instead of
prose: one JSON document naming the candidate SHA, the version it claims, the
registry it was published to and, per image, the candidate reference, the digest
to promote, the artifact's child-manifest identity and the OCI labels the
registry answers for it. It is what ``.github/workflows/candidate-images.yml``
hands the promotion, so that a promotion never starts from a digest somebody
pasted (issue #1799): the file is produced in the same run that pushed the
candidate, and ``release_promotion.py`` re-reads every digest from the registry
before it uses one. Like ``--verify`` it asks the registry rather than trusting
what it is told, and refuses - a candidate whose artifact answers another
revision than the SHA under review, a missing version label, an unpublished
digest - because evidence that cannot fail is not evidence.

OCI labels and reproducibility
------------------------------
Every build carries ``org.opencontainers.image.{title,version,revision,source,
documentation}`` and, for the backend image, ``io.github.mrmap.
dependency-fingerprint`` - the fingerprint ``scripts/dev_image_id.py`` computes
for that same Dockerfile and requirement set, so a runtime image names the
dependency layers it stands on. The frontend image is deliberately NOT stamped
with it: #962's frontend manifest covers ``docker/frontend/tests.Dockerfile``,
not the nginx image, and a label claiming a fingerprint of a different input set
is worse than no label. ``--build`` exports ``SOURCE_DATE_EPOCH`` of the commit
rather than the wall clock, so two builders of one commit get one digest.
Multi-arch is not offered because nothing here builds for anything but the
builder's platform today (no ``--platform`` exists in the repository);
advertising ``linux/arm64`` would publish a promise nothing tests.

Usage
  python3 scripts/image_release.py --inventory
  python3 scripts/image_release.py --plan                    # what a release does
  python3 scripts/image_release.py --build --push --kind dev
  python3 scripts/image_release.py --attest candidate.json --kind dev
  python3 scripts/image_release.py --promote --digest backend=sha256:...
  python3 scripts/image_release.py --manifest mrmap-0.2.0.yml --kind stable
  python3 scripts/image_release.py --check-manifest mrmap-0.2.0.yml --verify

Exit codes
  0  the plan, manifest, evidence file or answer was produced, or the manifest
     is coherent
  1  refused: incoherent manifest, an immutable tag that already serves other
     bytes, a missing or invalid VERSION, a build argument the build requires,
     an artifact whose labels contradict the candidate it attests
  2  usage error (argparse, before anything is read or run)
"""

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPTS.parent

# The namespace dev-images.yml already publishes into; a release build aims at
# the same organisation under its own repository names (no `-dev` suffix).
REGISTRY_BASE = "ghcr.io/mrmap-community"

# docker is only called by --build/--promote/--manifest/--verify. The cap keeps
# a stuck daemon from hanging the caller, as in dev_image_id.py; a build needs
# more than the inspect calls, so two limits.
DOCKER_TIMEOUT_S = 120
DOCKER_BUILD_TIMEOUT_S = 3 * 3600

# Aliases that promise "the current release"; a prerelease may never move one.
STABLE_ALIASES = ("latest", "stable", "main", "prod")

# distribution/distribution's reference grammar, narrowed to what one manifest
# line may look like: repository [: tag] [@ sha256:64hex].
IMAGE_REF_RE = re.compile(
    r'^(?P<repository>[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?'
    r'(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+)'
    r'(?::(?P<tag>[\w][\w.-]{0,127}))?'
    r'(?:@(?P<digest>sha256:[0-9a-f]{64}))?$'
)
DIGEST_RE = re.compile(r'^sha256:[0-9a-f]{64}$')
SEMVER_BASE_RE = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')

# Nothing secret belongs in a manifest: it is shipped to whatever host runs the
# deployment, while MrMap's runtime configuration comes from the .env.
SECRET_KEY_RE = re.compile(
    r'(secret|password|passwd|token|api[_-]?key|access[_-]?key|private[_-]?key)',
    re.IGNORECASE)

_spec = importlib.util.spec_from_file_location("canonical_version", SCRIPTS / "canonical_version.py")
canonical_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(canonical_version)

_spec = importlib.util.spec_from_file_location("dev_image_id", SCRIPTS / "dev_image_id.py")
dev_image_id = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev_image_id)


class ReleaseError(Exception):
    """What this tool refuses to do, with the reason a human can act on."""


# The inventory. `services` names the build sections of docker-compose.yml one
# image serves; scripts/test_image_release.py asserts the table still matches
# the file, so a service added later cannot quietly miss a release.
IMAGES = {
    "backend": {
        "repository": "mrmap-backend",
        "dockerfile": "docker/backend/alpine.Dockerfile",
        "context": "./backend",
        "services": ("backend", "celery-worker", "celery-beat"),
        "title": "MrMap backend (Django and Celery)",
        "documentation": "https://mrmap.readthedocs.io",
        # The dependency fingerprint of #959 describes exactly this Dockerfile
        # and this requirement set, so the runtime image can name it.
        "dependency_fingerprint": True,
    },
    "frontend": {
        "repository": "mrmap-frontend",
        "dockerfile": "docker/nginx/nginx.Dockerfile",
        "context": "./",
        "services": ("frontend",),
        "title": "MrMap frontend (SPA and nginx)",
        "documentation": "https://mrmap.readthedocs.io",
        # #962's frontend manifest is docker/frontend/tests.Dockerfile, not this
        # one: reusing that fingerprint here would state something untrue.
        "dependency_fingerprint": False,
    },
}

KINDS = ("stable", "prerelease", "dev", "candidate")
DIGEST_ARG_RE = re.compile(r'^(?P<image>[\w-]+)=(?P<digest>sha256:[0-9a-f]{64})$')


# ---------------------------------------------------------------- the identity


def repository(image, registry_base=REGISTRY_BASE):
    """The full repository name of one first-party image."""
    if image not in IMAGES:
        raise ReleaseError(f"unknown image {image!r}; this release builds "
                           f"{', '.join(sorted(IMAGES))}")
    return f"{registry_base}/{IMAGES[image]['repository']}"


def version_of(root):
    """The canonical version, read through #1579's tool - never a second constant."""
    try:
        return canonical_version.read_version(root)
    except canonical_version.VersionError as error:
        raise ReleaseError(str(error)) from None


def split_version(version):
    """(base, prerelease, buildmeta) of a strict SemVer string.

    The base is all a Docker tag may hold: the reference grammar has no ``+``,
    so build metadata never becomes a tag name. Without this a ``+rev`` in
    VERSION would fail at push time with a message about invalid characters.
    """
    buildmeta = ""
    rest = version
    if "+" in rest:
        rest, buildmeta = rest.split("+", 1)
    if "-" in rest:
        base, prerelease = rest.split("-", 1)
        return base, prerelease, buildmeta
    return rest, "", buildmeta


def classify(version):
    """Which kind of release a version is: prerelease or stable."""
    _base, prerelease, _meta = split_version(version)
    return "prerelease" if prerelease else "stable"


def version_tag(version):
    """The immutable image tag of a version: SemVer without build metadata."""
    base, prerelease, _meta = split_version(version)
    return f"{base}-{prerelease}" if prerelease else base


def git_output(root, *args):
    try:
        proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True,
                              text=True, timeout=30)
    except OSError as error:
        raise ReleaseError(f"git {args[0]} could not run: {error}") from None
    if proc.returncode != 0:
        raise ReleaseError(f"git {args[0]} failed in {root}: {proc.stderr.strip()}")
    return proc.stdout.strip()


def git_identity(root):
    """(full sha, commit epoch) of HEAD, for the revision label and dev tags.

    An exact commit is not decoration: ``dev-<sha>`` and
    ``org.opencontainers.image.revision`` are how an operator answers "which
    bytes is this container" for anything that is not a released version.
    """
    sha = git_output(root, "rev-parse", "HEAD")
    epoch = git_output(root, "show", "-s", "--format=%ct", "HEAD")
    return sha, int(epoch)


def tags_for(image, version, sha, kind="stable", aliases=(), registry_base=REGISTRY_BASE):
    """Every reference one build may write, as ``(version_refs, alias_refs)``.

    The policy of the module docstring lives here and nowhere else, so a future
    workflow reads it by calling it instead of restating it.
    """
    repo = repository(image, registry_base)
    _base, prerelease, _meta = split_version(version)
    aliases = list(aliases or [])
    if kind in ("dev", "candidate"):
        if aliases:
            raise ReleaseError(
                f"--kind {kind} cannot carry the alias(es) {', '.join(aliases)}: a "
                f"{kind} build is a revision, not a release, and a rolling alias is "
                "the promise that it is")
        return [f"{repo}:{kind}-{short_sha(sha)}"], []
    if kind not in KINDS:
        raise ReleaseError(f"unknown kind {kind!r}; expected one of {', '.join(KINDS)}")
    if kind == "stable" and prerelease:
        raise ReleaseError(
            f"{version} is a prerelease, so --kind stable would publish it as if it "
            "were a release; drop --kind stable or release the version")
    if kind == "prerelease" and not prerelease:
        raise ReleaseError(
            f"--kind prerelease asks for a prerelease tag but {version} carries no "
            "prerelease part")
    unwanted = [a for a in aliases if a in STABLE_ALIASES and prerelease]
    if unwanted:
        raise ReleaseError(
            f"a prerelease ({version}) may not move the stable alias(es) "
            f"{', '.join(unwanted)}: the alias promises the current release, and an "
            "upgrade candidate must not be what an operator pulls by default")
    return [f"{repo}:{version_tag(version)}"], [f"{repo}:{a}" for a in aliases]


def short_sha(sha):
    """The dev-tag form: 12 hex digits, the length of a dependency fingerprint."""
    return sha[:12]


def labels_for(image, root, version, sha):
    """The OCI labels of one build."""
    spec = IMAGES[image]
    labels = {
        "org.opencontainers.image.title": spec["title"],
        "org.opencontainers.image.version": version,
        "org.opencontainers.image.revision": sha,
        "org.opencontainers.image.source": "https://github.com/mrmap-community/mrmap",
        "org.opencontainers.image.documentation": spec["documentation"],
    }
    if spec["dependency_fingerprint"]:
        labels["io.github.mrmap.dependency-fingerprint"] = dev_image_id.fingerprint(root, "backend")
    return labels


def build_args_for(image, root, env=None, sha=None):
    """The build args one image needs, and the refusal when one is missing.

    The frontend bundle bakes its API address in at build time, which is why
    docker-compose.yml demands the three EXTERNAL_* values with ``:?`` (#1027
    measured what a stale address costs). A release build driven from outside
    Compose has to fail the same way rather than publish a bundle that talks to
    nowhere.
    """
    env = os.environ if env is None else env
    args = {}
    if image == "frontend":
        required = {
            "VITE_API_BASE_URL": "EXTERNAL_BASE_URL",
            "VITE_API_PORT": "EXTERNAL_PORT",
            "VITE_API_SCHEMA": "EXTERNAL_SCHEME",
        }
        for arg, source in required.items():
            value = (env.get(arg) or env.get(source) or "").strip()
            if not value:
                raise ReleaseError(
                    f"the frontend image bakes its API address into the bundle, so "
                    f"{arg} is required; export {source} (the variable "
                    f"docker-compose.yml reads) or {arg} before building")
            args[arg] = value
    args["MRMAP_BUILD_REVISION"] = sha or git_identity(root)[0]
    return args


# ------------------------------------------------------------- the build plan


def docker(argv, root, timeout=DOCKER_TIMEOUT_S, capture=False, check=True):
    """One docker call; the failure text is kept for the refusal message."""
    command = ["docker", *argv]
    try:
        proc = subprocess.run(command, cwd=str(root), capture_output=capture,
                              text=capture, timeout=timeout)
    except OSError as error:
        raise ReleaseError(f"docker could not run: {error}") from None
    except subprocess.TimeoutExpired:
        raise ReleaseError(f"`{' '.join(command)}` did not finish within {timeout}s") from None
    if check and proc.returncode != 0:
        detail = ""
        if capture:
            detail = (proc.stderr or proc.stdout or "").strip()
        raise ReleaseError(f"`{' '.join(command)}` failed"
                           + (f": {detail}" if detail else "; see the output above"))
    return (proc.stdout or "").strip() if capture else ""


_JSON = json.JSONDecoder()


def _json_documents(text):
    """Every JSON document of a string, in order, whatever the pretty printing.

    ``{{ json ... }}`` in a buildx template writes INDENTED JSON over several
    lines, so the two documents one inspect call asks for cannot be told apart at
    line boundaries - the first evidence run of #1582 died on exactly that, with
    ``Extra data`` from a parser handed a fragment. raw_decode reads the stream
    instead, and a fragment it cannot read is refused rather than guessed at.
    """
    documents = []
    position = 0
    while position < len(text):
        while position < len(text) and text[position] in " \t\r\n":
            position += 1
        if position >= len(text):
            break
        try:
            document, position = _JSON.raw_decode(text, position)
        except json.JSONDecodeError as error:
            raise ReleaseError(
                "an inspect answer carried unreadable JSON "
                f"({error}); refusing to read a manifest whose shape is not known") from None
        documents.append(document)
    return documents


def _inspect(ref, root, ask_image):
    """One inspect call: the manifest digest, the manifest, and its image config.

    Nothing is pulled: the digest and the manifest are what a registry answers on
    a HEAD/GET of the reference, and the image config the same request resolves is
    where the OCI labels live. That is what makes ``--verify`` cheap enough to
    recommend on every deployment.
    """
    template = '{{.Manifest.Digest}}{{"\\n"}}{{ json .Manifest }}'
    if ask_image:
        template += '{{"\\n"}}{{ json .Image }}'
    out = docker(["buildx", "imagetools", "inspect", "--format", template, ref], root,
                 capture=True)
    digest, _sep, rest = out.partition("\n")
    if not DIGEST_RE.match(digest):
        raise ReleaseError(f"{ref} did not answer a manifest digest")
    try:
        documents = _json_documents(rest)
    except ReleaseError as error:
        raise ReleaseError(f"{ref}: {error}") from None
    manifest = documents[0] if documents else {}
    image = documents[1] if ask_image and len(documents) > 1 else None
    return digest, manifest, image


def artifact_info(ref, root):
    """What a registry reference answers about itself: ``(digest, labels)``.

    The image config comes back as a map keyed by platform for a multi-platform
    index and as one document for a bare image manifest; either way the first
    config with labels is the answer.
    """
    digest, _manifest, image = _inspect(ref, root, ask_image=True)
    return digest, _labels_of(image)


def _labels_of(image):
    """The OCI labels out of an inspect answer, index or bare manifest alike."""
    if not isinstance(image, dict):
        return {}
    documents = [image] if "config" in image else [
        value for value in image.values() if isinstance(value, dict)]
    for document in documents:
        config = document.get("config") or {}
        if isinstance(config.get("Labels"), dict):
            return config["Labels"]
    return {}


def artifact_identity(ref, root):
    """What a reference IS, independent of the manifest that wraps it.

    Measured for #1582 against an isolated registry: ``docker buildx build``
    pushes a bare ``application/vnd.oci.image.manifest.v1+json``, while
    ``imagetools create`` - the promotion step - copies those same bytes into a
    new ``...image.index.v1+json`` and therefore writes a DIFFERENT digest for
    identical content (candidate ``0d24dce2...`` became index ``da504ede...``
    whose only child is ``0d24dce2...``). A promotion that compared manifest
    digests would call its own second run a conflicting release.

    So identity is the set of child manifests, falling back to the manifest
    digest itself for a bare image manifest. Two references with the same
    identity are the same image; the wrapper is packaging.
    """
    digest, manifest, _image = _inspect(ref, root, ask_image=False)
    children = sorted(entry.get("digest", "") for entry in (manifest or {}).get("manifests") or []
                      if entry.get("digest"))
    return digest, tuple(children) or (digest,)


def existing_artifact(ref, root):
    """The digest and identity a tag already serves, or None when it is free.

    Anything that is not "that name is not there" raises instead of reading as
    free: a promotion that cannot look must not add a tag either.
    """
    try:
        return artifact_identity(ref, root)
    except ReleaseError as error:
        text = str(error).lower()
        if any(shape in text for shape in ("not found", "manifest unknown", "unknown",
                                           "no such")):
            return None
        raise


def build_plan(image, root, version, sha, kind, aliases, registry_base, env=None):
    """What one image of one candidate IS, as data a builder may consume.

    ``.github/workflows/candidate-images.yml`` reads this instead of computing a
    tag, a label or a build arg itself: those are the policy of this module, and a
    workflow that restated them would be a second place where the name of a
    release image is decided - the failure #1582 exists to prevent. The keys are
    exactly what ``docker/build-push-action`` is handed, and ``--print`` renders
    each of them the way that action wants to read it, the same service
    ``dev_image_id.py --print-build-args`` performs for the dependency images.
    """
    spec = IMAGES[image]
    tags, alias_refs = tags_for(image, version, sha, kind, aliases, registry_base)
    return {
        "image": image,
        "repository": repository(image, registry_base),
        "dockerfile": spec["dockerfile"],
        "context": spec["context"],
        "services": list(spec["services"]),
        "tags": tags + alias_refs,
        "candidate_tag": tags[0].rsplit(":", 1)[-1],
        "labels": labels_for(image, root, version, sha),
        "build_args": build_args_for(image, root, env=env, sha=sha),
        "source_date_epoch": git_output(root, "show", "-s", "--format=%ct", "HEAD"),
    }


# What `--print` renders, as the key a caller asks for -> (the key of the plan it
# reads, how to print it). A builder asks for one key per call and gets one line,
# so no step of a workflow has to parse JSON in a shell.
PRINT_KEYS = {
    "tags": ("tags", lambda value: ",".join(value)),
    "candidate-tag": ("candidate_tag", lambda value: value),
    "dockerfile": ("dockerfile", lambda value: value),
    "context": ("context", lambda value: value),
    "repository": ("repository", lambda value: value),
    "labels": ("labels", lambda value: "\n".join(f"{k}={v}"
                                                 for k, v in sorted(value.items()))),
    "build-args": ("build_args", lambda value: ",".join(
        f"{k}={v}" for k, v in sorted(value.items()))),
    "source-date-epoch": ("source_date_epoch", lambda value: value),
}


def plan_value(image, root, version, sha, kind, aliases, registry_base, key):
    """One key of the build plan, rendered for a shell to capture."""
    if key not in PRINT_KEYS:
        raise ReleaseError(f"--print {key!r} names no plan key; ask for "
                           f"{', '.join(sorted(PRINT_KEYS))}")
    plan_key, render = PRINT_KEYS[key]
    return str(render(build_plan(image, root, version, sha, kind, aliases,
                                 registry_base)[plan_key]))


def plan_for(image, root, version, sha, kind, aliases, registry_base):
    """The command that produces this image for this release, as readable text."""
    spec = IMAGES[image]
    tags, alias_refs = tags_for(image, version, sha, kind, aliases, registry_base)
    labels = labels_for(image, root, version, sha)
    args = build_args_for(image, root, sha=sha)
    epoch = git_output(root, "show", "-s", "--format=%ct", "HEAD")
    lines = [f"# {image}: {spec['dockerfile']} (context {spec['context']})"]
    # shlex.quote, not decoration: `org.opencontainers.image.title` holds a
    # space, and a printed plan a shell cannot run verbatim is a plan that gets
    # run wrongly.
    lines.append(
        f"SOURCE_DATE_EPOCH={epoch} docker buildx build --provenance=false "
        + " ".join(f"--tag {shlex.quote(t)}" for t in tags + alias_refs) + " "
        + " ".join(f"--label {shlex.quote(f'{k}={v}')}" for k, v in sorted(labels.items())) + " "
        + " ".join(f"--build-arg {shlex.quote(f'{k}={v}')}" for k, v in sorted(args.items())) + " "
        + f"-f {spec['dockerfile']} {spec['context']}")
    for tag in tags:
        lines.append(f"  candidate ref   {tag}")
    for tag in alias_refs:
        lines.append(f"  alias written {tag}")
    if not alias_refs:
        lines.append("  no alias written; --promote creates the version tag from the")
        lines.append("  tested digest, so the released bytes are the built bytes")
    return lines


def build_image(image, root, version, sha, kind, aliases, registry_base, push, dry_run):
    """Build one image under its candidate tags; push them only with --push."""
    spec = IMAGES[image]
    tags, alias_refs = tags_for(image, version, sha, kind, aliases, registry_base)
    labels = labels_for(image, root, version, sha)
    args = build_args_for(image, root, sha=sha)
    argv = ["buildx", "build", "--provenance=false"]
    for tag in tags + alias_refs:
        argv += ["--tag", tag]
    for key, value in sorted(labels.items()):
        argv += ["--label", f"{key}={value}"]
    for key, value in sorted(args.items()):
        argv += ["--build-arg", f"{key}={value}"]
    if push:
        argv += ["--push"]
    argv += ["-f", spec["dockerfile"], spec["context"]]
    # The commit's own timestamp as the build timestamp: two builders of one
    # commit then get one digest, which is what makes "promote the tested bytes"
    # mean the same thing on two machines.
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = git_output(root, "show", "-s", "--format=%ct", "HEAD")
    if dry_run:
        print(f"SOURCE_DATE_EPOCH={env['SOURCE_DATE_EPOCH']} "
              + shlex.join(["docker", *argv]))
        return tags
    print(f"image_release: building {image} for {version} as "
          f"{', '.join(t.split(':')[-1] for t in tags)}", file=sys.stderr)
    command = ["docker", *argv]
    try:
        subprocess.run(command, cwd=str(root), env=env, timeout=DOCKER_BUILD_TIMEOUT_S,
                       check=True)
    except subprocess.CalledProcessError:
        raise ReleaseError(f"the build of {image} failed; the builder's output above "
                           "says why") from None
    if push:
        pushed = []
        for tag in tags + alias_refs:
            digest, labels_answered = artifact_info(tag, root)
            if labels_answered.get("org.opencontainers.image.version") != version:
                raise ReleaseError(
                    f"{tag} reports {labels_answered.get('org.opencontainers.image.version')!r} "
                    f"after the push, not {version!r}: the registry serves something "
                    "else under this name")
            pushed.append(f"{tag}@{digest[:19]}...")
        for line in pushed:
            print(f"image_release: pushed {line}", file=sys.stderr)
    return tags


def promote(image, root, version, sha, kind, digest, registry_base, aliases, dry_run):
    """Point the version tag (and opt-in aliases) at an already tested digest.

    The registry creates the tag from the digest, so no build runs and no second
    set of bytes can appear. That difference is the point: "promote" and
    "rebuild and hope it matches" are not the same operation.

    The refs come from ``tags_for``, not from a local computation: that is where
    the alias policy lives, and a promotion which skipped it would let
    ``--promote --alias latest`` move the stable alias with a prerelease - the
    exact accident the rule exists for.
    """
    version_refs, alias_refs = tags_for(image, version, sha, kind, aliases, registry_base)
    repo = repository(image, registry_base)
    source = f"{repo}@{digest}"
    # Reading the source is what proves the digest exists at all: a promotion of
    # a digest nobody published would create a tag pointing at nothing.
    _source_digest, source_identity = artifact_identity(source, root)
    results = []
    for ref in version_refs + alias_refs:
        existing = existing_artifact(ref, root)
        if existing:
            _existing_digest, existing_identity = existing
            if existing_identity == source_identity:
                results.append((ref, "already promoted"))
                continue
            raise ReleaseError(
                f"{ref} already holds {' vs '.join(existing_identity)} - not the "
                f"{' vs '.join(source_identity)} of {source}. An immutable tag is "
                "never moved: publish the next version. Deleting a published tag and "
                "re-releasing is a human decision, not a flag on this tool.")
        if dry_run:
            results.append((ref, f"would create from {digest[:19]}..."))
            continue
        docker(["buildx", "imagetools", "create", "--tag", ref, source], root)
        results.append((ref, "promoted"))
    return results


# ------------------------------------------------------ the deployment manifest


MANIFEST_HEADER = """\
# MrMap {version} - version-pinned deployment manifest ({kind} build {short}).
#
# Generated by `python3 scripts/image_release.py --manifest ...` (#1582); do not
# hand-edit - regenerate. Bring the deployment up with:
#
#   docker compose -f docker-compose.yml -f {filename} up -d
#
# Every first-party service names the exact digest that was built and tested for
# {version}, so the running container testifies to itself: its OCI labels answer
# org.opencontainers.image.version = {version} and
# org.opencontainers.image.revision = {revision}. Check that with:
#
#   python3 scripts/image_release.py --check-manifest {filename} --verify --version {version}
#
# The `build: !reset null` lines are what makes "pinned" true rather than likely:
# with a build section left in place, a compose run that cannot pull silently
# builds from whatever checkout the host has - which, before this manifest
# existed, was the entire deployment story of MrMap (#1578). The shape is the one
# docker-compose.prebuilt.yml established for the dependency images.
#
# Third-party images are deliberately absent: they stay pinned by
# docker-compose.yml to their own upstream versions and are updated by Renovate,
# not by a MrMap release. A manifest that pinned them too would be a second
# place to change when one of them moves.
services:
"""

MANIFEST_SERVICE = """\
  {service}:
    image: {repository}:{tag}@{digest}
    build: !reset null"""


def render_manifest(version, kind, registry_base, digests, sha,
                    filename="mrmap-release.yml", aliases=()):
    """The overlay text that pins one release's coherent image set."""
    missing = [image for image in sorted(IMAGES) if image not in digests]
    if missing:
        raise ReleaseError(
            f"the manifest would leave {', '.join(missing)} unpinned; a release "
            "manifest names every image it builds, otherwise one service keeps "
            "building from a checkout while the others are pulled")
    lines = [MANIFEST_HEADER.format(version=version, kind=kind, filename=filename,
                                    revision=sha, short=sha[:12]).rstrip("\n")]
    for image in sorted(IMAGES):
        repo = repository(image, registry_base)
        _refs, alias_refs = tags_for(image, version, sha, kind, aliases, registry_base)
        for service in IMAGES[image]["services"]:
            lines.append(MANIFEST_SERVICE.format(service=service, repository=repo,
                                                 tag=version_tag(version),
                                                 digest=digests[image]))
        for alias in alias_refs:
            lines.append(f"  # {image} is additionally published as {alias}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_manifest(text):
    """Read a manifest back: ``{service: {image, build, lines}}``, comments ignored.

    Deliberately a strict reader rather than a YAML dependency: the file is a
    generated artifact with one shape, and a reader that understands only that
    shape also refuses the edits that matter. What it cannot place is reported
    by --check-manifest as unpinned or unexpected, never guessed at.
    """
    services = {}
    current = None
    in_services = False
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.rstrip() == "services:":
            in_services = True
            continue
        if in_services and raw.startswith("  ") and not raw.startswith("   ") \
                and raw.rstrip().endswith(":"):
            current = raw.strip()[:-1]
            services[current] = {"image": None, "build": False, "lines": []}
            continue
        if in_services and not raw.startswith(" ") and raw.strip():
            in_services = False
            current = None
            continue
        if current is None or not raw.strip():
            continue
        entry = raw.strip()
        services[current]["lines"].append(entry)
        if entry.startswith("image:"):
            services[current]["image"] = entry.split(":", 1)[1].strip()
        elif entry.startswith("build:"):
            services[current]["build"] = True
    return services


def base_compose_image_pins(root):
    """The third-party pins of docker-compose.yml, as ``{service: image}``."""
    pins = {}
    service = None
    for raw in (Path(root) / "docker-compose.yml").read_text(encoding="utf-8").splitlines():
        if raw.startswith("  ") and not raw.startswith("   ") and raw.rstrip().endswith(":"):
            service = raw.strip()[:-1]
        elif service and raw.strip().startswith("image:"):
            pins[service] = raw.strip().split(":", 1)[1].strip()
    return pins


def parse_image_ref(image_ref):
    """``(repository, tag, digest)`` of one reference, or a refusal that names it."""
    match = IMAGE_REF_RE.match(image_ref)
    if not match:
        raise ReleaseError(f"{image_ref!r} is not a valid image reference "
                           "(repository[:tag][@sha256:<64 hex>])")
    return match.group("repository"), match.group("tag"), match.group("digest")


def image_of_service(service):
    """Which image of the inventory a service of the base compose runs."""
    for image, spec in IMAGES.items():
        if service in spec["services"]:
            return image
    return None


def secret_scan(text):
    """Refuse a manifest that carries a credential-shaped value."""
    problems = []
    for number, raw in enumerate(text.splitlines(), start=1):
        if raw.lstrip().startswith("#") or not raw.strip():
            continue
        key, _sep, value = raw.partition(":")
        if not value.strip():
            continue
        if SECRET_KEY_RE.search(key):
            problems.append(f"line {number} sets {key.strip()}, which looks like a "
                            "credential; a deployment manifest names artifacts, "
                            "runtime configuration belongs in the .env")
    return problems


# ------------------------------------------------------- the candidate evidence


# The shape of the file `--attest` writes and `release_promotion.py` reads. A
# name, not a version number to bump: a promotion that accepted two shapes would
# accept the one it was written for and quietly ignore the other.
CANDIDATE_EVIDENCE = "mrmap-candidate-images/1"


def attest_candidate(images, root, version, sha, kind, registry_base=REGISTRY_BASE,
                     actor=None):
    """Ask the registry what the candidate of this commit IS, as a document.

    Every fact in the answer comes from the registry, not from the caller: the
    digest a build printed to stdout is a claim, the digest the candidate tag
    RESOLVES to is a fact, and the promotion has to be able to tell the two
    apart. The labels are the second half of the answer - an artifact under the
    right name that says it is somebody else's revision is exactly the stale
    candidate a re-run of an old build leaves behind, and only the artifact
    itself can say so.

    Returns ``(document, problems)``; ``document`` is None when anything is
    refused, so a caller cannot write a partial file by accident.
    """
    problems = []
    entries = {}
    for image in images:
        tags, _aliases = tags_for(image, version, sha, kind, [], registry_base)
        ref = tags[0]
        try:
            digest, identity = artifact_identity(ref, root)
            _probe_digest, labels = artifact_info(ref, root)
        except ReleaseError as error:
            problems.append(f"{image}: the candidate {ref} could not be read "
                            f"({error}); an artifact that cannot be looked at is "
                            "not a candidate")
            continue
        answered = labels.get("org.opencontainers.image.version")
        if answered is None:
            problems.append(
                f"{image}: {ref} carries no org.opencontainers.image.version "
                "label, so it was not built by scripts/image_release.py and "
                "cannot attest itself")
            continue
        if answered != version:
            problems.append(f"{image}: {ref} answers version {answered!r} while the "
                            f"candidate under review is {version}; this is the "
                            "artifact of another build")
            continue
        revision = labels.get("org.opencontainers.image.revision")
        if revision != sha:
            problems.append(f"{image}: {ref} answers revision {revision!r}, not the "
                            f"candidate {sha}; a stale candidate tag is not evidence "
                            "for a commit it was not built from")
            continue
        entries[image] = {
            "repository": IMAGES[image]["repository"],
            "repository_ref": repository(image, registry_base),
            "candidate_ref": ref,
            "digest": digest,
            "identity": list(identity),
            "labels": {key: labels[key] for key in sorted(labels)},
        }
        try:
            # Reading the digest as its own reference is the second of the two
            # --verify questions, and the one a promotion depends on: it is what
            # `--promote` will be handed, so it has to resolve on its own.
            source_digest, _labels = artifact_info(
                f"{repository(image, registry_base)}@{digest}", root)
        except ReleaseError as error:
            problems.append(f"{image}: the digest {digest} of {ref} does not resolve "
                            f"on its own ({error}); promotion is by digest, so an "
                            "unresolvable digest is nothing to promote")
            continue
        if source_digest != digest:
            problems.append(f"{image}: {ref} resolves to {digest} but {source_digest} "
                            "answers under that digest; the registry is giving two "
                            "answers for one artifact")
            continue
    if problems:
        return None, problems
    document = {
        "evidence": CANDIDATE_EVIDENCE,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": actor or os.environ.get("GITHUB_ACTOR") or "unknown",
        "candidate": {"sha": sha, "version": version, "kind": kind},
        "registry_base": registry_base,
        "images": {image: entries[image] for image in sorted(entries)},
        "note": "what the registry answers for the candidate published by "
                ".github/workflows/candidate-images.yml; the promotion re-reads "
                "every digest here before it uses one, and a version tag is "
                "created only by scripts/image_release.py --promote",
    }
    return document, []


def validate_candidate_evidence(path, version=None, sha=None,
                                registry_base=REGISTRY_BASE, images=None):
    """Read an evidence file back and check everything the FILE can answer.

    No registry is asked here, so this is the half a promotion may run host-side:
    the shape, the binding to (sha, version), the registry it was written for and
    the repository names. ``load_candidate_evidence`` adds the registry's own
    answer on top. Splitting the two is what lets ``release_promotion.py`` refuse
    a stale or hand-edited file without a container, while the tool that writes
    the tag still asks the registry itself.

    Returns ``(document, problems)``; problems is empty when the file is usable.
    """
    problems = []
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ReleaseError(f"the candidate evidence {path} could not be read: {error}")
    except json.JSONDecodeError as error:
        raise ReleaseError(f"the candidate evidence {path} is not JSON: {error}")
    if document.get("evidence") != CANDIDATE_EVIDENCE:
        raise ReleaseError(
            f"the candidate evidence {path} declares {document.get('evidence')!r}, "
            f"not {CANDIDATE_EVIDENCE!r}; a promotion reads one shape and refuses "
            "every other, because a silently-unknown field is a silently-missing "
            "check")
    candidate = document.get("candidate") or {}
    file_sha = candidate.get("sha")
    file_version = candidate.get("version")
    if sha and file_sha != sha:
        problems.append(f"the evidence file is for {str(file_sha)[:12]}, not the "
                        f"candidate {sha[:12]} - digests of another build cannot "
                        "promote this one")
    if version and file_version != version:
        problems.append(f"the evidence file is for version {file_version!r}, not "
                        f"{version!r}")
    base = document.get("registry_base") or REGISTRY_BASE
    if base != registry_base:
        problems.append(f"the evidence file was published to {base}, not to "
                        f"{registry_base}; a digest is only meaningful inside the "
                        "registry that wrote it")
    entries = document.get("images") or {}
    wanted = list(images) if images else sorted(IMAGES)
    for image in wanted:
        entry = entries.get(image)
        if not isinstance(entry, dict):
            problems.append(f"the evidence file says nothing about {image}; every "
                            "image of the release needs its own digest")
            continue
        if entry.get("repository") != IMAGES[image]["repository"]:
            problems.append(f"{image}: the evidence names {entry.get('repository')!r}, "
                            f"this release builds {IMAGES[image]['repository']!r}")
            continue
        digest = entry.get("digest", "")
        if not DIGEST_RE.match(digest):
            problems.append(f"{image}: {digest!r} is not sha256:<64 hex>")
            continue
        repo = repository(image, registry_base)
        expected_ref = entry.get("repository_ref")
        if expected_ref and expected_ref != repo:
            problems.append(f"{image}: the evidence points at {expected_ref}, this "
                            f"release builds {repo}")
            continue
    return document, problems


def load_candidate_evidence(path, root, version=None, sha=None,
                            registry_base=REGISTRY_BASE, images=None):
    """The evidence file plus the registry's own answer about every line.

    The file is the candidate's own claim; the registry answers the same question
    independently, so a hand-edited digest, a candidate that has since been
    rebuilt and a reference that never existed all end here with a refusal naming
    the image, the value and the question it failed. Re-reading the registry
    costs three requests; releasing the wrong bytes costs a database.
    """
    document, problems = validate_candidate_evidence(
        path, version, sha, registry_base, images)
    entries = document.get("images") or {}
    wanted = list(images) if images else sorted(IMAGES)
    for image in wanted:
        entry = entries.get(image)
        if not isinstance(entry, dict) or not DIGEST_RE.match(entry.get("digest", "")):
            continue
        if entry.get("repository") != IMAGES[image]["repository"]:
            continue
        digest = entry["digest"]
        repo = repository(image, registry_base)
        try:
            served, labels = artifact_info(f"{repo}@{digest}", root)
        except ReleaseError as error:
            problems.append(f"{image}: {repo}@{digest} could not be read ({error}); "
                            "promotion is by digest, so an unreadable digest is not "
                            "an artifact")
            continue
        if served != digest:
            problems.append(f"{image}: {repo}@{digest} answered {served}; the "
                            "registry does not serve these bytes under this digest")
            continue
        answered = labels.get("org.opencontainers.image.version")
        if version and answered != version:
            problems.append(f"{image}: the artifact under {digest} answers version "
                            f"{answered!r}, not {version!r}")
            continue
        revision = labels.get("org.opencontainers.image.revision")
        if sha and revision != sha:
            problems.append(f"{image}: the artifact under {digest} answers revision "
                            f"{str(revision)[:12]}, not the candidate {sha[:12]} - "
                            "these are the bytes of another commit")
    return document, problems


def verify_pinned_artifacts(services, expected, version, root):
    """Ask each pinned artifact which version it is, and compare what it answers.

    Two questions, because they fail differently. Resolving the TAG answers "is
    this still what was released" - a tag that was moved, republished or raced is
    caught here. Resolving the DIGEST answers "are these the bytes of this
    release" - which is what the version label says.

    Asking only the full ``repo:tag@digest`` reference would ask neither:
    measured for #1582, a distribution resolves that form by the digest and
    ignores the tag, so the digest check would compare a value with itself and
    always pass. That is the hole this function had before it was measured.
    """
    problems = []
    for service in sorted(expected & set(services)):
        ref = services[service]["image"]
        if not ref:
            continue
        try:
            repo, tag, digest = parse_image_ref(ref)
        except ReleaseError as error:
            problems.append(f"{service}: {error}")
            continue
        if tag:
            try:
                served, _labels = artifact_info(f"{repo}:{tag}", root)
            except ReleaseError as error:
                problems.append(f"{service}: the tag {tag} could not be resolved "
                                f"({error}); a manifest may not pin a name the "
                                "registry does not serve")
                continue
            if digest and served != digest:
                problems.append(f"{service}: {repo}:{tag} resolves to {served}, but the "
                                f"manifest pins {digest}; the tag has moved away from "
                                "what was released")
        probe = f"{repo}@{digest}" if digest else f"{repo}:{tag}"
        try:
            _digest, labels = artifact_info(probe, root)
        except ReleaseError as error:
            problems.append(f"{service}: the pinned artifact could not be inspected "
                            f"({error}); an artifact that cannot be looked at is not a pin")
            continue
        answer = labels.get("org.opencontainers.image.version")
        if answer is None:
            problems.append(f"{service}: the artifact carries no "
                            "org.opencontainers.image.version label, so it was not "
                            "built by scripts/image_release.py")
        elif version and answer != version:
            problems.append(f"{service}: the artifact answers version {answer} while "
                            f"the manifest pins {version}; this tag points at the "
                            "bytes of another release")
    return problems


def check_manifest(path, root, version=None, registry_base=REGISTRY_BASE,
                   verify=False, allow_tag_only=False):
    """Every way a deployment manifest can be wrong, as a list of problems.

    Version mixing is the reason this exists: four services, three of them one
    image, and one line left behind by an edit is a backend and a worker of two
    versions against one database.
    """
    problems = []
    text = Path(path).read_text(encoding="utf-8")
    services = parse_manifest(text)
    expected = {service for spec in IMAGES.values() for service in spec["services"]}
    named = set(services)

    for service in sorted(expected - named):
        problems.append(f"{service} is not pinned by this manifest, so it keeps "
                        "building from the checkout instead of running the release")
    for service in sorted(named - expected):
        if services[service]["image"]:
            problems.append(f"{service} is pinned here although docker-compose.yml "
                            "does not build it from a first-party Dockerfile; "
                            "third-party images stay pinned by docker-compose.yml")

    tags = {}
    for service in sorted(expected & named):
        entry = services[service]
        if entry["image"] is None:
            problems.append(f"{service} names no image")
            continue
        try:
            repo, tag, digest = parse_image_ref(entry["image"])
        except ReleaseError as error:
            problems.append(f"{service}: {error}")
            continue
        if digest is None and not allow_tag_only:
            problems.append(f"{service} is pinned by tag only; without a digest a "
                            "rebuilt tag changes the deployment unnoticed")
        if entry["build"]:
            resets = [line for line in entry["lines"] if line.startswith("build:")]
            if not any("reset" in line or "null" in line for line in resets):
                problems.append(f"{service} keeps a live build: section, so compose "
                                "may build from the checkout instead of pulling the "
                                "pinned artifact")
        image = image_of_service(service)
        wanted_repo = repository(image, registry_base)
        if repo != wanted_repo:
            problems.append(f"{service} points at {repo}, but this release builds "
                            f"{wanted_repo}")
        tags[service] = tag

    if version:
        for service, tag in sorted(tags.items()):
            if tag is not None and tag != version_tag(version):
                problems.append(f"{service} is tagged {tag}, this manifest is for "
                                f"{version}; a deployment that mixes versions of one "
                                "release is exactly what a manifest prevents")
    distinct = {tag for tag in tags.values() if tag}
    if len(distinct) > 1:
        problems.append(f"the manifest mixes {len(distinct)} tags "
                        f"({', '.join(sorted(distinct))}); backend, celery-worker and "
                        "celery-beat are one image, so a split tag is a split release")

    pins = base_compose_image_pins(root)
    for service, entry in sorted(services.items()):
        if service in pins and entry["image"] and entry["image"] != pins[service]:
            problems.append(f"{service} overrides the third-party pin {pins[service]} "
                            f"with {entry['image']}; third-party images are versioned "
                            "by docker-compose.yml and Renovate")

    problems.extend(secret_scan(text))
    if verify:
        problems.extend(verify_pinned_artifacts(services, expected, version, root))
    return problems


# ------------------------------------------------------------- inventory output


def inventory_lines(root, registry_base=REGISTRY_BASE):
    """The build and pull paths of the #1582 inventory, as readable lines."""
    lines = []
    for image in sorted(IMAGES):
        spec = IMAGES[image]
        lines.append(f"{image:<9} builds   {spec['dockerfile']} (context {spec['context']})")
        lines.append(f"{'':<9} names     {repository(image, registry_base)}"
                     ":<version> | :candidate-<sha> | :dev-<sha>")
        lines.append(f"{'':<9} serves   docker-compose.yml: {', '.join(spec['services'])}")
    lines.append("")
    lines.append("  .github/workflows/candidate-images.yml publishes the CANDIDATE tags of")
    lines.append("  one explicitly selected, reviewed commit and writes this tool's")
    lines.append("  evidence file (#1799); nothing else writes a version tag, because only")
    lines.append("  --promote creates one and --promote runs behind the release-stable")
    lines.append("  environment of .github/workflows/release-promotion.yml. Q1/Q4 of #1578")
    lines.append("  are answered policy, not a publisher (ADR-0002): publishing a release")
    lines.append("  stays a human act, and dev-images.yml on the #959 dependency contract")
    lines.append("  is the only other publisher in the repository.")
    lines.append("")
    lines.append("dev tooling only - contract of #959, untouched by a release:")
    lines.append("  ghcr.io/mrmap-community/mrmap-backend-dev:<fingerprint>")
    lines.append("      backend, celery-worker, celery-beat, pre-commit-check, behave,")
    lines.append("      django-tests in the agent stack; built by dev-images.yml, named")
    lines.append("      by scripts/dev_image_id.py, resolved by --resolve / --exists")
    lines.append("  ghcr.io/mrmap-community/mrmap-frontend-dev:<fingerprint>")
    lines.append("      seeds the frontend-tests node_modules volume")
    lines.append("")
    lines.append("pinned by docker-compose.yml, never by a release manifest:")
    for service, image in sorted(base_compose_image_pins(root).items()):
        lines.append(f"  {service:<18} {image}")
    return lines


# ------------------------------------------------------------------------- main


def parse_digest_args(entries):
    """``--digest image=sha256:...`` repeated per image, as a dict."""
    digests = {}
    for entry in entries:
        match = DIGEST_ARG_RE.match(entry)
        if not match:
            raise ReleaseError(f"--digest {entry!r} must read image=sha256:<64 hex>")
        name = match.group("image")
        if name not in IMAGES:
            raise ReleaseError(f"--digest names {name!r}; this release builds "
                               f"{', '.join(sorted(IMAGES))}")
        digests[name] = match.group("digest")
    return digests


def build_parser():
    parser = argparse.ArgumentParser(
        description="the version identity of the first-party runtime images (#1582)",
        allow_abbrev=False)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT,
                        help="checkout to read (default: the repository holding this script)")
    parser.add_argument("--registry-base", default=REGISTRY_BASE,
                        help=f"registry and namespace to name (default: {REGISTRY_BASE}); "
                             "point it at a local registry to test a release end to end")
    parser.add_argument("--image", choices=sorted(IMAGES), default=None,
                        help="one image only (default: every image this release builds)")
    parser.add_argument("--version", default=None,
                        help="the version to name (default: the root VERSION file)")
    parser.add_argument("--revision", default=None,
                        help="the source commit to name (default: HEAD)")
    parser.add_argument("--kind", choices=KINDS, default=None,
                        help="stable, prerelease or dev (default: what VERSION says)")
    parser.add_argument("--alias", action="append", default=[], dest="aliases",
                        metavar="TAG", help="additionally write this rolling alias; "
                        "refused for a dev build and for stable aliases of a prerelease")
    parser.add_argument("--digest", action="append", default=[], dest="digests",
                        metavar="IMAGE=sha256:...",
                        help="the digest of one image, repeated per image; needed by "
                             "--promote and --manifest unless the candidate is in the registry")
    parser.add_argument("--candidate-evidence", metavar="PATH", default=None,
                        dest="candidate_evidence",
                        help="with --promote: read the digests to promote from the "
                             "evidence file of --attest instead of pasting them, and "
                             "re-ask the registry about every line before writing a "
                             "tag; --digest entries override the file per image")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --build/--promote: print the commands, run nothing")
    parser.add_argument("--push", action="store_true",
                        help="with --build: also publish the candidate tags this plan names")
    parser.add_argument("--verify", action="store_true",
                        help="with --check-manifest: ask each pinned artifact its own version")
    parser.add_argument("--actor", default=None,
                        help="with --attest: who produced this evidence (default: "
                             "$GITHUB_ACTOR, then 'unknown')")
    parser.add_argument("--allow-tag-only", action="store_true", dest="allow_tag_only",
                        help="with --check-manifest: accept a manifest without digests")
    # Only the ACTIONS are mutually exclusive; --push/--verify/--allow-tag-only
    # are modifiers of one action and would otherwise refuse their own use:
    # `--build --push` and `--check-manifest --verify` are what the docstring
    # recommends and what the evidence run of #1582 runs.
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true",
                      help="print the build commands and refs, change nothing (default)")
    mode.add_argument("--build", action="store_true",
                      help="build the candidate image(s) under their candidate tags")
    mode.add_argument("--attest", metavar="PATH", default=None,
                      help="write the registry's answer about the published "
                           "candidate(s) of one commit as a JSON evidence file for "
                           "the promotion; refuses when an artifact contradicts the "
                           "candidate it is supposed to attest")
    mode.add_argument("--promote", action="store_true",
                      help="create the immutable version tag from a tested digest")
    mode.add_argument("--manifest", metavar="PATH", default=None,
                      help="write the version-pinned deployment manifest")
    mode.add_argument("--check-manifest", metavar="PATH", default=None,
                      help="verify that a deployment manifest is coherent")
    mode.add_argument("--inventory", action="store_true",
                      help="print the inventory of build and pull paths")
    mode.add_argument("--labels", action="store_true",
                      help="print the OCI labels of one image as JSON")
    mode.add_argument("--print", metavar="KEY", default=None, dest="print_key",
                      choices=sorted(PRINT_KEYS),
                      help="print one key of what to build (tags, candidate-tag, "
                           "repository, dockerfile, context, labels, build-args, "
                           "source-date-epoch) - the machine read of --plan, so a "
                           "builder consumes the tool's decision instead of "
                           "computing its own")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = args.repo_root.resolve()

    if args.inventory:
        print("\n".join(inventory_lines(root, args.registry_base)))
        return 0

    if args.check_manifest:
        problems = check_manifest(args.check_manifest, root, args.version,
                                  args.registry_base, args.verify, args.allow_tag_only)
        for problem in problems:
            print(f"image_release: {problem}", file=sys.stderr)
        if problems:
            return 1
        print(f"image_release: {args.check_manifest} is coherent"
              + (f" for {args.version}" if args.version else "")
              + (" and every pinned artifact confirms its own version" if args.verify else ""))
        return 0

    version = args.version or version_of(root)
    if args.version and not SEMVER_BASE_RE.match(split_version(args.version)[0]):
        raise ReleaseError(f"--version {args.version} is not a SemVer major.minor.patch")
    kind = args.kind or classify(version)
    sha = args.revision or git_identity(root)[0]
    images = [args.image] if args.image else sorted(IMAGES)
    digests = parse_digest_args(args.digests)

    if args.labels:
        if len(images) != 1:
            raise ReleaseError("--labels asks for one image; pass --image")
        print(json.dumps(labels_for(images[0], root, version, sha), indent=2))
        return 0

    if args.print_key:
        if len(images) != 1:
            raise ReleaseError("--print asks for one image; pass --image")
        print(plan_value(images[0], root, version, sha, kind, args.aliases,
                         args.registry_base, args.print_key))
        return 0

    if args.manifest:
        if args.candidate_evidence:
            raise ReleaseError(
                "--candidate-evidence belongs with --promote: a deployment manifest "
                "pins what the release tag ANSWERS in the registry, which is not the "
                "candidate digest an evidence file names")
        resolved = dict(digests)
        for image in images:
            if image in resolved:
                continue
            # The digest a release tag RESOLVES TO, not the candidate digest the
            # caller happens to hold: promotion wraps the copied bytes in an
            # index, so the tag's digest is the one an operator will pull, and it
            # is the only digest a later `--verify` can meaningfully compare.
            tag_ref = f"{repository(image, args.registry_base)}:{version_tag(version)}"
            found = existing_artifact(tag_ref, root)
            if found is None:
                raise ReleaseError(
                    f"{tag_ref} is not published, so there is nothing to pin; promote "
                    f"the tested candidate first, or name a digest explicitly with "
                    f"--digest {image}=sha256:...")
            resolved[image] = found[0]
        text = render_manifest(version, kind, args.registry_base, resolved, sha,
                               filename=Path(args.manifest).name, aliases=args.aliases)
        Path(args.manifest).write_text(text, encoding="utf-8")
        problems = check_manifest(args.manifest, root, version, args.registry_base)
        if problems:
            Path(args.manifest).unlink()
            for problem in problems:
                print(f"image_release: {problem}", file=sys.stderr)
            return 1
        print(f"image_release: wrote {args.manifest} for {version} ({kind})")
        return 0

    if args.attest:
        document, problems = attest_candidate(images, root, version, sha, kind,
                                              args.registry_base, args.actor)
        for problem in problems:
            print(f"image_release: {problem}", file=sys.stderr)
        if problems:
            return 1
        path = Path(args.attest)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        answered = ", ".join(f"{image}@{document['images'][image]['digest'][:19]}..."
                             for image in sorted(document["images"]))
        print(f"image_release: attested {version} at {sha[:12]} from "
              f"{args.registry_base}: {answered}")
        print(f"image_release: wrote {args.attest}")
        return 0

    if args.promote:
        if args.candidate_evidence:
            # The digests are not handed to this run by a person: they are read
            # from the file the candidate build wrote and then RE-READ from the
            # registry, so a stale, hand-edited or foreign artifact is refused
            # here rather than becoming a released tag (#1799).
            document, problems = load_candidate_evidence(
                args.candidate_evidence, root, version, sha, args.registry_base,
                images)
            for problem in problems:
                print(f"image_release: {problem}", file=sys.stderr)
            if problems:
                return 1
            for image in images:
                # An explicit --digest still wins: it is how an operator names a
                # re-built candidate, and the identity checks in promote() then
                # have to agree with the registry about it either way.
                digests.setdefault(image, document["images"][image]["digest"])
        missing = [image for image in images if image not in digests]
        if missing:
            raise ReleaseError(
                "--promote needs --digest <image>=sha256:... for "
                f"{', '.join(missing)}: promotion is by digest, because rebuilding "
                "is not promoting")
        for image in images:
            for ref, state in promote(image, root, version, sha, kind, digests[image],
                                      args.registry_base, args.aliases, args.dry_run):
                print(f"image_release: {state}: {ref}")
        return 0

    for image in images:
        if args.build:
            tags = build_image(image, root, version, sha, kind, args.aliases,
                               args.registry_base, args.push, args.dry_run)
            print(f"image_release: {image} candidate refs: {', '.join(tags)}")
            continue
        for line in plan_for(image, root, version, sha, kind, args.aliases,
                             args.registry_base):
            print(line)
        print("")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ReleaseError as error:
        print(f"image_release: refused - {error}", file=sys.stderr)
        sys.exit(1)
