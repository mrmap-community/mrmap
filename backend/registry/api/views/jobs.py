from registry.api.serializers.jobs import TaskResultSerializer
from rest_framework_json_api.views import ReadOnlyModelViewSet
from django_celery_results.models import TaskResult


class TaskResultReadOnlyViewSet(ReadOnlyModelViewSet):
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer
