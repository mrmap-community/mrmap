from accounts.models.users import User
from accounts.serializers.auth import PermissionSerializer
from accounts.serializers.users import UserSerializer
from django.contrib.auth.models import Permission
from knox.views import LoginView as KnoxLoginView
from knox.views import LogoutView as KnoxLogoutView
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework_json_api.views import ReadOnlyModelViewSet


class LoginView(KnoxLoginView):
    """Customized LoginView without json:api renderer"""
    renderer_classes = [JSONRenderer]


class LogoutView(KnoxLogoutView):
    """Customized LoutView without json:api renderer"""
    renderer_classes = [JSONRenderer]


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
    filterset_fields = {
        'name': ['exact', 'icontains'],
        'codename': ['exact', 'icontains'],
    }
