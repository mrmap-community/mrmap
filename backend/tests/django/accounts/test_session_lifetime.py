"""Pins the session lifetime and the auth-vs-denied contract of #834.

The browser's credential is the knox token that ``api/auth/login`` issues
(until #835 migrates browser auth to Django sessions). Its validity is
configured explicitly in ``MrMap/settings.py`` as ``REST_KNOX`` - one working
day, no automatic refresh - instead of silently inherited from the knox
package default. ``tests/django/accounts/test_logout_revokes_token.py``
already pins that a logout deletes the row; these tests hold the lifetime
itself and the answer a dead or refused credential gets:

* a login honours the configured ``TOKEN_TTL``: the ``AuthToken`` row expires
  at creation plus that exactly-documented span, and the ``expiry`` the login
  response hands the client is that same moment - one value, so the client can
  never "stay valid" past what the server enforces;
* an expired token is refused like an unknown one, and the refusal names its
  reason: mrmap answers both an unauthenticated caller and an expired
  credential with **403** - DRF keeps the 401 only when the *first* configured
  authenticator offers a ``WWW-Authenticate`` scheme and ``SessionAuthentication``
  has none - so the deliberate contract lives in the JSON:API error **code**:
  ``authentication_failed`` (the presented token is dead), ``not_authenticated``
  (no credential at all) versus ``permission_denied`` (a valid credential whose
  caller may not do this). The frontend distinguishes exactly that (#834);
* anonymous ``who-am-i`` stays answerable (the anonymous read-only baseline of
  #833): the identity probe of the frontend contract relies on a dead token
  being refused while the same request without one is served.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from knox.models import AuthToken

LOGIN_URL = "/api/auth/login"
WHOAMI_URL = "/api/accounts/who-am-i/"
JSONAPI = "application/vnd.api+json"


def basic_header(username, password):
    """The ``Authorization`` header value of one Basic credential."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


def parse_expiry(value):
    """The login response's ``expiry`` as an aware datetime (Z-suffix safe)."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class SessionLifetimeTests(TestCase):
    """One probe user: login, expiry, refusal - all with real credentials."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="lifetime-probe", password="not-a-secret-pw1")
        self.client = Client()

    def login(self, username=None, password=None):
        """A Basic login through the real endpoint; answers the raw response."""
        return self.client.post(
            LOGIN_URL,
            HTTP_AUTHORIZATION=basic_header(
                username or self.user.username, password or "not-a-secret-pw1"),
            HTTP_ACCEPT="application/json")

    def auth(self, key):
        return {"HTTP_AUTHORIZATION": f"Token {key}"}

    def test_ttl_is_an_explicit_deployment_decision(self):
        """The lifetime is configured, not left to the knox package default."""
        self.assertIn("TOKEN_TTL", settings.REST_KNOX)
        self.assertIn("AUTO_REFRESH", settings.REST_KNOX)
        self.assertFalse(settings.REST_KNOX["AUTO_REFRESH"])
        self.assertGreater(settings.REST_KNOX["TOKEN_TTL"], timedelta(0))

    def test_login_honours_the_configured_ttl(self):
        """Row and answer agree on ``created + configured TTL`` - one moment."""
        ttl = settings.REST_KNOX["TOKEN_TTL"]

        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        body = json.loads(response.content)
        self.assertIn("token", body)
        token = AuthToken.objects.get(user=self.user)
        self.assertTrue(token.created)

        # the server-side enforcement point: the row the request check reads
        self.assertAlmostEqual(
            (token.expiry - token.created).total_seconds(),
            ttl.total_seconds(), delta=2)
        # the client's copy of that very moment; it can never outlive the row
        self.assertAlmostEqual(
            (parse_expiry(body["expiry"]) - token.created).total_seconds(),
            ttl.total_seconds(), delta=2)

    def test_an_expired_token_is_refused_and_names_the_reason(self):
        """Expired means gone: the 403's code is ``authentication_failed``."""
        token, key = AuthToken.objects.create(self.user)
        token.expiry = datetime.now(timezone.utc) - timedelta(seconds=5)
        token.save()

        response = self.client.get(
            WHOAMI_URL, HTTP_ACCEPT=JSONAPI, **self.auth(key))

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(
            json.loads(response.content)["errors"][0]["code"],
            "authentication_failed")

    def test_an_anonymous_caller_is_refused_apart_from_a_dead_token(self):
        """No credential at all answers code ``not_authenticated``, same 403.

        The status cannot tell the two apart in this authentication stack
        (compare the ``authentication_failed`` of the dead token above); the
        code is the deliberate contract the frontend's ``checkError`` reads,
        and it keeps reading it after #835 replaces the credential.
        """
        definitions = self.client.get(
            reverse("accounts:roledefinition-list"), HTTP_ACCEPT=JSONAPI)

        self.assertEqual(definitions.status_code, 403, definitions.content)
        self.assertEqual(
            json.loads(definitions.content)["errors"][0]["code"],
            "not_authenticated")

    def test_the_identity_endpoint_stays_readable_anonymously(self):
        """Precondition of the distinction above: no token answers who-am-i.

        The refusal of the dead credential in the other tests is only
        meaningful because the *absence* of a token is served here - which is
        also the anonymous read-only baseline #833 keeps.
        """
        response = self.client.get(
            WHOAMI_URL, HTTP_ACCEPT=JSONAPI)

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_live_token_without_the_right_answers_permission_denied(self):
        """The valid-credential half of the contract: code ``permission_denied``.

        A plain user may read the role definition catalogue but the platform
        alone writes it - the 403 then carries a different code than a dead
        credential, and it must never be answered like one: the session behind
        a ``permission_denied`` stays valid (#834's 403-keeps-the-session).
        """
        response = self.login()
        key = json.loads(response.content)["token"]

        refused = self.client.post(
            reverse("accounts:roledefinition-list"),
            data="{}",
            content_type=JSONAPI,
            HTTP_ACCEPT=JSONAPI,
            **self.auth(key))

        self.assertEqual(refused.status_code, 403, refused.content)
        self.assertEqual(
            json.loads(refused.content)["errors"][0]["code"],
            "permission_denied")

        # the same credential still answers - 403 did not eat the session
        still_live = self.client.get(WHOAMI_URL, **self.auth(key))
        self.assertEqual(still_live.status_code, 200, still_live.content)
