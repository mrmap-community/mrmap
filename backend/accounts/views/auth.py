from accounts.models.users import User
from accounts.serializers.auth import PermissionSerializer
from accounts.serializers.users import UserSerializer
from accounts.throttling import (LoginAttemptThrottle,
                                 ThrottleLoginAttemptsMixin)
from django.conf import settings
from django.contrib.auth import login, logout
from django.contrib.auth.models import Permission
from django.middleware.csrf import get_token, rotate_token
from knox.auth import TokenAuthentication as KnoxTokenAuthentication
from knox.views import LoginView as KnoxLoginView
from knox.views import LogoutView as KnoxLogoutView
from rest_framework import generics, status
from rest_framework.authentication import (BasicAuthentication,
                                           SessionAuthentication)
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_json_api.renderers import JSONRenderer as JSONApiRenderer
from rest_framework_json_api.views import ReadOnlyModelViewSet


class LoginView(
    ThrottleLoginAttemptsMixin,
    KnoxLoginView
):
    """Login endpoint of the *machine* clients (#835).

    knox answers HTTP Basic credentials with a token the caller keeps itself.
    That is what scripts and CLI clients need - a credential which travels in a
    header and never touches a cookie jar - and it is deliberately *not* what
    the browser uses any more: the browser gets ``SessionView`` below, because
    a credential JavaScript can read is a credential an injected script can
    copy. The documented policy of these tokens (lifetime, revocation, what is
    still open) is in ``docs/source/administration/authentication.md``.

    ``authentication_classes`` names the stack explicitly - it is the list the
    global settings held until #1450 dropped Basic from them. Basic lives on
    this view and on ``SessionView`` alone, the two endpoints
    ``docs/source/administration/authentication.md`` documents it for; the
    order is kept exactly as it was, because it is what decides that a wrong
    credential answers 403 (the coerced shape of DRF's refusal) rather than a
    401 challenge. Every attempt to open a token here pays into the
    per-address login budget of #1450.
    """
    renderer_classes = [JSONRenderer]
    authentication_classes = [SessionAuthentication, BasicAuthentication,
                              KnoxTokenAuthentication]
    throttle_classes = [LoginAttemptThrottle]


class LogoutView(KnoxLogoutView):
    """Revocation endpoint of the *machine* clients (#835).

    Deletes exactly the token row the ``Authorization`` header authenticates, so
    one device signing out keeps the tokens of the others (#832). A browser
    session is not revoked here - it is closed by ``SessionView``.
    """
    renderer_classes = [JSONRenderer]


class SessionView(
    ThrottleLoginAttemptsMixin,
    APIView
):
    """The browser session of the SPA (accepted decision Q8=B, #835).

    One endpoint, three verbs, no credential in any answer:

    * ``POST`` turns the HTTP Basic credentials of the request into a Django
      session: ``login()`` stores the caller in the session and Django's
      ``SessionMiddleware`` answers the ``sessionid`` cookie, which is
      ``HttpOnly``, ``SameSite=Lax`` and ``Secure`` under TLS (the policy is in
      ``MrMap/settings.py``). The answer says ``authenticated`` and nothing
      else - a token an injected script could copy out of the answer, or a
      credential the WebSocket URL would have to carry, does not exist here.
    * ``GET`` asks whether this browser already has a live session, which is how
      the SPA decides between the app and the login page on load. It is
      deliberately answerable anonymously, like ``who-am-i`` of the read-only
      baseline (#833): knowing *whether* a cookie authenticates grants nothing.
    * ``DELETE`` closes the session server-side (#832 for the browser path):
      ``logout()`` flushes the session row and clears the cookie, so a
      credential copied out of this browser before the logout answers nothing
      afterwards. It is idempotent - an already absent session is answered the
      same as a closed one, because the client's local state is cleared either
      way.

    CSRF: the state-changing verbs (``POST``, ``DELETE``) of a caller the session
    authenticates are checked by DRF's ``SessionAuthentication``, first in this
    view's ``authentication_classes``, which demands the ``X-CSRFToken`` header
    beside the cookie. That is why every verb of this view makes sure the CSRF
    cookie itself is present: a plain JSON ``GET`` would not set it (Django sets
    it where a template or ``get_token`` asks for it), and the SPA can only send
    what it was given. A ``POST`` which authenticates by Basic - the normal
    first login of a browser without session - is not a session-authenticated
    request, so no token is asked of it; a re-login while a session is alive
    does need one, which is the login-CSRF guard Django's own login view gives.

    The credentials this view speaks are declared on the view, not inherited:
    Basic lives here (and on ``LoginView``) alone, #1450 dropped it from the
    global stack - this POST and the machine login are what
    ``docs/source/administration/authentication.md`` documents it for, and
    every password-carrying POST here pays into the per-address login budget
    which refuses the flood with 429 before a credential is read (#1450). The
    verbs without a password - the probe, the logout - cost nothing.
    """
    renderer_classes = [JSONRenderer]
    # the verbs' own policies are in the methods: this view answers anonymous
    # callers on GET and DELETE by design, so no global permission class
    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication, BasicAuthentication,
                              KnoxTokenAuthentication]
    throttle_classes = [LoginAttemptThrottle]
    http_method_names = ['get', 'head', 'options', 'post', 'delete']

    def get(self, request):
        # asking for the token is what puts the cookie on the response, so the
        # SPA's next state-changing request has a header to send
        get_token(request)
        return Response({"authenticated": request.user.is_authenticated})

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            # no credential, or one which does not resolve to an account:
            # DRF answers this the same way it answers a refused permission
            # (403, code ``not_authenticated``), which is the contract of
            # docs/source/administration/authentication.md
            raise NotAuthenticated()
        # DRF resolved the caller through Basic, a knox token or the session
        # itself; only the first two paths leave ``backend`` on the user
        # object, and ``login()`` needs to know which backend to store. The
        # first configured backend is what Django's own login view falls back
        # to, and guardian's backend is checked per permission anyway.
        login(request, user,
              backend=getattr(user, "backend",
                              settings.AUTHENTICATION_BACKENDS[0]))
        # a new session gets a new CSRF secret, as Django's login view does, so
        # a token an attacker could have learned before the login is worthless
        rotate_token(request)
        return Response({"authenticated": True})

    def delete(self, request):
        # ``SessionAuthentication`` has already demanded the CSRF header for
        # this request when a session authenticated it; an anonymous caller has
        # nothing to flush and gets the same answer as one which had a session
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class WhoAmIView(generics.GenericAPIView):
    renderer_classes = [JSONApiRenderer]
    http_method_names = ['get', 'head', 'options']
    resource_name = "CurrentUser"
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get(self, *args, **kwargs):
        return self.retrieve(*args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
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
