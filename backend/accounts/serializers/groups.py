from accounts.models.groups import Organization
from django.contrib.auth.models import Group
from extras.serializers import (StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer
from rest_framework_json_api.relations import ResourceRelatedField
from django.utils.translation import gettext_lazy as _
from accounts.models.users import User


class GroupSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:group-detail',
    )
    users = ResourceRelatedField(
        source='user_set',
        label=_("users"),
        help_text=_("users who are members of this group"),
        many=True,
        # related_link_view_name='accounts:group-users-list',
        # related_link_url_kwarg='parent_lookup_group',
        queryset=User.objects
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
