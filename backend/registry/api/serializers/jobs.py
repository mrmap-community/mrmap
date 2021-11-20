from registry.models.jobs import RegisterOgcServiceJob
from rest_framework_json_api.serializers import ModelSerializer


class RegisterOgcServiceSerializer(ModelSerializer):

    class Meta:
        model = RegisterOgcServiceJob
        fields = "__all__"
