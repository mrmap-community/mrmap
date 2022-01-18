from django.contrib.auth.models import Group
from django.db.models.query import Prefetch
from extras.serializers import ObjectPermissionCheckerSerializer
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceOperation,
                                      WebMapServiceOperation)
from registry.models.service import Layer
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer,
                                                 ValidationError)


class WebMapServiceOperationSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:wmsoperation-detail',
    )

    class Meta:
        model = WebMapServiceOperation
        fields = '__all__'


class WebFeatureServiceOperationSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:wfsoperation-detail',
    )

    class Meta:
        model = WebFeatureServiceOperation
        fields = '__all__'


class AllowedWebMapServiceOperationSerializer(ObjectPermissionCheckerSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:allowedwmsoperation-detail',
    )
    allowed_groups = ResourceRelatedField(
        queryset=Group.objects,
        many=True,
        required=False)
    allowed_area = GeometryField(required=False)

    class Meta:
        model = AllowedWebMapServiceOperation
        fields = '__all__'

    def validate(self, attrs):
        data = super().validate(attrs)
        secured_service = attrs['secured_service']
        secured_layers = attrs['secured_layers']
        if secured_layers:
            secured_layer_pks = [
                secured_layer.pk for secured_layer in secured_layers]
            prefetch_children = Prefetch(
                "children",
                queryset=Layer.objects.only(
                    "id",
                    "service_id",
                    "parent_id",
                    "tree_id",
                    "lft"),
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


class AllowedWebFeatureServiceOperationSerializer(ObjectPermissionCheckerSerializer, ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:allowedwfsoperation-detail',
    )
    allowed_groups = ResourceRelatedField(
        queryset=Group.objects,
        many=True,
        required=False)
    allowed_area = GeometryField(required=False)

    class Meta:
        model = AllowedWebFeatureServiceOperation
        fields = '__all__'
