import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core import serializers
from django.template.loader import render_to_string
from django.test import RequestFactory

from service.tables import PendingTaskTable
from structure.models import PendingTask


class PendingTaskConsumer(JsonWebsocketConsumer):
    user = None

    def connect(self):
        print('connect called')
        if "user" in self.scope:
            self.user = self.scope["user"]
            print(self.user)
            if self.user.is_authenticated:
                print('authenticated')
                # get the correct user model object instead of channels.LazyUser
                self.user = get_user_model().objects.get(pk=self.user.pk)
                async_to_sync(self.channel_layer.group_add)("pending_task_observers", self.channel_name)
                self.accept()

    def disconnect(self, code):
        async_to_sync(self.channel_layer.group_discard)("pending_task_observers", self.channel_name)
        self.close()

    def send_table_as_json(self, event):
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
        pending_tasks_json = serializers.serialize('json', pending_tasks)
        self.send_json(content=pending_tasks_json)

    def send_table_as_html(self, event):
        """
        Call back function to send the changed rendered table to the client
        """
        # todo: for now we send all pending tasks serialized as json
        #  further changes:
        #   * filter by the user object based permissions to show only pending tasks for that the user
        #     has permissions
        #   * check if the self.user has permissions for the instance that is created/modified. If not skip sending

        instance_pk = event['instance_pk']  # the created/modified instance

        # create dummy request to render table as html
        pending_tasks = PendingTask.objects.all()
        request = RequestFactory().get('')
        request.user = self.user

        # todo: speed up rendering of PendingTaskTable by using TemplateColumns
        # render the table
        pending_task_table = PendingTaskTable(data=pending_tasks)
        import time
        start = time.time()
        rendered_table = pending_task_table.as_html(request=request)
        end = time.time()
        print('rendering took: ')
        print(end - start)

        pending_tasks_json = serializers.serialize('json', pending_tasks)
        self.send_json(content=json.dumps({'json': pending_tasks_json,
                                           'html': rendered_table}))
