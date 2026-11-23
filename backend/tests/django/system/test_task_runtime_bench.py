"""Opt-in runtime benchmarks of the first-party Celery task families (#1396).

This is the workload half of the runtime benchmark story; the reading and the
verdict live in ``scripts/task_perf_bench.py`` and are documented on
:ref:`celery-task-runtime-benchmarks`. The split follows what #1395 established
for statements: the fixtures, models and mocked remotes of the application are
the only reproducible description of a harvest chunk or a probe run there is, so
the workload is generated here - next to the guards that pin its *shape* - and
this suite measures how long that shape actually takes.

Why these tests skip unless a variable says otherwise
#####################################################

They measure seconds, and seconds on a shared CI runner are not a fact but a
reading of whatever else the machine was doing. That is the flakiness #1396 asks
to remove rather than add, so:

*   every test skips unless ``MRMAP_TASK_PERF_BENCH=1`` - the ``unit-tests`` job
    runs everything below ``tests/`` and must never become a stopwatch;
*   the 400k-record backlog arm (the acceptance transferred from #1392) needs
    ``MRMAP_TASK_PERF_HEAVY=1`` as well, so the repeatable half stays runnable
    on an ordinary runner and the heavy half runs where it was measured;
*   nothing here publishes a verdict or fails on a number. A run writes
    machine-readable workload JSON, and ``task_perf_bench.py report|compare|gate
    |detect`` decides what the numbers mean - against the repeatability floor
    and the reviewed thresholds of the baseline file. A benchmark which graded
    itself on the machine that produced it is how a noisy green is born.

The durations stay separate and are never summed (#1330): the per-attempt
*active* time comes from the attempt rows the #1330 collector writes about these
very runs, the *queue wait* from the publish stamps on the same rows, and the
*end-to-end* elapsed of the unit from this runner's monotonic clock. With
``MRMAP_TASK_PERF_EAGER=1`` the work rides celery's own trace machinery, so the
active time is a #1330 measurement rather than a wall reading; the eager path
publishes nothing, so the queue wait of those rows is unknown and stays unknown
instead of becoming 0.0 - only a real worker answers it, and the runbook shows
that path.

The injected defects, and what they prove
#########################################

The acceptance asks that the harness *detect* an injected SQL N+1, a duplicate
remote call and a slow task body against a statistically stable baseline. Each
family therefore runs one workload under four arms which differ only in the
defect installed for that arm:

``baseline``
    the task as it is.
``sql-n-plus-one``
    one read per record inside the loop the shape of #895's locked read already
    names - what a "harmless" ``.get()`` in a chunk loop looks like.
``duplicate-remote-call``
    the same remote answer requested per record instead of per chunk, the shape
    of the #1392 capabilities-document bug.
``slow-body``
    a bounded CPU burn inside the attempt: the case which is neither SQL nor
    HTTP and must therefore be visible as time and nothing else.

The injections are installed by the test and touch no production path. An arm
whose injection did not take is recorded as ``injection_missing`` in its own
file rather than measuring the baseline a second time and reporting a perfect
repeatability.

Running them
############

::

    export MRMAP_BACKEND_DEV_FP=$(python3 scripts/dev_image_id.py --resolve --image backend --build)
    export COMPOSE_FILE="docker-compose.yml:docker-compose.dev.yml:docker-compose.prebuilt.yml"
    docker compose up -d postgis redis mapserver

    MRMAP_TASK_PERF_BENCH=1 MRMAP_TASK_PERF_REPEATS=7 MRMAP_TASK_PERF_SEED=20261121 \\
    docker compose run --rm --no-deps \\
      -e MRMAP_TASK_PERF_BENCH -e MRMAP_TASK_PERF_REPEATS -e MRMAP_TASK_PERF_SEED \\
      -e MRMAP_TASK_PERF_OUT=/opt/mrmap/task-perf \\
      -e MRMAP_USER=mrmap -e MRMAP_PASSWORD=mrmap \\
      django-tests python manage.py test \\
      tests.django.system.test_task_runtime_bench --noinput --keepdb

    python3 scripts/task_perf_bench.py load --arm baseline --seed 20261121 \\
      --fixture-dir backend/task-perf --out task-perf.jsonl
    python3 scripts/task_perf_bench.py report --in task-perf.jsonl
    python3 scripts/task_perf_bench.py compare --in task-perf.jsonl \\
      --baseline baseline --candidate sql-n-plus-one
    python3 scripts/task_perf_bench.py gate --in task-perf.jsonl \\
      --baseline scripts/task_perf_baseline.json --mode warn
    python3 scripts/task_perf_bench.py detect --in task-perf.jsonl \\
      --arm sql-n-plus-one --fail-on

``--keepdb`` matters the way it does for #1395: timings taken against a freshly
created test database describe a different state than the steady state a
deployment is in, and the environment block of every record says which one it
measured.
"""
import os
import time
import uuid
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.base import ContentFile
from django.test import TestCase, tag
from django_celery_beat.models import IntervalSchedule

from tests.django.system._task_runtime_bench_support import (
    ARMS, BENCH_ENABLED, BENCH_SKIP, EAGER_ENABLED, HEAVY_BACKLOG_RECORDS,
    HEAVY_CHUNK_SIZE, HEAVY_ENABLED, HEAVY_SKIP, REPEATS,
    attempt_rows, burn, collect_attempt_rows, cgroup_limits,
    database_fingerprint, dispatch, git_revision, oom_observed,
    peak_memory_bytes, remember_slow_body_reference, slow_body_reference,
    slow_body_seconds, write_workload)

WMS_PK = 'cd16cc1f-3abb-4625-bb96-fbe80dbe23e3'


def _now_iso():
    from django.utils import timezone
    return timezone.now().isoformat(timespec='seconds')


class BenchCase(TestCase):
    """Bookkeeping shared by the benchmarked workloads.

    ``TestCase``, not ``TransactionTestCase``: like the #1395 guards, the arms
    call the task inside the test's own atomic block, so an arm which crashes
    rolls its own fixture away instead of leaving 400 000 rows for the next
    test. The direct ``.run()`` dispatch is the default for that reason; the
    eager alternative exists for the arms whose active time must be a #1330
    measurement, and the record says which of the two it is.
    """

    #: each family names these; they are part of the workload identity
    family = None
    queue = None
    tasks = ()
    fixture = 'synthetic-deterministic'
    mock_responses = 'in-process-mock'

    def setUp(self):
        super().setUp()
        if not BENCH_ENABLED:
            self.skipTest(BENCH_SKIP)
        self.seed = int(os.environ.get('MRMAP_TASK_PERF_SEED', '20261121'))
        self.eager = EAGER_ENABLED
        self.http_calls = 0
        self.instrumentation = {'overhead_seconds': None,
                                'note': 'profiler of #1389 off for this arm'}
        self.environment = {
            'database': database_fingerprint(),
            'python': os.sys.version.split()[0],
            'platform': os.uname().sysname,
            'cores': os.cpu_count(),
            'cache': 'warm' if self.schema_was_reused() else 'cold',
            'concurrency': 1,
            'worker_count': 1,
            'dispatch': 'celery-apply-eager' if self.eager else 'direct-run',
            'cgroup': cgroup_limits() or None,
        }

    def schema_was_reused(self):
        """Whether this run reused a test database (``--keepdb``) or built one.

        Asked of the connection rather than guessed from the command line: a
        cold schema and a warm one produce different numbers, and the record has
        to say which one it holds.
        """
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from pg_class where relname = "
                "'system_celerytaskattempt'")
            return bool(cursor.fetchone()[0])

    def claim_defect(self, arm):
        """Record which defect this arm claims to run.

        An arm which claims none is the baseline; an arm which claims one and
        whose body never reached the injection writes ``injection_missing`` so a
        reader is never shown two identical arms with a beautiful CV.
        """
        self.injection = {'arm': arm,
                          'installed': [] if arm == 'baseline' else [arm],
                          'missing': []}

    def run_unit(self, scale, arm, index, body):
        """One unit of one arm, timed by the runner's own monotonic clock.

        A unit is the family's natural work item - a chunk, a probe fire, a beat
        fire - never an arbitrary request. The unit carries the runner's elapsed
        time (its end-to-end) and the attempt rows #1330 wrote for the attempts
        inside it; where the collector saw nothing (a direct ``.run()`` fires no
        signals) the runner's own reading stands in and the row says so in its
        ``quality`` list.
        """
        from django.db import connection, reset_queries
        from django.test.utils import CaptureQueriesContext
        from django.utils import timezone

        from system.models import CeleryTaskAttempt

        db_since = timezone.now()
        reset_queries()
        with CaptureQueriesContext(connection) as context:
            started = time.monotonic()
            outcome = body()
            elapsed = time.monotonic() - started
        collect_attempt_rows()
        attempts = attempt_rows(db_since)
        if not attempts:
            attempts = [{'task_id': 'runner-%s-%s' % (scale, index),
                         'task_name': self.tasks[0] if self.tasks else None,
                         'attempt_no': 0,
                         'active_seconds': round(elapsed, 6),
                         'wait_seconds': None,
                         'outcome': outcome or 'success',
                         'quality': ['no_collector_row'],
                         'queue': self.queue, 'worker': 'bench-runner'}]
        unit = {
            'id': '%s-%s' % (scale, index),
            'elapsed_seconds': round(elapsed, 6),
            'attempts': attempts,
            'sql': {'statements': len(context.captured_queries),
                    'total_ms': round(sum(
                        float(query.get('time_ms') or 0.0)
                        for query in context.captured_queries), 3)},
            'http': {'calls': self.http_calls},
            'outcome': outcome or 'success',
        }
        CeleryTaskAttempt.objects.all().delete()
        return unit

    def write_arm(self, scale, arm, units, body, records=None, chunks=None,
                  chunk_size=None, attempts_per_unit=1, notes=''):
        """Run one arm over every planned repeat and write one file per repeat.

        Repeats rather than one longer run: repeatability is a property of
        independent runs of the same fixed workload, and the analyzer's
        stability floor reads the spread of their medians.
        """
        # the closure a caller built before this call runs inside it, so the cell
        # it belongs to has to be published here for the slow-body injection to
        # look its own reference up (see `slow_body_reference`)
        self._bench_scale = scale
        written = []
        for repeat in range(1, REPEATS + 1):
            self.http_calls = 0
            started = time.monotonic()
            collected = [self.run_unit(scale, arm, index, body)
                         for index in range(units)]
            elapsed = time.monotonic() - started
            peak = peak_memory_bytes()
            spec = {
                'schema': 'mrmap.task-perf.v1',
                'kind': 'load',
                'family': self.family,
                'arm': arm,
                'fixture': self.fixture,
                'scale': scale,
                'records': records if records is not None else units,
                'chunks': chunks,
                'chunk_size': chunk_size,
                'attempts_per_unit': attempts_per_unit,
                'queue': self.queue,
                'queue_config': os.environ.get(
                    'MRMAP_TASK_PERF_QUEUE_CONFIG',
                    'in-process dispatch, prefetch_multiplier=1'),
                'concurrency': 1,
                'worker_count': 1,
                'mock_responses': self.mock_responses,
                'tasks': list(self.tasks),
                'seed': self.seed,
                'repeat': repeat,
                'repeats_planned': REPEATS,
                'ts': _now_iso(),
                'revision': git_revision(),
                'environment': self.environment,
                'workload': {'units': len(collected),
                             'attempts': sum(len(unit['attempts'])
                                             for unit in collected)},
                'units': collected,
                'pressure': {
                    'occupied_slot_seconds': {
                        'value': round(sum(
                            attempt['active_seconds'] or 0.0
                            for unit in collected for attempt in unit['attempts']
                            if attempt.get('outcome')), 6),
                        'evidence': 'derived'},
                    'resource': {'peak_rss_bytes': peak,
                                 'oom_observed': oom_observed(),
                                 'evidence': 'measured'},
                },
                'sql': {
                    'statements': {'value': sum(unit['sql']['statements']
                                                for unit in collected),
                                   'evidence': 'measured'},
                    'total_ms': {'value': round(sum(unit['sql']['total_ms']
                                                    for unit in collected), 3),
                                 'evidence': 'measured'}},
                'http': {'calls': {'value': self.http_calls,
                                   'evidence': 'measured'}},
                'instrumentation': self.instrumentation,
                'correlation': {'slow_task': None},
                'quality': {'evidence': 'measured' if self.eager
                            else 'measured_local',
                            'injection': getattr(self, 'injection', None),
                            'runner_elapsed_seconds': round(elapsed, 6)},
                'notes': notes,
            }
            written.append(write_workload(self.family, scale, arm, repeat, spec))
            if arm == 'baseline' and collected:
                # the arms of a cell run baseline first, so handing on its cost
                # is what lets the slow-body arm be twice *this* workload rather
                # than a fixed 50 ms - noise on a chunk, signal on a probe
                costs = sorted(unit['elapsed_seconds'] for unit in collected)
                remember_slow_body_reference(
                    self.family, scale, costs[len(costs) // 2])
        return written


# ------------------------------------------------------------- harvesting chunk


@tag('bench', 'system', 'celery')
class ImportChunkRuntimeBench(BenchCase):
    """The import of a bounded backlog chunk, timed (#859 / #895 shapes).

    The reference family, because it is the shape the epic names: a per-record
    locked read inside a chunk loop, so all three injected defects have a natural
    place to hide - one read per record too many, one remote answer per record
    instead of per chunk (#1392's bug), and CPU time which is neither.
    """

    family = 'harvesting.import_chunk'
    queue = 'harvest-import'
    tasks = ('registry.tasks.harvest.call_md_metadata_files_to_db',)
    fixture = 'synthetic-xml-backlog'
    mock_responses = 'mapper-mocked-lxml-200'

    SIZES = {'typical': 100, 'large': 1000}

    def setUp(self):
        super().setUp()
        from registry.enums.harvesting import HarvestingPhaseEnum as Phase
        from registry.models.harvest import HarvestingJob

        self.Phase = Phase
        self.HarvestingJob = HarvestingJob
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        from django.test import override_settings
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)

    def _seed(self, count):
        from registry.models.harvest import TemporaryMdMetadataFile

        job = self.HarvestingJob.objects.create(
            total_records=count, phase=self.Phase.RECORDS_TO_DB)
        rows = []
        for number in range(count):
            stored = TemporaryMdMetadataFile(job=job)
            stored.md_metadata_file.save('record_%d.xml' % number,
                                         ContentFile(b'<record/>'), save=False)
            rows.append(stored)
        TemporaryMdMetadataFile.objects.bulk_create(rows, batch_size=500)
        return job

    def _body(self, arm, job, ids):
        from registry.models.harvest import TemporaryMdMetadataFile
        from registry.tasks.harvest import call_md_metadata_files_to_db
        from tests.django.registry.tasks.tests_harvest_import_fan_out import (
            HTTP_REQUEST, imports_a_record)

        counters = {'remote': 0, 'extra': 0}

        def import_one(record):
            if arm == 'sql-n-plus-one':
                # the injected N+1: one read of the job per record, the shape of
                # a `job = Job.objects.get(...)` inside a chunk loop
                self.HarvestingJob.objects.filter(pk=job.pk).exists()
                counters['extra'] += 1
            if arm == 'duplicate-remote-call':
                # the injected duplicate fetch: one "remote" answer per record
                # where the reviewed shape asks for one per chunk (#1392)
                counters['remote'] += 1
                self.http_calls += 1
            return imports_a_record(record)

        def body():
            if arm == 'slow-body':
                burn(slow_body_seconds(
                    slow_body_reference(self.family, self._bench_scale)))
            with patch.object(TemporaryMdMetadataFile,
                              'md_metadata_file_to_db', import_one):
                dispatch(call_md_metadata_files_to_db, {
                    'md_metadata_file_ids': list(ids),
                    'harvesting_job_id': job.pk,
                    'background_process_pk': job.background_process_id,
                    'http_request': HTTP_REQUEST}, self.eager)
            if arm == 'sql-n-plus-one' and counters['extra'] != len(ids):
                self.injection['missing'].append(
                    'per-record read fired %d of %d times'
                    % (counters['extra'], len(ids)))
            if arm == 'duplicate-remote-call' and counters['remote'] != len(ids):
                self.injection['missing'].append(
                    'duplicate fetch fired %d of %d times'
                    % (counters['remote'], len(ids)))
            return 'success'
        return body

    def test_typical_chunk(self):
        self._run_scale('typical')

    def test_large_chunk(self):
        self._run_scale('large')

    def _run_scale(self, scale):
        from registry.models.harvest import TemporaryMdMetadataFile

        count = self.SIZES[scale]
        for arm in ARMS:
            self.claim_defect(arm)
            job = self._seed(count)
            ids = list(TemporaryMdMetadataFile.objects
                       .filter(job=job).order_by('id')
                       .values_list('id', flat=True))
            self.assertEqual(len(ids), count)
            self.write_arm(scale, arm, 1, self._body(arm, job, ids),
                           records=count, chunks=1, chunk_size=count,
                           notes='bounded import chunk over %d backlog rows'
                                 % count)


# --------------------------------------------------------------- catalogue fan-out


@tag('bench', 'system', 'celery')
class TotalRecordsFanOutRuntimeBench(BenchCase):
    """The planning fan-out of one harvest, timed over its round-trip count.

    The scale axis is the number of catalogue pages the fan-out plans - the same
    axis the #1395 guard of #1392 pinned as flat (1 / 10 / 100+ pages), measured
    here in time and in statements, so a slope the guard would name and a slope
    the stopwatch would name agree or one of them is being read wrong.
    """

    family = 'harvesting.fan_out'
    queue = 'download'
    tasks = ('registry.tasks.harvest.call_fetch_total_records',)
    fixture = 'synthetic-catalogue-pages'
    mock_responses = 'in-process-mock-GetRecords'

    SIZES = {'typical': 50, 'large': 5000}

    def setUp(self):
        super().setUp()
        # the planning fire falls back to the deployment's own request context,
        # which names the superuser the deployment seeded (settings.MRMAP_USER,
        # #1278). A benchmark must not depend on how the test database happened
        # to be created, so the arm seeds and names that account itself.
        from django.contrib.auth import get_user_model
        from django.test import override_settings

        # a password a human could never use, because nobody uses it: this row
        # exists so the task's request context has a user to name
        self.admin_user = get_user_model().objects.create_superuser(
            username='bench-deployment-admin',
            password='bench-only-not-a-real-credential')
        override = override_settings(MRMAP_USER=self.admin_user.username)
        override.enable()
        self.addCleanup(override.disable)

    def _body(self, arm, job, total):
        from registry.models.harvest import HarvestingJob
        from registry.tasks.harvest import call_fetch_total_records

        counters = {'remote': 0}

        def fetch(pending_job):
            counters['remote'] += 1
            self.http_calls += 1
            if arm == 'duplicate-remote-call':
                # the injected duplicate: the catalogue asked again for what the
                # fan-out already knows
                counters['remote'] += 1
                self.http_calls += 1
            pending_job.total_records = total

        def body():
            if arm == 'sql-n-plus-one':
                # one extra read per planned page - the shape of the per-page
                # request-context read the #1395 guard names
                for _ in range(max(1, total // 50)):
                    HarvestingJob.objects.filter(pk=job.pk).exists()
            if arm == 'slow-body':
                burn(slow_body_seconds(
                    slow_body_reference(self.family, self._bench_scale)))
            with patch.object(HarvestingJob, 'fetch_total_records', fetch):
                with patch('registry.models.harvest.chord'):
                    with self.captureOnCommitCallbacks(execute=True):
                        dispatch(call_fetch_total_records,
                                 {'harvesting_job_id': job.pk}, self.eager)
            if arm == 'duplicate-remote-call' and counters['remote'] < 2:
                self.injection['missing'].append('duplicate fetch did not fire')
            return 'success'
        return body

    def test_typical_fan_out(self):
        self._run_scale('typical')

    def test_large_fan_out(self):
        self._run_scale('large')

    def _run_scale(self, scale):
        from registry.enums.harvesting import HarvestingPhaseEnum as Phase
        from registry.models.harvest import HarvestingJob

        total = self.SIZES[scale]
        pages = max(1, total // 50)
        for arm in ARMS:
            self.claim_defect(arm)
            job = HarvestingJob.objects.bulk_create([HarvestingJob(
                total_records=None, phase=Phase.DOWNLOAD_RECORDS)])[0]
            self.write_arm(scale, arm, 1, self._body(arm, job, total),
                           records=total, chunks=pages, chunk_size=50,
                           notes='planning fan-out over %d catalogue records in '
                                 '%d planned pages' % (total, pages))


# --------------------------------------------------------------------- monitoring


@tag('bench', 'system', 'celery')
class ProbeCheckRuntimeBench(BenchCase):
    """Monitoring probe checks against a mocked remote, timed.

    The monitoring family is where the HTTP-bound tasks live, so
    ``duplicate-remote-call`` is its natural defect and queue wait matters most:
    the checks of one run are a fan-out, and "the probe was slow" versus "the
    probe waited" is the whole reading (#1330's example, applied to monitoring).
    GetMap is the widest probe kind, so it is the arm that gets measured.
    """

    family = 'monitoring.wms'
    queue = 'monitoring'
    tasks = ('registry.tasks.monitoring.run_probe_check',)
    fixture = 'synthetic-getmap-probe'
    mock_responses = 'patched-ogc-client-200'
    fixtures = ['test_users.json', 'test_keywords.json', 'test_wms.json']

    SIZES = {'typical': 10, 'large': 100}

    def setUp(self):
        super().setUp()
        # the media root first, then the stored capabilities document: the
        # document is written into whatever MEDIA_ROOT answers at save time, so
        # a probe run whose storage points elsewhere fails with
        # CapabilitiesBackupMissing before its first mocked request
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        from django.test import override_settings
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        from tests.django.registry.tasks.tests_monitoring import (
            setup_capabilitites_file)
        setup_capabilitites_file()

    def _seed(self, count):
        from registry.models.monitoring import (GetMapProbe,
                                                WebMapServiceMonitoringRun,
                                                WebMapServiceMonitoringSetting)
        from registry.models.service import WebMapService

        service = WebMapService.objects.get(pk=WMS_PK)
        interval = IntervalSchedule.objects.create(every=1, period='days')
        setting = WebMapServiceMonitoringSetting.objects.create(
            service=service, interval=interval,
            # the setting IS a PeriodicTask subclass, and its name is unique:
            # one bench method seeds several arms, each with its own setting
            name='bench wms monitoring %s' % uuid.uuid4())
        run = WebMapServiceMonitoringRun.objects.create(setting=setting)
        probes = []
        for _ in range(count):
            probe = GetMapProbe.objects.create(setting=setting)
            probe.layers.set(service.layers.all())
            probes.append(probe)
        return run, probes

    def _body(self, arm, run, probes):
        from registry.ows_lib.client.core import OgcClient
        from registry.tasks.monitoring import run_probe_check
        from tests.django.registry.tasks.tests_monitoring import side_effect

        counters = {'calls': 0}

        def send_request(*args, **kwargs):
            counters['calls'] += 1
            self.http_calls += 1
            if arm == 'duplicate-remote-call':
                # the injected duplicate: the same answer asked for twice per
                # check, the shape of a forgotten per-probe capabilities read
                counters['calls'] += 1
                self.http_calls += 1
            return side_effect(*args, **kwargs)

        def body():
            if arm == 'sql-n-plus-one':
                # one extra read of the setting per probe - what a
                # `setting = Setting.objects.get(pk=...)` inside the probe loop
                # of a fan-out parent costs
                from registry.models.monitoring import (
                    WebMapServiceMonitoringSetting)
                for _probe in probes:
                    WebMapServiceMonitoringSetting.objects.filter(
                        pk=run.setting_id).exists()
            if arm == 'slow-body':
                burn(slow_body_seconds(
                    slow_body_reference(self.family, self._bench_scale)))
            with patch.object(OgcClient, 'send_request',
                              side_effect=send_request):
                for probe in probes:
                    dispatch(run_probe_check, {
                        'probe_model': probe._meta.label_lower,
                        'run_model': run._meta.label_lower,
                        'probe_pk': probe.pk, 'run_pk': run.pk}, self.eager)
            if arm == 'duplicate-remote-call' \
                    and counters['calls'] < 2 * len(probes):
                self.injection['missing'].append(
                    'duplicate call fired %d times over %d probes'
                    % (counters['calls'], len(probes)))
            return 'success'
        return body

    def test_probe_fan_out(self):
        for scale in self.SIZES:
            count = self.SIZES[scale]
            for arm in ARMS:
                self.claim_defect(arm)
                run, probes = self._seed(count)
                # one unit is one fire of the run's probe fan-out, not one
                # probe: units x probes would measure a quadratic of its own
                self.write_arm(scale, arm, 1, self._body(arm, run, probes),
                               records=count, chunks=1, chunk_size=count,
                               attempts_per_unit=count,
                               notes='%d GetMap probe checks against a mocked '
                                     'remote' % count)


# ------------------------------------------------------------------- housekeeping


@tag('bench', 'system', 'celery')
class HousekeepingRuntimeBench(BenchCase):
    """The beat-scheduled housekeeping fire, timed at two table sizes.

    ``bound_task_attempt_samples`` is the family every deployment pays on every
    interval, and #1395 pinned its statement shape as page-bound. The runtime
    question is the same question in seconds: does a fire cost the same with a
    full table as with an empty one, and what does it cost? A beat task which
    drifted to minutes would be invisible to a statement guard and obvious here -
    which is why the ``sql-n-plus-one`` arm of this family reintroduces exactly
    the regression that guard forbids, so the two readings must agree.
    """

    family = 'housekeeping.system'
    queue = 'db-routines'
    tasks = ('system.tasks.bound_task_attempt_samples',)
    fixture = 'synthetic-attempt-rows'
    mock_responses = 'none'

    SIZES = {'typical': 1, 'large': 1000}

    def _seed(self, count):
        from tests.django.system.test_task_sql_guards import seed_attempt
        for _ in range(count):
            seed_attempt(outcome='', started_ago_seconds=10 * 24 * 3600)
        return count

    def _body(self, arm):
        from django.test import override_settings
        from system.models import CeleryTaskAttempt
        from system.tasks import bound_task_attempt_samples

        def body():
            if arm == 'sql-n-plus-one':
                # one extra read per attempt row rather than per page of 500 -
                # the regression #1395's page-shape guard forbids, and the case
                # the time side has to catch too
                for pk in (CeleryTaskAttempt.objects.filter(outcome='')
                           .values_list('pk', flat=True)
                           .iterator(chunk_size=500)):
                    CeleryTaskAttempt.objects.filter(pk=pk).exists()
            if arm == 'slow-body':
                burn(slow_body_seconds(
                    slow_body_reference(self.family, self._bench_scale)))
            with override_settings(CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                                   CAPACITY_TELEMETRY_MAX_ATTEMPTS=0):
                dispatch(bound_task_attempt_samples, {}, self.eager)
            return 'success'
        return body

    def test_housekeeping_fire(self):
        from system.models import CeleryTaskAttempt
        for scale in self.SIZES:
            count = self.SIZES[scale]
            for arm in ARMS:
                self.claim_defect(arm)
                CeleryTaskAttempt.objects.all().delete()
                self._seed(count)
                self.write_arm(scale, arm, 1, self._body(arm),
                               records=count, chunks=1, chunk_size=500,
                               notes='one beat fire over %d open attempts' % count)


# ------------------------------------------------------------------ heavy backlog


@tag('bench', 'system', 'celery', 'heavy')
class BacklogHeavyRuntimeBench(BenchCase):
    """The 400k-record backlog arm, transferred from #1392.

    What that acceptance asks of this arm, and what it asks NOT to do:

    *   the backlog is seeded in bounded chunks and read back through an
        iterator with a chunk size - the rows are never all materialized in
        Python, because a benchmark which dies on its own fixture measures
        nothing about the task;
    *   the import runs in bounded chunks of ``MRMAP_TASK_PERF_CHUNK_SIZE``
        messages with the per-record mapper mocked to its own measured cost. The
        mapper's real cost is the ``harvesting.import_chunk`` family's business;
        this arm answers the backlog-side questions - query growth with backlog
        size, bounded row materialization, and the chunk fan-out over a big
        table;
    *   peak RSS and whether the cgroup reports an OOM kill are recorded, per
        "including whether OOM occurs". A peak against the recorded cgroup limit
        is stated as what it is, and an unreadable limit is ``null`` rather than
        a comforting zero.

    The comparison is against an explicitly identified baseline: the same
    workload at the 1 / 10 / 100+ rungs of the ladder plus a full backlog run,
    all of them in the same file set and all named by their workload digest, so
    `compare` can only pair arms which really describe the same workload.
    """

    family = 'harvesting.import_chunk'
    queue = 'harvest-import'
    tasks = ('registry.tasks.harvest.call_md_metadata_files_to_db',)
    fixture = 'synthetic-backlog-400k'
    mock_responses = 'mapper-mocked'

    def setUp(self):
        super().setUp()
        if not HEAVY_ENABLED:
            self.skipTest(HEAVY_SKIP)

    def _seed(self, job, count):
        """Rows in bounded batches: the whole backlog exists once, in the DB."""
        from registry.models.harvest import TemporaryMdMetadataFile

        batch = 10_000
        created = 0
        for offset in range(0, count, batch):
            size = min(batch, count - offset)
            rows = [TemporaryMdMetadataFile(
                job=job, has_import_error=False,
                requested_url='http://example.invalid/record/%d' % number)
                for number in range(offset, offset + size)]
            TemporaryMdMetadataFile.objects.bulk_create(rows, batch_size=2000)
            del rows
            created += size
        return created

    def _body(self, arm, job, count):
        from registry.models.harvest import TemporaryMdMetadataFile
        from registry.tasks.harvest import call_md_metadata_files_to_db
        from tests.django.registry.tasks.tests_harvest_import_fan_out import (
            HTTP_REQUEST, imports_a_record)

        counters = {'extra': 0, 'remote': 0, 'chunks': 0}

        def import_one(record):
            if arm == 'sql-n-plus-one':
                TemporaryMdMetadataFile.objects.filter(pk=record.pk).exists()
                counters['extra'] += 1
            if arm == 'duplicate-remote-call':
                counters['remote'] += 1
                self.http_calls += 1
            return imports_a_record(record)

        def run_chunk(chunk_ids):
            counters['chunks'] += 1
            with patch.object(TemporaryMdMetadataFile,
                              'md_metadata_file_to_db', import_one):
                dispatch(call_md_metadata_files_to_db, {
                    'md_metadata_file_ids': list(chunk_ids),
                    'harvesting_job_id': job.pk,
                    'background_process_pk': job.background_process_id,
                    'http_request': HTTP_REQUEST}, self.eager)

        def body():
            if arm == 'slow-body':
                burn(slow_body_seconds(
                    slow_body_reference(self.family, self._bench_scale)))
            # ids stream out in bounded pages: the backlog is iterated, never
            # materialized (#1392's transferred acceptance)
            ids = (TemporaryMdMetadataFile.objects
                   .filter(job_id=job.pk)
                   .order_by('id')
                   .values_list('id', flat=True)
                   .iterator(chunk_size=HEAVY_CHUNK_SIZE))
            chunk = []
            for pk in ids:
                chunk.append(pk)
                if len(chunk) >= HEAVY_CHUNK_SIZE:
                    run_chunk(chunk)
                    chunk = []
            if chunk:
                run_chunk(chunk)
            if arm == 'sql-n-plus-one' and counters['extra'] != count:
                self.injection['missing'].append(
                    'per-record read fired %d of %d times'
                    % (counters['extra'], count))
            if arm == 'duplicate-remote-call' and counters['remote'] != count:
                self.injection['missing'].append(
                    'duplicate call fired %d of %d times'
                    % (counters['remote'], count))
            return 'success'
        return body

    def test_backlog_query_growth(self):
        from registry.enums.harvesting import HarvestingPhaseEnum as Phase
        from registry.models.harvest import HarvestingJob

        ladder = (1, 10, 100, HEAVY_BACKLOG_RECORDS)
        for arm in ARMS:
            for size in ladder:
                self.claim_defect(arm)
                job = HarvestingJob.objects.create(
                    total_records=size, phase=Phase.RECORDS_TO_DB)
                self.assertEqual(self._seed(job, size), size,
                                 'the backlog the record names is the backlog '
                                 'that exists')
                self.write_arm(str(size), arm, 1, self._body(arm, job, size),
                               records=size,
                               chunks=max(1, -(-size // HEAVY_CHUNK_SIZE)),
                               chunk_size=HEAVY_CHUNK_SIZE,
                               notes='backlog growth ladder rung %d of %s; the '
                                     'mapper is mocked, the backlog-side work '
                                     'is measured' % (size, list(ladder)))
                job.delete()

    def test_backlog_drain_and_recovery(self):
        """Drain rate and recovery of the backlog, as the transferred item asks.

        Drain rate is *derived* and labelled as such: it is the fixed workload of
        this arm divided by measured time, so the analyzer sees the derivation and
        a reader sees the samples behind it. Recovery is measured the way #891's
        recovery path is checked - a backlog which is published a second time must
        not import a record twice - by counting what the drain left behind.
        """
        from registry.enums.harvesting import HarvestingPhaseEnum as Phase
        from registry.models.harvest import (HarvestingJob,
                                             TemporaryMdMetadataFile)

        size = HEAVY_BACKLOG_RECORDS
        self.claim_defect('baseline')
        job = HarvestingJob.objects.create(
            total_records=size, phase=Phase.RECORDS_TO_DB)
        self._seed(job, size)
        written = self.write_arm(
            'drain', 'baseline', 1, self._body('baseline', job, size),
            records=size, chunks=max(1, -(-size // HEAVY_CHUNK_SIZE)),
            chunk_size=HEAVY_CHUNK_SIZE,
            notes='drain rate of a %d-row backlog in chunks of %d'
                  % (size, HEAVY_CHUNK_SIZE))
        left = TemporaryMdMetadataFile.objects.filter(job=job).count()
        self.assertEqual(
            left, 0,
            'a chunk which imported its records retired them; %d left behind '
            'means the drain was not a drain' % left)
        self.assertTrue(written, 'the drain arm wrote no workload file')
        # bounded materialization, asserted from the process the run left behind
        # rather than from an expectation about the code
        limit = (self.environment.get('cgroup') or {}).get('cgroup_limit_bytes')
        peak = peak_memory_bytes()
        if limit:
            self.assertLess(peak, limit,
                            'the drain peaked at %d bytes against a %d byte '
                            'ceiling' % (peak, limit))
        job.delete()
