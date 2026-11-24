"""How the transport-security settings are derived from the environment (#1473).

Audit SEC-12 names the settings which let a deployment run unprotected by
default: the ``CORS_ALLOW_ALL_ORIGINS`` fallback, the ``CSRF_TRUSTED_ORIGINS``
list derived from every host of the allow-list, the random ``SECRET_KEY``
fallback and the debug toolbar which answered every client. All four are decided
by functions of ``MrMap.settings`` which take the environment as an argument, so
the decision is testable without a database and without re-importing the module.
"""

import pathlib
import re
from urllib.parse import unquote

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from MrMap.middleware import ContentSecurityPolicyMiddleware
from MrMap.settings import (
    _content_security_policy_from_env,
    _cookie_secure_from_env,
    _cors_decisions_from_env,
    CSP_DEFAULT,
    _csrf_trusted_origins_from_env,
    _redis_url_authority,
    _secret_key_from_env,
    show_debug_toolbar,
)

VITE = ["http://127.0.0.1:5173", "http://localhost:5173"]
# the conf of the frontend container, one level above the bind mount of the
# backend suite - present on a checkout, absent inside the QA image
EDGE_CONF = pathlib.Path(__file__).resolve().parents[3] / "docker" / "nginx" / "mrmap.conf"


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
            [*VITE, "https://geo.example"])


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


class ContentSecurityPolicyTests(SimpleTestCase):
    """The policy of the backend's own documents, including the error pages.

    The knox token sits in ``localStorage`` and the browser session of #835
    beside it: no cookie flag protects either from script which runs in the
    page, so the header is the layer which stops such script from reaching an
    address it was not given. Two properties are worth pinning: the policy is
    not gated on the deployment mode (a policy only exercised in production
    breaks in production), and the one knob replaces the whole policy rather
    than appending to it - a browser enforces the intersection of every CSP of
    a response, so fragments are how a deployment loses a directive silently.
    """

    def test_shipped_default_in_both_modes(self):
        for production in (True, False):
            with self.subTest(production=production):
                policy = _content_security_policy_from_env({}, production)
                self.assertIn("default-src 'self'", policy)
                # no inline script, which is the point of the header
                self.assertNotIn("script-src 'unsafe-inline'", policy)
                # what the frontend really loads, or the shipped UI breaks
                for source in ("https://unpkg.com", "https://cdn.jsdelivr.net",
                               "https://fonts.googleapis.com",
                               "https://fonts.gstatic.com",
                               "https://*.tile.openstreetmap.org"):
                    self.assertIn(source, policy)
                for directive in ("object-src 'none'", "base-uri 'self'",
                                  "form-action 'self'", "frame-ancestors 'none'"):
                    self.assertIn(directive, policy)

    def test_upgrade_insecure_requests_follows_the_deployment_mode(self):
        self.assertIn("upgrade-insecure-requests",
                      _content_security_policy_from_env({}, True))
        self.assertNotIn("upgrade-insecure-requests",
                         _content_security_policy_from_env({}, False))

    def test_the_knob_replaces_the_whole_policy(self):
        env = {"DJANGO_CONTENT_SECURITY_POLICY": " default-src 'none' "}
        self.assertEqual(_content_security_policy_from_env(env, True),
                         "default-src 'none'")

    def test_an_empty_value_turns_the_header_off(self):
        env = {"DJANGO_CONTENT_SECURITY_POLICY": ""}
        self.assertEqual(_content_security_policy_from_env(env, True), "")

    def test_the_middleware_answers_and_never_overwrites(self):
        """The policy is decided in settings and answered below Security.

        Below ``SecurityMiddleware`` is what makes the 301 of the SSL redirect
        and the 400 of the host validation carry the policy: the error answers
        are where a forged ``X-Forwarded-Host`` and a stored ``http://``
        reference show up.
        """
        factory = RequestFactory()

        def respond(request):
            return HttpResponse("x")

        answered = ContentSecurityPolicyMiddleware(respond)(factory.get("/"))
        self.assertEqual(answered.headers["Content-Security-Policy"],
                         settings.CONTENT_SECURITY_POLICY)

        def respond_own(request):
            response = HttpResponse("x")
            response.headers["Content-Security-Policy"] = "default-src 'none'"
            return response

        kept = ContentSecurityPolicyMiddleware(respond_own)(factory.get("/"))
        self.assertEqual(kept.headers["Content-Security-Policy"],
                         "default-src 'none'")

        with self.settings(CONTENT_SECURITY_POLICY=""):
            off = ContentSecurityPolicyMiddleware(respond)(factory.get("/"))
        self.assertNotIn("Content-Security-Policy", off.headers)

    def test_the_middleware_is_listed_above_security_middleware(self):
        """The policy has to be answered by the outermost middleware.

        A middleware only sees the responses of the ones *below* it, and
        ``SecurityMiddleware`` answers the SSL redirect from inside its own
        request phase without calling further down. Listed below it, this
        middleware would never see that 301 - the one answer of a production
        deployment which every client of a plain-http origin receives.
        """
        middleware = list(settings.MIDDLEWARE)
        self.assertLess(
            middleware.index("MrMap.middleware.ContentSecurityPolicyMiddleware"),
            middleware.index("django.middleware.security.SecurityMiddleware"))

    def test_the_ssl_redirect_carries_the_policy(self):
        """The one answer of a production deployment every client gets.

        A middleware only sees the responses of the ones *below* it, and
        ``SecurityMiddleware`` answers the redirect from inside its own request
        phase without calling further down: listed below it, the policy of
        #1473 would be missing on exactly this response.
        """
        with self.settings(MRMAP_PRODUCTION=True, SECURE_SSL_REDIRECT=True,
                           SECURE_HSTS_SECONDS=31536000):
            redirected = self.client.get("/api/system/info", SERVER_NAME="localhost")
        self.assertEqual(redirected.status_code, 301)
        self.assertEqual(redirected["Content-Security-Policy"],
                         settings.CONTENT_SECURITY_POLICY)

    def test_the_framing_answer_reaches_an_answered_response(self):
        """``X_FRAME_OPTIONS`` needs its middleware, not only its setting.

        The setting is inert without django's clickjacking middleware, which is
        the kind of hygiene that reads as configured and is not; a body a
        browser could frame is only ever an answered document, so that is what
        is measured.
        """
        answered = self.client.get(
            "/api/system/info", HTTP_X_FORWARDED_PROTO="https",
            SERVER_NAME="localhost")
        self.assertIn(answered.status_code, (200, 403))
        self.assertEqual(answered["X-Frame-Options"], settings.X_FRAME_OPTIONS)

    def test_the_edge_answers_the_same_policy(self):
        """The frontend container and the backend may not drift apart.

        The SPA shell is answered by nginx (``docker/nginx/mrmap.conf``), the
        backend's documents by the middleware above. Two copies of one policy
        in two files are one bug waiting to happen - whichever of them a
        developer edits last wins, and a browser enforces the intersection, so
        nobody sees the loss. The shipped policy of both sides is therefore
        compared directive by directive.
        """
        if not EDGE_CONF.is_file():
            # the QA container binds ./backend only, so the edge of the
            # frontend is not inside the image which runs this suite; on a
            # checkout the file is there and the check is real
            self.skipTest(f"no {EDGE_CONF} on this runner")
        edge = re.search(r'set \$mrmap_csp "([^"]+)"',
                         EDGE_CONF.read_text(encoding="utf-8"))
        self.assertIsNotNone(edge, "the edge answers no policy at all")

        def directives(policy):
            return sorted(part.strip() for part in
                          policy.strip().rstrip(";").split(";") if part.strip())

        self.assertEqual(directives(edge.group(1)),
                         directives(CSP_DEFAULT))


class RedisAuthTests(SimpleTestCase):
    """The one credential of the instance which is broker, results and cache.

    Any client which reaches an unauthenticated redis port can enqueue work
    this fleet executes and flush the queue, which voids the broker contract
    of #1618. The URL of the instance is assembled in one function, so its two
    interesting properties are testable without a redis: the credential of a
    deployment with one, and the encoding of a password whose characters would
    otherwise change which host the client connects to.
    """

    def test_passwordless_authority_is_the_plain_host_and_port(self):
        self.assertEqual(_redis_url_authority("", "redis", "6379"), "redis:6379")

    def test_password_joins_as_userinfo(self):
        self.assertEqual(_redis_url_authority("s3cret", "redis", "6379"),
                         ":s3cret@redis:6379")

    def test_a_reserved_character_cannot_escape_the_userinfo(self):
        # "@" in a password is what turns "host" into part of the password and
        # the address after it into the password of nobody, so it must be
        # encoded - and the encoding must be the one redis-py and kombu undo.
        authority = _redis_url_authority("a@b/c:d", "redis", "6379")
        userinfo = authority.split("@")[0][1:]      # strip ":" and the host
        self.assertEqual(unquote(userinfo), "a@b/c:d")
        self.assertEqual(authority, ":a%40b%2Fc%3Ad@redis:6379")

    def test_the_settings_urls_carry_the_password_of_the_environment(self):
        # the module-level values of a deployment which set the variable, read
        # back through the same function the settings used
        self.assertIn(_redis_url_authority(
            settings.REDIS_PASSWORD, settings.REDIS_HOST, settings.REDIS_PORT),
            settings.BROKER_URL)
        self.assertTrue(settings.CELERY_RESULT_BACKEND.startswith(settings.BROKER_URL))
        self.assertTrue(settings.CACHES["default"]["LOCATION"].startswith(settings.BROKER_URL))
        self.assertEqual(
            settings.CHANNEL_LAYERS["default"]["CONFIG"]["hosts"][0]["password"],
            settings.REDIS_PASSWORD)
