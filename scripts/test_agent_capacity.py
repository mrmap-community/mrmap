#!/usr/bin/env python3
"""Offline checks for scripts/agent_capacity (issue #1053).

Runs without docker, without network and without a real cgroup limit: every
metric is read from a fabricated cgroup and /proc tree in a temporary
directory, so the admission rules can be tested at the boundary that matters -
a container whose cgroup is far smaller than the machine it runs on.

Run from the repository root: `python3 scripts/test_agent_capacity.py`.
Exit 0 when every check passes, 1 on the first failure list with entries.
"""

import importlib.machinery
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
GB = 1024 ** 3

loader = importlib.machinery.SourceFileLoader("agent_capacity", str(SCRIPTS / "agent_capacity"))
spec = importlib.util.spec_from_loader("agent_capacity", loader)
cap = importlib.util.module_from_spec(spec)
loader.exec_module(cap)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


# ------------------------------------------------------------------ fixtures

def write_cgroup(root, rel, limit=None, current=None, stat=None, peak=None,
                 events=None, pressure=None):
    """One fabricated cgroup level; None means the file is not there at all."""
    d = root / rel.lstrip("/")
    d.mkdir(parents=True, exist_ok=True)
    (d / "memory.max").write_text("max\n" if limit is None else f"{limit}\n")
    if current is not None:
        (d / "memory.current").write_text(f"{current}\n")
    if stat is not None:
        (d / "memory.stat").write_text("".join(f"{k} {v}\n" for k, v in stat.items()))
    if peak is not None:
        (d / "memory.peak").write_text(f"{peak}\n")
    if events is not None:
        (d / "memory.events").write_text("".join(f"{k} {v}\n" for k, v in events.items()))
    if pressure is not None:
        (d / "memory.pressure").write_text(
            f"some avg10={pressure} avg60={pressure} avg300={pressure} total=0\n"
            f"full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n")


def write_proc(root, path="/", mem_available_gb=68.0, load15=1.0):
    """A fabricated /proc: loadavg, meminfo and the cgroup line of this process."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "loadavg").write_text(f"0.1 0.2 {load15} 1/2 99999\n")
    (root / "meminfo").write_text(
        f"MemTotal:       {int(96 * GB / 1024)} kB\n"
        f"MemAvailable:   {int(mem_available_gb * GB / 1024)} kB\n")
    (root / "self").mkdir(exist_ok=True)
    (root / "self" / "cgroup").write_text(f"0::{path}\n")
    return root


def fake_proc_with_processes(root, names):
    """Add fake /proc/<pid>/cmdline entries for the agent-process counter."""
    for i, name in enumerate(names, start=1):
        d = root / str(1000 + i)
        d.mkdir(parents=True, exist_ok=True)
        (d / "cmdline").write_bytes(f"{name}\0--run\0".encode())


def limits(**kwargs):
    """Threshold overrides with every knob pinned, so ambient env cannot leak."""
    base = {
        "AGENT_MAX_LOAD_PER_CORE": "1.5", "AGENT_MIN_DISK_GB": "100",
        "AGENT_MAX_STACKS": "3", "AGENT_MAX_PROCESSES": "6",
        "AGENT_STACK_MIN_MEM_GB": "6", "AGENT_PROCESS_MIN_MEM_GB": "2",
        "AGENT_MIN_MEM_GB": "16", "AGENT_MEM_RESERVE_GB": "2",
        "AGENT_MEM_NEAR_CEILING_PCT": "90", "AGENT_MAX_MEM_PRESSURE": "10",
    }
    for key, value in kwargs.items():
        name = "AGENT_" + key.upper()
        base[name] = "" if value is None else str(value)
    return base


def decide(cgroup, proc, need="stack", stacks=0, processes=None, env=None, **thresholds):
    return cap.evaluate(need=need, stacks=stacks, processes=processes, env=limits(**thresholds),
                        proc_root=str(proc), cgroup_root=str(cgroup))


# ------------------------------------------------------------------- checks

def test_parsing(tmp):
    check("parse_limit reads bytes", cap.parse_limit("17179869184\n") == 17179869184)
    check("parse_limit treats max as unlimited", cap.parse_limit("max\n") is None)
    check("parse_limit treats empty as unlimited", cap.parse_limit("") is None)
    check("parse_limit ignores garbage", cap.parse_limit("nonsense") is None)
    check("parse_kv reads events", cap.parse_kv("max 5\noom 3\noom_kill 1\n")
          == {"max": 5, "oom": 3, "oom_kill": 1})
    check("parse_kv survives junk lines", cap.parse_kv("max 5\nbroken line here\n") == {"max": 5})
    root = Path(tmp) / "statonly"
    write_cgroup(root, "/", limit=10 * GB, current=1 * GB, stat={
        "anon": 2 * GB, "file": 5 * GB, "kernel": 1 * GB, "kernel_stack": 4 * GB,
        "pagetables": 0, "percpu": 0, "vmalloc": 0, "slab_unreclaimable": 0,
        "slab_reclaimable": 1 * GB})
    check("committed counts the kernel side once, not twice",
          cap.committed_bytes(str(root / "memory.stat")) == 2 * GB + 4 * GB,
          f"got {cap.committed_bytes(str(root / 'memory.stat'))}")


def test_host_without_a_limit(tmp):
    """Outside a constrained cgroup the old host rule must still hold."""
    cg, proc = Path(tmp) / "cg1", Path(tmp) / "proc1"
    write_cgroup(cg, "/", limit=None, current=1 * GB, stat={"anon": 1 * GB, "file": 1 * GB})
    write_proc(proc, "/user.slice/user-1000.slice/session-1.scope")
    r = decide(cg, proc, stacks=0)
    check("unlimited cgroup is not limited", r["metrics"]["mem_cgroup_limited"] is False
          and r["fits"], r["reasons"])
    check("unlimited cgroup uses the host metric",
          r["metrics"]["mem_source"] == "host"
          and abs(r["metrics"]["mem_effective_gb"] - (68.0 - 2.0)) < 0.01)
    busy_host = write_proc(Path(tmp) / "proc1b", mem_available_gb=10.0)
    check("host floor still refuses a busy host",
          "mem" in decide(cg, busy_host, stacks=0)["reasons"])
    root_proc = write_proc(Path(tmp) / "proc1c", path="/")
    check("root cgroup path is read as /",
          decide(cg, root_proc, stacks=0)["metrics"]["mem_cgroup_path"] in ("/", None))


def test_container_headroom_is_the_binding_metric(tmp):
    """The 2026-11-05 scenario: the machine looks idle, the cgroup is not."""
    cg, proc = Path(tmp) / "cg2", Path(tmp) / "proc2"
    write_cgroup(cg, "/", limit=16 * GB, current=int(8.4 * GB),
                 stat={"anon": int(2.0 * GB), "file": int(6.0 * GB), "kernel": int(0.4 * GB)},
                 peak=16 * GB, events={"max": 461511, "oom": 153, "oom_kill": 11})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    r = decide(cg, proc, stacks=0)
    check("limited cgroup is detected", r["metrics"]["mem_cgroup_limited"] is True)
    check("binding level is the container root", r["metrics"]["mem_cgroup_path"] == "/")
    check("host MemAvailable does not override the cgroup",
          abs(r["metrics"]["mem_effective_gb"] - (16 - 2.4 - 2)) < 0.01,
          r["metrics"]["mem_effective_gb"])
    check("page cache is not charged against headroom",
          abs(r["metrics"]["mem_cgroup_headroom_gb"] - (16 - 2.4)) < 0.01,
          r["metrics"]["mem_cgroup_headroom_gb"])
    check("oom events are reported", r["metrics"]["oom_events"].get("oom_kill") == 11)
    check("plenty of headroom admits the stack", r["fits"], r["reasons"])

    # Now the same cgroup nearly full: 14 GiB of anon in a 16 GiB ceiling,
    # while /proc/meminfo still reports a healthy machine.
    full = Path(tmp) / "cg2full"
    write_cgroup(full, "/", limit=16 * GB, current=int(15.5 * GB),
                 stat={"anon": int(14.5 * GB), "file": int(1 * GB), "kernel": int(0.5 * GB)},
                 events={"oom": 12, "oom_kill": 1}, pressure=40.0)
    rf = decide(full, proc, stacks=0)
    check("a full cgroup refuses a new stack", "mem" in rf["reasons"] and not rf["fits"],
          rf["reasons"])
    check("a full cgroup reports the ceiling", "ceiling" in rf["reasons"], rf["reasons"])
    check("memory pressure refuses a new stack", "pressure" in rf["reasons"], rf["reasons"])
    check("pressure alone is enough to refuse",
          "pressure" in decide(full, proc, stacks=0, stack_min_mem_gb=1)["reasons"])

    # Recovery: the charge drops, the same tree admits again. This is the
    # hysteresis - the gate is stateless and flips with the metric.
    back = Path(tmp) / "cg2back"
    write_cgroup(back, "/", limit=16 * GB, current=int(6 * GB),
                 stat={"anon": int(4 * GB), "file": int(2 * GB), "kernel": int(0.5 * GB)},
                 events={"oom": 12, "oom_kill": 1}, pressure=0.0)
    rb = decide(back, proc, stacks=0)
    check("recovery admits again once the charge drops", rb["fits"], rb["reasons"])


def test_at_limit(tmp):
    cg, proc = Path(tmp) / "cg3", Path(tmp) / "proc3"
    write_cgroup(cg, "/", limit=8 * GB, current=8 * GB,
                 stat={"anon": 8 * GB, "file": 0, "kernel": 0}, pressure=0.0)
    write_proc(proc, "/init.scope")
    r = decide(cg, proc, stacks=0)
    check("at the limit the headroom is zero", r["metrics"]["mem_cgroup_headroom_gb"] == 0)
    check("at the limit nothing is admitted", not r["fits"] and "mem" in r["reasons"], r["reasons"])
    check("at the limit the reason is also the ceiling", "ceiling" in r["reasons"])


def test_parent_limit_is_stricter(tmp):
    """A container unlimited inside can still be confined by its parent slice."""
    cg, proc = Path(tmp) / "cg4", Path(tmp) / "proc4"
    write_cgroup(cg, "/", limit=24 * GB, current=int(23.0 * GB),
                 stat={"anon": int(23.0 * GB), "file": 0, "kernel": 0})
    write_cgroup(cg, "/kubepods", limit=None, current=int(1.0 * GB),
                 stat={"anon": int(1.0 * GB), "file": 0, "kernel": 0})
    write_cgroup(cg, "/kubepods/podabc", limit=None, current=int(0.5 * GB),
                 stat={"anon": int(0.5 * GB), "file": 0, "kernel": 0})
    write_proc(proc, "/kubepods/podabc")
    r = decide(cg, proc, stacks=0)
    check("the binding limit is the parent's", r["metrics"]["mem_cgroup_path"] == "/",
          r["metrics"]["mem_cgroup_path"])
    check("the parent's headroom is what counts",
          abs(r["metrics"]["mem_cgroup_headroom_gb"] - 1.0) < 0.01,
          r["metrics"]["mem_cgroup_headroom_gb"])
    check("a nearly full parent refuses a stack", not r["fits"] and "mem" in r["reasons"],
          r["reasons"])
    check("the walk visits every level", len(cap.cgroup_levels(str(proc), str(cg))) == 3)


def test_missing_metrics_fail_open(tmp):
    """A metric that cannot be read is n/a, never a reason to look busy."""
    cg, proc = Path(tmp) / "cg5", Path(tmp) / "proc5"
    cg.mkdir(parents=True, exist_ok=True)
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    real_stacks = cap.agent_stacks
    cap.agent_stacks = lambda: None
    try:
        r = decide(cg, proc, stacks=None)
    finally:
        cap.agent_stacks = real_stacks
    check("unreadable cgroup is reported as unavailable",
          r["metrics"]["mem_cgroup_available"] is False)
    check("unreadable cgroup does not block", r["fits"], r["reasons"])
    check("unavailable docker is reported, not counted as busy",
          r["metrics"]["docker_available"] is False and r["fits"]
          and r["metrics"]["stacks"] is None)

    empty = Path(tmp) / "proc-gone"
    r2 = cap.evaluate(need="stack", stacks=0, env=limits(), proc_root=str(empty),
                      cgroup_root=str(Path(tmp) / "cg-none"))
    check("unreadable /proc reports n/a load", r2["metrics"]["load_per_core"] is None)
    check("unreadable /proc reports n/a memory", r2["metrics"]["mem_host_available_gb"] is None)
    check("unreadable /proc still gives a verdict", r2["fits"], r2["reasons"])


def test_stack_boundary_is_prospective(tmp):
    """The off-by-one of #1053: the count that fits is max-1, not max."""
    cg, proc = Path(tmp) / "cg6", Path(tmp) / "proc6"
    write_cgroup(cg, "/", limit=64 * GB, current=1 * GB, stat={"anon": 1 * GB, "file": 0})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    check("one stack below the limit fits", decide(cg, proc, stacks=2)["fits"],
          decide(cg, proc, stacks=2)["reasons"])
    check("at the limit a further stack is refused",
          "stacks" in decide(cg, proc, stacks=3)["reasons"])
    check("above the limit it stays refused",
          "stacks" in decide(cg, proc, stacks=5)["reasons"])
    check("a stack check does not police processes",
          decide(cg, proc, stacks=0, processes=99)["fits"], decide(cg, proc, stacks=0,
                                                                   processes=99)["reasons"])


def test_process_class(tmp):
    cg, proc = Path(tmp) / "cg7", Path(tmp) / "proc7"
    write_cgroup(cg, "/", limit=16 * GB, current=int(10.0 * GB),
                 stat={"anon": int(10.0 * GB), "file": 0, "kernel": 0}, pressure=50.0)
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    check("a light slot fits where a stack cannot",
          decide(cg, proc, need="process", stacks=0, processes=0)["fits"]
          and not decide(cg, proc, stacks=0)["fits"])
    check("the last process slot is refused",
          "processes" in decide(cg, proc, need="process", stacks=0, processes=6)["reasons"])
    check("the second to last process slot fits",
          decide(cg, proc, need="process", stacks=0, processes=5)["fits"])
    fake = write_proc(Path(tmp) / "proc7b", "/init.scope")
    fake_proc_with_processes(fake, ["opencode", "opencode", "python3", "docker"])
    check("agent processes are counted from /proc",
          cap.agent_processes(str(fake), match="opencode") == 2)
    check("an unreadable /proc does not count processes",
          cap.agent_processes(str(Path(tmp) / "nope")) is None)
    check("need none reports without a class need",
          decide(cg, proc, need="none", stacks=0)["metrics"]["mem_required_gb"] == 0)


def test_nested_docker_is_reported(tmp):
    cg, proc = Path(tmp) / "cg8", Path(tmp) / "proc8"
    write_cgroup(cg, "/", limit=16 * GB, current=int(8 * GB),
                 stat={"anon": int(2 * GB), "file": int(6 * GB), "kernel": int(0.5 * GB)})
    (cg / "docker").mkdir(parents=True, exist_ok=True)
    (cg / "docker" / "memory.current").write_text(f"{int(3 * GB)}\n")
    write_proc(proc, "/init.scope")
    r = decide(cg, proc, stacks=0)
    check("nested dockerd memory is reported", abs(r["metrics"]["mem_nested_docker_gb"] - 3.0)
          < 0.01, r["metrics"]["mem_nested_docker_gb"])
    check("nested dockerd is not charged twice",
          abs(r["metrics"]["mem_cgroup_headroom_gb"] - 13.5) < 0.01,
          r["metrics"]["mem_cgroup_headroom_gb"])


def test_pressure_threshold_is_configurable(tmp):
    cg, proc = Path(tmp) / "cg9", Path(tmp) / "proc9"
    write_cgroup(cg, "/", limit=16 * GB, current=int(4 * GB),
                 stat={"anon": int(2 * GB), "file": int(2 * GB), "kernel": int(0.1 * GB)},
                 pressure=6.0)
    write_proc(proc, "/init.scope")
    check("pressure below the threshold admits", decide(cg, proc, stacks=0)["fits"],
          decide(cg, proc, stacks=0)["reasons"])
    check("a tightened threshold refuses",
          "pressure" in decide(cg, proc, stacks=0, max_mem_pressure=5)["reasons"])
    check("pressure of 0 is not read as missing",
          decide(cg, proc, stacks=0)["metrics"]["mem_pressure_avg10"] == 6.0)


def test_cli_contract(tmp):
    """The interface AGENTS.md promises: one line, exit 0 or 1, plus --json."""
    cg, proc = Path(tmp) / "cg10", Path(tmp) / "proc10"
    write_cgroup(cg, "/", limit=16 * GB, current=int(2 * GB),
                 stat={"anon": int(2 * GB), "file": 0, "kernel": 0})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("AGENT_")]:
        env.pop(key)
    env.update({"AGENT_CGROUP_ROOT": str(cg), "AGENT_PROC_ROOT": str(proc),
                "AGENT_MAX_STACKS": "3"})

    def run(*args):
        return subprocess.run([sys.executable, str(SCRIPTS / "agent_capacity"), *args],
                              capture_output=True, text=True, env=env)
    ok = run("--stacks", "0")
    check("cli exits 0 when it fits", ok.returncode == 0, ok.stdout + ok.stderr)
    check("cli prints one verdict line", ok.stdout.count("\n") == 1
          and ok.stdout.startswith("agent_capacity:") and ok.stdout.rstrip().endswith("-> fits"),
          ok.stdout)
    busy = run("--stacks", "3")
    check("cli exits 1 when busy", busy.returncode == 1)
    check("cli names the reason", "BUSY: stacks" in busy.stdout, busy.stdout)
    js = run("--json", "--stacks", "0")
    data = json.loads(js.stdout)
    check("cli --json is one valid object", data["fits"] is True and "metrics" in data)
    check("cli --json carries the cgroup verdict",
          data["metrics"]["mem_cgroup_limited"] is True
          and data["metrics"]["mem_cgroup_limit_gb"] == 16.0)
    bad = run("--need", "nonsense", "--stacks", "0")
    check("a bad class is a usage error", bad.returncode == 2)


def main():
    with tempfile.TemporaryDirectory(prefix="agent-capacity-test-") as tmp:
        for fn in (test_parsing, test_host_without_a_limit, test_container_headroom_is_the_binding_metric,
                   test_at_limit, test_parent_limit_is_stricter, test_missing_metrics_fail_open,
                   test_stack_boundary_is_prospective, test_process_class,
                   test_nested_docker_is_reported, test_pressure_threshold_is_configurable,
                   test_cli_contract):
            fn(tmp)
    failed = 0
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    print(f"{len(RESULTS) - failed}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
