import json
from django.template import Context
from django.test import RequestFactory
from django_tables2 import RequestConfig
from django.contrib.contenttypes.models import ContentType

from service.filters import PendingTaskFilter
from service.tables import PendingTaskTable
from structure.models import PendingTask
from ws.auth import NonAnonymousJsonWebsocketConsumer
from ws.utils import get_app_view_model
from ws.messages import Toast


class AppViewModelConsumer(NonAnonymousJsonWebsocketConsumer):
    def connect(self):
        super().connect()
        self.update_app_view_model()

    def update_app_view_model(self):
        self.send_msg({'msg': get_app_view_model(self.user)})


class PendingTaskTableConsumer(NonAnonymousJsonWebsocketConsumer):

    def send_table_as_html(self, event):
        """
        Call back function to send the changed rendered table to the client
        """
        # create dummy request to render table as html
        url = self.scope['path']
        if self.scope['query_string']:
            url += f"?{self.scope['query_string'].decode('utf-8')}"

        request = RequestFactory().get(url)
        request.user = self.user

        all_task_results = self.user.get_instances(klass=PendingTask)

        pending_tasks_filterset = PendingTaskFilter(data=request.GET, queryset=all_task_results)
        if pending_tasks_filterset.qs:
            # render the table only if the filtered qs in not empty
            pending_task_table = PendingTaskTable(data=pending_tasks_filterset.qs)
            pending_task_table.context = Context()
            pending_task_table.context.update({'filter': pending_tasks_filterset})

            RequestConfig(request=request).configure(table=pending_task_table)

            rendered_table = pending_task_table.as_html(request=request)
            self.send_json(content=json.dumps({'rendered_table': rendered_table}))


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
