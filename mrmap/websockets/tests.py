import json

from asgiref.sync import sync_to_async
from django.core import serializers
from django.test import Client, TransactionTestCase, RequestFactory

from service.tables import PendingTaskTable
from structure.models import PendingTask
from tests.baker_recipes.db_setup import create_superadminuser
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from channels.testing import WebsocketCommunicator
from MrMap.asgi import application


class PendingTaskConsumerTestCase(TransactionTestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        # workaround to login a user for WebsocketCommunicator since login is not implemented for this
        # ApplicationCommunicator (see: https://github.com/django/channels/issues/903#issuecomment-365448451)
        self.headers = [(b'origin', b'http://127.0.0.1:8000'), (b'cookie', self.client.cookies.output(header='', sep='; ').encode())]

    @sync_to_async
    def create_pending_task(self):
        pending_task = PendingTask.objects.create(description='Test')
        return pending_task

    @sync_to_async
    def count_pending_tasks(self):
        return PendingTask.objects.count()

    @sync_to_async
    def all_pending_tasks(self):
        return PendingTask.objects.all()

    @sync_to_async
    def serialize_pending_tasks(self, pending_tasks):
        return serializers.serialize('json', pending_tasks)

    @sync_to_async
    def render_pending_task_table(self, pending_tasks, request):
        pending_task_table = PendingTaskTable(data=pending_tasks)
        return pending_task_table.as_html(request=request)

    async def test_pending_task_consumer_with_session_id(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path=f"/ws/pending-tasks/",
                                             headers=self.headers)
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected)

        # if a PendingTask is created/modified, we shall receive the updated pending task list as json and html
        pending_task = await self.create_pending_task()
        response = await communicator.receive_json_from()
        all_pending_tasks = await self.all_pending_tasks()

        # create dummy request to render table as html
        request = RequestFactory().get('')
        request.user = self.user

        # render the table
        rendered_table = await self.render_pending_task_table(all_pending_tasks, request)
        self.assertEqual(rendered_table, json.loads(response).get('rendered_table'))

        # Close
        await communicator.disconnect()

    async def test_pending_task_consumer_without_session_id(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path=f"/ws/pending-tasks/")
        connected, exit_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(1000, exit_code)

        # Close
        await communicator.disconnect()
