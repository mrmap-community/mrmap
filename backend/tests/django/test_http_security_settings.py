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
    _hsts_seconds_from_env,
    _cors_decisions_from_env,
    CSP_DEFAULT,
    CSP_DEV_CONNECT_SRC,
    _csrf_trusted_origins_from_env,
    _redis_url_authority,
    _secret_key_from_env,
    show_debug_toolbar,
)

VITE = ["http://127.0.0.1:5173", "http://localhost:5173"]
# the conf of the frontend container, one level above the bind mount of the
# backend suite - present on a checkout, absent inside the QA image
EDGE_CONF = pathlib.Path(__file__).resolve().parents[3] / "docker" / "nginx" / "mrmap.conf"
COMPOSE_FILE = pathlib.Path(__file__).resolve().parents[3] / "docker-compose.yml"


def _directives(policy: str) -> list:
    """The directives of a policy, normalized, in policy order.

    Both copies of the shipped policy are compared like this, and a wildcard
    source is looked for like this, because a browser enforces the intersection
    of the two and nobody sees the side which lost.
    """
    return sorted(part.strip() for part in policy.strip().rstrip(";").split(";") if part.strip())


def _scheme_sources(policy: str) -> list:
    """Sources which name a scheme but no host, e.g. ``wss:`` in ``connect-src``.

    CSP matches such a source against *every* address of that scheme, so it is
    not a narrowed source but a wildcard wearing one.
    """
    offenders = []
    for directive in _directives(policy):
        if not directive.startswith("connect-src"):
            continue
        offenders += [source for source in directive.split()[1:]
                      if source.endswith(":") and not source.startswith("'")]
    return offenders


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

    def test_a_blank_value_is_not_a_decision(self):
        """An empty ``DJANGO_COOKIE_SECURE`` must not drop ``Secure`` from prod.

        Blank is what an unset variable looks like once anything has passed it
        through - a compose ``"${VAR:-}"`` pass-through, a CI export, an ``.env``
        line written without a value. Reading it as ``False`` would ship a
        production session cookie over plain http on the strength of a value
        nobody wrote, which is the opposite of what the block is for, and it is
        what the page of this block already promises: "(including an empty value)
        means 'use the default'".
        """
        for blank in ("", "   ", "\t"):
            with self.subTest(value=repr(blank)):
                self.assertTrue(_cookie_secure_from_env({"DJANGO_COOKIE_SECURE": blank}, True))
                self.assertFalse(_cookie_secure_from_env({"DJANGO_COOKIE_SECURE": blank}, False))

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
                self.assertEqual(
                    _scheme_sources(policy), [],
                    f"a scheme source in connect-src admits that scheme to every "
                    f"host, which is the channel this policy exists to close "
                    f"(production={production})")
                # what the frontend really loads, or the shipped UI breaks
                for source in ("https://unpkg.com", "https://cdn.jsdelivr.net",
                               "https://fonts.googleapis.com",
                               "https://fonts.gstatic.com",
                               "https://*.tile.openstreetmap.org"):
                    self.assertIn(source, policy)
                for directive in ("object-src 'none'", "base-uri 'self'",
                                  "form-action 'self'", "frame-ancestors 'none'"):
                    self.assertIn(directive, policy)

    def test_production_connect_src_names_no_socket_but_the_own_origin(self):
        """The socket of the shipped SPA is same-origin, so it needs no source.

        ``RealtimeBus.tsx`` builds it from ``VITE_API_BASE_URL``/``VITE_API_PORT``,
        which ``docker-compose.yml`` feeds from ``EXTERNAL_BASE_URL``/
        ``EXTERNAL_PORT`` - the host and port the SPA was loaded from, which the
        edge also serves ``/ws/`` on. CSP normalizes ``wss`` to ``https`` when it
        matches a source, so ``'self'`` covers it and a source of its own would
        only be breadth.
        """
        policy = _content_security_policy_from_env({}, True)
        connect = [d for d in _directives(policy) if d.startswith("connect-src")]
        self.assertEqual(connect, ["connect-src 'self'"])

    def test_only_the_development_topology_may_reach_a_second_socket_origin(self):
        """The vite dev server proxies nothing, so its sockets are cross-origin.

        A page on ``:5173`` reaches the backend on ``:8001``, which ``'self'``
        does not admit - so the two loopback sockets join outside production, the
        way the vite origins join ``CSRF_TRUSTED_ORIGINS``, and never in
        production, where the same breadth would be a pivot inside the operator's
        own network.
        """
        dev = _content_security_policy_from_env({}, False)
        for socket in ("ws://localhost:8001", "ws://127.0.0.1:8001"):
            self.assertIn(socket, dev)
        self.assertEqual(CSP_DEV_CONNECT_SRC.split(),
                         ["ws://localhost:8001", "ws://127.0.0.1:8001"])
        prod = _content_security_policy_from_env({}, True)
        self.assertNotIn("8001", prod)
        self.assertNotIn("ws:", prod.replace("wss:", ""))

    def test_a_wildcard_socket_in_the_shipped_policy_is_refused_at_import(self):
        """The guard, not a browser console, finds a ``wss:`` in the default.

        Both copies of the policy ship as constants, so the failure mode this
        guards against is an edit to one of them - which is exactly what the
        scheme source of #1473 was.
        """
        from MrMap.settings import _shipped_policy_has_no_wildcard_socket
        for wildcard in ("wss:", "ws:"):
            with self.subTest(wildcard=wildcard):
                tampered = CSP_DEFAULT.replace(
                    "connect-src 'self'", f"connect-src 'self' {wildcard}")
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    _shipped_policy_has_no_wildcard_socket(tampered)
                self.assertIn(wildcard, str(ctx.exception))
        # a narrowed policy of the same shape is not refused
        _shipped_policy_has_no_wildcard_socket(CSP_DEFAULT)

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

        edge_policy = edge.group(1)
        self.assertEqual(_directives(edge_policy), _directives(CSP_DEFAULT))
        # the guard above covers settings.py; the edge is the second copy of the
        # policy and the one a browser enforces against the SPA, so it is asked
        # the same question here rather than trusted to drift in step
        self.assertEqual(
            _scheme_sources(edge_policy), [],
            "the edge carries a scheme source in connect-src: it admits that "
            "scheme to every host for the whole SPA")


class TransportSecurityEnvTests(SimpleTestCase):
    """The non-boolean knobs of the block, and what an empty value means.

    ``_flag_from_env`` already treats blank as "no decision". These four are read
    without it, and each would otherwise take a blank value as an answer: an empty
    ``DJANGO_SECURE_HSTS_SECONDS`` does not even parse, and an empty
    ``DJANGO_SECURE_REFERRER_POLICY`` or ``DJANGO_X_FRAME_OPTIONS`` answers a
    header with no value, which is no header. Same failure, same fix, and the
    reason the pass-through in ``docker-compose.yml`` declares these names without
    a value rather than with the ``"${VAR:-}"`` fallback the neighbouring knobs
    use.
    """

    def test_hsts_seconds_blank_is_the_default_of_the_mode(self):
        self.assertEqual(_hsts_seconds_from_env({"DJANGO_SECURE_HSTS_SECONDS": ""}, True),
                         31536000)
        self.assertEqual(_hsts_seconds_from_env({"DJANGO_SECURE_HSTS_SECONDS": "  "}, False), 0)

    def test_hsts_seconds_accepts_the_number_it_was_given(self):
        self.assertEqual(_hsts_seconds_from_env({"DJANGO_SECURE_HSTS_SECONDS": "600"}, True), 600)
        self.assertEqual(_hsts_seconds_from_env({"DJANGO_SECURE_HSTS_SECONDS": "0"}, True), 0)

    def test_hsts_seconds_refuses_what_is_not_a_count_of_seconds(self):
        """Never guess at a one-way door.

        ``Strict-Transport-Security`` is remembered by the browser, so a max-age
        read as something else than written can lock a deployment out of its own
        https - or send no header when a year was meant. Both directions fail the
        deployment while the settings load, naming the rejected value.
        """
        for bad in ("1y", "31536000s", "a year", "1_000", "-5"):
            with self.subTest(value=bad):
                with self.assertRaises(ImproperlyConfigured) as ctx:
                    _hsts_seconds_from_env({"DJANGO_SECURE_HSTS_SECONDS": bad}, True)
                self.assertIn(bad, str(ctx.exception))


class ComposePassThroughTests(SimpleTestCase):
    """The documented opt-outs have to reach Django through the shipped stack.

    ``docker-compose.yml`` interpolates ``.env`` only into the entries it declares
    - it never injects the file - so a knob which is not named there cannot be set
    by the operator who follows ``docs/source/development/environment.rst``. That
    is a compose question, and the compose file is one directory above the bind
    mount of this suite: absent inside the QA image, present on a checkout, where
    the check is real. It reads the file as text rather than as YAML, so the
    runner needs no extra dependency and the check asks the question the settings
    actually care about - is this name passed, and is it passed *without* a value.
    """

    # every knob the transport-security section of environment.rst documents
    KNOBS = [
        "DJANGO_SECURE_SSL_REDIRECT",
        "DJANGO_SECURE_HSTS_SECONDS",
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
        "DJANGO_SECURE_HSTS_PRELOAD",
        "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF",
        "DJANGO_SECURE_REFERRER_POLICY",
        "DJANGO_X_FRAME_OPTIONS",
        "DJANGO_COOKIE_SECURE",
        "DJANGO_CORS_ALLOWED_ORIGINS",
        "DJANGO_CSRF_TRUSTED_ORIGINS",
        "DJANGO_CONTENT_SECURITY_POLICY",
    ]

    def _service_block(self, compose: str, service: str) -> str:
        """The lines of one service, from its name to the next service."""
        lines = compose.splitlines()
        out, inside = [], False
        for line in lines:
            if line.startswith(f"  {service}:"):
                inside = True
                continue
            if inside and line.startswith("  ") and not line.startswith("    "):
                break
            if inside:
                out.append(line)
        self.assertTrue(out, f"no service named {service} in docker-compose.yml")
        return "\n".join(out)

    def _declaration(self, block: str, knob: str):
        """The value part of the line which declares ``knob``, or ``None``.

        Returns the text after the colon - empty for a name declared without a
        value, ``"${KNOB:-}"`` for the fallback form - so both questions, is it
        declared and is it declared *without* a value, are answered from the one
        line the settings actually depend on.
        """
        for line in block.splitlines():
            stripped = line.strip()
            if stripped == f"{knob}:" or stripped.startswith(f"{knob}: "):
                self.assertTrue(line.startswith("      "),
                                f"{knob} is not declared inside the service block")
                return stripped[len(knob) + 1:].strip()
        return None

    def test_every_opt_out_is_passed_to_which_imports_the_settings(self):
        if not COMPOSE_FILE.is_file():
            self.skipTest(f"no {COMPOSE_FILE} on this runner")
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        for service in ("backend", "celery-worker", "celery-beat"):
            block = self._service_block(compose, service)
            for knob in self.KNOBS:
                with self.subTest(service=service, knob=knob):
                    self.assertIsNotNone(
                        self._declaration(block, knob),
                        f"{knob} is not declared for {service}, so an operator who "
                        f"sets it in .env per the documentation narrows nothing")

    def test_the_knobs_are_declared_without_an_empty_fallback(self):
        """``NAME: "${NAME:-}"`` would set the knob to "" - and "" is an answer.

        For this family an empty value means "off": no ``Secure`` on the session
        cookie, no policy at all on a production response. A pass-through written
        that way would weaken the deployment it wires, which is how a review fix
        turns into a regression; declaring the name with no value leaves it absent
        from the container when nothing supplies it, so settings.py sees no value
        and keeps the default of the deployment mode.
        """
        if not COMPOSE_FILE.is_file():
            self.skipTest(f"no {COMPOSE_FILE} on this runner")
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        for service in ("backend", "celery-worker", "celery-beat"):
            block = self._service_block(compose, service)
            for knob in self.KNOBS:
                with self.subTest(service=service, knob=knob):
                    declared = self._declaration(block, knob)
                    if declared is None:  # the test above reports it
                        continue
                    self.assertEqual(
                        declared, "",
                        f"{knob} is passed to {service} with {declared!r}; a value "
                        f"here is a value the settings read, and an empty one is a "
                        f"decision nobody made")

    def test_no_knob_is_also_carried_by_the_env_file_of_the_image(self):
        """A name declared without a value is removed when nothing sets it - the
        ``env_file`` included. None of these knobs may therefore live in
        ``docker/backend/.mrmap.env`` as well, or the pass-through would silently
        stop working for whoever put it there.
        """
        env_file = COMPOSE_FILE.parent / "docker" / "backend" / ".mrmap.env"
        if not env_file.is_file():
            self.skipTest(f"no {env_file} on this runner")
        names = {line.split("=", 1)[0].strip()
                 for line in env_file.read_text(encoding="utf-8").splitlines()
                 if "=" in line and not line.lstrip().startswith("#")}
        for knob in self.KNOBS:
            self.assertNotIn(
                knob, names,
                f"{knob} is set in the image's env_file and declared without a "
                f"value in docker-compose.yml: the compose entry wins and drops it")


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
