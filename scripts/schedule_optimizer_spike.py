#!/usr/bin/env python3
"""schedule_optimizer_spike: offline design spike for #1333 (V3, design only).

Maintenance/design tool carried by this repository; run it as
`python3 scripts/schedule_optimizer_spike.py` from the repository root. It
exists to make the V3 idea of issue #1333 - an opt-in optimizer that shifts
the PHASE of authorized monitoring/update/harvest schedules without ever
touching their cadence - discussable against numbers instead of vibes. It is
a SPIKE: it simulates an offline fixture and never touches a database, a
broker, Django or the network. Nothing here is runtime implementation; the
issue and `docs/source/development/schedule-optimization-v3.rst` say which
stage gates any real implementation would have to pass first (notably the
measured telemetry of #1330/#126... - see #1330/#1326 - which this host has
no way to observe).

What one run answers, deterministically:

  - a FIXTURE in the shape the epic #1324 reported for a live deployment
    (43,478 enabled settings across the queues of `MrMap/celery_queues.py`),
    plus a small `mvp` fixture for the test suite;
  - a MULTI-QUEUE simulation: FIFO per queue, one shared worker slot pool
    consumed round-robin over the queues, which is how the stock worker of
    `docker-compose.yml` (no `-Q`) really behaves (#1040);
  - two OPTIMIZER alternatives over the same evidence: a greedy phase-spread
    under a change budget, and a constrained even phase packing per cadence
    family - the deliverable "validated algorithm alternatives";
  - OBJECTIVE METRICS: p95 queue wait, cadence-deadline violations, peak
    worker duty, number of changes;
  - a STOP rule: without enough measured worker-occupancy evidence the
    optimizer must answer `cannot optimize reliably` and change nothing
    (`--telemetry missing` demonstrates exactly that);
  - a CADENCE PROOF: every changed schedule is recounted per full natural
    calendar unit (day / ISO week / calendar month) over a padded window, and
    a change that alters any per-unit count is rejected. A phase shift may
    move WHEN a run happens, never HOW OFTEN.

Determinism: no wall-clock, no threading, one seeded RNG for the fixture,
sorted iteration everywhere; identical arguments print an identical report
whose SHA-256 digest the report names. `scripts/test_schedule_optimizer_spike.py`
holds that promise down offline.

Usage:
  python3 scripts/schedule_optimizer_spike.py [--fixture mvp|full43k]
      [--days N] [--workers W] [--telemetry measured|missing]
      [--algorithm greedy|constrained|both] [--change-budget N]
      [--optimize-org K] [--seed N] [--min-measured-coverage F]
      [--improvement-threshold F] [--json] [--out FILE]

Numbers in the fixture are historical rig priors from epic #1324 used as
validation inputs of this spike - they are not application defaults and not
proof about any real deployment.
"""

import argparse
import hashlib
import heapq
import json
import math
import random
import sys
from collections import deque
from datetime import date, datetime, timedelta

try:  # wall-time semantics need tzdata; without it the fixture runs in UTC
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

DEFAULT_TZ = "Europe/Berlin"
FALLBACK_TZ = "UTC"

# The queue order of one shared worker pool. A stock worker consumes every
# declared queue (MrMap/celery_queues.py, #1040); the simulator hands free
# slots to these queues round-robin, which is the fairness the issue names as
# a hard constraint. Queues absent from the fixture (db-routines here carries
# only event traffic) keep their place in the rotation.
QUEUE_ORDER = ["db-routines", "monitoring", "update", "default", "download",
               "harvest-import"]

# Composition the epic #1324 reported for one live deployment ("~13,678 WMS
# monitoring + updates each; ~8,007 WFS monitoring + updates each; ~100 other
# settings" on 43,478 enabled settings). The pattern shares below are the
# spike's own construction; the worker-occupancy priors (2.4 s monitoring,
# 0.6 s update) are the epic's historical rig priors used as validation input
# only - see the epic's warning that they are never trusted defaults.
KINDS = [
    # kind, queue, occupancy prior s, weight (settings), tz, window, patterns
    ("wms-monitor", "monitoring", 2.4, 13678, None, [
        ("0 2,8,14,20 * * *", 0.93), ("0 * * * *", 0.01),
        ("15 * * * *", 0.01), ("0 8 * * *", 0.05)]),
    ("wfs-monitor", "monitoring", 2.4, 8007, None, [
        ("0 2,8,14,20 * * *", 0.93), ("0 * * * *", 0.01),
        ("45 * * * *", 0.01), ("30 7 * * *", 0.05)]),
    ("wms-update", "update", 0.6, 13678, None, [
        ("0 2 * * *", 0.70), ("0 */4 * * *", 0.20), ("30 1 * * *", 0.10)]),
    ("wfs-update", "update", 0.6, 8007, None, [
        ("0 3 * * *", 0.70), ("30 */4 * * *", 0.20), ("0 4 * * *", 0.10)]),
    ("csw-monitor", "monitoring", 2.4, 36, None, [("0 6 * * *", 1.0)]),
    # pinned: the spike marks csw-update locked - the administrator fixed it
    # for a legal reporting window; a future optimizer must leave it alone.
    ("csw-update", "update", 0.6, 36, "locked", [("0 5 * * *", 1.0)]),
    # harvesting occupies the worker far longer than a probe; it runs in the
    # nightly maintenance window 20:00-06:00 of this fixture.
    ("csw-harvest", "default", 900, 36, {"night": True},
     [("0 22 * * *", 0.70), ("0 23 * * *", 0.30)]),
]
FULL43K_TOTAL = 43478  # 13678*2 + 8007*2 + 108; the epic's reported size

NIGHT_WINDOW = (20 * 60, 30 * 60)  # 20:00 -> 06:00 (wraps midnight)

# event-driven background work arriving independent of any schedule the
# optimizer may shift: user imports, alerts refresh, publish runs. The epic's
# "concurrent event-driven/harvest demand" precondition. Distributed over a
# diurnal profile; still deterministic through the seed.
EVENT_RATE_PER_HOUR = {h: (40 if 8 <= h < 18 else 8) for h in range(24)}
EVENT_QUEUES = ["default", "db-routines"]
EVENT_OCC = 5  # seconds of worker time per event task


# --------------------------------------------------------------------- cron --

def parse_field(token, lo, hi):
    """Values of one cron field; supports `*`, `*/n`, `a`, `a-b`, `a-b/n` and
    comma lists of those. The fixture uses no other shape, and anything else
    raises so the spike can never silently misread a pattern."""
    values = set()
    for part in token.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_text = part.split("/", 1)
            step = int(step_text)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            if "/" in token:
                raise ValueError("step needs a range or *")
            start = end = int(part)
        if start > end:
            raise ValueError("wrapping ranges are not supported: %r" % token)
        values.update(range(start, end + 1, step))
    return sorted(v for v in values if lo <= v <= hi)


def parse_cron(pattern):
    """Parse the five-field subset the fixture uses. Returns the field value
    sets and the shape flags the classifier and the window rule need."""
    fields = pattern.split()
    if len(fields) != 5:
        raise ValueError("need five fields: %r" % pattern)
    minute, hour, dom, month, dow = fields
    if month != "*":
        raise ValueError("month field is not supported: %r" % pattern)
    return {
        "pattern": pattern,
        "minutes": parse_field(minute, 0, 59),
        "hours": parse_field(hour, 0, 23),
        "doms": parse_field(dom, 1, 31),
        "dom_star": dom == "*",
        "months": list(range(1, 13)),
        "dows": [(v % 7) for v in parse_field(dow, 0, 7)] if dow != "*" else None,
        "dow_star": dow == "*",
    }


def pattern_matches_day(parsed, day):
    """Whether the dom/dow/month part admits one local calendar day, with the
    cron rule that two restricted fields select the union."""
    if day.month not in parsed["months"]:
        return False
    dom_ok = parsed["dom_star"] or day.day in parsed["doms"]
    dow = day.isoweekday() % 7  # cron: sunday is 0
    dow_ok = parsed["dow_star"] or dow in parsed["dows"]
    if not parsed["dom_star"] and not parsed["dow_star"]:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def get_tz():
    if ZoneInfo is not None:
        try:
            return ZoneInfo(DEFAULT_TZ), DEFAULT_TZ
        except Exception:
            pass
    return (ZoneInfo(FALLBACK_TZ) if ZoneInfo else None), FALLBACK_TZ


def day_occurrence_minutes(parsed, day):
    """Wall-time (hour, minute) pairs of the pattern on one matching day."""
    if not pattern_matches_day(parsed, day):
        return []
    return [(h, m) for h in parsed["hours"] for m in parsed["minutes"]]


_occurrence_cache = {}


def occurrences(pattern, t_start, t_end, tz):
    """Epoch seconds of every occurrence of `pattern` inside [t_start, t_end).
    Wall-time based with fold=0: the spring hour that does not exist is
    skipped, the autumn hour is taken on its first pass - the spike keeps one
    rule and names it; a real implementation defers to django-celery-beat (see
    extras/scheduling.py). Cached per (pattern, window)."""
    key = (pattern, t_start, t_end)
    hit = _occurrence_cache.get(key)
    if hit is not None:
        return hit
    parsed = parse_cron(pattern)
    result = []
    if tz is None:
        day = datetime.fromtimestamp(t_start - 172800).date()
        last = datetime.fromtimestamp(t_end + 172800).date()
        while day <= last:
            for h, m in day_occurrence_minutes(parsed, day):
                dt = datetime(day.year, day.month, day.day, h, m)
                epoch = int(dt.timestamp())
                if t_start <= epoch < t_end:
                    result.append(epoch)
            day += timedelta(days=1)
    else:
        day = datetime.fromtimestamp(t_start - 172800, tz).date()
        last = datetime.fromtimestamp(t_end + 172800, tz).date()
        while day <= last:
            for h, m in day_occurrence_minutes(parsed, day):
                wall = datetime(day.year, day.month, day.day, h, m, fold=0)
                epoch = int(wall.replace(tzinfo=tz).timestamp())
                # A wall time inside the spring gap does not exist; fold=0
                # maps it forward and the round-trip names it. The autumn
                # duplicate resolves to its first pass and round-trips
                # unchanged, so it is kept.
                back = datetime.fromtimestamp(epoch, tz)
                if (back.hour, back.minute) != (h, m):
                    continue
                if t_start <= epoch < t_end:
                    result.append(epoch)
            day += timedelta(days=1)
    result.sort()
    _occurrence_cache[key] = result
    return result


# ---------------------------------------------------------------- classify --

def classify(parsed):
    """Natural cycle of a supported pattern shape, which also decides the
    phase shifts the spike may offer for it:

      subhourly  minute grid repeated every hour, cycle `period` minutes
      hourly     one fixed minute per hour, cycle 60
      hourlylist k evenly spaced hours, one minute, cycle 1440/k
      daily      one wall time per matching day, cycle 1440
      weekly     one wall time on one weekday, cycle 10080
      monthly    one wall time on one day of month, cycle "calendar month"

    Anything else is not eligible: the optimizer may only shift shapes whose
    cadence it can state exactly."""
    minutes, hours = parsed["minutes"], parsed["hours"]
    anchored = (not parsed["dom_star"]) or (not parsed["dow_star"])
    if anchored:
        if len(minutes) == 1 and len(hours) == 1:
            if not parsed["dom_star"]:
                return {"kind": "monthly", "period": "month",
                        "shift_max": 360, "same_day": True}
            return {"kind": "weekly", "period": 7 * 1440,
                    "shift_max": 360, "same_day": True}
        return None
    if len(minutes) == 1 and len(hours) == 24:
        return {"kind": "hourly", "period": 60, "shift_max": 59,
                "same_day": False}
    if len(minutes) == 1 and len(hours) == 1:
        # one wall time on every matching day: daily, cycle 24 h. A phase
        # shift may cross midnight - the count per local calendar day stays 1
        return {"kind": "daily", "period": 1440, "shift_max": 360,
                "same_day": False}
    if len(minutes) == 1 and len(hours) >= 2:
        spacing = [hours[i + 1] - hours[i] for i in range(len(hours) - 1)]
        if len(set(spacing)) == 1:
            # every listed hour carries the same minute; a phase shift may
            # move the whole list (the count per day stays len(hours))
            return {"kind": "hourlylist", "period": spacing[0] * 60,
                    "shift_max": spacing[0] * 60 - 1, "same_day": False}
        return None
    if len(hours) == 24:  # a minute grid over every hour
        steps = [minutes[i + 1] - minutes[i] for i in range(len(minutes) - 1)]
        if len(set(steps)) == 1:
            step = steps[0]
            if len(minutes) * step == 60:
                return {"kind": "subhourly", "period": step,
                        "shift_max": step - 1, "same_day": False}
        return None
    return None


def classify_str(pattern):
    return classify(parse_cron(pattern))


# ----------------------------------------------------------------- shifting --

def minutes_string(values):
    return ",".join(str(v) for v in sorted(values))


def shifted_pattern(parsed, delta):
    """The same pattern shifted by `delta` minutes of PHASE, or None when the
    shift would change something other than the phase. The rule set:

      subhourly   rotate the minute grid inside the hour (delta < period)
      hourly      move the fixed minute (delta < 60)
      hourlylist  move only the minutes, hours stay (delta < 60)
      daily       move the wall time; may cross midnight (still 1/day)
      weekly,
      monthly     move the wall time inside its anchored day only

    Field semantics of the other fields never change, and every result is
    re-parsed, re-classified and later counted by `cadence_proof`."""
    if delta == 0:
        return parsed["pattern"]
    info = classify(parsed)
    if info is None:
        return None
    if delta > info["shift_max"]:
        return None
    minutes, hours = parsed["minutes"], parsed["hours"]
    dom, dow = ("*" if parsed["dom_star"] else minutes_string(parsed["doms"]),
                "*" if parsed["dow_star"] else minutes_string(
                    [7 if d == 0 else d for d in parsed["dows"]]))
    kind = info["kind"]
    if kind == "subhourly":
        step = info["period"]
        base = (minutes[0] + delta) % step
        new_minutes = sorted((base + k * step) % 60
                             for k in range(60 // step))
        return "%s * * * *" % minutes_string(new_minutes)
    if kind == "hourly":
        new_minute = (minutes[0] + delta) % 60
        hours_str = "*" if len(hours) == 24 else minutes_string(hours)
        return "%d %s * * *" % (new_minute, hours_str)
    if kind == "hourlylist":
        # shift every listed wall time by the same delta; the hours may move,
        # the count per day and the equal spacing of the list stay
        times = sorted((h * 60 + minutes[0] + delta) % 1440 for h in hours)
        new_minute = times[0] % 60
        if any((t % 60) != new_minute for t in times):
            return None  # a shift must keep one shared minute across hours
        new_hours = sorted(t // 60 for t in times)
        return "%d %s %s * %s" % (new_minute, minutes_string(new_hours),
                                  dom, dow)
    if kind in ("daily", "weekly", "monthly"):
        new_time = hours[0] * 60 + minutes[0] + delta
        if info["same_day"] and not (0 <= new_time < 1440):
            return None  # an anchored schedule keeps its anchored day
        new_time %= 1440
        return "%d %d %s * %s" % (new_time % 60, new_time // 60, dom, dow)
    return None


def window_ok(parsed, window):
    """Whether every wall-time minute of the pattern respects the window.
    The window is day-anchored: for sub-daily patterns it must be wide
    enough to contain every occurrence of the day."""
    if window is None:
        return True
    start, end = window
    for h, m in day_occurrence_minutes_all(parsed):
        minute_of_day = h * 60 + m
        if end <= 1440:
            inside = start <= minute_of_day < end
        else:  # wraps midnight, e.g. the nightly window 20:00 -> 06:00
            inside = minute_of_day >= start or minute_of_day < end % 1440
        if not inside:
            return False
    return True


def day_occurrence_minutes_all(parsed):
    """(hour, minute) pairs of one matching day without building a date."""
    return [(h, m) for h in parsed["hours"] for m in parsed["minutes"]]


# ----------------------------------------------------------------- fixture --

def _split(shares, total, rng):
    """Split `total` settings over the shares so the parts sum exactly to
    total; remainders go to the largest shares first, deterministically."""
    raw = [total * s for s in shares]
    parts = [int(math.floor(x)) for x in raw]
    rest = total - sum(parts)
    order = sorted(range(len(raw)), key=lambda i: (-(raw[i] - parts[i]), i))
    for i in order[:rest]:
        parts[i] += 1
    return parts


def build_fixture(name="full43k", seed=1333, rng=None):
    """The schedule fixture. Each entry: kind, queue, pattern, occupancy,
    org, locked, window, id. Deterministic for a fixed seed."""
    if rng is None:
        rng = random.Random(seed)
    total = FULL43K_TOTAL if name == "full43k" else 500
    orgs = 8
    schedules = []
    idx = 0
    for kind, queue, occ, weight, window, patterns in KINDS:
        if name != "full43k":
            weight = max(1, round(weight * total / FULL43K_TOTAL))
        shares = [s for _, s in patterns]
        parts = _split(shares, weight, rng)
        for (pattern, _), part in zip(patterns, parts):
            for _ in range(part):
                win = None
                if window == "locked":
                    win = None
                elif isinstance(window, dict) and window.get("night"):
                    win = NIGHT_WINDOW
                schedules.append({
                    "id": idx,
                    "kind": kind,
                    "queue": queue,
                    "pattern": pattern,
                    "occupancy": occ,
                    "org": idx % orgs,
                    "locked": window == "locked" or rng.random() < 0.05,
                    "window": win,
                })
                idx += 1
    return schedules


def build_events(t_start, days, seed=1333):
    """Deterministic event-driven arrivals on the shared queues; the fixture's
    share of "concurrent event-driven demand" (#1324 precondition)."""
    rng = random.Random(seed + 7)
    events = []
    for d in range(days):
        day_start = t_start + d * 86400
        for h in range(24):
            n = EVENT_RATE_PER_HOUR[h]
            for _ in range(n):
                epoch = day_start + h * 3600 + rng.randrange(3600)
                queue = EVENT_QUEUES[rng.randrange(len(EVENT_QUEUES))]
                events.append((epoch, queue))
    return events


# ------------------------------------------------------------------- gates --

def evidence_gate(schedules, t_start, days, telemetry, min_coverage):
    """Demand-weighted share of worker-occupancy evidence that is measured.
    Returns (coverage, classes, enough). The epic's non-negotiable rule: a
    forecast may not be advertised beyond its evidence classes."""
    horizon_s = days * 86400
    by_class = {}
    for s in schedules:
        parsed = parse_cron(s["pattern"])
        runs = len(occurrences(s["pattern"], t_start, t_start + horizon_s,
                               get_tz()[0]))
        demand = runs * s["occupancy"]
        if telemetry == "measured":
            cls = "measured_worker" if s["kind"] != "csw-harvest" \
                else "estimated_prior"
        elif telemetry == "missing":
            cls = "unknown"
        else:  # pragma: no cover
            raise ValueError(telemetry)
        cur = by_class.get(cls, [0, 0])
        cur[0] += demand
        cur[1] += runs
        by_class[cls] = cur
    total_demand = sum(v[0] for v in by_class.values()) or 1
    coverage = by_class.get("measured_worker", [0, 0])[0] / total_demand
    return coverage, by_class, coverage >= min_coverage


# ------------------------------------------------------------- simulation --

def p95(sorted_values, q=0.95):
    n = len(sorted_values)
    if n == 0:
        return None
    return sorted_values[max(0, min(n - 1, int(math.ceil(q * n)) - 1))]


def simulate(schedules, events, t_start, days, workers, tz):
    """Deterministic multi-queue FIFO simulation over one shared slot pool.

    Arrival order is time order (ties by schedule id), dispatch is round-robin
    over the queues that have backlog, occupancy is the schedule's worker
    seconds. Cadence-deadline violations count arrivals that start later than
    one natural period of their own schedule after enqueueing - the freshness
    SLA the epic names, evaluated per queue because a daily update waits by a
    different clock than an hourly probe."""
    horizon_s = days * 86400
    t_end = t_start + horizon_s
    arrivals = [[] for _ in QUEUE_ORDER]
    q_index = {q: i for i, q in enumerate(QUEUE_ORDER)}
    occ_by_sid = {}
    period_by_sid = {}
    org_by_sid = {}
    for s in schedules:
        qi = q_index[s["queue"]]
        for epoch in occurrences(s["pattern"], t_start, t_end, tz):
            arrivals[qi].append((epoch, s["id"]))
        occ_by_sid[s["id"]] = s["occupancy"]
        info = classify(parse_cron(s["pattern"]))
        period_by_sid[s["id"]] = (info["period"] if info
                                  and info["period"] != "month" else 30 * 1440)
        org_by_sid[s["id"]] = s["org"]
    for epoch, queue in events:
        if t_start <= epoch < t_end:
            arrivals[q_index[queue]].append((epoch, -1))
        occ_by_sid.setdefault(-1, EVENT_OCC)
        period_by_sid.setdefault(-1, 10 * 1440)
        org_by_sid.setdefault(-1, -1)
    for qi in range(len(QUEUE_ORDER)):
        arrivals[qi].sort()
    # merge the queue-local arrival streams into one global event stream
    merged = []
    for qi in range(len(QUEUE_ORDER)):
        merged.extend((epoch, qi, sid) for epoch, sid in arrivals[qi])
    merged.sort()

    queues = [deque() for _ in QUEUE_ORDER]
    busy_ends = []  # min heap of moments a busy slot frees again
    busy_n = 0
    peak_busy = 0
    busy_s = 0
    waits = [[] for _ in QUEUE_ORDER]
    org_waits = {}
    violations = 0
    rr = 0
    runs = 0
    cursor = 0
    n_merged = len(merged)
    n_queues = len(QUEUE_ORDER)

    def dispatch(now):
        """Occupy every free slot from the backlogs, one queue turn per
        sweep, so no queue may starve the others behind a long head."""
        nonlocal busy_n, peak_busy, rr, violations, busy_s
        turns = 0
        while busy_n < workers and turns < n_queues:
            qi = -1
            for k in range(n_queues):
                cand = (rr + k) % n_queues
                if queues[cand]:
                    qi = cand
                    break
            if qi < 0:
                return
            arr, sid = queues[qi].popleft()
            rr = (qi + 1) % n_queues
            turns += 1
            wait = now - arr
            waits[qi].append(wait)
            org = org_by_sid[sid]
            if org >= 0:
                org_waits.setdefault(org, []).append(wait)
            if wait > period_by_sid[sid] * 60:
                violations += 1
            busy_n += 1
            peak_busy = max(peak_busy, busy_n)
            busy_s += occ_by_sid[sid]
            heapq.heappush(busy_ends, now + occ_by_sid[sid])

    while cursor < n_merged or any(queues) or busy_n:
        next_arrival = merged[cursor][0] if cursor < n_merged else None
        next_end = busy_ends[0] if busy_ends else None
        if next_arrival is not None and (next_end is None
                                         or next_arrival <= next_end):
            now = next_arrival
            while cursor < n_merged and merged[cursor][0] == now:
                _, qi, sid = merged[cursor]
                queues[qi].append((now, sid))
                cursor += 1
                runs += 1
            while busy_ends and busy_ends[0] <= now:
                heapq.heappop(busy_ends)
                busy_n -= 1
            dispatch(now)
        elif next_end is not None:
            now = next_end
            while busy_ends and busy_ends[0] <= now:
                heapq.heappop(busy_ends)
                busy_n -= 1
            dispatch(now)
        else:  # backlog left but nothing busy: unreachable, a slot always
            break  # takes work if there is one
    peak_busy = max(peak_busy, busy_n)

    all_waits = sorted(w for q in waits for w in q)
    per_queue = {}
    for qi, qname in enumerate(QUEUE_ORDER):
        if waits[qi]:
            w = sorted(waits[qi])
            per_queue[qname] = {"runs": len(w), "p95": p95(w),
                                "mean": round(sum(w) / len(w), 1),
                                "max": w[-1]}
    org_metrics = {}
    for org, w in sorted(org_waits.items()):
        w.sort()
        org_metrics[org] = {"runs": len(w), "p95": p95(w)}
    return {
        "runs": runs,
        "wait_p95": p95(all_waits),
        "wait_mean": round(sum(all_waits) / len(all_waits), 1) if all_waits
        else None,
        "cadence_violations": violations,
        "peak_worker_duty": peak_busy,
        "worker_utilization": round(busy_s / (workers * horizon_s), 3),
        "per_queue": per_queue,
        "org_p95": org_metrics,
    }


# ------------------------------------------------------------- optimizers --

def eligible(schedules, t_start, days, tz, only_org=None):
    """Schedules a future optimizer could even consider: unlocked, of a shape
    whose cadence it can state, inside a window it can prove it keeps. The
    org rule demonstrates the multi-organization constraint of the issue."""
    out = []
    for s in schedules:
        if s["locked"]:
            continue
        if only_org is not None and s["org"] != only_org:
            continue
        parsed = parse_cron(s["pattern"])
        info = classify(parsed)
        if info is None:
            continue
        out.append((s, parsed, info))
    return out


def _minute_load(schedules, t_start, days, tz):
    """Worker-seconds arriving per minute, per queue - the objective curve
    both optimizers flatten. Minute resolution is honest here: it is exactly
    the granularity of the cron expressions under discussion."""
    minutes = days * 1440
    q_index = {q: i for i, q in enumerate(QUEUE_ORDER)}
    load = [[0] * minutes for _ in QUEUE_ORDER]
    for s in schedules:
        occ = occurrences(s["pattern"], t_start, t_start + days * 86400, tz)
        col = load[q_index[s["queue"]]]
        for epoch in occ:
            col[(epoch - t_start) // 60] += s["occupancy"]
    return load


def _candidate_phases(info, grid=60):
    """The deterministic phase grid an optimizer may offer for a shape; big
    families need minute-level phases, anchored shapes stay in their day."""
    if info["kind"] in ("daily", "weekly", "monthly"):
        grid = 12
    step = max(1, (info["shift_max"] + 1) // (grid + 1))
    return [d for d in range(step, info["shift_max"] + 1, step)]


def optimize_greedy(schedules, t_start, days, tz, budget, only_org=None):
    """Alternative A - greedy phase spread. Members of one cadence family
    (same queue, same pattern) are interchangeable, so the greedy works on
    their phase counts and applies each accepted move to the lowest member id
    holding the worst phase. A move is accepted only when it lowers the
    convex cost sum(load^2) of the queue's per-minute arrival curve - which
    means the moved run leaves a busier minute of its own cadence for a
    flatter one, never a different frequency. The per-phase sums over the
    shared curve are kept incrementally (a family's phase minutes are
    disjoint), which is what lets the greedy consider minute-level phases
    across thousands of members. Stops at the change budget. It never claims
    a free minute: only the measured shape of the curve decides.
    """
    load = _minute_load(schedules, t_start, days, tz)
    q_index = {q: i for i, q in enumerate(QUEUE_ORDER)}
    horizon_s = days * 86400
    families = {}
    for s, parsed, info in eligible(schedules, t_start, days, tz, only_org):
        families.setdefault((s["queue"], s["pattern"]), []).append(
            (s, parsed, info))
    changed = {}
    used = 0
    for (queue, pattern), members in sorted(families.items()):
        if used >= budget:
            break
        qi = q_index[queue]
        col = load[qi]
        parsed = members[0][1]
        info = members[0][2]
        occ_s = members[0][0]["occupancy"]
        phase_pat = {0: pattern}
        for delta in _candidate_phases(info):
            cand = shifted_pattern(parsed, delta)
            if cand is None:
                continue
            if not window_ok(parse_cron(cand), members[0][0]["window"]):
                continue
            phase_pat[delta] = cand
        phase_minutes = {p: [(e - t_start) // 60 for e in occurrences(
            pat, t_start, t_start + horizon_s, tz)]
            for p, pat in phase_pat.items()}
        # member lists per phase, lowest id first: the deterministic holder
        holders = {p: [] for p in phase_pat}
        holders[0] = [s["id"] for s, _, _ in sorted(
            members, key=lambda t: t[0]["id"])]
        sums = {p: sum(col[m] for m in mins)
                for p, mins in phase_minutes.items()}
        sizes = {p: len(mins) for p, mins in phase_minutes.items()}
        phases = sorted(phase_pat)
        # ONE deterministic pass over the member ids: every schedule is
        # proposed at most once per run and a schedule moved into a later
        # phase is not evaluated again. That is the spike's no-churn rule; a
        # recurring optimizer additionally needs the real cooldown and change
        # budget of the issue, not just this.
        moved = set()
        for worst in phases:
            if used >= budget:
                break
            for sid in holders[worst]:
                if used >= budget:
                    break
                if sid in moved:
                    continue
                best = None
                for p in phases:
                    if p == worst:
                        continue
                    # moving one member worst -> p on disjoint minutes:
                    #   sum((c-o)^2 - c^2 over worst) + sum((c+o)^2 - c^2 over p)
                    delta_cost = (-2 * occ_s * sums[worst] + occ_s * occ_s
                                  * sizes[worst]
                                  + 2 * occ_s * sums[p] + occ_s * occ_s
                                  * sizes[p])
                    if delta_cost < 0 and (best is None
                                           or delta_cost < best[0]
                                           or (delta_cost == best[0]
                                               and p < best[1])):
                        best = (delta_cost, p)
                if best is None:
                    continue  # no verified improvement: keep it where it is
                target = best[1]
                for m in phase_minutes[worst]:
                    col[m] -= occ_s
                for m in phase_minutes[target]:
                    col[m] += occ_s
                sums[worst] -= occ_s * sizes[worst]
                sums[target] += occ_s * sizes[target]
                holders[target].append(sid)
                moved.add(sid)
                changed[sid] = phase_pat[target]
                used += 1
    return changed


def optimize_constrained(schedules, t_start, days, tz, budget, only_org=None):
    """Alternative B - constrained even phase packing per cadence family.
    Schedules of the same queue AND the same pattern form a family; their
    members are ordered round-robin over their organizations (fairness first)
    and get phases spread evenly over ONE natural cycle. A family is packed
    only when every member's shifted pattern passes the window proof; a
    saturated window makes the whole family `cannot optimize reliably` and
    changes nothing about it - the all-or-nothing rule of the issue."""
    changed = {}
    refused = []
    families = {}
    for s, parsed, info in eligible(schedules, t_start, days, tz, only_org):
        families.setdefault((s["queue"], s["pattern"]), []).append(
            (s, parsed, info))
    used = 0
    for (queue, pattern), members in sorted(families.items()):
        if len(members) < 2 or used >= budget:
            continue
        info = members[0][2]
        # fairness order: rotate members over their orgs, then by id
        by_org = {}
        for m in members:
            by_org.setdefault(m[0]["org"], []).append(m)
        order = []
        while any(by_org.values()):
            for org in sorted(by_org):
                if by_org[org]:
                    order.append(by_org[org].pop(0))
        # spread the members over the allowed shift span of their cycle;
        # more members than phases means deliberate shared phases
        span = info["shift_max"] + 1
        plan = []
        ok = True
        for rank, (s, parsed, _) in enumerate(order):
            delta = int(rank * span / len(order))
            cand = shifted_pattern(parsed, delta)
            cp = parse_cron(cand) if cand is not None else None
            if cp is None or not window_ok(cp, s["window"]):
                ok = False
                break
            plan.append((s["id"], cand))
        if not ok:
            refused.append({"queue": queue, "pattern": pattern,
                            "members": len(members),
                            "reason": "window or cadence proof rejects a "
                                      "member; the family stays unchanged"})
            continue
        if len(plan) > budget - used:
            refused.append({"queue": queue, "pattern": pattern,
                            "members": len(members),
                            "reason": "change budget cannot hold the whole "
                                      "family; the family stays unchanged"})
            continue
        for sid, cand in plan:
            changed[sid] = cand
        used += len(plan)
    return changed, refused


# ----------------------------------------------------------- cadence proof --

def _per_unit_counts(pattern, tz, t_start, days):
    """Occurrences of the pattern per full natural calendar unit over a
    padded window; the unit is the pattern's natural cycle (local calendar
    day / ISO week / calendar month). Padding by +-40 days covers the cycle
    margins, so an aligned unit count cannot differ by window edges."""
    t0 = t_start - 40 * 86400
    t1 = t_start + days * 86400 + 40 * 86400
    parsed = parse_cron(pattern)
    info = classify(parsed)
    counts = {}
    if tz is None:
        for epoch in occurrences(pattern, t0, t1, tz):
            dt = datetime.fromtimestamp(epoch)
            key = _unit_key(info["kind"], dt)
            counts[key] = counts.get(key, 0) + 1
    else:
        for epoch in occurrences(pattern, t0, t1, tz):
            dt = datetime.fromtimestamp(epoch, tz)
            key = _unit_key(info["kind"], dt)
            counts[key] = counts.get(key, 0) + 1
    # compare only units fully inside [t_start - 20d, t_start + days*86400 + 20d)
    lo = datetime.fromtimestamp(t_start - 20 * 86400, tz) if tz \
        else datetime.fromtimestamp(t_start - 20 * 86400)
    hi = datetime.fromtimestamp(t_start + days * 86400 + 20 * 86400, tz) \
        if tz else datetime.fromtimestamp(t_start + days * 86400 + 20 * 86400)
    return {k: v for k, v in counts.items() if _unit_full(k, lo, hi)}


def _unit_key(kind, dt):
    if kind == "weekly":
        iso = dt.isocalendar()
        return ("W", iso[0], iso[1])
    if kind == "monthly":
        return ("M", dt.year, dt.month)
    return ("D", dt.year, dt.month, dt.day)


def _unit_full(key, lo, hi):
    """Whether the calendar unit named by the key lies fully inside [lo, hi)."""
    if key[0] == "D":
        d = date(*key[1:])
        return _midnight(d) >= _midnight(lo) and \
            _midnight(d) + timedelta(days=1) <= _midnight(hi)
    if key[0] == "M":
        y, m = key[1], key[2]
        start = datetime(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        end = datetime(ny, nm, 1)
        return _whole(start, end, lo, hi)
    year, week = key[1], key[2]
    start = date.fromisocalendar(year, week, 1)
    end = start + timedelta(days=7)
    return _midnight(start) >= _midnight(lo) and \
        _midnight(end) <= _midnight(hi)


def _midnight(dt):
    return datetime(dt.year, dt.month, dt.day)


def _whole(start, end, lo, hi):
    lo2 = _midnight(lo) if lo.tzinfo is None else datetime(
        lo.year, lo.month, lo.day)
    hi2 = _midnight(hi) if hi.tzinfo is None else datetime(
        hi.year, hi.month, hi.day)
    return start >= lo2 and end <= hi2


def cadence_proof(schedules, changes, t_start, days, tz):
    """The proof the deliverable asks for: for EVERY changed schedule, the
    occurrences per full natural calendar unit are equal before and after.
    A shift that changes any unit count is rejected and reported."""
    by_id = {s["id"]: s for s in schedules}
    rejected = []
    checked = 0
    for sid in sorted(changes):
        s = by_id[sid]
        before = _per_unit_counts(s["pattern"], tz, t_start, days)
        after = _per_unit_counts(changes[sid], tz, t_start, days)
        checked += 1
        if before != after:
            rejected.append({"id": sid, "old": s["pattern"],
                             "new": changes[sid]})
            del changes[sid]
    return checked, rejected


# ------------------------------------------------------------------ report --

def fmt(seconds):
    if seconds is None:
        return "n/a"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return ("%dh %02dm %02ds" % (h, m, s)) if h else ("%dm %02ds" % (m, s))


def run(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", choices=["mvp", "full43k"], default="full43k")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--workers", type=int, default=4,
                    help="slots of the one shared pool (the rig of #1324 "
                         "reported --concurrency=4)")
    ap.add_argument("--telemetry", choices=["measured", "missing"],
                    default="measured")
    ap.add_argument("--algorithm", choices=["greedy", "constrained", "both"],
                    default="both")
    ap.add_argument("--change-budget", type=int, default=5000)
    ap.add_argument("--optimize-org", type=int, default=None,
                    help="restrict eligibility to one org (multi-org "
                         "externality demo)")
    ap.add_argument("--seed", type=int, default=1333)
    ap.add_argument("--min-measured-coverage", type=float, default=0.75)
    ap.add_argument("--improvement-threshold", type=float, default=0.05)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    tz, tz_name = get_tz()
    # horizon anchored to a DST-free Monday so both DST boundaries of the
    # fixture year are irrelevant to the numbers quoted in the docs
    t_start = int(datetime(2026, 11, 2, 0, 0, tzinfo=tz).timestamp()) \
        if tz else int(datetime(2026, 11, 2).timestamp())
    schedules = build_fixture(args.fixture, args.seed)
    events = build_events(t_start, args.days, args.seed)

    coverage, classes, enough = evidence_gate(
        schedules, t_start, args.days, args.telemetry,
        args.min_measured_coverage)

    base = simulate(schedules, events, t_start, args.days, args.workers, tz)

    result = {
        "tool": "schedule_optimizer_spike",
        "issue": 1333,
        "fixture": args.fixture,
        "schedules": len(schedules),
        "days": args.days,
        "workers": args.workers,
        "timezone": tz_name,
        "telemetry": args.telemetry,
        "measured_coverage": round(coverage, 3),
        "evidence_classes": {k: {"worker_seconds": v[0], "runs": v[1]}
                             for k, v in sorted(classes.items())},
        "baseline": base,
    }

    if not enough:
        result["status"] = "cannot_optimize_reliably"
        result["stop_reason"] = (
            "measured worker-occupancy covers %.0f%% of the demand "
            "(threshold %.0f%%); the optimizer refuses and changes "
            "nothing" % (100 * coverage, 100 * args.min_measured_coverage))
        result["changes"] = 0
        return finish(result, args)

    variants = {}
    if args.algorithm in ("greedy", "both"):
        changed = optimize_greedy(schedules, t_start, args.days, tz,
                                  args.change_budget, args.optimize_org)
        variants["greedy"] = changed
    if args.algorithm in ("constrained", "both"):
        changed, refused = optimize_constrained(
            schedules, t_start, args.days, tz, args.change_budget,
            args.optimize_org)
        variants["constrained"] = changed
        result["constrained_refused_families"] = refused

    results = {}
    for name, changed in variants.items():
        checked, rejected = cadence_proof(schedules, changed, t_start,
                                          args.days, tz)
        sim = simulate([{**s, "pattern": changed.get(s["id"], s["pattern"])}
                        for s in schedules], events, t_start, args.days,
                       args.workers, tz)
        results[name] = {
            "changes": len(changed),
            "cadence_checked": checked,
            "cadence_rejected": rejected,
            "metrics": sim,
        }

    # objective: p95 wait first, then peak duty, then fewer changes
    def key(item):
        m = item[1]["metrics"]
        return (m["wait_p95"] if m["wait_p95"] is not None else 2 ** 62,
                m["peak_worker_duty"], item[1]["changes"])

    best_name, best = min(results.items(), key=key)
    threshold = args.improvement_threshold
    base_p95 = base["wait_p95"] or 0
    improved = best["metrics"]["wait_p95"] is not None and \
        (base_p95 - best["metrics"]["wait_p95"]) >= threshold * base_p95
    result["variants"] = results
    result["recommended"] = best_name if improved else None
    result["status"] = "OPTIMIZED" if improved else \
        "NO_CHANGE_without_verified_improvement"
    result["changes"] = results[best_name]["changes"] if improved else 0
    return finish(result, args)


def finish(result, args):
    result["digest"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
    if args.out:
        with open(args.out, "w") as handle:
            json.dump(result, handle, indent=1, default=str, sort_keys=True)
    if args.json:
        print(json.dumps(result, sort_keys=True, default=str))
    else:
        print(text_report(result))
    return result


def text_report(result):
    lines = []
    add = lines.append
    add("schedule_optimizer_spike - design spike for #1333 "
        "(fixture numbers are rig priors, not deployment facts)")
    add("fixture: %s  schedules: %d  horizon: %d day(s)  worker pool: %d "
        "slot(s)  timezone: %s" % (result["fixture"], result["schedules"],
                                   result["days"], result["workers"],
                                   result["timezone"]))
    add("evidence: telemetry=%s, measured coverage %.1f%%"
        % (result["telemetry"], 100 * result["measured_coverage"]))
    base = result["baseline"]
    add("")
    add("BASELINE      runs %d | p95 wait %s | mean %s | cadence violations "
        "%d | peak duty %d/%d | utilization %.0f%%"
        % (base["runs"], fmt(base["wait_p95"]), fmt(base["wait_mean"]),
           base["cadence_violations"], base["peak_worker_duty"],
           result["workers"], 100 * base["worker_utilization"]))
    for q, m in sorted(base["per_queue"].items()):
        add("  queue %-15s runs %6d  p95 %12s  mean %9s  max %s"
            % (q, m["runs"], fmt(m["p95"]), fmt(m["mean"]), fmt(m["max"])))
    if result.get("status") == "cannot_optimize_reliably":
        add("")
        add("STATUS: cannot optimize reliably - %s" % result["stop_reason"])
    else:
        for name, r in sorted(result["variants"].items()):
            m = r["metrics"]
            add("")
            add("VARIANT %s  changes %d | cadence-proofed %d, rejected %d"
                % (name, r["changes"], r["cadence_checked"],
                   len(r["cadence_rejected"])))
            add("            p95 wait %s | violations %d | peak duty %d | "
                "utilization %.0f%%"
                % (fmt(m["wait_p95"]), m["cadence_violations"],
                   m["peak_worker_duty"], 100 * m["worker_utilization"]))
            if result.get("constrained_refused_families") and \
                    name == "constrained":
                add("            families refused unchanged: %d (reasons in "
                    "the JSON report)"
                    % len(result["constrained_refused_families"]))
        add("")
        add("STATUS: %s  recommended: %s"
            % (result["status"], result.get("recommended") or "-"))
        if result["status"] == "OPTIMIZED":
            base_p95 = base["wait_p95"]
            rec = result["variants"][result["recommended"]]["metrics"]
            add("p95 wait %s -> %s (%.0f%% less, p95 only, prior-based - "
                "the UI must show the evidence class, never a promise)"
                % (fmt(base_p95), fmt(rec["wait_p95"]),
                   100 * (base_p95 - rec["wait_p95"]) / base_p95))
        if result.get("org_p95_note"):
            add(result["org_p95_note"])
    add("")
    add("report digest (sha256): %s" % result["digest"])
    return "\n".join(lines)


if __name__ == "__main__":
    run()
    sys.exit(0)
