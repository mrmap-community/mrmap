"""Pins the login throttle and the per-user token cap of #1450 (SEC-8).

``POST /api/auth/login`` was the endpoint an anonymous caller could hit
without any limit: no DRF throttle settings existed, and knox ran with its
stock ``TOKEN_LIMIT_PER_USER=None``, so one accepted credential could create
unbounded parallel tokens. ``accounts.views.auth.LoginView`` now throttles
through ``ScopedRateThrottle`` with two scopes declared in
``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` (``login`` per user,
``login_anon`` per client IP; the window lives in the ``default`` cache —
redis — shared by every worker), and ``REST_KNOX`` names the cap explicitly.

What these tests hold:

* refused attempts — wrong credentials *and* no credential at all — are
  counted (DRF would otherwise consult its throttles only after
  authentication and permission have already answered, i.e. never for the
  attempts guessing consists of): after the ``login_anon`` rate the client
  is answered **429**, with DRF's plain ``detail`` body — the login endpoint
  renders plain JSON, not JSON:API (see ``tests/behave/AGENTS.md``), and
  ``UNIFORM_EXCEPTIONS`` is off;
* the refusal is keyed per IP, never per guessed username, and a *valid*
  credential still logs in while that window is full — a guessing client
  cannot use the throttle to lock the honest caller out of the address;
* successful logins count per user against ``login``, so one user's flood
  neither exhausts another's window nor creates token rows without bound;
* ``REST_KNOX["TOKEN_LIMIT_PER_USER"]`` is explicit and enforced by the
  login endpoint: at the cap a further login is a 403 which issues no token,
  expired rows do not occupy a slot, and freeing one opens the gate again.

Each test clears the ``default`` cache first: throttle history is the only
state these tests keep there, it survives the per-test transaction rollback
(caches are not transactional), and without the reset the module would only
pass in one order.
"""
import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import caches
from django.test import Client, TestCase, override_settings
from knox.models import AuthToken
from knox.settings import knox_settings
from rest_framework.throttling import ScopedRateThrottle

LOGIN_URL = "/api/auth/login"


def basic_header(username, password):
    """The ``Authorization`` header value of one Basic credential."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


def rate_requests(scope):
    """The request count of one configured throttle rate ('10/min' -> 10)."""
    rate = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"][scope]
    return int(rate.split("/")[0])


class LoginThrottleTests(TestCase):
    """The two scopes of the login endpoint, probed with real requests."""

    def setUp(self):
        caches["default"].clear()
        self.user = get_user_model().objects.create_user(
            username="throttle-probe", password="not-a-secret-pw1")
        self.client = Client()

    def attempt(self, header=None):
        headers = {"HTTP_ACCEPT": "application/json"}
        if header:
            headers["HTTP_AUTHORIZATION"] = header
        return self.client.post(LOGIN_URL, **headers)

    def test_both_scopes_are_configured(self):
        """The rates are a deployment decision, not a missing setting."""
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        self.assertIn("login", rates)
        self.assertIn("login_anon", rates)

    def test_wrong_credentials_are_throttled_after_the_anon_rate(self):
        """Guessing passwords runs into the IP window: 403s, then a 429."""
        limit = rate_requests("login_anon")
        bad = basic_header(self.user.username, "wrong-password")

        for attempt in range(limit):
            refused = self.attempt(bad)
            self.assertEqual(refused.status_code, 403, refused.content)

        blocked = self.attempt(bad)
        self.assertEqual(blocked.status_code, 429, blocked.content)
        self.assertIn(
            "throttl", json.loads(blocked.content)["detail"].lower())
        # the 429 issued nothing: the throttle answers before token creation
        self.assertEqual(AuthToken.objects.filter(user=self.user).count(), 0)

    def test_a_missing_credential_counts_the_same_window(self):
        """No credential at all shares the guesser's window, not a free one.

        An attempt without credentials is refused by the permission check
        rather than by an authenticator — a different code path than a wrong
        password — so pinning it keeps the view's counting honest for both
        shapes of an anonymous hit.
        """
        limit = rate_requests("login_anon")

        for attempt in range(limit - 1):
            refused = self.attempt()
            self.assertEqual(refused.status_code, 403, refused.content)

        last_before_window_full = self.attempt()
        self.assertEqual(last_before_window_full.status_code, 403,
                         last_before_window_full.content)
        blocked = self.attempt()
        self.assertEqual(blocked.status_code, 429, blocked.content)

    def test_a_valid_credential_survives_a_full_anon_window(self):
        """The lockout targets guessing, never the caller behind the IP.

        A poisoned IP window must not deny the honest user on that address:
        the accepted attempt lands in the per-user window instead and is
        served even while every refused attempt from the same client is 429.
        """
        limit = rate_requests("login_anon")
        bad = basic_header(self.user.username, "wrong-password")
        for attempt in range(limit):
            self.attempt(bad)
        self.assertEqual(self.attempt(bad).status_code, 429)

        good = self.attempt(basic_header(self.user.username,
                                         "not-a-secret-pw1"))
        self.assertEqual(good.status_code, 200, good.content)
        self.assertIn("token", json.loads(good.content))

    def test_accepted_logins_count_per_user_and_stop_other_users_nothing(self):
        """``login`` is keyed by user: one user's flood throttles only itself.

        The rate is patched on the throttle class's own rates dict rather
        than through ``override_settings``: DRF snapshots
        ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`` into
        ``SimpleRateThrottle.THROTTLE_RATES`` at import time and a settings
        reload never rebinds that class attribute. Patching the dict in place
        (restored afterwards) lets the test count three requests instead of
        thirty. ``TOKEN_LIMIT_PER_USER`` is released through a real settings
        override — knox reloads its settings on that signal — because the cap
        would answer 403 before the third login reaches its throttle.
        """
        other = get_user_model().objects.create_user(
            username="throttle-bystander", password="not-a-secret-pw2")

        with patch.dict(ScopedRateThrottle.THROTTLE_RATES, {"login": "2/min"}), \
                override_settings(REST_KNOX={
                    **settings.REST_KNOX, "TOKEN_LIMIT_PER_USER": None}):
            for attempt in range(2):
                first_user = self.attempt(
                    basic_header(self.user.username, "not-a-secret-pw1"))
                self.assertEqual(first_user.status_code, 200,
                                 first_user.content)

            flood = self.attempt(
                basic_header(self.user.username, "not-a-secret-pw1"))
            self.assertEqual(flood.status_code, 429, flood.content)

            bystander = self.attempt(
                basic_header(other.username, "not-a-secret-pw2"))
            self.assertEqual(bystander.status_code, 200, bystander.content)


class TokenLimitPerUserTests(TestCase):
    """The explicit ``TOKEN_LIMIT_PER_USER`` knox's login endpoint enforces."""

    def setUp(self):
        caches["default"].clear()
        self.user = get_user_model().objects.create_user(
            username="tokenlimit-probe", password="not-a-secret-pw1")
        self.client = Client()

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
        # what the login view actually reads is the same value
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
