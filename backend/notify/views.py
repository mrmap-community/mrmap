from django_celery_results.models import TaskResult
from extras.viewsets import NestedModelViewSet
from notify.filters import BackgroundProcessFilterSet
from notify.models import BackgroundProcess, BackgroundProcessLog
from notify.permissions import CanChangeRelatedResource
from notify.serializers import (BackgroundProcessLogSerializer,
                                BackgroundProcessSerializer,
                                TaskResultSerializer)
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet


class TaskResultViewSetMixin:
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        'task_id': ['exact', 'icontains', 'contains', 'in'],
        'periodic_task_name': ['exact', 'icontains', 'contains'],
        'task_name': ['exact', 'icontains', 'contains'],
        'task_args': ['exact', 'icontains', 'contains'],
        'task_kwargs': ['exact', 'icontains', 'contains'],
        'status': ['exact', 'icontains', 'contains'],
        'worker': ['exact', 'icontains', 'contains'],
        'content_type': ['exact', 'icontains', 'contains'],
        'content_encoding': ['exact', 'icontains', 'contains'],
        'result': ['exact', 'icontains', 'contains'],
        'traceback': ['exact', 'icontains', 'contains'],
        'meta': ['exact', 'icontains', 'contains'],
        "date_created": ["exact", "gt", "lt", "range"],
        'date_done': ["exact", "gt", "lt", "range"],
    }
    search_fields = [
        "id",
        'task_id',
        'periodic_task_name',
        'task_name',
        'task_args',
        'task_kwargs',
        'status',
        'worker',
        'content_type',
        'content_encoding',
        'result',
        'date_created',
        'date_done',
        'traceback',
        'meta',
    ]
    ordering_fields = [
        "id",
        'task_id',
        'periodic_task_name',
        'task_name',
        'task_args',
        'task_kwargs',
        'status',
        'worker',
        'content_type',
        'content_encoding',
        'result',
        'date_created',
        'date_done',
        'traceback',
        'meta',
    ]


"""
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == states.SUCCESS and 'build_ogc_service' or 'fetch_remote_metadata_xml' in instance.task_name:
            # followed the jsonapi recommendation for async processing
            # https://jsonapi.org/recommendations/#asynchronous-processing
            result = json.loads(instance.result)
            return Response(
                status=status.HTTP_303_SEE_OTHER,
                headers={
                    "Location": str(
                        self.request.build_absolute_uri(
                            result["data"]["links"]["self"])
                    )
                },
            )
        else:
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
"""


class TaskResultReadOnlyViewSet(TaskResultViewSetMixin, ReadOnlyModelViewSet):
    pass


class NestedTaskResultReadOnlyViewSet(TaskResultViewSetMixin, NestedModelViewSet):
    pass


class BackgroundProcessViewSetMixin(

):
    queryset = BackgroundProcess.objects.process_info()
    serializer_class = BackgroundProcessSerializer
    filterset_class = BackgroundProcessFilterSet
    permission_classes = [CanChangeRelatedResource]
    ordering_fields = [
        "id",
        "date_created",
    ]

    def get_queryset(self):
        """Answer only the processes which belong to resources the user may see.

        A process names its resource with a generic relation, so what the user is
        permitted to see has to be looked up per type of the related resource.
        Anonymous clients read this endpoint like every other read only endpoint
        of the api and a superuser sees every process, so neither of them needs
        the lookup.
        """
        queryset = super().get_queryset()
        user = getattr(self.request, 'user', None)
        if user is None or not user.is_authenticated or user.is_superuser:
            return queryset
        return BackgroundProcess.objects.visible_for_user(
            user, queryset=queryset)


class BackgroundProcessViewSet(
    BackgroundProcessViewSetMixin,
    ModelViewSet
):
    pass


class BackgroundProcessLogViewSetMixin(

):
    queryset = BackgroundProcessLog.objects.all()
    serializer_class = BackgroundProcessLogSerializer
    filterset_fields = {
        'id': ['exact', 'icontains', 'contains', 'in'],
        "log_type": ["exact", "icontains", "contains"],
        "description": ["exact", "icontains", "contains"],
        "date": ["exact", "icontains", "contains"],
    }
    ordering_fields = [
        "id",
    ]


class BackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    ReadOnlyModelViewSet
):
    pass


class NestedBackgroundProcessLogViewSet(
    BackgroundProcessLogViewSetMixin,
    NestedModelViewSet
):
    pass
