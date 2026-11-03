"""The bounded life of the slow request dumps (#888).

Every record the syslog handler formats leaves a json dump below the media root and
nothing used to take them back, so a deployment which ran for a few weeks held a few
hundred thousand files in one directory. The sweep of ``system.tasks`` deletes them
by age and by count, and beat hands it over hourly through a ``PeriodicTask`` row
which the application creates on migrate.

The file work is asserted against a temporary media root: the sweep reads
``MEDIA_ROOT`` while it runs, like the formatter which writes the dumps, so an
``override_settings(MEDIA_ROOT=...)`` reaches it. The hand-over to beat is asserted
against the schedule table, because beat only knows what it finds there.
"""

import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from system.apps import (SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME,
                         create_slow_request_dump_cleanup_task)
from system.logging.formatter import SLOW_REQUEST_DUMP_SUBDIR
from system.tasks import (delete_dumps, delete_old_slow_request_dumps,
                          slow_request_dumps_dir)


def write_dump(directory, age_days=0, name=None):
    """One dump of ``directory``, written ``age_days`` days ago, as the formatter writes it."""
    path = directory / (name or f'{uuid.uuid4()}.json')
    path.write_text('{"metaSDID@request": {"duration_ms": 450}}')
    if age_days:
        modified = (timezone.now() - timedelta(days=age_days)).timestamp()
        os.utime(path, (modified, modified))
    return path


class SlowRequestDumpSweepTests(SimpleTestCase):
    """What the sweep takes back and what it leaves alone.

    Every test gets its own media root: the sweep counts what it finds, so a dump
    a earlier test left behind would answer the summary of the next one.
    """

    def setUp(self):
        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        self.media_root = Path(media_root.name)
        self.dumps = self.media_root / SLOW_REQUEST_DUMP_SUBDIR
        self.dumps.mkdir()

    def sweep(self, retention_days=14, max_files=0):
        return delete_dumps(self.dumps, retention_days, max_files)

    def test_dumps_past_the_retention_are_gone(self):
        expired = write_dump(self.dumps, age_days=15)

        summary = self.sweep(retention_days=14)

        self.assertFalse(expired.exists())
        self.assertEqual(summary['expired'], 1)
        self.assertEqual(summary['remaining'], 0)

    def test_dumps_within_the_retention_stay(self):
        recent = write_dump(self.dumps, age_days=13)

        summary = self.sweep(retention_days=14)

        self.assertTrue(recent.exists())
        self.assertEqual(summary['expired'], 0)
        self.assertEqual(summary['remaining'], 1)

    def test_the_count_takes_the_oldest_dumps_beyond_it(self):
        dumps = [write_dump(self.dumps, age_days=age) for age in range(4, -1, -1)]

        summary = self.sweep(retention_days=0, max_files=2)

        self.assertEqual([dump.exists() for dump in dumps],
                         [False, False, False, True, True])
        self.assertEqual(summary['excess'], 3)
        self.assertEqual(summary['remaining'], 2)

    def test_the_count_bounds_what_the_age_rule_left(self):
        """Both bounds belong to one sweep, so neither is paid twice."""
        expired = write_dump(self.dumps, age_days=30)
        dumps = [write_dump(self.dumps, age_days=age) for age in (3, 2, 1)]

        summary = self.sweep(retention_days=14, max_files=2)

        self.assertFalse(expired.exists())
        self.assertEqual([dump.exists() for dump in dumps], [False, True, True])
        self.assertEqual(summary['expired'], 1)
        self.assertEqual(summary['excess'], 1)
        self.assertEqual(summary['remaining'], 2)

    def test_a_bound_of_zero_keeps_the_dumps(self):
        """A deployment which wants its dumps until it reads them gets them."""
        recent = write_dump(self.dumps)
        old = write_dump(self.dumps, age_days=400)

        summary = self.sweep(retention_days=0, max_files=0)

        self.assertTrue(recent.exists())
        self.assertTrue(old.exists())
        self.assertEqual(summary['remaining'], 2)

    def test_only_the_dumps_of_that_directory_are_asked_about(self):
        """The media root holds other logs which belong to rows of the database."""
        dump = write_dump(self.dumps, age_days=400)
        # the request and response bodies of the security proxy live below the media
        # root too and go with their HttpRequestLog rows
        proxy_log = (self.media_root
                     / 'security_proxy' / 'logs' / 'requests')
        proxy_log.mkdir(parents=True)
        proxy_body = proxy_log / 'request.json'
        proxy_body.write_text('{}')
        nested = self.dumps / 'nested'
        nested.mkdir()
        in_subdirectory = write_dump(nested, age_days=400)
        not_a_dump = write_dump(self.dumps, age_days=400, name='notes.txt')

        self.sweep(retention_days=14)

        self.assertFalse(dump.exists())
        self.assertTrue(proxy_body.exists())
        self.assertTrue(in_subdirectory.exists())
        self.assertTrue(not_a_dump.exists())

    def test_a_missing_directory_is_no_failure(self):
        """A deployment which never logged a slow request has nothing to sweep."""
        with tempfile.TemporaryDirectory() as empty:
            summary = delete_dumps(
                Path(empty) / SLOW_REQUEST_DUMP_SUBDIR, 14, 0)

        self.assertEqual(summary['expired'], 0)
        self.assertEqual(summary['excess'], 0)
        self.assertEqual(summary['remaining'], 0)

    def test_the_sweep_reads_the_media_root_of_the_deployment(self):
        """The sweep follows a deployment which moves its media root."""
        with self.settings(MEDIA_ROOT=str(self.media_root)):
            self.assertEqual(slow_request_dumps_dir(), self.dumps)


class SlowRequestDumpCleanupTaskTests(SimpleTestCase):
    """The celery task reads the bounds of the deployment and sweeps with them."""

    # the sweep itself reads nothing but the file system, but the task is a
    # SingletonTask and the lock which keeps two sweeps apart is an advisory lock of
    # a database session since #852, so the run needs one connection
    databases = {"default"}

    def setUp(self):
        media_root = tempfile.TemporaryDirectory()
        self.addCleanup(media_root.cleanup)
        self.dumps = Path(media_root.name) / SLOW_REQUEST_DUMP_SUBDIR
        self.dumps.mkdir()

    def test_the_task_sweeps_with_the_configured_bounds(self):
        expired = write_dump(self.dumps, age_days=15)
        within_retention = [write_dump(self.dumps, age_days=age)
                            for age in (2, 1)]

        with self.settings(MEDIA_ROOT=str(self.dumps.parent),
                           SLOW_REQUEST_DUMP_RETENTION_DAYS=14,
                           SLOW_REQUEST_DUMP_MAX_FILES=1):
            # over apply() and not over the task itself: the singleton lock of the
            # task is what keeps two sweeps apart, it is not what is asked here
            summary = delete_old_slow_request_dumps.apply().get()

        self.assertFalse(expired.exists())
        self.assertEqual([dump.exists() for dump in within_retention],
                         [False, True])
        self.assertEqual(summary['directory'], str(self.dumps))
        self.assertEqual(summary['expired'], 1)
        self.assertEqual(summary['excess'], 1)
        self.assertEqual(summary['remaining'], 1)


class SlowRequestDumpScheduleTests(TestCase):
    """The schedule beat needs, which the application creates while migrating."""

    def setUp(self):
        self.scheduled()

    @staticmethod
    def scheduled():
        create_slow_request_dump_cleanup_task(sender=None)
        return PeriodicTask.objects.filter(
            name=SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME)

    def test_the_sweep_is_scheduled_hourly(self):
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().task,
                         'system.tasks.delete_old_slow_request_dumps')
        self.assertEqual(tasks.get().crontab.minute, '5')
        self.assertEqual(tasks.get().crontab.hour, '*')
        self.assertTrue(tasks.get().enabled)

    def test_migrating_again_keeps_one_schedule(self):
        """A deployment migrating repeatedly does not sweep twice an hour."""
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)

    def test_a_re_scheduled_sweep_keeps_its_schedule(self):
        """A deployment which re-scheduled the sweep is not overruled.

        The row is keyed by its name: a schedule chosen over the api belongs to the
        deployment, while a create which compared the crontab would answer a
        conflicting insert for the unique name of the row.
        """
        every_minute, _ = CrontabSchedule.objects.get_or_create(minute='*')
        self.scheduled().update(crontab=every_minute)

        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().crontab_id, every_minute.pk)
        self.assertEqual(tasks.get().task,
                         'system.tasks.delete_old_slow_request_dumps')
