import json

from celery import states
from django.template import Context
from django.test import RequestFactory
from django_celery_results.models import TaskResult
from django_tables2 import RequestConfig

from service.filters import TaskResultFilter
from service.tables import PendingTaskTable
from websockets.auth import NonAnonymousJsonWebsocketConsumer


class PendingTaskTableConsumer(NonAnonymousJsonWebsocketConsumer):
    groups = ['pending_task_table_observers']

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
        url = self.scope['path']
        if self.scope['query_string']:
            url += f"?{self.scope['query_string'].decode('utf-8')}"

        request = RequestFactory().get(url)
        request.user = self.user

        all_task_results = TaskResult.objects.all()

        pending_tasks_filterset = TaskResultFilter(data=request.GET, queryset=all_task_results)
        if pending_tasks_filterset.qs:
            # render the table only if the filtered qs in not empty
            pending_task_table = PendingTaskTable(data=pending_tasks_filterset.qs)
            pending_task_table.context = Context()
            pending_task_table.context.update({'filter': pending_tasks_filterset})

            RequestConfig(request=request).configure(table=pending_task_table)

            rendered_table = pending_task_table.as_html(request=request)
            self.send_json(content=json.dumps({'rendered_table': rendered_table}))


class PendingTaskCountConsumer(NonAnonymousJsonWebsocketConsumer):
    groups = ['pending_task_count_observers']

    old_count = None

    def connect(self):
        super().connect()
        self.send_count(None)

    def send_count(self, event):
        """
        Call back function to send the changed pending task count to the client
        """
        # todo: for now we send all pending tasks serialized as json
        #  further changes:
        #   * filter by the user object based permissions to show only pending tasks for that the user
        #     has permissions
        #   * check if the self.user has permissions for the instance that is created/modified. If not skip sending

        tasks_count = TaskResult.objects.filter(status__in=[states.STARTED, states.PENDING]).count()
        if self.old_count is None or self.old_count != tasks_count:
            # only send message if the count differs
            self.old_count = tasks_count
            response = {'running_tasks_count': tasks_count}
            self.send_json(content=json.dumps(response))
