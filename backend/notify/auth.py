from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack as DefaultAuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from knox.auth import TokenAuthentication
from notify.ws_ticket import consume_ticket
from rest_framework.exceptions import AuthenticationFailed


class TokenAuthMiddleware:
    """
    Token authorization middleware for Django Channels 2

    Two credentials are answered here, and they are deliberately not equal
    (#1472):

    * ``?ticket=`` - a random, single-use, 10-second value the client minted at
      ``POST /api/notify/websocket-ticket`` with its token (``notify/ws_ticket.py``,
      ``notify/views.py``). It is what a non-browser client which only holds a
      knox token uses: it may be logged by the proxy and it still authenticates
      at most one handshake.
    * ``?token=`` - a live knox token in the URL, which the proxy access logs
      keep verbatim for the whole lifetime of that token (#10 h of
      ``REST_KNOX["TOKEN_TTL"]``). Deprecated by #835: the browser does not use
      it any more, because ``channels.auth.AuthMiddlewareStack`` underneath this
      middleware resolves the same-origin ``sessionid`` cookie (pinned by
      ``tests/django/notify/test_consumers.py``). Since #1472 a production
      deployment refuses it - ``MRMAP_PRODUCTION`` - and only a development one
      still accepts it, so that a local machine client can open a socket without
      the ticket round trip.

    A handshake with neither is anonymous and refused by
    ``NonAnonymousJsonWebsocketConsumer`` below.
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, *args, **kwargs):
        user = scope.get("user")
        if (user and user.is_anonymous) or not user:
            # no successfull authentication before. try to authenticate by ticket
            query_string = scope["query_string"]
            if isinstance(query_string, bytes):
                query_string = query_string.decode()
            query_params = parse_qs(query_string)
            ticket = query_params.get("ticket", [None])[0]
            user = await database_sync_to_async(consume_ticket)(ticket)
            if user is not None:
                scope["user"] = user
            elif not settings.MRMAP_PRODUCTION:
                # the deprecated query token, kept for development only (#1472)
                tokens = query_params.get('token', '')
                knox_auth = TokenAuthentication()
                for token in tokens:
                    if isinstance(token, str):
                        token = token.encode()
                    try:
                        user, _ = await database_sync_to_async(knox_auth.authenticate_credentials)(token)
                        scope['user'] = user
                        break
                    except AuthenticationFailed:
                        pass
        return await self.inner(dict(scope,), *args, **kwargs)


# Handy shortcut for applying all three layers at once
def token_auth_middleware_stack(inner):
    return TokenAuthMiddleware(DefaultAuthMiddlewareStack(inner))


class NonAnonymousJsonWebsocketConsumer(JsonWebsocketConsumer):
    """
    Only allows non anonymous users to connect
    """

    user = None

    def connect(self):
        if self.scope['user'].is_anonymous:
            self.close(code=3000)
        else:
            super().connect()
            self.user = get_user_model().objects.get(
                username=self.scope['user'].username)

    def send_msg(self, event):
        """
        Default call back function to send messages to the client from the event['msg'] dict attribute.
        """
        self.send_json(content=event['json'])
