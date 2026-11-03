
from django.apps import AppConfig
from django.core.management import call_command
from django.db import connection
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

    # at five past the hour, out of the way of the five minute metadata import
    schedule, _ = CrontabSchedule.objects.get_or_create(minute="5")

    PeriodicTask.objects.get_or_create(
        name=SLOW_REQUEST_DUMP_CLEANUP_TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "system.tasks.delete_old_slow_request_dumps",
        }
    )


def sync_pg_views_if_missing(sender, **kwargs):
    import logging

    from django.apps import apps
    from django_pgviews.view import MaterializedView, View
    logger = logging.getLogger(__name__)

    # ------------------------
    # Views Check
    # ------------------------
    SCHEMA = "public"

    # Collect all views defined via django-pgviews: a materialized view is
    # answered by pg_matviews and a plain view by pg_views - both are created
    # by the same sync command, which the settings of this deployment keep
    # away from the migrations of the package (see MATERIALIZED_VIEWS_DISABLE
    # _SYNC_ON_MIGRATE), so this hook answers the creation of all of them
    views = []
    for model in apps.get_models():
        if issubclass(model, View) and not getattr(model._meta, 'abstract', False):
            views.append((model._meta.db_table,
                          "pg_matviews" if issubclass(model, MaterializedView)
                          else "pg_views"))

    if not views:
        logger.info(
            "No non-abstract views defined with django-pgviews.")
        return

    def view_exists(view_name: str, catalog: str) -> bool:
        column = "matviewname" if catalog == "pg_matviews" else "viewname"
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT EXISTS (
                    SELECT 1
                    FROM {catalog}
                    WHERE schemaname = %s
                      AND {column} = %s
                );
                """,
                [SCHEMA, view_name],
            )
            return cursor.fetchone()[0]

    try:
        missing = [name for name, catalog in views
                   if not view_exists(name, catalog)]

        if missing:
            logger.warning(
                "Views missing: %s. Running sync_pgviews --force...",
                ", ".join(missing),
            )
            call_command("sync_pgviews", "--force")
            logger.info("sync_pgviews executed successfully.")
        else:
            logger.info("All views exist.")
    except Exception as e:
        logger.error("Error while checking/creating views: %s", e)


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'
    label = 'system'
    verbose_name = _('System')

    def ready(self):
        # Connect signal handlers
        post_migrate.connect(sync_pg_views_if_missing, sender=self)
        post_migrate.connect(
            create_slow_request_dump_cleanup_task,
            sender=self
        )
