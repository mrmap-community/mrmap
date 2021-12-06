from accounts.models.users import User
from accounts.serializers.auth import LoginSerializer, LogoutSerializer
from accounts.serializers.users import UserSerializer
from django.contrib.auth import login, logout
from rest_framework import generics, status
from rest_framework.response import Response


class LoginView(generics.GenericAPIView):
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

    serializer_class = LogoutSerializer

    class Meta:
        resource_name = 'Logout'

    def post(self, request, *args, **kwargs):
        logout(request=request)
        return Response(status=status.HTTP_200_OK)
