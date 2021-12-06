from django.contrib.auth import authenticate
from rest_framework import exceptions
from rest_framework.fields import CharField
from rest_framework_json_api.serializers import Serializer


class PasswordField(CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('style', {})

        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True

        super().__init__(*args, **kwargs)


class LoginSerializer(Serializer):
    username = CharField()
    password = PasswordField()

    class Meta:
        resource_name = 'Login'

    def validate(self, attrs):
        self.user = authenticate(
            username=attrs['username'], password=attrs['password'])
        if not self.user:
            raise exceptions.AuthenticationFailed
        return {}


class LogoutSerializer(Serializer):

    class Meta:
        resource_name = 'Logout'
