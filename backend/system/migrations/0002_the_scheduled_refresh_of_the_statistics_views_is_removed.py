"""The rows of the scheduled refresh which a deployment carries are swept (#857).

The rebuild of the history (#1850) generated the chain of this app from its
models. One node of the old chain had no model state of its own to generate
from: the first one, which removed the ``PeriodicTask`` of the statistics
refresh and the crontab entry which only that task used. Its data duty
therefore stood uncarried, and a deployment which once scheduled the refresh
would keep rows which answer to no task any more -- ``system.tasks`` does not
announce ``refresh_materialized_views`` and ``system.apps`` creates no
``PeriodicTask`` on a migrate. Nothing of the new chain initializes the
schedule; this migration is where the sweep belongs, because the rows are
data which only the chain of the app can answer for: it removes the task by
both names it is known by and, with it, only the schedule no other task uses.

The way back does not write the row again: a deployment which rolls back over
this migration checks out the code which had the ``post_migrate`` hook, and
that hook creates the task while it migrates back, with the schedule of that
revision.
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
        ("system", "0001_initial"),
        # the tables of the scheduler belong to the package which owns them,
        # and this migration reads them -- the app itself owns no model of
        # the schedule
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.RunPython(
            remove_statistics_refresh_task, migrations.RunPython.noop),
    ]
