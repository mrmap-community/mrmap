from registry.models.monitoring import (LayerGetFeatureInfoResult,
                                        LayerGetMapResult,
                                        WMSGetCapabilitiesResult)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 SerializerMethodField)


class WMSGetCapabilitiesResultCreateSerializer(ModelSerializer):

    class Meta:
        model = WMSGetCapabilitiesResult
        fields = (
            "service"
        )


class WMSGetCapabilitiesResultSerializer(ModelSerializer):

    class Meta:
        model = WMSGetCapabilitiesResult
        fields = "__all__"


class LayerGetMapResultCreateSerializer(ModelSerializer):

    class Meta:
        model = LayerGetMapResult
        fields = (
            "layer"
        )


class LayerGetMapResultSerializer(ModelSerializer):

    class Meta:
        model = LayerGetMapResult
        fields = "__all__"


class LayerGetFeatureInfoResultCreateSerializer(ModelSerializer):

    class Meta:
        model = LayerGetFeatureInfoResult
        fields = (
            "layer"
        )


class LayerGetFeatureInfoResultSerializer(ModelSerializer):

    class Meta:
        model = LayerGetFeatureInfoResult
        fields = "__all__"
