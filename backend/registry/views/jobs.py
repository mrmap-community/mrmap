import json

from celery import states
from django_celery_results.models import TaskResult
from registry.serializers.jobs import TaskResultSerializer
from rest_framework import status
from rest_framework.response import Response
from rest_framework_json_api.views import ReadOnlyModelViewSet


class TaskResultReadOnlyViewSet(ReadOnlyModelViewSet):
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer
    filter_fields = {
        "task_name": ["exact", "icontains", "contains"],
        "status": ["exact"],
        "date_created": ["exact", "gt", "lt", "range"],
    }

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == states.SUCCESS:
            # followed the jsonapi recommendation for async processing

            # https://jsonapi.org/recommendations/#asynchronous-processing
            # FIXME: rethink about the data schema of the result field... It could be possible that there is no api_endpoint which represents the concrete result as json:api resource
            result = json.loads(instance.result)
            return Response(
                status=status.HTTP_303_SEE_OTHER,
                headers={
                    "Location": str(
                        self.request.build_absolute_uri(
                            result.get("api_enpoint"))
                    )
                },
            )
        else:
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
