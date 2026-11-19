"""The authentication viewsets are security endpoints (#1446).

``registry/views/security.py`` kept the two ``ServiceAuthentication`` viewsets
as the only security viewsets without ``permission_classes``, and their
serializers answered ``fields='__all__'`` — so an anonymous read of
``/api/registry/security/wms-authentication`` or ``/wfs-authentication``
answered every stored credential: the username, the Fernet ciphertext of the
password and the ``key_file`` member pointing at the key which decrypts it.

These tests pin the closed state: both endpoints refuse an anonymous caller
with ``not_authenticated``, a read answers neither ``password`` nor
``keyFile``, and a write still stores working credentials — the proxy reads
them back through ``decrypt()``, the same way ``registry/tasks/service.py``
and the proxy do. That the proxy keeps authenticating upstream services with
such a record is proven by ``tests/django/registry/mrmap-proxy``.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from registry.enums.service import AuthTypeEnum
from registry.models.security import (WebFeatureServiceAuthentication,
                                      WebMapServiceAuthentication)
from rest_framework.test import APIClient

JSONAPI = "application/vnd.api+json"

#: one entry per endpoint family, both share the view and serializer shape
ENDPOINTS = (
    {
        "url_base": "registry:wmsauth",
        "model": WebMapServiceAuthentication,
        "type": "WebMapServiceAuthentication",
    },
    {
        "url_base": "registry:wfsauth",
        "model": WebFeatureServiceAuthentication,
        "type": "WebFeatureServiceAuthentication",
    },
)


class ServiceAuthenticationApiTest(TestCase):
    """Anonymous refusal and the write-only password on both endpoints."""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="authapi", password="test")
        # guardian maps an anonymous request to this row; a TransactionTestCase
        # run earlier in the same process can flush it (see tests/AGENTS.md)
        get_user_model().objects.get_or_create(username="AnonymousUser")
        self.client = APIClient()
        # without an explicit accept the browsable api renderer is used
        self.client.credentials(HTTP_ACCEPT=JSONAPI)

    def add_payload(self, kind):
        return {
            "data": {
                "type": kind["type"],
                "attributes": {
                    "username": "remote-user",
                    "password": "remote-password",
                    "authType": AuthTypeEnum.BASIC.value,
                },
            }
        }

    def test_anonymous_list_answers_not_authenticated(self):
        """The leak of #1446: the list answered every credential to anyone."""
        for kind in ENDPOINTS:
            with self.subTest(url_base=kind["url_base"]):
                kind["model"].objects.create(
                    username="remote-user", password="remote-password",
                    auth_type=AuthTypeEnum.BASIC.value)
                response = self.client.get(reverse(f"{kind['url_base']}-list"))
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(
                    response.json()["errors"][0]["code"], "not_authenticated")

    def test_anonymous_detail_answers_not_authenticated(self):
        for kind in ENDPOINTS:
            with self.subTest(url_base=kind["url_base"]):
                auth = kind["model"].objects.create(
                    username="remote-user", password="remote-password",
                    auth_type=AuthTypeEnum.BASIC.value)
                response = self.client.get(
                    reverse(f"{kind['url_base']}-detail", args=[auth.pk]))
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(
                    response.json()["errors"][0]["code"], "not_authenticated")

    def test_anonymous_add_is_refused_and_stores_nothing(self):
        for kind in ENDPOINTS:
            with self.subTest(url_base=kind["url_base"]):
                response = self.client.post(
                    reverse(f"{kind['url_base']}-list"),
                    self.add_payload(kind), format="vnd.api+json")
                self.assertEqual(response.status_code, 403, response.content)
                self.assertEqual(
                    response.json()["errors"][0]["code"], "not_authenticated")
                self.assertEqual(kind["model"].objects.count(), 0)

    def test_read_answers_no_password_and_no_key_file(self):
        """Both members belong to the write side only (#1446)."""
        self.client.force_authenticate(self.user)
        for kind in ENDPOINTS:
            with self.subTest(url_base=kind["url_base"]):
                auth = kind["model"].objects.create(
                    username="remote-user", password="remote-password",
                    auth_type=AuthTypeEnum.BASIC.value)
                detail = self.client.get(
                    reverse(f"{kind['url_base']}-detail", args=[auth.pk]))
                self.assertEqual(detail.status_code, 200, detail.content)
                attributes = detail.json()["data"]["attributes"]
                self.assertNotIn("password", attributes)
                self.assertNotIn("keyFile", attributes)
                # the list answers the same resource shape
                listing = self.client.get(reverse(f"{kind['url_base']}-list"))
                self.assertEqual(listing.status_code, 200, listing.content)
                listed = listing.json()["data"][0]["attributes"]
                self.assertNotIn("password", listed)
                self.assertNotIn("keyFile", listed)

    def test_write_stores_credentials_the_proxy_can_decrypt(self):
        """write_only hides the member on reads; the write side keeps working."""
        self.client.force_authenticate(self.user)
        for kind in ENDPOINTS:
            with self.subTest(url_base=kind["url_base"]):
                response = self.client.post(
                    reverse(f"{kind['url_base']}-list"),
                    self.add_payload(kind), format="vnd.api+json")
                self.assertEqual(response.status_code, 201, response.content)
                attributes = response.json()["data"]["attributes"]
                self.assertNotIn("password", attributes)
                self.assertNotIn("keyFile", attributes)

                auth = kind["model"].objects.get()
                # not stored in the clear, and decryptable exactly as the
                # security proxy reads it
                self.assertNotEqual(auth.password, "remote-password")
                self.assertEqual(
                    auth.decrypt(), ("remote-user", "remote-password"))
