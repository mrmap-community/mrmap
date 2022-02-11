from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission
from django.utils.translation import gettext_lazy as _
from extras.serializers import StringRepresentationSerializer
from rest_framework import exceptions
from rest_framework.fields import CharField
from rest_framework.relations import HyperlinkedIdentityField
from rest_framework_json_api.serializers import ModelSerializer, Serializer


class CsrfTokenSerializer(Serializer):
    token = CharField(
        label=_("token"),
        help_text=("token to protect against cross-site-request-forgery")
    )

    class Meta:
        resource_name = 'CsrfToken'


class PasswordField(CharField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('style', {})

        kwargs['style']['input_type'] = 'password'
        kwargs['write_only'] = True

        super().__init__(*args, **kwargs)


class LoginSerializer(Serializer):
    username = CharField(
        label=_("username"),
    )
    password = PasswordField(
        label=_("password"),
    )

    class Meta:
        resource_name = 'Login'

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self.user = authenticate(
            username=attrs['username'], password=attrs['password'])
        if not self.user:
            raise exceptions.AuthenticationFailed
        return attrs


class LogoutSerializer(Serializer):

    class Meta:
        resource_name = 'Logout'


class PermissionSerializer(
        StringRepresentationSerializer,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name='accounts:user-detail',
    )

    class Meta:
        model = Permission
        fields = "__all__"
        meta_fields = ("string_representation",)
