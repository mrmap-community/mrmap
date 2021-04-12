import json

from django.test import RequestFactory
from django_celery_results.models import TaskResult

from service.tables import PendingTaskTable
from websockets.auth import NonAnonymousJsonWebsocketConsumer


class PendingTaskConsumer(NonAnonymousJsonWebsocketConsumer):
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

        # create dummy request to render table as html
        pending_tasks = TaskResult.objects.all()
        request = RequestFactory().get('')
        request.user = self.user

        # todo: speed up rendering of PendingTaskTable by using TemplateColumns
        # render the table
        pending_task_table = PendingTaskTable(data=pending_tasks)
        rendered_table = pending_task_table.as_html(request=request)
        self.send_json(content=json.dumps({'rendered_table': rendered_table}))
