from accounts.models.users import User
from accounts.serializers.auth import PermissionSerializer
from accounts.serializers.users import UserSerializer
from django.contrib.auth.models import AnonymousUser, Permission
from knox.views import LoginView as KnoxLoginView
from knox.views import LogoutView as KnoxLogoutView
from rest_framework import exceptions, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_json_api.renderers import JSONRenderer as JSONApiRenderer
from rest_framework_json_api.views import ReadOnlyModelViewSet


class LoginView(KnoxLoginView):
    """Customized LoginView without json:api renderer.

    Rate limited (#1450, audit SEC-8): this is the endpoint that turns a
    presented credential into a token row, and it is reachable without one.
    Both scopes live in the deployment's ``default`` cache (redis), so every
    worker shares one counter:

    * ``login`` (set below): requests that presented a valid credential,
      counted per user — bounds token-row creation by an accepted caller;
    * ``login_anon``: refused attempts — no credential, or wrong credentials
      — counted per client IP, the window credential guessing runs into.
    """
    renderer_classes = [JSONRenderer]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def initial(self, request, *args, **kwargs):
        try:
            super().initial(request, *args, **kwargs)
        except exceptions.APIException as exc:
            if isinstance(exc, exceptions.Throttled):
                raise
            # DRF consults the throttles only after authentication and
            # permission have had their say, so a refused credential — the
            # attempt brute force actually consists of — would never reach
            # the counter. Record it in the anonymous window (keyed per IP,
            # never per guessed username) before answering, so guessing runs
            # into the rate instead of being unlimited. A valid credential
            # still lands in the per-user window and is not locked out by a
            # full one — a guessed-at client cannot use this to deny the
            # honest caller behind the same address.
            self.throttle_scope = "login_anon"
            request.user = AnonymousUser()
            self.check_throttles(request)
            raise


class LogoutView(KnoxLogoutView):
    """Customized LoutView without json:api renderer"""
    renderer_classes = [JSONRenderer]


class WhoAmIView(generics.GenericAPIView):
    renderer_classes = [JSONApiRenderer]
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
