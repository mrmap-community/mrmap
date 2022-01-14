from django.contrib.auth.models import Group
from registry.models.security import AllowedWebMapServiceOperation
from rest_framework_gis.fields import GeometryField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (HyperlinkedIdentityField,
                                                 ModelSerializer)


class AllowedWebMapServiceOperationSerializer(ModelSerializer):
    url = HyperlinkedIdentityField(
        view_name='registry:allowedoperation-detail',
    )
    allowed_groups = ResourceRelatedField(
        queryset=Group.objects,
        many=True,
        required=False)
    allowed_area = GeometryField(required=False)

    class Meta:
        model = AllowedWebMapServiceOperation
        fields = '__all__'
