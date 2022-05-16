from typing import OrderedDict

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import Client, TransactionTestCase
from django_celery_results.models import TaskResult
from MrMap.asgi import application
from rest_framework.test import APIRequestFactory
from simple_history.models import HistoricalRecords

from notify.models import BackgroundProcess, ProcessNameEnum


class SignalsTestCase(TransactionTestCase):
    fixtures = ['test_users.json']

    def setUp(self):
        self.client = Client()
        self.client.login(username='User1', password='User1')
        # workaround to login a user for WebsocketCommunicator since login is not implemented for this
        # ApplicationCommunicator (see: https://github.com/django/channels/issues/903#issuecomment-365448451)
        self.headers = [(b'origin', b'http://127.0.0.1:8000'), (b'cookie',
                                                                self.client.cookies.output(header='', sep='; ').encode())]

        dummy_request = APIRequestFactory().get(
            path="/api/notify/background-processes/")
        dummy_request.query_params = OrderedDict()

        HistoricalRecords.context.request = dummy_request

    @sync_to_async
    def create_background_process(self):
        background_process = BackgroundProcess.objects.create(
            phase="started",
            process_type=ProcessNameEnum.REGISTERING.value,
            description="register a new service"
        )
        background_process = BackgroundProcess.objects.process_info().get(
            pk=background_process.pk)
        return background_process

    @sync_to_async
    def get_background_process(self, pk):
        return BackgroundProcess.objects.process_info().get(
            pk=pk)

    @sync_to_async
    def create_thread(self, background_process):
        task_result = TaskResult.objects.create(task_id=123)
        task_result.processes.add(background_process)
        return task_result

    @sync_to_async
    def update_thread(self):
        task_result = TaskResult.objects.get(task_id=123)
        task_result.status = "STARTED"
        task_result.meta = "{ \"done\": \"1\", \"total\": \"3\"}"
        task_result.save()
        return task_result

    @sync_to_async
    def delete_pending_task(self):
        return TaskResult.objects.get(task_id=123).delete()

    async def test_signal_events_for_task_result(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path="/ws/default/",
                                             headers=self.headers)
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected)

        # if a BackgroundProcess is created, we shall receive a create event
        background_process = await self.create_background_process()

        response = await communicator.receive_json_from()
        self.assertEqual(response['payload']['type'], "BackgroundProcess")
        self.assertEqual(response['payload']['id'], str(background_process.pk))
        self.assertEqual(response['type'], "backgroundProcesses/created")

        # # if a thread is updated, we shall receive a update event
        # await self.create_thread(background_process)
        # await self.update_thread()
        # background_process = await self.get_background_process(background_process.pk)

        # response = await communicator.receive_json_from()
        # self.assertEqual(response['payload']['type'], "BackgroundProcess")
        # self.assertEqual(response['payload']['id'], str(background_process.pk))
        # self.assertEqual(response['type'], "backgroundProcesses/updated")

        # Close
        await communicator.disconnect()
