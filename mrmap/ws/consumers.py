from channels.exceptions import DenyConnection
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from ws.messages import Toast
from ws.utils import get_object_counts


class NonAnonymousJsonWebsocketConsumer(JsonWebsocketConsumer):
    """
    Only allows non anonymous users to connect
    """

    user = None
    auto_groups = True

    def build_groups(self):
        groups = []
        for organization in self.user.organizations:
            groups.append(f'{self.__class__.__name__.lower()}_{organization.pk}_observers')
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


class ObjectCountsConsumer(NonAnonymousJsonWebsocketConsumer):
    def connect(self):
        super().connect()
        self.update_app_view_model()

    def update_app_view_model(self):
        self.send_msg({'msg': get_object_counts(self.user)})


class ToastConsumer(NonAnonymousJsonWebsocketConsumer):
    def send_toast(self, event):
        content_type_id = event['content_type']
        object_id = event['object_id']
        title = event['title']
        body = event['body']
        content_type = ContentType.objects.get(pk=content_type_id)
        obj = content_type.get_object_for_this_type(pk=object_id)
        if self.user.has_perm(f"view_{obj.__class__.__name__.lower()}", obj):
            response = Toast(title=title, body=body).get_response()
            self.send_msg({'msg': response})
