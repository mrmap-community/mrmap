from collections import OrderedDict
from rest_framework.serializers import ModelSerializer


class NonNullModelSerializer(ModelSerializer):
    def to_representation(self, instance):
        result = super(NonNullModelSerializer, self).to_representation(instance)
        return OrderedDict([(key, result[key]) for key in result if result[key] is not None])
