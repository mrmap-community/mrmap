from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer
from registry.models.metadata import DatasetMetadata, Keyword, Style


class KeywordSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:keyword-detail',
    )

    class Meta:
        model = Keyword
        fields = '__all__'


class StyleSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:style-detail',
    )

    class Meta:
        model = Style
        fields = '__all__'


class DatasetMetadataSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:datasetmetadata-detail'
    )

    class Meta:
        model = DatasetMetadata
        fields = '__all__'
