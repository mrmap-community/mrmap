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
                 events=None, pressure=None, cpu_pressure=None):
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
    if cpu_pressure is not None:
        (d / "cpu.pressure").write_text(
            f"some avg10={cpu_pressure} avg60={cpu_pressure} avg300={cpu_pressure} total=0\n"
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
    """Threshold overrides with every knob pinned, so ambient env cannot leak.

    AGENT_MIN_DISK_GB is pinned OFF, at 0 rather than the gate's 100 GiB default,
    and that is the one number here that is about the machine and not about the
    gate. A constant would have to be guessed: pinned to 1 GiB this suite still
    failed on a host with 0.4 GiB free, so the pin is "no disk requirement", which
    no host can violate. Disk free is the only metric `agent_capacity` reads from the
    real host: memory comes from a fabricated /proc, the cgroup from a fabricated
    tree, stacks from a passed count -- but disk is `shutil.disk_usage("/")`, with
    no seam to fake it. Pinning the real default here therefore made every check
    in this file depend on where it happened to run, and it showed: the same 71
    checks passed on the deployment host (1.7 TiB free) and failed 19 of them on a
    CI runner (85 GiB free). A check about memory or stacks must fail for the
    reason it is about.

    The disk dimension itself is not skipped -- see
    `test_disk_is_measured_not_assumed`, which tests it with thresholds derived
    from the host, so it behaves the same on a runner and on a server. Do not
    restore this to 100 to "test the real threshold": that reattaches the whole
    suite to the machine it runs on.
    """
    base = {
        "AGENT_MAX_LOAD_PER_CORE": "1.5", "AGENT_MIN_DISK_GB": "0",
        "AGENT_MAX_CPU_PRESSURE": "10",
        "AGENT_MAX_STACKS": "3", "AGENT_MAX_PROCESSES": "6",
        "AGENT_STACK_MIN_MEM_GB": "6", "AGENT_SUITE_MIN_MEM_GB": "8",
        "AGENT_PROCESS_MIN_MEM_GB": "2",
        "AGENT_MIN_MEM_GB": "16", "AGENT_MEM_RESERVE_GB": "2",
        "AGENT_MEM_NEAR_CEILING_PCT": "90", "AGENT_MAX_MEM_PRESSURE": "10",
    }
    for key, value in kwargs.items():
        name = "AGENT_" + key.upper()
        base[name] = "" if value is None else str(value)
    return base


def decide(cgroup, proc, need="stack", stacks=0, processes=None, **thresholds):
    """One verdict against fabricated metrics.

    No `env` parameter: an earlier version took one and dropped it on the floor,
    because the thresholds below always rebuild the environment. Callers who need
    a threshold they did not name should pass it as a keyword.
    """
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
    # AGENT_MIN_DISK_GB turns the gate's 100 GiB requirement off, because disk is
    # the one metric read from the machine itself and no constant is small enough
    # for every host. See limits(): the checks below are about stacks and memory.
    env.update({"AGENT_CGROUP_ROOT": str(cg), "AGENT_PROC_ROOT": str(proc),
                "AGENT_MAX_STACKS": "3", "AGENT_MIN_DISK_GB": "0"})

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


def test_suite_class(tmp):
    """The suite arm of #1055 is heavier than a targeted check and must be
    refused where a targeted check would still be admitted."""
    cg, proc = Path(tmp) / "cg11", Path(tmp) / "proc11"
    # 16 GiB ceiling, 6.5 GiB unreclaimable: headroom 9.5, effective 7.5 -
    # room for a 6 GiB stack, not for an 8 GiB full-suite run.
    write_cgroup(cg, "/", limit=16 * GB, current=int(10 * GB),
                 stat={"anon": int(6.0 * GB), "file": int(3.5 * GB), "kernel": int(0.5 * GB)})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    rs = decide(cg, proc, need="suite", stacks=0)
    check("a suite is refused where a targeted stack fits",
          not rs["fits"] and "mem" in rs["reasons"] and decide(cg, proc, stacks=0)["fits"],
          rs["reasons"])
    check("the suite requirement is the suite threshold",
          rs["metrics"]["mem_required_gb"] == 8, rs["metrics"]["mem_required_gb"])
    deep = Path(tmp) / "cg11deep"
    write_cgroup(deep, "/", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0})
    check("a deep-idle cgroup admits the suite", decide(deep, proc, need="suite", stacks=0)["fits"])
    check("the stacks rule polices suites too",
          "stacks" in decide(cg, proc, need="suite", stacks=3)["reasons"])
    check("the ceiling rule polices suites too",
          "ceiling" in decide(cg, proc, need="suite", stacks=0,
                              mem_near_ceiling_pct=50)["reasons"]
          or "ceiling" in decide(deep, proc, need="suite", stacks=0,
                                 mem_near_ceiling_pct=10)["reasons"])
    unlimited = Path(tmp) / "cg11free"
    write_cgroup(unlimited, "/", limit=None, current=int(3.0 * GB),
                 stat={"anon": int(3.0 * GB), "file": 0, "kernel": 0})
    busy_host = write_proc(Path(tmp) / "proc11b", mem_available_gb=10.0)
    check("on an unrestricted host the suite pays the host floor too",
          "mem" in decide(unlimited, busy_host, need="suite", stacks=0)["reasons"],
          decide(unlimited, busy_host, need="suite", stacks=0)["reasons"])


def test_agent_stack_counting(tmp):
    """Both naming schemes an agent stack actually has are counted, nothing
    else is: the repository convention and the AO-generated worktree name."""
    projects = ["mrmap-agent-852-1103", "mrmap-ao-27b9cb6b0f67",
                "mrmap-dev", "mrmapagent-nope", "backend", ""]
    check("agent stacks are counted by project prefix", cap.count_stacks(projects) == 2,
          cap.count_stacks(projects))
    check("an empty project list counts none", cap.count_stacks([]) == 0)


def test_wait_queues_without_displacing(tmp):
    """--wait turns a refusal into a bounded queue: exit stays 1 while busy,
    the stdout verdict stays exactly one line or one JSON object, and a
    refusal clears on its own when the room appears."""
    cg, proc = Path(tmp) / "cg12", Path(tmp) / "proc12"
    write_cgroup(cg, "/", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    env = dict(os.environ)
    for key in [k for k in env if k.startswith("AGENT_")]:
        env.pop(key)
    # AGENT_MIN_DISK_GB turns the gate's 100 GiB requirement off, because disk is
    # the one metric read from the machine itself and no constant is small enough
    # for every host. See limits(): the checks below are about stacks and memory.
    env.update({"AGENT_CGROUP_ROOT": str(cg), "AGENT_PROC_ROOT": str(proc),
                "AGENT_MAX_STACKS": "3", "AGENT_MIN_DISK_GB": "0"})

    def run(*args):
        return subprocess.run([sys.executable, str(SCRIPTS / "agent_capacity"), *args],
                              capture_output=True, text=True, env=env, timeout=60)
    busy = run("--stacks", "3", "--wait", "1")
    check("a waited-through refusal still exits 1", busy.returncode == 1)
    check("wait progress goes to stderr", "waiting" in busy.stderr, busy.stderr)
    check("wait keeps stdout to one verdict line", busy.stdout.count("\n") == 1
          and busy.stdout.startswith("agent_capacity:"), busy.stdout)
    check("a waited refusal names its reason on the final line",
          "BUSY: stacks" in busy.stdout, busy.stdout)
    js = run("--json", "--stacks", "3", "--wait", "1")
    check("wait with --json prints exactly one JSON object on stdout",
          js.returncode == 1 and json.loads(js.stdout)["fits"] is False)
    fits = run("--wait", "1", "--stacks", "0")
    check("a fitting job is not delayed by --wait", fits.returncode == 0
          and fits.stderr == "", fits.stderr)


def test_disk_is_measured_not_assumed(tmp):
    """Disk free has no fake root, so the thresholds around it are host-relative.

    Memory, load, pressure and the cgroup come from fixtures and stacks are passed
    in; disk is `shutil.disk_usage("/")` on the machine running the suite. That is
    the one input this file cannot fabricate, and a fixed 100 GiB threshold
    therefore attached every other check to the host as well: 71 green on the
    deployment host with 1.7 TiB free, 19 red on a CI runner with 85 GiB. The
    answer is not to skip the dimension but to derive its thresholds from what the
    host reports, so the checks say the same thing on a runner and on a server.
    """
    cg, proc = Path(tmp) / "cg13", Path(tmp) / "proc13"
    write_cgroup(cg, "/", limit=16 * GB, current=int(2 * GB),
                 stat={"anon": int(2 * GB), "file": 0, "kernel": 0})
    write_proc(proc, "/init.scope", mem_available_gb=64.0)
    free = cap.disk_free_gb()
    if free is None:                      # / cannot be stat'd: say so, do not divide by it
        check("disk free is readable on the host running the suite", False, "unreadable")
        return
    check("disk free is readable on the host running the suite", free > 0, free)
    check("enough free disk is not a reason",
          "disk" not in decide(cg, proc, stacks=0, min_disk_gb=max(0.1, free / 2))["reasons"])
    tight = decide(cg, proc, stacks=0, min_disk_gb=free + 1)["reasons"]
    check("too little free disk refuses, and says only that", tight == ["disk"], tight)
    # The gate's own default is pinned without depending on the host's disk: the
    # threshold is a number in the verdict, so a CI runner can check the deployment
    # floor it will never itself satisfy.
    bare = cap.evaluate(need="stack", stacks=0, env={}, proc_root=str(proc),
                        cgroup_root=str(cg))
    check("the gate's disk default is the documented 100 GiB",
          bare["metrics"]["disk_min_gb"] == 100.0, bare["metrics"]["disk_min_gb"])
    check("that metric is the host's, not the fixture's",
          abs(bare["metrics"]["disk_free_gb"] - free) < 0.01,
          f"{bare['metrics']['disk_free_gb']} vs {free}")


def test_cpu_admission_is_cgroup_scoped(tmp):
    """The 2026-11-11 scenario, reversed: the cgroup is idle, the host is not.

    `/proc/loadavg` has no cgroup scope - a shared host's tenants run the gate
    down while this cgroup has the machine's CPU waiting unused. CPU PSI of
    this cgroup (and, worst-case, its parents) is what a new job would meet;
    the load average keeps deciding only where no cpu.pressure is readable.
    """
    cg, proc = Path(tmp) / "cg14", Path(tmp) / "proc14"
    write_cgroup(cg, "/", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0},
                 cpu_pressure=4.0)
    # load 1000 refuses at max_load on any core count this suite runs on
    write_proc(proc, "/init.scope", mem_available_gb=64.0, load15=1000.0)
    r = decide(cg, proc, stacks=0)
    check("an idle cgroup on a busy host admits", r["fits"], r["reasons"])
    check("the stall number is reported",
          r["metrics"]["cpu_pressure_avg10"] == 4.0
          and r["metrics"]["cpu_pressure_max"] == 10.0)
    line = cap.verdict_line(r)
    check("the verdict reads the cgroup's stall, not the host's load",
          "cpu 4.0% stall" in line and "host load" in line, line)

    scg, sproc = Path(tmp) / "cg14s", Path(tmp) / "proc14s"
    write_cgroup(scg, "/", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0}, cpu_pressure=60.0)
    write_proc(sproc, "/init.scope", mem_available_gb=64.0, load15=1.0)
    r = decide(scg, sproc, stacks=0)
    check("a stalling cgroup refuses a new stack",
          "cpu" in r["reasons"] and "load" not in r["reasons"], r["reasons"])
    r = decide(cg, proc, stacks=0, max_cpu_pressure=2)
    check("the CPU pressure threshold is configurable",
          "cpu" in r["reasons"], r["reasons"])

    # a parent stalling at 30% stalls every task below it, whatever the
    # container itself reports
    pcg, pproc = Path(tmp) / "cg14p", Path(tmp) / "proc14p"
    write_cgroup(pcg, "/", limit=64 * GB, current=8 * GB,
                 stat={"anon": 8 * GB, "file": 0, "kernel": 0}, cpu_pressure=2.0)
    write_cgroup(pcg, "/slice.slice", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0}, cpu_pressure=30.0)
    write_proc(pproc, "/slice.slice", mem_available_gb=64.0, load15=1.0)
    r = decide(pcg, pproc, stacks=0)
    check("the worst parent's stall binds the child",
          "cpu" in r["reasons"], r["reasons"])

    # without cpu.pressure the host-wide load average still decides
    ocg, oproc = Path(tmp) / "cg14f", Path(tmp) / "proc14f"
    write_cgroup(ocg, "/", limit=16 * GB, current=2 * GB,
                 stat={"anon": 2 * GB, "file": 0, "kernel": 0})
    write_proc(oproc, "/init.scope", mem_available_gb=64.0, load15=1000.0)
    r = decide(ocg, oproc, stacks=0)
    check("no cpu.pressure falls back to the load average",
          "load" in r["reasons"], r["reasons"])
    check("the fallback reports no stall number",
          r["metrics"]["cpu_pressure_avg10"] is None)


def main():
    with tempfile.TemporaryDirectory(prefix="agent-capacity-test-") as tmp:
        for fn in (test_parsing, test_host_without_a_limit, test_container_headroom_is_the_binding_metric,
                   test_at_limit, test_parent_limit_is_stricter, test_missing_metrics_fail_open,
                   test_stack_boundary_is_prospective, test_process_class,
                   test_nested_docker_is_reported, test_pressure_threshold_is_configurable,
                   test_cli_contract, test_suite_class, test_agent_stack_counting,
                   test_wait_queues_without_displacing, test_disk_is_measured_not_assumed,
                   test_cpu_admission_is_cgroup_scoped):
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
