
from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _

#: the name the sweep of the slow request dumps has in the schedule of beat; the
#: tests look the row up by it
SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME = "delete old slow request dumps"


def create_slow_request_dump_cleanup_task(sender, **kwargs):
    """Creates the periodic task which keeps the slow request dumps bounded.

    Beat reads its schedule out of the database, so a task which shall run on its
    own has to exist as a row of ``PeriodicTask``, like the import of the metadata
    files does (#888). Keyed by its name and not by its schedule: a deployment which
    re-scheduled the row over the api keeps what it chose, while a ``get_or_create``
    over the crontab would answer a conflicting insert for the unique name.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    # at five past the hour, out of the way of the five minute metadata
    # import. Asked by its whole shape and not by the minute alone: the
    # staggered per-service schedules (system/fields.py) legitimately hold
    # rows at five past with any hour, and the bare minute lookup answered
    # them all -- the migrate died on MultipleObjectsReturned (#1273)
    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="5", hour="*", day_of_week="*",
        day_of_month="*", month_of_year="*")

    PeriodicTask.objects.get_or_create(
        name=SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.delete_old_slow_request_dumps",
        }
    )


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'
    label = 'system'
    verbose_name = _('System')

    def ready(self):
        post_migrate.connect(
            create_slow_request_dump_cleanup_task,
            sender=self
        )
