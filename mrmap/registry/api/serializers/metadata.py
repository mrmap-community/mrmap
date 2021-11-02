from extras.api.serializers import ObjectAccessSerializer
from registry.models import DatasetMetadata


class DatasetMetadataSerializer(ObjectAccessSerializer):

    class Meta:
        model = DatasetMetadata
        fields = '__all__'
