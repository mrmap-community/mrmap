"""The beat schedule of the file system import of metadata files.

The import watches the exchange directory every five minutes through a
``PeriodicTask`` row which ``registry.apps`` creates on ``post_migrate``, like
the housekeeping sweeps. The row is what makes the import run at all - the
same contract the sweeps are tested for; #1273 adds why the hook asks its
crontab by the whole shape and not by the minutes alone.
"""

from django.test import TestCase
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from registry.apps import create_file_system_import_task

#: the name the import of new metadata files has in the schedule of beat
IMPORT_TASK_NAME = "check for new metadata to import"

#: the minutes the import runs on, every five minutes over the hour
IMPORT_MINUTES = "0,5,10,15,20,25,30,35,40,45,50,55"


class FileSystemImportScheduleTest(TestCase):
    """The schedule beat needs, which the application creates while migrating."""

    @staticmethod
    def scheduled():
        create_file_system_import_task(sender=None)
        return PeriodicTask.objects.filter(name=IMPORT_TASK_NAME)

    def test_the_import_is_scheduled_every_five_minutes(self):
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(
            tasks.get().task,
            "registry.tasks.harvest.check_for_files_to_import")
        self.assertEqual(tasks.get().crontab.minute, IMPORT_MINUTES)
        self.assertEqual(tasks.get().crontab.hour, "*")
        self.assertTrue(tasks.get().enabled)

    def test_migrating_again_keeps_one_schedule(self):
        """A deployment migrating repeatedly does not import twice a grid."""
        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)

    def test_a_staggered_row_on_the_same_minutes_does_not_break_the_hook(self):
        """A deployment which scheduled another task over the very same
        minute string keeps its migrate: the hook asks its schedule by the
        whole shape and finds its own hourly row, while the bare minutes
        lookup answered both rows and django_celery_beat raised
        MultipleObjectsReturned, which took the whole migrate down (#1273).
        """
        CrontabSchedule.objects.create(minute=IMPORT_MINUTES, hour="3")

        tasks = self.scheduled()

        self.assertEqual(tasks.count(), 1)
        self.assertEqual(tasks.get().crontab.minute, IMPORT_MINUTES)
        self.assertEqual(tasks.get().crontab.hour, "*")
