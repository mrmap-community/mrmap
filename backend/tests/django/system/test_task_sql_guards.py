"""Task-side SQL guards for the system housekeeping tasks (#1395).

Audit page: ``docs/source/development/celery-task-orm-audit.rst`` ("Family:
system housekeeping"). ``bound_task_attempt_samples`` (#1330) sweeps the
attempt table three times; the checklist asks: "constant statements per page
of 500". The abandon loop is page-bound by design - growth per PAGE is fine,
growth per ROW is the regression. The ``recorded_at`` index the audit names
as a candidate landed with #1394 (``attempt_recorded_idx``); the retention
window and the hard-cap order are guarded as plans, below.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone
from system.models import CeleryTaskAttempt
from system.tasks import bound_task_attempt_samples
from tests.django.sql_guard import SqlGuardMixin


@contextmanager
def off_seqscan():
    """EXPLAIN under ``enable_seqscan = off`` for one assertion block.

    The same pattern ``tests_task_sql_harvesting`` documents: ``SET LOCAL``
    lives with the test's own atomic block, and the question asked is
    whether the named index CAN answer this read shape - not the planner's
    mood on a small fixture.
    """
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL enable_seqscan = off')
    yield


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


class AttemptRecordedAtPlanTest(SqlGuardMixin, TestCase):
    """The two ``recorded_at`` sweeps read through the index of #1394.

    The retention window of the sweep ends in a DELETE and the hard cap
    orders the whole table, so what these asserts EXPLAIN is the rendered
    SELECT of the same filter and the same order - the shapes the sweeps
    pay - with the named index of the migration required, the way #1395
    asserts plans whenever an index candidate lands.
    """

    ATTEMPT_TABLE = CeleryTaskAttempt._meta.db_table

    @staticmethod
    def _explainable(qs):
        """The queryset's SELECT as literal SQL the planner can be asked.

        ``str(query)`` splices parameters into the text unquoted - integers
        survive that, timestamps do not (the syntax error PostgreSQL answers
        at the rendered ``datetime``). Rendering the parameters through
        quotes keeps the EXPLAINED statement the shape the sweep pays.
        """
        sql, params = qs.query.get_compiler('default').as_sql()
        for param in params:
            literal = (f"'{param}'"
                       if isinstance(param, (str, datetime)) else str(param))
            sql = sql.replace('%s', literal, 1)
        return sql

    def _retention_shape(self):
        cutoff = timezone.now() - timedelta(days=7)
        return self._explainable(CeleryTaskAttempt.objects.filter(
            recorded_at__lt=cutoff))

    def _cap_order_shape(self):
        return self._explainable(CeleryTaskAttempt.objects.order_by(
            'recorded_at'))

    def test_the_recorded_at_reads_are_index_backed(self):
        for _ in range(10):
            seed_attempt(outcome='success')
        with off_seqscan():
            self.assertPlanUsesIndex(
                self._retention_shape(), self.ATTEMPT_TABLE,
                index='attempt_recorded_idx',
                label='the retention window')
            self.assertPlanUsesIndex(
                self._cap_order_shape(), self.ATTEMPT_TABLE,
                index='attempt_recorded_idx',
                label='the hard-cap order of the oldest rows')
