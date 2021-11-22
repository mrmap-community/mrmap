from registry.api.serializers.jobs import RegisterOgcServiceSerializer, TaskResultSerializer
from registry.models.jobs import RegisterOgcServiceJob
from rest_framework_json_api.views import ModelViewSet, ReadOnlyModelViewSet
from django_celery_results.models import TaskResult


class RegisterOgcServiceViewSet(ModelViewSet):
    queryset = RegisterOgcServiceJob.objects.all()
    serializer_class = RegisterOgcServiceSerializer


class TaskResultReadOnlyViewSet(ReadOnlyModelViewSet):
    queryset = TaskResult.objects.all()
    serializer_class = TaskResultSerializer
