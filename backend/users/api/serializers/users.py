from rest_framework.fields import CharField
from users.api.serializers.groups import GroupSerializer
from users.models.users import MrMapUser
from rest_framework_json_api.serializers import ModelSerializer, Serializer
from rest_framework.relations import HyperlinkedIdentityField
from django.contrib.auth import authenticate
from rest_framework import exceptions


class PasswordField(CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('style', {})

        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True

        super().__init__(*args, **kwargs)


class MrMapUserSerializer(ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='users:mrmapuser-detail',
    )

    included_serializers = {
        'groups': GroupSerializer,
    }

    class Meta:
        resource_name = 'MrMapUser'
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
        self.user = authenticate(username=attrs['username'], password=attrs['password'])

        if not self.user:
            raise exceptions.AuthenticationFailed(
                self.error_messages['no_active_account'],
                'no_active_account',
            )

        return {}
  

class LogoutSerializer(Serializer):

    class Meta:
        resource_name = 'Logout'
