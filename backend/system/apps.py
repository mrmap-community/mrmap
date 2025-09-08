
import sys

from django.apps import AppConfig
from django.core.management import call_command
from django.db import connection
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def create_default_system_tasks(sender, **kwargs):
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0,15,30,45",
    )

    PeriodicTask.objects.get_or_create(
        name="refresh materialized views",
        task="system.tasks.refresh_materialized_views",
        defaults={"crontab": schedule, }
    )


def sync_pg_views_if_missing():
    import logging

    from django.apps import apps
    from django_pgviews.view import MaterializedView
    logger = logging.getLogger(__name__)

    # ------------------------
    # Materialized Views Check
    # ------------------------
    SCHEMA = "public"

    # Collect all materialized views defined via django-pgviews
    matviews = []
    for model in apps.get_models():
        if issubclass(model, MaterializedView) and not getattr(model._meta, 'abstract', False):
            matviews.append(model._meta.db_table)

    if not matviews:
        logger.info(
            "No non-abstract materialized views defined with django-pgviews.")
        return

    def matview_exists(mv_name: str) -> bool:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_matviews
                    WHERE schemaname = %s
                      AND matviewname = %s
                );
                """,
                [SCHEMA, mv_name],
            )
            return cursor.fetchone()[0]

    try:
        missing = [mv for mv in matviews if not matview_exists(mv)]

        if missing:
            logger.warning(
                "Materialized views missing: %s. Running sync_pgviews --force...",
                ", ".join(missing),
            )
            call_command("sync_pgviews", "--force")
            logger.info("sync_pgviews executed successfully.")
        else:
            logger.info("All materialized views exist.")
    except Exception as e:
        logger.error("Error while checking/creating materialized views: %s", e)


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'
    label = 'system'
    verbose_name = _('System')

    def ready(self):
        # Connect signal handlers
        post_migrate.connect(create_default_system_tasks, sender=self)

        if any(cmd in sys.argv for cmd in ["migrate", "makemigrations", "collectstatic", "createsuperuser"]):
            return
        sync_pg_views_if_missing()
