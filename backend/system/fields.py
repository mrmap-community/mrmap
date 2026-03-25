import datetime
import re
import zoneinfo

from django.conf import settings
from django_celery_beat.models import CrontabSchedule
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

CRONTAB_TIME_REGEX = (
    r"(?P<minute>[\d\*/,\-]+)\s+"
    r"(?P<hour>[\d\*/,\-]+)\s+"
    r"(?P<day_of_month>[\d\*/,\-]+)\s+"
    r"(?P<month_of_year>[\d\*/,\-]+)\s+"
    r"(?P<day_of_week>[\d\*/,\-]+)"
    r"(?:\s+(?P<timezone>\S+))?"
)


def parse_timezone(tz_string: str) -> datetime.tzinfo:
    """Konvertiert einen Timezone-String in ein ZoneInfo-Objekt."""
    try:
        return zoneinfo.ZoneInfo(tz_string)
    except zoneinfo.ZoneInfoNotFoundError:
        pass

    match = re.fullmatch(r"UTC([+-]\d{1,2})", tz_string)
    if not match:
        raise ValueError(f"Unsupported timezone format: {tz_string}")
    utc_offset = int(match.group(1))
    # Etc/GMT* zones use reversed signs (POSIX style)
    gmt_offset = -utc_offset
    gmt_name = f"Etc/GMT{gmt_offset:+d}"
    return zoneinfo.ZoneInfo(gmt_name)


@extend_schema_field(str)
class CrontabStringField(serializers.Field):
    def __init__(self, **kwargs):
        help_text = kwargs.pop(
            "help_text",
            "Crontab-Zeitstring mit optionaler Zeitzone (z. B. '0 12 * * 1-5 UTC+2')",
        )
        super().__init__(help_text=help_text, **kwargs)

    def to_representation(self, value: CrontabSchedule) -> str:
        base = f"{value.minute} {value.hour} {value.day_of_month} {value.month_of_year} {value.day_of_week}"
        if value.timezone:
            base += f" {value.timezone.key}"
        return base

    def to_internal_value(self, data: str) -> CrontabSchedule:
        data = data.strip()
        match = re.fullmatch(CRONTAB_TIME_REGEX, data)
        if not match:
            raise serializers.ValidationError(f"Invalid crontab string format: {data}")
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
                timezone = parse_timezone(tz_string)
            except Exception as e:
                raise serializers.ValidationError(str(e))
        else:
            timezone = zoneinfo.ZoneInfo(settings.TIME_ZONE)

        obj, _ = CrontabSchedule.objects.get_or_create(
            minute=minute,
            hour=hour,
            day_of_month=day_of_month,
            month_of_year=month_of_year,
            day_of_week=day_of_week,
            timezone=timezone,
        )
        return obj
