from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule
from rest_framework import serializers


class CrontabStringField(serializers.CharField):
    """
    Accepts a crontab string like "*/5 * * * *" (minute hour day month weekday)
    Creates or re-uses a CrontabSchedule via get_or_create and returns the model instance.
    """

    def to_internal_value(self, data):
        s = super().to_internal_value(data)

        # allow passing an existing id or dict with id
        if isinstance(s, dict):
            pk = s.get('id') or s.get('pk')
            if pk:
                try:
                    return CrontabSchedule.objects.get(pk=int(pk))
                except (CrontabSchedule.DoesNotExist, ValueError):
                    pass

        if isinstance(s, int) or (isinstance(s, str) and s.isdigit()):
            try:
                return CrontabSchedule.objects.get(pk=int(s))
            except CrontabSchedule.DoesNotExist:
                pass

        parts = s.strip().split()
        if len(parts) != 5:
            raise serializers.ValidationError(
                "Invalid crontab format — expected 5 fields: minute hour day month weekday"
            )
        minute, hour, day_of_month, month_of_year, day_of_week = parts

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
        )
        return schedule

    def to_representation(self, obj):
        # Represent schedule as a cron string in responses
        if isinstance(obj, CrontabSchedule):
            return f"{obj.minute} {obj.hour} {obj.day_of_month} {obj.month_of_year} {obj.day_of_week}"
        return super().to_representation(obj)
