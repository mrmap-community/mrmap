from auth.models.groups import Organization
from django.contrib.auth.models import Group
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer


class GroupSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='auth:group-detail',
    )

    class Meta:
        model = Group
        fields = "__all__"


class OrganizationSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='auth:organization-detail',
    )

    class Meta:
        model = Organization
        fields = "__all__"
