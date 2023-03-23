from accounts.models.users import User
from accounts.serializers.auth import (LoginSerializer, LogoutSerializer,
                                       PermissionSerializer)
from accounts.serializers.users import UserSerializer
from django.contrib.auth import login, logout
from django.contrib.auth.models import Permission
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.views import ReadOnlyModelViewSet


class LoginRequestView(generics.GenericAPIView):
    """ Login a user by the given credentials

        post: Login a user by the given credentials

    """
    http_method_names = ['post', 'head', 'options']
    resource_name = "LoginRequest"
    serializer_class = LoginSerializer
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login(request=request, user=serializer.user)
        return Response(serializer.data)


class LogoutRequestView(generics.GenericAPIView):
    """ Logout a user by the given session id

        delete: Logout a user by the given session id

    """
    serializer_class = LogoutSerializer

    class Meta:
        resource_name = 'LogoutRequest'

    def delete(self, request, *args, **kwargs):
        logout(request=request)
        return Response(status=status.HTTP_200_OK)


class WhoAmIView(generics.GenericAPIView):
    http_method_names = ['get', 'head', 'options']
    resource_name = "CurrentUser"
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, *args, **kwargs):
        return self.retreive(*args, **kwargs)

    def retreive(self, request, *args, **kwargs):
        user = request.user
        if user.is_anonymous:
            user = User.get_anonymous()
        serializer = self.get_serializer(user)
        return Response(serializer.data)


class PermissionViewSet(ReadOnlyModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filter_fields = {
        'name': ['exact', 'icontains'],
        'codename': ['exact', 'icontains'],
    }
