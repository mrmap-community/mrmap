from accounts.models.users import User
from accounts.serializers.auth import (LoginSerializer, LogoutSerializer,
                                       PermissionSerializer)
from accounts.serializers.users import UserSerializer
from django.contrib.auth import login, logout
from django.contrib.auth.models import Permission
from extras.openapi import CustomAutoSchema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.views import ReadOnlyModelViewSet


class LoginView(generics.GenericAPIView):
    schema = CustomAutoSchema(
        tags=['Auth'],
    )
    queryset = User.objects.all()
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        login(request=request, user=serializer.user)
        user = serializer.user
        user.group_count = user.groups.count()
        return Response(UserSerializer(serializer.user, context={'request': request}).data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):
    schema = CustomAutoSchema(
        tags=['Auth'],
    )
    serializer_class = LogoutSerializer

    class Meta:
        resource_name = 'Logout'

    def post(self, request, *args, **kwargs):
        logout(request=request)
        return Response(status=status.HTTP_200_OK)


class PermissionViewSet(ReadOnlyModelViewSet):
    schema = CustomAutoSchema(
        tags=['Permission'],
    )
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]
    filter_fields = {
        'name': ['exact', 'icontains'],
        'codename': ['exact', 'icontains'],
    }
