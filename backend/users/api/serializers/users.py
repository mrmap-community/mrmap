from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from extras.fields import ExtendedHyperlinkedRelatedField
from rest_framework import exceptions
from rest_framework.fields import CharField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer, Serializer

from users.api.serializers.groups import GroupSerializer
from users.models.users import MrMapUser


class PasswordField(CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('style', {})

        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True

        super().__init__(*args, **kwargs)


class MrMapUserSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='users:user-detail',
    )

    groups = ExtendedHyperlinkedRelatedField(
        queryset=Group.objects,
        many=True,
        related_link_view_name='users:user-groups-list',
        related_link_url_kwarg='parent_lookup_user',
        self_link_view_name='users:user-relationships',
        required=False,
        meta_attrs={'group_count': 'count'})

    related_serializers = {
        'groups': GroupSerializer,
    }

    class Meta:
        resource_name = 'User'
        model = MrMapUser
        exclude = ("password", )


class LoginSerializer(Serializer):
    username = CharField()
    password = PasswordField()

    class Meta:
        resource_name = 'Login'
        # model = MrMapUser
        # fields = ('username', 'password',)

    def validate(self, attrs):
        self.user = authenticate(
            username=attrs['username'], password=attrs['password'])

        if not self.user:
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        return {}


class LogoutSerializer(Serializer):

    class Meta:
        resource_name = 'Logout'
