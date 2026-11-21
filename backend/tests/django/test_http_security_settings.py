"""How the transport-security settings are derived from the environment (#1473).

Audit SEC-12 names the settings which let a deployment run unprotected by
default: the ``CORS_ALLOW_ALL_ORIGINS`` fallback, the ``CSRF_TRUSTED_ORIGINS``
list derived from every host of the allow-list, the random ``SECRET_KEY``
fallback and the debug toolbar which answered every client. All four are decided
by functions of ``MrMap.settings`` which take the environment as an argument, so
the decision is testable without a database and without re-importing the module.
"""

from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, SimpleTestCase

from MrMap.settings import (
    _cookie_secure_from_env,
    _cors_decisions_from_env,
    _csrf_trusted_origins_from_env,
    _secret_key_from_env,
    show_debug_toolbar,
)

VITE = ["http://127.0.0.1:5173", "http://localhost:5173"]


class SecretKeyTests(SimpleTestCase):
    def test_production_without_a_key_is_refused(self):
        """A random key per boot invalidates every session on restart."""
        with self.assertRaises(ImproperlyConfigured):
            _secret_key_from_env({}, True)

    def test_given_key_wins_in_both_modes(self):
        for production in (True, False):
            with self.subTest(production=production):
                self.assertEqual(
                    _secret_key_from_env({"DJANGO_SECRET_KEY": "given"}, production), "given")

    def test_development_keeps_the_random_fallback(self):
        """A throwaway checkout has no value to keep and must still import."""
        self.assertTrue(_secret_key_from_env({}, False))


class CookieSecureTests(SimpleTestCase):
    def test_mode_default(self):
        self.assertTrue(_cookie_secure_from_env({}, True))
        self.assertFalse(_cookie_secure_from_env({}, False))

    def test_explicit_override_wins_both_ways(self):
        self.assertFalse(_cookie_secure_from_env({"DJANGO_COOKIE_SECURE": "False"}, True))
        self.assertTrue(_cookie_secure_from_env({"DJANGO_COOKIE_SECURE": "True"}, False))


class CsrfTrustedOriginsTests(SimpleTestCase):
    def test_production_without_an_explicit_list_trusts_no_extra_origin(self):
        """The old derivation made every ALLOWED_HOSTS entry a trusted origin."""
        self.assertEqual(_csrf_trusted_origins_from_env({}, True), [])

    def test_production_never_gains_the_http_vite_origins(self):
        self.assertEqual(
            _csrf_trusted_origins_from_env({"DJANGO_ALLOWED_HOSTS": "geo.example"}, True), [])

    def test_explicit_list_is_taken_verbatim(self):
        self.assertEqual(
            _csrf_trusted_origins_from_env(
                {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://geo.example;https://cms.example"}, True),
            ["https://cms.example", "https://geo.example"])

    def test_development_adds_the_vite_origins(self):
        """The development frontend logs in through this backend's session (#835)."""
        self.assertEqual(
            _csrf_trusted_origins_from_env(
                {"DJANGO_CSRF_TRUSTED_ORIGINS": "https://geo.example"}, False),
            ["https://geo.example", *VITE])


class CorsDecisionTests(SimpleTestCase):
    def test_production_without_a_list_allows_no_origin_at_all(self):
        """The removed fallback was CORS_ALLOW_ALL_ORIGINS = True."""
        origins, allow_all, credentials = _cors_decisions_from_env({}, True)
        self.assertEqual(origins, [])
        self.assertFalse(allow_all)
        self.assertFalse(credentials)

    def test_explicit_list_answers_in_both_modes_and_never_allows_all(self):
        for production in (True, False):
            with self.subTest(production=production):
                origins, allow_all, credentials = _cors_decisions_from_env(
                    {"DJANGO_CORS_ALLOWED_ORIGINS": "https://geo.example"}, production)
                self.assertEqual(origins, ["https://geo.example"])
                self.assertFalse(allow_all)
                self.assertEqual(credentials, not production)

    def test_development_allows_the_vite_origins_with_credentials(self):
        origins, allow_all, credentials = _cors_decisions_from_env({}, False)
        self.assertEqual(origins, VITE)
        self.assertFalse(allow_all)
        self.assertTrue(credentials)


class DebugToolbarTests(SimpleTestCase):
    """The callback used to be ``lambda request: True``, for every client."""

    def _get(self, remote_addr):
        return RequestFactory().get("/", REMOTE_ADDR=remote_addr)

    def test_production_never_shows_it(self):
        self.assertFalse(show_debug_toolbar(self._get("127.0.0.1"), production=True))

    def test_development_shows_it_to_loopback_only(self):
        self.assertTrue(show_debug_toolbar(self._get("127.0.0.1"), production=False))
        self.assertFalse(show_debug_toolbar(self._get("203.0.113.7"), production=False))

    def test_named_addresses_join(self):
        self.assertTrue(
            show_debug_toolbar(
                self._get("172.17.0.1"), production=False, internal_ips=["172.17.0.1"]))
