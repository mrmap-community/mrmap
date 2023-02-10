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
