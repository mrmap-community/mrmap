from rest_framework.serializers import ModelSerializer

from registry.models import MapContext


class MapContextSerializer(ModelSerializer):

    class Meta:
        model = MapContext
        fields = ['title', 'abstract']
        extra_kwargs = {}


class MapContextOWSSerializer(ModelSerializer):
    class Meta:
        model = MapContext
        fields = ['id', 'title', 'abstract']
        extra_kwargs = {}
