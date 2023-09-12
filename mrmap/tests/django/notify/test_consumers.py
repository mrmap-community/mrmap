
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import Client, TransactionTestCase
from knox.models import AuthToken
from MrMap.asgi import application


class PendingTaskConsumerTestCase(TransactionTestCase):
    fixtures = ['test_users.json']

    def setUp(self):
        instance, token = AuthToken.objects.create(
            get_user_model().objects.get(username="User1"))
        self.token = token
        self.client = Client()
        self.client.login(username='User1', password='User1')
        # workaround to login a user for WebsocketCommunicator since login is not implemented for this
        # ApplicationCommunicator (see: https://github.com/django/channels/issues/903#issuecomment-365448451)
        self.headers = [(b'origin', b'http://127.0.0.1:8000'), (b'cookie',
                                                                self.client.cookies.output(header='', sep='; ').encode())]

    async def test_auth_on_default_consumer_without_user(self):
        # test connection established for authenticated user
        communicator = WebsocketCommunicator(application=application,
                                             path="/ws/default/")
        connected, exit_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(1000, exit_code)

        # Close
        await communicator.disconnect()

    async def test_auth_on_default_consumer_with_session_auth(self):
        # test connection established for authenticated user with session cookie authentication method
        communicator = WebsocketCommunicator(application=application,
                                             path="/ws/default/",
                                             headers=self.headers)
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected)

        # Close
        await communicator.disconnect()

    async def test_auth_on_default_consumer_with_token_auth(self):
        # test connection established for authenticated user with session cookie authentication method
        communicator = WebsocketCommunicator(application=application,
                                             path=f"/ws/default/?token={self.token}&something=anything",
                                             headers=[(b'origin', b'http://127.0.0.1:8000')])
        connected, exit_code = await communicator.connect()
        self.assertTrue(connected)

        # Close
        await communicator.disconnect()
