from rest_framework.serializers import ModelSerializer

from registry.models import OperationUrl


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'
