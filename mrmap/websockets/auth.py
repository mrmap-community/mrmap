from channels.exceptions import DenyConnection
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model


class NonAnonymousJsonWebsocketConsumer(JsonWebsocketConsumer):
    """
    Only allows non anonymous users to connect
    """

    user = None

    def connect(self):
        if self.scope['user'].is_anonymous:
            raise DenyConnection
        else:
            super().connect()
            self.user = get_user_model().objects.get(username=self.scope['user'].username)

