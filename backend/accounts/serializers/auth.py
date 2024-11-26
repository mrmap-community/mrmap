from django.contrib.auth.models import Permission
from extras.serializers import StringRepresentationSerializer
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer


class PermissionSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    class Meta:
        model = Permission
        fields = "__all__"
