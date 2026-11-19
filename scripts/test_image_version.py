#!/usr/bin/env python3
"""Versioned app images guard (#1582): identity, tag policy, deployment coherence.

Run from the repository root:  python3 scripts/test_image_version.py
Standard library only, no docker, no network. Exit 0 = every check passed,
1 = a check failed, 2 = the harness itself could not run.

Why this guard exists
---------------------
#1582 turns the four build-only compose services (backend, celery-worker,
celery-beat, frontend) into versioned artifacts: OCI identity labels from
the canonical VERSION and the exact commit (#1579), a channel-gated tag
policy where no dev or RC build can ever touch a stable name, one build
promoted by digest, and a deployment overlay that pins a coherent image
set. Every one of those rules lives in scripts/image_version.py and in a
file this suite can read - a Dockerfile stage, a compose target, a workflow
step. The failure mode refused here is the silent one: a rule that survives
only in someone's head, a build path that forgot the new stage target and
quietly builds the app artifact as the dependency image, or a deployment
overlay that rebinds the checkout over the baked code (the #922/#1027
stale-shadow lesson, relocated to /opt/mrmap).

What it checks
--------------
1. The rules themselves: image_version.self_check() - tag derivation per
   channel, the guard's exact-equality, the rolling-alias approval gate,
   label and build-arg derivation, the env and overlay coherence rules -
   on throw-away fixtures, no git, no docker, no network.
2. The live repository: the deploy/ surface passes its own coherence check;
   every compose build path of docker/backend/alpine.Dockerfile pins the
   runtime-image target (the production-image stage of #1582 is the LAST
   stage, so any path that forgot the target would build the application
   artifact as the dependency image); dev-images.yml pins the same target
   and stays the only publisher of the dependency images; the fallback
   build of scripts/dev_image_id.py carries the target; the Dockerfiles
   carry the identity ARGs, the labels and the backend's refuse rule; the
   workflow wiring is as claimed: the PR path never pushes, every push job
   needs the identity job that ran the guard, and no job can name a rolling
   alias.
3. A deliberately mismatched copy of the deployment surface (a split tag
   variable, a floating tag, a re-added checkout mount): the coherence
   check must refuse it - the "mismatched versions" scenario of the issue,
   offline and deterministic.
"""

import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import image_version as iv  # noqa: E402
import dev_image_id  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def build_blocks(text, dockerfile_part):
    """{service: build-block} for services whose build: uses the fragment."""
    hits = {}
    for name, block in iv._service_blocks(text).items():
        build = re.search(r"^    build:\n((?:^      .*\n?)*)", block,
                          re.MULTILINE)
        if build and dockerfile_part in build.group(1):
            hits[name] = build.group(1)
    return hits


def replace_in_service(text, service, old, new):
    """Replace old with new inside one service block of a compose file."""
    lines = text.splitlines(keepends=True)
    out, inside, replaced = [], None, False
    for line in lines:
        match = re.match(r"^  ([A-Za-z0-9_-]+):", line)
        if match:
            inside = match.group(1) == service and not replaced
        if inside and old in line:
            line = line.replace(old, new)
            replaced = True
        out.append(line)
    return "".join(out), replaced


def main():
    try:
        # ---- 1. the rules themselves ------------------------------------
        print("image_version self-check (tag policy, guard, deploy rules):")
        rc = iv.self_check()
        check("image_version.self_check() is green", rc == 0, f"exit {rc}")

        # ---- 2. the live repository wiring -----------------------------
        alpine = (REPO / "docker/backend/alpine.Dockerfile").read_text(
            encoding="utf-8")
        check("backend Dockerfile keeps the dev runtime stage and adds the "
              "production stage on top",
              "AS runtime-image" in alpine
              and "FROM runtime-image AS production-image" in alpine
              and alpine.index("FROM runtime-image AS production-image")
              > alpine.index("AS runtime-image"))
        prod_stage = alpine.split("AS production-image", 1)[-1]
        check("the production stage takes the identity args and labels them",
              all(part in prod_stage for part in (
                  'ARG MRMAP_VERSION=""', 'ARG MRMAP_REVISION=""',
                  'ARG MRMAP_SOURCE=', 'ARG MRMAP_CHANNEL="dev"',
                  "org.opencontainers.image.version=",
                  "org.opencontainers.image.revision=",
                  "org.opencontainers.image.source=",
              )))
        check("the production stage refuses to build without version and "
              "exact revision",
              "MRMAP_VERSION" in prod_stage
              and "MRMAP_REVISION" in prod_stage
              and "grep -Eq" in prod_stage
              and "[0-9a-f]{40}" in prod_stage)
        check("the production stage bakes the code the checkout model bind-"
              "mounts", "COPY --chown=mrmapuser:mrmapgroup . /opt/mrmap"
              in prod_stage)

        nginx = (REPO / "docker/nginx/nginx.Dockerfile").read_text(
            encoding="utf-8")
        check("frontend image labels the identity and bakes the nginx conf "
              "(deployment without a checkout, #1582)",
              all(part in nginx for part in (
                  'ARG MRMAP_VERSION=""', 'ARG MRMAP_REVISION=""',
                  'ARG MRMAP_SOURCE=',
                  "org.opencontainers.image.version=",
                  "org.opencontainers.image.revision=",
                  "org.opencontainers.image.source=",
                  "COPY docker/nginx/mrmap.conf /etc/nginx/conf.d/default.conf",
              )))

        # Every compose build path of the shared backend Dockerfile must pin
        # the dev target now that the LAST stage is the application artifact.
        for compose_name in ("docker-compose.yml", "docker-compose.dev.yml"):
            text = (REPO / compose_name).read_text(encoding="utf-8")
            builders = build_blocks(text, "alpine.Dockerfile")
            check(f"{compose_name}: found alpine.Dockerfile build sections "
                  f"({len(builders)})", len(builders) >= 1)
            for service, build_block in sorted(builders.items()):
                check(f"{compose_name}: {service} pins target runtime-image",
                      "target: runtime-image" in build_block, build_block)

        dev_workflow = (REPO / ".github/workflows/dev-images.yml").read_text(
            encoding="utf-8")
        check("dev-images.yml pins both backend builds to runtime-image "
              "(the dependency image stays the dependency image)",
              dev_workflow.count("target: runtime-image") == 2
              and "production-image" not in dev_workflow)
        check("dev-images.yml still fingerprints through dev_image_id.py "
              "(the prebuilt dev cache contract of #959 is untouched)",
              "scripts/dev_image_id.py" in dev_workflow
              and "--print-build-args" in dev_workflow)

        cmd_b = dev_image_id.local_build_command(REPO, "backend", "ref:1", "fp")
        check("dev_image_id fallback build pins the runtime-image target",
              "--target" in cmd_b and "runtime-image" in cmd_b,
              " ".join(cmd_b))

        app_workflow = REPO / ".github/workflows/app-images.yml"
        check("app-images.yml exists (the versioned build of #1582)",
              app_workflow.is_file())
        if app_workflow.is_file():
            wf = app_workflow.read_text(encoding="utf-8")
            jobs = iv._service_blocks(wf.split("jobs:\n", 1)[1])
            pushers = sorted(name for name, body in jobs.items()
                             if re.search(r"^\s+push:\s*true", body,
                                          re.MULTILINE))
            builders = sorted(name for name, body in jobs.items()
                              if "docker/build-push-action" in body)
            check("every push:true build job needs the image-identity job",
                  bool(pushers) and all(
                      "needs:" in jobs[name] and "image-identity" in jobs[name]
                      for name in pushers),
                  f"pushers: {pushers}")
            check("the guard runs in the identity job that gates every push",
                  "--guard" in wf and bool(pushers))
            check("build jobs exist that cannot push (PR build-proof)",
                  any(name not in pushers for name in builders),
                  f"builders: {builders}, pushers: {pushers}")
            check("no application image reference in the workflow is a "
                  "rolling alias",
                  not re.search(r"mrmap-(backend|frontend):latest", wf)
                  and ":main" not in wf.split("jobs:", 1)[1])
            check("the workflow never opts out of immutable dev image tags "
                  "(MRMAP_ALLOW_MUTABLE_DEV_IMAGE is human-only)",
                  "MRMAP_ALLOW_MUTABLE_DEV_IMAGE" not in wf)
            check("the backend artifact build targets the production stage",
                  "target: production-image" in wf)
            check("registry pushes are triggered by master/dispatch/call "
                  "only (the dev-images discipline; develop stays "
                  "build-proof)",
                  re.search(r"push:\s*\n\s+branches:\s*\[master\]", wf)
                  is not None)

        # ---- 3. the deployment surface, and its sabotage ---------------
        problems = iv.check_deploy(REPO)
        check("the committed deployment surface is coherent (deploy/ + "
              "third-party pins + no secrets)", problems == [],
              "; ".join(problems))

        m = iv.manifest(REPO, revision="0" * 40, channel="dev")
        check("manifest names both application images and the third-party set",
              set(m["images"]) == {"mrmap-backend", "mrmap-frontend"}
              and len(m["third_party"]) >= 7
              and m["images"]["mrmap-backend"]["repository"].endswith(
                  "mrmap-backend"))
        check("manifest services are exactly the compose services that build "
              "today",
              m["images"]["mrmap-backend"]["services"]
              == ["backend", "celery-worker", "celery-beat"]
              and m["images"]["mrmap-frontend"]["services"] == ["frontend"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "deploy").mkdir()
            deploy_file = root / "deploy/docker-compose.images.yml"
            good_overlay = (REPO / "deploy/docker-compose.images.yml"
                            ).read_text(encoding="utf-8")
            deploy_file.write_text(good_overlay, encoding="utf-8")
            shutil.copy(REPO / "deploy/images.env.example",
                        root / "deploy/images.env.example")
            shutil.copy(REPO / "docker-compose.yml", root / "docker-compose.yml")

            # mismatch a: two services, two tag variables, two versions
            split, done = replace_in_service(
                good_overlay, "frontend", "MRMAP_IMAGE_TAG",
                "MRMAP_FRONTEND_TAG")
            deploy_file.write_text(split, encoding="utf-8")
            check("sabotage setup (split tag variable) applied", done)
            found = any("MRMAP_FRONTEND_TAG" in p
                        or "one tag variable" in p
                        for p in iv.check_deploy(root))
            check("coherence check refuses a split tag variable set", found)

            # mismatch b: the checkout rebinds itself over the baked code
            bound, done = replace_in_service(
                good_overlay, "backend", "    volumes: !override\n",
                "    volumes: !override\n      - type: bind\n"
                "        source: ./backend\n        target: /opt/mrmap\n")
            check("sabotage setup (checkout bind) applied", done)
            deploy_file.write_text(bound, encoding="utf-8")
            found = any("./backend" in p for p in iv.check_deploy(root))
            check("coherence check refuses a checkout bind over the baked "
                  "artifact", found)

            # mismatch c: a floating, then a half-shaped, then a good tag
            deploy_file.write_text(good_overlay, encoding="utf-8")
            (root / "deploy/mismatch.env").write_text(
                "MRMAP_IMAGE_TAG=1.0\n", encoding="utf-8")
            check("a half-version deployment tag is refused",
                  iv.check_env_file(root / "deploy/mismatch.env") != [])
            (root / "deploy/mismatch.env").write_text(
                "MRMAP_IMAGE_TAG=0.2.0-rc.1\n", encoding="utf-8")
            check("a prerelease deployment tag is deployable (the channel "
                  "rule gates publishing, not running)",
                  iv.check_env_file(root / "deploy/mismatch.env") == [])

        # ---- 4. docs and the shared version source ----------------------
        doc = REPO / "docs/source/development/versioned-images.rst"
        check("the versioned-images doc exists", doc.is_file())
        index = (REPO / "docs/source/development/index.rst").read_text(
            encoding="utf-8")
        check("the doc is in the development toctree",
              "versioned-images" in index)

        try:
            iv.read_version(REPO)
            check("the canonical VERSION validates for image identity", True)
        except iv.IdentityError as error:
            check("the canonical VERSION validates for image identity", False,
                  str(error))
    except Exception as error:  # a harness failure, not a check failure
        print(f"test_image_version: harness could not run: {error!r}",
              file=sys.stderr)
        return 2

    failed = [r for r in RESULTS if not r[1]]
    for name, ok, detail in RESULTS:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}"
              + (f"\n        {detail}" if detail and not ok else ""))
    print(f"test_image_version: {len(RESULTS) - len(failed)} of "
          f"{len(RESULTS)} checks passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
