from registry.api.serializers.jobs import RegisterOgcServiceSerializer
from registry.models.jobs import RegisterOgcServiceJob
from rest_framework_json_api.views import ModelViewSet


class RegisterOgcServiceViewSet(ModelViewSet):
    queryset = RegisterOgcServiceJob.objects.all()
    serializer_class = RegisterOgcServiceSerializer
