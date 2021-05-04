from channels.exceptions import DenyConnection
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model


class NonAnonymousJsonWebsocketConsumer(JsonWebsocketConsumer):
    """
    Only allows non anonymous users to connect
    """

    user = None
    auto_groups = True

    def build_groups(self):
        groups = []
        for organization in self.user.get_organizations():
            groups.append(f'{self.__class__.__name__.lower()}_{organization.name}_observers')
        self.groups = groups

    def websocket_connect(self, message):
        if self.scope['user'].is_anonymous:
            raise DenyConnection
        else:
            self.user = get_user_model().objects.get(username=self.scope['user'].username)
            if self.auto_groups:
                self.build_groups()
            super().websocket_connect(message)

    def send_msg(self, event):
        """
        Default call back function to send messages to the client from the event['msg'] dict attribute.
        """
        self.send_json(content=event['msg'])
