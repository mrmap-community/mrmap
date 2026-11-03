"""The migration which removes the scheduled refresh of the statistics.

A deployment which scheduled the refresh of the statistics materialized views
carries that schedule in its database: a ``PeriodicTask`` naming the task of
``system.tasks``, plus the crontab entry it alone used. Neither is part of the
migration state, so the application losing the task leaves both behind and the
migration has to answer for them. Which rows it leaves is what this asks: a
schedule which another periodic task still uses belongs to that task and
survives.
"""

from django.core.management import call_command
from django.test import TransactionTestCase

from django_celery_beat.models import CrontabSchedule, PeriodicTask

APP_LABEL = "system"

#: the name the periodic task of the refresh had in every deployment
REFRESH_TASK_NAME = "refresh materialized views"


class RemoveRefreshTaskMigrationTest(TransactionTestCase):
    """Going over the migration which removes the periodic task of the refresh.

    Needs a transaction test case: the migration is only worth testing by
    rolling it back and applying it again against the rows a deployment had.
    """

    @staticmethod
    def migrate(target=None):
        call_command("migrate", APP_LABEL, *([target] if target else []),
                     verbosity=0, interactive=False)

    @staticmethod
    def refresh_tasks():
        return list(PeriodicTask.objects.filter(name=REFRESH_TASK_NAME))

    def test_the_task_and_its_schedule_are_gone(self):
        """The task goes, and with it only the schedule no other task uses."""
        unused_crontab, _ = CrontabSchedule.objects.get_or_create(
            minute="0", hour="1", day_of_week="*", day_of_month="*",
            month_of_year="*")
        used_crontab, _ = CrontabSchedule.objects.get_or_create(
            minute="30", hour="3", day_of_week="*", day_of_month="*",
            month_of_year="*")
        PeriodicTask.objects.update_or_create(
            name=REFRESH_TASK_NAME,
            defaults={"task": "system.tasks.refresh_materialized_views",
                      "crontab": unused_crontab, "args": "[]"})
        other_task = PeriodicTask.objects.create(
            name="a task of another feature",
            task="registry.tasks.harvesting.harvest_record",
            crontab=used_crontab, args="[]")

        # the migration ran when the test database was created, so the way back
        # is the only way to have it answer the rows of a deployment again
        self.migrate("zero")
        self.assertEqual(len(self.refresh_tasks()), 1)

        self.migrate()

        self.assertEqual(self.refresh_tasks(), [])
        self.assertNotIn(unused_crontab, CrontabSchedule.objects.all())
        self.assertIn(used_crontab, CrontabSchedule.objects.all())
        self.assertIn(other_task, PeriodicTask.objects.all())

    def test_nothing_refreshes_the_statistics_anymore(self):
        """The task the periodic task named is gone from the module it lived in.

        The module answers again, because the sweep of the slow request dumps of
        #888 is filed in it, so what has to stay away is the task itself: a
        deployment which still carries a stale row of the schedule must not find a
        body to run over it.
        """
        import system.tasks

        self.assertFalse(hasattr(system.tasks, 'refresh_materialized_views'))
