#!/usr/bin/env python3
"""Versioned image guard (#1582): one identity per release, one pinned image set.

Run from the repository root:  python3 scripts/test_image_release.py
Standard library only; no network, no push. Exit 0 = every check passed, 1 = a
check failed, 2 = the harness itself could not run. The two checks that ask
docker what Compose really renders probe for the CLI and say so out loud when
they skip (the convention of the other image suites and of
``scripts/check_repo_tooling.sh``).

Why this guard exists
---------------------
#1579 gave MrMap one canonical application version. #1582 gives that version an
artifact identity: names, immutable tags, OCI labels, and a deployment manifest
whose every line is a digest. Each of those is a rule somebody can break with a
well-meaning edit - a workflow that computes a tag itself, a service added to
``docker-compose.yml`` and quietly left out of a release, an alias written by a
dev build, one line of a manifest left at the previous version. The last one is
the expensive failure: three of the four first-party services run the SAME image,
so one stale line puts a backend and its worker on two versions against one
database, and nothing fails until data is wrong.

What it checks
--------------
1. The tag policy: build metadata never becomes a tag (the reference grammar has
   no ``+``), prereleases stay prereleases, ``dev-<sha>`` can never carry an
   alias, and a prerelease can never move ``latest``.
2. The labels: the full version (metadata included) in
   ``org.opencontainers.image.version``, the exact commit in ``.revision``, the
   dependency fingerprint on the backend image and NOT on the frontend image,
   whose inputs #962's fingerprint does not describe.
3. The build arguments: the frontend refuses to build without its API address,
   which is what ``docker-compose.yml``'s ``:?`` already demands.
4. The live repository: the inventory still matches the ``build:`` sections of
   ``docker-compose.yml`` in both directions, the Dockerfiles exist, the release
   names are not the ``-dev`` names of #959, and the manifest shape still is the
   ``image:`` + ``build: !reset null`` shape ``docker-compose.prebuilt.yml``
   established.
5. The manifest round trip and every refusal: an unpinned service, two versions
   in one manifest, a foreign repository, a missing digest, a live build section,
   an overridden third-party pin, a credential-shaped line.
6. Promotion, with the two registry doors of the module stubbed: identical
   content re-promoted is ``already promoted`` and not a conflict - because
   promotion re-wraps the bytes in a new index and therefore writes a different
   digest - while another image's content under the same tag is refused, an
   unpublished source digest cannot be tagged, and neither a dev build nor a
   prerelease can promote its way onto a stable alias.
7. ``--verify``, which asks the TAG and the DIGEST separately: resolving the
   combined ``repo:tag@digest`` reference would trivially pass, because a
   distribution resolves that form by the digest and ignores the tag. A moved
   tag, an artifact answering another version and an unlabelled artifact are each
   refused by name.
8. The answer of one inspect call, read as what it is: a stream of INDENTED JSON
   documents. docker's ``{{ json }}`` spans several lines, so a reader that
   splits at newlines reads fragments and calls a pushed image unreadable - both
   manifest shapes, the bare one a build pushes and the index a promotion wraps
   around it, are read here.
9. With docker: ``docker compose config`` really drops the ``build:`` section and
   keeps the pinned reference - the guarantee the whole overlay rests on.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_release as ir  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
RESULTS = []

FAKE = "sha256:" + "a" * 64
FAKE2 = "sha256:" + "b" * 64
SHA = "0123456789abcdef0123456789abcdef01234567"


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def refused(name, call, fragment=""):
    """A refusal is a pass; a silent success is the failure being guarded."""
    try:
        call()
    except ir.ReleaseError as error:
        text = str(error)
        if fragment and fragment.lower() not in text.lower():
            check(name, False, f"refused for the wrong reason: {text}")
        else:
            check(name, True)
        return
    except Exception as error:  # noqa: BLE001
        check(name, False, f"raised {type(error).__name__} instead of refusing: {error}")
        return
    check(name, False, "accepted, and that is the hole this guard exists for")


# ------------------------------------------------------------ tag policy


def tag_policy_checks():
    check("split_version keeps prerelease",
          ir.split_version("0.2.0-rc.1") == ("0.2.0", "rc.1", ""),
          str(ir.split_version("0.2.0-rc.1")))
    check("split_version separates build metadata",
          ir.split_version("0.1.0+9f8e7d6") == ("0.1.0", "", "9f8e7d6"),
          str(ir.split_version("0.1.0+9f8e7d6")))
    check("version_tag drops build metadata (no '+' in a Docker tag)",
          ir.version_tag("1.0.0+9f8e7d6") == "1.0.0", ir.version_tag("1.0.0+9f8e7d6"))
    check("version_tag keeps a prerelease",
          ir.version_tag("0.2.0-rc.1") == "0.2.0-rc.1", ir.version_tag("0.2.0-rc.1"))
    check("classify reads 0.1.0 as stable", ir.classify("0.1.0") == "stable")
    check("classify reads 0.2.0-rc.1 as prerelease",
          ir.classify("0.2.0-rc.1") == "prerelease")

    tags, aliases = ir.tags_for("backend", "0.2.0", SHA, "stable")
    check("a stable release names one immutable tag",
          tags == ["ghcr.io/mrmap-community/mrmap-backend:0.2.0"] and aliases == [],
          f"{tags} {aliases}")
    tags, aliases = ir.tags_for("frontend", "0.2.0", SHA, "dev")
    check("a dev build is tagged by its commit",
          tags == ["ghcr.io/mrmap-community/mrmap-frontend:dev-" + SHA[:12]]
          and aliases == [], f"{tags} {aliases}")
    tags, aliases = ir.tags_for("backend", "0.2.0", SHA, "stable", aliases=["latest", "0.2"])
    check("aliases are opt-in and explicit",
          aliases == ["ghcr.io/mrmap-community/mrmap-backend:latest",
                      "ghcr.io/mrmap-community/mrmap-backend:0.2"], str(aliases))
    check("the registry base is overridable for an isolated test",
          ir.tags_for("backend", "0.2.0", SHA, "stable",
                      registry_base="reg:5000/mrmap")[0][0]
          == "reg:5000/mrmap/mrmap-backend:0.2.0")

    refused("a dev build may not write a rolling alias",
            lambda: ir.tags_for("backend", "0.2.0", SHA, "dev", aliases=["latest"]),
            "alias")
    refused("a prerelease may not move latest",
            lambda: ir.tags_for("backend", "0.2.0-rc.1", SHA, "prerelease", aliases=["latest"]),
            "stable alias")
    check("a prerelease may carry its own alias",
          ir.tags_for("backend", "0.2.0-rc.1", SHA, "prerelease", aliases=["rc"])[1]
          == ["ghcr.io/mrmap-community/mrmap-backend:rc"])
    refused("--kind stable on a prerelease version is refused",
            lambda: ir.tags_for("backend", "0.2.0-rc.1", SHA, "stable"), "prerelease")
    refused("--kind prerelease on a plain version is refused",
            lambda: ir.tags_for("backend", "0.2.0", SHA, "prerelease"), "prerelease part")
    refused("an unknown image has no release name",
            lambda: ir.repository("docs"), "unknown image")


# --------------------------------------------------------------- labels/args


def label_checks():
    labels = ir.labels_for("backend", REPO, "1.2.3+9f8e7d6", SHA)
    check("the label carries the FULL version, metadata included",
          labels["org.opencontainers.image.version"] == "1.2.3+9f8e7d6",
          labels["org.opencontainers.image.version"])
    check("the label carries the exact commit",
          labels["org.opencontainers.image.revision"] == SHA)
    check("the label names the source repository",
          labels["org.opencontainers.image.source"]
          == "https://github.com/mrmap-community/mrmap")
    fingerprint = labels.get("io.github.mrmap.dependency-fingerprint", "")
    check("the backend image names the dependency fingerprint of #959",
          re.match(r"^[0-9a-f]{12}$", fingerprint) is not None, fingerprint)
    frontend = ir.labels_for("frontend", REPO, "1.2.3", SHA)
    check("the frontend image carries NO dependency fingerprint (different inputs)",
          "io.github.mrmap.dependency-fingerprint" not in frontend,
          str(sorted(frontend)))

    refused("the frontend refuses to build without its API address",
            lambda: ir.build_args_for("frontend", REPO, env={}, sha=SHA), "VITE_API_BASE_URL")
    args = ir.build_args_for("frontend", REPO,
                             env={"EXTERNAL_BASE_URL": "mrmap.example", "EXTERNAL_PORT": "443",
                                  "EXTERNAL_SCHEME": "https"}, sha=SHA)
    check("the compose variable names are accepted",
          args["VITE_API_BASE_URL"] == "mrmap.example"
          and args["VITE_API_SCHEMA"] == "https", str(args))
    check("every build stamps the exact revision",
          args["MRMAP_BUILD_REVISION"] == SHA)
    check("the backend build needs no API address",
          ir.build_args_for("backend", REPO, env={}, sha=SHA)["MRMAP_BUILD_REVISION"] == SHA)


# ------------------------------------------------- the live repository's shape


def live_repo_checks():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    lines = compose.splitlines()
    service = None
    building = []
    for raw in lines:
        if raw.startswith("  ") and not raw.startswith("   ") and raw.rstrip().endswith(":"):
            service = raw.strip()[:-1]
        elif service and raw.strip() == "build:":
            building.append(service)
    inventoried = sorted(s for spec in ir.IMAGES.values() for s in spec["services"])
    check("every build: section of the production compose is in the inventory",
          sorted(building) == inventoried,
          f"compose builds {sorted(building)}, inventory says {inventoried}")

    for image, spec in ir.IMAGES.items():
        check(f"{image}'s Dockerfile exists",
              (REPO / spec["dockerfile"]).exists(), spec["dockerfile"])
        check(f"{image}'s build context exists",
              (REPO / spec["context"].rstrip("/").lstrip("./") or ".").exists(),
              spec["context"])
        named = len(re.findall(re.escape(spec["dockerfile"]), compose))
        check(f"{image}'s Dockerfile is named once per service it serves",
              named >= len(spec["services"]),
              f"{spec['dockerfile']} appears {named}x for {len(spec['services'])} services")

    check("a release name is never a #959 dependency name",
          all(not spec["repository"].endswith("-dev") for spec in ir.IMAGES.values()),
          str([spec["repository"] for spec in ir.IMAGES.values()]))

    pins = ir.base_compose_image_pins(REPO)
    check("the third-party pins of docker-compose.yml are read",
          {"postgis", "redis", "docker-api", "victoria-logs", "grafana", "pgadmin", "flower"}
          <= set(pins), str(sorted(pins)))
    check("no first-party image carries a pin (they are built, not pulled)",
          not any(s in pins for s in inventoried), str(sorted(pins)))

    prebuilt = (REPO / "docker-compose.prebuilt.yml").read_text(encoding="utf-8")
    check("the manifest shape is the one docker-compose.prebuilt.yml established",
          "build: !reset null" in prebuilt)

    nginx = (REPO / "docker/nginx/nginx.Dockerfile").read_text(encoding="utf-8")
    check("the frontend image still takes the revision the release stamps",
          "ARG MRMAP_BUILD_REVISION" in nginx)
    workflow = (REPO / ".github/workflows/dev-images.yml").read_text(encoding="utf-8")
    untouched = "mrmap-backend:" not in workflow.replace("mrmap-backend-dev", "")
    check("the dev-image publisher is untouched by this tool's names",
          "mrmap-backend-dev" in workflow and untouched)


# ----------------------------------------------------------------- the manifest


def manifest_checks():
    digests = {"backend": FAKE, "frontend": FAKE2}
    text = ir.render_manifest("0.2.0", "stable", ir.REGISTRY_BASE, digests, SHA,
                              filename="mrmap-0.2.0.yml")
    services = ir.parse_manifest(text)
    check("the manifest names all four first-party services",
          set(services) == {"backend", "celery-worker", "celery-beat", "frontend"},
          str(sorted(services)))
    check("worker and beat carry the backend digest, frontend its own",
          services["celery-worker"]["image"].endswith(FAKE)
          and services["celery-beat"]["image"].endswith(FAKE)
          and services["frontend"]["image"].endswith(FAKE2))
    check("every line pins tag AND digest",
          all("@sha256:" in (s["image"] or "") and ":0.2.0@" in (s["image"] or "")
              for s in services.values()),
          str({k: v["image"] for k, v in services.items()}))
    check("the alias comment lines create no services",
          "services:" in text and set(ir.parse_manifest(text + "  # note\n")) == set(services))
    refused("a manifest cannot be rendered with one image unpinned",
            lambda: ir.render_manifest("0.2.0", "stable", ir.REGISTRY_BASE,
                                       {"backend": FAKE}, SHA),
            "unpinned")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docker-compose.yml").write_text(
            (REPO / "docker-compose.yml").read_text(encoding="utf-8"), encoding="utf-8")
        good = root / "good.yml"
        good.write_text(text, encoding="utf-8")
        check("a rendered manifest passes its own check",
              ir.check_manifest(good, root, "0.2.0") == [],
              str(ir.check_manifest(good, root, "0.2.0")))

        def refuses(name, body, fragment, version="0.2.0"):
            path = root / f"{re.sub(r'[^a-z]+', '_', name)}.yml"
            path.write_text(body, encoding="utf-8")
            problems = ir.check_manifest(path, root, version)
            hit = any(fragment.lower() in p.lower() for p in problems)
            check(name, hit, f"no problem matched {fragment!r}; got {problems}")

        lost = text.replace("  celery-beat:\n    image:", "  celery-beat-disabled:\n    image:")
        refuses("an unpublished service is refused", lost, "celery-beat is not pinned")

        mixed = text.replace("mrmap-frontend:0.2.0@", "mrmap-frontend:0.1.9@")
        refuses("two versions in one manifest are refused", mixed, "mixes")

        foreign = text.replace("ghcr.io/mrmap-community/mrmap-backend:0.2.0@",
                               "registry.example.com/mrmap-backend:0.2.0@")
        refuses("a foreign repository is refused", foreign, "this release builds")

        drifted = text.replace("image: ghcr.io/mrmap-community/mrmap-backend:0.2.0@",
                               "image: ghcr.io/mrmap-community/mrmap-backend:0.1.9@")
        refuses("a service left at the previous version is refused", drifted,
                "celery-worker is tagged 0.1.9")

        tagonly = text.replace("@" + FAKE, "").replace("@" + FAKE2, "")
        refuses("a digest-less pin is refused", tagonly, "tag only")
        allowed = root / "tagonly.yml"
        allowed.write_text(tagonly, encoding="utf-8")
        check("a digest-less pin passes only when it is explicitly allowed",
              ir.parse_manifest(tagonly)["backend"]["image"].endswith(":0.2.0")
              and not any("tag only" in p for p in
                          ir.check_manifest(allowed, root, "0.2.0", allow_tag_only=True)),
              str(ir.check_manifest(allowed, root, "0.2.0", allow_tag_only=True)))

        rebuilt = text.replace("    build: !reset null", "    build:\n      context: ./backend")
        refuses("a live build section is refused", rebuilt, "build: section")

        overridden = text + "\n  postgis:\n    image: postgis/postgis:17-3.4-alpine\n"
        refuses("an overridden third-party pin is refused", overridden, "third-party pin")

        secret = text + "\n  backend:\n    image: ghcr.io/mrmap-community/mrmap-backend:0.2.0@" \
            + FAKE + "\n    DJANGO_SECRET_KEY:hunter2\n"
        refuses("a credential in a manifest is refused", secret, "credential")

        broken = text.replace("@" + FAKE, "@sha256:notadigest")
        refuses("a malformed reference is refused", broken, "not a valid image reference")

        pr = ir.render_manifest("0.2.0-rc.1", "prerelease", ir.REGISTRY_BASE, digests, SHA)
        path = root / "rc.yml"
        path.write_text(pr, encoding="utf-8")
        check("a prerelease manifest pins the -rc tag",
              ir.parse_manifest(pr)["backend"]["image"].startswith(
                  "ghcr.io/mrmap-community/mrmap-backend:0.2.0-rc.1@")
              and ir.check_manifest(path, root, "0.2.0-rc.1") == [],
              str(ir.check_manifest(path, root, "0.2.0-rc.1")))


# ------------------------------------------------------- promotion immutability


def promote_checks():
    """The promotion rules, with the module's two registry doors stubbed.

    ``artifact_identity`` and ``existing_artifact`` are the only doors to a
    registry in this module, so replacing those two is the honest way to hold the
    rules without a registry in the suite.
    """
    repo = ir.repository("backend")
    source = f"{repo}@{FAKE}"
    tag = f"{repo}:0.2.0"
    real_identity, real_existing = ir.artifact_identity, ir.existing_artifact

    def registry(answers):
        def identity(ref, root):
            if ref not in answers:
                raise ir.ReleaseError(f"{ref}: manifest unknown")
            return answers[ref]
        ir.artifact_identity = identity
        ir.existing_artifact = lambda ref, root: answers.get(ref)

    try:
        registry({source: (FAKE, (FAKE,))})
        check("promotion into a free tag is planned, not run, under --dry-run",
              ir.promote("backend", REPO, "0.2.0", SHA, "stable", FAKE, ir.REGISTRY_BASE,
                         (), True) == [(tag, f"would create from {FAKE[:19]}...")])
        refused("a promotion reads its source before writing, so an unpublished "
                "digest cannot be tagged",
                lambda: ir.promote("backend", REPO, "0.2.0", SHA, "stable", FAKE2,
                                   ir.REGISTRY_BASE, (), True),
                "manifest unknown")

        # The measured re-wrap: `buildx build` pushes a bare image manifest,
        # `imagetools create` copies those bytes into a NEW index, so the released
        # tag has a different digest for identical content (candidate 0d24dce2...
        # became index da504ede..., whose only child is 0d24dce2...). Identity is
        # the child set, and a promotion that compared digests would call its own
        # second run a conflicting release.
        registry({source: (FAKE, (FAKE,)), tag: (FAKE2, (FAKE,))})
        check("re-promoting the same content reports already promoted, not a conflict",
              ir.promote("backend", REPO, "0.2.0", SHA, "stable", FAKE, ir.REGISTRY_BASE,
                         (), False) == [(tag, "already promoted")])

        registry({source: (FAKE, (FAKE,)), tag: (FAKE2, (FAKE2,))})
        refused("a tag holding another image's content is never moved",
                lambda: ir.promote("backend", REPO, "0.2.0", SHA, "stable", FAKE,
                                   ir.REGISTRY_BASE, (), False),
                "never moved")

        # The alias policy is enforced because promote goes through tags_for; a
        # promote that computed its refs itself skipped it, which is the hole this
        # guard was written after.
        refused("a prerelease may not promote its way onto latest",
                lambda: ir.promote("backend", REPO, "0.2.0-rc.1", SHA, "prerelease", FAKE,
                                   ir.REGISTRY_BASE, ["latest"], True),
                "stable alias")
        refused("a dev build may not promote an alias either",
                lambda: ir.promote("backend", REPO, "0.2.0", SHA, "dev", FAKE,
                                   ir.REGISTRY_BASE, ["latest"], True),
                "alias")
    finally:
        ir.artifact_identity, ir.existing_artifact = real_identity, real_existing


def inspect_parsing_checks():
    """One inspect call's answer, read the way docker really writes it.

    ``{{ json ... }}`` in a buildx template is INDENTED over several lines, so a
    reader that splits the answer at newlines reads fragments - the bug the first
    evidence run of #1582 paid five minutes of building for, after a successful
    push. Both manifest shapes matter: the bare one a build pushes, and the index
    a promotion writes around those same bytes.
    """
    index = ('{\n  "schemaVersion": 2,\n'
             '  "mediaType": "application/vnd.oci.image.index.v1+json",\n'
             f'  "digest": "{FAKE2}",\n'
             f'  "manifests": [{{"digest": "{FAKE}", "size": 634}}]\n'
             '}\n')
    config = ('{\n  "created": "2026-11-19T00:00:00Z",\n  "config": {\n'
              '    "User": "mrmapuser",\n    "Labels": {\n'
              '      "org.opencontainers.image.version": "0.1.0"\n    }\n  }\n}\n')
    bare = ('{\n  "schemaVersion": 2,\n'
            '  "mediaType": "application/vnd.oci.image.manifest.v1+json",\n'
            f'  "digest": "{FAKE}",\n  "config": {{"digest": "{FAKE2}"}}\n'
            '}\n')
    answer = f"{FAKE2}\n{index}{config}"
    real = ir.docker
    try:
        ir.docker = lambda argv, root, **kwargs: answer
        check("the digest of a pretty-printed inspect answer is read",
              ir.artifact_info("any:ref", REPO)[0] == FAKE2)
        check("its labels arrive with it, indent and all",
              ir.artifact_info("any:ref", REPO)[1]
              == {"org.opencontainers.image.version": "0.1.0"})
        check("the identity of an index is its child, not its wrapper",
              ir.artifact_identity("any:ref", REPO) == (FAKE2, (FAKE,)))

        ir.docker = lambda argv, root, **kwargs: f"{FAKE}\n{bare}null\n"
        check("a bare image manifest is its own identity",
              ir.artifact_identity("any:ref", REPO) == (FAKE, (FAKE,)))
        check("an answer without an image config reads as no labels, not as an error",
              ir.artifact_info("any:ref", REPO)[1] == {})

        ir.docker = lambda argv, root, **kwargs: f"{FAKE}\n{{\n  \"schemaVersion\": 2,\n"
        refused("a fragment instead of a document is refused, not guessed",
                lambda: ir.artifact_info("any:ref", REPO), "unreadable json")
    finally:
        ir.docker = real


def verify_checks():
    """The two questions --verify asks, with the registry door stubbed.

    Asking the combined ``repo:tag@digest`` reference would trivially pass:
    measured for #1582, a distribution resolves that form by the DIGEST and
    ignores the tag. So the check resolves the tag and the digest separately, and
    each of the two answers is pinned here.
    """
    repo = ir.repository("backend")
    services = {"backend": {"image": f"{repo}:0.2.0@{FAKE}"}}
    expected = {"backend"}
    real = ir.artifact_info

    def answers(moved=None, answer="0.2.0"):
        def probe(ref, root):
            if ref.endswith(":0.2.0"):
                return (moved or FAKE, {})
            return (FAKE, {"org.opencontainers.image.version": answer})
        return probe

    try:
        ir.artifact_info = lambda ref, root: (
            FAKE, {"org.opencontainers.image.version": "0.2.0"})
        check("a tag that still resolves to the pinned digest is coherent",
              ir.verify_pinned_artifacts(services, expected, "0.2.0", REPO) == [],
              str(ir.verify_pinned_artifacts(services, expected, "0.2.0", REPO)))

        ir.artifact_info = answers(moved=FAKE2)
        problems = ir.verify_pinned_artifacts(services, expected, "0.2.0", REPO)
        check("a tag moved away from the pinned digest is refused",
              any("has moved" in p for p in problems), str(problems))

        ir.artifact_info = answers(answer="0.1.9")
        problems = ir.verify_pinned_artifacts(services, expected, "0.2.0", REPO)
        check("an artifact answering another version is refused",
              any("answers version 0.1.9" in p for p in problems), str(problems))

        ir.artifact_info = lambda ref, root: (FAKE, {})
        problems = ir.verify_pinned_artifacts(services, expected, "0.2.0", REPO)
        check("an artifact with no version label is refused",
              any("no org.opencontainers.image.version" in p for p in problems),
              str(problems))
    finally:
        ir.artifact_info = real


# ------------------------------------------------- what Compose really renders


def cli_checks():
    """The flag combinations the docs promise parse.

    An action exclusive group that swallows its own modifiers is the bug this
    guard caught in the making: ``--build --push`` is what the docstring
    recommends, and argparse refused it.
    """
    parser = ir.build_parser()
    parsed = parser.parse_args(["--build", "--push", "--registry-base", "reg:5000/m"])
    check("--build --push parses", parsed.build and parsed.push)
    parsed = parser.parse_args(["--check-manifest", "a.yml", "--verify", "--version", "1.2.3"])
    check("--check-manifest --verify parses", parsed.check_manifest == "a.yml" and parsed.verify)
    parsed = parser.parse_args(["--promote", "--digest", "backend=" + FAKE, "--alias", "latest"])
    check("--promote --digest --alias parses",
          parsed.promote and parsed.digests == ["backend=" + FAKE] and parsed.aliases == ["latest"])
    try:
        parser.parse_args(["--build", "--promote"])
    except SystemExit:
        check("two actions at once stay refused", True)
    else:
        check("two actions at once stay refused", False, "argparse accepted build and promote")
    check("--digest reaches the tool's own check, not argparse's",
          parser.parse_args(["--digest", "backend=notadigest"]).digests == ["backend=notadigest"])
    refused("a malformed --digest value is refused by parse_digest_args",
            lambda: ir.parse_digest_args(["backend=notadigest"]), "sha256")
    refused("--digest for an image this release does not build is refused",
            lambda: ir.parse_digest_args(["docs=" + FAKE]), "this release builds")


def compose_checks():
    """The guarantee the overlay rests on, asked of Compose itself.

    ``build: !reset null`` is a claim about Compose's merge semantics. A claim of
    that shape belongs next to the thing it describes: if a Compose version ever
    starts merging instead of resetting, a release would silently go back to
    building from a checkout - so this check asks, where docker is present.
    """
    if shutil.which("docker") is None:
        check("compose renders the pinned images and no build section", None,
              "skipped: no docker on this runner")
        RESULTS[-1] = ("compose renders the pinned images and no build section", True,
                       "skipped: no docker on this runner")
        return
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "mrmap-0.2.0.yml"
        overlay.write_text(ir.render_manifest("0.2.0", "stable", ir.REGISTRY_BASE,
                                              {"backend": FAKE, "frontend": FAKE2}, SHA),
                           encoding="utf-8")
        env = {"EXTERNAL_BASE_URL": "localhost", "EXTERNAL_PORT": "8001",
               "EXTERNAL_SCHEME": "http", "PATH": "/usr/bin:/bin:/usr/local/bin"}
        try:
            proc = subprocess.run(
                ["docker", "compose", "-f", "docker-compose.yml", "-f", str(overlay),
                 "config"],
                cwd=str(REPO), capture_output=True, text=True, timeout=180, env=env)
        except (OSError, subprocess.TimeoutExpired) as error:
            check("compose renders the pinned images and no build section", False, str(error))
            return
        rendered = proc.stdout
        ok = proc.returncode == 0
        sections = {}
        current = None
        for raw in rendered.splitlines():
            if re.match(r"^  [a-z0-9-]+:$", raw):
                current = raw.strip().rstrip(":")
            elif current and re.match(r"^    (image|build):", raw):
                sections.setdefault(current, []).append(raw.strip())
        for service in ("backend", "celery-worker", "celery-beat", "frontend"):
            found = " ".join(sections.get(service, []))
            ok = ok and f"image: ghcr.io/mrmap-community/{('mrmap-frontend' if service == 'frontend' else 'mrmap-backend')}:0.2.0@" in found \
                and "build:" not in found
        check("compose renders the pinned images and no build section", ok,
              f"rc={proc.returncode} {proc.stderr.strip()[:200]} sections={sections}")


def main():
    try:
        if not (REPO / "docker-compose.yml").exists():
            raise RuntimeError("run from the repository root (no docker-compose.yml found)")
        tag_policy_checks()
        label_checks()
        live_repo_checks()
        manifest_checks()
        promote_checks()
        inspect_parsing_checks()
        verify_checks()
        cli_checks()
        compose_checks()
    except Exception as error:  # noqa: BLE001 - harness failure, not a check
        print(f"harness: {error}", file=sys.stderr)
        return 2

    width = max((len(name) for name, _, _ in RESULTS), default=0)
    failed = [(name, detail) for name, ok, detail in RESULTS if not ok]
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name:<{width}}"
        if not ok and detail:
            line += f"   <- {detail}"
        elif detail and "skipped" in detail:
            line += f"   ({detail})"
        print(line)
    if failed:
        print(f"FAILED ({len(failed)} of {len(RESULTS)} checks)", file=sys.stderr)
        return 1
    print(f"OK ({len(RESULTS)} checks)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
