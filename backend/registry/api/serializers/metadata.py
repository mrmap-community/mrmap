from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer
from registry.models.metadata import Keyword, Style


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
        models = Style
        fields = '__all__'
