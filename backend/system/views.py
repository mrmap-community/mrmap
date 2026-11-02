import datetime
import platform

from django import __version__ as DJANGO_VERSION
from django.conf import settings
from django.db import ProgrammingError, connection
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from MrMap import VERSION
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
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


class FrontendErrorView(APIView):
    """ Accepts browser side error reports from the frontend

        The frontend ships a small beacon script which POSTs uncaught
        exceptions, unhandled promise rejections, resource load failures and
        failing same origin API calls to this endpoint. Reports are logged
        through the root logger (RFC 5424 syslog) so they end up in the
        central log stack; the verbose parts (stack traces) live in the
        per record JSON dump, as with every other structured log record.

        Deliberately unauthenticated: errors of anonymous visitors matter
        too and a beacon must never depend on session or token state. The
        payload is untrusted input: every field is truncated and nothing is
        ever rendered back.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    # a beacon sends plain JSON, not a JSON:API document
    parser_classes = [JSONParser]

    MAX_FIELD_SIZES = {
        "source": 40,
        "message": 1000,
        "stack": 4000,
        "url": 500,
        "page": 500,
        "status": 8,
        "user_agent": 300,
    }

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}

        def field(name):
            value = data.get(name)
            if value is None:
                return None
            if not isinstance(value, str):
                value = str(value)
            return value[:self.MAX_FIELD_SIZES[name]]

        message = field("message") or "unspecified frontend error"
        frontend_data = {
            key: value
            for key, value in (
                ("source", field("source") or "error"),
                ("msg", message),
                ("stack", field("stack")),
                ("url", field("url")),
                ("page", field("page")),
                ("status", field("status")),
                ("user_agent", field("user_agent")),
            )
            if value is not None
        }
        settings.ROOT_LOGGER.warning(
            msg=f"Frontend Error: {message[:200]}",
            extra={
                "disable_python_meta": True,
                "structured_data": {
                    "metaSDID@Frontend": frontend_data
                },
            },
        )
        return Response(status=204)
