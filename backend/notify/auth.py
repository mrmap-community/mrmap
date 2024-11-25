from urllib.parse import parse_qs

from channels.auth import AuthMiddlewareStack as DefaultAuthMiddlewareStack
from channels.db import database_sync_to_async
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model
from knox.auth import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class TokenAuthMiddleware:
    """
    Token authorization middleware for Django Channels 2
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, *args, **kwargs):
        user = scope.get("user")
        if (user and user.is_anonymous) or not user:
            # no successfull authentication before. try to authenticate by token
            query_string = scope["query_string"]
            if isinstance(query_string, bytes):
                query_string = query_string.decode()
            query_params = parse_qs(query_string)
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
        return await self.inner(scope, *args, **kwargs)


# Handy shortcut for applying all three layers at once
def AuthMiddlewareStack(inner):
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
