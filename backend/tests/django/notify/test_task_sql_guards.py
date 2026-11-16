"""Task-side SQL guards for the operational watchdog fire (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
the watchdog"). The beat task ``watch_operational_work`` runs every interval,
so its per-fire cost is multiplied by the lifetime of the deployment. What
this pins, per the #1395 coverage checklist:

*   the READ side is constant in the number of standing processes - the
    stale-window scan is one set-based SELECT (#1320's design), and no
    process is ever read a second time;
*   the WRITE side grows exactly with the verdicts published - the workload
    of the fire IS its verdicts, so linear in the verdicts is the honest
    shape, and this guard is what keeps it from turning linear in the
    merely watched processes;
*   a dark broker publishes nothing and pays no process reads for it;
*   and the two retention sweeps of the same family (processes #1208,
    incidents #1319), which the audit classes as already optimal, keep
    their windowed-delete shape - constant statements whatever the
    expired history holds, and nothing standing is touched.

The numbers below are statements and rows, not runtime (V1 scope; #1396 owns
timings).
"""
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils.timezone import now
from notify.enums import (IncidentSeverityEnum, IncidentSourceEnum,
                          IncidentStatusEnum, ProcessStatusEnum)
from notify.incident_watchdog import watch_operational_work
from notify.models import (BackgroundProcess, OperationalIncident,
                           purge_expired_background_processes,
                           purge_expired_operational_incidents)
from registry.models.metadata import MetadataContact
from registry.models.service import WebMapService
from tests.django.notify.test_incident_watchdog import (INSPECT,
                                                        WatchdogTestMixin,
                                                        broker)
from tests.django.sql_guard import SqlGuardMixin, statements_of

PROCESS_TABLE = BackgroundProcess._meta.db_table
INCIDENT_TABLE = OperationalIncident._meta.db_table


class WatchdogFireMixin(WatchdogTestMixin):
    """Seam: stalled processes like #1038 left behind, fired against an empty broker."""

    def _stalled_processes(self, count):
        """``count`` services with an open process whose retry window expired.

        The real seam of #1207/#1038 driven like the neighbour watchdog
        tests: an open process reporting a retry written back into the
        past, the attempt never coming. Each stalled operation names its
        own typed resource - a verdict and its dedup key (#1319) are per
        resource, so distinct resources are distinct verdicts.
        """
        contact = MetadataContact.objects.create(
            name=f'watchdog contact {MetadataContact.objects.count()}')
        for index in range(count):
            service = WebMapService.objects.create(
                title=f'watchdog growth service {index}',
                version=130, origin=1,
                service_url=f'http://watchdog-growth.example.org/{index}',
                metadata_contact=contact, service_contact=contact)
            self.build_process(related=service, window_minutes_ago=30)

    def _healthy_processes(self, count):
        """``count`` open processes whose retry window is NOT yet expired."""
        contact = MetadataContact.objects.create(
            name=f'watchdog contact {MetadataContact.objects.count()}')
        for index in range(count):
            service = WebMapService.objects.create(
                title=f'watchdog healthy service {index}',
                version=130, origin=1,
                service_url=f'http://watchdog-healthy.example.org/{index}',
                metadata_contact=contact, service_contact=contact)
            process = self.build_process(related=service,
                                         window_minutes_ago=None)
            # a window due in the FUTURE: open, reported, healthy
            BackgroundProcess.objects.report_retry(
                process.pk, reason="the service did not answer once",
                until=now() + timedelta(minutes=5))

    def _reset(self):
        """Start the next measured fire with a clean board.

        Both tables go through a queryset delete (seed work, not measured):
        a standing verdict of an earlier fire would re-pay its standing
        UPDATE and blur the per-verdict measurement, and a process of an
        earlier fire would widen the scan beyond the seeded size.
        """
        OperationalIncident.objects.all().delete()
        BackgroundProcess.objects.all().delete()

    def _fire(self):
        """One fire with an empty broker: no worker reports any work."""
        def run():
            with patch(INSPECT) as inspect:
                broker(inspect)
                return watch_operational_work()
        return run


class WatchdogFireReadsConstantTest(WatchdogFireMixin, SqlGuardMixin,
                                    TestCase):
    """One fire reads the deployment as sets, never per process."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def test_the_scan_stays_one_statement_per_table(self):
        """1 vs 10 stalled windows: same SELECTs over the same tables.

        The failure this catches is the per-process read pretending to be
        a scan: the fire may read the process table and the incident table
        a fixed number of times total - the stale-window scan, the stale
        verdict sweep and, if a queue stands empty, the consumer check.
        """
        for size in (1, 10):
            with self.subTest(size=size):
                self._reset()
                self._stalled_processes(size)
                _, context = self.capture(self._fire())
                # the same fire with nothing standing: the constant part
                clean = self._capture_clean()
                process_reads = statements_of(
                    context, verb='select', table=PROCESS_TABLE)
                incident_reads = statements_of(
                    context, verb='select', table=INCIDENT_TABLE)
                self.assertEqual(len(process_reads), len(statements_of(
                    clean, verb='select',
                    table=PROCESS_TABLE)),
                    'the process reads of a fire do not depend on how many '
                    'stalled windows stand in the table')
                # the incident table is read once by the sweep AND once per
                # verdict by the dedup probe of report() (#1319) - the
                # per-verdict share is the fire's own output, so the bound
                # is the sweep plus the seeded windows, never more
                incident_base = len(statements_of(
                    clean, verb='select', table=INCIDENT_TABLE))
                self.assertLessEqual(
                    len(incident_reads), incident_base + size,
                    msg=f'the fire over {size} windows read the incident '
                        f'table {len(incident_reads)} times beyond the '
                        f'{incident_base} of a clean fire - one dedup '
                        f'probe per verdict is the ceiling')

    def _capture_clean(self):
        """The fire's statements with nothing standing to judge."""
        self._reset()
        return self.capture(self._fire())[1]

    def test_no_statement_repeats_per_watch_process(self):
        """A fingerprint never repeats per watched process.

        The report of #1319 reads and moves ONE incident per verdict -
        those statements repeat per verdict (the fire's own output, bounded
        by the seeded size); anything else repeating is a per-row read.
        """
        self._stalled_processes(5)

        def fire():
            with patch(INSPECT) as inspect:
                broker(inspect)
                return watch_operational_work()

        self.assertNoNPlusOne(
            fire,
            sanctioned={INCIDENT_TABLE: 5},
            label='the watchdog fire over 5 stalled windows')

    def test_a_dark_fire_reads_no_process_rows(self):
        """The broker dark: nothing is published and no row is asked."""
        self._stalled_processes(3)

        def dark_fire():
            with patch(INSPECT) as inspect:
                broker(inspect, dark=True)
                return watch_operational_work()

        _, context = self.capture(dark_fire)
        process_reads = statements_of(
            context, verb='select', table=PROCESS_TABLE)
        self.assertEqual(
            process_reads, [],
            'a fire which publishes nothing must not read the processes it '
            'will not judge (#1320: the dark fire returns early)')


class WatchdogFireWritesScaleWithVerdictsTest(WatchdogFireMixin,
                                              SqlGuardMixin, TestCase):
    """The fire's writes ARE its verdicts - exactly, not more."""

    fixtures = ["test_users.json", "test_keywords.json", "test_crs.json",
                "test_wms.json", "test_csw.json"]

    def test_the_write_slope_is_the_verdict_count_exactly(self):
        """statements(N verdicts) - statements(0) == N times one verdict.

        No magic constant: the cost of ten verdicts is measured against the
        cost of one, so an extra statement creeping into the per-verdict
        report OR a per-row read both fail the slope, while #1396 may move
        the per-verdict cost itself without touching this guard.
        """
        measured = {}
        verdicts = {}
        for size in (0, 1, 10):
            self._reset()
            self._stalled_processes(size)
            _, context = self.capture(self._fire())
            measured[size] = len(context.captured_queries)
            verdicts[size] = OperationalIncident.objects.filter(
                status=IncidentStatusEnum.ACTIVE.value).count()
        self.assertEqual(verdicts, {0: 0, 1: 1, 10: 10},
                         'every stalled window became exactly one verdict')
        one_verdict = measured[1] - measured[0]
        self.assertGreater(one_verdict, 0, 'publishing does cost something')
        self.assertEqual(
            measured[10] - measured[0], 10 * one_verdict,
            msg=f'the fire over 10 verdicts costs {measured[10] - measured[0]} '
                f'statements beyond idle, but one verdict costs '
                f'{one_verdict} - something grows per process, not per '
                f'verdict')

    def test_healthy_processes_cost_no_writes(self):
        """Windows which have NOT expired: zero verdicts, zero writes.

        A deployment with many RUNNING processes must not cost the fire a
        single write.
        """
        self._healthy_processes(10)
        _, context = self.capture(self._fire())
        writes = [q for q in context.captured_queries
                  if q['sql'].lstrip().lower().startswith(
                      ('insert', 'update', 'delete'))]
        self.assertEqual(
            writes, [],
            f'a healthy deployment costs the fire {len(writes)} writes')


class HousekeepingSweepScalingTest(SqlGuardMixin, TestCase):
    """The retention sweeps of the notify housekeeping family (#1208/#1319).

    The audit classes both as *already optimal* - "one windowed SELECT +
    delete". This is the regression guard it asks for: the sweep's
    statements are constant in the number of expired rows (rows go in
    batches, never per row), and nothing which stands is touched.
    """

    PAST = timedelta(days=30)

    def test_the_process_sweep_grows_not_with_the_expired_history(self):
        """1 vs 100 decided-and-expired processes: same statements.

        Also the correctness half: an open process is never deleted out
        of the history by a sweep - the history is bounded, a running job
        is not.
        """
        def seed(size):
            for index in range(size):
                BackgroundProcess.objects.create(
                    process_type=f'harvesting-{index}',
                    description='a decided run of the past',
                    status=ProcessStatusEnum.COMPLETED.value,
                    done_at=now() - self.PAST)

        measured = self.assertQueryCountIndependent(
            sizes=(1, 10, 100), seed=seed,
            run=lambda: purge_expired_background_processes(retention_days=7),
            label='the background-process retention sweep')
        self.assertEqual(measured[1], measured[100],
                         'the sweep is a windowed delete, not a per-row one')

        survivor = BackgroundProcess.objects.create(
            process_type='harvesting', description='still running')
        purge_expired_background_processes(retention_days=7)
        self.assertTrue(
            BackgroundProcess.objects.filter(pk=survivor.pk).exists(),
            'an open process is never purged')

    def test_the_incident_sweep_takes_only_the_resolved_past(self):
        """Resolved-and-expired go in constant statements; active stays."""
        def seed(size):
            for index in range(size):
                OperationalIncident.objects.report(
                    code=f'test:purge-{index}',
                    source=IncidentSourceEnum.SYSTEM.value,
                    severity=IncidentSeverityEnum.WARNING.value,
                    summary='a resolved problem of the past')
        seed(1)
        OperationalIncident.objects.update(
            status=IncidentStatusEnum.RESOLVED.value,
            resolved_at=now() - self.PAST)

        def seed_more(size):
            seed(size)
            OperationalIncident.objects.filter(
                status=IncidentStatusEnum.ACTIVE.value).update(
                    status=IncidentStatusEnum.RESOLVED.value,
                    resolved_at=now() - self.PAST)

        measured = self.assertQueryCountIndependent(
            sizes=(1, 10, 100), seed=seed_more,
            run=lambda: purge_expired_operational_incidents(retention_days=7),
            label='the incident retention sweep')
        self.assertEqual(measured[1], measured[100],
                         'the sweep is a windowed delete, not a per-row one')

        standing, _ = OperationalIncident.objects.report(
            code='test:standing',
            source=IncidentSourceEnum.SYSTEM.value,
            severity=IncidentSeverityEnum.WARNING.value,
            summary='an open problem')
        purge_expired_operational_incidents(retention_days=7)
        self.assertTrue(
            OperationalIncident.objects.filter(pk=standing.pk).exists(),
            'an active incident is the open problem itself - never purged')
