from django_celery_beat.models import CrontabSchedule, PeriodicTask
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.fields import (BooleanField, CharField, DateTimeField,
                                   IntegerField)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer, Serializer)
from system.fields import CrontabStringField
from timezone_field.rest_framework import TimeZoneSerializerField


class CrontabScheduleSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
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


class PeriodicTaskSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='system:periodictask-detail',
    )
    scheduling = CrontabStringField(source='crontab')

    class Meta:
        model = PeriodicTask
        fields = (
            'url',
            'id',
            'name',
            'task',
            'scheduling',
            'args',
            'kwargs',
            'queue',
            'enabled',
        )


class SystemSerializer(
    Serializer
):
    id = CharField()
    mrmap_release = CharField()
    django_version = CharField()
    python_version = CharField()
    postgresql_version = CharField()
    database_name = CharField()
    database_size = CharField()
    celery_worker_count = IntegerField()
    redis_up = BooleanField()

    system_time = DateTimeField()

    class Meta:
        resource_name = 'SystemInfo'
        resource_name = 'SystemInfo'
        resource_name = 'SystemInfo'
