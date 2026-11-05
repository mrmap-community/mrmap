#!/usr/bin/env python3
"""Offline checks for scripts/dev_image_gate.py (issue #1057).

Run from the repository root: `python3 scripts/dev_image_gate.py` is the tool,
`python3 scripts/test_dev_image_gate.py` checks it. Needs no docker, no
network and no gh: every probe answer is canned by a stub resolver, so the
exit-code contract can be walked through completely - including the codes a
live registry only shows occasionally (5, 7) and the ones the private ghcr.io
packages show today (4). The workflow half checks the wiring of
.github/workflows/dev-images.yml as text, because PyYAML is not a stdlib
dependency.

Exit 0 when every check passed, 1 otherwise.
"""

import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

_spec = importlib.util.spec_from_file_location("dev_image_gate", SCRIPTS / "dev_image_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

_spec2 = importlib.util.spec_from_file_location("dev_image_id", SCRIPTS / "dev_image_id.py")
dev_image_id = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(dev_image_id)

WORKFLOW = ROOT / ".github" / "workflows" / "dev-images.yml"
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


# ------------------------------------------------------------------- fixtures
def write_stub(path, rc, record=None):
    """Stand in for scripts/dev_image_id.py: record how it was called, answer rc."""
    lines = ["import os, sys\n"]
    if record:
        lines.append("with open(%r, 'w') as fh:\n" % str(record))
        lines.append("    fh.write('\\n'.join(sys.argv[1:]) + '\\n')\n")
        lines.append("    fh.write('Mutable=' + os.environ.get(%r, 'unset') + '\\n')\n"
                     % dev_image_id.MUTABLE_OPT_OUT_ENV)
    lines.append("print('stub resolver: what the resolver would have reported', file=sys.stderr)\n")
    lines.append(f"raise SystemExit({rc})\n")
    path.write_text("".join(lines))


def run_gate(*args, env_extra=None, github_output=None):
    env = dict(os.environ)
    env.pop("GITHUB_OUTPUT", None)
    env.pop(dev_image_id.MUTABLE_OPT_OUT_ENV, None)
    if github_output:
        env["GITHUB_OUTPUT"] = str(github_output)
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, str(SCRIPTS / "dev_image_gate.py"), *args],
                          capture_output=True, text=True, timeout=180, cwd=ROOT, env=env)


def outputs_of(text):
    """Parse stdout (or a $GITHUB_OUTPUT file) as name=value lines."""
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def gate_with_stub(tmp, rc, image="backend"):
    """Run the gate against a stub resolver answering ``rc``; outputs included."""
    tag = f"{rc}-{image}"
    stub = tmp / f"stub-{tag}.py"
    recorded = tmp / f"argv-{tag}.txt"
    write_stub(stub, rc, record=recorded)
    out = tmp / f"out-{tag}.txt"
    proc = run_gate("--image", image, "--probe-argv", sys.executable, str(stub),
                    github_output=out)
    outputs = outputs_of(proc.stdout) if proc.returncode == 0 else {}
    argv = recorded.read_text().splitlines() if recorded.exists() else []
    return proc, outputs, out, argv


def job_slice(text, job):
    """The YAML text of one job, from its key to the next job at the same indent."""
    start = re.search(rf"(?m)^  {re.escape(job)}:\n", text)
    if not start:
        return None
    rest = text[start.end():]
    following = re.search(r"(?m)^  [A-Za-z0-9_-]+:\n", rest)
    return rest[:following.start()] if following else rest


# ------------------------------------------------- the decision table, as pure data
def test_decision_table():
    check("exit 0 is the only code that skips the build",
          gate.decision_for(dev_image_id.EXIT_OK)[0] is False,
          str(gate.decision_for(dev_image_id.EXIT_OK)))
    for rc, label in ((dev_image_id.EXIT_MISS, "never published"),
                      (dev_image_id.EXIT_TRANSIENT, "transient or denied"),
                      (dev_image_id.EXIT_PLATFORM, "platform"),
                      (dev_image_id.EXIT_BUILD_FAILED, "build failed"),
                      (dev_image_id.EXIT_STAMP_MISMATCH, "foreign content"),
                      (1, "resolver crashed"), (2, "usage error"),
                      (124, "timed out"), (137, "killed")):
        needs_build, reason = gate.decision_for(rc)
        check(f"exit {rc} ({label}) still builds", needs_build is True, str((rc, reason)))
        check(f"exit {rc} reason explains itself", bool(reason) and "\n" not in reason, reason)
    transient = gate.decision_for(dev_image_id.EXIT_TRANSIENT)[1]
    check("exit 4 names the denied-anonymous-inspection trap it guards against",
          "transient" in transient.lower() and "denied" in transient.lower(), transient)
    check("no decision except the published one can ever say false",
          all(gate.decision_for(code)[0] is True for code in (1, 2, 3, 4, 5, 6, 7, 8, 130)))


# ------------------------------------------------------- the probe is the resolver
def test_probe_command(tmp):
    default = gate.probe_command(ROOT, "backend")
    check("the probe is the repository's own resolver",
          str(ROOT / "scripts" / "dev_image_id.py") in default, " ".join(default))
    check("the probe is the documented --resolve call",
          default[-3:] == ["--resolve", "--image", "backend"], " ".join(default))
    check("the probe never asks the resolver to build", "--build" not in default, " ".join(default))
    check("the probe is per image",
          gate.probe_command(ROOT, "frontend")[-2:] == ["--image", "frontend"])
    check("the opt-out env never reaches the probe",
          dev_image_id.MUTABLE_OPT_OUT_ENV not in gate.probe_env())

    recorded_argv = gate_with_stub(tmp, 0, image="frontend")[3]
    check("a run forwards the documented --resolve call for its image",
          recorded_argv[:3] == ["--resolve", "--image", "frontend"], str(recorded_argv))
    check("a run never asks the resolver to build", "--build" not in recorded_argv,
          str(recorded_argv))
    check("the gate strips the mutable-image opt-out from the probe environment",
          recorded_argv[-1:] == ["Mutable=unset"], str(recorded_argv))

    usage = run_gate("--image", "backend", "--build")
    check("the gate itself has no --build to pass on", usage.returncode == 2, usage.stderr[-200:])


# ------------------------------------------------------------ end to end, canned rc
def test_cli_contract(tmp):
    for rc, want in ((dev_image_id.EXIT_OK, "false"), (dev_image_id.EXIT_MISS, "true"),
                     (dev_image_id.EXIT_TRANSIENT, "true"), (dev_image_id.EXIT_PLATFORM, "true"),
                     (dev_image_id.EXIT_STAMP_MISMATCH, "true"), (2, "true")):
        proc, outputs, out_file, _ = gate_with_stub(tmp, rc)
        check(f"probe rc {rc} -> needs_build={want}",
              outputs.get("needs_build") == want,
              f"rc={proc.returncode} outputs={outputs} err={proc.stderr[-200:]}")
        check(f"probe rc {rc} reports the code back", outputs.get("probe_rc") == str(rc),
              str(outputs))
        check(f"probe rc {rc} still exits 0 so the required check keeps reporting success",
              proc.returncode == 0, f"rc={proc.returncode} err={proc.stderr[-200:]}")
        written = out_file.read_text() if out_file.exists() else ""
        check(f"probe rc {rc} lands in $GITHUB_OUTPUT unchanged",
              written == proc.stdout, f"file={written!r} stdout={proc.stdout!r}")
        check(f"probe rc {rc} forwards the resolver diagnostics for the log",
              "stub resolver" in proc.stderr, proc.stderr[-200:])
        check(f"probe rc {rc} output is three single-line assignments",
              len(outputs) == 3 and all(v and "\n" not in v for v in outputs.values()), str(outputs))

    quiet = run_gate("--image", "backend", "--probe-argv", str(tmp / "no-such-interpreter"))
    outputs = outputs_of(quiet.stdout) if quiet.returncode == 0 else {}
    check("a probe that cannot run is a decision to build, not a failed step",
          quiet.returncode == 0 and outputs.get("needs_build") == "true"
          and outputs.get("probe_rc") == "-1", f"rc={quiet.returncode} out={outputs}")


# ----------------------------------------------------------- the workflow wiring
def test_workflow_wiring():
    if not WORKFLOW.is_file():
        check("dev-images.yml is present to be checked", False, str(WORKFLOW))
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    check("dev-images.yml parses as YAML-ish text with the four jobs",
          all(f"\n  {job}:\n" in text for job in
              ("backend-dev-build", "backend-dev-publish",
               "frontend-dev-build", "frontend-dev-publish")))

    for job, image in (("backend-dev-build", "backend"), ("frontend-dev-build", "frontend")):
        block = job_slice(text, job)
        if block is None:
            check(f"{job} still exists as a job", False, "job key not found")
            continue
        check(f"{job} asks the gate about its own image",
              f"scripts/dev_image_gate.py --image {image}" in block, block[:200])
        gated = re.findall(r"(?m)^ {8}if: steps\.gate\.outputs\.needs_build != 'false'$", block)
        check(f"{job} conditions both its buildx and its build step on the gate",
              len(gated) >= 2, f"{len(gated)} gated steps")
        check(f"{job} skips nothing on a missing answer (asks != 'false', never == 'true')",
              "== 'true'" not in block, block[:200])
        check(f"{job} keeps the gate off the job itself (the check must always report)",
              not re.search(r"(?m)^ {4}if:.*needs_build", block), block[:200])
        check(f"{job} still cannot push", "push: true" not in block)
        check(f"{job} keeps its event condition only",
              re.search(r"(?m)^ {4}if: github\.event_name", block) is not None, block[:200])

    for job in ("backend-dev-publish", "frontend-dev-publish"):
        block = job_slice(text, job) or ""
        check(f"{job} still publishes unconditionally",
              "push: true" in block and "dev_image_gate" not in block, block[:200])


def test_default_probe_path(tmp):
    """Without a stub the gate asks the resolver of the checkout it is gating."""
    fake = tmp / "fake-checkout"
    (fake / "scripts").mkdir(parents=True)
    (fake / "scripts" / "dev_image_id.py").write_text(
        "import os, sys\n"
        "sys.stderr.write('fake resolver ran in ' + os.getcwd() + '\\n')\n"
        "sys.stdout.write('beef0000cafe\\n')\n"
        "raise SystemExit(0)\n")
    proc = run_gate("--repo-root", str(fake))
    outputs = outputs_of(proc.stdout) if proc.returncode == 0 else {}
    check("the default probe is that checkout's dev_image_id.py, run from its root",
          proc.returncode == 0 and outputs.get("needs_build") == "false"
          and str(fake.resolve()) in proc.stderr,
          f"rc={proc.returncode} out={outputs} err={proc.stderr[-200:]}")


def test_a_gate_that_crashes_keeps_the_build_and_stays_green():
    """The gate's own failure may not redden the check the merge queue waits for.

    Driven in-process, because the failure to simulate is one the probe cannot
    produce from the outside: a `run_probe` that raises instead of answering. What
    has to hold is that the step still exits 0 and still says `needs_build=true` -
    a traceback here would block every pull request over a helper whose only job is
    to save minutes, and a missing output would read as "skip" to an `== 'true'`
    condition.
    """
    original = gate.run_probe

    def explode(*args, **kwargs):
        raise RuntimeError("the resolver module could not be read")

    gate.run_probe = explode
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(io.StringIO()):
            code = gate.main(["--image", "backend"])
    finally:
        gate.run_probe = original
    outputs = outputs_of(captured.getvalue())
    check("a gate that crashes internally still exits 0", code == 0, f"rc={code}")
    check("a gate that crashes internally still says the build is needed",
          outputs.get("needs_build") == "true", f"outputs={outputs}")


def test_a_gate_that_cannot_write_its_output_still_builds(tmp):
    """``$GITHUB_OUTPUT`` unwritable: the decision is printed, the step is not red.

    A directory in the place of the file is the cheapest honest way to make the
    append fail. The property worth pinning is what the workflow then sees: no
    output, and steps that ask ``!= 'false'`` build anyway.
    """
    stub = tmp / "stub-unwritable.py"
    write_stub(stub, dev_image_id.EXIT_OK)
    proc = run_gate("--image", "backend", "--probe-argv", sys.executable, str(stub),
                    github_output=tmp)
    check("an unwritable $GITHUB_OUTPUT does not fail the step", proc.returncode == 0,
          f"rc={proc.returncode} err={proc.stderr[-200:]}")
    check("and the decision still reaches stdout",
          "needs_build=false" in proc.stdout, proc.stdout[:200])
    check("and the missing output is named as the reason the build may still run",
          "GITHUB_OUTPUT" in proc.stderr, proc.stderr[-200:])


def main():
    print(f"dev_image_gate checks on {ROOT}")
    with tempfile.TemporaryDirectory(prefix="dev-image-gate-test-") as tmp:
        work = Path(tmp)
        test_decision_table()
        test_probe_command(work)
        test_cli_contract(work)
        test_default_probe_path(work)
        test_a_gate_that_crashes_keeps_the_build_and_stays_green()
        test_a_gate_that_cannot_write_its_output_still_builds(work)
    test_workflow_wiring()

    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    for name, ok, detail in RESULTS:
        line = f"{'PASS' if ok else 'FAIL'}  {name}"
        if not ok and detail:
            line += f"  [{detail}]"
        print(line)
    print(f"{len(RESULTS) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
