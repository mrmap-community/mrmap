#!/usr/bin/env python3
"""Offline checks for scripts/schedule_optimizer_spike (issue #1333).

Runs without docker, without network and without `gh`: the simulator, the
two optimizers, the cadence proof and the stop rule are exercised on the
tool's own fixtures. The promise under test is the one the design spike is
built on: a deterministic baseline-vs-recommended comparison, in which
nothing but the PHASE ever moves (cadence proof), and in which the optimizer
stays silent when the evidence is not measured. One end-to-end pass over the
full 43k-schedule fixture runs here as well, so the deliverable the issue
asks for ("offline test fixture including 43k schedules") is executed, not
just shipped.

Run from the repository root:
`python3 scripts/test_schedule_optimizer_spike.py`.
Exit 0 when every check passes, 1 with the failed ones listed.
"""

import contextlib
import importlib.machinery
import importlib.util
import io
from datetime import datetime
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SPIKE = SCRIPTS / "schedule_optimizer_spike.py"

loader = importlib.machinery.SourceFileLoader("schedule_optimizer_spike",
                                              str(SPIKE))
spec = importlib.util.spec_from_loader("schedule_optimizer_spike", loader)
S = importlib.util.module_from_spec(spec)
loader.exec_module(S)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))


def horizon(days=2):
    tz, _ = S.get_tz()
    t0 = int(datetime(2026, 11, 2, tzinfo=tz).timestamp()) if tz \
        else int(datetime(2026, 11, 2).timestamp())
    return tz, t0, days


def run_quiet(argv):
    """`S.run` prints its report; the suite only wants the result."""
    with contextlib.redirect_stdout(io.StringIO()):
        return S.run(argv)


# ------------------------------------------------------------------ cron --

def test_cron():
    p = S.parse_cron("*/30 * * * *")
    check("cron: */30 parses minutes", p["minutes"] == [0, 30], p["minutes"])
    p = S.parse_cron("0 2,8,14,20 * * *")
    check("cron: hour list parses", p["hours"] == [2, 8, 14, 20])
    try:
        S.parse_cron("55-5 * * * *")
        check("cron: wrapping range rejected", False)
    except ValueError:
        check("cron: wrapping range rejected", True)

    tz, t0, days = horizon()
    occ = S.occurrences("0 2,8,14,20 * * *", t0, t0 + days * 86400, tz)
    check("cron: 4 occurrences per day", len(occ) == 8, len(occ))
    occ2 = S.occurrences("7 * * * *", t0, t0 + days * 86400, tz)
    check("cron: hourly gives 48", len(occ2) == 48, len(occ2))


def test_dst():
    tz, name = S.get_tz()
    if name != S.DEFAULT_TZ:
        check("dst: skipped (no Europe/Berlin tzdata here)", True)
        return
    # 2027-03-28 is the spring change in Europe/Berlin: 02:30 does not exist
    t0 = int(datetime(2027, 3, 26, tzinfo=tz).timestamp())
    occ = S.occurrences("30 2 * * *", t0, t0 + 5 * 86400, tz)
    days = sorted({datetime.fromtimestamp(e, tz).day for e in occ})
    check("dst: nonexistent 02:30 on the spring day is skipped",
          28 not in days and len(days) == 4, "days with a run: %s" % days)
    # 2026-10-25 is the autumn change: 02:30 exists twice, taken on its
    # first pass - exactly one occurrence that day
    t0 = int(datetime(2026, 10, 24, tzinfo=tz).timestamp())
    occ = S.occurrences("30 2 * * *", t0, t0 + 4 * 86400, tz)
    oct25 = [e for e in occ
             if datetime.fromtimestamp(e, tz).day == 25]
    check("dst: autumn duplicate taken once", len(oct25) == 1, len(oct25))


# ------------------------------------------------------------- classify --

def test_classify_and_shift():
    info = S.classify_str("*/30 * * * *")
    check("classify: */30 is subhourly with cycle 30",
          info and info["kind"] == "subhourly" and info["period"] == 30)
    info = S.classify_str("0 * * * *")
    check("classify: fixed minute hourly", info
          and info["kind"] == "hourly" and info["period"] == 60)
    info = S.classify_str("0 2 * * *")
    check("classify: single wall time is daily",
          info and info["kind"] == "daily" and info["period"] == 1440)
    info = S.classify_str("0 2,8,14,20 * * *")
    check("classify: evenly spaced hour list",
          info and info["kind"] == "hourlylist" and info["period"] == 360)
    info = S.classify_str("0 8 * * 1")
    check("classify: weekday anchored is weekly",
          info and info["kind"] == "weekly")

    p = S.parse_cron("*/30 * * * *")
    check("shift: subhourly rotates the grid",
          S.shifted_pattern(p, 7) == "7,37 * * * *",
          S.shifted_pattern(p, 7))
    p = S.parse_cron("0 8 * * *")
    check("shift: daily +90 is 09:30",
          S.shifted_pattern(p, 90) == "30 9 * * *",
          S.shifted_pattern(p, 90))
    p = S.parse_cron("0 8 * * 1")
    check("shift: weekly shift stays inside its day",
          S.shifted_pattern(p, 360) is None
          or S.parse_cron(S.shifted_pattern(p, 360))["dows"] == [1],
          S.shifted_pattern(p, 360))
    check("shift: beyond the allowed span is rejected",
          S.shifted_pattern(p, 361) is None)
    check("shift: unsupported shape has no candidate",
          S.shifted_pattern(S.parse_cron("0-5 3 * * *"), 10) is None
          or S.classify_str("0-5 3 * * *") is None)


# ---------------------------------------------------------- fixtures ----

def test_fixture():
    full = S.build_fixture("full43k", 1333)
    check("fixture: full43k holds 43,478 schedules",
          len(full) == 43478, len(full))
    queues = {s["queue"] for s in full}
    check("fixture: uses the monitoring/update/default queues of the app",
          queues == {"monitoring", "update", "default"}, queues)
    locked = [s for s in full if s["kind"] == "csw-update"]
    check("fixture: the pinned csw-update schedules are locked",
          locked and all(s["locked"] for s in locked))
    f2 = S.build_fixture("full43k", 1333)
    check("fixture: same seed, same fixture",
          [s["pattern"] for s in full[:200]]
          == [s["pattern"] for s in f2[:200]])


# ------------------------------------------------------ cadence proof ----

def test_cadence_proof_rejects_a_real_change():
    """The proof must catch a cadence change, not wave every pattern
    through: hand it a change that halves the frequency and expect exactly
    that one rejection."""
    tz, t0, days = horizon()
    schedules = [{"id": 0, "kind": "wms-monitor", "queue": "monitoring",
                  "pattern": "*/30 * * * *", "occupancy": 2.4, "org": 0,
                  "locked": False, "window": None}]
    changes = {0: "0 * * * *"}  # */30 -> hourly: a cadence change!
    checked, rejected = S.cadence_proof(schedules, dict(changes), t0, days, tz)
    check("cadence proof: a frequency change is rejected",
          checked == 1 and len(rejected) == 1, "%d/%d" % (checked, len(
              rejected)))
    changes = {0: "7,37 * * * *"}  # a pure phase rotation
    checked, rejected = S.cadence_proof(schedules, changes, t0, days, tz)
    check("cadence proof: a phase rotation passes",
          checked == 1 and not rejected and changes[0] == "7,37 * * * *")


# --------------------------------------------------------------- rules ----

def test_budget_and_locks():
    tz, t0, days = horizon(1)
    schedules = []
    for i in range(40):
        schedules.append({"id": i, "kind": "wms-monitor",
                          "queue": "monitoring", "pattern": "0 * * * *",
                          "occupancy": 2.4, "org": i % 4,
                          "locked": i == 0, "window": None})
    changed = S.optimize_greedy(schedules, t0, days, tz, budget=7)
    check("greedy: honours the change budget", len(changed) <= 7,
          len(changed))
    check("greedy: never touches a locked schedule", 0 not in changed)
    shapes_ok = all(S.classify_str(pat) is not None
                    and S.classify_str(pat)["kind"] == "hourly"
                    for pat in changed.values())
    check("greedy: every change keeps the hourly shape", shapes_ok,
          sorted(set(changed.values())))


def test_window_refusal():
    """A family whose members cannot all stay inside their window is
    refused whole (the all-or-nothing rule), not half-moved."""
    tz, t0, days = horizon(1)
    narrow = (22 * 60, 22 * 60 + 10)  # ten minutes at 22:00 only
    schedules = [{"id": i, "kind": "csw-harvest", "queue": "default",
                  "pattern": "0 22 * * *", "occupancy": 900, "org": 0,
                  "locked": False, "window": narrow}
                 for i in range(6)]
    changed, refused = S.optimize_constrained(schedules, t0, days, tz, 100)
    check("constrained: a saturated window refuses the family whole",
          not changed and len(refused) == 1
          and "window" in refused[0]["reason"], refused)


def test_convoy_improvement():
    """The spike's claim in miniature: a convoy of identical hourly probes
    on the full hour, with worker occupancy, queues up behind itself; the
    greedy phase spread must lower the p95 wait it causes and change no
    cadence."""
    tz, t0, days = horizon(2)
    schedules = [{"id": i, "kind": "wms-monitor", "queue": "monitoring",
                  "pattern": "0 * * * *", "occupancy": 30.0, "org": i % 3,
                  "locked": False, "window": None}
                 for i in range(60)]
    before = S.simulate(schedules, [], t0, days, 4, tz)
    changed = S.optimize_greedy(schedules, t0, days, tz, budget=200)
    after_sched = [{**s, "pattern": changed.get(s["id"], s["pattern"])}
                   for s in schedules]
    checked, rejected = S.cadence_proof(schedules, dict(changed), t0, days,
                                        tz)
    after = S.simulate(after_sched, [], t0, days, 4, tz)
    check("convoy: the greedy moves schedules", len(changed) > 0,
          len(changed))
    check("convoy: every move survives the cadence proof",
          checked == len(changed) and not rejected,
          "%d rejected" % len(rejected))
    check("convoy: p95 wait drops",
          after["wait_p95"] < before["wait_p95"],
          "%s -> %s" % (before["wait_p95"], after["wait_p95"]))
    check("convoy: cadence violations drop",
          after["cadence_violations"] <= before["cadence_violations"],
          "%d -> %d" % (before["cadence_violations"],
                        after["cadence_violations"]))


# ----------------------------------------------------------- stop rule ----

def test_stop_rule():
    out = run_quiet(["--fixture", "mvp", "--days", "1",
                     "--telemetry", "missing"])
    check("stop: without measured telemetry the optimizer refuses",
          out["status"] == "cannot_optimize_reliably"
          and out["changes"] == 0, out["status"])
    check("stop: the refusal names the coverage it saw",
          out["measured_coverage"] == 0.0, out["measured_coverage"])


def test_determinism():
    a = run_quiet(["--fixture", "mvp", "--days", "2", "--algorithm", "greedy",
                   "--json"])
    b = run_quiet(["--fixture", "mvp", "--days", "2", "--algorithm", "greedy",
                   "--json"])
    check("determinism: same arguments, same report digest",
          a["digest"] == b["digest"], "%s vs %s" % (a["digest"], b["digest"]))


# --------------------------------------------------------------- 43k ------

def test_full43k():
    """The end-to-end deliverable: 43,478 schedules, both alternatives,
    the proof, and the numbers the design document quotes are produced by
    this run class."""
    out = run_quiet(["--fixture", "full43k", "--days", "1", "--json"])
    check("43k: the run optimizes with a verified improvement",
          out["status"] == "OPTIMIZED", out["status"])
    check("43k: fixture size is the reported deployment size",
          out["schedules"] == 43478, out["schedules"])
    for name in ("greedy", "constrained"):
        v = out["variants"][name]
        check("43k/%s: no change fails the cadence proof" % name,
              not v["cadence_rejected"], v["cadence_rejected"][:2])
        check("43k/%s: changes respect the budget" % name,
              v["changes"] <= 5000, v["changes"])
        check("43k/%s: p95 wait improves" % name,
              v["metrics"]["wait_p95"] < out["baseline"]["wait_p95"],
              "%s vs %s" % (v["metrics"]["wait_p95"],
                            out["baseline"]["wait_p95"]))
    check("43k: a recommendation is named", out["recommended"] in
          ("greedy", "constrained"), out["recommended"])


def main():
    test_cron()
    test_dst()
    test_classify_and_shift()
    test_fixture()
    test_cadence_proof_rejects_a_real_change()
    test_budget_and_locks()
    test_window_refusal()
    test_convoy_improvement()
    test_stop_rule()
    test_determinism()
    test_full43k()
    failed = 0
    width = max(len(name) for name, _, _ in RESULTS)
    for name, ok, detail in RESULTS:
        if not ok:
            failed += 1
            print("FAIL %s %s" % (name.ljust(width), detail))
    print("%d of %d checks passed." % (len(RESULTS) - failed, len(RESULTS)))
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
