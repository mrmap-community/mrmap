from django.contrib.auth.models import Group
from users.models.groups import Organization
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework.relations import HyperlinkedIdentityField


class GroupSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='users:group-detail',
    )

    class Meta:
        model = Group
        fields = "__all__"


class OrganizationSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='users:organization-detail',
    )

    class Meta:
        model = Organization
        fields = "__all__"
