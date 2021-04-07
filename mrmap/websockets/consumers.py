from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.core import serializers
from structure.models import PendingTask


class PendingTaskConsumer(JsonWebsocketConsumer):
    user = None

    def connect(self):
        if "user" in self.scope:
            self.user = self.scope["user"]
            if self.user.is_authenticated:
                async_to_sync(self.channel_layer.group_add)("pending_task_observers", self.channel_name)
                self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)("pending_task_observers", self.channel_name)
        self.close()

    def send_rendered_table(self, event):
        """
        Call back function to send the changed rendered table to the client
        """
        # todo: for now we send all pending tasks serialized as json
        #  further changes:
        #   * filter by the user object based permissions to show only pending tasks for that the user
        #     has permissions
        #   * check if the self.user has permissions for the instance that is created/modified. If not skip sending

        instance_pk = event['instance_pk']  # the created/modified instance

        pending_tasks = PendingTask.objects.all()
        pending_tasks_qs = serializers.serialize('json', pending_tasks)
        self.send_json(content=pending_tasks_qs)
