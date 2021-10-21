from rest_framework.serializers import ModelSerializer

from registry.models import DatasetMetadata


class DatasetMetadataSerializer(ModelSerializer):

    class Meta:
        model = DatasetMetadata
        fields = '__all__'
