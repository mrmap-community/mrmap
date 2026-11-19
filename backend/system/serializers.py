
from django.utils.translation import gettext_lazy as _
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin,
                                TimeUntilNextRunMixin)
from rest_framework.fields import (BooleanField, CharField, DateTimeField,
                                   IntegerField, JSONField,
                                   SerializerMethodField)
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
    TimeUntilNextRunMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='system:periodictask-detail',
    )
    scheduling = CrontabStringField(source='crontab')
    time_until_next_run = SerializerMethodField(label=_("time until next run"))

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
            'time_until_next_run',
            'last_run_at'
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
    system_time = DateTimeField()

    class Meta:
        resource_name = 'SystemInfo'


class SystemStatusSerializer(Serializer):
    id = CharField()
    observed_at = DateTimeField()
    stale = BooleanField()
    stale_after = IntegerField()
    components = JSONField()

    class Meta:
        resource_name = 'SystemStatus'


class CapacitySnapshotSerializer(Serializer):
    """The admin-only deployment capacity snapshot of #1326.

    The sections mirror the answer of ``system.capacity_snapshot``: the
    moment the snapshot speaks about (``snapshot_at``/``expires_at`` and
    the honest ``stale``), the horizon it counted, the unique worker pools
    and per-queue answers (depth is a count, seconds come only from
    measurements, ``rho`` only when comparable) and the stated reasons of
    everything that stayed unknown.
    """

    id = CharField()
    snapshot_at = DateTimeField()
    expires_at = DateTimeField()
    built_at = DateTimeField()
    stale = BooleanField()
    available = BooleanField()
    reason = CharField(required=False, allow_null=True)
    confidence = CharField()
    # the fail-closed answer of ``capacity_snapshot._verdict`` carries the
    # statement and its reason and *no* section at all - an answer of
    # "unknown" must not leak a partially observed deployment either. Every
    # section is therefore optional here: a required field would turn that
    # honest answer into a serialization error.
    horizon = JSONField(required=False)
    schedules = JSONField(required=False)
    gaps = JSONField()
    pools = JSONField(required=False)
    fleet = JSONField(required=False)
    queues = JSONField(required=False)
    messages = JSONField(required=False)
    rho = JSONField(required=False)
    other_workload = JSONField(required=False)
    demand = JSONField(required=False)
    costs = JSONField(required=False)
    build = JSONField(required=False)
    limitations = JSONField(required=False)

    class Meta:
        resource_name = 'CapacitySnapshot'
