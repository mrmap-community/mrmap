"""Tests of the one-time WebSocket ticket (#1472).

The store lives in the default cache; like the login throttle tests
(``tests/django/accounts/test_login_throttle.py``) these run on a private locmem
cache so nothing wanders into the Redis of a development deployment.
"""
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, TransactionTestCase, override_settings
from knox.models import AuthToken
from MrMap.asgi import application
from notify.ws_ticket import (TICKET_TTL_SECONDS, consume_ticket,
                              mint_ticket)
from rest_framework.test import APIClient

PRIVATE_CACHE = override_settings(
    CACHES={'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ws-ticket-tests',
    }}
)


@PRIVATE_CACHE
class WsTicketStoreTestCase(TestCase):
    """The store itself: single use, expiry, and a gone user."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='ticket-user', password='ticket-password')

    def test_a_minted_ticket_authenticates_its_user(self):
        ticket = mint_ticket(self.user.pk)
        self.assertEqual(consume_ticket(ticket), self.user)

    def test_a_ticket_authenticates_once(self):
        ticket = mint_ticket(self.user.pk)
        consume_ticket(ticket)
        self.assertIsNone(consume_ticket(ticket))

    def test_an_unknown_ticket_authenticates_nobody(self):
        self.assertIsNone(consume_ticket('never-minted'))
        self.assertIsNone(consume_ticket(''))
        self.assertIsNone(consume_ticket(None))

    def test_an_unspent_ticket_dies_on_its_own(self):
        ticket = mint_ticket(self.user.pk)
        # what a mint which never reached a handshake leaves behind: not a
        # credential any more once the backend lets the key go
        cache.set(f'notify:ws-ticket:{ticket}', self.user.pk, 0)
        self.assertIsNone(consume_ticket(ticket))
        self.assertEqual(TICKET_TTL_SECONDS, 10)

    def test_a_ticket_minted_for_a_deleted_user_authenticates_nobody(self):
        ticket = mint_ticket(self.user.pk)
        self.user.delete()
        self.assertIsNone(consume_ticket(ticket))

    def test_a_minted_ticket_is_a_long_random_value(self):
        # the value may be logged by the proxy, so it must carry nothing but
        # randomness: no user id, no structure an attacker could exploit
        ticket = mint_ticket(self.user.pk)
        self.assertNotIn(str(self.user.pk), ticket)
        self.assertGreaterEqual(len(ticket), 32)
        self.assertNotEqual(ticket, mint_ticket(self.user.pk))


@PRIVATE_CACHE
class WebsocketTicketEndpointTestCase(TestCase):
    """``POST /api/notify/websocket-ticket`` and the handshake behind it."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='ticket-user', password='ticket-password')

    def _mint(self, **credentials):
        client = APIClient()
        if credentials:
            client.credentials(**credentials)
        return client.post('/api/notify/websocket-ticket', format='json')

    def test_a_token_client_mints_a_ticket(self):
        _instance, token = AuthToken.objects.create(self.user)
        response = self._mint(HTTP_AUTHORIZATION=f'Token {token}')
        self.assertEqual(response.status_code, 200)
        ticket = response.json()['ticket']
        self.assertEqual(response.json()['expires_in'], TICKET_TTL_SECONDS)
        self.assertEqual(consume_ticket(ticket), self.user)

    def test_anonymous_is_refused_and_mints_nothing(self):
        response = self._mint()
        self.assertEqual(response.status_code, 403)
        self.assertNotIn('ticket', response.json())

    def test_only_post_is_offered(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        self.assertEqual(
            client.get('/api/notify/websocket-ticket').status_code, 405)


@PRIVATE_CACHE
class WebsocketHandshakeAuthTestCase(TransactionTestCase):
    """Which credential opens ``/ws/default/`` (#1472)."""

    headers = [(b'origin', b'http://127.0.0.1:8000')]

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='ticket-user', password='ticket-password')

    async def _connect(self, path):
        communicator = WebsocketCommunicator(
            application=application, path=path, headers=self.headers)
        return await communicator.connect()

    async def test_a_ticket_opens_the_socket(self):
        connected, _ = await self._connect(
            f'/ws/default/?ticket={mint_ticket(self.user.pk)}')
        self.assertTrue(connected)

    async def test_a_ticket_opens_the_socket_once(self):
        ticket = mint_ticket(self.user.pk)
        connected, _ = await self._connect(f'/ws/default/?ticket={ticket}')
        self.assertTrue(connected)
        replayed, _ = await self._connect(f'/ws/default/?ticket={ticket}')
        self.assertFalse(replayed)

    async def test_an_unknown_ticket_is_refused(self):
        connected, _ = await self._connect('/ws/default/?ticket=never-minted')
        self.assertFalse(connected)

    async def test_a_query_token_opens_the_socket_in_development(self):
        _instance, token = await database_sync_to_async(AuthToken.objects.create)(self.user)
        connected, _ = await self._connect(f'/ws/default/?token={token}')
        self.assertTrue(connected)

    @override_settings(MRMAP_PRODUCTION=True)
    async def test_a_query_token_is_refused_in_production(self):
        # the audit finding this issue closes: a token in the URL survives in
        # the proxy access log, so a production deployment must not take it
        _instance, token = await database_sync_to_async(AuthToken.objects.create)(self.user)
        connected, _ = await self._connect(f'/ws/default/?token={token}')
        self.assertFalse(connected)

    @override_settings(MRMAP_PRODUCTION=True)
    async def test_a_ticket_still_opens_the_socket_in_production(self):
        connected, _ = await self._connect(
            f'/ws/default/?ticket={mint_ticket(self.user.pk)}')
        self.assertTrue(connected)

    async def test_anonymous_is_refused(self):
        connected, _ = await self._connect('/ws/default/')
        self.assertFalse(connected)
