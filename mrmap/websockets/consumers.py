from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer


class PendingTaskConsumer(JsonWebsocketConsumer):
    user = None

    def connect(self):
        if "user" in self.scope:
            self.user = self.scope["user"]
            if self.user.is_authenticated:
                print('authenticated user')
                async_to_sync(self.channel_layer.group_add)("pending_task_observers", self.channel_name)

                # Make a database row with our channel name
                #Clients.objects.create(channel_name=self.channel_name, consumer='PendingTaskConsumer')
                self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)("pending_task_observers", self.channel_name)
        # Note that in some rare cases (power loss, etc) disconnect may fail
        # to run; this naive example would leave zombie channel names around.
        #Clients.objects.filter(channel_name=self.channel_name, consumer='PendingTaskConsumer').delete()
        self.close()

    def send_message(self, event):
        """
        Call back function to send message to the client
        """
        print('send_message called')
        self.send_json(content=event["text"])

