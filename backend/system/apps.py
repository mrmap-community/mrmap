from django.apps import AppConfig
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


class SystemConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'system'
    label = 'system'
    verbose_name = _('System')

    def ready(self):
        # Implicitly connect signal handlers decorated with @receiver.
        post_migrate.connect(create_default_system_tasks, sender=self)
