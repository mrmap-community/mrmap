from django.contrib.auth.models import Group
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation,
                                      WebFeatureServiceOperation,
                                      WebMapServiceOperation)
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


class AllowedWebMapServiceOperationSerializer(ModelSerializer):
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
        secured_layers = attrs.get('secured_layers', None)
        if secured_layers:
            secured_layers_pk = set(
                [secured_layer.pk for secured_layer in secured_layers])
            # TODO: let the database evaluate this...
            for secured_layer in secured_layers:
                descendant_pks = set(
                    secured_layer.get_descendants().values_list('id', flat=True))
                if not descendant_pks.issubset(secured_layers_pk):
                    raise ValidationError(
                        'Incomplete subtree selection is not allowed.')

        return data


class AllowedWebFeatureServiceOperationSerializer(ModelSerializer):
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
