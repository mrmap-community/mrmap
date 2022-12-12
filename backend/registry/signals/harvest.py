import json

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from registry.models.service import CatalogueService


@receiver(pre_save, sender=CatalogueService)
def add_periodic_harvesting_task(sender, instance, created, **kwargs):
    if created:
        schedule, _created = CrontabSchedule.objects.get_or_create(
            minute="0",
            hour="0",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )
        PeriodicTask.objects.get_or_create(
            crontab=schedule,
            name=f"Start harvesting of csw: {instance}",
            task="registry.tasks.create_harvesting_job",
            args=json.dumps([str(instance.pk)])
        )
