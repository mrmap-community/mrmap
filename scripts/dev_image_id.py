#!/usr/bin/env python3
"""dev_image_id: fingerprint of the dependency inputs of a mrmap dev image.

Host-side tool carried by this repository; run it as `python3
scripts/dev_image_id.py` from the repository root. Standard library only and
entirely local - it reads the checkout and opens no network connection, so CI
and every agent worktree derive the same value from the same tree.

It prints the first 12 hex digits of the sha256 over a canonical, sorted
manifest of the inputs a development image's layers depend on (the
integration contract of epic #959):

  * docker/backend/alpine.Dockerfile (whole file, hashed)
  * every file under backend/.requirements/
  * the build args the image is built with
  * the FROM base image references the Dockerfile pins

Source-code-only changes are not in the manifest, so they never change the
fingerprint; dependency, Dockerfile or build-arg changes always do. That makes
the fingerprint a safe immutable image tag (`ghcr.io/mrmap-community/
mrmap-backend-dev:<fp>`) for prebuilt dev/test images.

The FROM references are the base references as the Dockerfile pins them: an
exact version tag is already the resolved reference, and resolving to a digest
would need the network, which this tool never uses. Renaming a FROM line
changes the Dockerfile hash anyway, so the manifest covers it either way.

Usage:
  python3 scripts/dev_image_id.py
                  print the fingerprint of the backend dev/test image
  python3 scripts/dev_image_id.py --print-build-args
                  print the docker build args the fingerprint assumes, so the
                  CI workflow and agent tooling cannot drift from them
  python3 scripts/dev_image_id.py --self-check
                  verify on a throwaway tree in /tmp: the fingerprint is
                  stable across runs, an edited or added requirements .txt
                  changes it, and a source-file change does not
"""

import argparse
import hashlib
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Single source of truth for the build args of the published backend dev/test
# image: docker-compose.dev.yml passes the same value to the shared
# Dockerfile. CI reads them through --print-build-args instead of repeating
# them, so the args the fingerprint covers are the args the image is built by.
BACKEND_DEV_BUILD_ARGS = {"MRMAP_PRODUCTION": "False"}

BACKEND_DOCKERFILE = "docker/backend/alpine.Dockerfile"
BACKEND_REQUIREMENTS_DIR = "backend/.requirements"

# Versioned manifest format tag, so a later extension of this script (the
# frontend image of #962/#963 adds its own inputs under its own image name)
# can change the layout without silently colliding with backend fingerprints.
MANIFEST_FORMAT = "mrmap-dev-image-manifest/1"


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
    for dependency_file in dependency_files:
        digest = hashlib.sha256(dependency_file.read_bytes()).hexdigest()
        lines.append(f"file {dependency_file.relative_to(root)} sha256={digest}")
    for name, value in BACKEND_DEV_BUILD_ARGS.items():
        lines.append(f"build-arg {name}={value}")
    for ref in _from_references(dockerfile):
        lines.append(f"from {ref}")
    return "\n".join(sorted(lines)) + "\n"


def fingerprint(root):
    """The 12-hex dependency fingerprint of the backend dev/test image."""
    manifest = backend_manifest(root)
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()[:12]


def print_build_args():
    return ",".join(f"{name}={value}" for name, value in sorted(BACKEND_DEV_BUILD_ARGS.items()))


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
        source = work / "backend" / "MrMap" / "settings.py"
        source.parent.mkdir(parents=True)
        source.write_text("# original source content\n")

        fp = fingerprint(work)
        results.append(("fingerprint is 12 lowercase hex digits",
                        re.fullmatch(r"[0-9a-f]{12}", fp) is not None))
        results.append(("deterministic across repeated runs", fingerprint(work) == fp))

        (requirements / "selfcheck.txt").write_text("pinned-dep==1.2.3\n")
        results.append(("added requirements .txt changes the fingerprint",
                        fingerprint(work) != fp))
        (requirements / "selfcheck.txt").unlink()

        base = requirements / "base.txt"
        base_backup = base.read_text()
        base.write_text(base_backup + "\n# touched by self-check\n")
        results.append(("touched requirements .txt changes the fingerprint",
                        fingerprint(work) != fp))
        base.write_text(base_backup)

        source.write_text("# changed application source only\n")
        results.append(("source-file change keeps the fingerprint",
                        fingerprint(work) == fp))

    width = max(len(name) for name, _ in results)
    failed = [name for name, ok in results if not ok]
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}")
    if failed:
        print(f"self-check FAILED ({len(failed)} of {len(results)} checks)", file=sys.stderr)
        return 1
    print(f"self-check OK ({len(results)} checks) on a copy of {root}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="fingerprint the dependency inputs of a mrmap dev image"
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1],
                        help="checkout to read (defaults to the repository holding this script)")
    parser.add_argument("--print-build-args", action="store_true",
                        help="print the docker build args the fingerprint "
                        "assumes instead of the fingerprint")
    parser.add_argument("--self-check", action="store_true",
                        help="verify fingerprint determinism and input "
                        "sensitivity on a throwaway tree")
    args = parser.parse_args(argv)

    if args.self_check:
        return self_check(args.repo_root.resolve())
    if args.print_build_args:
        print(print_build_args())
        return 0
    print(fingerprint(args.repo_root.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
