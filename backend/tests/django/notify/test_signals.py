import json
from typing import OrderedDict

from asgiref.sync import sync_to_async
from channels.testing import WebsocketCommunicator
from crum import set_current_request
from django.test import Client, TransactionTestCase
from django.utils import timezone
from django_celery_results.models import TaskResult
from MrMap.asgi import application
from rest_framework.test import APIRequestFactory


class SignalsTestCase(TransactionTestCase):
    fixtures = ['test_users.json']

    def setUp(self):
        self.client = Client()
        self.client.login(username='User1', password='User1')
        # workaround to login a user for WebsocketCommunicator since login is not implemented for this
        # ApplicationCommunicator (see: https://github.com/django/channels/issues/903#issuecomment-365448451)
        self.headers = [(b'origin', b'http://127.0.0.1:8000'), (b'cookie',
                                                                self.client.cookies.output(header='', sep='; ').encode())]

        dummy_request = APIRequestFactory().get(path="/api/notify/task-results/")
        dummy_request.query_params = OrderedDict()

        set_current_request(dummy_request)

    @sync_to_async
    def create_pending_task(self):
        pending_task = TaskResult.objects.create(task_id=123)
        return pending_task

    @sync_to_async
    def get_pending_task(self):
        return TaskResult.objects.get(task_id=123)

    @sync_to_async
    def update_pending_task(self):
        return TaskResult.objects.get(task_id=123).save()

    @sync_to_async
    def delete_pending_task(self):
        return TaskResult.objects.get(task_id=123).delete()

    def get_expected_json(self, task_result):
        return {
            'type': 'taskResults/add',
            'payload': {
                'type': 'TaskResult',
                'id': f'{task_result.id}',
                'attributes': {
                    'task_id': f'{task_result.task_id}',
                    'task_name': None,
                    'task_args': None,
                    'task_kwargs': None,
                    'status': 'PENDING',
                    'worker': None,
                    'content_type': '',
                    'content_encoding': '',
                    'result': {},
                    'date_created': f'{timezone.localtime(task_result.date_created).isoformat()}',
                    'date_done': f'{timezone.localtime(task_result.date_done).isoformat()}',
                    'traceback': None,
                    'task_meta': {}
                },
                'links': {
                    'self': f'http://testserver/api/v1/notify/task-results/{task_result.id}/'
                }
            }
        }

    async def test_signal_events_for_task_result(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path="/ws/default/",
                                             headers=self.headers)
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected)
        # if a TaskResult is created, we shall receive a create event
        task_result = await self.create_pending_task()
        expected_json = self.get_expected_json(task_result)

        response = await communicator.receive_json_from()
        self.assertJSONEqual(raw=json.dumps(response, sort_keys=True),
                             expected_data=json.dumps(expected_json, sort_keys=True))

        task_result = await self.update_pending_task()
        task_result = await self.get_pending_task()
        expected_json = self.get_expected_json(task_result)
        expected_json.update({'type': 'taskResults/update'})

        response = await communicator.receive_json_from()
        self.assertJSONEqual(raw=json.dumps(response, sort_keys=True),
                             expected_data=json.dumps(expected_json, sort_keys=True))

        task_result = await self.get_pending_task()
        expected_json = self.get_expected_json(task_result)
        expected_json.update({'type': 'taskResults/remove'})

        task_result = await self.delete_pending_task()

        response = await communicator.receive_json_from()
        self.assertJSONEqual(raw=json.dumps(response, sort_keys=True),
                             expected_data=json.dumps(expected_json, sort_keys=True))

        # Close
        await communicator.disconnect()
