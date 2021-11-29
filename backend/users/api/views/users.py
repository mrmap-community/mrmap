from rest_framework.exceptions import AuthenticationFailed
from rest_framework_json_api.schemas.openapi import AutoSchema
from users.api.serializers.users import LoginSerializer, LogoutSerializer, MrMapUserSerializer
from users.models.users import MrMapUser
from rest_framework_extensions.mixins import NestedViewSetMixin
from rest_framework_json_api.views import ModelViewSet
from rest_framework import generics, status
from rest_framework.response import Response
from django.contrib.auth import login, logout
from rest_framework.permissions import DjangoObjectPermissions


class MrMapUserViewSet(NestedViewSetMixin, ModelViewSet):
    schema = AutoSchema(
        tags=['Users'],
    )
    queryset = MrMapUser.objects.all()
    serializer_class = MrMapUserSerializer
    permission_classes = [DjangoObjectPermissions]
    prefetch_for_includes = {
        '__all__': [],
        'groups': ['groups']
    }


class LoginView(generics.GenericAPIView):
    queryset = MrMapUser.objects.all()
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        try:
            serializer.is_valid(raise_exception=True)
            login(request=request, user=serializer.user)

        except AuthenticationFailed:
            # TODO find out why error code 403 is swallowed -> backend returns 200 in any case
            return Response(status=status.HTTP_403_FORBIDDEN)
        finally:
            return Response(MrMapUserSerializer(serializer.user, context={'request': request}).data, status=status.HTTP_200_OK)


class LogoutView(generics.GenericAPIView):

    serializer_class = LogoutSerializer

    class Meta:
        resource_name = 'Logout'

    def post(self, request, *args, **kwargs):
        logout(request=request)
        return Response(status=status.HTTP_200_OK)
