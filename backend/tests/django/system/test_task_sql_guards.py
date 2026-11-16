"""Task-side SQL guards for the system housekeeping tasks (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
system housekeeping"). ``bound_task_attempt_samples`` (#1330) sweeps the
attempt table three times; the checklist asks: "constant statements per page
of 500". The abandon loop is page-bound by design - growth per PAGE is fine,
growth per ROW is the regression. The ``recorded_at`` index the audit names
as a candidate is #1394's migration; until it lands, the retention sweeps are
guarded for statement count, not plan.
"""
import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from system.models import CeleryTaskAttempt
from system.tasks import bound_task_attempt_samples
from tests.django.sql_guard import SqlGuardMixin


def seed_attempt(outcome='success', started_ago_seconds=0, quality=None):
    """One attempt row as the #1330 collector would have written it."""
    started = timezone.now() - timedelta(seconds=started_ago_seconds)
    terminal = outcome != ''
    return CeleryTaskAttempt.objects.create(
        task_id=str(uuid.uuid4()), attempt_no=0,
        task_name='some.task', queue='default', worker='celery@a',
        started_at=started,
        finished_at=started + timedelta(seconds=2) if terminal else None,
        active_seconds=2.0 if terminal else None,
        outcome=outcome, quality=quality or [])


class AttemptSweepPageShapeTest(SqlGuardMixin, TestCase):
    """The abandon sweep pays per page, never per row."""

    TEN_DAYS = 10 * 24 * 3600

    def _open_attempts(self, count):
        for _ in range(count):
            seed_attempt(outcome='', started_ago_seconds=self.TEN_DAYS)

    def test_flagging_grows_with_pages_not_rows(self):
        # one page: one read, one bulk write, and the page-bound stop
        self._open_attempts(1)
        with override_settings(CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=0):
            _, one_page = self.capture(bound_task_attempt_samples.run)
        first = len(one_page.captured_queries)

        # a full page adds no read at all beyond the one more page-check
        CeleryTaskAttempt.objects.all().delete()
        self._open_attempts(500)
        with override_settings(CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=0):
            _, full = self.capture(bound_task_attempt_samples.run)
        full_count = len(full.captured_queries)

        # spilling over the page bound costs AT MOST two more statements
        # (the next page's read and its bulk write), never one per row
        self._open_attempts(1)
        with override_settings(CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=0):
            _, spill = self.capture(bound_task_attempt_samples.run)
        spill_count = len(spill.captured_queries)

        self.assertLessEqual(full_count - first, 1)
        self.assertLessEqual(spill_count - full_count, 2,
                             msg='one extra row may not cost one extra '
                                 'statement - the page bound is the '
                                 'statement bound')
        # every write is a bulk UPDATE, never an UPDATE of one row
        row_writes = [
            query for query in spill.captured_queries
            if query['sql'].lstrip().lower().startswith('update')
            and '"celerytaskattempt"' in query['sql'].lower()]
        for query in row_writes:
            self.assertIn('"id" in', query['sql'].lower(),
                          msg='the flag write must ride the page, not '
                              'touch one row at a time')


class AttemptRetentionAndCapTest(SqlGuardMixin, TestCase):
    """Retention delete and hard cap: constant statements as rows grow."""

    def _aged_attempts(self, count, days=30):
        rows = [seed_attempt(outcome='success') for _ in range(count)]
        CeleryTaskAttempt.objects.filter(
            pk__in=[row.pk for row in rows]).update(
            recorded_at=timezone.now() - timedelta(days=days))

    def test_the_retention_delete_is_one_statement(self):
        def seed(size):
            self._aged_attempts(size)

        with override_settings(CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS=100000,
                               CAPACITY_TELEMETRY_RETENTION_DAYS=7,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=0):
            self.assertQueryCountIndependent(
                sizes=(1, 10, 100), seed=seed,
                run=bound_task_attempt_samples.run,
                label='the retention delete')
        # retention really removed the aged rows (statement side asserted)
        self.assertEqual(CeleryTaskAttempt.objects.count(), 0)

    def test_the_hard_cap_costs_the_same_whatever_the_excess(self):
        def seed(size):
            for _ in range(size):
                seed_attempt(outcome='success')

        with override_settings(CAPACITY_TELEMETRY_ABANDON_GRACE_HOURS=100000,
                               CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=5):
            self.assertQueryCountIndependent(
                sizes=(6, 30, 60), seed=seed,
                run=bound_task_attempt_samples.run,
                label='the hard cap')
        # the cap itself: only the five youngest attempts of the last seed
        # survive - the oldest go first by recorded_at
        self.assertEqual(CeleryTaskAttempt.objects.count(), 5)

    def test_no_sweep_writes_per_attempt(self):
        """Duplicate-SQL detection over a full fire with 60 rows.

        The sanctioned repeats are the page loop itself: a few page SELECTs
        and the bulk UPDATE of each page - never one statement per row.
        """
        for _ in range(60):
            seed_attempt(outcome='', started_ago_seconds=10 * 24 * 3600)
        with override_settings(CAPACITY_TELEMETRY_RETENTION_DAYS=0,
                               CAPACITY_TELEMETRY_MAX_ATTEMPTS=10):
            self.assertNoNPlusOne(
                bound_task_attempt_samples.run,
                sanctioned={'select': 6, 'update': 3},
                label='the full bound fire')
