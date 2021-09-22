import json
from django.template import Context
from django.test import RequestFactory
from django_tables2 import RequestConfig
from django.contrib.contenttypes.models import ContentType

from jobs.filtersets import JobFilterSet, TaskFilterSet
from jobs.tables import JobTable, TaskTable
from jobs.models import Job, Task
from ws.auth import NonAnonymousJsonWebsocketConsumer
from ws.utils import get_app_view_model
from ws.messages import Toast


class AppViewModelConsumer(NonAnonymousJsonWebsocketConsumer):
    def connect(self):
        super().connect()
        self.update_app_view_model()

    def update_app_view_model(self):
        self.send_msg({'msg': get_app_view_model(self.user)})


class JobTableConsumer(NonAnonymousJsonWebsocketConsumer):

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

        all_task_results = self.user.get_instances(klass=Job)

        job_filterset = JobFilterSet(data=request.GET, queryset=all_task_results)
        if job_filterset.qs:
            # render the table only if the filtered qs in not empty
            job_table = JobTable(data=job_filterset.qs)
            job_table.context = Context()
            job_table.context.update({'filter': job_filterset})

            RequestConfig(request=request, paginate={"per_page": request.GET.get('per_page', 5)}).configure(table=job_table)

            rendered_table = job_table.as_html(request=request)
            self.send_json(content=json.dumps({'rendered_table': rendered_table}))


class TaskTableConsumer(NonAnonymousJsonWebsocketConsumer):

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

        all_task_results = self.user.get_instances(klass=Task)

        task_filterset = TaskFilterSet(data=request.GET, queryset=all_task_results)
        if task_filterset.qs:
            # render the table only if the filtered qs in not empty
            task_table = TaskTable(data=task_filterset.qs)
            task_table.context = Context()
            task_table.context.update({'filter': task_filterset})

            RequestConfig(request=request, paginate={"per_page": request.GET.get('per_page', 5)}).configure(table=task_table)

            rendered_table = task_table.as_html(request=request)
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
