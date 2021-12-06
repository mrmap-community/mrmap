from accounts.models.users import User
from accounts.serializers.groups import GroupSerializer
from django.contrib.auth.models import Group
from extras.fields import ExtendedHyperlinkedRelatedField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import ModelSerializer


class UserSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    groups = ExtendedHyperlinkedRelatedField(
        many=True,
        related_link_view_name='accounts:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',
        self_link_view_name='accounts:user-relationships',
        read_only=True,
        meta_attrs={'group_count': 'count'})

    class Meta:
        resource_name = 'User'
        model = User
        exclude = ("password", )


class UserCreateSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    groups = ResourceRelatedField(
        queryset=Group.objects.all(),
        many=True,
        related_link_view_name='accounts:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',
        self_link_view_name='accounts:user-relationships')

    related_serializers = {
        "groups": GroupSerializer
    }

    class Meta:
        resource_name = 'User'
        model = User
        fields = ("username", "password", "url", "groups")

    def save(self, **kwargs):
        user = super().save(**kwargs)
        # set the correct password
        user.set_password(self.validated_data['password'])
        return user
