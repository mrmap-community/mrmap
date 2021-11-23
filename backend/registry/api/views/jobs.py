from registry.api.serializers.jobs import TaskResultSerializer
from rest_framework_json_api.views import ReadOnlyModelViewSet
from django_celery_results.models import TaskResult
from celery import states
from rest_framework.response import Response
from rest_framework import status
import json


class TaskResultReadOnlyViewSet(ReadOnlyModelViewSet):
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()

        if instance.status == states.SUCCESS:
            result = json.loads(instance.result)
            return Response(status=status.HTTP_303_SEE_OTHER, headers={'Location': str(self.request.build_absolute_uri(result.get("api_enpoint")))})
        else:
            serializer = self.get_serializer(instance)
            return Response(serializer.data)
