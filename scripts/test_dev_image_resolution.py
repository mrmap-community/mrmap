#!/usr/bin/env python3
"""Offline tests for scripts/dev_image_id.py - the #962 resolver (#959 wave).

Run from the repository root:  python3 scripts/test_dev_image_resolution.py
Needs no network and no gh. Needs the local docker CLI and daemon for the
resolver integration cases; they are SKIPPED (not failed) when docker is
unavailable, so the pure-offline half always runs. Nothing is pulled from any
registry: fake tags live in the unroutable `localhost:1/...` namespace and the
fake images are built from `scratch`/the local `alpine` image. The live
"never published" check against ghcr.io is opt-in via MRMAP_TEST_LIVE=1.

Exit code 0 = all ran checks passed.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_spec = importlib.util.spec_from_file_location("dev_image_id", SCRIPTS / "dev_image_id.py")
dev_image_id = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev_image_id)

RESULTS = []
FAKE_TAGS = []  # exact names to remove at the end, never anything else


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def docker(*args, timeout=300):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=timeout)


def docker_available():
    try:
        return docker("version").returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def build_fake(ref, dockerfile, build_args=(), platform=None):
    cmd = ["build", "-q", "-t", ref]
    for arg in build_args:
        cmd += ["--build-arg", arg]
    if platform:
        cmd += ["--platform", platform]
    cmd += ["-f", "-", str(ROOT)]
    proc = subprocess.run(["docker", *cmd], input=dockerfile,
                          capture_output=True, text=True, timeout=600)
    if proc.returncode == 0:
        FAKE_TAGS.append(ref)
    return proc


def run_resolver(*args, env_extra=None):
    env = dict(os.environ)
    env.pop("MRMAP_ALLOW_MUTABLE_DEV_IMAGE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "dev_image_id.py"), *args],
        capture_output=True, text=True, timeout=900, cwd=ROOT, env=env)


def teardown():
    for tag in FAKE_TAGS:
        docker("rmi", tag)


# ---------------------------------------------------------------- unit half
def unit_checks():
    cases = [
        ("Error response from daemon: pull access denied for ghcr.io/mrmap-community/"
         "mrmap-backend-dev, repository does not exist or may require 'docker login': "
         "denied: requested access to the resource is denied", "miss"),
        ("failed to resolve reference docker.io/x/y: failed to do request: "
         "http: server gave an HTTP response to HTTPS client", "transient"),
        ("error getting credentials - err: exit status 1", "unknown"),
        ("failed to copy: read tcp 10.0.0.2:45678->140.82.113.10:443: i/o timeout",
         "transient"),
        ("no match for platform in manifest: not found", "platform"),
    ]
    for text, want in cases:
        got = dev_image_id.classify_pull_failure(text)
        check(f"classifier: {want:<9} for {text.split(chr(10))[0][:48]!r}",
              got == want, f"got {got}")

    cmd_b = " ".join(dev_image_id.local_build_command(ROOT, "backend", "ref:1", "fp"))
    check("backend fallback build uses the workflow's context/Dockerfile/build-args",
          all(part in cmd_b for part in
              ("docker build", "-f", str(ROOT / "docker/backend/alpine.Dockerfile"),
               "--build-arg MRMAP_PRODUCTION=False", "-t ref:1", str(ROOT / "backend"))),
          cmd_b)
    cmd_f = " ".join(dev_image_id.local_build_command(ROOT, "frontend", "ref:1", "deadbeefcafe"))
    check("frontend fallback build stamps MRMAP_IMAGE_FP",
          "--build-arg MRMAP_IMAGE_FP=deadbeefcafe" in cmd_f
          and str(ROOT / "docker/frontend/tests.Dockerfile") in cmd_f, cmd_f)

    # The host --deps-marker must agree with the container shell formula
    # byte-for-byte (the sync contract with #963). Run the shell pipeline.
    shell = ("{ cat package.json package-lock.json; printf 'v26.13.0\\n'; "
             "printf '11.20.0\\n'; } | sha256sum | cut -d ' ' -f1 | cut -c1-12")
    try:
        proc = subprocess.run(["sh", "-c", shell], capture_output=True, text=True,
                              timeout=30, cwd=ROOT / "frontend")
    except FileNotFoundError:
        proc = None
    if proc is not None and proc.returncode == 0:
        host = dev_image_id.deps_marker(ROOT, "v26.13.0", "11.20.0")
        check("host deps marker == container sha256sum pipeline",
              host == proc.stdout.strip(), f"host {host} vs shell {proc.stdout.strip()}")
    else:
        check("host deps marker == container sha256sum pipeline", False,
              "host sha256sum unavailable")


# ----------------------------------------------------------- integration half
def docker_checks():
    scratch = "FROM scratch\n"

    # hit: a fake fp-tagged image in the unroutable localhost:1 namespace
    fp = dev_image_id.fingerprint(ROOT, "backend")
    hit_ref = f"localhost:1/mrmap-962-test/mrmap-backend-dev:{fp}"
    proc = build_fake(hit_ref, scratch)
    if proc.returncode != 0:
        check("scratch fake image builds", False, proc.stderr[-300:])
        return
    check("scratch fake image builds", True)
    res = run_resolver("--resolve", "--image", "backend", "--repo",
                       "localhost:1/mrmap-962-test/mrmap-backend-dev")
    check("resolver exits 0 on a local hit", res.returncode == 0,
          f"rc={res.returncode} {res.stderr[-300:]}")
    check("hit resolves without registry noise", res.stdout.strip() == fp,
          f"stdout={res.stdout.strip()!r} fp={fp}")
    check("hit is reported on stderr", "local hit" in res.stderr)

    # platform mismatch: arm64 scratch on an amd64 host (daemon platform read
    # from `docker version`); skipped when the host IS arm64 or when the fake
    # cross-arch image does not carry a foreign Architecture in its metadata.
    host_platform = dev_image_id.host_platform()
    fp_id = None
    ins = docker("image", "inspect", hit_ref, "--format", "{{.Id}}")
    if ins.returncode == 0:
        fp_id = ins.stdout.strip()
    if host_platform == "linux/amd64":
        pf_ref = "localhost:1/mrmap-962-test/mrmap-backend-dev:arm64-fake"
        proc = build_fake(pf_ref, scratch, platform="linux/arm64")
        arch = docker("image", "inspect", pf_ref, "--format", "{{.Architecture}}").stdout.strip()
        if proc.returncode != 0:
            print("SKIP  platform mismatch case (cross-arch scratch build unsupported)")
        elif arch != "arm64":
            print(f"SKIP  platform mismatch case (fake image reports {arch!r})")
        else:
            docker("tag", pf_ref, hit_ref)  # the fp tag now holds foreign-platform content
            res = run_resolver("--resolve", "--image", "backend", "--repo",
                               "localhost:1/mrmap-962-test/mrmap-backend-dev")
            check("platform mismatch fails loudly with exit 5",
                  res.returncode == dev_image_id.EXIT_PLATFORM,
                  f"rc={res.returncode} {res.stderr[-200:]}")
            if fp_id:
                docker("tag", fp_id, hit_ref)  # restore the good hit for later cases
            docker("rmi", pf_ref)
            FAKE_TAGS.remove(pf_ref)
    else:
        print("SKIP  platform mismatch case (host is not linux/amd64)")

    # frontend content stamp: matching, missing, mismatching
    base_fp = dev_image_id.fingerprint(ROOT, "frontend")
    stamp_dockerfile = (
        "FROM alpine:latest\n"
        "ARG MRMAP_IMAGE_FP=unset\n"
        "RUN mkdir -p /opt/frontend-deps && printf '%s\\n' \"$MRMAP_IMAGE_FP\" "
        "> /opt/frontend-deps/.mrmap-image-fp\n")
    repo = "localhost:1/mrmap-962-test/mrmap-frontend-dev"

    ok_ref = f"{repo}:{base_fp}"
    proc = build_fake(ok_ref, stamp_dockerfile, build_args=[f"MRMAP_IMAGE_FP={base_fp}"])
    check("stamp fake image builds", proc.returncode == 0, proc.stderr[-300:])
    res = run_resolver("--resolve", "--image", "frontend", "--repo", repo)
    check("frontend hit with matching stamp exits 0", res.returncode == 0,
          f"rc={res.returncode} {res.stderr[-200:]}")

    bad_ref = f"{repo}:111111111111"
    proc = build_fake(bad_ref, stamp_dockerfile, build_args=["MRMAP_IMAGE_FP=222222222222"])
    if proc.returncode == 0:
        # tag it under the real fp name too: a foreign-content tag
        if docker("tag", bad_ref, f"{repo}:{base_fp}").returncode == 0:
            FAKE_TAGS.append(f"{repo}:{base_fp}")
            docker("rmi", bad_ref)
            FAKE_TAGS.remove(bad_ref)
            res = run_resolver("--resolve", "--image", "frontend", "--repo", repo)
            check("foreign-stamped tag is rejected with exit 7",
                  res.returncode == dev_image_id.EXIT_STAMP_MISMATCH,
                  f"rc={res.returncode} {res.stderr[-300:]}")
            docker("rmi", f"{repo}:{base_fp}")
            FAKE_TAGS.remove(f"{repo}:{base_fp}")
        # restore the good tag for later cases
        build_fake(ok_ref, stamp_dockerfile, build_args=[f"MRMAP_IMAGE_FP={base_fp}"])

    # transient: unreachable registry, nothing published, exit code for retry
    res = run_resolver("--resolve", "--image", "backend", "--repo",
                       "localhost:1/does-not-resolve/mrmap-backend-dev")
    check("unreachable registry is TRANSIENT with exit 4",
          res.returncode == dev_image_id.EXIT_TRANSIENT,
          f"rc={res.returncode} {res.stderr[-300:]}")
    check("transient message tells about retry and --build",
          "TRANSIENT" in res.stderr and "--build" in res.stderr)

    # miss classification against a live registry is opt-in
    if os.environ.get("MRMAP_TEST_LIVE") == "1":
        res = run_resolver("--resolve", "--image", "backend", "--repo",
                           "ghcr.io/mrmap-community/mrmap-backend-dev-does-not-exist-962")
        check("live registry miss exits 3 with actionable fallbacks",
              res.returncode == dev_image_id.EXIT_MISS
              and "NO IMAGE FOR THIS CHECKOUT" in res.stderr
              and "build locally" in res.stderr.replace("build locally under", "build locally")
              and "dev-images.yml" in res.stderr,
              f"rc={res.returncode} {res.stderr[-400:]}")
    else:
        print("SKIP  live ghcr miss case (set MRMAP_TEST_LIVE=1)")

    # opt-out env var: exits 0 loudly without touching docker at all
    res = run_resolver("--resolve", "--image", "backend", "--repo",
                       "localhost:1/does-not-resolve/mrmap-backend-dev",
                       env_extra={"MRMAP_ALLOW_MUTABLE_DEV_IMAGE": "1"})
    check("opt-out env exits 0 and shouts about mutable images",
          res.returncode == 0 and "OPT-OUT ACTIVE" in res.stderr,
          f"rc={res.returncode} {res.stderr[-200:]}")

    # dry run never touches docker
    res = run_resolver("--resolve", "--image", "frontend", "--dry-run")
    check("--dry-run exits 0 and prints the fp",
          res.returncode == 0 and res.stdout.strip() == base_fp,
          f"rc={res.returncode} stdout={res.stdout.strip()!r}")

    # concurrent resolvers on the same fp agree and corrupt nothing
    procs = []
    for _ in range(3):
        procs.append(subprocess.Popen(
            [sys.executable, str(SCRIPTS / "dev_image_id.py"),
             "--resolve", "--image", "backend", "--repo",
             "localhost:1/mrmap-962-test/mrmap-backend-dev"],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    outs = [(p.wait(), p.stdout.read().strip()) for p in procs]
    check("3 concurrent resolver runs all exit 0 on the shared fp tag",
          all(rc == 0 for rc, _ in outs) and all(o == fp for _, o in outs),
          str(outs))


def main():
    print(f"dev_image_id resolver tests on {ROOT}")
    unit_checks()
    if docker_available():
        docker_checks()
    else:
        print("SKIP  all docker integration cases (docker CLI/daemon unavailable)")

    teardown()
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
