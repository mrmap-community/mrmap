"""The scheduled refresh of the statistics views is removed (#857).

The per-day statistics answer their aggregation themselves now, so the task
which rebuilt the nine views is gone with them: ``system.tasks`` does not
announce it anymore and ``system.apps`` does not create the ``PeriodicTask``
which handed it to celery beat on every migrate.

Neither of that reaches a deployment which already runs: its beat scheduler
reads the task from the database, where the hook of an earlier version wrote the
row. This migration removes it there, together with the schedule only that task
used -- a schedule another task shares stays, because the task which shares it
still points at it.

The way back does not write the row again: a deployment which rolls back over
this migration checks out the code which had the ``post_migrate`` hook, and that
hook creates the task while it migrates back, with the schedule of that revision.
"""

from django.db import migrations

# the task is looked for by both names it is known by: the path is what the
# scheduler of the deployment runs, the name is what its operator sees
REFRESH_TASK_NAME = "refresh materialized views"
REFRESH_TASK_PATH = "system.tasks.refresh_materialized_views"


def remove_statistics_refresh_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat.PeriodicTask")
    CrontabSchedule = apps.get_model("django_celery_beat.CrontabSchedule")

    tasks = PeriodicTask.objects.filter(name=REFRESH_TASK_NAME) | PeriodicTask.objects.filter(
        task=REFRESH_TASK_PATH)
    schedules = {task.crontab_id for task in tasks if task.crontab_id}
    tasks.delete()

    CrontabSchedule.objects.filter(
        pk__in=schedules, periodictask__isnull=True).delete()


class Migration(migrations.Migration):
    """Removes the periodic task which rebuilt the statistics views."""

    dependencies = [
        # the tables of the scheduler belong to the package which owns them, and
        # this migration reads them -- the app itself has no models of its own
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.RunPython(
            remove_statistics_refresh_task, migrations.RunPython.noop),
    ]
