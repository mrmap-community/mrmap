"""Offline regression check for the coverage data of parallel unit tests (#1055).

Run from the repository root with an interpreter that has the dev tooling of
``backend/.requirements`` in it::

    .venv/bin/python scripts/test_coverage_parallel_data.py

Exit code 0 means every check passed. Needs no docker, no network and no
application code; when ``coverage`` is missing it says so out loud instead of
reporting a pass it did not earn.

What is being protected is invisible in CI, which is exactly why it needs a
check. The unit-test job runs the suite with ``manage.py test --parallel=4``, and
that runner executes test cases in *forked children*. Coverage then has two ways
to lose work without any command failing:

*   it does not trace a forked child unless ``concurrency = multiprocessing`` is
    configured, so every line only a worker executed is simply absent from the
    uploaded report, and
*   a child inherits the *environment* of the parent, not its ``--data-file``
    argument, so even with the first problem solved the children write data files
    the report step never looks for.

Both are checked against the repository's real ``backend/setup.cfg``, using a
module with one function that only ever runs in the parent and one that only ever
runs in the worker. A smaller line rate for that module is a lost worker.

The third pair of checks protects the other job that shares this configuration
file: Behave runs one process and uploads ``.coverage.acceptance`` with
``if-no-files-found: error``, so it must keep producing that exact file after the
key above was added to the section it shares with the unit tests.
"""

import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETUP_CFG = os.path.join(REPO_ROOT, "backend", "setup.cfg")

PASS = FAIL = 0
FAILURES = []

MODULE = '''"""One function per process, so coverage can be asked which one it saw."""


def parent_only():
    total = 0
    for value in range(20):
        total += value
    return total


def child_only():
    total = 0
    for value in range(20):
        total += value * 2
    return total
'''

RUNNER = '''"""Runs one function here and one in a forked worker.

The worker branch is a separate function because that is what the parallel test
runner does: it hands the worker a target, not a re-read of ``sys.argv``. A target
that looked at ``sys.argv`` instead would run the parent's branch twice and prove
nothing at all - which is how a first version of this probe passed while measuring
the wrong thing.
"""
import multiprocessing

import only_here


def worker():
    only_here.child_only()


def main():
    only_here.parent_only()
    child = multiprocessing.Process(target=worker)
    child.start()
    child.join()


if __name__ == "__main__":
    main()
'''

SOLO = '''"""One process only, the shape of the acceptance-test job.

It calls both functions because the point of this case is not which process ran
what: it is that a single-process run under the same configuration still reports
every line it executed and still leaves the data file the upload step names.
"""
import only_here

only_here.parent_only()
only_here.child_only()
'''

# The same rcfile without the key under test, as the negative control: if this
# variant ever *keeps* the worker's lines, the check has stopped measuring
# anything and has to say so rather than report a pass.
WITHOUT_CONCURRENCY = """[coverage:run]
branch = True
source = .
relative_files = True
"""


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


def coverage_available():
    return subprocess.run([sys.executable, "-m", "coverage", "--version"],
                          capture_output=True, text=True).returncode == 0


def workspace(tmp, rcfile_body, extra=()):
    """A directory with the module, a script to run and the rcfile to measure with."""
    for name, body in (("only_here.py", MODULE), ("run_both.py", RUNNER)) + tuple(extra):
        with open(os.path.join(tmp, name), "w") as handle:
            handle.write(body)
    rc = os.path.join(tmp, "setup.cfg")
    with open(rc, "w") as handle:
        handle.write(rcfile_body)
    return rc


def run_coverage(tmp, rc, command, *args, env=None):
    """One coverage command, returning (returncode, stderr).

    Two positions matter here and both came from a run that failed: the rcfile has
    to follow the sub-command, because coverage reads its own options only after the
    command word (``coverage --rcfile X run ...`` is refused outright); and it must
    not trail the line either, because everything after the script name of
    ``coverage run`` belongs to the program being measured.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "coverage", command, "--rcfile", rc, *args],
        cwd=tmp, capture_output=True, text=True,
        env=env or dict(os.environ, PYTHONPATH=tmp))
    return proc.returncode, proc.stderr.strip()


def covered_lines(xml_path, filename):
    """(line number, hit count) for every line of one file in an XML report.

    Read line by line rather than taken from the ``line-rate`` attribute, so the
    check asks coverage's own numbers but does not trust the summary it is being
    sold.
    """
    root = ET.parse(xml_path).getroot()
    for klass in root.iter("class"):
        if klass.get("filename", "").endswith(filename):
            return [(int(line.get("number")), int(line.get("hits", "0")))
                    for line in klass.iter("line") if line.get("number")]
    return None


def measure(tmp, rc, script, filename, data_name, use_coverage_file_env):
    """Run one script under the two commands of the real job, report the line rate.

    ``rate`` is None when coverage produced no report at all, which a caller reads
    as a failure rather than as a low number.
    """
    env = dict(os.environ, PYTHONPATH=tmp)
    data_file = os.path.join(tmp, data_name)
    if use_coverage_file_env:
        env["COVERAGE_FILE"] = data_file
    else:
        env.pop("COVERAGE_FILE", None)
    xml = os.path.join(tmp, "report.xml")

    code, err = run_coverage(tmp, rc, "run", "--data-file", data_file, script, env=env)
    if code != 0:
        return None, f"coverage run failed: {err[:200]}"
    code, err = run_coverage(tmp, rc, "xml", "--data-file", data_file, "-o", "report.xml",
                             env=env)
    if code != 0 or not os.path.exists(xml):
        return None, f"coverage xml failed: {err[:200]}"

    lines = covered_lines(xml, filename)
    if not lines:
        return None, f"{filename} is not in the report at all"
    hits = sum(1 for _, hit in lines if hit)
    return hits / len(lines), f"{hits} of {len(lines)} lines hit"


def rcfile_of_setup_cfg():
    """The repository's own [coverage:run] section, as an rcfile.

    Read rather than duplicated on purpose: the check is about this configuration,
    so a copy of it in the test file would pass while the real one regressed.
    """
    with open(SETUP_CFG) as handle:
        text = handle.read()
    section = re.search(r"^\[coverage:run\][^\[]*", text, re.MULTILINE | re.DOTALL)
    if not section:
        return None
    # `source = .` means "the directory coverage was asked about", and the check
    # runs inside a temporary directory, so the real section applies unchanged.
    return section.group(0).rstrip() + "\n"


def test_the_shipped_configuration_keeps_a_workers_lines():
    body = rcfile_of_setup_cfg()
    check("backend/setup.cfg has a [coverage:run] section", body is not None)
    if body is None:
        return
    check("the shipped configuration tells coverage about forked workers",
          "concurrency" in body and "multiprocessing" in body,
          "no `concurrency = multiprocessing` in [coverage:run]")
    tmp = tempfile.mkdtemp(prefix="coverage-parallel-")
    rc = workspace(tmp, body)
    rate, detail = measure(tmp, rc, "run_both.py", "only_here.py",
                           ".coverage.unit", use_coverage_file_env=True)
    check("a worker's lines are in the report the job uploads", rate == 1.0,
          f"line rate {rate}: {detail} - every line of that module was executed by "
          f"one of the two processes, so anything below 1.0 is lost work")


def test_without_the_key_the_lines_are_actually_lost():
    """The negative control, so a pass above means something."""
    tmp = tempfile.mkdtemp(prefix="coverage-parallel-neg-")
    rc = workspace(tmp, WITHOUT_CONCURRENCY)
    rate, detail = measure(tmp, rc, "run_both.py", "only_here.py",
                           ".coverage.unit", use_coverage_file_env=True)
    check("without that key the worker's lines really are lost",
          rate is not None and rate < 1.0,
          f"line rate {rate} ({detail}); if a forked worker is reported without the "
          f"key, this check no longer measures the failure it exists for")


def test_a_child_sees_the_environment_not_the_flag():
    """COVERAGE_FILE is all a forked child can see of ``--data-file``.

    Same configuration, same run, only the variable withheld: the children then
    write files the report step never looks for, which is how the job ends up with
    a healthy-looking but incomplete number.
    """
    body = rcfile_of_setup_cfg()
    if body is None:
        return
    tmp = tempfile.mkdtemp(prefix="coverage-parallel-env-")
    rc = workspace(tmp, body)
    rate, detail = measure(tmp, rc, "run_both.py", "only_here.py",
                           ".coverage.unit", use_coverage_file_env=False)
    check("withholding COVERAGE_FILE loses the worker's data",
          rate is None or rate < 1.0,
          f"line rate {rate} without COVERAGE_FILE ({detail}) - the job would need a "
          f"new reason for this check")


def test_a_single_process_run_keeps_its_named_data_file():
    """Behave shares this configuration, runs one process, and uploads the data file.

    ``concurrency = multiprocessing`` changes how coverage names the file it
    writes - it appends a host and pid suffix, because a fork could happen at any
    moment. The acceptance job's upload step looks for ``.coverage.acceptance`` by
    name with ``if-no-files-found: error``, so this checks the whole shape of that
    command: no COVERAGE_FILE in its environment, the plain flag only, and the
    named file present after the XML step that combines the suffixed ones.
    """
    body = rcfile_of_setup_cfg()
    if body is None:
        return
    tmp = tempfile.mkdtemp(prefix="coverage-parallel-solo-")
    rc = workspace(tmp, body, extra=(("run_one.py", SOLO),))
    rate, detail = measure(tmp, rc, "run_one.py", "only_here.py",
                           ".coverage.acceptance", use_coverage_file_env=False)
    check("the acceptance job's own lines are all still reported", rate == 1.0,
          f"line rate {rate}: {detail}")
    check("and the data file the upload step names by hand is there afterwards",
          os.path.exists(os.path.join(tmp, ".coverage.acceptance")),
          f"files: {sorted(n for n in os.listdir(tmp) if n.startswith('.coverage'))}")


def main():
    if not coverage_available():
        print(f"{sys.executable} has no coverage module "
              f"(backend/.requirements/dev.txt provides it); nothing was measured.")
        print("0 passed, 0 failed, 1 skipped")
        return 0
    tests = (test_the_shipped_configuration_keeps_a_workers_lines,
             test_without_the_key_the_lines_are_actually_lost,
             test_a_child_sees_the_environment_not_the_flag,
             test_a_single_process_run_keeps_its_named_data_file)
    for fn in tests:
        try:
            fn()
        except Exception as exc:                       # a crash is a failed check
            check(f"{fn.__name__} raised", False, f"{type(exc).__name__}: {exc}")
    print(f"{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
