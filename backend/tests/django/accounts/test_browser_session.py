"""Pins the browser session of accepted decision Q8=B (#835).

The browser authenticates with the Django session which ``api/auth/session``
opens, not with a token it has to hold itself. The three leaks this replaces are
asserted here as facts of the answer, not as intentions:

* the login answer carries **no credential**: nothing a script could copy out of
  the response, out of ``localStorage`` or into a WebSocket URL. The knox token
  stays what it always was - the credential of *machine* clients, minted by
  ``api/auth/login`` - and a browser login mints no such row at all;
* the session cookie is the one cookie the browser may not read (``HttpOnly``),
  while the CSRF cookie is the one it must, because a SPA has to repeat its value
  in the ``X-CSRFToken`` header. Those two flags are a decision, so they are
  pinned as a decision (``MrMap/settings.py``);
* logout is server-side: the session row is flushed, so a copy of the cookie
  taken before the logout answers nothing afterwards (#832 for the browser path).

The CSRF half is the price of cookie credentials and is pinned both ways: an
unsafe request which the session authenticates is refused without the header,
and served with it - while the #834 rule holds, the session *stays* valid.
Like the knox views it sits beside, this view renders plain JSON: its own
refusals name the reason in DRF's ``detail`` field, while the JSON:API error
codes of the auth contract are the data endpoints' answer and pinned by
``test_session_lifetime.py``. ``docs/source/administration/authentication.md``
documents the whole contract; the machine token path is left untouched.
"""
import base64
import json
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from knox.models import AuthToken

from MrMap.settings import _cookie_secure_from_env

SESSION_URL = "/api/auth/session"
LOGIN_URL = "/api/auth/login"
WHOAMI_URL = "/api/accounts/who-am-i/"
JSON = "application/json"
JSONAPI = "application/vnd.api+json"
PASSWORD = "not-a-secret-pw1"

SessionStore = import_module(settings.SESSION_ENGINE).SessionStore


def basic_header(username, password):
    """The ``Authorization`` header value of one Basic credential."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


class BrowserSessionTests(TestCase):
    """The verbs of ``api/auth/session`` with a real user behind them."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="session-probe", password=PASSWORD)

    def browser(self):
        """A fresh browser, with the CSRF checks a deployment makes."""
        return Client(enforce_csrf_checks=True)

    def login(self, client, username=None, password=None):
        """The SPA's login: Basic credentials, cookies coming back."""
        return client.post(
            SESSION_URL,
            HTTP_AUTHORIZATION=basic_header(
                username or self.user.username, password or PASSWORD),
            HTTP_ACCEPT=JSON)

    def csrf_header(self, client):
        """The header the SPA builds from the CSRF cookie it was given."""
        return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}

    def who_am_i_id(self, client):
        """Whose ``who-am-i`` the client currently is asked for."""
        response = client.get(WHOAMI_URL, HTTP_ACCEPT=JSONAPI)
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)["data"]["id"]

    # --- the login opens a session and hands out no credential -------------

    def test_the_browser_login_sets_a_session_cookie_and_no_token(self):
        client = self.browser()

        response = self.login(client)

        self.assertEqual(response.status_code, 200, response.content)
        body = json.loads(response.content)
        self.assertTrue(body["authenticated"])
        # the whole point of Q8=B: the answer holds nothing to keep
        self.assertNotIn("token", body)
        self.assertNotIn("key", body)
        self.assertIn("sessionid", response.cookies)
        # and no machine credential was minted on the way
        self.assertEqual(AuthToken.objects.filter(user=self.user).count(), 0)

        self.assertEqual(self.who_am_i_id(client), str(self.user.pk))

    def test_the_session_cookie_is_not_readable_by_javascript(self):
        """``HttpOnly`` on the session, ``SameSite=Lax``, path wide."""
        client = self.browser()

        response = self.login(client)

        cookie = response.cookies["sessionid"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")
        # the CSRF cookie is the deliberate opposite: the SPA must read it
        self.assertFalse(response.cookies["csrftoken"]["httponly"])

    def test_the_cookie_policy_is_a_deployment_decision(self):
        """The flags are set here, not left to whatever the framework ships."""
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, "Lax")
        self.assertFalse(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, "Lax")
        # one knob for both, so no deployment stores one cookie over http
        self.assertEqual(
            settings.SESSION_COOKIE_SECURE, settings.CSRF_COOKIE_SECURE)
        self.assertTrue(
            _cookie_secure_from_env({}, True),
            "a production deployment serves the cookies over TLS by default")
        self.assertFalse(
            _cookie_secure_from_env({}, False),
            "the development stack stays reachable over plain http")
        self.assertFalse(
            _cookie_secure_from_env(
                {"DJANGO_COOKIE_SECURE": "False"}, True),
            "an http-only deployment can opt out explicitly")

    def test_wrong_credentials_open_no_session(self):
        client = self.browser()

        response = self.login(client, password="wrong-on-purpose")

        self.assertEqual(response.status_code, 403, response.content)
        self.assertNotIn("sessionid", response.cookies)
        self.assertIsNone(client.session.get("_auth_user_id"))

    def test_a_caller_without_a_credential_is_refused_by_the_auth_contract(self):
        """No credential answers 403, in this view's plain-JSON shape.

        The machine-readable ``not_authenticated`` code (#834) is the JSON:API
        renderer's answer of the data endpoints, pinned by
        ``test_session_lifetime.py``; this view renders plain JSON like the
        knox views beside it, so the reason arrives in DRF's ``detail`` field
        - and as a 403, not a 401, because the first configured authenticator
        advertises no ``WWW-Authenticate`` scheme.
        """
        response = self.browser().post(SESSION_URL, HTTP_ACCEPT=JSON)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertIn(
            "Authentication credentials were not provided",
            json.loads(response.content)["detail"])

    # --- the session is what authenticates the following requests ----------

    def test_a_live_session_authenticates_without_a_header(self):
        """The browser sends no ``Authorization`` header anywhere any more."""
        client = self.browser()
        self.login(client)

        response = client.get(WHOAMI_URL, HTTP_ACCEPT=JSONAPI)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            json.loads(response.content)["data"]["id"], str(self.user.pk))

    def test_the_endpoint_answers_whether_this_browser_has_a_session(self):
        """The SPA's boot probe: readable anonymously, true once logged in."""
        client = self.browser()

        anonymous = client.get(SESSION_URL, HTTP_ACCEPT=JSON)
        self.assertEqual(anonymous.status_code, 200, anonymous.content)
        self.assertFalse(json.loads(anonymous.content)["authenticated"])
        # the probe is also where a fresh browser learns its CSRF token, because
        # Django only sends that cookie where somebody asks for it
        self.assertIn("csrftoken", anonymous.cookies)

        self.login(client)
        logged_in = client.get(
            SESSION_URL, HTTP_ACCEPT=JSON, **self.csrf_header(client))
        self.assertTrue(json.loads(logged_in.content)["authenticated"])

    # --- CSRF: the price of a cookie credential, pinned from both sides ----

    def test_an_unsafe_session_request_without_the_csrf_header_is_refused(self):
        """403 refuses the request, not the login (#834's contract)."""
        client = self.browser()
        self.login(client)

        refused = client.post(SESSION_URL, HTTP_ACCEPT=JSON)

        self.assertEqual(refused.status_code, 403, refused.content)
        # plain JSON, like the knox views: the refusal names its reason in the
        # ``detail`` text; the JSON:API ``permission_denied`` code is the data
        # endpoints' answer and pinned by test_session_lifetime.py
        self.assertIn(
            "CSRF", json.loads(refused.content)["detail"])
        # the session survived the refusal: it is still the user's own
        self.assertEqual(self.who_am_i_id(client), str(self.user.pk))

        # the same request with the header the browser was given goes through
        allowed = client.post(
            SESSION_URL, HTTP_ACCEPT=JSON, **self.csrf_header(client))
        self.assertEqual(allowed.status_code, 200, allowed.content)

    def test_the_login_response_carries_a_csrf_cookie_of_its_own(self):
        """A plain JSON answer sets no CSRF cookie, so the view asks for it."""
        response = self.login(self.browser())

        self.assertIn("csrftoken", response.cookies)

    # --- logout is server-side ---------------------------------------------

    def test_logout_flushes_the_session_row(self):
        client = self.browser()
        self.login(client)
        session_key = client.session.session_key
        self.assertTrue(SessionStore().exists(session_key))
        self.assertEqual(client.session.get("_auth_user_id"),
                         str(self.user.pk))

        response = client.delete(
            SESSION_URL, HTTP_ACCEPT=JSON, **self.csrf_header(client))

        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(
            SessionStore().exists(session_key),
            "the row behind the cookie is gone, not only the cookie")
        self.assertNotEqual(self.who_am_i_id(client), str(self.user.pk))

    def test_logout_of_an_absent_session_is_answered_like_a_closed_one(self):
        """Idempotent: the client clears its own state either way."""
        response = self.browser().delete(SESSION_URL, HTTP_ACCEPT=JSON)

        self.assertEqual(response.status_code, 204, response.content)

    # --- the machine path keeps working beside it --------------------------

    def test_api_login_still_issues_a_machine_token(self):
        """CLI clients are untouched by the browser migration (#835)."""
        client = self.browser()

        response = client.post(
            LOGIN_URL,
            HTTP_AUTHORIZATION=basic_header(self.user.username, PASSWORD),
            HTTP_ACCEPT=JSON)

        self.assertEqual(response.status_code, 200, response.content)
        issued = json.loads(response.content)
        self.assertIn("token", issued)

        # and that token keeps authenticating on its own, cookie-free
        authenticated = self.browser().get(
            WHOAMI_URL, HTTP_ACCEPT=JSONAPI,
            HTTP_AUTHORIZATION=f"Token {issued['token']}")

        self.assertEqual(authenticated.status_code, 200,
                         authenticated.content)
        self.assertEqual(
            json.loads(authenticated.content)["data"]["id"], str(self.user.pk))
