from django_celery_beat.models import CrontabSchedule
from extras.serializers import StringRepresentationSerializer
from rest_framework_json_api.serializers import ModelSerializer
from timezone_field.rest_framework import TimeZoneSerializerField


class CrontabScheduleSerializer(
    StringRepresentationSerializer,
    ModelSerializer
):

    timezone = TimeZoneSerializerField()

    class Meta:
        model = CrontabSchedule
        fields = (
            'minute',
            'hour',
            'day_of_month',
            'month_of_year',
            'day_of_week',
            'string_representation',
            'timezone',
        )

    def get_string_representation(self, obj) -> str:
        return obj.human_readable
