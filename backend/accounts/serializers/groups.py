from accounts.models.groups import Organization
from django.contrib.auth.models import Group
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer


class GroupSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:group-detail',
    )

    class Meta:
        model = Group
        fields = "__all__"


class OrganizationSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:organization-detail',
    )

    class Meta:
        model = Organization
        fields = "__all__"
        fields = "__all__"
