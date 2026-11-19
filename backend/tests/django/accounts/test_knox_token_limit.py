"""The knox token concurrency cap of #1450.

``REST_KNOX["TOKEN_LIMIT_PER_USER"]`` is explicit, and the login endpoint
of #835 — the *machine* path ``POST /api/auth/login`` — enforces it: at the
cap a further login answers knox's own 403 and issues no token, rows whose
expiry has passed do not occupy a slot, and freeing one (a logout, a
deleted row) opens the gate again. The attempt budget in front of this
refusal is a different mechanism and pinned by
``test_login_throttle.py``; what lives here is only what the cap itself
promises, which no other test of the suite would notice if it were dropped
back to knox's stock default of unlimited parallel tokens.

Test isolation is by *key*, not by clearing the cache: the CI suite runs
``--parallel=4`` over one shared redis, and every POST to a credential
endpoint pays into the per-address login budget of #1450. This module
therefore counts its handful of logins into a client address it owns
(``REMOTE_ADDR``, never the 127.0.0.1 the rest of the suite shares) and
gives its user an explicit pk far above anything the fixtures or the auto
sequences reach. Leftover counters expire with the 60 s window.
"""
import base64
import json
from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from knox.models import AuthToken
from knox.settings import knox_settings

LOGIN_URL = "/api/auth/login"

# Address owned by this module (see the isolation note above).
IP_THIS_MODULE = "10.145.0.10"

# Pk far above any auto sequence or fixture id (see the note above).
PK_TOKEN_LIMIT = 1450000004


def basic_header(username, password):
    """The ``Authorization`` header value of one Basic credential."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


class TokenLimitPerUserTests(TestCase):
    """The explicit ``TOKEN_LIMIT_PER_USER`` knox's login endpoint enforces."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="tokenlimit-probe", password="not-a-secret-pw1",
            pk=PK_TOKEN_LIMIT)
        # own address: the accepted logins below pay into the per-address
        # login budget of #1450, and stay far below 30/min on their own key
        self.client = Client(REMOTE_ADDR=IP_THIS_MODULE)

    def login(self):
        return self.client.post(
            LOGIN_URL,
            HTTP_AUTHORIZATION=basic_header(
                self.user.username, "not-a-secret-pw1"),
            HTTP_ACCEPT="application/json")

    def test_the_cap_is_an_explicit_deployment_decision(self):
        """Configured, not left at the knox default of unlimited tokens."""
        self.assertIn("TOKEN_LIMIT_PER_USER", settings.REST_KNOX)
        self.assertGreaterEqual(settings.REST_KNOX["TOKEN_LIMIT_PER_USER"], 1)
        # knox resolves its own settings from REST_KNOX at import; what the
        # login view reads must be the value the deployment wrote
        self.assertEqual(
            knox_settings.TOKEN_LIMIT_PER_USER,
            settings.REST_KNOX["TOKEN_LIMIT_PER_USER"])

    def test_below_the_cap_the_login_is_served(self):
        cap = settings.REST_KNOX["TOKEN_LIMIT_PER_USER"]
        for _ in range(cap - 1):
            AuthToken.objects.create(self.user)

        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("token", json.loads(response.content))

    def test_at_the_cap_a_further_login_is_refused_without_a_new_token(self):
        cap = settings.REST_KNOX["TOKEN_LIMIT_PER_USER"]
        for _ in range(cap):
            AuthToken.objects.create(self.user)

        response = self.login()

        self.assertEqual(response.status_code, 403, response.content)
        # knox's own refusal body — the login view answers plain JSON
        self.assertIn("error", json.loads(response.content))
        self.assertEqual(AuthToken.objects.filter(user=self.user).count(), cap)

    def test_expired_rows_do_not_occupy_a_slot(self):
        """The cap counts *usable* tokens: expiry frees, like a logout."""
        cap = settings.REST_KNOX["TOKEN_LIMIT_PER_USER"]
        for _ in range(cap):
            token, _key = AuthToken.objects.create(self.user)
            token.expiry = datetime.now(timezone.utc) - timedelta(seconds=5)
            token.save()

        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)

    def test_freeing_a_slot_opens_the_gate_again(self):
        """A revoked row — logout, deleted token — is the documented way out."""
        cap = settings.REST_KNOX["TOKEN_LIMIT_PER_USER"]
        tokens = [AuthToken.objects.create(self.user)[0] for _ in range(cap)]

        self.assertEqual(self.login().status_code, 403)

        tokens[0].delete()
        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
