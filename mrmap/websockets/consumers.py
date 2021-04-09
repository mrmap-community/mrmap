import json

from channels.exceptions import DenyConnection
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.test import RequestFactory
from service.tables import PendingTaskTable
from structure.models import PendingTask


class PendingTaskConsumer(JsonWebsocketConsumer):
    user = None
    groups = ['pending_task_observers']

    def send_table_as_html(self, event):
        """
        Call back function to send the changed rendered table to the client
        """
        # todo: for now we send all pending tasks serialized as json
        #  further changes:
        #   * filter by the user object based permissions to show only pending tasks for that the user
        #     has permissions
        #   * check if the self.user has permissions for the instance that is created/modified. If not skip sending
        instance_pk = event['instance_pk']  # the created/modified instance pk

        # create dummy request to render table as html
        pending_tasks = PendingTask.objects.all()
        request = RequestFactory().get('')
        request.user = self.user

        # todo: speed up rendering of PendingTaskTable by using TemplateColumns
        # render the table
        pending_task_table = PendingTaskTable(data=pending_tasks)
        rendered_table = pending_task_table.as_html(request=request)
        self.send_json(content=json.dumps({'rendered_table': rendered_table}))
