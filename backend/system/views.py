import datetime
import platform

from django import __version__ as DJANGO_VERSION
from django.db import ProgrammingError, connection
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from MrMap import VERSION
from rest_framework.permissions import IsAdminUser
from rest_framework_json_api.views import ModelViewSet, generics
from system.serializers import (CrontabScheduleSerializer,
                                PeriodicTaskSerializer, SystemSerializer,
                                SystemStatusSerializer)
from system.status import get_status_snapshot


class CrontabScheduleViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `CrontabSchedule`

        create:
            Endpoint to register new `CrontabSchedule` object
        list:
            Retrieves all registered `CrontabSchedule` objects
        retrieve:
            Retrieve one specific `CrontabSchedule` by the given id
        partial_update:
            Endpoint to update some fields of a `CrontabSchedule`
        destroy:
            Endpoint to remove a registered `CrontabSchedule` from the system
    """
    queryset = CrontabSchedule.objects.all()
    serializer_class = CrontabScheduleSerializer

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'minute': ['exact', 'icontains', 'contains'],
        'hour': ['exact', 'icontains', 'contains'],
        'day_of_month': ['exact', 'icontains', 'contains'],
        'month_of_year': ['exact', 'icontains', 'contains'],
        'day_of_week': ['exact', 'icontains', 'contains'],
        # 'timezone': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id",)
    ordering_fields = [
        "id",
        "minute",
        "hour",
        "day_of_month",
        "month_of_year",
        "day_of_week",
        # "timezone"
    ]


class PeriodicTaskViewSet(
    ModelViewSet,
):
    """ Endpoints for resource `PeriodicTask`

        create:
            Endpoint to register new `PeriodicTask` object
        list:
            Retrieves all registered `PeriodicTask` objects
        retrieve:
            Retrieve one specific `PeriodicTask` by the given id
        partial_update:
            Endpoint to update some fields of a `PeriodicTask`
        destroy:
            Endpoint to remove a registered `PeriodicTask` from the system
    """
    queryset = PeriodicTask.objects.all()
    serializer_class = PeriodicTaskSerializer

    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'name': ['exact', 'icontains', 'contains'],
        'task': ['exact', 'icontains', 'contains'],
        # 'scheduling': ['exact', 'icontains', 'contains'],
        'args': ['exact', 'icontains', 'contains'],
        'kwargs': ['exact', 'icontains', 'contains'],
        'queue': ['exact', 'icontains', 'contains'],
        'enabled': ['exact'],
        # 'timezone': ['exact', 'icontains', 'contains'],
    }
    search_fields = ("id",)
    ordering_fields = [
        "id",
        "name",
        "task",
        "args",
        "kwargs",
        "queue",
        "enabled",
    ]


class SystemView(generics.RetrieveAPIView):

    serializer_class = SystemSerializer

    def check_docker_container(self):
        pass

    def get_object(self):

        # System stats
        psql_version = db_name = db_size = None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT version(), current_database(), "
                    "pg_size_pretty(pg_database_size(current_database()))")
                psql_version, db_name, db_size = cursor.fetchone()
                psql_version = psql_version.split('(')[0].strip()
        except (ProgrammingError, IndexError):
            pass
        return {
            'id': VERSION,
            'mrmap_release': VERSION,
            'django_version': DJANGO_VERSION,
            'python_version': platform.python_version(),
            'postgresql_version': psql_version,
            'database_name': db_name,
            'database_size': db_size,
            'system_time': datetime.datetime.now(),
        }


class SystemStatusView(generics.RetrieveAPIView):
    serializer_class = SystemStatusSerializer
    permission_classes = [IsAdminUser]

    def get_object(self):
        return get_status_snapshot()
