
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework_json_api.views import ModelViewSet
from system.serializers import (CrontabScheduleSerializer,
                                PeriodicTaskSerializer)


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
