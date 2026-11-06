#!/usr/bin/env python3
"""dev_image_gate: does CI still need to build a dev image for this checkout?

Host-side tool carried by this repository and read by
``.github/workflows/dev-images.yml`` (issue #1057). Run it as `python3
scripts/dev_image_gate.py` from the repository root, once per image, in the
pull_request / merge_group validation jobs. It is stdlib-only and itself
builds nothing, pushes nothing and logs into no registry; the only registry
contact it causes is the resolver's own read-only pull probe (and where there
is no docker CLI, the probe cannot answer and CI builds).

Why a gate at all: the dependency fingerprint of ``scripts/dev_image_id.py`` is
a hash of exactly the inputs an image is built from - the requirements files
or lockfiles, the Dockerfile (and the frontend entrypoint), the build args and
the resolved ``FROM`` base references. A pull request whose fingerprint is
ALREADY published therefore asks for an image that exists, immutable, in the
registry: rebuilding it proves nothing new and costs the merge queue minutes.
Source-only changes never move a fingerprint, so they are the common case.

The probe IS the documented resolver - one call, no reimplementation of
registry logic here::

    python3 scripts/dev_image_id.py --resolve --image <image>

WITHOUT ``--build``, so a validation run never builds and never pushes; its
exit 0 can then only mean "this fp tag is published and pulled intact".

The cheaper probe exists and is deliberately not used here.
``scripts/dev_image_id.py --exists`` answers "is this tag published?" in about
0.4 s against the 38 s that one cold pull costs (measured 2026-11-05, issue
#1077), so it is the right tool for an agent's pre-flight and for anyone
asking about a name. It is not the right tool for a gate that decides whether a
build still proves something: an unchanged pull request whose published image
arrives broken is exactly what this build validates, and a manifest answer
cannot see broken bytes. Swapping ``--exists`` in here would be a one-word
change that quietly changes what ``needs_build=false`` means, so if this ever
changes, the change has to say what the build then validates.

The decision is one-sided on purpose. Only exit 0 skips the build:

    0  -> needs_build=false  published and pulled intact, nothing to prove
    3  -> needs_build=true   never published: this checkout changed a
                             dependency input, so the build IS the validation
    4  -> needs_build=true   transient failure, or a private package refusing
                             anonymous inspection - "unchanged" and "could not
                             look" are indistinguishable here, so build
    5  -> needs_build=true   the tag exists but not for this platform
    6  -> needs_build=true   the resolver reported a failed build
    7  -> needs_build=true   the tag carries content that is not its own
    any other / no answer -> needs_build=true

Treating 4 (or a hang, or a missing docker CLI) as "unchanged" would silently
drop a build that is really needed and would let a broken Dockerfile through;
the cost of the other direction is one unnecessary build, so the gate fails
towards building.

Output is for ``$GITHUB_OUTPUT``: ``needs_build`` (``true``/``false``),
``probe_rc`` and a one-line ``reason``. The lines go to stdout and, when
``GITHUB_OUTPUT`` is set, are appended to that file as well; diagnostics go to
stderr, which is the convention of the resolver.

The gate sits inside a job whose status the merge queue waits for, so two of its
properties matter more than the decision itself:

*   It always exits 0. A step that fails reddens ``backend-dev-build``, which
    blocks every pull request - the gate would then be the reason the queue
    stops, for a tool whose whole job is to save minutes. An unexpected failure
    is reported as ``needs_build=true`` and printed, not raised.
*   Its consumers ask ``needs_build != 'false'``, not ``== 'true'``. An output
    that never arrived (crash before the write, an unwritable ``$GITHUB_OUTPUT``)
    reads as "not false", so the build runs. Only a gate that positively answered
    "published, pulled intact" may skip work.

Usage
  python3 scripts/dev_image_gate.py [--image backend] [--repo-root PATH]

Exit codes
  0  always: a decision was made and printed, or the gate failed and said so
  2  usage error (argparse, before any decision is expected)
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
DEFAULT_ROOT = SCRIPTS.parent

_spec = importlib.util.spec_from_file_location("dev_image_id", SCRIPTS / "dev_image_id.py")
dev_image_id = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dev_image_id)

# Outer guard only: the resolver already caps every docker call it makes, this
# keeps a stuck daemon from eating the whole CI job. Exceeding it is "no
# answer", which means build.
PROBE_TIMEOUT_S = dev_image_id.DOCKER_PULL_TIMEOUT_S + 300

# Set by GitHub Actions when a step may record outputs; also honoured by hand
# runs, which is what makes the offline test able to check the wiring.
GITHUB_OUTPUT_ENV = "GITHUB_OUTPUT"


def probe_command(root, image, probe_argv=None):
    """The probe argv: the repository's own resolver, no ``--build``.

    ``probe_argv`` replaces only the interpreter-and-script part; it exists for
    the offline test, which cannot ask the real resolver to answer with a
    specific exit code without docker or the network.
    """
    argv = list(probe_argv) if probe_argv else [sys.executable, str(root / "scripts" / "dev_image_id.py")]
    return argv + ["--resolve", "--image", image]


def probe_env():
    """The environment of the probe: the resolver's opt-out must not reach it.

    ``MRMAP_ALLOW_MUTABLE_DEV_IMAGE=1`` makes the resolver exit 0 without ever
    looking at the registry. Read as "already published" that would skip a
    needed build on a human's machine, so the gate clears it - the same way the
    resolver tests do.
    """
    env = dict(os.environ)
    env.pop(dev_image_id.MUTABLE_OPT_OUT_ENV, None)
    return env


def decision_for(rc):
    """Map one resolver exit code onto ``(needs_build, reason)``."""
    if rc == dev_image_id.EXIT_OK:
        return False, ("this fingerprint is published and pulled intact, the build "
                       "would rebuild bytes that are already immutable")
    if rc == dev_image_id.EXIT_MISS:
        return True, ("no published image for this fingerprint yet (exit 3): a dependency input "
                      "changed here, so this build is the validation")
    if rc == dev_image_id.EXIT_TRANSIENT:
        return True, ("exit 4: transient registry failure or anonymous inspection denied - "
                      "not published and unchanged cannot be told apart, so build")
    if rc == dev_image_id.EXIT_PLATFORM:
        return True, ("exit 5: the published image is not for this platform; building here is "
                      "what proves the Dockerfile works")
    if rc == dev_image_id.EXIT_BUILD_FAILED:
        return True, "exit 6: the resolver reported a failed build; run it in CI where it can be read"
    if rc == dev_image_id.EXIT_STAMP_MISMATCH:
        return True, ("exit 7: the tag carries content that does not match its own name, so it "
                      "proves nothing about this checkout")
    return True, f"the probe answered with exit code {rc}, which is not a published image"


def run_probe(argv, root, timeout=PROBE_TIMEOUT_S):
    """Run the probe; returns ``(rc, stderr)`` with rc None when it could not run."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True,
                              cwd=str(root), env=probe_env(), timeout=timeout)
    except OSError as exc:
        return None, f"dev_image_gate: the probe could not run: {exc}"
    except subprocess.TimeoutExpired:
        return None, f"dev_image_gate: the probe did not answer within {timeout}s"
    return proc.returncode, proc.stderr


def emit(outputs, github_output=None):
    """Print the output lines; append them to ``$GITHUB_OUTPUT`` when it is set.

    The file write is the part that can fail on a runner (a full disk, a file
    another step holds open), and failing here would mean no output at all. That is
    survivable *because* the workflow asks ``!= 'false'``: no output means the build
    runs. So the line still goes to stdout, the problem goes to stderr, and the
    process still reports a decision.
    """
    lines = "".join(f"{name}={str(value).replace(chr(10), ' ')}\n" for name, value in outputs.items())
    sys.stdout.write(lines)
    if github_output:
        try:
            with open(github_output, "a", encoding="utf-8") as handle:
                handle.write(lines)
        except OSError as exc:
            sys.stderr.write(f"dev_image_gate: could not append to $GITHUB_OUTPUT: {exc}\n")
            sys.stderr.write("dev_image_gate: the step conditions treat a missing output as "
                             "'build', which is the safe reading\n")


def decide(args):
    """The whole question, as ``(needs_build, reason, probe_rc)``."""
    root = args.repo_root.resolve()
    command = probe_command(root, args.image, args.probe_argv)
    rc, diagnostics = run_probe(command, root)
    if diagnostics:
        sys.stderr.write(diagnostics if diagnostics.endswith("\n") else diagnostics + "\n")
    if rc is None:
        return (True, "the probe did not answer; an inconclusive probe never skips a build",
                -1)
    needs_build, reason = decision_for(rc)
    return needs_build, reason, rc


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="decide whether CI still needs to build a dev image (issue #1057)"
    )
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_ROOT,
                        help="checkout to read (defaults to the repository holding this script)")
    parser.add_argument("--image", choices=dev_image_id.IMAGES, default="backend",
                        help="which dev image to ask about (default: backend)")
    parser.add_argument("--probe-argv", nargs="+", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        needs_build, reason, rc = decide(args)
    except Exception as exc:                       # noqa: BLE001
        # Anything that escapes the decision - a resolver that cannot even be read,
        # an unexpected os error - becomes "build", because the alternative is a
        # red required check that stops every pull request over a helper script.
        needs_build = True
        reason = (f"the gate itself failed ({type(exc).__name__}: {exc}); a gate that cannot "
                  f"answer does not skip a build")
        rc = -1
    print(f"dev_image_gate: needs_build={'true' if needs_build else 'false'} - {reason}",
          file=sys.stderr)
    emit({"needs_build": "true" if needs_build else "false",
          "probe_rc": rc,
          "reason": reason}, os.environ.get(GITHUB_OUTPUT_ENV))
    return 0


if __name__ == "__main__":
    sys.exit(main())
