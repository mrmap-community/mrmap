
from registry.models.metadata import DatasetMetadata, Keyword, Style
from registry.serializers.metadata import (DatasetMetadataSerializer,
                                           KeywordSerializer, StyleSerializer)
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filterset_fields = {
        'keyword': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('keyword',)


class StyleViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Style.objects.all()
    serializer_class = StyleSerializer
    filterset_fields = {
        'name': ['exact', 'icontains', 'contains'],
        'title': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('name', 'title',)


class DatasetMetadataViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = DatasetMetadata.objects.all()
    serializer_class = DatasetMetadataSerializer
    filterset_fields = {
        'title': ['exact', 'icontains', 'contains'],
        'abstract': ['exact', 'icontains', 'contains'],
        'keywords__keyword': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('title', 'abstract', 'keywords__keyword')
