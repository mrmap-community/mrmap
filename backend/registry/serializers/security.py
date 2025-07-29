from django.contrib.auth.models import Group
from django.db.models.query import Prefetch
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceAuthentication,
                                      WebFeatureServiceOperation,
                                      WebFeatureServiceProxySetting,
                                      WebMapServiceAuthentication,
                                      WebMapServiceOperation,
                                      WebMapServiceProxySetting)
from registry.models.service import Layer
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 ValidationError)


class WebMapServiceAuthenticationSerializer(SystemInfoSerializerMixin, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:wmsauth-detail',
    )

    class Meta:
        model = WebMapServiceAuthentication
        fields = '__all__'


class WebMapServiceOperationSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wmsoperation-detail',
    )

    class Meta:
        model = WebMapServiceOperation
        fields = '__all__'


class WebFeatureServiceAuthenticationSerializer(SystemInfoSerializerMixin, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:wfsauth-detail',
    )

    class Meta:
        model = WebFeatureServiceAuthentication
        fields = '__all__'


class WebFeatureServiceOperationSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):
    url = HyperlinkedIdentityField(
        view_name='registry:wfsoperation-detail',
    )

    class Meta:
        model = WebFeatureServiceOperation
        fields = '__all__'


class AllowedWebMapServiceOperationSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:allowedwmsoperation-detail',
    )
    allowed_groups = ResourceRelatedField(
        queryset=Group.objects,
        many=True,
        required=False)
    allowed_area = GeometryField(required=False, allow_null=True)

    class Meta:
        model = AllowedWebMapServiceOperation
        fields = '__all__'

    def validate(self, attrs):
        data = super().validate(attrs)

        if self.instance:
            secured_service = attrs.get(
                'secured_service', self.instance.secured_service)
        else:
            secured_service = attrs.get('secured_service')

        secured_layers = attrs.get('secured_layers')
        if secured_layers:
            secured_layer_pks = [
                secured_layer.pk for secured_layer in secured_layers]
            prefetch_children = Prefetch(
                "chilren",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "mptt_parent_id",
                    "mptt_tree_id",
                    "mptt_lft"),
                to_attr="descendant_pks"
            )
            _secured_layers = Layer.objects.filter(
                pk__in=secured_layer_pks).prefetch_related(prefetch_children)

            secured_layers_pk = set(
                [secured_layer.pk for secured_layer in _secured_layers])
            for secured_layer in _secured_layers:
                if secured_layer.service_id != secured_service.pk:
                    raise ValidationError(
                        {"secured_layers": "Missmatching layer for selected service."})
                descendant_pks = set(
                    [descendant.pk for descendant in secured_layer.descendant_pks])
                if not descendant_pks.issubset(secured_layers_pk):
                    raise ValidationError(
                        {"secured_layers": "Incomplete subtree selection is not allowed."})

        return data


class AllowedWebFeatureServiceOperationSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:allowedwfsoperation-detail',
    )
    allowed_groups = ResourceRelatedField(
        queryset=Group.objects,
        many=True,
        required=False)
    allowed_area = GeometryField(required=False, allow_null=True)

    class Meta:
        model = AllowedWebFeatureServiceOperation
        fields = '__all__'


class WebMapServiceProxySettingSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapserviceproxysetting-detail',
    )

    class Meta:
        model = WebMapServiceProxySetting
        fields = '__all__'


class WebFeatureServiceProxySettingSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:webmapserviceproxysetting-detail',
    )

    class Meta:
        model = WebFeatureServiceProxySetting
        fields = '__all__'
        fields = '__all__'
