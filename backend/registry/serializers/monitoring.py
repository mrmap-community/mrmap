from registry.models.monitoring import (LayerGetFeatureInfoResult,
                                        LayerGetMapResult,
                                        WMSGetCapabilitiesResult)
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class WMSGetCapabilitiesResultCreateSerializer(ModelSerializer):

    class Meta:
        model = WMSGetCapabilitiesResult
        fields = ("service",)


class WMSGetCapabilitiesResultSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:wmsgetcapabilitiesresult-detail',
    )

    class Meta:
        model = WMSGetCapabilitiesResult
        fields = "__all__"


class LayerGetMapResultCreateSerializer(ModelSerializer):

    class Meta:
        model = LayerGetMapResult
        fields = ("layer", )


class LayerGetMapResultSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:layergetmapresult-detail',
    )

    class Meta:
        model = LayerGetMapResult
        fields = "__all__"


class LayerGetFeatureInfoResultCreateSerializer(ModelSerializer):

    class Meta:
        model = LayerGetFeatureInfoResult
        fields = ("layer",)


class LayerGetFeatureInfoResultSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='registry:layergetfeatureinforesult-detail',
    )

    class Meta:
        model = LayerGetFeatureInfoResult
        fields = "__all__"
