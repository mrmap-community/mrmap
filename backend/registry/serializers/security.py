from django.contrib.auth.models import Group
from registry.models.security import (AllowedWebFeatureServiceOperation,
                                      AllowedWebMapServiceOperation)
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


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
