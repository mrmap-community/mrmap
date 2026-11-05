"""Offline regression checks for the capacity adapter of the agent supervisor (#1059).

Run from the repository root: python3 scripts/test_agent_supervisor_capacity.py
Exit code 0 means every check passed. Needs no docker, no `gh` and no network: the
capacity gate is replaced by small throwaway shell scripts in a temporary
directory, so the checks cover the **real contract** - arguments, exit codes,
stdout - instead of a mocked return value.

The rule these checks exist for: the supervisor may only start a heavy stack when
the repository's own gate said so. So every way that saying can fail - the gate
missing, too old, confused, timing out, answering nonsense - has to end in
"do not start", and only the gate's own `fits` may end in "start".
"""

import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_supervisor import capacity as capacity_module               # noqa: E402
from agent_supervisor.capacity import Capacity, NEED_PROCESS, NEED_STACK   # noqa: E402

PASS = FAIL = 0
FAILURES = []
TMP = tempfile.mkdtemp(prefix="supervisor-capacity-tests-")


def check(name, condition, note=""):
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name + (f" - {note}" if note else ""))


class Cfg:
    """The adapter only reads nothing from the configuration - the gate decides."""

    def get(self, key, default=None):
        return default


def gate(name, body):
    """One fake gate: an executable shell script with `body` as its behaviour."""
    path = os.path.join(TMP, name)
    with open(path, "w") as handle:
        handle.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP)
    return path


METRICS = {"need": NEED_STACK, "mem_effective_gb": 11.2, "mem_cgroup_limit_gb": 16.0,
           "mem_source": "cgroup", "stacks": 1, "stacks_max": 3, "load_per_core": 0.4}


def test_modern_gate():
    """The #1053 contract: --need <class> --json, exit 0 fits / 1 busy."""
    seen = os.path.join(TMP, "args.txt")
    good = gate("modern", f'''echo "$@" > {seen}
case "$*" in
  *--json*) cat <<'JSON'
{{"need":"stack","fits":true,"reasons":[],
 "metrics":{{"need":"stack","mem_effective_gb":11.2,"mem_cgroup_limit_gb":16.0,
             "mem_source":"cgroup","stacks":1,"stacks_max":3,"load_per_core":0.4}}}}
JSON
    ;;
esac
exit 0''')
    answer = Capacity(Cfg(), path=good).evaluate(NEED_STACK)
    check("the gate's fits is the supervisor's fits", answer["fits"] is True, str(answer))
    check("the verdict word is the supervisor's own", answer["verdict"] == "fits", str(answer))
    check("metrics come through", answer["metrics"].get("stacks_max") == 3, str(answer))
    check("the source says the modern gate", answer["source"] == "json", answer["source"])
    args = open(seen).read()
    check("the job class is asked for explicitly", "--need stack" in args, args)
    check("and JSON is asked for", "--json" in args, args)
    check("the summary line is human readable", "11.2G" in answer["explanation"],
          answer["explanation"])

    busy = gate("busy", '''case "$*" in
  *--json*) cat <<'JSON'
{"need": "stack", "fits": false,
 "reasons": ["mem 1.2G is below the 6G a stack needs", "2 stacks already run"],
 "metrics": {"need": "stack", "mem_effective_gb": 1.2, "mem_source": "cgroup",
             "stacks": 2, "stacks_max": 3, "load_per_core": 0.4}}
JSON
    ;;
esac
exit 1''')
    answer = Capacity(Cfg(), path=busy).evaluate(NEED_STACK)
    check("a busy host is not admitted", answer["fits"] is False, str(answer))
    check("the refusal reasons survive", len(answer["reasons"]) == 2, str(answer))
    check("and are the explanation", "below the 6G" in answer["explanation"],
          answer["explanation"])
    check("busy is reported as busy", answer["verdict"] == "busy", answer["verdict"])

    process = gate("process", '''case "$1$2$3$4$5$6" in
  *process*) echo '{"need":"process","fits":true,"reasons":[],"metrics":{}}';;
  *) echo '{"need":"stack","fits":false,"reasons":["stack needs more than this host"],"metrics":{}}'
     exit 1;;
esac''')
    check("the light class is asked for by name",
          Capacity(Cfg(), path=process).evaluate(NEED_PROCESS)["fits"] is True)
    try:
        Capacity(Cfg(), path=good).evaluate("everything")
        check("an unknown job class is a programming error", False, "no exception")
    except ValueError as exc:
        check("an unknown job class is a programming error", "everything" in str(exc), str(exc))


def test_legacy_gate():
    """A gate from before #1053: no --need, no --json, one verdict line."""
    legacy = gate("legacy", '''case "$*" in
  *--need*|*--json*) echo "unknown option" >&2; exit 2;;
esac
echo "agent_capacity: load 0.2/core (max 1.5), mem 64.7G (min 16)," \\
  "disk 1736G (min 100), stacks 0 (max 3) -> fits"''')
    answer = Capacity(Cfg(), path=legacy).evaluate(NEED_STACK)
    check("an old gate is still understood", answer["fits"] is True, str(answer))
    check("and that is said in the source", answer["source"] == "legacy-line", answer["source"])
    check("its whole line is the explanation", answer["explanation"].endswith("-> fits"),
          answer["explanation"])

    legacy_busy = gate("legacy-busy", '''case "$*" in
  *--need*|*--json*) echo "unknown option" >&2; exit 2;;
esac
echo "agent_capacity: mem 3.0G (min 16) -> busy"
exit 1''')
    answer = Capacity(Cfg(), path=legacy_busy).evaluate(NEED_STACK)
    check("an old gate's busy is respected", answer["fits"] is False, str(answer))

    nonsense = gate("nonsense", '''case "$*" in
  *--need*|*--json*) echo "unknown option" >&2; exit 2;;
esac
echo "something else entirely"''')
    answer = Capacity(Cfg(), path=nonsense).evaluate(NEED_STACK)
    check("an unreadable line admits nothing", answer["fits"] is False, str(answer))
    check("and says it was not understood", "not understood" in answer["explanation"],
          answer["explanation"])


def test_gate_that_ignores_the_new_flags():
    """The old gate that does not reject `--need`/`--json`, it ignores them.

    This is the common case in practice: a shell script with a permissive
    argument parser prints its one verdict line and exits 0 whatever it was
    asked. Reading that line is what makes the supervisor usable on a host one
    release behind; demanding JSON there would refuse all work on a host that
    has plenty, which is a failure the operator would notice as a queue that
    never starts anything.
    """
    ignoring = gate("ignoring", '''echo "agent_capacity: load 0.3/core (max 1.5), mem 40.0G (min 16)," \\
  "disk 900.0G (min 100), stacks 1 (max 3) -> fits"''')
    answer = Capacity(Cfg(), path=ignoring).evaluate(NEED_STACK)
    check("a gate that ignores the new flags is still read",
          answer["fits"] is True, str(answer))
    check("and it is labelled as the legacy answer, not as JSON",
          answer["source"] == "legacy-line", answer["source"])
    check("its job class is the heavy one, because that is all it measured",
          answer["need"] == NEED_STACK, str(answer))

    ignoring_busy = gate("ignoring-busy", '''echo "agent_capacity: mem 3.0G (min 16) -> busy"
exit 1''')
    answer = Capacity(Cfg(), path=ignoring_busy).evaluate(NEED_PROCESS)
    check("its busy is respected for the light class too",
          answer["fits"] is False and answer["verdict"] == "busy", str(answer))

    # a gate whose word and exit code disagree is a gate with a bug, and the bug
    # is on the side that lets work start
    disagree = gate("disagree", '''echo "agent_capacity: mem 40.0G (min 16) -> fits"
exit 1''')
    answer = Capacity(Cfg(), path=disagree).evaluate(NEED_STACK)
    check("a gate that says fits and exits busy admits nothing",
          answer["fits"] is False, str(answer))
    check("and the contradiction is named", "but exits busy" in answer["explanation"],
          answer["explanation"])


def test_broken_gate():
    missing = os.path.join(TMP, "not-here")
    answer = Capacity(Cfg(), path=missing).evaluate(NEED_STACK)
    check("no gate means no admission", answer["fits"] is False, str(answer))
    check("and names the path it looked at", missing in answer["explanation"],
          answer["explanation"])

    garbage = gate("garbage", 'echo "this is not json"')
    answer = Capacity(Cfg(), path=garbage).evaluate(NEED_STACK)
    check("an unparsable JSON answer admits nothing", answer["fits"] is False, str(answer))

    not_object = gate("array", 'echo "[1,2,3]"')
    check("a JSON answer that is not an object admits nothing",
          Capacity(Cfg(), path=not_object).evaluate(NEED_STACK)["fits"] is False)

    crash = gate("crash", 'echo "traceback" >&2; exit 3')
    answer = Capacity(Cfg(), path=crash).evaluate(NEED_STACK)
    check("a gate that crashes admits nothing", answer["fits"] is False, str(answer))
    check("and the exit code is kept for the log", "exited 3" in answer["explanation"],
          answer["explanation"])

    slow = gate("slow", "sleep 5")
    original = capacity_module.TIMEOUT_S
    capacity_module.TIMEOUT_S = 1
    try:
        answer = Capacity(Cfg(), path=slow).evaluate(NEED_STACK)
        check("a gate that hangs admits nothing", answer["fits"] is False, str(answer))
        check("and says it timed out", "timed out" in answer["explanation"],
              answer["explanation"])
    finally:
        capacity_module.TIMEOUT_S = original

    silent = gate("silent", "exit 0")
    answer = Capacity(Cfg(), path=silent).evaluate(NEED_STACK)
    check("an empty answer admits nothing", answer["fits"] is False, str(answer))


def test_no_side_effects():
    """The adapter reads; it must never be able to change anything."""
    path = os.path.join(capacity_module.__file__)
    with open(path) as handle:
        source = handle.read()
    check("the adapter opens nothing but the gate",
          "subprocess.run" in source and "Popen" not in source and "os.system" not in source)
    check("it spawns with an argument list, not a shell",
          "shell=True" not in source)
    check("it does not start containers", "docker" not in source.replace("docker ps", ""))


def main():
    for fn in (test_modern_gate, test_legacy_gate, test_gate_that_ignores_the_new_flags,
               test_broken_gate, test_no_side_effects):
        fn()
    print(f"\n{PASS} passed, {FAIL} failed")
    for failure in FAILURES:
        print(f"  FAIL {failure}")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
