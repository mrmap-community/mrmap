import json

from celery import states
from django_celery_results.models import TaskResult
from extras.openapi import CustomAutoSchema
from rest_framework import status
from rest_framework.response import Response
from rest_framework_json_api.views import ReadOnlyModelViewSet

from notify.models import BackgroundProcess
from notify.serializers import (BackgroundProcessSerializer,
                                TaskResultSerializer)


class TaskResultReadOnlyViewSet(ReadOnlyModelViewSet):
    schema = CustomAutoSchema(
        tags=['TaskResult'],
    )
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer
    filterset_fields = {
        "task_name": ["exact", "icontains", "contains"],
        "status": ["exact"],
        "date_created": ["exact", "gt", "lt", "range"],
    }

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


class BackgroundProcessViewSetMixin():
    schema = CustomAutoSchema(
        tags=["BackgroundProcess"],
    )
    queryset = BackgroundProcess.objects.process_info()
    serializer_class = BackgroundProcessSerializer
    filterset_fields = {
        "process_type": ["exact", "icontains", "contains"],
        "description": ["exact", "icontains", "contains"],
        "phase": ["exact", "icontains", "contains"],
    }


class BackgroundProcessViewSet(
    BackgroundProcessViewSetMixin,
    ReadOnlyModelViewSet
):
    pass
