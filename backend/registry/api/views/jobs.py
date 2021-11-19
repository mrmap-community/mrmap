from registry.api.serializers.jobs import BuildWebMapServiceTaskSerializer, RegisterWebMapServiceSerializer
from registry.models.jobs import BuildWebMapServiceTask, RegisterWebMapService
from rest_framework_json_api.views import ModelViewSet


class RegisterWebMapServiceViewSet(ModelViewSet):
    queryset = RegisterWebMapService.objects.all()
    serializer_class = RegisterWebMapServiceSerializer


class BuildWebMapServiceTaskViewSet(ModelViewSet):
    queryset = BuildWebMapServiceTask.objects.all()
    serializer_class = BuildWebMapServiceTaskSerializer
