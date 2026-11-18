"""The login attempt budget of the credential endpoints (#1450).

``api/auth/session`` and ``api/auth/login`` read passwords, and until #1450
they read one per request without limit: DRF shipped no throttle rates, so a
credential guessing tool ran unthrottled against the only anonymous,
password-carrying surface of the API.

What is pinned here is the one property that makes the throttle a protection
and not a statistic: **a refused attempt must count**. DRF checks throttles
*after* authenticating the request, and a wrong password ends the request in
that step - a throttle installed at DRF's standard place would therefore see
only the attempts which succeeded. So ``accounts.throttling`` counts before
the credential is looked at, and the tests below exhaust the budget entirely
with **wrong** credentials - which is exactly what an attacker sends.

The budget is the configured one (``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
["login"]``) lowered to three per minute for the tests, on a private locmem
cache so the counting does not wander into the deployment's Redis and repeated
runs start even. The verbs without a password - the session probe, the logout -
are pinned to cost nothing, and one client's exhaustion is pinned not to
touch another address's budget: the pooling of an entire deployment behind
``REMOTE_ADDR`` would itself be a denial of service.
"""
import base64

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, SimpleTestCase, TestCase, override_settings

from rest_framework.settings import api_settings

SESSION_URL = "/api/auth/session"
LOGIN_URL = "/api/auth/login"
WHOAMI_URL = "/api/accounts/who-am-i/"
JSON = "application/json"
JSONAPI = "application/vnd.api+json"
PASSWORD = "not-a-secret-pw1"
# TEST-NET-3 address of documentation (RFC 5737): another "client" in the test
OTHER_CLIENT = "203.0.113.7"

RATE_OF_THE_TESTS = "3/min"


def basic_header(username, password):
    """The ``Authorization`` header value of one Basic credential."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


def throttled_settings(cls):
    """The production rates replaced by the test budget, on a private cache.

    The base dict is taken from the real settings so the override changes the
    rate and nothing else about the REST framework configuration.
    """
    return override_settings(
        CACHES={"default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "login-throttle-tests"}},
        REST_FRAMEWORK={
            **settings.REST_FRAMEWORK,
            "DEFAULT_THROTTLE_RATES": {"login": RATE_OF_THE_TESTS},
        })(cls)


@throttled_settings
class LoginAttemptThrottleTests(TestCase):
    """The budget of one address, filled entirely with refused attempts."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="throttle-target", password=PASSWORD)

    def setUp(self):
        # the budget of every test starts full
        cache.clear()

    def attempt(self, client=None, url=SESSION_URL, username=None,
                password=None, real_ip=None):
        """One credential-carrying POST; wrong credentials unless told."""
        client = client or Client()
        extra = {"HTTP_ACCEPT": JSON}
        if real_ip:
            extra["HTTP_X_REAL_IP"] = real_ip
        return client.post(
            url,
            HTTP_AUTHORIZATION=basic_header(
                username or self.user.username,
                password if password is not None else "wrong-password"),
            **extra)

    # --- the refused attempts are what fills the budget ---------------------

    def test_wrong_credentials_count_until_the_budget_is_spent(self):
        """The #1450 assertion: refusal by rate, not only by credential.

        Four wrong tries from one address: the endpoint answers the first
        three with its normal credential refusal and the fourth with 429 -
        while the credentials of the fourth request are exactly as wrong as
        the first's. An uncounted flood answers 403 forever.
        """
        for _ in range(3):
            refused = self.attempt()
            self.assertEqual(refused.status_code, 403, refused.content)

        flooded = self.attempt()
        self.assertEqual(flooded.status_code, 429, flooded.content)

    def test_the_right_password_is_answered_by_the_rate_too(self):
        """The budget is per address, not per outcome: success pays in as well.

        Otherwise the throttle would only ever chase the failures a guessing
        tool regenerates instantly, and a caller holding one valid credential
        could mint tokens without any bound.
        """
        self.attempt(password="wrong")
        self.attempt(password="wrong")
        good = self.attempt(password=PASSWORD)
        self.assertEqual(good.status_code, 200, good.content)

        flooded = self.attempt(password=PASSWORD)
        self.assertEqual(flooded.status_code, 429, flooded.content)

    def test_both_credential_endpoints_draw_one_budget(self):
        """Splitting the flood across login and session saves nothing.

        The scope is shared, so an attacker cannot buy two budgets from one
        address by alternating the endpoints.
        """
        self.attempt(url=LOGIN_URL)
        self.attempt(url=SESSION_URL)
        self.attempt(url=LOGIN_URL)

        flooded = self.attempt(url=SESSION_URL)
        self.assertEqual(flooded.status_code, 429, flooded.content)

    def test_the_token_endpoint_refuses_its_own_flood(self):
        """The machine endpoint refuses a flood of guesses the same way."""
        for _ in range(3):
            refused = self.attempt(url=LOGIN_URL)
            self.assertEqual(refused.status_code, 403, refused.content)

        flooded = self.attempt(url=LOGIN_URL)
        self.assertEqual(flooded.status_code, 429, flooded.content)
        # DRF's refusal says how long this window still costs the caller - the
        # header is the whole point of a 429, and it surviving the JSON:API
        # exception handler is what the row in
        # docs/source/administration/authentication.md documents
        wait = int(flooded.headers["Retry-After"])
        self.assertGreaterEqual(wait, 1)
        self.assertLessEqual(wait, 60)

    # --- what the budget does not charge --------------------------------------

    def test_the_password_free_verbs_cost_nothing(self):
        """A spent budget refuses passwords, not sessions.

        The probe and the logout carry no credential; locking them out of a
        budget they never spent would turn the protection into an outage for
        the browser already logged in - the DELETE especially, which is how a
        client closes a session after the password flood of somebody else.
        """
        for _ in range(3):
            self.attempt()

        client = Client()
        probe = client.get(SESSION_URL, HTTP_ACCEPT=JSON)
        self.assertEqual(probe.status_code, 200, probe.content)
        closed = client.delete(SESSION_URL, HTTP_ACCEPT=JSON)
        self.assertEqual(closed.status_code, 204, closed.content)

        # the budget is still spent
        self.assertEqual(self.attempt().status_code, 429)

    def test_the_rest_of_the_api_answers_on_a_spent_budget(self):
        """Throttling lives on the credential endpoints, nowhere else."""
        for _ in range(3):
            self.attempt()

        client = Client()
        whoami = client.get(WHOAMI_URL, HTTP_ACCEPT=JSONAPI)
        self.assertNotEqual(whoami.status_code, 429, whoami.content)

    def test_another_address_keeps_its_budget(self):
        """The client the edge saw decides, not the pooled peer address.

        Behind the frontend's nginx every caller arrives from one container
        address, so a budget on the peer alone is one attacker locking the
        whole deployment out of its logins. The edge names the real client in
        ``X-Real-IP`` (nginx replaces the header, so it is the edge's word and
        not the caller's), and this is the budget split that makes.
        """
        for _ in range(3):
            self.attempt()
        self.assertEqual(self.attempt().status_code, 429)

        other = self.attempt(real_ip=OTHER_CLIENT)
        self.assertEqual(other.status_code, 403, other.content)

    def test_the_budget_lives_in_the_shared_cache(self):
        """The budget is cache state, not process state.

        A deployment runs several workers over several machines; the budget
        only protects when the counting is the shared cache the whole
        application already uses - and the counter carries its own expiry, so
        a spent budget is a window and not a lockout: the forgotten password
        of the morning must not lock its owner out for good.
        """
        for _ in range(3):
            self.attempt()
        self.assertEqual(self.attempt().status_code, 429)

        # the counted window sits in the cache under the throttle's own key
        self.assertIsNotNone(cache.get("throttle_login_127.0.0.1"))


@override_settings(  # the production settings, deliberately not overridden
    CACHES={"default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache"}})
class LoginRateConfigurationTests(SimpleTestCase):
    """The shipped configuration the throttle views depend on."""

    def test_the_shipped_settings_configure_the_login_scope(self):
        """A view can throttle only what the settings rate.

        DRF 3.15 ships the rate table empty and ``LoginAttemptThrottle`` fails
        loudly on a missing scope, so a settings edit which drops the entry
        must fail here rather than leave the endpoints silently unthrottled.
        """
        rate = api_settings.DEFAULT_THROTTLE_RATES.get("login")
        self.assertIsNotNone(rate, "REST_FRAMEWORK drops the login rate")
        num, _, period = rate.partition("/")
        self.assertGreater(int(num), 0)
        self.assertEqual(period, "min")
