
from registry.models.metadata import DatasetMetadata, Keyword, Style
from registry.serializers.metadata import (DatasetMetadataSerializer,
                                           KeywordSerializer, StyleSerializer)
from rest_framework_json_api.schemas.openapi import AutoSchema
from rest_framework_json_api.views import ModelViewSet


class KeywordViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    filter_fields = {
        'keyword': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('keyword',)

    def get_queryset(self):
        queryset = super(KeywordViewSet, self).get_queryset()
        if 'parent_lookup_layer' in self.kwargs:
            queryset = queryset.filter(
                layer_metadata=self.kwargs['parent_lookup_layer'])
        if 'parent_lookup_featuretype' in self.kwargs:
            queryset = queryset.filter(
                featuretype_metadata=self.kwargs['parent_lookup_featuretype'])
        return queryset


class StyleViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = Style.objects.all()
    serializer_class = StyleSerializer
    filter_fields = {
        'name': ['exact', 'icontains', 'contains'],
        'title': ['exact', 'icontains', 'contains'],
    }
    search_fields = ('name', 'title',)

    def get_queryset(self):
        queryset = super(StyleViewSet, self).get_queryset()
        if 'parent_lookup_layer' in self.kwargs:
            queryset = queryset.filter(
                layer_id=self.kwargs['parent_lookup_layer'])
        return queryset


class DatasetMetadataViewSet(ModelViewSet):
    schema = AutoSchema(
        tags=['Metadata'],
    )
    queryset = DatasetMetadata.objects.all()
    serializer_class = DatasetMetadataSerializer
