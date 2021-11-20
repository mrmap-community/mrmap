from django.core.exceptions import ObjectDoesNotExist
from rest_framework.fields import SerializerMethodField
from rest_framework.reverse import reverse
from registry.models.metadata import Keyword


from extras.api.serializers import ObjectAccessSerializer
from registry.models import DatasetMetadata
from rest_framework_json_api.serializers import ModelSerializer


class KeywordSerializer(ModelSerializer):

    class Meta:
        model = Keyword
        fields = '__all__'


class DatasetMetadataSerializer(ObjectAccessSerializer):
    feature_type = SerializerMethodField()
    layer = SerializerMethodField()

    class Meta:
        model = DatasetMetadata
        fields = [
            'id',
            'feature_type',
            'layer'
        ]

    def get_feature_type(self, obj):
        try:
            feature_type = obj.self_pointing_feature_types.get()
        except ObjectDoesNotExist:
            feature_type = None
        if feature_type:
            return self.context['request'].build_absolute_uri(
                reverse('api:feature_type-detail', args=[feature_type.id]))
        return None

    def get_layer(self, obj):
        try:
            layer = obj.self_pointing_layers.get()
        except ObjectDoesNotExist:
            layer = None
        if layer:
            return self.context['request'].build_absolute_uri(
                reverse('api:layer-detail', args=[layer.id]))
        return None
