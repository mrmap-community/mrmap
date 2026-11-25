"""Shared machinery of the opt-in Celery runtime benchmarks (#1396).

Kept out of the test module so the test file reads as the list of benchmarked
workloads and not as a runner implementation. Nothing here asserts anything: a
benchmark measures and writes, the analyzer in ``scripts/task_perf_bench.py``
judges. The reason is #1396's own framing - a duration measured on a shared
runner is a reading of that runner, so the numbers go out with their sample
size, their seed and their environment, and the judgement happens where the
repeatability floor and the reviewed thresholds live.
"""
import hashlib
import json
import os
import resource
import time
from pathlib import Path

from django.db import connection

#: the switch the "opt-in" requirement turns into; unset skips every bench test
BENCH_ENABLED = os.environ.get('MRMAP_TASK_PERF_BENCH', '').strip().lower() in (
    '1', 'on', 'true', 'yes')
#: the heavy backlog arm (400k+ records) on its own switch, so the repeatable
#: half stays runnable on an ordinary runner
HEAVY_ENABLED = os.environ.get('MRMAP_TASK_PERF_HEAVY', '').strip().lower() in (
    '1', 'on', 'true', 'yes')
#: dispatch through celery's own trace machinery instead of ``.run()``. The
#: eager path still has no broker, so the queue wait stays unknown - but the
#: worker-side ACTIVE time of #1330 is then a real measurement, and #1330's
#: rule is that only that distinction may be reported as measured.
EAGER_ENABLED = os.environ.get('MRMAP_TASK_PERF_EAGER', '').strip().lower() in (
    '1', 'on', 'true', 'yes')

SEED = int(os.environ.get('MRMAP_TASK_PERF_SEED', '20261121'))
REPEATS = max(1, int(os.environ.get('MRMAP_TASK_PERF_REPEATS', '7')))
OUT_DIR = os.environ.get('MRMAP_TASK_PERF_OUT', 'task-perf')
#: one family name, when the run is asked to measure a single family; unset runs
#: every family. The runner passes `--family` through as this, so the flag
#: selects the workload in CI and on a laptop instead of only naming it.
FAMILY = (os.environ.get('MRMAP_TASK_PERF_FAMILY', '') or '').strip() or None
HEAVY_BACKLOG_RECORDS = int(os.environ.get('MRMAP_TASK_PERF_BACKLOG', '400000'))
HEAVY_CHUNK_SIZE = int(os.environ.get('MRMAP_TASK_PERF_CHUNK_SIZE', '1000'))

#: the arms of one workload; the analyzer compares them by label
ARMS = ('baseline', 'sql-n-plus-one', 'duplicate-remote-call', 'slow-body')
#: The per-attempt cost of the ``slow-body`` arm, as a multiple of what the same
#: unit cost clean - so the arm is a RELATIVE defect, which is what a regression
#: is. A fixed burn cannot work: the 50 ms which doubles a 20 ms probe fire is 1%
#: of a 4 s import chunk, and an arm which stays within noise of its baseline
#: proves only that the harness can be slow. Bounded at both ends - a burn of a
#: millisecond is the noise floor of a container, and an arm which took an hour to
#: be slow proves nothing either.
SLOW_BODY_FACTOR = float(os.environ.get('MRMAP_TASK_PERF_SLOW_FACTOR', '2.0'))
SLOW_BODY_MIN_SECONDS = float(os.environ.get('MRMAP_TASK_PERF_SLOW_MIN', '0.005'))
SLOW_BODY_MAX_SECONDS = float(os.environ.get('MRMAP_TASK_PERF_SLOW_MAX', '15.0'))

BENCH_SKIP = ('opt-in runtime benchmark: set MRMAP_TASK_PERF_BENCH=1 to run it '
              '(a stopwatch in the normal unit-tests job is the flakiness #1396 '
              'asks to remove, not to add)')
HEAVY_SKIP = ('opt-in runtime benchmark: set MRMAP_TASK_PERF_BENCH=1 and '
              'MRMAP_TASK_PERF_HEAVY=1 to run the 400k-record backlog arm')

#: the workload keys the analyzer hashes; kept in sync with
#: ``WORKLOAD_KEYS`` of scripts/task_perf_bench.py, and pinned from both sides
#: by tests so the two cannot drift apart unnoticed
WORKLOAD_KEYS = ('family', 'fixture', 'scale', 'records', 'chunks', 'chunk_size',
                 'attempts_per_unit', 'concurrency', 'worker_count', 'queue',
                 'queue_config', 'mock_responses', 'seed', 'environment')


#: how long a clean cost remembered by one test process stays usable as the
#: reference of the arm which follows it, in seconds
SLOW_BODY_REFERENCE_TTL = 1800.0


def _slow_body_reference_path(family, scale):
    # one reference per (family, scale): the clean cost of a probe fire must not
    # become the reference of an import chunk of another family. Not ``.json``:
    # the artifact directory is swept by ``load --fixture-dir``, which reads every
    # ``*.json`` it finds and would refuse this bookkeeping as a malformed record.
    return Path(OUT_DIR) / ('slow-body-reference__%s__%s' % (family, scale))


def output_dir():
    directory = Path(OUT_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


#: the manifest of workload files one run wrote, in the order they were written.
#: The host sweep reads this list rather than ``*.json``: "the files on disk" is
#: not "the files this run measured" once a directory is reused, and a report
#: assembled from both is a report of a run which never happened. Not ``.json``
#: for the same reason as the slow-body bookkeeping above.
MANIFEST_NAME = '.written-workloads'


def record_written(path):
    """Append one written workload file to this run's manifest.

    Written per file rather than swept at the end, so a run which died halfway
    reports the cells it measured and no more.
    """
    try:
        with open(Path(OUT_DIR) / MANIFEST_NAME, 'a', encoding='utf-8') as handle:
            handle.write('%s\n' % path.name)
    except OSError:
        # a read-only artifact directory must not fail a benchmark run over how
        # the host finds its files; the sweep falls back to the directory itself
        pass


def workload_slug(family, scale, arm, repeat):
    """The file name of one workload record - it names its own identity.

    Family, scale, arm and repeat are what a reader compares on, so they are in
    the name and a rerun of the same workload overwrites its own file instead of
    leaving a second reading nobody asked for.
    """
    return '%s__%s__%s__r%s.json' % (family, scale, arm, repeat)


def workload_digest(spec):
    """The analyzer's digest, computed here too so the file is self-describing.

    A workload whose identity changed between two arms is refused by the
    analyzer; carrying the digest in the file makes that mismatch visible in
    what the run wrote, not only in the analyzer's error message.
    """
    identity = {key: spec[key] for key in WORKLOAD_KEYS if spec.get(key) is not None}
    payload = json.dumps(identity, sort_keys=True, separators=(',', ':'),
                         default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def write_workload(family, scale, arm, repeat, payload):
    path = output_dir() / workload_slug(family, scale, arm, repeat)
    payload['digest'] = workload_digest(payload)
    path.write_text(json.dumps(payload, sort_keys=True, default=str),
                    encoding='utf-8')
    record_written(path)
    return path


def git_revision():
    """The revision under test, from the checkout the container mounted."""
    try:
        import subprocess   # nosec B404 - read-only git call, no shell
        out = subprocess.run(  # nosec B603 - fixed argv, no shell
            ['git', 'rev-parse', 'HEAD'], cwd='/opt/mrmap',
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return os.environ.get('MRMAP_TASK_PERF_REVISION') or None


def database_fingerprint():
    """What the measured database actually is, read from the server itself.

    PostgreSQL/PostGIS are part of the documented environment per the
    acceptance; reading them from the connection under test means the record
    cannot drift from the thing it measured.
    """
    with connection.cursor() as cursor:
        cursor.execute('select version()')
        version = cursor.fetchone()[0]
        try:
            cursor.execute('select postgis_version()')
            postgis = cursor.fetchone()[0]
        except Exception:
            postgis = None
    return {'postgres': version, 'postgis': postgis,
            'alias': connection.alias,
            'name': connection.settings_dict.get('NAME')}


def cgroup_limits():
    """The memory ceiling of this process, from its own cgroup (#1054's rule)."""
    limits = {}
    for key, path in (('cgroup_limit_bytes', '/sys/fs/cgroup/memory.max'),
                      ('memory_limit_bytes',
                       '/sys/fs/cgroup/memory/memory.limit_in_bytes')):
        try:
            text = Path(path).read_text().strip()
        except OSError:
            continue
        if text in ('', 'max'):
            continue
        try:
            value = int(text)
        except ValueError:
            continue
        if value < 2 ** 62:
            limits[key] = value
    return limits


def peak_memory_bytes():
    """The kernel's high-water mark for this process (ru_maxrss is KiB)."""
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def oom_observed():
    """Whether this process has been OOM-killed and recovered from.

    The acceptance asks whether an OOM occurred. A kill of the runner itself
    ends the run and the artifact never lands, so the question can only be
    answered for what survived: the kernel counter of this cgroup. ``None``
    when the counter is unreadable - never a comforting zero.
    """
    for path in ('/sys/fs/cgroup/memory.events',
                 '/sys/fs/cgroup/memory/memory.oom_control'):
        try:
            text = Path(path).read_text()
        except OSError:
            continue
        for line in text.splitlines():
            if line.strip().startswith('oom_kill'):
                try:
                    return int(line.split()[1]) > 0
                except (IndexError, ValueError):
                    continue
    return None


def burn(seconds):
    """Burn wall time inside the attempt, the way a CPU-bound body does.

    Not ``time.sleep``: a sleeping body reports as idle, and the point of the
    ``slow-body`` arm is a task which is slow for a reason the SQL and HTTP
    counters cannot see.
    """
    deadline = time.monotonic() + seconds
    value = 0
    while time.monotonic() < deadline:
        value = len(hashlib.sha256(str(value).encode()).hexdigest())
    return value


def slow_body_reference(family, scale):
    """The last clean cost of one workload cell, or None before its baseline ran.

    The four arms of a scale cell run baseline first (``ARMS`` is ordered for
    it), so the ``slow-body`` arm can burn a multiple of what the same unit
    actually cost rather than a fixed number which is huge for a probe fire and
    noise for an import chunk. Absent - a run which asks for one arm only - the
    caller burns a bounded floor, which keeps the arm non-trivial and bounded.
    """
    path = _slow_body_reference_path(family, scale)
    try:
        with open(path, encoding='utf-8') as handle:
            reference = json.load(handle)
    except (OSError, ValueError):
        return None
    if time.time() - reference.get('written_at', 0) > SLOW_BODY_REFERENCE_TTL:
        return None
    return reference.get('active_seconds')


def remember_slow_body_reference(family, scale, active_seconds):
    """Record the cost of a clean unit for the arms of that cell which follow."""
    if active_seconds is None:
        return
    try:
        path = _slow_body_reference_path(family, scale)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump({'active_seconds': active_seconds, 'written_at': time.time()},
                      handle)
    except OSError:
        # a read-only artifact directory must not fail a benchmark run over an
        # optimisation of one arm
        pass


def slow_body_seconds(active_seconds):
    """How long the ``slow-body`` arm burns for this unit.

    ``SLOW_BODY_FACTOR`` times what the same unit cost clean, clamped into a
    bounded band: proportional enough that a slow 5 s chunk is slowed, bounded
    enough that no arm ever takes an hour to prove a point.
    """
    if active_seconds is None:
        return min(SLOW_BODY_MAX_SECONDS, max(SLOW_BODY_MIN_SECONDS, 0.05))
    if active_seconds < SLOW_BODY_MIN_SECONDS:
        # a unit this cheap cannot be doubled into a signal above the noise of a
        # container, so burn the floor instead
        return min(SLOW_BODY_MAX_SECONDS, max(SLOW_BODY_MIN_SECONDS, 0.02))
    return min(SLOW_BODY_MAX_SECONDS,
               max(SLOW_BODY_MIN_SECONDS, active_seconds * SLOW_BODY_FACTOR))


def collect_attempt_rows():
    """Force the #1330 buffer out so the rows of this run are readable now.

    The collector writes bounded batches on purpose; reading the table before a
    flush would measure a partial window and call it the whole run.
    """
    from system.capacity_telemetry import flush_attempts, reset_collector

    try:
        flush_attempts()
    except Exception:
        # losing telemetry must not fail a benchmark - the durations then come
        # from the runner's clock and the record says `measured_local`
        reset_collector()


def attempt_rows(since):
    """#1330's own readings of the attempts made since ``since``.

    Read from the collector's table instead of a second stopwatch here, so the
    active time of an arm is the number a capacity reader would also see in the
    snapshot endpoint of #1326. Queue wait rides along on the same rows.
    """
    from system.models import CeleryTaskAttempt

    return list(CeleryTaskAttempt.objects
                .filter(started_at__gte=since)
                .order_by('started_at')
                .values('task_id', 'task_name', 'attempt_no', 'active_seconds',
                        'wait_seconds', 'outcome', 'quality', 'queue',
                        'worker'))


def dispatch(task, kwargs, eager):
    """One execution of one task, either in-process or through celery's trace.

    ``.run()`` is what the #1395 guards use: deterministic, inside the test's
    atomic block, and it fires no signals - so the collector sees nothing and
    the record must say ``measured_local``. ``.apply()`` rides the real trace
    machinery, the collector observes it and the active time becomes a #1330
    measurement; the eager path publishes nothing, so the queue wait of those
    rows is unknown and stays unknown. Only a real worker answers the wait, and
    the runbook shows that path.
    """
    if eager:
        return task.apply(kwargs=kwargs)
    return task.run(**kwargs)
