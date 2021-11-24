
from rest_framework_json_api.schemas.openapi import AutoSchema
from registry.api.serializers.metadata import KeywordSerializer, StyleSerializer
from registry.models.metadata import Keyword, Style
from rest_framework_json_api.views import ModelViewSet


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
