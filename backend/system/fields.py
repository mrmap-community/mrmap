import re
from datetime import timedelta

import pytz
from django.conf import settings
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule
from rest_framework import fields, serializers

CRONTAB_TIME_REGEX = (
    r"^(?P<minute>[\d\*/,\-]+)\s+"
    r"(?P<hour>[\d\*/,\-]+)\s+"
    r"(?P<day_of_month>[\d\*/,\-]+)\s+"
    r"(?P<month>[\d\*/,\-]+)\s+"
    r"(?P<day_of_week>[\d\*/,\-]+)"
    r"(?:\s+(?P<timezone>UTC(?:[+-]\d{1,2}(?::\d{2})?)?))?"
    r"\Z"
)


def parse_utc_timezone(tz_string: str) -> pytz.BaseTzInfo:
    """Konvertiert UTC+X oder UTC-X:XX in eine pytz-Zeitzone."""
    if tz_string == "UTC":
        return pytz.UTC
    match = re.fullmatch(r"UTC([+-])(\d{1,2})(?::(\d{2}))?", tz_string)
    if not match:
        raise ValueError(f"Unsupported timezone format: {tz_string}")
    sign, hours, minutes = match.groups()
    offset_hours = int(hours)
    offset_minutes = int(minutes or 0)
    total_offset = offset_hours + offset_minutes / 60
    if sign == "+":
        gmt_offset = -total_offset
    else:
        gmt_offset = total_offset
    # pytz uses reversed signs: UTC+2 → Etc/GMT-2
    gmt_name = f"Etc/GMT{int(gmt_offset):+d}"
    return pytz.timezone(gmt_name)


class CrontabStringField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(
            help_text="Crontab-Zeitstring mit optionaler UTC-Zeitzone (z. B. '0 12 * * 1-5 UTC+2')",
            **kwargs
        )

    def to_representation(self, obj: CrontabSchedule):
        base = f"{obj.minute} {obj.hour} {obj.day_of_month} {obj.month_of_year} {obj.day_of_week}"
        if obj.timezone:
            base += f" {obj.timezone.key}"
        return base

    def to_internal_value(self, data):
        data = data.strip()
        match = re.fullmatch(CRONTAB_TIME_REGEX, data)
        if not match:
            raise serializers.ValidationError("Invalid crontab string format.")
        values = match.groupdict()
        minute = values["minute"]
        hour = values["hour"]
        day_of_month = values["day_of_month"]
        month_of_year = values["month_of_year"]
        day_of_week = values["day_of_week"]
        tz_string = values.get("timezone")

        # Zeitzone bestimmen
        if tz_string:
            try:
                timezone = parse_utc_timezone(tz_string)
            except Exception as e:
                raise serializers.ValidationError(str(e))
        else:
            timezone = pytz.timezone(settings.TIME_ZONE)

        obj, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
            timezone=timezone,
        )
        return obj
