import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.template.loader import render_to_string
from django.test import RequestFactory

from service.tables import PendingTaskTable
from structure.models import PendingTask
from urllib.parse import urlparse, parse_qs


class PendingTaskConsumer(JsonWebsocketConsumer):
    user = None
    groups = ['pending_task_observers']

    def connect(self):
        query_string = parse_qs(self.scope['query_string'].decode("utf-8"))
        try:
            # try to get the user object from db. For further usage we need to get the user which opened the
            # ws connection. Use cases are: filter PendingTask objects by user.organization membership

            # WARNING !!!: this is not secure. Anyone with username knowledge could pass the username in the header and
            # get all data based on the given username.

            self.user = get_user_model().objects.get(username=query_string['username'][0])
            self.accept()
        except ObjectDoesNotExist:
            # provided username does not exist
            self.close()
        except KeyError:
            # no user provided with the header
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
        print('send_table_as_html called')
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
