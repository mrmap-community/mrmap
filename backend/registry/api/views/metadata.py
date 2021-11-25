
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet
from registry.api.serializers.metadata import DatasetMetadataSerializer, KeywordSerializer, StyleSerializer
from registry.models.metadata import DatasetMetadata, Keyword, Style


class KeywordViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer


class StyleViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Style.objects.all()
    serializer_class = StyleSerializer


class DatasetMetadataViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = DatasetMetadata.objects.all()
    serializer_class = DatasetMetadataSerializer
