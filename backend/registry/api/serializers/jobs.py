from registry.models.jobs import BuildWebMapServiceTask, RegisterWebMapService
from rest_framework_json_api.serializers import ModelSerializer


class RegisterWebMapServiceSerializer(ModelSerializer):

    class Meta:
        model = RegisterWebMapService
        fields = "__all__"


class BuildWebMapServiceTaskSerializer(ModelSerializer):

    class Meta:
        model = BuildWebMapServiceTask
        fields = "__all__"
