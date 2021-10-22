from rest_framework.serializers import ModelSerializer
from registry.models.service import Layer
from registry.models import OperationUrl


class OperationsUrlSerializer(ModelSerializer):

    class Meta:
        model = OperationUrl
        fields = '__all__'


class LayerSerializer(ModelSerializer):

    class Meta:
        model = Layer
        fields = [
            'id',
            'scale_min',
            'scale_max',
            'inherit_scale_min',
            'inherit_scale_max']
