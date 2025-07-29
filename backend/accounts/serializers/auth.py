from django.contrib.auth.models import Permission
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer


class PermissionSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    class Meta:
        model = Permission
        fields = "__all__"
        fields = "__all__"
