import json

from asgiref.sync import async_to_sync, sync_to_async
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.core import serializers
from django.test import Client, TransactionTestCase

from structure.models import PendingTask
from tests.baker_recipes.db_setup import create_superadminuser, create_pending_task, create_guest_groups
from tests.baker_recipes.structure_app.baker_recipes import PASSWORD
from websockets.consumers import PendingTaskConsumer
from channels.testing import WebsocketCommunicator
from MrMap.asgi import application


class PendingTaskConsumerTestCase(TransactionTestCase):

    def setUp(self):
        self.user = create_superadminuser()
        self.client = Client()
        self.client.login(username=self.user.username, password=PASSWORD)
        # workaround to login a user for WebsocketCommunicator since login is not implemented for this
        # ApplicationCommunicator (see: https://github.com/django/channels/issues/903#issuecomment-365448451)
        self.headers = [(b'origin', b'...'), (b'cookie', self.client.cookies.output(header='', sep='; ').encode())]

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

    async def test_pending_task_consumer(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path="/ws/pending-task/",
                                             headers=self.headers)
        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        # if a PendingTask is created/modified, we shall receive the updated pending task list as json
        pending_task = await self.create_pending_task()
        response = await communicator.receive_json_from()
        all_pending_tasks = await self.all_pending_tasks()
        pending_tasks_json = await self.serialize_pending_tasks(all_pending_tasks)
        self.assertJSONEqual(pending_tasks_json, json.loads(response))

        # Close
        await communicator.disconnect()
